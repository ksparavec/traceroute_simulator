#!/usr/bin/env python3
"""
iptables_forward_analyzer.py - Analyze iptables FORWARD chain rules for packet forwarding decisions

This script analyzes iptables configuration to determine if a packet will be forwarded
by a specific router based on source/destination IP/port and FORWARD chain rules.

Usage:
    python3 iptables_forward_analyzer.py -s <source_ip> [-sp <source_port>] -d <dest_ip> [-dp <dest_port>] --router <router_name> --tsim-facts <path> [-p <protocol>] [-v]

Arguments:
    -s, --source        Source IP address (supports ranges and lists: 10.1.1.1,10.1.1.2 or 10.1.1.0/24)
    -sp, --source-port  Source port number (optional, supports multiport: 80,443 or 8000:8080)
    -d, --dest          Destination IP address (supports ranges and lists: 10.1.1.1,10.1.1.2 or 10.1.1.0/24)  
    -dp, --dest-port    Destination port number (optional, supports multiport: 80,443 or 8000:8080)
    -p, --protocol      Protocol type: all, tcp, udp, icmp (default: all)
    --router            Router name to analyze (must match iptables file prefix)
    --tsim-facts        Directory containing routing facts and iptables files
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
            # Port-based member (e.g., "10.1.1.1,tcp:80" or "10.1.1.1,udp:514")
            parts = member.split(',', 1)
            ip_part = parts[0].strip()
            port_protocol_part = parts[1].strip()
            
            if ':' in port_protocol_part:
                # Format: protocol:port (e.g., "tcp:514", "udp:514")
                protocol, port = port_protocol_part.split(':', 1)
                return ip_part, port.strip(), protocol.strip()
            else:
                # Port without protocol (e.g., "10.1.1.1,80")
                return ip_part, port_protocol_part.strip(), '*'
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
            
            if self.verbosity >= 2:
                print(f"      Checking membership: {ip}:{port_str}/{protocol_str} in {set_name}")
            
            # Check exact matches first (most common case)
            if (ip, port_str, protocol_str) in lookup_set:
                if self.verbosity >= 2:
                    print(f"      Exact match found: {ip},{protocol_str}:{port_str}")
                return True
            if (ip, '*', '*') in lookup_set:  # IP-only match
                if self.verbosity >= 2:
                    print(f"      IP-only match found: {ip}")
                return True
            if (ip, port_str, '*') in lookup_set:  # IP+port match without protocol
                if self.verbosity >= 2:
                    print(f"      IP+port match found: {ip},{port_str}")
                return True
            if (ip, '*', protocol_str) in lookup_set:  # IP+protocol match without port
                if self.verbosity >= 2:
                    print(f"      IP+protocol match found: {ip},{protocol_str}")
                return True
            
            # Check network membership for CIDR blocks and exact IP matches
            for member_ip, member_port, member_protocol in lookup_set:
                try:
                    # Check if this is a network (contains '/')
                    if '/' in member_ip:
                        network = ipaddress.ip_network(member_ip, strict=False)
                        if ip_addr in network:
                            # IP is in network, now check port and protocol
                            if self._port_protocol_matches(port_str, protocol_str, member_port, member_protocol):
                                if self.verbosity >= 2:
                                    print(f"      Network match found: {ip} in {member_ip}, port/protocol: {member_port}/{member_protocol}")
                                return True
                    else:
                        # Direct IP comparison for non-CIDR entries
                        if ip == member_ip:
                            if self._port_protocol_matches(port_str, protocol_str, member_port, member_protocol):
                                if self.verbosity >= 2:
                                    print(f"      Direct IP match found: {ip}, port/protocol: {member_port}/{member_protocol}")
                                return True
                except ValueError:
                    # Invalid network format, skip
                    continue
            
            if self.verbosity >= 2:
                print(f"      No match found for {ip}:{port_str}/{protocol_str}")
            return False
        
        except ValueError:
            # Invalid IP address
            if self.verbosity >= 2:
                print(f"      Warning: Invalid IP address '{ip}' for ipset lookup")
            return False
    
    def _port_protocol_matches(self, test_port: str, test_protocol: str, member_port: str, member_protocol: str) -> bool:
        """Check if port and protocol match the member criteria."""
        # Port matching
        port_match = (member_port == '*' or member_port == test_port)
        
        # Protocol matching  
        protocol_match = (member_protocol == '*' or member_protocol == test_protocol)
        
        return port_match and protocol_match
    
    # Keep backward compatibility
    def ip_in_set(self, ip: str, set_name: str, port: Optional[int] = None, protocol: str = 'tcp') -> bool:
        """Backward compatibility wrapper for check_membership."""
        return self.check_membership(ip, set_name, port, protocol)


class IptablesRule:
    """Represents a single iptables rule with its match criteria and target."""
    
    def __init__(self, line_number: int, rule_text: str, target: str):
        self.line_number = line_number
        self.rule_text = rule_text.strip()
        self.target = target  # Preserve original case for custom chains
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
            if tokens[i] in ['match-set', '--match-set'] and i + 2 < len(tokens):
                # Format: --match-set SET_NAME src|dst or match-set SET_NAME src|dst
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
            
            # Multiport destination ports (colon format: dpts:80,443,3389)
            if token.startswith('dpts:'):
                criteria['dest_port'] = token[5:]  # Remove 'dpts:' prefix
                i += 1
                continue
            
            # Single destination port (colon format: dpt:80)
            if token.startswith('dpt:'):
                criteria['dest_port'] = token[4:]  # Remove 'dpt:' prefix
                i += 1
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
            
            # Multiport source ports (colon format: spts:1024,2048)
            if token.startswith('spts:'):
                criteria['source_port'] = token[5:]  # Remove 'spts:' prefix
                i += 1
                continue
            
            # Single source port (colon format: spt:1024)
            if token.startswith('spt:'):
                criteria['source_port'] = token[4:]  # Remove 'spt:' prefix
                i += 1
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
    
    def matches_packet(self, src_ip: str, src_port: Optional[int], dest_ip: str, dest_port: Optional[int], protocol: str = 'tcp', connection_state: str = 'NEW', verbosity: int = 0, analyzer = None, chain_context: str = "") -> bool:
        """Check if this rule matches the given packet parameters."""
        
        if verbosity >= 2:
            if chain_context:
                print(f"    Checking {chain_context} rule {self.line_number}: {self.target} - {self.rule_text}")
            else:
                print(f"    Checking rule {self.line_number}: {self.target} - {self.rule_text}")
        
        # Track which criteria fail for better debugging
        failed_criteria = []
        
        # Check match-set conditions first (most restrictive)
        if 'match_sets' in self.parsed_criteria:
            match_sets = self.parsed_criteria['match_sets']
            if not self._check_match_sets(src_ip, src_port, dest_ip, dest_port, protocol, match_sets, verbosity, analyzer):
                failed_criteria.append("match-set")
                if verbosity >= 2:
                    print(f"      Rule {self.line_number} does not match - FAILED: match-set condition")
                return False
        
        # Check source IP
        if 'source' in self.parsed_criteria:
            match_result = self._ip_matches(src_ip, self.parsed_criteria['source'])
            if verbosity >= 2:
                print(f"      Source IP check: {src_ip} vs {self.parsed_criteria['source']} = {'MATCH' if match_result else 'NO MATCH'}")
            if not match_result:
                failed_criteria.append("source IP")
                if verbosity >= 2:
                    print(f"      Rule {self.line_number} does not match - FAILED: source IP ({src_ip} does not match {self.parsed_criteria['source']})")
                return False
        elif verbosity >= 2:
            print(f"      Source IP check: {src_ip} (rule has no source restriction) = MATCH")
        
        # Check destination IP
        if 'destination' in self.parsed_criteria:
            match_result = self._ip_matches(dest_ip, self.parsed_criteria['destination'])
            if verbosity >= 2:
                print(f"      Destination IP check: {dest_ip} vs {self.parsed_criteria['destination']} = {'MATCH' if match_result else 'NO MATCH'}")
            if not match_result:
                failed_criteria.append("destination IP")
                if verbosity >= 2:
                    print(f"      Rule {self.line_number} does not match - FAILED: destination IP ({dest_ip} does not match {self.parsed_criteria['destination']})")
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
                        failed_criteria.append("input interface")
                        if verbosity >= 2:
                            print(f"      Rule {self.line_number} does not match - FAILED: input interface (expected {expected_in_interface}, rule requires {self.parsed_criteria['in_interface']})")
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
                        failed_criteria.append("output interface")
                        if verbosity >= 2:
                            print(f"      Rule {self.line_number} does not match - FAILED: output interface (expected {expected_out_interface}, rule requires {self.parsed_criteria['out_interface']})")
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
                failed_criteria.append("protocol")
                if verbosity >= 2:
                    print(f"      Rule {self.line_number} does not match - FAILED: protocol ({protocol} does not match {self.parsed_criteria['protocol']})")
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
                failed_criteria.append("source port")
                if verbosity >= 2:
                    print(f"      Rule {self.line_number} does not match - FAILED: source port ({src_port} does not match {self.parsed_criteria['source_port']})")
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
                failed_criteria.append("destination port")
                if verbosity >= 2:
                    print(f"      Rule {self.line_number} does not match - FAILED: destination port ({dest_port} does not match {self.parsed_criteria['dest_port']})")
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
                failed_criteria.append("connection state")
                if verbosity >= 2:
                    print(f"      Rule {self.line_number} does not match - FAILED: connection state ({connection_state} does not match {self.parsed_criteria['conntrack_state']})")
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
    
    def _check_compound_match_set(self, analyzer, set_name: str, directions: List[str], 
                                  field1_ip: str, field1_port: Optional[int], 
                                  field2_ip: str, field2_port: Optional[int], 
                                  protocol: str, verbosity: int) -> bool:
        """
        Check compound match-set conditions for multi-dimensional ipsets.
        
        This handles complex cases like:
        - hash:ip,port with src,src (source IP + source port)
        - hash:ip,port with dst,dst (destination IP + destination port) 
        - hash:ip,port with src,dst (source IP + destination port)
        - hash:net,port,net with src,dst,dst (source IP + dest port + dest IP)
        
        Args:
            analyzer: Analyzer instance with ipset parser
            set_name: Name of the ipset
            directions: List of direction arguments (e.g., ['src', 'dst'])
            field1_ip, field1_port: First field values
            field2_ip, field2_port: Second field values
            protocol: Protocol type
            verbosity: Verbosity level
            
        Returns:
            True if the compound condition matches the ipset
        """
        if not analyzer or not analyzer.ipset_parser:
            return False
            
        # Get ipset information to determine the set type
        set_info = analyzer.ipset_parser.get_set_info(set_name)
        if not set_info:
            if verbosity >= 2:
                print(f"      Warning: No information available for ipset '{set_name}'")
            return False
            
        set_type = set_info.get('type', 'unknown')
        
        if verbosity >= 2:
            print(f"      Compound match-set check: {set_name} (type: {set_type}) with directions {directions}")
        
        # Handle different set types
        if set_type.startswith('hash:ip,port') or set_type.startswith('hash:net,port'):
            # Both hash:ip,port and hash:net,port expect IP/network and port in that order
            # The direction arguments specify which packet fields to match against
            if directions == ['src', 'src']:
                # Source IP + source port
                return analyzer.ipset_parser.check_membership(field1_ip, set_name, field1_port, protocol)
            elif directions == ['dst', 'dst']:
                # Destination IP + destination port  
                return analyzer.ipset_parser.check_membership(field2_ip, set_name, field2_port, protocol)
            elif directions == ['src', 'dst']:
                # Source IP + destination port
                return analyzer.ipset_parser.check_membership(field1_ip, set_name, field2_port, protocol)
            elif directions == ['dst', 'src']:
                # Destination IP + source port
                return analyzer.ipset_parser.check_membership(field2_ip, set_name, field1_port, protocol)
                
        else:
            if verbosity >= 2:
                print(f"      Unsupported compound match-set type: {set_type}")
            return False
            
        return False

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
            
            # Parse direction arguments for complex match-set handling
            directions = direction.split(',')
            
            # Handle match-set based on number of direction arguments
            if len(directions) == 1:
                # Simple single-field matching
                if directions[0] == 'src':
                    test_ip = src_ip
                    test_port = src_port
                elif directions[0] == 'dst':
                    test_ip = dest_ip
                    test_port = dest_port
                else:
                    if verbosity >= 2:
                        print(f"      Unknown single match-set direction: {directions[0]}")
                    continue
                    
                # Check membership in ipset
                is_member = analyzer.ipset_parser.check_membership(test_ip, set_name, test_port, protocol)
                
            elif len(directions) == 2:
                # Complex multi-field matching for hash:ip,port or hash:net,port sets
                # The order of directions must match the order in the ipset definition
                
                # Extract field values based on directions
                field1_ip, field1_port = None, None
                field2_ip, field2_port = None, None
                
                if directions[0] == 'src':
                    field1_ip, field1_port = src_ip, src_port
                elif directions[0] == 'dst':
                    field1_ip, field1_port = dest_ip, dest_port
                    
                if directions[1] == 'src':
                    field2_ip, field2_port = src_ip, src_port
                elif directions[1] == 'dst':
                    field2_ip, field2_port = dest_ip, dest_port
                
                if field1_ip is None or field2_ip is None:
                    if verbosity >= 2:
                        print(f"      Invalid multi-field match-set direction: {direction}")
                    continue
                
                # For multi-field sets, we need to check compound membership
                # This requires special handling based on the set type
                is_member = self._check_compound_match_set(
                    analyzer, set_name, directions, 
                    field1_ip, field1_port, field2_ip, field2_port, 
                    protocol, verbosity
                )
                
            else:
                if verbosity >= 2:
                    print(f"      Unsupported match-set direction with {len(directions)} fields: {direction}")
                continue
            
            if verbosity >= 2:
                if len(directions) == 1:
                    # Simple single-field output
                    port_info = f":{test_port}" if test_port is not None else ""
                    result_str = "MATCH" if is_member else "NO MATCH"
                    print(f"      Match-set check: {test_ip}{port_info}/{protocol} in {set_name} ({direction}) = {result_str}")
                else:
                    # Complex multi-field output is handled in _check_compound_match_set
                    result_str = "MATCH" if is_member else "NO MATCH"
                    print(f"      Match-set compound result: {result_str}")
            
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
    
    # Official iptables targets validated against iptables(8) man page and netfilter documentation
    # These are the targets that actually affect packet forwarding decisions
    KNOWN_TARGETS = {
        # Standard targets - affect packet fate directly
        'ACCEPT',     # Accept packet for further processing
        'DROP',       # Drop packet silently  
        'REJECT',     # Drop packet and send error response
        'RETURN',     # Return to previous chain or apply default policy
        
        # NAT targets - available in nat table, may affect routing
        'DNAT',       # Destination NAT (PREROUTING, OUTPUT chains)
        'SNAT',       # Source NAT (POSTROUTING chain)
        'MASQUERADE', # Dynamic source NAT (POSTROUTING chain)
        'REDIRECT',   # Redirect to localhost (nat table)
        
        # Logging target - non-terminating, continues processing
        'LOG',        # Log packet and continue to next rule
        
        # Connection tracking targets
        'CONNMARK',   # Set connection mark
        'MARK',       # Set packet mark
        
        # Rate limiting
        'LIMIT',      # Rate limit packets
        
        # Quality of Service
        'TOS',        # Type of Service manipulation
        'DSCP',       # Differentiated Services Code Point
        
        # Advanced targets (less common but valid)
        'ULOG',       # Userspace logging
        'NFLOG',      # Netfilter logging
        'TCPMSS',     # TCP Maximum Segment Size manipulation
        'TTL',        # Time To Live manipulation
        'HL',         # Hop Limit (IPv6)
    }
    
    def __init__(self, facts_cache_dir: str = None, router_name: str = None, verbosity: int = 0):
        # Use environment variable if facts_cache_dir not provided
        if facts_cache_dir is None:
            facts_cache_dir = os.environ.get('TRACEROUTE_SIMULATOR_FACTS', 'tsim_facts')
        
        self.facts_cache_dir = facts_cache_dir
        self.router_name = router_name
        self.verbosity = verbosity
        self.facts_file = os.path.join(facts_cache_dir, f"{router_name}.json")
        self.forward_rules = []
        self.custom_chains = {}
        self.default_policy = "ACCEPT"
        self.routing_table = []
        self.ipsets = {}
        
        # Check if unified facts file exists
        if not os.path.exists(self.facts_file):
            raise FileNotFoundError(f"Unified facts file not found: {self.facts_file}")
        
        # Load unified facts and extract relevant data
        self._load_unified_facts()
        
        # Extract iptables rules from structured format
        self._extract_iptables_rules()
        
        # Extract ipsets from structured format
        self._extract_ipsets()
        
        # Create ipset parser instance with extracted ipsets
        # Note: We pass a dummy file path since we already have structured data
        try:
            self.ipset_parser = IpsetParser("/dev/null", verbosity)  # Use /dev/null to avoid file not found warnings
        except:
            self.ipset_parser = IpsetParser("", 0)  # Fallback with no verbosity
        self.ipset_parser.ipsets = self.ipsets
        self.ipset_parser._build_lookup_sets()
        
        # Extract routing table from structured format
        self._extract_routing_table()
    
    def _load_unified_facts(self):
        """Load unified facts file containing all router information."""
        try:
            import json
            with open(self.facts_file, 'r') as f:
                self.facts = json.load(f)
            
            if self.verbosity >= 2:
                print(f"Loaded unified facts from {self.facts_file}")
                
        except (json.JSONDecodeError, Exception) as e:
            raise ValueError(f"Could not load unified facts file: {e}")
    
    def _extract_iptables_rules(self):
        """Extract iptables rules from structured firewall data."""
        if 'firewall' not in self.facts or 'iptables' not in self.facts['firewall']:
            if self.verbosity >= 1:
                print("Warning: No iptables data found in facts")
            return
        
        iptables_data = self.facts['firewall']['iptables']
        
        if not iptables_data.get('available', False):
            if self.verbosity >= 1:
                print("Warning: Iptables data marked as not available")
            return
        
        # Extract FORWARD chain rules and custom chains from structured data
        if 'filter' in iptables_data:
            filter_tables = iptables_data['filter']
            
            # Process all filter tables to extract both FORWARD rules and custom chains
            for table in filter_tables:
                # Extract FORWARD chain rules
                if 'FORWARD' in table:
                    forward_rules = table['FORWARD']
                    for rule_data in forward_rules:
                        # Convert structured rule to our internal format
                        rule = self._convert_structured_rule(rule_data)
                        if rule:
                            self.forward_rules.append(rule)
                    
                    if self.verbosity >= 2:
                        print(f"Extracted {len(forward_rules)} FORWARD rules from structured data")
                
                # Extract custom chains from all tables (not just the FORWARD table)
                for chain_name, chain_rules in table.items():
                    if chain_name not in ['INPUT', 'OUTPUT', 'FORWARD']:
                        if chain_name not in self.custom_chains:
                            self.custom_chains[chain_name] = []
                        for rule_data in chain_rules:
                            rule = self._convert_structured_rule(rule_data)
                            if rule:
                                self.custom_chains[chain_name].append(rule)
                        
                        if self.verbosity >= 2:
                            print(f"Extracted custom chain {chain_name}: {len(chain_rules)} rules")
        
        # TODO: Extract default policy from structured data
        # For now, keep ACCEPT as default
        
        if self.verbosity >= 1:
            print(f"Extracted {len(self.forward_rules)} FORWARD rules and {len(self.custom_chains)} custom chains")
    
    def _convert_structured_rule(self, rule_data: dict):
        """Convert structured rule data to IptablesRule format."""
        if not isinstance(rule_data, dict):
            if self.verbosity >= 2:
                print(f"Warning: Expected dict for rule_data, got {type(rule_data)}")
            return None
        
        # Extract basic rule information
        line_number = rule_data.get('number', 0)
        target = rule_data.get('target', 'ACCEPT')
        
        # Build rule text from structured data (similar to old iptables -L format)
        rule_parts = []
        
        # Protocol
        protocol = rule_data.get('protocol', 'all')
        if protocol and protocol != 'all':
            rule_parts.append(protocol)
        else:
            rule_parts.append('all')
        
        # Add placeholder for opt field (not used in analysis)
        rule_parts.append('--')
        
        # In interface
        in_interface = rule_data.get('in_interface', '*')
        rule_parts.append(in_interface)
        
        # Out interface
        out_interface = rule_data.get('out_interface', '*')
        rule_parts.append(out_interface)
        
        # Source
        source = rule_data.get('source', '0.0.0.0/0')
        rule_parts.append(source)
        
        # Destination  
        destination = rule_data.get('destination', '0.0.0.0/0')
        rule_parts.append(destination)
        
        # Add additional match criteria if present
        extensions = rule_data.get('extensions', {})
        
        # Handle destination ports
        if 'dport' in rule_data:
            rule_parts.append(f"dpt:{rule_data['dport']}")
        elif 'dports' in rule_data:
            rule_parts.append(f"dpts:{rule_data['dports']}")
        elif extensions and 'multiport_dports' in extensions:
            # Handle flat multiport_dports format
            dports = extensions['multiport_dports']
            if isinstance(dports, list):
                rule_parts.append(f"dpts:{','.join(dports)}")
            else:
                rule_parts.append(f"dpts:{dports}")
        elif extensions and 'multiport' in extensions and 'dports' in extensions['multiport']:
            # Handle nested multiport format  
            dports = extensions['multiport']['dports']
            if isinstance(dports, list):
                rule_parts.append(f"dpts:{','.join(dports)}")
            else:
                rule_parts.append(f"dpts:{dports}")
        
        # Handle source ports
        if 'sport' in rule_data:
            rule_parts.append(f"spt:{rule_data['sport']}")
        elif 'sports' in rule_data:
            rule_parts.append(f"spts:{rule_data['sports']}")
        elif extensions and 'multiport_sports' in extensions:
            # Handle flat multiport_sports format
            sports = extensions['multiport_sports']
            if isinstance(sports, list):
                rule_parts.append(f"spts:{','.join(sports)}")
            else:
                rule_parts.append(f"spts:{sports}")
        elif extensions and 'multiport' in extensions and 'sports' in extensions['multiport']:
            # Handle nested multiport format
            sports = extensions['multiport']['sports']
            if isinstance(sports, list):
                rule_parts.append(f"spts:{','.join(sports)}")
            else:
                rule_parts.append(f"spts:{sports}")
        
        # Handle interfaces
        if 'in_interface' in rule_data and rule_data['in_interface'] != '*':
            rule_parts.append(f"in:{rule_data['in_interface']}")
        if 'out_interface' in rule_data and rule_data['out_interface'] != '*':
            rule_parts.append(f"out:{rule_data['out_interface']}")
        
        # Handle state matching (check both direct field and extensions)
        states = rule_data.get('state') or (extensions.get('state') if extensions else None)
        if states:
            if isinstance(states, list):
                rule_parts.append(f"state {','.join(states)}")
            else:
                rule_parts.append(f"state {states}")
        
        # Handle match-set (ipset) conditions
        if extensions and 'match_sets' in extensions:
            # New enhanced format with support for complex directions
            match_sets = extensions['match_sets']
            for match_set_info in match_sets:
                set_name = match_set_info.get('set_name', '')
                direction = match_set_info.get('direction', 'src')
                if set_name:
                    rule_parts.append(f"match-set {set_name} {direction}")
        elif extensions and 'set' in extensions:
            # Legacy format support
            set_info = extensions['set']
            if isinstance(set_info, dict):
                set_name = set_info.get('name', '')
                direction = set_info.get('direction', 'src')
                if set_name:
                    rule_parts.append(f"match-set {set_name} {direction}")
            elif isinstance(set_info, str):
                rule_parts.append(f"match-set {set_info} src")
        
        # Handle comment
        if 'comment' in rule_data and rule_data['comment']:
            comment = rule_data['comment'].strip('/* */')
            rule_parts.append(f"/* {comment} */")
        
        # Join all parts to create rule text
        rule_text = ' '.join(rule_parts)
        
        # Create and return IptablesRule object
        rule = IptablesRule(line_number, rule_text, target)
        
        if self.verbosity >= 3:
            print(f"Converted structured rule {line_number}: {target} - {rule_text}")
        
        return rule
    
    def _extract_ipsets(self):
        """Extract ipset data from structured firewall data."""
        if 'firewall' not in self.facts or 'ipset' not in self.facts['firewall']:
            if self.verbosity >= 1:
                print("Warning: No ipset data found in facts")
            return
        
        ipset_data = self.facts['firewall']['ipset']
        
        if not ipset_data.get('available', False):
            if self.verbosity >= 1:
                print("Warning: Ipset data marked as not available")
            return
        
        # Extract ipset lists from structured data
        if 'lists' in ipset_data:
            ipset_lists = ipset_data['lists']
            
            for ipset_list in ipset_lists:
                for set_name, set_info in ipset_list.items():
                    self.ipsets[set_name] = {
                        'type': set_info.get('type', 'unknown'),
                        'members': set_info.get('members', [])
                    }
            
            if self.verbosity >= 2:
                print(f"Extracted {len(self.ipsets)} ipsets from structured data")
        
        if self.verbosity >= 3 and self.ipsets:
            print("\n=== EXTRACTED IPSET DATA ===")
            for set_name, set_info in self.ipsets.items():
                print(f"\nIpset: {set_name}")
                print(f"  Type: {set_info['type']}")
                print(f"  Members ({len(set_info['members'])}):")
                for i, member in enumerate(set_info['members']):
                    print(f"    [{i+1}] {member}")
            print("=== END IPSET DATA ===\n")
    
    def _extract_routing_table(self):
        """Extract routing table from structured routing data."""
        if 'routing' not in self.facts or 'tables' not in self.facts['routing']:
            if self.verbosity >= 1:
                print("Warning: No routing table data found in facts")
            return
        
        routing_tables = self.facts['routing']['tables']
        
        if isinstance(routing_tables, list):
            self.routing_table = routing_tables
            if self.verbosity >= 2:
                print(f"Extracted {len(self.routing_table)} routing entries from structured data")
        elif isinstance(routing_tables, dict) and 'parsing_error' in routing_tables:
            if self.verbosity >= 1:
                print(f"Warning: Routing table parsing error: {routing_tables['parsing_error']}")
            self.routing_table = []
        else:
            if self.verbosity >= 1:
                print("Warning: Unexpected routing table format")
            self.routing_table = []

    
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
                print(f"Default policy is {self.default_policy} - checking all rules in order")
        
        # Process rules in order - we must check ALL rules because:
        # 1. Rules are processed in order and the first match wins
        # 2. Even with ACCEPT default policy, there might be explicit DENY rules that override it
        # 3. Even with DROP/REJECT default policy, there might be explicit ACCEPT rules that override it
        rules_checked = 0
        
        for rule in self.forward_rules:
            rules_checked += 1
                
            # Skip unknown targets entirely - don't even check if the packet matches
            # This prevents misclassification since most unknown targets don't affect packet acceptance/denial
            # Check both case-insensitive known targets and case-sensitive custom chains
            if rule.target.upper() not in self.KNOWN_TARGETS and rule.target not in self.custom_chains:
                if self.verbosity >= 2:
                    print(f"  FORWARD rule {rule.line_number} has unknown target '{rule.target}' - skipping entirely (packet assumed to pass)")
                continue
            
            if rule.matches_packet(src_ip, src_port, dest_ip, dest_port, protocol, connection_state, self.verbosity, self, "FORWARD"):
                decision_info = f"FORWARD rule {rule.line_number} matches: {rule.target}"
                if self.verbosity >= 1:
                    print(f"\n{decision_info}")
                    print(f"  Rule: {rule.rule_text}")
                    # Only show packet fate decided for terminal targets, not custom chains
                    if self.verbosity >= 2 and rule.target not in self.custom_chains:
                        print(f"  *** PACKET FATE DECIDED BY THIS RULE ***")
                
                # Handle different targets (all validated against official iptables documentation)
                # Use case-insensitive comparison for known targets, case-sensitive for custom chains
                target_upper = rule.target.upper()
                
                if target_upper == "ACCEPT":
                    reason = f"Allowed by FORWARD rule {rule.line_number}: {rule.rule_text}"
                    if self.verbosity >= 1:
                        print(f"Decision: ACCEPT - {reason}")
                    if self.verbosity >= 2:
                        print(f"  *** PACKET FATE DECIDED BY THIS RULE ***")
                    return True, reason
                elif target_upper in ["DROP", "REJECT"]:
                    reason = f"Denied by FORWARD rule {rule.line_number}: {rule.rule_text}"
                    if self.verbosity >= 1:
                        print(f"Decision: {target_upper} - {reason}")
                    if self.verbosity >= 2:
                        print(f"  *** PACKET FATE DECIDED BY THIS RULE ***")
                    return False, reason
                elif target_upper == "RETURN":
                    # RETURN: jump back to previous chain or apply default policy
                    if self.verbosity >= 2:
                        print(f"  RETURN target - applying default policy")
                        print(f"  *** PACKET FATE DECIDED BY THIS RULE ***")
                    # For FORWARD chain, RETURN applies default policy
                    if self.default_policy == "ACCEPT":
                        reason = f"RETURN in FORWARD rule {rule.line_number}, applying default ACCEPT policy"
                        if self.verbosity >= 1:
                            print(f"Decision: ACCEPT (RETURN) - {reason}")
                        return True, reason
                    else:
                        reason = f"RETURN in FORWARD rule {rule.line_number}, applying default {self.default_policy} policy"
                        if self.verbosity >= 1:
                            print(f"Decision: {self.default_policy} (RETURN) - {reason}")
                        return False, reason
                elif target_upper in ["LOG", "ULOG", "NFLOG"]:
                    # Non-terminating logging targets - log and continue
                    if self.verbosity >= 2:
                        print(f"  Logging target {rule.target} - packet logged, continuing to next rule")
                    continue
                elif target_upper in ["CONNMARK", "MARK", "TOS", "DSCP", "TCPMSS", "TTL", "HL"]:
                    # Non-terminating manipulation targets - modify and continue
                    if self.verbosity >= 2:
                        print(f"  Manipulation target {rule.target} - packet modified, continuing to next rule")
                    continue
                elif target_upper in ["DNAT", "SNAT", "MASQUERADE", "REDIRECT"]:
                    # NAT targets - assume packet is accepted after NAT (typical behavior)
                    reason = f"Packet processed by NAT target {rule.target} in FORWARD rule {rule.line_number}"
                    if self.verbosity >= 1:
                        print(f"Decision: ACCEPT (NAT) - {reason}")
                    if self.verbosity >= 2:
                        print(f"  *** PACKET FATE DECIDED BY THIS RULE ***")
                    return True, reason
                elif rule.target in self.custom_chains:
                    # Follow custom chain (always check custom chains regardless of policy)
                    if self.verbosity >= 2:
                        print(f"  Following custom chain: {rule.target}")
                    result, reason = self._analyze_custom_chain(rule.target, src_ip, src_port, dest_ip, dest_port, protocol, connection_state, "FORWARD")
                    if result is not None:
                        chain_reason = f"FORWARD/{rule.target}: {reason}"
                        if self.verbosity >= 1:
                            decision = "ACCEPT" if result else "DROP/REJECT"
                            print(f"Decision: {decision} - {chain_reason}")
                        return result, chain_reason
                    # If custom chain returns, continue with next rule
                    if self.verbosity >= 2:
                        print(f"  Custom chain {rule.target} returned, continuing with next rule")
                else:
                    # This should never happen since we filter unknown targets above
                    if self.verbosity >= 2:
                        print(f"  Unexpected known target {rule.target}, treating as non-terminating")
                    continue
            elif self.verbosity >= 2:
                print(f"  Rule {rule.line_number} does not match")
        
        # No rules matched, apply default policy
        policy_decision = f"No rules matched after checking {rules_checked} rules, applying default policy: {self.default_policy}"
        
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
    
    def _analyze_custom_chain(self, chain_name: str, src_ip: str, src_port: Optional[int], dest_ip: str, dest_port: Optional[int], protocol: str, connection_state: str = 'NEW', parent_chain: str = "FORWARD") -> Tuple[Optional[bool], str]:
        """Analyze rules in a custom chain."""
        if chain_name not in self.custom_chains:
            return None, f"Custom chain {chain_name} not found"
        
        if self.verbosity >= 2:
            print(f"    Entering custom chain: {chain_name}")
        
        for rule in self.custom_chains[chain_name]:
            # Skip unknown targets entirely in custom chains too
            # Check both case-insensitive known targets and case-sensitive custom chains
            if rule.target.upper() not in self.KNOWN_TARGETS and rule.target not in self.custom_chains:
                if self.verbosity >= 2:
                    print(f"    {parent_chain}/{chain_name} rule {rule.line_number} has unknown target '{rule.target}' - skipping entirely")
                continue
            
            if rule.matches_packet(src_ip, src_port, dest_ip, dest_port, protocol, connection_state, self.verbosity, self, f"{parent_chain}/{chain_name}"):
                decision_info = f"{chain_name} rule {rule.line_number} matches: {rule.target}"
                if self.verbosity >= 1:
                    print(f"\n    {decision_info}")
                    print(f"      Rule: {rule.rule_text}")
                    # Only show packet fate decided for terminal targets, not nested custom chains
                    if self.verbosity >= 2 and rule.target not in self.custom_chains:
                        print(f"      *** PACKET FATE DECIDED BY THIS RULE ***")
                
                # Handle targets in custom chains (same logic as main chain)
                # Use case-insensitive comparison for known targets, case-sensitive for custom chains
                target_upper = rule.target.upper()
                
                if target_upper == "ACCEPT":
                    return True, f"Allowed by {parent_chain}/{chain_name} rule {rule.line_number}"
                elif target_upper in ["DROP", "REJECT"]:
                    return False, f"Denied by {parent_chain}/{chain_name} rule {rule.line_number}"
                elif target_upper == "RETURN":
                    return None, f"Returned from {parent_chain}/{chain_name} rule {rule.line_number}"
                elif target_upper in ["LOG", "ULOG", "NFLOG"]:
                    # Non-terminating logging targets - log and continue
                    if self.verbosity >= 2:
                        print(f"    Logging target {rule.target} - packet logged, continuing to next rule")
                    continue
                elif target_upper in ["CONNMARK", "MARK", "TOS", "DSCP", "TCPMSS", "TTL", "HL"]:
                    # Non-terminating manipulation targets - modify and continue
                    if self.verbosity >= 2:
                        print(f"    Manipulation target {rule.target} - packet modified, continuing to next rule")
                    continue
                elif target_upper in ["DNAT", "SNAT", "MASQUERADE", "REDIRECT"]:
                    # NAT targets - assume packet is accepted after NAT
                    return True, f"Packet processed by NAT target {rule.target} in {parent_chain}/{chain_name} rule {rule.line_number}"
                elif rule.target in self.custom_chains:
                    # Nested custom chain - recursive call
                    if self.verbosity >= 2:
                        print(f"    Following nested custom chain: {rule.target}")
                    result, reason = self._analyze_custom_chain(rule.target, src_ip, src_port, dest_ip, dest_port, protocol, connection_state, f"{parent_chain}/{chain_name}")
                    if result is not None:
                        return result, f"Nested chain {rule.target} (from {parent_chain}/{chain_name} rule {rule.line_number}): {reason}"
                    # If nested chain returns, continue with next rule
                    if self.verbosity >= 2:
                        print(f"    Nested chain {rule.target} returned, continuing in {chain_name}")
                    continue
                else:
                    # This should never happen since we filter unknown targets above
                    if self.verbosity >= 2:
                        print(f"    Unexpected known target {rule.target}, treating as non-terminating")
                    continue
        
        # No rules matched in custom chain, return to main chain
        return None, f"No matches in {parent_chain}/{chain_name}, returning to calling chain"


def main():
    """Main function to parse arguments and run analysis."""
    parser = argparse.ArgumentParser(
        description="Analyze iptables FORWARD chain rules for packet forwarding decisions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Analyze TCP packet forwarding
    python3 iptables_forward_analyzer.py -s 10.1.1.1 -sp 12345 -d 10.2.1.1 -dp 80 --router hq-gw
    
    # Analyze without port specification (protocol agnostic)
    python3 iptables_forward_analyzer.py -s 10.1.1.0/24 -d 8.8.8.8 --router hq-gw -p all
    
    # Analyze with multiple IPs and ports
    python3 iptables_forward_analyzer.py -s 10.1.1.1,10.1.1.2 -sp 80,443 -d 8.8.8.8 -dp 53 --router hq-gw -p tcp
    
    # Analyze with port ranges and basic verbose output
    python3 iptables_forward_analyzer.py -s 192.168.1.100 -sp 8000:8080 -d 10.2.1.1-10.2.1.10 -dp 443 --router hq-gw -v
    
    # Analyze with detailed verbose output (shows each rule check)
    python3 iptables_forward_analyzer.py -s 10.1.1.1 -d 8.8.8.8 --router hq-gw -vv
        """
    )
    
    parser.add_argument('-s', '--source', required=True, help='Source IP address (supports ranges and lists: 10.1.1.1,10.1.1.2 or 10.1.1.0/24)')
    parser.add_argument('-sp', '--source-port', type=str, required=False, help='Source port number (supports multiport: 80,443 or 8000:8080)')
    parser.add_argument('-d', '--dest', required=True, help='Destination IP address (supports ranges and lists: 10.1.1.1,10.1.1.2 or 10.1.1.0/24)')
    parser.add_argument('-dp', '--dest-port', type=str, required=False, help='Destination port number (supports multiport: 80,443 or 8000:8080)')
    parser.add_argument('--router', required=True, help='Router name to analyze')
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
        
        # Create analyzer and run analysis (assume NEW connections)
        analyzer = IptablesForwardAnalyzer(router_name=args.router, verbosity=args.verbose)
        allowed, reason = analyzer.analyze_packet(
            args.source, source_port, 
            args.dest, dest_port, 
            args.protocol, 'NEW'
        )
        
        if args.verbose:
            print(f"Result: {'ALLOWED' if allowed else 'DENIED'}")
        
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