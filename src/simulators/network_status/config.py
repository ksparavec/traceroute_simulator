#!/usr/bin/env -S python3 -B -u
"""
Configuration loader for network status module.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from tsim.simulators.network_status.exceptions import ConfigurationError


logger = logging.getLogger(__name__)


class NetworkStatusConfig:
    """Configuration manager for network status module."""
    
    DEFAULT_CONFIG = {
        'cache': {
            'enabled': True,
            'backend': 'shared_memory',
            'base_path': '/dev/shm/tsim/network_status_cache',
            'expiration_seconds': 3600,
            'max_size_mb': 100,
            'compression': False,
            'cleanup_interval': 7200
        },
        'parallelization': {
            'enabled': True,
            'max_workers': 20,
            'timeout_per_namespace': 5,
            'batch_size': 50
        },
        'collection': {
            'interfaces': True,
            'routes': True,
            'rules': True,
            'iptables': True,
            'ipsets': True
        },
        'formatting': {
            'translate_interface_names': True,
            'show_original_names': True,
            'json_indent': 2
        },
        'performance': {
            'use_json_commands': True,
            'cache_warmup': False,
            'stale_cache_timeout': 300
        }
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration.
        
        Args:
            config_path: Optional path to configuration file
        """
        self.config = self.DEFAULT_CONFIG.copy()
        self.config_path = config_path
        
        # Load configuration from file
        if config_path:
            self._load_from_file(config_path)
        else:
            self._load_from_standard_locations()
        
        # Apply environment variable overrides
        self._apply_env_overrides()
        
        logger.debug(f"Network status config loaded: cache={self.cache_enabled}, "
                    f"parallel={self.parallel_enabled}, workers={self.max_workers}")
    
    def _load_from_file(self, config_path: str):
        """Load configuration from specified file."""
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Config file not found: {config_path}")
            return
            
        try:
            with open(path, 'r') as f:
                full_config = yaml.safe_load(f)
                
            # Extract network_status section
            if 'network_status' in full_config:
                self._merge_config(full_config['network_status'])
                logger.info(f"Loaded network_status config from {config_path}")
                
        except (yaml.YAMLError, IOError) as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise ConfigurationError(f"Invalid configuration file: {e}")
    
    def _load_from_standard_locations(self):
        """Load configuration from standard locations."""
        # Configuration file precedence
        config_locations = []
        
        # 1. Environment variable
        if 'TRACEROUTE_SIMULATOR_CONF' in os.environ:
            config_locations.append(os.environ['TRACEROUTE_SIMULATOR_CONF'])
        
        # 2. User home directory
        home_config = Path.home() / 'traceroute_simulator.yaml'
        if home_config.exists():
            config_locations.append(str(home_config))
        
        # 3. Current directory
        local_config = Path('traceroute_simulator.yaml')
        if local_config.exists():
            config_locations.append(str(local_config))
        
        # 4. Installed location
        installed_config = Path('/opt/tsim/wsgi/conf/traceroute_simulator.yaml')
        if installed_config.exists():
            config_locations.append(str(installed_config))
        
        # Load from first available location
        for config_path in config_locations:
            try:
                self._load_from_file(config_path)
                self.config_path = config_path
                break
            except ConfigurationError:
                continue
    
    def _merge_config(self, new_config: Dict[str, Any]):
        """Recursively merge new configuration into existing."""
        def merge_dict(base: dict, update: dict):
            for key, value in update.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    merge_dict(base[key], value)
                else:
                    base[key] = value
        
        merge_dict(self.config, new_config)
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides."""
        env_mappings = {
            'TSIM_NETWORK_STATUS_CACHE_ENABLED': ('cache', 'enabled', self._parse_bool),
            'TSIM_NETWORK_STATUS_CACHE_PATH': ('cache', 'base_path', str),
            'TSIM_NETWORK_STATUS_CACHE_EXPIRATION': ('cache', 'expiration_seconds', int),
            'TSIM_NETWORK_STATUS_CACHE_BACKEND': ('cache', 'backend', str),
            'TSIM_NETWORK_STATUS_MAX_WORKERS': ('parallelization', 'max_workers', int),
            'TSIM_NETWORK_STATUS_TIMEOUT': ('parallelization', 'timeout_per_namespace', int),
            'TSIM_NETWORK_STATUS_PARALLEL_ENABLED': ('parallelization', 'enabled', self._parse_bool),
        }
        
        for env_var, (section, key, converter) in env_mappings.items():
            if env_var in os.environ:
                try:
                    value = converter(os.environ[env_var])
                    self.config[section][key] = value
                    logger.debug(f"Applied env override: {env_var} -> {section}.{key}={value}")
                except (ValueError, KeyError) as e:
                    logger.warning(f"Invalid env variable {env_var}: {e}")
    
    def _parse_bool(self, value: str) -> bool:
        """Parse boolean from string."""
        return value.lower() in ('true', '1', 'yes', 'on')
    
    # Convenience properties
    @property
    def cache_config(self) -> Dict[str, Any]:
        """Get cache configuration."""
        return self.config['cache']
    
    @property
    def cache_enabled(self) -> bool:
        """Check if cache is enabled."""
        return self.config['cache']['enabled']
    
    @property
    def cache_path(self) -> str:
        """Get cache base path."""
        return self.config['cache']['base_path']
    
    @property
    def cache_ttl(self) -> int:
        """Get cache TTL in seconds."""
        return self.config['cache']['expiration_seconds']
    
    @property
    def parallel_config(self) -> Dict[str, Any]:
        """Get parallelization configuration."""
        return self.config['parallelization']
    
    @property
    def parallel_enabled(self) -> bool:
        """Check if parallelization is enabled."""
        return self.config['parallelization']['enabled']
    
    @property
    def max_workers(self) -> int:
        """Get maximum number of worker threads."""
        return self.config['parallelization']['max_workers']
    
    @property
    def namespace_timeout(self) -> int:
        """Get timeout per namespace in seconds."""
        return self.config['parallelization']['timeout_per_namespace']
    
    @property
    def collection_config(self) -> Dict[str, bool]:
        """Get data collection configuration."""
        return self.config['collection']
    
    @property
    def formatting_config(self) -> Dict[str, Any]:
        """Get formatting configuration."""
        return self.config['formatting']
    
    @property
    def performance_config(self) -> Dict[str, Any]:
        """Get performance configuration."""
        return self.config['performance']
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation key.
        
        Args:
            key: Configuration key (e.g., 'cache.enabled')
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        parts = key.split('.')
        value = self.config
        
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
                
        return value