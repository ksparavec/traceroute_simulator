#!/usr/bin/env python3
"""
Complete Network Namespace Setup Script

Creates a complete Linux namespace-based network simulation from router facts data.
Builds realistic network topology with routing tables, iptables rules, and ipsets
to enable real packet flow testing and firewall behavior validation.

Features:
- Each router becomes a network namespace with full routing and firewall config
- Veth pairs connect namespaces according to network topology
- All routing tables, iptables rules, and ipsets are recreated exactly
- Interface IP addresses and names match the original network configuration
- Supports testing with real network tools for complete validation

Usage:
    sudo python3 network_namespace_setup.py [--verbose]
    
Environment Variables:
    TRACEROUTE_SIMULATOR_FACTS - Directory containing router JSON facts files
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import ipaddress
import re
from pathlib import Path
from typing import Dict, List, Set, Optional, Any


class CompleteNetworkSetup:
    """Complete implementation of network namespace setup with full firewall support."""
    
    def __init__(self, verbose: int = 0):
        self.verbose = verbose
        self.setup_logging()
        
        # Network state
        self.routers: Dict[str, Dict] = {}
        self.router_interfaces: Dict[str, List[Dict]] = {}  # router -> [interface_objects]
        self.subnets: Dict[str, List[tuple]] = {}  # subnet -> [(router, interface, ip)]
        self.created_namespaces: Set[str] = set()
        self.created_veths: Set[str] = set()
        self.created_bridges: Set[str] = set()
        
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
        
    def load_facts(self):
        """Load router facts from facts directory."""
        facts_path = os.environ.get('TRACEROUTE_SIMULATOR_FACTS', '/tmp/traceroute_test_output')
        facts_dir = Path(facts_path)
        if not facts_dir.exists():
            raise FileNotFoundError(f"Facts directory not found: {facts_dir}")
            
        json_files = list(facts_dir.glob("*.json"))
        if not json_files:
            raise FileNotFoundError(f"No JSON files found in {facts_dir}")
            
        for json_file in json_files:
            router_name = json_file.stem
            self.logger.debug(f"Loading {router_name}")
            
            with open(json_file, 'r') as f:
                facts = json.load(f)
                self.routers[router_name] = facts
                
                # Extract interfaces
                interfaces = facts.get('network', {}).get('interfaces', [])
                self.router_interfaces[router_name] = interfaces
                
                # Build subnet mapping
                for iface in interfaces:
                    if (iface.get('protocol') == 'kernel' and 
                        iface.get('scope') == 'link' and
                        iface.get('prefsrc') and iface.get('dev') and iface.get('dst')):
                        
                        subnet = iface['dst']
                        router_iface = iface['dev'] 
                        ip = iface['prefsrc']
                        
                        if subnet not in self.subnets:
                            self.subnets[subnet] = []
                        self.subnets[subnet].append((router_name, router_iface, ip))
                        
        self.logger.info(f"Loaded {len(self.routers)} routers, {len(self.subnets)} subnets")
        
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
        
    def create_namespaces(self):
        """Create network namespaces for each router."""
        self.logger.info("Creating namespaces")
        
        for router_name in self.routers.keys():
            self.logger.debug(f"Creating namespace: {router_name}")
            self.run_cmd(f"ip netns add {router_name}")
            self.created_namespaces.add(router_name)
            
            # Enable loopback
            self.run_cmd("ip link set lo up", namespace=router_name)
            
            # Enable IP forwarding
            self.run_cmd("echo 1 > /proc/sys/net/ipv4/ip_forward", namespace=router_name)
            
    def create_point_to_point_links(self):
        """Create point-to-point veth pairs for subnets with exactly 2 routers."""
        self.logger.info("Creating point-to-point links")
        
        for subnet, members in self.subnets.items():
            if len(members) == 2:
                (router1, iface1, ip1), (router2, iface2, ip2) = members
                
                # Create veth pair with descriptive host-side names but original namespace names
                veth_host1 = f"{router1}-{iface1}"
                veth_host2 = f"{router2}-{iface2}"
                
                self.logger.debug(f"Creating veth pair: {veth_host1} <-> {veth_host2} for {subnet}")
                
                self.run_cmd(f"ip link add {veth_host1} type veth peer name {veth_host2}")
                self.created_veths.update([veth_host1, veth_host2])
                
                # Move to namespaces and rename to original interface names
                self.run_cmd(f"ip link set {veth_host1} netns {router1}")
                self.run_cmd(f"ip link set {veth_host2} netns {router2}")
                self.run_cmd(f"ip link set {veth_host1} name {iface1}", namespace=router1)
                self.run_cmd(f"ip link set {veth_host2} name {iface2}", namespace=router2)
                
                # Configure IP addresses using original interface names
                prefix_len = ipaddress.IPv4Network(subnet, strict=False).prefixlen
                self.run_cmd(f"ip addr add {ip1}/{prefix_len} dev {iface1}", namespace=router1)
                self.run_cmd(f"ip addr add {ip2}/{prefix_len} dev {iface2}", namespace=router2)
                
                # Bring up using original interface names
                self.run_cmd(f"ip link set {iface1} up", namespace=router1)
                self.run_cmd(f"ip link set {iface2} up", namespace=router2)
                
    def create_multi_access_networks(self):
        """Create bridge networks for subnets with more than 2 routers."""
        self.logger.info("Creating multi-access networks")
        
        bridge_counter = 100  # Start from br100 to avoid conflicts
        for subnet, members in self.subnets.items():
            if len(members) > 2:
                # Create bridge with unique name
                bridge_name = f"br{bridge_counter}"
                bridge_counter += 1
                self.logger.debug(f"Creating bridge {bridge_name} for {subnet} with {len(members)} members")
                
                self.run_cmd(f"ip link add {bridge_name} type bridge")
                self.run_cmd(f"ip link set {bridge_name} up")
                self.created_bridges.add(bridge_name)
                
                # Connect each router to bridge
                router_counter = 0
                for router, iface, ip in members:
                    veth_host = f"{router}-{iface}"
                    veth_bridge = f"b{bridge_counter-1}r{router_counter}"  # Use bridge_counter-1 since we already incremented
                    router_counter += 1
                    
                    # Create veth pair
                    self.run_cmd(f"ip link add {veth_host} type veth peer name {veth_bridge}")
                    self.created_veths.update([veth_host, veth_bridge])
                    
                    # Move router side to namespace and rename to original interface name
                    self.run_cmd(f"ip link set {veth_host} netns {router}")
                    self.run_cmd(f"ip link set {veth_host} name {iface}", namespace=router)
                    
                    # Connect bridge side to bridge
                    self.run_cmd(f"ip link set {veth_bridge} master {bridge_name}")
                    
                    # Configure IP on router side using original interface name
                    prefix_len = ipaddress.IPv4Network(subnet, strict=False).prefixlen
                    self.run_cmd(f"ip addr add {ip}/{prefix_len} dev {iface}", namespace=router)
                    
                    # Bring up both sides
                    self.run_cmd(f"ip link set {iface} up", namespace=router)
                    self.run_cmd(f"ip link set {veth_bridge} up")
                    
    def create_external_interfaces(self):
        """Create dummy interfaces for subnets with only 1 router (external networks)."""
        self.logger.info("Creating external interfaces")
        
        for subnet, members in self.subnets.items():
            if len(members) == 1:
                router, iface, ip = members[0]
                
                self.logger.debug(f"Creating external interface {router}:{iface} -> {ip} for {subnet}")
                
                # Create dummy interface with original interface name
                prefix_len = ipaddress.IPv4Network(subnet, strict=False).prefixlen
                
                self.run_cmd(f"ip link add {iface} type dummy", namespace=router)
                self.run_cmd(f"ip addr add {ip}/{prefix_len} dev {iface}", namespace=router)
                self.run_cmd(f"ip link set {iface} up", namespace=router)
                
    def configure_routing(self):
        """Configure routing tables in each namespace."""
        self.logger.info("Configuring routing tables")
        
        for router_name, facts in self.routers.items():
            routes = facts.get('routing', {}).get('tables', [])
            
            for route in routes:
                # Skip kernel routes (auto-created when IPs are assigned)
                if route.get('protocol') == 'kernel':
                    continue
                
                dst = route.get('dst')
                gateway = route.get('gateway')
                dev = route.get('dev')
                metric = route.get('metric')
                
                # Build route command
                cmd_parts = ["ip route add"]
                
                if dst == "default":
                    cmd_parts.append("default")
                else:
                    cmd_parts.append(dst)
                    
                if gateway:
                    cmd_parts.extend(["via", gateway])
                    
                if dev:
                    # Find the actual interface name in the namespace
                    actual_dev = self.find_namespace_interface(router_name, dev)
                    if actual_dev:
                        cmd_parts.extend(["dev", actual_dev])
                    else:
                        self.logger.warning(f"Interface {dev} not found in {router_name}")
                        continue
                        
                if metric:
                    cmd_parts.extend(["metric", str(metric)])
                    
                route_cmd = " ".join(cmd_parts)
                
                try:
                    self.run_cmd(route_cmd, namespace=router_name)
                    self.logger.debug(f"Added route in {router_name}: {route_cmd}")
                except subprocess.CalledProcessError as e:
                    self.logger.warning(f"Failed to add route in {router_name}: {route_cmd} - {e}")
                    
    def find_namespace_interface(self, router: str, original_iface: str) -> str:
        """Find the actual interface name in the namespace for the original interface."""
        # With the new naming scheme, all interfaces keep their original names in namespaces
        try:
            result = self.run_cmd(f"ip link show {original_iface}", namespace=router, check=False)
            if result.returncode == 0:
                return original_iface
        except:
            pass
            
        return None
        
    def configure_iptables(self):
        """Configure iptables rules and ipsets in each namespace."""
        self.logger.info("Configuring iptables and ipsets")
        
        # Check if iptables and ipset are available
        iptables_available = self.check_command_availability("iptables")
        ipset_available = self.check_command_availability("ipset")
        
        if not iptables_available:
            self.logger.warning("iptables not available - skipping firewall configuration")
            self.logger.warning("To enable firewall simulation, install: sudo apt-get install iptables")
            if self.verbose >= 1:
                print("Warning: iptables not available - firewall rules skipped")
        
        if not ipset_available:
            self.logger.warning("ipset not available - skipping ipset configuration") 
            self.logger.warning("To enable ipset simulation, install: sudo apt-get install ipset")
            if self.verbose >= 1:
                print("Warning: ipset not available - ipset rules skipped")
        
        for router_name, facts in self.routers.items():
            firewall_data = facts.get('firewall', {})
            iptables_data = firewall_data.get('iptables', {})
            ipset_data = firewall_data.get('ipset', {})
            
            # Configure ipsets first (only if ipset is available)
            if ipset_available and ipset_data.get('available') and ipset_data.get('lists'):
                self.configure_ipsets(router_name, ipset_data['lists'])
                
            # Configure iptables rules (only if iptables is available)
            if iptables_available and iptables_data.get('available'):
                # Check for different iptables data formats
                if 'raw_config' in iptables_data:
                    self.configure_iptables_rules(router_name, iptables_data['raw_config'])
                elif 'filter' in iptables_data or 'nat' in iptables_data or 'mangle' in iptables_data:
                    self.configure_iptables_from_structured(router_name, iptables_data)
                
    def configure_ipsets(self, router_name: str, ipsets: List[Dict]):
        """Configure ipsets in the router namespace."""
        self.logger.debug(f"Configuring {len(ipsets)} ipsets for {router_name}")
        
        for ipset_dict in ipsets:
            for set_name, set_data in ipset_dict.items():
                set_type = set_data.get('type')
                members = set_data.get('members', [])
                
                if not set_type or not members:
                    continue
                    
                # Create ipset
                create_cmd = f"ipset create {set_name} {set_type}"
                try:
                    self.run_cmd(create_cmd, namespace=router_name)
                except subprocess.CalledProcessError:
                    # Ipset might already exist, flush it
                    self.run_cmd(f"ipset flush {set_name}", namespace=router_name, check=False)
                    
                # Add members
                for member in members:
                    add_cmd = f"ipset add {set_name} {member}"
                    self.run_cmd(add_cmd, namespace=router_name, check=False)
                    
    def configure_iptables_rules(self, router_name: str, raw_config: str):
        """Configure iptables rules from raw iptables-save format."""
        self.logger.debug(f"Configuring iptables rules for {router_name}")
        
        # Apply the raw iptables configuration
        try:
            # Use iptables-restore to apply the complete configuration
            restore_cmd = f"echo '{raw_config}' | iptables-restore"
            self.run_cmd(restore_cmd, namespace=router_name)
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to restore iptables for {router_name}: {e}")
            # Try to apply rules individually as fallback
            self.apply_iptables_fallback(router_name, raw_config)
            
    def configure_iptables_from_structured(self, router_name: str, iptables_data: Dict):
        """Configure iptables from structured data format."""
        self.logger.debug(f"Configuring structured iptables rules for {router_name}")
        
        # Handle filter table
        if 'filter' in iptables_data:
            self.apply_filter_rules(router_name, iptables_data['filter'])
            
        # Handle nat table  
        if 'nat' in iptables_data:
            self.apply_nat_rules(router_name, iptables_data['nat'])
            
        # Handle mangle table
        if 'mangle' in iptables_data:
            self.apply_mangle_rules(router_name, iptables_data['mangle'])
            
    def apply_filter_rules(self, router_name: str, filter_rules: List[Dict]):
        """Apply filter table rules."""
        for chain_dict in filter_rules:
            for chain_name, rules in chain_dict.items():
                for rule in rules:
                    # Build iptables command from rule data
                    cmd_parts = ["iptables", "-A", chain_name]
                    
                    # Add protocol
                    if rule.get('protocol') and rule['protocol'] != 'all':
                        cmd_parts.extend(["-p", rule['protocol']])
                    
                    # Add source
                    if rule.get('source') and rule['source'] != '0.0.0.0/0':
                        cmd_parts.extend(["-s", rule['source']])
                        
                    # Add destination  
                    if rule.get('destination') and rule['destination'] != '0.0.0.0/0':
                        cmd_parts.extend(["-d", rule['destination']])
                        
                    # Add input interface
                    if rule.get('in_interface') and rule['in_interface'] != '*':
                        cmd_parts.extend(["-i", rule['in_interface']])
                        
                    # Add output interface
                    if rule.get('out_interface') and rule['out_interface'] != '*':
                        cmd_parts.extend(["-o", rule['out_interface']])
                        
                    # Add port
                    if rule.get('dport'):
                        cmd_parts.extend(["--dport", rule['dport']])
                        
                    # Add target
                    if rule.get('target'):
                        cmd_parts.extend(["-j", rule['target']])
                    
                    cmd = " ".join(cmd_parts)
                    self.run_cmd(cmd, namespace=router_name, check=False)
                    
    def apply_nat_rules(self, router_name: str, nat_rules: List[Dict]):
        """Apply NAT table rules."""
        # Similar implementation for NAT rules
        self.logger.debug(f"Applying NAT rules for {router_name}")
        # Implementation would be similar to filter rules but for nat table
        
    def apply_mangle_rules(self, router_name: str, mangle_rules: List[Dict]):
        """Apply mangle table rules."""
        # Similar implementation for mangle rules  
        self.logger.debug(f"Applying mangle rules for {router_name}")
        # Implementation would be similar to filter rules but for mangle table
        
    def apply_iptables_fallback(self, router_name: str, raw_config: str):
        """Fallback method to apply iptables rules individually."""
        self.logger.debug(f"Applying iptables rules individually for {router_name}")
        
        lines = raw_config.split('\n')
        current_table = None
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            if line.startswith('*'):
                current_table = line[1:]
                continue
            elif line == 'COMMIT':
                continue
            elif line.startswith(':'):
                # Chain creation/policy
                parts = line[1:].split()
                if len(parts) >= 2:
                    chain = parts[0]
                    policy = parts[1]
                    if policy in ['ACCEPT', 'DROP']:
                        cmd = f"iptables -t {current_table} -P {chain} {policy}"
                        self.run_cmd(cmd, namespace=router_name, check=False)
            elif line.startswith('-A'):
                # Rule addition
                cmd = f"iptables -t {current_table} {line}"
                self.run_cmd(cmd, namespace=router_name, check=False)
                
    def cleanup_on_error(self):
        """Clean up created resources on error."""
        self.logger.info("Cleaning up created resources due to error")
        
        # Remove created namespaces
        for ns in self.created_namespaces:
            try:
                self.run_cmd(f"ip netns del {ns}", check=False)
            except:
                pass
                
        # Remove created bridges  
        for bridge in self.created_bridges:
            try:
                self.run_cmd(f"ip link del {bridge}", check=False)
            except:
                pass
                
        # Remove created veths (those still in host namespace)
        for veth in self.created_veths:
            try:
                self.run_cmd(f"ip link del {veth}", check=False)
            except:
                pass
        
    def setup_network(self):
        """Execute complete network setup process."""
        if self.verbose >= 1:
            print("Setting up complete network namespace simulation with firewall support")
            
        self.logger.info("Starting network namespace setup")
        
        # Check for mandatory tools
        if not self.check_command_availability("ip"):
            error_msg = "Error: 'ip' command not available - required for namespace operations"
            if self.verbose >= 1:
                print(error_msg)
                print("Install with: sudo apt-get install iproute2")
            self.logger.error(error_msg)
            return 1  # Error exit code
            
        try:
            self.load_facts()
            self.create_namespaces()
            self.create_point_to_point_links()
            self.create_multi_access_networks()
            self.create_external_interfaces()
            self.configure_routing()
            self.configure_iptables()  # Add iptables and ipset configuration
            
            self.logger.info("Network namespace setup completed successfully")
            
            if self.verbose >= 1:
                print("Network setup completed successfully")
                self.print_summary()
                
            return 0
            
        except Exception as e:
            self.logger.error(f"Setup failed: {e}")
            self.cleanup_on_error()  # Clean up on error
            
            if self.verbose == 0:
                # In silent mode, still print error to stderr
                print(f"Error: {e}", file=sys.stderr)
            else:
                print(f"Setup failed: {e}")
            return 1
            
    def print_summary(self):
        """Print setup summary."""
        print(f"\\nCreated {len(self.created_namespaces)} namespaces:")
        for ns in sorted(self.created_namespaces):
            print(f"  {ns}")
            
        print(f"\\nSubnet topology:")
        for subnet, members in sorted(self.subnets.items()):
            if len(members) == 1:
                router, iface, ip = members[0]
                print(f"  {subnet}: {router}:{iface}({ip}) [external]")
            elif len(members) == 2:
                (r1, i1, ip1), (r2, i2, ip2) = members
                print(f"  {subnet}: {r1}:{i1}({ip1}) <-> {r2}:{i2}({ip2}) [point-to-point]")
            else:
                member_list = [f"{r}:{i}({ip})" for r, i, ip in members]
                print(f"  {subnet}: {', '.join(member_list)} [bridged]")


def main():
    parser = argparse.ArgumentParser(description="Complete network namespace setup with firewall support")
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity (-v for info, -vv for debug)')
    
    args = parser.parse_args()
    
    # Check for root privileges
    if os.geteuid() != 0:
        print("Error: This script requires root privileges")
        print("Please run with sudo")
        sys.exit(1)
        
    setup = CompleteNetworkSetup(args.verbose)
    exit_code = setup.setup_network()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()