#!/usr/bin/env -S python3 -B -u
"""
TSIM Job Details Handler
Returns detailed information about a specific run for admin UI.
"""

import json
import logging
from typing import Dict, Any, List
from pathlib import Path
from .tsim_base_handler import TsimBaseHandler


class TsimJobDetailsHandler(TsimBaseHandler):
    def __init__(self, config_service, session_manager, logger_service):
        super().__init__(session_manager, logger_service)
        self.config = config_service
        self.logger = logging.getLogger('tsim.handler.job_details')

    def handle(self, environ: Dict[str, Any], start_response) -> List[bytes]:
        session = self.validate_session(environ)
        if not session:
            return self.error_response(start_response, 'Authentication required', '401 Unauthorized')
        if session.get('role') != 'admin':
            return self.error_response(start_response, 'Admin access required', '403 Forbidden')

        params = self.parse_query_params(environ)
        run_id = (params.get('id') or params.get('run_id') or '').strip()
        if not run_id:
            return self.error_response(start_response, 'Missing run id')

        run_dir = Path(self.config.get('run_dir', '/dev/shm/tsim/runs')) / run_id
        if not run_dir.exists():
            return self.error_response(start_response, 'Run not found', '404 Not Found')

        # Optional trace download: /admin-job?id=<id>&download=trace
        download = (params.get('download') or '').strip().lower()
        if download == 'trace':
            # Determine trace file path
            trace_path = run_dir / f"{run_id}.trace"
            if not trace_path.exists():
                # Try to infer from run.json params.trace_file
                try:
                    with open(run_dir / 'run.json', 'r') as f:
                        meta = json.load(f)
                    p = (meta or {}).get('params', {})
                    tf = p.get('trace_file')
                    if tf:
                        from pathlib import Path as _P
                        tp = _P(tf)
                        if tp.exists():
                            trace_path = tp
                except Exception:
                    pass
            if not trace_path.exists():
                return self.error_response(start_response, 'Trace file not found', '404 Not Found')
            try:
                data = trace_path.read_bytes()
            except Exception:
                return self.error_response(start_response, 'Failed to read trace file', '500 Internal Server Error')
            # Serve inline so browsers display it in a new tab
            headers = [
                ('Content-Type', 'application/json; charset=utf-8'),
                ('Cache-Control', 'no-cache')
            ]
            start_response('200 OK', headers)
            return [data]

        def read_json(path: Path):
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                return None

        resp = {
            'run_id': run_id,
            'meta': read_json(run_dir / 'run.json') or {},
            'progress': read_json(run_dir / 'progress.json') or {},
            'cancel': read_json(run_dir / 'cancel.json') or {},
            'logs': {},
            'links': {
                'trace_file': f"/admin-job?id={run_id}&download=trace"
            },
            'derived': {}
        }

        # Only include selected logs in response
        for name in ['audit.log', 'timing.json']:
            p = run_dir / name
            if p.exists():
                try:
                    if name.endswith('.json'):
                        resp['logs'][name] = read_json(p)
                    else:
                        with open(p, 'r') as f:
                            resp['logs'][name] = f.read()[-20000:]
                except Exception:
                    pass

        # Derive source_port(s) actually used (if not explicitly provided)
        try:
            params = (resp.get('meta') or {}).get('params', {})
            sp = params.get('source_port')
            used_list = []
            if sp:
                used_list = [sp]
            else:
                # Look into results directory for a *_results.json file
                results_dir = run_dir / 'results'
                # Prefer summary.json if available
                try:
                    sfile = results_dir / 'summary.json'
                    if sfile.exists():
                        with open(sfile, 'r') as f:
                            sdata = json.load(f)
                        sl = sdata.get('source_ports')
                        if isinstance(sl, list):
                            for v in sl:
                                if v and v not in used_list:
                                    used_list.append(v)
                except Exception:
                    pass
                if results_dir.exists():
                    # Prefer files with run_id prefix to avoid collisions
                    candidates = list(results_dir.glob(f"{run_id}_*_results.json"))
                    if not candidates:
                        candidates = list(results_dir.glob("*_results.json"))
                    for c in candidates:
                        try:
                            with open(c, 'r') as f:
                                data = json.load(f)
                            # New formatted result stores actual in summary.source_port
                            sp2 = None
                            try:
                                sp2 = (data.get('summary') or {}).get('source_port')
                            except Exception:
                                pass
                            # Fallbacks
                            if not sp2:
                                sp2 = data.get('source_port') or (data.get('connectivity_test') or {}).get('source_port')
                            if sp2 and sp2 not in used_list:
                                used_list.append(sp2)
                        except Exception:
                            continue
            if not used_list:
                used_list = ['ephemeral']
            resp['derived']['source_ports_used'] = used_list
        except Exception:
            pass

        return self.json_response(start_response, resp)
