#!/usr/bin/env -S python3 -B -u
"""
TSIM Test Config Handler
Returns test configuration for authenticated users
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from .tsim_base_handler import TsimBaseHandler
from services.tsim_port_parser_service import TsimPortParserService


class TsimTestConfigHandler(TsimBaseHandler):
    """Handler for test configuration requests"""
    
    def __init__(self, config_service, session_manager, logger_service):
        """Initialize test config handler
        
        Args:
            config_service: TsimConfigService instance
            session_manager: TsimSessionManager instance
            logger_service: TsimLoggerService instance
        """
        super().__init__(session_manager, logger_service)
        self.config = config_service
        self.port_parser = TsimPortParserService()
        self.logger = logging.getLogger('tsim.handler.test_config')
    
    def handle(self, environ: Dict[str, Any], start_response) -> List[bytes]:
        """Handle test configuration request
        
        Args:
            environ: WSGI environment
            start_response: WSGI start_response callable
            
        Returns:
            Response body
        """
        # Check session
        session = self.validate_session(environ)
        if not session:
            return self.error_response(start_response, 'Authentication required', '401 Unauthorized')
        
        # Get user role
        user_role = session.get('role', 'user')
        
        # Check if trace file input is enabled (test mode)
        # This allows users to provide their own trace data instead of executing real traces
        trace_input_enabled = self.config.get('allow_trace_input', True)
        test_mode = self.config.get('test_mode', False)
        
        # Build test configuration based on user role
        test_config = {
            'success': True,
            'mode': 'test' if test_mode else 'production',
            'allow_trace_input': trace_input_enabled,
            'user': {
                'username': session.get('username'),
                'role': user_role
            },
            'available_ports': {
                'quick': self.port_parser.get_quick_ports(),
                'common': list(self.port_parser.get_common_ports().keys()),
                'custom': 'Use custom port specification (e.g., 80,443,3306/tcp)'
            },
            'protocols': ['tcp', 'udp'],
            'limits': {
                'max_services': self.config.get('max_services', 10),
                'max_trace_hops': self.config.get('max_trace_hops', 30),
                'trace_timeout': self.config.get('trace_timeout', 60),
                'session_timeout': self.config.get('session_timeout', 3600)
            },
            'trace_options': {
                'allow_custom_trace': trace_input_enabled,  # Allow users to provide their own trace JSON
                'max_trace_length': 100000,
                'trace_input_help': 'Paste JSON trace data to use pre-recorded trace instead of executing live trace',
                'default_protocol': 'ICMP'
            },
            'features': {
                'realtime_progress': True,
                'pdf_export': True,
                'multi_service_test': True,
                'custom_source_port': user_role == 'admin'  # Only admins can set source port
            }
        }
        
        # Add recent tests if available
        recent_tests = []
        test_results = session.get('test_results', {})
        
        # Get last 5 tests
        for run_id, test_data in list(test_results.items())[-5:]:
            recent_tests.append({
                'run_id': run_id,
                'timestamp': test_data.get('timestamp', 0),
                'pdf_available': bool(test_data.get('data', {}).get('pdf_file'))
            })
        
        if recent_tests:
            test_config['recent_tests'] = recent_tests
        
        # Log config request
        self.logger.info(f"Test config requested by {session.get('username')} ({user_role})")
        
        return self.json_response(start_response, test_config)