#!/usr/bin/env -S python3 -B -u
"""
TSIM Progress Tracker Service - IN-MEMORY VERSION
Fast in-memory progress tracking with thread-safe access
"""

import time
import json
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from collections import defaultdict


class TsimProgressTracker:
    """In-memory progress tracking with optional file persistence"""
    
    def __init__(self, config_service):
        """Initialize progress tracker
        
        Args:
            config_service: TsimConfigService instance
        """
        self.config = config_service
        self.logger = logging.getLogger('tsim.progress_tracker')
        
        # In-memory progress storage
        self.progress = {}
        self.lock = threading.Lock()
        
        # Track active runs per user to prevent parallel execution
        self.active_runs = {}  # username -> run_id
        
        # Optional file persistence for SSE
        self.run_dir = Path(config_service.get('run_dir', '/dev/shm/tsim/runs'))
        self.run_dir.mkdir(parents=True, exist_ok=True)
        
        # Phase definitions for progress calculation (using actual CGI phase names)
        self.expected_phases = [
            'START', 'parse_args', 
            'MULTI_REACHABILITY_PHASE1_start', 'MULTI_REACHABILITY_PHASE1_trace_load', 
            'MULTI_REACHABILITY_PHASE1_complete',
            'MULTI_REACHABILITY_PHASE2_start', 'MULTI_REACHABILITY_PHASE2_host_list',
            'MULTI_REACHABILITY_PHASE2_host_setup_start', 'MULTI_REACHABILITY_PHASE2_hosts_complete',
            'MULTI_REACHABILITY_PHASE2_service_check', 'MULTI_REACHABILITY_PHASE2_services_start',
            'MULTI_REACHABILITY_PHASE2_complete',
            'MULTI_REACHABILITY_PHASE3_start', 'MULTI_REACHABILITY_PHASE3_complete',
            'MULTI_REACHABILITY_PHASE4_start', 'MULTI_REACHABILITY_PHASE4_complete',
            'PDF_GENERATION', 'PDF_COMPLETE', 'COMPLETE'
        ]
        
        self.logger.info("In-memory progress tracker initialized")
    
    def create_run_directory(self, run_id: str) -> Path:
        """Create run directory and initialize progress
        
        Args:
            run_id: Run identifier
            
        Returns:
            Path to run directory
        """
        # Create directory structure
        run_path = self.run_dir / run_id
        run_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize in-memory progress
        with self.lock:
            self.progress[run_id] = {
                'run_id': run_id,
                'start_time': time.time(),
                'phases': [],
                'current_phase': 'START',
                'overall_progress': 0,
                'expected_steps': len(self.expected_phases),
                'complete': False,
                'success': None,
                'error': None,
                'pdf_file': None
            }
        
        # Write initial files for SSE compatibility
        self._write_timing_file(run_id, 'START', 'Test execution started')
        self._write_audit_file(run_id, 'START', 'Test execution started')
        
        self.logger.debug(f"Created run directory: {run_path}")
        return run_path
    
    def log_phase(self, run_id: str, phase: str, message: str = "", 
                  details: Optional[Dict[str, Any]] = None):
        """Log a phase update
        
        Args:
            run_id: Run identifier
            phase: Phase name
            message: Optional message
            details: Optional details dictionary
        """
        timestamp = time.time()
        
        # Update in-memory progress
        with self.lock:
            if run_id not in self.progress:
                self.logger.warning(f"Run {run_id} not found in progress tracker")
                return
            
            progress = self.progress[run_id]
            
            # Add phase entry
            phase_entry = {
                'phase': phase,
                'timestamp': timestamp,
                'message': message,
                'details': details or {}
            }
            progress['phases'].append(phase_entry)
            progress['current_phase'] = phase
            
            # Calculate overall progress
            if phase == 'COMPLETE':
                progress['overall_progress'] = 100
                progress['complete'] = True
                progress['success'] = True
            elif phase == 'ERROR' or phase == 'FAILED':
                progress['complete'] = True
                progress['success'] = False
                if message:
                    progress['error'] = message
            else:
                # Calculate based on steps completed vs expected steps
                completed = len(progress['phases'])
                expected = max(1, progress.get('expected_steps') or len(self.expected_phases))
                # Cap at 99% until completion
                progress['overall_progress'] = min(99, int(100 * completed / expected))
        
        # Write to files for SSE
        self._write_timing_file(run_id, phase, message)
        self._write_audit_file(run_id, phase, message, details)
        
        # Also write progress.json for easy reading
        self._write_progress_json(run_id)
    
    def get_progress(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get current progress for a run
        
        Args:
            run_id: Run identifier
            
        Returns:
            Progress data or None
        """
        with self.lock:
            if run_id in self.progress:
                # Return a copy to prevent external modification
                return dict(self.progress[run_id])
        
        # Fallback to file-based progress if not in memory
        return self._read_file_progress(run_id)

    def set_expected_steps(self, run_id: str, expected_steps: int):
        """Set the expected total number of steps for a run
        
        Args:
            run_id: Run identifier
            expected_steps: Total steps expected
        """
        with self.lock:
            if run_id in self.progress:
                self.progress[run_id]['expected_steps'] = max(1, int(expected_steps))
                # Recalculate progress with new expected value
                completed = len(self.progress[run_id]['phases'])
                expected = self.progress[run_id]['expected_steps']
                if not self.progress[run_id].get('complete'):
                    self.progress[run_id]['overall_progress'] = min(99, int(100 * completed / expected))
    
    def get_all_progress(self) -> Dict[str, Dict[str, Any]]:
        """Get progress for all active runs
        
        Returns:
            Dictionary of run_id -> progress data
        """
        with self.lock:
            return {k: dict(v) for k, v in self.progress.items()}
    
    def set_pdf_url(self, run_id: str, pdf_path: str):
        """Set the PDF URL for a run
        
        Args:
            run_id: Run identifier  
            pdf_path: Full path to the PDF file
        """
        with self.lock:
            if run_id in self.progress:
                # Convert file path to URL path
                if '/dev/shm/tsim/runs/' in pdf_path:
                    # Extract relative path from run directory
                    parts = pdf_path.split('/dev/shm/tsim/runs/')
                    if len(parts) > 1:
                        pdf_url = f"/pdf?file={parts[1]}"
                        self.progress[run_id]['pdf_url'] = pdf_url
                        self.progress[run_id]['pdf_file'] = pdf_path
    
    def get_active_run_for_user(self, username: str) -> Optional[str]:
        """Get active run ID for a user
        
        Args:
            username: Username
            
        Returns:
            Active run ID or None
        """
        with self.lock:
            run_id = self.active_runs.get(username)
            if run_id and run_id in self.progress:
                # Check if the run is still active (not complete)
                if not self.progress[run_id].get('complete', False):
                    return run_id
                else:
                    # Clean up completed run
                    del self.active_runs[username]
            elif run_id:
                # Clean up stale entry
                del self.active_runs[username]
        return None
    
    def set_active_run_for_user(self, username: str, run_id: str):
        """Set active run ID for a user
        
        Args:
            username: Username
            run_id: Run ID to set as active
        """
        with self.lock:
            self.active_runs[username] = run_id
    
    def clear_active_run_for_user(self, username: str):
        """Clear active run for a user
        
        Args:
            username: Username
        """
        with self.lock:
            if username in self.active_runs:
                del self.active_runs[username]
    
    def mark_complete(self, run_id: str, success: bool = True, 
                     pdf_file: Optional[str] = None, error: Optional[str] = None):
        """Mark a test as complete
        
        Args:
            run_id: Run identifier
            success: Whether test succeeded
            pdf_file: Optional PDF file path
            error: Optional error message
        """
        with self.lock:
            if run_id in self.progress:
                progress = self.progress[run_id]
                progress['complete'] = True
                progress['success'] = success
                progress['overall_progress'] = 100
                if pdf_file:
                    progress['pdf_file'] = str(pdf_file)
                    # Set PDF URL directly without calling set_pdf_url (avoid deadlock)
                    if '/dev/shm/tsim/runs/' in str(pdf_file):
                        parts = str(pdf_file).split('/dev/shm/tsim/runs/')
                        if len(parts) > 1:
                            progress['pdf_url'] = f"/pdf?file={parts[1]}"
                if error:
                    progress['error'] = error
                
                # Clear active run for any user that has this run
                for username, active_run_id in list(self.active_runs.items()):
                    if active_run_id == run_id:
                        del self.active_runs[username]
                        self.logger.debug(f"Cleared active run {run_id} for user {username}")
        
        # Log completion phase
        phase = 'COMPLETE' if success else 'FAILED'
        message = 'Test completed successfully' if success else f'Test failed: {error or "Unknown error"}'
        details = {}
        if pdf_file:
            details['pdf_file'] = str(pdf_file)
        
        # Write final progress to file
        self._write_progress_json(run_id)
        
        self.log_phase(run_id, phase, message, details)
        
        # Log TOTAL phase for compatibility
        if success:
            elapsed = time.time() - self.progress.get(run_id, {}).get('start_time', time.time())
            self.log_phase(run_id, 'TOTAL', f"Total execution time: {elapsed:.2f}s", details)
    
    def cleanup_memory(self, max_age_seconds: int = 3600):
        """Clean up old in-memory progress data
        
        Args:
            max_age_seconds: Maximum age in seconds (default 1 hour)
        """
        current_time = time.time()
        to_remove = []
        
        with self.lock:
            for run_id, progress in self.progress.items():
                age = current_time - progress['start_time']
                if age > max_age_seconds:
                    to_remove.append(run_id)
            
            for run_id in to_remove:
                del self.progress[run_id]
                self.logger.debug(f"Removed old progress data for {run_id}")
        
        if to_remove:
            self.logger.info(f"Cleaned up {len(to_remove)} old progress entries from memory")
    
    def cleanup_old_runs(self, max_age_seconds: Optional[int] = None):
        """Clean up old run directories from disk
        
        Args:
            max_age_seconds: Maximum age in seconds, defaults to config's cleanup_age
        """
        if max_age_seconds is None:
            max_age_seconds = self.config.get('cleanup_age', 86400)
        
        current_time = time.time()
        cleaned = 0
        
        for run_path in self.run_dir.iterdir():
            if run_path.is_dir():
                try:
                    mtime = run_path.stat().st_mtime
                    if current_time - mtime > max_age_seconds:
                        import shutil
                        shutil.rmtree(run_path)
                        cleaned += 1
                        self.logger.debug(f"Cleaned up old run directory: {run_path.name}")
                except Exception as e:
                    self.logger.warning(f"Error cleaning up {run_path}: {e}")
        
        if cleaned > 0:
            self.logger.info(f"Cleaned up {cleaned} old run directories from disk")
        
        # Also clean memory
        self.cleanup_memory(max_age_seconds)
    
    def _write_timing_file(self, run_id: str, phase: str, message: str):
        """Write to timing.log for SSE compatibility
        
        Args:
            run_id: Run identifier
            phase: Phase name
            message: Phase message
        """
        timing_file = self.run_dir / run_id / 'timing.log'
        try:
            mode = 'a' if timing_file.exists() else 'w'
            with open(timing_file, mode) as f:
                f.write(f"{phase} {time.time():.6f} {message}\n")
        except Exception as e:
            self.logger.warning(f"Failed to write timing file: {e}")
    
    def _write_progress_json(self, run_id: str):
        """Write progress.json for easy reading
        
        Args:
            run_id: Run identifier
        """
        progress_file = self.run_dir / run_id / 'progress.json'
        try:
            with self.lock:
                if run_id in self.progress:
                    progress_data = dict(self.progress[run_id])
                    with open(progress_file, 'w') as f:
                        json.dump(progress_data, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to write progress.json: {e}")
    
    def _write_audit_file(self, run_id: str, phase: str, message: str, 
                         details: Optional[Dict[str, Any]] = None):
        """Write to audit.log for SSE compatibility
        
        Args:
            run_id: Run identifier
            phase: Phase name
            message: Phase message
            details: Optional details
        """
        audit_file = self.run_dir / run_id / 'audit.log'
        try:
            audit_entry = {
                'timestamp': datetime.now().isoformat(),
                'run_id': run_id,
                'phase': phase,
                'message': message
            }
            if details:
                audit_entry['details'] = details
            
            mode = 'a' if audit_file.exists() else 'w'
            with open(audit_file, mode) as f:
                f.write(json.dumps(audit_entry) + '\n')
        except Exception as e:
            self.logger.warning(f"Failed to write audit file: {e}")
    
    def _read_file_progress(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Read progress from files as fallback
        
        Args:
            run_id: Run identifier
            
        Returns:
            Progress data or None
        """
        run_path = self.run_dir / run_id
        if not run_path.exists():
            return None
        
        # First try to read progress.json
        progress_file = run_path / 'progress.json'
        if progress_file.exists():
            try:
                with open(progress_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"Failed to read progress.json: {e}")
        
        # Fallback to reading timing.log
        phases = []
        timing_file = run_path / 'timing.log'
        if timing_file.exists():
            try:
                with open(timing_file, 'r') as f:
                    for line in f:
                        parts = line.strip().split(None, 2)
                        if len(parts) >= 2:
                            phase = parts[0]
                            timestamp = float(parts[1])
                            message = parts[2] if len(parts) > 2 else ""
                            phases.append({
                                'phase': phase,
                                'timestamp': timestamp,
                                'message': message
                            })
            except Exception as e:
                self.logger.warning(f"Failed to read timing file: {e}")
        
        if phases:
            # Reconstruct progress from phases
            start_time = phases[0]['timestamp'] if phases else time.time()
            current_phase = phases[-1]['phase'] if phases else 'UNKNOWN'
            complete = any(p['phase'] in ('COMPLETE', 'FAILED', 'ERROR') for p in phases)
            success = any(p['phase'] == 'COMPLETE' for p in phases)
            
            return {
                'run_id': run_id,
                'start_time': start_time,
                'phases': phases,
                'current_phase': current_phase,
                'overall_progress': 100 if complete else min(95, len(phases) * 100 // len(self.expected_phases)),
                'complete': complete,
                'success': success
            }
        
        return None
