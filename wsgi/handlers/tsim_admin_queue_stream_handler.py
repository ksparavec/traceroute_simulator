#!/usr/bin/env -S python3 -B -u
"""
TSIM Admin Queue Stream Handler - SSE for admin queue
"""

import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Generator, List
from .tsim_base_handler import TsimBaseHandler


class TsimAdminQueueStreamHandler(TsimBaseHandler):
    def __init__(self, config_service, session_manager, logger_service, queue_service, lock_manager):
        super().__init__(session_manager, logger_service)
        self.config = config_service
        self.queue_service = queue_service
        self.lock_manager = lock_manager
        self.logger = logging.getLogger('tsim.handler.admin_queue_stream')

    def handle(self, environ: Dict[str, Any], start_response) -> Generator[bytes, None, None]:
        session = self.validate_session(environ)
        if not session:
            return self.error_response(start_response, 'Authentication required', '401 Unauthorized')
        if session.get('role') != 'admin':
            return self.error_response(start_response, 'Admin access required', '403 Forbidden')

        self.stream_response(start_response, 'text/event-stream')
        return self._stream()

    def _stream(self) -> Generator[bytes, None, None]:
        max_ticks = 36000
        last = None
        for tick in range(max_ticks):
            try:
                payload = self._build_payload()
                if payload != last or (tick % 4 == 0):
                    yield f"data: {json.dumps(payload)}\n\n".encode('utf-8')
                    last = payload
                yield b": heartbeat\n\n"
                time.sleep(0.5)
            except Exception as e:
                self.logger.debug(f"admin-queue stream error: {e}")
                break

    def _build_payload(self) -> Dict[str, Any]:
        # queue
        try:
            jobs = self.queue_service.list_jobs()
        except Exception:
            jobs = []
        # running with progress
        running = self.queue_service.get_current()
        if running and isinstance(running, dict):
            try:
                from services.tsim_progress_tracker import TsimProgressTracker
                tracker = TsimProgressTracker(self.config)
                prog = tracker.get_progress(running.get('run_id', '')) or {}
                running['percent'] = int(prog.get('overall_progress', 0))
                phases = prog.get('phases', [])
                running['phase'] = phases[-1]['phase'] if phases else 'UNKNOWN'
            except Exception:
                pass
            # meta enrich
            try:
                rd = Path(self.config.get('run_dir', '/dev/shm/tsim/runs')) / running.get('run_id', '')
                import json as _json
                with open(rd / 'run.json', 'r') as f:
                    meta = _json.load(f)
                running.setdefault('username', meta.get('username'))
                running.setdefault('created_at', meta.get('created_at'))
            except Exception:
                pass
        return {
            'running': running,
            'queue': jobs,
            'history': self._history(),
            'locks': {
                'scheduler_leader': self.lock_manager.is_locked('scheduler_leader'),
                'network_test': self.lock_manager.is_locked('network_test')
            }
        }

    def _history(self) -> List[Dict[str, Any]]:
        out = []
        base = Path(self.config.get('run_dir', '/dev/shm/tsim/runs'))
        if not base.exists():
            return out
        import json as _json
        for d in base.iterdir():
            if not d.is_dir():
                continue
            p = d / 'progress.json'
            if not p.exists():
                continue
            try:
                with open(p, 'r') as f:
                    data = _json.load(f)
            except Exception:
                continue
            if not data.get('complete'):
                continue
            meta = {}
            try:
                with open(d / 'run.json', 'r') as f:
                    meta = _json.load(f)
            except Exception:
                pass
            cancel = {}
            try:
                with open(d / 'cancel.json', 'r') as f:
                    cancel = _json.load(f)
            except Exception:
                pass
            mtime = 0
            try:
                mtime = p.stat().st_mtime
            except Exception:
                pass
            ph = 'COMPLETE'
            try:
                phs = data.get('phases', [])
                if phs:
                    ph = phs[-1].get('phase', ph)
            except Exception:
                pass
            status = 'SUCCESS' if data.get('success') else ('CANCELLED' if (cancel.get('cancelled_by') or cancel.get('cancelled_at')) else 'FAILED')
            out.append({
                'run_id': d.name,
                'username': meta.get('username'),
                'status': status,
                'phase': ph,
                'finished_at': mtime,
                'pdf_url': data.get('pdf_url'),
                'cancelled_by': cancel.get('cancelled_by'),
                'cancelled_at': cancel.get('cancelled_at'),
                'params': meta.get('params', {})
            })
        out.sort(key=lambda x: x.get('finished_at', 0), reverse=True)
        return out
