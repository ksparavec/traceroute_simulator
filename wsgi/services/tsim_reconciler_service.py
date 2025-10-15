#!/usr/bin/env -S python3 -B -u
"""
TSIM Run Reconciler Service
"""

import time
import json
import logging
import threading
from pathlib import Path
from typing import Optional


class TsimReconcilerService:
    def __init__(self, config_service, queue_service, progress_tracker, interval: float = 1.0):
        self.config = config_service
        self.queue = queue_service
        self.progress_tracker = progress_tracker
        self.logger = logging.getLogger('tsim.reconciler')
        self.run_dir = Path(self.config.get('run_dir', '/dev/shm/tsim/runs'))

        # Get reconciler config
        reconciler_config = self.config.get('reconciler', {})
        self.enabled = reconciler_config.get('enabled', True)
        self.interval = reconciler_config.get('check_interval', interval)
        self.stale_job_timeout = reconciler_config.get('stale_job_timeout', 30.0)
        self.min_age_before_check = reconciler_config.get('min_age_before_check', 5.0)

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self.logger.debug(f"Reconciler initialized: enabled={self.enabled}, interval={self.interval}s, "
                         f"stale_timeout={self.stale_job_timeout}s, min_age={self.min_age_before_check}s")

    def start(self):
        if not self.enabled:
            self.logger.debug("Reconciler is disabled in config, not starting")
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name='tsim-reconciler', daemon=True)
        self._thread.start()
        self.logger.debug("Run reconciler thread started")

    def stop(self, timeout: float = 2.0):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def _run(self):
        while not self._stop.is_set():
            try:
                self._reconcile_once()
            except Exception as e:
                self.logger.debug(f"Reconciler iteration error: {e}")
            time.sleep(self.interval)

    def _reconcile_once(self):
        # Get queued jobs
        try:
            queued = {j.get('run_id') for j in (self.queue.list_jobs() or [])}
        except Exception:
            queued = set()

        # Get currently running jobs (supports both serial and parallel modes)
        running = set()
        try:
            running_jobs = self.queue.get_running()
            if running_jobs:
                running = {j.get('run_id') for j in running_jobs if isinstance(j, dict)}
        except Exception:
            # Fallback to old single-job method for backward compatibility
            try:
                c = self.queue.get_current()
                if isinstance(c, dict) and c.get('run_id'):
                    running.add(c.get('run_id'))
            except Exception:
                pass

        if not self.run_dir.exists():
            return

        for run_path in self.run_dir.iterdir():
            if not run_path.is_dir():
                continue
            run_id = run_path.name
            progress_file = run_path / 'progress.json'
            if not progress_file.exists():
                continue
            try:
                with open(progress_file, 'r') as f:
                    pdata = json.load(f)
            except Exception:
                continue

            if pdata.get('complete') is True:
                continue

            # Skip if job is queued or currently running
            if run_id in queued or run_id in running:
                continue

            # Also skip if job's current phase is QUEUED (even if not in queue list - race condition)
            current_phase = pdata.get('current_phase', '')
            if current_phase == 'QUEUED':
                continue

            # Job is not queued and not running - check if it's stale
            try:
                age = time.time() - progress_file.stat().st_mtime
            except Exception:
                age = 0

            # Only check jobs that have been inactive for at least min_age_before_check
            if age < self.min_age_before_check:
                continue

            # If job hasn't updated progress in stale_job_timeout, mark as cancelled
            if age < self.stale_job_timeout:
                # Job is still active (progress.json recently updated)
                continue

            # Job is stale - mark as cancelled
            try:
                from datetime import datetime
                cancel_marker = run_path / 'cancel.json'
                if cancel_marker.exists():
                    try:
                        with open(cancel_marker, 'r') as cf:
                            cdata = json.load(cf)
                        by = cdata.get('cancelled_by') or 'admin'
                        at = cdata.get('cancelled_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        msg = f"Your job was cancelled by {by} at {at}"
                    except Exception:
                        msg = f"Your job was cancelled at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                else:
                    msg = f"Your job was cancelled at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                self.progress_tracker.mark_complete(run_id, success=False, error=msg)
                self.logger.debug(f"Reconciler marked {run_id} as cancelled/aborted")
            except Exception as e:
                self.logger.debug(f"Failed to mark {run_id} cancelled: {e}")
