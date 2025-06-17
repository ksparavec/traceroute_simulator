#!/usr/bin/env python3
"""
iptables_forward_analyzer.py - Analyze iptables FORWARD chain rules for packet forwarding decisions

This script analyzes iptables configuration to determine if a packet will be forwarded
by a specific router based on source/destination IP/port and FORWARD chain rules.

Usage:
    python3 iptables_forward_analyzer.py -s <source_ip> [-sp <source_port>] -d <dest_ip> [-dp <dest_port>] --router <router_name> --routing-dir <path> [-p <protocol>] [-v]

Arguments:
    -s, --source        Source IP address (supports ranges and lists: 10.1.1.1,10.1.1.2 or 10.1.1.0/24)
    -sp, --source-port  Source port number (optional, supports multiport: 80,443 or 8000:8080)
    -d, --dest          Destination IP address (supports ranges and lists: 10.1.1.1,10.1.1.2 or 10.1.1.0/24)  
    -dp, --dest-port    Destination port number (optional, supports multiport: 80,443 or 8000:8080)
    -p, --protocol      Protocol type: all, tcp, udp, icmp (default: all)
    --router            Router name to analyze (must match iptables file prefix)
    --routing-dir       Directory containing routing facts and iptables files
    -v, --verbose       Enable verbose output (-v: basic decisions, -vv: detailed rule checks, -vvv: ipset structure)

Exit codes:
    0 - Packet forwarding allowed
    1 - Packet forwarding denied
    2 - Error (missing files, invalid arguments, etc.)
"""

import argparse
import sys
import os
import re
import ipaddress
from typing import Dict, List, Tuple, Optional, Any


