#!/usr/bin/env -S python3 -B -u
"""Configuration management for web service"""
import json
import os
import secrets

class Config:
    DEFAULT_CONFIG = {
        "data_retention_days": 365,
        "session_timeout": 3600,
        "venv_path": "/home/sparavec/tsim-venv",
        "tsimsh_path": "tsimsh",
        "traceroute_simulator_path": "/var/www/traceroute-web/scripts",
        "traceroute_simulator_conf": "/var/www/traceroute-web/conf/traceroute_simulator.yaml",
        "traceroute_simulator_facts": "/var/local/tsim_facts",
        "traceroute_simulator_raw_facts": "/var/local/tsim_raw_facts",
        "log_level": "DEBUG",
        "secret_key": None,  # Generated on first run
        "controller_ip": "127.0.0.1",
        "registry_files": {
            "hosts": "/var/opt/traceroute-simulator/traceroute_hosts_registry.json",
            "routers": "/var/opt/traceroute-simulator/traceroute_routers_registry.json",
            "interfaces": "/var/opt/traceroute-simulator/traceroute_interfaces_registry.json",
            "bridges": "/var/opt/traceroute-simulator/traceroute_bridges_registry.json",
            "services": "/var/opt/traceroute-simulator/traceroute_services_registry.json"
        }
    }
    
    def __init__(self, config_file="/var/www/traceroute-web/conf/config.json"):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                config = json.load(f)
        else:
            config = self.DEFAULT_CONFIG.copy()
            # Generate secret key
            config['secret_key'] = secrets.token_hex(32)
            self.save_config(config)
        return config
    
    def save_config(self, config):
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True, mode=0o775)
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)