#!/usr/bin/env -S python3 -B -u
"""
TSIM Cleanup Handler
Handles cleanup of old test data and sessions
"""

import time
import logging
from typing import Dict, Any, List
from .tsim_base_handler import TsimBaseHandler
from services.tsim_executor import TsimExecutor
from services.tsim_pdf_generator import TsimPDFGenerator


class TsimCleanupHandler(TsimBaseHandler):
    """Handler for cleanup requests"""
    
    def __init__(self, config_service, session_manager, logger_service):
        """Initialize cleanup handler
        
        Args:
            config_service: TsimConfigService instance
            session_manager: TsimSessionManager instance
            logger_service: TsimLoggerService instance
        """
        super().__init__(session_manager, logger_service)
        self.config = config_service
        self.executor = TsimExecutor(config_service)
        self.pdf_generator = TsimPDFGenerator(config_service)
        self.logger = logging.getLogger('tsim.handler.cleanup')
    
    def handle(self, environ: Dict[str, Any], start_response) -> List[bytes]:
        """Handle cleanup request
        
        Args:
            environ: WSGI environment
            start_response: WSGI start_response callable
            
        Returns:
            Response body
        """
        # Check session and admin role
        session = self.validate_session(environ)
        if not session:
            return self.error_response(start_response, 'Authentication required', '401 Unauthorized')
        
        # Only admins can perform cleanup
        if session.get('role') != 'admin':
            self.logger.warning(f"Cleanup access denied for user {session.get('username')}")
            return self.error_response(start_response, 'Admin access required', '403 Forbidden')
        
        method = environ.get('REQUEST_METHOD', 'GET')
        
        if method == 'POST':
            return self._handle_post(environ, start_response, session)
        elif method == 'GET':
            return self._handle_get(environ, start_response, session)
        else:
            return self.error_response(start_response, 'Method not allowed', '405 Method Not Allowed')
    
    def _handle_get(self, environ: Dict[str, Any], start_response,
                    session: Dict[str, Any]) -> List[bytes]:
        """Handle GET request - return cleanup status
        
        Args:
            environ: WSGI environment
            start_response: WSGI start_response callable
            session: Session data
            
        Returns:
            Response body
        """
        # Get cleanup configuration
        max_age = self.config.get('cleanup_age', 86400)  # 24 hours default
        
        # Calculate sizes and counts (simplified for now)
        from pathlib import Path
        
        stats = {
            'sessions': 0,
            'test_files': 0,
            'pdf_files': 0,
            'total_size': 0
        }
        
        # Count sessions
        session_dir = self.config.session_dir
        if session_dir.exists():
            stats['sessions'] = len(list(session_dir.glob('*.json')))
        
        # Count test files
        data_dir = self.config.data_dir
        for subdir in ['traces', 'results', 'progress']:
            dir_path = data_dir / subdir
            if dir_path.exists():
                for file_path in dir_path.iterdir():
                    stats['test_files'] += 1
                    stats['total_size'] += file_path.stat().st_size
        
        # Count PDF files
        pdf_dir = data_dir / 'pdfs'
        if pdf_dir.exists():
            pdf_files = list(pdf_dir.glob('*.pdf'))
            stats['pdf_files'] = len(pdf_files)
            for pdf in pdf_files:
                stats['total_size'] += pdf.stat().st_size
        
        # Format size
        size_mb = stats['total_size'] / (1024 * 1024)
        
        return self.json_response(start_response, {
            'success': True,
            'stats': {
                'sessions': stats['sessions'],
                'test_files': stats['test_files'],
                'pdf_files': stats['pdf_files'],
                'total_size_mb': round(size_mb, 2)
            },
            'config': {
                'max_age_hours': max_age / 3600,
                'auto_cleanup': False  # Could be made configurable
            }
        })
    
    def _handle_post(self, environ: Dict[str, Any], start_response,
                    session: Dict[str, Any]) -> List[bytes]:
        """Handle POST request - perform cleanup
        
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
            data = {}
        
        # Get cleanup parameters
        max_age = data.get('max_age', self.config.get('cleanup_age', 86400))
        clean_sessions = data.get('clean_sessions', True)
        clean_tests = data.get('clean_tests', True)
        clean_pdfs = data.get('clean_pdfs', True)
        
        # Convert max_age to integer if string
        if isinstance(max_age, str):
            try:
                max_age = int(max_age)
            except ValueError:
                max_age = 86400
        
        cleanup_stats = {
            'sessions_removed': 0,
            'test_files_removed': 0,
            'pdf_files_removed': 0,
            'total_space_freed': 0,
            'errors': []
        }
        
        start_time = time.time()
        
        try:
            # Clean up sessions
            if clean_sessions:
                try:
                    sessions_cleaned = self.session_manager.cleanup_expired_sessions()
                    cleanup_stats['sessions_removed'] = sessions_cleaned
                    self.logger.info(f"Cleaned {sessions_cleaned} expired sessions")
                except Exception as e:
                    cleanup_stats['errors'].append(f"Session cleanup error: {str(e)}")
                    self.logger.error(f"Session cleanup failed: {e}")
            
            # Clean up test data
            if clean_tests:
                try:
                    files_cleaned = self.executor.cleanup_old_data(max_age)
                    cleanup_stats['test_files_removed'] = files_cleaned
                    self.logger.info(f"Cleaned {files_cleaned} old test files")
                except Exception as e:
                    cleanup_stats['errors'].append(f"Test data cleanup error: {str(e)}")
                    self.logger.error(f"Test data cleanup failed: {e}")
            
            # Clean up PDFs
            if clean_pdfs:
                try:
                    pdfs_cleaned = self.pdf_generator.cleanup_old_pdfs(max_age)
                    cleanup_stats['pdf_files_removed'] = pdfs_cleaned
                    self.logger.info(f"Cleaned {pdfs_cleaned} old PDF files")
                except Exception as e:
                    cleanup_stats['errors'].append(f"PDF cleanup error: {str(e)}")
                    self.logger.error(f"PDF cleanup failed: {e}")
            
            # Calculate space freed (simplified)
            cleanup_stats['total_space_freed'] = (
                cleanup_stats['sessions_removed'] * 1024 +  # Estimate 1KB per session
                cleanup_stats['test_files_removed'] * 10240 +  # Estimate 10KB per test file
                cleanup_stats['pdf_files_removed'] * 512000  # Estimate 500KB per PDF
            )
            
            elapsed_time = time.time() - start_time
            
            # Log audit event
            self.logger_service.log_audit(
                'cleanup_performed',
                session.get('username'),
                self.get_client_ip(environ),
                True,
                {
                    'max_age': max_age,
                    'stats': cleanup_stats,
                    'elapsed_time': elapsed_time
                }
            )
            
            self.logger.info(
                f"Cleanup completed by {session.get('username')}: "
                f"{cleanup_stats['sessions_removed']} sessions, "
                f"{cleanup_stats['test_files_removed']} test files, "
                f"{cleanup_stats['pdf_files_removed']} PDFs removed"
            )
            
            return self.json_response(start_response, {
                'success': True,
                'message': 'Cleanup completed successfully',
                'stats': cleanup_stats,
                'elapsed_time': round(elapsed_time, 2)
            })
            
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}", exc_info=True)
            
            # Log audit event
            self.logger_service.log_audit(
                'cleanup_failed',
                session.get('username'),
                self.get_client_ip(environ),
                False,
                {'error': str(e)}
            )
            
            return self.error_response(
                start_response,
                f'Cleanup failed: {str(e)}',
                '500 Internal Server Error'
            )