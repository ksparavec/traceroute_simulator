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
    
    def __init__(self, config_service, session_manager, logger_service, progress_tracker=None, queue_service=None):
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
        # Optional queue service for live queue position
        if queue_service is not None:
            self.queue_service = queue_service
        else:
            try:
                from services.tsim_queue_service import TsimQueueService
                self.queue_service = TsimQueueService(config_service)
            except Exception:
                self.queue_service = None
    
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
                            expected_steps = progress_data.get('expected_steps') or len(current_phases) or 1
                            percent = int(progress_data.get('overall_progress', 0))
                            
                            # Prefer explicit flags for completion/success if present
                            is_complete = bool(progress_data.get('complete', False))
                            has_error = (progress_data.get('success') is False)
                            
                            # Fallback to phases to infer state
                            if not is_complete or not has_error:
                                for phase in current_phases:
                                    p = phase.get('phase')
                                    if p in ('COMPLETE', 'FAILED'):
                                        is_complete = True
                                    if p in ('ERROR', 'FAILED'):
                                        has_error = True
                        except json.JSONDecodeError:
                            self.logger.error(f"Failed to parse progress.json for {run_id}")
                            continue
                    
                    # Always sync all_phases with current_phases to ensure we have the latest (including TOTAL)
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
                    elif is_complete and len(current_phases) == len(all_phases):
                        # When complete, ensure the last phase (likely TOTAL) is properly included
                        # This handles the case where TOTAL phase is added in the same write as complete=true
                        if current_phases and all_phases:
                            last_current = current_phases[-1]
                            last_all = all_phases[-1] if all_phases else {}
                            # If the last phase content differs, update it
                            if (last_current.get('phase') != last_all.get('phase') or 
                                last_current.get('message') != last_all.get('details')):
                                
                                phase_name = last_current.get('phase', 'UNKNOWN')
                                if phase_name.startswith('MULTI_REACHABILITY_'):
                                    phase_name = phase_name.replace('MULTI_REACHABILITY_', '')
                                elif phase_name.startswith('REACHABILITY_'):
                                    phase_name = phase_name.replace('REACHABILITY_', '')
                                
                                all_phases[-1] = {
                                    'phase': phase_name,
                                    'details': last_current.get('message', last_current.get('details', '')),
                                    'duration': last_current.get('duration', 0)
                                }
                            
                            # Send SSE event for this phase update (matching CGI format)
                            # Live queue position if waiting
                            queue_position = None
                            if self.queue_service and not is_complete and phase_name in ('QUEUED', 'WAITING_FOR_ENVIRONMENT'):
                                try:
                                    queue_position = self.queue_service.get_position(run_id)
                                except Exception:
                                    queue_position = None

                            data = {
                                'phase': phase_name,
                                'details': phase.get('message', phase.get('details', '')),
                                'duration': phase.get('duration', 0),
                                'all_phases': all_phases,
                                'complete': is_complete,
                                'expected_steps': expected_steps,
                                'percent': percent,
                                'queue_position': queue_position,
                                'success': progress_data.get('success'),
                                'error': progress_data.get('error'),
                                'redirect_url': f'/pdf_viewer_final.html?id={run_id}' if (is_complete and not has_error) else None
                            }
                            
                            # Use CGI format: "data: json\n\n"
                            event = f"data: {json.dumps(data)}\n\n"
                            yield event.encode('utf-8')
                        
                        # Check if test is complete
                        if is_complete:
                            self.logger.info(f"Progress stream completed for run_id {run_id}")
                            break
                    elif is_complete:
                        # Run is complete but no new phases (e.g., race during cancellation) -> emit final state once
                        last = current_phases[-1] if current_phases else {}
                        phase_name = last.get('phase', 'UNKNOWN')
                        if phase_name.startswith('MULTI_REACHABILITY_'):
                            phase_name = phase_name.replace('MULTI_REACHABILITY_', '')
                        elif phase_name.startswith('REACHABILITY_'):
                            phase_name = phase_name.replace('REACHABILITY_', '')
                        data = {
                            'phase': phase_name,
                            'details': last.get('message', last.get('details', '')),
                            'duration': last.get('duration', 0),
                            'all_phases': all_phases,
                            'complete': True,
                            'expected_steps': expected_steps,
                            'percent': percent,
                            'queue_position': None,
                            'success': progress_data.get('success'),
                            'error': progress_data.get('error'),
                            'redirect_url': f'/pdf_viewer_final.html?id={run_id}' if not has_error else None
                        }
                        event = f"data: {json.dumps(data)}\n\n"
                        yield event.encode('utf-8')
                        self.logger.info(f"Final completion event sent for run_id {run_id}")
                        break
                    else:
                        # Emit a lightweight snapshot periodically to refresh UI (e.g., queue position cleared after cancel)
                        if retry_count % 2 == 0:  # every ~1s (loop is 0.5s)
                            last = current_phases[-1] if current_phases else {}
                            phase_name = last.get('phase', 'UNKNOWN')
                            if phase_name.startswith('MULTI_REACHABILITY_'):
                                phase_name = phase_name.replace('MULTI_REACHABILITY_', '')
                            elif phase_name.startswith('REACHABILITY_'):
                                phase_name = phase_name.replace('REACHABILITY_', '')
                            snapshot = {
                                'phase': phase_name,
                                'details': last.get('message', last.get('details', '')),
                                'duration': last.get('duration', 0),
                                'all_phases': all_phases,
                                'complete': is_complete,
                                'expected_steps': expected_steps,
                                'percent': percent,
                                'queue_position': None if is_complete else None,
                                'success': progress_data.get('success'),
                                'error': progress_data.get('error'),
                                'redirect_url': None
                            }
                            event = f"data: {json.dumps(snapshot)}\n\n"
                            yield event.encode('utf-8')
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
