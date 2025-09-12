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
        self.interval = max(0.5, float(interval))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
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
        try:
            queued = {j.get('run_id') for j in (self.queue.list_jobs() or [])}
        except Exception:
            queued = set()
        cur = None
        try:
            c = self.queue.get_current()
            cur = c.get('run_id') if isinstance(c, dict) else None
        except Exception:
            cur = None

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

            if run_id not in queued and run_id != cur:
                try:
                    age = time.time() - progress_file.stat().st_mtime
                except Exception:
                    age = 0
                if age < 1.5:
                    continue
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
