#!/usr/bin/env -S python3 -B -u
"""
Sequential Network Connectivity and Path Tester

Tests connectivity and path analysis between routers using ICMP ping and/or MTR traceroute.
Tests one router at a time to avoid overwhelming the system. Supports any destination IP
(internal, external, or unknown) - follows routing tables and gateway behavior.

Features:
- ICMP ping connectivity testing (default)
- MTR traceroute path analysis with hop-by-hop data
- Combined testing with both ping and MTR
- Sequential testing to avoid network congestion
- Configurable verbosity and timing
- Supports any destination IP (follows routing)

Routing Behavior:
- Internal IPs: Routes according to configured routing tables
- External IPs: Gateway routers handle public IPs via default routes
- Unknown IPs: Follows default gateway or gets blackholed based on router type

Usage:
    # Test all routers with ping (default)
    python3 network_namespace_tester.py --all
    
    # Test all routers with MTR traceroute
    python3 network_namespace_tester.py --all --test-type mtr

    # Test specific source to any destination with both ping and MTR
    python3 network_namespace_tester.py -s 10.1.1.1 -d 8.8.8.8 --test-type both

    # Test path to external IP with MTR
    python3 network_namespace_tester.py -s 10.1.1.1 -d 1.1.1.1 --test-type mtr

Environment Variables:
    TRACEROUTE_SIMULATOR_FACTS - Directory containing router JSON facts files
"""

import argparse
import json
import os
import subprocess
import sys
import time
import ipaddress
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional



