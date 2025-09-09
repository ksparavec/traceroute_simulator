#!/usr/bin/env -S python3 -B -u
"""
TSIM Logout Handler
Handles user logout requests
"""

import json
import logging
from typing import Dict, Any, List
from .tsim_base_handler import TsimBaseHandler


class TsimLogoutHandler(TsimBaseHandler):
    """Handler for logout requests"""
    
    def __init__(self, session_manager, logger_service):
        """Initialize logout handler
        
        Args:
            session_manager: TsimSessionManager instance
            logger_service: TsimLoggerService instance
        """
        super().__init__(session_manager, logger_service)
        self.logger = logging.getLogger('tsim.handler.logout')
    
    def handle(self, environ: Dict[str, Any], start_response) -> List[bytes]:
        """Handle logout request
        
        Args:
            environ: WSGI environment
            start_response: WSGI start_response callable
            
        Returns:
            Response body
        """
        # Get session ID
        session_id = self.get_session_id(environ)
        
        if session_id:
            # Get session data for logging
            session = self.session_manager.get_session(session_id)
            username = session.get('username', 'unknown') if session else 'unknown'
            client_ip = self.get_client_ip(environ)
            
            # Destroy session
            if self.session_manager.destroy_session(session_id):
                # Log successful logout
                self.logger_service.log_audit(
                    'logout',
                    username,
                    client_ip,
                    True,
                    {}
                )
                
                self.logger.info(f"User {username} logged out from {client_ip}")
                
                # Check if this is an AJAX request
                is_ajax = environ.get('HTTP_X_REQUESTED_WITH', '').lower() == 'xmlhttprequest'
                accept_header = environ.get('HTTP_ACCEPT', '')
                wants_json = 'application/json' in accept_header
                
                if is_ajax or wants_json:
                    # Return JSON for AJAX requests
                    response_data = {
                        'success': True,
                        'message': 'Logged out successfully',
                        'redirect': '/login.html'
                    }
                    
                    response_body = json.dumps(response_data).encode('utf-8')
                    response_headers = [
                        ('Content-Type', 'application/json; charset=utf-8'),
                        ('Content-Length', str(len(response_body))),
                        ('Set-Cookie', 'session_id=; Max-Age=0; Path=/; HttpOnly; Secure'),
                        ('Cache-Control', 'no-cache, no-store, must-revalidate')
                    ]
                    
                    start_response('200 OK', response_headers)
                    return [response_body]
                else:
                    # Perform HTTP redirect for direct navigation
                    response_headers = [
                        ('Location', '/login.html'),
                        ('Set-Cookie', 'session_id=; Max-Age=0; Path=/; HttpOnly; Secure'),
                        ('Cache-Control', 'no-cache, no-store, must-revalidate')
                    ]
                    
                    start_response('302 Found', response_headers)
                    return [b'']
            else:
                self.logger.warning(f"Failed to destroy session {session_id}")
                return self.error_response(
                    start_response,
                    'Logout failed',
                    '500 Internal Server Error'
                )
        else:
            # No session to logout
            # Check if this is an AJAX request
            is_ajax = environ.get('HTTP_X_REQUESTED_WITH', '').lower() == 'xmlhttprequest'
            accept_header = environ.get('HTTP_ACCEPT', '')
            wants_json = 'application/json' in accept_header
            
            if is_ajax or wants_json:
                return self.json_response(start_response, {
                    'success': True,
                    'message': 'Not logged in',
                    'redirect': '/login.html'
                })
            else:
                # Redirect to login page
                response_headers = [
                    ('Location', '/login.html'),
                    ('Cache-Control', 'no-cache, no-store, must-revalidate')
                ]
                
                start_response('302 Found', response_headers)
                return [b'']