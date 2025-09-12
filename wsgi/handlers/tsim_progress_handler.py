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
    
    def __init__(self, config_service, session_manager, logger_service, progress_tracker=None, queue_service=None):
        """Initialize progress handler
        
        Args:
            config_service: TsimConfigService instance
            session_manager: TsimSessionManager instance
            logger_service: TsimLoggerService instance
            progress_tracker: Optional shared TsimProgressTracker instance
        """
        super().__init__(session_manager, logger_service)
        self.config = config_service
        self.logger = logging.getLogger('tsim.handler.progress')
        
        # Use shared progress tracker if provided
        if progress_tracker:
            self.progress_tracker = progress_tracker
        else:
            from services.tsim_progress_tracker import TsimProgressTracker
            self.progress_tracker = TsimProgressTracker(config_service)
        # Optional queue service for live queue position
        if queue_service is not None:
            self.queue_service = queue_service
        else:
            try:
                from services.tsim_queue_service import TsimQueueService
                self.queue_service = TsimQueueService(config_service)
            except Exception:
                self.queue_service = None
    
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
        
        # Get progress from progress tracker (in-memory first, then files)
        progress = self.progress_tracker.get_progress(run_id)
        
        if not progress:
            # No progress yet - test may be starting or invalid run_id
            # Return CGI-compatible format
            return self.json_response(start_response, {
                'run_id': run_id,
                'phase': 'UNKNOWN',
                'details': 'Test initializing...',
                'all_phases': [],
                'complete': False
            })
        
        # Get the latest phase
        phases = progress.get('phases', [])
        latest_phase = phases[-1] if phases else {'phase': 'UNKNOWN', 'message': 'Test initializing...'}
        
        # Format phases as all_phases with details field
        all_phases = []
        for phase_entry in phases:
            phase_name = phase_entry.get('phase', 'UNKNOWN')
            
            # Strip prefixes like CGI does
            if phase_name.startswith('MULTI_REACHABILITY_'):
                phase_name = phase_name.replace('MULTI_REACHABILITY_', '')
            elif phase_name.startswith('REACHABILITY_'):
                phase_name = phase_name.replace('REACHABILITY_', '')
            
            all_phases.append({
                'phase': phase_name,
                'details': phase_entry.get('message', '')
            })
        
        # Get latest phase name with prefix stripped
        latest_phase_name = latest_phase.get('phase', 'UNKNOWN')
        if latest_phase_name.startswith('MULTI_REACHABILITY_'):
            latest_phase_name = latest_phase_name.replace('MULTI_REACHABILITY_', '')
        elif latest_phase_name.startswith('REACHABILITY_'):
            latest_phase_name = latest_phase_name.replace('REACHABILITY_', '')
        
        # Build response matching CGI format exactly
        # Include percent and expected steps for accurate progress meters
        percent = int(progress.get('overall_progress', 0))
        expected_steps = int(progress.get('expected_steps', len(all_phases) or 1))
        # Live queue position for queued/waiting
        queue_position = None
        if self.queue_service and not progress.get('complete') and latest_phase_name in ('QUEUED', 'WAITING_FOR_ENVIRONMENT'):
            try:
                queue_position = self.queue_service.get_position(run_id)
            except Exception:
                queue_position = None

        response = {
            'run_id': run_id,
            'phase': latest_phase_name,
            'details': latest_phase.get('message', ''),
            'all_phases': all_phases,  # This is what the frontend expects
            'complete': progress.get('complete', False),
            'percent': percent,
            'expected_steps': expected_steps,
            'queue_position': queue_position,
            'success': progress.get('success', None),
            'error': progress.get('error', None)
        }
        
        # Add redirect URL if complete
        if progress.get('complete'):
            session_id = session.get('session_id', '')
            if session_id:
                response['redirect_url'] = f'/pdf_viewer_final.html?id={run_id}&session={session_id}'
            else:
                response['redirect_url'] = f'/pdf_viewer_final.html?id={run_id}'
        
        return self.json_response(start_response, response)
