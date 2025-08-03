#!/usr/bin/env -S python3 -B -u
"""
Configuration loader for traceroute simulator.

Provides centralized configuration loading for all components.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


def load_traceroute_config() -> Dict[str, Any]:
    """
    Load traceroute simulator configuration with proper precedence.
    
    Configuration file location precedence:
    1. Environment variable TRACEROUTE_SIMULATOR_CONF (if set)
    2. ~/traceroute_simulator.yaml (user's home directory)
    3. ./traceroute_simulator.yaml (current directory)
    
    Returns:
        Dictionary containing configuration values
    """
    # Default configuration
    defaults = {
        'tsim_facts': os.environ.get('TRACEROUTE_SIMULATOR_FACTS', 'tsim_facts'),
        'verbose': False,
        'verbose_level': 1,
        'quiet': False,
        'json_output': False,
        'enable_mtr_fallback': True,
        'enable_reverse_trace': True,
        'force_forward_trace': False,
        'software_simulation_only': False,
        'controller_ip': None,
        'registry_files': {
            'hosts': '/var/opt/traceroute-simulator/traceroute_hosts_registry.json',
            'routers': '/var/opt/traceroute-simulator/traceroute_routers_registry.json',
            'interfaces': '/var/opt/traceroute-simulator/traceroute_interfaces_registry.json',
            'bridges': '/var/opt/traceroute-simulator/traceroute_bridges_registry.json',
            'services': '/var/opt/traceroute-simulator/traceroute_services_registry.json'
        }
    }
    
    # Configuration file locations in order of precedence
    config_files = []
    
    # Check environment variable first
    env_config = os.environ.get('TRACEROUTE_SIMULATOR_CONF')
    if env_config:
        config_files.append(Path(env_config))
    
    # Add default locations
    config_files.extend([
        Path.home() / 'traceroute_simulator.yaml',
        Path('./traceroute_simulator.yaml')
    ])
    
    # Try to load configuration from the first available file
    config = defaults.copy()
    
    for config_file in config_files:
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    file_config = yaml.safe_load(f) or {}
                    
                # Deep merge registry_files if present
                if 'registry_files' in file_config and 'registry_files' in config:
                    registry_files = config['registry_files'].copy()
                    registry_files.update(file_config.get('registry_files', {}))
                    file_config['registry_files'] = registry_files
                
                # Update config with file values
                config.update(file_config)
                break
                
            except Exception:
                # Continue to next file if current one fails
                continue
    
    return config


def get_registry_paths() -> Dict[str, str]:
    """
    Get registry file paths from configuration.
    
    Returns:
        Dictionary with keys: 'hosts', 'routers', 'interfaces', 'bridges', 'services'
    """
    config = load_traceroute_config()
    return config.get('registry_files', {
        'hosts': '/var/opt/traceroute-simulator/traceroute_hosts_registry.json',
        'routers': '/var/opt/traceroute-simulator/traceroute_routers_registry.json',
        'interfaces': '/var/opt/traceroute-simulator/traceroute_interfaces_registry.json',
        'bridges': '/var/opt/traceroute-simulator/traceroute_bridges_registry.json',
        'services': '/var/opt/traceroute-simulator/traceroute_services_registry.json'
    })


def get_registry_path(registry_type: str) -> Optional[str]:
    """
    Get a specific registry file path.
    
    Args:
        registry_type: One of 'hosts', 'routers', 'interfaces', 'bridges', 'services'
        
    Returns:
        Path to the registry file, or None if not found
    """
    paths = get_registry_paths()
    return paths.get(registry_type)