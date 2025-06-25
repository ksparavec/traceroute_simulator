#!/usr/bin/env python3
"""
Network Namespace Status Tool

Displays the current state of the namespace-based network simulation with
original interface names restored using the reversible hash function.

Shows IP configuration, routing tables, and policy rules for any router
in the simulation, making it easy to debug and verify the network setup.

Features:
- Displays IP addresses and interface configuration
- Shows routing tables with original interface names
- Shows policy routing rules
- Supports querying specific routers or all routers
- Uses reversible hash function to display original names
- Comprehensive network status overview

Usage:
    python3 network_namespace_status.py <router_name> <function>
    python3 network_namespace_status.py all summary
    python3 network_namespace_status.py hq-gw interfaces
    python3 network_namespace_status.py br-core routes
    python3 network_namespace_status.py dc-srv rules

Functions:
    interfaces  - Show IP configuration (ip addr show equivalent)
    routes      - Show routing table (ip route show equivalent) 
    rules       - Show policy rules (ip rule show equivalent)
    summary     - Show brief overview of all configuration
    all         - Show complete configuration

Environment Variables:
    TRACEROUTE_SIMULATOR_FACTS - Directory containing router JSON facts files
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Any


class NetworkNamespaceStatus:
    """
    Displays status of namespace network simulation with original interface names.
    
    Provides comprehensive view of network configuration including interfaces,
    routing tables, and policy rules with proper name translation.
    """
    
    def __init__(self, facts_dir: str, verbose: int = 0):
        """
        Initialize the network status tool.
        
        Args:
            facts_dir: Directory containing router JSON facts files
            verbose: Verbosity level (0=silent, 1=basic, 2=info, 3=debug)
        """
        self.facts_dir = Path(facts_dir)
        self.verbose = verbose
        self.setup_logging()
        
        # Network state tracking
        self.routers: Dict[str, Dict] = {}
        self.available_namespaces: Set[str] = set()
        
        # Reversible name mapping reconstruction
        self.name_map: Dict[str, str] = {}  # short_name -> original_name
        self.reverse_name_map: Dict[str, str] = {}  # original_name -> short_name
        self.interface_counter = 0
        
        # Check for mandatory tools
        if not self.check_command_availability("ip"):
            raise RuntimeError("Error: 'ip' command not available - required for namespace operations. Install with: sudo apt-get install iproute2")
        
        # Load router facts and rebuild name mapping
        self.load_router_facts()
        self.discover_namespaces()
        self.rebuild_name_mapping()
        
    def setup_logging(self):
        """Configure logging based on verbosity level."""
        # Configure logging levels based on verbosity
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
        
    def discover_namespaces(self):
        """Discover available network namespaces."""
        self.logger.debug("Discovering available namespaces")
        
        try:
            result = self.run_command("ip netns list", check=False)
            if result.returncode != 0:
                self.logger.warning("Failed to list namespaces")
                return
                
            # Parse namespace list
            for line in result.stdout.split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                # Extract namespace name (format: "namespace_name (id: X)")
                ns_match = re.match(r'^([^\s(]+)', line)
                if ns_match:
                    namespace = ns_match.group(1)
                    if namespace in self.routers:
                        self.available_namespaces.add(namespace)
                        
        except Exception as e:
            self.logger.error(f"Error discovering namespaces: {e}")
            
        self.logger.info(f"Found {len(self.available_namespaces)} available router namespaces")
        
    def rebuild_name_mapping(self):
        """Rebuild the interface name mapping by analyzing current network topology."""
        self.logger.debug("Rebuilding interface name mapping")
        
        # Parse interface information from each router to recreate the mapping
        subnet_routers: Dict[str, List[tuple]] = {}
        
        for router_name, facts in self.routers.items():
            network_data = facts.get('network', {})
            interfaces_list = network_data.get('interfaces', [])
            
            # Process interface information from network.interfaces section
            for interface_info in interfaces_list:
                prefsrc = interface_info.get('prefsrc')
                dev = interface_info.get('dev')
                protocol = interface_info.get('protocol')
                scope = interface_info.get('scope')
                dst = interface_info.get('dst')
                
                # Only process kernel routes with preferred source (interface IPs)
                if (protocol == 'kernel' and scope == 'link' and 
                    prefsrc and dev and dst and '/' in dst):
                    
                    ip_addr = prefsrc
                    
                    # Skip loopback addresses
                    if ip_addr.startswith('127.'):
                        continue
                    
                    # Extract prefix length from destination network
                    try:
                        import ipaddress
                        network = ipaddress.IPv4Network(dst, strict=False)
                        subnet_str = str(network)
                        prefix_len = network.prefixlen
                    except (ipaddress.AddressValueError, ValueError):
                        continue
                    
                    # Track which routers are on each subnet
                    if subnet_str not in subnet_routers:
                        subnet_routers[subnet_str] = []
                    subnet_routers[subnet_str].append((router_name, dev, ip_addr))
                    
        # Recreate the mapping using the same logic as setup
        for subnet, router_interfaces in subnet_routers.items():
            if len(router_interfaces) == 2:
                # Two routers on same subnet - veth pair
                (router1, if1, ip1), (router2, if2, ip2) = router_interfaces
                veth1_orig = f"{router1}-{if1}"
                veth2_orig = f"{router2}-{if2}"
                self._get_short_name(veth1_orig)
                self._get_short_name(veth2_orig)
            elif len(router_interfaces) > 2:
                # Multiple routers - star topology
                hub_router, hub_if, hub_ip = router_interfaces[0]
                for router, interface, ip in router_interfaces[1:]:
                    veth1_orig = f"{hub_router}-{hub_if}-{router}"
                    veth2_orig = f"{router}-{interface}"
                    self._get_short_name(veth1_orig)
                    self._get_short_name(veth2_orig)
                    
        self.logger.debug(f"Rebuilt mapping for {len(self.name_map)} interface names")
        
    def _get_short_name(self, original_name: str) -> str:
        """Generate short name using same logic as setup script."""
        if original_name in self.reverse_name_map:
            return self.reverse_name_map[original_name]
            
        short_name = f"v{self.interface_counter:03d}"
        self.interface_counter += 1
        
        self.name_map[short_name] = original_name
        self.reverse_name_map[original_name] = short_name
        
        return short_name
        
    def get_original_name(self, short_name: str) -> str:
        """Get original interface name from short name."""
        return self.name_map.get(short_name, short_name)
        
    def check_command_availability(self, command: str) -> bool:
        """Check if a command is available on the system."""
        try:
            result = subprocess.run(
                f"which {command}",
                shell=True,
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode == 0
        except Exception:
            return False
            
    def run_command(self, command: str, namespace: str = None, check: bool = True) -> subprocess.CompletedProcess:
        """Execute command optionally in namespace."""
        if namespace:
            full_command = f"ip netns exec {namespace} {command}"
        else:
            full_command = command
            
        self.logger.debug(f"Running: {full_command}")
        
        try:
            result = subprocess.run(
                full_command,
                shell=True,
                capture_output=True,
                text=True,
                check=check
            )
            return result
        except subprocess.CalledProcessError as e:
            if check:
                raise
            return e
            
    def show_interfaces(self, router: str) -> str:
        """Show interface configuration with original names."""
        if router not in self.available_namespaces:
            return f"Router {router} namespace not found"
            
        result = self.run_command("ip addr show", namespace=router, check=False)
        if result.returncode != 0:
            return f"Failed to get interface information for {router}"
            
        # Parse and translate interface names
        output_lines = []
        current_short_name = None
        
        for line in result.stdout.split('\n'):
            # Check for interface header line
            if_match = re.match(r'^(\d+):\s+([^@:]+)(@[^:]*)?:', line)
            if if_match:
                interface_name = if_match.group(2)
                current_short_name = interface_name
                
                # Translate interface name if it's a short name
                if interface_name.startswith('v') and re.match(r'^v\d{3}$', interface_name):
                    original_name = self.get_original_name(interface_name)
                    translated_line = line.replace(interface_name, f"{interface_name}({original_name})")
                    output_lines.append(translated_line)
                else:
                    output_lines.append(line)
            else:
                output_lines.append(line)
                
        return '\n'.join(output_lines)
        
    def show_routes(self, router: str) -> str:
        """Show routing table with original interface names."""
        if router not in self.available_namespaces:
            return f"Router {router} namespace not found"
            
        result = self.run_command("ip route show", namespace=router, check=False)
        if result.returncode != 0:
            return f"Failed to get routing information for {router}"
            
        # Parse and translate interface names in routes
        output_lines = []
        
        for line in result.stdout.split('\n'):
            if not line.strip():
                continue
                
            # Look for 'dev interface_name' patterns
            translated_line = line
            dev_matches = re.finditer(r'\bdev\s+(v\d{3})\b', line)
            for match in dev_matches:
                short_name = match.group(1)
                original_name = self.get_original_name(short_name)
                translated_line = translated_line.replace(
                    f"dev {short_name}", 
                    f"dev {short_name}({original_name})"
                )
                
            output_lines.append(translated_line)
            
        return '\n'.join(output_lines)
        
    def show_rules(self, router: str) -> str:
        """Show policy routing rules."""
        if router not in self.available_namespaces:
            return f"Router {router} namespace not found"
            
        result = self.run_command("ip rule show", namespace=router, check=False)
        if result.returncode != 0:
            return f"Failed to get policy rules for {router}"
            
        return result.stdout
        
    def show_summary(self, router: str) -> str:
        """Show brief summary of router configuration."""
        if router not in self.available_namespaces:
            return f"Router {router} namespace not found"
            
        summary_lines = [f"=== {router} SUMMARY ==="]
        
        # Get interface count and IPs
        addr_result = self.run_command("ip addr show", namespace=router, check=False)
        if addr_result.returncode == 0:
            interfaces = []
            current_if = None
            
            for line in addr_result.stdout.split('\n'):
                if_match = re.match(r'^\d+:\s+([^@:]+)', line)
                if if_match:
                    current_if = if_match.group(1)
                    if current_if != 'lo':  # Skip loopback
                        interfaces.append(current_if)
                        
                ip_match = re.match(r'^\s*inet\s+([^/]+)/(\d+)', line)
                if ip_match and current_if and current_if != 'lo':
                    ip_addr = ip_match.group(1)
                    prefix = ip_match.group(2)
                    
                    # Translate interface name
                    display_name = current_if
                    if current_if.startswith('v') and re.match(r'^v\d{3}$', current_if):
                        original_name = self.get_original_name(current_if)
                        display_name = f"{current_if}({original_name})"
                        
                    summary_lines.append(f"  {display_name}: {ip_addr}/{prefix}")
                    
        # Get route count
        route_result = self.run_command("ip route show", namespace=router, check=False)
        if route_result.returncode == 0:
            route_count = len([line for line in route_result.stdout.split('\n') if line.strip()])
            summary_lines.append(f"  Routes: {route_count}")
            
        return '\n'.join(summary_lines)
        
    def show_all_configuration(self, router: str) -> str:
        """Show complete configuration for router."""
        if router not in self.available_namespaces:
            return f"Router {router} namespace not found"
            
        sections = []
        
        # Interfaces
        sections.append(f"=== {router} INTERFACES ===")
        sections.append(self.show_interfaces(router))
        
        # Routes
        sections.append(f"\n=== {router} ROUTES ===")
        sections.append(self.show_routes(router))
        
        # Rules
        sections.append(f"\n=== {router} RULES ===")
        sections.append(self.show_rules(router))
        
        return '\n'.join(sections)
        
    def show_all_routers_summary(self) -> str:
        """Show summary for all available routers."""
        if not self.available_namespaces:
            return "No router namespaces found"
            
        sections = ["=== NETWORK SIMULATION STATUS ==="]
        sections.append(f"Available routers: {len(self.available_namespaces)}")
        sections.append(f"Interface mappings: {len(self.name_map)}")
        sections.append("")
        
        for router in sorted(self.available_namespaces):
            sections.append(self.show_summary(router))
            sections.append("")
            
        return '\n'.join(sections)


def main():
    """Main entry point for network status tool."""
    parser = argparse.ArgumentParser(
        description="Show network namespace simulation status with original interface names",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s all summary                    # Overview of all routers
  %(prog)s hq-gw interfaces              # Interface config for hq-gw
  %(prog)s br-core routes                # Routing table for br-core
  %(prog)s dc-srv rules                  # Policy rules for dc-srv
  %(prog)s hq-dmz all                    # Complete config for hq-dmz
  %(prog)s hq-gw interfaces -v           # Interface config with basic verbosity
  %(prog)s all summary -vv               # Overview with info messages
  %(prog)s br-core routes -vvv           # Routing table with debug output
  
Functions:
  interfaces  - IP configuration (ip addr show equivalent)
  routes      - Routing table (ip route show equivalent)
  rules       - Policy rules (ip rule show equivalent)  
  summary     - Brief overview
  all         - Complete configuration
  
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
        'router',
        type=str,
        help='Router name (e.g., hq-gw, br-core, dc-srv) or "all" for all routers'
    )
    
    parser.add_argument(
        'function',
        type=str,
        choices=['interfaces', 'routes', 'rules', 'summary', 'all'],
        help='Information to display'
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
        print("Example: TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output")
        sys.exit(1)
    
    # Check for root privileges
    if os.geteuid() != 0:
        print("Error: This script requires root privileges to access network namespaces")
        print("Please run with sudo:")
        print(f"  sudo {' '.join(sys.argv)}")
        sys.exit(1)
        
    try:
        status_tool = NetworkNamespaceStatus(facts_dir, args.verbose)
        
        if args.router == 'all' and args.function == 'summary':
            output = status_tool.show_all_routers_summary()
        elif args.router == 'all':
            # Show function for all routers
            output_sections = []
            for router in sorted(status_tool.available_namespaces):
                if args.function == 'interfaces':
                    output_sections.append(f"=== {router} INTERFACES ===")
                    output_sections.append(status_tool.show_interfaces(router))
                elif args.function == 'routes':
                    output_sections.append(f"=== {router} ROUTES ===")
                    output_sections.append(status_tool.show_routes(router))
                elif args.function == 'rules':
                    output_sections.append(f"=== {router} RULES ===")
                    output_sections.append(status_tool.show_rules(router))
                elif args.function == 'all':
                    output_sections.append(status_tool.show_all_configuration(router))
                output_sections.append("")
            output = '\n'.join(output_sections)
        else:
            # Show specific function for specific router
            if args.function == 'interfaces':
                output = status_tool.show_interfaces(args.router)
            elif args.function == 'routes':
                output = status_tool.show_routes(args.router)
            elif args.function == 'rules':
                output = status_tool.show_rules(args.router)
            elif args.function == 'summary':
                output = status_tool.show_summary(args.router)
            elif args.function == 'all':
                output = status_tool.show_all_configuration(args.router)
            else:
                print(f"Unknown function: {args.function}")
                sys.exit(1)
                
        print(output)
        
    except Exception as e:
        print(f"Status check failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()