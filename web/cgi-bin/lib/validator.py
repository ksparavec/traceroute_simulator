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
    def validate_port_spec(port_spec):
        """Validate port specification with ranges and protocols
        
        Examples: 22/tcp, 80, 443/tcp, 1000-2000/udp, 53/tcp,53/udp
        """
        if not port_spec or not port_spec.strip():
            return False
            
        parts = [p.strip() for p in port_spec.split(',')]
        
        for part in parts:
            if not part:
                return False
                
            # Check if protocol is specified
            if '/' in part:
                port_part, protocol = part.rsplit('/', 1)
                if protocol.lower() not in ['tcp', 'udp']:
                    return False
            else:
                port_part = part
                
            # Check if it's a range
            if '-' in port_part:
                try:
                    start, end = port_part.split('-', 1)
                    start_port = int(start.strip())
                    end_port = int(end.strip())
                    
                    if not (1 <= start_port <= 65535):
                        return False
                    if not (1 <= end_port <= 65535):
                        return False
                    if start_port > end_port:
                        return False
                except:
                    return False
            else:
                # Single port
                try:
                    port = int(port_part.strip())
                    if not (1 <= port <= 65535):
                        return False
                except:
                    return False
                    
        return True
    
    @staticmethod
    def validate_protocol(protocol):
        return protocol in ['tcp', 'udp']
    
    @staticmethod
    def sanitize_input(value):
        # Remove any shell metacharacters except comma, dash, and forward slash (needed for port specs)
        # Allow: alphanumeric, comma, dash, forward slash, underscore, dot
        return re.sub(r'[;&|`$()<>\\\'"{}\[\]*?~]', '', value)