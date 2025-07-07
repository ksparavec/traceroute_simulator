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
import json
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
    
    def __init__(self, verbose: int = 0, limit_pattern: str = None):
        self.verbose = verbose
        self.limit_pattern = limit_pattern
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
        
        # Router registry for persistent code mapping
        self.router_registry_file = Path("/tmp/traceroute_routers_registry.json")
        
        # Hidden infrastructure namespace
        self.hidden_ns = "hidden-mesh"
        
    def setup_logging(self):
        """Configure logging based on verbosity level."""
        if self.verbose == 0:
            level = logging.WARNING
        elif self.verbose == 1:
            level = logging.INFO
        elif self.verbose == 2:
            level = logging.DEBUG
        else:  # verbose >= 3 (-vvv)
            level = logging.DEBUG
            
        logging.basicConfig(
            level=level,
            format='%(message)s'  # Simplified format for cleaner output
        )
        self.logger = logging.getLogger(__name__)
        
        # Track router setup statistics
        self.router_stats = {}
        self.setup_errors = []
        self.setup_warnings = []
        
    def load_raw_facts_only(self):
        """Load router facts from raw facts directory ONLY."""
        raw_facts_dir = self.raw_facts_dir
        
        if not raw_facts_dir.exists():
            raise FileNotFoundError(f"Raw facts directory not found: {raw_facts_dir}")
        
        self.logger.info(f"Loading raw facts from {raw_facts_dir}")
        all_routers = self.raw_loader.load_raw_facts_directory(raw_facts_dir)
        
        # Apply router filtering if limit pattern is specified
        if self.limit_pattern:
            self.routers = self._filter_routers(all_routers, self.limit_pattern)
            if self.verbose >= 1:
                print(f"Filtered {len(all_routers)} routers to {len(self.routers)} using pattern '{self.limit_pattern}'")
                if self.verbose >= 2:
                    filtered_names = list(self.routers.keys())
                    print(f"Selected routers: {', '.join(filtered_names)}")
        else:
            self.routers = all_routers
        
        if not self.routers:
            raise ValueError(f"No routers found matching pattern '{self.limit_pattern}' in {raw_facts_dir}")
        
        # Extract interface configurations from raw facts interfaces section
        self._extract_interface_configurations()
        
        self.logger.info(f"Loaded {len(self.routers)} routers with interface configs")
        
        # Generate compressed router codes
        self._generate_router_codes()
    
    def _filter_routers(self, all_routers: Dict, pattern: str) -> Dict:
        """Filter routers based on glob pattern."""
        import fnmatch
        
        filtered_routers = {}
        
        for router_name, router_facts in all_routers.items():
            if fnmatch.fnmatch(router_name, pattern):
                filtered_routers[router_name] = router_facts
        
        return filtered_routers
        
    def load_router_registry(self) -> Dict[str, str]:
        """Load registry of router name to code mappings."""
        if not self.router_registry_file.exists():
            return {}
            
        try:
            with open(self.router_registry_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Could not load router registry: {e}")
            return {}
            
    def save_router_registry(self):
        """Save registry of router name to code mappings."""
        try:
            with open(self.router_registry_file, 'w') as f:
                json.dump(self.router_codes, f, indent=2)
        except IOError as e:
            self.logger.error(f"Could not save router registry: {e}")

    def _generate_router_codes(self):
        """Generate compressed router codes for hidden infrastructure naming."""
        # Load existing registry first
        existing_registry = self.load_router_registry()
        self.router_codes.update(existing_registry)
        
        # Build reverse mapping
        for router_name, router_code in self.router_codes.items():
            self.code_to_router[router_code] = router_name
        
        # Sort router names for consistent ordering
        router_names = sorted(self.routers.keys())
        
        # Find the next available code number
        used_numbers = set()
        for code in self.router_codes.values():
            if code.startswith('r') and len(code) == 4 and code[1:].isdigit():
                used_numbers.add(int(code[1:]))
        
        next_code_num = 0
        
        for router_name in router_names:
            # Skip if router already has a code
            if router_name in self.router_codes:
                self.logger.debug(f"Router {router_name} -> {self.router_codes[router_name]} (from registry)")
                continue
                
            # Find next available code number
            while next_code_num in used_numbers:
                next_code_num += 1
                
            router_code = f"r{next_code_num:03d}"
            used_numbers.add(next_code_num)
            next_code_num += 1
            
            self.router_codes[router_name] = router_code
            self.code_to_router[router_code] = router_name
            
            self.logger.debug(f"Router {router_name} -> {router_code} (new)")
        
        self.logger.info(f"Generated {len(self.router_codes)} router codes")
        
        # Save the updated registry
        self.save_router_registry()
        
    def _extract_interface_configurations(self):
        """Extract complete interface configurations from raw facts interfaces section."""
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
                
                # Interface line: "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast state UP group default qlen 1000"
                if_match = re.match(r'^\d+:\s+([^@:]+)(@\S+)?:\s+<([^>]+)>(.*)$', line)
                if if_match:
                    interface_name = if_match.group(1)
                    interface_flags = if_match.group(3)
                    interface_details = if_match.group(4).strip() if if_match.group(4) else ""
                    
                    # Skip loopback
                    if interface_name == 'lo':
                        current_interface = None
                        continue
                    
                    # Extract interface properties from details line
                    mtu = self._extract_interface_property(interface_details, r'mtu\s+(\d+)')
                    qdisc = self._extract_interface_property(interface_details, r'qdisc\s+(\S+)')
                    state = self._extract_interface_property(interface_details, r'state\s+(\S+)')
                    
                    # Determine if interface should be UP based on flags and state
                    flags_list = [f.strip() for f in interface_flags.split(',')]
                    should_be_up = 'UP' in flags_list and state != 'DOWN'
                    
                    current_interface = {
                        'name': interface_name,
                        'flags': interface_flags,
                        'flags_list': flags_list,
                        'mtu': mtu,
                        'qdisc': qdisc,
                        'state': state,
                        'should_be_up': should_be_up,
                        'addresses': []
                    }
                    interfaces.append(current_interface)
                    continue
                
                # Link line: "    link/ether 52:54:00:12:34:56 brd ff:ff:ff:ff:ff:ff"
                if current_interface and line.startswith('link/'):
                    link_match = re.search(r'link/\w+\s+([a-f0-9:]+)(?:\s+brd\s+([a-f0-9:]+))?', line)
                    if link_match:
                        current_interface['mac_address'] = link_match.group(1)
                        if link_match.group(2):
                            current_interface['link_broadcast'] = link_match.group(2)
                    continue
                
                # IP address line: "    inet 10.1.1.1/24 brd 10.1.1.255 scope global eth1"
                if current_interface and 'inet ' in line:
                    ip_match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+/\d+)(?:\s+brd\s+(\d+\.\d+\.\d+\.\d+))?(?:\s+scope\s+(\S+))?', line)
                    if ip_match:
                        ip_with_prefix = ip_match.group(1)
                        broadcast = ip_match.group(2)
                        scope = ip_match.group(3) if ip_match.group(3) else 'global'
                        
                        # Check if this is a secondary address
                        is_secondary = 'secondary' in line
                        
                        addr_info = {
                            'ip': ip_with_prefix,
                            'broadcast': broadcast,
                            'scope': scope,
                            'secondary': is_secondary
                        }
                        current_interface['addresses'].append(addr_info)
            
            self.router_interfaces[router_name] = interfaces
            self.logger.debug(f"Found {len(interfaces)} interfaces for {router_name}: {[i['name'] for i in interfaces]}")
    
    def _extract_interface_property(self, details_line: str, regex_pattern: str) -> Optional[str]:
        """Extract a specific property from interface details line."""
        match = re.search(regex_pattern, details_line)
        return match.group(1) if match else None
            
    def run_cmd(self, cmd: str, namespace: str = None, check: bool = True, log_cmd: bool = False):
        """Run a command, optionally in a namespace."""
        if namespace:
            full_cmd = f"ip netns exec {namespace} {cmd}"
        else:
            full_cmd = cmd
            
        # Log command details for -vvv level
        if self.verbose >= 3 and log_cmd:
            print(f"      CMD: {full_cmd}")
        
        self.logger.debug(f"Running: {full_cmd}")
        
        result = subprocess.run(
            full_cmd, shell=True, capture_output=True, text=True, check=check
        )
        
        # Log command response for -vvv level
        if self.verbose >= 3 and log_cmd:
            if result.returncode == 0:
                print(f"      OK: Command succeeded")
                if result.stdout.strip():
                    print(f"      OUT: {result.stdout.strip()}")
            else:
                print(f"      ERR: Command failed (exit {result.returncode})")
                if result.stderr.strip():
                    print(f"      STDERR: {result.stderr.strip()}")
        
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
            
            if self.verbose >= 1:
                self._print_final_summary()
            else:
                self.logger.info("Hidden mesh network setup complete")
            
        except Exception as e:
            self.logger.error(f"Setup failed: {e}")
            self.cleanup_network()
            return False
        
        return True
    
    def _print_final_summary(self):
        """Print final setup summary with overall statistics."""
        total_routers = len(self.routers)
        successful = sum(1 for stats in self.router_stats.values() 
                        if stats['namespace_created'] and not stats['errors'])
        partial = sum(1 for stats in self.router_stats.values() 
                     if stats['namespace_created'] and stats['interfaces_failed'] > 0)
        failed = sum(1 for stats in self.router_stats.values() 
                    if not stats['namespace_created'] or stats['errors'])
        
        total_interfaces = sum(stats['total_interfaces'] for stats in self.router_stats.values())
        created_interfaces = sum(stats['interfaces_created'] for stats in self.router_stats.values())
        failed_interfaces = sum(stats['interfaces_failed'] for stats in self.router_stats.values())
        
        total_warnings = sum(len(stats['warnings']) for stats in self.router_stats.values())
        total_errors = sum(len(stats['errors']) for stats in self.router_stats.values())
        
        # Count skipped sections
        routers_with_skipped = [name for name, stats in self.router_stats.items() 
                               if stats['skipped_sections']]
        
        print("\n=== SETUP SUMMARY ===")
        print(f"Routers: {successful} successful, {partial} partial, {failed} failed (total: {total_routers})")
        print(f"Interfaces: {created_interfaces}/{total_interfaces} created, {failed_interfaces} failed")
        
        if total_warnings > 0:
            print(f"Warnings: {total_warnings}")
        if total_errors > 0:
            print(f"Errors: {total_errors}")
        
        # Report skipped sections
        if routers_with_skipped:
            print(f"\nSkipped sections due to failures:")
            for router_name in routers_with_skipped:
                stats = self.router_stats[router_name]
                skipped = ', '.join(stats['skipped_sections'])
                print(f"  • {router_name}: {skipped}")
        
        if failed == 0 and failed_interfaces == 0:
            print("\n✓ Network setup completed successfully!")
        elif failed == 0:
            print("\n⚠ Network setup completed with some interface issues")
        else:
            print("\n✗ Network setup completed with router failures")
        
        print(f"\nUse 'sudo make netshow ROUTER=<name> FUNC=<function>' to check status")
            
    def create_hidden_infrastructure(self):
        """Create hidden mesh infrastructure namespace."""
        if self.verbose >= 1:
            print("\n=== Creating hidden mesh infrastructure ===")
        
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
                for addr_info in interface['addresses']:
                    # Extract network from IP/prefix (handle both dict and string formats)
                    try:
                        import ipaddress
                        # Extract IP address from the address info dictionary
                        ip_addr = addr_info['ip'] if isinstance(addr_info, dict) else addr_info
                        network = ipaddress.IPv4Network(ip_addr, strict=False)
                        subnets.add(str(network))
                    except:
                        continue
        
        if self.verbose >= 1:
            print(f"  → Creating {len(subnets)} subnet bridges")
        
        for subnet in subnets:
            # Create bridge name from subnet (abbreviated to fit 15 char limit)
            bridge_name = self._generate_bridge_name(subnet)
            
            try:
                self.run_cmd(f"ip link add {bridge_name} type bridge", self.hidden_ns)
                self.run_cmd(f"ip link set {bridge_name} up", self.hidden_ns)
                self.created_bridges.add(bridge_name)
                
                if self.verbose >= 2:
                    print(f"    ✓ Bridge {bridge_name} for {subnet}")
                
            except subprocess.CalledProcessError:
                if self.verbose >= 2:
                    print(f"    ⚠ Bridge {bridge_name} already exists")
                
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
        if self.verbose >= 1:
            print(f"\n=== Creating {len(self.routers)} router namespaces ===")
        
        for i, router_name in enumerate(self.routers.keys(), 1):
            if self.verbose >= 1:
                print(f"\n[{i}/{len(self.routers)}] Setting up router: {router_name}")
            
            # Initialize router statistics
            self.router_stats[router_name] = {
                'namespace_created': False,
                'interfaces_created': 0,
                'interfaces_failed': 0,
                'total_interfaces': len(self.router_interfaces.get(router_name, [])),
                'interfaces_success': False,  # True only if ALL interfaces successful
                'routing_applied': False,
                'routing_success': False,
                'ipsets_applied': False,
                'ipsets_success': False,
                'iptables_applied': False,
                'iptables_success': False,
                'errors': [],
                'warnings': [],
                'failed_interfaces': [],  # Track detailed failure info
                'skipped_sections': []  # Track sections skipped due to failures
            }
            
            try:
                # Create namespace
                if self.verbose >= 1:
                    print(f"  → Creating namespace {router_name}")
                
                try:
                    self.run_cmd(f"ip netns add {router_name}")
                    self.created_namespaces.add(router_name)
                    self.router_stats[router_name]['namespace_created'] = True
                    if self.verbose >= 2:
                        print(f"    ✓ Namespace created")
                except subprocess.CalledProcessError as e:
                    # Check if namespace already exists
                    result = self.run_cmd(f"ip netns list | grep -w {router_name}", check=False)
                    if result.returncode == 0:
                        if self.verbose >= 1:
                            print(f"    ⚠ Namespace already exists")
                        self.router_stats[router_name]['warnings'].append("Namespace already existed")
                        self.created_namespaces.add(router_name)
                        self.router_stats[router_name]['namespace_created'] = True
                    else:
                        error_msg = f"Failed to create namespace: {e}"
                        self.router_stats[router_name]['errors'].append(error_msg)
                        self.logger.error(f"Critical error for {router_name}: {error_msg}")
                        continue
                
                # Enable IP forwarding
                if self.verbose >= 2:
                    print(f"    → Enabling IP forwarding")
                try:
                    self.run_cmd(f"echo 1 > /proc/sys/net/ipv4/ip_forward", router_name)
                    if self.verbose >= 2:
                        print(f"    ✓ IP forwarding enabled")
                except subprocess.CalledProcessError as e:
                    warning_msg = f"Failed to enable IP forwarding: {e}"
                    self.router_stats[router_name]['warnings'].append(warning_msg)
                
                # Enable loopback
                if self.verbose >= 2:
                    print(f"    → Enabling loopback interface")
                try:
                    self.run_cmd(f"ip link set lo up", router_name)
                    if self.verbose >= 2:
                        print(f"    ✓ Loopback enabled")
                except subprocess.CalledProcessError as e:
                    warning_msg = f"Failed to enable loopback: {e}"
                    self.router_stats[router_name]['warnings'].append(warning_msg)
                
                # Create ONLY the actual interfaces from raw facts
                self._create_router_actual_interfaces(router_name)
                
            except Exception as e:
                error_msg = f"Unexpected error during setup: {e}"
                self.router_stats[router_name]['errors'].append(error_msg)
                self.logger.error(f"Critical error for {router_name}: {error_msg}")
            
            # Check if all interfaces were created successfully
            stats = self.router_stats[router_name]
            if stats['interfaces_created'] == stats['total_interfaces'] and stats['interfaces_failed'] == 0:
                stats['interfaces_success'] = True
            
            # Print router completion summary
            self._print_router_summary(router_name)
    
    def _print_router_summary(self, router_name: str):
        """Print one-line summary of router setup completion."""
        stats = self.router_stats[router_name]
        
        # Determine overall status - SUCCESS only if ALL sections successful
        if not stats['namespace_created']:
            status = "FAILED"
            status_icon = "✗"
        elif stats['errors']:
            status = "FAILED"
            status_icon = "✗"
        elif not stats['interfaces_success']:
            status = "FAILED"
            status_icon = "✗"
        elif stats['routing_applied'] and not stats['routing_success']:
            status = "FAILED"
            status_icon = "✗"
        elif stats['ipsets_applied'] and not stats['ipsets_success']:
            status = "FAILED"
            status_icon = "✗"
        elif stats['iptables_applied'] and not stats['iptables_success']:
            status = "FAILED"
            status_icon = "✗"
        elif stats['warnings']:
            status = "SUCCESS"
            status_icon = "✓"
        else:
            status = "SUCCESS"
            status_icon = "✓"
        
        # Build summary line
        if self.verbose >= 1:
            interfaces_info = f"{stats['interfaces_created']}/{stats['total_interfaces']} interfaces"
            missing_info = ""
            
            if stats['interfaces_failed'] > 0:
                missing_info += f", {stats['interfaces_failed']} failed"
            
            if stats['warnings']:
                missing_info += f", {len(stats['warnings'])} warnings"
            
            if stats['errors']:
                missing_info += f", {len(stats['errors'])} errors"
            
            if stats['skipped_sections']:
                missing_info += f", skipped: {', '.join(stats['skipped_sections'])}"
            
            print(f"  {status_icon} {router_name}: {status} - {interfaces_info}{missing_info}")
            
            # Print failed interface details
            if stats['failed_interfaces']:
                print(f"    Failed interfaces:")
                for failed_if in stats['failed_interfaces']:
                    print(f"      • {failed_if['name']}: {failed_if['error']}")
                    if failed_if.get('command'):
                        print(f"        Command: {failed_if['command']}")
                    if failed_if.get('kernel_error'):
                        print(f"        Kernel: {failed_if['kernel_error']}")
            
            # Print specific errors/warnings if verbose
            if self.verbose >= 2:
                for error in stats['errors']:
                    print(f"    ERROR: {error}")
                for warning in stats['warnings']:
                    print(f"    WARNING: {warning}")
                
    def _create_router_actual_interfaces(self, router_name: str):
        """Create ONLY the actual interfaces from raw facts."""
        interfaces = self.router_interfaces.get(router_name, [])
        
        if self.verbose >= 1:
            print(f"  → Creating {len(interfaces)} interfaces")
        
        for i, interface_config in enumerate(interfaces, 1):
            interface_name = interface_config['name']
            addresses = interface_config['addresses']
            
            # We'll print the result on one line after processing
            
            try:
                # Create unique veth pair names using compressed router codes (max 15 chars for Linux interface names)
                router_code = self.router_codes[router_name]  # e.g. r00, r01, r02
                
                # Create safe interface abbreviation for Linux interface names
                # Remove problematic characters and ensure uniqueness
                safe_name = re.sub(r'[^a-zA-Z0-9]', '', interface_name)  # Remove dots, hyphens, etc.
                
                if len(safe_name) <= 5:
                    interface_abbrev = safe_name  # eth0, wg0, etc. - use safe name
                else:
                    # For longer names, use first 4 chars + hash of full name for uniqueness
                    import hashlib
                    name_hash = hashlib.md5(interface_name.encode()).hexdigest()[:2]
                    interface_abbrev = safe_name[:3] + name_hash  # e.g. ens2f080 -> ens + 2-char hash
                    
                veth_router = f"{router_code}{interface_abbrev}r"  # e.g. r00eth0r, r02wlan0r (max 10 chars)
                veth_hidden = f"{router_code}{interface_abbrev}h"  # e.g. r00eth0h, r02wlan0h (max 10 chars)
                
                # Ensure interface names are valid (max 15 chars for Linux)
                if len(veth_router) > 15 or len(veth_hidden) > 15:
                    self.logger.warning(f"Interface names too long for {interface_name}: {veth_router}, {veth_hidden}")
                    # Truncate to fit Linux limits
                    veth_router = veth_router[:15]
                    veth_hidden = veth_hidden[:15]
                
                self.logger.debug(f"Creating veth pair {veth_router} <-> {veth_hidden} for {router_name}:{interface_name}")
                
                # Create veth pair in host namespace (required by Linux kernel)
                try:
                    self.run_cmd(f"ip link add {veth_router} type veth peer name {veth_hidden}", log_cmd=(self.verbose >= 3))
                    if self.verbose >= 2:
                        print(f"      → Created veth pair {veth_router} <-> {veth_hidden}")
                except subprocess.CalledProcessError as e:
                    error_msg = f"Failed to create veth pair {veth_router}/{veth_hidden}"
                    
                    # Track detailed failure info
                    failed_interface = {
                        'name': interface_name,
                        'error': error_msg,
                        'command': f"ip link add {veth_router} type veth peer name {veth_hidden}",
                        'kernel_error': str(e.stderr) if hasattr(e, 'stderr') and e.stderr else str(e)
                    }
                    self.router_stats[router_name]['failed_interfaces'].append(failed_interface)
                    self.router_stats[router_name]['interfaces_failed'] += 1
                    
                    if self.verbose >= 1:
                        print(f"    ✗ {interface_name}: {error_msg}")
                    continue
                
                # Move router end to router namespace
                try:
                    self.run_cmd(f"ip link set {veth_router} netns {router_name}", log_cmd=(self.verbose >= 3))
                    if self.verbose >= 2:
                        print(f"      → Moved {veth_router} to namespace {router_name}")
                except subprocess.CalledProcessError as e:
                    # Clean up the veth pair from host namespace
                    self.run_cmd(f"ip link del {veth_router}", check=False)
                    error_msg = f"Failed to move {veth_router} to namespace {router_name}"
                    
                    # Track detailed failure info
                    failed_interface = {
                        'name': interface_name,
                        'error': error_msg,
                        'command': f"ip link set {veth_router} netns {router_name}",
                        'kernel_error': str(e.stderr) if hasattr(e, 'stderr') and e.stderr else str(e)
                    }
                    self.router_stats[router_name]['failed_interfaces'].append(failed_interface)
                    self.router_stats[router_name]['interfaces_failed'] += 1
                    
                    if self.verbose >= 1:
                        print(f"    ✗ {interface_name}: {error_msg}")
                    continue
                
                # Move hidden end to hidden infrastructure namespace
                try:
                    self.run_cmd(f"ip link set {veth_hidden} netns {self.hidden_ns}", log_cmd=(self.verbose >= 3))
                    if self.verbose >= 2:
                        print(f"      → Moved {veth_hidden} to hidden namespace")
                except subprocess.CalledProcessError as e:
                    # Clean up the stranded router interface
                    self.run_cmd(f"ip netns exec {router_name} ip link del {veth_router}", check=False)
                    error_msg = f"Failed to move {veth_hidden} to hidden namespace"
                    
                    # Track detailed failure info
                    failed_interface = {
                        'name': interface_name,
                        'error': error_msg,
                        'command': f"ip link set {veth_hidden} netns {self.hidden_ns}",
                        'kernel_error': str(e.stderr) if hasattr(e, 'stderr') and e.stderr else str(e)
                    }
                    self.router_stats[router_name]['failed_interfaces'].append(failed_interface)
                    self.router_stats[router_name]['interfaces_failed'] += 1
                    
                    if self.verbose >= 1:
                        print(f"    ✗ {interface_name}: {error_msg}")
                    continue
                
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
                    self.run_cmd(f"ip link set {veth_router} name {interface_name}", router_name, log_cmd=(self.verbose >= 3))
                    if self.verbose >= 2:
                        print(f"      → Renamed to {interface_name}")
                except subprocess.CalledProcessError as e:
                    error_msg = f"Failed to rename {veth_router} to {interface_name}"
                    
                    # Track detailed failure info
                    failed_interface = {
                        'name': interface_name,
                        'error': error_msg,
                        'command': f"ip netns exec {router_name} ip link set {veth_router} name {interface_name}",
                        'kernel_error': str(e.stderr) if hasattr(e, 'stderr') and e.stderr else str(e)
                    }
                    self.router_stats[router_name]['failed_interfaces'].append(failed_interface)
                    self.router_stats[router_name]['interfaces_failed'] += 1
                    
                    if self.verbose >= 1:
                        print(f"    ✗ {interface_name}: {error_msg}")
                    continue
                
                # Configure IP addresses on router interface with proper broadcast addresses
                ip_success = 0
                applied_addresses = []
                for addr_info in addresses:
                    try:
                        # Build proper ip addr add command with broadcast address
                        cmd_parts = ["ip", "addr", "add", addr_info['ip'], "dev", interface_name]
                        
                        # Add broadcast address if available
                        if addr_info.get('broadcast'):
                            cmd_parts.extend(["broadcast", addr_info['broadcast']])
                        
                        # Add scope if not global (global is default)
                        if addr_info.get('scope') and addr_info['scope'] != 'global':
                            cmd_parts.extend(["scope", addr_info['scope']])
                        
                        # Add secondary flag if needed
                        if addr_info.get('secondary'):
                            cmd_parts.append("secondary")
                        
                        cmd = " ".join(cmd_parts)
                        self.run_cmd(cmd, router_name, log_cmd=(self.verbose >= 3))
                        ip_success += 1
                        applied_addresses.append(addr_info['ip'])
                        if self.verbose >= 2:
                            brd_info = f" brd {addr_info['broadcast']}" if addr_info.get('broadcast') else ""
                            print(f"      → Added IP {addr_info['ip']}{brd_info}")
                    except subprocess.CalledProcessError as e:
                        error_msg = f"Failed to add IP {addr_info['ip']}"
                        self.router_stats[router_name]['warnings'].append(error_msg)
                        if self.verbose >= 1:
                            print(f"      ⚠ IP add failed: {addr_info['ip']}")
                
                # Set interface state based on raw facts (UP/DOWN)
                should_be_up = interface_config.get('should_be_up', True)
                if should_be_up:
                    try:
                        self.run_cmd(f"ip link set {interface_name} up", router_name, log_cmd=(self.verbose >= 3))
                        if self.verbose >= 2:
                            print(f"      → Interface UP")
                    except subprocess.CalledProcessError as e:
                        error_msg = f"Failed to bring up interface {interface_name}"
                        self.router_stats[router_name]['warnings'].append(error_msg)
                        if self.verbose >= 1:
                            print(f"      ⚠ Failed to bring up interface")
                else:
                    # Keep interface DOWN as per raw facts
                    if self.verbose >= 2:
                        print(f"      → Interface DOWN (as per raw facts)")
                    # Note: interfaces are created DOWN by default, so no action needed
                
                # Bring up hidden interface
                try:
                    self.run_cmd(f"ip link set {veth_hidden} up", self.hidden_ns, log_cmd=(self.verbose >= 3))
                    if self.verbose >= 2:
                        print(f"      → Hidden interface up")
                except subprocess.CalledProcessError as e:
                    error_msg = f"Failed to bring up hidden interface {veth_hidden}"
                    self.router_stats[router_name]['warnings'].append(error_msg)
                    if self.verbose >= 2:
                        print(f"      ⚠ Hidden interface failed")
                
                # Mark interface as successfully created
                self.router_stats[router_name]['interfaces_created'] += 1
                if self.verbose >= 1:
                    ip_info = f" ({', '.join(applied_addresses)})" if applied_addresses else " (no IPs)"
                    if ip_success < len(addresses):
                        ip_info += f" [{ip_success}/{len(addresses)} IPs]"
                    print(f"    ✓ {interface_name}{ip_info}")
                
            except Exception as e:
                # Any unhandled exception in interface creation
                error_msg = f"Unexpected error creating interface {interface_name}"
                self.router_stats[router_name]['errors'].append(error_msg)
                self.router_stats[router_name]['interfaces_failed'] += 1
                
                # Track detailed failure info
                failed_interface = {
                    'name': interface_name,
                    'error': error_msg,
                    'command': 'Interface creation process',
                    'kernel_error': str(e)
                }
                self.router_stats[router_name]['failed_interfaces'].append(failed_interface)
                
                if self.verbose >= 1:
                    print(f"    ✗ {interface_name}: {error_msg}")
                continue  # Continue with next interface instead of failing completely
                
    def connect_routers_to_infrastructure(self):
        """Connect router interfaces to appropriate bridges in hidden infrastructure."""
        if self.verbose >= 1:
            print("\n=== Connecting routers to infrastructure ===")
        
        for router_name, interfaces in self.router_interfaces.items():
            for interface_config in interfaces:
                interface_name = interface_config['name']
                addresses = interface_config['addresses']
                
                # Find which bridge this interface should connect to
                for addr_info in addresses:
                    try:
                        import ipaddress
                        # Extract IP address from the address info dictionary
                        ip_addr = addr_info['ip'] if isinstance(addr_info, dict) else addr_info
                        network = ipaddress.IPv4Network(ip_addr, strict=False)
                        subnet = str(network)
                        bridge_name = self._generate_bridge_name(subnet)
                        
                        # Connect hidden interface to bridge
                        router_code = self.router_codes[router_name]
                        
                        # Use SAME interface abbreviation logic as in interface creation
                        safe_name = re.sub(r'[^a-zA-Z0-9]', '', interface_name)  # Remove dots, hyphens, etc.
                        
                        if len(safe_name) <= 5:
                            interface_abbrev = safe_name  # eth0, wg0, etc. - use safe name
                        else:
                            # For longer names, use first 4 chars + hash of full name for uniqueness
                            import hashlib
                            name_hash = hashlib.md5(interface_name.encode()).hexdigest()[:2]
                            interface_abbrev = safe_name[:3] + name_hash  # e.g. ens2f080 -> ens + 2-char hash
                        
                        veth_hidden = f"{router_code}{interface_abbrev}h"
                        
                        try:
                            self.run_cmd(f"ip link set {veth_hidden} master {bridge_name}", self.hidden_ns)
                            if self.verbose >= 2:
                                print(f"    ✓ Connected {interface_name} to {bridge_name}")
                        except subprocess.CalledProcessError as e:
                            if self.verbose >= 1:
                                print(f"    ✗ Bridge connection failed: {e}")
                            self.logger.error(f"CRITICAL: Failed to connect {veth_hidden} to {bridge_name}: {e}")
                            raise Exception(f"Bridge connection failed for {router_name}:{interface_name}")
                            
                    except Exception as e:
                        self.logger.warning(f"Failed to process IP {addr_info}: {e}")
                        continue
                        
    def apply_complete_configurations(self):
        """Apply complete router configurations from raw facts."""
        if self.verbose >= 1:
            print("\n=== Applying router configurations ===")
        
        for i, (router_name, router_facts) in enumerate(self.routers.items(), 1):
            if self.verbose >= 1:
                print(f"\n[{i}/{len(self.routers)}] Configuring {router_name}")
            
            stats = self.router_stats[router_name]
            
            # Only proceed if interfaces were 100% successful
            if not stats['interfaces_success']:
                if self.verbose >= 1:
                    print(f"  ⚠ Skipping configuration due to interface failures")
                stats['skipped_sections'] = ['routing', 'ipsets', 'iptables']
                continue
            
            try:
                # Apply routing configuration
                if self.verbose >= 1:
                    print(f"  → Applying routing configuration")
                self._apply_routing_configuration(router_name, router_facts)
                
                # Only proceed with ipsets if routing was 100% successful
                if stats['routing_success']:
                    if self.verbose >= 1:
                        print(f"  → Applying ipsets configuration")
                    self._apply_ipsets_configuration(router_name, router_facts)
                    
                    # Only proceed with iptables if ipsets was 100% successful
                    if stats['ipsets_success']:
                        if self.verbose >= 1:
                            print(f"  → Applying iptables configuration")
                        self._apply_iptables_configuration(router_name, router_facts)
                    else:
                        if self.verbose >= 1:
                            print(f"  ⚠ Skipping iptables due to ipsets failures")
                        stats['skipped_sections'].append('iptables')
                else:
                    if self.verbose >= 1:
                        print(f"  ⚠ Skipping ipsets and iptables due to routing failures")
                    stats['skipped_sections'].extend(['ipsets', 'iptables'])
                
                if self.verbose >= 2:
                    print(f"  ✓ Configuration applied")
                
            except Exception as e:
                if self.verbose >= 1:
                    print(f"  ✗ Configuration failed: {e}")
                # Continue with other routers
                
    def _apply_routing_configuration(self, router_name: str, router_facts: RouterRawFacts):
        """Apply routing tables and policy rules (policy routing conditional)."""
        stats = self.router_stats[router_name]
        stats['routing_applied'] = True
        
        routes_applied = 0
        rules_applied = 0
        tables_applied = 0
        applied_tables = []  # Track table names for output
        errors = []
        
        try:
            # Always apply main routing table
            routing_section = router_facts.get_section('routing_table_main')
            if routing_section:
                route_count = self._apply_routes(router_name, routing_section.content, 'main')
                routes_applied += route_count
                tables_applied += 1
                applied_tables.append('main')
            
            # Apply policy rules and additional routing tables
            policy_section = router_facts.get_section('policy_rules')
            if policy_section:
                rule_count = self._apply_policy_rules(router_name, policy_section.content, router_facts)
                rules_applied += rule_count
            
            # Apply additional routing tables
            for section_name, section in router_facts.sections.items():
                if section_name.startswith('routing_table_') and section_name != 'routing_table_main':
                    table_identifier = section_name.replace('routing_table_', '')
                    
                    # Check if table_identifier is already a numeric ID
                    if table_identifier.isdigit():
                        table_id = table_identifier
                    else:
                        # Look up table name in rt_tables mapping
                        table_id = self._get_table_id(table_identifier, router_facts)
                    
                    if table_id:
                        route_count = self._apply_routes(router_name, section.content, table_id)
                        routes_applied += route_count
                        tables_applied += 1
                        
                        # Find table name for output
                        rt_tables_section = router_facts.get_section('rt_tables')
                        table_name = table_identifier
                        if table_identifier.isdigit() and rt_tables_section:
                            # Look up actual table name from rt_tables
                            for line in rt_tables_section.content.split('\n'):
                                line = line.strip()
                                if not line or line.startswith('#'):
                                    continue
                                parts = line.split()
                                if len(parts) == 2 and parts[0] == table_id:
                                    table_name = parts[1]
                                    break
                        applied_tables.append(f"{table_name}({table_id})")
            
            # Clean up duplicate kernel routes (remove auto-generated routes if explicit metric routes exist)
            removed_duplicates = self._remove_duplicate_kernel_routes(router_name, router_facts)
            
            # Mark as successful
            stats['routing_success'] = True
            
            if self.verbose >= 1:
                summary = f"    ✓ routing: {routes_applied} routes"
                if rules_applied > 0:
                    summary += f", {rules_applied} rules"
                if applied_tables:
                    summary += f", {len(applied_tables)} tables ({', '.join(applied_tables)})"
                print(summary)
                
        except Exception as e:
            stats['routing_success'] = False
            error_msg = str(e)
            stats['errors'].append(f"Routing configuration failed: {error_msg}")
            
            if self.verbose >= 1:
                print(f"    ✗ routing: {error_msg}")
            raise  # Re-raise to be caught by caller
    
    def _get_table_id(self, table_name: str, router_facts: RouterRawFacts) -> Optional[str]:
        """Get numeric table ID for named table from router's rt_tables section."""
        rt_tables_section = router_facts.get_section('rt_tables')
        if not rt_tables_section:
            return None
            
        # Parse rt_tables content to build table_name -> table_id mapping
        table_mapping = {}
        
        for line in rt_tables_section.content.split('\n'):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
                
            # Split on whitespace - expect exactly 2 parts: <table_id> <table_name>
            parts = line.split()
            if len(parts) == 2:
                table_id, name = parts
                table_mapping[name] = table_id
                
        return table_mapping.get(table_name)
        
    def _apply_routes(self, router_name: str, routes_content: str, table: str):
        """Apply routing table entries."""
        if not routes_content.strip():
            return 0
        
        routes_count = 0
        
        # Handle embedded newlines and escaped tabs in content
        routes_content = routes_content.replace('\\n', '\n').replace('\\t', ' ')
        
        for line in routes_content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Additional cleanup for escaped characters
            line = line.replace('\\t', ' ').replace('\\', '')
            
            # Normalize multiple spaces to single spaces
            import re
            line = re.sub(r'\s+', ' ', line)
            
            # Skip auto-generated direct network routes WITHOUT explicit metrics
            # Kernel routes with explicit metrics should be applied as they indicate specific configuration
            if 'proto kernel scope link' in line and 'metric' not in line:
                self.logger.debug(f"Skipping auto-generated route without metric: {line}")
                continue
            
            # Apply route
            if table != 'main':
                cmd = f"ip route add table {table} {line}"
            else:
                cmd = f"ip route add {line}"
            
            try:
                self.run_cmd(cmd, router_name)
                routes_count += 1
                self.logger.debug(f"Added route: {line}")
            except subprocess.CalledProcessError as e:
                # Check if route already exists (expected for direct network routes)
                error_msg = str(e) + (e.stderr if e.stderr else "")
                if "File exists" in error_msg or "RTNETLINK answers: File exists" in error_msg:
                    self.logger.debug(f"Route already exists (expected): {line}")
                else:
                    self.logger.error(f"CRITICAL: Route add failed for {line}: {e}")
                    if e.stderr:
                        self.logger.error(f"Stderr: {e.stderr}")
                    raise Exception(f"Failed to add route: {line}")
            except Exception as e:
                self.logger.error(f"CRITICAL: Route add failed for {line}: {e}")
                raise Exception(f"Failed to add route: {line}")
        
        return routes_count
                
    def _apply_policy_rules(self, router_name: str, rules_content: str, router_facts: RouterRawFacts):
        """Apply policy routing rules."""
        if not rules_content.strip():
            return 0
        
        # Build table name to ID mapping from rt_tables
        table_name_to_id = {}
        rt_tables_section = router_facts.get_section('rt_tables')
        if rt_tables_section:
            for line in rt_tables_section.content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                if len(parts) == 2:
                    table_id, table_name = parts
                    table_name_to_id[table_name] = table_id
        
        rules_count = 0
        
        for line in rules_content.split('\n'):
            line = line.strip()
            # Skip empty lines, comments, and default system rules that are automatically created
            if (not line or line.startswith('#') or 
                line.startswith('0:') or 'lookup local' in line or
                line.startswith('32766:') and 'lookup main' in line or
                line.startswith('32767:') and 'lookup default' in line):
                continue
            
            # Parse rule and convert to ip rule add command
            rule_match = re.match(r'(\d+):\s*(.+)', line)
            if rule_match:
                priority = rule_match.group(1)
                rule_spec = rule_match.group(2)
                
                # Convert table names to IDs using dynamic mapping
                for table_name, table_id in table_name_to_id.items():
                    rule_spec = rule_spec.replace(f'lookup {table_name}', f'table {table_id}')
                
                cmd = f"ip rule add pref {priority} {rule_spec}"
                
                try:
                    self.run_cmd(cmd, router_name, check=False)
                    rules_count += 1
                    self.logger.debug(f"Added rule: {rule_spec}")
                except Exception as e:
                    self.logger.debug(f"Rule add failed (expected): {e}")
        
        return rules_count
    
    def _remove_duplicate_kernel_routes(self, router_name: str, router_facts: RouterRawFacts):
        """Remove duplicate kernel routes when explicit metric routes exist."""
        removed_count = 0
        
        # Get main routing table facts to identify routes with explicit metrics
        routing_section = router_facts.get_section('routing_table_main')
        if not routing_section:
            return removed_count
        
        # Parse routes from raw facts to find kernel routes with metrics
        explicit_metric_routes = []
        for line in routing_section.content.split('\n'):
            line = line.strip()
            if 'proto kernel scope link' in line and 'metric' in line:
                # Extract network and device from the route
                # Format: "10.128.9.0/24 dev ens1f0 proto kernel scope link src 10.128.9.60 metric 100"
                parts = line.split()
                if len(parts) >= 4:
                    network = parts[0]
                    device = None
                    for i, part in enumerate(parts):
                        if part == 'dev' and i + 1 < len(parts):
                            device = parts[i + 1]
                            break
                    
                    if network and device:
                        explicit_metric_routes.append((network, device))
                        self.logger.debug(f"Found explicit metric route: {network} dev {device}")
        
        # Remove duplicate auto-generated routes (those without metrics)
        for network, device in explicit_metric_routes:
            try:
                # Try to remove the auto-generated route (without metric)
                cmd = f"ip route del {network} dev {device} proto kernel scope link"
                result = self.run_cmd(cmd, router_name, check=False, log_cmd=(self.verbose >= 3))
                
                if result.returncode == 0:
                    removed_count += 1
                    self.logger.debug(f"Removed duplicate route: {network} dev {device}")
                else:
                    # Route might not exist or have different parameters, this is fine
                    self.logger.debug(f"No duplicate route to remove: {network} dev {device}")
                    
            except Exception as e:
                # Route removal failures are not critical, just log
                self.logger.debug(f"Failed to remove duplicate route {network} dev {device}: {e}")
        
        if removed_count > 0 and self.verbose >= 2:
            print(f"      → Removed {removed_count} duplicate kernel routes")
        
        return removed_count
                    
    def _apply_iptables_configuration(self, router_name: str, router_facts: RouterRawFacts):
        """Apply iptables configuration."""
        stats = self.router_stats[router_name]
        stats['iptables_applied'] = True
        
        try:
            iptables_save_section = router_facts.get_section('iptables_save')
            if iptables_save_section:
                success, rule_count = self._apply_iptables_save(router_name, iptables_save_section.content)
                if success:
                    stats['iptables_success'] = True
                    if self.verbose >= 1:
                        print(f"    ✓ iptables: {rule_count} rules applied")
                else:
                    if self.verbose >= 1:
                        print(f"    ✗ iptables: configuration failed")
                    raise Exception("Iptables configuration failed")
            else:
                stats['iptables_success'] = True  # No iptables to apply
                if self.verbose >= 1:
                    print(f"    ✓ iptables: no configuration")
        except Exception as e:
            stats['iptables_success'] = False
            stats['errors'].append(f"Iptables configuration failed: {str(e)}")
            raise
            
    def _apply_iptables_save(self, router_name: str, iptables_content: str):
        """Apply iptables configuration using iptables-restore."""
        if not iptables_content.strip():
            return True, 0
        
        # Count rules in the content (lines that don't start with # or :)
        rule_count = sum(1 for line in iptables_content.split('\n') 
                        if line.strip() and not line.startswith('#') and not line.startswith(':'))
        
        try:
            if router_name:
                full_cmd = f"ip netns exec {router_name} iptables-restore"
            else:
                full_cmd = "iptables-restore"
            
            self.logger.info(f"Applying iptables to {router_name}: {len(iptables_content)} chars")
            
            # Use subprocess.run to pass content directly via stdin (same as ipsets)
            result = subprocess.run(
                full_cmd.split(), input=iptables_content, text=True, 
                capture_output=True, check=False
            )
            
            if result.returncode != 0:
                self.logger.error(f"iptables-restore failed for {router_name}: {result.stderr}")
                return False, rule_count
            else:
                self.logger.debug(f"iptables-restore succeeded for {router_name}")
                return True, rule_count
            
        except Exception as e:
            self.logger.error(f"iptables restore failed for {router_name}: {e}")
            return False, rule_count
            
    def _apply_ipsets_configuration(self, router_name: str, router_facts: RouterRawFacts):
        """Apply ipsets configuration."""
        stats = self.router_stats[router_name]
        stats['ipsets_applied'] = True
        
        try:
            ipset_save_section = router_facts.get_section('ipset_save')
            if ipset_save_section:
                success, set_count, member_count = self._apply_ipset_save(router_name, ipset_save_section.content)
                if success:
                    stats['ipsets_success'] = True
                    if self.verbose >= 1:
                        print(f"    ✓ ipsets: {set_count} sets, {member_count} members")
                else:
                    if self.verbose >= 1:
                        print(f"    ✗ ipsets: configuration failed")
                    raise Exception("Ipsets configuration failed")
            else:
                stats['ipsets_success'] = True  # No ipsets to apply
                if self.verbose >= 1:
                    print(f"    ✓ ipsets: no configuration")
        except Exception as e:
            stats['ipsets_success'] = False
            stats['errors'].append(f"Ipsets configuration failed: {str(e)}")
            raise
            
    def _apply_ipset_save(self, router_name: str, ipset_content: str):
        """Apply ipset configuration using ipset restore."""
        if not ipset_content.strip():
            return True, 0, 0
        
        # Count creates (sets) and adds (members)
        set_count = ipset_content.count('create')
        member_count = ipset_content.count('add')
        
        try:
            if router_name:
                full_cmd = f"ip netns exec {router_name} ipset restore"
            else:
                full_cmd = "ipset restore"
            
            self.logger.info(f"Applying ipsets to {router_name}: {len(ipset_content)} chars, {ipset_content.count('create')} creates, {ipset_content.count('add')} adds")
            
            # Use subprocess.PIPE to pass content directly via stdin
            result = subprocess.run(
                full_cmd.split(), input=ipset_content, text=True, 
                capture_output=True, check=False
            )
            
            if result.returncode != 0:
                self.logger.error(f"ipset restore failed for {router_name}: {result.stderr}")
                self.logger.error(f"Return code: {result.returncode}")
                if result.stdout:
                    self.logger.error(f"Stdout: {result.stdout}")
                return False, set_count, member_count
            else:
                self.logger.info(f"ipset restore succeeded for {router_name}")
                return True, set_count, member_count
            
        except Exception as e:
            self.logger.error(f"ipset restore failed (exception) for {router_name}: {e}")
            return False, set_count, member_count
            
    def cleanup_network(self):
        """Clean up all created network resources."""
        self.logger.info("Cleaning up hidden mesh network")
        
        # Clean up ipsets in each namespace before removing namespaces
        for ns in list(self.created_namespaces):
            try:
                self.run_cmd(f"ipset flush", ns, check=False)
                self.run_cmd(f"ipset destroy", ns, check=False)
            except:
                pass
        
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
                       help='Increase verbosity (-v for info, -vv for debug, -vvv for commands)')
    parser.add_argument('--cleanup', action='store_true',
                       help='Clean up existing setup and exit')
    parser.add_argument('--verify', action='store_true',
                       help='Verify setup after creation')
    parser.add_argument('--limit', type=str, default=None,
                       help='Limit routers to create (supports glob patterns, e.g. "br-core", "*core*", "hq-*")')
    
    args = parser.parse_args()
    
    if os.geteuid() != 0:
        print("Error: This script must be run as root (use sudo)")
        return 1
    
    setup = HiddenMeshNetworkSetup(verbose=args.verbose, limit_pattern=args.limit)
    
    try:
        if args.cleanup:
            setup.cleanup_network()
            print("Network cleanup completed")
            return 0
        
        # Load facts from raw facts only
        setup.load_raw_facts_only()
        
        # Set up hidden mesh network
        success = setup.setup_hidden_mesh_network()
        if not success:
            print("Network setup failed!")
            return 1
        
        # Verify if requested
        if args.verify:
            if not setup.verify_setup():
                return 1
        
        if args.verbose == 0:
            print(f"Hidden mesh network setup complete with {len(setup.routers)} routers")
            print("Use 'sudo make netshow ROUTER=<name> FUNC=<function>' to check status")
        
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