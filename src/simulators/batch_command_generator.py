#!/usr/bin/env -S python3 -B -u
"""
Batch Command Generator for Network Setup

Creates ip -b compatible batch files in shared memory.
Commands are EXACTLY copied from working network_namespace_setup.py with ZERO changes.
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
import hashlib
import uuid
import json
import logging
import logging.handlers
from datetime import datetime
import yaml
import time

# Import from installed package
from tsim.core.raw_facts_block_loader import RawFactsBlockLoader
from tsim.core.tsim_shm_manager import TsimBatchMemory
from tsim.core.config_loader import get_registry_paths, load_traceroute_config

# Don't import the full class, just copy what we need

class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.hostname = os.uname().nodename
        self.pid = os.getpid()
        
    def format(self, record):
        """Format log record as JSON"""
        log_obj = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage(),
            'hostname': self.hostname,
            'pid': self.pid,
            'thread': record.thread,
            'thread_name': record.threadName
        }
        
        # Add extra fields if present
        if hasattr(record, 'command'):
            log_obj['command'] = record.command
        if hasattr(record, 'batch_name'):
            log_obj['batch_name'] = record.batch_name
        if hasattr(record, 'chunk_name'):
            log_obj['chunk_name'] = record.chunk_name
        if hasattr(record, 'returncode'):
            log_obj['returncode'] = record.returncode
        if hasattr(record, 'duration'):
            log_obj['duration'] = record.duration
        if hasattr(record, 'error_type'):
            log_obj['error_type'] = record.error_type
        if hasattr(record, 'errors'):
            log_obj['errors'] = record.errors
        if hasattr(record, 'warnings'):
            log_obj['warnings'] = record.warnings
            
        # Add stdout/stderr if configured and present
        if self.config.get('log_outputs', True):
            max_size = self.config.get('max_output_size', 10000)
            if hasattr(record, 'stdout') and record.stdout:
                stdout = record.stdout
                if len(stdout) > max_size:
                    stdout = stdout[:max_size] + f"\n... (truncated {len(stdout) - max_size} bytes)"
                log_obj['stdout'] = stdout
            if hasattr(record, 'stderr') and record.stderr:
                stderr = record.stderr
                if len(stderr) > max_size:
                    stderr = stderr[:max_size] + f"\n... (truncated {len(stderr) - max_size} bytes)"
                log_obj['stderr'] = stderr
        
        # Handle exceptions
        if record.exc_info:
            log_obj['exception'] = self.formatException(record.exc_info)
        
        # Add any other extra fields from the record
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName', 
                          'levelname', 'levelno', 'lineno', 'module', 'msecs', 
                          'pathname', 'process', 'processName', 'relativeCreated',
                          'thread', 'threadName', 'exc_info', 'exc_text', 'stack_info',
                          'getMessage', 'command', 'batch_name', 'chunk_name', 
                          'returncode', 'duration', 'stdout', 'stderr', 'errors', 
                          'warnings', 'error_type']:
                log_obj[key] = value
        
        return json.dumps(log_obj, ensure_ascii=False)

class BatchCommandGenerator:
    """
    Generates batch files with EXACT commands from network_namespace_setup.py
    """
    
    def __init__(self, verbose: int = 0, log_file: str = None):
        self.verbose = verbose
        
        # Load configuration first (needed for unix_group)
        self.config = load_traceroute_config()
        
        # Get unix group from config
        self.unix_group = self.config.get('system', {}).get('unix_group', 'tsim-users')
        
        # Ensure /dev/shm/tsim directory exists with proper permissions
        self._ensure_shm_directory()
        
        # Use hidden namespace from config
        self.hidden_ns = self.config.get('network_setup', {}).get('hidden_namespace', 'tsim-hidden')
        
        # Setup logging with config
        self.setup_logging(log_file)
        
        # Load raw facts
        raw_facts_path = os.environ.get('TRACEROUTE_SIMULATOR_RAW_FACTS')
        if not raw_facts_path:
            raise EnvironmentError("TRACEROUTE_SIMULATOR_RAW_FACTS environment variable must be set")
        
        self.raw_facts_dir = Path(raw_facts_path)
        if not self.raw_facts_dir.exists():
            raise FileNotFoundError(f"Raw facts directory not found: {self.raw_facts_dir}")
            
        # Initialize facts loader - EXACTLY as in network_namespace_setup.py line 106
        self.facts_loader = RawFactsBlockLoader(verbose=self.verbose)
        
        # Session ID for unique batch names
        self.session_id = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()[:8]
        
        # Track all batch files created
        self.batch_files = []
        
        # Initialize registries (copied from network_namespace_setup.py)
        registry_paths = get_registry_paths()
        self.router_registry_file = Path(registry_paths['routers'])
        self.interface_registry_file = Path(registry_paths['interfaces'])
        self.bridge_registry_file = Path(registry_paths['bridges'])
        
        # Registry data structures
        self.router_codes = {}  # router_name -> router_code
        self.interface_registry = {}  # router_code -> {interface_name -> interface_code}
        self.bridge_registry = {}  # bridge_name -> {"routers": {}, "hosts": {}}
    
    def _ensure_shm_directory(self):
        """
        Ensure /dev/shm/tsim directory exists with proper permissions.
        Must have mode 2775 and be owned by current_user:unix_group.
        """
        shm_dir = Path('/dev/shm/tsim')
        
        # Create directory if it doesn't exist
        if not shm_dir.exists():
            try:
                shm_dir.mkdir(mode=0o2775, parents=True, exist_ok=True)
                if self.verbose:
                    print(f"Created {shm_dir} with mode 2775")
            except Exception as e:
                print(f"Warning: Could not create {shm_dir}: {e}")
                return
        
        # Try to set proper permissions and ownership
        try:
            import grp
            import pwd
            
            # Get current user
            uid = os.getuid()
            
            # Get unix group from config
            try:
                gid = grp.getgrnam(self.unix_group).gr_gid
            except KeyError:
                print(f"Warning: {self.unix_group} group not found. Please create it with: sudo groupadd {self.unix_group}")
                return
            
            # Set group ownership (keep current user)
            os.chown(shm_dir, -1, gid)  # -1 keeps current user, only changes group
            
            # Set permissions to 2775 (setgid + rwxrwxr-x)
            os.chmod(shm_dir, 0o2775)
            
            if self.verbose:
                user_name = pwd.getpwuid(uid).pw_name
                print(f"Set {shm_dir} ownership to {user_name}:{self.unix_group} with mode 2775")
                
        except PermissionError:
            # If not running as root, try to at least set the permissions we can
            try:
                current_stat = shm_dir.stat()
                if current_stat.st_gid == grp.getgrnam(self.unix_group).gr_gid:
                    # Directory has correct group, just ensure setgid bit
                    os.chmod(shm_dir, 0o2775)
                else:
                    print(f"Warning: Cannot set ownership of {shm_dir}. Run as root or ensure you own the directory.")
            except Exception as e:
                print(f"Warning: Could not set permissions on {shm_dir}: {e}")
        except Exception as e:
            print(f"Warning: Could not configure {shm_dir}: {e}")
    
    def setup_logging(self, log_file: str = None):
        """
        Setup logging based on configuration from traceroute_simulator.yaml
        """
        # Get logging config
        log_config = self.config.get('logging', {})
        batch_config = log_config.get('batch_generator', {})
        
        # Determine log file path
        if log_file is None:
            log_base_dir = Path(log_config.get('base_directory', '/dev/shm/tsim/logs'))
            # Support env override
            if 'TRACEROUTE_SIMULATOR_LOGS' in os.environ:
                log_base_dir = Path(os.environ['TRACEROUTE_SIMULATOR_LOGS'])
            
            log_base_dir.mkdir(parents=True, exist_ok=True)
            
            # Use pattern from config
            log_pattern = batch_config.get('log_file_pattern', 'batch_generator_%Y%m%d_%H%M%S.json')
            log_filename = datetime.now().strftime(log_pattern)
            log_file = log_base_dir / log_filename
        else:
            log_file = Path(log_file)
            log_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.log_file_path = log_file
        
        # Configure logger
        self.logger = logging.getLogger('BatchGenerator')
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()  # Clear any existing handlers
        
        # Determine log format
        use_json = log_config.get('format', 'json').lower() == 'json'
        
        # File handler - logs based on config file_level
        file_handler = logging.FileHandler(log_file)
        file_level = getattr(logging, log_config.get('file_level', 'DEBUG'))
        file_handler.setLevel(file_level)
        
        if use_json:
            # Custom JSON formatter
            file_handler.setFormatter(JsonFormatter(batch_config))
        else:
            file_formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
        
        self.logger.addHandler(file_handler)
        
        # Console handler - based on verbosity mapping in config
        console_handler = logging.StreamHandler()
        console_levels = log_config.get('console_levels', {})
        console_level_name = console_levels.get(
            str(self.verbose),  # Try string key first
            console_levels.get(self.verbose, 'CRITICAL')  # Then int key
        )
        console_level = getattr(logging, console_level_name)
        console_handler.setLevel(console_level)
        
        # Simple console format
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # Store config for later use
        self.log_config = batch_config
        
        self.logger.info(f"Logging initialized", extra={
            'log_file': str(log_file),
            'verbosity': self.verbose,
            'format': 'json' if use_json else 'text'
        })
        
    def create_batch(self, commands: List[str], batch_name: str) -> str:
        """
        Create a batch file in shared memory with given commands.
        
        Args:
            commands: List of commands for this batch
            batch_name: Name for the batch file
            
        Returns:
            Full batch name with session ID
        """
        full_batch_name = f"{batch_name}_{self.session_id}"
        
        # Create batch in shared memory
        batch = TsimBatchMemory(full_batch_name)
        batch.write('\n'.join(commands))
        
        # Track this batch
        self.batch_files.append(full_batch_name)
        
        if self.verbose >= 2:
            print(f"Created batch /dev/shm/tsim/batch_{full_batch_name} with {len(commands)} commands")
            
        return full_batch_name
        
    def _create_route_key(self, route, table):
        """Create a normalized key for route duplicate detection."""
        # Parse route to extract key components
        parts = route.split()
        destination = parts[0] if parts else ""
        
        # Extract key attributes
        dev = None
        via = None
        metric = None
        proto = None
        
        for i, part in enumerate(parts):
            if part == "dev" and i + 1 < len(parts):
                dev = parts[i + 1]
            elif part == "via" and i + 1 < len(parts):
                via = parts[i + 1]
            elif part == "metric" and i + 1 < len(parts):
                metric = parts[i + 1]
            elif part == "proto" and i + 1 < len(parts):
                proto = parts[i + 1]
        
        # Create key from essential components
        # Routes are duplicates if they have same destination, device, gateway, and table
        return (table, destination, dev, via)
    
    def _extract_route_signature(self, route):
        """Extract route signature for TOS duplicate detection (from working code)."""
        parts = route.split()
        
        # Extract components
        dest = parts[0] if parts else ""
        dev = None
        metric = None
        proto = None
        scope = None
        src = None
        
        for i, part in enumerate(parts):
            if part == "dev" and i + 1 < len(parts):
                dev = parts[i + 1]
            elif part == "metric" and i + 1 < len(parts):
                metric = parts[i + 1]
            elif part == "proto" and i + 1 < len(parts):
                proto = parts[i + 1]
            elif part == "scope" and i + 1 < len(parts):
                scope = parts[i + 1]
            elif part == "src" and i + 1 < len(parts):
                src = parts[i + 1]
        
        # Signature without source IP (for detecting duplicates that differ only by src)
        signature = (dest, dev, metric, proto, scope)
        return signature, src
    
    def check_and_add_connected_route(self, route, router_name, table_name, interface_info_map, 
                                      added_connected_routes, all_routes, route_commands):
        """Check if a route needs a connected route for its gateway and add it if needed."""
        import ipaddress
        import re
        
        # Parse route to find gateway and device
        route_parts = route.split()
        gateway_ip = None
        gateway_dev = None
        
        for i, part in enumerate(route_parts):
            if part == "via" and i + 1 < len(route_parts):
                gateway_ip = route_parts[i + 1]
            elif part == "dev" and i + 1 < len(route_parts):
                gateway_dev = route_parts[i + 1]
        
        # If route has a gateway, check if we need to add a connected route
        if gateway_ip and gateway_dev:
            try:
                gw_addr = ipaddress.ip_address(gateway_ip)
                
                # Find the subnet for this gateway from interface configuration
                if router_name in interface_info_map and gateway_dev in interface_info_map[router_name]:
                    for addr_info in interface_info_map[router_name][gateway_dev]:
                        if 'ip' in addr_info:
                            try:
                                interface_addr = ipaddress.ip_interface(addr_info['ip'])
                                # Check if gateway is in this subnet
                                if gw_addr in interface_addr.network:
                                    subnet = str(interface_addr.network)
                                    interface_ip = str(interface_addr.ip)
                                    
                                    # Check if connected route needs to be added
                                    connected_route_key = (table_name, subnet, gateway_dev)
                                    if connected_route_key not in added_connected_routes:
                                        # Check if this connected route already exists
                                        connected_exists = any(
                                            subnet in r and gateway_dev in r and "proto kernel" in r 
                                            for r in all_routes
                                        )
                                        
                                        if not connected_exists:
                                            # Only add connected route for non-main tables
                                            # Main table gets connected routes automatically when IPs are assigned
                                            if table_name != 'main':
                                                connected_route = f"{subnet} dev {gateway_dev} proto kernel scope link src {interface_ip}"
                                                cmd = f"netns exec {router_name} ip route add {connected_route} table {table_name}"
                                                route_commands.append(cmd)
                                                added_connected_routes.add(connected_route_key)
                                                if self.verbose >= 2:
                                                    print(f"    Adding connected route for gateway {gateway_ip} in table {table_name}: {connected_route}")
                                            elif self.verbose >= 3:
                                                print(f"    Skipping connected route for main table (auto-created): {subnet} dev {gateway_dev}")
                                    break
                            except (ipaddress.AddressValueError, ValueError):
                                continue
            except (ipaddress.AddressValueError, ValueError):
                pass
    
    def generate_all_batches(self):
        """
        Generate all batch files, copying EXACT commands from network_namespace_setup.py
        """
        # Load all routers - EXACTLY as in network_namespace_setup.py line 177
        raw_facts_dir = Path(os.environ.get('TRACEROUTE_SIMULATOR_RAW_FACTS'))
        all_routers = self.facts_loader.load_raw_facts_directory(raw_facts_dir)
        router_names = sorted(all_routers.keys())
        
        if self.verbose >= 1:
            print(f"Generating batches for {len(router_names)} routers")
        
        # ========================================
        # BATCH 1: Create all router namespaces
        # From network_namespace_setup.py line 1499: self.run_cmd(f"ip netns add {router_name}")
        # ========================================
        commands = []
        for router_name in router_names:
            # EXACT command from line 1499
            commands.append(f"netns add {router_name}")
        self.create_batch(commands, "create_routers")
        
        # ========================================
        # BATCH 2: Enable loopback in all routers
        # From network_namespace_setup.py line 1525: self.run_cmd(f"ip link set lo up", router_name)
        # ========================================
        commands = []
        for router_name in router_names:
            # When run_cmd has namespace parameter, it becomes: ip netns exec {namespace} {cmd}
            # So: ip netns exec {router_name} ip link set lo up
            commands.append(f"netns exec {router_name} ip link set lo up")
        self.create_batch(commands, "enable_router_loopback")
        
        # ========================================
        # BATCH 3: Enable IP forwarding in all routers
        # From network_namespace_setup.py line 1516: self.run_cmd(f"sysctl -w net.ipv4.ip_forward=1", router_name)
        # ========================================
        commands = []
        for router_name in router_names:
            # Enable IP forwarding for routing between subnets
            commands.append(f"netns exec {router_name} sysctl -w net.ipv4.ip_forward=1")
        self.create_batch(commands, "enable_ip_forwarding")
        
        # ========================================
        # BATCH 4: Create hidden namespace
        # From network_namespace_setup.py line 1233: self.run_cmd(f"ip netns add {self.hidden_ns}")
        # ========================================
        commands = []
        commands.append(f"netns add {self.hidden_ns}")
        self.create_batch(commands, "create_hidden")
        
        # ========================================
        # BATCH 5: Enable loopback and IP forwarding in hidden namespace
        # From network_namespace_setup.py lines 1253-1254
        # ========================================
        commands = []
        commands.append(f"netns exec {self.hidden_ns} ip link set lo up")
        commands.append(f"netns exec {self.hidden_ns} sysctl -w net.ipv4.ip_forward=1")
        self.create_batch(commands, "configure_hidden_namespace")
        
        # ========================================
        # BATCH 6: Extract unique subnets and create bridges
        # From network_namespace_setup.py lines 1328-1329
        # ========================================
        import re
        import ipaddress
        
        unique_subnets = set()
        subnet_to_bridge = {}
        router_interfaces = {}  # Store parsed interfaces for later use
        
        # Parse interfaces from raw facts - copying logic from network_namespace_setup.py
        for router_name, router_facts in all_routers.items():
            interfaces_section = router_facts.get_section('interfaces')
            if not interfaces_section:
                continue
            
            interfaces = []
            current_interface = None
            
            # Parse interfaces section (ip addr show output)
            for line in interfaces_section.content.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Interface line
                if_match = re.match(r'^\d+:\s+([^@:]+)(@\S+)?:\s+<([^>]+)>', line)
                if if_match:
                    if current_interface:
                        interfaces.append(current_interface)
                    current_interface = {
                        'name': if_match.group(1),
                        'addresses': []
                    }
                # inet line
                elif line.startswith('inet ') and current_interface:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            ip_with_prefix = parts[1]
                            network = ipaddress.ip_network(ip_with_prefix, strict=False)
                            current_interface['addresses'].append({
                                'family': 'inet',
                                'ip': ip_with_prefix,
                                'network': str(network)
                            })
                            unique_subnets.add(str(network))
                        except:
                            pass
            
            if current_interface:
                interfaces.append(current_interface)
            
            router_interfaces[router_name] = interfaces
        
        # Create bridges
        commands = []
        for idx, subnet in enumerate(sorted(unique_subnets)):
            bridge_name = f"br{idx:04d}"
            subnet_to_bridge[subnet] = bridge_name
            
            # Line 1328: self.run_cmd(f"ip link add {bridge_name} type bridge", self.hidden_ns)
            commands.append(f"netns exec {self.hidden_ns} ip link add {bridge_name} type bridge")
        self.create_batch(commands, "create_bridges")
        
        # ========================================
        # BATCH 7: Bring up all bridges
        # From network_namespace_setup.py line 1329
        # ========================================
        commands = []
        for bridge_name in subnet_to_bridge.values():
            # Line 1329: self.run_cmd(f"ip link set {bridge_name} up", self.hidden_ns)
            commands.append(f"netns exec {self.hidden_ns} ip link set {bridge_name} up")
        self.create_batch(commands, "enable_bridges")
        
        # ========================================
        # BATCH 8: Create veth pairs directly in target namespaces with final names
        # This avoids the need for separate move and rename operations
        # ========================================
        
        # Generate router codes EXACTLY as in working code
        # Store in self.router_codes for registry saving
        for idx, router_name in enumerate(router_names):
            self.router_codes[router_name] = f"r{idx:03d}"  # r000, r001, r002, etc. (3 digits like in working code)
        
        # Use self.interface_registry for saving later
        
        # We need to create veths from hidden namespace to router namespaces
        # This allows us to use the final interface name directly
        veth_commands = []
        veth_info = []  # Store info for later phases
        
        for router_name in router_names:
            interfaces = router_interfaces.get(router_name, [])
            router_code = self.router_codes[router_name]
            
            # Initialize interface registry for this router
            if router_code not in self.interface_registry:
                self.interface_registry[router_code] = {}
            
            # Interface counter for this router (sequential i000, i001, i002)
            interface_counter = 0
            
            for interface in interfaces:
                iface_name = interface.get('name')
                if iface_name == 'lo':
                    continue
                
                # Skip kernel-created tunnel interfaces that exist by default in every namespace
                # These can't be created as veth pairs since they already exist
                # The working code tries to rename to these and fails, then skips them
                # We skip them upfront to avoid batch failures
                if iface_name in ['tunl0', 'sit0', 'gre0', 'gretap0', 'erspan0', 
                                  'ip6tnl0', 'ip6gre0', 'ip_vti0', 'ip6_vti0']:
                    if self.verbose >= 2:
                        print(f"    Skipping kernel interface {iface_name} on {router_name}")
                    continue
                
                # Generate interface code for this router (3 digits like in working code)
                interface_code = f"i{interface_counter:03d}"
                self.interface_registry[router_code][iface_name] = interface_code
                interface_counter += 1
                
                # Generate hidden veth name (always unique per router+interface)
                veth_hidden = f"{router_code}{interface_code}h"  # e.g. r000i000h
                
                # Ensure names are within Linux 15-char limit
                if len(veth_hidden) > 15:
                    veth_hidden = veth_hidden[:15]
                
                # Use final interface name directly (truncate if needed)
                final_interface_name = iface_name[:15] if len(iface_name) > 15 else iface_name
                
                veth_info.append({
                    'veth_hidden': veth_hidden,
                    'router_name': router_name,
                    'interface_name': final_interface_name,
                    'original_interface_name': iface_name,
                    'addresses': interface.get('addresses', [])
                })
                
                # Create veth pair from hidden namespace with peer directly in router namespace
                # This creates the interface with the final name immediately
                veth_commands.append(f"netns exec {self.hidden_ns} ip link add {veth_hidden} type veth peer name {final_interface_name} netns {router_name}")
        
        # Create ONE batch for all veth pairs
        if veth_commands:
            self.create_batch(veth_commands, "create_veth_pairs_in_namespaces")
        
        # ========================================
        # BATCH 9: Configure IP addresses
        # ========================================
        ip_commands = []
        for info in veth_info:
            for addr_info in info['addresses']:
                if addr_info.get('family') == 'inet':
                    ip_addr = addr_info.get('ip')
                    if ip_addr:
                        # Line 1772: Add IP address
                        ip_commands.append(f"netns exec {info['router_name']} ip addr add {ip_addr} dev {info['interface_name']}")
        
        if ip_commands:
            self.create_batch(ip_commands, "configure_ip_addresses")
        
        # ========================================
        # BATCH 10: Bring up router interfaces
        # ========================================
        up_commands = []
        for info in veth_info:
            # Line 1803: Bring up interface
            up_commands.append(f"netns exec {info['router_name']} ip link set {info['interface_name']} up")
        
        if up_commands:
            self.create_batch(up_commands, "bring_up_router_interfaces")
        
        # ========================================
        # BATCH 11: Attach to bridges
        # ========================================
        bridge_commands = []
        for info in veth_info:
            bridge_name = None
            for addr_info in info['addresses']:
                if 'network' in addr_info:
                    bridge_name = subnet_to_bridge.get(addr_info['network'])
                    break
            
            if bridge_name:
                # Update bridge registry (matching network_namespace_setup.py)
                if bridge_name not in self.bridge_registry:
                    self.bridge_registry[bridge_name] = {"routers": {}, "hosts": {}}
                
                # Add router to bridge registry
                router_name = info['router_name']
                self.bridge_registry[bridge_name]["routers"][router_name] = {
                    "interface": info['interface_name'],
                    "veth_hidden": info['veth_hidden']
                }
                
                # Line 1889: Attach to bridge
                bridge_commands.append(f"netns exec {self.hidden_ns} ip link set {info['veth_hidden']} master {bridge_name}")
        
        if bridge_commands:
            self.create_batch(bridge_commands, "attach_to_bridges")
        
        # ========================================
        # BATCH 12: Bring up hidden interfaces
        # ========================================
        hidden_up_commands = []
        for info in veth_info:
            # Line 1819: Bring up hidden interface
            hidden_up_commands.append(f"netns exec {self.hidden_ns} ip link set {info['veth_hidden']} up")
        
        if hidden_up_commands:
            self.create_batch(hidden_up_commands, "bring_up_hidden_interfaces")
        
        # ========================================
        # BATCH 13: Apply policy routing rules FIRST
        # Rules must be created before routes in custom tables
        # ========================================
        rule_commands = []
        for router_name in router_names:
            if router_name not in all_routers:
                continue
            
            router_facts = all_routers[router_name]
            
            # First, identify broken routing tables (same as for routes)
            broken_tables = set()
            for section_name, section in router_facts.sections.items():
                if section_name.startswith('routing_table_') and section_name != 'routing_table_main':
                    table_identifier = section_name.replace('routing_table_', '')
                    content = section.content.strip()
                    if content and ('Error:' in content or 'does not exist' in content or 'FIB table does not exist' in content):
                        broken_tables.add(table_identifier)
            
            rules_section = router_facts.get_section('policy_rules')
            
            if rules_section and rules_section.content.strip():
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
                
                import re
                for line in rules_section.content.strip().split('\n'):
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
                                    print(f"    Skipping rule that references broken table {broken_table}: {line}")
                                skip_rule = True
                                break
                        
                        if skip_rule:
                            continue
                        
                        # Convert table names to IDs using dynamic mapping
                        for table_name, table_id in table_name_to_id.items():
                            rule_spec = rule_spec.replace(f'lookup {table_name}', f'table {table_id}')
                        
                        rule_commands.append(f"netns exec {router_name} ip rule add pref {priority} {rule_spec}")
        
        if rule_commands:
            self.create_batch(rule_commands, "apply_rules")
        
        # ========================================
        # BATCH 14: Apply routes for each router
        # Routes in custom tables need rules to be accessible
        # ========================================
        route_commands = []
        import re  # Import at function level for route processing
        import ipaddress  # For gateway validation
        
        # Build interface info map for gateway validation
        interface_info_map = {}
        for info in veth_info:
            router = info['router_name']
            if router not in interface_info_map:
                interface_info_map[router] = {}
            interface_info_map[router][info['interface_name']] = info['addresses']
        
        for router_name in router_names:
            if router_name not in all_routers:
                continue
            
            router_facts = all_routers[router_name]
            
            # First, identify broken routing tables (tables that don't exist on production router)
            broken_tables = set()
            for section_name, section in router_facts.sections.items():
                if section_name.startswith('routing_table_') and section_name != 'routing_table_main':
                    table_identifier = section_name.replace('routing_table_', '')
                    
                    # Check if the routing table content indicates an error
                    content = section.content.strip()
                    if content and ('Error:' in content or 'does not exist' in content or 'FIB table does not exist' in content):
                        broken_tables.add(table_identifier)
                        if self.verbose >= 2:
                            print(f"    Warning: Router {router_name} has non-existent table {table_identifier} in production")
            
            # Track added connected routes to avoid duplicates
            added_connected_routes = set()
            
            # Track all routes for this router to detect duplicates
            router_route_tracker = set()  # Track (table, route_key) to avoid duplicates
            
            # Track route signatures for TOS handling (like working code line 2234)
            route_signatures = {}  # key: (dest, dev, metric, proto, scope), value: list of (route, src, table)
            
            # Valid TOS values from working code line 2271
            tos_values = ["0x00", "0x04", "0x08", "0x0c", "0x10", "0x14", "0x18", "0x1c",
                         "0x20", "0x24", "0x28", "0x2c", "0x30", "0x34", "0x38", "0x3c"]
            
            # Track main routes for connected route checking
            main_routes = []
            
            # Get main routing table
            routes_section = router_facts.get_section('routing_table_main')
            if routes_section and routes_section.content.strip():
                # Apply same processing as working code (network_namespace_setup.py line 2193)
                routes_content = routes_section.content
                # Handle embedded newlines and escaped tabs
                routes_content = routes_content.replace('\\n', '\n').replace('\\t', ' ')
                
                # Collect routes first for analysis
                for line in routes_content.split('\n'):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    # Skip error lines
                    if 'Error:' in line or 'Dump terminated' in line:
                        continue
                    
                    # Additional cleanup for escaped characters (from line 2204)
                    # IMPORTANT: Only remove backslash that's followed by 't' or 'n', not all backslashes
                    line = line.replace('\\t', ' ')
                    # Remove only standalone backslashes at end of line or before space
                    line = re.sub(r'\\(\s|$)', r'\1', line)
                    
                    # Normalize multiple spaces to single spaces
                    line = re.sub(r'\s+', ' ', line)
                    
                    # Skip automatically generated connected routes (proto kernel scope link)
                    # These are created automatically when we add IP addresses to interfaces
                    if 'proto kernel' in line and 'scope link' in line:
                        if self.verbose >= 3:
                            print(f"    Skipping auto-generated connected route: {line}")
                        continue
                    
                    # Skip simple dev routes without gateway (auto-created when IP assigned)
                    parts = line.split()
                    if len(parts) >= 3 and parts[1] == 'dev' and 'via' not in line:
                        # Check if this looks like an auto-generated route
                        # Format: "192.168.1.0/24 dev eth0" or with src
                        if '/' in parts[0] and not any(keyword in line for keyword in ['proto', 'metric', 'table']):
                            if self.verbose >= 3:
                                print(f"    Skipping simple dev route (likely auto-generated): {line}")
                            continue
                    
                    main_routes.append(line)
                
                # Collect routes with signature tracking for TOS handling
                for route in main_routes:
                    # Extract signature for TOS duplicate detection
                    signature, src = self._extract_route_signature(route)
                    if signature not in route_signatures:
                        route_signatures[signature] = []
                    route_signatures[signature].append((route, src, 'main'))
            
            # Get additional routing tables (policy routing)
            sections = router_facts.sections
            for section_name in sections:
                if section_name.startswith('routing_table_') and section_name != 'routing_table_main':
                    table_identifier = section_name.replace('routing_table_', '')
                    
                    # Skip broken tables
                    if table_identifier in broken_tables:
                        if self.verbose >= 3:
                            print(f"    Skipping broken table {table_identifier} for {router_name}")
                        continue
                    
                    routes_section = router_facts.get_section(section_name)
                    if routes_section and routes_section.content.strip():
                        # Apply same processing as main table
                        content = routes_section.content
                        # Handle embedded newlines and escaped tabs
                        content = content.replace('\\n', '\n').replace('\\t', ' ')
                        
                        for line in content.split('\n'):
                            line = line.strip()
                            if not line or line.startswith('#'):
                                continue
                            # Skip error lines
                            if 'Error:' in line or 'Dump terminated' in line:
                                continue
                            
                            # Additional cleanup for escaped characters
                            line = line.replace('\\t', ' ')
                            # Remove only standalone backslashes at end of line or before space
                            line = re.sub(r'\\(\s|$)', r'\1', line)
                            
                            # Normalize multiple spaces to single spaces
                            line = re.sub(r'\s+', ' ', line)
                            
                            # Skip automatically generated connected routes (proto kernel scope link)
                            if 'proto kernel' in line and 'scope link' in line:
                                if self.verbose >= 3:
                                    print(f"    Skipping auto-generated connected route in table {table_identifier}: {line}")
                                continue
                            
                            # Skip simple dev routes without gateway (auto-created when IP assigned)
                            parts = line.split()
                            if len(parts) >= 3 and parts[1] == 'dev' and 'via' not in line:
                                # Check if this looks like an auto-generated route
                                if '/' in parts[0] and not any(keyword in line for keyword in ['proto', 'metric', 'table']):
                                    if self.verbose >= 3:
                                        print(f"    Skipping simple dev route in table {table_identifier} (likely auto-generated): {line}")
                                    continue
                            
                            # Save original line for debugging
                            original_line = line
                            
                            # Check if this is a multipath route (contains "nexthop" keyword)
                            # Multipath routes from dynamic routing daemons like ripd/ospfd use nexthop syntax
                            if 'nexthop' in line:
                                # For multipath routes, only remove table specification at the very end
                                # to avoid breaking nexthop syntax
                                line = re.sub(r'\s+table\s+\S+\s*$', '', line)
                            else:
                                # For regular routes, remove any table specification
                                line = re.sub(r'\s+table\s+\S+', '', line)
                            
                            # Debug problematic routes
                            if self.verbose >= 3 and original_line != line:
                                self.logger.debug(f"Route table removal", extra={
                                    'router': router_name,
                                    'table': table_identifier,
                                    'original': original_line,
                                    'cleaned': line
                                })
                            
                            # Check if table_identifier is already a numeric ID or needs lookup
                            if table_identifier.isdigit():
                                table_id = table_identifier
                            else:
                                # Look up table name in rt_tables mapping
                                rt_tables_section = router_facts.get_section('rt_tables')
                                table_id = None
                                if rt_tables_section:
                                    for rt_line in rt_tables_section.content.split('\n'):
                                        rt_line = rt_line.strip()
                                        if not rt_line or rt_line.startswith('#'):
                                            continue
                                        parts = rt_line.split()
                                        if len(parts) == 2 and parts[1] == table_identifier:
                                            table_id = parts[0]
                                            break
                                
                                if not table_id:
                                    if self.verbose >= 2:
                                        print(f"    Warning: Could not find table ID for {table_identifier}")
                                    continue
                            
                            # Collect route with signature for TOS handling
                            signature, src = self._extract_route_signature(line)
                            if signature not in route_signatures:
                                route_signatures[signature] = []
                            route_signatures[signature].append((line, src, table_id))
            
            # Now process all collected routes with TOS handling for duplicates
            # (Similar to working code lines 2280-2355)
            for signature, route_list in route_signatures.items():
                for idx, (route, src, table) in enumerate(route_list):
                    modified_route = route
                    
                    # If multiple routes with same signature, add TOS to make unique (except first)
                    if len(route_list) > 1 and idx > 0:
                        tos_idx = idx % len(tos_values)
                        modified_route = f"{route} tos {tos_values[tos_idx]}"
                        if self.verbose >= 2:
                            print(f"    Adding TOS {tos_values[tos_idx]} to duplicate route in {router_name}: {route}")
                    
                    # Check and add connected route if needed
                    # Note: Connected routes are auto-created for main table when IPs are assigned
                    # We only need to add them explicitly for other tables
                    if table != 'main':
                        self.check_and_add_connected_route(modified_route, router_name, table, interface_info_map,
                                                          added_connected_routes, [], route_commands)
                    
                    # Add the route with proper table handling
                    if 'nexthop' in modified_route:
                        # For multipath routes with nexthop, table must come before nexthop specs
                        nexthop_pos = modified_route.find('nexthop')
                        if nexthop_pos > 0:
                            route_prefix = modified_route[:nexthop_pos].rstrip()
                            nexthop_suffix = modified_route[nexthop_pos:]
                            if table != 'main':
                                route_commands.append(f"netns exec {router_name} ip route add {route_prefix} table {table} {nexthop_suffix}")
                            else:
                                route_commands.append(f"netns exec {router_name} ip route add {route_prefix} {nexthop_suffix}")
                        else:
                            if table != 'main':
                                route_commands.append(f"netns exec {router_name} ip route add table {table} {modified_route}")
                            else:
                                route_commands.append(f"netns exec {router_name} ip route add {modified_route}")
                    else:
                        # Regular route
                        if table != 'main':
                            route_commands.append(f"netns exec {router_name} ip route add {modified_route} table {table}")
                        else:
                            route_commands.append(f"netns exec {router_name} ip route add {modified_route}")
        
        if route_commands:
            self.create_batch(route_commands, "apply_routes")
        
        # ========================================
        # BATCH 15: Apply ipsets
        # ========================================
        # Ipsets need to be created individually per router using ipset restore
        ipset_commands = []
        for router_name in router_names:
            if router_name not in all_routers:
                continue
            
            router_facts = all_routers[router_name]
            ipset_section = router_facts.get_section('ipset_save')
            
            if ipset_section and ipset_section.content.strip():
                ipset_content = ipset_section.content
                
                # Parse ipset content to adjust maxelem for sets that need it
                # Also remove timeout values (approach 1 - treat all entries as permanent)
                import re
                lines = ipset_content.split('\n')
                
                # First pass: count members per set
                set_members = {}
                current_set = None
                
                for line in lines:
                    if line.startswith('create '):
                        # Extract set name
                        parts = line.split()
                        if len(parts) >= 2:
                            current_set = parts[1]
                            set_members[current_set] = 0
                    elif line.startswith('add ') and current_set:
                        # Count members for current set
                        if line.startswith(f'add {current_set} '):
                            set_members[current_set] += 1
                
                # Second pass: adjust maxelem where needed and remove timeout values
                adjusted_lines = []
                sets_adjusted = []
                timeout_entries_removed = 0
                
                for line in lines:
                    # Remove timeout values from add commands (treat as permanent)
                    if line.startswith('add ') and ' timeout ' in line:
                        line = re.sub(r'\s+timeout\s+\d+', '', line)
                        timeout_entries_removed += 1
                    
                    if line.startswith('create '):
                        # Remove default timeout from create line (for crowdsec ipsets)
                        # Otherwise entries added without timeout will expire
                        if ' timeout ' in line:
                            line = re.sub(r'\s+timeout\s+\d+', '', line)
                            if self.verbose >= 3:
                                print(f"      Removed default timeout from ipset create: {line.split()[1]}")
                        
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
                
                if (sets_adjusted or timeout_entries_removed > 0) and self.verbose >= 1:
                    if sets_adjusted:
                        print(f"    Warning: Adjusted maxelem for {len(sets_adjusted)} ipsets in {router_name}")
                        if self.verbose >= 2:
                            for adjustment in sets_adjusted[:5]:  # Show first 5
                                print(f"      {adjustment}")
                            if len(sets_adjusted) > 5:
                                print(f"      ... and {len(sets_adjusted) - 5} more")
                    if timeout_entries_removed > 0 and self.verbose >= 2:
                        print(f"    Info: Removed timeout values from {timeout_entries_removed} ipset entries in {router_name}")
                
                ipset_content = '\n'.join(adjusted_lines)
                
                # Write adjusted ipset content to temporary file and restore
                ipset_file = f"/dev/shm/tsim/ipset_{router_name}_{self.session_id}"
                with open(ipset_file, 'w') as f:
                    f.write(ipset_content)
                # Use cat with pipe to avoid shell redirection issues in ip -b
                ipset_commands.append(f"netns exec {router_name} sh -c 'cat {ipset_file} | ipset restore'")
        
        if ipset_commands:
            self.create_batch(ipset_commands, "apply_ipsets")
        
        # ========================================
        # BATCH 16: Apply iptables rules
        # ========================================
        # Iptables rules need to be restored per router using iptables-restore
        iptables_commands = []
        for router_name in router_names:
            if router_name not in all_routers:
                continue
            
            router_facts = all_routers[router_name]
            iptables_section = router_facts.get_section('iptables_save')
            
            if iptables_section and iptables_section.content.strip():
                # Filter out problematic rules that may not work in namespaces
                filtered_lines = []
                
                for line in iptables_section.content.split('\n'):
                    # Skip metadata lines from facts collection
                    if line.strip() == '---' or line.strip().startswith('EXIT_CODE:'):
                        continue
                    # Skip time-based rules which require kernel modules not available in namespaces
                    if '-m time' in line:
                        if self.verbose >= 2:
                            print(f"    Skipping time-based rule for {router_name}: {line.strip()}")
                        continue
                    filtered_lines.append(line)
                
                filtered_content = '\n'.join(filtered_lines)
                
                # Write filtered iptables content to temporary file and restore
                iptables_file = f"/dev/shm/tsim/iptables_{router_name}_{self.session_id}"
                with open(iptables_file, 'w') as f:
                    f.write(filtered_content)
                # Use cat with pipe to avoid shell redirection issues in ip -b
                iptables_commands.append(f"netns exec {router_name} sh -c 'cat {iptables_file} | iptables-restore --noflush'")
        
        if iptables_commands:
            self.create_batch(iptables_commands, "apply_iptables")
        
        # Save all registries after generating batches
        self.save_router_registry()
        self.save_interface_registry()
        self.save_bridge_registry()
        
        print(f"Generated {len(self.batch_files)} batch files in /dev/shm/tsim/")
        
    def cleanup_batch_files(self):
        """Remove all batch files created during this session."""
        removed_count = 0
        
        # Remove tracked batch files
        for batch_name in self.batch_files:
            # Add the batch_ prefix to match actual filename
            batch_path = f"/dev/shm/tsim/batch_{batch_name}"
            if os.path.exists(batch_path):
                try:
                    os.remove(batch_path)
                    removed_count += 1
                except OSError as e:
                    if self.verbose >= 1:
                        print(f"Warning: Could not remove {batch_path}: {e}")
        
        # Also remove any chunk files created during splitting (using session ID)
        batch_pattern = Path('/dev/shm/tsim').glob(f'batch_*_{self.session_id}')
        for batch_file in batch_pattern:
            try:
                batch_file.unlink()
                removed_count += 1
            except OSError as e:
                if self.verbose >= 2:
                    print(f"Warning: Could not remove {batch_file}: {e}")
        
        # Remove temporary ipset and iptables files
        for pattern in [f'ipset_*_{self.session_id}', f'iptables_*_{self.session_id}']:
            temp_files = Path('/dev/shm/tsim').glob(pattern)
            for temp_file in temp_files:
                try:
                    temp_file.unlink()
                    removed_count += 1
                except OSError:
                    pass
        
        if self.verbose >= 1:
            print(f"Removed {removed_count} batch and temporary files from /dev/shm/tsim/")
    
    def verify_setup(self):
        """
        Verify that created resources match the facts data.
        Uses registry files to know what was supposed to be created.
        """
        print("Verifying network setup against facts...")
        
        issues = []
        
        # Load registries
        router_registry = {}
        interface_registry = {}
        bridge_registry = {}
        
        if self.router_registry_file.exists():
            try:
                with open(self.router_registry_file, 'r') as f:
                    router_registry = json.load(f)
            except (IOError, json.JSONDecodeError) as e:
                issues.append(f"Could not load router registry: {e}")
        else:
            issues.append("Router registry file not found")
        
        if self.interface_registry_file.exists():
            try:
                with open(self.interface_registry_file, 'r') as f:
                    interface_registry = json.load(f)
            except (IOError, json.JSONDecodeError) as e:
                issues.append(f"Could not load interface registry: {e}")
        else:
            issues.append("Interface registry file not found")
        
        if self.bridge_registry_file.exists():
            try:
                with open(self.bridge_registry_file, 'r') as f:
                    bridge_registry = json.load(f)
            except (IOError, json.JSONDecodeError) as e:
                issues.append(f"Could not load bridge registry: {e}")
        else:
            issues.append("Bridge registry file not found")
        
        # Verify namespaces exist
        print(f"  Checking {len(router_registry)} router namespaces...")
        missing_namespaces = []
        existing_namespaces = 0
        
        # Get list of existing namespaces
        cmd = ['ip', 'netns', 'list']
        if os.geteuid() != 0:
            cmd = ['sudo'] + cmd
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            existing_ns_list = set()
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        # ip netns list format: "namespace_name (id: X)" or just "namespace_name"
                        ns_name = line.split()[0]
                        existing_ns_list.add(ns_name)
        except Exception as e:
            issues.append(f"Could not list namespaces: {e}")
            existing_ns_list = set()
        
        # Check each router namespace
        for router_name in router_registry.keys():
            if router_name in existing_ns_list:
                existing_namespaces += 1
            else:
                missing_namespaces.append(router_name)
        
        # Check hidden namespace
        if self.hidden_ns not in existing_ns_list:
            missing_namespaces.append(self.hidden_ns)
        
        if missing_namespaces:
            issues.append(f"Missing {len(missing_namespaces)} namespaces")
            if self.verbose >= 1:
                for ns in missing_namespaces[:10]:  # Show first 10
                    print(f"    ✗ Missing namespace: {ns}")
        else:
            print(f"    ✓ All {existing_namespaces + 1} namespaces exist")
        
        # Verify interfaces in each namespace
        print(f"  Checking interfaces in namespaces...")
        interfaces_ok = 0
        interfaces_missing = 0
        
        # Load facts to compare
        all_routers = self.facts_loader.load_raw_facts_directory(self.raw_facts_dir)
        
        for router_name, router_code in router_registry.items():
            if router_name not in existing_ns_list:
                continue  # Skip if namespace doesn't exist
            
            # Get expected interfaces from facts
            if router_name in all_routers:
                router_facts = all_routers[router_name]
                interfaces_section = router_facts.get_section('interfaces')
                
                if interfaces_section and router_code in interface_registry:
                    expected_interfaces = interface_registry[router_code]
                    
                    # List interfaces in namespace
                    cmd = ['ip', '-n', router_name, 'link', 'show']
                    if os.geteuid() != 0:
                        cmd = ['sudo'] + cmd
                    
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            actual_interfaces = set()
                            for line in result.stdout.split('\n'):
                                if ':' in line and not line.startswith(' '):
                                    # Format: "1: lo: <LOOPBACK,UP>"
                                    parts = line.split(':')
                                    if len(parts) >= 2:
                                        iface_name = parts[1].strip().split('@')[0]
                                        actual_interfaces.add(iface_name)
                            
                            # Compare expected vs actual (excluding kernel interfaces)
                            for iface_name in expected_interfaces.keys():
                                if iface_name in ['tunl0', 'sit0', 'gre0', 'gretap0', 'erspan0', 
                                                 'ip6tnl0', 'ip6gre0', 'ip_vti0', 'ip6_vti0']:
                                    continue  # Skip kernel interfaces we can't create
                                
                                if iface_name in actual_interfaces:
                                    interfaces_ok += 1
                                else:
                                    interfaces_missing += 1
                                    if self.verbose >= 2:
                                        print(f"    ✗ Missing interface {iface_name} in {router_name}")
                    except Exception as e:
                        if self.verbose >= 1:
                            print(f"    Error checking interfaces in {router_name}: {e}")
        
        if interfaces_missing > 0:
            issues.append(f"Missing {interfaces_missing} interfaces")
        print(f"    ✓ {interfaces_ok} interfaces verified")
        
        # Verify bridges
        print(f"  Checking {len(bridge_registry)} bridges...")
        bridges_ok = 0
        bridges_missing = 0
        
        # List bridges in hidden namespace
        cmd = ['ip', '-n', self.hidden_ns, 'link', 'show', 'type', 'bridge']
        if os.geteuid() != 0:
            cmd = ['sudo'] + cmd
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                actual_bridges = set()
                for line in result.stdout.split('\n'):
                    if ':' in line and not line.startswith(' '):
                        parts = line.split(':')
                        if len(parts) >= 2:
                            bridge_name = parts[1].strip()
                            actual_bridges.add(bridge_name)
                
                for bridge_name in bridge_registry.keys():
                    if bridge_name in actual_bridges:
                        bridges_ok += 1
                    else:
                        bridges_missing += 1
                        if self.verbose >= 1:
                            print(f"    ✗ Missing bridge: {bridge_name}")
        except Exception as e:
            issues.append(f"Could not check bridges: {e}")
        
        if bridges_missing > 0:
            issues.append(f"Missing {bridges_missing} bridges")
        else:
            print(f"    ✓ All {bridges_ok} bridges exist")
        
        # Verify routes
        print(f"  Checking routes...")
        routes_ok = 0
        routes_checked = 0
        
        for router_name in router_registry.keys():
            if router_name not in existing_ns_list:
                continue
            
            # Get actual routes
            cmd = ['ip', '-n', router_name, 'route', 'show']
            if os.geteuid() != 0:
                cmd = ['sudo'] + cmd
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    actual_routes = result.stdout.strip()
                    routes_checked += 1
                    # Simple check - just verify we have routes (more than just kernel routes)
                    if actual_routes and len(actual_routes.split('\n')) > 0:
                        routes_ok += 1
                    elif self.verbose >= 2:
                        print(f"    ✗ No routes in {router_name}")
            except Exception as e:
                if self.verbose >= 1:
                    print(f"    Error checking routes in {router_name}: {e}")
        
        if routes_checked > 0 and routes_ok < routes_checked:
            issues.append(f"Missing routes in {routes_checked - routes_ok} routers")
        elif routes_ok > 0:
            print(f"    ✓ Routes configured in {routes_ok} routers")
        
        # Verify policy routing rules
        print(f"  Checking policy routing rules...")
        rules_ok = 0
        rules_configured = 0
        
        for router_name in router_registry.keys():
            if router_name not in existing_ns_list or router_name not in all_routers:
                continue
            
            router_facts = all_routers[router_name]
            rules_section = router_facts.get_section('policy_rules')
            
            if rules_section and rules_section.content.strip():
                # Count non-default rules in facts
                expected_rules = 0
                for line in rules_section.content.strip().split('\n'):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    # Skip default rules
                    if not (line.startswith('0:') or line.startswith('32766:') or line.startswith('32767:')):
                        expected_rules += 1
                
                if expected_rules > 0:
                    rules_configured += 1
                    
                    # Get actual rules
                    cmd = ['ip', '-n', router_name, 'rule', 'show']
                    if os.geteuid() != 0:
                        cmd = ['sudo'] + cmd
                    
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            # Count non-default rules
                            actual_rules = 0
                            for line in result.stdout.strip().split('\n'):
                                # Skip default rules (0, 32766, 32767)
                                if not any(line.startswith(p) for p in ['0:', '32766:', '32767:']):
                                    actual_rules += 1
                            
                            if actual_rules > 0:
                                rules_ok += 1
                            elif self.verbose >= 2:
                                print(f"    ✗ No custom policy rules in {router_name}")
                    except Exception as e:
                        if self.verbose >= 1:
                            print(f"    Error checking rules in {router_name}: {e}")
        
        if rules_configured > 0 and rules_ok < rules_configured:
            issues.append(f"Missing policy rules in {rules_configured - rules_ok} routers")
        elif rules_ok > 0:
            print(f"    ✓ Policy rules configured in {rules_ok} routers")
        
        # Verify ipsets
        print(f"  Checking ipsets...")
        import time
        ipsets_start = time.time()
        ipsets_ok = 0
        ipsets_configured = 0
        ipsets_mismatched = []
        
        for router_name in router_registry.keys():
            if router_name not in existing_ns_list or router_name not in all_routers:
                continue
            
            router_facts = all_routers[router_name]
            ipset_section = router_facts.get_section('ipset_save')
            
            if ipset_section and ipset_section.content.strip():
                ipsets_configured += 1
                expected_content = ipset_section.content.strip()
                
                # Get actual ipset save output
                cmd = ['ip', 'netns', 'exec', router_name, 'ipset', 'save']
                if os.geteuid() != 0:
                    cmd = ['sudo'] + cmd
                
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        actual_content = result.stdout.strip()
                        
                        # Normalize both for comparison (remove comments and empty lines)
                        def normalize_ipset(content):
                            import re
                            lines = []
                            for line in content.split('\n'):
                                line = line.strip()
                                # Skip empty lines, comments, and metadata from facts
                                if not line or line.startswith('#'):
                                    continue
                                # Skip metadata lines from facts collection
                                if line.startswith('TITLE:') or line.startswith('COMMAND:') or line.startswith('TIMESTAMP:'):
                                    continue
                                if line == '---' or line.startswith('EXIT_CODE:'):
                                    continue
                                # Only process create and add lines
                                if line.startswith('create ') or line.startswith('add '):
                                    # Remove dynamic attributes that change between versions
                                    # Remove bucketsize, initval, etc. that newer ipset adds
                                    line = re.sub(r'\s+bucketsize\s+\d+', '', line)
                                    line = re.sub(r'\s+initval\s+0x[0-9a-f]+', '', line)
                                    # Remove hashsize as it auto-adjusts based on number of entries
                                    line = re.sub(r'\s+hashsize\s+\d+', '', line)
                                    # Remove timeout values as they change over time
                                    line = re.sub(r'\s+timeout\s+\d+', '', line)
                                    # Normalize whitespace
                                    line = ' '.join(line.split())
                                    lines.append(line)
                            return '\n'.join(sorted(lines))
                        
                        expected_normalized = normalize_ipset(expected_content)
                        actual_normalized = normalize_ipset(actual_content)
                        
                        if expected_normalized == actual_normalized:
                            ipsets_ok += 1
                        else:
                            # Content differs - add to mismatched list
                            ipsets_mismatched.append((router_name, expected_content, actual_content, expected_normalized, actual_normalized))
                    else:
                        ipsets_mismatched.append(router_name)
                        if self.verbose >= 2:
                            print(f"    ✗ Failed to get ipset save from {router_name}")
                except Exception as e:
                    ipsets_mismatched.append(router_name)
                    if self.verbose >= 1:
                        print(f"    Error checking ipsets in {router_name}: {e}")
        
        # Process mismatched ipsets to check if only maxelem differences
        if ipsets_mismatched:
            actual_mismatches = []
            maxelem_only_fixes = []
            
            for item in ipsets_mismatched:
                if isinstance(item, tuple):
                    # This is a detailed mismatch with content
                    router_name, expected_content, actual_content, expected_normalized, actual_normalized = item
                    
                    # Use grep to quickly check if maxelem differences exist
                    import re
                    expected_maxelems = re.findall(r'create\s+(\S+).*maxelem\s+(\d+)', expected_content)
                    actual_maxelems = re.findall(r'create\s+(\S+).*maxelem\s+(\d+)', actual_content)
                    
                    if expected_maxelems or actual_maxelems:
                        # Convert to dicts for easier comparison
                        exp_dict = {name: int(val) for name, val in expected_maxelems}
                        act_dict = {name: int(val) for name, val in actual_maxelems}
                        
                        # Check if all differences are acceptable increases
                        all_increases = True
                        for set_name in exp_dict:
                            if set_name in act_dict:
                                if act_dict[set_name] < exp_dict[set_name]:
                                    all_increases = False
                                    break
                        
                        if all_increases and exp_dict != act_dict:
                            # Normalize maxelem values and recompare
                            actual_normalized_fixed = actual_normalized
                            for set_name in exp_dict:
                                if set_name in act_dict and act_dict[set_name] != exp_dict[set_name]:
                                    # Replace maxelem values in normalized content
                                    actual_normalized_fixed = re.sub(
                                        f'{set_name}(.*?)maxelem {act_dict[set_name]}',
                                        f'{set_name}\\1maxelem {exp_dict[set_name]}',
                                        actual_normalized_fixed
                                    )
                            
                            if expected_normalized == actual_normalized_fixed:
                                # Only maxelem differences
                                maxelem_only_fixes.append(router_name)
                                ipsets_ok += 1
                                if self.verbose >= 2:
                                    for set_name in exp_dict:
                                        if set_name in act_dict and act_dict[set_name] != exp_dict[set_name]:
                                            print(f"    ✓ Ipset matches in {router_name} (maxelem increased: {set_name} {exp_dict[set_name]} → {act_dict[set_name]})")
                            else:
                                actual_mismatches.append(router_name)
                                if self.verbose >= 2:
                                    print(f"    ✗ Ipset mismatch in {router_name}")
                                    if self.verbose >= 3:
                                        # Show first difference
                                        exp_lines = expected_normalized.split('\n')
                                        act_lines = actual_normalized.split('\n')
                                        for i, (e, a) in enumerate(zip(exp_lines, act_lines)):
                                            if e != a:
                                                print(f"      First diff at line {i+1}:")
                                                print(f"        Expected: {e[:100]}")
                                                print(f"        Actual:   {a[:100]}")
                                                break
                        else:
                            actual_mismatches.append(router_name)
                            if self.verbose >= 2:
                                print(f"    ✗ Ipset mismatch in {router_name}")
                    else:
                        actual_mismatches.append(router_name)
                        if self.verbose >= 2:
                            print(f"    ✗ Ipset mismatch in {router_name}")
                else:
                    # This is just a router name (failed to get ipset save)
                    actual_mismatches.append(item)
            
            ipsets_elapsed = time.time() - ipsets_start
            if actual_mismatches:
                issues.append(f"Ipset mismatches in {len(actual_mismatches)} routers: {', '.join(actual_mismatches[:5])}{'...' if len(actual_mismatches) > 5 else ''}")
            elif ipsets_configured > 0:
                print(f"    ✓ Ipsets verified in {ipsets_ok} routers (took {ipsets_elapsed:.1f}s)")
        elif ipsets_configured > 0:
            ipsets_elapsed = time.time() - ipsets_start
            print(f"    ✓ Ipsets verified in {ipsets_ok} routers (took {ipsets_elapsed:.1f}s)")
        
        # Verify iptables rules
        print(f"  Checking iptables rules...")
        import time
        iptables_start = time.time()
        iptables_ok = 0
        iptables_configured = 0
        iptables_mismatched = []
        
        for router_name in router_registry.keys():
            if router_name not in existing_ns_list or router_name not in all_routers:
                continue
            
            router_facts = all_routers[router_name]
            iptables_section = router_facts.get_section('iptables_save')
            
            if iptables_section and iptables_section.content.strip():
                iptables_configured += 1
                expected_content = iptables_section.content.strip()
                
                # Get actual iptables save output
                cmd = ['ip', 'netns', 'exec', router_name, 'iptables-save']
                if os.geteuid() != 0:
                    cmd = ['sudo'] + cmd
                
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        actual_content = result.stdout.strip()
                        
                        # Normalize both for comparison
                        def normalize_iptables(content):
                            import re
                            # Parse into tables, preserving rule order within each table and chain
                            tables = {}
                            current_table = None
                            chain_defs = []
                            chain_rules = {}  # Dictionary to hold rules for each chain
                            
                            for line in content.split('\n'):
                                line = line.strip()
                                # Skip empty lines, comments, timestamps, and metadata
                                if not line or line.startswith('#') or line == '---' or line.startswith('EXIT_CODE:'):
                                    continue
                                # Skip metadata lines from facts collection
                                if line.startswith('TITLE:') or line.startswith('COMMAND:') or line.startswith('TIMESTAMP:'):
                                    continue
                                # Skip time-based rules (same filtering as when applying)
                                if '-m time' in line:
                                    continue
                                    
                                # Normalize counters in brackets [packets:bytes] to [0:0]
                                line = re.sub(r'\[\d+:\d+\]', '[0:0]', line)
                                
                                if line.startswith('*'):
                                    # Save previous table if exists
                                    if current_table:
                                        # Build table content: table header, sorted chain defs, then rules for each chain
                                        table_content = [current_table] + sorted(chain_defs)
                                        # Add rules for each chain in alphabetical order of chain names
                                        # But preserve rule order within each chain!
                                        for chain_name in sorted(chain_rules.keys()):
                                            table_content.extend(chain_rules[chain_name])
                                        table_content.append('COMMIT')
                                        tables[current_table] = table_content
                                    # Start new table
                                    current_table = line
                                    chain_defs = []
                                    chain_rules = {}
                                elif line == 'COMMIT':
                                    # End of current table
                                    if current_table:
                                        # Build table content
                                        table_content = [current_table] + sorted(chain_defs)
                                        for chain_name in sorted(chain_rules.keys()):
                                            table_content.extend(chain_rules[chain_name])
                                        table_content.append('COMMIT')
                                        tables[current_table] = table_content
                                        current_table = None
                                        chain_defs = []
                                        chain_rules = {}
                                elif line.startswith(':'):
                                    # Chain definition
                                    chain_defs.append(line)
                                elif line.startswith('-A '):
                                    # Rule for a specific chain - preserve order within chain!
                                    parts = line.split()
                                    if len(parts) >= 2:
                                        chain_name = parts[1]
                                        if chain_name not in chain_rules:
                                            chain_rules[chain_name] = []
                                        chain_rules[chain_name].append(line)
                                else:
                                    # Other directives (shouldn't normally happen)
                                    # Add to a special '__other__' chain to preserve them
                                    if '__other__' not in chain_rules:
                                        chain_rules['__other__'] = []
                                    chain_rules['__other__'].append(line)
                            
                            # Save last table if no COMMIT found
                            if current_table:
                                table_content = [current_table] + sorted(chain_defs)
                                for chain_name in sorted(chain_rules.keys()):
                                    table_content.extend(chain_rules[chain_name])
                                if chain_rules or chain_defs:  # Only add COMMIT if there's content
                                    table_content.append('COMMIT')
                                tables[current_table] = table_content
                            
                            # Rebuild content with sorted table order but preserved rule order
                            result = []
                            for table_name in sorted(tables.keys()):
                                result.extend(tables[table_name])
                            
                            return '\n'.join(result)
                        
                        expected_normalized = normalize_iptables(expected_content)
                        actual_normalized = normalize_iptables(actual_content)
                        
                        if expected_normalized == actual_normalized:
                            iptables_ok += 1
                        else:
                            # Check if both are effectively empty (only default policies)
                            def is_empty_ruleset(content):
                                # Check if content only has table definitions, chains with ACCEPT policy, and COMMIT
                                essential_lines = []
                                for line in content.split('\n'):
                                    if line and not line.startswith('*') and line != 'COMMIT':
                                        # Check if it's just a chain definition with ACCEPT
                                        if not (line.startswith(':') and 'ACCEPT' in line):
                                            essential_lines.append(line)
                                return len(essential_lines) == 0
                            
                            if is_empty_ruleset(expected_normalized) and is_empty_ruleset(actual_normalized):
                                # Both are effectively empty, consider it OK
                                iptables_ok += 1
                            else:
                                iptables_mismatched.append(router_name)
                                if self.verbose >= 2:
                                    print(f"    ✗ Iptables mismatch in {router_name}")
                                    if self.verbose >= 3:
                                        # Show diff output
                                        import difflib
                                        expected_lines = expected_normalized.split('\n')
                                        actual_lines = actual_normalized.split('\n')
                                        diff = difflib.unified_diff(
                                            expected_lines, 
                                            actual_lines,
                                            fromfile=f'{router_name}_facts',
                                            tofile=f'{router_name}_namespace',
                                            lineterm='',
                                            n=1
                                        )
                                        print("      Diff output:")
                                        diff_shown = 0
                                        for line in diff:
                                            if diff_shown < 20:  # Limit output
                                                print(f"        {line}")
                                                diff_shown += 1
                                        if diff_shown >= 20:
                                            print("        ... (diff truncated)")
                    else:
                        iptables_mismatched.append(router_name)
                        if self.verbose >= 2:
                            print(f"    ✗ Failed to get iptables-save from {router_name}")
                except Exception as e:
                    iptables_mismatched.append(router_name)
                    if self.verbose >= 1:
                        print(f"    Error checking iptables in {router_name}: {e}")
        
        iptables_elapsed = time.time() - iptables_start
        if iptables_mismatched:
            issues.append(f"Iptables mismatches in {len(iptables_mismatched)} routers: {', '.join(iptables_mismatched[:5])}{'...' if len(iptables_mismatched) > 5 else ''}")
        elif iptables_configured > 0:
            print(f"    ✓ Iptables verified in {iptables_ok} routers (took {iptables_elapsed:.1f}s)")
        
        # Summary with comparison table
        print("\nVerification Summary:")
        
        # Print comparison table
        print("\n  Comparison Table:")
        print("  " + "="*60)
        print(f"  {'Resource':<20} {'Facts Data':<15} {'Namespace Data':<15} {'Status':<10}")
        print("  " + "-"*60)
        
        # Routers
        facts_routers = len(router_registry)
        ns_routers = existing_namespaces  # Not including hidden_mesh
        status = "✓ Match" if facts_routers == ns_routers else "✗ Mismatch"
        print(f"  {'Routers':<20} {facts_routers:<15} {ns_routers:<15} {status:<10}")
        
        # Interfaces - count total interfaces across all routers
        facts_interfaces = 0
        if interface_registry:
            for router_name, interfaces in interface_registry.items():
                facts_interfaces += len(interfaces)
        ns_interfaces = interfaces_ok
        status = "✓ Match" if facts_interfaces == ns_interfaces else "✗ Mismatch"
        print(f"  {'Interfaces':<20} {facts_interfaces:<15} {ns_interfaces:<15} {status:<10}")
        
        # Routes - all routers have routes
        facts_routes = len(router_registry)  
        ns_routes = routes_ok
        status = "✓ Match" if facts_routes == ns_routes else "✗ Mismatch"
        print(f"  {'Routes':<20} {facts_routes:<15} {ns_routes:<15} {status:<10}")
        
        # Policy Rules - count routers with policy rules
        facts_rules = 0
        for router_name in router_registry.keys():
            if router_name in all_routers:
                router_facts = all_routers[router_name]
                rule_section = router_facts.get_section('policy_rules')
                if rule_section and rule_section.content.strip():
                    # Check if there are actual non-default rules
                    has_rules = False
                    for line in rule_section.content.strip().split('\n'):
                        # Skip metadata lines from facts
                        if line.startswith('TITLE:') or line.startswith('COMMAND:') or line.startswith('TIMESTAMP:'):
                            continue
                        if line == '---' or line.startswith('EXIT_CODE:'):
                            continue
                        # Skip default rules
                        if (line and 
                            'from all lookup local' not in line and
                            'from all lookup main' not in line and
                            'from all lookup default' not in line):
                            has_rules = True
                            break
                    if has_rules:
                        facts_rules += 1
        ns_rules = rules_ok
        status = "✓ Match" if facts_rules == ns_rules else "✗ Mismatch"
        print(f"  {'Policy Rules':<20} {facts_rules:<15} {ns_rules:<15} {status:<10}")
        
        # Ipsets - count routers with ipsets
        facts_ipsets = 0
        for router_name in router_registry.keys():
            if router_name in all_routers:
                router_facts = all_routers[router_name]
                ipset_section = router_facts.get_section('ipset_save')
                if ipset_section and ipset_section.content.strip():
                    facts_ipsets += 1
        ns_ipsets = ipsets_ok
        status = "✓ Match" if facts_ipsets == ns_ipsets else "✗ Mismatch"
        print(f"  {'Ipsets':<20} {facts_ipsets:<15} {ns_ipsets:<15} {status:<10}")
        
        # Iptables - count routers with iptables
        facts_iptables = 0
        for router_name in router_registry.keys():
            if router_name in all_routers:
                router_facts = all_routers[router_name]
                iptables_section = router_facts.get_section('iptables_save')
                if iptables_section and iptables_section.content.strip():
                    facts_iptables += 1
        ns_iptables = iptables_ok
        status = "✓ Match" if facts_iptables == ns_iptables else "✗ Mismatch"
        print(f"  {'Iptables':<20} {facts_iptables:<15} {ns_iptables:<15} {status:<10}")
        
        print("  " + "="*60)
        
        if issues:
            print(f"\n  ✗ Found {len(issues)} issues:")
            for issue in issues:
                print(f"    - {issue}")
            return False
        else:
            print(f"\n  ✓ All resources verified successfully")
            return True
    
    def cleanup_namespaces_and_registries(self):
        """
        Clean up all namespaces and registry files using registry data.
        Reads from registry files to know what namespaces were created.
        """
        print("Cleaning up namespaces and registries...")
        
        # Load router registry to get list of namespaces
        namespaces_to_delete = set()
        
        # Always try to delete the hidden namespace
        namespaces_to_delete.add(self.hidden_ns)
        
        # Load router registry if it exists
        if self.router_registry_file.exists():
            try:
                with open(self.router_registry_file, 'r') as f:
                    router_registry = json.load(f)
                    # Add all router namespaces from registry
                    namespaces_to_delete.update(router_registry.keys())
                    if self.verbose >= 1:
                        print(f"Found {len(router_registry)} routers in registry")
            except (IOError, json.JSONDecodeError) as e:
                print(f"Warning: Could not load router registry: {e}")
        
        # Create batch file for deleting namespaces
        if namespaces_to_delete:
            # Create a batch file with all delete commands
            delete_commands = [f"netns del {ns_name}" for ns_name in sorted(namespaces_to_delete)]
            
            # Write to batch file
            batch_name = f"cleanup_namespaces_{self.session_id}"
            batch_path = f"/dev/shm/tsim/batch_{batch_name}"
            batch = TsimBatchMemory(batch_name)
            batch.write('\n'.join(delete_commands))
            
            # Execute batch deletion
            if self.verbose >= 1:
                print(f"  Deleting {len(namespaces_to_delete)} namespaces in batch...")
            
            cmd = ['sudo', 'ip', '-b', batch_path, '-force'] if os.geteuid() != 0 else ['ip', '-b', batch_path, '-force']
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                # Count successes and failures from output
                deleted_count = len(namespaces_to_delete)
                failed_count = 0
                
                if result.returncode != 0:
                    # Some deletions may have failed
                    for line in result.stderr.split('\n'):
                        if "Cannot find" in line or "No such" in line:
                            # Namespace didn't exist - that's OK
                            pass
                        elif line.strip():
                            failed_count += 1
                            if self.verbose >= 2:
                                print(f"  Error: {line.strip()}")
                    
                    # Adjust deleted count based on failures
                    deleted_count = deleted_count - failed_count
                
                # Clean up the batch file
                try:
                    os.remove(batch_path)
                except OSError:
                    pass
                    
            except subprocess.TimeoutExpired:
                print(f"  Timeout during batch deletion")
                deleted_count = 0
                failed_count = len(namespaces_to_delete)
            except Exception as e:
                print(f"  Error during batch deletion: {e}")
                deleted_count = 0
                failed_count = len(namespaces_to_delete)
        else:
            deleted_count = 0
            failed_count = 0
        
        print(f"Deleted {deleted_count} namespaces")
        if failed_count > 0:
            print(f"Failed to delete {failed_count} namespaces")
        
        # Remove registry files
        registry_files = [
            self.router_registry_file,
            self.interface_registry_file,
            self.bridge_registry_file,
            Path('/dev/shm/tsim/host_registry.json')  # Also clean host registry if exists
        ]
        
        removed_registries = 0
        for registry_file in registry_files:
            if registry_file.exists():
                try:
                    os.remove(registry_file)
                    removed_registries += 1
                    if self.verbose >= 2:
                        print(f"  Removed registry: {registry_file.name}")
                except OSError as e:
                    if self.verbose >= 1:
                        print(f"  Warning: Could not remove {registry_file}: {e}")
        
        print(f"Removed {removed_registries} registry files")
        
        # Clean up any leftover batch files
        batch_pattern = Path('/dev/shm/tsim').glob('batch_*')
        batch_count = 0
        for batch_file in batch_pattern:
            try:
                batch_file.unlink()
                batch_count += 1
            except OSError:
                pass
        
        if batch_count > 0 and self.verbose >= 1:
            print(f"Removed {batch_count} leftover batch files")
    
    def save_router_registry(self):
        """Save registry of router name to code mappings."""
        try:
            # Save current umask and set new one for group write
            old_umask = os.umask(0o002)  # Allow group write
            try:
                with open(self.router_registry_file, 'w') as f:
                    json.dump(self.router_codes, f, indent=2)
                
                # Ensure the file has correct permissions and group ownership
                os.chmod(self.router_registry_file, 0o664)  # rw-rw-r--
                # Set group ownership
                try:
                    import grp
                    gid = grp.getgrnam(self.unix_group).gr_gid
                    os.chown(self.router_registry_file, -1, gid)
                except (KeyError, OSError) as e:
                    if self.verbose:
                        print(f"Could not set {self.unix_group} group for router registry: {e}")
            finally:
                # Restore original umask
                os.umask(old_umask)
        except IOError as e:
            print(f"Could not save router registry: {e}")
    
    def save_interface_registry(self):
        """Save registry of interface name to code mappings per router."""
        try:
            # Save current umask and set new one for group write
            old_umask = os.umask(0o002)  # Allow group write
            try:
                with open(self.interface_registry_file, 'w') as f:
                    json.dump(self.interface_registry, f, indent=2)
                
                # Ensure the file has correct permissions and group ownership
                os.chmod(self.interface_registry_file, 0o664)  # rw-rw-r--
                # Set group ownership
                try:
                    import grp
                    gid = grp.getgrnam(self.unix_group).gr_gid
                    os.chown(self.interface_registry_file, -1, gid)
                except (KeyError, OSError) as e:
                    if self.verbose:
                        print(f"Could not set {self.unix_group} group for interface registry: {e}")
            finally:
                # Restore original umask
                os.umask(old_umask)
        except IOError as e:
            print(f"Could not save interface registry: {e}")
    
    def save_bridge_registry(self):
        """Save bridge registry to persistent file."""
        try:
            # Save current umask and set new one for group write
            old_umask = os.umask(0o002)  # Allow group write
            try:
                with open(self.bridge_registry_file, 'w') as f:
                    json.dump(self.bridge_registry, f, indent=2)
                
                # Ensure the file has correct permissions and group ownership
                os.chmod(self.bridge_registry_file, 0o664)  # rw-rw-r--
                # Set group ownership
                try:
                    import grp
                    gid = grp.getgrnam(self.unix_group).gr_gid
                    os.chown(self.bridge_registry_file, -1, gid)
                except (KeyError, OSError) as e:
                    if self.verbose:
                        print(f"Could not set {self.unix_group} group for bridge registry: {e}")
            finally:
                # Restore original umask
                os.umask(old_umask)
        except IOError as e:
            print(f"Could not save bridge registry: {e}")
        
    def split_large_batch(self, commands: List[str], batch_name: str, chunk_size: int = 100) -> List[str]:
        """
        Split large batch into smaller chunks.
        
        Args:
            commands: List of commands
            batch_name: Base name for the batch
            chunk_size: Maximum commands per chunk
            
        Returns:
            List of chunk batch names
        """
        if len(commands) <= chunk_size:
            # Small enough, create single batch
            full_name = f"{batch_name}_{self.session_id}"
            batch = TsimBatchMemory(full_name)
            batch.write('\n'.join(commands))
            return [full_name]
        
        # Split into chunks
        chunk_names = []
        for i in range(0, len(commands), chunk_size):
            chunk = commands[i:i+chunk_size]
            chunk_name = f"{batch_name}_chunk{i//chunk_size:03d}_{self.session_id}"
            batch = TsimBatchMemory(chunk_name)
            batch.write('\n'.join(chunk))
            chunk_names.append(chunk_name)
            
        if self.verbose >= 2:
            print(f"Split {batch_name} into {len(chunk_names)} chunks of up to {chunk_size} commands")
            
        return chunk_names
    
    def execute_batch_chunks_parallel(self, chunk_names: List[str], batch_description: str) -> bool:
        """
        Execute multiple batch chunks in parallel.
        
        Args:
            chunk_names: List of chunk batch names
            batch_description: Description for logging
            
        Returns:
            True if all chunks succeeded
        """
        import concurrent.futures
        
        def execute_chunk(chunk_name):
            batch_path = f"/dev/shm/tsim/batch_{chunk_name}"
            cmd = ['sudo', 'ip', '-b', batch_path, '-force'] if os.geteuid() != 0 else ['ip', '-b', batch_path, '-force']
            
            # Use longer timeout for move operations
            timeout_val = 60 if 'move' in chunk_name else 30
            
            start_time = time.time()
            try:
                # Log command execution start
                self.logger.debug(f"Executing batch chunk", extra={
                    'chunk_name': chunk_name,
                    'command': ' '.join(cmd),
                    'timeout': timeout_val
                })
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_val)
                duration = time.time() - start_time
                
                if result.returncode != 0:
                    stderr = result.stderr.strip()
                    stdout = result.stdout.strip()
                    
                    # Count actual errors vs warnings
                    error_lines = stderr.split('\n') if stderr else []
                    critical_errors = []
                    warnings = []
                    
                    for line in error_lines:
                        if not line.strip():
                            continue
                        # Non-critical errors that we can continue from
                        if 'File exists' in line or 'RTNETLINK answers: File exists' in line:
                            warnings.append(line)
                        elif 'already exists' in line:
                            warnings.append(line)
                        elif 'Cannot find device' in line and ('tunl0' in line or 'sit0' in line or 'gre0' in line):
                            warnings.append(line)  # Kernel interface issues
                        elif 'Nexthop has invalid gateway' in line and 'route' in chunk_name:
                            warnings.append(line)  # Invalid gateway due to /32 addresses
                        elif 'Command failed' in line and 'route' in chunk_name and 'Nexthop has invalid gateway' in stderr:
                            continue  # Skip "Command failed" lines when we have invalid gateway warnings
                        else:
                            critical_errors.append(line)
                    
                    # Log full details
                    self.logger.warning(f"Batch chunk failed", extra={
                        'chunk_name': chunk_name,
                        'returncode': result.returncode,
                        'duration': duration,
                        'errors': critical_errors,
                        'warnings': warnings,
                        'stdout': stdout,
                        'stderr': stderr,
                        'error_type': 'critical' if critical_errors else 'warning'
                    })
                    
                    # Determine if this is critical or not
                    if not critical_errors:
                        # Only warnings, consider it successful
                        if self.verbose >= 1 and warnings:
                            print(f"      Warnings in {chunk_name}:")
                            for warning in warnings[:5]:  # Show first 5 warnings
                                print(f"        - {warning}")
                            if len(warnings) > 5:
                                print(f"        ... and {len(warnings) - 5} more warnings")
                        return (chunk_name, True, "Non-critical errors only")
                    else:
                        # Has critical errors
                        if self.verbose >= 1:
                            print(f"      Critical errors in {chunk_name}:")
                            for error in critical_errors[:3]:
                                print(f"        ✗ {error}")
                        return (chunk_name, False, '; '.join(critical_errors[:3]))
                else:
                    # Success
                    self.logger.debug(f"Batch chunk succeeded", extra={
                        'chunk_name': chunk_name,
                        'returncode': 0,
                        'duration': duration
                    })
                    return (chunk_name, True, None)
                    
            except subprocess.TimeoutExpired as e:
                duration = time.time() - start_time
                self.logger.error(f"Batch chunk timed out", extra={
                    'chunk_name': chunk_name,
                    'duration': duration,
                    'timeout': timeout_val,
                    'error_type': 'timeout'
                })
                return (chunk_name, False, "Timeout")
            except Exception as e:
                duration = time.time() - start_time
                self.logger.error(f"Batch chunk exception", extra={
                    'chunk_name': chunk_name,
                    'duration': duration,
                    'error_type': 'exception',
                    'exception': str(e)
                }, exc_info=True)
                return (chunk_name, False, str(e))
        
        # Execute chunks in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(execute_chunk, chunk_names))
        
        # Check results
        failed = [r for r in results if not r[1]]
        if failed and self.verbose >= 1:
            for chunk_name, _, error in failed[:5]:  # Show first 5 errors
                print(f"    Chunk {chunk_name} failed: {error}")
        
        return len(failed) == 0
    
    def execute_all_batches(self, keep_batch_files: bool = False) -> bool:
        """
        Execute all batch files in order using ip -b.
        Split large batches and run chunks in parallel when possible.
        """
        if not self.batch_files:
            print("No batch files to execute")
            return False
            
        print(f"Executing {len(self.batch_files)} batch files...")
        
        # Define which batch types can be parallelized
        parallelizable = {
            'create_routers', 'enable_router_loopback', 'create_bridges', 'enable_bridges',
            'create_veth_pairs_in_namespaces', 'configure_ip_addresses', 
            'bring_up_router_interfaces', 'attach_to_bridges', 'bring_up_hidden_interfaces',
            'apply_routes', 'apply_rules', 'apply_ipsets', 'apply_iptables'
        }
        
        failed_batches = []
        
        for i, batch_name in enumerate(self.batch_files):
            if self.verbose >= 2:
                print(f"  [{i+1}/{len(self.batch_files)}] Executing {batch_name}")
            
            # Read the batch to check size
            batch_path = f"/dev/shm/tsim/batch_{batch_name}"
            batch = TsimBatchMemory(batch_name)
            commands = batch.read().strip().split('\n')
            
            # Check if this batch type can be parallelized
            batch_type = batch_name.rsplit('_', 1)[0]  # Remove session ID
            can_parallelize = any(bt in batch_type for bt in parallelizable)
            
            if len(commands) > 100 and can_parallelize:
                # Split and execute in parallel
                chunk_names = self.split_large_batch(commands, batch_type, 100)
                if self.verbose >= 1:
                    print(f"    Executing {len(chunk_names)} chunks in parallel...")
                success = self.execute_batch_chunks_parallel(chunk_names, batch_type)
                if not success:
                    failed_batches.append(batch_name)
            else:
                # Execute as single batch
                cmd = ['sudo', 'ip', '-b', batch_path, '-force'] if os.geteuid() != 0 else ['ip', '-b', batch_path, '-force']
                
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    
                    if result.returncode != 0:
                        stderr = result.stderr.strip()
                        error_lines = stderr.split('\n') if stderr else []
                        critical_errors = []
                        warnings = []
                        
                        for line in error_lines:
                            if not line.strip():
                                continue
                            # Non-critical errors
                            if 'File exists' in line or 'RTNETLINK answers: File exists' in line:
                                warnings.append(line)
                            elif 'already exists' in line:
                                warnings.append(line)
                            else:
                                critical_errors.append(line)
                        
                        if critical_errors:
                            # Has critical errors - this is a real failure
                            failed_batches.append(batch_name)
                            if self.verbose >= 1:
                                print(f"    Failed with critical errors:")
                                for error in critical_errors[:3]:
                                    print(f"      ✗ {error}")
                        elif warnings and self.verbose >= 1:
                            # Only warnings - not a failure
                            print(f"    Completed with {len(warnings)} warnings")
                            if self.verbose >= 2:
                                for warning in warnings[:5]:
                                    print(f"      - {warning}")
                                if len(warnings) > 5:
                                    print(f"      ... and {len(warnings) - 5} more")
                                
                except subprocess.TimeoutExpired:
                    failed_batches.append(batch_name)
                    if self.verbose >= 1:
                        print(f"    Timeout executing batch")
                except Exception as e:
                    failed_batches.append(batch_name)
                    if self.verbose >= 1:
                        print(f"    Error: {e}")
        
        # Clean up batch files unless debugging
        if not keep_batch_files:
            self.cleanup_batch_files()
        elif self.verbose >= 1:
            print(f"Keeping batch files in /dev/shm/tsim/ for debugging")
        
        if failed_batches:
            # Check which types of batches failed
            critical_failures = []
            route_warnings = []
            
            for batch in failed_batches:
                batch_type = batch.rsplit('_', 1)[0]
                # Routes failing is expected (duplicates, invalid gateways), not critical
                if 'apply_routes' in batch_type:
                    route_warnings.append(batch)
                else:
                    critical_failures.append(batch)
            
            # Report route warnings if verbose
            if route_warnings and self.verbose >= 1:
                # Parse log to get specific error counts
                invalid_gateway_errors = []
                file_exists_errors = 0
                
                try:
                    import json
                    with open(self.log_file, 'r') as f:
                        for line in f:
                            try:
                                entry = json.loads(line)
                                if 'chunk_name' in entry and any(w in entry['chunk_name'] for w in route_warnings):
                                    if 'stderr' in entry and entry['stderr']:
                                        stderr = entry['stderr']
                                        if 'Nexthop has invalid gateway' in stderr:
                                            # Extract route details if possible
                                            chunk = entry['chunk_name']
                                            count = stderr.count('Nexthop has invalid gateway')
                                            invalid_gateway_errors.append((chunk, count))
                                        if 'File exists' in stderr:
                                            file_exists_errors += stderr.count('File exists')
                            except:
                                pass
                except:
                    pass
                
                print(f"Warning: Route batches had non-critical errors:")
                if invalid_gateway_errors:
                    total_invalid = sum(count for _, count in invalid_gateway_errors)
                    print(f"  - {total_invalid} invalid gateway errors (interfaces with /32 addresses cannot reach gateway)")
                    if self.verbose >= 2:
                        print(f"    Affected chunks: {', '.join(chunk for chunk, _ in invalid_gateway_errors[:5])}")
                elif file_exists_errors > 0:
                    print(f"  - {file_exists_errors} duplicate route errors")
                else:
                    # Fallback if we couldn't parse specific errors
                    print(f"  - Route configuration warnings detected")
                print(f"  Note: These are configuration issues in the raw facts, not setup failures")
            
            if critical_failures:
                print(f"Execution completed with {len(critical_failures)} critical failures:")
                for batch in critical_failures[:10]:
                    print(f"  - {batch}")
                return False
            else:
                if self.verbose >= 1 and failed_batches:
                    print(f"Execution completed successfully (with {len(failed_batches)} batches having non-critical warnings)")
                else:
                    print(f"All batch files executed successfully")
                return True
        else:
            print(f"All {len(self.batch_files)} batch files executed successfully")
            return True
    
    def run(self, execute: bool = False, keep_batch_files: bool = False):
        """Main entry point."""
        print(f"Session ID: {self.session_id}")
        print(f"Loading facts from {self.raw_facts_dir}")
        
        # Generate all batches
        self.generate_all_batches()
        
        # Execute if requested
        if execute:
            success = self.execute_all_batches(keep_batch_files=keep_batch_files)
            # Cleanup is handled inside execute_all_batches based on keep_batch_files
            return success
        
        # Don't clean up if we're just generating files for inspection
        return True


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate batch commands for network setup')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity (can be used multiple times: -v, -vv, -vvv)')
    parser.add_argument('--log-file', 
                       help='Path to log file (default: auto-generated in /dev/shm/tsim/logs/)')
    parser.add_argument('--create', action='store_true',
                       help='Create the network setup by executing batches')
    parser.add_argument('--clean', action='store_true',
                       help='Clean up all namespaces and registries (uses registry data)')
    parser.add_argument('--verify', action='store_true',
                       help='Verify created resources match facts data')
    parser.add_argument('--keep-batch-files', action='store_true',
                       help='Keep batch files after execution (for debugging)')
    
    args = parser.parse_args()
    
    generator = BatchCommandGenerator(verbose=args.verbose, log_file=args.log_file)
    
    # Log startup
    generator.logger.info("Batch command generator started", extra={
        'mode': 'clean' if args.clean else 'verify' if args.verify else 'create' if args.create else 'generate',
        'verbose': args.verbose
    })
    
    # Handle different modes (allow both clean and create)
    start_time = time.time()
    try:
        success = True
        # Clean first if requested
        if args.clean:
            generator.cleanup_namespaces_and_registries()
        
        # Then create or verify if requested
        if args.verify:
            success = generator.verify_setup()
        elif args.create:
            success = generator.run(execute=True, keep_batch_files=args.keep_batch_files)
        elif not args.clean:
            # Only generate if not cleaning
            success = generator.run(execute=False)
    except Exception as e:
        generator.logger.critical("Fatal error in batch generator", exc_info=True)
        success = False
    
    duration = time.time() - start_time
    
    # Log completion
    generator.logger.info("Batch command generator completed", extra={
        'success': success,
        'duration': duration,
        'mode': 'clean' if args.clean else 'verify' if args.verify else 'create' if args.create else 'generate'
    })
    
    # Print log file location if verbose
    if args.verbose >= 1:
        print(f"\nLog file: {generator.log_file_path}")
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()