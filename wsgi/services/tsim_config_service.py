#!/usr/bin/env -S python3 -B -u
"""
TSIM Configuration Service
Manages application configuration from config.json
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from functools import lru_cache


class TsimConfigService:
    """Configuration service for TSIM application"""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration service
        
        Args:
            config_path: Optional path to config.json
        """
        self.logger = logging.getLogger('tsim.config')
        
        # Determine config file path
        if config_path:
            self.config_path = Path(config_path)
        else:
            # Look for config in order of preference
            web_root = os.environ.get('TSIM_WEB_ROOT', '/opt/tsim/wsgi')
            possible_paths = [
                Path(web_root) / 'conf' / 'config.json',
                Path('/opt/tsim/wsgi/conf/config.json'),
                Path(web_root) / 'config.json',  # Backward compatibility
                Path('/var/www/tsim/conf/config.json'),
                Path('./wsgi/conf/config.json'),  # For development
                Path('./wsgi/config.json')  # For development - backward compatibility
            ]
            
            for path in possible_paths:
                if path.exists():
                    self.config_path = path
                    break
            else:
                # Use default path even if it doesn't exist yet
                self.config_path = Path(web_root) / 'conf' / 'config.json'
        
        self.logger.info(f"Using config file: {self.config_path}")
        
        # Load configuration
        self.config = self._load_config()
        
        # Cache frequently accessed values
        self._cache_common_values()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file
        
        Returns:
            Configuration dictionary
        """
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                self.logger.info(f"Loaded configuration from {self.config_path}")
                return config
            except Exception as e:
                self.logger.error(f"Error loading config file: {e}")
        else:
            self.logger.warning(f"Config file not found at {self.config_path}, using defaults")
        
        # Return default configuration
        return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration
        
        Returns:
            Default configuration dictionary
        """
        return {
            'venv_path': '/opt/tsim/venv',
            'tsimsh_path': '/usr/local/bin/tsimsh',
            'tsim_raw_facts': os.environ.get('TRACEROUTE_SIMULATOR_RAW_FACTS', '/opt/tsim/raw_facts'),
            'data_dir': '/dev/shm/tsim/data',
            'log_dir': '/opt/tsim/logs',
            'session_dir': '/dev/shm/tsim',
            'secret_key': 'CHANGE_THIS_IN_PRODUCTION',
            'session_timeout': 3600,
            'max_services': 10,
            'max_trace_hops': 30,
            'trace_timeout': 60,
            'cleanup_age': 86400,
            'debug': False,
            'allowed_ips': [],  # Empty means allow all
            'blocked_ips': [],
            'matplotlib_cache': '/dev/shm/tsim/matplotlib_cache',
            'lock_dir': '/dev/shm/tsim/locks'
        }
    
    def _cache_common_values(self):
        """Cache commonly accessed configuration values"""
        self.venv_path = Path(self.get('venv_path', '/opt/tsim/venv'))
        self.tsimsh_path = self.get('tsimsh_path', '/usr/local/bin/tsimsh')
        self.data_dir = Path(self.get('data_dir', '/dev/shm/tsim/data'))
        self.log_dir = Path(self.get('log_dir', '/opt/tsim/logs'))
        self.session_dir = Path(self.get('session_dir', '/dev/shm/tsim'))
        # Environment variable takes precedence over config file
        self.raw_facts_dir = Path(
            os.environ.get('TRACEROUTE_SIMULATOR_RAW_FACTS') or 
            self.get('traceroute_simulator_raw_facts', '/opt/tsim/raw_facts')
        )
        self.secret_key = self.get('secret_key', 'CHANGE_THIS_IN_PRODUCTION')
        self.debug = self.get('debug', False)
        
        # Don't create directories here - let them be created on demand
        # by the processes that actually need them (running as www-data)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        # Support nested keys using dot notation
        if '.' in key:
            keys = key.split('.')
            value = self.config
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value
        
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set configuration value (in memory only)
        
        Args:
            key: Configuration key
            value: Configuration value
        """
        # Support nested keys using dot notation
        if '.' in key:
            keys = key.split('.')
            target = self.config
            for k in keys[:-1]:
                if k not in target:
                    target[k] = {}
                target = target[k]
            target[keys[-1]] = value
        else:
            self.config[key] = value
    
    def save(self) -> bool:
        """Save configuration to file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write config
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2, sort_keys=True)
            
            self.logger.info(f"Configuration saved to {self.config_path}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
            return False
    
    def reload(self):
        """Reload configuration from file"""
        self.config = self._load_config()
        self._cache_common_values()
        self.logger.info("Configuration reloaded")
    
    @lru_cache(maxsize=128)
    def is_ip_allowed(self, ip: str) -> bool:
        """Check if IP is allowed to access the service
        
        Args:
            ip: IP address to check
            
        Returns:
            True if allowed, False otherwise
        """
        # Check blocked IPs first
        blocked_ips = self.get('blocked_ips', [])
        if ip in blocked_ips:
            return False
        
        # Check allowed IPs
        allowed_ips = self.get('allowed_ips', [])
        if not allowed_ips:  # Empty means allow all
            return True
        
        return ip in allowed_ips
    
    def get_service_limits(self) -> Dict[str, Any]:
        """Get service limits configuration
        
        Returns:
            Dictionary of service limits
        """
        return {
            'max_services': self.get('max_services', 10),
            'max_trace_hops': self.get('max_trace_hops', 30),
            'trace_timeout': self.get('trace_timeout', 60),
            'session_timeout': self.get('session_timeout', 3600),
            'cleanup_age': self.get('cleanup_age', 86400),
            'max_pdf_size': self.get('max_pdf_size', 50 * 1024 * 1024),  # 50MB
            'max_upload_size': self.get('max_upload_size', 10 * 1024 * 1024),  # 10MB
        }
    
    def get_paths(self) -> Dict[str, Path]:
        """Get all configured paths
        
        Returns:
            Dictionary of paths
        """
        return {
            'venv': self.venv_path,
            'tsimsh': Path(self.tsimsh_path),
            'data': self.data_dir,
            'logs': self.log_dir,
            'sessions': self.session_dir,
            'raw_facts': self.raw_facts_dir,
            'traces': self.data_dir / 'traces',
            'results': self.data_dir / 'results',
            'progress': self.data_dir / 'progress',
            'pdfs': self.data_dir / 'pdfs',
        }
    
    def __repr__(self) -> str:
        """String representation"""
        return f"TsimConfigService(config_path={self.config_path})"