#!/usr/bin/env -S python3 -B -u
"""
TSIM Logger Service
Centralized logging service for the application
"""

import os
import json
import time
import logging
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from functools import wraps


class TsimLoggerService:
    """Centralized logging service"""
    
    def __init__(self, config_service):
        """Initialize logger service
        
        Args:
            config_service: TsimConfigService instance
        """
        self.config = config_service
        self.log_dir = config_service.log_dir
        
        # Ensure log directory exists
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
        except Exception as e:
            print(f"Warning: Could not create log directory: {e}")
            # Use config-based fallback for log directory
            fallback_log_dir = config_service.get('log_dir', '/var/log/tsim')
            self.log_dir = Path(fallback_log_dir)
        
        # Set up Python logging
        self.logger = logging.getLogger('tsim')
        
        # Configure log files
        self.app_log = self.log_dir / 'tsim.log'
        self.error_log = self.log_dir / 'tsim_error.log'
        self.audit_log = self.log_dir / 'audit.log'
        self.performance_log = self.log_dir / 'performance.log'
        self.timing_log = self.log_dir / 'timings.log'
        
        # Set up handlers if not already configured
        if not self.logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self):
        """Set up logging handlers"""
        # Application log handler
        try:
            app_handler = logging.FileHandler(self.app_log)
            app_handler.setLevel(logging.INFO)
            app_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            app_handler.setFormatter(app_formatter)
            self.logger.addHandler(app_handler)
        except Exception as e:
            print(f"Warning: Could not create app log handler: {e}")
        
        # Error log handler
        try:
            error_handler = logging.FileHandler(self.error_log)
            error_handler.setLevel(logging.ERROR)
            error_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s\n%(exc_info)s'
            )
            error_handler.setFormatter(error_formatter)
            self.logger.addHandler(error_handler)
        except Exception as e:
            print(f"Warning: Could not create error log handler: {e}")
        
        # Console handler for development
        if self.config.get('debug', False):
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            console_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)
        
        # Set overall log level
        self.logger.setLevel(logging.DEBUG if self.config.get('debug', False) else logging.INFO)
    
    def log_info(self, message: str, **kwargs):
        """Log informational message
        
        Args:
            message: Log message
            **kwargs: Additional context
        """
        self.logger.info(message, extra=kwargs)
    
    def log_warning(self, message: str, **kwargs):
        """Log warning message
        
        Args:
            message: Log message
            **kwargs: Additional context
        """
        self.logger.warning(message, extra=kwargs)
    
    def log_error(self, message: str, exception: Optional[Exception] = None, 
                  traceback: Optional[str] = None, **kwargs):
        """Log error message
        
        Args:
            message: Log message
            exception: Optional exception object
            traceback: Optional traceback string
            **kwargs: Additional context
        """
        if exception:
            self.logger.error(message, exc_info=exception, extra=kwargs)
        else:
            self.logger.error(message, extra=kwargs)
        
        # Also write to error log file directly for critical errors
        if traceback:
            try:
                with open(self.error_log, 'a') as f:
                    f.write(f"\n{'='*60}\n")
                    f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                    f.write(f"Error: {message}\n")
                    f.write(f"Traceback:\n{traceback}\n")
                    if kwargs:
                        f.write(f"Context: {json.dumps(kwargs, default=str)}\n")
            except:
                pass  # Fail silently
    
    def log_debug(self, message: str, **kwargs):
        """Log debug message
        
        Args:
            message: Log message
            **kwargs: Additional context
        """
        self.logger.debug(message, extra=kwargs)
    
    def log_audit(self, action: str, username: str, ip_address: str, 
                  success: bool = True, details: Optional[Dict[str, Any]] = None):
        """Log audit event
        
        Args:
            action: Action performed
            username: Username performing action
            ip_address: Client IP address
            success: Whether action was successful
            details: Additional details
        """
        audit_entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'username': username,
            'ip_address': ip_address,
            'success': success,
            'details': details or {}
        }
        
        try:
            with open(self.audit_log, 'a') as f:
                f.write(json.dumps(audit_entry) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to write audit log: {e}")
    
    def log_performance(self, operation: str, duration: float, 
                       details: Optional[Dict[str, Any]] = None):
        """Log performance metrics
        
        Args:
            operation: Operation name
            duration: Duration in seconds
            details: Additional details
        """
        perf_entry = {
            'timestamp': datetime.now().isoformat(),
            'operation': operation,
            'duration': duration,
            'details': details or {}
        }
        
        try:
            with open(self.performance_log, 'a') as f:
                f.write(json.dumps(perf_entry) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to write performance log: {e}")
    
    def log_timing(self, run_id: str, checkpoint: str, elapsed: float, 
                  details: Optional[str] = None):
        """Log timing information
        
        Args:
            run_id: Run ID
            checkpoint: Checkpoint name
            elapsed: Elapsed time in seconds
            details: Optional details
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        try:
            with open(self.timing_log, 'a') as f:
                log_entry = f"[{timestamp}] [{run_id}] {elapsed:7.2f}s | {checkpoint}"
                if details:
                    log_entry += f" | {details}"
                f.write(log_entry + '\n')
        except Exception as e:
            self.logger.error(f"Failed to write timing log: {e}")
    
    def timing_decorator(self, operation_name: str):
        """Decorator to log function execution time
        
        Args:
            operation_name: Name of the operation
            
        Returns:
            Decorator function
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time
                    self.log_performance(operation_name, duration, {'status': 'success'})
                    return result
                except Exception as e:
                    duration = time.time() - start_time
                    self.log_performance(operation_name, duration, 
                                       {'status': 'error', 'error': str(e)})
                    raise
            return wrapper
        return decorator
    
    def get_recent_errors(self, limit: int = 100) -> list:
        """Get recent errors from error log
        
        Args:
            limit: Maximum number of errors to return
            
        Returns:
            List of recent error entries
        """
        errors = []
        
        try:
            if self.error_log.exists():
                with open(self.error_log, 'r') as f:
                    lines = f.readlines()
                    # Parse and return last N errors
                    # This is a simple implementation; could be enhanced
                    errors = lines[-limit:] if len(lines) > limit else lines
        except Exception as e:
            self.logger.error(f"Failed to read error log: {e}")
        
        return errors
    
    def get_audit_trail(self, username: Optional[str] = None, 
                       action: Optional[str] = None,
                       limit: int = 100) -> list:
        """Get audit trail entries
        
        Args:
            username: Filter by username
            action: Filter by action
            limit: Maximum number of entries to return
            
        Returns:
            List of audit entries
        """
        entries = []
        
        try:
            if self.audit_log.exists():
                with open(self.audit_log, 'r') as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                            
                            # Apply filters
                            if username and entry.get('username') != username:
                                continue
                            if action and entry.get('action') != action:
                                continue
                            
                            entries.append(entry)
                            
                            if len(entries) >= limit:
                                break
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            self.logger.error(f"Failed to read audit log: {e}")
        
        return entries[-limit:]  # Return last N entries
    
    def rotate_logs(self):
        """Rotate log files (to be called by cron or scheduler)"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        for log_file in [self.app_log, self.error_log, self.audit_log, 
                        self.performance_log, self.timing_log]:
            try:
                if log_file.exists() and log_file.stat().st_size > 100 * 1024 * 1024:  # 100MB
                    rotated_file = log_file.with_suffix(f'.{timestamp}.log')
                    log_file.rename(rotated_file)
                    self.logger.info(f"Rotated log file: {log_file} -> {rotated_file}")
            except Exception as e:
                self.logger.error(f"Failed to rotate log file {log_file}: {e}")