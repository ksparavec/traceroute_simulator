#!/usr/bin/env python3
"""
Log Filter Module

Provides filtering and analysis capabilities for network log processing.
This module includes utilities for time-based filtering, IP address matching,
protocol filtering, and advanced log analysis patterns.

Key features:
- Time range filtering with flexible date parsing
- IP address and network filtering with CIDR support
- Protocol and port-based filtering
- Regex pattern matching for log prefixes
- Interface-based filtering
- Log aggregation and deduplication

Author: Network Analysis Tool
License: MIT
"""

import re
import ipaddress
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Union, Callable
from dataclasses import dataclass
import socket


@dataclass
class FilterCriteria:
    """Comprehensive filter criteria for log analysis."""
    # Network filters
    source_networks: List[str] = None
    dest_networks: List[str] = None
    protocols: List[str] = None
    source_ports: List[int] = None
    dest_ports: List[int] = None
    
    # Infrastructure filters
    routers: List[str] = None
    interfaces_in: List[str] = None
    interfaces_out: List[str] = None
    
    # Time filters
    time_start: Optional[datetime] = None
    time_end: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    
    # Content filters
    prefix_patterns: List[str] = None
    actions: List[str] = None
    min_packet_length: Optional[int] = None
    max_packet_length: Optional[int] = None
    ttl_range: Optional[tuple] = None
    
    # Advanced filters
    exclude_internal: bool = False
    exclude_broadcast: bool = False
    exclude_multicast: bool = False
    include_only_errors: bool = False
    
    def __post_init__(self):
        """Initialize list fields if None."""
        list_fields = [
            'source_networks', 'dest_networks', 'protocols', 
            'source_ports', 'dest_ports', 'routers',
            'interfaces_in', 'interfaces_out', 'prefix_patterns', 'actions'
        ]
        for field in list_fields:
            if getattr(self, field) is None:
                setattr(self, field, [])


