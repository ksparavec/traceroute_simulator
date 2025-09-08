#!/usr/bin/env -S python3 -B -u
"""
TSIM WSGI Application
NOTE: All imports should already be preloaded by app.wsgi for maximum performance
"""

import json
import os
import sys
import traceback
import logging
from urllib.parse import parse_qs
from http.cookies import SimpleCookie

# All handlers are already preloaded in app.wsgi
from handlers.tsim_login_handler import TsimLoginHandler
from handlers.tsim_logout_handler import TsimLogoutHandler
from handlers.tsim_main_handler import TsimMainHandler
from handlers.tsim_pdf_handler import TsimPDFHandler
from handlers.tsim_progress_handler import TsimProgressHandler
from handlers.tsim_progress_stream_handler import TsimProgressStreamHandler
from handlers.tsim_services_config_handler import TsimServicesConfigHandler
from handlers.tsim_test_config_handler import TsimTestConfigHandler
from handlers.tsim_cleanup_handler import TsimCleanupHandler

# All services are already preloaded in app.wsgi
from services.tsim_session_manager import TsimSessionManager
from services.tsim_config_service import TsimConfigService
from services.tsim_logger_service import TsimLoggerService
from services.tsim_progress_tracker import TsimProgressTracker
from services.tsim_hybrid_executor import TsimHybridExecutor


