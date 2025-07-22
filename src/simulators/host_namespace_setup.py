#!/usr/bin/env python3
"""
Host Namespace Setup Script

Manages dynamic host namespaces that can be added to and removed from the network simulation.
Hosts are simpler than routers - they have only one physical interface (eth0) for network
connectivity, plus optional dummy interfaces for secondary IPs.

Features:
- Dynamic host creation with primary IP on eth0
- Optional secondary IPs on dummy interfaces (dummy0, dummy1, etc.)
- Point-to-point connection to any existing router
- Simple routing: direct network + dummy IPs + default route via connected router
- Realistic latency simulation: 1ms on physical interface (eth0), 0ms on dummy interfaces
- Host removal with complete cleanup
- Compatible with existing nettest tools

Usage:
    # Add host with primary IP only
    sudo python3 host_namespace_setup.py --add-host host1 --primary-ip 10.1.1.100/24 --connect-to hq-gw
    
    # Add host with primary and secondary IPs
    sudo python3 host_namespace_setup.py --add-host host2 --primary-ip 10.2.1.100/24 --secondary-ips 192.168.100.1/24,172.16.1.1/24 --connect-to br-gw
    
    # Remove host
    sudo python3 host_namespace_setup.py --remove-host host1
    
    # List all hosts
    sudo python3 host_namespace_setup.py --list-hosts

Environment Variables:
    TRACEROUTE_SIMULATOR_FACTS - Directory containing router JSON facts files (read-only)
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
from typing import Dict, List, Set, Optional, Any, Tuple


class HostNamespaceManager:
    """
    Manages dynamic host namespaces in the network simulation.
    
    Hosts are endpoint devices with single physical interface and simple routing.
    They can be dynamically added to and removed from the running network simulation.
    """
    
    def __init__(self, verbose: int = 0):
        self.verbose = verbose
        self.setup_logging()
        
        # Network state
        self.routers: Dict[str, Dict] = {}
        self.router_subnets: Dict[str, List[tuple]] = {}  # subnet -> [(router, interface, ip)]
        self.available_namespaces: Set[str] = set()
        self.host_registry_file = Path("/tmp/traceroute_hosts_registry.json")
        
        # Registry files for interface tracking
        self.router_registry_file = Path("/tmp/traceroute_routers_registry.json")
        self.interface_registry_file = Path("/tmp/traceroute_interfaces_registry.json")
        self.interface_registry: Dict[str, Dict[str, str]] = {}  # host_code -> {interface_name -> interface_code}
        
    def setup_logging(self):
        """Configure logging based on verbosity level."""
        if self.verbose == 0:
            level = logging.WARNING
        elif self.verbose == 1:
            level = logging.INFO
        else:
            level = logging.DEBUG
            
        logging.basicConfig(
            level=level,
            format='%(levelname)s: %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
    def load_router_facts(self):
        """Load router facts to understand network topology."""
        facts_path = os.environ.get('TRACEROUTE_SIMULATOR_FACTS')
        if not facts_path:
            raise EnvironmentError("TRACEROUTE_SIMULATOR_FACTS environment variable must be set")
        facts_dir = Path(facts_path)
        
        if not facts_dir.exists():
            raise FileNotFoundError(f"Facts directory not found: {facts_dir}")
            
        json_files = list(facts_dir.glob("*.json"))
        if not json_files:
            raise FileNotFoundError(f"No JSON files found in {facts_dir}")
            
        for json_file in json_files:
            # Skip metadata files and host files
            if "_metadata.json" in json_file.name or json_file.name.startswith("host_"):
                continue
                
            router_name = json_file.stem
            self.logger.debug(f"Loading {router_name}")
            
            with open(json_file, 'r') as f:
                facts = json.load(f)
                self.routers[router_name] = facts
                
        # Build subnet mapping from router facts
        for router_name, facts in self.routers.items():
            # Check routing tables for interface subnets
            routing_tables = facts.get('routing', {}).get('tables', [])
            for route in routing_tables:
                if (route.get('protocol') == 'kernel' and 
                    route.get('scope') == 'link' and
                    route.get('prefsrc') and route.get('dev') and route.get('dst')):
                    
                    subnet = route['dst']
                    router_iface = route['dev'] 
                    ip = route['prefsrc']
                    
                    if subnet not in self.router_subnets:
                        self.router_subnets[subnet] = []
                    self.router_subnets[subnet].append((router_name, router_iface, ip))
                    
        self.logger.info(f"Loaded {len(self.routers)} routers, {len(self.router_subnets)} subnets")
        
    def discover_namespaces(self):
        """Discover available network namespaces."""
        try:
            result = self.run_command("ip netns list", check=False)
            if result.returncode != 0:
                self.logger.warning("Failed to list namespaces")
                return
                
            for line in result.stdout.split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                ns_match = re.match(r'^([^\s(]+)', line)
                if ns_match:
                    namespace = ns_match.group(1)
                    self.available_namespaces.add(namespace)
                    
        except Exception as e:
            self.logger.error(f"Error discovering namespaces: {e}")
            
        self.logger.info(f"Found {len(self.available_namespaces)} available namespaces")
        
    def run_command(self, command: str, namespace: str = None, check: bool = True) -> subprocess.CompletedProcess:
        """Execute command optionally in namespace."""
        if namespace:
            full_command = f"ip netns exec {namespace} {command}"
        else:
            full_command = command
            
        self.logger.debug(f"Running: {full_command}")
        
        # With -vvv, print the command before execution
        if self.verbose >= 3:
            print(f"[CMD] {full_command}")
        
        result = subprocess.run(
            full_command, shell=True, capture_output=True, text=True, check=check
        )
        
        # With -vvv, print the command output
        if self.verbose >= 3:
            # Skip stdout for network_namespace_status.py and host listing to avoid verbose output
            if 'network_namespace_status.py' not in full_command and '--list-hosts' not in full_command:
                if result.stdout:
                    print(f"[STDOUT]\n{result.stdout}")
            if result.stderr:
                print(f"[STDERR]\n{result.stderr}")
            print(f"[RETCODE] {result.returncode}")
        
        if result.returncode != 0 and check:
            self.logger.error(f"Command failed: {full_command}")
            self.logger.error(f"Error: {result.stderr}")
            raise subprocess.CalledProcessError(result.returncode, full_command, result.stderr)
            
        return result
        
    def load_router_registry(self) -> Dict[str, str]:
        """Load registry of router/host name to code mappings."""
        if not self.router_registry_file.exists():
            return {}
            
        try:
            with open(self.router_registry_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Could not load router registry: {e}")
            return {}
            
    def save_router_registry(self, registry: Dict[str, str]):
        """Save registry of router/host name to code mappings."""
        try:
            with open(self.router_registry_file, 'w') as f:
                json.dump(registry, f, indent=2)
        except IOError as e:
            self.logger.error(f"Could not save router registry: {e}")

    def load_interface_registry(self) -> Dict[str, Dict[str, str]]:
        """Load registry of interface name to code mappings per router/host."""
        if not self.interface_registry_file.exists():
            return {}
            
        try:
            with open(self.interface_registry_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Could not load interface registry: {e}")
            return {}
            
    def save_interface_registry(self):
        """Save registry of interface name to code mappings per router/host."""
        try:
            with open(self.interface_registry_file, 'w') as f:
                json.dump(self.interface_registry, f, indent=2)
        except IOError as e:
            self.logger.error(f"Could not save interface registry: {e}")

    def get_host_code(self, host_name: str) -> str:
        """Get or generate host code for given host name."""
        router_registry = self.load_router_registry()
        
        # If host already has a code, return it
        if host_name in router_registry:
            return router_registry[host_name]
        
        # Generate new host code (h000 to h999)
        existing_codes = set(router_registry.values())
        
        for i in range(1000):  # h000 to h999
            host_code = f"h{i:03d}"
            if host_code not in existing_codes:
                router_registry[host_name] = host_code
                self.save_router_registry(router_registry)
                return host_code
        
        # If we somehow reach 1000 hosts, fall back to a hash-based approach
        import hashlib
        name_hash = hashlib.md5(host_name.encode()).hexdigest()[:3]
        fallback_code = f"h{name_hash}"
        router_registry[host_name] = fallback_code
        self.save_router_registry(router_registry)
        return fallback_code

    def get_interface_code(self, host_code: str, interface_name: str) -> str:
        """Get or generate interface code for given host and interface."""
        # Ensure host exists in registry
        if host_code not in self.interface_registry:
            self.interface_registry[host_code] = {}
        
        # If interface already has a code, return it
        if interface_name in self.interface_registry[host_code]:
            return self.interface_registry[host_code][interface_name]
        
        # Generate new interface code (i000 to i999)
        existing_codes = set(self.interface_registry[host_code].values())
        
        for i in range(1000):  # i000 to i999
            interface_code = f"i{i:03d}"
            if interface_code not in existing_codes:
                self.interface_registry[host_code][interface_name] = interface_code
                return interface_code
        
        # If we somehow reach 1000 interfaces, fall back to a hash-based approach
        import hashlib
        name_hash = hashlib.md5(interface_name.encode()).hexdigest()[:3]
        fallback_code = f"i{name_hash}"
        self.interface_registry[host_code][interface_name] = fallback_code
        return fallback_code

    def register_host_interfaces(self, host_name: str, interfaces: List[str]):
        """Register all interfaces for a host in the interface registry."""
        host_code = self.get_host_code(host_name)
        
        # Load current interface registry
        self.interface_registry = self.load_interface_registry()
        
        # Register each interface
        for interface_name in interfaces:
            interface_code = self.get_interface_code(host_code, interface_name)
            self.logger.debug(f"Registered interface {interface_name} as {interface_code} for host {host_name} ({host_code})")
        
        # Save updated registry
        self.save_interface_registry()

    def register_host_in_bridge_registry(self, host_name: str, primary_ip: str, bridge_name: str):
        """Register host in the bridge registry."""
        try:
            registry_file = Path("/tmp/traceroute_bridges_registry.json")
            if not registry_file.exists():
                self.logger.error("Bridge registry not found")
                return False
                
            with open(registry_file, 'r') as f:
                bridge_registry = json.load(f)
            
            # Add host to the bridge
            if bridge_name in bridge_registry:
                if 'hosts' not in bridge_registry[bridge_name]:
                    bridge_registry[bridge_name]['hosts'] = {}
                
                bridge_registry[bridge_name]['hosts'][host_name] = {
                    "interface": "eth0",
                    "ipv4": primary_ip,
                    "state": "UP"
                }
                
                # Save updated registry
                with open(registry_file, 'w') as f:
                    json.dump(bridge_registry, f, indent=2)
                    
                self.logger.debug(f"Registered host {host_name} in bridge {bridge_name}")
                return True
            else:
                self.logger.error(f"Bridge {bridge_name} not found in registry")
                return False
                
        except Exception as e:
            self.logger.error(f"Error registering host in bridge registry: {e}")
            return False

    def unregister_host_interfaces(self, host_name: str):
        """Unregister all interfaces for a host from the interface registry."""
        router_registry = self.load_router_registry()
        
        # Find host code
        host_code = router_registry.get(host_name)
        if not host_code:
            self.logger.warning(f"Host {host_name} not found in router registry")
            return
        
        # Load current interface registry
        self.interface_registry = self.load_interface_registry()
        
        # Remove host's interfaces from registry
        if host_code in self.interface_registry:
            del self.interface_registry[host_code]
            self.save_interface_registry()
            self.logger.debug(f"Unregistered all interfaces for host {host_name} ({host_code})")
        
        # Remove host from router registry
        if host_name in router_registry:
            del router_registry[host_name]
            self.save_router_registry(router_registry)
            self.logger.debug(f"Unregistered host {host_name} from router registry")

    def unregister_host_from_bridge_registry(self, host_name: str):
        """Unregister host from the bridge registry."""
        try:
            registry_file = Path("/tmp/traceroute_bridges_registry.json")
            if not registry_file.exists():
                return
                
            with open(registry_file, 'r') as f:
                bridge_registry = json.load(f)
            
            # Find and remove host from all bridges
            for bridge_name, bridge_info in bridge_registry.items():
                hosts = bridge_info.get('hosts', {})
                if host_name in hosts:
                    del hosts[host_name]
                    self.logger.debug(f"Unregistered host {host_name} from bridge {bridge_name}")
            
            # Save updated registry
            with open(registry_file, 'w') as f:
                json.dump(bridge_registry, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Error unregistering host from bridge registry: {e}")
        
    def check_command_availability(self, command: str) -> bool:
        """Check if a command is available on the system."""
        try:
            # First try which
            result = subprocess.run(
                f"which {command}",
                shell=True,
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                return True
                
            # Also check common system directories
            common_paths = ['/bin', '/sbin', '/usr/bin', '/usr/sbin']
            for path in common_paths:
                if os.path.exists(os.path.join(path, command)):
                    return True
                    
            return False
        except Exception:
            return False
            
    def configure_host_latency(self, host_name: str, interface: str, latency_ms: float = 1.0):
        """Configure latency on host interface for realistic network behavior."""
        # Check if tc (traffic control) is available
        if not self.check_command_availability("tc"):
            self.logger.warning("tc (traffic control) not available - skipping host latency configuration")
            if self.verbose >= 2:
                print("Warning: tc not available - host latency simulation skipped")
            return
        
        try:
            # Configure latency using netem (network emulation)
            latency_str = f"{latency_ms}ms"
            tc_cmd = f"/sbin/tc qdisc add dev {interface} root netem delay {latency_str}"
            tc_result = self.run_command(tc_cmd, namespace=host_name, check=False)
            
            if tc_result.returncode == 0:
                self.logger.debug(f"Added {latency_str} latency to {host_name}:{interface}")
            else:
                # Interface might already have qdisc, try to replace
                tc_replace_cmd = f"/sbin/tc qdisc replace dev {interface} root netem delay {latency_str}"
                tc_replace_result = self.run_command(tc_replace_cmd, namespace=host_name, check=False)
                if tc_replace_result.returncode == 0:
                    self.logger.debug(f"Replaced qdisc with {latency_str} latency on {host_name}:{interface}")
                else:
                    self.logger.warning(f"Failed to add latency to {host_name}:{interface}: {tc_result.stderr}")
                    
        except Exception as e:
            self.logger.warning(f"Error configuring latency for {host_name}:{interface}: {e}")
            
    def load_host_registry(self) -> Dict[str, Dict]:
        """Load registry of existing hosts."""
        if not self.host_registry_file.exists():
            return {}
            
        try:
            with open(self.host_registry_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Could not load host registry: {e}")
            return {}
            
    def save_host_registry(self, registry: Dict[str, Dict]):
        """Save registry of hosts."""
        try:
            with open(self.host_registry_file, 'w') as f:
                json.dump(registry, f, indent=2)
        except IOError as e:
            self.logger.error(f"Could not save host registry: {e}")
            
    def find_router_for_subnet(self, primary_ip: str) -> Optional[Tuple[str, str, str]]:
        """Find which router and interface can connect to the given IP."""
        try:
            host_network = ipaddress.IPv4Network(primary_ip, strict=False)
        except ipaddress.AddressValueError:
            return None
            
        # Look for a subnet that contains this IP
        for subnet, members in self.router_subnets.items():
            try:
                subnet_network = ipaddress.IPv4Network(subnet, strict=False)
                if host_network.subnet_of(subnet_network) or host_network.overlaps(subnet_network):
                    # Found matching subnet, return first router (could be enhanced for selection)
                    if members:
                        router_name, router_iface, router_ip = members[0]
                        return router_name, router_iface, router_ip
            except ipaddress.AddressValueError:
                continue
                
        return None
        
    def get_default_gateway(self, primary_ip: str, router_name: str) -> Optional[str]:
        """Get the default gateway IP for the host based on connected router."""
        try:
            host_network = ipaddress.IPv4Network(primary_ip, strict=False)
        except ipaddress.AddressValueError:
            return None
            
        # Find router's IP in the same subnet
        for subnet, members in self.router_subnets.items():
            try:
                subnet_network = ipaddress.IPv4Network(subnet, strict=False)
                if host_network.subnet_of(subnet_network) or host_network.overlaps(subnet_network):
                    for r_name, r_iface, r_ip in members:
                        if r_name == router_name:
                            return r_ip
            except ipaddress.AddressValueError:
                continue
                
        return None
        
    def router_has_ip_in_subnet(self, router_name: str, subnet: str) -> bool:
        """Check if router already has an IP address in the given subnet."""
        try:
            subnet_net = ipaddress.IPv4Network(subnet, strict=False)
            
            # Get router's IP addresses from facts
            if router_name in self.routers:
                routing_tables = self.routers[router_name].get('routing', {}).get('tables', [])
                for route in routing_tables:
                    if (route.get('protocol') == 'kernel' and 
                        route.get('scope') == 'link' and
                        route.get('prefsrc') and route.get('dst')):
                        
                        dst_subnet = route['dst']
                        try:
                            iface_net = ipaddress.IPv4Network(dst_subnet, strict=False)
                            if subnet_net.overlaps(iface_net):
                                return True
                        except ipaddress.AddressValueError:
                            continue
                            
        except ipaddress.AddressValueError:
            pass
            
        return False
        
    def find_router_interface_info(self, router_name: str, interface_name: str) -> Optional[tuple]:
        """Find information about a specific router interface."""
        if router_name not in self.routers:
            return None
            
        routing_tables = self.routers[router_name].get('routing', {}).get('tables', [])
        for route in routing_tables:
            if (route.get('protocol') == 'kernel' and 
                route.get('scope') == 'link' and
                route.get('prefsrc') and route.get('dev') == interface_name and route.get('dst')):
                
                subnet = route['dst']
                router_ip = route['prefsrc']
                return (interface_name, router_ip)
                
        return None
        
    def find_shared_mesh_bridge(self, primary_ip: str) -> Optional[str]:
        """Find the shared mesh bridge for the host's subnet using bridge registry."""
        try:
            host_network = ipaddress.IPv4Network(primary_ip, strict=False)
            
            # Load bridge registry
            registry_file = Path("/tmp/traceroute_bridges_registry.json")
            if not registry_file.exists():
                self.logger.error("Bridge registry not found. Run netsetup first.")
                return None
                
            with open(registry_file, 'r') as f:
                bridge_registry = json.load(f)
            
            # Find bridge that contains this IP
            for bridge_name, bridge_info in bridge_registry.items():
                routers = bridge_info.get('routers', {})
                for router_name, router_info in routers.items():
                    router_ip = router_info.get('ipv4', '')
                    if router_ip:
                        try:
                            router_network = ipaddress.IPv4Network(router_ip, strict=False)
                            if host_network.subnet_of(router_network) or host_network.overlaps(router_network):
                                # Check if this bridge exists in hidden-mesh namespace
                                result = self.run_command(f"ip netns exec hidden-mesh ip link show {bridge_name}", check=False)
                                if result.returncode == 0:
                                    return bridge_name
                        except ipaddress.AddressValueError:
                            continue
                    
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding shared mesh bridge: {e}")
            return None
            
    def find_router_bridge(self, router_name: str, interface_name: str) -> Optional[str]:
        """Find the bridge that a specific router interface is connected to."""
        try:
            # Load bridge registry
            registry_file = Path("/tmp/traceroute_bridges_registry.json")
            if not registry_file.exists():
                self.logger.error("Bridge registry not found. Run netsetup first.")
                return None
                
            with open(registry_file, 'r') as f:
                bridge_registry = json.load(f)
            
            # Find bridge that contains this router and interface
            for bridge_name, bridge_info in bridge_registry.items():
                routers = bridge_info.get('routers', {})
                if router_name in routers:
                    router_info = routers[router_name]
                    if router_info.get('interface') == interface_name:
                        # Check if this bridge exists in hidden-mesh namespace
                        result = self.run_command(f"ip netns exec hidden-mesh ip link show {bridge_name}", check=False)
                        if result.returncode == 0:
                            return bridge_name
                            
            return None
        except Exception as e:
            self.logger.error(f"Error finding bridge: {e}")
            return None

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

    def get_all_registered_ips(self) -> Dict[str, Dict]:
        """Get all IP addresses registered in the bridge registry."""
        try:
            registry_file = Path("/tmp/traceroute_bridges_registry.json")
            if not registry_file.exists():
                return {}
                
            with open(registry_file, 'r') as f:
                bridge_registry = json.load(f)
            
            all_ips = {}
            
            for bridge_name, bridge_info in bridge_registry.items():
                # Check router IPs
                routers = bridge_info.get('routers', {})
                for router_name, router_info in routers.items():
                    ip_address = router_info.get('ipv4', '')
                    if ip_address:
                        # Extract IP without prefix
                        ip_without_prefix = ip_address.split('/')[0] if '/' in ip_address else ip_address
                        all_ips[ip_without_prefix] = {
                            'type': 'router',
                            'name': router_name,
                            'bridge': bridge_name,
                            'interface': router_info.get('interface', 'unknown'),
                            'full_ip': ip_address
                        }
                
                # Check host IPs
                hosts = bridge_info.get('hosts', {})
                for host_name, host_info in hosts.items():
                    ip_address = host_info.get('ipv4', '')
                    if ip_address:
                        # Extract IP without prefix
                        ip_without_prefix = ip_address.split('/')[0] if '/' in ip_address else ip_address
                        all_ips[ip_without_prefix] = {
                            'type': 'host',
                            'name': host_name,
                            'bridge': bridge_name,
                            'interface': host_info.get('interface', 'unknown'),
                            'full_ip': ip_address
                        }
            
            return all_ips
            
        except Exception as e:
            self.logger.error(f"Error reading bridge registry: {e}")
            return {}

    def get_active_router_ips(self) -> Dict[str, Dict]:
        """Get all IP addresses from active routers using netstatus tool."""
        all_ips = {}
        
        try:
            # Get all router interfaces in single call
            result = self.run_command(
                f"python3 {Path(__file__).parent}/network_namespace_status.py interfaces -j",
                check=False
            )
            
            if result.returncode == 0:
                try:
                    routers_data = json.loads(result.stdout)
                    
                    # Check if routers_data is a dictionary and iterate properly
                    if isinstance(routers_data, dict):
                        for router_name, router_info in routers_data.items():
                            if isinstance(router_info, dict):
                                # Get all interfaces and their IPs for this router
                                interfaces = router_info.get('interfaces', [])
                                for interface in interfaces:
                                    if isinstance(interface, dict):
                                        for addr_info in interface.get('addr_info', []):
                                            if isinstance(addr_info, dict) and addr_info.get('family') == 'inet':
                                                ip_addr = addr_info.get('local', '')
                                                if ip_addr and ip_addr != '127.0.0.1':  # Skip loopback
                                                    all_ips[ip_addr] = {
                                                        'type': 'router',
                                                        'name': router_name,
                                                        'interface': interface.get('ifname', 'unknown'),
                                                        'full_ip': f"{ip_addr}/{addr_info.get('prefixlen', 24)}"
                                                    }
                    else:
                        self.logger.warning(f"Unexpected router data format: {type(routers_data)}")
                except json.JSONDecodeError as e:
                    self.logger.warning(f"Failed to parse router interfaces JSON output: {e}")
        except Exception as e:
            self.logger.warning(f"Failed to get active router IPs: {e}")
        
        return all_ips
    
    def get_active_host_ips(self) -> Dict[str, Dict]:
        """Get all IP addresses from active hosts using hostlist tool."""
        all_ips = {}
        
        try:
            # Get all active hosts using host_namespace_setup.py with JSON output
            result = self.run_command(
                f"python3 {Path(__file__).resolve()} --list-hosts -j",
                check=False
            )
            
            if result.returncode == 0:
                try:
                    hosts_data = json.loads(result.stdout)
                    
                    for host_name, host_info in hosts_data.get('hosts', {}).items():
                        if host_info.get('status') == 'running':
                            # Add primary IP
                            primary_ip = host_info.get('primary_ip', '')
                            if primary_ip and '/' in primary_ip:
                                ip_without_prefix = primary_ip.split('/')[0]
                                all_ips[ip_without_prefix] = {
                                    'type': 'host',
                                    'name': host_name,
                                    'interface': 'eth0',
                                    'full_ip': primary_ip
                                }
                            
                            # Add secondary IPs
                            secondary_ips = host_info.get('secondary_ips', [])
                            for i, secondary_ip in enumerate(secondary_ips):
                                if secondary_ip and '/' in secondary_ip:
                                    ip_without_prefix = secondary_ip.split('/')[0]
                                    all_ips[ip_without_prefix] = {
                                        'type': 'host',
                                        'name': host_name,
                                        'interface': f'dummy{i}',
                                        'full_ip': secondary_ip
                                    }
                except json.JSONDecodeError:
                    self.logger.warning("Failed to parse host list JSON output")
        except Exception as e:
            self.logger.warning(f"Failed to get active host IPs: {e}")
        
        return all_ips

    def check_ip_collision(self, ip_address: str, target_router: str = None) -> Tuple[bool, Dict]:
        """Check if an IP address is already in use.
        
        For router IPs: Always check for collision (routers must have unique IPs)
        For host IPs: Only check if another host on the same router has this IP
        """
        # Extract IP without prefix if provided
        ip_without_prefix = ip_address.split('/')[0] if '/' in ip_address else ip_address
        
        # Check active router IPs - routers must always have unique IPs
        router_ips = self.get_active_router_ips()
        if ip_without_prefix in router_ips:
            return True, router_ips[ip_without_prefix]
        
        # For hosts, only check collision if target_router is specified
        if target_router:
            # Load host registry to check hosts on the same router
            registry = self.load_host_registry()
            for host_name, host_config in registry.items():
                host_ip = host_config.get('primary_ip', '').split('/')[0]
                host_router = host_config.get('connected_to', '')
                
                # Check if this host has the same IP and is connected to the same router
                if host_ip == ip_without_prefix and host_router == target_router:
                    return True, {
                        'type': 'host',
                        'name': host_name,
                        'interface': 'eth0',
                        'full_ip': host_config.get('primary_ip', ip_address),
                        'router': host_router
                    }
                    
                # Also check secondary IPs
                for secondary_ip in host_config.get('secondary_ips', []):
                    secondary_ip_clean = secondary_ip.split('/')[0] if '/' in secondary_ip else secondary_ip
                    if secondary_ip_clean == ip_without_prefix and host_router == target_router:
                        return True, {
                            'type': 'host',
                            'name': host_name,
                            'interface': 'dummy',
                            'full_ip': secondary_ip,
                            'router': host_router
                        }
        
        return False, {}

    def create_mesh_connection(self, host_name: str, primary_ip: str, router_bridge: Optional[str] = None) -> Tuple[bool, Dict]:
        """Connect host directly to specific mesh bridge in simulation namespace."""
        
        # Use the router's bridge if provided, otherwise find based on IP
        if router_bridge:
            mesh_bridge = router_bridge
            self.logger.info(f"Using router's bridge {mesh_bridge} for connection")
        else:
            # Find the shared mesh bridge for this subnet in simulation namespace
            mesh_bridge = self.find_shared_mesh_bridge(primary_ip)
            if not mesh_bridge:
                self.logger.error(f"No shared mesh bridge found for IP {primary_ip}. Run netsetup first.")
                return False, {}
        
        self.logger.info(f"Connecting host {host_name} directly to mesh {mesh_bridge} in hidden-mesh namespace")
        
        # Create veth pair: host namespace <-> specific mesh bridge in hidden-mesh namespace
        # Use shorter names to avoid Linux 15-character interface name limit
        import hashlib
        name_hash = hashlib.md5(host_name.encode()).hexdigest()[:6]
        host_veth = f"h{name_hash}"
        mesh_veth = f"m{name_hash}"
        
        self.run_command(f"ip link add {host_veth} type veth peer name {mesh_veth}")
        
        # Move host side to host namespace and rename to eth0
        self.run_command(f"ip link set {host_veth} netns {host_name}")
        self.run_command(f"ip link set {host_veth} name eth0", namespace=host_name)
        
        # Move mesh side to hidden-mesh namespace and connect to specific mesh bridge
        self.run_command(f"ip link set {mesh_veth} netns hidden-mesh")
        self.run_command(f"ip link set {mesh_veth} master {mesh_bridge}", namespace="hidden-mesh")
        self.run_command(f"ip link set {mesh_veth} up", namespace="hidden-mesh")
        
        # Configure host IP
        self.run_command(f"ip addr add {primary_ip} dev eth0", namespace=host_name)
        self.run_command(f"ip link set eth0 up", namespace=host_name)
        
        # Add 1ms latency to physical interface for realistic network behavior
        self.configure_host_latency(host_name, "eth0", latency_ms=1.0)
        
        connection_info = {
            "connection_type": "sim_mesh_direct",
            "mesh_bridge": mesh_bridge,
            "host_veth": host_veth,
            "mesh_veth": mesh_veth,
            "sim_namespace": "netsim"
        }
        
        return True, connection_info
        
    def add_host(self, host_name: str, primary_ip: str, secondary_ips: List[str], connect_to: str = None, router_interface: str = None) -> bool:
        """Add a new host to the network using unified mesh infrastructure."""
        if host_name in self.available_namespaces:
            self.logger.error(f"Namespace {host_name} already exists")
            return False
            
        # Load host registry
        registry = self.load_host_registry()
        if host_name in registry:
            self.logger.error(f"Host {host_name} already registered")
            return False
            
        # Validate primary IP format
        if '/' not in primary_ip:
            self.logger.error("Primary IP must include prefix length (e.g., 10.1.1.100/24)")
            return False
            
        try:
            primary_network = ipaddress.IPv4Network(primary_ip, strict=False)
            primary_addr = str(primary_network.network_address)
            primary_prefix = primary_network.prefixlen
        except ipaddress.AddressValueError as e:
            self.logger.error(f"Invalid primary IP format: {e}")
            return False
            
        # Determine target router first (needed for collision check)
        if connect_to:
            target_router = connect_to
        else:
            # Auto-detect based on primary IP
            router_info = self.find_router_for_subnet(primary_ip)
            if not router_info:
                self.logger.error(f"Could not find suitable router for IP {primary_ip}")
                return False
            target_router, _, _ = router_info
            
        # Check for IP collision on primary IP (only on the same router)
        collision_detected, collision_info = self.check_ip_collision(primary_ip, target_router)
        if collision_detected:
            entity_type = collision_info.get('type', 'unknown')
            entity_name = collision_info.get('name', 'unknown')
            entity_interface = collision_info.get('interface', 'unknown')
            full_ip = collision_info.get('full_ip', primary_ip)
            
            if entity_type == 'router':
                error_msg = f"IP address collision detected: {primary_ip.split('/')[0]} is already in use by router '{entity_name}' on interface '{entity_interface}'"
            else:
                error_msg = f"IP address collision detected: {primary_ip.split('/')[0]} is already in use by host '{entity_name}' connected to router '{target_router}'"
            raise ValueError(error_msg)
            
        # Check for IP collision on secondary IPs
        for secondary_ip in secondary_ips:
            collision_detected, collision_info = self.check_ip_collision(secondary_ip, target_router)
            if collision_detected:
                entity_type = collision_info.get('type', 'unknown')
                entity_name = collision_info.get('name', 'unknown')
                entity_interface = collision_info.get('interface', 'unknown')
                full_ip = collision_info.get('full_ip', secondary_ip)
                
                if entity_type == 'router':
                    error_msg = f"IP address collision detected: {secondary_ip.split('/')[0]} is already in use by router '{entity_name}' on interface '{entity_interface}'"
                else:
                    error_msg = f"IP address collision detected: {secondary_ip.split('/')[0]} is already in use by host '{entity_name}' connected to router '{target_router}'"
                raise ValueError(error_msg)
            
        # Validate router interface option
        if router_interface and not connect_to:
            self.logger.error("--router-interface requires --connect-to to specify the router")
            return False
            
        # Get router details (we already have target_router from above)
        target_iface = None  # Initialize target_iface
        gateway_ip = None    # Initialize gateway_ip
        
        # Validate router exists
        if connect_to:
            # Check if router exists either in facts or as a namespace
            if connect_to not in self.routers and connect_to not in self.available_namespaces:
                self.logger.error(f"Router {connect_to} not found in facts or namespaces")
                return False
            
            # Get gateway IP
            if router_interface:
                interface_info = self.find_router_interface_info(target_router, router_interface)
                if not interface_info:
                    self.logger.error(f"Interface {router_interface} not found on router {target_router}")
                    return False
                target_iface, gateway_ip = interface_info
            else:
                # Get router's IP in the same subnet as host
                gateway_ip = self.get_default_gateway(primary_ip, target_router)
                if gateway_ip:
                    # Find which interface has this IP
                    for subnet, members in self.router_subnets.items():
                        for r_name, r_iface, r_ip in members:
                            if r_name == target_router and r_ip == gateway_ip:
                                target_iface = r_iface
                                break
                        if target_iface:
                            break
                else:
                    # If no gateway in same subnet, get any IP from the router
                    # Look for the first IP address we can find for this router
                    for subnet, members in self.router_subnets.items():
                        for r_name, r_iface, r_ip in members:
                            if r_name == target_router and r_ip:
                                gateway_ip = r_ip
                                target_iface = r_iface
                                self.logger.warning(f"No matching subnet on {target_router}, using router IP {gateway_ip} as gateway")
                                break
                        if gateway_ip:
                            break
                    
                    if not gateway_ip:
                        self.logger.error(f"Could not find any IP address for router {target_router}")
                        return False
        else:
            # We already found the router info above for collision check
            # Now get the interface and gateway details
            router_info = self.find_router_for_subnet(primary_ip)
            if router_info:
                _, target_iface, gateway_ip = router_info
            
        self.logger.info(f"Connecting host {host_name} to router {target_router} via gateway {gateway_ip} using unified mesh infrastructure")
        
        # Calculate the first available IP in host's network to use as gateway
        try:
            host_network = ipaddress.IPv4Network(primary_ip, strict=False)
            gateway_addr = ipaddress.IPv4Address(gateway_ip)
            
            # If gateway is not in host's subnet, add first available IP to router interface
            if gateway_addr not in host_network:
                # Use first usable IP in the network as new gateway
                new_gateway_ip = str(host_network.network_address + 1)
                
                # Add this IP to the router's interface in the mesh
                # Find the bridge for this subnet
                subnet_str = str(host_network)
                bridge_name = self._generate_bridge_name(subnet_str)
                
                # Add IP to the router's interface that connects to this subnet
                self.logger.info(f"Adding {new_gateway_ip}/{host_network.prefixlen} to router {target_router}")
                
                # First, find which interface on the router connects to this bridge
                # The router should have a veth interface connected to the bridge
                # We need to add the IP to the router's namespace, not the bridge
                
                # Find the bridge for this subnet
                bridge_name_for_subnet = self._generate_bridge_name(subnet_str)
                
                # Check if bridge exists in hidden-mesh
                result = self.run_command(f"ip link show {bridge_name_for_subnet}", namespace="hidden-mesh", check=False)
                if result.returncode != 0:
                    # Create bridge if it doesn't exist
                    self.run_command(f"ip link add {bridge_name_for_subnet} type bridge", namespace="hidden-mesh")
                    self.run_command(f"ip link set {bridge_name_for_subnet} up", namespace="hidden-mesh")
                
                # Now we need to connect the router to this bridge if not already connected
                # and add the IP to the router's interface
                # For now, add to the router's target interface if it exists
                if target_iface and target_router in self.available_namespaces:
                    # Add the IP directly to the router's interface
                    self.run_command(f"ip addr add {new_gateway_ip}/{host_network.prefixlen} dev {target_iface}", 
                                   namespace=target_router, check=False)
                    self.logger.info(f"Added {new_gateway_ip}/{host_network.prefixlen} to {target_router} interface {target_iface}")
                else:
                    # Fallback: add to bridge
                    self.logger.warning(f"Router {target_router} not accessible, adding IP to bridge instead")
                    self.run_command(f"ip addr add {new_gateway_ip}/{host_network.prefixlen} dev {bridge_name_for_subnet}", 
                                   namespace="hidden-mesh", check=False)
                
                # Update gateway_ip to use the new one
                gateway_ip = new_gateway_ip
                self.logger.info(f"Updated gateway IP to {gateway_ip}")
                
        except Exception as e:
            self.logger.warning(f"Could not set up gateway IP on router interface: {e}")
        
        try:
            # Create host namespace
            self.run_command(f"ip netns add {host_name}")
            
            # Enable loopback
            self.run_command("ip link set lo up", namespace=host_name)
            
            # Connect to mesh infrastructure (unified mesh architecture)
            # If we have a specific router target, find its bridge
            router_bridge = None
            if connect_to and target_iface:
                router_bridge = self.find_router_bridge(target_router, target_iface)
                if router_bridge:
                    self.logger.info(f"Found router {target_router}'s interface {target_iface} connected to bridge {router_bridge}")
                else:
                    self.logger.warning(f"Could not find bridge for {target_router} interface {target_iface}, falling back to IP-based selection")
                    
            success, connection_info = self.create_mesh_connection(host_name, primary_ip, router_bridge)
            if not success:
                raise Exception(f"Failed to connect to mesh infrastructure")
                
            # Create dummy interfaces for secondary IPs
            dummy_configs = []
            for i, secondary_ip in enumerate(secondary_ips):
                if '/' not in secondary_ip:
                    self.logger.error(f"Secondary IP must include prefix length: {secondary_ip}")
                    raise Exception(f"Invalid secondary IP format: {secondary_ip}")
                    
                try:
                    ipaddress.IPv4Network(secondary_ip, strict=False)
                    dummy_name = f"dummy{i}"
                    
                    self.run_command(f"ip link add {dummy_name} type dummy", namespace=host_name)
                    self.run_command(f"ip addr add {secondary_ip} dev {dummy_name}", namespace=host_name)
                    self.run_command(f"ip link set {dummy_name} up", namespace=host_name)
                    
                    # Add 0ms latency to dummy interface (virtual loopback, nearly zero latency)
                    self.configure_host_latency(host_name, dummy_name, latency_ms=0.0)
                    
                    dummy_configs.append({
                        "interface": dummy_name,
                        "ip": secondary_ip
                    })
                    
                except ipaddress.AddressValueError as e:
                    self.logger.warning(f"Invalid secondary IP {secondary_ip}: {e}")
                    continue
                    
            # Configure routing (direct network route is automatic, only add default route)
            # Check if gateway is in the same subnet as the host
            try:
                host_network = ipaddress.IPv4Network(primary_ip, strict=False)
                gateway_addr = ipaddress.IPv4Address(gateway_ip)
                if gateway_addr in host_network:
                    self.run_command(f"ip route add default via {gateway_ip} dev eth0", namespace=host_name)
                else:
                    self.logger.warning(f"Gateway {gateway_ip} is not in host subnet {host_network}, skipping default route")
            except Exception as e:
                self.logger.warning(f"Could not add default route: {e}")
            
            # Register host interfaces in interface registry
            host_interfaces = ["lo", "eth0"]  # Standard interfaces for all hosts
            host_interfaces.extend([f"dummy{i}" for i in range(len(secondary_ips))])  # Add dummy interfaces
            self.register_host_interfaces(host_name, host_interfaces)
            
            # Register host in bridge registry
            bridge_name = connection_info.get('mesh_bridge')
            if bridge_name:
                self.register_host_in_bridge_registry(host_name, primary_ip, bridge_name)
            
            # Register host
            host_config = {
                "primary_ip": primary_ip,
                "secondary_ips": secondary_ips,
                "connected_to": target_router,
                "router_interface": target_iface if target_iface else "unknown",
                "gateway_ip": gateway_ip,
                "dummy_interfaces": dummy_configs,
                "created_at": str(subprocess.run("date", capture_output=True, text=True).stdout.strip())
            }
            
            # Add connection-specific information
            host_config.update(connection_info)
            
            registry[host_name] = host_config
            self.save_host_registry(registry)
            
            if self.verbose >= 1:
                print(f"✓ Host {host_name} created successfully")
                print(f"  Primary IP: {primary_ip} on eth0")
                print(f"  Connected to: {target_router} interface {target_iface if target_iface else 'unknown'} (gateway: {gateway_ip})")
                if secondary_ips:
                    print(f"  Secondary IPs: {', '.join(secondary_ips)}")
                print(f"  Mesh bridge: {connection_info.get('mesh_bridge', 'auto-detected')}")
                    
            return True
            
        except ValueError as e:
            # IP collision or other validation error - no cleanup needed since nothing was created
            return False
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to create host {host_name}: {e}")
            # Cleanup on failure
            self.cleanup_host_resources(host_name, host_config if 'host_config' in locals() else {})
            return False
            
    def remove_host(self, host_name: str) -> bool:
        """Remove a host from the network."""
        registry = self.load_host_registry()
        
        if host_name not in registry:
            self.logger.error(f"Host {host_name} not found in registry")
            return False
            
        host_config = registry[host_name]
        
        try:
            # Unregister host interfaces from interface registry
            self.unregister_host_interfaces(host_name)
            
            # Unregister host from bridge registry
            self.unregister_host_from_bridge_registry(host_name)
            
            # Remove host resources
            self.cleanup_host_resources(host_name, host_config)
            
            # Remove from registry
            del registry[host_name]
            self.save_host_registry(registry)
            
            if self.verbose >= 1:
                print(f"✓ Host {host_name} removed successfully")
                
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to remove host {host_name}: {e}")
            return False
            
    def _recreate_host_namespace(self, host_name: str, host_config: Dict) -> bool:
        """Recreate host namespace from existing registry config without updating registry."""
        # Extract parameters from registry
        primary_ip = host_config.get('primary_ip', '')
        secondary_ips = host_config.get('secondary_ips', [])
        connected_to = host_config.get('connected_to', '')
        
        if not primary_ip or not connected_to:
            self.logger.error(f"Invalid host config for {host_name}")
            return False
            
        # Call the full add_host method with skip_registry=True
        return self.add_host(
            host_name=host_name,
            primary_ip=primary_ip, 
            secondary_ips=secondary_ips,
            connect_to=connected_to,
            skip_registry=True
        )
            
    def cleanup_host_resources(self, host_name: str, host_config: Dict):
        """Clean up all resources associated with a host."""
        try:
            # Remove namespace (this automatically removes all interfaces in it)
            self.run_command(f"ip netns del {host_name}", check=False)
            
            # Remove mesh-side veth interfaces based on connection type
            connection_type = host_config.get("connection_type", "")
            
            if connection_type == "sim_mesh_direct":
                # Remove mesh veth from hidden-mesh namespace (direct mesh connection)
                mesh_veth = host_config.get("mesh_veth")
                if mesh_veth:
                    self.run_command(f"ip netns exec hidden-mesh ip link del {mesh_veth}", check=False)
            elif connection_type == "sim_namespace":
                # Remove sim veth from host namespace (simulation bridge connection) - legacy
                sim_veth = host_config.get("sim_veth")
                if sim_veth:
                    self.run_command(f"ip link del {sim_veth}", check=False)
            elif connection_type == "mesh_direct":
                # Remove mesh veth from host namespace (shared mesh) - legacy
                mesh_veth = host_config.get("mesh_veth")
                if mesh_veth:
                    self.run_command(f"ip link del {mesh_veth}", check=False)
            elif connection_type == "bridge_direct":
                # Remove bridge veth from router namespace (legacy)
                connected_router = host_config.get("connected_to")
                bridge_veth = host_config.get("bridge_veth")
                if connected_router and bridge_veth and connected_router in self.available_namespaces:
                    self.run_command(f"ip link del {bridge_veth}", namespace=connected_router, check=False)
            elif connection_type == "veth_pair":
                # Remove legacy veth pair
                connected_router = host_config.get("connected_to")
                router_veth = host_config.get("router_veth")
                if connected_router and router_veth and connected_router in self.available_namespaces:
                    # Remove specific host route if it exists
                    primary_ip = host_config.get("primary_ip", "")
                    if primary_ip and '/' in primary_ip:
                        host_ip = primary_ip.split('/')[0]
                        self.run_command(f"ip route del {host_ip}/32 dev {router_veth}", namespace=connected_router, check=False)
                    
                    # Remove veth from router namespace
                    self.run_command(f"ip link del {router_veth}", namespace=connected_router, check=False)
                    
        except Exception as e:
            self.logger.debug(f"Error during cleanup: {e}")
            
    def list_hosts(self, json_output: bool = False) -> bool:
        """List all registered hosts."""
        registry = self.load_host_registry()
        
        if not registry:
            if json_output:
                print(json.dumps({"hosts": {}, "count": 0}))
            else:
                print("No hosts currently registered")
            return True
        
        if json_output:
            # JSON output format
            hosts_data = {}
            for host_name, config in sorted(registry.items()):
                status = "running" if host_name in self.available_namespaces else "stopped"
                hosts_data[host_name] = {
                    "status": status,
                    "primary_ip": config.get('primary_ip', 'unknown'),
                    "connected_to": config.get('connected_to', 'unknown'),
                    "gateway_ip": config.get('gateway_ip', 'unknown'),
                    "secondary_ips": config.get('secondary_ips', []),
                    "created_at": config.get('created_at', 'unknown'),
                    "connection_type": config.get('connection_type', 'unknown'),
                    "mesh_bridge": config.get('mesh_bridge', 'unknown')
                }
            
            output = {
                "hosts": hosts_data,
                "count": len(registry)
            }
            print(json.dumps(output, indent=2))
        else:
            # Text output format
            print(f"Registered hosts ({len(registry)}):")
            print("=" * 50)
            
            for host_name, config in sorted(registry.items()):
                status = "running" if host_name in self.available_namespaces else "stopped"
                print(f"Host: {host_name} [{status}]")
                print(f"  Primary IP: {config.get('primary_ip', 'unknown')}")
                router_iface = config.get('router_interface', 'unknown')
                print(f"  Connected to: {config.get('connected_to', 'unknown')} interface {router_iface} (gateway: {config.get('gateway_ip', 'unknown')})")
                
                secondary_ips = config.get('secondary_ips', [])
                if secondary_ips:
                    print(f"  Secondary IPs: {', '.join(secondary_ips)}")
                    
                print(f"  Created: {config.get('created_at', 'unknown')}")
                print()
            
        return True
        
    def check_prerequisites(self) -> bool:
        """Check that required tools and conditions are met."""
        if not self.check_command_availability("ip"):
            self.logger.error("'ip' command not available - required for namespace operations")
            return False
            
        # Check for root privileges
        if os.geteuid() != 0:
            self.logger.error("Root privileges required for namespace operations")
            return False
            
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Manage dynamic host namespaces in network simulation using unified mesh infrastructure",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add host with primary IP only (connects to mesh)
  %(prog)s --host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw
  
  # Add host to specific router interface mesh
  %(prog)s --host server1 --primary-ip 10.1.11.100/24 --connect-to hq-lab --router-interface eth2
  
  # Add host with secondary IPs
  %(prog)s --host db1 --primary-ip 10.2.1.100/24 --secondary-ips 192.168.100.1/24,172.16.1.1/24 --connect-to br-gw
  
  # Auto-detect router based on IP
  %(prog)s --host client1 --primary-ip 10.3.1.100/24
  
  # Remove host
  %(prog)s --host web1 --remove
  
  # List all hosts
  %(prog)s --list-hosts

