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
- Handles multiple text encodings gracefully (UTF-8, Latin-1, ISO-8859-1, CP1252)

Usage:
    python3 process_facts.py input_facts.txt output_facts.json
    python3 process_facts.py --verbose input_facts.txt output_facts.json
    python3 process_facts.py --raw input_facts.txt output_facts.json
    python3 process_facts.py --pretty input_facts.txt output_facts.json
    python3 process_facts.py --help

Text Encoding Support:
    The script automatically detects and handles various text encodings commonly
    found in different Linux distributions and system configurations:
    - UTF-8 (preferred)
    - Latin-1/ISO-8859-1 (common in European systems)
    - CP1252 (Windows systems)
    - Falls back to UTF-8 with character replacement as last resort
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
    
    def __init__(self, verbose: bool = False, store_raw: bool = False):
        """Initialize the facts processor."""
        self.ip_parser = IPCommandParser() if IP_WRAPPER_AVAILABLE else None
        self.facts = {}
        self.sections = {}
        self.verbose = verbose
        self.store_raw = store_raw
        
    def parse_facts_file(self, facts_file: str) -> Dict[str, Any]:
        """
        Parse a facts file and extract all sections.
        
        Args:
            facts_file: Path to the facts file to parse
            
        Returns:
            Dictionary containing parsed facts in structured format
        """
        # Try multiple encodings to handle different character sets
        encodings_to_try = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'utf-8-sig']
        content = None
        encoding_used = None
        
        for encoding in encodings_to_try:
            try:
                with open(facts_file, 'r', encoding=encoding) as f:
                    content = f.read()
                encoding_used = encoding
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            # Last resort: read as binary and replace problematic characters
            try:
                with open(facts_file, 'rb') as f:
                    raw_content = f.read()
                content = raw_content.decode('utf-8', errors='replace')
                encoding_used = 'utf-8-with-replacement'
            except Exception as e:
                raise ValueError(f"Could not read facts file with any encoding: {e}")
        
        # Log encoding used for debugging
        if self.verbose:
            print(f"Successfully read {facts_file} using encoding: {encoding_used}")
            if encoding_used in ['utf-8-with-replacement']:
                print(f"Warning: Some characters were replaced due to encoding issues")
        
        # Initialize facts structure - conditionally include raw fields
        iptables_data = {
            'available': False,
            'filter_table': '',
            'nat_table': '',
            'mangle_table': ''
        }
        if self.store_raw:
            iptables_data['raw_config'] = ''
        
        ipset_data = {
            'available': False,
            'lists': ''
        }
        
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
                'iptables': iptables_data,
                'ipset': ipset_data
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
        # Process routing tables - look for all routing_table_* sections
        all_routing_entries = []
        routing_errors = []
        
        # Find all routing table sections (using numeric IDs, with 'main' as special case)
        routing_table_sections = {name: section for name, section in self.sections.items() 
                                if name.startswith('routing_table_')}
        
        if routing_table_sections:
            for section_name, section in routing_table_sections.items():
                # Extract table ID: routing_table_main -> main, routing_table_220 -> 220
                table_id = section_name.replace('routing_table_', '')
                
                if section['exit_code'] == 0 and self.ip_parser:
                    try:
                        # Parse this routing table's entries
                        table_entries = self.ip_parser.parse_route_output(section['output'])
                        # Add table ID to each entry for identification
                        for entry in table_entries:
                            if isinstance(entry, dict):
                                entry['table'] = table_id
                        all_routing_entries.extend(table_entries)
                    except Exception as e:
                        # Track parsing errors but continue with other tables
                        routing_errors.append({
                            'table': table_id,
                            'error': str(e),
                            'section': section_name
                        })
                        if self.store_raw:
                            routing_errors[-1]['raw_output'] = section['output']
                else:
                    # Track failed sections
                    routing_errors.append({
                        'table': table_id,
                        'error': 'Command failed or IP wrapper not available',
                        'exit_code': section['exit_code'],
                        'section': section_name
                    })
                    if self.store_raw:
                        routing_errors[-1]['raw_output'] = section['output']
            
            # Store results
            self.facts['routing']['tables'] = all_routing_entries
            if routing_errors:
                self.facts['routing']['table_errors'] = routing_errors
                
        else:
            # No routing table sections found
            self.facts['routing']['tables'] = []
        
        # Process routing table names mapping
        if 'rt_tables' in self.sections:
            section = self.sections['rt_tables']
            if section['exit_code'] == 0:
                try:
                    # Parse rt_tables file to get table ID to name mapping
                    table_mapping = {}
                    for line in section['output'].split('\n'):
                        line = line.strip()
                        if line and not line.startswith('#'):
                            parts = line.split(None, 1)  # Split on whitespace, max 2 parts
                            if len(parts) >= 2:
                                table_id = parts[0]
                                table_name = parts[1]
                                table_mapping[table_id] = table_name
                    self.facts['routing']['table_names'] = table_mapping
                except Exception as e:
                    self.facts['routing']['table_names'] = {'error': str(e)}
                    if self.store_raw:
                        self.facts['routing']['table_names']['raw_output'] = section['output']
            else:
                self.facts['routing']['table_names'] = {'error': 'rt_tables file not accessible'}
        else:
            self.facts['routing']['table_names'] = {}
        
        # Process policy rules
        if 'policy_rules' in self.sections:
            section = self.sections['policy_rules']
            if section['exit_code'] == 0 and self.ip_parser:
                try:
                    self.facts['routing']['rules'] = self.ip_parser.parse_rule_output(section['output'])
                except Exception as e:
                    # Fallback to text storage if parsing fails
                    fallback_data = {
                        'parsing_error': str(e)
                    }
                    if self.store_raw:
                        fallback_data['raw_output'] = section['output']
                    self.facts['routing']['rules'] = fallback_data
            else:
                error_data = {
                    'error': 'Command failed or IP wrapper not available',
                    'exit_code': section['exit_code']
                }
                if self.store_raw:
                    error_data['raw_output'] = section['output']
                self.facts['routing']['rules'] = error_data
    
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
        
        # Process interfaces - parse interface data into structured format
        if 'interfaces' in self.sections:
            section = self.sections['interfaces']
            if section['exit_code'] == 0:
                try:
                    parsed_interfaces = self._parse_interfaces_output(section['output'])
                    self.facts['network']['interfaces'] = {
                        'command': section['command'],
                        'exit_code': section['exit_code'],
                        'parsed': parsed_interfaces
                    }
                    if self.store_raw:
                        self.facts['network']['interfaces']['raw_output'] = section['output']
                except Exception as e:
                    # Fallback to basic metadata if parsing fails
                    interface_data = {
                        'command': section['command'],
                        'exit_code': section['exit_code'],
                        'parsing_error': str(e)
                    }
                    if self.store_raw:
                        interface_data['raw_output'] = section['output']
                    self.facts['network']['interfaces'] = interface_data
            else:
                # Command failed
                interface_data = {
                    'command': section['command'],
                    'exit_code': section['exit_code'],
                    'error': 'Command failed'
                }
                if self.store_raw:
                    interface_data['raw_output'] = section['output']
                self.facts['network']['interfaces'] = interface_data
        
        # Process interface statistics - conditionally store raw data
        if 'interface_stats' in self.sections:
            section = self.sections['interface_stats']
            stats_data = {
                'command': section['command'],
                'exit_code': section['exit_code']
            }
            if self.store_raw:
                stats_data['raw_output'] = section['output']
            self.facts['network']['interface_stats'] = stats_data
    
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
                
                # Store raw tables as fallback only if --raw specified
                if self.store_raw:
                    if 'iptables_filter' in self.sections:
                        self.facts['firewall']['iptables']['filter_table_raw'] = self.sections['iptables_filter']['output']
                    if 'iptables_nat' in self.sections:
                        self.facts['firewall']['iptables']['nat_table_raw'] = self.sections['iptables_nat']['output']
                    if 'iptables_mangle' in self.sections:
                        self.facts['firewall']['iptables']['mangle_table_raw'] = self.sections['iptables_mangle']['output']
                    if 'iptables_save' in self.sections:
                        self.facts['firewall']['iptables']['raw_config'] = self.sections['iptables_save']['output']
        
        # Process ipset information - prefer ipset_save over ipset_list
        if 'ipset_save' in self.sections:
            section = self.sections['ipset_save']
            self.facts['firewall']['ipset']['available'] = True
            try:
                self.facts['firewall']['ipset']['lists'] = self._parse_ipset_save_output(section['output'])
            except Exception as e:
                # Fallback to ipset_list if save parsing fails
                if 'ipset_list' in self.sections:
                    try:
                        self.facts['firewall']['ipset']['lists'] = self._parse_ipset_output(self.sections['ipset_list']['output'])
                    except:
                        fallback_data = {
                            'parsing_error': f"Both ipset_save and ipset_list parsing failed: {str(e)}"
                        }
                        if self.store_raw:
                            fallback_data['raw_output'] = section['output']
                        self.facts['firewall']['ipset']['lists'] = fallback_data
                else:
                    fallback_data = {
                        'parsing_error': str(e)
                    }
                    if self.store_raw:
                        fallback_data['raw_output'] = section['output']
                    self.facts['firewall']['ipset']['lists'] = fallback_data
        elif 'ipset_list' in self.sections:
            section = self.sections['ipset_list']
            self.facts['firewall']['ipset']['available'] = True
            try:
                self.facts['firewall']['ipset']['lists'] = self._parse_ipset_output(section['output'])
            except Exception as e:
                # Fallback to raw text if parsing fails
                fallback_data = {
                    'parsing_error': str(e)
                }
                if self.store_raw:
                    fallback_data['raw_output'] = section['output']
                self.facts['firewall']['ipset']['lists'] = fallback_data
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
            if self.store_raw:
                self.facts['system']['connection_tracking'] = section['output']
            else:
                # Only store basic status when not storing raw
                self.facts['system']['connection_tracking'] = 'available' if section['exit_code'] == 0 else 'unavailable'
    
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
        
        # Always prefer iptables-save if available as it contains complete rule sets
        if 'iptables_save' in self.sections:
            section = self.sections['iptables_save']
            if section['exit_code'] == 0:
                save_tables, save_refs = self._parse_iptables_save(section['output'])
                parsed_tables.update(save_tables)
                chain_references.update(save_refs)
        # Only use individual table sections as fallback if iptables-save not available
        elif not parsed_tables:
            # Individual table sections may miss rules or entire tables (like raw)
            pass  # parsed_tables already populated above
        
        # Also parse iptables-save if available for additional validation/raw config
        if 'iptables_save' in self.sections and self.store_raw:
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
        
        # Store raw rule text if requested
        if self.store_raw:
            rule_data["raw_rule_text"] = rule_text
        
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
                
            # Match sets (ipset integration) - handle both formats from iptables -L
            elif part == 'match-set' and i + 2 < len(remaining_parts):
                set_name = remaining_parts[i + 1]
                direction = remaining_parts[i + 2]
                
                # Parse match-set direction arguments (can be complex like src,dst or src,src)
                directions = direction.split(',')
                
                # Store match-set information in extensions for proper handling
                if 'match_sets' not in rule_data['extensions']:
                    rule_data['extensions']['match_sets'] = []
                
                match_set_info = {
                    'set_name': set_name,
                    'direction': direction,
                    'parsed_directions': directions
                }
                rule_data['extensions']['match_sets'].append(match_set_info)
                
                # Note: We do NOT replace source/destination fields with set names
                # The analyzer needs to check ipset membership, not string matching
                # All match-set logic is handled via the extensions.match_sets data
                
                i += 3
                
            # Alternative match-set format that might appear in some iptables outputs
            elif (part.startswith('match-set') or part == 'set') and i + 2 < len(remaining_parts):
                # Handle cases where match-set appears as a single word or as 'set'
                if part == 'set':
                    # Format: "set SET_NAME direction"
                    set_name = remaining_parts[i + 1] 
                    direction = remaining_parts[i + 2]
                else:
                    # Could be match-set:SET_NAME:direction or similar variants
                    if ':' in part:
                        # Parse match-set:SET_NAME:direction format
                        parts_split = part.split(':')
                        if len(parts_split) >= 3:
                            set_name = parts_split[1]
                            direction = parts_split[2]
                            # Skip the next parts since they're included in this one
                            i += 1
                        else:
                            # Fallback to normal parsing
                            set_name = remaining_parts[i + 1] if i + 1 < len(remaining_parts) else ''
                            direction = remaining_parts[i + 2] if i + 2 < len(remaining_parts) else ''
                            i += 3
                    else:
                        set_name = remaining_parts[i + 1] if i + 1 < len(remaining_parts) else ''
                        direction = remaining_parts[i + 2] if i + 2 < len(remaining_parts) else ''
                        i += 3
                
                if set_name and direction:
                    # Parse directions
                    directions = direction.split(',')
                    
                    # Store match-set information in extensions
                    if 'match_sets' not in rule_data['extensions']:
                        rule_data['extensions']['match_sets'] = []
                    
                    match_set_info = {
                        'set_name': set_name,
                        'direction': direction,
                        'parsed_directions': directions
                    }
                    rule_data['extensions']['match_sets'].append(match_set_info)
                else:
                    i += 1
                
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
            
            # Handle IP ranges in source/destination
            elif part == 'source' and i + 3 < len(remaining_parts) and remaining_parts[i + 1] == 'IP' and remaining_parts[i + 2] == 'range':
                # Format: "source IP range 10.1.1.1-10.1.1.10"
                ip_range = remaining_parts[i + 3]
                rule_data['source'] = ip_range
                i += 4
                
            elif part == 'destination' and i + 3 < len(remaining_parts) and remaining_parts[i + 1] == 'IP' and remaining_parts[i + 2] == 'range':
                # Format: "destination IP range 10.1.1.1-10.1.1.10"
                ip_range = remaining_parts[i + 3]
                rule_data['destination'] = ip_range
                i += 4
                
            # Handle complex multiport expressions directly
            elif part == 'dpt:' or part.startswith('dpt:'):
                # Handle destination port
                if part == 'dpt:' and i + 1 < len(remaining_parts):
                    rule_data['dport'] = remaining_parts[i + 1]
                    i += 2
                else:
                    rule_data['dport'] = part[4:]  # Remove 'dpt:' prefix
                    i += 1
                    
            elif part == 'spt:' or part.startswith('spt:'):
                # Handle source port  
                if part == 'spt:' and i + 1 < len(remaining_parts):
                    rule_data['sport'] = remaining_parts[i + 1]
                    i += 2
                else:
                    rule_data['sport'] = part[4:]  # Remove 'spt:' prefix
                    i += 1
                    
            elif part == 'dpts:' or part.startswith('dpts:'):
                # Handle destination ports (multiport)
                if part == 'dpts:' and i + 1 < len(remaining_parts):
                    rule_data['dports'] = remaining_parts[i + 1]
                    i += 2
                else:
                    rule_data['dports'] = part[5:]  # Remove 'dpts:' prefix
                    i += 1
                    
            elif part == 'spts:' or part.startswith('spts:'):
                # Handle source ports (multiport)
                if part == 'spts:' and i + 1 < len(remaining_parts):
                    rule_data['sports'] = remaining_parts[i + 1]
                    i += 2
                else:
                    rule_data['sports'] = part[5:]  # Remove 'spts:' prefix
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
        
        # Post-process complex unparsed extensions (for rules that were already incorrectly parsed)
        self._post_process_complex_extensions(rule_data)
        
        # Clean up empty sections
        if not rule_data['state']:
            del rule_data['state']
        if not rule_data['extensions']:
            del rule_data['extensions']
        
        return rule_data
    
    def _post_process_complex_extensions(self, rule_data: Dict[str, Any]):
        """
        Post-process complex unparsed extensions to extract IP ranges, multiport, and state information.
        
        This handles cases where complex text like "destination IP range 10.1.1.1-10.1.1.10 multiport dports 80,443 state NEW"
        was stored as an unparsed extension and needs to be properly parsed.
        """
        if 'extensions' not in rule_data:
            return
            
        extensions = rule_data['extensions']
        
        # Look for complex unparsed destination or source extensions
        for key, value in list(extensions.items()):
            if isinstance(value, str) and ('IP range' in value or 'multiport' in value or 'state ' in value):
                # Parse complex extension text
                parts = value.split()
                i = 0
                
                while i < len(parts):
                    # Handle IP range parsing
                    if i + 3 < len(parts) and parts[i] == 'IP' and parts[i+1] == 'range':
                        ip_range = parts[i+2]
                        # Update the appropriate field based on extension key
                        if key in ['destination', 'dest']:
                            rule_data['destination'] = ip_range
                        elif key in ['source', 'src']:
                            rule_data['source'] = ip_range
                        i += 3
                        
                    # Handle multiport parsing
                    elif i + 2 < len(parts) and parts[i] == 'multiport':
                        port_type = parts[i+1]  # dports, sports, ports
                        ports = parts[i+2] if i+2 < len(parts) else ''
                        
                        # Store multiport information
                        if port_type == 'dports':
                            rule_data['dports'] = ports
                        elif port_type == 'sports':
                            rule_data['sports'] = ports
                        elif port_type == 'ports':
                            # Both source and destination ports
                            rule_data['ports'] = ports
                            
                        i += 3
                        
                    # Handle state parsing
                    elif i + 1 < len(parts) and parts[i] == 'state':
                        states = parts[i+1].split(',')
                        rule_data['state'] = states
                        i += 2
                        
                    else:
                        i += 1
                
                # Remove the unparsed extension since we've processed it
                del extensions[key]
    
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

    def _parse_ipset_save_output(self, ipset_save_output: str) -> List[Dict[str, Dict[str, Any]]]:
        """
        Parse ipset save output into structured JSON format.
        
        Args:
            ipset_save_output: Raw output from 'ipset save' command
            
        Returns:
            List of dictionaries where each element has:
            - Key: ipset name
            - Value: Dictionary with properties (type, members, etc.)
            
        Example input:
            create SET_NAME hash:ip family inet hashsize 1024 maxelem 65536
            add SET_NAME 192.168.1.1
            add SET_NAME 192.168.1.2
            
        Example output:
        [
            {
                "SET_NAME": {
                    "type": "hash:ip",
                    "header": "family inet hashsize 1024 maxelem 65536",
                    "members": ["192.168.1.1", "192.168.1.2"]
                }
            }
        ]
        """
        ipsets = {}
        
        for line in ipset_save_output.split('\n'):
            line = line.strip()
            
            if not line:
                continue
                
            if line.startswith('create '):
                # Parse create line: create SET_NAME hash:ip family inet hashsize 1024 maxelem 65536
                parts = line.split(' ', 3)  # Split into max 4 parts: ['create', 'SET_NAME', 'hash:ip', 'family inet hashsize 1024 maxelem 65536']
                if len(parts) >= 3:
                    set_name = parts[1]
                    set_type = parts[2]
                    header = parts[3] if len(parts) > 3 else ""
                    
                    ipsets[set_name] = {
                        'type': set_type,
                        'header': header,
                        'members': []
                    }
                    
            elif line.startswith('add '):
                # Parse add line: add SET_NAME 192.168.1.1
                parts = line.split(' ', 2)  # Split into max 3 parts: ['add', 'SET_NAME', '192.168.1.1']
                if len(parts) >= 3:
                    set_name = parts[1]
                    member = parts[2]
                    
                    if set_name in ipsets:
                        ipsets[set_name]['members'].append(member)
        
        # Convert to the expected format (list of single-key dictionaries)
        result = []
        for set_name, set_data in ipsets.items():
            result.append({set_name: set_data})
        
        return result

    def _parse_iptables_save(self, iptables_save_output: str) -> tuple[Dict[str, List[Dict[str, List[str]]]], Dict[str, List[str]]]:
        """
        Parse iptables-save output into structured format.
        
        Args:
            iptables_save_output: Raw iptables-save output containing all tables
            
        Returns:
            Tuple of (parsed_tables, chain_references)
            
        The iptables-save format looks like:
        # Generated by iptables-save v1.8.7 on Fri Jun 21 15:18:34 2025
        *filter
        :INPUT ACCEPT [567:98542]
        :FORWARD DROP [0:0]
        :CUSTOM_CHAIN - [0:0]
        -A FORWARD -i eth0 -o eth1 -j ACCEPT
        -A CUSTOM_CHAIN -j LOG
        COMMIT
        *nat
        :PREROUTING ACCEPT [0:0]
        :OUTPUT ACCEPT [0:0]
        COMMIT
        """
        parsed_tables = {}
        chain_references = {}
        current_table = None
        current_chains = {}
        all_custom_chains = set()
        
        # Standard built-in chains per table
        builtin_chains = {
            'filter': {'INPUT', 'FORWARD', 'OUTPUT'},
            'nat': {'PREROUTING', 'INPUT', 'OUTPUT', 'POSTROUTING'},
            'mangle': {'PREROUTING', 'INPUT', 'FORWARD', 'OUTPUT', 'POSTROUTING'},
            'raw': {'PREROUTING', 'OUTPUT'},
            'security': {'INPUT', 'FORWARD', 'OUTPUT'}
        }
        
        lines = iptables_save_output.split('\n')
        
        # First pass: identify all custom chains
        for line in lines:
            line = line.strip()
            if line.startswith('*'):
                # Table header
                current_table = line[1:]  # Remove the '*'
            elif line.startswith(':') and current_table:
                # Chain definition: :CHAINNAME policy [packets:bytes]
                parts = line[1:].split()  # Remove the ':'
                if parts:
                    chain_name = parts[0]
                    table_builtins = builtin_chains.get(current_table, set())
                    if chain_name not in table_builtins:
                        all_custom_chains.add(chain_name)
        
        # Second pass: parse tables and rules
        current_table = None
        current_chains = {}
        
        for line in lines:
            line = line.strip()
            
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
                
            if line.startswith('*'):
                # Save previous table if it exists
                if current_table and current_chains:
                    # Convert chains dict to list of single-key dicts
                    table_data = []
                    for chain_name, rules in current_chains.items():
                        table_data.append({chain_name: rules})
                    parsed_tables[current_table] = table_data
                
                # Start new table
                current_table = line[1:]  # Remove the '*'
                current_chains = {}
                
            elif line.startswith(':') and current_table:
                # Chain definition: :CHAINNAME policy [packets:bytes]
                parts = line[1:].split()  # Remove the ':'
                if parts:
                    chain_name = parts[0]
                    # Initialize empty rules list for this chain
                    current_chains[chain_name] = []
                    
            elif line.startswith('-A ') and current_table:
                # Rule: -A CHAINNAME rule...
                parts = line.split(' ', 2)  # Split into -A, CHAINNAME, and rest
                if len(parts) >= 3:
                    chain_name = parts[1]
                    rule_text = parts[2]
                    
                    # Ensure chain exists in current_chains
                    if chain_name not in current_chains:
                        current_chains[chain_name] = []
                    
                    # Parse the rule from iptables-save format
                    rule_number = len(current_chains[chain_name]) + 1
                    parsed_rule = self._parse_iptables_save_rule(rule_text, rule_number, all_custom_chains)
                    current_chains[chain_name].append(parsed_rule)
                    
                    # Track chain references
                    if 'target' in parsed_rule:
                        target = parsed_rule['target']
                        if target in all_custom_chains:
                            if target not in chain_references:
                                chain_references[target] = []
                            if chain_name not in chain_references[target]:
                                chain_references[target].append(chain_name)
                                
            elif line == 'COMMIT':
                # End of current table
                if current_table and current_chains:
                    # Convert chains dict to list of single-key dicts
                    table_data = []
                    for chain_name, rules in current_chains.items():
                        table_data.append({chain_name: rules})
                    parsed_tables[current_table] = table_data
                    current_chains = {}
        
        # Handle any remaining table at end of file
        if current_table and current_chains:
            table_data = []
            for chain_name, rules in current_chains.items():
                table_data.append({chain_name: rules})
            parsed_tables[current_table] = table_data
        
        return parsed_tables, chain_references

    def _parse_iptables_save_rule(self, rule_text: str, rule_number: int = 0, custom_chains: set = None) -> Dict[str, Any]:
        """
        Parse an iptables-save format rule into structured format.
        
        Args:
            rule_text: Rule text from iptables-save output (e.g., "-i eth0 -o eth1 -j ACCEPT")
            rule_number: Rule number
            custom_chains: Set of known custom chain names
            
        Returns:
            Dictionary with rule components in structured format compatible with forward analyzer
            
        Example input: "-i eth0 -o eth1 -p tcp --dport 22 -j ACCEPT"
        Example output:
        {
            "number": 1,
            "target": "ACCEPT",
            "protocol": "tcp", 
            "fragments": false,
            "in_interface": "eth0",
            "out_interface": "eth1",
            "source": "0.0.0.0/0",
            "destination": "0.0.0.0/0",
            "dport": "22",
            "extensions": {}
        }
        """
        if custom_chains is None:
            custom_chains = set()
            
        # Initialize rule structure with defaults
        rule_data = {
            "number": rule_number,
            "target": "ACCEPT",
            "protocol": "all",
            "fragments": False,
            "in_interface": "*",
            "out_interface": "*", 
            "source": "0.0.0.0/0",
            "destination": "0.0.0.0/0",
            "state": [],
            "extensions": {}
        }
        
        # Parse rule text using argparse-like logic
        parts = rule_text.split()
        i = 0
        
        while i < len(parts):
            part = parts[i]
            
            if part == "-i" and i + 1 < len(parts):
                rule_data["in_interface"] = parts[i + 1]
                i += 2
            elif part == "-o" and i + 1 < len(parts):
                rule_data["out_interface"] = parts[i + 1]
                i += 2
            elif part == "-p" and i + 1 < len(parts):
                rule_data["protocol"] = parts[i + 1]
                i += 2
            elif part == "-s" and i + 1 < len(parts):
                rule_data["source"] = parts[i + 1]
                i += 2
            elif part == "-d" and i + 1 < len(parts):
                rule_data["destination"] = parts[i + 1]
                i += 2
            elif part == "--dport" and i + 1 < len(parts):
                rule_data["dport"] = parts[i + 1]
                i += 2
            elif part == "--sport" and i + 1 < len(parts):
                rule_data["sport"] = parts[i + 1]
                i += 2
            elif part == "--dports" and i + 1 < len(parts):
                rule_data["dports"] = parts[i + 1].split(',')
                i += 2
            elif part == "--sports" and i + 1 < len(parts):
                rule_data["sports"] = parts[i + 1].split(',')
                i += 2
            elif part == "-j" and i + 1 < len(parts):
                rule_data["target"] = parts[i + 1]
                i += 2
            elif part == "-f":
                rule_data["fragments"] = True
                i += 1
            elif part == "-m" and i + 1 < len(parts):
                # Handle match modules
                module = parts[i + 1]
                i += 2
                
                if module == "state" and i < len(parts) and parts[i] == "--state":
                    if i + 1 < len(parts):
                        rule_data["state"] = parts[i + 1].split(',')
                        i += 2
                    else:
                        i += 1
                elif module == "set":
                    # Handle ipset match-set
                    if i < len(parts) and parts[i] == "--match-set":
                        if i + 2 < len(parts):
                            set_name = parts[i + 1]
                            set_flags = parts[i + 2]
                            rule_data["extensions"]["match_set"] = {
                                "set_name": set_name,
                                "flags": set_flags
                            }
                            i += 3
                        else:
                            i += 1
                    else:
                        i += 1
                elif module == "multiport":
                    # Handle multiport module
                    if i < len(parts):
                        if parts[i] == "--dports" and i + 1 < len(parts):
                            rule_data["dports"] = parts[i + 1].split(',')
                            i += 2
                        elif parts[i] == "--sports" and i + 1 < len(parts):
                            rule_data["sports"] = parts[i + 1].split(',')
                            i += 2
                        elif parts[i] == "--ports" and i + 1 < len(parts):
                            # --ports affects both source and dest
                            ports = parts[i + 1].split(',')
                            rule_data["dports"] = ports
                            rule_data["sports"] = ports
                            i += 2
                        else:
                            i += 1
                    else:
                        i += 1
                elif module == "conntrack":
                    # Handle connection tracking
                    if i < len(parts) and parts[i] == "--ctstate":
                        if i + 1 < len(parts):
                            rule_data["state"] = parts[i + 1].split(',')
                            i += 2
                        else:
                            i += 1
                    else:
                        i += 1
                elif module == "limit":
                    # Handle rate limiting
                    if i < len(parts) and parts[i] == "--limit":
                        if i + 1 < len(parts):
                            rule_data["extensions"]["limit"] = parts[i + 1]
                            i += 2
                        else:
                            i += 1
                    else:
                        i += 1
                elif module == "recent":
                    # Handle recent module for tracking
                    rule_data["extensions"]["recent"] = True
                    # Skip remaining recent options for now
                    while i < len(parts) and parts[i].startswith('--'):
                        if i + 1 < len(parts) and not parts[i + 1].startswith('-'):
                            i += 2
                        else:
                            i += 1
                elif module == "hashlimit":
                    # Handle hashlimit module 
                    rule_data["extensions"]["hashlimit"] = True
                    # Skip remaining hashlimit options for now
                    while i < len(parts) and parts[i].startswith('--'):
                        if i + 1 < len(parts) and not parts[i + 1].startswith('-'):
                            i += 2
                        else:
                            i += 1
                elif module == "connlimit":
                    # Handle connection limit module
                    rule_data["extensions"]["connlimit"] = True
                    # Skip remaining connlimit options for now
                    while i < len(parts) and parts[i].startswith('--'):
                        if i + 1 < len(parts) and not parts[i + 1].startswith('-'):
                            i += 2
                        else:
                            i += 1
                else:
                    # Unknown module, skip
                    i += 1
            elif part.startswith("--"):
                # Handle other long options
                if part == "--tcp-flags" and i + 2 < len(parts):
                    rule_data["extensions"]["tcp_flags"] = {
                        "mask": parts[i + 1],
                        "comp": parts[i + 2]
                    }
                    i += 3
                elif part == "--icmp-type" and i + 1 < len(parts):
                    rule_data["extensions"]["icmp_type"] = parts[i + 1]
                    i += 2
                elif part == "--log-prefix" and i + 1 < len(parts):
                    rule_data["extensions"]["log_prefix"] = parts[i + 1].strip('"')
                    i += 2
                elif part == "--log-level" and i + 1 < len(parts):
                    rule_data["extensions"]["log_level"] = parts[i + 1]
                    i += 2
                elif part == "--to-destination" and i + 1 < len(parts):
                    rule_data["extensions"]["to_destination"] = parts[i + 1]
                    i += 2
                elif part == "--to-source" and i + 1 < len(parts):
                    rule_data["extensions"]["to_source"] = parts[i + 1]
                    i += 2
                elif part == "--reject-with" and i + 1 < len(parts):
                    rule_data["extensions"]["reject_with"] = parts[i + 1]
                    i += 2
                else:
                    # Skip unknown long options with potential arguments
                    if i + 1 < len(parts) and not parts[i + 1].startswith('-'):
                        i += 2
                    else:
                        i += 1
            else:
                # Skip unrecognized parts
                i += 1
        
        # Store raw rule text if requested
        if self.store_raw:
            rule_data["raw_rule_text"] = rule_text
            
        return rule_data

    def _parse_interfaces_output(self, interfaces_output: str) -> Dict[str, Dict[str, Any]]:
        """
        Parse 'ip addr show' output into structured interface information.
        
        Args:
            interfaces_output: Raw output from 'ip addr show' command
            
        Returns:
            Dictionary with interface names as keys and interface data as values
            
        Example output format:
        {
            "lo": {
                "index": 1,
                "flags": ["LOOPBACK", "UP", "LOWER_UP"],
                "mtu": 65536,
                "qdisc": "noqueue",
                "state": "UNKNOWN",
                "group": "default",
                "qlen": 1000,
                "link_type": "loopback",
                "addresses": [
                    {
                        "family": "inet",
                        "address": "127.0.0.1",
                        "prefixlen": 8,
                        "scope": "host",
                        "label": "lo"
                    },
                    {
                        "family": "inet6", 
                        "address": "::1",
                        "prefixlen": 128,
                        "scope": "host"
                    }
                ]
            }
        }
        """
        interfaces = {}
        current_interface = None
        current_data = None
        
        for line in interfaces_output.split('\n'):
            line = line.strip()
            
            if not line:
                continue
                
            # Check for interface header line
            # Format: "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000"
            if re.match(r'^\d+:', line):
                # Save previous interface if exists
                if current_interface and current_data:
                    interfaces[current_interface] = current_data
                
                # Parse interface header
                parts = line.split()
                if len(parts) >= 2:
                    # Extract interface index and name
                    index_name = parts[0] + ' ' + parts[1]  # "1: lo:"
                    index_match = re.match(r'^(\d+):\s*([^:@]+)[@:]?', index_name)
                    
                    if index_match:
                        index = int(index_match.group(1))
                        interface_name = index_match.group(2)
                        
                        # Initialize interface data
                        current_interface = interface_name
                        current_data = {
                            'index': index,
                            'flags': [],
                            'addresses': []
                        }
                        
                        # Parse flags if present: <LOOPBACK,UP,LOWER_UP>
                        flags_match = re.search(r'<([^>]+)>', line)
                        if flags_match:
                            flags_str = flags_match.group(1)
                            current_data['flags'] = flags_str.split(',')
                        
                        # Parse additional attributes
                        remaining_line = line
                        
                        # MTU
                        mtu_match = re.search(r'mtu (\d+)', remaining_line)
                        if mtu_match:
                            current_data['mtu'] = int(mtu_match.group(1))
                        
                        # QDISC
                        qdisc_match = re.search(r'qdisc (\S+)', remaining_line)
                        if qdisc_match:
                            current_data['qdisc'] = qdisc_match.group(1)
                        
                        # State
                        state_match = re.search(r'state (\S+)', remaining_line)
                        if state_match:
                            current_data['state'] = state_match.group(1)
                        
                        # Group
                        group_match = re.search(r'group (\S+)', remaining_line)
                        if group_match:
                            current_data['group'] = group_match.group(1)
                        
                        # Queue length
                        qlen_match = re.search(r'qlen (\d+)', remaining_line)
                        if qlen_match:
                            current_data['qlen'] = int(qlen_match.group(1))
                            
            # Check for link information line
            # Format: "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00"
            elif line.startswith('link/') and current_data is not None:
                link_parts = line.split()
                if len(link_parts) >= 1:
                    link_type = link_parts[0].split('/', 1)
                    if len(link_type) == 2:
                        current_data['link_type'] = link_type[1]
                    
                    # MAC address
                    if len(link_parts) >= 2 and link_parts[1] != 'brd':
                        current_data['mac_address'] = link_parts[1]
                    
                    # Broadcast address
                    if len(link_parts) >= 4 and link_parts[2] == 'brd':
                        current_data['broadcast_address'] = link_parts[3]
                        
            # Check for IP address lines
            # Format: "    inet 127.0.0.1/8 scope host lo"
            # Format: "    inet6 ::1/128 scope host"
            elif (line.startswith('inet ') or line.startswith('inet6 ')) and current_data is not None:
                addr_parts = line.split()
                if len(addr_parts) >= 2:
                    family = addr_parts[0]  # inet or inet6
                    addr_cidr = addr_parts[1]  # IP/prefix
                    
                    # Parse IP and prefix length
                    if '/' in addr_cidr:
                        address, prefix_str = addr_cidr.split('/', 1)
                        try:
                            prefixlen = int(prefix_str)
                        except ValueError:
                            prefixlen = None
                    else:
                        address = addr_cidr
                        prefixlen = None
                    
                    # Build address entry
                    addr_entry = {
                        'family': family,
                        'address': address
                    }
                    
                    if prefixlen is not None:
                        addr_entry['prefixlen'] = prefixlen
                    
                    # Parse additional attributes
                    remaining_parts = addr_parts[2:]
                    i = 0
                    while i < len(remaining_parts):
                        if remaining_parts[i] == 'scope' and i + 1 < len(remaining_parts):
                            addr_entry['scope'] = remaining_parts[i + 1]
                            i += 2
                        elif remaining_parts[i] == 'brd' and i + 1 < len(remaining_parts):
                            addr_entry['broadcast'] = remaining_parts[i + 1]
                            i += 2
                        elif remaining_parts[i] == 'peer' and i + 1 < len(remaining_parts):
                            addr_entry['peer'] = remaining_parts[i + 1]
                            i += 2
                        elif remaining_parts[i] == 'label' and i + 1 < len(remaining_parts):
                            addr_entry['label'] = remaining_parts[i + 1]
                            i += 2
                        elif remaining_parts[i] == 'secondary':
                            addr_entry['secondary'] = True
                            i += 1
                        elif remaining_parts[i] == 'dynamic':
                            addr_entry['dynamic'] = True
                            i += 1
                        elif remaining_parts[i] == 'noprefixroute':
                            addr_entry['noprefixroute'] = True
                            i += 1
                        elif remaining_parts[i] == 'tentative':
                            addr_entry['tentative'] = True
                            i += 1
                        elif remaining_parts[i] == 'deprecated':
                            addr_entry['deprecated'] = True
                            i += 1
                        elif remaining_parts[i] == 'dadfailed':
                            addr_entry['dadfailed'] = True
                            i += 1
                        elif remaining_parts[i] == 'valid_lft' and i + 1 < len(remaining_parts):
                            addr_entry['valid_lifetime'] = remaining_parts[i + 1]
                            i += 2
                        elif remaining_parts[i] == 'preferred_lft' and i + 1 < len(remaining_parts):
                            addr_entry['preferred_lifetime'] = remaining_parts[i + 1]
                            i += 2
                        else:
                            # Unknown attribute, skip
                            i += 1
                    
                    current_data['addresses'].append(addr_entry)
        
        # Save last interface
        if current_interface and current_data:
            interfaces[current_interface] = current_data
        
        return interfaces

    @staticmethod
    def extract_interface_info(json_facts_file: str, interface_name: str = None) -> Dict[str, Any]:
        """
        Extract interface information from a processed JSON facts file.
        
        Args:
            json_facts_file: Path to JSON facts file
            interface_name: Specific interface name to extract (optional)
            
        Returns:
            Dictionary containing interface information
            
        Examples:
            # Get all interfaces
            interfaces = FactsProcessor.extract_interface_info('/path/to/router.json')
            
            # Get specific interface
            eth0_info = FactsProcessor.extract_interface_info('/path/to/router.json', 'eth0')
        """
        try:
            with open(json_facts_file, 'r') as f:
                facts = json.load(f)
            
            interfaces_data = facts.get('network', {}).get('interfaces', {})
            
            if 'parsed' not in interfaces_data:
                return {'error': 'Interface data not parsed', 'available': False}
            
            parsed_interfaces = interfaces_data['parsed']
            
            if interface_name:
                if interface_name in parsed_interfaces:
                    return {
                        'interface': interface_name,
                        'data': parsed_interfaces[interface_name],
                        'available': True
                    }
                else:
                    return {
                        'error': f'Interface {interface_name} not found',
                        'available_interfaces': list(parsed_interfaces.keys()),
                        'available': False
                    }
            else:
                return {
                    'interfaces': parsed_interfaces,
                    'count': len(parsed_interfaces),
                    'available': True
                }
                
        except Exception as e:
            return {'error': str(e), 'available': False}

    @staticmethod
    def extract_interface_ips(json_facts_file: str, family: str = 'all') -> Dict[str, List[str]]:
        """
        Extract IP addresses from all interfaces in a JSON facts file.
        
        Args:
            json_facts_file: Path to JSON facts file
            family: IP family to extract ('inet', 'inet6', or 'all')
            
        Returns:
            Dictionary with interface names as keys and IP addresses as values
            
        Example:
            # Get all IP addresses
            all_ips = FactsProcessor.extract_interface_ips('/path/to/router.json')
            
            # Get only IPv4 addresses
            ipv4_ips = FactsProcessor.extract_interface_ips('/path/to/router.json', 'inet')
        """
        try:
            interface_info = FactsProcessor.extract_interface_info(json_facts_file)
            
            if not interface_info.get('available', False):
                return {'error': interface_info.get('error', 'Interface data not available')}
            
            result = {}
            
            for interface_name, interface_data in interface_info['interfaces'].items():
                addresses = interface_data.get('addresses', [])
                ip_list = []
                
                for addr in addresses:
                    addr_family = addr.get('family', '')
                    if family == 'all' or addr_family == family:
                        ip_list.append(addr['address'])
                
                result[interface_name] = ip_list
            
            return result
            
        except Exception as e:
            return {'error': str(e)}


