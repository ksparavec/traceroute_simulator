#!/usr/bin/env python3
"""
Raw Facts Parser Module

Parses raw facts files directly from TSIM_SECTION format into structured data.
This module eliminates the need for intermediate JSON processing by reading
and parsing raw shell output directly.

Supported sections:
- routing_table: IP routing table data
- policy_rules: IP policy rules
- routing_table_*: Additional routing tables (priority, service, backup, etc.)
- iptables_*: Iptables rules for all chains and tables
- ipset_save: Ipset save format data
- ipset_list: Ipset list format data
- interfaces: Network interface data
- system_info: System and kernel information

The parser converts raw shell output into structured dictionaries compatible
with the existing simulator infrastructure while maintaining full data fidelity.
"""

import re
import ipaddress
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field


@dataclass
class ParsedSection:
    """Represents a parsed TSIM section."""
    name: str
    title: str
    command: str
    timestamp: str
    content: str
    exit_code: int
    

@dataclass
class ParsedRoute:
    """Represents a parsed route entry."""
    destination: str
    gateway: Optional[str] = None
    device: Optional[str] = None
    proto: Optional[str] = None
    scope: Optional[str] = None
    src: Optional[str] = None
    metric: Optional[int] = None
    table: Optional[str] = None


@dataclass
class ParsedInterface:
    """Represents a parsed network interface."""
    name: str
    ip_address: Optional[str] = None
    network: Optional[str] = None
    broadcast: Optional[str] = None
    mtu: Optional[int] = None
    state: Optional[str] = None
    mac_address: Optional[str] = None


@dataclass
class ParsedRule:
    """Represents a parsed policy rule."""
    priority: int
    selector: str
    action: str
    table: Optional[str] = None


