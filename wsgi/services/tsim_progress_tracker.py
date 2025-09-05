#!/usr/bin/env -S python3 -B -u
"""
TSIM Progress Tracker Service
Creates and manages progress files in CGI-compatible format
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


class TsimProgressTracker:
    """Service for tracking test progress with CGI-compatible files"""
    
    def __init__(self, config_service):
        """Initialize progress tracker
        
        Args:
            config_service: TsimConfigService instance
        """
        self.config = config_service
        self.logger = logging.getLogger('tsim.progress_tracker')
        
        # Get run directory
        self.run_dir = Path(config_service.get('run_dir', '/dev/shm/tsim/runs'))
        self.run_dir.mkdir(parents=True, exist_ok=True)
    
    def create_run_directory(self, run_id: str) -> Path:
        """Create run directory with required files
        
        Args:
            run_id: Run identifier
            
        Returns:
            Path to run directory
        """
        run_path = self.run_dir / run_id
        run_path.mkdir(parents=True, exist_ok=True)
        
        # Create initial timing.log
        timing_file = run_path / 'timing.log'
        with open(timing_file, 'w') as f:
            f.write(f"START {time.time():.6f} Test execution started\n")
        
        # Create initial audit.log
        audit_file = run_path / 'audit.log'
        with open(audit_file, 'w') as f:
            timestamp = datetime.now().isoformat()
            f.write(json.dumps({
                'timestamp': timestamp,
                'run_id': run_id,
                'phase': 'START',
                'message': 'Test execution started'
            }) + '\n')
        
        # Create progress.json for compatibility
        progress_file = run_path / 'progress.json'
        with open(progress_file, 'w') as f:
            json.dump({
                'run_id': run_id,
                'start_time': time.time(),
                'phases': [],
                'complete': False
            }, f)
        
        self.logger.info(f"Created run directory: {run_path}")
        return run_path
    
    def log_phase(self, run_id: str, phase: str, message: str = "", 
                  details: Optional[Dict[str, Any]] = None):
        """Log a phase to timing and audit logs
        
        Args:
            run_id: Run identifier
            phase: Phase name
            message: Optional message
            details: Optional details dictionary
        """
        run_path = self.run_dir / run_id
        if not run_path.exists():
            self.logger.warning(f"Run directory not found: {run_path}")
            return
        
        timestamp = time.time()
        
        # Update timing.log
        timing_file = run_path / 'timing.log'
        with open(timing_file, 'a') as f:
            f.write(f"{phase} {timestamp:.6f} {message}\n")
        
        # Update audit.log
        audit_file = run_path / 'audit.log'
        audit_entry = {
            'timestamp': datetime.now().isoformat(),
            'run_id': run_id,
            'phase': phase,
            'message': message
        }
        if details:
            audit_entry['details'] = details
        
        with open(audit_file, 'a') as f:
            f.write(json.dumps(audit_entry) + '\n')
        
        # Update progress.json
        progress_file = run_path / 'progress.json'
        
        # Append new phase to the file (one JSON object per line)
        phase_data = {
            'phase': phase,
            'timestamp': timestamp,
            'message': message,
            'details': details
        }
        
        # Append to file
        with open(progress_file, 'a') as f:
            json.dump(phase_data, f)
            f.write('\n')
    
    def get_progress(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get current progress for a run
        
        Args:
            run_id: Run identifier
            
        Returns:
            Progress data or None
        """
        run_path = self.run_dir / run_id
        if not run_path.exists():
            return None
        
        # Read timing.log for phases
        phases = []
        timing_file = run_path / 'timing.log'
        if timing_file.exists():
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
        
        # Read progress.json for overall status
        progress_file = run_path / 'progress.json'
        if progress_file.exists():
            try:
                with open(progress_file, 'r') as f:
                    progress = json.load(f)
                
                # Merge phases from timing.log
                if phases:
                    progress['all_phases'] = phases
                
                # Calculate progress percentage
                total_phases = len(phases)
                if total_phases > 0:
                    if progress.get('complete'):
                        progress['overall_progress'] = 100
                    else:
                        # Estimate based on typical phases
                        expected_phases = 15  # Typical number of phases
                        progress['overall_progress'] = min(95, int(100 * total_phases / expected_phases))
                else:
                    progress['overall_progress'] = 0
                
                return progress
            except Exception as e:
                self.logger.error(f"Error reading progress file: {e}")
        
        return None
    
    def mark_complete(self, run_id: str, success: bool = True, 
                     pdf_file: Optional[str] = None):
        """Mark a test as complete
        
        Args:
            run_id: Run identifier
            success: Whether test succeeded
            pdf_file: Optional PDF file path
        """
        phase = 'COMPLETE' if success else 'FAILED'
        message = 'Test completed successfully' if success else 'Test failed'
        
        details = {}
        if pdf_file:
            details['pdf_file'] = str(pdf_file)
        
        self.log_phase(run_id, phase, message, details)
        
        # Also log TOTAL phase for compatibility
        self.log_phase(run_id, 'TOTAL', f"Total execution time", details)
    
    def cleanup_old_runs(self, max_age_seconds: Optional[int] = None):
        """Clean up old run directories
        
        Args:
            max_age_seconds: Maximum age in seconds, defaults to config's cleanup_age
        """
        if max_age_seconds is None:
            max_age_seconds = self.config.get('cleanup_age', 86400)
        current_time = time.time()
        cleaned = 0
        
        for run_path in self.run_dir.iterdir():
            if run_path.is_dir():
                # Check age
                try:
                    mtime = run_path.stat().st_mtime
                    if current_time - mtime > max_age_seconds:
                        # Remove directory
                        import shutil
                        shutil.rmtree(run_path)
                        cleaned += 1
                        self.logger.info(f"Cleaned up old run: {run_path.name}")
                except Exception as e:
                    self.logger.error(f"Error cleaning up {run_path}: {e}")
        
        if cleaned > 0:
            self.logger.info(f"Cleaned up {cleaned} old run directories")