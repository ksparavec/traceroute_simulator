#!/usr/bin/env -S python3 -B -u
"""
TSIM Quick Job Host Pool Service

Manages source host lifecycle for parallel quick job execution.
Provides centralized host management with reference counting to prevent
TOCTOU race conditions and resource conflicts.

Architecture:
1. Execute traces in parallel for all queued quick jobs
2. Parse traces to determine all required hosts
3. Create all hosts atomically before launching any job
4. Track reference counts (which jobs use which hosts)
5. Remove hosts after grace period when no jobs are using them

This design eliminates deadlocks that occur when jobs try to create
hosts one-by-one while running in parallel.
"""

import os
import sys
import json
import time
import logging
import threading
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed


def tsimsh_exec(command: str, capture_output: bool = False, verbose: int = 0, env: dict = None) -> Optional[str]:
    """Execute tsimsh command (copied exactly from MultiServiceTester pattern)"""
    # Always use tsimsh from PATH (properly installed version)
    tsimsh_path = "tsimsh"

    cmd = [tsimsh_path, "-q"]

    try:
        result = subprocess.run(
            cmd,
            input=command,
            capture_output=True,
            text=True,
            timeout=60,
            env=env
        )

        # Debug output for verbose mode
        if verbose > 0:
            print(f"[DEBUG] tsimsh command: {command}", file=sys.stderr)
            if verbose > 1:
                print(f"[DEBUG] tsimsh stdout: {result.stdout}", file=sys.stderr)
                print(f"[DEBUG] tsimsh stderr: {result.stderr}", file=sys.stderr)
            print(f"[DEBUG] tsimsh return code: {result.returncode}", file=sys.stderr)

        if result.returncode != 0:
            if verbose > 0:
                print(f"[ERROR] tsimsh command failed: {result.stderr}", file=sys.stderr)
            return None

        if capture_output:
            return result.stdout
        return None if result.returncode == 0 else result.stderr
    except Exception as e:
        print(f"Error executing tsimsh command: {e}", file=sys.stderr)
        return None


