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
        'ansible_controller': False,
        'controller_ip': None
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
                
                # Update config with file values
                config.update(file_config)
                break
                
            except Exception:
                # Continue to next file if current one fails
                continue
    
    return config




def get_system_config() -> Dict[str, Any]:
    """
    Get system configuration settings.
    
    Returns:
        Dictionary with system configuration including:
        - unix_group: Group name for file ownership
        - file_permissions: Octal permissions for files
        - directory_permissions: Octal permissions for directories
    """
    config = load_traceroute_config()
    
    # Default system configuration
    defaults = {
        'unix_group': 'tsim-users',
        'file_permissions': '0664',
        'directory_permissions': '0775'
    }
    
    # Get system config from loaded configuration
    system_config = config.get('system', {})
    
    # Merge with defaults
    result = defaults.copy()
    result.update(system_config)
    
    return result


def get_unix_group() -> Optional[str]:
    """
    Get the configured Unix group for file ownership.
    
    Returns:
        Group name or None if not configured
    """
    system_config = get_system_config()
    return system_config.get('unix_group')


def get_logging_config() -> Dict[str, Any]:
    """
    Get logging configuration settings.
    
    Returns:
        Dictionary with logging configuration
    """
    config = load_traceroute_config()
    
    # Default logging configuration
    defaults = {
        'base_directory': '/var/log/tsim',
        'compress': True,
        'compression_format': 'xz',
        'compression_level': 9,
        'session_logs': {
            'network_setup': True,
            'host_operations': True,
            'service_manager': True
        }
    }
    
    # Get logging config from loaded configuration
    logging_config = config.get('logging', {})
    
    # Merge with defaults
    result = defaults.copy()
    result.update(logging_config)
    
    # Override with environment variable if set
    log_dir = os.environ.get('TRACEROUTE_SIMULATOR_LOGS')
    if log_dir:
        result['base_directory'] = log_dir
    
    return result


def get_shared_memory_config() -> Dict[str, Any]:
    """
    Get shared memory configuration settings.
    
    Returns:
        Dictionary with shared memory configuration
    """
    config = load_traceroute_config()
    
    # Default shared memory configuration
    defaults = {
        'registries': {
            'routers': {'size': 2097152, 'persist': True},
            'interfaces': {'size': 4194304, 'persist': True},
            'bridges': {'size': 2097152, 'persist': True},
            'hosts': {'size': 1048576, 'persist': True}
        },
        'batch_segments': {
            'max_size': 10485760,
            'cleanup_policy': 'manual'
        }
    }
    
    # Get shared memory config from loaded configuration
    shm_config = config.get('shared_memory', {})
    
    # Deep merge
    result = defaults.copy()
    if 'registries' in shm_config:
        result['registries'].update(shm_config['registries'])
    if 'batch_segments' in shm_config:
        result['batch_segments'].update(shm_config['batch_segments'])
    
    return result


def get_registry_paths() -> Dict[str, str]:
    """
    Get registry file paths in /dev/shm/tsim/.
    
    Returns:
        Dictionary with registry paths
    """
    # All registries are now in shared memory at /dev/shm/tsim/
    return {
        'routers': '/dev/shm/tsim/router_registry.json',
        'interfaces': '/dev/shm/tsim/interface_registry.json', 
        'bridges': '/dev/shm/tsim/bridge_registry.json',
        'hosts': '/dev/shm/tsim/host_registry.json',
        'services': '/dev/shm/tsim/services_registry.json'
    }


def get_network_setup_config() -> Dict[str, Any]:
    """
    Get network setup configuration settings.

    Returns:
        Dictionary with network setup configuration
    """
    config = load_traceroute_config()

    # Default network setup configuration
    defaults = {
        'hidden_namespace': 'tsim-hidden',
        'batch_processing': {
            'enabled': True,
            'parallel_limit': 50
        }
    }

    # Get network setup config from loaded configuration
    network_config = config.get('network_setup', {})

    # Deep merge
    result = defaults.copy()
    if 'batch_processing' in network_config:
        result['batch_processing'].update(network_config['batch_processing'])
    if 'hidden_namespace' in network_config:
        result['hidden_namespace'] = network_config['hidden_namespace']

    return result


def get_ssh_config() -> Dict[str, Any]:
    """
    Get SSH configuration settings for remote execution.

    Returns:
        Dictionary with SSH configuration including:
        - ssh_mode: 'user' or 'standard' mode
        - ssh_user: Username for SSH connections (user mode)
        - ssh_key: Path to SSH private key (user mode)
        - ssh_options: Dictionary of SSH options (user mode)
    """
    config = load_traceroute_config()

    # Default SSH configuration (standard mode by default)
    defaults = {
        'ssh_mode': 'standard',
        'ssh_user': None,
        'ssh_key': None,
        'ssh_options': {}
    }

    # Get SSH config from loaded configuration
    ssh_config = config.get('ssh', {})

    # Merge with defaults
    result = defaults.copy()
    result.update(ssh_config)

    return result


def get_ssh_controller_config() -> Dict[str, Any]:
    """
    Get SSH configuration settings for Ansible controller connections.
    Returns:
        Dictionary with SSH controller configuration including:
        - ssh_mode: 'user' or 'standard' mode
        - ssh_user: Username for SSH connections (user mode)
        - ssh_key: Path to SSH private key (user mode)
        - ssh_options: Dictionary of SSH options
    """
    config = load_traceroute_config()

    # Default SSH controller configuration (standard mode by default)
    defaults = {
        'ssh_mode': 'standard',
        'ssh_user': None,
        'ssh_key': None,
        'ssh_options': {
            'BatchMode': 'yes',
            'ConnectTimeout': '10',
            'StrictHostKeyChecking': 'yes',
            'UserKnownHostsFile': '~/.ssh/known_hosts'
        }
    }

    # Get SSH controller config from loaded configuration
    ssh_controller_config = config.get('ssh_controller', {})

    # Merge with defaults
    result = defaults.copy()
    result.update(ssh_controller_config)

    return result