#!/usr/bin/env -S python3 -B -u
"""
Data formatter for network status output.

Handles formatting of collected data into JSON and text formats
with interface name translation support.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

logger = logging.getLogger(__name__)


class InterfaceNameTranslator:
    """Translates short interface names (v001) to original names using registries."""
    
    def __init__(self):
        """
        Initialize interface name translator using registry files.
        """
        self.name_map: Dict[str, str] = {}  # short -> original
        self.reverse_map: Dict[str, str] = {}  # original -> short
        
        # Registry paths
        self.interface_registry_path = Path('/dev/shm/tsim/interface_registry.json')
        self.router_registry_path = Path('/dev/shm/tsim/router_registry.json')
        
        self._load_from_registries()
    
    def _load_from_registries(self):
        """Load interface name mappings from registries."""
        try:
            # Load interface registry which contains the mappings
            if self.interface_registry_path.exists():
                with open(self.interface_registry_path, 'r') as f:
                    interface_registry = json.load(f)
                    
                # The interface registry should contain mappings like:
                # {"v001": {"original_name": "hq-gw-eth0", "namespace": "hq-gw", ...}}
                for short_name, interface_data in interface_registry.items():
                    if isinstance(interface_data, dict) and 'original_name' in interface_data:
                        original_name = interface_data['original_name']
                        self.name_map[short_name] = original_name
                        self.reverse_map[original_name] = short_name
                
                logger.debug(f"Loaded {len(self.name_map)} interface mappings from registry")
            else:
                logger.debug(f"Interface registry not found at {self.interface_registry_path}")
                # Try to build mappings from router registry
                self._build_from_router_registry()
                
        except Exception as e:
            logger.warning(f"Failed to load interface mappings from registry: {e}")
    
    def _build_from_router_registry(self):
        """Build interface mappings from router registry if interface registry is unavailable."""
        try:
            if not self.router_registry_path.exists():
                logger.debug("Router registry not found, no interface name translation available")
                return
                
            with open(self.router_registry_path, 'r') as f:
                router_registry = json.load(f)
            
            # Router registry contains router configurations with interfaces
            # We can extract the mappings from there
            interface_counter = 0
            
            for router_name, router_data in router_registry.items():
                if isinstance(router_data, dict):
                    # Look for interfaces in the router data
                    interfaces = router_data.get('interfaces', {})
                    for iface_name, iface_data in interfaces.items():
                        if isinstance(iface_data, dict):
                            # Check if this has a short name
                            short_name = iface_data.get('short_name')
                            if short_name:
                                # Use the provided short name
                                original = f"{router_name}-{iface_name}"
                                self.name_map[short_name] = original
                                self.reverse_map[original] = short_name
                            elif iface_name.startswith('v') and len(iface_name) == 4:
                                # This looks like a short name already
                                # Try to reconstruct the original name
                                original = iface_data.get('original_name', f"{router_name}-{iface_name}")
                                self.name_map[iface_name] = original
                                self.reverse_map[original] = iface_name
            
            logger.debug(f"Built {len(self.name_map)} interface mappings from router registry")
            
        except Exception as e:
            logger.warning(f"Failed to build interface mappings from router registry: {e}")
    
    
    def translate(self, short_name: str) -> str:
        """Translate short name to original."""
        return self.name_map.get(short_name, short_name)
    
    def translate_reverse(self, original_name: str) -> str:
        """Translate original name to short."""
        return self.reverse_map.get(original_name, original_name)


class DataFormatter:
    """
    Handles all data formatting operations.
    
    Provides JSON and text formatting with optional interface
    name translation.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize data formatter.
        
        Args:
            config: Formatting configuration
        """
        config = config or {}
        
        # Formatting settings
        self.translate_names = config.get('translate_interface_names', True)
        self.show_original_names = config.get('show_original_names', True)
        self.json_indent = config.get('json_indent', 2)
        
        # Initialize name translator (uses registries)
        self.name_translator = InterfaceNameTranslator() if self.translate_names else None
        
        logger.debug(f"DataFormatter initialized: translate={self.translate_names}, "
                    f"show_original={self.show_original_names}")
    
    def format_json(self, data: Dict, function: Optional[str] = None) -> str:
        """
        Format data as JSON.
        
        Args:
            data: Data to format
            function: Optional function name for specific formatting
            
        Returns:
            JSON formatted string
        """
        # Apply interface name translation if enabled
        if self.translate_names and self.name_translator:
            data = self._apply_name_translation_to_dict(data)
        
        return json.dumps(data, indent=self.json_indent, sort_keys=True)
    
    def format_text(self, data: Dict, function: str) -> str:
        """
        Format data as human-readable text.
        
        Args:
            data: Data to format
            function: Function name (interfaces, routes, rules, etc.)
            
        Returns:
            Text formatted string
        """
        if function == 'summary':
            return self.format_summary(data)
        elif function == 'interfaces':
            return self.format_interfaces(data)
        elif function == 'routes':
            return self.format_routes(data)
        elif function == 'rules':
            return self.format_rules(data)
        elif function == 'iptables':
            return self.format_iptables(data)
        elif function == 'ipsets':
            return self.format_ipsets(data)
        elif function == 'all':
            return self.format_all(data)
        else:
            # Default to summary
            return self.format_summary(data)
    
    def format_summary(self, data: Dict) -> str:
        """Format summary view of namespace data."""
        sections = []
        
        for namespace, ns_data in sorted(data.items()):
            if isinstance(ns_data, dict) and 'error' in ns_data:
                sections.append(f"=== {namespace} ===")
                sections.append(f"  Error: {ns_data['error']}")
                continue
            
            sections.append(f"=== {namespace} SUMMARY ===")
            
            # Count interfaces
            if 'interfaces' in ns_data:
                ifaces = ns_data['interfaces']
                if isinstance(ifaces, dict):
                    non_lo = [i for i in ifaces if i != 'lo']
                    sections.append(f"  Interfaces: {len(non_lo)}")
            
            # Count routes
            if 'routes' in ns_data:
                routes = ns_data['routes']
                if isinstance(routes, dict):
                    for table_name, table_routes in routes.items():
                        if isinstance(table_routes, list):
                            sections.append(f"  Routes ({table_name}): {len(table_routes)}")
            
            # Count rules
            if 'rules' in ns_data:
                rules = ns_data['rules']
                if isinstance(rules, list):
                    sections.append(f"  Policy rules: {len(rules)}")
            
            # Count iptables rules
            if 'iptables' in ns_data:
                iptables = ns_data['iptables']
                if isinstance(iptables, dict):
                    total_rules = 0
                    for table_name, table_data in iptables.items():
                        if isinstance(table_data, dict) and 'chains' in table_data:
                            for chain_name, chain_data in table_data['chains'].items():
                                if 'rules' in chain_data:
                                    total_rules += len(chain_data['rules'])
                    sections.append(f"  Iptables rules: {total_rules}")
            
            # Count ipsets
            if 'ipsets' in ns_data:
                ipsets = ns_data['ipsets']
                if isinstance(ipsets, dict):
                    sections.append(f"  Ipsets: {len(ipsets)}")
            
            sections.append("")
        
        return '\n'.join(sections)
    
    def format_interfaces(self, data: Dict) -> str:
        """Format interface data as text."""
        sections = []
        
        for namespace, ns_data in sorted(data.items()):
            sections.append(f"=== {namespace} INTERFACES ===")
            
            if isinstance(ns_data, dict) and 'interfaces' in ns_data:
                interfaces = ns_data['interfaces']
            else:
                interfaces = ns_data  # Direct interface data
            
            if isinstance(interfaces, dict):
                for iface_name, iface_data in sorted(interfaces.items()):
                    # Apply name translation
                    display_name = iface_name
                    if self.translate_names and self.name_translator:
                        original = self.name_translator.translate(iface_name)
                        if original != iface_name and self.show_original_names:
                            display_name = f"{iface_name}({original})"
                    
                    sections.append(f"  {display_name}:")
                    
                    if isinstance(iface_data, dict):
                        if 'addresses' in iface_data:
                            for addr in iface_data['addresses']:
                                sections.append(f"    inet {addr}")
                        if 'state' in iface_data:
                            sections.append(f"    state {iface_data['state']}")
                        if 'mtu' in iface_data:
                            sections.append(f"    mtu {iface_data['mtu']}")
            
            sections.append("")
        
        return '\n'.join(sections)
    
    def format_routes(self, data: Dict) -> str:
        """Format routing data as text."""
        sections = []
        
        for namespace, ns_data in sorted(data.items()):
            sections.append(f"=== {namespace} ROUTES ===")
            
            if isinstance(ns_data, dict) and 'routes' in ns_data:
                routes = ns_data['routes']
            else:
                routes = ns_data  # Direct routes data
            
            if isinstance(routes, dict):
                for table_name, table_routes in sorted(routes.items()):
                    sections.append(f"  Table {table_name}:")
                    
                    if isinstance(table_routes, list):
                        for route in table_routes:
                            if isinstance(route, dict):
                                route_str = self._format_route_line(route)
                                sections.append(f"    {route_str}")
                    sections.append("")
            
            sections.append("")
        
        return '\n'.join(sections)
    
    def format_rules(self, data: Dict) -> str:
        """Format policy rules as text."""
        sections = []
        
        for namespace, ns_data in sorted(data.items()):
            sections.append(f"=== {namespace} POLICY RULES ===")
            
            if isinstance(ns_data, dict) and 'rules' in ns_data:
                rules = ns_data['rules']
            else:
                rules = ns_data  # Direct rules data
            
            if isinstance(rules, list):
                for rule in rules:
                    if isinstance(rule, dict):
                        rule_str = self._format_rule_line(rule)
                        sections.append(f"  {rule_str}")
            
            sections.append("")
        
        return '\n'.join(sections)
    
    def format_iptables(self, data: Dict) -> str:
        """Format iptables data as text."""
        sections = []
        
        for namespace, ns_data in sorted(data.items()):
            sections.append(f"=== {namespace} IPTABLES ===")
            
            if isinstance(ns_data, dict) and 'iptables' in ns_data:
                iptables = ns_data['iptables']
            else:
                iptables = ns_data  # Direct iptables data
            
            if isinstance(iptables, dict):
                for table_name, table_data in sorted(iptables.items()):
                    sections.append(f"  Table {table_name}:")
                    
                    if isinstance(table_data, dict) and 'chains' in table_data:
                        for chain_name, chain_data in sorted(table_data['chains'].items()):
                            policy = chain_data.get('policy', '-')
                            packets = chain_data.get('packets', 0)
                            bytes_cnt = chain_data.get('bytes', 0)
                            sections.append(f"    Chain {chain_name} (policy {policy} "
                                          f"{packets} packets, {bytes_cnt} bytes)")
                            
                            if 'rules' in chain_data:
                                for rule in chain_data['rules']:
                                    if 'raw' in rule:
                                        sections.append(f"      {rule['raw']}")
            
            sections.append("")
        
        return '\n'.join(sections)
    
    def format_ipsets(self, data: Dict) -> str:
        """Format ipset data as text."""
        sections = []
        
        for namespace, ns_data in sorted(data.items()):
            sections.append(f"=== {namespace} IPSETS ===")
            
            if isinstance(ns_data, dict) and 'ipsets' in ns_data:
                ipsets = ns_data['ipsets']
            else:
                ipsets = ns_data  # Direct ipsets data
            
            if isinstance(ipsets, dict):
                for ipset_name, ipset_data in sorted(ipsets.items()):
                    sections.append(f"  {ipset_name}:")
                    
                    if isinstance(ipset_data, dict):
                        if 'type' in ipset_data:
                            sections.append(f"    Type: {ipset_data['type']}")
                        if 'members' in ipset_data:
                            sections.append(f"    Members: {len(ipset_data['members'])}")
                            for member in ipset_data['members'][:5]:  # Show first 5
                                sections.append(f"      {member}")
                            if len(ipset_data['members']) > 5:
                                sections.append(f"      ... and {len(ipset_data['members']) - 5} more")
            
            sections.append("")
        
        return '\n'.join(sections)
    
    def format_all(self, data: Dict) -> str:
        """Format all data as text."""
        sections = []
        
        # Format each section
        sections.append(self.format_interfaces(data))
        sections.append(self.format_routes(data))
        sections.append(self.format_rules(data))
        sections.append(self.format_iptables(data))
        sections.append(self.format_ipsets(data))
        
        return '\n'.join(sections)
    
    def _format_route_line(self, route: Dict) -> str:
        """Format a single route as text line."""
        parts = []
        
        dst = route.get('dst', 'default')
        parts.append(dst)
        
        if 'gateway' in route:
            parts.append(f"via {route['gateway']}")
        
        if 'dev' in route:
            dev = route['dev']
            # Apply name translation
            if self.translate_names and self.name_translator:
                original = self.name_translator.translate(dev)
                if original != dev and self.show_original_names:
                    dev = f"{dev}({original})"
            parts.append(f"dev {dev}")
        
        if 'prefsrc' in route:
            parts.append(f"src {route['prefsrc']}")
        
        if 'protocol' in route:
            parts.append(f"proto {route['protocol']}")
        
        if 'scope' in route:
            parts.append(f"scope {route['scope']}")
        
        if 'metric' in route:
            parts.append(f"metric {route['metric']}")
        
        return ' '.join(parts)
    
    def _format_rule_line(self, rule: Dict) -> str:
        """Format a single policy rule as text line."""
        parts = []
        
        priority = rule.get('priority', 0)
        parts.append(f"{priority}:")
        
        if 'src' in rule:
            parts.append(f"from {rule['src']}")
        
        if 'dst' in rule:
            parts.append(f"to {rule['dst']}")
        
        if 'iifname' in rule:
            parts.append(f"iif {rule['iifname']}")
        
        if 'oifname' in rule:
            parts.append(f"oif {rule['oifname']}")
        
        if 'table' in rule:
            parts.append(f"lookup {rule['table']}")
        
        return ' '.join(parts)
    
    def _apply_name_translation_to_dict(self, data: Dict) -> Dict:
        """Recursively apply interface name translation to dictionary."""
        if not self.name_translator:
            return data
        
        # This is a simplified version - full implementation would
        # recursively traverse and translate interface names
        return data
    
    def format_table(self, data: Dict, function: str) -> str:
        """
        Format data as a table.
        
        Args:
            data: Data to format
            function: Function name (only 'summary' is currently supported)
            
        Returns:
            Table formatted string
        """
        if function != 'summary':
            # For non-summary functions, fall back to text format
            return self.format_text(data, function)
        
        return self.format_summary_table(data)
    
    def format_summary_table(self, data: Dict) -> str:
        """Format summary data as a table."""
        if not data:
            return "No namespaces found."
        
        # Collect table data
        rows = []
        headers = ["Router", "Interfaces", "Routes (main)", "Policy rules", "Iptables rules", "Ipsets"]
        
        for namespace in sorted(data.keys()):
            ns_data = data[namespace]
            
            if isinstance(ns_data, dict) and 'error' in ns_data:
                # Handle error case
                rows.append([namespace, "ERROR", "ERROR", "ERROR", "ERROR", "ERROR"])
                continue
            
            # Extract counts from namespace data
            interface_count = 0
            route_count = 0
            rule_count = 0
            iptables_count = 0
            ipset_count = 0
            
            # Count interfaces
            if 'interfaces' in ns_data and isinstance(ns_data['interfaces'], dict):
                interface_count = len(ns_data['interfaces'])
            
            # Count routes in main table
            if 'routes' in ns_data and isinstance(ns_data['routes'], dict):
                routes = ns_data['routes']
                if 'main' in routes and isinstance(routes['main'], list):
                    route_count = len(routes['main'])
            
            # Count policy rules
            if 'rules' in ns_data and isinstance(ns_data['rules'], list):
                rule_count = len(ns_data['rules'])
            
            # Count iptables rules (sum across all tables and chains)
            if 'iptables' in ns_data and isinstance(ns_data['iptables'], dict):
                for table_name, table_data in ns_data['iptables'].items():
                    if isinstance(table_data, dict) and 'chains' in table_data:
                        for chain_name, chain_data in table_data['chains'].items():
                            if isinstance(chain_data, dict) and 'rules' in chain_data:
                                if isinstance(chain_data['rules'], list):
                                    iptables_count += len(chain_data['rules'])
            
            # Count ipsets
            if 'ipsets' in ns_data and isinstance(ns_data['ipsets'], dict):
                ipset_count = len(ns_data['ipsets'])
            
            rows.append([
                namespace,
                str(interface_count),
                str(route_count), 
                str(rule_count),
                str(iptables_count),
                str(ipset_count)
            ])
        
        # Calculate column widths
        col_widths = []
        for i in range(len(headers)):
            max_width = len(headers[i])
            for row in rows:
                max_width = max(max_width, len(row[i]))
            col_widths.append(max_width)
        
        # Format table
        lines = []
        
        # Header row
        header_row = "  ".join(headers[i].ljust(col_widths[i]) for i in range(len(headers)))
        lines.append(header_row)
        
        # Separator line
        separator = "  ".join("-" * col_widths[i] for i in range(len(headers)))
        lines.append(separator)
        
        # Data rows
        for row in rows:
            data_row = "  ".join(row[i].ljust(col_widths[i]) for i in range(len(row)))
            lines.append(data_row)
        
        return "\n".join(lines)