class RawFactsParser:
    """Parser for raw facts files in TSIM_SECTION format."""
    
    def __init__(self, verbose: int = 0):
        self.verbose = verbose
        # Use simple print-based logging to avoid conflicts
        self.debug = verbose >= 2
        self.info = verbose >= 1
    
    def parse_file(self, file_path: Path) -> Dict[str, Any]:
        """Parse a raw facts file and return structured data."""
        if self.info:
            print(f"INFO: Parsing raw facts file: {file_path}")
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Extract all sections
        sections = self._extract_sections(content)
        
        # Parse header information
        header_info = self._parse_header(content)
        
        # Convert sections to structured data
        parsed_data = {
            'header': header_info,
            'sections': {},
            'network': {},
            'firewall': {},
            'system': {}
        }
        
        for section in sections:
            self._process_section(section, parsed_data)
        
        # Post-process to match expected format
        self._normalize_data(parsed_data)
        
        return parsed_data
    
    def _extract_sections(self, content: str) -> List[ParsedSection]:
        """Extract all TSIM_SECTION blocks from content."""
        sections = []
        
        # Pattern to match TSIM sections
        pattern = r'=== TSIM_SECTION_START:(\w+) ===\n(.*?)\n=== TSIM_SECTION_END:\1 ==='
        matches = re.finditer(pattern, content, re.DOTALL)
        
        for match in matches:
            section_name = match.group(1)
            section_content = match.group(2)
            
            # Parse section header
            lines = section_content.split('\n')
            title = ""
            command = ""
            timestamp = ""
            exit_code = 0
            data_lines = []
            
            in_data = False
            for line in lines:
                line = line.strip()
                
                if line.startswith('TITLE: '):
                    title = line[7:]
                elif line.startswith('COMMAND: '):
                    command = line[9:]
                elif line.startswith('TIMESTAMP: '):
                    timestamp = line[11:]
                elif line.startswith('EXIT_CODE: '):
                    try:
                        exit_code = int(line[11:])
                    except ValueError:
                        exit_code = 0
                elif line == '---':
                    in_data = True
                elif in_data and line:
                    data_lines.append(line)
            
            sections.append(ParsedSection(
                name=section_name,
                title=title,
                command=command,
                timestamp=timestamp,
                content='\n'.join(data_lines),
                exit_code=exit_code
            ))
        
        return sections
    
    def _parse_header(self, content: str) -> Dict[str, Any]:
        """Parse header information from facts file."""
        header = {}
        
        # Extract header comments
        lines = content.split('\n')
        for line in lines:
            if line.startswith('# Hostname: '):
                header['hostname'] = line[12:]
            elif line.startswith('# Kernel: '):
                header['kernel'] = line[10:]
            elif line.startswith('# Generated on: '):
                header['generated_on'] = line[16:]
            elif line.startswith('# Collection Script Version: '):
                header['script_version'] = line[30:]
            elif line.startswith('# Running as root: '):
                header['running_as_root'] = line[19:] == '1'
        
        return header
    
    def _process_section(self, section: ParsedSection, parsed_data: Dict[str, Any]):
        """Process a single section and add to parsed data."""
        if self.debug:
            print(f"DEBUG: Processing section: {section.name}")
        
        # Store raw section
        parsed_data['sections'][section.name] = {
            'title': section.title,
            'command': section.command,
            'timestamp': section.timestamp,
            'content': section.content,
            'exit_code': section.exit_code
        }
        
        # Parse specific section types
        if section.name == 'routing_table':
            self._parse_routing_table(section, parsed_data)
        elif section.name == 'policy_rules':
            self._parse_policy_rules(section, parsed_data)
        elif section.name.startswith('routing_table_'):
            self._parse_additional_routing_table(section, parsed_data)
        elif section.name.startswith('iptables_'):
            self._parse_iptables_section(section, parsed_data)
        elif section.name == 'ipset_save':
            self._parse_ipset_save(section, parsed_data)
        elif section.name == 'ipset_list':
            self._parse_ipset_list(section, parsed_data)
        elif section.name == 'interfaces':
            self._parse_interfaces(section, parsed_data)
    
    def _parse_routing_table(self, section: ParsedSection, parsed_data: Dict[str, Any]):
        """Parse main routing table."""
        routes = []
        
        for line in section.content.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            route = self._parse_route_line(line)
            if route:
                routes.append({
                    'dst': route.destination,
                    'gateway': route.gateway,
                    'dev': route.device,
                    'proto': route.proto,
                    'scope': route.scope,
                    'prefsrc': route.src,
                    'metric': route.metric
                })
        
        # Store in network section for compatibility
        if 'interfaces' not in parsed_data['network']:
            parsed_data['network']['interfaces'] = []
        
        # Convert routes to interface format for compatibility
        for route in routes:
            if route.get('proto') == 'kernel' and route.get('scope') == 'link':
                interface_data = {
                    'dst': route['dst'],
                    'dev': route['dev'],
                    'proto': route['proto'],
                    'scope': route['scope'],
                    'prefsrc': route['prefsrc']
                }
                if route.get('metric'):
                    interface_data['metric'] = route['metric']
                parsed_data['network']['interfaces'].append(interface_data)
        
        parsed_data['network']['routes'] = routes
    
    def _parse_route_line(self, line: str) -> Optional[ParsedRoute]:
        """Parse a single route line."""
        # Handle different route formats
        parts = line.split()
        if not parts:
            return None
        
        route = ParsedRoute(destination=parts[0])
        
        i = 1
        while i < len(parts):
            if parts[i] == 'via' and i + 1 < len(parts):
                route.gateway = parts[i + 1]
                i += 2
            elif parts[i] == 'dev' and i + 1 < len(parts):
                route.device = parts[i + 1]
                i += 2
            elif parts[i] == 'proto' and i + 1 < len(parts):
                route.proto = parts[i + 1]
                i += 2
            elif parts[i] == 'scope' and i + 1 < len(parts):
                route.scope = parts[i + 1]
                i += 2
            elif parts[i] == 'src' and i + 1 < len(parts):
                route.src = parts[i + 1]
                i += 2
            elif parts[i] == 'metric' and i + 1 < len(parts):
                try:
                    route.metric = int(parts[i + 1])
                except ValueError:
                    pass
                i += 2
            else:
                i += 1
        
        return route
    
    def _parse_policy_rules(self, section: ParsedSection, parsed_data: Dict[str, Any]):
        """Parse policy rules section."""
        rules = []
        
        for line in section.content.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Parse rule format: "priority: selector action table"
            parts = line.split(':', 1)
            if len(parts) != 2:
                continue
            
            try:
                priority = int(parts[0])
                rule_parts = parts[1].strip().split()
                
                if not rule_parts:
                    continue
                
                # Find table if present
                table = None
                if 'lookup' in rule_parts:
                    lookup_idx = rule_parts.index('lookup')
                    if lookup_idx + 1 < len(rule_parts):
                        table = rule_parts[lookup_idx + 1]
                
                # Reconstruct selector and action
                selector = ' '.join(rule_parts)
                
                rules.append({
                    'priority': priority,
                    'selector': selector,
                    'table': table
                })
                
            except ValueError:
                continue
        
        parsed_data['network']['policy_rules'] = rules
    
    def _parse_additional_routing_table(self, section: ParsedSection, parsed_data: Dict[str, Any]):
        """Parse additional routing tables (priority_table, service_table, etc.)."""
        table_name = section.name.replace('routing_table_', '')
        
        routes = []
        for line in section.content.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Handle escaped newlines in routing table output
            line = line.replace('\\n', '\n')
            for route_line in line.split('\n'):
                route_line = route_line.strip()
                if route_line:
                    route = self._parse_route_line(route_line)
                    if route:
                        route_dict = {
                            'dst': route.destination,
                            'table': table_name
                        }
                        if route.gateway:
                            route_dict['gateway'] = route.gateway
                        if route.device:
                            route_dict['dev'] = route.device
                        if route.proto:
                            route_dict['proto'] = route.proto
                        if route.scope:
                            route_dict['scope'] = route.scope
                        if route.src:
                            route_dict['prefsrc'] = route.src
                        if route.metric:
                            route_dict['metric'] = route.metric
                        
                        routes.append(route_dict)
        
        # Store additional routes
        if 'additional_routes' not in parsed_data['network']:
            parsed_data['network']['additional_routes'] = {}
        parsed_data['network']['additional_routes'][table_name] = routes
    
    def _parse_iptables_section(self, section: ParsedSection, parsed_data: Dict[str, Any]):
        """Parse iptables sections."""
        table_chain = section.name.replace('iptables_', '')
        
        # Extract table and chain
        if '_' in table_chain:
            table, chain = table_chain.split('_', 1)
        else:
            table = 'filter'
            chain = table_chain
        
        rules = []
        for line in section.content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                rules.append(line)
        
        # Store in firewall section
        if 'iptables' not in parsed_data['firewall']:
            parsed_data['firewall']['iptables'] = {}
        if table not in parsed_data['firewall']['iptables']:
            parsed_data['firewall']['iptables'][table] = {}
        
        parsed_data['firewall']['iptables'][table][chain] = rules
    
    def _parse_ipset_save(self, section: ParsedSection, parsed_data: Dict[str, Any]):
        """Parse ipset save format."""
        ipsets = {}
        current_set = None
        
        for line in section.content.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('create '):
                # Parse create line: create setname type options
                parts = line.split()
                if len(parts) >= 3:
                    set_name = parts[1]
                    set_type = parts[2]
                    options = ' '.join(parts[3:]) if len(parts) > 3 else ''
                    
                    current_set = set_name
                    ipsets[set_name] = {
                        'type': set_type,
                        'options': options,
                        'members': []
                    }
            elif line.startswith('add ') and current_set:
                # Parse add line: add setname member
                parts = line.split(None, 2)
                if len(parts) >= 3:
                    member = parts[2]
                    ipsets[current_set]['members'].append(member)
        
        parsed_data['firewall']['ipsets_save'] = ipsets
    
    def _parse_ipset_list(self, section: ParsedSection, parsed_data: Dict[str, Any]):
        """Parse ipset list format."""
        ipsets = {}
        current_set = None
        current_data = {}
        in_members = False
        
        for line in section.content.split('\n'):
            line = line.strip()
            if not line:
                if current_set and current_data:
                    ipsets[current_set] = current_data
                    current_set = None
                    current_data = {}
                    in_members = False
                continue
            
            if line.startswith('Name: '):
                current_set = line[6:]
                current_data = {'members': []}
                in_members = False
            elif line.startswith('Type: ') and current_set:
                current_data['type'] = line[6:]
            elif line.startswith('Revision: ') and current_set:
                current_data['revision'] = line[10:]
            elif line.startswith('Header: ') and current_set:
                current_data['header'] = line[8:]
            elif line.startswith('Size in memory: ') and current_set:
                current_data['size'] = line[16:]
            elif line.startswith('References: ') and current_set:
                current_data['references'] = line[12:]
            elif line == 'Members:' and current_set:
                in_members = True
            elif in_members and current_set:
                current_data['members'].append(line)
        
        # Handle last set
        if current_set and current_data:
            ipsets[current_set] = current_data
        
        parsed_data['firewall']['ipsets_list'] = ipsets
    
    def _parse_interfaces(self, section: ParsedSection, parsed_data: Dict[str, Any]):
        """Parse network interfaces section."""
        interfaces = []
        
        # This would parse 'ip addr show' output
        # Implementation depends on exact format in raw facts
        
        for line in section.content.split('\n'):
            line = line.strip()
            if line:
                # Basic interface parsing - extend as needed
                if ':' in line and 'state' in line.lower():
                    # Parse interface header line
                    continue
                elif 'inet ' in line:
                    # Parse IP address line
                    continue
        
        parsed_data['network']['interface_details'] = interfaces
    
    def _normalize_data(self, parsed_data: Dict[str, Any]):
        """Normalize parsed data to match expected format."""
        # Ensure required sections exist
        if 'network' not in parsed_data:
            parsed_data['network'] = {}
        if 'interfaces' not in parsed_data['network']:
            parsed_data['network']['interfaces'] = []
        if 'firewall' not in parsed_data:
            parsed_data['firewall'] = {}
        
        # Add compatibility fields
        parsed_data['router_type'] = 'linux'  # Default for namespace simulation
        parsed_data['management_ip'] = None
        
        # Extract primary IP from interfaces
        for interface in parsed_data['network'].get('interfaces', []):
            if interface.get('prefsrc') and not parsed_data['management_ip']:
                parsed_data['management_ip'] = interface['prefsrc']
                break


