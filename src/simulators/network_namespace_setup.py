#!/usr/bin/env python3
"""
Network Namespace Setup - Hidden Mesh Infrastructure

Creates network namespaces with exact interfaces from raw facts.
Uses HIDDEN mesh infrastructure to simulate switches/network fabric.

Key Architecture:
- Routers see ONLY their actual interfaces from raw facts (eth0, eth1, wg0, etc.)
- Hidden mesh layer simulates switches/network fabric between routers
- Host sees ONLY its own namespace, not the hidden infrastructure
- Complete configuration applied from raw facts using system tools

Usage:
    sudo python3 network_namespace_setup.py [--verbose]
    
Environment Variables:
    TRACEROUTE_SIMULATOR_RAW_FACTS - Directory containing raw facts files (required)
"""

import argparse
import logging
import os
import subprocess
import sys
import re
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple

# Import the raw facts block loader
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.raw_facts_block_loader import RawFactsBlockLoader, RouterRawFacts


class HiddenMeshNetworkSetup:
    """
    Creates network with hidden mesh infrastructure.
    Routers see only their actual interfaces, mesh is hidden.
    """
    
    def __init__(self, verbose: int = 0, enable_policy_routing: bool = False):
        self.verbose = verbose
        self.enable_policy_routing = enable_policy_routing
        self.setup_logging()
        
        # Determine facts directories
        self.raw_facts_dir = Path(os.environ.get('TRACEROUTE_SIMULATOR_RAW_FACTS', 'tests/raw_facts'))
        self.json_facts_dir = Path(os.environ.get('TRACEROUTE_SIMULATOR_FACTS', '/tmp/traceroute_test_output'))
        
        # Raw facts loader - ONLY source of data
        self.raw_loader = RawFactsBlockLoader(verbose=verbose)
        
        # Network state from raw facts only
        self.routers: Dict[str, RouterRawFacts] = {}
        self.router_interfaces: Dict[str, List[Dict]] = {}  # router -> [interface_configs]
        self.created_namespaces: Set[str] = set()
        self.created_bridges: Set[str] = set()
        self.created_interfaces: Set[str] = set()
        
        # Router name compression for hidden infrastructure (max 4 chars)
        self.router_codes: Dict[str, str] = {}  # full_name -> short_code
        self.code_to_router: Dict[str, str] = {}  # short_code -> full_name
        
        # Hidden infrastructure namespace
        self.hidden_ns = "hidden-mesh"
        
    def setup_logging(self):
        """Configure logging based on verbosity level."""
        if self.verbose == 0:
            level = logging.CRITICAL
        elif self.verbose == 1:
            level = logging.INFO
        else:
            level = logging.DEBUG
            
        logging.basicConfig(
            level=level,
            format='%(levelname)s: %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
    def load_raw_facts_only(self):
        """Load router facts from raw facts directory ONLY."""
        raw_facts_path = os.environ.get('TRACEROUTE_SIMULATOR_RAW_FACTS', 'tests/raw_facts')
        raw_facts_dir = Path(raw_facts_path)
        
        if not raw_facts_dir.exists():
            raise FileNotFoundError(f"Raw facts directory not found: {raw_facts_path}")
        
        self.logger.info(f"Loading raw facts from {raw_facts_dir}")
        self.routers = self.raw_loader.load_raw_facts_directory(raw_facts_dir)
        
        # Extract interface configurations from raw facts interfaces section
        self._extract_interface_configurations()
        
        self.logger.info(f"Loaded {len(self.routers)} routers with interface configs")
        
        # Generate compressed router codes
        self._generate_router_codes()
        
    def _generate_router_codes(self):
        """Generate compressed router codes for hidden infrastructure naming."""
        import hashlib
        
        # Sort router names for consistent ordering
        router_names = sorted(self.routers.keys())
        
        for i, router_name in enumerate(router_names):
            # Method 1: Use simple index-based codes (r000, r001, r002, etc.)
            # This ensures uniqueness and supports up to 1000 routers
            router_code = f"r{i:03d}"
            
            # Ensure uniqueness (shouldn't happen with index-based approach)
            while router_code in self.code_to_router:
                i += 1
                router_code = f"r{i:03d}"
            
            self.router_codes[router_name] = router_code
            self.code_to_router[router_code] = router_name
            
            self.logger.debug(f"Router {router_name} -> {router_code}")
        
        self.logger.info(f"Generated {len(self.router_codes)} router codes")
        
    def _extract_interface_configurations(self):
        """Extract interface configurations from raw facts interfaces section."""
        for router_name, router_facts in self.routers.items():
            self.logger.debug(f"Extracting interface config for {router_name}")
            
            # Get interfaces section from raw facts
            interfaces_section = router_facts.get_section('interfaces')
            if not interfaces_section:
                self.logger.warning(f"No interfaces section found for {router_name}")
                continue
            
            interfaces = []
            current_interface = None
            
            # Parse interfaces section (ip addr show output)
            for line in interfaces_section.content.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Interface line: "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500..."
                if_match = re.match(r'^\d+:\s+([^@:]+)(@\S+)?:\s+<([^>]+)>', line)
                if if_match:
                    interface_name = if_match.group(1)
                    interface_flags = if_match.group(3)
                    
                    # Skip loopback
                    if interface_name == 'lo':
                        current_interface = None
                        continue
                    
                    current_interface = {
                        'name': interface_name,
                        'flags': interface_flags,
                        'addresses': []
                    }
                    interfaces.append(current_interface)
                    continue
                
                # IP address line: "    inet 10.1.1.1/24 brd 10.1.1.255 scope global eth1"
                if current_interface and 'inet ' in line:
                    ip_match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+/\d+)', line)
                    if ip_match:
                        ip_with_prefix = ip_match.group(1)
                        current_interface['addresses'].append(ip_with_prefix)
            
            self.router_interfaces[router_name] = interfaces
            self.logger.debug(f"Found {len(interfaces)} interfaces for {router_name}: {[i['name'] for i in interfaces]}")
            
    def run_cmd(self, cmd: str, namespace: str = None, check: bool = True):
        """Run a command, optionally in a namespace."""
        if namespace:
            full_cmd = f"ip netns exec {namespace} {cmd}"
        else:
            full_cmd = cmd
            
        self.logger.debug(f"Running: {full_cmd}")
        
        result = subprocess.run(
            full_cmd, shell=True, capture_output=True, text=True, check=check
        )
        
        if result.returncode != 0 and check:
            self.logger.error(f"Command failed: {full_cmd}")
            self.logger.error(f"Error: {result.stderr}")
            raise subprocess.CalledProcessError(result.returncode, full_cmd, result.stderr)
            
        return result
        
    def setup_hidden_mesh_network(self):
        """Set up network with hidden mesh infrastructure."""
        try:
            self.logger.info("Setting up network with hidden mesh infrastructure")
            
            # Clean any existing setup
            self.cleanup_network()
            
            # Create hidden mesh infrastructure
            self.create_hidden_infrastructure()
            
            # Create router namespaces with ONLY their actual interfaces
            self.create_router_namespaces()
            
            # Connect routers to hidden infrastructure
            self.connect_routers_to_infrastructure()
            
            # Apply complete configuration from raw facts
            self.apply_complete_configurations()
            
            # Apply VPN latency after everything is configured
            self._configure_vpn_latency()
            
            # Final cleanup: ensure no simulation interfaces remain in host namespace
            self._cleanup_host_namespace_interfaces()
            
            self.logger.info("Hidden mesh network setup complete")
            
        except Exception as e:
            self.logger.error(f"Setup failed: {e}")
            self.cleanup_network()
            raise
            
    def create_hidden_infrastructure(self):
        """Create hidden mesh infrastructure namespace."""
        self.logger.info("Creating hidden mesh infrastructure")
        
        try:
            self.run_cmd(f"ip netns add {self.hidden_ns}")
            self.created_namespaces.add(self.hidden_ns)
            self.logger.debug(f"Created hidden namespace {self.hidden_ns}")
            
        except subprocess.CalledProcessError as e:
            # Check if namespace actually exists
            result = self.run_cmd(f"ip netns list | grep -w {self.hidden_ns}", check=False)
            if result.returncode == 0:
                self.logger.debug(f"Hidden namespace {self.hidden_ns} already exists")
                self.created_namespaces.add(self.hidden_ns)
            else:
                error_msg = f"CRITICAL: Failed to create hidden namespace {self.hidden_ns}: {e}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
        
        # Verify the namespace exists before proceeding
        result = self.run_cmd(f"ip netns list | grep -w {self.hidden_ns}", check=False)
        if result.returncode != 0:
            error_msg = f"CRITICAL: Hidden namespace {self.hidden_ns} does not exist after creation attempt"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        
        try:
            # Enable IP forwarding in hidden namespace
            self.run_cmd(f"echo 1 > /proc/sys/net/ipv4/ip_forward", self.hidden_ns)
            self.run_cmd(f"ip link set lo up", self.hidden_ns)
            self.logger.debug(f"Configured hidden namespace {self.hidden_ns}")
            
        except subprocess.CalledProcessError as e:
            error_msg = f"CRITICAL: Failed to configure hidden namespace {self.hidden_ns}: {e}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        
        # Create bridges for each subnet in hidden namespace
        self._create_subnet_bridges()
        
    def _generate_bridge_name(self, subnet: str) -> str:
        """Generate abbreviated bridge name that fits 15 character limit."""
        # Convert subnet like "10.100.1.0/24" to abbreviated form
        # Examples: 10.1.1.0/24 -> br111024, 10.100.1.0/24 -> br1001024
        ip_part, prefix = subnet.split('/')
        octets = ip_part.split('.')
        
        # Remove trailing zeros and compress
        compressed_octets = []
        for octet in octets:
            if octet == '0':
                compressed_octets.append('')  # Skip trailing zeros
            else:
                compressed_octets.append(octet)
        
        # Join and create compact name
        ip_compressed = ''.join(compressed_octets)
        bridge_name = f"br{ip_compressed}{prefix}"
        
        # Ensure it fits in 15 characters
        if len(bridge_name) > 15:
            # Fallback: use hash for very long names
            import hashlib
            subnet_hash = hashlib.md5(subnet.encode()).hexdigest()[:8]
            bridge_name = f"br{subnet_hash}"
        
        return bridge_name
        
    def _create_subnet_bridges(self):
        """Create bridges for each subnet in hidden infrastructure."""
        # Extract all subnets from router interfaces
        subnets = set()
        
        for router_name, interfaces in self.router_interfaces.items():
            for interface in interfaces:
                for ip_addr in interface['addresses']:
                    # Extract network from IP/prefix
                    try:
                        import ipaddress
                        network = ipaddress.IPv4Network(ip_addr, strict=False)
                        subnets.add(str(network))
                    except:
                        continue
        
        self.logger.info(f"Creating bridges for {len(subnets)} subnets")
        
        for subnet in subnets:
            # Create bridge name from subnet (abbreviated to fit 15 char limit)
            bridge_name = self._generate_bridge_name(subnet)
            
            try:
                self.run_cmd(f"ip link add {bridge_name} type bridge", self.hidden_ns)
                self.run_cmd(f"ip link set {bridge_name} up", self.hidden_ns)
                self.created_bridges.add(bridge_name)
                
                
                self.logger.debug(f"Created bridge {bridge_name} for subnet {subnet}")
                
            except subprocess.CalledProcessError:
                self.logger.warning(f"Bridge {bridge_name} already exists")
                
    def _add_vpn_latency(self, bridge_name: str):
        """Add realistic VPN latency (10ms) to VPN interfaces."""
        # Apply latency to each wg0 interface connected to this bridge
        vpn_routers = ['hq-gw', 'br-gw', 'dc-gw']
        
        for router_name in vpn_routers:
            if router_name in self.created_namespaces:
                try:
                    # Add traffic control qdisc with 10ms delay to wg0 interface
                    self.run_cmd(f"tc qdisc add dev wg0 root netem delay 10ms", router_name)
                    self.logger.debug(f"Added 10ms VPN latency to {router_name}:wg0")
                except subprocess.CalledProcessError as e:
                    self.logger.warning(f"Failed to add VPN latency to {router_name}:wg0: {e}")
        
        # Also add some delay to the bridge for good measure
        try:
            self.run_cmd(f"tc qdisc add dev {bridge_name} root netem delay 5ms", self.hidden_ns)
            self.logger.debug(f"Added 5ms bridge latency to {bridge_name}")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to add bridge latency to {bridge_name}: {e}")
            
    def _configure_vpn_latency(self):
        """Configure VPN latency on all VPN interfaces after full setup."""
        self.logger.info("Configuring VPN latency for realistic WireGuard simulation")
        
        # Load metadata from JSON files to identify gateway routers
        import json
        from pathlib import Path
        
        for router_name in self.routers.keys():
            if router_name in self.created_namespaces:
                # Load metadata from JSON file
                json_file = self.json_facts_dir / f"{router_name}.json"
                if json_file.exists():
                    try:
                        with open(json_file, 'r') as f:
                            router_data = json.load(f)
                        
                        metadata = router_data.get('metadata', {})
                        if metadata.get('type') == 'gateway':
                            # This is a gateway router, check if it has wg0 interface
                            result = self.run_cmd(f"ip link show wg0", router_name, check=False)
                            if result.returncode == 0:
                                # wg0 interface exists, add VPN latency
                                self.run_cmd(f"tc qdisc add dev wg0 root netem delay 10ms", router_name)
                                self.logger.debug(f"Added 10ms VPN latency to {router_name}:wg0")
                            
                    except (json.JSONDecodeError, KeyError, subprocess.CalledProcessError) as e:
                        self.logger.warning(f"Failed to configure VPN latency for {router_name}: {e}")
                        
    def _recreate_registered_hosts(self):
        """Recreate all hosts from registry if they exist."""
        try:
            # Import host manager
            from pathlib import Path
            import sys
            host_manager_path = Path(__file__).parent
            sys.path.insert(0, str(host_manager_path))
            from host_namespace_setup import HostNamespaceManager
            
            host_manager = HostNamespaceManager(verbose=self.verbose)
            registry = host_manager.load_host_registry()
            
            if not registry:
                self.logger.debug("No hosts registered, skipping host recreation")
                return
                
            self.logger.info(f"Recreating {len(registry)} registered hosts")
            
            for host_name, host_config in registry.items():
                primary_ip = host_config.get('primary_ip', '')
                secondary_ips = host_config.get('secondary_ips', [])
                connected_to = host_config.get('connected_to', '')
                
                if primary_ip and connected_to:
                    self.logger.debug(f"Recreating host {host_name}: {primary_ip} -> {connected_to}")
                    try:
                        # Only recreate if namespace doesn't exist
                        if host_name not in host_manager.available_namespaces:
                            success = host_manager._recreate_host_namespace(
                                host_name=host_name,
                                host_config=host_config
                            )
                            if success:
                                self.logger.debug(f"Successfully recreated host {host_name}")
                            else:
                                self.logger.warning(f"Failed to recreate host {host_name}")
                        else:
                            self.logger.debug(f"Host {host_name} namespace already exists, skipping")
                    except Exception as e:
                        self.logger.warning(f"Error recreating host {host_name}: {e}")
                        
        except Exception as e:
            self.logger.warning(f"Failed to recreate registered hosts: {e}")
                
    def create_router_namespaces(self):
        """Create namespaces for routers with ONLY their actual interfaces."""
        self.logger.info(f"Creating {len(self.routers)} router namespaces")
        
        for router_name in self.routers.keys():
            self.logger.debug(f"Creating namespace for {router_name}")
            
            try:
                self.run_cmd(f"ip netns add {router_name}")
                self.created_namespaces.add(router_name)
                
                # Enable IP forwarding
                self.run_cmd(f"echo 1 > /proc/sys/net/ipv4/ip_forward", router_name)
                
                # Enable loopback
                self.run_cmd(f"ip link set lo up", router_name)
                
            except subprocess.CalledProcessError:
                self.logger.warning(f"Namespace {router_name} already exists")
            
            # Create ONLY the actual interfaces from raw facts
            self._create_router_actual_interfaces(router_name)
                
    def _create_router_actual_interfaces(self, router_name: str):
        """Create ONLY the actual interfaces from raw facts."""
        interfaces = self.router_interfaces.get(router_name, [])
        
        self.logger.debug(f"Creating actual interfaces for {router_name}")
        
        for interface_config in interfaces:
            interface_name = interface_config['name']
            addresses = interface_config['addresses']
            
            self.logger.debug(f"Creating interface {interface_name} for {router_name}")
            
            try:
                # Create unique veth pair names using compressed router codes (max 15 chars for Linux interface names)
                router_code = self.router_codes[router_name]  # e.g. r00, r01, r02
                
                # Create unique interface abbreviation to avoid conflicts like wlan0/wlan1
                if len(interface_name) <= 5:
                    interface_abbrev = interface_name  # eth0, wg0, etc. - use full name
                else:
                    # For longer names, include distinguishing character
                    interface_abbrev = interface_name[:4] + interface_name[-1]  # wlan0 -> wlan0, wlan1 -> wlan1
                    
                veth_router = f"{router_code}{interface_abbrev}r"  # e.g. r00eth0r, r02wlan0r (max 10 chars)
                veth_hidden = f"{router_code}{interface_abbrev}h"  # e.g. r00eth0h, r02wlan0h (max 10 chars)
                
                # Create veth pair in host namespace (required by Linux kernel)
                try:
                    self.run_cmd(f"ip link add {veth_router} type veth peer name {veth_hidden}")
                    self.logger.debug(f"Created veth pair {veth_router} <-> {veth_hidden}")
                except subprocess.CalledProcessError as e:
                    error_msg = f"CRITICAL: Failed to create veth pair {veth_router}/{veth_hidden} for {router_name}:{interface_name}: {e}"
                    self.logger.error(error_msg)
                    raise Exception(error_msg)
                
                # Move router end to router namespace
                try:
                    self.run_cmd(f"ip link set {veth_router} netns {router_name}")
                    self.logger.debug(f"Moved {veth_router} to namespace {router_name}")
                except subprocess.CalledProcessError as e:
                    # Clean up the veth pair from host namespace
                    self.run_cmd(f"ip link del {veth_router}", check=False)
                    error_msg = f"CRITICAL: Failed to move {veth_router} to namespace {router_name}: {e}"
                    self.logger.error(error_msg)
                    raise Exception(error_msg)
                
                # Move hidden end to hidden infrastructure namespace
                try:
                    self.run_cmd(f"ip link set {veth_hidden} netns {self.hidden_ns}")
                    self.logger.debug(f"Moved {veth_hidden} to namespace {self.hidden_ns}")
                except subprocess.CalledProcessError as e:
                    # The router end is already moved, can't clean up easily - this is a critical failure
                    error_msg = f"CRITICAL: Failed to move {veth_hidden} to namespace {self.hidden_ns}: {e}. Router interface {veth_router} is stranded in {router_name}."
                    self.logger.error(error_msg)
                    raise Exception(error_msg)
                
                # Verify both interfaces exist in their target namespaces
                try:
                    # Check router interface exists in router namespace
                    result = self.run_cmd(f"ip link show {veth_router}", router_name, check=False)
                    if result.returncode != 0:
                        error_msg = f"CRITICAL: Interface {veth_router} not found in namespace {router_name} after move"
                        self.logger.error(error_msg)
                        raise Exception(error_msg)
                    
                    # Check hidden interface exists in hidden namespace
                    result = self.run_cmd(f"ip link show {veth_hidden}", self.hidden_ns, check=False)
                    if result.returncode != 0:
                        error_msg = f"CRITICAL: Interface {veth_hidden} not found in namespace {self.hidden_ns} after move"
                        self.logger.error(error_msg)
                        raise Exception(error_msg)
                    
                    self.logger.debug(f"Verified both interfaces exist in target namespaces")
                    
                except subprocess.CalledProcessError as e:
                    error_msg = f"CRITICAL: Failed to verify interface existence after move: {e}"
                    self.logger.error(error_msg)
                    raise Exception(error_msg)
                
                # Only track as created if everything succeeded
                self.created_interfaces.add(veth_router)
                self.created_interfaces.add(veth_hidden)
                
                # Rename router interface to exact name from raw facts
                try:
                    self.run_cmd(f"ip link set {veth_router} name {interface_name}", router_name)
                    self.logger.debug(f"Renamed {veth_router} to {interface_name} in {router_name}")
                except subprocess.CalledProcessError as e:
                    error_msg = f"CRITICAL: Failed to rename {veth_router} to {interface_name} in {router_name}: {e}"
                    self.logger.error(error_msg)
                    raise Exception(error_msg)
                
                # Configure IP addresses on router interface
                for ip_addr in addresses:
                    try:
                        self.run_cmd(f"ip addr add {ip_addr} dev {interface_name}", router_name)
                        self.logger.debug(f"Added IP {ip_addr} to {interface_name} in {router_name}")
                    except subprocess.CalledProcessError as e:
                        error_msg = f"CRITICAL: Failed to add IP {ip_addr} to {interface_name} in {router_name}: {e}"
                        self.logger.error(error_msg)
                        raise Exception(error_msg)
                
                # Bring up router interface
                try:
                    self.run_cmd(f"ip link set {interface_name} up", router_name)
                    self.logger.debug(f"Brought up interface {interface_name} in {router_name}")
                except subprocess.CalledProcessError as e:
                    error_msg = f"CRITICAL: Failed to bring up interface {interface_name} in {router_name}: {e}"
                    self.logger.error(error_msg)
                    raise Exception(error_msg)
                
                # Bring up hidden interface
                try:
                    self.run_cmd(f"ip link set {veth_hidden} up", self.hidden_ns)
                    self.logger.debug(f"Brought up hidden interface {veth_hidden} in {self.hidden_ns}")
                except subprocess.CalledProcessError as e:
                    error_msg = f"CRITICAL: Failed to bring up hidden interface {veth_hidden} in {self.hidden_ns}: {e}"
                    self.logger.error(error_msg)
                    raise Exception(error_msg)
                
                self.logger.info(f"Successfully created and configured {interface_name} with IPs: {addresses}")
                
            except Exception as e:
                # Any unhandled exception in interface creation is critical
                error_msg = f"CRITICAL: Unexpected error creating interface {interface_name} for {router_name}: {e}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
                
    def connect_routers_to_infrastructure(self):
        """Connect router interfaces to appropriate bridges in hidden infrastructure."""
        self.logger.info("Connecting routers to hidden infrastructure")
        
        for router_name, interfaces in self.router_interfaces.items():
            for interface_config in interfaces:
                interface_name = interface_config['name']
                addresses = interface_config['addresses']
                
                # Find which bridge this interface should connect to
                for ip_addr in addresses:
                    try:
                        import ipaddress
                        network = ipaddress.IPv4Network(ip_addr, strict=False)
                        subnet = str(network)
                        bridge_name = self._generate_bridge_name(subnet)
                        
                        # Connect hidden interface to bridge
                        router_code = self.router_codes[router_name]
                        
                        # Use same interface abbreviation logic as in interface creation
                        if len(interface_name) <= 5:
                            interface_abbrev = interface_name  # eth0, wg0, etc. - use full name
                        else:
                            # For longer names, include distinguishing character
                            interface_abbrev = interface_name[:4] + interface_name[-1]  # wlan0 -> wlan0, wlan1 -> wlan1
                        
                        veth_hidden = f"{router_code}{interface_abbrev}h"
                        
                        try:
                            self.run_cmd(f"ip link set {veth_hidden} master {bridge_name}", self.hidden_ns)
                            self.logger.debug(f"Connected {router_name}:{interface_name} to {bridge_name}")
                        except subprocess.CalledProcessError as e:
                            self.logger.warning(f"Failed to connect {veth_hidden} to {bridge_name}: {e}")
                            
                    except Exception as e:
                        self.logger.warning(f"Failed to process IP {ip_addr}: {e}")
                        continue
                        
    def apply_complete_configurations(self):
        """Apply complete router configurations from raw facts."""
        self.logger.info("Applying complete router configurations from raw facts")
        
        for router_name, router_facts in self.routers.items():
            self.logger.info(f"Configuring {router_name} with complete raw facts")
            
            try:
                # Apply routing configuration
                self._apply_routing_configuration(router_name, router_facts)
                
                # Apply iptables configuration
                self._apply_iptables_configuration(router_name, router_facts)
                
                # Apply ipsets configuration
                self._apply_ipsets_configuration(router_name, router_facts)
                
                self.logger.debug(f"Successfully configured {router_name}")
                
            except Exception as e:
                self.logger.error(f"Failed to configure {router_name}: {e}")
                # Continue with other routers
                
    def _apply_routing_configuration(self, router_name: str, router_facts: RouterRawFacts):
        """Apply routing tables and policy rules (policy routing conditional)."""
        # Always apply main routing table
        routing_section = router_facts.get_section('routing_table')
        if routing_section:
            self._apply_routes(router_name, routing_section.content, 'main')
        
        # Apply policy rules and additional tables only if enabled
        if self.enable_policy_routing:
            # Apply policy rules
            policy_section = router_facts.get_section('policy_rules')
            if policy_section:
                self._apply_policy_rules(router_name, policy_section.content)
            
            # Apply additional routing tables
            for section_name, section in router_facts.sections.items():
                if section_name.startswith('routing_table_') and section_name != 'routing_table':
                    table_name = section_name.replace('routing_table_', '')
                    table_id = self._get_table_id(table_name)
                    if table_id:
                        self._apply_routes(router_name, section.content, table_id)
        else:
            self.logger.debug(f"Policy routing disabled for {router_name} (use --policy-routing to enable)")
    
    def _get_table_id(self, table_name: str) -> Optional[str]:
        """Get numeric table ID for named table."""
        table_mapping = {
            'priority_table': '100',
            'service_table': '200', 
            'backup_table': '300',
            'qos_table': '400',
            'management_table': '500',
            'database_table': '600',
            'web_table': '700',
            'emergency_table': '800'
        }
        return table_mapping.get(table_name)
        
    def _apply_routes(self, router_name: str, routes_content: str, table: str):
        """Apply routing table entries."""
        if not routes_content.strip():
            return
        
        # Handle embedded newlines in content
        routes_content = routes_content.replace('\\n', '\n')
        
        for line in routes_content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Apply route
            cmd = f"ip route add {line}"
            if table != 'main':
                cmd += f" table {table}"
            
            try:
                self.run_cmd(cmd, router_name, check=False)
            except Exception as e:
                self.logger.debug(f"Route add failed (expected): {e}")
                
    def _apply_policy_rules(self, router_name: str, rules_content: str):
        """Apply policy routing rules."""
        if not rules_content.strip():
            return
        
        for line in rules_content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('0:') or 'lookup local' in line:
                continue
            
            # Parse rule and convert to ip rule add command
            rule_match = re.match(r'(\d+):\s*(.+)', line)
            if rule_match:
                priority = rule_match.group(1)
                rule_spec = rule_match.group(2)
                
                # Convert table names to IDs
                for table_name, table_id in [
                    ('priority_table', '100'), ('service_table', '200'),
                    ('backup_table', '300'), ('qos_table', '400'),
                    ('management_table', '500'), ('database_table', '600'),
                    ('web_table', '700'), ('emergency_table', '800')
                ]:
                    rule_spec = rule_spec.replace(f'lookup {table_name}', f'table {table_id}')
                
                cmd = f"ip rule add pref {priority} {rule_spec}"
                
                try:
                    self.run_cmd(cmd, router_name, check=False)
                except Exception as e:
                    self.logger.debug(f"Rule add failed (expected): {e}")
                    
    def _apply_iptables_configuration(self, router_name: str, router_facts: RouterRawFacts):
        """Apply iptables configuration."""
        iptables_save_section = router_facts.get_section('iptables_save')
        if iptables_save_section:
            self._apply_iptables_save(router_name, iptables_save_section.content)
            
    def _apply_iptables_save(self, router_name: str, iptables_content: str):
        """Apply iptables configuration using iptables-restore."""
        if not iptables_content.strip():
            return
        
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.iptables', delete=False) as f:
                f.write(iptables_content)
                temp_file = f.name
            
            cmd = f"iptables-restore < {temp_file}"
            self.run_cmd(cmd, router_name, check=False)
            
            Path(temp_file).unlink()
            
        except Exception as e:
            self.logger.debug(f"iptables restore failed (expected): {e}")
            
    def _apply_ipsets_configuration(self, router_name: str, router_facts: RouterRawFacts):
        """Apply ipsets configuration."""
        ipset_save_section = router_facts.get_section('ipset_save')
        if ipset_save_section:
            self._apply_ipset_save(router_name, ipset_save_section.content)
            
    def _apply_ipset_save(self, router_name: str, ipset_content: str):
        """Apply ipset configuration using ipset restore."""
        if not ipset_content.strip():
            return
        
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.ipset', delete=False) as f:
                f.write(ipset_content)
                temp_file = f.name
            
            cmd = f"ipset restore < {temp_file}"
            self.run_cmd(cmd, router_name, check=False)
            
            Path(temp_file).unlink()
            
        except Exception as e:
            self.logger.debug(f"ipset restore failed (expected): {e}")
            
    def cleanup_network(self):
        """Clean up all created network resources."""
        self.logger.info("Cleaning up hidden mesh network")
        
        # Remove all created namespaces (this removes interfaces too)
        for ns in list(self.created_namespaces):
            try:
                self.run_cmd(f"ip netns del {ns}", check=False)
            except:
                pass
                
        self.created_namespaces.clear()
        self.created_interfaces.clear()
        self.created_bridges.clear()
        
    def _cleanup_host_namespace_interfaces(self):
        """Remove any simulation interfaces that may be left in the host namespace."""
        self.logger.debug("Checking for simulation interfaces in host namespace")
        
        try:
            # Get all interfaces in host namespace
            result = self.run_cmd("ip link show", check=False)
            if result.returncode != 0:
                return
            
            import re
            simulation_interfaces = []
            
            for line in result.stdout.split('\n'):
                # Look for simulation interface patterns
                match = re.search(r'^\d+:\s+([^@:]+)', line)
                if match:
                    interface_name = match.group(1)
                    
                    # Check if it matches our simulation patterns
                    if (re.match(r'^r\d{3}\w+[rh]$', interface_name) or  # New compressed naming
                        any(router_code in interface_name for router_code in self.router_codes.values())):
                        simulation_interfaces.append(interface_name)
            
            # Remove any found simulation interfaces
            for interface in simulation_interfaces:
                self.logger.warning(f"Removing leftover simulation interface from host: {interface}")
                self.run_cmd(f"ip link del {interface}", check=False)
                
            if simulation_interfaces:
                self.logger.info(f"Cleaned up {len(simulation_interfaces)} leftover interfaces from host namespace")
                
        except Exception as e:
            self.logger.debug(f"Error during host namespace cleanup: {e}")
        
    def verify_setup(self):
        """Verify the network setup."""
        self.logger.info("Verifying network setup")
        
        verification_passed = True
        
        for router_name in self.routers.keys():
            try:
                # Check namespace exists
                result = self.run_cmd(f"ip netns exec {router_name} ip addr show", check=False)
                if result.returncode != 0:
                    self.logger.error(f"Namespace {router_name} not accessible")
                    verification_passed = False
                    continue
                
                # Check interfaces exist
                interfaces = self.router_interfaces.get(router_name, [])
                for interface_config in interfaces:
                    interface_name = interface_config['name']
                    result = self.run_cmd(f"ip link show {interface_name}", router_name, check=False)
                    if result.returncode != 0:
                        self.logger.error(f"Interface {interface_name} missing in {router_name}")
                        verification_passed = False
                
            except Exception as e:
                self.logger.error(f"Verification failed for {router_name}: {e}")
                verification_passed = False
        
        if verification_passed:
            self.logger.info("Network setup verification passed")
        else:
            self.logger.error("Network setup verification failed")
            
        return verification_passed


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Hidden Mesh Network Namespace Setup')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity (-v for info, -vv for debug)')
    parser.add_argument('--cleanup', action='store_true',
                       help='Clean up existing setup and exit')
    parser.add_argument('--verify', action='store_true',
                       help='Verify setup after creation')
    parser.add_argument('--policy-routing', action='store_true',
                       help='Enable policy routing rules and additional routing tables (disabled by default)')
    
    args = parser.parse_args()
    
    if os.geteuid() != 0:
        print("Error: This script must be run as root (use sudo)")
        return 1
    
    setup = HiddenMeshNetworkSetup(verbose=args.verbose, enable_policy_routing=args.policy_routing)
    
    try:
        if args.cleanup:
            setup.cleanup_network()
            print("Network cleanup completed")
            return 0
        
        # Load facts from raw facts only
        setup.load_raw_facts_only()
        
        # Set up hidden mesh network
        setup.setup_hidden_mesh_network()
        
        # Verify if requested
        if args.verify:
            if not setup.verify_setup():
                return 1
        
        print(f"Hidden mesh network setup complete with {len(setup.routers)} routers")
        print("Use 'sudo make netstatus ARGS=\"<router> <function>\"' to check status")
        
    except KeyboardInterrupt:
        print("\nSetup interrupted")
        setup.cleanup_network()
        return 1
    except Exception as e:
        print(f"Setup failed: {e}")
        setup.cleanup_network()
        return 1
    
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())