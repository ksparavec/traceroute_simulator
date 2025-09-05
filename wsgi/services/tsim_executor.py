#!/usr/bin/env -S python3 -B -u
"""
TSIM Executor Service
Handles execution of traceroute simulations and tests
"""

import os
import sys
import subprocess
import json
import time
import uuid
import logging
import threading
import queue
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from .tsim_background_executor import TsimBackgroundExecutor


class TsimExecutor:
    """Service for executing traceroute simulations and tests"""
    
    def __init__(self, config_service, lock_manager=None, timing_service=None):
        """Initialize executor service
        
        Args:
            config_service: TsimConfigService instance
            lock_manager: Optional TsimLockManagerService instance
            timing_service: Optional TsimTimingService instance
        """
        self.config = config_service
        self.lock_manager = lock_manager
        self.timing_service = timing_service
        self.logger = logging.getLogger('tsim.executor')
        
        # Get paths from config
        self.tsimsh_path = config_service.tsimsh_path
        self.data_dir = config_service.data_dir
        self.venv_path = config_service.venv_path
        self.raw_facts_dir = config_service.raw_facts_dir
        
        # Ensure data directories exist
        for subdir in ['traces', 'results', 'progress']:
            (self.data_dir / subdir).mkdir(parents=True, exist_ok=True)
        
        # Progress tracking
        self.active_executions = {}
        self.execution_lock = threading.Lock()
        
        # Initialize background executor for process isolation
        if lock_manager and timing_service:
            self.background_executor = TsimBackgroundExecutor(
                config_service, lock_manager, timing_service
            )
        else:
            self.background_executor = None
    
    def tsim_execute_trace(self, run_id: str, source_ip: str, dest_ip: str,
                          user_trace_data: Optional[str] = None) -> Path:
        """Execute traceroute simulation
        
        Args:
            run_id: Unique run identifier
            source_ip: Source IP address
            dest_ip: Destination IP address
            user_trace_data: Optional user-provided trace data
            
        Returns:
            Path to trace output file
            
        Raises:
            RuntimeError: If execution fails
        """
        # Start timing if available
        if self.timing_service:
            timer_id = f"trace_{run_id}"
            self.timing_service.start_timer(timer_id)
        
        # Validate inputs
        if not run_id or not source_ip or not dest_ip:
            raise ValueError("Missing required parameters")
        
        # Create trace output file
        trace_file = self.data_dir / 'traces' / f"{run_id}_trace.txt"
        
        # Update progress
        self._update_progress(run_id, 'trace', 'starting', 0)
        
        try:
            if user_trace_data:
                # Use user-provided trace data (test mode)
                # User is responsible for providing proper JSON format
                self.logger.info(f"Using user-provided trace data for run {run_id}")
                
                # Basic validation - must be valid JSON
                try:
                    trace_json = json.loads(user_trace_data)
                    if not isinstance(trace_json, dict):
                        raise ValueError("Trace data must be a JSON object")
                    
                    # Write user-provided JSON as-is
                    with open(trace_file, 'w') as f:
                        json.dump(trace_json, f, indent=2)
                    
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in user trace data: {e}")
                
                self._update_progress(run_id, 'trace', 'completed', 100)
            else:
                # Execute actual traceroute via tsimsh
                self.logger.info(f"Executing traceroute for run {run_id}: {source_ip} -> {dest_ip}")
                
                # Acquire lock if available
                lock_acquired = False
                if self.lock_manager:
                    lock_acquired = self.lock_manager.acquire_lock('traceroute_execution', timeout=30)
                
                try:
                    # Build tsimsh trace command
                    trace_command = self._build_traceroute_command(source_ip, dest_ip)
                    
                    # Execute tsimsh with trace command
                    trace_timeout = self.config.get('trace_timeout', 120)
                    result = self._execute_tsimsh_command(trace_command, timeout=trace_timeout)
                    
                    # Parse JSON output from tsimsh
                    try:
                        trace_json = json.loads(result['stdout'])
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Failed to parse tsimsh JSON output: {e}")
                        self.logger.error(f"Output was: {result['stdout']}")
                        raise RuntimeError(f"tsimsh did not return valid JSON: {e}")
                    
                    # Write JSON to file
                    with open(trace_file, 'w') as f:
                        json.dump(trace_json, f, indent=2)
                    
                    if result['returncode'] != 0:
                        self.logger.warning(f"Traceroute completed with warnings: {result['stderr']}")
                    
                    self._update_progress(run_id, 'trace', 'completed', 100)
                    
                finally:
                    # Release lock
                    if lock_acquired and self.lock_manager:
                        self.lock_manager.release_lock('traceroute_execution')
            
            # End timing
            if self.timing_service:
                timing_data = self.timing_service.end_timer(timer_id)
                self.logger.info(f"Trace execution completed in {timing_data['total_elapsed']:.2f}s")
            
            return trace_file
            
        except Exception as e:
            self.logger.error(f"Trace execution failed for run {run_id}: {e}")
            self._update_progress(run_id, 'trace', 'failed', -1, str(e))
            raise RuntimeError(f"Trace execution failed: {e}")
    
    def tsim_execute_reachability_multi(self, run_id: str, trace_file: Path,
                                       source_ip: str, dest_ip: str,
                                       source_port: Optional[str],
                                       port_protocol_list: List[Tuple[int, str]]) -> Dict[str, Any]:
        """Execute multi-service reachability test
        
        Args:
            run_id: Unique run identifier
            trace_file: Path to trace file
            source_ip: Source IP address
            dest_ip: Destination IP address
            source_port: Optional source port
            port_protocol_list: List of (port, protocol) tuples
            
        Returns:
            Dictionary with results
        """
        # Import the reachability tester (should be preloaded)
        from scripts.tsim_reachability_tester import TsimReachabilityTester
        
        # Start timing
        if self.timing_service:
            timer_id = f"reachability_{run_id}"
            self.timing_service.start_timer(timer_id)
        
        self._update_progress(run_id, 'reachability', 'starting', 0)
        
        try:
            # Create tester instance
            tester = TsimReachabilityTester(
                source_ip=source_ip,
                dest_ip=dest_ip,
                source_port=source_port,
                port_protocol_list=port_protocol_list,
                trace_file=str(trace_file),
                results_dir=str(self.data_dir / 'results'),
                run_id=run_id,
                verbose=0,
                cleanup=True
            )
            
            # Run tests
            results = tester.run()
            
            self._update_progress(run_id, 'reachability', 'completed', 100)
            
            # End timing
            if self.timing_service:
                timing_data = self.timing_service.end_timer(timer_id)
                self.logger.info(f"Reachability tests completed in {timing_data['total_elapsed']:.2f}s")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Reachability test failed for run {run_id}: {e}")
            self._update_progress(run_id, 'reachability', 'failed', -1, str(e))
            raise RuntimeError(f"Reachability test failed: {e}")
    
    def tsim_execute_visualization(self, run_id: str, trace_file: Path,
                                  results_file: Path, output_file: Path,
                                  service_info: Optional[str] = None) -> Path:
        """Execute visualization generation
        
        Args:
            run_id: Unique run identifier
            trace_file: Path to trace file
            results_file: Path to results file
            output_file: Path for output PDF
            service_info: Optional service information
            
        Returns:
            Path to generated visualization
        """
        # Import the visualizer (should be preloaded)
        from scripts.tsim_reachability_visualizer import TsimReachabilityVisualizer
        
        # Start timing
        if self.timing_service:
            timer_id = f"visualization_{run_id}"
            self.timing_service.start_timer(timer_id)
        
        self._update_progress(run_id, 'visualization', 'starting', 0)
        
        try:
            # Create visualizer instance
            visualizer = TsimReachabilityVisualizer(
                trace_file=str(trace_file),
                results_file=str(results_file),
                output_file=str(output_file),
                service_info=service_info,
                progress_callback=lambda p, m: self._update_progress(run_id, 'visualization', m, p)
            )
            
            # Generate visualization
            visualizer.generate()
            
            self._update_progress(run_id, 'visualization', 'completed', 100)
            
            # End timing
            if self.timing_service:
                timing_data = self.timing_service.end_timer(timer_id)
                self.logger.info(f"Visualization completed in {timing_data['total_elapsed']:.2f}s")
            
            return output_file
            
        except Exception as e:
            self.logger.error(f"Visualization failed for run {run_id}: {e}")
            self._update_progress(run_id, 'visualization', 'failed', -1, str(e))
            raise RuntimeError(f"Visualization failed: {e}")
    
    def _build_traceroute_command(self, source_ip: str, dest_ip: str) -> str:
        """Build tsimsh trace command
        
        Args:
            source_ip: Source IP address
            dest_ip: Destination IP address
            
        Returns:
            Tsimsh trace command
        """
        # Use the same command format as CGI version
        # -s: source IP
        # -d: destination IP
        # -j: JSON output
        # -vv: verbose output
        return f"trace -s {source_ip} -d {dest_ip} -j -vv"
    
    def _execute_tsimsh_command(self, command: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Execute tsimsh command
        
        Args:
            command: Command to send to tsimsh
            timeout: Execution timeout in seconds, defaults to config's trace_timeout
            
        Returns:
            Dictionary with stdout, stderr, and returncode
        """
        if timeout is None:
            timeout = self.config.get('trace_timeout', 120)
        # Check if tsimsh exists
        if not os.path.exists(self.tsimsh_path):
            raise RuntimeError(f"tsimsh not found at {self.tsimsh_path}")
        
        # Set environment
        env = os.environ.copy()
        env['TRACEROUTE_SIMULATOR_RAW_FACTS'] = str(self.raw_facts_dir)
        
        try:
            # Execute tsimsh with -q flag and command via stdin (same as CGI)
            result = subprocess.run(
                [self.tsimsh_path, '-q'],
                input=command + '\n',
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=str(self.data_dir)
            )
            
            return {
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
            
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Tsimsh execution timed out after {timeout} seconds")
        except Exception as e:
            raise RuntimeError(f"Tsimsh execution failed: {e}")
    
    def _update_progress(self, run_id: str, phase: str, status: str,
                        progress: int, message: Optional[str] = None):
        """Update execution progress
        
        Args:
            run_id: Run identifier
            phase: Current phase (trace/reachability/visualization)
            status: Status message
            progress: Progress percentage (0-100, -1 for error)
            message: Optional message
        """
        progress_file = self.data_dir / 'progress' / f"{run_id}.json"
        
        try:
            # Read existing progress if exists
            if progress_file.exists():
                with open(progress_file, 'r') as f:
                    progress_data = json.load(f)
            else:
                progress_data = {
                    'run_id': run_id,
                    'started': time.time(),
                    'phases': {}
                }
            
            # Update phase data
            progress_data['phases'][phase] = {
                'status': status,
                'progress': progress,
                'message': message,
                'timestamp': time.time()
            }
            
            # Calculate overall progress
            total_progress = 0
            phase_weights = {'trace': 30, 'reachability': 50, 'visualization': 20}
            for p, weight in phase_weights.items():
                if p in progress_data['phases']:
                    phase_progress = progress_data['phases'][p].get('progress', 0)
                    if phase_progress >= 0:
                        total_progress += (phase_progress * weight) / 100
            
            progress_data['overall_progress'] = int(total_progress)
            progress_data['last_update'] = time.time()
            
            # Check if complete or failed
            if progress == -1:
                progress_data['complete'] = True
                progress_data['success'] = False
            elif all(p in progress_data['phases'] and 
                    progress_data['phases'][p].get('progress', 0) == 100
                    for p in phase_weights.keys()):
                progress_data['complete'] = True
                progress_data['success'] = True
            
            # Write progress file
            with open(progress_file, 'w') as f:
                json.dump(progress_data, f)
                
        except Exception as e:
            self.logger.error(f"Failed to update progress for {run_id}: {e}")
    
    def get_progress(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get execution progress
        
        Args:
            run_id: Run identifier
            
        Returns:
            Progress data or None
        """
        # Use background executor if available for better isolation
        if self.background_executor:
            return self.background_executor.get_task_status(run_id)
        
        # Fallback to file-based progress tracking
        progress_file = self.data_dir / 'progress' / f"{run_id}.json"
        
        if progress_file.exists():
            try:
                with open(progress_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Failed to read progress for {run_id}: {e}")
        
        return None
    
    def tsim_execute_async(self, run_id: str, source_ip: str, dest_ip: str,
                          source_port: Optional[str], port_protocol_list: List[Tuple[int, str]],
                          user_trace_data: Optional[str] = None) -> Dict[str, Any]:
        """Execute complete test pipeline asynchronously in background
        
        Args:
            run_id: Unique run identifier
            source_ip: Source IP address
            dest_ip: Destination IP address
            source_port: Optional source port
            port_protocol_list: List of (port, protocol) tuples
            user_trace_data: Optional user-provided trace data
            
        Returns:
            Dictionary with task info
        """
        if not self.background_executor:
            # Fallback to synchronous execution if no background executor
            self.logger.warning("No background executor available, falling back to synchronous execution")
            # Execute trace
            trace_file = self.tsim_execute_trace(run_id, source_ip, dest_ip, user_trace_data)
            # Execute reachability tests
            results = self.tsim_execute_reachability_multi(
                run_id, trace_file, source_ip, dest_ip, source_port, port_protocol_list
            )
            return {'run_id': run_id, 'synchronous': True, 'results': results}
        
        # Prepare task parameters for background execution
        task_params = {
            'source_ip': source_ip,
            'dest_ip': dest_ip,
            'source_port': source_port,
            'port_protocol_list': port_protocol_list,
            'user_trace_data': user_trace_data,
            'results_dir': str(self.data_dir / 'results'),
            'trace_file': str(Path('/dev/shm/tsim/runs') / run_id / f"{run_id}.trace"),
            'summary': {
                'source_ip': source_ip,
                'dest_ip': dest_ip,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'run_id': run_id,
                'services': [{'port': port, 'protocol': protocol} for port, protocol in port_protocol_list]
            }
        }
        
        # Execute in background
        return self.background_executor.execute_background_task(
            run_id, 'full_test', task_params
        )
    
    def cleanup_old_data(self, max_age: Optional[int] = None) -> int:
        """Clean up old execution data
        
        Args:
            max_age: Maximum age in seconds, defaults to config's cleanup_age
            
        Returns:
            Number of files cleaned
        """
        if max_age is None:
            max_age = self.config.get('cleanup_age', 86400)
        cleaned = 0
        current_time = time.time()
        
        for subdir in ['traces', 'results', 'progress']:
            dir_path = self.data_dir / subdir
            if dir_path.exists():
                for file_path in dir_path.iterdir():
                    try:
                        if current_time - file_path.stat().st_mtime > max_age:
                            file_path.unlink()
                            cleaned += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to clean {file_path}: {e}")
        
        if cleaned > 0:
            self.logger.info(f"Cleaned {cleaned} old files")
        
        return cleaned