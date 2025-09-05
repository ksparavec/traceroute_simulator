#!/usr/bin/env -S python3 -B -u
"""
TSIM Services Config Handler
Returns available services configuration
"""

import logging
from typing import Dict, Any, List
from .tsim_base_handler import TsimBaseHandler
from services.tsim_port_parser_service import TsimPortParserService


class TsimServicesConfigHandler(TsimBaseHandler):
    """Handler for services configuration requests"""
    
    def __init__(self, config_service, logger_service):
        """Initialize services config handler
        
        Args:
            config_service: TsimConfigService instance
            logger_service: TsimLoggerService instance
        """
        super().__init__(None, logger_service)  # No session manager needed
        self.config = config_service
        self.port_parser = TsimPortParserService()
        self.logger = logging.getLogger('tsim.handler.services_config')
    
    def handle(self, environ: Dict[str, Any], start_response) -> List[bytes]:
        """Handle services configuration request
        
        Args:
            environ: WSGI environment
            start_response: WSGI start_response callable
            
        Returns:
            Response body
        """
        # This endpoint doesn't require authentication - it's public config
        
        # Get services from config.json
        services = self.config.get('quick_select_services', [])
        
        # Ensure each service has required fields
        for service in services:
            if 'display' not in service:
                # Create display field if not present
                service['display'] = f"{service.get('name', 'Unknown')} ({service.get('port', 0)}/{service.get('protocol', 'tcp')})"
        
        # Get quick test ports
        quick_ports = self.port_parser.get_quick_ports()
        
        # Build response
        config = {
            'success': True,
            'services': services,
            'quick_ports': quick_ports,
            'port_modes': [
                {
                    'value': 'quick',
                    'label': 'Quick Test (5 common ports)',
                    'description': 'Test the most commonly used services'
                },
                {
                    'value': 'common',
                    'label': 'Common Services',
                    'description': 'Select from predefined common services'
                },
                {
                    'value': 'custom',
                    'label': 'Custom Ports',
                    'description': 'Specify custom ports (e.g., 80,443,3306/tcp)'
                }
            ],
            'protocols': ['tcp', 'udp'],
            'limits': {
                'max_services': self.config.get('max_services', 10),
                'max_trace_hops': self.config.get('max_trace_hops', 30),
                'trace_timeout': self.config.get('trace_timeout', 60)
            }
        }
        
        return self.json_response(start_response, config)