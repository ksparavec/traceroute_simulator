#!/usr/bin/env -S python3 -B -u
"""
TSIM Validator Service
Input validation for the application
"""

import re
import logging
from typing import Any, Optional, Tuple, List
from functools import lru_cache


class TsimValidatorService:
    """Input validation service"""
    
    def __init__(self):
        """Initialize validator service"""
        self.logger = logging.getLogger('tsim.validator')
        
        # Pre-compile regex patterns for performance
        self.ip_pattern = re.compile(r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$')
        self.port_pattern = re.compile(r'^([0-9]{1,5})(?:/([a-z]+))?$')
        self.hostname_pattern = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$')
        self.username_pattern = re.compile(r'^[a-zA-Z0-9_-]{3,32}$')
        self.uuid_pattern = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
        self.safe_filename_pattern = re.compile(r'^[a-zA-Z0-9_\-\.]+$')
    
    @lru_cache(maxsize=1024)
    def validate_ip(self, ip: str) -> bool:
        """Validate IP address
        
        Args:
            ip: IP address string
            
        Returns:
            True if valid, False otherwise
        """
        if not ip:
            return False
        
        # Check format
        if not self.ip_pattern.match(ip):
            return False
        
        # Additional validation - check for reserved ranges if needed
        parts = ip.split('.')
        first_octet = int(parts[0])
        
        # Reject 0.0.0.0 and 255.255.255.255
        if ip in ['0.0.0.0', '255.255.255.255']:
            return False
        
        # Reject multicast (224.0.0.0 to 239.255.255.255)
        if 224 <= first_octet <= 239:
            self.logger.warning(f"Rejected multicast IP: {ip}")
            return False
        
        return True
    
    def validate_port(self, port: Any, allow_range: bool = False) -> Tuple[bool, Optional[str]]:
        """Validate port number or port specification
        
        Args:
            port: Port number or specification (e.g., "80", "80/tcp", "80-90")
            allow_range: Whether to allow port ranges
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if port is None:
            return False, "Port is required"
        
        # Convert to string if integer
        port_str = str(port)
        
        # Check for port range if allowed
        if allow_range and '-' in port_str:
            try:
                start, end = port_str.split('-')
                start_port = int(start)
                end_port = int(end)
                
                if start_port < 1 or start_port > 65535:
                    return False, f"Invalid start port: {start_port}"
                if end_port < 1 or end_port > 65535:
                    return False, f"Invalid end port: {end_port}"
                if start_port > end_port:
                    return False, "Start port must be less than end port"
                
                return True, None
            except ValueError:
                return False, "Invalid port range format"
        
        # Check single port or port/protocol
        match = self.port_pattern.match(port_str)
        if not match:
            return False, "Invalid port format"
        
        port_num = int(match.group(1))
        protocol = match.group(2)
        
        # Validate port number
        if port_num < 1 or port_num > 65535:
            return False, f"Port must be between 1 and 65535"
        
        # Validate protocol if specified
        if protocol and protocol not in ['tcp', 'udp']:
            return False, f"Invalid protocol: {protocol}"
        
        return True, None
    
    def validate_port_list(self, ports: str, max_ports: int = 10) -> Tuple[bool, Optional[str], Optional[List[str]]]:
        """Validate a comma-separated list of ports
        
        Args:
            ports: Comma-separated port specifications
            max_ports: Maximum number of ports allowed
            
        Returns:
            Tuple of (is_valid, error_message, parsed_ports)
        """
        if not ports:
            return False, "No ports specified", None
        
        # Split by comma and strip whitespace
        port_list = [p.strip() for p in ports.split(',')]
        
        # Check maximum number
        if len(port_list) > max_ports:
            return False, f"Too many ports (maximum {max_ports})", None
        
        # Validate each port
        validated_ports = []
        for port_spec in port_list:
            if not port_spec:
                continue
            
            is_valid, error = self.validate_port(port_spec, allow_range=False)
            if not is_valid:
                return False, f"Invalid port '{port_spec}': {error}", None
            
            validated_ports.append(port_spec)
        
        if not validated_ports:
            return False, "No valid ports found", None
        
        return True, None, validated_ports
    
    def validate_hostname(self, hostname: str) -> bool:
        """Validate hostname
        
        Args:
            hostname: Hostname string
            
        Returns:
            True if valid, False otherwise
        """
        if not hostname:
            return False
        
        # Check length
        if len(hostname) > 253:
            return False
        
        # Check format
        return bool(self.hostname_pattern.match(hostname))
    
    def validate_username(self, username: str) -> Tuple[bool, Optional[str]]:
        """Validate username
        
        Args:
            username: Username string
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not username:
            return False, "Username is required"
        
        if not self.username_pattern.match(username):
            return False, "Username must be 3-32 characters, alphanumeric, dash, or underscore only"
        
        return True, None
    
    def validate_password(self, password: str, min_length: int = 8) -> Tuple[bool, Optional[str]]:
        """Validate password
        
        Args:
            password: Password string
            min_length: Minimum password length
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not password:
            return False, "Password is required"
        
        if len(password) < min_length:
            return False, f"Password must be at least {min_length} characters"
        
        # Check for basic complexity (optional, can be made configurable)
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        
        # Uncomment for stronger requirements
        # if not (has_upper and has_lower and has_digit):
        #     return False, "Password must contain uppercase, lowercase, and numbers"
        
        return True, None
    
    def validate_uuid(self, uuid_str: str) -> bool:
        """Validate UUID format
        
        Args:
            uuid_str: UUID string
            
        Returns:
            True if valid, False otherwise
        """
        if not uuid_str:
            return False
        
        return bool(self.uuid_pattern.match(uuid_str.lower()))
    
    def validate_trace_data(self, trace_data: str, max_length: int = 100000) -> Tuple[bool, Optional[str]]:
        """Validate user trace data in complex format
        
        Args:
            trace_data: User-provided trace data JSON
            max_length: Maximum allowed length
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not trace_data:
            return True, None  # Empty is valid
        
        # Check length
        if len(trace_data) > max_length:
            return False, f"Trace data too long (maximum {max_length} characters)"
        
        # Try to parse as JSON
        try:
            import json
            data = json.loads(trace_data)
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON format: {str(e)}"
        
        # Validate structure
        if not isinstance(data, dict):
            return False, "Trace data must be a JSON object"
        
        # Required fields
        required_fields = ['source', 'destination', 'path']
        for field in required_fields:
            if field not in data:
                return False, f"Missing required field: {field}"
        
        # Validate IPs
        if not self.validate_ip(data['source']):
            return False, f"Invalid source IP: {data['source']}"
        if not self.validate_ip(data['destination']):
            return False, f"Invalid destination IP: {data['destination']}"
        
        # Validate path
        if not isinstance(data.get('path'), list):
            return False, "Path must be an array"
        
        if len(data['path']) == 0:
            return False, "Path cannot be empty"
        
        # Validate each hop
        for i, hop in enumerate(data['path']):
            if not isinstance(hop, dict):
                return False, f"Hop {i+1} must be an object"
            
            # Required hop fields
            if 'hop' not in hop or 'ip' not in hop:
                return False, f"Hop {i+1} missing required fields (hop, ip)"
            
            # Validate hop number
            if not isinstance(hop['hop'], int) or hop['hop'] < 1:
                return False, f"Hop {i+1} has invalid hop number"
            
            # Validate IP
            if not self.validate_ip(hop['ip']):
                return False, f"Hop {i+1} has invalid IP: {hop['ip']}"
            
            # Validate optional fields
            if 'is_router' in hop and not isinstance(hop['is_router'], bool):
                return False, f"Hop {i+1} 'is_router' must be boolean"
            
            if 'rtt' in hop and not isinstance(hop['rtt'], (int, float)):
                return False, f"Hop {i+1} 'rtt' must be a number"
            
            # Check string fields for dangerous content
            string_fields = ['name', 'incoming', 'outgoing', 'prev_hop', 'next_hop']
            dangerous_patterns = [r'<script', r'javascript:', r'on\w+\s*=']
            
            for field in string_fields:
                if field in hop and isinstance(hop[field], str):
                    value_lower = hop[field].lower()
                    for pattern in dangerous_patterns:
                        if re.search(pattern, value_lower):
                            return False, f"Hop {i+1} field '{field}' contains dangerous content"
        
        return True, None
    
    def validate_filename(self, filename: str) -> Tuple[bool, Optional[str]]:
        """Validate filename
        
        Args:
            filename: Filename string
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not filename:
            return False, "Filename is required"
        
        # Check length
        if len(filename) > 255:
            return False, "Filename too long"
        
        # Check for directory traversal attempts
        if '..' in filename or '/' in filename or '\\' in filename:
            return False, "Invalid filename - directory traversal not allowed"
        
        # Check for safe characters
        if not self.safe_filename_pattern.match(filename):
            return False, "Filename contains invalid characters"
        
        return True, None
    
    def sanitize_string(self, input_str: str, max_length: int = 1000) -> str:
        """Sanitize a string for safe output
        
        Args:
            input_str: Input string
            max_length: Maximum allowed length
            
        Returns:
            Sanitized string
        """
        if not input_str:
            return ""
        
        # Truncate to max length
        sanitized = input_str[:max_length]
        
        # Remove control characters except newline and tab
        sanitized = ''.join(char for char in sanitized 
                          if char == '\n' or char == '\t' or 
                          (ord(char) >= 32 and ord(char) < 127))
        
        # HTML escape if needed (for web output)
        # This could be made optional based on context
        html_entities = {
            '<': '&lt;',
            '>': '&gt;',
            '&': '&amp;',
            '"': '&quot;',
            "'": '&#x27;'
        }
        
        for char, entity in html_entities.items():
            sanitized = sanitized.replace(char, entity)
        
        return sanitized
    
    def validate_request_size(self, content_length: int, max_size: int = 10485760) -> Tuple[bool, Optional[str]]:
        """Validate request content length
        
        Args:
            content_length: Content-Length header value
            max_size: Maximum allowed size in bytes (default 10MB)
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if content_length > max_size:
            return False, f"Request too large (maximum {max_size} bytes)"
        
        return True, None