#!/usr/bin/env -S python3 -B -u
"""
Dynamic completion providers for context-aware suggestions.
"""

import os
import glob
import json
from typing import List, Optional


class DynamicCompleters:
    """Dynamic completion providers for context-aware suggestions."""
    
    def __init__(self, shell):
        self.shell = shell
        self.facts_dir = shell.facts_dir
        self._cached_routers = None
        self._cached_ips = None
    
    def router_names(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Complete router names from current facts."""
        routers = self._get_router_names()
        return [r for r in routers if r.startswith(text)]
    
    def ip_addresses(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Complete IP addresses from network topology."""
        ips = self._get_all_ips()
        return [ip for ip in ips if ip.startswith(text)]
    
    def service_ports(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Complete active service ports."""
        # This would need to query running services
        # For now, return common ports
        common_ports = ['22', '80', '443', '53', '8080', '8443', '3306', '5432']
        return [p for p in common_ports if p.startswith(text)]
    
    def protocols(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Complete protocol names."""
        protocols = ['tcp', 'udp', 'icmp']
        return [p for p in protocols if p.startswith(text)]
    
    def shell_types(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Complete shell types."""
        shells = ['bash', 'zsh', 'fish']
        return [s for s in shells if s.startswith(text)]
    
    def output_formats(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Complete output formats."""
        formats = ['text', 'json']
        return [f for f in formats if f.startswith(text)]
    
    def _get_router_names(self) -> List[str]:
        """Get router names from facts directory."""
        if self._cached_routers is not None:
            return self._cached_routers
        
        routers = []
        
        if os.path.exists(self.facts_dir):
            # Look for JSON files
            json_files = glob.glob(os.path.join(self.facts_dir, '*.json'))
            
            for json_file in json_files:
                # Extract router name from filename
                basename = os.path.basename(json_file)
                if basename.endswith('.json'):
                    router_name = basename[:-5]  # Remove .json extension
                    # Skip metadata files
                    if not router_name.endswith('_metadata'):
                        routers.append(router_name)
        
        self._cached_routers = sorted(routers)
        return self._cached_routers
    
    def _get_all_ips(self) -> List[str]:
        """Get all IP addresses from network topology."""
        if self._cached_ips is not None:
            return self._cached_ips
        
        ips = set()
        
        if os.path.exists(self.facts_dir):
            # Look for JSON files
            json_files = glob.glob(os.path.join(self.facts_dir, '*.json'))
            
            for json_file in json_files:
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                    
                    # Extract IPs from various sections
                    self._extract_ips_from_data(data, ips)
                    
                except (json.JSONDecodeError, IOError):
                    # Skip files that can't be read
                    continue
        
        self._cached_ips = sorted(list(ips))
        return self._cached_ips
    
    def _extract_ips_from_data(self, data: dict, ips: set):
        """Extract IP addresses from facts data."""
        if not isinstance(data, dict):
            return
        
        # Extract from interfaces
        if 'interfaces' in data:
            for interface_data in data['interfaces'].values():
                if isinstance(interface_data, dict):
                    # Look for IP addresses in addr_info
                    if 'addr_info' in interface_data:
                        for addr in interface_data['addr_info']:
                            if isinstance(addr, dict) and 'local' in addr:
                                ip = addr['local']
                                if self._is_valid_ip(ip):
                                    ips.add(ip)
        
        # Extract from routing tables
        if 'routing' in data:
            for route in data['routing']:
                if isinstance(route, dict):
                    # Look for gateway and destination IPs
                    if 'gateway' in route and route['gateway'] != '':
                        ip = route['gateway']
                        if self._is_valid_ip(ip):
                            ips.add(ip)
                    
                    if 'dst' in route and route['dst'] != '':
                        # Extract network IP from CIDR
                        dst = route['dst']
                        if '/' in dst:
                            ip = dst.split('/')[0]
                            if self._is_valid_ip(ip):
                                ips.add(ip)
        
        # Add some common test IPs
        test_ips = [
            '10.1.1.1', '10.1.2.1', '10.1.10.1',
            '10.2.1.1', '10.2.2.1', '10.2.10.1',
            '10.3.1.1', '10.3.2.1', '10.3.10.1',
            '10.100.1.1', '10.100.1.2', '10.100.1.3',
            '8.8.8.8', '1.1.1.1', '192.168.1.1'
        ]
        
        for ip in test_ips:
            ips.add(ip)
    
    def _is_valid_ip(self, ip: str) -> bool:
        """Check if string is a valid IP address."""
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False
            
            for part in parts:
                num = int(part)
                if num < 0 or num > 255:
                    return False
            
            return True
            
        except ValueError:
            return False
    
    def clear_cache(self):
        """Clear cached completion data."""
        self._cached_routers = None
        self._cached_ips = None