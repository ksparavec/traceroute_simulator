#!/usr/bin/env -S python3 -B -u
"""
Base handler class for all TSIM request handlers
"""

from abc import ABC, abstractmethod
from urllib.parse import parse_qs, urlparse
from http.cookies import SimpleCookie
import json
import cgi
import io
import logging
from typing import Dict, Any, Optional, List, Tuple


class TsimBaseHandler(ABC):
    """Base class for all TSIM handlers"""
    
    def __init__(self, session_manager=None, logger_service=None):
        """Initialize base handler
        
        Args:
            session_manager: TsimSessionManager instance
            logger_service: TsimLoggerService instance
        """
        self.session_manager = session_manager
        self.logger_service = logger_service
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def parse_post_data(self, environ: Dict[str, Any]) -> Dict[str, Any]:
        """Parse POST data from environ
        
        Args:
            environ: WSGI environ dict
            
        Returns:
            Parsed POST data as dict
        """
        try:
            content_length = int(environ.get('CONTENT_LENGTH', 0))
        except ValueError:
            content_length = 0
        
        if content_length > 0:
            body = environ['wsgi.input'].read(content_length)
            content_type = environ.get('CONTENT_TYPE', '')
            
            if content_type.startswith('application/x-www-form-urlencoded'):
                # Parse URL-encoded form data
                parsed = parse_qs(body.decode('utf-8'))
                # Convert single-item lists to strings for convenience
                result = {}
                for key, value in parsed.items():
                    if len(value) == 1:
                        result[key] = value[0]
                    else:
                        result[key] = value
                return result
                
            elif content_type.startswith('multipart/form-data'):
                # Handle multipart form data
                fp = io.BytesIO(body)
                form = cgi.FieldStorage(
                    fp=fp, 
                    environ=environ, 
                    keep_blank_values=True
                )
                result = {}
                for key in form.keys():
                    field = form[key]
                    if isinstance(field, list):
                        result[key] = [item.value for item in field]
                    else:
                        result[key] = field.value
                return result
                
            elif content_type.startswith('application/json'):
                # Parse JSON data
                return json.loads(body.decode('utf-8'))
        
        return {}
    
    def parse_query_params(self, environ: Dict[str, Any]) -> Dict[str, Any]:
        """Parse query parameters from environ
        
        Args:
            environ: WSGI environ dict
            
        Returns:
            Parsed query parameters as dict
        """
        query_string = environ.get('QUERY_STRING', '')
        if query_string:
            parsed = parse_qs(query_string)
            # Convert single-item lists to strings for convenience
            result = {}
            for key, value in parsed.items():
                if len(value) == 1:
                    result[key] = value[0]
                else:
                    result[key] = value
            return result
        return {}
    
    def get_query_param(self, environ: Dict[str, Any], param: str, 
                       default: Optional[str] = None) -> Optional[str]:
        """Get a single query parameter
        
        Args:
            environ: WSGI environ dict
            param: Parameter name
            default: Default value if not found
            
        Returns:
            Parameter value or default
        """
        params = self.parse_query_params(environ)
        return params.get(param, default)
    
    def parse_cookies(self, environ: Dict[str, Any]) -> SimpleCookie:
        """Parse cookies from environ
        
        Args:
            environ: WSGI environ dict
            
        Returns:
            SimpleCookie object
        """
        cookie_str = environ.get('HTTP_COOKIE', '')
        cookies = SimpleCookie(cookie_str)
        return cookies
    
    def get_session_id(self, environ: Dict[str, Any]) -> Optional[str]:
        """Extract session ID from cookies
        
        Args:
            environ: WSGI environ dict
            
        Returns:
            Session ID or None
        """
        cookies = self.parse_cookies(environ)
        if 'session_id' in cookies:
            return cookies['session_id'].value
        return None
    
    def validate_session(self, environ: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Validate session and return session data
        
        Args:
            environ: WSGI environ dict
            
        Returns:
            Session data dict or None if invalid
        """
        session_id = self.get_session_id(environ)
        if not session_id:
            return None
        
        if self.session_manager:
            return self.session_manager.get_session(session_id)
        
        return None
    
    def json_response(self, start_response, data: Any, 
                     status: str = '200 OK') -> List[bytes]:
        """Send JSON response
        
        Args:
            start_response: WSGI start_response callable
            data: Data to serialize as JSON
            status: HTTP status string
            
        Returns:
            Response body as list of bytes
        """
        # Try to use ujson if available for better performance
        try:
            import ujson
            response_body = ujson.dumps(data).encode('utf-8')
        except ImportError:
            response_body = json.dumps(data).encode('utf-8')
        
        # Build response headers with proper CGI-style headers
        response_headers = [
            ('Content-Type', 'application/json; charset=utf-8'),
            ('Content-Length', str(len(response_body))),
            ('Cache-Control', 'no-cache, no-store, must-revalidate'),
            ('Pragma', 'no-cache'),
            ('Expires', '0'),
            ('X-Content-Type-Options', 'nosniff'),
            ('X-Frame-Options', 'DENY')
        ]
        
        # Add CORS headers if configured
        if hasattr(self, 'config') and self.config:
            # Backward-compat: cors_origin single value
            cors_origin = self.config.get('cors_origin')
            cors_cfg = self.config.get('cors', {}) if hasattr(self.config, 'get') else {}
            allow_cors = False
            origin_value = None

            if cors_origin:
                allow_cors = True
                origin_value = cors_origin
            elif isinstance(cors_cfg, dict) and cors_cfg.get('enabled'):
                allow_cors = True
                origins = cors_cfg.get('allowed_origins') or ['*']
                origin_value = origins[0] if isinstance(origins, list) and origins else '*'

            if allow_cors:
                response_headers.append(('Access-Control-Allow-Origin', origin_value))
                response_headers.append(('Access-Control-Allow-Methods', ', '.join(cors_cfg.get('allowed_methods', ['GET','POST','OPTIONS']))))
                response_headers.append(('Access-Control-Allow-Headers', ', '.join(cors_cfg.get('allowed_headers', ['Content-Type','X-Requested-With']))))
        start_response(status, response_headers)
        return [response_body]
    
    def error_response(self, start_response, error: str, 
                      status: str = '400 Bad Request',
                      details: Optional[Dict[str, Any]] = None) -> List[bytes]:
        """Send error response
        
        Args:
            start_response: WSGI start_response callable
            error: Error message
            status: HTTP status string
            details: Additional error details
            
        Returns:
            Response body as list of bytes
        """
        # Log error
        if self.logger_service:
            self.logger_service.log_error(error, details)
        
        # Prepare response data
        response_data = {
            'success': False,
            'error': error
        }
        if details:
            response_data['details'] = details
        
        # Extract status code for proper logging
        status_parts = status.split(None, 1)
        status_code = status_parts[0] if status_parts else '400'
        
        # Send appropriate response based on status
        if status_code.startswith('5'):
            # Server error - include less detail
            response_data = {
                'success': False,
                'error': 'Internal server error'
            }
            if details and details.get('show_to_user'):
                response_data['error'] = error
        
        return self.json_response(start_response, response_data, status)
    
    def redirect_response(self, start_response, location: str, 
                         cookie: Optional[str] = None) -> List[bytes]:
        """Send redirect response
        
        Args:
            start_response: WSGI start_response callable
            location: Redirect location
            cookie: Optional cookie header
            
        Returns:
            Response body as list of bytes
        """
        headers = [
            ('Location', location),
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Cache-Control', 'no-cache, no-store, must-revalidate')
        ]
        if cookie:
            headers.append(('Set-Cookie', cookie))
        
        start_response('302 Found', headers)
        
        # Provide a simple HTML fallback for browsers that don't auto-redirect
        html = f'''<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="refresh" content="0;url={location}">
    <title>Redirecting...</title>
</head>
<body>
    <p>Redirecting to <a href="{location}">{location}</a>...</p>
</body>
</html>'''.encode('utf-8')
        
        return [html]
    
    def stream_response(self, start_response, 
                       content_type: str = 'text/plain') -> Tuple[Any, ...]:
        """Setup streaming response (e.g., for Server-Sent Events)
        
        Args:
            start_response: WSGI start_response callable
            content_type: Content type for response
            
        Returns:
            start_response result
        """
        headers = [
            ('Content-Type', content_type),
            ('Cache-Control', 'no-cache'),
            ('Connection', 'keep-alive'),
            ('X-Accel-Buffering', 'no'),  # Disable Nginx buffering if present
        ]
        
        if content_type == 'text/event-stream':
            headers.append(('Access-Control-Allow-Origin', '*'))
        
        return start_response('200 OK', headers)
    
    def get_client_ip(self, environ: Dict[str, Any]) -> str:
        """Get client IP address, handling proxies
        
        Args:
            environ: WSGI environ dict
            
        Returns:
            Client IP address
        """
        # Check for proxy headers first
        if 'HTTP_X_FORWARDED_FOR' in environ:
            # X-Forwarded-For can contain multiple IPs
            ips = environ['HTTP_X_FORWARDED_FOR'].split(',')
            return ips[0].strip()
        
        if 'HTTP_X_REAL_IP' in environ:
            return environ['HTTP_X_REAL_IP']
        
        # Fall back to direct connection
        return environ.get('REMOTE_ADDR', 'unknown')
    
    def log_request(self, environ: Dict[str, Any], status: str = '200',
                   message: Optional[str] = None):
        """Log request details
        
        Args:
            environ: WSGI environ dict
            status: HTTP status code
            message: Optional log message
        """
        if self.logger_service:
            method = environ.get('REQUEST_METHOD', 'UNKNOWN')
            path = environ.get('PATH_INFO', '/')
            client_ip = self.get_client_ip(environ)
            
            log_msg = f"{method} {path} from {client_ip} - {status}"
            if message:
                log_msg += f" - {message}"
            
            if status.startswith('2'):
                self.logger_service.log_info(log_msg)
            elif status.startswith('4'):
                self.logger_service.log_warning(log_msg)
            else:
                self.logger_service.log_error(log_msg)
    
    @abstractmethod
    def handle(self, environ: Dict[str, Any], start_response) -> List[bytes]:
        """Handle the request
        
        Args:
            environ: WSGI environ dict
            start_response: WSGI start_response callable
            
        Returns:
            Response body as list of bytes
        """
        pass