class LogFilter:
    """
    Advanced log filtering engine for network analysis.
    
    Provides comprehensive filtering capabilities for network logs including
    time-based filtering, network filtering with CIDR support, protocol
    filtering, and advanced pattern matching.
    
    Attributes:
        verbose (bool): Enable verbose output for debugging
        case_sensitive (bool): Enable case-sensitive pattern matching
        compiled_patterns (Dict): Cache of compiled regex patterns
    """
    
    def __init__(self, verbose: bool = False, case_sensitive: bool = False):
        """
        Initialize log filter.
        
        Args:
            verbose: Enable verbose output for debugging
            case_sensitive: Enable case-sensitive pattern matching
        """
        self.verbose = verbose
        self.case_sensitive = case_sensitive
        self.compiled_patterns: Dict[str, re.Pattern] = {}
        
        # Pre-compile common patterns
        self._compile_common_patterns()
    
    def _compile_common_patterns(self):
        """Pre-compile commonly used regex patterns."""
        patterns = {
            'ipv4': r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
            'ipv6': r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b',
            'mac': r'\b[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\b',
            'timestamp': r'\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\b',
            'port': r'\b(?:port|PORT)\s*[=:]?\s*(\d{1,5})\b',
            'interface': r'\b(?:eth|wlan|lo|veth|br|tun|tap)\d*\b'
        }
        
        flags = 0 if self.case_sensitive else re.IGNORECASE
        for name, pattern in patterns.items():
            self.compiled_patterns[name] = re.compile(pattern, flags)
    
    def compile_pattern(self, pattern: str, name: str = None) -> re.Pattern:
        """Compile and cache a regex pattern."""
        if name and name in self.compiled_patterns:
            return self.compiled_patterns[name]
        
        flags = 0 if self.case_sensitive else re.IGNORECASE
        compiled = re.compile(pattern, flags)
        
        if name:
            self.compiled_patterns[name] = compiled
        
        return compiled
    
    def parse_time_string(self, time_str: str) -> datetime:
        """Parse various time string formats."""
        time_str = time_str.strip()
        
        # Handle relative times
        if time_str.endswith(' ago'):
            return self._parse_relative_time(time_str[:-4])
        
        # Handle absolute times
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%H:%M:%S',
            '%H:%M',
            '%m/%d/%Y %H:%M:%S',
            '%m/%d/%Y %H:%M',
            '%m/%d/%Y',
            '%b %d %H:%M:%S',
            '%b %d %H:%M',
            '%b %d %Y %H:%M:%S'
        ]
        
        for fmt in formats:
            try:
                parsed = datetime.strptime(time_str, fmt)
                # If no year specified, use current year
                if parsed.year == 1900:
                    parsed = parsed.replace(year=datetime.now().year)
                return parsed
            except ValueError:
                continue
        
        raise ValueError(f"Unable to parse time string: {time_str}")
    
    def _parse_relative_time(self, time_str: str) -> datetime:
        """Parse relative time strings like '1 hour', '30 minutes'."""
        time_str = time_str.strip().lower()
        now = datetime.now()
        
        # Parse number and unit
        parts = time_str.split()
        if len(parts) != 2:
            raise ValueError(f"Invalid relative time format: {time_str}")
        
        try:
            amount = int(parts[0])
        except ValueError:
            raise ValueError(f"Invalid time amount: {parts[0]}")
        
        unit = parts[1].rstrip('s')  # Remove trailing 's'
        
        if unit in ['second', 'sec']:
            delta = timedelta(seconds=amount)
        elif unit in ['minute', 'min']:
            delta = timedelta(minutes=amount)
        elif unit in ['hour', 'hr', 'h']:
            delta = timedelta(hours=amount)
        elif unit in ['day', 'd']:
            delta = timedelta(days=amount)
        elif unit in ['week', 'w']:
            delta = timedelta(weeks=amount)
        else:
            raise ValueError(f"Unknown time unit: {unit}")
        
        return now - delta
    
    def match_ip_network(self, ip: str, networks: List[str]) -> bool:
        """Check if IP address matches any of the specified networks."""
        if not networks:
            return True
        
        try:
            ip_addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        
        for network in networks:
            try:
                if '/' in network:
                    # CIDR notation
                    if ip_addr in ipaddress.ip_network(network, strict=False):
                        return True
                else:
                    # Exact IP match
                    if ip_addr == ipaddress.ip_address(network):
                        return True
            except ValueError:
                # Try as hostname
                try:
                    resolved_ip = socket.gethostbyname(network)
                    if str(ip_addr) == resolved_ip:
                        return True
                except socket.gaierror:
                    continue
        
        return False
    
    def match_pattern_list(self, text: str, patterns: List[str]) -> bool:
        """Check if text matches any pattern in the list."""
        if not patterns:
            return True
        
        for pattern in patterns:
            if self.case_sensitive:
                if pattern in text:
                    return True
            else:
                if pattern.lower() in text.lower():
                    return True
        
        return False
    
    def match_regex_patterns(self, text: str, patterns: List[str]) -> bool:
        """Check if text matches any regex pattern."""
        if not patterns:
            return True
        
        flags = 0 if self.case_sensitive else re.IGNORECASE
        
        for pattern in patterns:
            try:
                if re.search(pattern, text, flags):
                    return True
            except re.error:
                if self.verbose:
                    print(f"Invalid regex pattern: {pattern}")
                continue
        
        return False
    
    def is_internal_ip(self, ip: str) -> bool:
        """Check if IP address is internal (RFC 1918)."""
        try:
            ip_addr = ipaddress.ip_address(ip)
            return ip_addr.is_private
        except ValueError:
            return False
    
    def is_broadcast_ip(self, ip: str) -> bool:
        """Check if IP address is broadcast."""
        try:
            ip_addr = ipaddress.ip_address(ip)
            return ip_addr.is_broadcast if hasattr(ip_addr, 'is_broadcast') else False
        except ValueError:
            return False
    
    def is_multicast_ip(self, ip: str) -> bool:
        """Check if IP address is multicast."""
        try:
            ip_addr = ipaddress.ip_address(ip)
            return ip_addr.is_multicast
        except ValueError:
            return False
    
    def apply_network_filters(self, entry: Dict[str, Any], criteria: FilterCriteria) -> bool:
        """Apply network-based filters to a log entry."""
        # Source IP filter
        if criteria.source_networks:
            source_ip = entry.get('source_ip', '')
            if not self.match_ip_network(source_ip, criteria.source_networks):
                return False
        
        # Destination IP filter
        if criteria.dest_networks:
            dest_ip = entry.get('dest_ip', '')
            if not self.match_ip_network(dest_ip, criteria.dest_networks):
                return False
        
        # Protocol filter
        if criteria.protocols:
            protocol = entry.get('protocol', '').lower()
            if protocol not in [p.lower() for p in criteria.protocols]:
                return False
        
        # Port filters
        if criteria.source_ports:
            source_port = entry.get('source_port')
            if source_port not in criteria.source_ports:
                return False
        
        if criteria.dest_ports:
            dest_port = entry.get('dest_port')
            if dest_port not in criteria.dest_ports:
                return False
        
        return True
    
    def apply_infrastructure_filters(self, entry: Dict[str, Any], criteria: FilterCriteria) -> bool:
        """Apply infrastructure-based filters to a log entry."""
        # Router filter
        if criteria.routers:
            router = entry.get('router', '')
            if router not in criteria.routers:
                return False
        
        # Interface filters
        if criteria.interfaces_in:
            interface_in = entry.get('interface_in', '')
            if interface_in not in criteria.interfaces_in:
                return False
        
        if criteria.interfaces_out:
            interface_out = entry.get('interface_out', '')
            if interface_out not in criteria.interfaces_out:
                return False
        
        return True
    
    def apply_time_filters(self, entry: Dict[str, Any], criteria: FilterCriteria) -> bool:
        """Apply time-based filters to a log entry."""
        timestamp = entry.get('timestamp')
        if not timestamp:
            return True
        
        # Convert timestamp to datetime if it's a string
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                return True
        
        # Time range filters
        if criteria.time_start and timestamp < criteria.time_start:
            return False
        
        if criteria.time_end and timestamp > criteria.time_end:
            return False
        
        # Duration filter (last N minutes)
        if criteria.duration_minutes:
            cutoff = datetime.now() - timedelta(minutes=criteria.duration_minutes)
            if timestamp < cutoff:
                return False
        
        return True
    
    def apply_content_filters(self, entry: Dict[str, Any], criteria: FilterCriteria) -> bool:
        """Apply content-based filters to a log entry."""
        # Prefix pattern filter
        if criteria.prefix_patterns:
            prefix = entry.get('prefix', '')
            if not self.match_regex_patterns(prefix, criteria.prefix_patterns):
                return False
        
        # Action filter
        if criteria.actions:
            action = entry.get('action', '').upper()
            if action not in [a.upper() for a in criteria.actions]:
                return False
        
        # Packet length filters
        packet_length = entry.get('packet_length')
        if packet_length:
            if criteria.min_packet_length and packet_length < criteria.min_packet_length:
                return False
            if criteria.max_packet_length and packet_length > criteria.max_packet_length:
                return False
        
        # TTL filter
        ttl = entry.get('ttl')
        if ttl and criteria.ttl_range:
            min_ttl, max_ttl = criteria.ttl_range
            if ttl < min_ttl or ttl > max_ttl:
                return False
        
        return True
    
    def apply_advanced_filters(self, entry: Dict[str, Any], criteria: FilterCriteria) -> bool:
        """Apply advanced filters to a log entry."""
        source_ip = entry.get('source_ip', '')
        dest_ip = entry.get('dest_ip', '')
        
        # Exclude internal traffic filter
        if criteria.exclude_internal:
            if self.is_internal_ip(source_ip) and self.is_internal_ip(dest_ip):
                return False
        
        # Exclude broadcast traffic filter
        if criteria.exclude_broadcast:
            if self.is_broadcast_ip(source_ip) or self.is_broadcast_ip(dest_ip):
                return False
        
        # Exclude multicast traffic filter
        if criteria.exclude_multicast:
            if self.is_multicast_ip(source_ip) or self.is_multicast_ip(dest_ip):
                return False
        
        # Include only errors filter
        if criteria.include_only_errors:
            action = entry.get('action', '').upper()
            prefix = entry.get('prefix', '').upper()
            if action not in ['DROP', 'REJECT'] and 'ERROR' not in prefix and 'DENY' not in prefix:
                return False
        
        return True
    
    def filter_entries(self, entries: List[Dict[str, Any]], criteria: FilterCriteria) -> List[Dict[str, Any]]:
        """Apply all filters to a list of log entries."""
        filtered = []
        
        for entry in entries:
            if (self.apply_network_filters(entry, criteria) and
                self.apply_infrastructure_filters(entry, criteria) and
                self.apply_time_filters(entry, criteria) and
                self.apply_content_filters(entry, criteria) and
                self.apply_advanced_filters(entry, criteria)):
                filtered.append(entry)
        
        return filtered
    
    def group_entries(self, entries: List[Dict[str, Any]], 
                     group_by: Union[str, List[str]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group log entries by specified fields."""
        if isinstance(group_by, str):
            group_by = [group_by]
        
        groups = {}
        
        for entry in entries:
            # Create group key
            key_parts = []
            for field in group_by:
                value = entry.get(field, 'unknown')
                key_parts.append(str(value))
            
            key = '|'.join(key_parts)
            
            if key not in groups:
                groups[key] = []
            groups[key].append(entry)
        
        return groups
    
    def deduplicate_entries(self, entries: List[Dict[str, Any]], 
                           key_fields: List[str] = None) -> List[Dict[str, Any]]:
        """Remove duplicate log entries based on key fields."""
        if key_fields is None:
            key_fields = ['timestamp', 'source_ip', 'dest_ip', 'protocol']
        
        seen = set()
        unique = []
        
        for entry in entries:
            key_parts = []
            for field in key_fields:
                value = entry.get(field, '')
                key_parts.append(str(value))
            
            key = '|'.join(key_parts)
            
            if key not in seen:
                seen.add(key)
                unique.append(entry)
        
        return unique


def main():
    """Test the log filter module."""
    import json
    
    # Example log entries for testing
    test_entries = [
        {
            'timestamp': '2025-07-01 10:30:00',
            'router': 'hq-gw',
            'source_ip': '10.1.1.1',
            'dest_ip': '10.2.1.1',
            'protocol': 'tcp',
            'dest_port': 80,
            'action': 'ACCEPT',
            'prefix': 'FWD-ALLOW'
        },
        {
            'timestamp': '2025-07-01 10:31:00',
            'router': 'hq-gw',
            'source_ip': '192.168.1.1',
            'dest_ip': '8.8.8.8',
            'protocol': 'icmp',
            'action': 'DROP',
            'prefix': 'FWD-DROP'
        }
    ]
    
    # Create filter and criteria
    log_filter = LogFilter(verbose=True)
    criteria = FilterCriteria(
        protocols=['tcp'],
        actions=['ACCEPT']
    )
    
    # Apply filters
    filtered = log_filter.filter_entries(test_entries, criteria)
    
    print("Original entries:", len(test_entries))
    print("Filtered entries:", len(filtered))
    print("Filtered results:")
    print(json.dumps(filtered, indent=2))


if __name__ == '__main__':
    main()