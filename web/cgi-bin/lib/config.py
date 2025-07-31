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
        "traceroute_simulator_path": "/home/sparavec/git/traceroute_simulator",
        "log_level": "DEBUG",
        "secret_key": None  # Generated on first run
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
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)