Notes:
  - Hosts connect directly to existing shared mesh infrastructure
  - Hosts have one physical interface (eth0) only
  - Secondary IPs are configured on dummy interfaces
  - Hosts cannot forward packets (no routing between interfaces)
  - Compatible with nettest for ping/MTR testing
  - Requires netsetup to be run first to create mesh infrastructure
        """
    )
    
    # Action arguments
    parser.add_argument('--host', type=str, help='Host name to add or remove')
    parser.add_argument('--remove', action='store_true', help='Remove the specified host (use with --host)')
    parser.add_argument('--list-hosts', action='store_true', help='List all registered hosts')
    
    # Configuration arguments for --host
    parser.add_argument('--primary-ip', type=str, help='Primary IP address with prefix (e.g., 10.1.1.100/24)')
    parser.add_argument('--secondary-ips', type=str, help='Comma-separated secondary IPs with prefixes')
    parser.add_argument('--connect-to', type=str, help='Router to connect to (auto-detect if not specified)')
    parser.add_argument('--router-interface', type=str, help='Specific router interface bridge to connect to (e.g., eth2)')
    
    # General arguments
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity (-v for info, -vv for debug)')
    parser.add_argument('-j', '--json', action='store_true',
                       help='Output in JSON format (applies to --list-hosts)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.host and not args.list_hosts:
        parser.error("Either --host or --list-hosts is required")
    
    if args.host and args.remove and args.primary_ip:
        parser.error("--primary-ip cannot be used with --remove")
        
    if args.host and not args.remove and not args.primary_ip:
        parser.error("--primary-ip is required when adding a host")
        
    manager = HostNamespaceManager(args.verbose)
    
    if not manager.check_prerequisites():
        sys.exit(1)
        
    try:
        manager.load_router_facts()
        manager.discover_namespaces()
        
        if args.host and args.remove:
            # Remove host
            success = manager.remove_host(args.host)
            sys.exit(0 if success else 1)
            
        elif args.host:
            # Add host
            secondary_ips = []
            if args.secondary_ips:
                secondary_ips = [ip.strip() for ip in args.secondary_ips.split(',')]
                
            success = manager.add_host(args.host, args.primary_ip, secondary_ips, args.connect_to, args.router_interface)
            sys.exit(0 if success else 1)
            
        elif args.list_hosts:
            success = manager.list_hosts(json_output=args.json)
            sys.exit(0 if success else 1)
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()