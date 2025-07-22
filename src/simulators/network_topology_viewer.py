#!/usr/bin/env python3
"""
Network Topology Viewer

Displays static network topology information from router facts files only.
Shows the intended network design without checking live namespace status.

Features:
- Complete router configuration from static facts
- Network topology and subnet relationships
- Interface configuration and IP assignments
- Routing table information from facts
- Policy rules from facts
- No live namespace inspection

Usage:
    python3 network_topology_viewer.py <router_name> <function>
    python3 network_topology_viewer.py all summary
    python3 network_topology_viewer.py hq-gw interfaces
    python3 network_topology_viewer.py br-core routes
    python3 network_topology_viewer.py all topology

Functions:
    interfaces  - Show interface configuration from facts
    routes      - Show routing table from facts
    rules       - Show policy rules from facts
    summary     - Show brief overview of router configuration
    topology    - Show network topology and subnet connections
    all         - Show complete configuration from facts

Environment Variables:
    TRACEROUTE_SIMULATOR_FACTS - Directory containing router JSON facts files
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Any


class NetworkTopologyViewer:
    """
    Displays static network topology from router facts files.
    
    Shows intended network design from JSON facts without live namespace inspection.
    """
    
    def __init__(self, facts_dir: str, verbose: int = 0):
        """
        Initialize the topology viewer.
        
        Args:
            facts_dir: Directory containing router JSON facts files
            verbose: Verbosity level (0=silent, 1=basic, 2=info, 3=debug)
        """
        self.facts_dir = Path(facts_dir)
        self.verbose = verbose
        self.setup_logging()
        
        # Network state from facts only
        self.routers: Dict[str, Dict] = {}
        self.hosts: Dict[str, Dict] = {}  # host registry data
        self.host_registry_file = Path("/tmp/traceroute_hosts_registry.json")
        
        # Subnet topology data (extracted from router facts)
        self.subnets: Dict[str, List[tuple]] = {}  # subnet -> [(router, interface, ip)]
        
        # Load all data
        self.load_router_facts()
        self.load_host_registry()
        self.build_subnet_topology()
        
    def setup_logging(self):
        """Configure logging based on verbosity level."""
        if self.verbose == 0:
            level = logging.CRITICAL  # Silent mode - only critical errors
        elif self.verbose == 1:
            level = logging.ERROR     # Basic mode - errors only
        elif self.verbose == 2:
            level = logging.INFO      # Info mode - info and errors
        else:  # verbose >= 3
            level = logging.DEBUG     # Debug mode - everything
            
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)
        
    def load_router_facts(self):
        """Load network facts from all router JSON files."""
        self.logger.info(f"Loading router facts from {self.facts_dir}")
        
        if not self.facts_dir.exists():
            raise FileNotFoundError(f"Facts directory not found: {self.facts_dir}")
            
        facts_files = list(self.facts_dir.glob("*.json"))
        if not facts_files:
            raise FileNotFoundError(f"No JSON facts files found in {self.facts_dir}")
            
        for facts_file in facts_files:
            # Skip metadata files and test variations
            if "_metadata.json" in facts_file.name or "_" in facts_file.stem:
                continue
                
            router_name = facts_file.stem
            self.logger.debug(f"Loading facts for router: {router_name}")
            
            try:
                with open(facts_file, 'r') as f:
                    facts = json.load(f)
                    self.routers[router_name] = facts
            except (json.JSONDecodeError, IOError) as e:
                self.logger.error(f"Failed to load {facts_file}: {e}")
                continue
                
        self.logger.info(f"Loaded facts for {len(self.routers)} routers")
        
    def load_host_registry(self):
        """Load host registry data from host registry file."""
        self.logger.debug("Loading host registry data")
        
        if not self.host_registry_file.exists():
            self.logger.debug("No host registry file found")
            return
            
        try:
            with open(self.host_registry_file, 'r') as f:
                host_registry = json.load(f)
                self.hosts = host_registry
                
            self.logger.info(f"Loaded registry for {len(self.hosts)} hosts")
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Failed to load host registry: {e}")
        
    def build_subnet_topology(self):
        """Build subnet topology information from router facts."""
        self.logger.debug("Building subnet topology from router facts")
        
        for router_name, facts in self.routers.items():
            # Use routing table data which is more reliable
            routing_data = facts.get('routing', {})
            routing_tables = routing_data.get('tables', [])
            
            # Extract interface information from routing tables
            for route_info in routing_tables:
                prefsrc = route_info.get('prefsrc')
                dev = route_info.get('dev')
                protocol = route_info.get('protocol')
                scope = route_info.get('scope')
                dst = route_info.get('dst')
                
                # Only process kernel routes with preferred source (interface IPs)
                if (protocol == 'kernel' and scope == 'link' and 
                    prefsrc and dev and dst and '/' in dst):
                    
                    subnet = dst
                    router_iface = dev
                    ip = prefsrc
                    
                    # Skip loopback
                    if ip.startswith('127.'):
                        continue
                    
                    if subnet not in self.subnets:
                        self.subnets[subnet] = []
                    self.subnets[subnet].append((router_name, router_iface, ip))
                    
        self.logger.info(f"Built topology for {len(self.subnets)} subnets")
        
    def get_connected_hosts(self, router: str) -> Dict[str, Dict]:
        """Get all hosts connected to a specific router."""
        connected_hosts = {}
        for host_name, host_config in self.hosts.items():
            connected_to = host_config.get('connected_to')
            if connected_to == router:
                connected_hosts[host_name] = host_config
        return connected_hosts
        
    def get_hosts_in_subnet(self, subnet: str) -> List[str]:
        """Get hosts that have IPs in the specified subnet."""
        import ipaddress
        try:
            subnet_network = ipaddress.IPv4Network(subnet, strict=False)
        except ipaddress.AddressValueError:
            return []
            
        hosts_in_subnet = []
        for host_name, host_config in self.hosts.items():
            primary_ip = host_config.get('primary_ip', '')
            if primary_ip and '/' in primary_ip:
                try:
                    host_network = ipaddress.IPv4Network(primary_ip, strict=False)
                    if host_network.subnet_of(subnet_network) or host_network.overlaps(subnet_network):
                        hosts_in_subnet.append(host_name)
                except ipaddress.AddressValueError:
                    continue
                    
        return hosts_in_subnet
        
    def show_host_summary(self, host: str) -> str:
        """Show brief summary of host configuration from registry."""
        if host not in self.hosts:
            return f"Host {host} not found in registry"
            
        host_config = self.hosts[host]
        sections = [f"=== {host.upper()} HOST SUMMARY (from registry) ==="]
        
        # Basic host information
        primary_ip = host_config.get('primary_ip', 'unknown')
        connected_to = host_config.get('connected_to', 'unknown')
        gateway_ip = host_config.get('gateway_ip', 'unknown')
        created_at = host_config.get('created_at', 'unknown')
        
        sections.append(f"  Type: host")
        sections.append(f"  Primary IP: {primary_ip}")
        sections.append(f"  Connected to: {connected_to} (gateway: {gateway_ip})")
        sections.append(f"  Created: {created_at}")
        
        # Secondary IPs
        secondary_ips = host_config.get('secondary_ips', [])
        if secondary_ips:
            sections.append(f"  Secondary IPs: {', '.join(secondary_ips)}")
            
        # Connection details
        connection_type = host_config.get('connection_type', 'unknown')
        sections.append(f"  Connection type: {connection_type}")
        
        mesh_bridge = host_config.get('mesh_bridge')
        if mesh_bridge:
            sections.append(f"  Mesh bridge: {mesh_bridge}")
            
        return '\n'.join(sections)
        
    def show_all_hosts(self) -> str:
        """Show summary of all registered hosts."""
        if not self.hosts:
            return "No hosts currently registered"
            
        sections = [f"=== ALL HOSTS SUMMARY (from registry) ==="]
        sections.append(f"Total hosts: {len(self.hosts)}")
        sections.append("")
        
        for host_name in sorted(self.hosts.keys()):
            sections.append(self.show_host_summary(host_name))
            sections.append("")
            
        return '\n'.join(sections)
        
    def show_interfaces(self, router: str) -> str:
        """Show interface configuration from facts."""
        if router not in self.routers:
            return f"Router {router} not found in facts"
            
        facts = self.routers[router]
        network_data = facts.get('network', {})
        interfaces_list = network_data.get('interfaces', [])
        
        sections = [f"=== {router.upper()} INTERFACE CONFIGURATION (from facts) ==="]
        
        # Group interfaces by device name
        interface_groups = {}
        for iface in interfaces_list:
            dev = iface.get('dev')
            if dev:
                if dev not in interface_groups:
                    interface_groups[dev] = []
                interface_groups[dev].append(iface)
        
        for dev_name in sorted(interface_groups.keys()):
            if dev_name == 'lo':  # Skip loopback
                continue
                
            sections.append(f"\nInterface: {dev_name}")
            
            for iface in interface_groups[dev_name]:
                protocol = iface.get('protocol', 'unknown')
                scope = iface.get('scope', 'unknown')
                dst = iface.get('dst', 'unknown')
                prefsrc = iface.get('prefsrc')
                
                if protocol == 'kernel' and scope == 'link' and prefsrc:
                    sections.append(f"  IP: {prefsrc} network: {dst}")
                elif dst and dst != 'unknown':
                    sections.append(f"  Route: {dst} protocol: {protocol}")
                    
        return '\n'.join(sections)
        
    def show_routes(self, router: str) -> str:
        """Show routing table from facts."""
        if router not in self.routers:
            return f"Router {router} not found in facts"
            
        facts = self.routers[router]
        routing_data = facts.get('routing', {})
        routes = routing_data.get('tables', [])
        
        sections = [f"=== {router.upper()} ROUTING TABLE (from facts) ==="]
        
        if not routes:
            sections.append("No routing information in facts")
            return '\n'.join(sections)
        
        # Group routes by type
        kernel_routes = []
        static_routes = []
        other_routes = []
        
        for route in routes:
            protocol = route.get('protocol', 'unknown')
            if protocol == 'kernel':
                kernel_routes.append(route)
            elif protocol == 'static':
                static_routes.append(route)
            else:
                other_routes.append(route)
        
        # Show kernel routes (interface networks)
        if kernel_routes:
            sections.append("\nKernel routes (interface networks):")
            for route in kernel_routes:
                dst = route.get('dst', 'unknown')
                dev = route.get('dev', 'unknown')
                prefsrc = route.get('prefsrc', '')
                if prefsrc:
                    sections.append(f"  {dst} dev {dev} src {prefsrc}")
                else:
                    sections.append(f"  {dst} dev {dev}")
        
        # Show static routes
        if static_routes:
            sections.append("\nStatic routes:")
            for route in static_routes:
                dst = route.get('dst', 'default')
                gateway = route.get('gateway')
                dev = route.get('dev')
                metric = route.get('metric')
                
                route_parts = [dst]
                if gateway:
                    route_parts.extend(['via', gateway])
                if dev:
                    route_parts.extend(['dev', dev])
                if metric:
                    route_parts.extend(['metric', str(metric)])
                    
                sections.append(f"  {' '.join(route_parts)}")
        
        # Show other routes
        if other_routes:
            sections.append("\nOther routes:")
            for route in other_routes:
                protocol = route.get('protocol', 'unknown')
                dst = route.get('dst', 'unknown')
                sections.append(f"  {dst} (protocol: {protocol})")
                
        return '\n'.join(sections)
        
    def show_rules(self, router: str) -> str:
        """Show policy routing rules from facts."""
        if router not in self.routers:
            return f"Router {router} not found in facts"
            
        facts = self.routers[router]
        routing_data = facts.get('routing', {})
        rules = routing_data.get('rules', [])
        
        sections = [f"=== {router.upper()} POLICY RULES (from facts) ==="]
        
        if not rules:
            sections.append("No policy rules in facts")
            return '\n'.join(sections)
        
        for rule in rules:
            priority = rule.get('priority', 'unknown')
            selector = rule.get('selector', 'unknown')
            action = rule.get('action', 'unknown')
            
            sections.append(f"  {priority}: {selector} {action}")
            
        return '\n'.join(sections)
        
    def show_summary(self, router: str) -> str:
        """Show router summary in exact same format as netstatus but from JSON facts."""
        if router not in self.routers:
            return f"Router {router} not found in facts"
            
        facts = self.routers[router]
        summary_lines = [f"=== {router} ROUTER SUMMARY ==="]
        summary_lines.append(f"  Type: Router")
        
        # Show interface addresses from JSON facts (network.interfaces.parsed)
        summary_lines.append("")
        summary_lines.append("  Interfaces:")
        network_data = facts.get('network', {})
        interfaces_data = network_data.get('interfaces', {})
        parsed_interfaces = interfaces_data.get('parsed', {})
        
        if parsed_interfaces:
            for if_name, if_data in parsed_interfaces.items():
                # Interface line (like "1: lo: <LOOPBACK,UP,LOWER_UP>...")
                index = if_data.get('index', 0)
                flags = if_data.get('flags', [])
                flags_str = ','.join(flags)
                mtu = if_data.get('mtu', 0)
                qdisc = if_data.get('qdisc', 'unknown')
                state = if_data.get('state', 'UNKNOWN')
                group = if_data.get('group', 'default')
                qlen = if_data.get('qlen', 0)
                
                summary_lines.append(f"    {index}: {if_name}: <{flags_str}> mtu {mtu} qdisc {qdisc} state {state} group {group} qlen {qlen}")
                
                # Link line
                link_type = if_data.get('link_type', 'ether')
                mac = if_data.get('mac_address', '00:00:00:00:00:00')
                broadcast = if_data.get('broadcast_address', 'ff:ff:ff:ff:ff:ff')
                summary_lines.append(f"        link/{link_type} {mac} brd {broadcast}")
                
                # Address lines
                addresses = if_data.get('addresses', [])
                for addr in addresses:
                    family = addr.get('family', 'inet')
                    address = addr.get('address', '')
                    prefixlen = addr.get('prefixlen', 0)
                    scope = addr.get('scope', 'global')
                    secondary = addr.get('secondary', False)
                    
                    addr_line = f"        {family} {address}/{prefixlen}"
                    if 'broadcast' in addr:
                        addr_line += f" brd {addr['broadcast']}"
                    addr_line += f" scope {scope}"
                    if secondary:
                        addr_line += " secondary"
                    addr_line += f" {if_name}"
                    summary_lines.append(addr_line)
                    summary_lines.append("           valid_lft forever preferred_lft forever")
        else:
            summary_lines.append("    (no interface data in facts)")
        
        # Show policy rules from JSON facts
        summary_lines.append("")
        summary_lines.append("  Policy Rules:")
        routing_data = facts.get('routing', {})
        rules = routing_data.get('rules', [])
        
        if rules:
            for rule in rules:
                priority = rule.get('priority', 0)
                src = rule.get('src', 'all')
                table = rule.get('table', 'main')
                summary_lines.append(f"    {priority}:\tfrom {src} lookup {table}")
        else:
            summary_lines.append("    (no policy rules in facts)")
        
        # Show routing table from JSON facts
        summary_lines.append("")
        summary_lines.append("  Routing Table:")
        tables = routing_data.get('tables', [])
        
        if tables:
            for route in tables:
                dst = route.get('dst', '')
                gateway = route.get('gateway', '')
                dev = route.get('dev', '')
                protocol = route.get('protocol', '')
                scope = route.get('scope', '')
                metric = route.get('metric', '')
                prefsrc = route.get('prefsrc', '')
                
                route_line = f"    {dst}"
                if gateway:
                    route_line += f" via {gateway}"
                if dev:
                    route_line += f" dev {dev}"
                if protocol:
                    route_line += f" proto {protocol}"
                if scope:
                    route_line += f" scope {scope}"
                if prefsrc:
                    route_line += f" src {prefsrc}"
                if metric:
                    route_line += f" metric {metric}"
                    
                summary_lines.append(route_line)
        else:
            summary_lines.append("    (no routing table in facts)")
        
        # Show iptables totals from JSON facts
        summary_lines.append("")
        firewall_data = facts.get('firewall', {})
        iptables_data = firewall_data.get('iptables', {})
        
        if iptables_data.get('available', False):
            total_rules = 0
            table_counts = {}
            
            for table_name in ['filter', 'nat', 'mangle', 'raw']:
                if table_name in iptables_data:
                    table_data = iptables_data[table_name]
                    if isinstance(table_data, list) and table_data:
                        for chain_entry in table_data:
                            for chain_name, rules in chain_entry.items():
                                if isinstance(rules, list):
                                    count = len(rules)
                                    total_rules += count
                                    if table_name not in table_counts:
                                        table_counts[table_name] = 0
                                    table_counts[table_name] += count
            
            if total_rules > 0:
                table_summary = ', '.join([f"{table}:{count}" for table, count in table_counts.items() if count > 0])
                summary_lines.append(f"  Iptables: {total_rules} rules ({table_summary})")
            else:
                summary_lines.append("  Iptables: 0 rules")
        else:
            summary_lines.append("  Iptables: (not available in facts)")
        
        # Show ipsets count from JSON facts
        ipset_data = firewall_data.get('ipset', {})
        if ipset_data.get('available', False):
            ipset_lists = ipset_data.get('lists', [])
            if isinstance(ipset_lists, list):
                ipset_count = 0
                for ipset_entry in ipset_lists:
                    if isinstance(ipset_entry, dict):
                        ipset_count += len(ipset_entry.keys())
                summary_lines.append(f"  Ipsets: {ipset_count} sets")
            else:
                summary_lines.append("  Ipsets: 0 sets")
        else:
            summary_lines.append("  Ipsets: (not available in facts)")
            
        return '\n'.join(summary_lines)
        
    def show_all_configuration(self, router: str) -> str:
        """Show complete configuration for router from facts."""
        if router not in self.routers:
            return f"Router {router} not found in facts"
            
        sections = []
        
        # Interfaces
        sections.append(self.show_interfaces(router))
        
        # Routes
        sections.append(f"\n{self.show_routes(router)}")
        
        # Rules
        sections.append(f"\n{self.show_rules(router)}")
        
        return '\n'.join(sections)
        
    def show_topology(self, specific_router: str = None) -> str:
        """Show network topology information from facts."""
        sections = []
        
        if specific_router:
            # Router-specific topology view
            if specific_router not in self.routers:
                return f"Router {specific_router} not found in facts"
            
            sections.append(f"=== {specific_router.upper()} TOPOLOGY (from facts) ===")
            
            # Find all subnets this router is connected to
            router_subnets = []
            connected_routers = set()
            
            for subnet, members in sorted(self.subnets.items()):
                # Check if this router is in this subnet
                router_in_subnet = None
                for router, iface, ip in members:
                    if router == specific_router:
                        router_in_subnet = (router, iface, ip)
                        break
                
                if router_in_subnet:
                    router_subnets.append((subnet, members))
                    # Track connected routers
                    for router, iface, ip in members:
                        if router != specific_router:
                            connected_routers.add(router)
            
            if not router_subnets:
                sections.append(f"{specific_router} has no network connections in facts")
                return '\n'.join(sections)
            
            sections.append(f"Network connections for {specific_router}:")
            sections.append("")
            
            for subnet, members in router_subnets:
                if len(members) == 1:
                    router, iface, ip = members[0]
                    sections.append(f"  {subnet}: {router}:{iface}({ip}) [external]")
                elif len(members) == 2:
                    (r1, i1, ip1), (r2, i2, ip2) = members
                    if r1 == specific_router:
                        sections.append(f"  {subnet}: {r1}:{i1}({ip1}) <-> {r2}:{i2}({ip2}) [point-to-point]")
                    else:
                        sections.append(f"  {subnet}: {r2}:{i2}({ip2}) <-> {r1}:{i1}({ip1}) [point-to-point]")
                else:
                    # Multi-access network - highlight the specific router
                    member_list = []
                    specific_router_info = None
                    for r, i, ip in members:
                        if r == specific_router:
                            specific_router_info = f"**{r}:{i}({ip})**"
                        else:
                            member_list.append(f"{r}:{i}({ip})")
                    
                    if specific_router_info:
                        all_members = [specific_router_info] + member_list
                        sections.append(f"  {subnet}: {', '.join(all_members)} [bridged]")
            
            if connected_routers:
                sections.append("")
                sections.append(f"Connected to {len(connected_routers)} other routers: {', '.join(sorted(connected_routers))}")
                
            # Show connected hosts for this router
            connected_hosts = self.get_connected_hosts(specific_router)
            if connected_hosts:
                sections.append("")
                sections.append(f"Connected hosts ({len(connected_hosts)}):")
                for host_name, host_config in sorted(connected_hosts.items()):
                    primary_ip = host_config.get('primary_ip', 'unknown')
                    secondary_ips = host_config.get('secondary_ips', [])
                    if secondary_ips:
                        all_ips = [primary_ip] + secondary_ips
                        sections.append(f"  {host_name}: {', '.join(all_ips)} [host]")
                    else:
                        sections.append(f"  {host_name}: {primary_ip} [host]")
            
        else:
            # Global topology view
            sections.append("=== NETWORK TOPOLOGY (from facts) ===")
            sections.append(f"Total routers in facts: {len(self.routers)}")
            
            if self.hosts:
                sections.append(f"Registered hosts: {len(self.hosts)}")
            
            sections.append("")
            
            # Subnet topology
            sections.append("Subnet topology:")
            for subnet, members in sorted(self.subnets.items()):
                if len(members) == 1:
                    router, iface, ip = members[0]
                    # Check if this subnet has any connected hosts
                    subnet_hosts = self.get_hosts_in_subnet(subnet)
                    if subnet_hosts:
                        host_list = [f"{h}:{self.hosts[h].get('primary_ip', 'unknown').split('/')[0]}" for h in subnet_hosts]
                        sections.append(f"  {subnet}: {router}:{iface}({ip}) + hosts({', '.join(host_list)}) [external+hosts]")
                    else:
                        sections.append(f"  {subnet}: {router}:{iface}({ip}) [external]")
                elif len(members) == 2:
                    (r1, i1, ip1), (r2, i2, ip2) = members
                    sections.append(f"  {subnet}: {r1}:{i1}({ip1}) <-> {r2}:{i2}({ip2}) [point-to-point]")
                else:
                    member_list = [f"{r}:{i}({ip})" for r, i, ip in members]
                    sections.append(f"  {subnet}: {', '.join(member_list)} [bridged]")
                    
            # Show host connections summary
            if self.hosts:
                sections.append("")
                sections.append("Host connections:")
                for host_name, host_config in sorted(self.hosts.items()):
                    connected_to = host_config.get('connected_to', 'unknown')
                    primary_ip = host_config.get('primary_ip', 'unknown')
                    sections.append(f"  {host_name}: {primary_ip} -> {connected_to}")
                
        return '\n'.join(sections)
        
    def show_all_summary(self) -> str:
        """Show summary in exact same format as netstatus but from JSON facts."""
        if not self.routers:
            return "No routers found in facts"
            
        # Count available routers and hosts from facts
        total_routers = len(self.routers)
        total_hosts = len(self.hosts) if self.hosts else 0
        total_entities = total_routers + total_hosts
        
        sections = ["=== STATIC FACTS STATUS ==="]
        sections.append(f"Available routers: {total_entities}")
        sections.append("")
        
        if total_entities > 0:
            sections.append("Available routers:")
            
            # Show all routers
            for router_name in sorted(self.routers.keys()):
                sections.append(f"  {router_name} [ROUTER]")
            
            # Show all hosts  
            if self.hosts:
                for host_name in sorted(self.hosts.keys()):
                    sections.append(f"  {host_name} [HOST]")
            
            sections.append("")
            
            # Show detailed summary for each router
            for router_name in sorted(self.routers.keys()):
                sections.append(self.show_summary(router_name))
                sections.append("")
                
            # Show detailed summary for each host
            if self.hosts:
                for host_name in sorted(self.hosts.keys()):
                    sections.append(self.show_host_summary(host_name))
                    sections.append("")
        else:
            sections.append("No routers available in facts.")
            sections.append("Check TRACEROUTE_SIMULATOR_FACTS environment variable.")
            
        return '\n'.join(sections)


def main():
    """Main entry point for network topology viewer."""
    parser = argparse.ArgumentParser(
        description="Show static network topology from router facts files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s all summary                    # Overview of all routers and hosts from facts
  %(prog)s all topology                   # Complete network topology from facts
  %(prog)s all hosts                      # Show all registered hosts
  %(prog)s hq-gw topology                # Network connections for hq-gw from facts
  %(prog)s hq-gw interfaces              # Interface config for hq-gw from facts
  %(prog)s hq-gw hosts                    # Show hosts connected to hq-gw
  %(prog)s br-core routes                # Routing table for br-core from facts
  %(prog)s dc-srv rules                  # Policy rules for dc-srv from facts
  %(prog)s hq-dmz all                    # Complete config for hq-dmz from facts
  %(prog)s web1 summary                  # Host summary for web1 from registry
  %(prog)s web1 topology                 # Show which router web1 is connected to
  %(prog)s hq-gw interfaces -v           # Interface config with basic verbosity
  %(prog)s all summary -vv               # Overview with info messages
  %(prog)s br-core routes -vvv           # Routing table with debug output
  
Functions:
  interfaces  - Interface configuration (routers only, from facts)
  routes      - Routing table (routers only, from facts)
  rules       - Policy rules (routers only, from facts)  
  summary     - Brief overview (routers and hosts, from facts/registry)
  topology    - Network topology (global) or connections (specific entity)
  hosts       - Host information (all hosts or hosts connected to router)
  all         - Complete configuration (routers only, from facts)
  
Verbosity Levels:
  (none)  - Silent mode: minimal output
  -v      - Basic mode: show errors and basic info
  -vv     - Info mode: basic + INFO level messages  
  -vvv    - Debug mode: info + DEBUG level messages
  
Environment Variables:
  TRACEROUTE_SIMULATOR_FACTS - Required facts directory path
        """
    )
    
    parser.add_argument(
        'target',
        type=str,
        help='Router or host name (e.g., hq-gw, br-core, web1) or "all" for all entities'
    )
    
    parser.add_argument(
        'function',
        type=str,
        choices=['interfaces', 'routes', 'rules', 'summary', 'topology', 'hosts', 'all'],
        help='Information to display from facts'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='count',
        default=0,
        help='Increase verbosity: -v (basic), -vv (info), -vvv (debug)'
    )
    
    args = parser.parse_args()
    
    # Get facts directory from environment (required)
    facts_dir = os.environ.get('TRACEROUTE_SIMULATOR_FACTS')
    if not facts_dir:
        print("Error: TRACEROUTE_SIMULATOR_FACTS environment variable must be set")
        print("Example: TRACEROUTE_SIMULATOR_FACTS=/path/to/facts")
        sys.exit(1)
        
    try:
        viewer = NetworkTopologyViewer(facts_dir, args.verbose)
        
        if args.target == 'all' and args.function == 'summary':
            output = viewer.show_all_summary()
        elif args.target == 'all' and args.function == 'topology':
            # Special case: topology is global, not per-router
            output = viewer.show_topology()
        elif args.target == 'all' and args.function == 'hosts':
            # Show all hosts
            output = viewer.show_all_hosts()
        elif args.target == 'all':
            # Show function for all routers (hosts not applicable for most functions)
            output_sections = []
            for router_name in sorted(viewer.routers.keys()):
                if args.function == 'interfaces':
                    output_sections.append(viewer.show_interfaces(router_name))
                elif args.function == 'routes':
                    output_sections.append(viewer.show_routes(router_name))
                elif args.function == 'rules':
                    output_sections.append(viewer.show_rules(router_name))
                elif args.function == 'all':
                    output_sections.append(viewer.show_all_configuration(router_name))
                output_sections.append("")
            output = '\n'.join(output_sections)
        else:
            # Check if target is a router or host
            is_router = args.target in viewer.routers
            is_host = args.target in viewer.hosts
            
            if not is_router and not is_host:
                print(f"Error: '{args.target}' not found in routers or hosts")
                sys.exit(1)
            
            # Handle host-specific functions
            if is_host:
                if args.function in ['interfaces', 'routes', 'rules', 'all']:
                    print(f"Error: Function '{args.function}' not applicable to hosts. Use 'summary' or 'hosts'.")
                    sys.exit(1)
                elif args.function == 'summary':
                    output = viewer.show_host_summary(args.target)
                elif args.function == 'hosts':
                    output = viewer.show_host_summary(args.target)
                elif args.function == 'topology':
                    # Show which router the host is connected to
                    host_config = viewer.hosts[args.target]
                    connected_to = host_config.get('connected_to', 'unknown')
                    primary_ip = host_config.get('primary_ip', 'unknown')
                    output = f"=== {args.target.upper()} HOST TOPOLOGY ===\nHost: {args.target}\nPrimary IP: {primary_ip}\nConnected to router: {connected_to}"
                else:
                    print(f"Unknown function for host: {args.function}")
                    sys.exit(1)
            else:
                # Handle router-specific functions
                if args.function == 'interfaces':
                    output = viewer.show_interfaces(args.target)
                elif args.function == 'routes':
                    output = viewer.show_routes(args.target)
                elif args.function == 'rules':
                    output = viewer.show_rules(args.target)
                elif args.function == 'summary':
                    output = viewer.show_summary(args.target)
                elif args.function == 'topology':
                    # For specific router, show router-specific topology
                    output = viewer.show_topology(args.target)
                elif args.function == 'hosts':
                    # Show hosts connected to this router
                    connected_hosts = viewer.get_connected_hosts(args.target)
                    if connected_hosts:
                        sections = [f"=== HOSTS CONNECTED TO {args.target.upper()} ==="]
                        for host_name, host_config in sorted(connected_hosts.items()):
                            sections.append(viewer.show_host_summary(host_name))
                            sections.append("")
                        output = '\n'.join(sections)
                    else:
                        output = f"No hosts connected to router {args.target}"
                elif args.function == 'all':
                    output = viewer.show_all_configuration(args.target)
                else:
                    print(f"Unknown function: {args.function}")
                    sys.exit(1)
                
        print(output)
        
    except Exception as e:
        print(f"Topology view failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()