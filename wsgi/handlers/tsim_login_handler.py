#!/usr/bin/env -S python3 -B -u
"""
TSIM Login Handler
Handles user authentication requests
"""

import json
import logging
from typing import Dict, Any, List
from .tsim_base_handler import TsimBaseHandler
from services.tsim_auth_service import TsimAuthService


class TsimLoginHandler(TsimBaseHandler):
    """Handler for login requests"""
    
    def __init__(self, config_service, session_manager, logger_service):
        """Initialize login handler
        
        Args:
            config_service: TsimConfigService instance
            session_manager: TsimSessionManager instance
            logger_service: TsimLoggerService instance
        """
        super().__init__(session_manager, logger_service)
        self.config = config_service
        self.auth_service = TsimAuthService(config_service)
        self.logger = logging.getLogger('tsim.handler.login')
    
    def handle(self, environ: Dict[str, Any], start_response) -> List[bytes]:
        """Handle login request
        
        Args:
            environ: WSGI environment
            start_response: WSGI start_response callable
            
        Returns:
            Response body
        """
        method = environ.get('REQUEST_METHOD', 'GET')
        
        if method == 'GET':
            # Return login form or info
            return self._handle_get(environ, start_response)
        elif method == 'POST':
            # Process login
            return self._handle_post(environ, start_response)
        else:
            return self.error_response(start_response, 'Method not allowed', '405 Method Not Allowed')
    
    def _handle_get(self, environ: Dict[str, Any], start_response) -> List[bytes]:
        """Handle GET request - return login info
        
        Args:
            environ: WSGI environment
            start_response: WSGI start_response callable
            
        Returns:
            Response body
        """
        # Check if user is already logged in
        session = self.validate_session(environ)
        
        if session:
            # User is already logged in
            return self.json_response(start_response, {
                'success': True,
                'logged_in': True,
                'username': session.get('username'),
                'role': session.get('role', 'user')
            })
        else:
            # User is not logged in
            return self.json_response(start_response, {
                'success': True,
                'logged_in': False,
                'message': 'Please login'
            })
    
    def _handle_post(self, environ: Dict[str, Any], start_response) -> List[bytes]:
        """Handle POST request - process login
        
        Args:
            environ: WSGI environment
            start_response: WSGI start_response callable
            
        Returns:
            Response body
        """
        # Get client IP for audit logging
        client_ip = self.get_client_ip(environ)
        
        # Parse POST data
        try:
            post_data = self.parse_post_data(environ)
        except Exception as e:
            self.logger.error(f"Failed to parse POST data: {e}")
            return self.error_response(start_response, 'Invalid request data')
        
        # Extract credentials
        username = post_data.get('username', '').strip()
        password = post_data.get('password', '').strip()
        
        # Validate inputs
        if not username or not password:
            self.logger_service.log_audit(
                'login_attempt',
                username or 'unknown',
                client_ip,
                False,
                {'reason': 'missing_credentials'}
            )
            return self.error_response(start_response, 'Username and password required')
        
        # Authenticate user
        success, error_msg, user_data = self.auth_service.authenticate(username, password)
        
        if not success:
            # Authentication failed
            self.logger_service.log_audit(
                'login_failed',
                username,
                client_ip,
                False,
                {'reason': error_msg}
            )
            
            self.logger.warning(f"Login failed for {username} from {client_ip}: {error_msg}")
            
            return self.error_response(start_response, error_msg or 'Authentication failed')
        
        # Authentication successful - create session
        try:
            session_id, cookie_header = self.session_manager.create_session(
                username,
                client_ip,
                user_data.get('role', 'user')
            )
            
            # Log successful login
            self.logger_service.log_audit(
                'login_success',
                username,
                client_ip,
                True,
                {'role': user_data.get('role', 'user')}
            )
            
            self.logger.info(f"User {username} logged in from {client_ip}")
            
            # Return success response with cookie
            response_data = {
                'success': True,
                'message': 'Login successful',
                'username': username,
                'role': user_data.get('role', 'user'),
                'redirect': '/form.html'  # Default redirect
            }
            
            # Check for redirect parameter
            redirect_to = post_data.get('redirect', '/form.html')
            if redirect_to and redirect_to.startswith('/'):
                response_data['redirect'] = redirect_to
            
            # Send response with session cookie
            response_body = json.dumps(response_data).encode('utf-8')
            response_headers = [
                ('Content-Type', 'application/json; charset=utf-8'),
                ('Content-Length', str(len(response_body))),
                ('Set-Cookie', cookie_header),
                ('Cache-Control', 'no-cache, no-store, must-revalidate')
            ]
            
            start_response('200 OK', response_headers)
            return [response_body]
            
        except Exception as e:
            self.logger.error(f"Failed to create session for {username}: {e}")
            self.logger_service.log_audit(
                'login_error',
                username,
                client_ip,
                False,
                {'error': str(e)}
            )
            return self.error_response(
                start_response, 
                'Failed to create session',
                '500 Internal Server Error'
            )