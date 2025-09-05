#!/usr/bin/env -S python3 -B -u
"""
TSIM Reachability Tester - Wrapper for MultiServiceTester

This is a minimal wrapper that uses the copied CGI logic from TsimMultiServiceTester.
"""

import os
import sys
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path

# Import the actual implementation from the copied CGI script
from scripts.tsim_multi_service_tester import TsimMultiServiceTester


class TsimReachabilityTester:
    """Wrapper class that delegates to TsimMultiServiceTester"""
    
    def __init__(self, source_ip: str, dest_ip: str, source_port: Optional[str],
                 port_protocol_list: List[Tuple[int, str]], 
                 trace_file: str, results_dir: str, run_id: str, verbose: int = 0, 
                 cleanup: bool = True):
        """Initialize the reachability tester"""
        self.source_ip = source_ip
        self.dest_ip = dest_ip
        self.source_port = source_port
        self.port_protocol_list = port_protocol_list
        self.trace_file = trace_file
        self.results_dir = results_dir
        self.run_id = run_id
        self.verbose = verbose
        self.cleanup = cleanup
        
        # Set environment variables that the CGI script expects
        os.environ['RUN_ID'] = run_id
        if 'LOG_DIR' not in os.environ:
            os.environ['LOG_DIR'] = '/var/log/tsim'
        
        # Convert source_port string to int or None for TsimMultiServiceTester
        source_port_int = None
        if source_port and source_port != 'ephemeral':
            try:
                source_port_int = int(source_port)
            except ValueError:
                pass
        
        # Create the actual tester instance
        self.tester = TsimMultiServiceTester(
            source_ip=source_ip,
            source_port=source_port_int,  # Pass the converted port
            dest_ip=dest_ip,
            services=port_protocol_list,
            output_dir=results_dir,
            trace_file=trace_file,
            verbose=verbose,
            run_id=run_id
        )
    
    def run(self) -> Dict[str, Any]:
        """Run the multi-service test"""
        try:
            # Run the actual test
            result = self.tester.run()
            
            # The CGI script returns results directly
            return result
            
        except Exception as e:
            return {
                'error': str(e),
                'source_ip': self.source_ip,
                'dest_ip': self.dest_ip,
                'services': self.port_protocol_list
            }
    
    def cleanup_test_environment(self):
        """Cleanup test environment"""
        if hasattr(self.tester, 'phase5_cleanup'):
            self.tester.phase5_cleanup()