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
        
        if 'iptables_filter' in self.sections:
            section = self.sections['iptables_filter']
            self.facts['firewall']['iptables']['filter_table'] = section['output']
        
        if 'iptables_nat' in self.sections:
            section = self.sections['iptables_nat']
            self.facts['firewall']['iptables']['nat_table'] = section['output']
        
        if 'iptables_mangle' in self.sections:
            section = self.sections['iptables_mangle']
            self.facts['firewall']['iptables']['mangle_table'] = section['output']
        
        if 'iptables_save' in self.sections:
            section = self.sections['iptables_save']
            self.facts['firewall']['iptables']['raw_config'] = section['output']
        
        # Process ipset information
        if 'ipset_list' in self.sections:
            section = self.sections['ipset_list']
            self.facts['firewall']['ipset']['available'] = True
            self.facts['firewall']['ipset']['lists'] = section['output']
        else:
            self.facts['firewall']['ipset']['available'] = False
    
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