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

        # running jobs with progress (support parallel execution)
        running_list = []
        try:
            running_jobs = self.queue_service.get_running()
            if isinstance(running_jobs, list):
                running_list = running_jobs
            else:
                # Fallback to single job mode (legacy support)
                running = self.queue_service.get_current()
                # Check if it's a valid job dict with run_id (not the container object)
                if running and isinstance(running, dict) and running.get('run_id'):
                    running_list = [running]
        except Exception:
            pass

        # Split jobs into "actually running" (in thread pool execution) and "waiting"
        # A job is "actually running" if it has reached PHASE2_ksms_start (for quick analysis)
        # or any execution phase (for detailed analysis)
        running_pool = []
        waiting_in_threadpool = []

        for job in running_list:
            if not isinstance(job, dict):
                continue

            run_id = job.get('run_id')
            if not run_id:
                continue

            # Check if job has started actual execution by looking at progress phases
            try:
                from services.tsim_progress_tracker import TsimProgressTracker
                tracker = TsimProgressTracker(self.config)
                prog = tracker.get_progress(run_id) or {}
                phases = prog.get('phases', [])

                # Job is executing if it has reached KSMS start phase or later
                # (not just PHASE2_start which happens before thread pool submission)
                # For detailed jobs, consider MULTI_REACHABILITY phases as executing
                is_executing = False
                for phase in phases:
                    phase_name = phase.get('phase', '')
                    if 'PHASE2_ksms_start' in phase_name or \
                       'MULTI_REACHABILITY' in phase_name or \
                       'PHASE3' in phase_name or \
                       'PHASE4' in phase_name or \
                       'PDF' in phase_name or \
                       'COMPLETE' in phase_name:
                        is_executing = True
                        break

                if is_executing:
                    running_pool.append(job)
                else:
                    # Has DSCP but waiting in thread pool queue
                    waiting_in_threadpool.append(job)
            except Exception:
                # If we can't read progress, assume it's running (conservative)
                running_pool.append(job)

        # Enrich running pool jobs with progress and metadata
        running_list = running_pool
        for running in running_list:
            if not isinstance(running, dict):
                continue

            try:
                from services.tsim_progress_tracker import TsimProgressTracker
                tracker = TsimProgressTracker(self.config)
                prog = tracker.get_progress(running.get('run_id', '')) or {}
                running['percent'] = int(prog.get('overall_progress', 0))
                running['expected_steps'] = prog.get('expected_steps', 0)
                phases = prog.get('phases', [])
                if phases:
                    last_phase = phases[-1]
                    # Use the user-friendly message instead of cryptic phase name
                    running['phase_message'] = last_phase.get('message', last_phase.get('details', ''))
                    running['phase'] = last_phase.get('phase', 'UNKNOWN')
                else:
                    running['phase_message'] = ''
                    running['phase'] = 'UNKNOWN'
            except Exception:
                pass

            # Add DSCP information for KSMS jobs
            try:
                run_id = running.get('run_id')
                if run_id and running.get('params', {}).get('analysis_mode') == 'quick':
                    from services.tsim_dscp_registry import TsimDscpRegistry
                    dscp_registry = TsimDscpRegistry(self.config)
                    dscp_value = dscp_registry.get_dscp_for_job(run_id)
                    if dscp_value:
                        running['dscp_value'] = dscp_value
            except Exception as e:
                self.logger.debug(f"Could not get DSCP for job {run_id}: {e}")
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

        # Enrich thread pool waiting jobs with metadata
        for waiting_job in waiting_in_threadpool:
            if not isinstance(waiting_job, dict):
                continue

            try:
                rd = Path(self.config.get('run_dir', '/dev/shm/tsim/runs')) / waiting_job.get('run_id', '')
                import json as _json
                with open(rd / 'run.json', 'r') as f:
                    meta = _json.load(f)
                waiting_job.setdefault('username', meta.get('username'))
                waiting_job.setdefault('created_at', meta.get('created_at'))
                waiting_job.setdefault('params', meta.get('params', {}))
            except Exception:
                pass

        # Combine scheduler queue and thread pool waiting jobs into single waiting queue
        waiting_queue = waiting_in_threadpool + jobs

        # Truncate port lists for all job types (max 5 ports, add "..." if more)
        def truncate_ports(job):
            if not isinstance(job, dict):
                return job
            params = job.get('params', {})
            port_list = params.get('port_protocol_list', [])
            if isinstance(port_list, list) and len(port_list) > 5:
                params['port_protocol_list_truncated'] = port_list[:5]
                params['port_count_total'] = len(port_list)
            return job

        running_list = [truncate_ports(j) for j in running_list]
        waiting_queue = [truncate_ports(j) for j in waiting_queue]

        # For backward compatibility, return first running job as 'running' (for single-job UI)
        return {
            'running': running_list[0] if running_list else None,
            'running_pool': running_list,      # New: actually executing jobs
            'waiting_queue': waiting_queue,     # New: jobs waiting (scheduler + threadpool)
            'running_jobs': running_list,       # Legacy: for backward compatibility
            'queue': jobs,                      # Legacy: scheduler queue only
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

            # Determine status with better error detection
            success = data.get('success')
            has_error = data.get('error') is not None
            is_cancelled = cancel.get('cancelled_by') or cancel.get('cancelled_at')

            if success is True:
                status = 'SUCCESS'
            elif is_cancelled:
                status = 'CANCELLED'
            elif has_error or success is False:
                status = 'FAILED'
            else:
                # Unknown completion state
                status = 'UNKNOWN'

            out.append({
                'run_id': d.name,
                'username': meta.get('username'),
                'status': status,
                'phase': ph,
                'finished_at': mtime,
                'pdf_url': data.get('pdf_url'),
                'cancelled_by': cancel.get('cancelled_by'),
                'cancelled_at': cancel.get('cancelled_at'),
                'params': meta.get('params', {}),
                'error': data.get('error')  # Include error message for debugging
            })
        out.sort(key=lambda x: x.get('finished_at', 0), reverse=True)
        return out
