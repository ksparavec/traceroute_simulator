#!/usr/bin/env -S python3 -B -u
"""
TSIM Progress Stream Handler
Handles Server-Sent Events (SSE) for real-time progress updates
"""

import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Generator
from .tsim_base_handler import TsimBaseHandler


class TsimProgressStreamHandler(TsimBaseHandler):
    """Handler for SSE progress stream requests"""
    
    def __init__(self, config_service, session_manager, logger_service, progress_tracker=None):
        """Initialize progress stream handler
        
        Args:
            config_service: TsimConfigService instance
            session_manager: TsimSessionManager instance
            logger_service: TsimLoggerService instance
            progress_tracker: Optional shared TsimProgressTracker instance
        """
        super().__init__(session_manager, logger_service)
        self.config = config_service
        self.logger = logging.getLogger('tsim.handler.progress_stream')
        
        # Use shared progress tracker if provided
        if progress_tracker:
            self.progress_tracker = progress_tracker
        else:
            from services.tsim_progress_tracker import TsimProgressTracker
            self.progress_tracker = TsimProgressTracker(config_service)
    
    def handle(self, environ: Dict[str, Any], start_response) -> Generator[bytes, None, None]:
        """Handle SSE progress stream request
        
        Args:
            environ: WSGI environment
            start_response: WSGI start_response callable
            
        Returns:
            Generator yielding SSE events
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
        
        # Set up SSE response
        self.stream_response(start_response, 'text/event-stream')
        
        # Start streaming progress
        return self._stream_progress(run_id, session)
    
    def _stream_progress(self, run_id: str, session: Dict[str, Any]) -> Generator[bytes, None, None]:
        """Stream progress updates via SSE
        
        Args:
            run_id: Run identifier
            session: Session data
            
        Yields:
            SSE formatted progress events
        """
        progress_dir = Path(self.config.get('run_dir', '/dev/shm/tsim/runs'))
        run_dir = progress_dir / run_id
        progress_file = run_dir / "progress.json"
        
        all_phases = []  # Track all phases seen so far  
        last_phase_count = 0
        retry_count = 0
        max_retries = 600  # 5 minutes at 0.5 second intervals
        
        self.logger.info(f"Starting progress stream for run_id {run_id}")
        
        while retry_count < max_retries:
            try:
                # Check if progress file exists
                if progress_file.exists():
                    # Read the entire progress JSON file
                    current_phases = []
                    is_complete = False
                    has_error = False
                    
                    with open(progress_file, 'r') as f:
                        try:
                            progress_data = json.load(f)
                            # Extract phases from the JSON structure
                            current_phases = progress_data.get('phases', [])
                            
                            # Check for completion or error
                            for phase in current_phases:
                                if phase.get('phase') == 'COMPLETE':
                                    is_complete = True
                                elif phase.get('phase') == 'ERROR':
                                    has_error = True
                        except json.JSONDecodeError:
                            self.logger.error(f"Failed to parse progress.json for {run_id}")
                            continue
                    
                    # Check if we have new phases
                    if len(current_phases) > len(all_phases):
                        # Add new phases to our collection
                        for i in range(len(all_phases), len(current_phases)):
                            phase = current_phases[i]
                            phase_name = phase.get('phase', 'UNKNOWN')
                            
                            # Strip prefixes like CGI does
                            if phase_name.startswith('MULTI_REACHABILITY_'):
                                phase_name = phase_name.replace('MULTI_REACHABILITY_', '')
                            elif phase_name.startswith('REACHABILITY_'):
                                phase_name = phase_name.replace('REACHABILITY_', '')
                            
                            all_phases.append({
                                'phase': phase_name,
                                'details': phase.get('message', phase.get('details', '')),
                                'duration': phase.get('duration', 0)
                            })
                            
                            # Send SSE event for this phase update (matching CGI format)
                            data = {
                                'phase': phase_name,
                                'details': phase.get('message', phase.get('details', '')),
                                'duration': phase.get('duration', 0),
                                'all_phases': all_phases,
                                'complete': is_complete,
                                'redirect_url': f'/pdf_viewer_final.html?id={run_id}' if is_complete else None
                            }
                            
                            # Use CGI format: "data: json\n\n"
                            event = f"data: {json.dumps(data)}\n\n"
                            yield event.encode('utf-8')
                        
                        # Check if test is complete
                        if is_complete:
                            self.logger.info(f"Progress stream completed for run_id {run_id}")
                            break
                else:
                    # No progress file yet - send waiting event
                    if retry_count % 10 == 0:  # Every 5 seconds
                        data = {
                            'phase': 'WAITING',
                            'details': 'Waiting for test to start...',
                            'duration': 0,
                            'all_phases': all_phases,
                            'complete': False,
                            'redirect_url': None
                        }
                        event = f"data: {json.dumps(data)}\n\n"
                        yield event.encode('utf-8')
                
                # Send heartbeat to keep connection alive (matching CGI format)
                yield b": heartbeat\n\n"
                
                # Wait before next check
                time.sleep(0.5)
                retry_count += 1
                
            except Exception as e:
                self.logger.error(f"Error in progress stream for {run_id}: {e}")
                # Send error in CGI format
                data = {
                    'phase': 'ERROR',
                    'details': str(e),
                    'duration': 0,
                    'all_phases': all_phases,
                    'complete': False,
                    'redirect_url': None,
                    'error': str(e)
                }
                event = f"data: {json.dumps(data)}\n\n"
                yield event.encode('utf-8')
                break
        
        # Timeout reached
        if retry_count >= max_retries:
            data = {
                'phase': 'TIMEOUT',
                'details': 'Progress stream timeout',
                'duration': 0,
                'all_phases': all_phases,
                'complete': False,
                'redirect_url': None
            }
            event = f"data: {json.dumps(data)}\n\n"
            yield event.encode('utf-8')
            self.logger.warning(f"Progress stream timeout for run_id {run_id}")
    
    def _format_sse_event(self, event_type: str, data: Dict[str, Any]) -> bytes:
        """Format data as SSE event
        
        Args:
            event_type: Type of event
            data: Event data
            
        Returns:
            SSE formatted event as bytes
        """
        # Add event type to data so JavaScript can distinguish
        data['event_type'] = event_type
        
        # Format as SSE without custom event type (use default 'message')
        event = f"data: {json.dumps(data)}\n"
        event += f"id: {time.time()}\n"
        event += "\n"
        
        return event.encode('utf-8')