#!/usr/bin/env -S python3 -B -u
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
import time
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple
import posix_ipc
import hashlib

# Import configuration loader
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config_loader import get_registry_paths


class HostNamespaceManager:
    """
    Manages dynamic host namespaces in the network simulation.
    
    Hosts are endpoint devices with single physical interface and simple routing.
    They can be dynamically added to and removed from the running network simulation.
    """
    
    def __init__(self, verbose: int = 0, no_delay: bool = False):
        self.verbose = verbose
        self.no_delay = no_delay
        self.setup_logging()
        
        # Network state
        self.routers: Dict[str, Dict] = {}
        self.router_subnets: Dict[str, List[tuple]] = {}  # subnet -> [(router, interface, ip)]
        self.available_namespaces: Set[str] = set()
        
        # Load registry paths from configuration
        registry_paths = get_registry_paths()
        self.host_registry_file = Path(registry_paths['hosts'])
        self.router_registry_file = Path(registry_paths['routers'])
        self.interface_registry_file = Path(registry_paths['interfaces'])
        self.bridge_registry_file = Path(registry_paths['bridges'])
        
        self.interface_registry: Dict[str, Dict[str, str]] = {}  # host_code -> {interface_name -> interface_code}
        
        # Initialize semaphores for atomic registry operations
        self._init_semaphores()
        
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
    
    def _init_semaphores(self):
        """Initialize POSIX semaphores for registry files."""
        # Semaphore names for each registry
        self.sem_names = {
            str(self.host_registry_file): "/tsim_hosts_reg",
            str(self.router_registry_file): "/tsim_routers_reg", 
            str(self.interface_registry_file): "/tsim_interfaces_reg",
            str(self.bridge_registry_file): "/tsim_bridges_reg"
        }
        
        # Create or open semaphores
        self.semaphores = {}
        for path, sem_name in self.sem_names.items():
            try:
                # Try to create semaphore with initial value 1 and group permissions
                # Clear umask temporarily to ensure permissions are set correctly
                old_umask = os.umask(0)
                try:
                    sem = posix_ipc.Semaphore(sem_name, flags=posix_ipc.O_CREX, initial_value=1, mode=0o660)
                finally:
                    os.umask(old_umask)  # Restore original umask
                self.semaphores[path] = sem
                self.logger.debug(f"Created semaphore {sem_name}")
            except posix_ipc.ExistentialError:
                # Semaphore exists, open it
                sem = posix_ipc.Semaphore(sem_name)
                self.semaphores[path] = sem
                self.logger.debug(f"Opened existing semaphore {sem_name}")
    
    def _atomic_json_operation(self, file_path: str, operation, timeout: float = 5.0):
        """Perform atomic JSON file operation using semaphore locking.
        
        Args:
            file_path: Path to the JSON file
            operation: Function that takes current data and returns (success, result/updated_data)
            timeout: Semaphore acquire timeout in seconds
        """
        path_str = str(file_path)
        sem = self.semaphores.get(path_str)
        
        if not sem:
            # Create semaphore for unknown file
            path_hash = hashlib.md5(path_str.encode()).hexdigest()[:8]
            sem_name = f"/tsim_custom_{path_hash}"
            try:
                # Clear umask temporarily to ensure permissions are set correctly
                old_umask = os.umask(0)
                try:
                    sem = posix_ipc.Semaphore(sem_name, flags=posix_ipc.O_CREX, initial_value=1, mode=0o660)
                finally:
                    os.umask(old_umask)  # Restore original umask
            except posix_ipc.ExistentialError:
                sem = posix_ipc.Semaphore(sem_name)
            self.semaphores[path_str] = sem
        
        # Acquire semaphore
        try:
            sem.acquire(timeout)
        except posix_ipc.BusyError:
            self.logger.error(f"Failed to acquire lock for {file_path}")
            return False, None
        
        try:
            # Read current data
            current_data = {}
            if Path(file_path).exists():
                try:
                    with open(file_path, 'r') as f:
                        current_data = json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    self.logger.warning(f"Error reading {file_path}: {e}")
            
            # Perform operation
            success, result = operation(current_data)
            
            # If operation returns updated data, write it back
            if success and isinstance(result, dict):
                temp_file = Path(file_path).with_suffix('.tmp')
                try:
                    # Save current umask and set new one for group write
                    old_umask = os.umask(0o002)  # Allow group write
                    try:
                        with open(temp_file, 'w') as f:
                            json.dump(result, f, indent=2)
                        temp_file.replace(Path(file_path))
                        
                        # Ensure the final file has correct permissions
                        os.chmod(file_path, 0o664)  # rw-rw-r--
                    finally:
                        # Restore original umask
                        os.umask(old_umask)
                except IOError as e:
                    self.logger.error(f"Error writing {file_path}: {e}")
                    if temp_file.exists():
                        temp_file.unlink()
                    return False, None
            
            return success, result
            
        finally:
            # Always release semaphore
            sem.release()
        
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
    
    def _needs_sudo(self, cmd: str, namespace: str = None) -> bool:
        """Check if a command needs sudo privileges."""
        # If we're already root, no need for sudo
        if os.geteuid() == 0:
            return False
        
        # Commands that need privileges
        privileged_commands = [
            'ip netns add',
            'ip netns del',
            'ip netns exec',
            'ip link add',
            'ip link del',
            'ip link set',
            'ip addr add',
            'ip addr del',
            'ip route add',
            'ip route del',
            'brctl addbr',
            'brctl delbr',
            'brctl addif',
            'brctl delif',
            'tc qdisc',
            'kill',
            'pkill'
        ]
        
        # If executing in namespace, always needs sudo
        if namespace:
            return True
        
        # Check if command starts with any privileged command
        for priv_cmd in privileged_commands:
            if cmd.startswith(priv_cmd):
                return True
        
        return False
        
    def run_command(self, command: str, namespace: str = None, check: bool = True) -> subprocess.CompletedProcess:
        """Execute command optionally in namespace."""
        # Determine if command needs sudo
        needs_sudo = self._needs_sudo(command, namespace)
        
        if namespace:
            if needs_sudo and os.geteuid() != 0:
                full_command = f"sudo ip netns exec {namespace} {command}"
            else:
                full_command = f"ip netns exec {namespace} {command}"
        else:
            if needs_sudo and os.geteuid() != 0:
                full_command = f"sudo {command}"
            else:
                full_command = command
            
        self.logger.debug(f"Running: {full_command}")
        
        # With -vvv, print the command before execution
        if self.verbose >= 3:
            print(f"[CMD] {full_command}", file=sys.stderr)
        
        # Track command execution time
        cmd_start = time.time()
        result = subprocess.run(
            full_command, shell=True, capture_output=True, text=True, check=check
        )
        cmd_duration = (time.time() - cmd_start) * 1000
        
        # Store timing if we have timing_data available
        if hasattr(self, '_current_timing_data') and self._current_timing_data:
            # Categorize command type
            if 'ip netns add' in full_command:
                cmd_type = 'netns_add'
            elif 'ip netns exec' in full_command:
                if 'ip link add' in command:
                    cmd_type = 'link_add'
                elif 'ip link set' in command:
                    cmd_type = 'link_set'
                elif 'ip addr add' in command:
                    cmd_type = 'addr_add'
                elif 'ip route add' in command:
                    cmd_type = 'route_add'
                elif 'tc qdisc' in command:
                    cmd_type = 'tc_qdisc'
                else:
                    cmd_type = 'netns_exec'
            elif 'ip link add' in full_command:
                cmd_type = 'link_add'
            elif 'ip link set' in full_command:
                cmd_type = 'link_set'
            elif 'ip addr add' in full_command:
                cmd_type = 'addr_add'
            elif 'ip route' in full_command:
                cmd_type = 'route_cmd'
            elif 'network_namespace_status.py' in full_command:
                cmd_type = 'status_script'
            else:
                cmd_type = 'other'
            
            if 'command_timings' not in self._current_timing_data:
                self._current_timing_data['command_timings'] = []
            
            self._current_timing_data['command_timings'].append({
                'cmd': full_command[:100] + ('...' if len(full_command) > 100 else ''),
                'type': cmd_type,
                'duration_ms': cmd_duration,
                'returncode': result.returncode,
                'namespace': namespace if namespace else 'host'
            })
        
        # With -vvv, print the command output and timing
        if self.verbose >= 3:
            # Skip stdout for network_namespace_status.py and host listing to avoid verbose output
            if 'network_namespace_status.py' not in full_command and '--list-hosts' not in full_command:
                if result.stdout:
                    print(f"[STDOUT]\n{result.stdout}", file=sys.stderr)
            if result.stderr:
                print(f"[STDERR]\n{result.stderr}", file=sys.stderr)
            status = '✓' if result.returncode == 0 else '✗'
            print(f"[RETCODE] {result.returncode} {status} [{cmd_duration:.1f}ms]", file=sys.stderr)
        
        if result.returncode != 0 and check:
            self.logger.error(f"Command failed: {full_command}")
            self.logger.error(f"Error: {result.stderr}")
            raise subprocess.CalledProcessError(result.returncode, full_command, result.stderr)
            
        return result
        
    def load_router_registry(self) -> Dict[str, str]:
        """Load registry of router/host name to code mappings atomically."""
        def read_op(data):
            return True, data
        
        success, registry = self._atomic_json_operation(self.router_registry_file, read_op)
        return registry if success else {}
            
    def save_router_registry(self, registry: Dict[str, str]):
        """Save registry of router/host name to code mappings atomically."""
        def write_op(current):
            return True, registry
        
        success, _ = self._atomic_json_operation(self.router_registry_file, write_op)
        if not success:
            self.logger.error(f"Could not save router registry")

    def load_interface_registry(self) -> Dict[str, Dict[str, str]]:
        """Load registry of interface name to code mappings per router/host atomically."""
        def read_op(data):
            return True, data
        
        success, registry = self._atomic_json_operation(self.interface_registry_file, read_op)
        return registry if success else {}
            
    def save_interface_registry(self):
        """Save registry of interface name to code mappings per router/host atomically."""
        def write_op(current):
            return True, self.interface_registry
        
        success, _ = self._atomic_json_operation(self.interface_registry_file, write_op)
        if not success:
            self.logger.error(f"Could not save interface registry")

    def _is_tsim_managed_namespace(self, namespace_name: str) -> bool:
        """Check if a namespace is managed by tsim by checking registries."""
        # Check if it's the hidden namespace
        if namespace_name == "hidden-mesh":
            return True
        
        # Check router registry (hosts are stored here too)
        if self.router_registry_file.exists():
            try:
                router_registry = self.load_router_registry()
                if namespace_name in router_registry or namespace_name in router_registry.values():
                    return True
            except Exception:
                pass
        
        # Check host registry
        if self.host_registry_file.exists():
            try:
                with open(self.host_registry_file, 'r') as f:
                    host_registry = json.load(f)
                    if namespace_name in host_registry.get('hosts', {}):
                        return True
            except Exception:
                pass
        
        return False

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
        """Register host in the bridge registry atomically."""
        def update_op(bridge_registry):
            if bridge_name in bridge_registry:
                if 'hosts' not in bridge_registry[bridge_name]:
                    bridge_registry[bridge_name]['hosts'] = {}
                
                bridge_registry[bridge_name]['hosts'][host_name] = {
                    "interface": "eth0",
                    "ipv4": primary_ip,
                    "state": "UP"
                }
                
                self.logger.debug(f"Registered host {host_name} in bridge {bridge_name}")
                return True, bridge_registry
            else:
                self.logger.error(f"Bridge {bridge_name} not found in registry")
                return False, bridge_registry
        
        success, _ = self._atomic_json_operation(str(self.bridge_registry_file), update_op)
        return success

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
        """Unregister host from the bridge registry atomically."""
        def update_op(bridge_registry):
            # Find and remove host from all bridges
            for bridge_name, bridge_info in bridge_registry.items():
                hosts = bridge_info.get('hosts', {})
                if host_name in hosts:
                    del hosts[host_name]
                    self.logger.debug(f"Unregistered host {host_name} from bridge {bridge_name}")
            
            return True, bridge_registry
        
        self._atomic_json_operation(str(self.bridge_registry_file), update_op)
        
    def _batch_register_host(self, host_name: str, host_config: Dict, interfaces: List[str], 
                            bridge_name: str, primary_ip: str) -> bool:
        """
        Batch register host in all registries with minimal lock contention.
        This minimizes the time locks are held by doing all updates quickly.
        """
        try:
            # 1. Update host registry (quick lock)
            def add_host_op(registry):
                # Double-check no collision happened while we were creating the host
                if host_name in registry:
                    self.logger.error(f"Host name {host_name} already exists (race condition)")
                    return False, registry
                
                # Also check for IP collision on the same router (race condition check)
                ip_without_prefix = host_config['primary_ip'].split('/')[0]
                connected_router = host_config['connected_to']
                
                for existing_host, existing_config in registry.items():
                    if existing_host == host_name:
                        continue
                    existing_router = existing_config.get('connected_to', '')
                    if existing_router == connected_router:
                        # Check primary IP
                        existing_ip = existing_config.get('primary_ip', '').split('/')[0]
                        if existing_ip == ip_without_prefix:
                            self.logger.error(f"IP {ip_without_prefix} already in use by host {existing_host} on router {connected_router} (race condition)")
                            return False, registry
                        # Check secondary IPs
                        for sec_ip in existing_config.get('secondary_ips', []):
                            if sec_ip.split('/')[0] == ip_without_prefix:
                                self.logger.error(f"IP {ip_without_prefix} already in use by host {existing_host} on router {connected_router} (race condition)")
                                return False, registry
                
                # Also check secondary IPs for collision
                for sec_ip in host_config.get('secondary_ips', []):
                    sec_ip_clean = sec_ip.split('/')[0]
                    for existing_host, existing_config in registry.items():
                        if existing_config.get('connected_to') == connected_router:
                            existing_primary = existing_config.get('primary_ip', '').split('/')[0]
                            if existing_primary == sec_ip_clean:
                                self.logger.error(f"Secondary IP {sec_ip_clean} already in use by host {existing_host} on router {connected_router} (race condition)")
                                return False, registry
                            for existing_sec in existing_config.get('secondary_ips', []):
                                if existing_sec.split('/')[0] == sec_ip_clean:
                                    self.logger.error(f"Secondary IP {sec_ip_clean} already in use by host {existing_host} on router {connected_router} (race condition)")
                                    return False, registry
                
                # All checks passed, safe to add
                registry[host_name] = host_config
                return True, registry
            
            success, _ = self._atomic_json_operation(self.host_registry_file, add_host_op)
            if not success:
                self.logger.error(f"Failed to register host {host_name} in host registry")
                return False
            
            # 2. Update interface registry (quick lock)
            host_code = self.get_host_code(host_name)
            
            def update_interfaces_op(registry):
                if host_code not in registry:
                    registry[host_code] = {}
                for interface_name in interfaces:
                    # Generate interface code inline to avoid extra operations
                    existing_codes = set(registry[host_code].values())
                    for i in range(1000):
                        interface_code = f"i{i:03d}"
                        if interface_code not in existing_codes:
                            registry[host_code][interface_name] = interface_code
                            break
                return True, registry
            
            success, _ = self._atomic_json_operation(self.interface_registry_file, update_interfaces_op)
            if not success:
                self.logger.error(f"Failed to register interfaces for host {host_name}")
                # Rollback host registry
                self._remove_host_from_registry(host_name)
                return False
            
            # 3. Update bridge registry if needed (quick lock)
            if bridge_name:
                def update_bridge_op(bridge_registry):
                    if bridge_name in bridge_registry:
                        if 'hosts' not in bridge_registry[bridge_name]:
                            bridge_registry[bridge_name]['hosts'] = {}
                        
                        bridge_registry[bridge_name]['hosts'][host_name] = {
                            "interface": "eth0",
                            "ipv4": primary_ip,
                            "state": "UP"
                        }
                        return True, bridge_registry
                    else:
                        self.logger.error(f"Bridge {bridge_name} not found in registry")
                        return False, bridge_registry
                
                success, _ = self._atomic_json_operation(str(self.bridge_registry_file), update_bridge_op)
                if not success:
                    self.logger.error(f"Failed to register host {host_name} in bridge registry")
                    # Note: Not rolling back for bridge registry failure as it's non-critical
                    
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to batch register host: {e}")
            return False
    
    def _remove_host_from_registry(self, host_name: str):
        """Helper to remove host from registry during rollback."""
        def remove_op(registry):
            if host_name in registry:
                del registry[host_name]
            return True, registry
        self._atomic_json_operation(self.host_registry_file, remove_op)
    
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
                print("Warning: tc not available - host latency simulation skipped", file=sys.stderr)
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
        """Load registry of existing hosts atomically."""
        def read_op(data):
            return True, data
        
        success, registry = self._atomic_json_operation(self.host_registry_file, read_op)
        return registry if success else {}
            
    def save_host_registry(self, registry: Dict[str, Dict]):
        """Save registry of hosts atomically."""
        def write_op(current):
            return True, registry
        
        success, _ = self._atomic_json_operation(self.host_registry_file, write_op)
        if not success:
            self.logger.error(f"Could not save host registry")
            
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
        
    def determine_router_interface_by_routing(self, router_name: str, host_ip: str) -> Optional[Tuple[str, str]]:
        """Determine which router interface should be used to reach a host IP using 'ip route get'.
        
        Returns:
            Optional[Tuple[str, str]]: Tuple of (interface_name, gateway_ip) or None if not found
        """
        # Extract IP without prefix
        host_ip_clean = host_ip.split('/')[0] if '/' in host_ip else host_ip
        
        if self.verbose >= 3:
            print(f"\nDEBUG: determine_router_interface_by_routing() called with:", file=sys.stderr)
            print(f"  router_name: {router_name}", file=sys.stderr)
            print(f"  host_ip: {host_ip_clean}", file=sys.stderr)
        
        # Check if router namespace exists
        if router_name not in self.available_namespaces:
            self.logger.error(f"Router namespace {router_name} not found")
            return None
        
        # Use ip route get to determine the outgoing interface
        cmd = f"ip route get {host_ip_clean}"
        
        if self.verbose >= 3:
            print(f"\nExecuting in router namespace: ip netns exec {router_name} {cmd}", file=sys.stderr)
        
        result = self.run_command(cmd, namespace=router_name, check=False)
        
        if result.returncode != 0:
            self.logger.error(f"Failed to get route for {host_ip_clean} on {router_name}: {result.stderr}")
            return None
        
        if self.verbose >= 3:
            print(f"Route output: {result.stdout.strip()}", file=sys.stderr)
        
        # Parse the output to extract the interface
        # Example outputs:
        # "10.129.130.21 dev eno5 src 10.129.130.2 uid 0"
        # "10.128.47.21 via 10.1.1.1 dev eth0 src 10.1.1.2 uid 0"
        output = result.stdout.strip()
        
        # Extract interface using regex
        interface_match = re.search(r'dev\s+(\S+)', output)
        if not interface_match:
            self.logger.error(f"Could not parse interface from route output: {output}")
            return None
        
        interface_name = interface_match.group(1)
        
        if self.verbose >= 3:
            print(f"Determined interface: {interface_name}", file=sys.stderr)
        
        # Now find the router's IP on this interface
        # First check if it's a direct route (no via)
        if 'via' not in output:
            # Direct route - extract src IP
            src_match = re.search(r'src\s+(\S+)', output)
            if src_match:
                gateway_ip = src_match.group(1)
                if self.verbose >= 3:
                    print(f"Direct route - using source IP as gateway: {gateway_ip}", file=sys.stderr)
                return (interface_name, gateway_ip)
        
        # For routes with 'via' or if src not found, get the interface IP from router facts
        if router_name in self.routers:
            routing_tables = self.routers[router_name].get('routing', {}).get('tables', [])
            for route in routing_tables:
                if (route.get('protocol') == 'kernel' and 
                    route.get('scope') == 'link' and
                    route.get('prefsrc') and route.get('dev') == interface_name):
                    gateway_ip = route['prefsrc']
                    if self.verbose >= 3:
                        print(f"Found router IP {gateway_ip} on interface {interface_name} from facts", file=sys.stderr)
                    return (interface_name, gateway_ip)
        
        # If we still don't have a gateway IP, we may need to add one
        self.logger.warning(f"Could not find router IP on interface {interface_name}")
        return (interface_name, None)
        
    def find_shared_mesh_bridge(self, primary_ip: str) -> Optional[str]:
        """Find the shared mesh bridge for the host's subnet using bridge registry."""
        try:
            host_network = ipaddress.IPv4Network(primary_ip, strict=False)
            
            # Log bridge registry location in verbose mode
            if self.verbose > 0:
                self.logger.info(f"Loading bridge registry from: {self.bridge_registry_file}")
            
            # Load bridge registry atomically
            def read_op(data):
                return True, data
            
            success, bridge_registry = self._atomic_json_operation(str(self.bridge_registry_file), read_op)
            if not success or not bridge_registry:
                self.logger.error("Bridge registry not found. Run netsetup first.")
                return None
            
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
            # Log bridge registry location in verbose mode
            if self.verbose > 0:
                self.logger.info(f"Loading bridge registry from: {self.bridge_registry_file}")
            
            # Load bridge registry atomically
            def read_op(data):
                return True, data
            
            success, bridge_registry = self._atomic_json_operation(str(self.bridge_registry_file), read_op)
            if not success or not bridge_registry:
                self.logger.error("Bridge registry not found. Run netsetup first.")
                return None
            
            # Find bridge that contains this router and interface
            for bridge_name, bridge_info in bridge_registry.items():
                routers = bridge_info.get('routers', {})
                if router_name in routers:
                    router_info = routers[router_name]
                    if router_info.get('interface') == interface_name:
                        # Check if this bridge exists in hidden-mesh namespace
                        result = self.run_command(f"ip netns exec hidden-mesh ip link show {bridge_name}", check=False)
                        if result.returncode == 0:
                            self.logger.info(f"Found existing bridge {bridge_name} for {router_name}:{interface_name}")
                            return bridge_name
                            
            return None
        except Exception as e:
            self.logger.error(f"Error finding bridge: {e}")
            return None

    def _generate_bridge_name(self, subnet: str) -> str:
        """Generate bridge name with zero-padded format: b + 4 zero-padded octets + 2-digit prefix.
        
        Examples:
        - 10.11.12.128/25 -> b01001101212825
        - 192.168.1.0/24 -> b19216800102400
        - 172.16.0.0/12 -> b17201600001200
        
        Format: b + OOOOOOOOOOOO + PP (15 chars total)
        Where O = zero-padded octets (3 digits each), P = zero-padded prefix (2 digits)
        """
        ip_part, prefix = subnet.split('/')
        octets = ip_part.split('.')
        
        # Zero-pad each octet to 3 digits
        padded_octets = [f"{int(octet):03d}" for octet in octets]
        
        # Zero-pad prefix to 2 digits
        padded_prefix = f"{int(prefix):02d}"
        
        # Create bridge name: b + 12 octet digits + 2 prefix digits = 15 chars
        bridge_name = f"b{''.join(padded_octets)}{padded_prefix}"
        
        return bridge_name

    def get_all_registered_ips(self) -> Dict[str, Dict]:
        """Get all IP addresses registered in the bridge registry."""
        try:
            # Load bridge registry atomically
            def read_op(data):
                return True, data
            
            success, bridge_registry = self._atomic_json_operation(str(self.bridge_registry_file), read_op)
            if not success:
                return {}
            
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
        
        Only checks on the target router since each router is independent.
        Much faster than scanning all routers.
        """
        # Extract IP without prefix if provided
        ip_without_prefix = ip_address.split('/')[0] if '/' in ip_address else ip_address
        
        # Only check the target router if specified
        if target_router and target_router in self.available_namespaces:
            # Fast check: does this specific router have this IP?
            result = self.run_command(
                f"ip addr show | grep -w {ip_without_prefix}",
                namespace=target_router,
                check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                # Found the IP on this router - parse which interface has it
                interface = 'unknown'
                for line in result.stdout.split('\n'):
                    if ip_without_prefix in line:
                        # Extract interface name from ip addr show output
                        import re
                        # Format: "inet 10.1.1.1/24 brd 10.1.1.255 scope global eth0"
                        match = re.search(r'inet\s+' + re.escape(ip_without_prefix) + r'/\d+.*dev\s+(\S+)', line)
                        if match:
                            interface = match.group(1)
                        
                return True, {
                    'type': 'router',
                    'name': target_router,
                    'interface': interface,
                    'full_ip': ip_address
                }
        
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

    def find_router_mesh_interface(self, router_name: str, interface_name: str) -> Optional[str]:
        """Find the mesh-side interface name for a router interface."""
        try:
            # Get the interface index in the router namespace
            cmd = f"ip netns exec {router_name} ip link show {interface_name} | grep -o '@if[0-9]*' | cut -d'f' -f2"
            result = self.run_command(cmd, check=False)
            if result.returncode != 0 or not result.stdout.strip():
                return None
                
            peer_index = result.stdout.strip()
            
            # Find the interface with this index in hidden-mesh
            cmd = f"ip netns exec hidden-mesh ip link show | grep '^{peer_index}:' | cut -d: -f2 | cut -d@ -f1"
            result = self.run_command(cmd, check=False)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
                
        except Exception as e:
            self.logger.debug(f"Could not find router mesh interface: {e}")
            
        return None
    
    def create_mesh_connection(self, host_name: str, primary_ip: str, gateway_ip: Optional[str] = None, target_router: Optional[str] = None, router_bridge: Optional[str] = None, router_mesh_iface: Optional[str] = None) -> Tuple[bool, Dict]:
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
        
        # Short delay after moving to namespace (reduced from 1.0s)
        import time
        if not self.no_delay:
            time.sleep(0.2)
        
        self.run_command(f"ip link set {mesh_veth} master {mesh_bridge}", namespace="hidden-mesh")
        self.run_command(f"ip link set {mesh_veth} up", namespace="hidden-mesh")
        
        # Short delay after bringing interface up (reduced from 1.0s)
        if not self.no_delay:
            time.sleep(0.3)
        
        # Clean bridge FDB entries to prevent stale MAC issues
        # This is needed when hosts are recreated with same names but different MAC addresses
        self.logger.info(f"Cleaning bridge FDB entries - comprehensive flush")
        
        # First, flush all dynamic entries on the bridge by setting ageing to 0
        self.logger.info(f"Step 1: Flushing all learned entries on bridge {mesh_bridge}")
        self.run_command(f"ip link set {mesh_bridge} type bridge ageing_time 0", namespace="hidden-mesh", check=False)
        
        # Short delay to ensure ageing takes effect (reduced from 1.0s)
        if not self.no_delay:
            time.sleep(0.1)
        
        # Flush specific device entries
        self.logger.info(f"Step 2: Flushing FDB entries for {mesh_veth}")
        self.run_command(f"bridge fdb flush dev {mesh_veth} master", namespace="hidden-mesh", check=False)
        
        # Also clean router interface if provided
        if router_mesh_iface:
            self.logger.info(f"Step 3: Flushing FDB entries for router interface {router_mesh_iface}")
            self.run_command(f"bridge fdb flush dev {router_mesh_iface} master", namespace="hidden-mesh", check=False)
        
        # Flush all bridge FDB entries (more aggressive)
        self.logger.info(f"Step 4: Flushing all bridge FDB entries")
        self.run_command(f"bridge fdb flush dev {mesh_bridge} self", namespace="hidden-mesh", check=False)
        
        # Short delay before restoring ageing (reduced from 1.0s)
        if not self.no_delay:
            time.sleep(0.1)
        
        # Restore normal ageing time
        self.logger.info(f"Step 5: Restoring bridge ageing time")
        self.run_command(f"ip link set {mesh_bridge} type bridge ageing_time 30000", namespace="hidden-mesh", check=False)
        
        # Short delay to ensure settings are applied (reduced from 1.0s)
        if not self.no_delay:
            time.sleep(0.2)
        
        # Configure host IP
        self.run_command(f"ip addr add {primary_ip} dev eth0", namespace=host_name)
        self.run_command(f"ip link set eth0 up", namespace=host_name)
        
        # Short delay after bringing up interface (reduced from 1.0s)
        if not self.no_delay:
            time.sleep(0.3)
        
        # Add 1ms latency to physical interface for realistic network behavior
        self.configure_host_latency(host_name, "eth0", latency_ms=1.0)
        
        # Short delay to allow everything to stabilize (reduced from 1.0s)
        if not self.no_delay:
            time.sleep(0.5)
        
        # Clear neighbor cache on host to ensure fresh ARP
        self.logger.info(f"Clearing neighbor cache on host {host_name}")
        self.run_command(f"ip neigh flush all", namespace=host_name, check=False)
        
        # Also clear neighbor cache on router if available
        if target_router and target_router in self.available_namespaces:
            self.logger.info(f"Clearing neighbor cache on router {target_router}")
            self.run_command(f"ip neigh flush all", namespace=target_router, check=False)
        
        # Minimal delay to ensure bridge forwarding is ready (reduced from 2.0s)
        if not self.no_delay:
            self.logger.info("Waiting for bridge forwarding to stabilize...")
            time.sleep(0.5)
        else:
            self.logger.info("Skipping bridge stabilization delay (--no-delay)")
        
        # Trigger bidirectional traffic to ensure bridge MAC learning
        if gateway_ip and target_router:
            self.logger.info(f"Triggering bidirectional traffic for bridge MAC learning")
            
            # Use non-blocking pings to speed up MAC learning
            self.logger.info(f"Triggering non-blocking pings for fast MAC learning")
            host_network = ipaddress.IPv4Network(primary_ip, strict=False)
            broadcast_ip = str(host_network.broadcast_address)
            host_ip_only = primary_ip.split('/')[0]
            
            # Launch all pings in background (non-blocking)
            self.run_command(f"ping -b -c 1 -W 1 {broadcast_ip} >/dev/null 2>&1 &", namespace=host_name, check=False)
            
            if target_router in self.available_namespaces:
                self.run_command(f"ping -c 1 -W 1 {host_ip_only} >/dev/null 2>&1 &", namespace=target_router, check=False)
            
            self.run_command(f"ping -c 1 -W 1 {gateway_ip} >/dev/null 2>&1 &", namespace=host_name, check=False)
            
            # Single short delay for all pings to complete (reduced from 1.5s total)
            if not self.no_delay:
                time.sleep(0.3)
        
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
        # Initialize timing data
        operation_start = time.time()
        timing_data = {
            'total_time': 0.0,
            'operations': [],
            'command_timings': [],
            'host_name': host_name,
            'primary_ip': primary_ip,
            'secondary_ip_count': len(secondary_ips)
        }
        
        # Set current timing data for command tracking
        self._current_timing_data = timing_data
        
        # Operation: Check namespace existence
        op_start = time.time()
        if host_name in self.available_namespaces:
            self.logger.error(f"Namespace {host_name} already exists")
            timing_data['operations'].append({
                'name': 'check_namespace_exists',
                'duration_ms': (time.time() - op_start) * 1000,
                'result': 'failed'
            })
            return False
        timing_data['operations'].append({
            'name': 'check_namespace_exists',
            'duration_ms': (time.time() - op_start) * 1000,
            'result': 'success'
        })
            
        # Operation: Quick registry check for host name collision
        op_start = time.time()
        registry = self.load_host_registry()
        if host_name in registry:
            self.logger.error(f"Host {host_name} already registered")
            timing_data['operations'].append({
                'name': 'check_host_registry',
                'duration_ms': (time.time() - op_start) * 1000,
                'result': 'failed'
            })
            return False
        timing_data['operations'].append({
            'name': 'check_host_registry',
            'duration_ms': (time.time() - op_start) * 1000,
            'result': 'success'
        })
            
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
            
        # Operation: Check for IP collision on primary IP (only on the same router)
        op_start = time.time()
        collision_detected, collision_info = self.check_ip_collision(primary_ip, target_router)
        timing_data['operations'].append({
            'name': 'check_primary_ip_collision',
            'duration_ms': (time.time() - op_start) * 1000,
            'result': 'collision' if collision_detected else 'no_collision',
            'target_router': target_router
        })
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
            
        # Operation: Check for IP collision on secondary IPs
        if secondary_ips:
            op_start = time.time()
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
            
            timing_data['operations'].append({
                'name': 'check_secondary_ip_collisions',
                'duration_ms': (time.time() - op_start) * 1000,
                'result': 'no_collision',
                'count': len(secondary_ips),
                'target_router': target_router
            })
            
        # Validate router interface option
        if router_interface and not connect_to:
            self.logger.error("--router-interface requires --connect-to to specify the router")
            return False
            
        # Get router details (we already have target_router from above)
        target_iface = None  # Initialize target_iface
        gateway_ip = None    # Initialize gateway_ip
        router_ip_added = False  # Track if we added IP to router
        
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
                # Use ip route get to determine the correct interface
                if self.verbose >= 3:
                    print(f"\nDetermining router interface using routing table lookup...", file=sys.stderr)
                
                route_info = self.determine_router_interface_by_routing(target_router, primary_ip)
                if route_info:
                    target_iface, existing_ip = route_info
                    
                    # Now check if the router has an IP in the host's subnet on this interface
                    host_network = ipaddress.IPv4Network(primary_ip, strict=False)
                    gateway_ip = self.get_default_gateway(primary_ip, target_router)
                    
                    if not gateway_ip:
                        # Router doesn't have an IP in the host's subnet - we need to add one
                        gateway_ip = str(host_network.network_address + 1)
                        
                        self.logger.info(f"Router {target_router} has no IP in subnet {host_network}, adding {gateway_ip}/{host_network.prefixlen} to interface {target_iface}")
                        
                        # Add the IP to the router interface
                        cmd = f"ip addr add {gateway_ip}/{host_network.prefixlen} dev {target_iface}"
                        result = self.run_command(cmd, namespace=target_router, check=False)
                        
                        if result.returncode == 0:
                            self.logger.info(f"Successfully added {gateway_ip}/{host_network.prefixlen} to {target_router} interface {target_iface}")
                            router_ip_added = True  # Mark that we added this IP
                        else:
                            # IP might already exist, which is fine
                            if "File exists" in result.stderr:
                                self.logger.debug(f"IP {gateway_ip}/{host_network.prefixlen} already exists on {target_router}")
                            else:
                                self.logger.warning(f"Failed to add IP to router: {result.stderr}")
                    else:
                        if self.verbose >= 3:
                            print(f"Router already has IP {gateway_ip} in host subnet {host_network}", file=sys.stderr)
                else:
                    self.logger.error(f"Could not determine router interface for host IP {primary_ip}")
                    return False
        else:
            # We already found the router info above for collision check
            # Now get the interface and gateway details
            router_info = self.find_router_for_subnet(primary_ip)
            if router_info:
                _, target_iface, gateway_ip = router_info
            
        self.logger.info(f"Connecting host {host_name} to router {target_router} via gateway {gateway_ip} using unified mesh infrastructure")
        
        try:
            # Check if namespace exists first
            result = self.run_command(f"ip netns list | grep -w {host_name}", check=False)
            if result.returncode == 0:
                # Namespace exists - check if it's tsim-managed
                if self._is_tsim_managed_namespace(host_name):
                    if self.verbose > 0:
                        self.logger.warning(f"Host namespace {host_name} already exists (tsim-managed), continuing...")
                else:
                    # Not tsim-managed - critical error
                    error_msg = f"CRITICAL: Namespace {host_name} already exists but is not managed by tsim"
                    self.logger.error(error_msg)
                    raise Exception(error_msg)
            else:
                # Namespace doesn't exist - create it
                self.run_command(f"ip netns add {host_name}")
            
            # Enable loopback
            self.run_command("ip link set lo up", namespace=host_name)
            
            # Connect to mesh infrastructure (unified mesh architecture)
            # If we have a specific router target, find its bridge
            router_bridge = None
            router_mesh_iface = None
            if connect_to and target_iface:
                router_bridge = self.find_router_bridge(target_router, target_iface)
                if router_bridge:
                    self.logger.info(f"Found router {target_router}'s interface {target_iface} connected to bridge {router_bridge}")
                    # Find the mesh-side interface name for the router
                    router_mesh_iface = self.find_router_mesh_interface(target_router, target_iface)
                    if router_mesh_iface:
                        self.logger.info(f"Router mesh interface: {router_mesh_iface}")
                else:
                    self.logger.warning(f"Could not find bridge for {target_router} interface {target_iface}, falling back to IP-based selection")
                    
            success, connection_info = self.create_mesh_connection(host_name, primary_ip, gateway_ip, target_router, router_bridge, router_mesh_iface)
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
            
            # Prepare all registry data BEFORE acquiring any locks
            host_interfaces = ["lo", "eth0"]  # Standard interfaces for all hosts
            host_interfaces.extend([f"dummy{i}" for i in range(len(secondary_ips))])  # Add dummy interfaces
            
            bridge_name = connection_info.get('mesh_bridge')
            
            # Prepare host config
            host_config = {
                "primary_ip": primary_ip,
                "secondary_ips": secondary_ips,
                "connected_to": target_router,
                "router_interface": target_iface if target_iface else "unknown",
                "gateway_ip": gateway_ip,
                "router_ip_added": router_ip_added,  # Track if we added IP to router
                "dummy_interfaces": dummy_configs,
                "created_at": str(subprocess.run("date", capture_output=True, text=True).stdout.strip())
            }
            
            # Add connection-specific information
            host_config.update(connection_info)
            
            # Now do ALL registry updates in a SINGLE batch operation
            op_start = time.time()
            success = self._batch_register_host(host_name, host_config, host_interfaces, bridge_name, primary_ip)
            timing_data['operations'].append({
                'name': 'batch_registry_update',
                'duration_ms': (time.time() - op_start) * 1000,
                'result': 'success' if success else 'failed'
            })
            
            if not success:
                raise Exception("Failed to register host in registries")
            
            # Calculate total time
            timing_data['total_time'] = (time.time() - operation_start) * 1000
            
            # Clear current timing data
            self._current_timing_data = None
            
            # Print timing summary if verbose >= 2
            if self.verbose >= 2:
                print(f"\n=== Host Creation Timing Summary ===")
                print(f"Host: {host_name}")
                print(f"Total time: {timing_data['total_time']:.2f}ms")
                print(f"Total commands executed: {len(timing_data.get('command_timings', []))}")
                
                print(f"\nOperation breakdown:")
                for op in timing_data['operations']:
                    status = '✓' if op['result'] in ['success', 'no_collision', 'not_exists'] else '✗'
                    print(f"  {status} {op['name']}: {op['duration_ms']:.2f}ms")
                    if 'individual_times_ms' in op:
                        for idx, t in enumerate(op['individual_times_ms']):
                            print(f"      dummy{idx}: {t:.2f}ms")
                
                # Print command timing breakdown
                if 'command_timings' in timing_data and timing_data['command_timings']:
                    print(f"\nCommand execution breakdown:")
                    
                    # Group by command type
                    cmd_by_type = {}
                    for cmd in timing_data['command_timings']:
                        cmd_type = cmd['type']
                        if cmd_type not in cmd_by_type:
                            cmd_by_type[cmd_type] = []
                        cmd_by_type[cmd_type].append(cmd)
                    
                    # Print summary by type
                    for cmd_type, cmds in sorted(cmd_by_type.items()):
                        total_ms = sum(c['duration_ms'] for c in cmds)
                        avg_ms = total_ms / len(cmds) if cmds else 0
                        print(f"  {cmd_type}: {len(cmds)} cmds, {total_ms:.1f}ms total, {avg_ms:.1f}ms avg")
                    
                    # If verbose >= 3, show individual commands
                    if self.verbose >= 3:
                        print(f"\nDetailed command list:")
                        for i, cmd in enumerate(timing_data['command_timings'], 1):
                            status = '✓' if cmd['returncode'] == 0 else '✗'
                            ns_info = f" [ns: {cmd['namespace']}]" if cmd['namespace'] != 'host' else ""
                            print(f"  {i:3d}. {status} [{cmd['duration_ms']:6.1f}ms] {cmd['type']:12s}{ns_info}: {cmd['cmd']}")
                
                # Calculate overhead
                total_cmd_time = sum(cmd['duration_ms'] for cmd in timing_data.get('command_timings', []))
                overhead = timing_data['total_time'] - total_cmd_time
                print(f"\nTime distribution:")
                print(f"  Command execution: {total_cmd_time:.1f}ms ({total_cmd_time/timing_data['total_time']*100:.1f}%)")
                print(f"  Python overhead: {overhead:.1f}ms ({overhead/timing_data['total_time']*100:.1f}%)")
                print()
            
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
            self._current_timing_data = None  # Clear timing data
            return False
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to create host {host_name}: {e}")
            # Cleanup on failure
            self.cleanup_host_resources(host_name, host_config if 'host_config' in locals() else {})
            self._current_timing_data = None  # Clear timing data
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error creating host {host_name}: {e}")
            self._current_timing_data = None  # Clear timing data
            raise
            
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
            
            # Remove from registry atomically
            def remove_host_op(registry):
                if host_name in registry:
                    del registry[host_name]
                return True, registry
            
            self._atomic_json_operation(self.host_registry_file, remove_host_op)
            
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
            # First, remove router IP if we added it during host creation
            if host_config.get("router_ip_added", False):
                connected_router = host_config.get("connected_to")
                router_interface = host_config.get("router_interface")
                gateway_ip = host_config.get("gateway_ip")
                primary_ip = host_config.get("primary_ip")
                
                if connected_router and router_interface and gateway_ip and primary_ip:
                    # Check if router still exists
                    if connected_router in self.available_namespaces:
                        try:
                            # Extract network prefix from primary IP
                            host_network = ipaddress.IPv4Network(primary_ip, strict=False)
                            
                            self.logger.info(f"Removing IP {gateway_ip}/{host_network.prefixlen} from {connected_router} interface {router_interface} (added during host creation)")
                            
                            # Remove the IP from router
                            cmd = f"ip addr del {gateway_ip}/{host_network.prefixlen} dev {router_interface}"
                            result = self.run_command(cmd, namespace=connected_router, check=False)
                            
                            if result.returncode == 0:
                                self.logger.info(f"Successfully removed router IP {gateway_ip}/{host_network.prefixlen}")
                            else:
                                if "Cannot assign requested address" in result.stderr:
                                    self.logger.debug(f"IP {gateway_ip}/{host_network.prefixlen} was already removed")
                                else:
                                    self.logger.warning(f"Failed to remove router IP: {result.stderr}")
                            
                            # Clear ARP cache on router
                            self.logger.info(f"Clearing ARP cache on router {connected_router}")
                            self.run_command(f"ip neigh flush all", namespace=connected_router, check=False)
                            
                        except Exception as e:
                            self.logger.warning(f"Error removing router IP: {e}")
            
            # Remove namespace (this automatically removes all interfaces in it)
            self.run_command(f"ip netns del {host_name}", check=False)
            
            # Remove mesh-side veth interfaces based on connection type
            connection_type = host_config.get("connection_type", "")
            
            if connection_type == "sim_mesh_direct":
                # Remove mesh veth from hidden-mesh namespace (direct mesh connection)
                mesh_veth = host_config.get("mesh_veth")
                if mesh_veth:
                    self.run_command(f"ip netns exec hidden-mesh ip link del {mesh_veth}", check=False)
            
            # Clean bridge FDB entries if we have the mesh bridge info
            mesh_bridge = host_config.get("mesh_bridge")
            if mesh_bridge:
                self.logger.info(f"Cleaning bridge FDB entries for removed host on bridge {mesh_bridge}")
                # Flush dynamic entries on the bridge
                self.run_command(f"ip link set {mesh_bridge} type bridge ageing_time 0", namespace="hidden-mesh", check=False)
                import time
                if not self.no_delay:
                    time.sleep(0.1)
                self.run_command(f"ip link set {mesh_bridge} type bridge ageing_time 30000", namespace="hidden-mesh", check=False)
                    
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
            
        # Check if user is in tsim-users group (unless running as root)
        if os.geteuid() != 0:
            import grp
            import pwd
            try:
                username = pwd.getpwuid(os.getuid()).pw_name
                tsim_group = grp.getgrnam('tsim-users')
                if username not in tsim_group.gr_mem:
                    self.logger.warning("User not in tsim-users group. Namespace operations may fail.")
                    self.logger.warning("Run: sudo usermod -a -G tsim-users $USER")
            except (KeyError, OSError):
                self.logger.warning("tsim-users group not found. Namespace operations may fail.")
                self.logger.warning("Run: sudo groupadd -f tsim-users")
            
        return True
    
    def __del__(self):
        """Cleanup semaphores on object destruction."""
        if hasattr(self, 'semaphores'):
            for sem in self.semaphores.values():
                try:
                    sem.close()
                except:
                    pass


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
    parser.add_argument('--no-delay', action='store_true',
                       help='Skip stabilization delays for faster host creation')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.host and not args.list_hosts:
        parser.error("Either --host or --list-hosts is required")
    
    if args.host and args.remove and args.primary_ip:
        parser.error("--primary-ip cannot be used with --remove")
        
    if args.host and not args.remove and not args.primary_ip:
        parser.error("--primary-ip is required when adding a host")
        
    manager = HostNamespaceManager(args.verbose, args.no_delay)
    
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