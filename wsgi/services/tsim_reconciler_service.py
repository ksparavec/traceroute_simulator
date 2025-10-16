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
        # Zombie detection: jobs in running pool but not updating progress
        self.zombie_detection_timeout = reconciler_config.get('zombie_detection_timeout', 60.0)

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self.logger.info(f"Reconciler initialized: enabled={self.enabled}, interval={self.interval}s, "
                        f"stale_timeout={self.stale_job_timeout}s, min_age={self.min_age_before_check}s, "
                        f"zombie_timeout={self.zombie_detection_timeout}s")

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
        running_jobs_list = []
        try:
            running_jobs_list = self.queue.get_running()
            if running_jobs_list:
                running = {j.get('run_id') for j in running_jobs_list if isinstance(j, dict)}
        except Exception:
            # Fallback to old single-job method for backward compatibility
            try:
                c = self.queue.get_current()
                if isinstance(c, dict) and c.get('run_id'):
                    running.add(c.get('run_id'))
                    running_jobs_list = [c]
            except Exception:
                pass

        # ZOMBIE DETECTION: Check running jobs for stale progress (dead executor threads)
        self._detect_zombie_jobs(running_jobs_list)

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

            # Skip if job is queued
            if run_id in queued:
                continue

            # Skip if job is currently running AND progress is recent (not a zombie)
            if run_id in running:
                try:
                    age = time.time() - progress_file.stat().st_mtime
                    if age < self.zombie_detection_timeout:
                        # Still actively running
                        continue
                    # Else: will be handled by zombie detection above
                except Exception:
                    pass
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
            self._cleanup_stale_job(run_id, run_path, "Job was abandoned (not in queue or running pool)")

    def _detect_zombie_jobs(self, running_jobs_list):
        """Detect and clean up zombie jobs (in running pool but executor thread is dead)

        A job is considered a zombie if:
        1. It's in the running pool (current.json)
        2. Its progress hasn't updated in zombie_detection_timeout seconds
        3. This indicates the executor thread died/crashed

        Args:
            running_jobs_list: List of jobs currently in running pool
        """
        from datetime import datetime

        for job_info in running_jobs_list:
            if not isinstance(job_info, dict):
                continue

            run_id = job_info.get('run_id')
            if not run_id:
                continue

            run_path = self.run_dir / run_id
            progress_file = run_path / 'progress.json'

            if not progress_file.exists():
                self.logger.warning(f"Running job {run_id} has no progress file - marking as zombie")
                self._cleanup_zombie_job(run_id, job_info, "No progress file found for running job")
                continue

            try:
                # Check progress file age
                age = time.time() - progress_file.stat().st_mtime

                # If progress hasn't been updated in zombie_detection_timeout, it's a zombie
                if age > self.zombie_detection_timeout:
                    # Read progress to get more context
                    try:
                        with open(progress_file, 'r') as f:
                            pdata = json.load(f)
                        current_phase = pdata.get('current_phase', 'UNKNOWN')
                        self.logger.error(f"ZOMBIE JOB DETECTED: {run_id} stuck in phase '{current_phase}' "
                                        f"for {age:.1f}s (last update {age:.1f}s ago)")
                    except Exception:
                        current_phase = 'UNKNOWN'
                        self.logger.error(f"ZOMBIE JOB DETECTED: {run_id} (progress file unreadable, "
                                        f"last modified {age:.1f}s ago)")

                    self._cleanup_zombie_job(run_id, job_info,
                                           f"Job stuck in phase '{current_phase}' - executor thread likely crashed")
            except Exception as e:
                self.logger.error(f"Error checking zombie status for {run_id}: {e}")

    def _cleanup_zombie_job(self, run_id: str, job_info: dict, reason: str):
        """Clean up a zombie job (remove from running pool, release resources, mark as failed)

        Args:
            run_id: Run ID
            job_info: Job info from running pool
            reason: Reason for zombie detection
        """
        from datetime import datetime

        self.logger.error(f"Cleaning up zombie job {run_id}: {reason}")

        # Remove from running pool
        try:
            self.queue.remove_running(run_id)
            self.logger.info(f"Removed zombie job {run_id} from running pool")
        except Exception as e:
            self.logger.error(f"Failed to remove zombie job {run_id} from running pool: {e}")

        # Release DSCP if allocated
        analysis_mode = job_info.get('type', 'detailed')
        dscp = job_info.get('dscp')
        if analysis_mode == 'quick' and dscp is not None:
            try:
                from services.tsim_dscp_registry import TsimDscpRegistry
                dscp_registry = TsimDscpRegistry(self.config)
                dscp_registry.release_dscp(run_id)
                self.logger.info(f"Released DSCP {dscp} for zombie job {run_id}")
            except Exception as e:
                self.logger.error(f"Failed to release DSCP for zombie job {run_id}: {e}")

        # Mark job as failed in progress tracker
        try:
            error_msg = f"Job failed: {reason}. The system detected this job was stuck and automatically cancelled it."
            self.progress_tracker.mark_complete(run_id, success=False, error=error_msg)
            self.logger.info(f"Marked zombie job {run_id} as failed in progress tracker")
        except Exception as e:
            self.logger.error(f"Failed to mark zombie job {run_id} as failed: {e}")

        # Write cancel marker for audit trail
        try:
            run_path = self.run_dir / run_id
            cancel_marker = run_path / 'cancel.json'
            marker_data = {
                'run_id': run_id,
                'cancelled_by': 'reconciler',
                'cancelled_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'reason': 'zombie_detected',
                'details': reason
            }
            with open(cancel_marker, 'w') as f:
                json.dump(marker_data, f, indent=2)
            self.logger.info(f"Created cancel marker for zombie job {run_id}")
        except Exception as e:
            self.logger.error(f"Failed to create cancel marker for zombie job {run_id}: {e}")

    def _cleanup_stale_job(self, run_id: str, run_path: Path, reason: str):
        """Clean up a stale job (not in queue or running pool)

        Args:
            run_id: Run ID
            run_path: Path to run directory
            reason: Reason for cleanup
        """
        from datetime import datetime

        try:
            cancel_marker = run_path / 'cancel.json'
            if cancel_marker.exists():
                try:
                    with open(cancel_marker, 'r') as cf:
                        cdata = json.load(cf)
                    by = cdata.get('cancelled_by') or 'system'
                    at = cdata.get('cancelled_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    msg = f"Your job was cancelled by {by} at {at}"
                except Exception:
                    msg = f"Your job was cancelled at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            else:
                msg = f"{reason} (detected at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
            self.progress_tracker.mark_complete(run_id, success=False, error=msg)
            self.logger.info(f"Reconciler marked stale job {run_id} as cancelled: {reason}")
        except Exception as e:
            self.logger.error(f"Failed to mark stale job {run_id} cancelled: {e}")
