#!/usr/bin/env -S python3 -B -u
"""
TSIM Performance Middleware
Monitors and logs performance metrics for WSGI requests
"""

import time
import logging
import os
import json
from typing import Dict, Any, List, Callable
from datetime import datetime

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class TsimPerformanceMiddleware:
    """Performance monitoring middleware for WSGI application"""
    
    def __init__(self, app: Callable):
        """Initialize performance middleware
        
        Args:
            app: WSGI application to wrap
        """
        self.app = app
        self.logger = logging.getLogger('tsim.performance')
        
        # Statistics
        self.request_count = 0
        self.total_time = 0.0
        self.error_count = 0
        self.slow_requests = []
        self.request_times = []
        
        # Configuration
        self.slow_threshold = 1.0  # Requests slower than 1 second
        self.max_history = 1000  # Keep last N request times
        
        # Log startup metrics
        self._log_startup_metrics()
    
    def _log_startup_metrics(self):
        """Log application startup metrics"""
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'event': 'startup'
        }
        
        # Memory usage
        if PSUTIL_AVAILABLE:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            metrics['memory_rss_mb'] = memory_info.rss / 1024 / 1024
            metrics['memory_vms_mb'] = memory_info.vms / 1024 / 1024
            
            # CPU info
            metrics['cpu_count'] = psutil.cpu_count()
            metrics['cpu_percent'] = process.cpu_percent()
        
        # Python info
        import sys
        metrics['python_version'] = sys.version
        metrics['python_path'] = sys.executable
        
        self.logger.info(f"Application startup metrics: {json.dumps(metrics)}")
    
    def __call__(self, environ: Dict[str, Any], start_response: Callable) -> List[bytes]:
        """WSGI middleware callable
        
        Args:
            environ: WSGI environment
            start_response: WSGI start_response callable
            
        Returns:
            Response body
        """
        # Start timing
        start_time = time.time()
        self.request_count += 1
        
        # Extract request info
        method = environ.get('REQUEST_METHOD', 'UNKNOWN')
        path = environ.get('PATH_INFO', '/')
        query = environ.get('QUERY_STRING', '')
        remote_addr = self._get_client_ip(environ)
        
        # Log request start
        request_id = f"{start_time:.6f}_{self.request_count}"
        self.logger.debug(f"[{request_id}] Request start: {method} {path}")
        
        # Track response status
        response_status = '200'
        
        def custom_start_response(status: str, headers: List[tuple], *args):
            """Wrapper for start_response to capture status and add headers"""
            nonlocal response_status
            response_status = status.split()[0]
            
            # Calculate elapsed time
            elapsed = time.time() - start_time
            
            # Add performance headers
            perf_headers = [
                ('X-Response-Time', f'{elapsed:.3f}'),
                ('X-Request-ID', request_id),
                ('X-Request-Count', str(self.request_count))
            ]
            
            # Add average response time if we have history
            if self.request_count > 0:
                avg_time = self.total_time / self.request_count
                perf_headers.append(('X-Avg-Response-Time', f'{avg_time:.3f}'))
            
            # Add memory usage if available
            if PSUTIL_AVAILABLE:
                try:
                    process = psutil.Process(os.getpid())
                    memory_mb = process.memory_info().rss / 1024 / 1024
                    perf_headers.append(('X-Memory-Usage-MB', f'{memory_mb:.1f}'))
                except:
                    pass
            
            # Combine headers
            all_headers = headers + perf_headers
            
            return start_response(status, all_headers, *args)
        
        try:
            # Call the wrapped application
            response = self.app(environ, custom_start_response)
            
            # Calculate final elapsed time
            elapsed = time.time() - start_time
            self.total_time += elapsed
            
            # Track request time
            self.request_times.append(elapsed)
            if len(self.request_times) > self.max_history:
                self.request_times.pop(0)
            
            # Check for slow request
            if elapsed > self.slow_threshold:
                slow_info = {
                    'request_id': request_id,
                    'method': method,
                    'path': path,
                    'elapsed': elapsed,
                    'timestamp': start_time
                }
                self.slow_requests.append(slow_info)
                
                # Keep only last 100 slow requests
                if len(self.slow_requests) > 100:
                    self.slow_requests.pop(0)
                
                self.logger.warning(
                    f"[{request_id}] Slow request: {method} {path} took {elapsed:.3f}s"
                )
            
            # Log request completion
            self._log_request_metrics(
                request_id, method, path, response_status, 
                elapsed, remote_addr
            )
            
            return response
            
        except Exception as e:
            # Track error
            self.error_count += 1
            elapsed = time.time() - start_time
            
            # Log error
            self.logger.error(
                f"[{request_id}] Request error: {method} {path} - {str(e)}", 
                exc_info=True
            )
            
            # Re-raise the exception
            raise
    
    def _get_client_ip(self, environ: Dict[str, Any]) -> str:
        """Get client IP address from environ
        
        Args:
            environ: WSGI environment
            
        Returns:
            Client IP address
        """
        # Check for proxy headers
        if 'HTTP_X_FORWARDED_FOR' in environ:
            ips = environ['HTTP_X_FORWARDED_FOR'].split(',')
            return ips[0].strip()
        
        if 'HTTP_X_REAL_IP' in environ:
            return environ['HTTP_X_REAL_IP']
        
        return environ.get('REMOTE_ADDR', 'unknown')
    
    def _log_request_metrics(self, request_id: str, method: str, path: str,
                            status: str, elapsed: float, remote_addr: str):
        """Log request metrics
        
        Args:
            request_id: Request identifier
            method: HTTP method
            path: Request path
            status: Response status code
            elapsed: Request duration
            remote_addr: Client IP address
        """
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'request_id': request_id,
            'method': method,
            'path': path,
            'status': status,
            'elapsed': round(elapsed, 3),
            'remote_addr': remote_addr,
            'request_count': self.request_count,
            'avg_time': round(self.total_time / self.request_count, 3)
        }
        
        # Add memory metrics if available
        if PSUTIL_AVAILABLE:
            try:
                process = psutil.Process(os.getpid())
                metrics['memory_rss_mb'] = round(process.memory_info().rss / 1024 / 1024, 1)
                metrics['cpu_percent'] = process.cpu_percent()
            except:
                pass
        
        # Log based on status
        if status.startswith('2'):
            self.logger.info(f"Request completed: {json.dumps(metrics)}")
        elif status.startswith('4'):
            self.logger.warning(f"Client error: {json.dumps(metrics)}")
        else:
            self.logger.error(f"Server error: {json.dumps(metrics)}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get performance statistics
        
        Returns:
            Dictionary of performance metrics
        """
        stats = {
            'request_count': self.request_count,
            'error_count': self.error_count,
            'error_rate': self.error_count / max(1, self.request_count),
            'total_time': round(self.total_time, 3),
            'avg_time': round(self.total_time / max(1, self.request_count), 3),
            'slow_request_count': len(self.slow_requests)
        }
        
        # Calculate percentiles if we have history
        if self.request_times:
            sorted_times = sorted(self.request_times)
            stats['p50'] = round(sorted_times[len(sorted_times) // 2], 3)
            stats['p95'] = round(sorted_times[int(len(sorted_times) * 0.95)], 3)
            stats['p99'] = round(sorted_times[int(len(sorted_times) * 0.99)], 3)
            stats['min_time'] = round(min(sorted_times), 3)
            stats['max_time'] = round(max(sorted_times), 3)
        
        # Add memory stats if available
        if PSUTIL_AVAILABLE:
            try:
                process = psutil.Process(os.getpid())
                memory_info = process.memory_info()
                stats['memory_rss_mb'] = round(memory_info.rss / 1024 / 1024, 1)
                stats['memory_vms_mb'] = round(memory_info.vms / 1024 / 1024, 1)
                stats['cpu_percent'] = process.cpu_percent()
                
                # System-wide stats
                stats['system_memory_percent'] = psutil.virtual_memory().percent
                stats['system_cpu_percent'] = psutil.cpu_percent()
            except:
                pass
        
        return stats
    
    def reset_statistics(self):
        """Reset performance statistics"""
        self.request_count = 0
        self.total_time = 0.0
        self.error_count = 0
        self.slow_requests = []
        self.request_times = []
        
        self.logger.info("Performance statistics reset")