class TsimWSGIApp:
    """Main WSGI Application"""
    
    def __init__(self):
        """Initialize shared services once at startup
        
        PERFORMANCE NOTE: All service classes are already loaded in memory
        from app.wsgi preloading. This just instantiates them.
        """
        self.logger = logging.getLogger('tsim.app')
        self.logger.info("Initializing TSIM WSGI Application")
        
        # Initialize core services
        try:
            self.config = TsimConfigService()
            self.session_manager = TsimSessionManager(self.config)
            self.logger_service = TsimLoggerService(self.config)
            
            # Initialize shared progress tracker and hybrid executor
            self.progress_tracker = TsimProgressTracker(self.config)
            self.hybrid_executor = TsimHybridExecutor(self.config, self.progress_tracker)
            
            self.logger.info("Core services initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize core services: {e}")
            raise
        
        # Initialize ALL handlers with shared services
        try:
            self.handlers = {
                '/login': TsimLoginHandler(self.config, self.session_manager, self.logger_service),
                '/logout': TsimLogoutHandler(self.session_manager, self.logger_service),
                '/main': TsimMainHandler(self.config, self.session_manager, self.logger_service,
                                        self.progress_tracker, self.hybrid_executor),
                '/pdf': TsimPDFHandler(self.config, self.session_manager, self.logger_service),
                '/progress': TsimProgressHandler(self.config, self.session_manager, self.logger_service, 
                                                self.progress_tracker),
                '/progress-stream': TsimProgressStreamHandler(self.config, self.session_manager, self.logger_service,
                                                             self.progress_tracker),
                '/services-config': TsimServicesConfigHandler(self.config, self.logger_service),
                '/test-config': TsimTestConfigHandler(self.config, self.session_manager, self.logger_service),
                '/cleanup': TsimCleanupHandler(self.config, self.session_manager, self.logger_service),
            }
            
            self.logger.info(f"Initialized {len(self.handlers)} request handlers")
        except Exception as e:
            self.logger.error(f"Failed to initialize handlers: {e}")
            raise
        
        # Log successful initialization
        self.logger.info("WSGI Application initialized successfully")
        self.logger.info(f"Available endpoints: {list(self.handlers.keys())}")
    
    def __call__(self, environ, start_response):
        """WSGI application callable
        
        This is called for each HTTP request
        """
        # Debug: Log what we receive
        path_info = environ.get('PATH_INFO', '')
        script_name = environ.get('SCRIPT_NAME', '')
        request_uri = environ.get('REQUEST_URI', '')
        
        # Determine the actual path
        # When using WSGIScriptAliasMatch, we may need to reconstruct the path
        if path_info:
            path = path_info
        elif script_name:
            path = script_name
        elif request_uri:
            # Extract path from REQUEST_URI
            path = request_uri.split('?')[0]
        else:
            path = '/'
            
        method = environ.get('REQUEST_METHOD', 'GET')
        
        # Log request with debug info (use INFO level to ensure it shows)
        remote_addr = environ.get('REMOTE_ADDR', 'unknown')
        self.logger.info(f"{method} {path} from {remote_addr} (PATH_INFO='{path_info}', SCRIPT_NAME='{script_name}', REQUEST_URI='{request_uri}')")
        
        try:
            # Check for static file requests (should be handled by Apache, but just in case)
            if path.startswith('/css/') or path.startswith('/js/') or path.startswith('/images/'):
                return self._serve_static(environ, start_response, path)
            
            # Check for HTML page requests (serve from htdocs)
            if path.endswith('.html') or path == '/':
                return self._serve_html(environ, start_response, path)
            
            # Route to appropriate API handler
            if path in self.handlers:
                handler = self.handlers[path]
                return handler.handle(environ, start_response)
            else:
                # 404 Not Found
                self.logger.warning(f"404 - No handler for path: {path}")
                start_response('404 Not Found', [
                    ('Content-Type', 'application/json'),
                    ('Cache-Control', 'no-cache')
                ])
                error_response = json.dumps({
                    'error': 'Not Found',
                    'path': path,
                    'message': f'No handler registered for {path}'
                }).encode('utf-8')
                return [error_response]
                
        except Exception as e:
            # Log error with full traceback
            self.logger.error(f"WSGI Error handling {method} {path}: {str(e)}", 
                            exc_info=True)
            
            # Log to audit log if available
            try:
                self.logger_service.log_error(
                    f"WSGI Error: {str(e)}", 
                    traceback=traceback.format_exc()
                )
            except:
                pass
            
            # Return 500 error
            start_response('500 Internal Server Error', [
                ('Content-Type', 'application/json'),
                ('Cache-Control', 'no-cache')
            ])
            error_response = json.dumps({
                'error': 'Internal Server Error',
                'message': 'An unexpected error occurred processing your request'
            }).encode('utf-8')
            return [error_response]
    
    def _serve_static(self, environ, start_response, path):
        """Serve static files (fallback - should be handled by Apache)"""
        web_root = os.environ.get('TSIM_WEB_ROOT', '/opt/tsim/wsgi')
        file_path = os.path.join(web_root, 'htdocs', path.lstrip('/'))
        
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            start_response('404 Not Found', [('Content-Type', 'text/plain')])
            return [b'File not found']
        
        # Determine content type
        if path.endswith('.css'):
            content_type = 'text/css'
        elif path.endswith('.js'):
            content_type = 'application/javascript'
        elif path.endswith('.png'):
            content_type = 'image/png'
        elif path.endswith('.jpg') or path.endswith('.jpeg'):
            content_type = 'image/jpeg'
        elif path.endswith('.gif'):
            content_type = 'image/gif'
        elif path.endswith('.svg'):
            content_type = 'image/svg+xml'
        else:
            content_type = 'application/octet-stream'
        
        # Read and serve file
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            start_response('200 OK', [
                ('Content-Type', content_type),
                ('Content-Length', str(len(content))),
                ('Cache-Control', 'public, max-age=3600')
            ])
            return [content]
        except Exception as e:
            self.logger.error(f"Error serving static file {path}: {e}")
            start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
            return [b'Error reading file']
    
    def _serve_html(self, environ, start_response, path):
        """Serve HTML pages"""
        if path == '/':
            path = '/index.html'
        
        web_root = os.environ.get('TSIM_WEB_ROOT', '/opt/tsim/wsgi')
        file_path = os.path.join(web_root, 'htdocs', path.lstrip('/'))
        
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            # Try to serve 404.html if it exists
            not_found_path = os.path.join(web_root, 'htdocs', '404.html')
            if os.path.exists(not_found_path):
                file_path = not_found_path
                status = '404 Not Found'
            else:
                start_response('404 Not Found', [('Content-Type', 'text/plain')])
                return [b'Page not found']
        else:
            status = '200 OK'
        
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            start_response(status, [
                ('Content-Type', 'text/html; charset=utf-8'),
                ('Content-Length', str(len(content)))
            ])
            return [content]
        except Exception as e:
            self.logger.error(f"Error serving HTML page {path}: {e}")
            start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
            return [b'Error reading page']

# Expose a module-level WSGI callable for local testing tools
# Example: python3 -m wsgiref.simple_server tsim_app:application 8000
application = TsimWSGIApp()
