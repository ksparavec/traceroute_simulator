#!/usr/bin/env -S python3 -B -u
"""
TSIM PDF Handler
Handles PDF retrieval requests
"""

import os
import logging
import hmac
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from .tsim_base_handler import TsimBaseHandler
from services.tsim_validator_service import TsimValidatorService


class TsimPDFHandler(TsimBaseHandler):
    """Handler for PDF retrieval requests"""
    
    def __init__(self, config_service, session_manager, logger_service):
        """Initialize PDF handler
        
        Args:
            config_service: TsimConfigService instance
            session_manager: TsimSessionManager instance
            logger_service: TsimLoggerService instance
        """
        super().__init__(session_manager, logger_service)
        self.config = config_service
        self.run_dir = Path('/dev/shm/tsim/runs')  # Serve PDFs directly from run directory
        self.validator = TsimValidatorService()
        self.logger = logging.getLogger('tsim.handler.pdf')
    
    def handle(self, environ: Dict[str, Any], start_response) -> List[bytes]:
        """Handle PDF retrieval request
        
        Args:
            environ: WSGI environment
            start_response: WSGI start_response callable
            
        Returns:
            Response body
        """
        # Get parameters
        params = self.parse_query_params(environ)
        # Support both 'id' and 'run_id' for backwards compatibility
        run_id = params.get('id', params.get('run_id', '')).strip()
        token = params.get('token', '').strip()
        
        # Check authentication - either session or valid token
        session = self.validate_session(environ)
        
        if not session and not token:
            return self.error_response(start_response, 'Authentication required', '401 Unauthorized')
        
        # If token provided, validate it
        if token and run_id:
            secret_key = self.config.get('secret_key', 'default-secret-key')
            expected_token = hmac.new(
                key=secret_key.encode(),
                msg=run_id.encode(),
                digestmod=hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(token, expected_token):
                self.logger.warning(f"Invalid token for run_id {run_id}")
                return self.error_response(start_response, 'Invalid or expired token', '401 Unauthorized')
            
            # Token is valid - allow access
            self.logger.info(f"Token-based access granted for run_id {run_id}")
        
        if not run_id:
            return self.error_response(start_response, 'Missing run_id parameter')
        
        # Validate run_id format (UUID)
        if not self.validator.validate_uuid(run_id):
            return self.error_response(start_response, 'Invalid run_id format')
        
        # PDF location is deterministic: always in run directory
        pdf_file = self.run_dir / run_id / f"{run_id}_report.pdf"
        
        # Check if PDF exists
        if not pdf_file.exists():
            self.logger.error(f"PDF file not found at {pdf_file}")
            return self.error_response(start_response, 'PDF not found', '404 Not Found')
        
        # Security check - ensure file is within run_dir
        try:
            pdf_file = pdf_file.resolve()
            run_dir_resolved = self.run_dir.resolve()
            if not str(pdf_file).startswith(str(run_dir_resolved)):
                self.logger.error(f"Security violation: PDF path outside allowed directory: {pdf_file}")
                return self.error_response(start_response, 'Access denied', '403 Forbidden')
        except Exception as e:
            self.logger.error(f"Path resolution error: {e}")
            return self.error_response(start_response, 'Invalid file path', '400 Bad Request')
        
        # Check file size
        file_size = pdf_file.stat().st_size
        max_pdf_size = self.config.get('max_pdf_size', 50 * 1024 * 1024)  # 50MB default
        
        if file_size > max_pdf_size:
            self.logger.warning(f"PDF file too large: {file_size} bytes")
            return self.error_response(start_response, 'PDF file too large', '413 Payload Too Large')
        
        # Serve the PDF file
        try:
            with open(pdf_file, 'rb') as f:
                pdf_content = f.read()
            
            # Log access
            self.logger.info(f"Serving PDF for run_id {run_id} to user {session.get('username')}")
            self.logger_service.log_audit(
                'pdf_access',
                session.get('username'),
                self.get_client_ip(environ),
                True,
                {'run_id': run_id, 'file_size': file_size}
            )
            
            # Send PDF response
            response_headers = [
                ('Content-Type', 'application/pdf'),
                ('Content-Length', str(len(pdf_content))),
                ('Content-Disposition', f'inline; filename="{run_id}_report.pdf"'),
                ('Cache-Control', 'private, max-age=3600'),
                ('X-Content-Type-Options', 'nosniff'),
            ]
            
            start_response('200 OK', response_headers)
            return [pdf_content]
            
        except Exception as e:
            self.logger.error(f"Error reading PDF file: {e}")
            return self.error_response(
                start_response,
                'Error reading PDF file',
                '500 Internal Server Error'
            )