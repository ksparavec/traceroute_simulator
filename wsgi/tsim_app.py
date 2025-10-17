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
from handlers.tsim_cleanup_handler import TsimCleanupHandler
from handlers.tsim_queue_admin_handler import TsimQueueAdminHandler
from handlers.tsim_job_details_handler import TsimJobDetailsHandler
from handlers.tsim_admin_queue_stream_handler import TsimAdminQueueStreamHandler
from handlers.tsim_admin_host_remove_handler import TsimAdminHostRemoveHandler

# All services are already preloaded in app.wsgi
from services.tsim_session_manager import TsimSessionManager
from services.tsim_config_service import TsimConfigService
from services.tsim_logger_service import TsimLoggerService
from services.tsim_progress_tracker import TsimProgressTracker
from services.tsim_hybrid_executor import TsimHybridExecutor
from services.tsim_executor import TsimExecutor
from services.tsim_lock_manager_service import TsimLockManagerService
from services.tsim_queue_service import TsimQueueService
from services.tsim_scheduler_service import TsimSchedulerService
from services.tsim_reconciler_service import TsimReconcilerService


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
            # Global lock manager, executor, queue, and scheduler
            self.lock_manager = TsimLockManagerService(self.config)
            self.executor = TsimExecutor(self.config, self.lock_manager, None, self.progress_tracker)
            self.executor.set_hybrid_executor(self.hybrid_executor)
            self.queue_service = TsimQueueService(self.config)
            self.scheduler = TsimSchedulerService(
                self.config, self.queue_service, self.progress_tracker, self.executor, self.lock_manager
            )
            self.scheduler.start()
            # Start reconciler to finalize cancelled/aborted runs
            self.reconciler = TsimReconcilerService(self.config, self.queue_service, self.progress_tracker, interval=1.0)
            self.reconciler.start()
            
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
                                        self.progress_tracker, self.hybrid_executor, self.queue_service,
                                        self.lock_manager),
                '/pdf': TsimPDFHandler(self.config, self.session_manager, self.logger_service),
                '/progress': TsimProgressHandler(self.config, self.session_manager, self.logger_service,
                                                self.progress_tracker, self.queue_service),
                '/progress-stream': TsimProgressStreamHandler(self.config, self.session_manager, self.logger_service,
                                                             self.progress_tracker, self.queue_service),
                '/services-config': TsimServicesConfigHandler(self.config, self.logger_service),
                '/cleanup': TsimCleanupHandler(self.config, self.session_manager, self.logger_service),
                '/admin-queue': TsimQueueAdminHandler(self.config, self.session_manager, self.logger_service,
                                                     self.queue_service, self.lock_manager),
                '/admin-job': TsimJobDetailsHandler(self.config, self.session_manager, self.logger_service),
                '/admin-queue-stream': TsimAdminQueueStreamHandler(self.config, self.session_manager, self.logger_service,
                                                                   self.queue_service, self.lock_manager, self.scheduler),
                '/admin-host-remove': TsimAdminHostRemoveHandler(self.config, self.session_manager, self.logger_service,
                                                                 self.scheduler),
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

            # Check if facts validation failed - return user-friendly message
            if os.environ.get('TSIM_FACTS_INVALID') == '1':
                start_response('503 Service Unavailable', [
                    ('Content-Type', 'application/json'),
                    ('Cache-Control', 'no-cache')
                ])
                error_response = json.dumps({
                    'error': 'Service Unavailable',
                    'message': 'Network analysis is currently unavailable. Please contact your system administrator.'
                }).encode('utf-8')
                return [error_response]

            # Return 500 error for other exceptions
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
        htdocs_root = os.environ.get('TSIM_HTDOCS', '/opt/tsim/htdocs')
        file_path = os.path.join(htdocs_root, path.lstrip('/'))
        
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
            # Check if facts validation failed
            if os.environ.get('TSIM_FACTS_INVALID') == '1':
                start_response('503 Service Unavailable', [('Content-Type', 'text/plain')])
                return [b'Network analysis is currently unavailable. Please contact your system administrator.']
            start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
            return [b'Error reading file']
    
    def _serve_html(self, environ, start_response, path):
        """Serve HTML pages with authentication check"""
        # Handle root/index - redirect based on auth status
        if path in ['/', '/index.html']:
            # Check if user is authenticated
            cookie_header = environ.get('HTTP_COOKIE', '')
            session_id = None
            if cookie_header:
                for cookie in cookie_header.split(';'):
                    cookie = cookie.strip()
                    if cookie.startswith('session_id='):
                        session_id = cookie[11:]
                        break
            
            session = self.session_manager.get_session(session_id) if session_id else None
            if session:
                # Authenticated - redirect to main app
                start_response('302 Found', [
                    ('Location', '/form.html'),
                    ('Content-Type', 'text/plain')
                ])
                return [b'Redirecting to application...']
            else:
                # Not authenticated - redirect to login
                start_response('302 Found', [
                    ('Location', '/login.html'),
                    ('Content-Type', 'text/plain')
                ])
                return [b'Redirecting to login...']
        
        # Allow only login.html without authentication
        public_pages = ['/login.html']
        
        if path not in public_pages:
            # Check for valid session
            cookie_header = environ.get('HTTP_COOKIE', '')
            session_id = None
            if cookie_header:
                for cookie in cookie_header.split(';'):
                    cookie = cookie.strip()
                    if cookie.startswith('session_id='):
                        session_id = cookie[11:]  # Remove 'session_id=' prefix
                        break
            
            # Validate session
            session = self.session_manager.get_session(session_id) if session_id else None
            if not session:
                # Redirect to login page
                location = '/login.html?redirect=' + path
                start_response('302 Found', [
                    ('Location', location),
                    ('Content-Type', 'text/plain')
                ])
                return [b'Authentication required. Redirecting to login...']
        
        if path == '/':
            path = '/index.html'
        
        htdocs_root = os.environ.get('TSIM_HTDOCS', '/opt/tsim/htdocs')
        file_path = os.path.join(htdocs_root, path.lstrip('/'))
        
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            # Try to serve 404.html if it exists
            not_found_path = os.path.join(htdocs_root, '404.html')
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
            
            # Inject mode configuration into form.html
            if path == '/form.html' or file_path.endswith('form.html'):
                mode = self.config.get('traceroute_simulator_mode', 'prod')
                # DEBUG: Log what we're reading
                self.logger.error(f"DEBUG: WSGI app reading mode as '{mode}' from config")
                # Inject a script tag with the mode BEFORE form.js loads
                original_tag = b'<script src="/js/form.js"></script>'
                mode_script = f'<script>window.TSIM_MODE = "{mode}";</script>\n    <script src="/js/form.js"></script>'.encode('utf-8')
                content = content.replace(original_tag, mode_script)
                self.logger.debug(f"Injected mode '{mode}' into form.html")
            
            start_response(status, [
                ('Content-Type', 'text/html; charset=utf-8'),
                ('Content-Length', str(len(content)))
            ])
            return [content]
        except Exception as e:
            self.logger.error(f"Error serving HTML page {path}: {e}")
            # Check if facts validation failed
            if os.environ.get('TSIM_FACTS_INVALID') == '1':
                start_response('503 Service Unavailable', [('Content-Type', 'text/plain')])
                return [b'Network analysis is currently unavailable. Please contact your system administrator.']
            start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
            return [b'Error reading page']

# Expose a module-level WSGI callable for local testing tools
# Example: python3 -m wsgiref.simple_server tsim_app:application 8000
# NOTE: Only create instance when running directly, not when imported by app.wsgi
if __name__ == '__main__':
    application = TsimWSGIApp()
