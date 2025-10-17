#!/usr/bin/env -S python3 -B -u
"""
TSIM Scheduler Service
Background scheduler with unified execution model.

Execution Modes:
- serial: Jobs execute one at a time (max_workers=1, default)
- parallel: Quick jobs run concurrently (max_workers configurable, typically 33)

Both modes use the same code path - serial is just parallel with max_workers=1.
Configuration: Set "wsgi_execution_mode" in config.json
"""

import time
import json
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, Future


class TsimSchedulerService:
    """Background scheduler with centralized coordination via TsimRegistryManager.

    Unified execution model:
    - Always uses thread pool for execution
    - serial mode: max_workers=1 (one job at a time)
    - parallel mode: max_workers=33 (multiple quick jobs concurrently)

    Mode is configured via wsgi_execution_mode in config.json (default: serial)
    """

    def __init__(self, config_service, queue_service, progress_tracker, executor, lock_manager):
        self.config = config_service
        self.queue = queue_service
        self.progress = progress_tracker
        self.executor = executor
        self.lock_manager = lock_manager
        self.logger = logging.getLogger('tsim.scheduler')

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Execution mode configuration
        # Note: serial is just parallel with max_workers=1
        self.execution_mode = config_service.get('wsgi_execution_mode', 'serial')
        if self.execution_mode not in ['serial', 'parallel']:
            self.logger.error(f"Invalid wsgi_execution_mode '{self.execution_mode}', defaulting to serial")
            self.execution_mode = 'serial'

        # Unified execution infrastructure (always use thread pool)
        self.parallel_config = config_service.get('wsgi_parallel_config', {})
        self.enable_fallback = self.parallel_config.get('enable_fallback_to_serial', True)
        self.log_metrics = self.parallel_config.get('log_execution_metrics', True)

        # Serial mode = parallel mode with max_workers=1
        if self.execution_mode == 'parallel':
            self.max_workers = self.parallel_config.get('thread_pool_workers', 33)
            self.max_quick_jobs = self.parallel_config.get('max_quick_jobs', 32)
        else:
            # Serial mode: override all batch/parallel settings to 1
            self.max_workers = 1
            self.max_quick_jobs = 1
            # Override parallel config to ensure no batching
            self.parallel_config = dict(self.parallel_config)  # Copy
            self.parallel_config['thread_pool_workers'] = 1
            self.parallel_config['max_quick_jobs'] = 1

        self.thread_pool = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix='job-executor')
        self.running_jobs: Dict[str, Dict[str, Any]] = {}
        self.running_lock = threading.Lock()

        self.logger.info(f"Scheduler execution mode: {self.execution_mode} (max_workers={self.max_workers}, max_quick_jobs={self.max_quick_jobs})")

        # Initialize TsimRegistryManager for coordination visibility
        # (scripts initialize their own instances, but this provides monitoring capability)
        self.registry_mgr = None
        try:
            from tsim.core.registry_manager import TsimRegistryManager
            self.registry_mgr = TsimRegistryManager(config_service.config, self.logger)
            self.logger.info("TsimRegistryManager initialized in scheduler")
        except Exception as e:
            self.logger.warning(f"Failed to initialize TsimRegistryManager: {e}")
            self.logger.warning("Coordination will still work (scripts initialize their own instances)")

        # Initialize Quick Job Host Pool Service for quick job execution
        self.host_pool = None
        if self.registry_mgr:
            try:
                from services.tsim_quick_job_host_pool_service import TsimQuickJobHostPoolService

                # Create callback function that returns running jobs from scheduler's internal state
                def get_running_jobs():
                    """Return list of running jobs from scheduler's internal state

                    This is called from two contexts:
                    1. From scheduler thread (with lock held) in _cleanup_completed_jobs()
                    2. From Timer threads (no lock) in host_pool._cleanup_host()

                    To avoid deadlock while maintaining thread safety, we use a snapshot
                    of the running_jobs dict.
                    """
                    # Create snapshot to avoid holding lock during iteration
                    # Use list() to create snapshot of items before iteration
                    try:
                        running_list = []
                        # Make a shallow copy of dict items to avoid RuntimeError during iteration
                        snapshot = list(self.running_jobs.items())
                        for rid, info in snapshot:
                            running_list.append({
                                'run_id': rid,
                                'username': info['job'].get('username'),
                                'status': 'RUNNING',
                                'type': info['type'],
                                'dscp': info.get('dscp'),
                                'started_at': info['started_at'],
                                'params': info['job'].get('params', {})
                            })
                        return running_list
                    except (RuntimeError, KeyError):
                        # Dict changed during iteration - return empty list
                        return []

                self.host_pool = TsimQuickJobHostPoolService(
                    config_service,
                    self.registry_mgr,
                    logger_service=None,
                    queue_service=queue_service,
                    get_running_jobs_fn=get_running_jobs
                )
                self.logger.info("Quick job host pool service initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize host pool service: {e}")
                self.logger.warning("Quick jobs will use fallback mode (individual host creation)")

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name='tsim-scheduler', daemon=True)
        self._thread.start()
        self.logger.info("Scheduler thread started")

    def stop(self, timeout: float = 2.0):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def _run(self):
        # Leader election via file lock in /dev/shm/tsim/locks
        leader_name = 'scheduler_leader'
        while not self._stop_event.is_set():
            # Try to become leader briefly; if not, sleep and retry
            if not self.lock_manager.acquire_lock(leader_name, timeout=0.1, retry_interval=0.05):
                time.sleep(0.5)
                continue
            try:
                # Always use parallel loop (serial mode is just parallel with max_workers=1)
                self._leader_loop_parallel()
            finally:
                self.lock_manager.release_lock(leader_name)
            # Yield to others briefly
            time.sleep(0.25)

    def _leader_loop_parallel(self):
        """While leader, manage job execution via thread pool.

        Used for both serial (max_workers=1) and parallel modes (max_workers=33).
        """
        while not self._stop_event.is_set():
            # Check for completed jobs
            self._cleanup_completed_jobs()

            # Calculate available capacity: max_workers - current running jobs
            with self.running_lock:
                current_running = len(self.running_jobs)
                running_jobs_info = {
                    run_id: {'type': info['type'], 'dscp': info.get('dscp')}
                    for run_id, info in self.running_jobs.items()
                }

            available_slots = self.max_workers - current_running
            if available_slots <= 0:
                # No capacity available - wait for jobs to complete
                time.sleep(0.5)
                continue

            # Pop compatible jobs (limited by available capacity)
            jobs_to_start = self.queue.pop_compatible_jobs(running_jobs_info, max_jobs=available_slots)

            # Debug logging for serial mode
            if jobs_to_start and self.execution_mode == 'serial':
                self.logger.info(f"[SERIAL DEBUG] current_running={current_running}, max_workers={self.max_workers}, "
                               f"available_slots={available_slots}, jobs_popped={len(jobs_to_start)}")

            if not jobs_to_start:
                time.sleep(0.5)
                continue

            # Check if ALL jobs are quick jobs - if so, use host pool service
            all_quick = all(j.get('analysis_mode') == 'quick' for j in jobs_to_start)

            if all_quick and len(jobs_to_start) > 0 and self.host_pool:
                # Use host pool service for quick job execution
                # Works for both serial (batch=1) and parallel (batch=N) modes
                self.logger.info(f"Using host pool for {len(jobs_to_start)} quick job(s)")
                self._start_quick_jobs_batch(jobs_to_start)
            else:
                # Start jobs individually (fallback or detailed jobs)
                for job in jobs_to_start:
                    self._start_job_parallel(job)

            time.sleep(0.25)

    def _start_quick_jobs_batch(self, jobs: List[Dict[str, Any]]):
        """Start batch of quick jobs using host pool service.

        Args:
            jobs: List of quick job dictionaries
        """
        if not jobs:
            return

        self.logger.info(f"Preparing batch of {len(jobs)} quick jobs with host pool")

        # Create executor callback that will be called for each job after hosts are ready
        def executor_callback(job_params: Dict[str, Any], allocated_hosts: Dict[str, Dict]):
            """Callback invoked by host pool after hosts are created"""
            run_id = job_params['run_id']

            # Allocate DSCP for this job
            dscp = None
            try:
                from services.tsim_dscp_registry import TsimDscpRegistry
                dscp_registry = TsimDscpRegistry(self.config)
                dscp = dscp_registry.allocate_dscp(run_id)
                if dscp is None:
                    self.logger.error(f"No DSCP available for quick job {run_id}")
                    self.queue.update_status(run_id, 'FAILED')
                    try:
                        self.progress.log_phase(run_id, 'ERROR', 'No DSCP values available')
                    except Exception:
                        pass
                    # Release hosts since we couldn't start the job
                    if self.host_pool:
                        self.host_pool.release_job(run_id, list(allocated_hosts.keys()))
                    return
            except Exception as e:
                self.logger.error(f"Failed to allocate DSCP for {run_id}: {e}")
                if self.host_pool:
                    self.host_pool.release_job(run_id, list(allocated_hosts.keys()))
                return

            # Add allocated hosts to job params
            job_params['allocated_hosts'] = allocated_hosts
            job_params['host_pool_managed'] = True  # Flag to skip host creation in KSMS

            # Reconstruct job dict from params
            job = {
                'run_id': run_id,
                'username': job_params.get('username'),
                'analysis_mode': 'quick',
                'params': job_params,
                'created_at': job_params.get('created_at')
            }

            # Add to running jobs
            start_time = time.time()
            with self.running_lock:
                self.running_jobs[run_id] = {
                    'type': 'quick',
                    'dscp': dscp,
                    'started_at': start_time,
                    'job': job,
                    'allocated_hosts': list(allocated_hosts.keys())  # Track for cleanup
                }

            # Update queue tracking
            running_list = []
            with self.running_lock:
                for rid, info in self.running_jobs.items():
                    running_list.append({
                        'run_id': rid,
                        'username': info['job'].get('username'),
                        'status': 'RUNNING',
                        'type': info['type'],
                        'dscp': info.get('dscp'),
                        'started_at': info['started_at'],
                        'params': info['job'].get('params', {})
                    })
            self.queue.set_running(running_list)

            # Log start
            if self.log_metrics:
                self.logger.info(f"Starting job {run_id} (mode=quick, dscp={dscp}, hosts={list(allocated_hosts.keys())})")

            # Submit to thread pool
            future = self.thread_pool.submit(self._execute_job_wrapper, job, dscp, start_time)

            with self.running_lock:
                self.running_jobs[run_id]['future'] = future

        # Convert jobs to params format expected by host pool
        job_params_list = []
        for job in jobs:
            params = job.get('params', {})
            params['run_id'] = job['run_id']
            params['username'] = job.get('username')
            params['created_at'] = job.get('created_at')
            job_params_list.append(params)

        # Call host pool service to prepare hosts and execute jobs
        try:
            result = self.host_pool.prepare_and_execute_jobs(job_params_list, executor_callback)

            if not result['success']:
                error_msg = result.get('error', 'Unknown error')
                self.logger.error(f"Host pool batch preparation failed: {error_msg}")

                # Mark failed jobs
                failed_jobs = result.get('failed_jobs', [j['run_id'] for j in jobs])
                for run_id in failed_jobs:
                    self.queue.update_status(run_id, 'FAILED')
                    try:
                        self.progress.log_phase(run_id, 'ERROR', f'Batch preparation failed: {error_msg}')
                    except Exception:
                        pass
            else:
                self.logger.info(f"Successfully launched {result['jobs_launched']}/{len(jobs)} jobs in batch")

        except Exception as e:
            self.logger.error(f"Exception in batch job preparation: {e}", exc_info=True)
            # Mark all jobs as failed
            for job in jobs:
                run_id = job['run_id']
                self.queue.update_status(run_id, 'FAILED')
                try:
                    self.progress.log_phase(run_id, 'ERROR', f'Batch preparation exception: {e}')
                except Exception:
                    pass

    def _start_job_parallel(self, job: Dict[str, Any]):
        """Start a single job in thread pool (used for both serial and parallel modes)."""
        run_id = job.get('run_id')
        analysis_mode = job.get('analysis_mode', 'detailed')
        start_time = time.time()

        # Allocate DSCP for quick jobs
        dscp = None
        if analysis_mode == 'quick':
            try:
                from services.tsim_dscp_registry import TsimDscpRegistry
                dscp_registry = TsimDscpRegistry(self.config)
                dscp = dscp_registry.allocate_dscp(run_id)
                if dscp is None:
                    self.logger.error(f"No DSCP available for quick job {run_id}")
                    self.queue.update_status(run_id, 'FAILED')
                    try:
                        self.progress.log_phase(run_id, 'ERROR', 'No DSCP values available')
                    except Exception:
                        pass
                    return
            except Exception as e:
                self.logger.error(f"Failed to allocate DSCP for {run_id}: {e}")
                return

        # Add to running jobs
        with self.running_lock:
            self.running_jobs[run_id] = {
                'type': analysis_mode,
                'dscp': dscp,
                'started_at': start_time,
                'job': job
            }

        # Update queue tracking
        running_list = []
        with self.running_lock:
            for rid, info in self.running_jobs.items():
                running_list.append({
                    'run_id': rid,
                    'username': info['job'].get('username'),
                    'status': 'RUNNING',
                    'type': info['type'],
                    'dscp': info.get('dscp'),
                    'started_at': info['started_at'],
                    'params': info['job'].get('params', {})
                })
        self.queue.set_running(running_list)

        # Log start if metrics enabled
        if self.log_metrics:
            self.logger.info(f"Starting job {run_id} (mode={analysis_mode}, dscp={dscp})")

        # Submit to thread pool
        future = self.thread_pool.submit(self._execute_job_wrapper, job, dscp, start_time)

        with self.running_lock:
            self.running_jobs[run_id]['future'] = future

    def _execute_job_wrapper(self, job: Dict[str, Any], dscp: Optional[int], start_time: float) -> Dict[str, Any]:
        """Wrapper for job execution with error handling (used for both serial and parallel modes)."""
        run_id = job.get('run_id')
        analysis_mode = job.get('analysis_mode', 'detailed')

        try:
            # Ensure run directory exists
            try:
                self.progress.create_run_directory(run_id)
            except Exception:
                pass

            # Create run.json metadata file (required for admin interface)
            try:
                run_dir = Path(self.config.get('run_dir', '/dev/shm/tsim/runs')) / run_id
                params = job.get('params', {})
                meta = {
                    'run_id': run_id,
                    'username': job.get('username'),
                    'created_at': job.get('created_at'),
                    'params': params,
                    'status': 'RUNNING'
                }
                with open(run_dir / 'run.json', 'w') as f:
                    json.dump(meta, f, indent=2)
            except Exception:
                pass

            # Execute the job (pass DSCP and host pool params for quick analysis)
            result = self.executor.execute(
                run_id,
                params.get('source_ip'),
                params.get('dest_ip'),
                params.get('source_port'),
                params.get('port_protocol_list', []),
                params.get('user_trace_data'),
                analysis_mode,
                params.get('dest_ports', ''),
                job_dscp=dscp,
                allocated_hosts=params.get('allocated_hosts'),
                host_pool_managed=params.get('host_pool_managed', False),
                username=job.get('username')
            )

            # Log metrics if enabled
            if self.log_metrics:
                duration = time.time() - start_time
                self.logger.info(f"Completed job {run_id} in {duration:.2f}s (mode={analysis_mode})")

            return {'success': True, 'result': result, 'duration': time.time() - start_time}

        except Exception as e:
            self.logger.error(f"Job {run_id} failed: {e}")
            duration = time.time() - start_time

            # Log failure
            try:
                self.progress.log_phase(run_id, 'ERROR', f'Execution error: {e}')
            except Exception:
                pass

            if self.log_metrics:
                self.logger.info(f"Failed job {run_id} after {duration:.2f}s (mode={analysis_mode})")

            return {'success': False, 'error': str(e), 'duration': duration}

        finally:
            # Cleanup DSCP for quick jobs
            if analysis_mode == 'quick' and dscp is not None:
                try:
                    from services.tsim_dscp_registry import TsimDscpRegistry
                    dscp_registry = TsimDscpRegistry(self.config)
                    dscp_registry.release_dscp(run_id)
                except Exception as e:
                    self.logger.error(f"Failed to release DSCP for {run_id}: {e}")

    def _cleanup_completed_jobs(self):
        """Remove completed jobs from running_jobs (used for both serial and parallel modes)."""
        with self.running_lock:
            completed = []
            for run_id, info in self.running_jobs.items():
                future = info.get('future')
                if future and future.done():
                    completed.append((run_id, info))

            for run_id, info in completed:
                # Release hosts if this was a host-pool-managed job
                allocated_hosts = info.get('allocated_hosts')
                if allocated_hosts and self.host_pool:
                    try:
                        self.host_pool.release_job(run_id, allocated_hosts)
                        self.logger.debug(f"Released {len(allocated_hosts)} hosts for completed job {run_id}")
                    except Exception as e:
                        self.logger.error(f"Failed to release hosts for {run_id}: {e}")

                del self.running_jobs[run_id]
                self.queue.remove_running(run_id)
