#!/usr/bin/env -S python3 -B -u
"""
TSIM Queue Service
Simple file-backed FIFO queue to serialize test runs across users.

Stores a queue file in /dev/shm (RAM disk) with an accompanying lock file
to coordinate access across WSGI processes/threads.
"""

import os
import json
import time
import fcntl
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional


class TsimQueueService:
    """File-backed FIFO queue for test run jobs."""

    def __init__(self, config_service):
        self.config = config_service
        self.logger = logging.getLogger('tsim.queue')

        base_dir = Path(self.config.get('data_dir', '/dev/shm/tsim'))
        self.queue_dir = base_dir / 'queue'
        self.queue_file = self.queue_dir / 'queue.json'
        self.lock_file = self.queue_dir / 'queue.lock'
        self.current_file = self.queue_dir / 'current.json'

        # Ensure directory exists
        try:
            self.queue_dir.mkdir(parents=True, exist_ok=True, mode=0o775)
        except Exception:
            pass

        # Initialize queue file if missing
        if not self.queue_file.exists():
            self._save_queue({'version': 1, 'updated_at': time.time(), 'jobs': []})

        self.logger.info(f"Queue service using {self.queue_file}")

    # --------------- internal helpers ---------------
    def _lock(self):
        class _Lock:
            def __init__(self, path: Path):
                self.path = path
                self.fd = None
            def __enter__(self):
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR, 0o664)
                fcntl.flock(self.fd, fcntl.LOCK_EX)
                return self
            def __exit__(self, exc_type, exc, tb):
                try:
                    if self.fd is not None:
                        fcntl.flock(self.fd, fcntl.LOCK_UN)
                        os.close(self.fd)
                except Exception:
                    pass
        return _Lock(self.lock_file)

    def _load_queue(self) -> Dict[str, Any]:
        try:
            with open(self.queue_file, 'r') as f:
                return json.load(f)
        except Exception:
            return {'version': 1, 'updated_at': time.time(), 'jobs': []}

    def _save_queue(self, data: Dict[str, Any]):
        tmp = self.queue_file.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self.queue_file)

    # --------------- public api ---------------
    def enqueue(self, run_id: str, username: str, params: Dict[str, Any]) -> int:
        """Enqueue a new job and return its 1-based position."""
        with self._lock():
            q = self._load_queue()
            jobs: List[Dict[str, Any]] = q.get('jobs', [])

            # Avoid duplicating existing run_id
            for idx, j in enumerate(jobs):
                if j.get('run_id') == run_id:
                    return idx + 1

            jobs.append({
                'run_id': run_id,
                'username': username,
                'created_at': time.time(),
                'status': 'QUEUED',
                'params': params,
            })
            q['jobs'] = jobs
            q['updated_at'] = time.time()
            self._save_queue(q)
            return len(jobs)

    def has_user_job(self, username: str) -> bool:
        """True if user has a queued/starting/running job."""
        with self._lock():
            jobs = self._load_queue().get('jobs', [])
            return any(j.get('username') == username and j.get('status') in ('QUEUED', 'STARTING', 'RUNNING') for j in jobs)

    def get_position(self, run_id: str) -> Optional[int]:
        with self._lock():
            for idx, j in enumerate(self._load_queue().get('jobs', [])):
                if j.get('run_id') == run_id:
                    return idx + 1
            return None

    def pop_next(self) -> Optional[Dict[str, Any]]:
        """Pop and return the next job (FIFO)."""
        with self._lock():
            q = self._load_queue()
            jobs = q.get('jobs', [])
            if not jobs:
                return None
            job = jobs.pop(0)
            q['jobs'] = jobs
            q['updated_at'] = time.time()
            self._save_queue(q)
            return job

    def update_status(self, run_id: str, status: str) -> None:
        with self._lock():
            q = self._load_queue()
            jobs = q.get('jobs', [])
            updated = False
            for j in jobs:
                if j.get('run_id') == run_id:
                    j['status'] = status
                    updated = True
                    break
            if updated:
                q['updated_at'] = time.time()
                self._save_queue(q)

    def remove(self, run_id: str) -> bool:
        with self._lock():
            q = self._load_queue()
            jobs = q.get('jobs', [])
            new_jobs = [j for j in jobs if j.get('run_id') != run_id]
            if len(new_jobs) != len(jobs):
                q['jobs'] = new_jobs
                q['updated_at'] = time.time()
                self._save_queue(q)
                return True
            return False

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Return a shallow copy of queued jobs with positions."""
        with self._lock():
            q = self._load_queue()
            jobs = q.get('jobs', [])
            out = []
            for idx, j in enumerate(jobs):
                item = dict(j)
                item['position'] = idx + 1
                out.append(item)
            return out

    # --------------- current running job ---------------
    def set_current(self, job: Dict[str, Any]):
        with self._lock():
            tmp = self.current_file.with_suffix('.tmp')
            with open(tmp, 'w') as f:
                json.dump(job, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(self.current_file)

    def get_current(self) -> Optional[Dict[str, Any]]:
        with self._lock():
            if not self.current_file.exists():
                return None
            try:
                with open(self.current_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return None

    def clear_current(self):
        with self._lock():
            try:
                if self.current_file.exists():
                    self.current_file.unlink()
            except Exception:
                pass

    def request_cancel(self, run_id: str, cancelled_by: Optional[str] = None) -> bool:
        """Request cancellation for a job.

        - If the job is queued, remove it and return True.
        - If the job is currently running, set cancel_requested flag and return True.
        - Otherwise, return False.
        """
        # Try queued removal first, while preserving job metadata
        with self._lock():
            q = self._load_queue()
            jobs = q.get('jobs', [])
            removed_job = None
            new_jobs = []
            for j in jobs:
                if j.get('run_id') == run_id and removed_job is None:
                    removed_job = j
                else:
                    new_jobs.append(j)
            if removed_job is not None:
                q['jobs'] = new_jobs
                q['updated_at'] = time.time()
                self._save_queue(q)
                # Write cancel marker and minimal run.json for history/details
                try:
                    from datetime import datetime
                    run_dir = Path(self.config.get('run_dir', '/dev/shm/tsim/runs')) / run_id
                    run_dir.mkdir(parents=True, exist_ok=True)
                    # cancel.json
                    marker = {
                        'run_id': run_id,
                        'cancelled_by': cancelled_by or 'admin',
                        'cancelled_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    tmp = (run_dir / 'cancel.json').with_suffix('.tmp')
                    with open(tmp, 'w') as f:
                        json.dump(marker, f, indent=2)
                        f.flush()
                        os.fsync(f.fileno())
                    tmp.replace(run_dir / 'cancel.json')
                    # run.json (meta)
                    meta = {
                        'run_id': run_id,
                        'username': removed_job.get('username'),
                        'created_at': removed_job.get('created_at'),
                        'params': removed_job.get('params', {}),
                        'status': 'CANCELLED'
                    }
                    mtmp = (run_dir / 'run.json').with_suffix('.tmp')
                    with open(mtmp, 'w') as f:
                        json.dump(meta, f, indent=2)
                        f.flush()
                        os.fsync(f.fileno())
                    mtmp.replace(run_dir / 'run.json')
                except Exception:
                    pass
                return True

        # Mark current as cancel requested
        with self._lock():
            try:
                if self.current_file.exists():
                    cur = {}
                    with open(self.current_file, 'r') as f:
                        import json as _json
                        cur = _json.load(f)
                    if cur.get('run_id') == run_id:
                        from datetime import datetime
                        cur['cancel_requested'] = True
                        if cancelled_by:
                            cur['cancel_requested_by'] = cancelled_by
                            cur['cancel_requested_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        tmp = self.current_file.with_suffix('.tmp')
                        with open(tmp, 'w') as f:
                            _json.dump(cur, f, indent=2)
                            f.flush()
                            os.fsync(f.fileno())
                        tmp.replace(self.current_file)
                        # Also write cancel marker in run directory for reconciler
                        try:
                            run_dir = Path(self.config.get('run_dir', '/dev/shm/tsim/runs')) / run_id
                            run_dir.mkdir(parents=True, exist_ok=True)
                            marker = {
                                'run_id': run_id,
                                'cancelled_by': cancelled_by or 'admin',
                                'cancelled_at': cur.get('cancel_requested_at')
                            }
                            mtmp = (run_dir / 'cancel.json').with_suffix('.tmp')
                            with open(mtmp, 'w') as mf:
                                _json.dump(marker, mf, indent=2)
                                mf.flush()
                                os.fsync(mf.fileno())
                            mtmp.replace(run_dir / 'cancel.json')
                        except Exception:
                            pass
                        return True
            except Exception:
                return False
        return False