def main():
    """Main entry point for the facts processor."""
    parser = argparse.ArgumentParser(
        description='Convert collected facts to structured JSON format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic processing (compact JSON output)
    python3 process_facts.py facts.txt facts.json
    
    # Include original rule text (compact JSON)
    python3 process_facts.py --raw facts.txt facts.json
    
    # Human-readable formatting (without raw text)
    python3 process_facts.py --pretty facts.txt facts.json
    
    # Include original rule text with pretty formatting
    python3 process_facts.py --raw --pretty facts.txt facts.json
    
    # Debug encoding issues
    python3 process_facts.py --verbose facts.txt facts.json
    
    # Validate existing JSON file
    python3 process_facts.py --validate facts.json
        """
    )
    
    parser.add_argument('input_file', help='Input facts file to process')
    parser.add_argument('output_file', nargs='?', help='Output JSON file to create')
    parser.add_argument('--validate', action='store_true', 
                        help='Validate existing JSON file instead of processing facts')
    parser.add_argument('--pretty', action='store_true',
                        help='Pretty-print JSON output with indentation')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose output for debugging encoding issues')
    parser.add_argument('--raw', action='store_true',
                        help='Store all raw/unparsed data (rule text, raw_output, raw_config, etc.) in JSON output (significantly increases file size)')
    parser.add_argument('--merge-with', metavar='JSON_FILE',
                        help='Merge with existing JSON file (overrides routing data only)')
    
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
        processor = FactsProcessor(verbose=args.verbose, store_raw=args.raw)
        facts = processor.parse_facts_file(args.input_file)
        
        # Merge with existing JSON file if specified
        if args.merge_with:
            if not os.path.exists(args.merge_with):
                print(f"Warning: Merge file {args.merge_with} not found, proceeding without merge")
            else:
                try:
                    with open(args.merge_with, 'r') as f:
                        base_facts = json.load(f)
                    
                    # Merge: start with base facts, override/add sections from new facts
                    merged_facts = base_facts.copy()
                    
                    # Override routing data only (properly parsed)
                    if 'routing' in facts:
                        merged_facts['routing'] = facts['routing']
                    
                    # Only override specific network sections that are properly parsed
                    if 'network' in facts:
                        if 'network' not in merged_facts:
                            merged_facts['network'] = {}
                        
                        # Only override ip_forwarding_enabled if it's properly parsed
                        if 'ip_forwarding_enabled' in facts['network']:
                            merged_facts['network']['ip_forwarding_enabled'] = facts['network']['ip_forwarding_enabled']
                        
                        # DO NOT override interfaces - keep the structured data from tsim_facts
                        # DO NOT override interface_stats - keep the structured data from tsim_facts
                    
                    # Add firewall sections from raw facts (they don't exist in tsim_facts)
                    if 'firewall' in facts:
                        merged_facts['firewall'] = facts['firewall']
                    
                    # Add system sections from raw facts (they don't exist in tsim_facts)
                    if 'system' in facts:
                        merged_facts['system'] = facts['system']
                    
                    # Update metadata timestamp and sections_available
                    if 'metadata' in facts:
                        if 'metadata' not in merged_facts:
                            merged_facts['metadata'] = {}
                        
                        if 'collection_timestamp' in facts['metadata']:
                            merged_facts['metadata']['collection_timestamp'] = facts['metadata']['collection_timestamp']
                        
                        if 'sections_available' in facts['metadata']:
                            merged_facts['metadata']['sections_available'] = facts['metadata']['sections_available']
                    
                    facts = merged_facts
                    print(f"Merged routing data from {args.input_file} with base data from {args.merge_with}")
                    
                except Exception as e:
                    print(f"Warning: Could not merge with {args.merge_with}: {e}, proceeding without merge")
        
        # Write JSON output (compact by default, pretty only when requested)
        with open(args.output_file, 'w') as f:
            if args.pretty:
                json.dump(facts, f, indent=2, sort_keys=True)
            else:
                json.dump(facts, f, separators=(',', ':'))  # Most compact format
        
        print(f"Successfully processed facts from {args.input_file}")
        print(f"Output written to {args.output_file}")
        print(f"Hostname: {facts['metadata']['hostname']}")
        print(f"Sections processed: {len(facts['metadata']['sections_available'])}")
        
        return 0
        
    except UnicodeDecodeError as e:
        print(f"Error: Text encoding issue - {e}")
        print(f"Try using --verbose to see encoding details, or convert the file to UTF-8:")
        print(f"  iconv -f iso-8859-1 -t utf-8 {args.input_file} > {args.input_file}.utf8")
        print(f"  Or use dos2unix if it's a Windows line ending issue:")
        print(f"  dos2unix {args.input_file}")
        return 1
    except Exception as e:
        print(f"Error processing facts: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())