class TsimQuickJobHostPoolService:
    """Manages source hosts for parallel quick job execution"""

    def __init__(self, config_service, registry_manager, logger_service=None):
        """Initialize host pool service

        Args:
            config_service: TsimConfigService instance
            registry_manager: TsimRegistryManager instance for atomic operations
            logger_service: Optional TsimLoggerService instance
        """
        self.config = config_service
        self.registry_mgr = registry_manager
        self.logger = logging.getLogger('tsim.host_pool')

        # Track which jobs are using which hosts
        # Structure: {host_name: set(job_id1, job_id2, ...)}
        self.host_refcounts = {}

        # Track cleanup timers for hosts with zero refcount
        # Structure: {host_name: threading.Timer}
        self.cleanup_timers = {}

        # Lock for thread-safe operations
        self.lock = threading.Lock()

        # Grace period before removing unused hosts (allows reuse)
        self.cleanup_grace_period = config_service.get('quick_job_host_cleanup_grace_period', 30)

        # Path to tsimsh
        self.tsimsh_path = config_service.tsimsh_path

        self.logger.info(f"Host pool service initialized (cleanup grace period: {self.cleanup_grace_period}s)")

    def prepare_and_execute_jobs(self, job_list: List[Dict[str, Any]],
                                 executor_callback) -> Dict[str, Any]:
        """Prepare hosts and execute quick jobs in batch

        This is the main entry point called by the scheduler when quick jobs
        are ready to run.

        Args:
            job_list: List of job parameter dictionaries
            executor_callback: Function to call to execute each job's KSMS test
                             Signature: executor_callback(job_params, allocated_hosts)

        Returns:
            Dictionary with results:
                - success: bool
                - jobs_launched: int
                - hosts_created: List[str]
                - error: Optional[str]
        """
        if not job_list:
            return {'success': True, 'jobs_launched': 0, 'hosts_created': []}

        job_count = len(job_list)
        self.logger.info(f"Preparing batch of {job_count} quick jobs")

        try:
            # PHASE 1: Execute traces in parallel for all jobs
            self.logger.info("Phase 1: Executing traces in parallel")
            trace_results = self._execute_traces_parallel(job_list)

            # Check for trace failures
            failed_traces = [r for r in trace_results if not r['success']]
            if failed_traces:
                error_msg = f"Trace execution failed for {len(failed_traces)}/{job_count} jobs"
                self.logger.error(error_msg)
                return {
                    'success': False,
                    'jobs_launched': 0,
                    'hosts_created': [],
                    'error': error_msg,
                    'failed_jobs': [r['run_id'] for r in failed_traces]
                }

            # PHASE 2: Parse traces and determine all required hosts
            self.logger.info("Phase 2: Analyzing traces to determine required hosts")
            host_requirements = self._analyze_host_requirements(trace_results, job_list)

            if not host_requirements:
                error_msg = "No hosts required (empty trace results)"
                self.logger.error(error_msg)
                return {
                    'success': False,
                    'jobs_launched': 0,
                    'hosts_created': [],
                    'error': error_msg
                }

            # Log what we found
            all_hosts = set()
            for job_id, hosts in host_requirements.items():
                all_hosts.update(hosts.keys())

            self.logger.info(f"Jobs require {len(all_hosts)} unique hosts: {sorted(all_hosts)}")
            for job_id, hosts in host_requirements.items():
                self.logger.debug(f"  Job {job_id}: {sorted(hosts.keys())}")

            # PHASE 3: Create all required hosts atomically
            self.logger.info("Phase 3: Creating all hosts atomically")
            created_hosts = self._create_hosts_atomic(host_requirements)

            # PHASE 4: Update reference counts for all jobs
            self.logger.info("Phase 4: Registering host usage for all jobs")
            with self.lock:
                for job_id, hosts in host_requirements.items():
                    for host_name in hosts.keys():
                        if host_name not in self.host_refcounts:
                            self.host_refcounts[host_name] = set()
                        self.host_refcounts[host_name].add(job_id)

                        # Cancel any pending cleanup timer
                        if host_name in self.cleanup_timers:
                            self.cleanup_timers[host_name].cancel()
                            del self.cleanup_timers[host_name]
                            self.logger.debug(f"Cancelled cleanup timer for {host_name} (reused by {job_id})")

            # PHASE 5: Launch all KSMS testers in parallel
            self.logger.info("Phase 5: Launching all KSMS testers")
            launched_jobs = []
            for job_params in job_list:
                job_id = job_params['run_id']
                allocated_hosts = host_requirements.get(job_id, {})

                # Add trace file to params
                for trace_result in trace_results:
                    if trace_result['run_id'] == job_id and trace_result['success']:
                        job_params['trace_file'] = trace_result['trace_file']
                        break

                # Call executor callback to launch the job
                # Pass allocated_hosts so KSMS service knows which hosts to use
                try:
                    executor_callback(job_params, allocated_hosts)
                    launched_jobs.append(job_id)
                    self.logger.info(f"Launched KSMS tester for job {job_id}")
                except Exception as e:
                    self.logger.error(f"Failed to launch job {job_id}: {e}")
                    # Release hosts for this failed job
                    self.release_job(job_id, list(allocated_hosts.keys()))

            self.logger.info(f"Successfully launched {len(launched_jobs)}/{job_count} jobs")

            return {
                'success': True,
                'jobs_launched': len(launched_jobs),
                'hosts_created': list(created_hosts),
                'allocated_hosts': host_requirements
            }

        except Exception as e:
            error_msg = f"Batch job preparation failed: {e}"
            self.logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'jobs_launched': 0,
                'hosts_created': [],
                'error': error_msg
            }

    def _execute_traces_parallel(self, job_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute traces in parallel for all jobs

        Args:
            job_list: List of job parameter dictionaries

        Returns:
            List of trace results, each containing:
                - run_id: str
                - success: bool
                - trace_file: Optional[str]
                - error: Optional[str]
        """
        results = []

        # Use thread pool for parallel trace execution
        with ThreadPoolExecutor(max_workers=min(len(job_list), 10)) as executor:
            future_to_job = {}

            for job_params in job_list:
                future = executor.submit(self._execute_single_trace, job_params)
                future_to_job[future] = job_params['run_id']

            for future in as_completed(future_to_job):
                job_id = future_to_job[future]
                try:
                    result = future.result()
                    results.append(result)
                    if result['success']:
                        self.logger.info(f"Trace completed for {job_id}")
                    else:
                        self.logger.error(f"Trace failed for {job_id}: {result.get('error')}")
                except Exception as e:
                    self.logger.error(f"Trace execution exception for {job_id}: {e}")
                    results.append({
                        'run_id': job_id,
                        'success': False,
                        'error': str(e)
                    })

        return results

    def _execute_single_trace(self, job_params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute trace for a single job

        Args:
            job_params: Job parameters

        Returns:
            Trace result dictionary
        """
        run_id = job_params['run_id']
        source_ip = job_params['source_ip']
        dest_ip = job_params['dest_ip']

        # Determine trace file location
        run_dir = Path(self.config.get('run_dir', '/dev/shm/tsim/runs')) / run_id
        trace_file = run_dir / f'{run_id}.trace'

        # Check if trace already exists (development mode or user-provided)
        if trace_file.exists():
            self.logger.info(f"Using existing trace file for {run_id}")
            return {
                'run_id': run_id,
                'success': True,
                'trace_file': str(trace_file)
            }

        # Check for user-provided trace data
        if job_params.get('user_trace_data'):
            self.logger.info(f"Using user-provided trace data for {run_id}")
            run_dir.mkdir(parents=True, exist_ok=True)
            trace_file.write_text(job_params['user_trace_data'])
            return {
                'run_id': run_id,
                'success': True,
                'trace_file': str(trace_file)
            }

        # Execute trace using tsimsh (matching hybrid_executor format)
        self.logger.info(f"Executing trace for {run_id}: {source_ip} -> {dest_ip}")

        try:
            # Create run directory if it doesn't exist
            run_dir.mkdir(parents=True, exist_ok=True)

            # Use the same format as hybrid_executor: trace -s SOURCE -d DEST -j
            trace_command = f"trace -s {source_ip} -d {dest_ip} -j\n"

            # Set environment
            env = os.environ.copy()
            env['TRACEROUTE_SIMULATOR_CONF'] = self.config.get('traceroute_simulator_conf',
                                                               '/opt/tsim/wsgi/conf/traceroute_simulator.yaml')
            env.setdefault('PYTHONDONTWRITEBYTECODE', '1')
            env.setdefault('PYTHONPYCACHEPREFIX', '/dev/shm/tsim/pycache')

            # Execute command
            result = subprocess.run(
                [self.tsimsh_path, '-q'],
                input=trace_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,
                env=env
            )

            if result.returncode != 0:
                error_msg = f"Trace command failed: {result.stderr}"
                self.logger.error(f"Trace failed for {run_id}: {error_msg}")
                return {
                    'run_id': run_id,
                    'success': False,
                    'error': error_msg
                }

            # Save trace output
            trace_file.write_text(result.stdout)

            # Verify trace was created
            if not trace_file.exists() or trace_file.stat().st_size == 0:
                error_msg = "Trace file was not created or is empty"
                self.logger.error(f"Trace failed for {run_id}: {error_msg}")
                return {
                    'run_id': run_id,
                    'success': False,
                    'error': error_msg
                }

            self.logger.info(f"Trace completed successfully for {run_id}")
            return {
                'run_id': run_id,
                'success': True,
                'trace_file': str(trace_file)
            }

        except subprocess.TimeoutExpired:
            error_msg = "Trace execution timeout (60s)"
            self.logger.error(f"Trace timeout for {run_id}")
            return {
                'run_id': run_id,
                'success': False,
                'error': error_msg
            }
        except Exception as e:
            error_msg = f"Trace execution exception: {e}"
            self.logger.error(f"Trace exception for {run_id}: {e}")
            return {
                'run_id': run_id,
                'success': False,
                'error': error_msg
            }

    def _analyze_host_requirements(self, trace_results: List[Dict[str, Any]],
                                   job_list: List[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, str]]]:
        """Parse trace files and determine host requirements for each job

        Args:
            trace_results: List of trace result dictionaries
            job_list: Original job parameter list (for source IP)

        Returns:
            Dictionary mapping job_id to host requirements:
            {
                'job1': {
                    'source-1': {'ip': '10.0.0.1', 'router': 'router1'},
                    'source-2': {'ip': '10.0.0.1', 'router': 'router2'}
                },
                'job2': ...
            }
        """
        host_requirements = {}

        # Build job_id -> source_ip mapping
        job_source_ips = {j['run_id']: j['source_ip'] for j in job_list}

        for trace_result in trace_results:
            if not trace_result['success']:
                continue

            run_id = trace_result['run_id']
            trace_file = trace_result['trace_file']
            source_ip = job_source_ips.get(run_id, '10.0.0.1')

            try:
                with open(trace_file, 'r') as f:
                    trace_data = json.load(f)

                # Extract routers from path (only router hops)
                path = trace_data.get('path', [])
                routers = [hop['name'] for hop in path if hop.get('is_router')]

                if not routers:
                    self.logger.warning(f"No routers found in trace for {run_id}")
                    continue

                # Build host requirements for this job
                job_hosts = {}
                for i, router in enumerate(routers, 1):
                    host_name = f"source-{i}"
                    job_hosts[host_name] = {
                        'ip': source_ip,
                        'router': router
                    }

                host_requirements[run_id] = job_hosts
                self.logger.debug(f"Job {run_id} requires {len(job_hosts)} hosts on routers: {routers}")

            except Exception as e:
                self.logger.error(f"Failed to parse trace for {run_id}: {e}")
                continue

        return host_requirements

    def _create_hosts_atomic(self, host_requirements: Dict[str, Dict[str, Dict[str, str]]]) -> Set[str]:
        """Create all required hosts atomically

        This creates hosts in order, using atomic registry operations to prevent conflicts.
        If any host creation fails, we don't rollback already-created hosts since they
        might be in use by other jobs.

        Args:
            host_requirements: Dictionary of job_id -> host_name -> {ip, router}

        Returns:
            Set of newly created host names

        Raises:
            RuntimeError: If critical host creation fails
        """
        # Collect all unique hosts needed
        all_hosts = {}  # host_name -> {ip, router, jobs: [job_id1, ...]}

        for job_id, hosts in host_requirements.items():
            for host_name, host_info in hosts.items():
                if host_name not in all_hosts:
                    all_hosts[host_name] = {
                        'ip': host_info['ip'],
                        'router': host_info['router'],
                        'jobs': []
                    }
                all_hosts[host_name]['jobs'].append(job_id)

        self.logger.info(f"Creating {len(all_hosts)} unique hosts atomically")

        created_hosts = set()
        reused_hosts = set()

        for host_name, host_info in sorted(all_hosts.items()):
            ip = host_info['ip']
            router = host_info['router']
            jobs = host_info['jobs']

            try:
                # Create host using tsimsh (which handles registry internally)
                self.logger.info(f"Creating host {host_name} on {router} (used by {len(jobs)} jobs)")

                # Use exact same method as KSMS service
                result = tsimsh_exec(
                    f"host add --name {host_name} --primary-ip {ip}/24 --connect-to {router} --no-delay",
                    capture_output=True, verbose=2
                )

                if result is None:
                    # Physical creation failed
                    error_msg = f"Host add command failed for {host_name} on {router}"
                    self.logger.error(error_msg)
                    raise RuntimeError(error_msg)
                else:
                    # Check if host was reused (already existed physically) or created
                    if "[REUSED]" in result:
                        reused_hosts.add(host_name)
                        self.logger.info(f"Host {host_name} was reused (pre-existing physically), will not clean up")
                    else:
                        created_hosts.add(host_name)
                        self.logger.info(f"Host {host_name} was created, will clean up after test")

            except Exception as e:
                error_msg = f"Failed to create host {host_name}: {e}"
                self.logger.error(error_msg)
                # Don't rollback - other jobs might be using already-created hosts
                raise RuntimeError(error_msg)

        self.logger.info(f"Host creation complete: {len(created_hosts)} created, {len(reused_hosts)} reused")
        return created_hosts

    def release_job(self, job_id: str, hosts: List[str]) -> None:
        """Release hosts used by a completed job

        Decrements reference counts and schedules cleanup for unused hosts.

        Args:
            job_id: Job ID that completed
            hosts: List of host names used by this job
        """
        with self.lock:
            for host_name in hosts:
                if host_name in self.host_refcounts:
                    self.host_refcounts[host_name].discard(job_id)

                    if len(self.host_refcounts[host_name]) == 0:
                        # No more jobs using this host - schedule cleanup
                        self.logger.info(f"Host {host_name} no longer in use, scheduling cleanup in {self.cleanup_grace_period}s")

                        timer = threading.Timer(
                            self.cleanup_grace_period,
                            self._cleanup_host,
                            args=(host_name,)
                        )
                        timer.daemon = True
                        timer.start()

                        self.cleanup_timers[host_name] = timer
                    else:
                        # Still in use by other jobs
                        remaining_jobs = len(self.host_refcounts[host_name])
                        self.logger.debug(f"Host {host_name} still in use by {remaining_jobs} job(s)")

    def _cleanup_host(self, host_name: str) -> None:
        """Remove host after grace period expires

        Args:
            host_name: Name of host to clean up
        """
        with self.lock:
            # Double-check refcount (might have been reused during grace period)
            if host_name in self.host_refcounts and len(self.host_refcounts[host_name]) > 0:
                self.logger.info(f"Host {host_name} was reused during grace period, skipping cleanup")
                return

            # Remove from tracking
            if host_name in self.host_refcounts:
                del self.host_refcounts[host_name]
            if host_name in self.cleanup_timers:
                del self.cleanup_timers[host_name]

        # Remove physical host using exact same method as KSMS service
        self.logger.info(f"Cleaning up unused host {host_name}")

        # Use tsimsh to remove host
        result = tsimsh_exec(
            f"host remove --name {host_name} --force",
            capture_output=True, verbose=1
        )

        if result is None:
            self.logger.warning(f"Failed to remove source host {host_name}")
        else:
            # Check if removal was successful
            if "[SUCCESS]" in result or "[INFO]" in result:
                self.logger.info(f"Successfully removed host {host_name}")

                # Also unregister from registry
                if self.registry_mgr:
                    try:
                        self.registry_mgr.unregister_host(host_name)
                        self.logger.debug(f"Unregistered {host_name} from registry during cleanup")
                    except Exception as unreg_error:
                        self.logger.warning(f"Failed to unregister {host_name} from registry: {unreg_error}")
            else:
                self.logger.warning(f"Uncertain status removing {host_name}: {result[:100]}")

    def get_status(self) -> Dict[str, Any]:
        """Get current status of host pool

        Returns:
            Dictionary with status information
        """
        with self.lock:
            active_hosts = {
                host: list(jobs)
                for host, jobs in self.host_refcounts.items()
                if len(jobs) > 0
            }

            cleanup_pending = list(self.cleanup_timers.keys())

        return {
            'active_hosts': active_hosts,
            'active_host_count': len(active_hosts),
            'cleanup_pending': cleanup_pending,
            'cleanup_pending_count': len(cleanup_pending)
        }