def load_raw_facts_directory(facts_dir: Path, verbose: int = 0) -> Dict[str, Dict[str, Any]]:
    """Load all raw facts files from a directory."""
    parser = RawFactsParser(verbose)
    routers = {}
    
    # Look for *_facts.txt files
    for facts_file in facts_dir.glob("*_facts.txt"):
        router_name = facts_file.stem.replace('_facts', '')
        try:
            router_data = parser.parse_file(facts_file)
            routers[router_name] = router_data
            if verbose >= 1:
                print(f"✓ Loaded raw facts for {router_name}")
        except Exception as e:
            if verbose >= 1:
                print(f"✗ Failed to load {router_name}: {e}")
            continue
    
    return routers


def main():
    """Test the raw facts parser."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Parse raw facts files')
    parser.add_argument('file_path', help='Path to raw facts file')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity')
    
    args = parser.parse_args()
    
    # Simple verbosity handling without logging module
    if args.verbose >= 1:
        print(f"Parsing file: {args.file_path}")
    
    raw_parser = RawFactsParser(args.verbose)
    
    try:
        parsed_data = raw_parser.parse_file(Path(args.file_path))
        
        print(f"Successfully parsed {args.file_path}")
        print(f"Sections found: {list(parsed_data['sections'].keys())}")
        print(f"Network interfaces: {len(parsed_data['network'].get('interfaces', []))}")
        print(f"Routes: {len(parsed_data['network'].get('routes', []))}")
        
        if args.verbose >= 2:
            import json
            print("\nParsed data:")
            print(json.dumps(parsed_data, indent=2, default=str))
        
    except Exception as e:
        print(f"Error parsing file: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()