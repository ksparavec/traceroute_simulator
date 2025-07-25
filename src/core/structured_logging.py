#!/usr/bin/env -S python3 -B -u
"""
Structured Logging for Traceroute Simulator

This module provides structured logging with appropriate verbosity levels
and consistent formatting across all components.

Key Features:
- Structured log messages with context
- Verbosity-based filtering
- Performance metrics logging
- Security-sensitive data masking
- JSON output support for log aggregation
"""

import logging as std_logging
import sys
import time
import json
from typing import Dict, Any, Optional, List, Union
from functools import wraps
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


class StructuredLogger:
    """
    Structured logger with verbosity control and consistent formatting.
    
    Verbosity levels:
    - 0: Only errors and critical messages
    - 1: Info messages and warnings  
    - 2: Debug messages
    - 3: Trace-level debugging with full details
    """
    
    def __init__(self, name: str, verbose_level: int = 0):
        """
        Initialize structured logger.
        
        Args:
            name: Logger name (usually module name)
            verbose_level: Verbosity level (0-3)
        """
        self.name = name
        self.verbose_level = verbose_level
        self.logger = std_logging.getLogger(name)
        
        # Configure base logger
        self.logger.setLevel(std_logging.DEBUG)
        self.logger.handlers.clear()
        
        # Add console handler with custom formatter
        handler = std_logging.StreamHandler(sys.stderr)
        handler.setFormatter(self._create_formatter())
        self.logger.addHandler(handler)
        
        # Performance tracking
        self._timers: Dict[str, float] = {}
        
    def _create_formatter(self) -> std_logging.Formatter:
        """Create appropriate formatter based on verbosity."""
        if self.verbose_level >= 3:
            # Full debug format
            return std_logging.Formatter(
                '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        elif self.verbose_level >= 2:
            # Debug format
            return std_logging.Formatter('[%(name)s] %(levelname)s: %(message)s')
        else:
            # Simple format
            return std_logging.Formatter('%(message)s')
    
    def _should_log(self, level: int) -> bool:
        """Check if message should be logged based on verbosity."""
        level_map = {
            std_logging.ERROR: 0,
            std_logging.WARNING: 1,
            std_logging.INFO: 1,
            std_logging.DEBUG: 2,
        }
        return self.verbose_level >= level_map.get(level, 3)
    
    def error(self, message: str, **context: Any) -> None:
        """Log error message (always shown)."""
        if context and self.verbose_level >= 2:
            message = f"{message} | {self._format_context(context)}"
        self.logger.error(message)
    
    def warning(self, message: str, **context: Any) -> None:
        """Log warning message (shown at verbosity 1+)."""
        if self._should_log(std_logging.WARNING):
            if context and self.verbose_level >= 2:
                message = f"{message} | {self._format_context(context)}"
            self.logger.warning(message)
    
    def info(self, message: str, **context: Any) -> None:
        """Log info message (shown at verbosity 1+)."""
        if self._should_log(std_logging.INFO):
            if context and self.verbose_level >= 2:
                message = f"{message} | {self._format_context(context)}"
            self.logger.info(message)
    
    def debug(self, message: str, **context: Any) -> None:
        """Log debug message (shown at verbosity 2+)."""
        if self._should_log(std_logging.DEBUG):
            if context:
                message = f"{message} | {self._format_context(context)}"
            self.logger.debug(message)
    
    def trace(self, message: str, **context: Any) -> None:
        """Log trace message (shown at verbosity 3)."""
        if self.verbose_level >= 3:
            if context:
                message = f"{message} | {self._format_context(context)}"
            self.logger.debug(f"[TRACE] {message}")
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context dictionary for logging."""
        # Mask sensitive data
        masked_context = self._mask_sensitive_data(context)
        
        if self.verbose_level >= 3:
            # Full JSON format for trace level
            return json.dumps(masked_context, default=str)
        else:
            # Key=value format for normal logging
            return " ".join(f"{k}={v}" for k, v in masked_context.items())
    
    def _mask_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive data in context."""
        sensitive_keys = {'password', 'secret', 'token', 'key', 'auth'}
        masked_data = {}
        
        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                masked_data[key] = "***MASKED***"
            elif isinstance(value, dict):
                masked_data[key] = self._mask_sensitive_data(value)
            else:
                masked_data[key] = value
                
        return masked_data
    
    @contextmanager
    def timer(self, operation: str):
        """Context manager for timing operations."""
        start_time = time.time()
        self.debug(f"Starting {operation}")
        
        try:
            yield
        finally:
            elapsed = time.time() - start_time
            self.debug(f"Completed {operation}", elapsed_ms=f"{elapsed*1000:.2f}")
    
    def log_performance(self, operation: str, start_time: float) -> None:
        """Log performance metrics for an operation."""
        elapsed = time.time() - start_time
        self.debug(
            f"Performance: {operation}",
            elapsed_ms=f"{elapsed*1000:.2f}",
            elapsed_s=f"{elapsed:.3f}"
        )
    
    def log_router_loading(self, router_name: str, success: bool, **details: Any) -> None:
        """Log router loading events."""
        if success:
            self.info(f"Loaded router: {router_name}", **details)
        else:
            self.warning(f"Failed to load router: {router_name}", **details)
    
    def log_route_decision(
        self,
        src_ip: str,
        dst_ip: str,
        router: str,
        decision: str,
        **details: Any
    ) -> None:
        """Log routing decisions."""
        self.debug(
            f"Route decision on {router}",
            src=src_ip,
            dst=dst_ip,
            decision=decision,
            **details
        )
    
    def log_hop(self, hop_num: int, router: str, ip: str, **details: Any) -> None:
        """Log traceroute hop information."""
        self.debug(f"Hop {hop_num}: {router} ({ip})", **details)
    
    def log_command_execution(
        self,
        command: Union[str, List[str]],
        host: Optional[str] = None,
        success: Optional[bool] = None,
        **details: Any
    ) -> None:
        """Log command execution."""
        cmd_str = command if isinstance(command, str) else " ".join(command)
        
        # Mask sensitive command arguments
        for sensitive in ['--password', '--auth-token']:
            if sensitive in cmd_str:
                idx = cmd_str.index(sensitive)
                # Find next space or end of string
                next_space = cmd_str.find(' ', idx + len(sensitive) + 1)
                if next_space == -1:
                    next_space = len(cmd_str)
                # Mask the value
                cmd_str = cmd_str[:idx + len(sensitive) + 1] + "***MASKED***" + cmd_str[next_space:]
        
        message = f"Executing: {cmd_str}"
        if host:
            message = f"[{host}] {message}"
            
        if success is not None:
            message += f" - {'SUCCESS' if success else 'FAILED'}"
            
        self.debug(message, **details)


def get_logger(name: str, verbose_level: int = 0) -> StructuredLogger:
    """
    Get or create a structured logger.
    
    Args:
        name: Logger name (usually __name__)
        verbose_level: Verbosity level (0-3)
        
    Returns:
        StructuredLogger instance
    """
    # Cache loggers to avoid recreation
    if not hasattr(get_logger, '_loggers'):
        get_logger._loggers = {}
        
    cache_key = f"{name}:{verbose_level}"
    if cache_key not in get_logger._loggers:
        get_logger._loggers[cache_key] = StructuredLogger(name, verbose_level)
        
    return get_logger._loggers[cache_key]


def log_function_call(func):
    """
    Decorator to log function calls with arguments and results.
    
    Only logs at verbosity level 3 (trace).
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Get logger from first argument if it has verbose_level
        verbose_level = 0
        if args and hasattr(args[0], 'verbose_level'):
            verbose_level = args[0].verbose_level
        elif 'verbose_level' in kwargs:
            verbose_level = kwargs['verbose_level']
            
        logger = get_logger(func.__module__, verbose_level)
        
        # Only log at trace level
        if verbose_level >= 3:
            # Log function entry
            logger.trace(
                f"Calling {func.__name__}",
                args=str(args)[:200],  # Truncate long args
                kwargs=str(kwargs)[:200]
            )
            
            start_time = time.time()
            
        try:
            result = func(*args, **kwargs)
            
            if verbose_level >= 3:
                # Log function exit
                elapsed = time.time() - start_time
                logger.trace(
                    f"Completed {func.__name__}",
                    elapsed_ms=f"{elapsed*1000:.2f}",
                    result_type=type(result).__name__
                )
                
            return result
            
        except Exception as e:
            if verbose_level >= 3:
                logger.trace(
                    f"Exception in {func.__name__}",
                    exception_type=type(e).__name__,
                    exception_msg=str(e)
                )
            raise
            
    return wrapper


class LogContext:
    """Context manager for temporary log context."""
    
    def __init__(self, logger: StructuredLogger, **context: Any):
        self.logger = logger
        self.context = context
        self.saved_context = {}
        
    def __enter__(self):
        # Save and update context
        for key, value in self.context.items():
            if hasattr(self.logger, key):
                self.saved_context[key] = getattr(self.logger, key)
                setattr(self.logger, key, value)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore context
        for key, value in self.saved_context.items():
            setattr(self.logger, key, value)


# Convenience functions for module-level logging

def setup_logging(verbose_level: int = 0) -> None:
    """
    Setup logging for the entire application.
    
    Args:
        verbose_level: Global verbosity level (0-3)
    """
    # Set global verbosity level
    if not hasattr(setup_logging, '_verbose_level'):
        setup_logging._verbose_level = verbose_level
    else:
        setup_logging._verbose_level = verbose_level
        
    # Configure root logger to suppress unwanted messages
    root_logger = std_logging.getLogger()
    root_logger.setLevel(std_logging.WARNING)
    
    # Suppress specific noisy loggers
    for logger_name in ['paramiko', 'urllib3', 'asyncio']:
        std_logging.getLogger(logger_name).setLevel(std_logging.ERROR)


def get_verbose_level() -> int:
    """Get the global verbose level."""
    return getattr(setup_logging, '_verbose_level', 0)