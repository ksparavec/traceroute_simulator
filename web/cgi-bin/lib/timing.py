#!/usr/bin/env -S python3 -B -u
"""Timing instrumentation module for performance analysis."""

import time
import os
from datetime import datetime
from typing import Optional, Dict, Any


class TimingLogger:
    """Log timing information for performance analysis."""
    
    def __init__(self, session_id: str = "unknown", operation_name: str = "operation"):
        """Initialize timing logger.
        
        Args:
            session_id: Session or run ID for tracking related operations
            operation_name: Name of the operation being timed
        """
        self.session_id = session_id
        self.operation_name = operation_name
        self.start_time = time.time()
        self.last_checkpoint_time = self.start_time
        self.checkpoints: Dict[str, float] = {}
        self.durations: list = []  # Store durations with names
        self.log_file = "/var/www/traceroute-web/logs/timings.log"
        
        # Ensure log directory exists
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        
        # Log start
        self._log_raw("START", 0.0, f"{operation_name} begin")
    
    def _log_raw(self, checkpoint_name: str, duration: float, details: str = ""):
        """Internal method to log with specific duration."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Format log entry with duration in column 4
        log_entry = f"[{timestamp}] [{self.session_id}] {duration:7.2f}s | {self.operation_name}_{checkpoint_name}"
        if details:
            log_entry += f" | {details}"
        
        # Write to log file
        try:
            with open(self.log_file, 'a') as f:
                f.write(log_entry + "\n")
        except Exception:
            # Fail silently if we can't write logs
            pass
    
    def log_checkpoint(self, checkpoint_name: str, details: str = ""):
        """Log a timing checkpoint with duration since last checkpoint.
        
        Args:
            checkpoint_name: Name of the checkpoint
            details: Optional details about the checkpoint
        """
        current_time = time.time()
        duration = current_time - self.last_checkpoint_time
        self.last_checkpoint_time = current_time
        
        # Store checkpoint time and duration
        self.checkpoints[checkpoint_name] = current_time - self.start_time
        self.durations.append((checkpoint_name, duration, details))
        
        # Log with duration
        self._log_raw(checkpoint_name, duration, details)
    
    def log_operation(self, operation: str, details: str = ""):
        """Log a complete operation with its duration.
        
        Args:
            operation: Name of the operation (e.g., script name)
            details: Optional details about the operation
        """
        self.log_checkpoint(operation, details)
    
    def log_operation_start(self, operation: str):
        """Deprecated - use log_operation instead."""
        # Just mark the time, don't log
        self.last_checkpoint_time = time.time()
    
    def log_operation_end(self, operation: str, details: str = ""):
        """Deprecated - use log_operation instead."""
        # Log the operation with its duration
        self.log_checkpoint(operation, details)
    
    def finish(self, status: str = "complete", details: str = ""):
        """Mark the operation as finished and log total time.
        
        Args:
            status: Final status (e.g., "success", "failure", "complete")
            details: Optional details about the final status
        """
        total_time = time.time() - self.start_time
        self._log_raw("TOTAL", total_time, f"status={status} {details}".strip())
    
    def get_elapsed(self) -> float:
        """Get elapsed time since start.
        
        Returns:
            Elapsed time in seconds
        """
        return time.time() - self.start_time
    
    def get_checkpoint_time(self, checkpoint: str) -> Optional[float]:
        """Get the elapsed time at a specific checkpoint.
        
        Args:
            checkpoint: Name of the checkpoint
            
        Returns:
            Elapsed time at checkpoint, or None if checkpoint doesn't exist
        """
        return self.checkpoints.get(checkpoint)