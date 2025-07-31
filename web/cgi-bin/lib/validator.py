#!/usr/bin/env -S python3 -B -u
"""Input validation for web service"""
import re
import ipaddress

class InputValidator:
    @staticmethod
    def validate_ip(ip_str):
        try:
            ipaddress.ip_address(ip_str)
            return True
        except:
            return False
    
    @staticmethod
    def validate_port(port_str):
        try:
            port = int(port_str)
            return 1 <= port <= 65535
        except:
            return False
    
    @staticmethod
    def validate_protocol(protocol):
        return protocol in ['tcp', 'udp']
    
    @staticmethod
    def sanitize_input(value):
        # Remove any shell metacharacters
        return re.sub(r'[;&|`$()<>\\\'"{}[\]*?~]', '', value)