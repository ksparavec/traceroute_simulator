#!/usr/bin/env -S python3 -B -u
"""
TSIM Executor Service - SIMPLIFIED
Direct execution without subprocess spawning
"""

import os
import sys
import json
import time
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime


class TsimExecutor:
    """Service for executing traceroute simulations and tests - DIRECT EXECUTION"""
    
    def __init__(self, config_service, lock_manager=None, timing_service=None, progress_tracker=None):
        """Initialize executor service
        
        Args:
            config_service: TsimConfigService instance
            lock_manager: Optional TsimLockManagerService instance
            timing_service: Optional TsimTimingService instance
            progress_tracker: Optional TsimProgressTracker instance
        """
        self.config = config_service
        self.lock_manager = lock_manager
        self.timing_service = timing_service
        self.progress_tracker = progress_tracker
        self.logger = logging.getLogger('tsim.executor')
        
        # Get paths from config
        self.tsimsh_path = config_service.tsimsh_path
        self.data_dir = config_service.data_dir
        self.run_dir = Path('/dev/shm/tsim/runs')
        self.venv_path = config_service.venv_path
        self.raw_facts_dir = config_service.raw_facts_dir
        
        # Ensure directories exist
        self.run_dir.mkdir(parents=True, exist_ok=True)
        for subdir in ['traces', 'results', 'progress']:
            (self.data_dir / subdir).mkdir(parents=True, exist_ok=True)
        
        # Will be set when hybrid executor is created
        self.hybrid_executor = None
        
        self.logger.info("TsimExecutor initialized (subprocess-free version)")
    
    def set_hybrid_executor(self, hybrid_executor):
        """Set the hybrid executor instance
        
        Args:
            hybrid_executor: TsimHybridExecutor instance
        """
        self.hybrid_executor = hybrid_executor
        self.logger.info("Hybrid executor configured")
    
    def execute(self, run_id: str, source_ip: str, dest_ip: str,
                source_port: Optional[str], port_protocol_list: List[Tuple[int, str]],
                user_trace_data: Optional[str] = None) -> Dict[str, Any]:
        """Execute complete test pipeline using hybrid executor
        
        Args:
            run_id: Unique run identifier
            source_ip: Source IP address
            dest_ip: Destination IP address
            source_port: Optional source port
            port_protocol_list: List of (port, protocol) tuples
            user_trace_data: Optional user-provided trace data
            
        Returns:
            Dictionary with execution results
        """
        if not self.hybrid_executor:
            raise RuntimeError("Hybrid executor not configured")
        
        # Prepare parameters for hybrid executor
        params = {
            'run_id': run_id,
            'source_ip': source_ip,
            'dest_ip': dest_ip,
            'source_port': source_port,
            'port_protocol_list': port_protocol_list,
            'user_trace_data': user_trace_data,
            'run_dir': str(self.run_dir / run_id),
            'summary': {
                'source_ip': source_ip,
                'dest_ip': dest_ip,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'run_id': run_id,
                'services': [{'port': port, 'protocol': protocol} for port, protocol in port_protocol_list]
            }
        }
        
        # Execute directly using hybrid executor
        self.logger.info(f"Starting direct execution for run {run_id}")
        try:
            result = self.hybrid_executor.execute_full_test(params)
            self.logger.info(f"Execution completed for run {run_id}")
            return result
        except Exception as e:
            self.logger.error(f"Execution failed for run {run_id}: {e}")
            raise
    
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
        cutoff_time = time.time() - max_age
        
        # Clean up old run directories
        if self.run_dir.exists():
            for run_path in self.run_dir.iterdir():
                if run_path.is_dir():
                    try:
                        mtime = run_path.stat().st_mtime
                        if mtime < cutoff_time:
                            import shutil
                            shutil.rmtree(run_path)
                            cleaned += 1
                            self.logger.debug(f"Cleaned up old run directory: {run_path}")
                    except Exception as e:
                        self.logger.warning(f"Failed to clean up {run_path}: {e}")
        
        self.logger.info(f"Cleaned up {cleaned} old run directories")
        return cleaned