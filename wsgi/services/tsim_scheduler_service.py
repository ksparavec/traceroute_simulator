#!/usr/bin/env -S python3 -B -u
"""
TSIM Scheduler Service
Single-leader background scheduler that pulls jobs from the queue and executes
them one at a time under a global network lock.
"""

import time
import json
import logging
import threading
from pathlib import Path
from typing import Optional


class TsimSchedulerService:
    """Background scheduler that runs at most one job at a time globally."""

    def __init__(self, config_service, queue_service, progress_tracker, executor, lock_manager):
        self.config = config_service
        self.queue = queue_service
        self.progress = progress_tracker
        self.executor = executor
        self.lock_manager = lock_manager
        self.logger = logging.getLogger('tsim.scheduler')

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

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
                self._leader_loop()
            finally:
                self.lock_manager.release_lock(leader_name)
            # Yield to others briefly
            time.sleep(0.25)

    def _leader_loop(self):
        """While leader, pull jobs and execute one-at-a-time."""
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
            # Waiting for environment (global lock)
            try:
                self.progress.log_phase(run_id, 'WAITING_FOR_ENVIRONMENT', 'Waiting for simulator to be available')
            except Exception:
                pass

            # Acquire global network test lock; wait as long as needed
            try:
                with self.lock_manager.lock('network_test', timeout=self.config.get('session_timeout', 3600)):
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
            except Exception as e:
                # Could not get global lock
                try:
                    self.progress.log_phase(run_id, 'ERROR', f'Lock error: {e}')
                except Exception:
                    pass
                # Requeue at head is complex; for simplicity, mark failed
                self.queue.update_status(run_id, 'FAILED')
                continue
