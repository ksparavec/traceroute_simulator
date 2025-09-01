#!/usr/bin/env -S python3 -B -u
"""
Get configured quick select services for the form
"""
import json
import os
import sys

# Add lib directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from config import Config

def main():
    # Load configuration
    config = Config()
    
    # Get the quick select services from config
    services = config.config.get('quick_select_services', [
        # Default services if not configured
        {"port": 22, "protocol": "tcp", "name": "SSH", "description": "Secure Shell"},
        {"port": 80, "protocol": "tcp", "name": "HTTP", "description": "Web Traffic"},
        {"port": 443, "protocol": "tcp", "name": "HTTPS", "description": "Secure Web"},
        {"port": 3389, "protocol": "tcp", "name": "RDP", "description": "Remote Desktop"}
    ])
    
    # Output JSON response
    print("Content-Type: application/json")
    print()
    print(json.dumps({"services": services}))

if __name__ == "__main__":
    main()