class SequentialConnectivityTester:
    """Sequential network connectivity testing for namespace simulation."""
    
    def __init__(self, verbose: int = 0, wait_time: float = 0.1, test_type: str = 'ping', json_output: bool = False,
                 ping_count: int = 3, ping_timeout: float = 3.0, mtr_count: int = 10, mtr_timeout: float = 10.0):
        facts_path = os.environ.get('TRACEROUTE_SIMULATOR_FACTS')
        if not facts_path:
            raise EnvironmentError("TRACEROUTE_SIMULATOR_FACTS environment variable must be set")
        self.facts_dir = Path(facts_path)
        self.verbose = verbose
        self.wait_time = wait_time
        self.test_type = test_type
        self.json_output = json_output
        self.ping_count = ping_count
        self.ping_timeout = ping_timeout
        self.mtr_count = mtr_count
        self.mtr_timeout = mtr_timeout
        
        self.routers = {}
        self.router_ips = {}  # router_name -> [list of IPs]
        self.ip_to_router = {}  # IP -> router_name (includes hosts) - DEPRECATED
        self.ip_to_namespaces = {}  # IP -> [list of namespace names] (supports multiple hosts with same IP)
        self.gateway_routers = set()  # Gateway routers that can handle public IPs
        self.hosts = {}  # host_name -> host_config
        self.host_namespaces = set()  # Track which namespaces are hosts
        self.host_registry_file = Path("/tmp/traceroute_hosts_registry.json")
        self.added_public_ip_hosts = set()  # Track temporarily added public IP hosts
        
        self.total_tests = 0
        self.passed_tests = 0
        self.failed_tests = 0
        
        # JSON output collection
        self.json_results = {
            "summary": {},
            "tests": []
        }
        
    def load_facts(self):
        """Load router facts and build IP mappings, including hosts from bridge registry."""
        # Load bridge registry to get hosts
        try:
            bridge_registry_file = Path("/tmp/traceroute_bridges_registry.json")
            if bridge_registry_file.exists():
                with open(bridge_registry_file, 'r') as f:
                    bridge_registry = json.load(f)
                    
                # Process all bridges
                for bridge_name, bridge_info in bridge_registry.items():
                    # Load router IPs from bridge registry
                    routers = bridge_info.get('routers', {})
                    for router_name, router_info in routers.items():
                        # Mark router as loaded even if we don't have full facts
                        if router_name not in self.routers:
                            self.routers[router_name] = {}  # Placeholder for router data
                            
                        ip_address = router_info.get('ipv4', '')
                        if ip_address and '/' in ip_address:
                            ip = ip_address.split('/')[0]
                            if not ip.startswith('127.'):
                                # Maintain backward compatibility
                                self.ip_to_router[ip] = router_name
                                # Add to new multi-namespace mapping
                                if ip not in self.ip_to_namespaces:
                                    self.ip_to_namespaces[ip] = []
                                if router_name not in self.ip_to_namespaces[ip]:
                                    self.ip_to_namespaces[ip].append(router_name)
                                    
                                if router_name in self.router_ips:
                                    self.router_ips[router_name].append(ip)
                                else:
                                    self.router_ips[router_name] = [ip]
                    
                    # Load host IPs from bridge registry
                    hosts = bridge_info.get('hosts', {})
                    for host_name, host_info in hosts.items():
                        # Mark this as a host namespace
                        self.host_namespaces.add(host_name)
                        
                        ip_address = host_info.get('ipv4', '')
                        if ip_address and '/' in ip_address:
                            ip = ip_address.split('/')[0]
                            if not ip.startswith('127.'):
                                # Maintain backward compatibility
                                self.ip_to_router[ip] = host_name
                                # Add to new multi-namespace mapping
                                if ip not in self.ip_to_namespaces:
                                    self.ip_to_namespaces[ip] = []
                                if host_name not in self.ip_to_namespaces[ip]:
                                    self.ip_to_namespaces[ip].append(host_name)
                                    
                                if host_name in self.router_ips:
                                    self.router_ips[host_name].append(ip)
                                else:
                                    self.router_ips[host_name] = [ip]
                                    
        except (json.JSONDecodeError, IOError) as e:
            if self.verbose >= 1:
                print(f"Warning: Could not load bridge registry: {e}")
                
        # Load hosts from host registry
        try:
            if self.host_registry_file.exists():
                with open(self.host_registry_file, 'r') as f:
                    hosts = json.load(f)
                    
                for host_name, host_config in hosts.items():
                    # Mark this as a host namespace
                    self.host_namespaces.add(host_name)
                    # Store host configuration
                    self.hosts[host_name] = host_config
                    
                    # Add primary IP
                    primary_ip = host_config.get('primary_ip', '')
                    if primary_ip and '/' in primary_ip:
                        ip = primary_ip.split('/')[0]
                        if not ip.startswith('127.'):
                            # Maintain backward compatibility
                            self.ip_to_router[ip] = host_name
                            # Add to new multi-namespace mapping
                            if ip not in self.ip_to_namespaces:
                                self.ip_to_namespaces[ip] = []
                            if host_name not in self.ip_to_namespaces[ip]:
                                self.ip_to_namespaces[ip].append(host_name)
                                
                            if host_name in self.router_ips:
                                if ip not in self.router_ips[host_name]:
                                    self.router_ips[host_name].append(ip)
                            else:
                                self.router_ips[host_name] = [ip]
                    
                    # Add secondary IPs
                    secondary_ips = host_config.get('secondary_ips', [])
                    for secondary_ip in secondary_ips:
                        if secondary_ip and '/' in secondary_ip:
                            ip = secondary_ip.split('/')[0]
                            if not ip.startswith('127.'):
                                # Maintain backward compatibility
                                self.ip_to_router[ip] = host_name
                                # Add to new multi-namespace mapping
                                if ip not in self.ip_to_namespaces:
                                    self.ip_to_namespaces[ip] = []
                                if host_name not in self.ip_to_namespaces[ip]:
                                    self.ip_to_namespaces[ip].append(host_name)
                                    
                                if host_name in self.router_ips:
                                    if ip not in self.router_ips[host_name]:
                                        self.router_ips[host_name].append(ip)
                                else:
                                    self.router_ips[host_name] = [ip]
                                    
        except (json.JSONDecodeError, IOError) as e:
            if self.verbose >= 1:
                print(f"Warning: Could not load host registry: {e}")
        
        # Now load router facts from JSON files
        json_files = list(self.facts_dir.glob("*.json"))
        loaded_count = 0
        
        for json_file in json_files:
            # Skip metadata files
            if "_metadata.json" in json_file.name:
                continue
                
            router_name = json_file.stem
            
            try:
                with open(json_file, 'r') as f:
                    facts = json.load(f)
                    self.routers[router_name] = facts
                    
                    # Extract IPs from network interfaces
                    interfaces_data = facts.get('network', {}).get('interfaces', {})
                    if isinstance(interfaces_data, dict) and 'parsed' in interfaces_data:
                        # New format: interfaces are in parsed object
                        parsed_interfaces = interfaces_data.get('parsed', {})
                        for iface_name, iface_data in parsed_interfaces.items():
                            if isinstance(iface_data, dict):
                                addr_info = iface_data.get('addr_info', [])
                                for addr in addr_info:
                                    if addr.get('family') == 'inet':
                                        ip = addr.get('local', '')
                                        if ip and not ip.startswith('127.'):
                                            # Maintain backward compatibility
                                            self.ip_to_router[ip] = router_name
                                            # Add to new multi-namespace mapping
                                            if ip not in self.ip_to_namespaces:
                                                self.ip_to_namespaces[ip] = []
                                            if router_name not in self.ip_to_namespaces[ip]:
                                                self.ip_to_namespaces[ip].append(router_name)
                                                
                                            if router_name in self.router_ips:
                                                self.router_ips[router_name].append(ip)
                                            else:
                                                self.router_ips[router_name] = [ip]
                    
                    # Check if this is a gateway router (has metadata indicating it's a gateway)
                    metadata_file = self.facts_dir / f"{router_name}_metadata.json"
                    if metadata_file.exists():
                        try:
                            with open(metadata_file, 'r') as mf:
                                metadata = json.load(mf)
                                if metadata.get('type') == 'gateway':
                                    self.gateway_routers.add(router_name)
                        except:
                            pass
                    
                    loaded_count += 1
                    
            except (json.JSONDecodeError, IOError) as e:
                if self.verbose >= 1:
                    print(f"Warning: Could not load {json_file}: {e}")
                    
        if self.verbose >= 1:
            print(f"Loaded {loaded_count} router facts, {len(self.router_ips)} entities with IPs")
            if self.gateway_routers and self.verbose >= 2:
                print(f"Gateway routers: {', '.join(sorted(self.gateway_routers))}")
                
        # Discover runtime IPs that may have been dynamically added
        self._discover_runtime_router_ips()
            
    def _discover_runtime_router_ips(self):
        """Discover actual router IPs from runtime namespaces to catch dynamically added IPs."""
        try:
            # Get all namespaces
            result = subprocess.run(['ip', 'netns', 'list'], capture_output=True, text=True)
            if result.returncode != 0:
                return
                
            namespaces = [line.split()[0] for line in result.stdout.strip().split('\n') if line]
            
            # Process router namespaces
            for namespace in namespaces:
                # Skip host namespaces
                if namespace in self.host_namespaces:
                    continue
                    
                # Check if this looks like a router namespace (contains router patterns)
                if any(pattern in namespace for pattern in ['befw', 'beis', 'belb', 'bens']) or namespace in self.routers:
                    # Get all IPv4 addresses from this namespace
                    cmd = f'ip netns exec {namespace} ip -4 addr show'
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        # Parse IP addresses
                        for line in result.stdout.split('\n'):
                            if 'inet ' in line and 'inet6' not in line:
                                parts = line.strip().split()
                                if len(parts) >= 2:
                                    ip_cidr = parts[1]
                                    ip = ip_cidr.split('/')[0]
                                    
                                    # Skip loopback
                                    if ip.startswith('127.'):
                                        continue
                                        
                                    # Add to IP mappings if not already present
                                    if ip not in self.ip_to_namespaces:
                                        self.ip_to_namespaces[ip] = []
                                    if namespace not in self.ip_to_namespaces[ip]:
                                        self.ip_to_namespaces[ip].append(namespace)
                                        
                                    # Add to router IPs if not already present
                                    if namespace not in self.router_ips:
                                        self.router_ips[namespace] = []
                                    if ip not in self.router_ips[namespace]:
                                        self.router_ips[namespace].append(ip)
                                        
                                    # Mark this namespace as a router if not already
                                    if namespace not in self.routers:
                                        self.routers[namespace] = {}
                                        
        except Exception as e:
            if self.verbose >= 1:
                print(f"Warning: Could not discover runtime IPs: {e}")
    
    def load_hosts(self):
        """Load host configurations from host registry."""
        self.hosts = {}
        
    def is_public_routable_ip(self, ip_str: str) -> bool:
        """
        Check if an IP is public routable (not private, not special use).
        
        Public IPs are:
        - Not in private ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
        - Not loopback (127.0.0.0/8)
        - Not link-local (169.254.0.0/16)
        - Not multicast (224.0.0.0/4)
        - Not reserved (240.0.0.0/4)
        """
        try:
            ip = ipaddress.IPv4Address(ip_str)
            
            # Check if it's a private address
            if ip.is_private:
                return False
                
            # Check if it's loopback
            if ip.is_loopback:
                return False
                
            # Check if it's link-local
            if ip.is_link_local:
                return False
                
            # Check if it's multicast
            if ip.is_multicast:
                return False
                
            # Check if it's reserved
            if ip.is_reserved:
                return False
                
            # If none of the above, it's public routable
            return True
            
        except ipaddress.AddressValueError:
            return False
            
    def find_gateway_subnet(self, gateway_router: str) -> Optional[dict]:
        """Find a suitable subnet on a gateway router for adding public IP hosts."""
        if gateway_router not in self.routers:
            return None
            
        facts = self.routers[gateway_router]
        routing_tables = facts.get('routing', {}).get('tables', [])
        
        # Look for external/public interfaces (single-router subnets) in routing tables
        for route in routing_tables:
            if (route.get('protocol') == 'kernel' and 
                route.get('scope') == 'link' and
                route.get('prefsrc') and route.get('dev') and route.get('dst')):
                
                subnet = route['dst']
                dev = route['dev']
                
                # Check if this is a single-router subnet (external interface)
                subnet_members = []
                for subnet_key, members in [(s, m) for s, m in self.load_facts_subnets().items()]:
                    if subnet_key == subnet:
                        subnet_members = members
                        break
                
                # If this subnet only has one member, it's likely an external interface
                if len(subnet_members) == 1:
                    return {
                        'subnet': subnet,
                        'interface': dev,
                        'gateway_ip': iface['prefsrc']
                    }
                    
        # Fallback: look for any suitable interface
        for iface in interfaces:
            if (iface.get('protocol') == 'kernel' and 
                iface.get('scope') == 'link' and
                iface.get('prefsrc') and iface.get('dev') and iface.get('dst')):
                
                # Skip obviously internal interfaces
                if any(internal in iface['dev'] for internal in ['lo', 'dummy']):
                    continue
                    
                return {
                    'subnet': subnet,
                    'interface': iface['dev'],
                    'gateway_ip': iface['prefsrc']
                }
                
        return None
        
    def find_gateway_for_public_ip(self, public_ip: str) -> Optional[str]:
        """
        Find which gateway router would handle a public IP.
        Returns the gateway router name or None if no gateway is available.
        """
        # For now, just return the first available gateway
        # In a real implementation, this might consider routing policies
        if self.gateway_routers:
            return sorted(self.gateway_routers)[0]
        return None
        
    def generate_public_ip_host_name(self, public_ip: str) -> str:
        """Generate a deterministic host name for a public IP."""
        # Replace dots with dashes for valid namespace name
        return f"pub-{public_ip.replace('.', '-')}"
        
    def load_facts_subnets(self) -> Dict[str, List[tuple]]:
        """Load subnet information from router facts."""
        subnets = {}
        
        for router_name, facts in self.routers.items():
            routing_tables = facts.get('routing', {}).get('tables', [])
            for route in routing_tables:
                if (route.get('protocol') == 'kernel' and 
                    route.get('scope') == 'link' and
                    route.get('prefsrc') and route.get('dev') and route.get('dst')):
                    
                    subnet = route['dst']
                    if subnet not in subnets:
                        subnets[subnet] = []
                    subnets[subnet].append((router_name, route['dev'], route['prefsrc']))
                    
        return subnets
        
    def add_public_ip_host_to_gateways(self, public_ip: str):
        """
        Add a temporary host with the public IP to all gateway routers.
        This allows testing connectivity to public IPs.
        """
        if not self.is_public_routable_ip(public_ip):
            return
            
        if public_ip in self.added_public_ip_hosts:
            return  # Already added
            
        # Find suitable gateway routers
        if not self.gateway_routers:
            if self.verbose >= 1:
                print(f"Warning: No gateway routers found for public IP {public_ip}")
            return
            
        host_name = self.generate_public_ip_host_name(public_ip)
        
        # Try to add to each gateway router
        added_to_any = False
        for gateway_router in sorted(self.gateway_routers):
            # Find a suitable subnet on this gateway
            subnet_info = self.find_gateway_subnet(gateway_router)
            if not subnet_info:
                if self.verbose >= 2:
                    print(f"No suitable subnet found on gateway {gateway_router}")
                continue
                
            # Create the host
            cmd = f"python3 {Path(__file__).parent}/host_namespace_setup.py"
            cmd += f" --host {host_name}"
            cmd += f" --primary-ip {public_ip}/32"  # Use /32 for public IPs
            cmd += f" --connect-to {gateway_router}"
            
            if self.verbose >= 2:
                print(f"Adding public IP host: {cmd}")
                
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            # Verbose level 2: show command output
            if self.verbose >= 2 and (result.stdout or result.stderr):
                print(f"Command exit code: {result.returncode}")
                if result.stdout:
                    print("Command stdout:")
                    print(result.stdout.rstrip())
                if result.stderr:
                    print("Command stderr:")
                    print(result.stderr.rstrip())
            
            if result.returncode == 0:
                added_to_any = True
                self.added_public_ip_hosts.add(public_ip)
                
                # Update our IP mappings
                self.ip_to_router[public_ip] = host_name
                if public_ip not in self.ip_to_namespaces:
                    self.ip_to_namespaces[public_ip] = []
                if host_name not in self.ip_to_namespaces[public_ip]:
                    self.ip_to_namespaces[public_ip].append(host_name)
                    
                if host_name in self.router_ips:
                    self.router_ips[host_name].append(public_ip)
                else:
                    self.router_ips[host_name] = [public_ip]
                    
                if self.verbose >= 1:
                    print(f"Added public IP host {host_name} ({public_ip}) to gateway {gateway_router}")
                    
                # Only add to one gateway for now
                break
            else:
                if self.verbose >= 2:
                    print(f"Failed to add public IP host to {gateway_router}: {result.stderr}")
                    
        if not added_to_any and self.verbose >= 1:
            print(f"Warning: Could not add public IP host for {public_ip} to any gateway")
            
    def remove_public_ip_host_from_gateways(self, public_ip: str):
        """Remove a temporary public IP host."""
        if public_ip not in self.added_public_ip_hosts:
            return
            
        host_name = self.generate_public_ip_host_name(public_ip)
        
        # Remove the host
        cmd = f"python3 {Path(__file__).parent}/host_namespace_setup.py"
        cmd += f" --host {host_name} --remove"
        
        if self.verbose >= 2:
            print(f"Removing public IP host: {cmd}")
            
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        # Verbose level 2: show command output
        if self.verbose >= 2 and (result.stdout or result.stderr):
            print(f"Command exit code: {result.returncode}")
            if result.stdout:
                print("Command stdout:")
                print(result.stdout.rstrip())
            if result.stderr:
                print("Command stderr:")
                print(result.stderr.rstrip())
        
        if result.returncode == 0:
            self.added_public_ip_hosts.discard(public_ip)
            
            # Update our IP mappings
            if public_ip in self.ip_to_router:
                del self.ip_to_router[public_ip]
            if public_ip in self.ip_to_namespaces:
                self.ip_to_namespaces[public_ip] = [ns for ns in self.ip_to_namespaces[public_ip] if ns != host_name]
                if not self.ip_to_namespaces[public_ip]:
                    del self.ip_to_namespaces[public_ip]
                    
            if host_name in self.router_ips:
                del self.router_ips[host_name]
                
            if self.verbose >= 1:
                print(f"Removed public IP host {host_name} ({public_ip})")
        else:
            if self.verbose >= 2:
                print(f"Failed to remove public IP host: {result.stderr}")
                
    def cleanup_all_public_ip_hosts(self):
        """Remove all temporary public IP hosts that were added."""
        if not self.added_public_ip_hosts:
            return
            
        if self.verbose >= 1:
            print(f"\nCleaning up {len(self.added_public_ip_hosts)} temporary public IP hosts...")
            
        # Copy the set since we'll be modifying it
        public_ips = list(self.added_public_ip_hosts)
        for public_ip in public_ips:
            # Extract just the IP if it includes a port
            parts = public_ip.split(':')
            if len(parts) == 4:
                public_ip = '.'.join(parts)
                self.remove_public_ip_host_from_gateways(public_ip)
                
    def ping_test_from_namespace(self, namespace: str, source_ip: str, dest_ip: str, timeout: int = 3, count: int = 3) -> Tuple[bool, str, str]:
        """Perform ping test from a specific namespace using source IP to destination IP.
        
        Allows any destination IP - follows routing tables and gateway behavior.
        
        Returns:
            Tuple[bool, str, str]: (success, summary, full_output)
        """
        # Verbose level 3: show input variables
        if self.verbose >= 3:
            print(f"\nDEBUG: ping_test_from_namespace() called with:")
            print(f"  namespace: {namespace}")
            print(f"  source_ip: {source_ip}")
            print(f"  dest_ip: {dest_ip}")
            print(f"  timeout: {timeout}")
        
        # First, determine which router this namespace routes through
        router_info = ""
        if namespace in self.host_namespaces:
            # Get the connected router for this host
            connected_router = self.hosts.get(namespace, {}).get('connected_to', 'unknown')
            router_info = f" via {connected_router}"
        
        # Determine which namespace(s) have the destination IP
        dest_namespaces = self.ip_to_namespaces.get(dest_ip, [])
        dest_info = ""
        if dest_namespaces and namespace in self.host_namespaces:
            # For hosts, determine which destination is reachable based on the router
            connected_router = self.hosts.get(namespace, {}).get('connected_to')
            if connected_router:
                # Find destinations on the same router
                reachable_dests = []
                for dest_ns in dest_namespaces:
                    if dest_ns in self.host_namespaces:
                        # Check if this destination host is on the same router
                        dest_router = self.hosts.get(dest_ns, {}).get('connected_to')
                        if dest_router == connected_router:
                            reachable_dests.append(dest_ns)
                    elif dest_ns == connected_router:
                        # Destination is the router itself
                        reachable_dests.append(dest_ns)
                
                if reachable_dests:
                    if len(reachable_dests) == 1:
                        dest_info = f" (reaching {reachable_dests[0]})"
                    else:
                        dest_info = f" (reaching one of: {', '.join(reachable_dests)})"
                else:
                    # No local destinations, must route to another router
                    dest_info = f" (routed to remote: {', '.join(dest_namespaces)})"
        elif dest_namespaces:
            # For routers or unknown sources, show all possible destinations
            if len(dest_namespaces) == 1:
                dest_info = f" (reaching {dest_namespaces[0]})"
            else:
                dest_info = f" (reaching one of: {', '.join(dest_namespaces)})"
        
        # Run ping from specified namespace
        cmd = f"ip netns exec {namespace} ping -c {count} -W {timeout} -I {source_ip} {dest_ip}"
        
        # Verbose level 2: show namespace command
        if self.verbose >= 2:
            print(f"\nExecuting namespace command: {cmd}")
        
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout+2
            )
            
            # Verbose level 2: show command output
            if self.verbose >= 2:
                print(f"Command exit code: {result.returncode}")
                if result.stdout:
                    print("Command stdout:")
                    print(result.stdout.rstrip())
                if result.stderr:
                    print("Command stderr:")
                    print(result.stderr.rstrip())
            
            if result.returncode == 0:
                # Extract RTT from output
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'bytes from' in line and 'time=' in line:
                        # Extract time value
                        time_part = line.split('time=')[1].split()[0]
                        return True, f"Reply from {dest_ip}: time={time_part}", result.stdout
                        
                return True, f"Ping successful", result.stdout
            else:
                # Parse error message
                if "Destination Host Unreachable" in result.stderr or "Destination Host Unreachable" in result.stdout:
                    return False, "Destination Host Unreachable", result.stdout + result.stderr
                elif "Network is unreachable" in result.stderr or "Network is unreachable" in result.stdout:
                    return False, "Network is unreachable", result.stdout + result.stderr
                elif "100% packet loss" in result.stdout:
                    return False, "Request timed out (100% packet loss)", result.stdout
                else:
                    return False, f"Ping failed (code {result.returncode})", result.stdout + result.stderr
                    
        except subprocess.TimeoutExpired:
            return False, f"Command timeout after {timeout+2}s", ""
        except Exception as e:
            return False, f"Error: {str(e)}", ""
    
    def ping_test(self, source_ip: str, dest_ip: str, timeout: int = 3, count: int = 3) -> Tuple[bool, str, str]:
        """Legacy ping test - uses first namespace with source IP.
        
        DEPRECATED: Use ping_test_from_namespace for multiple namespace support.
        
        Returns:
            Tuple[bool, str, str]: (success, summary, full_output)
        """
        source_router = self.ip_to_router.get(source_ip)
        
        if not source_router:
            return False, f"Source IP {source_ip} not found", ""
            
        # Use the new function with the single namespace
        return self.ping_test_from_namespace(source_router, source_ip, dest_ip, timeout, count)
        
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout+2
            )
            
            # Prepare full output with command and result
            full_output = f"Command: {cmd}\n"
            full_output += f"Exit code: {result.returncode}\n"
            if result.stdout.strip():
                full_output += f"STDOUT:\n{result.stdout.strip()}"
            if result.stderr.strip():
                full_output += f"\nSTDERR:\n{result.stderr.strip()}"
            
            if result.returncode == 0:
                # Extract RTT from ping output for summary
                for line in result.stdout.split('\n'):
                    if 'time=' in line and 'ms' in line:
                        time_part = line.split('time=')[-1]
                        rtt = time_part.split()[0]
                        return True, f"{rtt}", full_output
                return True, "Success", full_output
            else:
                # Parse common error messages for summary
                if "Destination Host Unreachable" in result.stdout:
                    summary = "Host unreachable"
                elif "Network is unreachable" in result.stdout:
                    summary = "Network unreachable"
                elif "100% packet loss" in result.stdout:
                    summary = "100% packet loss"
                else:
                    summary = f"Failed (code {result.returncode})"
                return False, summary, full_output
                    
        except subprocess.TimeoutExpired:
            timeout_output = f"Command: {cmd}\nExit code: timeout\nCommand timed out after {timeout+2} seconds"
            return False, "Command timeout", timeout_output
        except Exception as e:
            exception_output = f"Command: {cmd}\nExit code: exception\nException occurred: {str(e)}"
            return False, f"Exception: {str(e)[:50]}", exception_output
            
    def mtr_test_from_namespace(self, namespace: str, source_ip: str, dest_ip: str, timeout: int = 10, count: int = 10) -> Tuple[bool, str, str]:
        """Perform MTR traceroute test from a specific namespace using source IP to destination IP.
        
        Allows any destination IP - follows routing tables and gateway behavior.
        
        Returns:
            Tuple[bool, str, str]: (success, summary, full_output)
        """
        # Verbose level 3: show input variables
        if self.verbose >= 3:
            print(f"\nDEBUG: mtr_test_from_namespace() called with:")
            print(f"  namespace: {namespace}")
            print(f"  source_ip: {source_ip}")
            print(f"  dest_ip: {dest_ip}")
            print(f"  timeout: {timeout}")
        
        # Run mtr from specified namespace
        # Use -r for report mode, -c for probe count, -n for no DNS, -Z for timeout, -G for interval
        cmd = f"ip netns exec {namespace} mtr -r -c {count} -n -Z {timeout} -G 1 -a {source_ip} {dest_ip}"
        
        # Verbose level 2: show namespace command
        if self.verbose >= 2:
            print(f"\nExecuting namespace command: {cmd}")
        
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout+2
            )
            
            # Verbose level 2: show command output
            if self.verbose >= 2:
                print(f"Command exit code: {result.returncode}")
                if result.stdout:
                    print("Command stdout:")
                    print(result.stdout.rstrip())
                if result.stderr:
                    print("Command stderr:")
                    print(result.stderr.rstrip())
            
            if result.returncode == 0:
                # Parse MTR output to count hops and check completion
                lines = result.stdout.strip().split('\n')
                hop_count = 0
                reached_dest = False
                
                for line in lines:
                    # Skip header lines
                    if line.strip() and not line.startswith('Start:') and not line.startswith('HOST:'):
                        parts = line.split()
                        if len(parts) >= 2:
                            hop_count += 1
                            # Check if we reached the destination
                            if parts[1] == dest_ip:
                                reached_dest = True
                                
                if reached_dest:
                    return True, f"Reached in {hop_count} hops", result.stdout
                else:
                    return True, f"Traced {hop_count} hops", result.stdout
            else:
                # Parse error
                if "mtr: can't find interface" in result.stderr:
                    return False, "Invalid source interface", result.stdout + result.stderr
                else:
                    return False, f"MTR failed (code {result.returncode})", result.stdout + result.stderr
                    
        except subprocess.TimeoutExpired:
            return False, f"Command timeout after {timeout+2}s", ""
        except Exception as e:
            return False, f"Error: {str(e)}", ""
    
    def mtr_test(self, source_ip: str, dest_ip: str, timeout: int = 10, count: int = 10) -> Tuple[bool, str, str]:
        """Legacy MTR test - uses first namespace with source IP.
        
        DEPRECATED: Use mtr_test_from_namespace for multiple namespace support.
        
        Returns:
            Tuple[bool, str, str]: (success, summary, full_output)
        """
        source_router = self.ip_to_router.get(source_ip)
        
        if not source_router:
            return False, f"Source IP {source_ip} not found", ""
            
        # Use the new function with the single namespace
        return self.mtr_test_from_namespace(source_router, source_ip, dest_ip, timeout, count)
            
    def _handle_test_result(self, source_router: str, dest_router: str, source_ip: str, dest_ip: str,
                           success: bool, summary: str, full_output: str, test_type: str,
                           router_passed: int, router_failed: int, source_namespace: str = None,
                           dest_namespace: str = None) -> Tuple[int, int]:
        """Handle test result output and statistics."""
        # Determine actual source namespace data
        if source_namespace:
            # Use the provided namespace
            src_ns = source_namespace
            src_type = "host" if source_namespace in self.host_namespaces else "router"
        else:
            # Fallback to router
            src_ns = source_router
            src_type = "router"
        
        # Determine actual destination namespace data
        if dest_namespace:
            dest_ns = dest_namespace
            dest_type = "host" if dest_namespace in self.host_namespaces else "router"
            is_external = False
        else:
            # No destination namespace - it's external or unknown
            dest_ns = None
            dest_type = None
            is_external = True
        
        # Determine which router is being used
        router = None
        if source_namespace and source_namespace in self.host_namespaces:
            # Source is a host, use its connected router
            router = source_router
        elif src_type == "router":
            # Source itself is a router
            router = src_ns
        
        # Collect JSON data
        test_result = {
            "source": {
                "namespace": src_ns,
                "namespace_type": src_type,
                "ip": source_ip
            },
            "destination": {
                "namespace": dest_ns,
                "namespace_type": dest_type,
                "ip": dest_ip
            },
            "router": router,
            "test_type": test_type,
            "success": success,
            "summary": summary,
            "output": full_output  # Always include the actual test output
        }
        
        # Parse ping-specific data from output if it's a ping test
        if test_type.upper() == 'PING' and full_output:
            # Extract ping statistics
            lines = full_output.strip().split('\n')
            for line in lines:
                if 'packets transmitted' in line:
                    # Parse: "3 packets transmitted, 3 received, 0% packet loss"
                    parts = line.split(',')
                    if len(parts) >= 3:
                        transmitted = parts[0].strip().split()[0]
                        received = parts[1].strip().split()[0]
                        loss = parts[2].strip().split()[0].rstrip('%')
                        test_result["ping_stats"] = {
                            "packets_transmitted": int(transmitted),
                            "packets_received": int(received),
                            "packet_loss_percent": float(loss)
                        }
                elif 'rtt min/avg/max/mdev' in line:
                    # Parse: "rtt min/avg/max/mdev = 2.269/2.327/2.359/0.041 ms"
                    parts = line.split('=')[1].strip().split()[0].split('/')
                    if len(parts) == 4:
                        test_result["ping_rtt"] = {
                            "min": float(parts[0]),
                            "avg": float(parts[1]),
                            "max": float(parts[2]),
                            "mdev": float(parts[3])
                        }
        
        # Parse MTR-specific data from output if it's an MTR test
        if test_type.upper() == 'MTR' and full_output:
            # Extract hop information from MTR output
            hops = []
            lines = full_output.strip().split('\n')
            for line in lines:
                # MTR output format: "1.|-- 10.1.1.1  0.0%  1  0.5  0.5  0.5  0.5  0.0"
                if line.strip() and ('|--' in line or '`--' in line):
                    parts = line.split()
                    if len(parts) >= 3:
                        hop_num = parts[0].rstrip('.')
                        hop_ip = parts[1]
                        # Try to map IP to namespace/router name
                        hop_namespaces = self.ip_to_namespaces.get(hop_ip, [])
                        hop_name = hop_namespaces[0] if hop_namespaces else hop_ip
                        hops.append({
                            "hop": hop_num,
                            "ip": hop_ip,
                            "namespace": hop_name,
                            "namespace_type": "host" if hop_name in self.host_namespaces else "router" if hop_namespaces else "unknown"
                        })
            
            if hops:
                test_result["mtr_hops"] = hops
            
        self.json_results["tests"].append(test_result)
        
        # Handle regular output (if not JSON mode)
        if not self.json_output:
            # Handle verbosity levels  
            if self.verbose == 1:
                # -v: compact single line format
                status = f"PASS: {summary}" if success else f"FAIL: {summary}"
                dest_display = dest_router if dest_router else "external"
                print(f"    {source_router} ({source_ip}) -> {dest_display} ({dest_ip}) [{test_type}] {status}")
            elif self.verbose >= 2:
                # -vv/-vvv: detailed format
                if self.verbose >= 3:
                    # -vvv: include full output
                    print(f"\nFull {test_type} output:")
                    print(full_output)
                    print()
                    
                # Pass/fail message
                if success:
                    print(f"✓ {test_type} PASS: {summary}")
                else:
                    print(f"✗ {test_type} FAIL: {summary}")
                
        # Update statistics
        self.total_tests += 1
        if success:
            self.passed_tests += 1
            router_passed += 1
        else:
            self.failed_tests += 1
            router_failed += 1
            
        return router_passed, router_failed
        
    def test_router_to_all_others(self, source_router: str):
        """Test connectivity from one router to all others."""
        source_ips = self.router_ips.get(source_router, [])
        
        if not source_ips:
            if self.verbose >= 1 and not self.json_output:
                print(f"✗ {source_router} has no IP addresses")
            return
            
        # Use first available IP as source
        source_ip = source_ips[0]
        
        if self.verbose >= 1 and not self.json_output:
            print(f"\nTesting from {source_router} ({source_ip}):")
            
        router_passed = 0
        router_failed = 0
        
        # Test to all other routers
        for dest_router in sorted(self.routers.keys()):
            if dest_router == source_router:
                continue
                
            dest_ips = self.router_ips.get(dest_router, [])
            if not dest_ips:
                continue
                
            # Use first available IP as destination
            dest_ip = dest_ips[0]
            
            # Wait between tests
            if self.wait_time > 0:
                time.sleep(self.wait_time)
                
            # Run test based on test_type
            if self.test_type in ['ping', 'both']:
                success, summary, full_output = self.ping_test(source_ip, dest_ip, self.ping_timeout, self.ping_count)
                router_passed, router_failed = self._handle_test_result(
                    source_router, dest_router, source_ip, dest_ip,
                    success, summary, full_output, 'PING',
                    router_passed, router_failed,
                    source_namespace=source_router,
                    dest_namespace=dest_router
                )
                
            if self.test_type in ['mtr', 'both']:
                success, summary, full_output = self.mtr_test(source_ip, dest_ip, self.mtr_timeout, self.mtr_count)
                router_passed, router_failed = self._handle_test_result(
                    source_router, dest_router, source_ip, dest_ip,
                    success, summary, full_output, 'MTR',
                    router_passed, router_failed,
                    source_namespace=source_router,
                    dest_namespace=dest_router
                )
                
        # Router summary
        total = router_passed + router_failed
        if total > 0:
            if self.verbose >= 1 and not self.json_output:
                if router_failed == 0:
                    print(f"  ✓ {source_router} passed all {router_passed} tests")
                else:
                    print(f"  ⚠ {source_router} passed {router_passed}/{total} tests")
            
            if router_failed > 0 and not self.json_output:
                print(f"  ⚠ {source_router} has {router_failed} failures - CRITICAL ISSUE!")
            
    def test_specific_pair(self, source_ip: str, dest_ip: str):
        """Test specific source to destination from all namespaces that have the source IP."""
        if self.verbose >= 1 and not self.json_output:
            print(f"\n=== Testing {source_ip} → {dest_ip} ===")
        
        # Get all namespaces that have this source IP
        source_namespaces = self.ip_to_namespaces.get(source_ip, [])
        
        if not source_namespaces:
            if self.json_output:
                # For JSON output, add an error entry
                self.json_results["tests"].append({
                    "error": f"Source IP {source_ip} not found in any namespace",
                    "source": {"ip": source_ip},
                    "destination": {"ip": dest_ip},
                    "success": False
                })
            elif self.verbose >= 1:
                print(f"✗ Source IP {source_ip} not found in any namespace")
            return False
            
        # Get all namespaces that have this destination IP
        dest_namespaces = self.ip_to_namespaces.get(dest_ip, [])
        
        # Sort namespaces numerically by extracting numbers from names
        def extract_number(name):
            # Extract number from names like "source-1", "destination-2", etc.
            import re
            match = re.search(r'-(\d+)$', name)
            if match:
                return int(match.group(1))
            return 0
        
        source_namespaces = sorted(source_namespaces, key=extract_number)
        dest_namespaces = sorted(dest_namespaces, key=extract_number)
            
        # Add temporary host with public IP to gateway routers if needed
        if self.is_public_routable_ip(dest_ip):
            self.add_public_ip_host_to_gateways(dest_ip)
            
        # Print source and destination info once (already sorted)
        if self.verbose >= 1 and not self.json_output:
            if len(source_namespaces) > 1:
                print(f"Found {len(source_namespaces)} namespaces with source IP {source_ip}: {', '.join(source_namespaces)}")
            if dest_namespaces:
                if len(dest_namespaces) > 1:
                    print(f"Found {len(dest_namespaces)} namespaces with destination IP {dest_ip}: {', '.join(dest_namespaces)}")
                else:
                    print(f"Destination namespace: {dest_namespaces[0]}")
            else:
                public_marker = " [PUBLIC IP]" if self.is_public_routable_ip(dest_ip) else ""
                print(f"Destination IP: {dest_ip} (external/unknown){public_marker}")
        
        overall_success = True
        test_count = 0
        
        # Test from each source namespace to the destination IP
        for src_idx, source_namespace in enumerate(source_namespaces):
            test_count += 1
            
            # Determine router and destination for header
            router_name = "direct"
            dest_name = dest_ip
            
            if source_namespace in self.host_namespaces:
                router_name = self.hosts.get(source_namespace, {}).get('connected_to', 'unknown')
                
                # Find which destination namespace will be reached
                dest_namespaces = self.ip_to_namespaces.get(dest_ip, [])
                if dest_namespaces:
                    for dest_ns in dest_namespaces:
                        if dest_ns in self.host_namespaces:
                            dest_router = self.hosts.get(dest_ns, {}).get('connected_to')
                            if dest_router == router_name:
                                dest_name = dest_ns
                                break
                        elif dest_ns == router_name:
                            dest_name = dest_ns
                            break
            
            if self.verbose >= 1 and not self.json_output:
                print(f"\n=== Testing {source_namespace} ({source_ip}) -> {dest_name} ({dest_ip}) via {router_name} ===")
            
            namespace_success = True
            
            try:
                # Determine which command to run
                # Note: These are the direct namespace commands, not using our wrapper functions
                # The wrapper functions handle the logic; these are just for display/output
                if self.test_type == 'ping':
                    test_commands = [('ping', f'ping -c {self.ping_count} -W {int(self.ping_timeout)} -i 1 -I {source_ip} {dest_ip}')]
                elif self.test_type == 'mtr':
                    test_commands = [('mtr', f'mtr --report -c {self.mtr_count} -n -Z {int(self.mtr_timeout)} -G 1 {dest_ip}')]
                else:  # both
                    test_commands = [
                        ('ping', f'ping -c {self.ping_count} -W {int(self.ping_timeout)} -i 1 -I {source_ip} {dest_ip}'),
                        ('mtr', f'mtr --report -c {self.mtr_count} -n -Z {int(self.mtr_timeout)} -G 1 {dest_ip}')
                    ]
                
                namespace_success = True
                
                # Run each test command
                for test_name, test_cmd in test_commands:
                    # Verbose level 3: show test command details
                    if self.verbose >= 3:
                        print(f"\nDEBUG: Running {test_name} test:")
                        print(f"  test_cmd: {test_cmd}")
                    
                    # Run the command in the namespace
                    full_cmd = f"ip netns exec {source_namespace} {test_cmd}"
                    
                    # Verbose level 2: show namespace command
                    if self.verbose >= 2:
                        print(f"\nExecuting namespace command: {full_cmd}")
                    
                    try:
                        # Check if we're in interactive mode
                        is_interactive = sys.stdin.isatty()
                        
                        if is_interactive and self.verbose >= 1:
                            # Interactive mode: stream output in real-time
                            process = subprocess.Popen(
                                full_cmd, shell=True, stdout=subprocess.PIPE, 
                                stderr=subprocess.STDOUT, text=True
                            )
                            
                            stdout_lines = []
                            stderr_lines = []
                            
                            # For MTR, we need to wait for it to complete before reading
                            # because it outputs everything at once when using --report
                            if test_name == 'mtr':
                                stdout, _ = process.communicate()
                                if stdout:
                                    for line in stdout.rstrip('\n').split('\n'):
                                        print(line)
                                
                                success = process.returncode == 0
                                result = type('Result', (), {
                                    'returncode': process.returncode,
                                    'stdout': stdout,
                                    'stderr': ''
                                })
                            else:
                                # For ping, just wait for completion
                                stdout, _ = process.communicate()
                                if stdout:
                                    print(stdout.rstrip())
                                
                                success = process.returncode == 0
                                result = type('Result', (), {
                                    'returncode': process.returncode,
                                    'stdout': stdout,
                                    'stderr': ''
                                })
                        else:
                            # Batch mode: capture output normally
                            result = subprocess.run(
                                full_cmd, shell=True, capture_output=True, text=True
                            )
                            
                            success = result.returncode == 0
                        
                        # In interactive mode with verbose >= 1, output was already streamed
                        if not (is_interactive and self.verbose >= 1):
                            if self.verbose >= 2:
                                print(f"\nFull {test_name.upper()} output from {source_namespace}:")
                                if result.stdout:
                                    # Indent each line of the full output
                                    indented_output = "\n".join([f"  {line}" for line in result.stdout.split('\n')])
                                    print(indented_output)
                                else:
                                    print("  No output captured")
                            
                            if self.verbose == 1:
                                # -v: Show command output directly
                                if test_name == 'ping':
                                    # Show ping output (success or failure)
                                    if result.stdout:
                                        print(result.stdout.strip())
                                    elif result.stderr:
                                        print(f"Ping failed: {result.stderr.strip()}")
                                    else:
                                        print(f"Ping failed: exit code {result.returncode}")
                                elif test_name == 'mtr':
                                    # Show MTR output as-is
                                    if result.stdout:
                                        print(result.stdout.strip())
                                    elif result.stderr:
                                        print(f"MTR failed: {result.stderr.strip()}")
                                    else:
                                        print(f"MTR failed: exit code {result.returncode}")
                        
                        namespace_success = namespace_success and success
                        
                        # Collect test result for JSON output
                        if self.json_output or self.verbose >= 1:
                            # Determine source router name
                            source_router = source_namespace
                            if source_namespace in self.host_namespaces:
                                source_router = self.hosts.get(source_namespace, {}).get('connected_to', source_namespace)
                            
                            # Create summary based on success
                            if success:
                                summary = f"{test_name.upper()} successful"
                            else:
                                summary = f"{test_name.upper()} failed (exit code {result.returncode})"
                            
                            # Determine destination namespace
                            dest_namespace_val = dest_name if dest_name != dest_ip else None
                            
                            # Handle test result
                            self._handle_test_result(
                                source_router, dest_name if dest_name != dest_ip else None,
                                source_ip, dest_ip,
                                success, summary, result.stdout or "",
                                test_name.upper(),
                                0, 0,  # We'll update stats differently
                                source_namespace=source_namespace,
                                dest_namespace=dest_namespace_val
                            )
                        
                    except Exception as e:
                        if self.verbose >= 1 and not self.json_output:
                            print(f"{test_name.upper()} error: {str(e)}")
                        namespace_success = False
                        
                        # Record error in JSON
                        if self.json_output:
                            self._handle_test_result(
                                source_namespace, None,
                                source_ip, dest_ip,
                                False, f"{test_name.upper()} error: {str(e)}", "",
                                test_name.upper(),
                                0, 0,
                                source_namespace=source_namespace,
                                dest_namespace=None
                            )
                
                overall_success = overall_success and namespace_success
                
            except Exception as e:
                if self.verbose >= 1:
                    print(f"✗ Test failed from {source_namespace}: {e}")
                overall_success = False
        
        # Clean up temporary public IP host if we added it
        if self.is_public_routable_ip(dest_ip):
            self.remove_public_ip_host_from_gateways(dest_ip)
            
        return overall_success
            
    def test_all_connectivity(self):
        """Test all routers sequentially."""
        if self.verbose >= 1 and not self.json_output:
            print("\n=== Testing All Routers ===")
            print(f"Test type: {self.test_type}")
            print(f"Wait time between tests: {self.wait_time}s")
            print(f"Total routers to test: {len(self.routers)}")
            
        # Test each router to all others
        for source_router in sorted(self.routers.keys()):
            self.test_router_to_all_others(source_router)
            
            # Wait between routers
            if self.wait_time > 0:
                time.sleep(self.wait_time)
                
    def print_final_summary(self):
        """Print final summary of all tests."""
        if self.total_tests == 0:
            return
            
        pass_rate = (self.passed_tests / self.total_tests) * 100 if self.total_tests > 0 else 0
        
        # Update JSON summary
        self.json_results["summary"] = {
            "total_tests": self.total_tests,
            "passed": self.passed_tests,
            "failed": self.failed_tests,
            "pass_rate": round(pass_rate, 1),
            "all_passed": self.failed_tests == 0
        }
        
        if self.json_output:
            # Output JSON
            print(json.dumps(self.json_results, indent=2))
        else:
            # Regular output
            print("\n" + "="*50)
            print("FINAL SUMMARY")
            print("="*50)
            print(f"Total tests: {self.total_tests}")
            print(f"Passed: {self.passed_tests}")
            print(f"Failed: {self.failed_tests}")
            print(f"Pass rate: {pass_rate:.1f}%")
            
            if self.failed_tests == 0:
                print("\n✓ ALL TESTS PASSED")
            else:
                print(f"\n⚠ {self.failed_tests} TESTS FAILED")
            
    def run_tests(self, source_ip: str = None, dest_ip: str = None, test_all: bool = False):
        """Run connectivity tests."""
        # Reset statistics
        self.total_tests = 0
        self.passed_tests = 0
        self.failed_tests = 0
        
        if test_all:
            self.test_all_connectivity()
        elif source_ip and dest_ip:
            success = self.test_specific_pair(source_ip, dest_ip)
            # Statistics are already updated via _handle_test_result
            # Just ensure we have the right counts
            if self.total_tests == 0:
                # If no tests were recorded (e.g., source IP not found), set stats manually
                self.total_tests = 1
                if success:
                    self.passed_tests = 1
                else:
                    self.failed_tests = 1
        else:
            print("Error: Must specify either --all or both -s and -d")
            return False
            
        # Clean up any temporary public IP hosts
        self.cleanup_all_public_ip_hosts()
        
        # Print final summary
        self.print_final_summary()
            
        return self.failed_tests == 0


