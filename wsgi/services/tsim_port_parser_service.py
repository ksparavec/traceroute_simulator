#!/usr/bin/env -S python3 -B -u
"""
TSIM Port Parser Service
Parses port specifications for network testing
"""

import re
import logging
from typing import List, Tuple, Optional, Dict, Any


class TsimPortParserService:
    """Port specification parser service"""
    
    def __init__(self):
        """Initialize port parser service"""
        self.logger = logging.getLogger('tsim.port_parser')
        
        # Common port definitions
        self.common_ports = {
            'ftp': (21, 'tcp'),
            'ssh': (22, 'tcp'),
            'telnet': (23, 'tcp'),
            'smtp': (25, 'tcp'),
            'dns': (53, 'udp'),
            'http': (80, 'tcp'),
            'pop3': (110, 'tcp'),
            'imap': (143, 'tcp'),
            'https': (443, 'tcp'),
            'smb': (445, 'tcp'),
            'mysql': (3306, 'tcp'),
            'rdp': (3389, 'tcp'),
            'postgresql': (5432, 'tcp'),
            'http-alt': (8080, 'tcp'),
            'https-alt': (8443, 'tcp'),
        }
        
        # Quick test ports
        self.quick_ports = [
            '22/tcp',   # SSH
            '80/tcp',   # HTTP
            '443/tcp',  # HTTPS
            '3306/tcp', # MySQL
            '5432/tcp', # PostgreSQL
        ]
        
        # Pre-compile regex patterns
        self.port_spec_pattern = re.compile(r'^(\d+)(?:/([a-z]+))?$')
        self.port_range_pattern = re.compile(r'^(\d+)-(\d+)(?:/([a-z]+))?$')
        self.service_pattern = re.compile(r'^([a-z]+[a-z0-9-]*)$')
    
    def parse_port_spec(self, port_spec: str, default_protocol: str = 'tcp',
                       max_services: int = 10) -> List[Tuple[int, str]]:
        """Parse port specification string
        
        Args:
            port_spec: Port specification (e.g., "80,443/tcp,22-25,ssh")
            default_protocol: Default protocol if not specified
            max_services: Maximum number of services allowed
            
        Returns:
            List of (port, protocol) tuples
            
        Raises:
            ValueError: If specification is invalid
        """
        if not port_spec:
            raise ValueError("Port specification cannot be empty")
        
        # Ensure default protocol is valid
        if default_protocol not in ['tcp', 'udp']:
            default_protocol = 'tcp'
        
        # Split by comma
        specs = [s.strip() for s in port_spec.split(',')]
        
        if len(specs) > max_services:
            raise ValueError(f"Too many services specified (maximum {max_services})")
        
        result = []
        
        for spec in specs:
            if not spec:
                continue
            
            # Try to parse as single port or port/protocol
            match = self.port_spec_pattern.match(spec)
            if match:
                port = int(match.group(1))
                protocol = match.group(2) or default_protocol
                
                if not self._validate_port(port):
                    raise ValueError(f"Invalid port number: {port}")
                if not self._validate_protocol(protocol):
                    raise ValueError(f"Invalid protocol: {protocol}")
                
                result.append((port, protocol))
                continue
            
            # Try to parse as port range
            match = self.port_range_pattern.match(spec)
            if match:
                start_port = int(match.group(1))
                end_port = int(match.group(2))
                protocol = match.group(3) or default_protocol
                
                if not self._validate_port(start_port) or not self._validate_port(end_port):
                    raise ValueError(f"Invalid port range: {start_port}-{end_port}")
                if start_port > end_port:
                    raise ValueError(f"Invalid port range: start > end")
                if end_port - start_port > 100:
                    raise ValueError(f"Port range too large (maximum 100 ports)")
                if not self._validate_protocol(protocol):
                    raise ValueError(f"Invalid protocol: {protocol}")
                
                # Add all ports in range
                for port in range(start_port, end_port + 1):
                    result.append((port, protocol))
                continue
            
            # Try to parse as service name
            match = self.service_pattern.match(spec.lower())
            if match:
                service = match.group(1)
                if service in self.common_ports:
                    port, protocol = self.common_ports[service]
                    result.append((port, protocol))
                    continue
                else:
                    raise ValueError(f"Unknown service: {service}")
            
            # If we get here, the specification is invalid
            raise ValueError(f"Invalid port specification: {spec}")
        
        if not result:
            raise ValueError("No valid ports found in specification")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_result = []
        for item in result:
            if item not in seen:
                seen.add(item)
                unique_result.append(item)
        
        # Check final count
        if len(unique_result) > max_services:
            raise ValueError(f"Too many services after expansion (maximum {max_services})")
        
        return unique_result
    
    def format_port_list(self, ports: List[Tuple[int, str]]) -> str:
        """Format port list for display
        
        Args:
            ports: List of (port, protocol) tuples
            
        Returns:
            Formatted string
        """
        if not ports:
            return "none"
        
        formatted = []
        for port, protocol in ports:
            # Look up service name if known
            service_name = self._get_service_name(port, protocol)
            if service_name:
                formatted.append(f"{port}/{protocol} ({service_name})")
            else:
                formatted.append(f"{port}/{protocol}")
        
        return ", ".join(formatted)
    
    def get_quick_ports(self) -> List[str]:
        """Get list of quick test ports
        
        Returns:
            List of port specifications
        """
        return self.quick_ports.copy()
    
    def get_common_ports(self) -> Dict[str, Tuple[int, str]]:
        """Get dictionary of common ports
        
        Returns:
            Dictionary mapping service names to (port, protocol) tuples
        """
        return self.common_ports.copy()
    
    def parse_port_protocol_string(self, port_str: str) -> Tuple[int, str]:
        """Parse a single port/protocol string
        
        Args:
            port_str: Port string (e.g., "80", "443/tcp", "53/udp")
            
        Returns:
            Tuple of (port, protocol)
            
        Raises:
            ValueError: If format is invalid
        """
        match = self.port_spec_pattern.match(port_str)
        if not match:
            raise ValueError(f"Invalid port format: {port_str}")
        
        port = int(match.group(1))
        protocol = match.group(2) or 'tcp'
        
        if not self._validate_port(port):
            raise ValueError(f"Invalid port number: {port}")
        if not self._validate_protocol(protocol):
            raise ValueError(f"Invalid protocol: {protocol}")
        
        return port, protocol
    
    def _validate_port(self, port: int) -> bool:
        """Validate port number
        
        Args:
            port: Port number
            
        Returns:
            True if valid, False otherwise
        """
        return 1 <= port <= 65535
    
    def _validate_protocol(self, protocol: str) -> bool:
        """Validate protocol
        
        Args:
            protocol: Protocol string
            
        Returns:
            True if valid, False otherwise
        """
        return protocol.lower() in ['tcp', 'udp']
    
    def _get_service_name(self, port: int, protocol: str) -> Optional[str]:
        """Get service name for a port/protocol combination
        
        Args:
            port: Port number
            protocol: Protocol
            
        Returns:
            Service name or None
        """
        for service, (p, proto) in self.common_ports.items():
            if p == port and proto == protocol:
                return service
        return None
    
    def expand_service_names(self, services: List[str], 
                           default_protocol: str = 'tcp') -> List[Tuple[int, str]]:
        """Expand service names to port/protocol tuples
        
        Args:
            services: List of service names
            default_protocol: Default protocol
            
        Returns:
            List of (port, protocol) tuples
            
        Raises:
            ValueError: If service is unknown
        """
        result = []
        
        for service in services:
            service_lower = service.lower()
            if service_lower in self.common_ports:
                port, protocol = self.common_ports[service_lower]
                result.append((port, protocol))
            else:
                # Try to parse as port number
                try:
                    port = int(service)
                    if self._validate_port(port):
                        result.append((port, default_protocol))
                    else:
                        raise ValueError(f"Invalid port number: {port}")
                except ValueError:
                    raise ValueError(f"Unknown service: {service}")
        
        return result
    
    def group_by_protocol(self, ports: List[Tuple[int, str]]) -> Dict[str, List[int]]:
        """Group ports by protocol
        
        Args:
            ports: List of (port, protocol) tuples
            
        Returns:
            Dictionary mapping protocol to list of ports
        """
        grouped = {}
        for port, protocol in ports:
            if protocol not in grouped:
                grouped[protocol] = []
            grouped[protocol].append(port)
        
        # Sort port lists
        for protocol in grouped:
            grouped[protocol].sort()
        
        return grouped