#!/usr/bin/env -S python3 -B -u
"""
Network Namespace Status Tool

Displays the current LIVE status of running network namespaces only.
Shows what's actually running in the system without referencing static facts.

Features:
- Displays live IP addresses and interface configuration
- Shows live routing tables with original interface names
- Shows live policy routing rules
- Supports querying specific namespaces or all running namespaces
- Uses reversible hash function to display original names
- Live namespace status overview only

Usage:
    python3 network_namespace_status.py [function] [--limit <pattern>]
    python3 network_namespace_status.py summary                          # Overview of all namespaces (default)
    python3 network_namespace_status.py interfaces --limit hq-gw         # Interfaces for specific router
    python3 network_namespace_status.py routes --limit "*-core"          # Routes for core routers
    python3 network_namespace_status.py summary --limit "hq-*"           # Summary for HQ routers
    python3 network_namespace_status.py rules --limit br-gw              # Policy rules for specific router
    python3 network_namespace_status.py ipsets --limit dc-srv            # Ipsets for specific router

Functions:
    interfaces  - Show live IP configuration (ip addr show equivalent)
    routes      - Show live routing table (ip route show equivalent) 
    rules       - Show live policy rules (ip rule show equivalent)
    ipsets      - Show live ipset configuration (ipset list equivalent)
    summary     - Show brief overview of live configuration
    all         - Show complete live configuration

Environment Variables:
    TRACEROUTE_SIMULATOR_FACTS - Directory containing router JSON facts files (for interface name mapping only)
    
Note:
    Only shows data from LIVE running namespaces. For static topology, use network_topology_viewer.py
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

# Import configuration loader
from tsim.core.config_loader import get_registry_paths


class NetworkNamespaceStatus:
    """
    Displays LIVE status of running network namespaces only.
    
    Provides view of actual running network configuration including interfaces,
    routing tables, and policy rules with proper name translation.
    Does NOT show static topology - only what's currently running.
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
        
        # Live namespace state tracking only
        self.hosts: Dict[str, Dict] = {}  # host registry data
        self.available_namespaces: Set[str] = set()
        
        # Load registry paths from configuration
        registry_paths = get_registry_paths()
        self.host_registry_file = Path(registry_paths['hosts'])
        
        self.known_routers: Set[str] = set()  # routers from facts
        
        # Reversible name mapping reconstruction (from facts for display purposes only)
        self.name_map: Dict[str, str] = {}  # short_name -> original_name
        self.reverse_name_map: Dict[str, str] = {}  # original_name -> short_name
        self.interface_counter = 0
        
        # Check for mandatory tools
        if not self.check_command_availability("ip"):
            raise RuntimeError("Error: 'ip' command not available - required for namespace operations. Install with: sudo apt-get install iproute2")
        
        # Load minimal data for live status only
        self.load_known_routers()
        self.load_host_registry()
        self.discover_namespaces()
        # Only build name mapping for actually running namespaces
        self.rebuild_name_mapping_for_running_namespaces()
        
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
        
    def load_known_routers(self):
        """Load list of known routers from facts directory."""
        self.logger.debug(f"Loading known routers from {self.facts_dir}")
        
        if self.facts_dir.exists():
            for facts_file in self.facts_dir.glob("*.json"):
                # Skip metadata files and test variations
                if "_metadata.json" not in facts_file.name and "_" not in facts_file.stem:
                    self.known_routers.add(facts_file.stem)
        else:
            # Fallback: try to load from raw facts if JSON facts don't exist
            raw_facts_dir = self.facts_dir.parent / "raw_facts"
            if raw_facts_dir.exists():
                for facts_file in raw_facts_dir.glob("*_facts.txt"):
                    router_name = facts_file.stem.replace("_facts", "")
                    self.known_routers.add(router_name)
                    
        self.logger.debug(f"Found {len(self.known_routers)} known routers: {self.known_routers}")
        
    def load_router_facts_for_naming(self):
        """Load minimal router facts for interface name mapping only."""
        self.logger.debug(f"Loading router facts for name mapping from {self.facts_dir}")
        
        if not self.facts_dir.exists():
            self.logger.warning(f"Facts directory not found: {self.facts_dir} - interface name mapping disabled")
            return {}
            
        facts_files = list(self.facts_dir.glob("*.json"))
        if not facts_files:
            self.logger.warning(f"No JSON facts files found in {self.facts_dir} - interface name mapping disabled")
            return {}
            
        routers = {}
        for facts_file in facts_files:
            # Skip metadata files and test variations
            if "_metadata.json" in facts_file.name or "_" in facts_file.stem:
                continue
                
            router_name = facts_file.stem
            
            try:
                with open(facts_file, 'r') as f:
                    facts = json.load(f)
                    routers[router_name] = facts
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Failed to load {facts_file}: {e}")
                continue
                
        self.logger.debug(f"Loaded facts for {len(routers)} routers for name mapping")
        return routers
        
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
        
    def discover_namespaces(self):
        """Discover available network namespaces."""
        self.logger.debug("Discovering available namespaces")
        
        try:
            result = self.run_command("ip netns list", check=False)
            if result.returncode != 0:
                self.logger.warning("Failed to list namespaces")
                return
                
            # Parse namespace list - include ALL namespaces found
            for line in result.stdout.split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                # Extract namespace name (format: "namespace_name (id: X)")
                ns_match = re.match(r'^([^\s(]+)', line)
                if ns_match:
                    namespace = ns_match.group(1)
                    self.available_namespaces.add(namespace)
                        
        except Exception as e:
            self.logger.error(f"Error discovering namespaces: {e}")
            
        host_count = len([ns for ns in self.available_namespaces if ns in self.hosts])
        router_count = len(self.available_namespaces) - host_count
        self.logger.info(f"Found {router_count} router namespaces and {host_count} host namespaces")
        
    def rebuild_name_mapping_from_facts(self):
        """Rebuild interface name mapping from facts for display purposes only."""
        self.logger.debug("Rebuilding interface name mapping from facts")
        
        # Load minimal facts for name mapping
        routers = self.load_router_facts_for_naming()
        
        if not routers:
            self.logger.warning("No router facts available - interface name mapping disabled")
            return
        
        # Build name mapping using same logic as setup
        subnet_routers: Dict[str, List[tuple]] = {}
        
        for router_name, facts in routers.items():
            # Get routing table data to extract interface IPs
            routing_data = facts.get('routing', {})
            routing_tables = routing_data.get('tables', [])
            
            # Process routing table entries to find interface IPs
            for route_info in routing_tables:
                prefsrc = route_info.get('prefsrc')
                dev = route_info.get('dev')
                protocol = route_info.get('protocol')
                scope = route_info.get('scope')
                dst = route_info.get('dst')
                
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
        
    def is_system_namespace(self, namespace: str) -> bool:
        """Check if a namespace is a system namespace (not a known router or host)."""
        return namespace not in self.known_routers and namespace not in self.hosts
    
    def is_host(self, namespace: str) -> bool:
        """Check if a namespace is a registered host."""
        return namespace in self.hosts
        
    def is_router(self, namespace: str) -> bool:
        """Check if a namespace is a known router from facts."""
        return namespace in self.known_routers
    
    def _is_system_namespace(self, namespace: str) -> bool:
        """Check if a namespace is a truly system namespace that should be hidden."""
        # Hide system namespaces and internal infrastructure
        # Get hidden namespace from configuration
        from tsim.core.config_loader import get_network_setup_config
        network_config = get_network_setup_config()
        hidden_ns = network_config.get('hidden_namespace', 'tsim-hidden')
        system_namespaces = {'default', hidden_ns}
        return namespace in system_namespaces
    
    def _get_namespace_type(self, namespace: str) -> str:
        """Determine the type of a namespace using JSON facts and host registry."""
        # Get hidden namespace from configuration
        from tsim.core.config_loader import get_network_setup_config
        network_config = get_network_setup_config()
        hidden_ns = network_config.get('hidden_namespace', 'tsim-hidden')
        
        if namespace == hidden_ns:
            return 'INFRASTRUCTURE'
        elif namespace in self.known_routers:
            return 'ROUTER'
        elif namespace in self.hosts:
            return 'HOST'
        else:
            return 'UNKNOWN'
        
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
        # Add sudo if needed
        needs_sudo = False
        if os.geteuid() != 0:
            # Commands that need sudo
            if namespace or command.startswith("ip netns"):
                needs_sudo = True
        
        if namespace:
            if needs_sudo:
                full_command = f"sudo ip netns exec {namespace} {command}"
            else:
                full_command = f"ip netns exec {namespace} {command}"
        else:
            if needs_sudo:
                full_command = f"sudo {command}"
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
            
    def get_interfaces_data(self, namespace: str) -> Dict[str, Any]:
        """Get interface data in structured format."""
        if namespace not in self.available_namespaces:
            return {"error": f"Namespace {namespace} not found"}
            
        result = self.run_command("ip -j addr show", namespace=namespace, check=False)
        if result.returncode != 0:
            # Fallback to non-JSON format
            result = self.run_command("ip addr show", namespace=namespace, check=False)
            if result.returncode != 0:
                return {"error": f"Failed to get interface information for {namespace}"}
            
            # Parse text output
            interfaces = {}
            current_iface = None
            
            for line in result.stdout.split('\n'):
                # Interface line
                if_match = re.match(r'^(\d+):\s+([^@:]+)(@[^:]*)?:', line)
                if if_match:
                    current_iface = if_match.group(2)
                    interfaces[current_iface] = {"addresses": []}
                
                # IP address line
                elif current_iface and 'inet ' in line:
                    ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+/\d+)', line)
                    if ip_match:
                        interfaces[current_iface]["addresses"].append(ip_match.group(1))
            
            return {"namespace": namespace, "interfaces": interfaces}
        else:
            # Parse JSON output
            try:
                data = json.loads(result.stdout)
                interfaces = {}
                for iface in data:
                    name = iface.get("ifname", "unknown")
                    addresses = []
                    for addr_info in iface.get("addr_info", []):
                        if addr_info.get("family") == "inet":
                            ip = addr_info.get("local", "")
                            prefix = addr_info.get("prefixlen", 32)
                            addresses.append(f"{ip}/{prefix}")
                    interfaces[name] = {"addresses": addresses}
                return {"namespace": namespace, "interfaces": interfaces}
            except json.JSONDecodeError:
                return {"error": "Failed to parse interface data"}
    
    def get_routes_data(self, namespace: str) -> Dict[str, Any]:
        """Get routing data in structured format."""
        if namespace not in self.available_namespaces:
            return {"error": f"Namespace {namespace} not found"}
        
        # Dynamically discover active routing tables from policy rules
        discovered_tables = self._discover_routing_tables(namespace)
        
        routes_data = {}
        
        for table_id, table_name in discovered_tables:
            if table_name == 'main':
                result = self.run_command("ip -j route show", namespace=namespace, check=False)
            else:
                result = self.run_command(f"ip -j route show table {table_id}", namespace=namespace, check=False)
            
            if result.returncode == 0 and result.stdout.strip():
                try:
                    routes = json.loads(result.stdout)
                    # Translate interface names in routes
                    for route in routes:
                        if 'dev' in route and route['dev'].startswith('v') and re.match(r'^v\d{3}$', route['dev']):
                            original_name = self.get_original_name(route['dev'])
                            route['original_dev'] = original_name
                    routes_data[table_name] = routes
                except json.JSONDecodeError:
                    # Fallback to text parsing
                    routes_data[table_name] = self._parse_text_routes(result.stdout)
            else:
                routes_data[table_name] = {"error": f"Failed to get routes for table {table_id}"}
        
        return {"namespace": namespace, "routes": routes_data}
    
    def _parse_text_routes(self, route_output: str) -> List[Dict[str, Any]]:
        """Parse text route output into structured format."""
        routes = []
        for line in route_output.split('\n'):
            if not line.strip():
                continue
            
            route = {}
            parts = line.split()
            
            # Parse destination
            if parts[0] == 'default':
                route['dst'] = 'default'
                i = 1
            else:
                route['dst'] = parts[0]
                i = 1
            
            # Parse remaining parts
            while i < len(parts):
                if parts[i] == 'via' and i + 1 < len(parts):
                    route['gateway'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'dev' and i + 1 < len(parts):
                    route['dev'] = parts[i + 1]
                    # Add original name if it's a short name
                    if parts[i + 1].startswith('v') and re.match(r'^v\d{3}$', parts[i + 1]):
                        route['original_dev'] = self.get_original_name(parts[i + 1])
                    i += 2
                elif parts[i] == 'proto' and i + 1 < len(parts):
                    route['protocol'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'scope' and i + 1 < len(parts):
                    route['scope'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'src' and i + 1 < len(parts):
                    route['prefsrc'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'metric' and i + 1 < len(parts):
                    route['metric'] = int(parts[i + 1])
                    i += 2
                else:
                    i += 1
            
            routes.append(route)
        
        return routes
    
    def get_rules_data(self, namespace: str) -> Dict[str, Any]:
        """Get policy rules data in structured format."""
        if namespace not in self.available_namespaces:
            return {"error": f"Namespace {namespace} not found"}
        
        result = self.run_command("ip -j rule show", namespace=namespace, check=False)
        if result.returncode == 0:
            try:
                rules = json.loads(result.stdout)
                return {"namespace": namespace, "rules": rules}
            except json.JSONDecodeError:
                # Fallback to text parsing
                pass
        
        # Fallback to text output parsing
        result = self.run_command("ip rule show", namespace=namespace, check=False)
        if result.returncode != 0:
            return {"error": f"Failed to get policy rules for {namespace}"}
        
        rules = []
        for line in result.stdout.split('\n'):
            if not line.strip():
                continue
            
            rule = {}
            # Parse priority
            priority_match = re.match(r'^(\d+):\s+(.+)$', line)
            if priority_match:
                rule['priority'] = int(priority_match.group(1))
                rule_text = priority_match.group(2)
                
                # Parse rule components
                if 'from all' in rule_text:
                    rule['src'] = 'all'
                elif from_match := re.search(r'from (\S+)', rule_text):
                    rule['src'] = from_match.group(1)
                
                if 'to all' in rule_text:
                    rule['dst'] = 'all'
                elif to_match := re.search(r'to (\S+)', rule_text):
                    rule['dst'] = to_match.group(1)
                
                if lookup_match := re.search(r'lookup (\S+)', rule_text):
                    rule['table'] = lookup_match.group(1)
                elif table_match := re.search(r'table (\S+)', rule_text):
                    rule['table'] = table_match.group(1)
                
                if iif_match := re.search(r'iif (\S+)', rule_text):
                    rule['iifname'] = iif_match.group(1)
                
                if oif_match := re.search(r'oif (\S+)', rule_text):
                    rule['oifname'] = oif_match.group(1)
                
                rules.append(rule)
        
        return {"namespace": namespace, "rules": rules}
    
    def get_iptables_data(self, namespace: str) -> Dict[str, Any]:
        """Get iptables data in structured format with full details including counters."""
        if namespace not in self.available_namespaces:
            return {"error": f"Namespace {namespace} not found"}
        
        iptables_data = {}
        
        # Get all tables
        tables = ['filter', 'nat', 'mangle', 'raw']
        
        for table in tables:
            # Use iptables-save with counters (-c) to get packet/byte counts
            result = self.run_command(f"iptables-save -t {table} -c", namespace=namespace, check=False)
            if result.returncode == 0:
                iptables_data[table] = self._parse_iptables_save_with_counters(result.stdout)
            else:
                iptables_data[table] = {"error": f"Failed to get {table} table"}
        
        return {"namespace": namespace, "iptables": iptables_data}
    
    def _parse_iptables_save_with_counters(self, output: str) -> Dict[str, Any]:
        """Parse iptables-save output with counters into structured format."""
        table_data = {
            'chains': {},
            'custom_chains': []
        }
        
        for line in output.split('\n'):
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('*') or line == 'COMMIT':
                continue
            
            # Chain definition with packet/byte counters
            # Format: :CHAIN_NAME POLICY [packets:bytes]
            if line.startswith(':'):
                chain_match = re.match(r':(\S+)\s+(\S+)(?:\s+\[(\d+):(\d+)\])?', line)
                if chain_match:
                    chain_name = chain_match.group(1)
                    chain_policy = chain_match.group(2)
                    packets = int(chain_match.group(3)) if chain_match.group(3) else 0
                    bytes_count = int(chain_match.group(4)) if chain_match.group(4) else 0
                    
                    table_data['chains'][chain_name] = {
                        'policy': chain_policy if chain_policy != '-' else None,
                        'packets': packets,
                        'bytes': bytes_count,
                        'rules': []
                    }
                    
                    # Track custom chains (those without a policy)
                    if chain_policy == '-':
                        table_data['custom_chains'].append(chain_name)
            
            # Rule with counters
            # Format: [packets:bytes] -A CHAIN_NAME rule_spec
            elif line.startswith('[') or line.startswith('-A '):
                rule_data = self._parse_iptables_rule(line)
                if rule_data and rule_data['chain'] in table_data['chains']:
                    table_data['chains'][rule_data['chain']]['rules'].append(rule_data)
        
        return table_data
    
    def _parse_iptables_rule(self, rule_line: str) -> Dict[str, Any]:
        """Parse a single iptables rule with all its parameters."""
        rule_info = {
            'packets': 0,
            'bytes': 0,
            'chain': None,
            'matches': {},
            'target': None,
            'target_options': {},
            'raw': rule_line
        }
        
        # Extract counters if present
        counter_match = re.match(r'^\[(\d+):(\d+)\]\s+(.+)', rule_line)
        if counter_match:
            rule_info['packets'] = int(counter_match.group(1))
            rule_info['bytes'] = int(counter_match.group(2))
            rule_line = counter_match.group(3)
        
        # Parse -A CHAIN_NAME
        if not rule_line.startswith('-A '):
            return None
            
        parts = rule_line.split()
        if len(parts) < 2:
            return None
            
        rule_info['chain'] = parts[1]
        
        i = 2
        while i < len(parts):
            # Source address
            if parts[i] == '-s' and i + 1 < len(parts):
                rule_info['matches']['source'] = parts[i + 1]
                i += 2
            # Destination address
            elif parts[i] == '-d' and i + 1 < len(parts):
                rule_info['matches']['destination'] = parts[i + 1]
                i += 2
            # Input interface
            elif parts[i] in ['-i', '--in-interface'] and i + 1 < len(parts):
                rule_info['matches']['in_interface'] = parts[i + 1]
                i += 2
            # Output interface
            elif parts[i] in ['-o', '--out-interface'] and i + 1 < len(parts):
                rule_info['matches']['out_interface'] = parts[i + 1]
                i += 2
            # Protocol
            elif parts[i] in ['-p', '--protocol'] and i + 1 < len(parts):
                rule_info['matches']['protocol'] = parts[i + 1]
                i += 2
            # Source port
            elif parts[i] == '--sport' and i + 1 < len(parts):
                rule_info['matches']['source_port'] = parts[i + 1]
                i += 2
            # Destination port
            elif parts[i] == '--dport' and i + 1 < len(parts):
                rule_info['matches']['destination_port'] = parts[i + 1]
                i += 2
            # Match extension
            elif parts[i] == '-m' and i + 1 < len(parts):
                match_name = parts[i + 1]
                if 'match_extensions' not in rule_info['matches']:
                    rule_info['matches']['match_extensions'] = []
                rule_info['matches']['match_extensions'].append(match_name)
                i += 2
            # State match
            elif parts[i] == '--state' and i + 1 < len(parts):
                rule_info['matches']['state'] = parts[i + 1].split(',')
                i += 2
            # Connection tracking state
            elif parts[i] == '--ctstate' and i + 1 < len(parts):
                rule_info['matches']['ctstate'] = parts[i + 1].split(',')
                i += 2
            # Set match
            elif parts[i] == '--match-set' and i + 2 < len(parts):
                if 'match_sets' not in rule_info['matches']:
                    rule_info['matches']['match_sets'] = []
                rule_info['matches']['match_sets'].append({
                    'name': parts[i + 1],
                    'direction': parts[i + 2]
                })
                i += 3
            # Comment
            elif parts[i] == '--comment' and i + 1 < len(parts):
                # Handle quoted comments
                if parts[i + 1].startswith('"'):
                    comment_parts = []
                    j = i + 1
                    while j < len(parts):
                        comment_parts.append(parts[j])
                        if parts[j].endswith('"'):
                            break
                        j += 1
                    rule_info['matches']['comment'] = ' '.join(comment_parts).strip('"')
                    i = j + 1
                else:
                    rule_info['matches']['comment'] = parts[i + 1]
                    i += 2
            # Jump target
            elif parts[i] in ['-j', '--jump'] and i + 1 < len(parts):
                rule_info['target'] = parts[i + 1]
                i += 2
                # Parse target options
                if rule_info['target'] == 'REJECT' and i < len(parts) and parts[i] == '--reject-with':
                    rule_info['target_options']['reject_with'] = parts[i + 1]
                    i += 2
                elif rule_info['target'] == 'LOG' and i < len(parts):
                    if parts[i] == '--log-prefix' and i + 1 < len(parts):
                        rule_info['target_options']['log_prefix'] = parts[i + 1]
                        i += 2
                    elif parts[i] == '--log-level' and i + 1 < len(parts):
                        rule_info['target_options']['log_level'] = parts[i + 1]
                        i += 2
                elif rule_info['target'] in ['SNAT', 'DNAT', 'MASQUERADE']:
                    if i < len(parts) and parts[i] == '--to-source' and i + 1 < len(parts):
                        rule_info['target_options']['to_source'] = parts[i + 1]
                        i += 2
                    elif i < len(parts) and parts[i] == '--to-destination' and i + 1 < len(parts):
                        rule_info['target_options']['to_destination'] = parts[i + 1]
                        i += 2
            # TCP flags
            elif parts[i] == '--tcp-flags' and i + 2 < len(parts):
                rule_info['matches']['tcp_flags'] = {
                    'mask': parts[i + 1].split(','),
                    'set': parts[i + 2].split(',')
                }
                i += 3
            # ICMP type
            elif parts[i] == '--icmp-type' and i + 1 < len(parts):
                rule_info['matches']['icmp_type'] = parts[i + 1]
                i += 2
            # Limit
            elif parts[i] == '--limit' and i + 1 < len(parts):
                rule_info['matches']['limit'] = parts[i + 1]
                i += 2
            # Limit burst
            elif parts[i] == '--limit-burst' and i + 1 < len(parts):
                rule_info['matches']['limit_burst'] = parts[i + 1]
                i += 2
            # Mark
            elif parts[i] == '--mark' and i + 1 < len(parts):
                rule_info['matches']['mark'] = parts[i + 1]
                i += 2
            # Set mark
            elif parts[i] == '--set-mark' and i + 1 < len(parts):
                rule_info['target_options']['set_mark'] = parts[i + 1]
                i += 2
            # Negation
            elif parts[i] == '!':
                # Handle negation for next parameter
                if i + 2 < len(parts):
                    next_param = parts[i + 1]
                    if next_param in ['-s', '-d', '-i', '-o', '-p']:
                        # Add negation flag to the match
                        negated_key = {
                            '-s': 'source_negated',
                            '-d': 'destination_negated',
                            '-i': 'in_interface_negated',
                            '-o': 'out_interface_negated',
                            '-p': 'protocol_negated'
                        }.get(next_param)
                        if negated_key:
                            rule_info['matches'][negated_key] = True
                i += 1
            else:
                # Unknown parameter, skip
                i += 1
        
        return rule_info
    
    def get_ipsets_data(self, namespace: str) -> Dict[str, Any]:
        """Get ipsets data in structured format."""
        # Check if this is a host namespace (hosts don't typically have ipsets)
        if namespace in self.hosts:
            return {"namespace": namespace, "ipsets": {}, "note": "Hosts don't typically have ipsets"}
        
        if namespace not in self.available_namespaces:
            return {"error": f"Namespace {namespace} not found"}
        
        result = self.run_command("ipset list -n", namespace=namespace, check=False)
        if result.returncode != 0:
            return {"namespace": namespace, "ipsets": {}}
        
        ipset_names = [name.strip() for name in result.stdout.split('\n') if name.strip()]
        ipsets = {}
        
        for ipset_name in ipset_names:
            result = self.run_command(f"ipset list {ipset_name}", namespace=namespace, check=False)
            if result.returncode == 0:
                ipsets[ipset_name] = self._parse_ipset_list(result.stdout)
        
        return {"namespace": namespace, "ipsets": ipsets}
    
    def _parse_ipset_list(self, output: str) -> Dict[str, Any]:
        """Parse ipset list output into structured format."""
        ipset_info = {
            'type': None,
            'header': {},
            'members': []
        }
        
        in_members = False
        
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            if line == 'Members:':
                in_members = True
                continue
            
            if not in_members:
                # Parse header information
                if line.startswith('Name:'):
                    continue  # Skip name, we already have it
                elif line.startswith('Type:'):
                    ipset_info['type'] = line.split(':', 1)[1].strip()
                elif ':' in line:
                    key, value = line.split(':', 1)
                    ipset_info['header'][key.strip()] = value.strip()
            else:
                # Parse members
                ipset_info['members'].append(line)
        
        return ipset_info
    
    def get_all_data(self, namespace: str) -> Dict[str, Any]:
        """Get all configuration data in structured format."""
        if namespace not in self.available_namespaces:
            return {"error": f"Namespace {namespace} not found"}
        
        entity_type = "host" if self.is_host(namespace) else "router"
        
        all_data = {
            "namespace": namespace,
            "type": entity_type,
            "interfaces": self.get_interfaces_data(namespace).get("interfaces", {}),
            "routes": self.get_routes_data(namespace).get("routes", {}),
            "rules": self.get_rules_data(namespace).get("rules", []),
            "iptables": self.get_iptables_data(namespace).get("iptables", {}),
            "ipsets": self.get_ipsets_data(namespace).get("ipsets", {})
        }
        
        return all_data
    
    def show_interfaces(self, namespace: str) -> str:
        """Show interface configuration with original names."""
        if namespace not in self.available_namespaces:
            # For non-existent namespaces, we can't determine the type, so use generic term
            if namespace in self.hosts:
                return f"Host {namespace} namespace not found"
            elif namespace in self.known_routers:
                return f"Router {namespace} namespace not found"
            else:
                return f"Namespace {namespace} not found"
            
        result = self.run_command("ip addr show", namespace=namespace, check=False)
        if result.returncode != 0:
            return f"Failed to get interface information for {namespace}"
            
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
        
    def show_routes(self, namespace: str) -> str:
        """Show all routing tables dynamically discovered from policy rules."""
        if namespace not in self.available_namespaces:
            # For non-existent namespaces, we can't determine the type, so use generic term
            if namespace in self.hosts:
                return f"Host {namespace} namespace not found"
            elif namespace in self.known_routers:
                return f"Router {namespace} namespace not found"
            else:
                return f"Namespace {namespace} not found"
        
        # Dynamically discover active routing tables from policy rules
        discovered_tables = self._discover_routing_tables(namespace)
        
        sections = []
        
        for table_id, table_name in discovered_tables:
            if table_name == 'main':
                sections.append("Main routing table:")
                result = self.run_command("ip route show", namespace=namespace, check=False)
            else:
                sections.append(f"Table {table_id} ({table_name}):")
                result = self.run_command(f"ip route show table {table_id}", namespace=namespace, check=False)
            
            if result.returncode == 0 and result.stdout.strip():
                sections.append(self._translate_interface_names(result.stdout))
            else:
                sections.append(f"Failed to get table {table_id}")
            
            sections.append("")  # Add blank line between tables
        
        return '\n'.join(sections).rstrip()
    
    def _discover_routing_tables(self, namespace: str):
        """Dynamically discover active routing tables from ip rule show output."""
        discovered_tables = []
        seen_tables = set()
        
        # Get policy rules to discover active tables
        result = self.run_command("ip rule show", namespace=namespace, check=False)
        if result.returncode != 0:
            # Fallback to main table only
            return [('main', 'main')]
        
        import re
        
        for line in result.stdout.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Look for table references in policy rules
            # Examples: "lookup main", "table 100", "lookup local"
            table_match = re.search(r'(?:lookup|table)\s+(\w+)', line)
            if table_match:
                table_ref = table_match.group(1)
                
                # Skip system tables we don't want to show
                if table_ref in ['local', 'default']:
                    continue
                
                # Determine table ID and name
                if table_ref == 'main':
                    table_id = 'main'
                    table_name = 'main'
                elif table_ref.isdigit():
                    table_id = table_ref
                    table_name = f"table_{table_ref}"
                else:
                    # Named table, try to resolve to number or use name
                    table_id = table_ref
                    table_name = table_ref
                
                if table_id not in seen_tables:
                    discovered_tables.append((table_id, table_name))
                    seen_tables.add(table_id)
        
        # Ensure main table is included if not found in rules
        if 'main' not in seen_tables:
            discovered_tables.insert(0, ('main', 'main'))
        
        return discovered_tables
    
    def _translate_interface_names(self, route_output: str) -> str:
        """Helper method to translate interface names in routing output."""
        output_lines = []
        
        for line in route_output.split('\n'):
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
        
    def show_rules(self, namespace: str) -> str:
        """Show policy routing rules."""
        if namespace not in self.available_namespaces:
            # For non-existent namespaces, we can't determine the type, so use generic term
            if namespace in self.hosts:
                return f"Host {namespace} namespace not found"
            elif namespace in self.known_routers:
                return f"Router {namespace} namespace not found"
            else:
                return f"Namespace {namespace} not found"
            
        result = self.run_command("ip rule show", namespace=namespace, check=False)
        if result.returncode != 0:
            return f"Failed to get policy rules for {namespace}"
            
        return result.stdout
        
    def get_summary_data(self, namespace: str) -> Dict[str, Any]:
        """Get summary data for a namespace in structured format, matching text summary exactly."""
        if namespace not in self.available_namespaces:
            return {
                "namespace": namespace,
                "status": "not_found",
                "error": f"Namespace {namespace} not found"
            }
            
        entity_type = "host" if self.is_host(namespace) else "router"
        summary_data = {
            "namespace": namespace,
            "type": entity_type,
            "status": "running"
        }
        
        # Add host-specific information if this is a host
        if self.is_host(namespace):
            host_config = self.hosts[namespace]
            summary_data.update({
                "primary_ip": host_config.get('primary_ip', 'unknown'),
                "connected_to": host_config.get('connected_to', 'unknown'),
                "gateway_ip": host_config.get('gateway_ip', 'unknown'),
                "secondary_ips": host_config.get('secondary_ips', []),
                "created_at": host_config.get('created_at', 'unknown')
            })
        
        # Count interfaces (same as text version)
        addr_result = self.run_command("ip -j addr show", namespace=namespace, check=False)
        if addr_result.returncode == 0:
            try:
                interfaces = json.loads(addr_result.stdout)
                # Count only non-loopback interfaces
                iface_count = len([iface for iface in interfaces if iface.get('ifname') != 'lo'])
                summary_data["interface_count"] = iface_count
            except json.JSONDecodeError:
                # Fallback to counting lines method
                addr_result = self.run_command("ip addr show", namespace=namespace, check=False)
                if addr_result.returncode == 0:
                    # Count lines that start with a number (interface definitions)
                    iface_count = len([line for line in addr_result.stdout.split('\n') 
                                     if re.match(r'^\d+:', line) and 'lo:' not in line])
                    summary_data["interface_count"] = iface_count
                else:
                    summary_data["interface_count"] = "failed to retrieve"
        else:
            summary_data["interface_count"] = "failed to retrieve"
        
        # Count policy rules (same as text version)
        rules_result = self.run_command("ip rule show", namespace=namespace, check=False)
        if rules_result.returncode == 0:
            rule_count = len([line for line in rules_result.stdout.split('\n') if line.strip()])
            summary_data["policy_rules"] = rule_count
        else:
            summary_data["policy_rules"] = "failed to retrieve"
            
        # Count routes per routing table (same as text version)
        routing_tables = {}
        discovered_tables = self._discover_routing_tables(namespace)
        
        for table_id, table_name in discovered_tables:
            if table_name == 'main':
                result = self.run_command("ip route show", namespace=namespace, check=False)
            else:
                result = self.run_command(f"ip route show table {table_id}", namespace=namespace, check=False)
            
            if result.returncode == 0 and result.stdout.strip():
                route_count = len([line for line in result.stdout.split('\n') if line.strip()])
                if table_name == 'main':
                    routing_tables["main"] = route_count
                else:
                    routing_tables[f"{table_name} (id {table_id})"] = route_count
            else:
                if table_name == 'main':
                    routing_tables["main"] = "failed to retrieve"
                else:
                    routing_tables[f"{table_name} (id {table_id})"] = "failed to retrieve"
        
        summary_data["routing_tables"] = routing_tables
        
        # Get iptables totals using iptables-save (same as text version)
        iptables_result = self.run_command("iptables-save", namespace=namespace, check=False)
        if iptables_result.returncode == 0:
            table_counts = {}
            current_table = None
            total_rules = 0
            
            for line in iptables_result.stdout.split('\n'):
                # Start of table
                table_match = re.match(r'^\*(\w+)', line)
                if table_match:
                    current_table = table_match.group(1)
                    table_counts[current_table] = 0
                # Actual rule (starts with -A)
                elif line.startswith('-A ') and current_table:
                    table_counts[current_table] += 1
                    total_rules += 1
            
            summary_data["iptables"] = {
                "total_rules": total_rules,
                "table_counts": {table: count for table, count in table_counts.items() if count > 0}
            }
        else:
            summary_data["iptables"] = "failed to retrieve"
        
        # Get ipsets count (same as text version)
        ipset_result = self.run_command("ipset list -n", namespace=namespace, check=False)
        if ipset_result.returncode == 0:
            ipset_count = len([line for line in ipset_result.stdout.split('\n') if line.strip()])
            summary_data["ipsets"] = ipset_count
        else:
            summary_data["ipsets"] = "failed to retrieve"
            
        return summary_data
        
    def show_summary(self, namespace: str) -> str:
        """Show brief summary of namespace configuration with counts only."""
        if namespace not in self.available_namespaces:
            # For non-existent namespaces, we can't determine the type, so use generic term
            if namespace in self.hosts:
                return f"Host {namespace} namespace not found"
            elif namespace in self.known_routers:
                return f"Router {namespace} namespace not found"
            else:
                return f"Namespace {namespace} not found"
            
        entity_type = "HOST" if self.is_host(namespace) else "ROUTER"
        summary_lines = [f"=== {namespace} {entity_type} SUMMARY ==="]
        
        # Add host-specific information if this is a host
        if self.is_host(namespace):
            host_config = self.hosts[namespace]
            primary_ip = host_config.get('primary_ip', 'unknown')
            connected_to = host_config.get('connected_to', 'unknown')
            gateway_ip = host_config.get('gateway_ip', 'unknown')
            secondary_ips = host_config.get('secondary_ips', [])
            
            summary_lines.append(f"  Type: Host")
            summary_lines.append(f"  Primary IP: {primary_ip}")
            summary_lines.append(f"  Connected to: {connected_to} (gateway: {gateway_ip})")
            if secondary_ips:
                summary_lines.append(f"  Secondary IPs: {', '.join(secondary_ips)}")
            summary_lines.append(f"  Created: {host_config.get('created_at', 'unknown')}")
        else:
            summary_lines.append(f"  Type: Router")
        
        # Count interfaces
        summary_lines.append("")
        addr_result = self.run_command("ip -j addr show", namespace=namespace, check=False)
        if addr_result.returncode == 0:
            try:
                interfaces = json.loads(addr_result.stdout)
                # Count only non-loopback interfaces
                iface_count = len([iface for iface in interfaces if iface.get('ifname') != 'lo'])
                summary_lines.append(f"  Interfaces: {iface_count}")
            except json.JSONDecodeError:
                # Fallback to counting lines method
                addr_result = self.run_command("ip addr show", namespace=namespace, check=False)
                if addr_result.returncode == 0:
                    # Count lines that start with a number (interface definitions)
                    iface_count = len([line for line in addr_result.stdout.split('\n') 
                                     if re.match(r'^\d+:', line) and 'lo:' not in line])
                    summary_lines.append(f"  Interfaces: {iface_count}")
                else:
                    summary_lines.append("  Interfaces: (failed to retrieve)")
        else:
            summary_lines.append("  Interfaces: (failed to retrieve)")
        
        # Count policy rules
        rules_result = self.run_command("ip rule show", namespace=namespace, check=False)
        if rules_result.returncode == 0:
            rule_count = len([line for line in rules_result.stdout.split('\n') if line.strip()])
            summary_lines.append(f"  Policy rules: {rule_count}")
        else:
            summary_lines.append("  Policy rules: (failed to retrieve)")
            
        # Count routes per routing table
        summary_lines.append("  Routing tables:")
        
        # Discover all routing tables dynamically
        discovered_tables = self._discover_routing_tables(namespace)
        
        for table_id, table_name in discovered_tables:
            if table_name == 'main':
                result = self.run_command("ip route show", namespace=namespace, check=False)
            else:
                result = self.run_command(f"ip route show table {table_id}", namespace=namespace, check=False)
            
            if result.returncode == 0 and result.stdout.strip():
                route_count = len([line for line in result.stdout.split('\n') if line.strip()])
                if table_name == 'main':
                    summary_lines.append(f"    main: {route_count} routes")
                else:
                    summary_lines.append(f"    {table_name} (id {table_id}): {route_count} routes")
            else:
                if table_name == 'main':
                    summary_lines.append(f"    main: (failed to retrieve)")
                else:
                    summary_lines.append(f"    {table_name} (id {table_id}): (failed to retrieve)")
            
        # Get iptables totals using iptables-save
        summary_lines.append("")
        iptables_result = self.run_command("iptables-save", namespace=namespace, check=False)
        if iptables_result.returncode == 0:
            table_counts = {}
            current_table = None
            total_rules = 0
            
            for line in iptables_result.stdout.split('\n'):
                # Start of table
                table_match = re.match(r'^\*(\w+)', line)
                if table_match:
                    current_table = table_match.group(1)
                    table_counts[current_table] = 0
                # Actual rule (starts with -A)
                elif line.startswith('-A ') and current_table:
                    table_counts[current_table] += 1
                    total_rules += 1
            
            if total_rules > 0:
                table_summary = ', '.join([f"{table}:{count}" for table, count in table_counts.items() if count > 0])
                summary_lines.append(f"  Iptables: {total_rules} rules ({table_summary})")
            else:
                summary_lines.append("  Iptables: 0 rules")
        else:
            summary_lines.append("  Iptables: (failed to retrieve)")
        
        # Get ipsets count
        ipset_result = self.run_command("ipset list -n", namespace=namespace, check=False)
        if ipset_result.returncode == 0:
            ipset_count = len([line for line in ipset_result.stdout.split('\n') if line.strip()])
            summary_lines.append(f"  Ipsets: {ipset_count} sets")
            
        return '\n'.join(summary_lines)
        
    def show_iptables(self, namespace: str) -> str:
        """Show iptables configuration."""
        if namespace not in self.available_namespaces:
            if namespace in self.hosts:
                return f"Host {namespace} namespace not found"
            elif namespace in self.known_routers:
                return f"Router {namespace} namespace not found"
            else:
                return f"Namespace {namespace} not found"
        
        result = self.run_command("iptables -L -n -v", namespace=namespace, check=False)
        if result.returncode != 0:
            return f"Failed to get iptables information for {namespace}"
        
        return result.stdout
    
    def show_iptables_nat(self, namespace: str) -> str:
        """Show iptables NAT table."""
        if namespace not in self.available_namespaces:
            if namespace in self.hosts:
                return f"Host {namespace} namespace not found"
            elif namespace in self.known_routers:
                return f"Router {namespace} namespace not found"
            else:
                return f"Namespace {namespace} not found"
        
        result = self.run_command("iptables -t nat -L -n -v", namespace=namespace, check=False)
        if result.returncode != 0:
            return f"Failed to get iptables NAT information for {namespace}"
        
        return result.stdout
    
    def show_iptables_mangle(self, namespace: str) -> str:
        """Show iptables mangle table."""
        if namespace not in self.available_namespaces:
            if namespace in self.hosts:
                return f"Host {namespace} namespace not found"
            elif namespace in self.known_routers:
                return f"Router {namespace} namespace not found"
            else:
                return f"Namespace {namespace} not found"
        
        result = self.run_command("iptables -t mangle -L -n -v", namespace=namespace, check=False)
        if result.returncode != 0:
            return f"Failed to get iptables mangle information for {namespace}"
        
        return result.stdout
    
    def show_ipsets(self, namespace: str) -> str:
        """Show ipset configuration for routers only."""
        # Check if this is a host namespace (hosts don't typically have ipsets)
        if namespace in self.hosts:
            return f"Ipsets are not applicable for host {namespace} (hosts don't have ipsets)"
        
        if namespace not in self.available_namespaces:
            return f"Router {namespace} namespace not found"
        
        result = self.run_command("ipset list", namespace=namespace, check=False)
        if result.returncode != 0:
            return f"No ipsets configured in {namespace} or ipset command failed"
        
        return result.stdout
    
    def show_routing_tables(self, namespace: str) -> str:
        """Show all routing tables dynamically discovered from policy rules."""
        # Use the same dynamic discovery logic as show_routes but without interface name translation
        if namespace not in self.available_namespaces:
            if namespace in self.hosts:
                return f"Host {namespace} namespace not found"
            elif namespace in self.known_routers:
                return f"Router {namespace} namespace not found"
            else:
                return f"Namespace {namespace} not found"
        
        # Dynamically discover active routing tables from policy rules
        discovered_tables = self._discover_routing_tables(namespace)
        
        sections = []
        
        for table_id, table_name in discovered_tables:
            if table_name == 'main':
                sections.append("Main routing table:")
                result = self.run_command("ip route show", namespace=namespace, check=False)
            else:
                sections.append(f"Table {table_id} ({table_name}):")
                result = self.run_command(f"ip route show table {table_id}", namespace=namespace, check=False)
            
            if result.returncode == 0 and result.stdout.strip():
                sections.append(result.stdout)
            else:
                sections.append(f"Failed to get table {table_id}")
            
            sections.append("")  # Add blank line between tables
        
        return '\n'.join(sections).rstrip()

    def show_all_configuration(self, namespace: str) -> str:
        """Show complete configuration for namespace."""
        if namespace not in self.available_namespaces:
            # For non-existent namespaces, we can't determine the type, so use generic term
            if namespace in self.hosts:
                return f"Host {namespace} namespace not found"
            elif namespace in self.known_routers:
                return f"Router {namespace} namespace not found"
            else:
                return f"Namespace {namespace} not found"
            
        entity_type = "HOST" if self.is_host(namespace) else "ROUTER"
        sections = []
        
        # Interfaces
        sections.append(f"=== {namespace} {entity_type} INTERFACES ===")
        sections.append(self.show_interfaces(namespace))
        
        # All Routes (including additional tables)
        sections.append(f"\n=== {namespace} {entity_type} ROUTING TABLES ===")
        sections.append(self.show_routing_tables(namespace))
        
        # Policy Rules
        sections.append(f"\n=== {namespace} {entity_type} POLICY RULES ===")
        sections.append(self.show_rules(namespace))
        
        # Iptables Filter table
        sections.append(f"\n=== {namespace} {entity_type} IPTABLES FILTER ===")
        sections.append(self.show_iptables(namespace))
        
        # Iptables NAT table
        sections.append(f"\n=== {namespace} {entity_type} IPTABLES NAT ===")
        sections.append(self.show_iptables_nat(namespace))
        
        # Iptables Mangle table
        sections.append(f"\n=== {namespace} {entity_type} IPTABLES MANGLE ===")
        sections.append(self.show_iptables_mangle(namespace))
        
        # Ipsets
        sections.append(f"\n=== {namespace} {entity_type} IPSETS ===")
        sections.append(self.show_ipsets(namespace))
        
        return '\n'.join(sections)
    
    def rebuild_name_mapping_for_running_namespaces(self):
        """Build interface name mapping ONLY for actually running namespaces."""
        self.logger.debug("Building interface name mapping for running namespaces only")
        
        # Only process namespaces that are actually running
        user_namespaces = [ns for ns in self.available_namespaces if not self._is_system_namespace(ns)]
        
        # For each running namespace, build name mapping only if it's a known router with facts
        for namespace in user_namespaces:
            if namespace in self.known_routers:
                # Load facts only for this specific running router
                facts_file = self.facts_dir / f"{namespace}.json"
                if facts_file.exists():
                    try:
                        with open(facts_file, 'r') as f:
                            facts = json.load(f)
                        
                        # Process routing table to extract interface mappings for this router only
                        routing_data = facts.get('routing', {})
                        routing_tables = routing_data.get('tables', [])
                        
                        for route_info in routing_tables:
                            prefsrc = route_info.get('prefsrc')
                            dev = route_info.get('dev')
                            protocol = route_info.get('protocol')
                            scope = route_info.get('scope')
                            dst = route_info.get('dst')
                            
                            # Only process kernel routes with preferred source (interface IPs)
                            if (protocol == 'kernel' and scope == 'link' and 
                                prefsrc and dev and dst and '/' in dst):
                                
                                # Create mapping for this interface
                                if dev:
                                    veth_name = f"{namespace}-{dev}"
                                    self._get_short_name(veth_name)
                    
                    except (json.JSONDecodeError, IOError) as e:
                        self.logger.warning(f"Failed to load facts for running namespace {namespace}: {e}")
        
        self.logger.debug(f"Built interface name mapping for {len(self.name_map)} interfaces in running namespaces")
        
        
    def show_all_summary(self) -> str:
        """Show summary for all available namespaces."""
        if not self.available_namespaces:
            return "No live namespaces found"
            
        # Show ALL namespaces except truly system ones (default, etc.)
        user_namespaces = [ns for ns in self.available_namespaces if not self._is_system_namespace(ns)]
        total_user_namespaces = len(user_namespaces)
        
        sections = ["=== LIVE NAMESPACE STATUS ==="]
        sections.append(f"Running namespaces: {total_user_namespaces}")
        sections.append(f"Interface name mappings: {len(self.name_map)}")
        sections.append("")
        
        if total_user_namespaces > 0:
            sections.append("Running namespaces:")
            
            # Show ALL user namespaces
            for namespace in sorted(user_namespaces):
                namespace_type = self._get_namespace_type(namespace)
                sections.append(f"  {namespace} [{namespace_type}]")
            sections.append("")
            
            # Show detailed summary for each namespace
            for namespace in sorted(user_namespaces):
                sections.append(self.show_summary(namespace))
                sections.append("")
        else:
            sections.append("No namespaces are currently running.")
            sections.append("Use 'sudo make netsetup' to create router namespaces.")
            sections.append("Use 'sudo make hostadd' to create host namespaces.")
            
        return '\n'.join(sections)


def main():
    """Main entry point for network status tool."""
    parser = argparse.ArgumentParser(
        description="Show LIVE network namespace status with original interface names",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s summary                          # Overview of all live namespaces (default)
  %(prog)s interfaces --limit hq-gw         # Live interface config for specific router
  %(prog)s routes --limit br-core           # Live routing table for specific router
  %(prog)s summary --limit "hq-*"           # Live summary for routers matching pattern
  %(prog)s interfaces --limit web1          # Live interface config for host
  %(prog)s rules --limit "*-core"           # Live policy rules for core routers
  %(prog)s iptables --limit hq-gw           # Live iptables configuration for router
  %(prog)s ipsets --limit hq-core           # Live ipset configuration for router
  %(prog)s all --limit dc-srv               # Complete live config for router
  %(prog)s interfaces --limit hq-gw -v      # Live interface config with basic verbosity
  %(prog)s summary -vv                      # Live overview with info messages
  %(prog)s routes --limit "*" -vvv          # Live routing table for all with debug output
  
Functions:
  interfaces  - Live IP configuration (ip addr show equivalent)
  routes      - Live routing table (ip route show equivalent)
  rules       - Live policy rules (ip rule show equivalent)
  iptables    - Live iptables configuration (iptables -L equivalent)
  ipsets      - Live ipset configuration (ipset list equivalent)  
  summary     - Brief live overview (default if no function specified)
  all         - Complete live configuration
  
Limit Options:
  --limit <pattern>  - Limit to specific namespaces (supports glob patterns)
                       If not specified, shows all namespaces
                       Examples: "hq-gw", "br-*", "*-core", "web1"
  
Verbosity Levels:
  (none)  - Silent mode: minimal output
  -v      - Basic mode: show errors and basic info
  -vv     - Info mode: basic + INFO level messages  
  -vvv    - Debug mode: info + DEBUG level messages
  
Environment Variables:
  TRACEROUTE_SIMULATOR_FACTS - Facts directory path (for interface name mapping only)
        """
    )
    
    parser.add_argument(
        'function',
        type=str,
        nargs='?',
        default='summary',
        choices=['interfaces', 'routes', 'rules', 'iptables', 'ipsets', 'summary', 'all'],
        help='Live information to display (default: summary)'
    )
    
    parser.add_argument(
        '--limit',
        type=str,
        help='Limit to specific namespaces (supports glob patterns like "hq-*", "*-core")'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='count',
        default=0,
        help='Increase verbosity: -v (basic), -vv (info), -vvv (debug)'
    )
    
    parser.add_argument(
        '-j', '--json',
        action='store_true',
        help='Output in JSON format'
    )

    # Accept but ignore cache-related flags for backward compatibility
    parser.add_argument('--no-cache', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--invalidate-cache', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--cache-stats', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--timeout', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--table', '-t', action='store_true', help=argparse.SUPPRESS)

    args = parser.parse_args()
    
    # Get facts directory from environment (required)
    facts_dir = os.environ.get('TRACEROUTE_SIMULATOR_FACTS')
    if not facts_dir:
        if args.json:
            print(json.dumps({"error": "TRACEROUTE_SIMULATOR_FACTS environment variable must be set"}), file=sys.stdout)
        else:
            print("Error: TRACEROUTE_SIMULATOR_FACTS environment variable must be set", file=sys.stderr)
            print("Example: TRACEROUTE_SIMULATOR_FACTS=/path/to/facts", file=sys.stderr)
        sys.exit(1)
    
    # Check if user is in tsim-users group (unless running as root)
    if os.geteuid() != 0:
        import grp
        import pwd
        try:
            username = pwd.getpwuid(os.getuid()).pw_name
            tsim_group = grp.getgrnam('tsim-users')
            if username not in tsim_group.gr_mem:
                if not args.json and args.verbose >= 1:
                    print("Warning: User not in tsim-users group. Namespace operations may fail.", file=sys.stderr)
                    print("Run: sudo usermod -a -G tsim-users $USER", file=sys.stderr)
        except (KeyError, OSError):
            if not args.json and args.verbose >= 1:
                print("Warning: tsim-users group not found. Namespace operations may fail.", file=sys.stderr)
                print("Run: sudo groupadd -f tsim-users", file=sys.stderr)
        
    try:
        status_tool = NetworkNamespaceStatus(facts_dir, args.verbose)
        
        # Get target namespaces based on --limit parameter
        active_routers = [ns for ns in status_tool.known_routers if ns in status_tool.available_namespaces]
        active_hosts = [ns for ns in status_tool.hosts.keys() if ns in status_tool.available_namespaces]
        all_active_entities = active_routers + active_hosts
        
        if args.limit:
            # Apply glob pattern matching
            import fnmatch
            target_namespaces = []
            for ns in all_active_entities:
                if fnmatch.fnmatch(ns, args.limit):
                    target_namespaces.append(ns)
            if not target_namespaces:
                if args.json:
                    print(json.dumps({"error": f"No namespaces found matching pattern: {args.limit}"}), file=sys.stdout)
                else:
                    print(f"No namespaces found matching pattern: {args.limit}", file=sys.stderr)
                sys.exit(0)
        else:
            # No limit specified - show all
            target_namespaces = all_active_entities
        
        # Sort namespaces for consistent output
        target_namespaces = sorted(target_namespaces)
        
        if args.json:
            # JSON output mode
            data = {}
            for namespace in target_namespaces:
                if args.function == 'interfaces':
                    data[namespace] = status_tool.get_interfaces_data(namespace)
                elif args.function == 'summary':
                    data[namespace] = status_tool.get_summary_data(namespace)
                elif args.function == 'routes':
                    data[namespace] = status_tool.get_routes_data(namespace)
                elif args.function == 'rules':
                    data[namespace] = status_tool.get_rules_data(namespace)
                elif args.function == 'iptables':
                    data[namespace] = status_tool.get_iptables_data(namespace)
                elif args.function == 'ipsets':
                    data[namespace] = status_tool.get_ipsets_data(namespace)
                elif args.function == 'all':
                    data[namespace] = status_tool.get_all_data(namespace)
            output = json.dumps(data, indent=2)
        else:
            # Text output mode
            if args.function == 'summary' and not args.limit:
                # Special case: summary with no limit shows the all summary view
                output = status_tool.show_all_summary()
            elif len(target_namespaces) == 1:
                # Single namespace - show without headers
                namespace = target_namespaces[0]
                if args.function == 'interfaces':
                    output = status_tool.show_interfaces(namespace)
                elif args.function == 'routes':
                    output = status_tool.show_routes(namespace)
                elif args.function == 'rules':
                    output = status_tool.show_rules(namespace)
                elif args.function == 'iptables':
                    output = status_tool.show_iptables(namespace)
                elif args.function == 'ipsets':
                    output = status_tool.show_ipsets(namespace)
                elif args.function == 'summary':
                    output = status_tool.show_summary(namespace)
                elif args.function == 'all':
                    output = status_tool.show_all_configuration(namespace)
                else:
                    if args.json:
                        output = json.dumps({"error": f"Unknown function: {args.function}"})
                    else:
                        print(f"Unknown function: {args.function}", file=sys.stderr)
                        sys.exit(1)
            else:
                # Multiple namespaces - show with headers
                output_sections = []
                
                # For ipsets, only show routers (not hosts)
                if args.function == 'ipsets':
                    target_namespaces = [ns for ns in target_namespaces if ns in active_routers]
                
                for namespace in target_namespaces:
                    entity_type = "HOST" if status_tool.is_host(namespace) else "ROUTER"
                    if args.function == 'interfaces':
                        output_sections.append(f"=== {namespace} {entity_type} LIVE INTERFACES ===")
                        output_sections.append(status_tool.show_interfaces(namespace))
                    elif args.function == 'routes':
                        output_sections.append(f"=== {namespace} {entity_type} LIVE ROUTES ===")
                        output_sections.append(status_tool.show_routes(namespace))
                    elif args.function == 'rules':
                        output_sections.append(f"=== {namespace} {entity_type} LIVE RULES ===")
                        output_sections.append(status_tool.show_rules(namespace))
                    elif args.function == 'iptables':
                        output_sections.append(f"=== {namespace} {entity_type} LIVE IPTABLES ===")
                        output_sections.append(status_tool.show_iptables(namespace))
                    elif args.function == 'ipsets':
                        output_sections.append(f"=== {namespace} {entity_type} LIVE IPSETS ===")
                        output_sections.append(status_tool.show_ipsets(namespace))
                    elif args.function == 'summary':
                        output_sections.append(status_tool.show_summary(namespace))
                    elif args.function == 'all':
                        output_sections.append(status_tool.show_all_configuration(namespace))
                    output_sections.append("")
                output = '\n'.join(output_sections)
                
        print(output)
        
    except Exception as e:
        if args.json:
            print(json.dumps({"error": f"Status check failed: {str(e)}"}), file=sys.stdout)
        else:
            print(f"Status check failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()