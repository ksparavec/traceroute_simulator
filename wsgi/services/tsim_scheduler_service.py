#!/usr/bin/env -S python3 -B -u
"""
TSIM Scheduler Service
Background scheduler supporting both serial and parallel execution modes.

Execution Modes:
- serial: Jobs execute one at a time (proven baseline, default)
- parallel: Quick jobs run concurrently (up to 32), detailed jobs serialize

Configuration: Set "wsgi_execution_mode" in config.json
"""

import time
import json
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, Future


class TsimSchedulerService:
    """Background scheduler with centralized coordination via TsimRegistryManager.

    Supports two execution modes:
    - serial: One job at a time (baseline, proven code path)
    - parallel: Multiple quick jobs concurrently, detailed jobs serialize

    Mode is configured via wsgi_execution_mode in config.json
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
        self.execution_mode = config_service.get('wsgi_execution_mode', 'serial')
        if self.execution_mode not in ['serial', 'parallel']:
            self.logger.error(f"Invalid wsgi_execution_mode '{self.execution_mode}', defaulting to serial")
            self.execution_mode = 'serial'

        self.logger.info(f"Scheduler execution mode: {self.execution_mode}")

        # Parallel execution infrastructure
        self.parallel_config = config_service.get('wsgi_parallel_config', {})
        self.enable_fallback = self.parallel_config.get('enable_fallback_to_serial', True)
        self.log_metrics = self.parallel_config.get('log_execution_metrics', True)

        if self.execution_mode == 'parallel':
            max_workers = self.parallel_config.get('thread_pool_workers', 33)
            self.thread_pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='job-executor')
            self.running_jobs: Dict[str, Dict[str, Any]] = {}
            self.running_lock = threading.Lock()
            self.logger.info(f"Parallel execution enabled: max_workers={max_workers}")
        else:
            self.thread_pool = None
            self.running_jobs = None
            self.running_lock = None

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
                # Dispatch to appropriate leader loop based on execution mode
                if self.execution_mode == 'parallel':
                    self._leader_loop_parallel()
                else:
                    self._leader_loop_serial()
            finally:
                self.lock_manager.release_lock(leader_name)
            # Yield to others briefly
            time.sleep(0.25)

    def _leader_loop_serial(self):
        """While leader, pull jobs and execute one-at-a-time (serial mode)."""
        while not self._stop_event.is_set():
            job = self.queue.pop_next()
            if not job:
                # Nothing to do; short sleep
                time.sleep(0.5)
                return

            run_id = job.get('run_id')
            username = job.get('username')
            params = job.get('params', {})

            # Ensure run directory and initial progress exist
            try:
                self.progress.create_run_directory(run_id)
            except Exception:
                pass
            # NOTE: No global lock needed - coordination handled by TsimRegistryManager
            # in the scripts themselves (router locks, host leases, etc.)

            # Record current running job for admin view
            current = {
                'run_id': run_id,
                'username': username,
                'status': 'STARTING',
                'created_at': job.get('created_at'),
                'params': params
            }
            self.queue.set_current(current)

            # Persist run metadata for admin/details
            try:
                run_dir = Path(self.config.get('run_dir', '/dev/shm/tsim/runs')) / run_id
                run_dir.mkdir(parents=True, exist_ok=True)
                meta = {
                    'run_id': run_id,
                    'username': username,
                    'created_at': current.get('created_at'),
                    'params': params,
                    'status': 'STARTING'
                }
                with open(run_dir / 'run.json', 'w') as f:
                    json.dump(meta, f, indent=2)
            except Exception:
                pass

            # Mark starting and execute
            self.queue.update_status(run_id, 'STARTING')
            try:
                # If cancel was requested before start, skip execution
                cur = self.queue.get_current() or {}
                if cur.get('cancel_requested'):
                    try:
                        self.progress.log_phase(run_id, 'FAILED', 'Cancelled before start by admin')
                    except Exception:
                        pass
                    self.queue.update_status(run_id, 'FAILED')
                    return

                # Execute job - coordination happens inside scripts via TsimRegistryManager
                result = self.executor.execute(
                    run_id,
                    params.get('source_ip'),
                    params.get('dest_ip'),
                    params.get('source_port'),
                    params.get('port_protocol_list', []),
                    params.get('user_trace_data'),
                    params.get('analysis_mode', 'detailed')
                )

                # Update current as running (for completeness)
                current['status'] = 'RUNNING'
                self.queue.set_current(current)
                try:
                    run_dir = Path(self.config.get('run_dir', '/dev/shm/tsim/runs')) / run_id
                    with open(run_dir / 'run.json', 'r') as f:
                        meta = json.load(f)
                    meta['status'] = 'RUNNING'
                    with open(run_dir / 'run.json', 'w') as f:
                        json.dump(meta, f, indent=2)
                except Exception:
                    pass

                # executor marks completion via progress tracker; nothing else to do here
                self.queue.update_status(run_id, 'RUNNING')

            except Exception as e:
                self.queue.update_status(run_id, 'FAILED')
                try:
                    self.progress.log_phase(run_id, 'ERROR', f'Scheduler error: {e}')
                except Exception:
                    pass
            finally:
                # Clear current job
                self.queue.clear_current()

    # ==================== PARALLEL EXECUTION MODE ====================

    def _leader_loop_parallel(self):
        """While leader, manage parallel job execution."""
        while not self._stop_event.is_set():
            # Check for completed jobs
            self._cleanup_completed_jobs()

            # Pop compatible jobs
            with self.running_lock:
                running_jobs_info = {
                    run_id: {'type': info['type'], 'dscp': info.get('dscp')}
                    for run_id, info in self.running_jobs.items()
                }

            jobs_to_start = self.queue.pop_compatible_jobs(running_jobs_info)

            if not jobs_to_start:
                time.sleep(0.5)
                continue

            # Start all compatible jobs
            for job in jobs_to_start:
                self._start_job_parallel(job)

            time.sleep(0.25)

    def _start_job_parallel(self, job: Dict[str, Any]):
        """Start a single job in thread pool (parallel mode)."""
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
        """Wrapper for job execution with error handling (parallel mode)."""
        run_id = job.get('run_id')
        analysis_mode = job.get('analysis_mode', 'detailed')

        try:
            # Ensure run directory exists
            try:
                self.progress.create_run_directory(run_id)
            except Exception:
                pass

            # Inject DSCP into params for quick jobs
            params = job.get('params', {})
            if dscp is not None:
                params['job_dscp'] = dscp

            # Execute the job
            result = self.executor.execute(
                run_id,
                params.get('source_ip'),
                params.get('dest_ip'),
                params.get('source_port'),
                params.get('port_protocol_list', []),
                params.get('user_trace_data'),
                analysis_mode
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
        """Remove completed jobs from running_jobs (parallel mode)."""
        with self.running_lock:
            completed = []
            for run_id, info in self.running_jobs.items():
                future = info.get('future')
                if future and future.done():
                    completed.append(run_id)

            for run_id in completed:
                del self.running_jobs[run_id]
                self.queue.remove_running(run_id)
