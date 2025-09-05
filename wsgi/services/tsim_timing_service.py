#!/usr/bin/env -S python3 -B -u
"""
TSIM Timing Service
Performance timing and measurement service
"""

import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from functools import wraps


class TsimTimingService:
    """Service for timing operations and performance measurement"""
    
    def __init__(self):
        """Initialize timing service"""
        self.logger = logging.getLogger('tsim.timing')
        self.active_timers = {}
    
    def start_timer(self, timer_id: str) -> float:
        """Start a timer
        
        Args:
            timer_id: Unique identifier for the timer
            
        Returns:
            Start time
        """
        start_time = time.time()
        self.active_timers[timer_id] = {
            'start': start_time,
            'checkpoints': [],
            'end': None
        }
        return start_time
    
    def checkpoint(self, timer_id: str, checkpoint_name: str, 
                  details: Optional[str] = None) -> float:
        """Record a checkpoint for a timer
        
        Args:
            timer_id: Timer identifier
            checkpoint_name: Name of the checkpoint
            details: Optional details
            
        Returns:
            Elapsed time since start
        """
        if timer_id not in self.active_timers:
            self.logger.warning(f"Timer {timer_id} not found")
            return 0.0
        
        current_time = time.time()
        timer = self.active_timers[timer_id]
        elapsed = current_time - timer['start']
        
        checkpoint_data = {
            'name': checkpoint_name,
            'time': current_time,
            'elapsed': elapsed,
            'details': details
        }
        
        timer['checkpoints'].append(checkpoint_data)
        
        # Log the checkpoint
        log_msg = f"[{timer_id}] Checkpoint '{checkpoint_name}': {elapsed:.3f}s"
        if details:
            log_msg += f" - {details}"
        self.logger.debug(log_msg)
        
        return elapsed
    
    def end_timer(self, timer_id: str) -> Dict[str, Any]:
        """End a timer and return timing data
        
        Args:
            timer_id: Timer identifier
            
        Returns:
            Complete timing data
        """
        if timer_id not in self.active_timers:
            self.logger.warning(f"Timer {timer_id} not found")
            return {}
        
        end_time = time.time()
        timer = self.active_timers[timer_id]
        timer['end'] = end_time
        
        total_elapsed = end_time - timer['start']
        
        # Calculate checkpoint deltas
        checkpoints_with_delta = []
        last_time = timer['start']
        
        for checkpoint in timer['checkpoints']:
            delta = checkpoint['time'] - last_time
            checkpoints_with_delta.append({
                'name': checkpoint['name'],
                'elapsed': checkpoint['elapsed'],
                'delta': delta,
                'details': checkpoint['details']
            })
            last_time = checkpoint['time']
        
        result = {
            'timer_id': timer_id,
            'start': timer['start'],
            'end': end_time,
            'total_elapsed': total_elapsed,
            'checkpoints': checkpoints_with_delta
        }
        
        # Clean up
        del self.active_timers[timer_id]
        
        # Log summary
        self.logger.info(f"[{timer_id}] Total time: {total_elapsed:.3f}s")
        
        return result
    
    def get_elapsed(self, timer_id: str) -> float:
        """Get elapsed time for an active timer
        
        Args:
            timer_id: Timer identifier
            
        Returns:
            Elapsed time in seconds, or 0 if timer not found
        """
        if timer_id not in self.active_timers:
            return 0.0
        
        return time.time() - self.active_timers[timer_id]['start']
    
    def timing_decorator(self, operation_name: Optional[str] = None):
        """Decorator to time function execution
        
        Args:
            operation_name: Optional name for the operation
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Use function name if operation name not provided
                name = operation_name or f"{func.__module__}.{func.__name__}"
                timer_id = f"{name}_{time.time()}"
                
                self.start_timer(timer_id)
                
                try:
                    result = func(*args, **kwargs)
                    timing_data = self.end_timer(timer_id)
                    
                    # Log timing
                    self.logger.info(
                        f"Operation '{name}' completed in {timing_data['total_elapsed']:.3f}s"
                    )
                    
                    # Optionally attach timing data to result if it's a dict
                    if isinstance(result, dict):
                        result['_timing'] = timing_data
                    
                    return result
                    
                except Exception as e:
                    # Still end timer on exception
                    timing_data = self.end_timer(timer_id)
                    self.logger.error(
                        f"Operation '{name}' failed after {timing_data['total_elapsed']:.3f}s: {e}"
                    )
                    raise
            
            return wrapper
        return decorator
    
    def context_timer(self, timer_id: str):
        """Context manager for timing code blocks
        
        Usage:
            with timing_service.context_timer('my_operation'):
                # Code to time
                pass
        """
        class TimerContext:
            def __init__(self, service, timer_id):
                self.service = service
                self.timer_id = timer_id
                self.elapsed = 0.0
            
            def __enter__(self):
                self.service.start_timer(self.timer_id)
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                timing_data = self.service.end_timer(self.timer_id)
                self.elapsed = timing_data.get('total_elapsed', 0.0)
                return False
            
            def checkpoint(self, name: str, details: Optional[str] = None):
                return self.service.checkpoint(self.timer_id, name, details)
        
        return TimerContext(self, timer_id)
    
    def format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            Formatted string
        """
        if seconds < 0.001:
            return f"{seconds * 1000000:.0f}μs"
        elif seconds < 1:
            return f"{seconds * 1000:.1f}ms"
        elif seconds < 60:
            return f"{seconds:.2f}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.1f}s"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h {minutes}m"
    
    def get_active_timers(self) -> list:
        """Get list of active timers
        
        Returns:
            List of active timer IDs and their elapsed times
        """
        current_time = time.time()
        active = []
        
        for timer_id, timer in self.active_timers.items():
            elapsed = current_time - timer['start']
            active.append({
                'timer_id': timer_id,
                'elapsed': elapsed,
                'elapsed_formatted': self.format_duration(elapsed),
                'checkpoints': len(timer['checkpoints'])
            })
        
        return active