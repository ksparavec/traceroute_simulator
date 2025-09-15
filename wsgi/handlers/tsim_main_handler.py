#!/usr/bin/env -S python3 -B -u
"""
TSIM Main Handler
Handles main test execution requests
"""

import json
import uuid
import logging
import hmac
import hashlib
import os
from typing import Dict, Any, List
from .tsim_base_handler import TsimBaseHandler
from services.tsim_validator_service import TsimValidatorService
from services.tsim_port_parser_service import TsimPortParserService
from services.tsim_executor import TsimExecutor
from services.tsim_lock_manager_service import TsimLockManagerService
from services.tsim_queue_service import TsimQueueService
from services.tsim_timing_service import TsimTimingService
from services.tsim_progress_tracker import TsimProgressTracker


class TsimMainHandler(TsimBaseHandler):
    """Handler for main test execution requests"""
    
    def __init__(self, config_service, session_manager, logger_service, 
                 progress_tracker=None, hybrid_executor=None, queue_service: TsimQueueService = None,
                 lock_manager: TsimLockManagerService = None):
        """Initialize main handler
        
        Args:
            config_service: TsimConfigService instance
            session_manager: TsimSessionManager instance
            logger_service: TsimLoggerService instance
            progress_tracker: Optional shared TsimProgressTracker instance
            hybrid_executor: Optional shared TsimHybridExecutor instance
        """
        super().__init__(session_manager, logger_service)
        self.config = config_service
        self.validator = TsimValidatorService()
        self.port_parser = TsimPortParserService()
        self.lock_manager = lock_manager or TsimLockManagerService(config_service)
        self.timing_service = TsimTimingService()
        
        # Use shared instances if provided, otherwise create new ones
        self.progress_tracker = progress_tracker or TsimProgressTracker(config_service)
        self.queue_service = queue_service or TsimQueueService(config_service)
        
        # Create executor and set hybrid executor (not used directly for immediate runs anymore)
        self.executor = TsimExecutor(config_service, self.lock_manager, 
                                    self.timing_service, self.progress_tracker)
        if hybrid_executor:
            self.executor.set_hybrid_executor(hybrid_executor)
        
        # PDF generation is handled by the hybrid executor; no direct PDF generator needed here
        self.logger = logging.getLogger('tsim.handler.main')
    
    def handle(self, environ: Dict[str, Any], start_response) -> List[bytes]:
        """Handle test execution request
        
        Args:
            environ: WSGI environment
            start_response: WSGI start_response callable
            
        Returns:
            Response body
        """
        # Check session
        session = self.validate_session(environ)
        if not session:
            # Distinguish between browser form submission and AJAX/JSON
            is_ajax = environ.get('HTTP_X_REQUESTED_WITH', '').lower() == 'xmlhttprequest'
            accept_header = environ.get('HTTP_ACCEPT', '')
            content_type = environ.get('CONTENT_TYPE', '')
            wants_json = 'application/json' in accept_header or 'application/json' in content_type

            if is_ajax or wants_json:
                return self.error_response(start_response, 'Authentication required', '401 Unauthorized')
            else:
                # Redirect interactive users to login page instead of showing JSON
                return self.redirect_response(start_response, '/login.html')
        
        method = environ.get('REQUEST_METHOD', 'GET')
        
        if method == 'POST':
            return self._handle_post(environ, start_response, session)
        elif method == 'GET':
            return self._handle_get(environ, start_response, session)
        else:
            return self.error_response(start_response, 'Method not allowed', '405 Method Not Allowed')
    
    def _handle_get(self, environ: Dict[str, Any], start_response, 
                    session: Dict[str, Any]) -> List[bytes]:
        """Handle GET request - return test status or form data
        
        Args:
            environ: WSGI environment
            start_response: WSGI start_response callable
            session: Session data
            
        Returns:
            Response body
        """
        # Check for run_id parameter to get test status
        params = self.parse_query_params(environ)
        run_id = params.get('run_id')
        
        if run_id:
            # Get test status
            progress = self.executor.get_progress(run_id)
            if progress:
                return self.json_response(start_response, {
                    'success': True,
                    'run_id': run_id,
                    'progress': progress
                })
            else:
                return self.error_response(start_response, 'Test not found', '404 Not Found')
        
        # Return form configuration
        return self.json_response(start_response, {
            'success': True,
            'config': {
                'max_services': self.config.get('max_services', 10),
                'quick_ports': self.port_parser.get_quick_ports(),
                'common_ports': list(self.port_parser.get_common_ports().keys()),
                'session': {
                    'username': session.get('username'),
                    'role': session.get('role', 'user')
                }
            }
        })
    
    def _handle_post(self, environ: Dict[str, Any], start_response,
                    session: Dict[str, Any]) -> List[bytes]:
        """Handle POST request - execute test
        
        Args:
            environ: WSGI environment
            start_response: WSGI start_response callable
            session: Session data
            
        Returns:
            Response body
        """
        # Check if facts are valid before processing
        if os.environ.get('TSIM_FACTS_INVALID') == '1':
            self.logger.error("Network analysis request rejected: Facts validation failed")
            return self.error_response(
                start_response, 
                'Network analysis is currently unavailable. Please contact your system administrator.',
                '503 Service Unavailable'
            )
        
        # Parse POST data
        try:
            data = self.parse_post_data(environ)
        except Exception as e:
            self.logger.error(f"Failed to parse POST data: {e}")
            return self.error_response(start_response, 'Invalid request data')
        
        # Determine mode and extract parameters
        mode = self.config.get('traceroute_simulator_mode', 'prod')
        source_ip = data.get('source_ip', '').strip()
        source_port = data.get('source_port', '').strip() or None
        dest_ip = data.get('dest_ip', '').strip()
        port_mode = data.get('port_mode', 'quick')
        default_protocol = data.get('default_protocol', 'tcp')
        user_trace_data = data.get('user_trace_data', '').strip() or None

        # Enforce allowed execution paths by mode
        if mode == 'prod':
            # In prod mode, require source/destination IPs and do not accept user trace input
            if not self.validator.validate_ip(source_ip):
                return self.error_response(start_response, f'Invalid source IP: {source_ip}')
            if not self.validator.validate_ip(dest_ip):
                return self.error_response(start_response, f'Invalid destination IP: {dest_ip}')
            # Ignore any user-provided trace data to avoid alternate paths
            user_trace_data = None
        else:
            # Test mode: require user trace data; source/destination fields are hidden in UI
            if not user_trace_data:
                return self.error_response(start_response, 'Trace file is required in test mode')
            # Validate that provided trace is valid JSON and try to infer IPs
            is_valid, error = self.validator.validate_trace_data(user_trace_data)
            if not is_valid:
                return self.error_response(start_response, f'Invalid trace data: {error}')
            try:
                trace_json = json.loads(user_trace_data)
            except Exception:
                return self.error_response(start_response, 'Trace file must be valid JSON')
            # Try to infer source/destination IPs from trace JSON
            def _get(d: dict, keys: list):
                for k in keys:
                    if isinstance(d, dict) and k in d and isinstance(d[k], str) and d[k].strip():
                        return d[k].strip()
                return None
            inferred_source = _get(trace_json, ['source_ip', 'source', 'src'])
            inferred_dest = _get(trace_json, ['dest_ip', 'destination', 'dest', 'dst'])
            if not inferred_source or not self.validator.validate_ip(inferred_source):
                return self.error_response(start_response, 'Trace file missing valid source IP')
            if not inferred_dest or not self.validator.validate_ip(inferred_dest):
                return self.error_response(start_response, 'Trace file missing valid destination IP')
            source_ip = inferred_source
            dest_ip = inferred_dest
        
        # Validate source port if provided
        if source_port:
            is_valid, error = self.validator.validate_port(source_port)
            if not is_valid:
                return self.error_response(start_response, f'Invalid source port: {error}')
        
        # Parse destination ports based on mode
        try:
            if port_mode == 'quick':
                # Use quick ports
                quick_ports = data.get('quick_ports', [])
                if isinstance(quick_ports, str):
                    quick_ports = [quick_ports]
                dest_port_spec = ','.join(quick_ports) if quick_ports else ','.join(self.port_parser.get_quick_ports())
            elif port_mode in ('custom', 'manual'):
                # Use custom port specification
                dest_port_spec = data.get('dest_ports', '').strip()
                if not dest_port_spec:
                    return self.error_response(start_response, 'No destination ports specified')
            else:
                # Use common ports
                dest_port_spec = ','.join(self.port_parser.get_quick_ports())
            
            # Parse port specifications
            port_protocol_list = self.port_parser.parse_port_spec(
                dest_port_spec, 
                default_protocol,
                max_services=self.config.get('max_services', 10)
            )
            
        except ValueError as e:
            return self.error_response(start_response, f'Invalid port specification: {str(e)}')
        
        # At this point, user_trace_data is only non-None in test mode; already validated above
        
        # Allow multiple jobs per user; global queue will serialize execution
        username = session.get('username', 'unknown')
        
        # Generate run ID
        run_id = str(uuid.uuid4())
        
        # Create run directory and initial progress files
        run_dir = self.progress_tracker.create_run_directory(run_id)
        self.progress_tracker.log_phase(run_id, 'parse_args', 'Parsing arguments')
        
        # Estimate expected steps to enable precise percentage progress
        try:
            base_steps = 21  # static phases incl. cleanup/pdf/complete
            per_service_steps = 9  # per-service phases incl. file_created
            expected_steps = base_steps + per_service_steps * len(port_protocol_list)
            self.progress_tracker.set_expected_steps(run_id, expected_steps)
        except Exception:
            pass
        
        # Do not register per-user active run; queuing handles concurrency globally
        
        # Log test execution
        client_ip = self.get_client_ip(environ)
        self.logger_service.log_audit(
            'test_execution',
            session.get('username'),
            client_ip,
            True,
            {
                'run_id': run_id,
                'source_ip': source_ip,
                'dest_ip': dest_ip,
                'services': len(port_protocol_list)
            }
        )
        
        # Enqueue job instead of starting immediately
        try:
            # Prepare parameters for executor
            params = {
                'run_id': run_id,
                'source_ip': source_ip,
                'dest_ip': dest_ip,
                'source_port': source_port,
                'port_protocol_list': port_protocol_list,
                'user_trace_data': user_trace_data,
                'run_dir': str(self.config.get('run_dir', '/dev/shm/tsim/runs'))
            }

            position = self.queue_service.enqueue(run_id, username, params)
            # Log queued state to progress
            self.progress_tracker.log_phase(run_id, 'QUEUED', f'In queue (position {position})')

            # Generate shareable link with HMAC token for progress monitoring
            secret_key = self.config.get('secret_key', 'default-secret-key')
            token = hmac.new(
                key=secret_key.encode(),
                msg=run_id.encode(),
                digestmod=hashlib.sha256
            ).hexdigest()
            base_url = environ.get('HTTP_HOST', 'localhost')
            share_link = f"https://{base_url}/progress.html?id={run_id}&token={token}"

            # Save initial test info to session
            summary_data = {
                'source_ip': source_ip,
                'dest_ip': dest_ip,
                'service_count': len(port_protocol_list),
                'services': [
                    {'name': f"{port}/{protocol}", 'port': port, 'protocol': protocol, 'status': 'PENDING'}
                    for port, protocol in port_protocol_list
                ]
            }
            test_result = {
                'status': 'queued',
                'run_id': run_id,
                'summary': summary_data,
                'share_link': share_link,
                'token': token,
                'queue_position': position
            }
            session_id = self.get_session_id(environ)
            self.session_manager.save_test_result(session_id, run_id, test_result)

            # Response (AJAX or redirect) with queued status
            is_ajax = environ.get('HTTP_X_REQUESTED_WITH', '').lower() == 'xmlhttprequest'
            accept_header = environ.get('HTTP_ACCEPT', '')
            content_type = environ.get('CONTENT_TYPE', '')
            wants_json = 'application/json' in accept_header or 'application/json' in content_type

            if is_ajax or wants_json:
                return self.json_response(start_response, {
                    'success': True,
                    'run_id': run_id,
                    'message': f'Your test has been queued at position {position}',
                    'status': 'queued',
                    'position': position,
                    'redirect': f'/progress.html?id={run_id}',
                    'share_link': share_link,
                    'token': token
                })
            else:
                redirect_url = f'/progress.html?id={run_id}'
                response_headers = [
                    ('Location', redirect_url),
                    ('Cache-Control', 'no-cache, no-store, must-revalidate')
                ]
                start_response('302 Found', response_headers)
                return [b'']

        except Exception as e:
            self.logger.error(f"Queueing failed for {run_id}: {e}", exc_info=True)
            return self.error_response(start_response, f'Queueing failed: {str(e)}', '500 Internal Server Error')
    
    def _extract_service_from_filename(self, filename):
        """Extract service name from result filename
        
        Args:
            filename: Result filename
            
        Returns:
            Service name
        """
        # Filename format: {run_id}_{port}_{protocol}_results.json
        from pathlib import Path
        parts = Path(filename).stem.split('_')
        if len(parts) >= 3:
            return f"{parts[-3]}/{parts[-2]}"
        return "unknown"