def main():
    parser = argparse.ArgumentParser(
        description='Test network connectivity in namespace simulation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test all routers with ping (default)
  %(prog)s --all
  
  # Test all routers with MTR traceroute
  %(prog)s --all --test-type mtr
  
  # Test specific connection with ping
  %(prog)s -s 10.1.1.1 -d 10.2.1.1
  
  # Test to public IP with both ping and MTR
  %(prog)s -s 10.1.1.1 -d 8.8.8.8 --test-type both -v
  
  # Test with increased verbosity
  %(prog)s -s 10.1.1.1 -d 10.2.1.1 -vv
  
  # Test with full output
  %(prog)s -s 10.1.1.1 -d 10.2.1.1 -vvv
"""
    )
    
    # Test selection
    test_group = parser.add_mutually_exclusive_group(required=True)
    test_group.add_argument('--all', action='store_true',
                           help='Test all routers to all others')
    test_group.add_argument('-s', '--source', 
                           help='Source IP address')
    
    parser.add_argument('-d', '--dest', '--destination',
                       help='Destination IP address (required with -s)')
    
    # Test type
    parser.add_argument('--test-type', choices=['ping', 'mtr', 'both'],
                       default='ping',
                       help='Type of connectivity test (default: ping)')
    
    # Options
    parser.add_argument('-w', '--wait', type=float, default=0.1,
                       help='Wait time between tests in seconds (default: 0.1)')
    parser.add_argument('-j', '--json', action='store_true',
                       help='Output in JSON format')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity (-v: summary, -vv: details, -vvv: full output)')
    
    # Test parameters
    parser.add_argument('--count', type=int, default=None,
                       help='Number of packets/probes to send (default: 3 for ping, 10 for mtr)')
    parser.add_argument('--timeout', type=float, default=None,
                       help='Timeout in seconds (default: 3.0 for ping, 10.0 for mtr)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.source and not args.dest:
        parser.error("-s/--source requires -d/--dest")
    if args.dest and not args.source:
        parser.error("-d/--dest requires -s/--source")
        
    # Check for root privileges
    if os.geteuid() != 0:
        print("Error: This script requires root privileges")
        print("Please run: sudo -E python3 network_namespace_tester.py ...")
        sys.exit(1)
        
    try:
        # Determine count and timeout based on test type and arguments
        if args.test_type == 'ping':
            ping_count = args.count if args.count is not None else 3
            ping_timeout = args.timeout if args.timeout is not None else 3.0
            mtr_count = 10  # default
            mtr_timeout = 10.0  # default
        elif args.test_type == 'mtr':
            ping_count = 3  # default
            ping_timeout = 3.0  # default
            mtr_count = args.count if args.count is not None else 10
            mtr_timeout = args.timeout if args.timeout is not None else 10.0
        else:  # both
            ping_count = args.count if args.count is not None else 3
            ping_timeout = args.timeout if args.timeout is not None else 3.0
            mtr_count = args.count if args.count is not None else 10
            mtr_timeout = args.timeout if args.timeout is not None else 10.0
        
        # Create tester
        tester = SequentialConnectivityTester(
            verbose=args.verbose,
            wait_time=args.wait,
            test_type=args.test_type,
            json_output=args.json,
            ping_count=ping_count,
            ping_timeout=ping_timeout,
            mtr_count=mtr_count,
            mtr_timeout=mtr_timeout
        )
        
        # Load facts
        tester.load_facts()
        
        if not tester.routers and not tester.router_ips:
            print("Error: No routers found in facts directory")
            print("Please run 'make netsetup' first to create namespace simulation")
            sys.exit(1)
            
        # Run tests
        success = tester.run_tests(
            source_ip=args.source,
            dest_ip=args.dest,
            test_all=args.all
        )
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        # Clean up any temporary hosts
        if 'tester' in locals():
            tester.cleanup_all_public_ip_hosts()
        sys.exit(130)
    except Exception as e:
        print(f"\nError: {e}")
        if args.verbose >= 2:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()