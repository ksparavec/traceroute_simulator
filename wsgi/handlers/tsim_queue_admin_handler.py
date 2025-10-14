#!/usr/bin/env -S python3 -B -u
"""
TSIM Queue Admin Handler
Provides admin-only endpoint to inspect the run queue and lock states.

Supports both serial and parallel execution modes. Returns list of all currently
running jobs with progress tracking, DSCP values, and job metadata.
"""

import json
import logging
from typing import Dict, Any, List
from .tsim_base_handler import TsimBaseHandler
from services.tsim_queue_service import TsimQueueService
from services.tsim_lock_manager_service import TsimLockManagerService


class TsimQueueAdminHandler(TsimBaseHandler):
    """Admin endpoint for queue inspection

    Shows all running jobs (supports both serial and parallel execution),
    queued jobs, and execution history with progress tracking.
    """

    def __init__(self, config_service, session_manager, logger_service,
                 queue_service: TsimQueueService, lock_manager: TsimLockManagerService):
        super().__init__(session_manager, logger_service)
        self.config = config_service
        self.queue_service = queue_service
        self.lock_manager = lock_manager
        self.logger = logging.getLogger('tsim.handler.queue_admin')

    def handle(self, environ: Dict[str, Any], start_response) -> List[bytes]:
        session = self.validate_session(environ)
        if not session:
            return self.error_response(start_response, 'Authentication required', '401 Unauthorized')
        if session.get('role') != 'admin':
            return self.error_response(start_response, 'Admin access required', '403 Forbidden')

        method = environ.get('REQUEST_METHOD', 'GET')
        if method == 'POST':
            return self._handle_post(environ, start_response, session)
        elif method != 'GET':
            return self.error_response(start_response, 'Method not allowed', '405 Method Not Allowed')

        jobs = self.queue_service.list_jobs()

        # Get all running jobs (supports both serial and parallel execution)
        running_jobs = self.queue_service.get_running()

        # Enrich each running job with progress info and ensure metadata consistency
        if running_jobs:
            try:
                from services.tsim_progress_tracker import TsimProgressTracker
                tracker = TsimProgressTracker(self.config)
                for job in running_jobs:
                    if not isinstance(job, dict):
                        continue
                    prog = tracker.get_progress(job.get('run_id', '')) or {}
                    job['percent'] = int(prog.get('overall_progress', 0))
                    phases = prog.get('phases', [])
                    job['phase'] = phases[-1]['phase'] if phases else 'UNKNOWN'
                    job['status'] = 'RUNNING'

                    # Ensure analysis_mode field exists (may be stored as 'type')
                    if 'analysis_mode' not in job and 'type' in job:
                        job['analysis_mode'] = job['type']
            except Exception:
                pass

        response = {
            'success': True,
            'running': running_jobs,  # Now returns list of running jobs
            'queue': jobs,
            'history': self._get_history(),
            'locks': {
                'scheduler_leader': self.lock_manager.is_locked('scheduler_leader'),
                'network_test': self.lock_manager.is_locked('network_test')
            }
        }
        return self.json_response(start_response, response)

    def _get_history(self) -> List[Dict[str, Any]]:
        from pathlib import Path
        import json as _json
        run_dir = Path(self.config.get('run_dir', '/dev/shm/tsim/runs'))
        items = []
        if not run_dir.exists():
            return items
        for rp in run_dir.iterdir():
            if not rp.is_dir():
                continue
            pid = rp / 'progress.json'
            if not pid.exists():
                continue
            try:
                with open(pid, 'r') as f:
                    pdata = _json.load(f)
            except Exception:
                continue
            if not pdata.get('complete'):
                continue
            # Meta and cancel info
            meta = {}
            try:
                with open(rp / 'run.json', 'r') as f:
                    meta = _json.load(f)
            except Exception:
                pass
            cancel_by = None
            cancel_at = None
            try:
                with open(rp / 'cancel.json', 'r') as f:
                    c = _json.load(f)
                    cancel_by = c.get('cancelled_by')
                    cancel_at = c.get('cancelled_at')
            except Exception:
                pass
            mtime = pid.stat().st_mtime
            phase = 'COMPLETE'
            try:
                phases = pdata.get('phases', [])
                if phases:
                    phase = phases[-1].get('phase', phase)
            except Exception:
                pass
            status = 'SUCCESS' if pdata.get('success') else ('CANCELLED' if (cancel_by or cancel_at) else 'FAILED')
            items.append({
                'run_id': rp.name,
                'username': meta.get('username'),
                'status': status,
                'phase': phase,
                'finished_at': mtime,
                'pdf_url': pdata.get('pdf_url'),
                'cancelled_by': cancel_by,
                'cancelled_at': cancel_at,
                'params': meta.get('params', {})
            })
        items.sort(key=lambda x: x.get('finished_at', 0), reverse=True)
        return items

    def _handle_post(self, environ, start_response, session):
        # Parse form data
        try:
            data = self.parse_post_data(environ)
        except Exception:
            data = {}
        action = (data.get('action') or '').strip()
        run_id = (data.get('run_id') or '').strip()
        if not action or not run_id:
            return self.error_response(start_response, 'Missing action or run_id')

        if action == 'cancel':
            ok = self.queue_service.request_cancel(run_id, session.get('username'))
            # Mark complete with failure for queued jobs so clients stop waiting
            if ok:
                try:
                    from services.tsim_progress_tracker import TsimProgressTracker
                    from datetime import datetime
                    tracker = TsimProgressTracker(self.config)
                    admin_user = session.get('username', 'admin')
                    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    msg = f"Your job was cancelled by {admin_user} at {ts}"
                    tracker.mark_complete(run_id, success=False, error=msg)
                except Exception:
                    pass
            # Log to audit
            try:
                client_ip = self.get_client_ip(environ)
                # Try to infer target user
                target_user = None
                try:
                    for j in (self.queue_service.list_jobs() or []):
                        if j.get('run_id') == run_id:
                            target_user = j.get('username')
                            break
                    if not target_user:
                        cur = self.queue_service.get_current()
                        if isinstance(cur, dict) and cur.get('run_id') == run_id:
                            target_user = cur.get('username')
                except Exception:
                    pass
                details = {'run_id': run_id}
                if target_user:
                    details['target_user'] = target_user
                self.logger_service.log_audit('cancel_job', session.get('username','admin'), client_ip, bool(ok), details)
            except Exception:
                pass
            return self.json_response(start_response, {
                'success': bool(ok),
                'message': 'Cancellation requested' if ok else 'Unable to cancel run'
            })

        return self.error_response(start_response, 'Unsupported action')
