#!/usr/bin/env python3
"""
process_facts.py - Convert collected facts to structured JSON format

This script processes the text-based facts collected by get_facts.sh and converts
them into a structured JSON format suitable for the traceroute simulator.

The script makes intelligent decisions about parsing:
- Fully parses routing tables and policy rules using the IP JSON wrapper
- Stores iptables and ipset information as structured text blocks for later parsing
- Processes basic system information into structured format
- Maintains section metadata for debugging and validation

Usage:
    python3 process_facts.py input_facts.txt output_facts.json
    python3 process_facts.py --help
"""

import json
import sys
import re
import argparse
from typing import Dict, List, Optional, Any
from datetime import datetime
import os

# Import the IP JSON wrapper for routing table and policy rule parsing
try:
    from ip_json_wrapper import IPCommandParser
    IP_WRAPPER_AVAILABLE = True
except ImportError:
    IP_WRAPPER_AVAILABLE = False


class FactsProcessor:
    """
    Processes collected facts and converts them to structured JSON format.
    
    This class handles the conversion of text-based facts collected from remote
    hosts into a structured JSON format. It makes intelligent decisions about
    what to parse immediately and what to leave as structured text for later
    parsing by specific Python modules.
    """
    
    def __init__(self):
        """Initialize the facts processor."""
        self.ip_parser = IPCommandParser() if IP_WRAPPER_AVAILABLE else None
        self.facts = {}
        self.sections = {}
        
    def parse_facts_file(self, facts_file: str) -> Dict[str, Any]:
        """
        Parse a facts file and extract all sections.
        
        Args:
            facts_file: Path to the facts file to parse
            
        Returns:
            Dictionary containing parsed facts in structured format
        """
        with open(facts_file, 'r') as f:
            content = f.read()
        
        self.facts = {
            'metadata': {
                'collection_timestamp': None,
                'hostname': None,
                'kernel_version': None,
                'processor_version': '1.0',
                'sections_available': []
            },
            'routing': {
                'tables': [],
                'rules': []
            },
            'network': {
                'interfaces': {},
                'interface_stats': {},
                'ip_forwarding_enabled': False
            },
            'firewall': {
                'iptables': {
                    'available': False,
                    'filter_table': '',
                    'nat_table': '',
                    'mangle_table': '',
                    'raw_config': ''
                },
                'ipset': {
                    'available': False,
                    'lists': ''
                }
            },
            'system': {
                'netfilter_modules': [],
                'connection_tracking': ''
            }
        }
        
        # Extract header information
        self._extract_header_info(content)
        
        # Parse all sections
        self._parse_sections(content)
        
        # Process each section
        self._process_routing_sections()
        self._process_network_sections()
        self._process_firewall_sections()
        self._process_system_sections()
        
        # Update metadata
        self.facts['metadata']['sections_available'] = list(self.sections.keys())
        
        return self.facts
    
    def _extract_header_info(self, content: str):
        """Extract header information from facts file."""
        lines = content.split('\n')
        for line in lines:
            if line.startswith('# Generated on:'):
                timestamp_str = line.split('# Generated on: ', 1)[1]
                self.facts['metadata']['collection_timestamp'] = timestamp_str
            elif line.startswith('# Hostname:'):
                hostname = line.split('# Hostname: ', 1)[1]
                self.facts['metadata']['hostname'] = hostname
            elif line.startswith('# Kernel:'):
                kernel = line.split('# Kernel: ', 1)[1]
                self.facts['metadata']['kernel_version'] = kernel
    
    def _parse_sections(self, content: str):
        """Parse all sections from the facts file."""
        # Find all sections using regex
        section_pattern = r'=== TSIM_SECTION_START:(\w+) ===\n(.*?)\n=== TSIM_SECTION_END:\1 ==='
        matches = re.findall(section_pattern, content, re.DOTALL)
        
        for section_name, section_content in matches:
            self.sections[section_name] = self._parse_section_content(section_content)
    
    def _parse_section_content(self, content: str) -> Dict[str, Any]:
        """Parse individual section content."""
        lines = content.split('\n')
        section_data = {
            'title': '',
            'command': '',
            'timestamp': '',
            'exit_code': 0,
            'output': ''
        }
        
        # Parse header lines
        output_lines = []
        in_output = False
        
        for line in lines:
            if line.startswith('TITLE: '):
                section_data['title'] = line.split('TITLE: ', 1)[1]
            elif line.startswith('COMMAND: '):
                section_data['command'] = line.split('COMMAND: ', 1)[1]
            elif line.startswith('TIMESTAMP: '):
                section_data['timestamp'] = line.split('TIMESTAMP: ', 1)[1]
            elif line.startswith('EXIT_CODE: '):
                try:
                    section_data['exit_code'] = int(line.split('EXIT_CODE: ', 1)[1])
                except ValueError:
                    section_data['exit_code'] = 0
            elif line == '---':
                in_output = True
            elif in_output and not line.startswith('EXIT_CODE: '):
                output_lines.append(line)
        
        section_data['output'] = '\n'.join(output_lines).strip()
        return section_data
    
    def _process_routing_sections(self):
        """Process routing-related sections."""
        # Process routing table
        if 'routing_table' in self.sections:
            section = self.sections['routing_table']
            if section['exit_code'] == 0 and self.ip_parser:
                try:
                    self.facts['routing']['tables'] = self.ip_parser.parse_route_output(section['output'])
                except Exception as e:
                    # Fallback to text storage if parsing fails
                    self.facts['routing']['tables'] = {
                        'parsing_error': str(e),
                        'raw_output': section['output']
                    }
            else:
                self.facts['routing']['tables'] = {
                    'error': 'Command failed or IP wrapper not available',
                    'exit_code': section['exit_code'],
                    'raw_output': section['output']
                }
        
        # Process policy rules
        if 'policy_rules' in self.sections:
            section = self.sections['policy_rules']
            if section['exit_code'] == 0 and self.ip_parser:
                try:
                    self.facts['routing']['rules'] = self.ip_parser.parse_rule_output(section['output'])
                except Exception as e:
                    # Fallback to text storage if parsing fails
                    self.facts['routing']['rules'] = {
                        'parsing_error': str(e),
                        'raw_output': section['output']
                    }
            else:
                self.facts['routing']['rules'] = {
                    'error': 'Command failed or IP wrapper not available',
                    'exit_code': section['exit_code'],
                    'raw_output': section['output']
                }
    
    def _process_network_sections(self):
        """Process network-related sections."""
        # Process IP forwarding status
        if 'ip_forwarding' in self.sections:
            section = self.sections['ip_forwarding']
            if section['exit_code'] == 0:
                try:
                    forwarding_value = section['output'].strip()
                    self.facts['network']['ip_forwarding_enabled'] = forwarding_value == '1'
                except:
                    self.facts['network']['ip_forwarding_enabled'] = False
        
        # Process interfaces - store as structured text for later parsing
        if 'interfaces' in self.sections:
            section = self.sections['interfaces']
            self.facts['network']['interfaces'] = {
                'command': section['command'],
                'exit_code': section['exit_code'],
                'raw_output': section['output']
            }
        
        # Process interface statistics - store as structured text
        if 'interface_stats' in self.sections:
            section = self.sections['interface_stats']
            self.facts['network']['interface_stats'] = {
                'command': section['command'],
                'exit_code': section['exit_code'],
                'raw_output': section['output']
            }
    
    def _process_firewall_sections(self):
        """Process firewall-related sections."""
        # Process iptables sections
        iptables_sections = ['iptables_filter', 'iptables_nat', 'iptables_mangle', 'iptables_save']
        iptables_available = any(section in self.sections for section in iptables_sections)
        
        self.facts['firewall']['iptables']['available'] = iptables_available
        
        if iptables_available:
            try:
                parsed_tables = self._parse_iptables_sections()
                self.facts['firewall']['iptables'].update(parsed_tables)
            except Exception as e:
                # Fallback to raw text if parsing fails
                self.facts['firewall']['iptables']['parsing_error'] = str(e)
                
                # Store raw tables as fallback
                if 'iptables_filter' in self.sections:
                    self.facts['firewall']['iptables']['filter_table_raw'] = self.sections['iptables_filter']['output']
                if 'iptables_nat' in self.sections:
                    self.facts['firewall']['iptables']['nat_table_raw'] = self.sections['iptables_nat']['output']
                if 'iptables_mangle' in self.sections:
                    self.facts['firewall']['iptables']['mangle_table_raw'] = self.sections['iptables_mangle']['output']
                if 'iptables_save' in self.sections:
                    self.facts['firewall']['iptables']['raw_config'] = self.sections['iptables_save']['output']
        
        # Process ipset information
        if 'ipset_list' in self.sections:
            section = self.sections['ipset_list']
            self.facts['firewall']['ipset']['available'] = True
            try:
                self.facts['firewall']['ipset']['lists'] = self._parse_ipset_output(section['output'])
            except Exception as e:
                # Fallback to raw text if parsing fails
                self.facts['firewall']['ipset']['lists'] = {
                    'parsing_error': str(e),
                    'raw_output': section['output']
                }
        else:
            self.facts['firewall']['ipset']['available'] = False
            self.facts['firewall']['ipset']['lists'] = []
    
    def _process_system_sections(self):
        """Process system-related sections."""
        # Process netfilter modules
        if 'netfilter_modules' in self.sections:
            section = self.sections['netfilter_modules']
            if section['exit_code'] == 0:
                # Simple parsing of lsmod output
                modules = []
                for line in section['output'].split('\n'):
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 1:
                            modules.append(parts[0])
                self.facts['system']['netfilter_modules'] = modules
        
        # Process connection tracking
        if 'conntrack' in self.sections:
            section = self.sections['conntrack']
            self.facts['system']['connection_tracking'] = section['output']
    
    def _extract_custom_chains(self, iptables_output: str) -> set:
        """
        Extract all custom chain names from iptables output.
        
        Args:
            iptables_output: Raw iptables output containing all tables
            
        Returns:
            Set of custom chain names
        """
        custom_chains = set()
        
        # Standard built-in chains that are not custom
        builtin_chains = {'INPUT', 'OUTPUT', 'FORWARD', 'PREROUTING', 'POSTROUTING'}
        
        lines = iptables_output.split('\n')
        for line in lines:
            line = line.strip()
            
            # Look for chain definitions: "Chain CHAINNAME (...)"
            if line.startswith('Chain '):
                parts = line.split()
                if len(parts) >= 2:
                    chain_name = parts[1]
                    # If not a builtin chain, it's custom
                    if chain_name not in builtin_chains:
                        custom_chains.add(chain_name)
        
        return custom_chains

    def _parse_iptables_sections(self) -> Dict[str, Any]:
        """
        Parse iptables sections into structured format.
        
        Returns:
            Dictionary containing parsed iptables tables with chains and rules
            
        Example output format:
        {
            "filter": [
                {"INPUT": ["rule1", "rule2"]},
                {"FORWARD": ["rule3", "rule4"]},
                {"LOG_DROP": ["rule5", "rule6"]}
            ],
            "nat": [
                {"PREROUTING": ["rule7"]},
                {"POSTROUTING": ["rule8"]}
            ],
            "chain_references": {
                "LOG_DROP": ["FORWARD"]
            }
        }
        """
        parsed_tables = {}
        chain_references = {}
        
        # First pass: Extract all custom chains from all tables
        all_custom_chains = set()
        table_mappings = {
            'iptables_filter': 'filter',
            'iptables_nat': 'nat', 
            'iptables_mangle': 'mangle'
        }
        
        for section_name, table_name in table_mappings.items():
            if section_name in self.sections:
                section = self.sections[section_name]
                if section['exit_code'] == 0:
                    custom_chains = self._extract_custom_chains(section['output'])
                    all_custom_chains.update(custom_chains)
        
        # Second pass: Parse individual table sections with custom chain knowledge
        for section_name, table_name in table_mappings.items():
            if section_name in self.sections:
                section = self.sections[section_name]
                if section['exit_code'] == 0:
                    chains, refs = self._parse_iptables_table(section['output'], all_custom_chains)
                    parsed_tables[table_name] = chains
                    chain_references.update(refs)
        
        # Also parse iptables-save if available for additional validation
        if 'iptables_save' in self.sections:
            section = self.sections['iptables_save']
            if section['exit_code'] == 0:
                parsed_tables['raw_config'] = section['output']
        
        # Add chain references
        if chain_references:
            parsed_tables['chain_references'] = chain_references
        
        return parsed_tables
    
    def _parse_iptables_table(self, table_output: str, custom_chains: set = None) -> tuple[List[Dict[str, List[str]]], Dict[str, List[str]]]:
        """
        Parse a single iptables table output.
        
        Args:
            table_output: Raw output from iptables -L command for a table
            custom_chains: Set of known custom chain names
            
        Returns:
            Tuple of (chains_list, chain_references)
            - chains_list: List of dictionaries with chain names as keys and rules as values
            - chain_references: Dictionary mapping custom chains to chains that reference them
        """
        chains = []
        chain_references = {}
        current_chain = None
        current_rules = []
        
        lines = table_output.split('\n')
        
        for line in lines:
            line = line.strip()
            
            if not line:
                continue
                
            # Check for chain header: "Chain CHAINNAME (policy POLICY packets bytes)"
            if line.startswith('Chain '):
                # Save previous chain if exists
                if current_chain:
                    chains.append({current_chain: current_rules})
                
                # Extract chain name
                parts = line.split()
                if len(parts) >= 2:
                    current_chain = parts[1]
                    current_rules = []
                    
                    # Check for references in chain header
                    if '(' in line and 'references)' in line:
                        # Extract reference count for custom chains
                        # This indicates other chains jump to this chain
                        pass  # We'll detect actual references when parsing rules
                        
            # Check for rule header (num   pkts bytes target ...)
            elif line.startswith('num ') or 'pkts bytes target' in line:
                # Skip header lines
                continue
                
            # Parse actual rules
            elif current_chain and line and not line.startswith('Chain'):
                # Clean up the rule line - extract rule number and stats
                rule_parts = line.split(None, 6)  # Split into max 7 parts
                
                if len(rule_parts) >= 4:
                    # Extract rule number (first part)
                    try:
                        rule_number = int(rule_parts[0])
                    except (ValueError, IndexError):
                        rule_number = 0
                    
                    # Skip rule number, packet count, byte count
                    # Keep target and everything after
                    if len(rule_parts) >= 7:
                        rule_text = ' '.join(rule_parts[3:])  # target onwards
                    else:
                        rule_text = ' '.join(rule_parts[3:])
                        
                    # Parse the rule into structured format
                    parsed_rule = self._parse_iptables_rule(rule_text, rule_number, custom_chains)
                    current_rules.append(parsed_rule)
                    
                    # Check for chain references in target
                    target = rule_parts[3] if len(rule_parts) > 3 else ''
                    if target and target not in ['ACCEPT', 'DROP', 'REJECT', 'LOG', 'DNAT', 'SNAT', 'MASQUERADE', 'RETURN']:
                        # This is likely a custom chain reference
                        if target not in chain_references:
                            chain_references[target] = []
                        if current_chain not in chain_references[target]:
                            chain_references[target].append(current_chain)
        
        # Save last chain
        if current_chain:
            chains.append({current_chain: current_rules})
        
        return chains, chain_references
    
    def _parse_iptables_rule(self, rule_text: str, rule_number: int = 0, custom_chains: set = None) -> Dict[str, Any]:
        """
        Parse a single iptables rule into structured format.
        
        Args:
            rule_text: Rule text from iptables -L output (e.g., "ACCEPT tcp -- eth0 * 10.1.0.0/16 0.0.0.0/0 tcp dpt:22")
            rule_number: Rule number from iptables -L output
            custom_chains: Set of known custom chain names
            
        Returns:
            Dictionary with rule components as structured hash (no target-as-key wrapper)
            
        Example:
        {
            "number": 1,
            "target": "ACCEPT",
            "protocol": "tcp",
            "fragments": false,
            "in_interface": "eth0",
            "out_interface": "*",
            "source": "trusted_hosts",  // match-set name instead of 0.0.0.0/0
            "destination": "0.0.0.0/0",
            "dport": "22",
            "comment": "/* allow SSH access */",
            "extensions": {}
        }
        """
        # Parse comment first if present
        comment = None
        comment_start = rule_text.find('/*')
        comment_end = rule_text.find('*/')
        
        if comment_start != -1 and comment_end != -1 and comment_end > comment_start:
            comment = rule_text[comment_start:comment_end + 2]  # Include /* and */
            # Remove comment from rule text for further parsing
            rule_text = rule_text[:comment_start] + rule_text[comment_end + 2:]
            rule_text = rule_text.strip()
        
        parts = rule_text.split()
        if len(parts) < 1:
            # Fallback for completely empty rules
            return {"number": rule_number, "raw_rule": rule_text, "parsing_error": "No parts found"}
        
        target = parts[0]
        
        # Define known targets that have specific parsing logic
        known_targets = ['ACCEPT', 'DROP', 'REJECT', 'LOG', 'RETURN', 'DNAT', 'SNAT', 'MASQUERADE']
        
        # Add custom chains to known targets
        if custom_chains:
            known_targets.extend(custom_chains)
        
        # If target is unknown, return early with unparsed definition
        if target not in known_targets:
            # Everything after target is the definition
            definition = ' '.join(parts[1:]) if len(parts) > 1 else ''
            result = {
                "number": rule_number,
                "target": target,
                "definition": definition
            }
            if comment:
                result["comment"] = comment
            return result
        
        # For known targets, we need at least 6 parts for proper parsing
        if len(parts) < 6:
            # Fallback for malformed rules with known targets
            return {"number": rule_number, "raw_rule": rule_text, "parsing_error": "Insufficient parts for known target"}
        
        protocol = parts[1]
        
        # Check for fragments flag
        fragments = False
        offset = 2
        if len(parts) > offset and parts[offset] == '-f':
            fragments = True
            offset += 1
        elif len(parts) > offset and parts[offset] == '--':
            offset += 1
        
        # Extract basic fields
        if len(parts) > offset + 3:
            in_interface = parts[offset]
            out_interface = parts[offset + 1]
            source = parts[offset + 2]
            destination = parts[offset + 3]
            offset += 4
        else:
            # Fallback for malformed rules
            return {"number": rule_number, "raw_rule": rule_text, "parsing_error": "Missing basic fields"}
        
        # Initialize rule structure
        rule_data = {
            "number": rule_number,
            "target": target,
            "protocol": protocol,
            "fragments": fragments,
            "in_interface": in_interface,
            "out_interface": out_interface,
            "source": source,
            "destination": destination,
            "state": [],
            "extensions": {}
        }
        
        # Add comment if present
        if comment:
            rule_data["comment"] = comment
        
        # Parse remaining extensions and matches
        remaining_parts = parts[offset:]
        i = 0
        while i < len(remaining_parts):
            part = remaining_parts[i]
            
            # Port options (TCP/UDP)
            if part == 'tcp' and i + 1 < len(remaining_parts):
                tcp_opts = remaining_parts[i + 1]
                if tcp_opts.startswith('dpt:'):
                    rule_data['dport'] = tcp_opts[4:]
                elif tcp_opts.startswith('spt:'):
                    rule_data['sport'] = tcp_opts[4:]
                elif tcp_opts.startswith('dpts:'):
                    rule_data['dports'] = tcp_opts[5:]
                elif tcp_opts.startswith('dports:'):
                    rule_data['dports'] = tcp_opts[7:]
                elif tcp_opts.startswith('spts:'):
                    rule_data['sports'] = tcp_opts[5:]
                elif tcp_opts.startswith('sports:'):
                    rule_data['sports'] = tcp_opts[7:]
                i += 2
                
            # UDP port options
            elif part == 'udp' and i + 1 < len(remaining_parts):
                udp_opts = remaining_parts[i + 1]
                if udp_opts.startswith('dpt:'):
                    rule_data['dport'] = udp_opts[4:]
                elif udp_opts.startswith('spt:'):
                    rule_data['sport'] = udp_opts[4:]
                elif udp_opts.startswith('dpts:'):
                    rule_data['dports'] = udp_opts[5:]
                elif udp_opts.startswith('dports:'):
                    rule_data['dports'] = udp_opts[7:]
                elif udp_opts.startswith('spts:'):
                    rule_data['sports'] = udp_opts[5:]
                elif udp_opts.startswith('sports:'):
                    rule_data['sports'] = udp_opts[7:]
                i += 2
                
            # State tracking
            elif part == 'state' and i + 1 < len(remaining_parts):
                states = remaining_parts[i + 1].split(',')
                rule_data['state'] = states
                i += 2
                
            # Match sets (ipset integration)
            elif part == 'match-set' and i + 2 < len(remaining_parts):
                set_name = remaining_parts[i + 1]
                direction = remaining_parts[i + 2]
                
                # Replace source or destination with match-set name based on direction
                if direction == 'src':
                    # Replace source field with match-set name
                    rule_data['source'] = set_name
                elif direction == 'dst':
                    # Replace destination field with match-set name
                    rule_data['destination'] = set_name
                # Note: Other directions like 'src,dst' could be handled here if needed
                
                i += 3
                
            # Multiport
            elif part == 'multiport' and i + 1 < len(remaining_parts):
                multiport_type = remaining_parts[i + 1]
                multiport_ports = None
                
                # Handle different multiport formats
                if multiport_type.startswith('dpts:'):
                    # Format: multiport dpts:22,80,443
                    ports_str = multiport_type[5:]
                    multiport_ports = ports_str.split(',')
                    rule_data['extensions']['multiport_dports'] = multiport_ports
                    i += 2
                elif multiport_type.startswith('sports:'):
                    # Format: multiport sports:1024,2048,3072
                    ports_str = multiport_type[7:]
                    multiport_ports = ports_str.split(',')
                    rule_data['extensions']['multiport_sports'] = multiport_ports
                    i += 2
                elif multiport_type == 'dports' and i + 2 < len(remaining_parts):
                    # Format: multiport dports 22,80,443
                    ports_str = remaining_parts[i + 2]
                    multiport_ports = ports_str.split(',')
                    rule_data['extensions']['multiport_dports'] = multiport_ports
                    i += 3
                elif multiport_type == 'sports' and i + 2 < len(remaining_parts):
                    # Format: multiport sports 1024,2048,3072
                    ports_str = remaining_parts[i + 2]
                    multiport_ports = ports_str.split(',')
                    rule_data['extensions']['multiport_sports'] = multiport_ports
                    i += 3
                elif multiport_type == 'ports' and i + 2 < len(remaining_parts):
                    # Format: multiport ports 22,80,443 (both source and destination)
                    ports_str = remaining_parts[i + 2]
                    multiport_ports = ports_str.split(',')
                    rule_data['extensions']['multiport_ports'] = multiport_ports
                    i += 3
                else:
                    # Unknown multiport format, store as is
                    rule_data['extensions']['multiport_unknown'] = multiport_type
                    i += 2
                
            # LOG options
            elif part == 'LOG' and target == 'LOG':
                log_opts = {}
                j = i + 1
                while j < len(remaining_parts):
                    if remaining_parts[j] == 'flags' and j + 1 < len(remaining_parts):
                        log_opts['flags'] = remaining_parts[j + 1]
                        j += 2
                    elif remaining_parts[j] == 'level' and j + 1 < len(remaining_parts):
                        log_opts['level'] = remaining_parts[j + 1]
                        j += 2
                    elif remaining_parts[j] == 'prefix' and j + 1 < len(remaining_parts):
                        # Handle quoted prefixes
                        prefix = remaining_parts[j + 1]
                        if prefix.startswith('"') and not prefix.endswith('"'):
                            # Multi-word prefix, collect until closing quote
                            k = j + 2
                            while k < len(remaining_parts) and not remaining_parts[k - 1].endswith('"'):
                                prefix += ' ' + remaining_parts[k]
                                k += 1
                            j = k
                        else:
                            j += 2
                        log_opts['prefix'] = prefix.strip('"')
                    else:
                        j += 1
                rule_data['extensions']['log'] = log_opts
                i = j
                
            # DNAT/SNAT options
            elif part.startswith('to:'):
                if ':' in part and len(part) > 3:
                    rule_data['extensions']['to'] = part[3:]  # Remove 'to:' prefix
                elif i + 1 < len(remaining_parts):
                    rule_data['extensions']['to'] = remaining_parts[i + 1]
                    i += 1
                i += 1
                
            # Reject options
            elif part == 'reject-with' and i + 1 < len(remaining_parts):
                rule_data['extensions']['reject_with'] = remaining_parts[i + 1]
                i += 2
                
            # Limit options
            elif part == 'limit:' and i + 1 < len(remaining_parts):
                limit_opts = {}
                j = i + 1
                while j < len(remaining_parts) and not remaining_parts[j].endswith(':'):
                    if remaining_parts[j] == 'avg' and j + 1 < len(remaining_parts):
                        limit_opts['avg'] = remaining_parts[j + 1]
                        j += 2
                    elif remaining_parts[j] == 'burst' and j + 1 < len(remaining_parts):
                        limit_opts['burst'] = remaining_parts[j + 1]
                        j += 2
                    else:
                        j += 1
                rule_data['extensions']['limit'] = limit_opts
                i = j
                
            # Time options
            elif part == 'time:' and i + 1 < len(remaining_parts):
                time_opts = {}
                j = i + 1
                while j < len(remaining_parts) and not remaining_parts[j].endswith(':'):
                    if remaining_parts[j] == 'timestart' and j + 1 < len(remaining_parts):
                        time_opts['timestart'] = remaining_parts[j + 1]
                        j += 2
                    elif remaining_parts[j] == 'timestop' and j + 1 < len(remaining_parts):
                        time_opts['timestop'] = remaining_parts[j + 1]
                        j += 2
                    elif remaining_parts[j] == 'weekdays' and j + 1 < len(remaining_parts):
                        time_opts['weekdays'] = remaining_parts[j + 1].split(',')
                        j += 2
                    else:
                        j += 1
                rule_data['extensions']['time'] = time_opts
                i = j
                
            # Mark options
            elif part == 'mark' and i + 1 < len(remaining_parts):
                if remaining_parts[i + 1] == 'match' and i + 2 < len(remaining_parts):
                    rule_data['extensions']['mark_match'] = remaining_parts[i + 2]
                    i += 3
                else:
                    # Store mark verbatim if not in expected format
                    rule_data['extensions']['mark'] = 'mark'
                    i += 1
                    
            # Length options
            elif part == 'length' and i + 1 < len(remaining_parts):
                rule_data['extensions']['length'] = remaining_parts[i + 1]
                i += 2
                
            # Recent options
            elif part == 'recent:' and i + 1 < len(remaining_parts):
                recent_opts = {}
                j = i + 1
                while j < len(remaining_parts) and not remaining_parts[j].endswith(':'):
                    if remaining_parts[j] == 'SET' and j + 1 < len(remaining_parts):
                        recent_opts['action'] = 'SET'
                        j += 1
                    elif remaining_parts[j] == 'name:' and j + 1 < len(remaining_parts):
                        recent_opts['name'] = remaining_parts[j + 1]
                        j += 2
                    elif remaining_parts[j] == 'side:' and j + 1 < len(remaining_parts):
                        recent_opts['side'] = remaining_parts[j + 1]
                        j += 2
                    else:
                        j += 1
                rule_data['extensions']['recent'] = recent_opts
                i = j
                
            # DSCP options
            elif part == 'DSCP' and i + 1 < len(remaining_parts):
                if remaining_parts[i + 1] == 'set' and i + 2 < len(remaining_parts):
                    rule_data['extensions']['dscp_set'] = remaining_parts[i + 2]
                    i += 3
                else:
                    # Store DSCP verbatim if not in expected format
                    rule_data['extensions']['DSCP'] = 'DSCP'
                    i += 1
                    
            # Redirect options
            elif part == 'redir' and i + 1 < len(remaining_parts):
                if remaining_parts[i + 1] == 'ports' and i + 2 < len(remaining_parts):
                    rule_data['extensions']['redirect_ports'] = remaining_parts[i + 2]
                    i += 3
                else:
                    # Store redir verbatim if not in expected format
                    rule_data['extensions']['redir'] = 'redir'
                    i += 1
                    
            # ICMP type options (icmptype extension)
            elif part == 'icmptype' and i + 1 < len(remaining_parts):
                icmp_type_value = remaining_parts[i + 1]
                rule_data['extensions']['icmptype'] = icmp_type_value
                i += 2
                
            # PKTTYPE extension
            elif part == 'PKTTYPE' and i + 2 < len(remaining_parts) and remaining_parts[i + 1] == '=':
                pkttype_value = remaining_parts[i + 2]
                rule_data['extensions']['PKTTYPE'] = pkttype_value
                i += 3
                
            # Skip malformed PKTTYPE (PKTTYPE without proper = value format)
            elif part == 'PKTTYPE':
                # Skip malformed PKTTYPE to avoid generic parsing
                i += 1
                    
            else:
                # Unknown extension, store rest of rule as unparsed definition
                if part not in rule_data['extensions']:
                    # Store everything from current position to end as unparsed string
                    unparsed_definition = ' '.join(remaining_parts[i:])
                    rule_data['extensions'][part] = unparsed_definition
                    # Stop parsing - rest is handled as unparsed
                    break
                i += 1
        
        # Clean up empty sections
        if not rule_data['state']:
            del rule_data['state']
        if not rule_data['extensions']:
            del rule_data['extensions']
        
        return rule_data
    
    def _parse_ipset_output(self, ipset_output: str) -> List[Dict[str, Dict[str, Any]]]:
        """
        Parse ipset list output into structured JSON format.
        
        Args:
            ipset_output: Raw output from 'ipset list' command
            
        Returns:
            List of dictionaries where each element has:
            - Key: ipset name
            - Value: Dictionary with properties (type, revision, header, etc.)
            
        Example output format:
        [
            {
                "blacklist_ips": {
                    "type": "hash:ip",
                    "revision": "4",
                    "header": "family inet hashsize 1024 maxelem 65536",
                    "size_in_memory": "96",
                    "references": "1", 
                    "number_of_entries": "3",
                    "members": ["192.168.1.100", "10.0.0.5", "172.16.0.10"]
                }
            }
        ]
        """
        ipsets = []
        current_ipset = None
        current_name = None
        members = []
        in_members_section = False
        
        for line in ipset_output.split('\n'):
            line = line.strip()
            
            if not line:
                # Empty line - end current ipset if we have one
                if current_ipset and current_name:
                    current_ipset['members'] = members
                    ipsets.append({current_name: current_ipset})
                    current_ipset = None
                    current_name = None
                    members = []
                    in_members_section = False
                continue
            
            if line.startswith('Name: '):
                # Start of new ipset - save previous one if exists
                if current_ipset and current_name:
                    current_ipset['members'] = members
                    ipsets.append({current_name: current_ipset})
                
                # Initialize new ipset
                current_name = line.split('Name: ', 1)[1]
                current_ipset = {}
                members = []
                in_members_section = False
                
            elif line.startswith('Type: ') and current_ipset is not None:
                current_ipset['type'] = line.split('Type: ', 1)[1]
                
            elif line.startswith('Revision: ') and current_ipset is not None:
                current_ipset['revision'] = line.split('Revision: ', 1)[1]
                
            elif line.startswith('Header: ') and current_ipset is not None:
                current_ipset['header'] = line.split('Header: ', 1)[1]
                
            elif line.startswith('Size in memory: ') and current_ipset is not None:
                current_ipset['size_in_memory'] = line.split('Size in memory: ', 1)[1]
                
            elif line.startswith('References: ') and current_ipset is not None:
                current_ipset['references'] = line.split('References: ', 1)[1]
                
            elif line.startswith('Number of entries: ') and current_ipset is not None:
                current_ipset['number_of_entries'] = line.split('Number of entries: ', 1)[1]
                
            elif line == 'Members:':
                in_members_section = True
                
            elif in_members_section and current_ipset is not None:
                # This is a member entry
                members.append(line)
        
        # Handle last ipset if file doesn't end with empty line
        if current_ipset and current_name:
            current_ipset['members'] = members
            ipsets.append({current_name: current_ipset})
        
        return ipsets


