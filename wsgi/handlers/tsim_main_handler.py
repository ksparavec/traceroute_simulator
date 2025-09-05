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
from typing import Dict, Any, List
from .tsim_base_handler import TsimBaseHandler
from services.tsim_validator_service import TsimValidatorService
from services.tsim_port_parser_service import TsimPortParserService
from services.tsim_executor import TsimExecutor
from services.tsim_pdf_generator import TsimPDFGenerator
from services.tsim_lock_manager_service import TsimLockManagerService
from services.tsim_timing_service import TsimTimingService
from services.tsim_progress_tracker import TsimProgressTracker


class TsimMainHandler(TsimBaseHandler):
    """Handler for main test execution requests"""
    
    def __init__(self, config_service, session_manager, logger_service):
        """Initialize main handler
        
        Args:
            config_service: TsimConfigService instance
            session_manager: TsimSessionManager instance
            logger_service: TsimLoggerService instance
        """
        super().__init__(session_manager, logger_service)
        self.config = config_service
        self.validator = TsimValidatorService()
        self.port_parser = TsimPortParserService()
        self.lock_manager = TsimLockManagerService(config_service)
        self.timing_service = TsimTimingService()
        self.executor = TsimExecutor(config_service, self.lock_manager, self.timing_service)
        self.pdf_generator = TsimPDFGenerator(config_service)
        self.progress_tracker = TsimProgressTracker(config_service)
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
            return self.error_response(start_response, 'Authentication required', '401 Unauthorized')
        
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
        # Parse POST data
        try:
            data = self.parse_post_data(environ)
        except Exception as e:
            self.logger.error(f"Failed to parse POST data: {e}")
            return self.error_response(start_response, 'Invalid request data')
        
        # Extract and validate parameters
        source_ip = data.get('source_ip', '').strip()
        source_port = data.get('source_port', '').strip() or None
        dest_ip = data.get('dest_ip', '').strip()
        port_mode = data.get('port_mode', 'quick')
        default_protocol = data.get('default_protocol', 'tcp')
        user_trace_data = data.get('user_trace_data', '').strip() or None
        
        # Validate IPs
        if not self.validator.validate_ip(source_ip):
            return self.error_response(start_response, f'Invalid source IP: {source_ip}')
        
        if not self.validator.validate_ip(dest_ip):
            return self.error_response(start_response, f'Invalid destination IP: {dest_ip}')
        
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
            elif port_mode == 'custom':
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
        
        # Validate user trace data if provided
        if user_trace_data:
            is_valid, error = self.validator.validate_trace_data(user_trace_data)
            if not is_valid:
                return self.error_response(start_response, f'Invalid trace data: {error}')
        
        # Generate run ID
        run_id = str(uuid.uuid4())
        
        # Create run directory and initial progress files
        run_dir = self.progress_tracker.create_run_directory(run_id)
        self.progress_tracker.log_phase(run_id, 'parse_args', 'Parsing arguments')
        
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
        
        # Execute test asynchronously
        try:
            # Start overall timing
            self.timing_service.start_timer(f"test_{run_id}")
            self.progress_tracker.log_phase(run_id, 'START', 'Starting test execution')
            
            # Execute the entire test pipeline asynchronously
            task_info = self.executor.tsim_execute_async(
                run_id, source_ip, dest_ip, source_port, port_protocol_list, user_trace_data
            )
            
            # Log that the test has been started in background
            self.progress_tracker.log_phase(run_id, 'BACKGROUND', 'Test running in background')
            
            # For async execution, we don't wait for results
            # The progress page will poll for updates
            final_pdf = None
            summary_data = {
                'source_ip': source_ip,
                'dest_ip': dest_ip,
                'service_count': len(port_protocol_list),
                'services': [
                    {
                        'name': f"{port}/{protocol}",
                        'port': port,
                        'protocol': protocol,
                        'status': 'PENDING'
                    }
                    for port, protocol in port_protocol_list
                ],
                'task_info': task_info
            }
            
            # For async execution, we don't have results yet
            # Generate shareable link with HMAC token for progress monitoring
            secret_key = self.config.get('secret_key', 'default-secret-key')
            token = hmac.new(
                key=secret_key.encode(),
                msg=run_id.encode(),
                digestmod=hashlib.sha256
            ).hexdigest()
            
            # Build share URL for progress page
            base_url = environ.get('HTTP_HOST', 'localhost')
            share_link = f"https://{base_url}/progress.html?id={run_id}&token={token}"
            
            # Save initial test info to session
            test_result = {
                'status': 'running',
                'task_info': task_info,
                'summary': summary_data,
                'share_link': share_link,
                'token': token
            }
            
            session_id = self.get_session_id(environ)
            self.session_manager.save_test_result(session_id, run_id, test_result)
            
            # Log that test started
            self.logger.info(
                f"Test {run_id} started in background mode"
            )
            
            # Check if this is an AJAX request
            is_ajax = environ.get('HTTP_X_REQUESTED_WITH', '').lower() == 'xmlhttprequest'
            accept_header = environ.get('HTTP_ACCEPT', '')
            content_type = environ.get('CONTENT_TYPE', '')
            
            # If Content-Type is application/json, it's likely AJAX
            # If it's application/x-www-form-urlencoded, it's likely a regular form submission
            wants_json = 'application/json' in accept_header or 'application/json' in content_type
            
            if is_ajax or wants_json:
                # Return JSON for AJAX requests
                return self.json_response(start_response, {
                    'success': True,
                    'run_id': run_id,
                    'message': 'Test started successfully',
                    'status': 'running',
                    'redirect': f'/progress.html?id={run_id}',
                    'share_link': share_link,
                    'token': token
                })
            else:
                # Perform HTTP redirect for regular form submission to progress page
                redirect_url = f'/progress.html?id={run_id}'
                response_headers = [
                    ('Location', redirect_url),
                    ('Cache-Control', 'no-cache, no-store, must-revalidate')
                ]
                
                start_response('302 Found', response_headers)
                return [b'']
            
        except Exception as e:
            self.logger.error(f"Test execution failed for {run_id}: {e}", exc_info=True)
            
            # Log failure
            self.logger_service.log_audit(
                'test_failed',
                session.get('username'),
                client_ip,
                False,
                {
                    'run_id': run_id,
                    'error': str(e)
                }
            )
            
            return self.error_response(
                start_response,
                f'Test execution failed: {str(e)}',
                '500 Internal Server Error'
            )
    
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