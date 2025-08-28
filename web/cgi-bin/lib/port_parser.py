#!/usr/bin/env -S python3 -B -u
"""Port specification parser for handling ranges and comma-separated lists"""
import re
from typing import List, Tuple, Optional, Dict

class PortParser:
    """Parse port specifications with protocol support
    
    Supports:
    - Single ports: "80", "22/tcp", "53/udp"
    - Port ranges: "8000-8010", "2000-2010/udp"
    - Comma-separated lists: "22/tcp,80,443/tcp,53/udp"
    - Mixed: "22/tcp,80-90,443/tcp,1000-2000/udp"
    """
    
    def __init__(self):
        self.services_cache = None
        
    def count_services(self, port_protocol_list: List[Tuple[int, str]]) -> int:
        """Count the total number of services in the port/protocol list
        
        Args:
            port_protocol_list: List of (port, protocol) tuples
            
        Returns:
            Total count of services
        """
        return len(port_protocol_list)
    
    def parse_port_spec(self, port_spec: str, default_protocol: str = 'tcp', max_services: int = None) -> List[Tuple[int, str]]:
        """Parse port specification string into list of (port, protocol) tuples
        
        Args:
            port_spec: Port specification string
            default_protocol: Default protocol when not specified (tcp/udp)
            max_services: Maximum number of services allowed (optional)
            
        Returns:
            List of (port, protocol) tuples
            
        Raises:
            ValueError: If port specification is invalid or exceeds max_services
        """
        if not port_spec or not port_spec.strip():
            raise ValueError("Empty port specification")
            
        results = []
        port_spec = port_spec.strip()
        
        # Split by comma for multiple specifications
        parts = [p.strip() for p in port_spec.split(',')]
        
        for part in parts:
            if not part:
                continue
                
            # Check if protocol is specified
            protocol = default_protocol
            if '/' in part:
                port_part, protocol = part.rsplit('/', 1)
                protocol = protocol.lower()
                if protocol not in ['tcp', 'udp']:
                    raise ValueError(f"Invalid protocol: {protocol}")
            else:
                port_part = part
                
            # Check if it's a range
            if '-' in port_part:
                # Handle range
                try:
                    start, end = port_part.split('-', 1)
                    start_port = int(start.strip())
                    end_port = int(end.strip())
                    
                    if start_port < 1 or start_port > 65535:
                        raise ValueError(f"Invalid port number: {start_port}")
                    if end_port < 1 or end_port > 65535:
                        raise ValueError(f"Invalid port number: {end_port}")
                    if start_port > end_port:
                        raise ValueError(f"Invalid range: {start_port}-{end_port}")
                        
                    for port in range(start_port, end_port + 1):
                        results.append((port, protocol))
                        
                except (ValueError, TypeError) as e:
                    if "Invalid" in str(e):
                        raise
                    raise ValueError(f"Invalid port range: {port_part}")
            else:
                # Single port
                try:
                    port = int(port_part.strip())
                    if port < 1 or port > 65535:
                        raise ValueError(f"Invalid port number: {port}")
                    results.append((port, protocol))
                except ValueError:
                    raise ValueError(f"Invalid port number: {port_part}")
                    
        if not results:
            raise ValueError("No valid ports specified")
            
        # Remove duplicates while preserving order
        seen = set()
        unique_results = []
        for item in results:
            if item not in seen:
                seen.add(item)
                unique_results.append(item)
        
        # Check if max_services limit is exceeded
        if max_services is not None and len(unique_results) > max_services:
            raise ValueError(f"Too many services specified ({len(unique_results)}). Maximum allowed is {max_services}")
                
        return unique_results
    
    def load_services(self, services_file: str = '/etc/services') -> Dict[Tuple[int, str], str]:
        """Load service descriptions from /etc/services
        
        Returns:
            Dictionary mapping (port, protocol) to service name/description
        """
        if self.services_cache is not None:
            return self.services_cache
            
        services = {}
        try:
            with open(services_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                        
                    # Parse service line: name port/protocol [aliases...] [# comment]
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                        
                    service_name = parts[0]
                    port_proto = parts[1]
                    
                    if '/' not in port_proto:
                        continue
                        
                    try:
                        port_str, protocol = port_proto.split('/', 1)
                        port = int(port_str)
                        protocol = protocol.lower()
                        
                        if protocol in ['tcp', 'udp']:
                            # Extract comment if present
                            comment_idx = line.find('#')
                            if comment_idx > 0:
                                description = line[comment_idx+1:].strip()
                                services[(port, protocol)] = f"{service_name} - {description}"
                            else:
                                services[(port, protocol)] = service_name
                    except (ValueError, TypeError):
                        continue
                        
        except (IOError, OSError):
            # If /etc/services is not available, provide common defaults
            services = {
                (22, 'tcp'): 'ssh - Secure Shell',
                (23, 'tcp'): 'telnet - Telnet',
                (25, 'tcp'): 'smtp - Simple Mail Transfer',
                (53, 'tcp'): 'domain - Domain Name Server',
                (53, 'udp'): 'domain - Domain Name Server',
                (80, 'tcp'): 'http - World Wide Web HTTP',
                (110, 'tcp'): 'pop3 - Post Office Protocol v3',
                (143, 'tcp'): 'imap - Internet Message Access Protocol',
                (443, 'tcp'): 'https - HTTP over TLS/SSL',
                (445, 'tcp'): 'microsoft-ds - Microsoft-DS',
                (3306, 'tcp'): 'mysql - MySQL Database',
                (3389, 'tcp'): 'ms-wbt-server - MS WBT Server (RDP)',
                (5432, 'tcp'): 'postgresql - PostgreSQL Database',
                (8080, 'tcp'): 'http-alt - HTTP Alternate',
                (8443, 'tcp'): 'https-alt - HTTPS Alternate',
            }
            
        self.services_cache = services
        return services
    
    def get_service_description(self, port: int, protocol: str) -> str:
        """Get service description for a port/protocol combination
        
        Args:
            port: Port number
            protocol: Protocol (tcp/udp)
            
        Returns:
            Service description or generic string
        """
        services = self.load_services()
        key = (port, protocol.lower())
        return services.get(key, f"Port {port}/{protocol}")
    
    def get_common_services(self, limit: int = 50) -> List[Dict[str, any]]:
        """Get list of common services for UI dropdown
        
        Returns:
            List of service dictionaries with port, protocol, and description
        """
        common_ports = [
            (22, 'tcp'), (23, 'tcp'), (25, 'tcp'), (53, 'tcp'), (53, 'udp'),
            (80, 'tcp'), (110, 'tcp'), (143, 'tcp'), (443, 'tcp'), (445, 'tcp'),
            (465, 'tcp'), (587, 'tcp'), (993, 'tcp'), (995, 'tcp'), (1433, 'tcp'),
            (1521, 'tcp'), (3306, 'tcp'), (3389, 'tcp'), (5432, 'tcp'), (5900, 'tcp'),
            (8080, 'tcp'), (8443, 'tcp'), (27017, 'tcp'),
            # Common UDP services
            (69, 'udp'), (123, 'udp'), (161, 'udp'), (162, 'udp'), (514, 'udp'),
            (1194, 'udp'), (4500, 'udp'), (5060, 'udp')
        ]
        
        services = self.load_services()
        result = []
        
        for port, protocol in common_ports[:limit]:
            description = services.get((port, protocol), f"Port {port}/{protocol}")
            result.append({
                'port': port,
                'protocol': protocol,
                'description': description,
                'value': f"{port}/{protocol}"
            })
            
        return result
    
    def format_port_list(self, ports: List[Tuple[int, str]]) -> str:
        """Format list of ports for display
        
        Args:
            ports: List of (port, protocol) tuples
            
        Returns:
            Formatted string representation
        """
        if not ports:
            return ""
            
        # Group consecutive ports with same protocol
        formatted = []
        current_range = []
        current_protocol = None
        
        for port, protocol in sorted(ports):
            if current_protocol == protocol and current_range:
                if port == current_range[-1] + 1:
                    current_range.append(port)
                else:
                    # End current range
                    if len(current_range) > 2:
                        formatted.append(f"{current_range[0]}-{current_range[-1]}/{current_protocol}")
                    else:
                        for p in current_range:
                            formatted.append(f"{p}/{current_protocol}")
                    current_range = [port]
            else:
                # Finish previous range
                if current_range:
                    if len(current_range) > 2:
                        formatted.append(f"{current_range[0]}-{current_range[-1]}/{current_protocol}")
                    else:
                        for p in current_range:
                            formatted.append(f"{p}/{current_protocol}")
                # Start new range
                current_range = [port]
                current_protocol = protocol
                
        # Handle final range
        if current_range:
            if len(current_range) > 2:
                formatted.append(f"{current_range[0]}-{current_range[-1]}/{current_protocol}")
            else:
                for p in current_range:
                    formatted.append(f"{p}/{current_protocol}")
                    
        return ','.join(formatted)