def main():
    """Main entry point for the facts processor."""
    parser = argparse.ArgumentParser(
        description='Convert collected facts to structured JSON format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 process_facts.py facts.txt facts.json
    python3 process_facts.py --validate facts.json
        """
    )
    
    parser.add_argument('input_file', help='Input facts file to process')
    parser.add_argument('output_file', nargs='?', help='Output JSON file to create')
    parser.add_argument('--validate', action='store_true', 
                        help='Validate existing JSON file instead of processing facts')
    parser.add_argument('--pretty', action='store_true',
                        help='Pretty-print JSON output with indentation')
    
    args = parser.parse_args()
    
    if args.validate:
        # Validate existing JSON file
        try:
            with open(args.input_file, 'r') as f:
                facts = json.load(f)
            print(f"JSON file {args.input_file} is valid")
            print(f"Hostname: {facts.get('metadata', {}).get('hostname', 'unknown')}")
            print(f"Sections: {len(facts.get('metadata', {}).get('sections_available', []))}")
            return 0
        except Exception as e:
            print(f"Error validating JSON file: {e}")
            return 1
    
    if not args.output_file:
        print("Error: output_file is required when not using --validate")
        return 1
    
    if not IP_WRAPPER_AVAILABLE:
        print("Warning: IP JSON wrapper not available - routing data will be stored as raw text")
    
    try:
        processor = FactsProcessor()
        facts = processor.parse_facts_file(args.input_file)
        
        # Write JSON output
        with open(args.output_file, 'w') as f:
            if args.pretty:
                json.dump(facts, f, indent=2, sort_keys=True)
            else:
                json.dump(facts, f)
        
        print(f"Successfully processed facts from {args.input_file}")
        print(f"Output written to {args.output_file}")
        print(f"Hostname: {facts['metadata']['hostname']}")
        print(f"Sections processed: {len(facts['metadata']['sections_available'])}")
        
        return 0
        
    except Exception as e:
        print(f"Error processing facts: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())