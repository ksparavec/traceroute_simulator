#!/usr/bin/env -S python3 -B -u
"""
TSIM Progress Handler
Handles progress polling requests
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from .tsim_base_handler import TsimBaseHandler


class TsimProgressHandler(TsimBaseHandler):
    """Handler for progress polling requests"""
    
    def __init__(self, config_service, session_manager, logger_service):
        """Initialize progress handler
        
        Args:
            config_service: TsimConfigService instance
            session_manager: TsimSessionManager instance
            logger_service: TsimLoggerService instance
        """
        super().__init__(session_manager, logger_service)
        self.config = config_service
        self.logger = logging.getLogger('tsim.handler.progress')
    
    def handle(self, environ: Dict[str, Any], start_response) -> List[bytes]:
        """Handle progress request
        
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
        
        # Get run_id from query parameters
        params = self.parse_query_params(environ)
        run_id = params.get('run_id', '').strip()
        
        if not run_id:
            return self.error_response(start_response, 'Missing run_id parameter')
        
        # Get progress file path
        # Get progress from /dev/shm/tsim/runs/<run_id>/progress.json
        progress_dir = Path(self.config.get('run_dir', '/dev/shm/tsim/runs'))
        run_dir = progress_dir / run_id
        progress_file = run_dir / "progress.json"
        
        if not progress_file.exists():
            # No progress file yet - test may be starting
            return self.json_response(start_response, {
                'success': True,
                'run_id': run_id,
                'overall_progress': 0,
                'phases': {},
                'complete': False,
                'message': 'Test initializing...'
            })
        
        try:
            # Read progress file (contains multiple JSON objects, one per line)
            phases = []
            latest_phase = None
            is_complete = False
            has_error = False
            
            with open(progress_file, 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            phase_data = json.loads(line)
                            phases.append(phase_data)
                            latest_phase = phase_data
                            
                            # Check for completion or error
                            if phase_data.get('phase') == 'COMPLETE':
                                is_complete = True
                            elif phase_data.get('phase') == 'ERROR':
                                has_error = True
                        except json.JSONDecodeError:
                            continue
            
            # Calculate overall progress based on phases
            phase_progress = {
                'PHASE1_START': 10,
                'PHASE1_COMPLETE': 20,
                'PHASE2_START': 30,
                'PHASE3_START': 40,
                'PHASE4_START': 50,
                'PHASE4_COMPLETE': 70,
                'PHASE5_START': 80,
                'PHASE5_COMPLETE': 85,
                'PDF_GENERATION': 90,
                'COMPLETE': 100,
                'ERROR': -1
            }
            
            # Get the latest phase progress
            overall_progress = 0
            current_message = "Test initializing..."
            
            if latest_phase:
                phase_name = latest_phase.get('phase', '')
                overall_progress = phase_progress.get(phase_name, 0)
                current_message = latest_phase.get('message', '')
            
            # Build response
            progress_data = {
                'success': True,
                'run_id': run_id,
                'overall_progress': overall_progress,
                'phases': phases,
                'complete': is_complete,
                'error': has_error,
                'message': current_message
            }
            
            # Add PDF URL if complete
            if is_complete and not has_error:
                progress_data['pdf_url'] = f'/pdf?run_id={run_id}'
                progress_data['redirect'] = f'/pdf_viewer_final.html?id={run_id}'
            
            return self.json_response(start_response, progress_data)
            
        except Exception as e:
            self.logger.error(f"Error reading progress for {run_id}: {e}")
            return self.error_response(
                start_response,
                'Error reading progress',
                '500 Internal Server Error'
            )