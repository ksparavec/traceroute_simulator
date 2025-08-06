#!/usr/bin/env -S python3 -B -u
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

# Configure global output flushing - disable all buffering
class FlushingWrapper:
    """Wrapper to ensure immediate flushing of all output."""
    def __init__(self, stream):
        self.stream = stream
    
    def write(self, data):
        result = self.stream.write(data)
        self.stream.flush()
        return result
    
    def flush(self):
        return self.stream.flush()
    
    def __getattr__(self, name):
        return getattr(self.stream, name)

# Apply immediate flushing to stdout and stderr
sys.stdout = FlushingWrapper(sys.stdout)
sys.stderr = FlushingWrapper(sys.stderr)

# Import the raw facts block loader and config loader
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from core.raw_facts_block_loader import RawFactsBlockLoader, RouterRawFacts
from core.config_loader import get_registry_paths


class HiddenMeshNetworkSetup:
    """
    Creates network with hidden mesh infrastructure.
    Routers see only their actual interfaces, mesh is hidden.
    """
    
    def __init__(self, verbose: int = 0, limit_pattern: str = None):
        self.verbose = verbose
        self.limit_pattern = limit_pattern
        self.setup_logging()
        
        # Cache frequently used values for performance
        self.is_root = os.geteuid() == 0
        
        # Create set of privileged commands for O(1) lookup
        self.privileged_commands_set = {
            'ip', 'brctl', 'iptables', 'ip6tables', 'ipset',
            'nft', 'ovs-vsctl', 'ovs-ofctl', 'modprobe', 
            'rmmod', 'mount', 'umount', 'sysctl', 'tc',
            'echo', 'kill', 'pkill'
        }
        
        # Determine facts directories
        raw_facts_path = os.environ.get('TRACEROUTE_SIMULATOR_RAW_FACTS')
        if not raw_facts_path:
            raise EnvironmentError("TRACEROUTE_SIMULATOR_RAW_FACTS environment variable must be set")
        self.raw_facts_dir = Path(raw_facts_path)
        
        json_facts_path = os.environ.get('TRACEROUTE_SIMULATOR_FACTS')
        if not json_facts_path:
            raise EnvironmentError("TRACEROUTE_SIMULATOR_FACTS environment variable must be set")
        self.json_facts_dir = Path(json_facts_path)
        
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
        
        # Load registry paths from configuration
        registry_paths = get_registry_paths()
        
        # Router registry for persistent code mapping
        self.router_registry_file = Path(registry_paths['routers'])
        
        # Interface registry for persistent interface numbering
        self.interface_registry_file = Path(registry_paths['interfaces'])
        self.interface_registry: Dict[str, Dict[str, str]] = {}  # router_code -> {interface_name -> interface_code}
        
        # Bridge registry for subnet bridge tracking
        self.bridge_registry_file = Path(registry_paths['bridges'])
        # Enhanced bridge registry: bridge_name -> {"routers": {router_name: {interface, ipv4, state}}, "hosts": {host_name: {interface, ipv4, state}}}
        self.bridge_registry: Dict[str, Dict[str, Dict[str, Dict[str, str]]]] = {}
        
        # Hidden infrastructure namespace
        self.hidden_ns = "hidden-mesh"
        
    def setup_logging(self):
        """Configure logging based on verbosity level."""
        if self.verbose == 0:
            level = logging.CRITICAL + 1  # Disable all logging
        elif self.verbose == 1:
            level = logging.WARNING
        elif self.verbose == 2:
            level = logging.INFO
        else:  # verbose >= 3 (-vvv)
            level = logging.DEBUG
            
        logging.basicConfig(
            level=level,
            format='%(message)s',  # Simplified format for cleaner output
            stream=sys.stdout  # Force logging to stdout to match print statements
        )
        self.logger = logging.getLogger(__name__)
        
        # Track router setup statistics
        self.router_stats = {}
        self.setup_errors = []
        self.setup_warnings = []
        
        # Track infrastructure bridge statistics
        self.infrastructure_stats = {
            'bridges_total': 0,
            'bridges_created': 0,
            'bridges_existing': 0,
            'bridges_failed': 0
        }
        
    def load_raw_facts_only(self):
        """Load router facts from raw facts directory ONLY."""
        raw_facts_dir = self.raw_facts_dir
        
        if not raw_facts_dir.exists():
            raise FileNotFoundError(f"Raw facts directory not found: {raw_facts_dir}")
        
        if self.verbose >= 3:
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
        
        if self.verbose >= 3:
            self.logger.info(f"Loaded {len(self.routers)} routers with interface configs")
        
        # Generate compressed router codes
        self._generate_router_codes()
    
    def _is_tsim_managed_namespace(self, namespace_name: str) -> bool:
        """Check if a namespace is managed by tsim by checking registries."""
        # Check if it's the hidden namespace
        if namespace_name == self.hidden_ns:
            return True
        
        # Check router registry
        if self.router_registry_file.exists():
            try:
                router_registry = self.load_router_registry()
                if namespace_name in router_registry or namespace_name in router_registry.values():
                    return True
            except Exception:
                pass
        
        # Check if it's in our loaded routers
        if namespace_name in self.routers:
            return True
        
        # Check host registry (if it exists)
        host_registry_file = Path("/var/opt/traceroute-simulator/traceroute_simulator_host_registry.json")
        if host_registry_file.exists():
            try:
                with open(host_registry_file, 'r') as f:
                    host_registry = json.load(f)
                    if namespace_name in host_registry.get('hosts', {}):
                        return True
            except Exception:
                pass
        
        return False

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
            # Debug: Check who we're running as
            if self.verbose >= 2:
                import pwd
                current_user = pwd.getpwuid(os.getuid()).pw_name
                current_euid = os.geteuid()
                if current_euid == 0:
                    self.logger.warning(f"WARNING: Running as root! User={current_user}, EUID={current_euid}")
                else:
                    self.logger.debug(f"Running as user={current_user}, EUID={current_euid}")
            
            # Save current umask and set new one for group write
            old_umask = os.umask(0o002)  # Allow group write
            try:
                with open(self.router_registry_file, 'w') as f:
                    json.dump(self.router_codes, f, indent=2)
                
                # Ensure the file has correct permissions
                os.chmod(self.router_registry_file, 0o664)  # rw-rw-r--
            finally:
                # Restore original umask
                os.umask(old_umask)
        except IOError as e:
            self.logger.error(f"Could not save router registry: {e}")

    def load_interface_registry(self) -> Dict[str, Dict[str, str]]:
        """Load registry of interface name to code mappings per router."""
        if not self.interface_registry_file.exists():
            return {}
            
        try:
            with open(self.interface_registry_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Could not load interface registry: {e}")
            return {}
            
    def save_interface_registry(self):
        """Save registry of interface name to code mappings per router."""
        try:
            # Save current umask and set new one for group write
            old_umask = os.umask(0o002)  # Allow group write
            try:
                with open(self.interface_registry_file, 'w') as f:
                    json.dump(self.interface_registry, f, indent=2)
                
                # Ensure the file has correct permissions
                os.chmod(self.interface_registry_file, 0o664)  # rw-rw-r--
            finally:
                # Restore original umask
                os.umask(old_umask)
        except IOError as e:
            self.logger.error(f"Could not save interface registry: {e}")
    
    def load_bridge_registry(self):
        """Load bridge registry from persistent file."""
        if self.bridge_registry_file.exists():
            try:
                import json
                with open(self.bridge_registry_file, 'r') as f:
                    self.bridge_registry = json.load(f)
                self.logger.debug(f"Loaded bridge registry from {self.bridge_registry_file}")
                
                # Fix permissions on existing file if needed
                try:
                    os.chmod(self.bridge_registry_file, 0o664)
                except OSError:
                    pass  # Ignore if we can't change permissions
                    
            except Exception as e:
                self.logger.warning(f"Failed to load bridge registry: {e}")
                self.bridge_registry = {}
        else:
            self.bridge_registry = {}
    
    def save_bridge_registry(self):
        """Save bridge registry to persistent file."""
        try:
            import json
            # Save current umask and set new one for group write
            old_umask = os.umask(0o002)  # Allow group write
            try:
                with open(self.bridge_registry_file, 'w') as f:
                    json.dump(self.bridge_registry, f, indent=2)
                
                # Ensure the file has correct permissions
                os.chmod(self.bridge_registry_file, 0o664)  # rw-rw-r--
                self.logger.debug(f"Saved bridge registry to {self.bridge_registry_file}")
            finally:
                # Restore original umask
                os.umask(old_umask)
        except Exception as e:
            self.logger.warning(f"Failed to save bridge registry: {e}")
    
    def register_bridge_connection(self, bridge_name: str, router_name: str = None, host_name: str = None, 
                                  interface_name: str = None, ipv4_address: str = None, state: str = "UP"):
        """Register a connection between a bridge and router/host with detailed interface information.
        
        Args:
            bridge_name: Name of the bridge
            router_name: Name of the router (if connecting a router)
            host_name: Name of the host (if connecting a host)
            interface_name: Real interface name (e.g., bond1.vlan180)
            ipv4_address: IPv4 address assigned to the interface
            state: Interface state (UP/DOWN)
        """
        if bridge_name not in self.bridge_registry:
            self.bridge_registry[bridge_name] = {"routers": {}, "hosts": {}}
        
        if router_name:
            self.bridge_registry[bridge_name]["routers"][router_name] = {
                "interface": interface_name or "unknown",
                "ipv4": ipv4_address or "none",
                "state": state
            }
        
        if host_name:
            self.bridge_registry[bridge_name]["hosts"][host_name] = {
                "interface": interface_name or "unknown",
                "ipv4": ipv4_address or "none",
                "state": state
            }
    
    def unregister_bridge_connection(self, bridge_name: str, router_name: str = None, host_name: str = None):
        """Unregister a connection between a bridge and router/host."""
        if bridge_name not in self.bridge_registry:
            return
        
        if router_name and router_name in self.bridge_registry[bridge_name]["routers"]:
            del self.bridge_registry[bridge_name]["routers"][router_name]
        
        if host_name and host_name in self.bridge_registry[bridge_name]["hosts"]:
            del self.bridge_registry[bridge_name]["hosts"][host_name]
    
    def is_bridge_in_use(self, bridge_name: str) -> bool:
        """Check if a bridge is connected to any routers or hosts."""
        if bridge_name not in self.bridge_registry:
            return False
        
        registry_entry = self.bridge_registry[bridge_name]
        return len(registry_entry["routers"]) > 0 or len(registry_entry["hosts"]) > 0
    
    def get_unused_bridges(self) -> List[str]:
        """Get list of bridges that are not connected to any routers or hosts."""
        unused_bridges = []
        for bridge_name, connections in self.bridge_registry.items():
            if len(connections["routers"]) == 0 and len(connections["hosts"]) == 0:
                unused_bridges.append(bridge_name)
        return unused_bridges

    def get_interface_code(self, router_code: str, interface_name: str) -> str:
        """Get or generate interface code for given router and interface."""
        # Ensure router exists in registry
        if router_code not in self.interface_registry:
            self.interface_registry[router_code] = {}
        
        # If interface already has a code, return it
        if interface_name in self.interface_registry[router_code]:
            return self.interface_registry[router_code][interface_name]
        
        # Generate new interface code (i000 to i999)
        existing_codes = set(self.interface_registry[router_code].values())
        
        for i in range(1000):  # i000 to i999
            interface_code = f"i{i:03d}"
            if interface_code not in existing_codes:
                self.interface_registry[router_code][interface_name] = interface_code
                return interface_code
        
        # If we somehow reach 1000 interfaces, fall back to a hash-based approach
        import hashlib
        name_hash = hashlib.md5(interface_name.encode()).hexdigest()[:3]
        fallback_code = f"i{name_hash}"
        self.interface_registry[router_code][interface_name] = fallback_code
        return fallback_code

    def _validate_no_registry_conflicts(self):
        """Check for existing registry entries and raise exception if found (called during router code generation)."""
        existing_routers = set()
        
        # Check router registry
        if self.router_registry_file.exists():
            try:
                with open(self.router_registry_file, 'r') as f:
                    router_registry = json.load(f)
                
                # Check which of our target routers already exist in registry
                for router_name in self.routers.keys():
                    if router_name in router_registry:
                        existing_routers.add(router_name)
                        
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Could not read router registry: {e}")
        
        # Check interface registry
        existing_interface_routers = set()
        if self.interface_registry_file.exists():
            try:
                with open(self.interface_registry_file, 'r') as f:
                    interface_registry = json.load(f)
                
                # Load router registry to map codes back to names
                router_code_to_name = {}
                if self.router_registry_file.exists():
                    try:
                        with open(self.router_registry_file, 'r') as f:
                            router_registry = json.load(f)
                        for router_name, router_code in router_registry.items():
                            router_code_to_name[router_code] = router_name
                    except:
                        pass
                
                # Check if any router codes in interface registry match our target routers
                for router_code in interface_registry.keys():
                    router_name = router_code_to_name.get(router_code)
                    if router_name and router_name in self.routers:
                        existing_interface_routers.add(router_name)
                        
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Could not read interface registry: {e}")
        
        # Combine all existing routers
        all_existing = existing_routers.union(existing_interface_routers)
        
        if all_existing:
            existing_list = sorted(all_existing)
            router_word = "router" if len(all_existing) == 1 else "routers"
            
            error_msg = f"""
Registry entries already exist for {len(all_existing)} {router_word}: {', '.join(existing_list)}

This indicates that network setup has already been run for these routers.
To avoid conflicts, please clean up existing entries first:

For specific routers:
  sudo make netclean ARGS='--limit {existing_list[0]}' -v
  
For all routers:  
  sudo make netclean -v

Then run netsetup again.
"""
            raise RuntimeError(error_msg.strip())

    def validate_no_existing_registries(self):
        """Check for existing registry entries and raise exception if found."""
        existing_routers = set()
        
        # Check router registry
        if self.router_registry_file.exists():
            try:
                with open(self.router_registry_file, 'r') as f:
                    router_registry = json.load(f)
                
                # Check which of our target routers already exist in registry
                for router_name in self.routers.keys():
                    if router_name in router_registry:
                        existing_routers.add(router_name)
                        
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Could not read router registry: {e}")
        
        # Check interface registry
        existing_interface_routers = set()
        if self.interface_registry_file.exists():
            try:
                with open(self.interface_registry_file, 'r') as f:
                    interface_registry = json.load(f)
                
                # Load router registry to map codes back to names
                router_code_to_name = {}
                if self.router_registry_file.exists():
                    try:
                        with open(self.router_registry_file, 'r') as f:
                            router_registry = json.load(f)
                        for router_name, router_code in router_registry.items():
                            router_code_to_name[router_code] = router_name
                    except:
                        pass
                
                # Check if any router codes in interface registry match our target routers
                for router_code in interface_registry.keys():
                    router_name = router_code_to_name.get(router_code)
                    if router_name and router_name in self.routers:
                        existing_interface_routers.add(router_name)
                        
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Could not read interface registry: {e}")
        
        # Combine all existing routers
        all_existing = existing_routers.union(existing_interface_routers)
        
        if all_existing:
            existing_list = sorted(all_existing)
            router_word = "router" if len(all_existing) == 1 else "routers"
            
            error_msg = f"""
Registry entries already exist for {len(all_existing)} {router_word}: {', '.join(existing_list)}

This indicates that network setup has already been run for these routers.
To avoid conflicts, please clean up existing entries first:

For specific routers:
  sudo make netclean ARGS='--limit {existing_list[0]}' -v
  
For all routers:  
  sudo make netclean -v

Then run netsetup again.
"""
            raise RuntimeError(error_msg.strip())

    def _generate_router_codes(self):
        """Generate compressed router codes for hidden infrastructure naming."""
        # Validate no registry conflicts for target routers before generating codes
        self._validate_no_registry_conflicts()
        
        # Load existing registries first
        existing_registry = self.load_router_registry()
        self.router_codes.update(existing_registry)
        
        # Load interface and bridge registries
        self.interface_registry = self.load_interface_registry()
        self.load_bridge_registry()
        
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
        
        if self.verbose >= 3:
            self.logger.info(f"Generated {len(self.router_codes)} router codes")
        
        # Save the updated registries
        self.save_router_registry()
        self.save_interface_registry()
        
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
    
    def _needs_sudo(self, cmd: str, namespace: str = None) -> bool:
        """Check if a command needs sudo privileges."""
        # Phase 1 optimization: Use cached root check
        if self.is_root:
            return False
        
        # Phase 1 optimization: Check namespace first (early return)
        if namespace:
            return True
        
        # Phase 1 optimization: Use set for O(1) lookup on first word
        first_word = cmd.split()[0] if cmd else ''
        
        # Special cases that need checking beyond first word
        if first_word == 'echo' and '>' in cmd:
            return True
        elif first_word == 'ip':
            # Check second word for ip commands
            parts = cmd.split()
            if len(parts) > 1 and parts[1] in {'netns', 'link', 'addr', 'route', 'rule', 'tunnel', 'xfrm', 'tuntap'}:
                return True
        elif first_word == 'ipset':
            # Check second word for ipset commands
            parts = cmd.split()
            if len(parts) > 1 and parts[1] in {'create', 'add', 'destroy', 'save', 'restore'}:
                return True
        elif first_word == 'tc':
            # Check if it's tc qdisc
            if 'qdisc' in cmd:
                return True
        elif first_word in self.privileged_commands_set:
            return True
        
        return False
            
    def run_cmd(self, cmd: str, namespace: str = None, check: bool = True, log_cmd: bool = False):
        """Run a command, optionally in a namespace."""
        # Phase 2 optimization: Try to use command list instead of shell=True
        # Check if command contains shell metacharacters that require shell
        shell_required = any(char in cmd for char in ['|', '>', '<', '&', ';', '$', '`', '(', ')', '[', ']', '{', '}', '*', '?', '~'])
        
        if not shell_required:
            # Try to execute without shell for better performance
            try:
                return self._run_cmd_no_shell(cmd, namespace, check, log_cmd)
            except Exception as e:
                # Fall back to shell execution if parsing fails
                if self.verbose >= 3:
                    self.logger.debug(f"Failed to run without shell, falling back: {e}")
        
        # Original shell-based execution
        needs_sudo = self._needs_sudo(cmd, namespace)
        
        if namespace:
            if needs_sudo and not self.is_root:
                full_cmd = f"sudo ip netns exec {namespace} {cmd}"
            else:
                full_cmd = f"ip netns exec {namespace} {cmd}"
        else:
            if needs_sudo and not self.is_root:
                full_cmd = f"sudo {cmd}"
            else:
                full_cmd = cmd
            
        # Log command details for -vvv level
        if self.verbose >= 3 and log_cmd:
            print(f"      CMD: {full_cmd}")
        
        if self.verbose >= 3:
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
            if self.verbose >= 1:
                self.logger.error(f"Command failed: {full_cmd}")
                self.logger.error(f"Error: {result.stderr}")
            raise subprocess.CalledProcessError(result.returncode, full_cmd, result.stderr)
            
        return result
    
    def _run_cmd_no_shell(self, cmd: str, namespace: str = None, check: bool = True, log_cmd: bool = False):
        """Run a command without shell=True for better performance.
        
        Phase 2 optimization: Direct execution without shell overhead.
        """
        import shlex
        
        # Parse command into list
        cmd_parts = shlex.split(cmd)
        if not cmd_parts:
            return subprocess.CompletedProcess(args=[], returncode=0)
        
        # Determine if command needs sudo
        needs_sudo = self._needs_sudo(cmd, namespace)
        
        # Build command list
        if namespace:
            if needs_sudo and not self.is_root:
                cmd_list = ['sudo', 'ip', 'netns', 'exec', namespace] + cmd_parts
            else:
                cmd_list = ['ip', 'netns', 'exec', namespace] + cmd_parts
        else:
            if needs_sudo and not self.is_root:
                cmd_list = ['sudo'] + cmd_parts
            else:
                cmd_list = cmd_parts
        
        # Log command details for -vvv level
        if self.verbose >= 3 and log_cmd:
            print(f"      CMD: {' '.join(cmd_list)}")
        
        if self.verbose >= 3:
            self.logger.debug(f"Running (no shell): {' '.join(cmd_list)}")
        
        result = subprocess.run(
            cmd_list, capture_output=True, text=True, check=check
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
            if self.verbose >= 1:
                self.logger.error(f"Command failed: {' '.join(cmd_list)}")
                self.logger.error(f"Error: {result.stderr}")
            raise subprocess.CalledProcessError(result.returncode, cmd_list, result.stderr)
            
        return result
    
    def run_cmd_batch(self, cmds: List[str], namespace: str = None, check: bool = True):
        """Run multiple commands in batch mode for better performance.
        
        Phase 2 optimization: Batch multiple commands together to reduce subprocess overhead.
        """
        if not cmds:
            return
        
        # Group commands by type for IP batch mode
        ip_route_cmds = []
        ip_rule_cmds = []
        other_cmds = []
        
        for cmd in cmds:
            if cmd.startswith('ip route add'):
                # Extract route spec after 'ip route add'
                route_spec = cmd[13:].strip()
                ip_route_cmds.append(route_spec)
            elif cmd.startswith('ip rule add'):
                # Extract rule spec after 'ip rule add'
                rule_spec = cmd[12:].strip()
                ip_rule_cmds.append(rule_spec)
            else:
                other_cmds.append(cmd)
        
        # Execute IP route commands in batch
        if ip_route_cmds:
            batch_content = '\n'.join(f"route add {spec}" for spec in ip_route_cmds)
            batch_cmd = f"ip -batch -"
            
            if namespace:
                if not self.is_root:
                    full_cmd = ['sudo', 'ip', 'netns', 'exec', namespace, 'ip', '-batch', '-']
                else:
                    full_cmd = ['ip', 'netns', 'exec', namespace, 'ip', '-batch', '-']
            else:
                if not self.is_root:
                    full_cmd = ['sudo', 'ip', '-batch', '-']
                else:
                    full_cmd = ['ip', '-batch', '-']
            
            if self.verbose >= 2:
                self.logger.info(f"Executing {len(ip_route_cmds)} routes in batch mode")
            
            # Phase 2 optimization: Use subprocess without shell=True
            result = subprocess.run(
                full_cmd, 
                input=batch_content,
                capture_output=True, 
                text=True, 
                check=False
            )
            
            if result.returncode != 0 and check:
                if self.verbose >= 1:
                    self.logger.error(f"Batch route command failed")
                    self.logger.error(f"Error: {result.stderr}")
                # Fall back to individual commands on batch failure
                for cmd in [f"ip route add {spec}" for spec in ip_route_cmds]:
                    self.run_cmd(cmd, namespace, check=False)
        
        # Execute IP rule commands in batch
        if ip_rule_cmds:
            batch_content = '\n'.join(f"rule add {spec}" for spec in ip_rule_cmds)
            
            if namespace:
                if not self.is_root:
                    full_cmd = ['sudo', 'ip', 'netns', 'exec', namespace, 'ip', '-batch', '-']
                else:
                    full_cmd = ['ip', 'netns', 'exec', namespace, 'ip', '-batch', '-']
            else:
                if not self.is_root:
                    full_cmd = ['sudo', 'ip', '-batch', '-']
                else:
                    full_cmd = ['ip', '-batch', '-']
            
            if self.verbose >= 2:
                self.logger.info(f"Executing {len(ip_rule_cmds)} rules in batch mode")
            
            result = subprocess.run(
                full_cmd, 
                input=batch_content,
                capture_output=True, 
                text=True, 
                check=False
            )
            
            if result.returncode != 0 and check:
                if self.verbose >= 1:
                    self.logger.error(f"Batch rule command failed")
                    self.logger.error(f"Error: {result.stderr}")
                # Fall back to individual commands on batch failure
                for cmd in [f"ip rule add {spec}" for spec in ip_rule_cmds]:
                    self.run_cmd(cmd, namespace, check=False)
        
        # Execute other commands individually
        for cmd in other_cmds:
            self.run_cmd(cmd, namespace, check)
        
    def setup_hidden_mesh_network(self):
        """Set up network with hidden mesh infrastructure."""
        try:
            if self.verbose >= 2:
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
            
            # Save final interface and bridge registries
            self.save_interface_registry()
            self.save_bridge_registry()
            
        except Exception as e:
            if self.verbose >= 1:
                self.logger.error(f"Setup failed: {e}")
            self.cleanup_network()
            return False
        
        # Check if setup was successful - only CRITICAL infrastructure errors mean failure
        # Non-critical errors (routing errors, warnings, iptables warnings) are acceptable
        
        # Check for critical infrastructure failures
        for router_name, stats in self.router_stats.items():
            # Namespace creation failure - CRITICAL
            if not stats['namespace_created']:
                return False
                
            # Interface failures - CRITICAL
            if stats['interfaces_failed'] > 0:
                return False
                
            # Bridge connection failures - CRITICAL
            if stats['bridges_failed'] > 0:
                return False
                
            # NOTE: The following are NON-CRITICAL and do not cause failure:
            # - Route addition errors (stats['route_errors'])
            # - Routing warnings (in stats['warnings'])
            # - Iptables warnings (skipped rules)
            # - Non-existent routing tables
            # - Policy rules referencing broken tables
        
        # Check infrastructure failures
        if self.infrastructure_stats['bridges_failed'] > 0:
            return False
            
        # Only return True if absolutely everything succeeded
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
        
        total_bridges = sum(stats['bridges_total'] for stats in self.router_stats.values())
        connected_bridges = sum(stats['bridges_connected'] for stats in self.router_stats.values())
        failed_bridges = sum(stats['bridges_failed'] for stats in self.router_stats.values())
        
        total_warnings = sum(len(stats['warnings']) for stats in self.router_stats.values())
        total_errors = sum(len(stats['errors']) for stats in self.router_stats.values())
        
        # Count skipped sections
        routers_with_skipped = [name for name, stats in self.router_stats.items() 
                               if stats['skipped_sections']]
        
        if self.verbose >= 1:
            print("\n=== SETUP SUMMARY ===")
            print(f"Routers: {successful} successful, {partial} partial, {failed} failed (total: {total_routers})")
            # Format infrastructure bridges summary
            infra_created = self.infrastructure_stats['bridges_created']
            infra_existing = self.infrastructure_stats['bridges_existing']
            infra_total = self.infrastructure_stats['bridges_total']
            infra_failed = self.infrastructure_stats['bridges_failed']
            
            if infra_existing > 0:
                print(f"Infrastructure bridges: {infra_created} created, {infra_existing} existing, {infra_failed} failed (total: {infra_total})")
            else:
                print(f"Infrastructure bridges: {infra_created}/{infra_total} created, {infra_failed} failed")
            print(f"Interfaces: {created_interfaces}/{total_interfaces} created, {failed_interfaces} failed")
            print(f"Bridge connections: {connected_bridges}/{total_bridges} created, {failed_bridges} failed")
            
            # Bridge connections already shown in main summary line above
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
            
            # Report all errors at verbose level 1+
            if self.verbose >= 1:
                # General errors
                routers_with_errors = []
                for router_name, stats in self.router_stats.items():
                    if stats['errors']:
                        routers_with_errors.append(router_name)
                
                if routers_with_errors:
                    print(f"\nGeneral errors:")
                    for router_name in sorted(routers_with_errors):
                        stats = self.router_stats[router_name]
                        print(f"  {router_name}:")
                        for error in stats['errors']:
                            print(f"    • {error}")
                
                # Route errors
                routers_with_route_errors = []
                for router_name, stats in self.router_stats.items():
                    if 'route_errors' in stats and stats['route_errors']:
                        routers_with_route_errors.append(router_name)
                
                if routers_with_route_errors:
                    print(f"\nRoute addition errors:")
                    for router_name in sorted(routers_with_route_errors):
                        stats = self.router_stats[router_name]
                        print(f"  {router_name}:")
                        for error in stats['route_errors']:
                            print(f"    • {error}")
            
            # Report warnings in detail at verbose level 1+
            if self.verbose >= 1:
                # Separate warnings by category
                route_warnings = {}
                iptables_warnings = {}
                other_warnings = {}
                
                for router_name, stats in self.router_stats.items():
                    for warning in stats['warnings']:
                        if 'route' in warning.lower() or 'gateway' in warning.lower() or 'TOS' in warning:
                            if router_name not in route_warnings:
                                route_warnings[router_name] = []
                            route_warnings[router_name].append(warning)
                        elif 'iptables' in warning.lower():
                            if router_name not in iptables_warnings:
                                iptables_warnings[router_name] = []
                            iptables_warnings[router_name].append(warning)
                        else:
                            if router_name not in other_warnings:
                                other_warnings[router_name] = []
                            other_warnings[router_name].append(warning)
                
                # Print route warnings
                if route_warnings:
                    print(f"\nRoute addition warnings:")
                    for router_name in sorted(route_warnings.keys()):
                        print(f"  {router_name}:")
                        for warning in route_warnings[router_name]:
                            print(f"    • {warning}")
                
                # Print iptables warnings
                if iptables_warnings:
                    print(f"\nIptables configuration warnings:")
                    for router_name in sorted(iptables_warnings.keys()):
                        print(f"  {router_name}:")
                        for warning in iptables_warnings[router_name]:
                            print(f"    • {warning}")
                
                # Print other warnings
                if other_warnings:
                    print(f"\nOther warnings:")
                    for router_name in sorted(other_warnings.keys()):
                        print(f"  {router_name}:")
                        for warning in other_warnings[router_name]:
                            print(f"    • {warning}")
            
            if failed == 0 and failed_interfaces == 0 and failed_bridges == 0 and self.infrastructure_stats['bridges_failed'] == 0:
                print("\n✓ Network setup completed successfully!")
            elif failed == 0 and failed_interfaces == 0 and failed_bridges == 0:
                print("\n⚠ Network setup completed with infrastructure bridge issues")
            elif failed == 0 and failed_interfaces == 0:
                print("\n⚠ Network setup completed with bridge connection issues")
            elif failed == 0:
                print("\n⚠ Network setup completed with interface and/or bridge issues")
            else:
                print("\n✗ Network setup completed with router failures")
        
            
    def create_hidden_infrastructure(self):
        """Create hidden mesh infrastructure namespace."""
        if self.verbose >= 1:
            print("\n=== Creating hidden mesh infrastructure ===")
        
        # Check if namespace exists first
        result = self.run_cmd(f"ip netns list | grep -w {self.hidden_ns}", check=False)
        if result.returncode == 0:
            # Namespace exists - this is OK for hidden-mesh as it's a known tsim namespace
            if self.verbose > 0:
                self.logger.warning(f"Hidden namespace {self.hidden_ns} already exists, continuing...")
            self.created_namespaces.add(self.hidden_ns)
            return
        
        try:
            self.run_cmd(f"ip netns add {self.hidden_ns}")
            self.created_namespaces.add(self.hidden_ns)
            if self.verbose >= 3:
                self.logger.debug(f"Created hidden namespace {self.hidden_ns}")
            
        except subprocess.CalledProcessError as e:
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
            self.run_cmd(f"sysctl -w net.ipv4.ip_forward=1", self.hidden_ns)
            self.run_cmd(f"ip link set lo up", self.hidden_ns)
            self.logger.debug(f"Configured hidden namespace {self.hidden_ns}")
            
        except subprocess.CalledProcessError as e:
            error_msg = f"CRITICAL: Failed to configure hidden namespace {self.hidden_ns}: {e}"
            self.logger.error(error_msg)
            raise Exception(error_msg)
        
        # Create bridges for each subnet in hidden namespace
        self._create_subnet_bridges()
        
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
        
        # Initialize bridge counters
        self.infrastructure_stats['bridges_total'] = len(subnets)
        
        if self.verbose >= 1:
            print(f"  → Creating {len(subnets)} subnet bridges")
        
        for subnet in subnets:
            # Create bridge name with new zero-padded format
            bridge_name = self._generate_bridge_name(subnet)
            
            # Check if bridge already exists in registry
            if bridge_name in self.bridge_registry:
                # Bridge already exists in registry, mark as existing
                self.created_bridges.add(bridge_name)
                self.infrastructure_stats['bridges_existing'] += 1
                
                if self.verbose >= 2:
                    print(f"    ◯ Bridge {bridge_name} for {subnet} (existing)")
            else:
                # Bridge doesn't exist in registry, create it
                try:
                    self.run_cmd(f"ip link add {bridge_name} type bridge", self.hidden_ns)
                    self.run_cmd(f"ip link set {bridge_name} up", self.hidden_ns)
                    self.created_bridges.add(bridge_name)
                    self.infrastructure_stats['bridges_created'] += 1
                    
                    # Initialize bridge in registry (will be populated when routers connect)
                    self.bridge_registry[bridge_name] = {"routers": {}, "hosts": {}}
                    
                    if self.verbose >= 2:
                        print(f"    ✓ Bridge {bridge_name} for {subnet}")
                    
                except subprocess.CalledProcessError as e:
                    self.infrastructure_stats['bridges_failed'] += 1
                    if self.verbose >= 2:
                        print(f"    ✗ Bridge {bridge_name} for {subnet} (failed)")
                    self.logger.error(f"Failed to create bridge {bridge_name}: {e}")
                
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
        if self.verbose >= 3:
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
                
            if self.verbose >= 2:
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
            if self.verbose >= 2:
                print(f"\n[{i}/{len(self.routers)}] Setting up router: {router_name}")
            
            # Initialize router statistics
            self.router_stats[router_name] = {
                'namespace_created': False,
                'interfaces_created': 0,
                'interfaces_failed': 0,
                'total_interfaces': len(self.router_interfaces.get(router_name, [])),
                'interfaces_success': False,  # True only if ALL interfaces successful
                'bridges_total': 0,
                'bridges_connected': 0,
                'bridges_failed': 0,
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
                if self.verbose >= 2:
                    print(f"  → Creating namespace {router_name}")
                
                # Check if namespace exists first
                result = self.run_cmd(f"ip netns list | grep -w {router_name}", check=False)
                if result.returncode == 0:
                    # Namespace exists - check if it's tsim-managed
                    if self._is_tsim_managed_namespace(router_name):
                        if self.verbose > 0:
                            self.logger.warning(f"Namespace {router_name} already exists (tsim-managed), continuing...")
                        if self.verbose >= 2:
                            print(f"    ⚠ Namespace already exists (tsim-managed)")
                        self.router_stats[router_name]['warnings'].append("Namespace already existed (tsim-managed)")
                        self.created_namespaces.add(router_name)
                        self.router_stats[router_name]['namespace_created'] = True
                    else:
                        # Not tsim-managed - critical error
                        error_msg = f"CRITICAL: Namespace {router_name} already exists but is not managed by tsim"
                        self.router_stats[router_name]['errors'].append(error_msg)
                        self.logger.error(error_msg)
                        raise Exception(error_msg)
                else:
                    # Namespace doesn't exist - create it
                    try:
                        self.run_cmd(f"ip netns add {router_name}")
                        self.created_namespaces.add(router_name)
                        self.router_stats[router_name]['namespace_created'] = True
                        if self.verbose >= 2:
                            print(f"    ✓ Namespace created")
                    except subprocess.CalledProcessError as e:
                        error_msg = f"Failed to create namespace: {e}"
                        self.router_stats[router_name]['errors'].append(error_msg)
                        self.logger.error(f"Critical error for {router_name}: {error_msg}")
                        continue
                
                # Enable IP forwarding
                if self.verbose >= 2:
                    print(f"    → Enabling IP forwarding")
                try:
                    self.run_cmd(f"sysctl -w net.ipv4.ip_forward=1", router_name)
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
        
        if self.verbose >= 2:
            print(f"  → Creating {len(interfaces)} interfaces")
        
        for i, interface_config in enumerate(interfaces, 1):
            interface_name = interface_config['name']
            addresses = interface_config['addresses']
            
            # We'll print the result on one line after processing
            
            try:
                # Create unique veth pair names using compressed router codes (max 15 chars for Linux interface names)
                router_code = self.router_codes[router_name]  # e.g. r00, r01, r02
                
                # Get sequential interface code (i000 to i999) to ensure uniqueness
                interface_code = self.get_interface_code(router_code, interface_name)
                interface_abbrev = interface_code  # e.g. i000, i001, i002
                    
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
                    
                    if self.verbose >= 2:
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
                    
                    if self.verbose >= 2:
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
                    
                    if self.verbose >= 2:
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
                    
                    if self.verbose >= 2:
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
                        if self.verbose >= 2:
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
                if self.verbose >= 2:
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
        
        for i, (router_name, interfaces) in enumerate(self.router_interfaces.items(), 1):
            if self.verbose >= 1:
                print(f"\n[{i}/{len(self.router_interfaces)}] Connecting {router_name}")
            
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
                        
                        # Use sequential interface code (same as interface creation)
                        interface_code = self.get_interface_code(router_code, interface_name)
                        veth_hidden = f"{router_code}{interface_code}h"
                        
                        # Count bridge connection attempt
                        self.router_stats[router_name]['bridges_total'] += 1
                        
                        try:
                            self.run_cmd(f"ip link set {veth_hidden} master {bridge_name}", self.hidden_ns)
                            self.router_stats[router_name]['bridges_connected'] += 1
                            
                            # Extract IPv4 address from addr_info
                            ipv4_addr = ip_addr if ip_addr else "none"
                            
                            # Register the bridge connection in registry with detailed info
                            self.register_bridge_connection(
                                bridge_name=bridge_name, 
                                router_name=router_name,
                                interface_name=interface_name,  # Real interface name (e.g., bond1.vlan180)
                                ipv4_address=ipv4_addr,
                                state="UP"  # Assume UP since we successfully connected
                            )
                            
                            if self.verbose >= 2:
                                print(f"    ✓ {interface_name} → {bridge_name} ({ipv4_addr} on {subnet}, UP)")
                        except subprocess.CalledProcessError as e:
                            self.router_stats[router_name]['bridges_failed'] += 1
                            if self.verbose >= 2:
                                print(f"    ✗ {interface_name} → {bridge_name} (on {subnet}, FAILED)")
                            self.logger.error(f"CRITICAL: Failed to connect {veth_hidden} to {bridge_name}: {e}")
                            
                            self.router_stats[router_name]['errors'].append(f"Bridge connection failed for {interface_name}: {e}")
                            
                            # Continue processing other interfaces instead of raising exception
                            continue
                            
                    except Exception as e:
                        self.logger.warning(f"Failed to process IP {addr_info}: {e}")
                        continue
                        
    def apply_complete_configurations(self):
        """Apply complete router configurations from raw facts."""
        if self.verbose >= 1:
            print("\n=== Applying router configurations ===")
        
        for i, (router_name, router_facts) in enumerate(self.routers.items(), 1):
            if self.verbose >= 2:
                print(f"\n[{i}/{len(self.routers)}] Configuring {router_name}")
            
            stats = self.router_stats[router_name]
            
            # Only proceed if interfaces were 100% successful
            if not stats['interfaces_success']:
                if self.verbose >= 2:
                    print(f"  ⚠ Skipping configuration due to interface failures")
                stats['skipped_sections'] = ['routing', 'ipsets', 'iptables']
                continue
            
            try:
                # Apply routing configuration
                if self.verbose >= 2:
                    print(f"  → Applying routing configuration")
                self._apply_routing_configuration(router_name, router_facts)
                
                # Only proceed with ipsets if routing was 100% successful
                if stats['routing_success']:
                    if self.verbose >= 2:
                        print(f"  → Applying ipsets configuration")
                    self._apply_ipsets_configuration(router_name, router_facts)
                    
                    # Only proceed with iptables if ipsets was 100% successful
                    if stats['ipsets_success']:
                        if self.verbose >= 2:
                            print(f"  → Applying iptables configuration")
                        self._apply_iptables_configuration(router_name, router_facts)
                    else:
                        if self.verbose >= 2:
                            print(f"  ⚠ Skipping iptables due to ipsets failures")
                        stats['skipped_sections'].append('iptables')
                else:
                    if self.verbose >= 2:
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
        broken_tables = set()  # Track tables that don't exist on the production router
        
        try:
            # First, identify broken routing tables (tables that don't exist on production router)
            for section_name, section in router_facts.sections.items():
                if section_name.startswith('routing_table_') and section_name != 'routing_table_main':
                    table_identifier = section_name.replace('routing_table_', '')
                    
                    # Check if the routing table content indicates an error
                    content = section.content.strip()
                    if content and ('Error:' in content or 'does not exist' in content):
                        broken_tables.add(table_identifier)
                        if self.verbose >= 2:
                            self.logger.warning(f"Router {router_name} has non-existent table {table_identifier} in production")
                        stats['warnings'].append(f"Production router error: table {table_identifier} does not exist")
            
            # Apply policy rules FIRST to ensure custom routing tables are created
            # But skip rules that reference broken tables
            policy_section = router_facts.get_section('policy_rules')
            if policy_section:
                rule_count = self._apply_policy_rules(router_name, policy_section.content, router_facts, broken_tables)
                rules_applied += rule_count
            
            # Now apply main routing table
            routing_section = router_facts.get_section('routing_table_main')
            if routing_section:
                route_count, route_errors, route_warnings = self._apply_routes(router_name, routing_section.content, 'main')
                routes_applied += route_count
                errors.extend(route_errors)
                stats['warnings'].extend(route_warnings)
                tables_applied += 1
                applied_tables.append('main')
            
            # Finally apply additional routing tables (custom tables should now exist)
            for section_name, section in router_facts.sections.items():
                if section_name.startswith('routing_table_') and section_name != 'routing_table_main':
                    table_identifier = section_name.replace('routing_table_', '')
                    
                    # Skip broken tables
                    if table_identifier in broken_tables:
                        if self.verbose >= 3:
                            self.logger.info(f"Skipping broken table {table_identifier} for {router_name}")
                        continue
                    
                    # Check if table_identifier is already a numeric ID
                    if table_identifier.isdigit():
                        table_id = table_identifier
                    else:
                        # Look up table name in rt_tables mapping
                        table_id = self._get_table_id(table_identifier, router_facts)
                    
                    if table_id:
                        route_count, route_errors, route_warnings = self._apply_routes(router_name, section.content, table_id)
                        routes_applied += route_count
                        errors.extend(route_errors)
                        stats['warnings'].extend(route_warnings)
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
            
            # Mark as successful (even if some routes failed)
            stats['routing_success'] = True
            if errors:
                stats['route_errors'] = errors
            
            if self.verbose >= 1:
                if errors:
                    summary = f"    ⚠ routing: {routes_applied} routes"
                else:
                    summary = f"    ✓ routing: {routes_applied} routes"
                if rules_applied > 0:
                    summary += f", {rules_applied} rules"
                if applied_tables:
                    summary += f", {len(applied_tables)} tables ({', '.join(applied_tables)})"
                if errors:
                    summary += f", {len(errors)} errors"
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
        """Apply routing table entries in dependency order."""
        if not routes_content.strip():
            return 0, [], []
        
        # Print router info at level 1 when starting to add routes
        if self.verbose == 1 and routes_content.strip():
            print(f"    {router_name}: adding routes to table {table}")
        
        routes_count = 0
        route_errors = []
        route_warnings = []
        
        # Flush the routing table before adding routes
        if table != 'main':
            flush_cmd = f"ip route flush all table {table}"
        else:
            flush_cmd = "ip route flush all table main"
        
        try:
            self.run_cmd(flush_cmd, router_name)
            self.logger.debug(f"Flushed routing table {table}")
        except subprocess.CalledProcessError as e:
            # It's OK if flush fails (e.g., table doesn't exist yet)
            self.logger.debug(f"Table flush failed (may not exist yet): {e}")
        
        # Handle embedded newlines and escaped tabs in content
        routes_content = routes_content.replace('\\n', '\n').replace('\\t', ' ')
        
        # Collect all routes first
        routes = []
        import re
        for line in routes_content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Additional cleanup for escaped characters
            line = line.replace('\\t', ' ').replace('\\', '')
            
            # Normalize multiple spaces to single spaces
            line = re.sub(r'\s+', ' ', line)
            
            # No need to skip kernel routes anymore since we're flushing the table
            routes.append(line)
        
        # Sort routes by dependency order
        def route_priority(route):
            """Return priority for route ordering (lower = higher priority)."""
            # Priority 1: Host routes (/32) and link-scoped routes
            if '/32' in route or 'scope link' in route:
                return 1
            # Priority 2: Network routes (with prefix)
            elif re.search(r'\d+\.\d+\.\d+\.\d+/\d+', route) and 'via' not in route:
                return 2
            # Priority 3: Routes via gateway (but not default)
            elif 'via' in route and not route.startswith('default'):
                return 3
            # Priority 4: Default routes
            elif route.startswith('default'):
                return 4
            # Priority 5: Everything else
            else:
                return 5
        
        # Sort routes by priority
        sorted_routes = sorted(routes, key=route_priority)
        
        # Track routes to detect duplicates that differ only by source IP
        route_signatures = {}  # key: (dest, dev, metric, proto, scope), value: list of (route, src_ip)
        
        # Parse routes to detect duplicates
        for route in sorted_routes:
            # Extract key components of the route
            parts = route.split()
            dest = parts[0] if parts else ""
            dev = ""
            src = ""
            metric = ""
            proto = ""
            scope = ""
            
            # Parse route components
            for i, part in enumerate(parts):
                if part == "dev" and i + 1 < len(parts):
                    dev = parts[i + 1]
                elif part == "src" and i + 1 < len(parts):
                    src = parts[i + 1]
                elif part == "metric" and i + 1 < len(parts):
                    metric = parts[i + 1]
                elif part == "proto" and i + 1 < len(parts):
                    proto = parts[i + 1]
                elif part == "scope" and i + 1 < len(parts):
                    scope = parts[i + 1]
            
            # Create signature without source IP
            signature = (dest, dev, metric, proto, scope)
            
            if signature not in route_signatures:
                route_signatures[signature] = []
            route_signatures[signature].append((route, src))
        
        # Apply routes in order, adding TOS for duplicates
        tos_counter = 0
        # Valid TOS values - must have ECN bits (0-1) as 0, so values must be multiples of 4
        tos_values = ["0x00", "0x04", "0x08", "0x0c", "0x10", "0x14", "0x18", "0x1c", 
                      "0x20", "0x24", "0x28", "0x2c", "0x30", "0x34", "0x38", "0x3c"]
        
        # Track added connected routes to avoid duplicates
        added_connected_routes = set()
        
        # Phase 2 optimization: Collect all route commands for batch execution
        route_commands = []
        
        for route in sorted_routes:
            # Check if this route has a gateway that needs a connected route
            route_parts = route.split()
            gateway_ip = None
            gateway_dev = None
            
            # Parse route to find gateway and device
            for i, part in enumerate(route_parts):
                if part == "via" and i + 1 < len(route_parts):
                    gateway_ip = route_parts[i + 1]
                elif part == "dev" and i + 1 < len(route_parts):
                    gateway_dev = route_parts[i + 1]
            
            # If route has a gateway, check if we need to add a connected route
            if gateway_ip and gateway_dev:
                # Check if this is a valid IP address
                try:
                    import ipaddress
                    gw_addr = ipaddress.ip_address(gateway_ip)
                    
                    # Find the subnet for this gateway from interface configuration
                    interface_info = self._find_interface_subnet(router_name, gateway_dev, gateway_ip)
                    if interface_info:
                        subnet = interface_info['subnet']
                        interface_ip = interface_info['ip']
                        
                        # Check if connected route needs to be added
                        connected_route_key = (table, subnet, gateway_dev)
                        if connected_route_key not in added_connected_routes:
                            # Check if this connected route already exists in sorted_routes
                            connected_exists = any(
                                subnet in r and gateway_dev in r and "proto kernel" in r 
                                for r in sorted_routes
                            )
                            
                            if not connected_exists:
                                # Add connected route to this table
                                connected_route = f"{subnet} dev {gateway_dev} proto kernel scope link src {interface_ip}"
                                if table != 'main':
                                    connected_cmd = f"ip route add table {table} {connected_route}"
                                else:
                                    connected_cmd = f"ip route add {connected_route}"
                                
                                # Phase 2: Collect command instead of executing immediately
                                route_commands.append(connected_cmd)
                                added_connected_routes.add(connected_route_key)
                                route_warnings.append(f"Added missing connected route for gateway {gateway_ip}: {connected_route}")
                                if self.verbose >= 2:
                                    self.logger.info(f"Will add missing connected route: {connected_route}")
                                
                except (ipaddress.AddressValueError, ValueError):
                    # Not a valid IP address, skip
                    pass
            
            # Check if this route needs TOS
            modified_route = route
            for signature, route_list in route_signatures.items():
                if len(route_list) > 1:  # Multiple routes with same signature
                    for idx, (r, src) in enumerate(route_list):
                        if r == route and idx > 0:  # Not the first occurrence
                            # Add TOS to make it unique
                            tos_idx = idx % len(tos_values)
                            modified_route = f"{route} tos {tos_values[tos_idx]}"
                            route_warnings.append(f"Added TOS {tos_values[tos_idx]} to duplicate route (same destination, different source IP): {route}")
                            if self.verbose >= 2:
                                self.logger.info(f"Adding TOS {tos_values[tos_idx]} to duplicate route with src {src}")
                            break
            
            # Apply route
            if table != 'main':
                cmd = f"ip route add table {table} {modified_route}"
            else:
                cmd = f"ip route add {modified_route}"
            
            # Phase 2: Collect command for batch execution
            route_commands.append(cmd)
            if self.verbose >= 2:
                self.logger.info(f"Will add route: {modified_route}")
        
        # Phase 2: Execute all route commands in batch
        if route_commands:
            if self.verbose >= 2:
                self.logger.info(f"Executing {len(route_commands)} route commands in batch mode")
            
            try:
                self.run_cmd_batch(route_commands, router_name, check=False)
                routes_count = len(route_commands)
            except Exception as e:
                # Fall back to individual execution on batch failure
                if self.verbose >= 1:
                    self.logger.warning(f"Batch execution failed, falling back to individual commands: {e}")
                
                for cmd in route_commands:
                    try:
                        self.run_cmd(cmd, router_name)
                        routes_count += 1
                    except subprocess.CalledProcessError as e:
                        # Extract route from command
                        route = cmd.replace('ip route add table', '').replace('ip route add', '').strip()
                        if route.startswith(table + ' '):
                            route = route[len(table)+1:].strip()
                        
                        error_msg = f"Route '{route}' in table '{table}': {str(e)}"
                        if e.stderr:
                            error_msg += f" - {e.stderr.strip()}"
                        route_errors.append(error_msg)
                        if self.verbose >= 2:
                            self.logger.error(f"Route add failed: {error_msg}")
                    except Exception as e:
                        route = cmd.replace('ip route add table', '').replace('ip route add', '').strip()
                        if route.startswith(table + ' '):
                            route = route[len(table)+1:].strip()
                        
                        error_msg = f"Route '{route}' in table '{table}': {str(e)}"
                        route_errors.append(error_msg)
                        if self.verbose >= 2:
                            self.logger.error(f"Route add failed: {error_msg}")
        
        return routes_count, route_errors, route_warnings
                
    def _apply_policy_rules(self, router_name: str, rules_content: str, router_facts: RouterRawFacts, broken_tables: set = None):
        """Apply policy routing rules, skipping rules for broken tables."""
        if not rules_content.strip():
            return 0
        
        # Print router info at level 1 when starting to add rules
        if self.verbose == 1:
            print(f"    {router_name}: adding policy rules")
        
        if broken_tables is None:
            broken_tables = set()
        
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
        import re
        
        # Phase 2: Collect all rule commands for batch execution
        rule_commands = []
        
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
                
                # Check if rule references a broken table
                skip_rule = False
                for broken_table in broken_tables:
                    if f'lookup {broken_table}' in rule_spec:
                        if self.verbose >= 2:
                            self.logger.warning(f"Skipping rule that references broken table {broken_table}: {line}")
                        skip_rule = True
                        break
                
                if skip_rule:
                    continue
                
                # Convert table names to IDs using dynamic mapping
                for table_name, table_id in table_name_to_id.items():
                    rule_spec = rule_spec.replace(f'lookup {table_name}', f'table {table_id}')
                
                cmd = f"ip rule add pref {priority} {rule_spec}"
                
                # Phase 2: Collect command for batch execution
                rule_commands.append(cmd)
                self.logger.debug(f"Will add rule: {rule_spec}")
        
        # Phase 2: Execute all rule commands in batch
        if rule_commands:
            if self.verbose >= 2:
                self.logger.info(f"Executing {len(rule_commands)} rule commands in batch mode")
            
            try:
                self.run_cmd_batch(rule_commands, router_name, check=False)
                rules_count = len(rule_commands)
            except Exception as e:
                # Fall back to individual execution on batch failure
                if self.verbose >= 1:
                    self.logger.warning(f"Batch rule execution failed, falling back to individual commands: {e}")
                
                for cmd in rule_commands:
                    try:
                        self.run_cmd(cmd, router_name, check=False)
                        rules_count += 1
                    except Exception as e:
                        self.logger.debug(f"Rule add failed (expected): {e}")
        
        return rules_count
    
    def _find_interface_subnet(self, router_name: str, interface_name: str, gateway_ip: str):
        """Find the subnet and interface IP for a given interface that can reach the gateway."""
        import ipaddress
        
        # Get interface configuration for this router
        interfaces = self.router_interfaces.get(router_name, [])
        
        for interface in interfaces:
            if interface['name'] == interface_name:
                # Check each address on this interface
                for addr_info in interface['addresses']:
                    try:
                        # Parse the interface address
                        interface_addr = ipaddress.ip_interface(addr_info['ip'])
                        gateway_addr = ipaddress.ip_address(gateway_ip)
                        
                        # Check if gateway is in this subnet
                        if gateway_addr in interface_addr.network:
                            return {
                                'subnet': str(interface_addr.network),
                                'ip': str(interface_addr.ip)
                            }
                    except (ipaddress.AddressValueError, ValueError):
                        continue
        
        return None
                    
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
                    stats['iptables_success'] = False
                    if self.verbose >= 1:
                        print(f"    ✗ iptables: configuration failed")
                    # Don't raise exception - iptables failures are non-critical
            else:
                stats['iptables_success'] = True  # No iptables to apply
                if self.verbose >= 1:
                    print(f"    ✓ iptables: no configuration")
        except Exception as e:
            stats['iptables_success'] = False
            # Don't add to errors or re-raise - iptables issues are non-critical
            if self.verbose >= 1:
                print(f"    ✗ iptables: {str(e)}")
            
    def _apply_iptables_save(self, router_name: str, iptables_content: str):
        """Apply iptables configuration using iptables-restore."""
        if not iptables_content.strip():
            return True, 0
        
        # Filter out problematic rules that may not work in namespaces
        filtered_lines = []
        removed_rules = []
        stats = self.router_stats[router_name]
        
        for line in iptables_content.split('\n'):
            # Skip time-based rules which require kernel modules not available in namespaces
            if '-m time' in line:
                removed_rules.append("time-based rule (kernel module not available in namespace)")
                if self.verbose >= 2:
                    self.logger.warning(f"Skipping time-based rule for {router_name}: {line.strip()}")
                # Extract a meaningful identifier from the rule (comment or key details)
                rule_summary = line.strip()
                if '-m comment --comment' in line:
                    # Extract comment content
                    import re
                    comment_match = re.search(r'-m comment --comment "([^"]+)"', line)
                    if comment_match:
                        rule_summary = f"rule with comment '{comment_match.group(1)}'"
                else:
                    # Truncate long rules
                    if len(rule_summary) > 80:
                        rule_summary = rule_summary[:77] + "..."
                stats['warnings'].append(f"Skipped time-based iptables rule (kernel module not available): {rule_summary}")
                continue
            filtered_lines.append(line)
        
        filtered_content = '\n'.join(filtered_lines)
        
        # Count rules in the filtered content (lines that don't start with # or :)
        rule_count = sum(1 for line in filtered_content.split('\n') 
                        if line.strip() and not line.startswith('#') and not line.startswith(':') and not line.startswith('*') and not line.startswith('COMMIT'))
        
        try:
            if router_name:
                # Add sudo if not running as root
                if os.geteuid() != 0:
                    full_cmd = f"sudo ip netns exec {router_name} iptables-restore"
                else:
                    full_cmd = f"ip netns exec {router_name} iptables-restore"
            else:
                full_cmd = "iptables-restore"
            
            if self.verbose >= 3:
                self.logger.info(f"Applying iptables to {router_name}: {len(filtered_content)} chars")
            
            # Use subprocess.run to pass content directly via stdin (same as ipsets)
            result = subprocess.run(
                full_cmd.split(), input=filtered_content, text=True, 
                capture_output=True, check=False
            )
            
            if result.returncode != 0:
                if self.verbose >= 1:
                    self.logger.error(f"iptables-restore failed for {router_name}: {result.stderr}")
                return False, rule_count
            else:
                self.logger.debug(f"iptables-restore succeeded for {router_name}")
                return True, rule_count
            
        except Exception as e:
            if self.verbose >= 1:
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
        
        # Parse ipset content to adjust maxelem for sets that need it
        import re
        lines = ipset_content.split('\n')
        
        # First pass: count members per set
        set_members = {}
        current_set = None
        
        for line in lines:
            if line.startswith('create '):
                # Extract set name
                match = re.match(r'create (\w+)', line)
                if match:
                    current_set = match.group(1)
                    set_members[current_set] = 0
            elif line.startswith('add ') and current_set:
                # Count members for current set
                if line.startswith(f'add {current_set} '):
                    set_members[current_set] += 1
        
        # Second pass: adjust maxelem where needed
        adjusted_lines = []
        sets_adjusted = []
        
        for line in lines:
            if line.startswith('create '):
                # Parse create line
                match = re.match(r'create (\w+) .* maxelem (\d+)', line)
                if match:
                    set_name = match.group(1)
                    maxelem = int(match.group(2))
                    actual_members = set_members.get(set_name, 0)
                    
                    # Keep doubling maxelem until it's larger than actual members
                    original_maxelem = maxelem
                    while actual_members >= maxelem:
                        maxelem *= 2
                    
                    if maxelem != original_maxelem:
                        # Replace maxelem value in line
                        line = re.sub(r'maxelem \d+', f'maxelem {maxelem}', line)
                        sets_adjusted.append(f"{set_name}: {actual_members} members, maxelem {original_maxelem}->{maxelem}")
                
            adjusted_lines.append(line)
        
        if sets_adjusted:
            if self.verbose >= 3:
                self.logger.info(f"Adjusted maxelem for {len(sets_adjusted)} ipsets in {router_name}:")
            if self.verbose >= 3:
                for adjustment in sets_adjusted[:5]:  # Show first 5
                    self.logger.info(f"  {adjustment}")
                if len(sets_adjusted) > 5:
                    self.logger.info(f"  ... and {len(sets_adjusted) - 5} more")
        
        ipset_content = '\n'.join(adjusted_lines)
        
        try:
            if router_name:
                # Add sudo if not running as root
                if os.geteuid() != 0:
                    full_cmd = f"sudo ip netns exec {router_name} ipset restore"
                else:
                    full_cmd = f"ip netns exec {router_name} ipset restore"
            else:
                full_cmd = "ipset restore"
            
            if self.verbose >= 3:
                self.logger.info(f"Applying ipsets to {router_name}: {len(ipset_content)} chars, {ipset_content.count('create')} creates, {ipset_content.count('add')} adds")
            
            # Use subprocess.PIPE to pass content directly via stdin
            result = subprocess.run(
                full_cmd.split(), input=ipset_content, text=True, 
                capture_output=True, check=False
            )
            
            if result.returncode != 0:
                if self.verbose >= 1:
                    self.logger.error(f"ipset restore failed for {router_name}: {result.stderr}")
                if self.verbose >= 1:
                    self.logger.error(f"Return code: {result.returncode}")
                    if result.stdout:
                        self.logger.error(f"Stdout: {result.stdout}")
                return False, set_count, member_count
            else:
                if self.verbose >= 3:
                    self.logger.info(f"ipset restore succeeded for {router_name}")
                return True, set_count, member_count
            
        except Exception as e:
            if self.verbose >= 1:
                self.logger.error(f"ipset restore failed (exception) for {router_name}: {e}")
            return False, set_count, member_count
            
    def cleanup_network(self):
        """Clean up all created network resources."""
        if self.verbose >= 2:
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
                if self.verbose >= 2:
                    self.logger.info(f"Cleaned up {len(simulation_interfaces)} leftover interfaces from host namespace")
                
        except Exception as e:
            self.logger.debug(f"Error during host namespace cleanup: {e}")
        
    def verify_setup(self):
        """Verify the network setup."""
        if self.verbose >= 2:
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
            if self.verbose >= 2:
                self.logger.info("Network setup verification passed")
        else:
            if self.verbose >= 1:
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
    
    # No longer require root - sudo will be added to individual commands as needed
    # Just check if user is in tsim-users group
    import grp
    import pwd
    try:
        username = pwd.getpwuid(os.getuid()).pw_name
        tsim_group = grp.getgrnam('tsim-users')
        if username not in tsim_group.gr_mem and os.getuid() != 0:
            if args.verbose >= 1:
                print("Warning: User not in tsim-users group. Namespace operations may fail.")
                print("Run: sudo usermod -a -G tsim-users $USER")
    except (KeyError, OSError):
        if args.verbose >= 1 and os.getuid() != 0:
            print("Warning: tsim-users group not found. Namespace operations may fail.")
            print("Run: sudo groupadd -f tsim-users")
    
    setup = HiddenMeshNetworkSetup(verbose=args.verbose, limit_pattern=args.limit)
    
    try:
        if args.cleanup:
            setup.cleanup_network()
            if args.verbose >= 1:
                print("Network cleanup completed")
            return 0
        
        # Load facts from raw facts only
        setup.load_raw_facts_only()
        
        # Set up hidden mesh network
        success = setup.setup_hidden_mesh_network()
        if not success:
            if args.verbose >= 1:
                print("Network setup failed!")
            return 1
        
        # Verify if requested
        if args.verify:
            if not setup.verify_setup():
                return 1
        
        # Silent mode - no output at all
        
    except KeyboardInterrupt:
        if args.verbose >= 1:
            print("\nSetup interrupted")
        setup.cleanup_network()
        return 1
    except Exception as e:
        if args.verbose >= 1:
            print(f"Setup failed: {e}")
        setup.cleanup_network()
        return 1
    
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())