class IpsetParser:
    """Parser for ipset list output to handle match-set conditions using efficient Python sets."""
    
    def __init__(self, ipsets_file: str, verbosity: int = 0):
        self.ipsets_file = ipsets_file
        self.verbosity = verbosity
        self.ipsets = {}  # Dict[str, Dict[str, Any]] - original ipset data
        self.ipset_lookup_sets = {}  # Dict[str, Set[Tuple[str, str, str]]] - efficient lookup sets
        
        if os.path.exists(ipsets_file):
            self._parse_ipsets()
            self._build_lookup_sets()
        elif verbosity >= 1:
            print(f"Warning: Ipset file not found: {ipsets_file}")
            print("Match-set rules will be skipped")
    
    def _parse_ipsets(self):
        """Parse ipset list output and store set definitions."""
        try:
            with open(self.ipsets_file, 'r') as f:
                content = f.read()
            
            # Split into individual ipset blocks
            sets = re.split(r'\n(?=Name: )', content)
            
            for set_block in sets:
                if not set_block.strip():
                    continue
                
                ipset_info = self._parse_single_ipset(set_block)
                if ipset_info:
                    self.ipsets[ipset_info['name']] = ipset_info
            
            if self.verbosity >= 2:
                print(f"Loaded {len(self.ipsets)} ipsets from {self.ipsets_file}")
                for name in self.ipsets:
                    print(f"  - {name}: {self.ipsets[name]['type']} with {len(self.ipsets[name]['members'])} members")
        
        except Exception as e:
            if self.verbosity >= 1:
                print(f"Warning: Could not parse ipsets file: {e}")
            self.ipsets = {}
            self.ipset_lookup_sets = {}
    
    def _parse_single_ipset(self, set_block: str) -> Optional[Dict[str, Any]]:
        """Parse a single ipset definition block."""
        lines = set_block.strip().split('\n')
        if not lines:
            return None
        
        ipset_info = {
            'name': '',
            'type': '',
            'members': []
        }
        
        in_members = False
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('Name: '):
                ipset_info['name'] = line[6:].strip()
            elif line.startswith('Type: '):
                ipset_info['type'] = line[6:].strip()
            elif line == 'Members:':
                in_members = True
            elif in_members and line and not line.startswith('Name: '):
                # Skip empty lines and headers
                ipset_info['members'].append(line)
        
        return ipset_info if ipset_info['name'] else None
    
    def _build_lookup_sets(self):
        """Build efficient Python sets for fast membership testing.
        
        Each set contains tuples of (ip_or_network, port, protocol) where:
        - ip_or_network: IP address or CIDR network (always present)
        - port: port number as string or '*' for any
        - protocol: protocol as string or '*' for any
        """
        for set_name, ipset_info in self.ipsets.items():
            lookup_set = set()
            
            for member in ipset_info['members']:
                ip_part, port_part, protocol_part = self._parse_member(member)
                if ip_part:  # IP address is required
                    lookup_set.add((ip_part, port_part, protocol_part))
            
            self.ipset_lookup_sets[set_name] = lookup_set
            
            if self.verbosity >= 2:
                print(f"Built lookup set for {set_name}: {len(lookup_set)} entries")
    
    def _parse_member(self, member: str) -> Tuple[str, str, str]:
        """Parse an ipset member into (ip, port, protocol) components.
        
        Returns:
            Tuple of (ip_or_network, port, protocol) where:
            - ip_or_network: IP address or CIDR network
            - port: port number as string or '*' for any
            - protocol: protocol as string or '*' for any
        """
        if ',' in member:
            # Port-based member (e.g., "10.1.1.1,tcp:80")
            parts = member.split(',', 1)
            ip_part = parts[0].strip()
            port_protocol_part = parts[1].strip()
            
            if ':' in port_protocol_part:
                protocol, port = port_protocol_part.split(':', 1)
                return ip_part, port.strip(), protocol.strip()
            else:
                # Malformed port part, treat as IP-only
                return ip_part, '*', '*'
        else:
            # Regular IP-only member
            return member.strip(), '*', '*'
    
    def get_set_info(self, set_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific ipset."""
        return self.ipsets.get(set_name)
    
    def get_lookup_set_size(self, set_name: str) -> int:
        """Get the size of a lookup set for debugging."""
        return len(self.ipset_lookup_sets.get(set_name, set()))
    
    def check_membership(self, ip: str, set_name: str, port: Optional[int] = None, protocol: str = 'tcp') -> bool:
        """Check if an IP address (and optionally port/protocol) matches any member in the specified ipset.
        
        Uses efficient set-based lookup with proper IP network matching.
        
        Args:
            ip: IP address to check
            set_name: Name of the ipset
            port: Optional port number
            protocol: Protocol ('tcp', 'udp', etc.)
            
        Returns:
            True if the IP (and optionally port/protocol) matches any member in the set
        """
        if set_name not in self.ipset_lookup_sets:
            if self.verbosity >= 2:
                print(f"      Warning: ipset '{set_name}' not found in lookup sets")
            return False
        
        lookup_set = self.ipset_lookup_sets[set_name]
        
        try:
            ip_addr = ipaddress.ip_address(ip)
            
            # Convert port to string for lookup
            port_str = str(port) if port is not None else '*'
            protocol_str = protocol.lower() if protocol else '*'
            
            # Check exact matches first (most common case)
            if (ip, port_str, protocol_str) in lookup_set:
                return True
            if (ip, '*', '*') in lookup_set:  # IP-only match
                return True
            if (ip, port_str, '*') in lookup_set:  # IP+port match without protocol
                return True
            if (ip, '*', protocol_str) in lookup_set:  # IP+protocol match without port
                return True
            
            # Check network membership for CIDR blocks
            for member_ip, member_port, member_protocol in lookup_set:
                try:
                    # Check if this is a network (contains '/')
                    if '/' in member_ip:
                        network = ipaddress.ip_network(member_ip, strict=False)
                        if ip_addr in network:
                            # IP is in network, now check port and protocol
                            if member_port == '*' or member_port == port_str:
                                if member_protocol == '*' or member_protocol == protocol_str:
                                    return True
                except ValueError:
                    # Invalid network format, skip
                    continue
            
            return False
        
        except ValueError:
            # Invalid IP address
            if self.verbosity >= 2:
                print(f"      Warning: Invalid IP address '{ip}' for ipset lookup")
            return False
    
    # Keep backward compatibility
    def ip_in_set(self, ip: str, set_name: str, port: Optional[int] = None, protocol: str = 'tcp') -> bool:
        """Backward compatibility wrapper for check_membership."""
        return self.check_membership(ip, set_name, port, protocol)


class IptablesRule:
    """Represents a single iptables rule with its match criteria and target."""
    
    def __init__(self, line_number: int, rule_text: str, target: str):
        self.line_number = line_number
        self.rule_text = rule_text.strip()
        self.target = target.upper()
        self.parsed_criteria = self._parse_rule_criteria()
    
    def _parse_rule_criteria(self) -> Dict[str, Any]:
        """Parse rule text to extract match criteria."""
        criteria = {}
        
        # Split rule into tokens
        tokens = self.rule_text.split()
        
        # Parse match-set conditions for later expansion
        match_sets = []
        i = 0
        while i < len(tokens):
            if tokens[i] == 'match-set' and i + 2 < len(tokens):
                # Format: match-set SET_NAME src|dst
                set_name = tokens[i + 1]
                direction = tokens[i + 2]
                match_sets.append({'set_name': set_name, 'direction': direction})
                i += 3
            else:
                i += 1
        
        if match_sets:
            criteria['match_sets'] = match_sets
        
        # Handle two different iptables output formats:
        # Format 1: -s source -d dest -p protocol ... (iptables-save format)
        # Format 2: protocol -- in_if out_if source dest ... (iptables -L format)
        
        if len(tokens) >= 6 and tokens[1] == '--':
            # Format 2: iptables -L format (positional)
            criteria['protocol'] = tokens[0] if tokens[0] != 'all' else None
            # tokens[1] is '--'
            criteria['in_interface'] = tokens[2] if tokens[2] != '*' else None
            criteria['out_interface'] = tokens[3] if tokens[3] != '*' else None
            criteria['source'] = tokens[4] if tokens[4] != '0.0.0.0/0' else None
            criteria['destination'] = tokens[5] if tokens[5] != '0.0.0.0/0' else None
            
            # Parse remaining tokens for ports and state
            i = 6
        else:
            # Format 1: iptables-save format (flag-based)
            i = 0
        
        while i < len(tokens):
            token = tokens[i]
            
            # Source IP/network (flag format)
            if token == '-s' and i + 1 < len(tokens):
                criteria['source'] = tokens[i + 1]
                i += 2
                continue
            
            # Destination IP/network (flag format)
            if token == '-d' and i + 1 < len(tokens):
                criteria['destination'] = tokens[i + 1]
                i += 2
                continue
            
            # Input interface
            if token == '-i' and i + 1 < len(tokens):
                criteria['in_interface'] = tokens[i + 1]
                i += 2
                continue
            
            # Output interface
            if token == '-o' and i + 1 < len(tokens):
                criteria['out_interface'] = tokens[i + 1]
                i += 2
                continue
            
            # Protocol (flag format)
            if token == '-p' and i + 1 < len(tokens):
                criteria['protocol'] = tokens[i + 1]
                i += 2
                continue
            
            # Source port (requires -p tcp or -p udp)
            if token == '--sport' and i + 1 < len(tokens):
                criteria['source_port'] = tokens[i + 1]
                i += 2
                continue
            
            # Destination port (requires -p tcp or -p udp)
            if token == '--dport' and i + 1 < len(tokens):
                criteria['dest_port'] = tokens[i + 1]
                i += 2
                continue
            
            # Multiport destination ports (iptables-save format: --dports)
            if token == '--dports' and i + 1 < len(tokens):
                criteria['dest_port'] = tokens[i + 1]
                i += 2
                continue
            
            # Multiport destination ports (iptables -L format: dports)
            if token == 'dports' and i + 1 < len(tokens):
                criteria['dest_port'] = tokens[i + 1]
                i += 2
                continue
            
            # Multiport source ports (iptables-save format: --sports)
            if token == '--sports' and i + 1 < len(tokens):
                criteria['source_port'] = tokens[i + 1]
                i += 2
                continue
            
            # Multiport source ports (iptables -L format: sports)
            if token == 'sports' and i + 1 < len(tokens):
                criteria['source_port'] = tokens[i + 1]
                i += 2
                continue
            
            # Connection state (multiple formats)
            if token == '-m' and i + 1 < len(tokens) and tokens[i + 1] == 'conntrack':
                if i + 3 < len(tokens) and tokens[i + 2] == '--ctstate':
                    criteria['conntrack_state'] = tokens[i + 3]
                    i += 4
                    continue
            
            # Connection state (-m state --state NEW)
            if token == '-m' and i + 1 < len(tokens) and tokens[i + 1] == 'state':
                if i + 3 < len(tokens) and tokens[i + 2] == '--state':
                    criteria['conntrack_state'] = tokens[i + 3]
                    i += 4
                    continue
            
            # Connection state (direct format: state NEW)
            if token == 'state' and i + 1 < len(tokens):
                criteria['conntrack_state'] = tokens[i + 1]
                i += 2
                continue
            
            # Destination IP range (format: "destination IP range 10.1.1.1-10.1.1.10")
            if token == 'destination' and i + 3 < len(tokens) and tokens[i + 1] == 'IP' and tokens[i + 2] == 'range':
                criteria['destination'] = tokens[i + 3]
                i += 4
                continue
            
            # Source IP range (format: "source IP range 10.1.1.1-10.1.1.10")
            if token == 'source' and i + 3 < len(tokens) and tokens[i + 1] == 'IP' and tokens[i + 2] == 'range':
                criteria['source'] = tokens[i + 3]
                i += 4
                continue
            
            i += 1
        
        return criteria
    
    def matches_packet(self, src_ip: str, src_port: Optional[int], dest_ip: str, dest_port: Optional[int], protocol: str = 'tcp', connection_state: str = 'NEW', verbosity: int = 0, analyzer = None) -> bool:
        """Check if this rule matches the given packet parameters."""
        
        if verbosity >= 2:
            print(f"    Checking rule {self.line_number}: {self.target} - {self.rule_text}")
        
        # Check match-set conditions first (most restrictive)
        if 'match_sets' in self.parsed_criteria:
            match_sets = self.parsed_criteria['match_sets']
            if not self._check_match_sets(src_ip, src_port, dest_ip, dest_port, protocol, match_sets, verbosity, analyzer):
                return False
        
        # Check source IP
        if 'source' in self.parsed_criteria:
            match_result = self._ip_matches(src_ip, self.parsed_criteria['source'])
            if verbosity >= 2:
                print(f"      Source IP check: {src_ip} vs {self.parsed_criteria['source']} = {'MATCH' if match_result else 'NO MATCH'}")
            if not match_result:
                return False
        elif verbosity >= 2:
            print(f"      Source IP check: {src_ip} (rule has no source restriction) = MATCH")
        
        # Check destination IP
        if 'destination' in self.parsed_criteria:
            match_result = self._ip_matches(dest_ip, self.parsed_criteria['destination'])
            if verbosity >= 2:
                print(f"      Destination IP check: {dest_ip} vs {self.parsed_criteria['destination']} = {'MATCH' if match_result else 'NO MATCH'}")
            if not match_result:
                return False
        elif verbosity >= 2:
            print(f"      Destination IP check: {dest_ip} (rule has no destination restriction) = MATCH")
        
        # Check input interface (using symmetric routing assumption)
        if 'in_interface' in self.parsed_criteria and self.parsed_criteria['in_interface'] is not None:
            if analyzer is not None:
                # Assume symmetric routing: find outgoing interface for source IP
                expected_in_interface = analyzer._find_outgoing_interface(src_ip)
                if expected_in_interface is None:
                    if verbosity >= 2:
                        print(f"      Input interface check: cannot determine interface for source {src_ip}, skipping interface check")
                else:
                    match_result = expected_in_interface == self.parsed_criteria['in_interface']
                    if verbosity >= 2:
                        print(f"      Input interface check: {src_ip} should come via {expected_in_interface} vs rule requires {self.parsed_criteria['in_interface']} = {'MATCH' if match_result else 'NO MATCH'}")
                    if not match_result:
                        return False
            else:
                if verbosity >= 2:
                    print(f"      Input interface check: no routing info available, skipping interface check")
        elif verbosity >= 2:
            print(f"      Input interface check: rule has no input interface restriction = MATCH")
        
        # Check output interface (using routing table lookup)
        if 'out_interface' in self.parsed_criteria and self.parsed_criteria['out_interface'] is not None:
            if analyzer is not None:
                expected_out_interface = analyzer._find_outgoing_interface(dest_ip)
                if expected_out_interface is None:
                    if verbosity >= 2:
                        print(f"      Output interface check: cannot determine interface for destination {dest_ip}, skipping interface check")
                else:
                    match_result = expected_out_interface == self.parsed_criteria['out_interface']
                    if verbosity >= 2:
                        print(f"      Output interface check: {dest_ip} should go via {expected_out_interface} vs rule requires {self.parsed_criteria['out_interface']} = {'MATCH' if match_result else 'NO MATCH'}")
                    if not match_result:
                        return False
            else:
                if verbosity >= 2:
                    print(f"      Output interface check: no routing info available, skipping interface check")
        elif verbosity >= 2:
            print(f"      Output interface check: rule has no output interface restriction = MATCH")
        
        # Check protocol (skip if 'all' is specified)
        if 'protocol' in self.parsed_criteria and self.parsed_criteria['protocol'] is not None and protocol != 'all':
            match_result = self.parsed_criteria['protocol'] == protocol
            if verbosity >= 2:
                print(f"      Protocol check: {protocol} vs {self.parsed_criteria['protocol']} = {'MATCH' if match_result else 'NO MATCH'}")
            if not match_result:
                return False
        elif verbosity >= 2:
            if 'protocol' in self.parsed_criteria and self.parsed_criteria['protocol'] is not None:
                print(f"      Protocol check: {protocol} vs {self.parsed_criteria['protocol']} (rule allows all protocols) = MATCH")
            else:
                protocol_info = f"any protocol" if protocol == 'all' else f"protocol {protocol} (rule has no protocol restriction)"
                print(f"      Protocol check: {protocol_info} = MATCH")
        
        # Check source port (only if port is specified)
        if 'source_port' in self.parsed_criteria and self.parsed_criteria['source_port'] is not None and src_port is not None:
            match_result = self._port_matches(src_port, self.parsed_criteria['source_port'])
            if verbosity >= 2:
                print(f"      Source port check: {src_port} vs {self.parsed_criteria['source_port']} = {'MATCH' if match_result else 'NO MATCH'}")
            if not match_result:
                return False
        elif verbosity >= 2:
            port_info = "not specified" if src_port is None else "any port (rule has no restriction)"
            print(f"      Source port check: {port_info} = MATCH")
        
        # Check destination port (only if port is specified)
        if 'dest_port' in self.parsed_criteria and self.parsed_criteria['dest_port'] is not None and dest_port is not None:
            match_result = self._port_matches(dest_port, self.parsed_criteria['dest_port'])
            if verbosity >= 2:
                print(f"      Destination port check: {dest_port} vs {self.parsed_criteria['dest_port']} = {'MATCH' if match_result else 'NO MATCH'}")
            if not match_result:
                return False
        elif verbosity >= 2:
            port_info = "not specified" if dest_port is None else "any port (rule has no restriction)"
            print(f"      Destination port check: {port_info} = MATCH")
        
        # Check connection state (focus on NEW state matching)
        if 'conntrack_state' in self.parsed_criteria and self.parsed_criteria['conntrack_state'] is not None:
            match_result = self._state_matches(connection_state, self.parsed_criteria['conntrack_state'])
            if verbosity >= 2:
                print(f"      Connection state check: {connection_state} vs {self.parsed_criteria['conntrack_state']} = {'MATCH' if match_result else 'NO MATCH'}")
            if not match_result:
                return False
        elif verbosity >= 2:
            print(f"      Connection state check: {connection_state} (rule has no state restriction) = MATCH")
        
        if verbosity >= 2:
            print(f"    Rule {self.line_number} MATCHES all criteria!")
        
        return True
    
    def _ip_matches(self, ip: str, criteria: str) -> bool:
        """Check if IP matches the criteria (supports CIDR, ranges, and lists)."""
        if criteria is None:
            return True  # No criteria means all IPs match
        
        try:
            # Handle comma-separated lists (10.1.1.1,10.1.1.2,10.1.1.3)
            if ',' in criteria:
                for ip_item in criteria.split(','):
                    if self._single_ip_matches(ip, ip_item.strip()):
                        return True
                return False
            else:
                return self._single_ip_matches(ip, criteria)
        except (ipaddress.AddressValueError, ValueError):
            return False
    
    def _single_ip_matches(self, ip: str, criteria: str) -> bool:
        """Check if IP matches a single criteria item."""
        try:
            if '/' in criteria:
                # CIDR network
                network = ipaddress.ip_network(criteria, strict=False)
                return ipaddress.ip_address(ip) in network
            elif '-' in criteria and criteria.count('.') >= 3:
                # IP range (10.1.1.1-10.1.1.10)
                start_ip, end_ip = criteria.split('-', 1)
                start_addr = ipaddress.ip_address(start_ip.strip())
                end_addr = ipaddress.ip_address(end_ip.strip())
                test_addr = ipaddress.ip_address(ip)
                return start_addr <= test_addr <= end_addr
            else:
                # Exact IP match
                return ip == criteria
        except (ipaddress.AddressValueError, ValueError):
            return False
    
    def _port_matches(self, port: int, criteria: str) -> bool:
        """Check if port matches the criteria (supports ranges, lists, and multiport syntax)."""
        try:
            # Handle comma-separated lists (80,443,8080)
            if ',' in criteria:
                for port_item in criteria.split(','):
                    if self._single_port_matches(port, port_item.strip()):
                        return True
                return False
            else:
                return self._single_port_matches(port, criteria)
        except ValueError:
            return False
    
    def _single_port_matches(self, port: int, criteria: str) -> bool:
        """Check if port matches a single criteria item."""
        try:
            if ':' in criteria:
                # Port range (8000:8080)
                start, end = criteria.split(':', 1)
                return int(start) <= port <= int(end)
            elif '-' in criteria:
                # Port range alternative syntax (8000-8080)
                start, end = criteria.split('-', 1)
                return int(start) <= port <= int(end)
            else:
                # Exact port match
                return port == int(criteria)
        except ValueError:
            return False
    
    def _state_matches(self, packet_state: str, criteria: str) -> bool:
        """Check if connection state matches the criteria."""
        # Handle comma-separated states (NEW,RELATED,ESTABLISHED)
        allowed_states = [state.strip() for state in criteria.split(',')]
        
        # For our simplified model, we focus on NEW connections
        # RELATED,ESTABLISHED connections are assumed to pass by default (handled elsewhere)
        return packet_state.upper() in [state.upper() for state in allowed_states]
    
    def _check_match_sets(self, src_ip: str, src_port: Optional[int], dest_ip: str, dest_port: Optional[int], protocol: str, match_sets: List[Dict[str, str]], verbosity: int, analyzer) -> bool:
        """Check if packet matches all match-set conditions in a rule.
        
        Args:
            src_ip, src_port, dest_ip, dest_port, protocol: Packet parameters
            match_sets: List of match-set conditions from rule
            verbosity: Verbosity level
            analyzer: Reference to analyzer for ipset access
            
        Returns:
            True if packet matches ALL match-set conditions
        """
        if not analyzer or not analyzer.ipset_parser:
            if verbosity >= 2:
                print(f"      No ipset parser available, skipping match-set checks")
            return False
        
        # All match-sets must match for the rule to match
        for i, match_set in enumerate(match_sets):
            set_name = match_set['set_name']
            direction = match_set['direction']
            
            if verbosity >= 2:
                print(f"      Checking match-set {i+1}/{len(match_sets)}: {set_name} {direction}")
            
            # Determine which IP/port to test based on direction
            if direction == 'src':
                test_ip = src_ip
                test_port = src_port
            elif direction == 'dst':
                test_ip = dest_ip
                test_port = dest_port
            elif direction == 'src,src':
                # Both source IP and source port - use compound matching
                test_ip = src_ip
                test_port = src_port
            elif direction == 'dst,dst':
                # Both destination IP and destination port - use compound matching
                test_ip = dest_ip
                test_port = dest_port
            elif direction == 'src,dst':
                # Mixed - typically use source IP
                test_ip = src_ip
                test_port = dest_port
            elif direction == 'dst,src':
                # Mixed - typically use destination IP
                test_ip = dest_ip
                test_port = src_port
            else:
                if verbosity >= 2:
                    print(f"      Unknown match-set direction: {direction}")
                continue
            
            # Check membership in ipset
            is_member = analyzer.ipset_parser.check_membership(test_ip, set_name, test_port, protocol)
            
            if verbosity >= 2:
                port_info = f":{test_port}" if test_port is not None else ""
                result_str = "MATCH" if is_member else "NO MATCH"
                print(f"      Match-set check: {test_ip}{port_info}/{protocol} in {set_name} ({direction}) = {result_str}")
            
            if not is_member:
                return False
        
        if verbosity >= 2:
            print(f"      All {len(match_sets)} match-set(s) matched!")
        return True


def validate_ip_argument(ip_arg: str, arg_name: str):
    """Validate IP argument which can be single IP, CIDR, range, or comma-separated list."""
    try:
        # Handle comma-separated lists
        if ',' in ip_arg:
            for ip_item in ip_arg.split(','):
                validate_single_ip(ip_item.strip(), arg_name)
        else:
            validate_single_ip(ip_arg, arg_name)
    except (ipaddress.AddressValueError, ValueError) as e:
        raise ValueError(f"Invalid {arg_name} IP: {e}")


def validate_single_ip(ip_str: str, arg_name: str):
    """Validate a single IP address, CIDR, or range."""
    if '/' in ip_str:
        # CIDR network
        ipaddress.ip_network(ip_str, strict=False)
    elif '-' in ip_str and ip_str.count('.') >= 3:
        # IP range (10.1.1.1-10.1.1.10)
        start_ip, end_ip = ip_str.split('-', 1)
        start_addr = ipaddress.ip_address(start_ip.strip())
        end_addr = ipaddress.ip_address(end_ip.strip())
        if start_addr > end_addr:
            raise ValueError(f"Invalid IP range: start IP {start_addr} is greater than end IP {end_addr}")
    else:
        # Single IP address
        ipaddress.ip_address(ip_str)


def parse_port_argument(port_arg: str, arg_name: str) -> int:
    """Parse and validate port argument which can be single port, range, or comma-separated list."""
    # For analysis, we need a single port. If multiple ports are specified,
    # we'll use the first one for the analysis (this could be enhanced later)
    try:
        if ',' in port_arg:
            # Use first port from comma-separated list
            first_port = port_arg.split(',')[0].strip()
            return parse_single_port(first_port, arg_name)
        else:
            return parse_single_port(port_arg, arg_name)
    except ValueError as e:
        raise ValueError(f"Invalid {arg_name}: {e}")


def parse_single_port(port_str: str, arg_name: str) -> int:
    """Parse and validate a single port number or range."""
    if ':' in port_str or '-' in port_str:
        # Port range - use the first port
        separator = ':' if ':' in port_str else '-'
        start_port = port_str.split(separator)[0].strip()
        port = int(start_port)
    else:
        # Single port
        port = int(port_str)
    
    if not (1 <= port <= 65535):
        raise ValueError(f"Port {port} out of valid range (1-65535)")
    
    return port


class IptablesForwardAnalyzer:
    """Analyzes iptables FORWARD chain rules to determine packet forwarding decisions."""
    
    def __init__(self, routing_dir: str, router_name: str, verbosity: int = 0):
        self.routing_dir = routing_dir
        self.router_name = router_name
        self.verbosity = verbosity
        self.iptables_file = os.path.join(routing_dir, f"{router_name}_iptables.txt")
        self.routing_file = os.path.join(routing_dir, f"{router_name}_route.json")
        self.ipsets_file = os.path.join(routing_dir, f"{router_name}_ipsets.txt")
        self.forward_rules = []
        self.custom_chains = {}
        self.default_policy = "ACCEPT"
        self.policy_found = False  # Track if we've already found the policy
        self.routing_table = []
        self.ipset_parser = None
        
        if not os.path.exists(self.iptables_file):
            raise FileNotFoundError(f"Iptables file not found: {self.iptables_file}")
        
        # Load routing table for interface matching
        self._load_routing_table()
        
        # Load ipsets for match-set rule support
        self._load_ipsets()
        
        self._parse_iptables_config()
    
    def _load_routing_table(self):
        """Load routing table for interface matching."""
        if not os.path.exists(self.routing_file):
            if self.verbosity >= 1:
                print(f"Warning: Routing file not found: {self.routing_file}")
                print("Interface matching will be disabled")
            return
        
        try:
            import json
            with open(self.routing_file, 'r') as f:
                self.routing_table = json.load(f)
            if self.verbosity >= 2:
                print(f"Loaded {len(self.routing_table)} routing entries from {self.routing_file}")
        except (json.JSONDecodeError, Exception) as e:
            if self.verbosity >= 1:
                print(f"Warning: Could not load routing table: {e}")
                print("Interface matching will be disabled")
            self.routing_table = []
    
    def _load_ipsets(self):
        """Load ipsets for match-set rule support."""
        self.ipset_parser = IpsetParser(self.ipsets_file, self.verbosity)
        
        # Output complete ipset data structure when -vvv is specified
        if self.verbosity >= 3 and self.ipset_parser.ipsets:
            print("\n=== COMPLETE IPSET DATA STRUCTURE ===")
            for set_name, set_info in self.ipset_parser.ipsets.items():
                print(f"\nIpset: {set_name}")
                print(f"  Type: {set_info['type']}")
                print(f"  Members ({len(set_info['members'])}):")
                for i, member in enumerate(set_info['members']):
                    print(f"    [{i+1}] {member}")
            print("=== END IPSET DATA STRUCTURE ===\n")
    
    
    
    
    def _find_outgoing_interface(self, dest_ip: str) -> Optional[str]:
        """Find the outgoing interface for a destination IP using routing table."""
        if not self.routing_table:
            return None
        
        try:
            import ipaddress
            dest_addr = ipaddress.ip_address(dest_ip)
            
            # Find the most specific route (longest prefix match)
            best_match = None
            best_prefix_len = -1
            
            for route in self.routing_table:
                if 'dst' not in route or 'dev' not in route:
                    continue
                
                dst = route['dst']
                if dst == 'default':
                    # Default route (0.0.0.0/0)
                    if best_prefix_len < 0:
                        best_match = route
                        best_prefix_len = 0
                elif '/' in dst:
                    # Network route
                    try:
                        network = ipaddress.ip_network(dst, strict=False)
                        if dest_addr in network and network.prefixlen > best_prefix_len:
                            best_match = route
                            best_prefix_len = network.prefixlen
                    except ValueError:
                        continue
                else:
                    # Host route
                    try:
                        if dest_addr == ipaddress.ip_address(dst) and best_prefix_len < 32:
                            best_match = route
                            best_prefix_len = 32
                    except ValueError:
                        continue
            
            return best_match['dev'] if best_match else None
            
        except Exception:
            return None
    
    def _parse_iptables_config(self):
        """Parse iptables configuration file and extract FORWARD chain rules."""
        if self.verbosity >= 1:
            print(f"Parsing iptables configuration from: {self.iptables_file}")
        
        # Try different encodings for iptables files
        encodings = ['utf-8', 'iso-8859-1', 'latin-1', 'cp1252']
        content = None
        
        for encoding in encodings:
            try:
                with open(self.iptables_file, 'r', encoding=encoding) as f:
                    content = f.read()
                if self.verbosity >= 2:
                    print(f"Successfully read file using {encoding} encoding")
                break
            except UnicodeDecodeError:
                if self.verbosity >= 2:
                    print(f"Failed to read with {encoding} encoding, trying next...")
                continue
        
        if content is None:
            raise ValueError(f"Could not read iptables file with any supported encoding: {self.iptables_file}")
        
        # Find FORWARD chain section
        forward_section = False
        current_chain = None
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Check for chain headers
            if line.startswith("Chain FORWARD"):
                forward_section = True
                current_chain = "FORWARD"
                # Extract default policy (only from the first FORWARD chain found)
                if "policy" in line.lower() and not self.policy_found:
                    policy_match = re.search(r'policy\s+(\w+)', line, re.IGNORECASE)
                    if policy_match:
                        self.default_policy = policy_match.group(1).upper()
                        self.policy_found = True
                if self.verbosity >= 1:
                    print(f"Found FORWARD chain with default policy: {self.default_policy}")
                continue
            
            # Check for other chain headers
            if line.startswith("Chain "):
                forward_section = False
                chain_match = re.search(r'Chain\s+(\S+)', line)
                if chain_match:
                    current_chain = chain_match.group(1)
                continue
            
            # Parse rules in FORWARD chain
            if forward_section and current_chain == "FORWARD":
                self._parse_forward_rule(line)
            
            # Parse rules in custom chains (we might need to follow them)
            elif current_chain and current_chain != "FORWARD":
                if current_chain not in self.custom_chains:
                    self.custom_chains[current_chain] = []
                self._parse_custom_chain_rule(line, current_chain)
    
    def _parse_forward_rule(self, line: str):
        """Parse a single FORWARD chain rule."""
        # Skip table headers
        if line.startswith("num") or line.startswith("pkts") or "---" in line:
            return
        
        # Parse rule line: num pkts bytes target prot opt source destination
        parts = line.split()
        if len(parts) < 4:
            return
        
        try:
            line_number = int(parts[0])
            target = parts[3]
            
            # Reconstruct rule text (protocol and everything after target)
            rule_text = ' '.join(parts[4:]) if len(parts) > 4 else ""
            
            rule = IptablesRule(line_number, rule_text, target)
            self.forward_rules.append(rule)
            
            if self.verbosity >= 2:
                print(f"Parsed FORWARD rule {line_number}: {target} - {rule_text}")
        
        except (ValueError, IndexError):
            if self.verbosity >= 2:
                print(f"Skipping unparseable rule line: {line}")
    
    def _parse_custom_chain_rule(self, line: str, chain_name: str):
        """Parse rules in custom chains that might be referenced from FORWARD."""
        # Similar parsing logic but store in custom_chains
        parts = line.split()
        if len(parts) < 4:
            return
        
        try:
            line_number = int(parts[0])
            target = parts[3]
            # Reconstruct rule text (protocol and everything after target)
            rule_text = ' '.join(parts[4:]) if len(parts) > 4 else ""
            
            rule = IptablesRule(line_number, rule_text, target)
            self.custom_chains[chain_name].append(rule)
            
        except (ValueError, IndexError):
            pass
    
    def analyze_packet(self, src_ip: str, src_port: Optional[int], dest_ip: str, dest_port: Optional[int], protocol: str = 'tcp', connection_state: str = 'NEW') -> Tuple[bool, str]:
        """
        Analyze if a packet will be forwarded based on iptables rules.
        
        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        if self.verbosity >= 1:
            print(f"\nAnalyzing packet: {src_ip}:{src_port} -> {dest_ip}:{dest_port} ({protocol}) [state: {connection_state}]")
            print(f"Router: {self.router_name}")
            if self.verbosity >= 2:
                print(f"Processing {len(self.forward_rules)} FORWARD chain rules...")
                if self.default_policy == "ACCEPT":
                    print(f"Optimization: Default policy is ACCEPT - only checking for DENY rules (DROP/REJECT)")
                else:
                    print(f"Default policy is {self.default_policy} - checking for ALLOW rules (ACCEPT)")
        
        # Process rules in order with policy-aware optimization
        deny_rules_checked = 0
        allow_rules_skipped = 0
        
        for rule in self.forward_rules:
            # Policy-aware optimization: 
            # If default policy is ACCEPT, only check rules that could DENY the packet or custom chains
            # If default policy is DROP/REJECT, only check rules that could ALLOW the packet or custom chains
            if self.default_policy == "ACCEPT" and rule.target not in ["DROP", "REJECT"] and rule.target not in self.custom_chains:
                allow_rules_skipped += 1
                if self.verbosity >= 2:
                    print(f"\n  Skipping rule {rule.line_number} ({rule.target}) - default policy is ACCEPT, only checking DENY rules and custom chains")
                continue
            elif self.default_policy in ["DROP", "REJECT"] and rule.target != "ACCEPT" and rule.target not in self.custom_chains:
                if self.verbosity >= 2:
                    print(f"\n  Skipping rule {rule.line_number} ({rule.target}) - default policy is {self.default_policy}, only checking ACCEPT rules and custom chains")
                continue
            
            if self.default_policy == "ACCEPT" and rule.target in ["DROP", "REJECT"]:
                deny_rules_checked += 1
            
            if self.verbosity >= 2:
                print(f"\n  Evaluating rule {rule.line_number}...")
            
            if rule.matches_packet(src_ip, src_port, dest_ip, dest_port, protocol, connection_state, self.verbosity, self):
                decision_info = f"Rule {rule.line_number} matches: {rule.target}"
                if self.verbosity >= 1:
                    print(f"\n{decision_info}")
                    print(f"  Rule: {rule.rule_text}")
                    if self.verbosity >= 2:
                        print(f"  *** PACKET FATE DECIDED BY THIS RULE ***")
                
                # Handle different targets
                if rule.target == "ACCEPT":
                    reason = f"Allowed by rule {rule.line_number}: {rule.rule_text}"
                    if self.verbosity >= 1:
                        print(f"Decision: ACCEPT - {reason}")
                    return True, reason
                elif rule.target in ["DROP", "REJECT"]:
                    reason = f"Denied by rule {rule.line_number}: {rule.rule_text}"
                    if self.verbosity >= 1:
                        print(f"Decision: {rule.target} - {reason}")
                    return False, reason
                elif rule.target in self.custom_chains:
                    # Follow custom chain (always check custom chains regardless of policy)
                    if self.verbosity >= 2:
                        print(f"  Following custom chain: {rule.target}")
                    result, reason = self._analyze_custom_chain(rule.target, src_ip, src_port, dest_ip, dest_port, protocol, connection_state)
                    if result is not None:
                        chain_reason = f"Custom chain {rule.target}: {reason}"
                        if self.verbosity >= 1:
                            decision = "ACCEPT" if result else "DROP/REJECT"
                            print(f"Decision: {decision} - {chain_reason}")
                        return result, chain_reason
                    # If custom chain returns, continue with next rule
                    if self.verbosity >= 2:
                        print(f"  Custom chain {rule.target} returned, continuing with next rule")
                else:
                    if self.verbosity >= 2:
                        print(f"  Unknown target {rule.target}, continuing with next rule")
            elif self.verbosity >= 2:
                print(f"  Rule {rule.line_number} does not match")
        
        # No rules matched, apply default policy
        if self.default_policy == "ACCEPT":
            policy_decision = f"No DENY rules matched (checked {deny_rules_checked} rules, skipped {allow_rules_skipped} ACCEPT rules)"
        else:
            policy_decision = f"No ALLOW rules matched, applying default policy: {self.default_policy}"
        
        if self.verbosity >= 1:
            print(f"\n{policy_decision}")
            if self.verbosity >= 2:
                print(f"  *** PACKET FATE DECIDED BY DEFAULT POLICY ***")
        
        if self.default_policy == "ACCEPT":
            reason = f"Allowed by default policy (no DENY rules matched): {self.default_policy}"
            if self.verbosity >= 1:
                print(f"Decision: ACCEPT (default) - {reason}")
            return True, reason
        else:
            reason = f"Denied by default policy: {self.default_policy}"
            if self.verbosity >= 1:
                print(f"Decision: {self.default_policy} (default) - {reason}")
            return False, reason
    
    def _analyze_custom_chain(self, chain_name: str, src_ip: str, src_port: Optional[int], dest_ip: str, dest_port: Optional[int], protocol: str, connection_state: str = 'NEW') -> Tuple[Optional[bool], str]:
        """Analyze rules in a custom chain."""
        if chain_name not in self.custom_chains:
            return None, f"Custom chain {chain_name} not found"
        
        if self.verbosity >= 2:
            print(f"    Entering custom chain: {chain_name}")
        
        for rule in self.custom_chains[chain_name]:
            if self.verbosity >= 2:
                print(f"    Evaluating {chain_name} rule {rule.line_number}...")
            
            if rule.matches_packet(src_ip, src_port, dest_ip, dest_port, protocol, connection_state, self.verbosity, self):
                if self.verbosity >= 2:
                    print(f"    Chain {chain_name} rule {rule.line_number} matches: {rule.target}")
                
                if rule.target == "ACCEPT":
                    return True, f"Allowed by {chain_name} rule {rule.line_number}"
                elif rule.target in ["DROP", "REJECT"]:
                    return False, f"Denied by {chain_name} rule {rule.line_number}"
                elif rule.target == "RETURN":
                    return None, f"Returned from {chain_name}"
        
        # No rules matched in custom chain, return to main chain
        return None, f"No matches in custom chain {chain_name}, returning"


def main():
    """Main function to parse arguments and run analysis."""
    parser = argparse.ArgumentParser(
        description="Analyze iptables FORWARD chain rules for packet forwarding decisions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Analyze TCP packet forwarding
    python3 iptables_forward_analyzer.py -s 10.1.1.1 -sp 12345 -d 10.2.1.1 -dp 80 --router hq-gw --routing-dir tests/routing_facts
    
    # Analyze without port specification (protocol agnostic)
    python3 iptables_forward_analyzer.py -s 10.1.1.0/24 -d 8.8.8.8 --router hq-gw --routing-dir data -p all
    
    # Analyze with multiple IPs and ports
    python3 iptables_forward_analyzer.py -s 10.1.1.1,10.1.1.2 -sp 80,443 -d 8.8.8.8 -dp 53 --router hq-gw --routing-dir data -p tcp
    
    # Analyze with port ranges and basic verbose output
    python3 iptables_forward_analyzer.py -s 192.168.1.100 -sp 8000:8080 -d 10.2.1.1-10.2.1.10 -dp 443 --router hq-gw --routing-dir data -v
    
    # Analyze with detailed verbose output (shows each rule check)
    python3 iptables_forward_analyzer.py -s 10.1.1.1 -d 8.8.8.8 --router hq-gw --routing-dir data -vv
        """
    )
    
    parser.add_argument('-s', '--source', required=True, help='Source IP address (supports ranges and lists: 10.1.1.1,10.1.1.2 or 10.1.1.0/24)')
    parser.add_argument('-sp', '--source-port', type=str, required=False, help='Source port number (supports multiport: 80,443 or 8000:8080)')
    parser.add_argument('-d', '--dest', required=True, help='Destination IP address (supports ranges and lists: 10.1.1.1,10.1.1.2 or 10.1.1.0/24)')
    parser.add_argument('-dp', '--dest-port', type=str, required=False, help='Destination port number (supports multiport: 80,443 or 8000:8080)')
    parser.add_argument('--router', required=True, help='Router name to analyze')
    parser.add_argument('--routing-dir', required=True, help='Directory containing routing facts and iptables files')
    parser.add_argument('-v', '--verbose', action='count', default=0, help='Increase verbosity (-v: basic, -vv: detailed checks, -vvv: ipset structure)')
    parser.add_argument('-p', '--protocol', default='all', choices=['all', 'tcp', 'udp', 'icmp'], help='Protocol type (default: all)')
    
    args = parser.parse_args()
    
    try:
        # Validate IP addresses (can be lists, ranges, or single IPs)
        validate_ip_argument(args.source, 'source')
        validate_ip_argument(args.dest, 'destination')
        
        # Parse and validate port numbers (optional)
        source_port = None
        dest_port = None
        
        if args.source_port:
            source_port = parse_port_argument(args.source_port, 'source-port')
        if args.dest_port:
            dest_port = parse_port_argument(args.dest_port, 'dest-port')
        
        # Validate routing directory
        if not os.path.isdir(args.routing_dir):
            raise FileNotFoundError(f"Routing directory not found: {args.routing_dir}")
        
        # Create analyzer and run analysis (assume NEW connections)
        analyzer = IptablesForwardAnalyzer(args.routing_dir, args.router, args.verbose)
        allowed, reason = analyzer.analyze_packet(
            args.source, source_port, 
            args.dest, dest_port, 
            args.protocol, 'NEW'
        )
        
        if args.verbose:
            print(f"Result: {'ALLOWED' if allowed else 'DENIED'}")
            print(f"Reason: {reason}")
        
        # Exit with appropriate code
        sys.exit(0 if allowed else 1)
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    except (ipaddress.AddressValueError, ValueError) as e:
        print(f"Error: Invalid argument - {e}", file=sys.stderr)
        sys.exit(2)
    except UnicodeDecodeError as e:
        print(f"Error: File encoding issue - {e}", file=sys.stderr)
        print(f"Try converting the file to UTF-8: iconv -f iso-8859-1 -t utf-8 <file>", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()