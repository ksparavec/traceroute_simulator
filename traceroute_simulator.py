"""
Traceroute Simulator - Network Path Discovery Tool

This module simulates traceroute behavior between two IP addresses using real
routing information collected from multiple Linux routers. It reads JSON files
containing routing tables and policy rules, then calculates the network path
that packets would take from source to destination.

The simulator implements Linux routing logic including:
- Longest prefix matching for route selection
- Policy-based routing rules
- WireGuard VPN tunnel routing
- Multi-interface routing scenarios
- Gateway and next-hop resolution

Author: Network Analysis Tool
License: MIT
"""

import json
import sys
import argparse
import ipaddress
import os
import glob
from typing import Dict, List, Optional, Tuple, Any

# Import YAML for configuration file support
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# Import MTR execution, route formatting, and reverse path tracing modules
try:
    from mtr_executor import MTRExecutor
    from route_formatter import RouteFormatter
    from reverse_path_tracer import ReversePathTracer
    MTR_AVAILABLE = True
    REVERSE_TRACER_AVAILABLE = True
except ImportError:
    MTR_AVAILABLE = False
    REVERSE_TRACER_AVAILABLE = False

# Exit codes for quiet mode operation
# These codes allow automated scripts to determine the result without parsing output
EXIT_SUCCESS = 0        # Path found successfully between source and destination
EXIT_NO_PATH = 1        # Source and destination found, but no path between them
EXIT_NOT_FOUND = 2      # Source not found in router network or destination not reachable
EXIT_NO_LINUX = 4       # MTR executed but no Linux routers found in path
EXIT_ERROR = 10         # Input validation errors or system errors


class Router:
    """
    Represents a Linux router with its routing table and policy rules.
    
    This class encapsulates all routing information for a single router including:
    - Routing table entries (from 'ip route' command)
    - Policy routing rules (from 'ip rule' command)  
    - Interface to IP address mappings
    - Route selection and next-hop determination logic
    
    Attributes:
        name (str): Router identifier/hostname
        routes (List[Dict]): Routing table entries in JSON format
        rules (List[Dict]): Policy routing rules in JSON format
        interfaces (Dict[str, str]): Interface name to IP address mapping
    """
    
    def __init__(self, name: str, routes: List[Dict], rules: List[Dict]):
        """
        Initialize router with routing data.
        
        Args:
            name: Router identifier (typically hostname)
            routes: List of routing table entries from 'ip --json route list'
            rules: List of policy rules from 'ip --json rule list'
        """
        self.name = name
        self.routes = routes
        self.rules = rules
        # Build interface mapping for quick lookups
        self.interfaces = self._extract_interfaces()
    
    def _extract_interfaces(self) -> Dict[str, str]:
        """
        Extract interface to IP address mapping from routing table.
        
        Scans routing table entries for 'prefsrc' (preferred source) addresses
        which indicate the IP address configured on each interface. This mapping
        is used to determine which router owns specific IP addresses.
        
        Returns:
            Dict mapping interface names to their IP addresses
            Example: {'eth0': '192.168.1.1', 'wg0': '10.0.0.1'}
        """
        interfaces = {}
        for route in self.routes:
            # prefsrc indicates the preferred source IP for this route
            # dev indicates the outgoing interface
            if route.get('prefsrc') and route.get('dev'):
                interfaces[route['dev']] = route['prefsrc']
        return interfaces
    
    def get_best_route(self, dst_ip: str, src_ip: Optional[str] = None) -> Optional[Dict]:
        """
        Find the best route for destination IP using Linux routing logic.
        
        Implements longest prefix matching algorithm similar to Linux kernel:
        1. Filters out blackhole routes
        2. Finds all routes that match the destination
        3. Selects route with longest prefix (most specific)
        4. Default routes (0.0.0.0/0) have lowest priority
        
        Args:
            dst_ip: Destination IP address to find route for
            src_ip: Optional source IP (not currently used in route selection)
            
        Returns:
            Dictionary containing best matching route, or None if no route found
            Route dict contains: dst, gateway, dev, metric, etc.
        """
        dst_addr = ipaddress.ip_address(dst_ip)
        best_route = None
        best_match_len = -1  # Start with -1 so default routes (len=0) can match
        
        # Filter out blackhole routes which drop packets
        # In real networks, blackhole routes prevent routing loops
        applicable_routes = [r for r in self.routes if r.get('type') != 'blackhole']
        
        # Iterate through all applicable routes to find best match
        for route in applicable_routes:
            dst = route.get('dst', '')
            
            # Handle default route (0.0.0.0/0 or ::/0)
            # Default routes have prefix length 0 and lowest priority
            if dst == 'default':
                if best_match_len < 0:  # Only use if no other route found
                    best_route = route
                    best_match_len = 0
                continue
            
            # Handle specific IP addresses or network prefixes
            try:
                if '/' in dst:
                    # Network prefix (e.g., 192.168.1.0/24)
                    network = ipaddress.ip_network(dst, strict=False)
                    if dst_addr in network:
                        prefix_len = network.prefixlen
                        # Longer prefix = more specific = higher priority
                        if prefix_len > best_match_len:
                            best_route = route
                            best_match_len = prefix_len
                else:
                    # Single IP address - highest possible priority
                    if dst_addr == ipaddress.ip_address(dst):
                        best_route = route
                        # Host routes have maximum prefix length
                        best_match_len = 32 if dst_addr.version == 4 else 128
            except (ValueError, ipaddress.AddressValueError):
                # Skip invalid route entries
                continue
        
        return best_route
    
    def get_interface_ip(self, interface: str) -> Optional[str]:
        """
        Get the IP address assigned to a specific interface.
        
        Args:
            interface: Interface name (e.g., 'eth0', 'wg0', 'enp1s0')
            
        Returns:
            IP address string if interface exists, None otherwise
        """
        return self.interfaces.get(interface)


def load_configuration() -> Dict[str, Any]:
    """
    Load configuration from YAML file with proper precedence.
    
    Configuration file location precedence:
    1. Environment variable TRACEROUTE_SIMULATOR_CONF (if set)
    2. ~/traceroute_simulator.yaml (user's home directory)
    3. ./traceroute_simulator.yaml (current directory)
    
    Returns:
        Dictionary containing configuration values
    """
    config = {}
    
    if not YAML_AVAILABLE:
        return config
    
    # Define potential configuration file locations in order of precedence
    config_files = []
    
    # 1. Environment variable (highest precedence)
    env_config = os.environ.get('TRACEROUTE_SIMULATOR_CONF')
    if env_config:
        config_files.append(env_config)
    
    # 2. User's home directory
    home_config = os.path.expanduser('~/traceroute_simulator.yaml')
    config_files.append(home_config)
    
    # 3. Current directory (lowest precedence)
    local_config = './traceroute_simulator.yaml'
    config_files.append(local_config)
    
    # Try to load configuration from the first available file
    for config_file in config_files:
        try:
            if os.path.isfile(config_file):
                with open(config_file, 'r') as f:
                    config = yaml.safe_load(f) or {}
                break
        except (yaml.YAMLError, IOError, OSError) as e:
            # Continue to next file if current one fails
            continue
    
    return config


def get_default_config() -> Dict[str, Any]:
    """
    Get hard-coded default configuration values.
    
    Returns:
        Dictionary containing default configuration
    """
    return {
        'routing_dir': 'routing_facts',
        'verbose': False,
        'verbose_level': 1,
        'quiet': False,
        'json_output': False,
        'enable_mtr_fallback': True,
        'enable_reverse_trace': False,
        'controller_ip': None
    }


def merge_config(defaults: Dict[str, Any], config_file: Dict[str, Any], 
                 args: argparse.Namespace) -> Dict[str, Any]:
    """
    Merge configuration from defaults, config file, and command line arguments.
    
    Precedence (highest to lowest):
    1. Command line arguments
    2. Configuration file values
    3. Hard-coded defaults
    
    Args:
        defaults: Hard-coded default values
        config_file: Values from configuration file
        args: Parsed command line arguments
        
    Returns:
        Merged configuration dictionary
    """
    config = defaults.copy()
    
    # Apply configuration file values (override defaults)
    config.update(config_file)
    
    # Apply command line arguments (override config file and defaults)
    # Only set values that were explicitly provided on command line
    if hasattr(args, 'routing_dir') and args.routing_dir is not None:
        config['routing_dir'] = args.routing_dir
    if hasattr(args, 'verbose') and args.verbose is not None:
        if args.verbose == 0:
            config['verbose'] = False
            config['verbose_level'] = 1
        elif args.verbose == 1:
            config['verbose'] = True
            config['verbose_level'] = 1
        elif args.verbose >= 2:
            config['verbose'] = True
            config['verbose_level'] = args.verbose
    if hasattr(args, 'quiet') and args.quiet:
        config['quiet'] = True
    if hasattr(args, 'json') and args.json:
        config['json_output'] = True
    if hasattr(args, 'no_mtr') and args.no_mtr:
        config['enable_mtr_fallback'] = False
    if hasattr(args, 'reverse_trace') and args.reverse_trace:
        config['enable_reverse_trace'] = True
    if hasattr(args, 'controller_ip') and args.controller_ip:
        config['controller_ip'] = args.controller_ip
    
    return config


class TracerouteSimulator:
    """
    Simulates traceroute behavior using collected routing data from multiple routers.
    
    This class orchestrates the entire traceroute simulation process:
    1. Loads routing data from JSON files for all routers
    2. Builds lookup tables for efficient IP-to-router mapping
    3. Implements traceroute path discovery algorithm
    4. Handles various network scenarios (VPN, multi-homed, etc.)
    5. Falls back to real MTR execution when simulation cannot complete the path
    
    The simulation follows standard traceroute behavior:
    - Starts from source IP
    - Follows routing decisions hop by hop
    - Tracks interfaces and next-hop routers
    - Handles both router-owned and network-segment IPs
    - Uses MTR for non-Linux router segments
    
    Attributes:
        verbose (bool): Enable debug output during router loading
        routers (Dict[str, Router]): All loaded router objects by name
        router_lookup (Dict[str, str]): IP address to router name mapping
        mtr_executor (MTRExecutor): MTR execution handler (if available)
        route_formatter (RouteFormatter): Output formatting handler
    """
    
    def __init__(self, routing_facts_dir: str = 'routing_facts', verbose: bool = False, verbose_level: int = 1):
        """
        Initialize the traceroute simulator.
        
        Args:
            routing_facts_dir: Directory containing *_route.json and *_rule.json files
            verbose: Enable verbose output for debugging router loading
            verbose_level: Verbosity level (1=basic, 2=detailed debugging)
        """
        self.verbose = verbose
        self.verbose_level = verbose_level
        # Load all router data from JSON files
        self.routers = self._load_routers(routing_facts_dir)
        # Build fast lookup table for IP-to-router mapping
        self.router_lookup = self._build_router_lookup()
        
        # Initialize MTR executor and route formatter if available
        if MTR_AVAILABLE:
            # Use router names as known Linux routers (since we have their routing data)
            linux_routers = set(self.routers.keys())
            self.mtr_executor = MTRExecutor(linux_routers, verbose, verbose_level)
            self.route_formatter = RouteFormatter(verbose)
        else:
            self.mtr_executor = None
            self.route_formatter = None
    
    def _load_routers(self, routing_facts_dir: str) -> Dict[str, Router]:
        """
        Load all router data from JSON files dynamically.
        
        Discovers routers by scanning for *_route.json files, then loads
        corresponding *_rule.json files. This allows adding new routers
        without code changes - just add their JSON files to the directory.
        
        File naming convention:
        - {router_name}_route.json: Contains 'ip --json route list' output
        - {router_name}_rule.json: Contains 'ip --json rule list' output
        
        Args:
            routing_facts_dir: Directory containing router JSON files
            
        Returns:
            Dictionary mapping router names to Router objects
            
        Raises:
            ValueError: If no router files found in directory
        """
        routers = {}
        
        # Discover all routers by finding their route files
        # This pattern allows dynamic addition of new routers
        route_files = glob.glob(os.path.join(routing_facts_dir, '*_route.json'))
        
        for route_file in route_files:
            # Extract router name from filename (e.g., master_route.json -> master)
            basename = os.path.basename(route_file)
            name = basename.replace('_route.json', '')
            
            # Corresponding rule file (may not exist for simple setups)
            rule_file = os.path.join(routing_facts_dir, f'{name}_rule.json')
            
            try:
                # Load routing table (required)
                with open(route_file, 'r') as f:
                    routes = json.load(f)
                
                # Load policy rules (optional)
                rules = []
                if os.path.exists(rule_file):
                    with open(rule_file, 'r') as f:
                        rules = json.load(f)
                else:
                    if self.verbose and self.verbose_level >= 3:
                        print(f"Warning: Rule file for {name} not found, using empty rules", file=sys.stderr)
                
                # Create router object with loaded data
                routers[name] = Router(name, routes, rules)
                if self.verbose and self.verbose_level >= 3:
                    print(f"Loaded router: {name}", file=sys.stderr)
                    
            except (FileNotFoundError, json.JSONDecodeError) as e:
                if self.verbose:
                    print(f"Error loading router {name}: {e}", file=sys.stderr)
        
        # Ensure at least one router was loaded
        if not routers:
            raise ValueError(f"No router data found in {routing_facts_dir}")
        
        return routers
    
    def _build_router_lookup(self) -> Dict[str, str]:
        """
        Build IP address to router name lookup table for fast queries.
        
        Creates a reverse mapping from IP addresses to router names,
        allowing quick determination of which router owns a specific IP.
        Only includes router interface IPs, not network ranges.
        
        Returns:
            Dictionary mapping IP addresses to router names
            Example: {'192.168.1.1': 'router1', '10.0.0.1': 'router2'}
        """
        lookup = {}
        for name, router in self.routers.items():
            # Add all interface IPs for this router
            for interface, ip in router.interfaces.items():
                lookup[ip] = name
        return lookup
    
    def _find_router_by_ip(self, ip: str) -> Optional[str]:
        """Find which router owns an IP address."""
        return self.router_lookup.get(ip)
    
    def _get_incoming_interface(self, router_name: str, from_ip: str) -> Optional[str]:
        """
        Determine the incoming interface on a router based on the source IP.
        
        When traffic arrives at a router from another router's IP address,
        we need to find which interface on the receiving router is in the
        same network as the source IP.
        
        Args:
            router_name: Name of the receiving router
            from_ip: IP address of the sending router
            
        Returns:
            Interface name that receives traffic from from_ip, or None if not found
        """
        if router_name not in self.routers:
            return None
            
        router = self.routers[router_name]
        from_addr = ipaddress.ip_address(from_ip)
        
        # Check each interface to see if from_ip is in the same network
        for route in router.routes:
            if (route.get('protocol') == 'kernel' and 
                route.get('scope') == 'link' and 
                route.get('dst', '').count('/') == 1):
                try:
                    network = ipaddress.ip_network(route['dst'], strict=False)
                    if from_addr in network:
                        return route.get('dev')
                except (ValueError, ipaddress.AddressValueError):
                    continue
        
        return None
    
    def _is_destination_reachable(self, router_name: str, dst_ip: str) -> Tuple[bool, bool]:
        """
        Check if destination IP is directly reachable from this router.
        Returns (is_reachable, is_router_owned).
        """
        if router_name not in self.routers:
            return False, False
        
        router = self.routers[router_name]
        dst_addr = ipaddress.ip_address(dst_ip)
        
        # Check if destination IP is configured on any interface
        if dst_ip in router.interfaces.values():
            return True, True
        
        # Check if destination is in a directly connected network
        for route in router.routes:
            if route.get('protocol') == 'kernel' and route.get('scope') == 'link':
                dst_net = route.get('dst', '')
                if '/' in dst_net:
                    try:
                        network = ipaddress.ip_network(dst_net, strict=False)
                        if dst_addr in network:
                            return True, False
                    except (ValueError, ipaddress.AddressValueError):
                        continue
        
        return False, False
    
    def _validate_ip_reachability(self, ip: str) -> bool:
        """Check if an IP is reachable by any router (configured or in connected network)."""
        for router_name in self.routers:
            is_reachable, _ = self._is_destination_reachable(router_name, ip)
            if is_reachable:
                return True
        return False
    
    def _resolve_ip_to_fqdn(self, ip: str) -> str:
        """
        Resolve IP address to FQDN using reverse DNS lookup.
        
        Uses the same getent hosts approach as MTR executor for consistency.
        Falls back to original IP if resolution fails.
        
        Args:
            ip: IP address to resolve
            
        Returns:
            FQDN if resolution succeeds, original IP if it fails
        """
        try:
            import subprocess
            ipaddress.ip_address(ip)  # Validate IP address
            
            # Use getent hosts for reverse DNS lookup
            result = subprocess.run(
                ['getent', 'hosts', ip],
                capture_output=True,
                text=True,
                timeout=2  # Shorter timeout for UI responsiveness
            )
            
            if result.returncode == 0 and result.stdout.strip():
                # Parse getent output: "IP hostname [aliases...]"
                parts = result.stdout.strip().split()
                if len(parts) >= 2:
                    hostname = parts[1]
                    return hostname
            
            return ip  # Fallback to IP if resolution fails
            
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, 
                ValueError, ipaddress.AddressValueError, FileNotFoundError):
            return ip  # Fallback to IP if any error occurs
    
    def _get_next_hop(self, current_router: str, dst_ip: str, src_ip: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Get next hop router, gateway IP, and interface for destination."""
        if current_router not in self.routers:
            return None, None, None
        
        router = self.routers[current_router]
        route = router.get_best_route(dst_ip, src_ip)
        
        if not route:
            return None, None, None
        
        gateway = route.get('gateway')
        interface = route.get('dev')
        
        if gateway:
            # Find which router owns the gateway IP
            next_router = self._find_router_by_ip(gateway)
            return next_router, gateway, interface
        elif interface:
            # Direct connection - check if destination is in same network
            interface_ip = router.get_interface_ip(interface)
            if interface_ip:
                try:
                    # Check if destination is directly reachable
                    for other_name, other_router in self.routers.items():
                        if other_name != current_router:
                            for other_interface, other_ip in other_router.interfaces.items():
                                if other_ip == dst_ip:
                                    return other_name, dst_ip, interface
                except:
                    pass
        
        return None, None, interface
    
    def simulate_traceroute(self, src_ip: str, dst_ip: str) -> List[Tuple[int, str, str, str, bool, str, str]]:
        """
        Simulate traceroute from source to destination IP address.
        
        This is the main algorithm that implements traceroute path discovery:
        1. Validates that both source and destination are reachable
        2. Finds the starting router (owns source IP or can reach it)
        3. Follows routing decisions hop by hop until destination reached
        4. Handles special cases like same-router communication
        5. Detects routing loops and unreachable destinations
        
        The algorithm models real traceroute behavior including:
        - Router interface traversal
        - Gateway/next-hop following
        - Network segment identification
        - VPN tunnel routing
        
        Args:
            src_ip: Source IP address (must be reachable by some router)
            dst_ip: Destination IP address (can be any valid IP address)
            
        Returns:
            List of hop tuples containing:
            - hop_number: Sequential hop count starting from 1
            - router_name: Name of router or "source"/"destination" for endpoints
            - ip_address: IP address at this hop
            - interface: Network interface name
            - is_router_owned: True if IP belongs to router interface
            - connected_router: Router that connects to this hop
            - outgoing_interface: Interface used to reach next hop
            
        Raises:
            ValueError: If source IP not reachable by any router
        """
        # Validate source IP reachability
        if not self._validate_ip_reachability(src_ip):
            raise ValueError(f"Source IP {src_ip} is not configured on any router or in any directly connected network")
        
        # Note: Destination IP is no longer required to be reachable by routers
        # It can be any valid IP address that routing decisions can be made for
        
        # Find starting router - the router that owns or can directly reach the source IP
        current_router = self._find_router_by_ip(src_ip)
        if not current_router:
            # Find the router that has the source IP in its directly connected network
            for name, router in self.routers.items():
                is_reachable, _ = self._is_destination_reachable(name, src_ip)
                if is_reachable:
                    current_router = name
                    break
        
        if not current_router:
            raise ValueError(f"No router found that can reach source IP {src_ip}")
        
        # Check if both source and destination are router-owned IPs on the same router
        src_router_name = self._find_router_by_ip(src_ip)
        dst_router_name = self._find_router_by_ip(dst_ip)
        
        # Single router scenario - only for router-owned IPs on the same router
        if (src_router_name and dst_router_name and src_router_name == dst_router_name):
            
            src_interface = ""
            dst_interface = ""
            
            # Get source interface
            for interface, ip in self.routers[src_router_name].interfaces.items():
                if ip == src_ip:
                    src_interface = interface
                    break
            
            # Get destination interface
            for interface, ip in self.routers[dst_router_name].interfaces.items():
                if ip == dst_ip:
                    dst_interface = interface
                    break
            
            return [(1, f"{src_router_name} -> {dst_router_name}", f"{src_ip} -> {dst_ip}", 
                    f"{src_interface} -> {dst_interface}", False, "", "")]
        
        path = []
        visited = set()
        hop = 1
        max_hops = 30
        
        # Determine source router name and interface - check if source IP is owned by a router
        src_interface = None
        
        incoming_interface = ""  # Track the interface used to reach current router
        
        if src_router_name:
            # Source IP is directly configured on a router
            for interface, ip in self.routers[src_router_name].interfaces.items():
                if ip == src_ip:
                    src_interface = interface
                    break
            path.append((hop, src_router_name, src_ip, src_interface or "", True, "", ""))
            current_router = src_router_name
        else:
            # Source IP is in a directly connected network - add source and then router
            for route in self.routers[current_router].routes:
                if (route.get('protocol') == 'kernel' and 
                    route.get('scope') == 'link' and 
                    route.get('dst', '').count('/') == 1):
                    try:
                        network = ipaddress.ip_network(route['dst'], strict=False)
                        if ipaddress.ip_address(src_ip) in network:
                            src_interface = route.get('dev', '')
                            incoming_interface = src_interface
                            break
                    except (ValueError, ipaddress.AddressValueError):
                        continue
            # Try to resolve source IP to FQDN
            src_label = self._resolve_ip_to_fqdn(src_ip)
            path.append((hop, src_label, src_ip, src_interface or "", False, current_router, ""))
            hop += 1
            # Add the router that the source connects through - will get outgoing interface from next hop
            router_ip = self.routers[current_router].interfaces.get(src_interface, "")
            if router_ip:
                path.append((hop, current_router, router_ip, incoming_interface, True, "", ""))
            else:
                # Fallback - find any IP on this router
                for interface, ip in self.routers[current_router].interfaces.items():
                    path.append((hop, current_router, ip, incoming_interface, True, "", ""))
                    break
                    
        visited.add(current_router)
        hop += 1
        
        while hop <= max_hops:
            # Check if destination is directly reachable from current router
            is_reachable, is_router_owned = self._is_destination_reachable(current_router, dst_ip)
            if is_reachable:
                # Destination is directly reachable - update previous router's outgoing interface
                if len(path) > 0:
                    prev_hop_num, prev_router_name, prev_ip, prev_incoming, prev_owned, prev_connected, _ = path[-1]
                    if prev_router_name not in ["source", "destination"] and not (" -> " in prev_router_name):
                        # Find outgoing interface for reaching destination
                        route = self.routers[current_router].get_best_route(dst_ip, src_ip)
                        outgoing_interface = route.get('dev', '') if route else ""
                        # Update the last router entry with outgoing interface
                        path[-1] = (prev_hop_num, prev_router_name, prev_ip, prev_incoming, prev_owned, prev_connected, outgoing_interface)
                
                if dst_ip not in [ip.split(' -> ')[0] if ' -> ' in ip else ip for _, _, ip, _, _, _, _ in path]:
                    if is_router_owned:
                        # Find which router owns this IP and its interface
                        dst_router_name = self._find_router_by_ip(dst_ip)
                        dst_interface = ""
                        if dst_router_name:
                            for interface, ip in self.routers[dst_router_name].interfaces.items():
                                if ip == dst_ip:
                                    dst_interface = interface
                                    break
                            path.append((hop, dst_router_name, dst_ip, dst_interface, True, "", ""))
                        else:
                            path.append((hop, current_router, dst_ip, "", True, "", ""))
                    else:
                        # Find interface for directly connected destination
                        dst_interface = ""
                        for route in self.routers[current_router].routes:
                            if (route.get('protocol') == 'kernel' and 
                                route.get('scope') == 'link' and 
                                route.get('dst', '').count('/') == 1):
                                try:
                                    network = ipaddress.ip_network(route['dst'], strict=False)
                                    if ipaddress.ip_address(dst_ip) in network:
                                        dst_interface = route.get('dev', '')
                                        break
                                except (ValueError, ipaddress.AddressValueError):
                                    continue
                        # Try to resolve destination IP to FQDN
                        dst_label = self._resolve_ip_to_fqdn(dst_ip)
                        path.append((hop, dst_label, dst_ip, dst_interface, False, current_router, ""))
                break
            
            # Find next hop
            next_router, next_ip, outgoing_interface = self._get_next_hop(current_router, dst_ip, src_ip)
            
            if not next_router or not next_ip:
                # No route found
                path.append((hop, "* * *", "No route", "", False, "", ""))
                break
            
            if next_router in visited:
                # Loop detected
                path.append((hop, next_router, f"{next_ip} (loop detected)", outgoing_interface or "", False, "", ""))
                break
            
            # Update previous router's outgoing interface if it's a router (not source/destination)
            if len(path) > 0:
                prev_hop_num, prev_router_name, prev_ip, prev_incoming, prev_owned, prev_connected, _ = path[-1]
                if prev_router_name not in ["source", "destination"] and not (" -> " in prev_router_name):
                    path[-1] = (prev_hop_num, prev_router_name, prev_ip, prev_incoming, prev_owned, prev_connected, outgoing_interface or "")
            
            # Determine if next IP is router-owned and incoming interface
            next_is_owned = self._find_router_by_ip(next_ip) is not None
            # Determine the correct incoming interface based on the current router's outgoing interface IP
            current_router_outgoing_ip = self.routers[current_router].get_interface_ip(outgoing_interface) if outgoing_interface else None
            next_incoming_interface = self._get_incoming_interface(next_router, current_router_outgoing_ip) if current_router_outgoing_ip else outgoing_interface
            
            path.append((hop, next_router, next_ip, next_incoming_interface or "", next_is_owned, "", ""))
            visited.add(next_router)
            current_router = next_router
            incoming_interface = next_incoming_interface
            hop += 1
            
            # Check if we've reached destination exactly
            if next_ip == dst_ip:
                break
        
        return path
    
    def simulate_traceroute_with_fallback(self, src_ip: str, dst_ip: str) -> Tuple[List[Tuple], bool]:
        """
        Simulate traceroute with MTR fallback for incomplete paths.
        
        This enhanced version of simulate_traceroute attempts simulation first,
        and if the simulation cannot complete the path due to non-Linux routers
        or routing failures, it falls back to executing real MTR from the last
        known Linux router in the path.
        
        The method follows this logic:
        1. Attempt normal simulation
        2. Check if simulation completed successfully
        3. If incomplete, find the last Linux router in the path
        4. Execute MTR from that router to the destination
        5. Filter MTR results to include only Linux routers
        6. Return combined or MTR-only results
        
        Args:
            src_ip: Source IP address
            dst_ip: Destination IP address
            
        Returns:
            Tuple of (path_data, used_mtr) where:
            - path_data: Either List[Tuple] for simulated or List[Dict] for MTR results
            - used_mtr: Boolean indicating if MTR was used
            
        Raises:
            ValueError: If neither simulation nor MTR can provide results
        """
        # First attempt normal simulation
        try:
            simulated_path = self.simulate_traceroute(src_ip, dst_ip)
            
            # Show simulation output in detailed debug mode
            if self.verbose_level >= 2:
                print("=== SIMULATION OUTPUT ===", file=sys.stderr)
                if self.route_formatter:
                    sim_lines = self.route_formatter._format_simulated_text(simulated_path)
                    for line in sim_lines:
                        print(f"SIM: {line}", file=sys.stderr)
                else:
                    for hop in simulated_path:
                        print(f"SIM: {hop}", file=sys.stderr)
                print("=== END SIMULATION ===", file=sys.stderr)
            
            # Check if simulation completed successfully
            if not self.route_formatter or not self.route_formatter.has_route_failure(simulated_path):
                return simulated_path, False  # Simulation successful, no MTR needed
            
            if self.verbose:
                print("Simulation incomplete, attempting mtr tool fallback", file=sys.stderr)
            
        except ValueError as e:
            if self.verbose:
                print(f"Simulation failed: {e}, attempting mtr tool fallback", file=sys.stderr)
            simulated_path = []
        
        # mtr tool fallback is needed
        if not MTR_AVAILABLE or not self.mtr_executor:
            raise ValueError("mtr tool fallback not available - modules not imported")
        
        # Find the last Linux router for mtr tool execution
        mtr_source_router = None
        
        if simulated_path:
            # Get last router from simulation path
            mtr_source_router = self.route_formatter.get_last_linux_router(simulated_path)
        
        if not mtr_source_router:
            # Find any router that can reach the source IP
            src_router = self._find_router_by_ip(src_ip)
            if src_router:
                mtr_source_router = src_router
            else:
                # Find router with source in connected network
                for name, router in self.routers.items():
                    is_reachable, _ = self._is_destination_reachable(name, src_ip)
                    if is_reachable:
                        mtr_source_router = name
                        break
        
        if not mtr_source_router:
            # No suitable router found - this should trigger reverse path tracing
            raise ValueError("No suitable Linux router found for mtr tool execution")
        
        
        # Execute mtr tool and get both all hops and filtered results
        try:
            all_mtr_hops, filtered_mtr_hops = self.mtr_executor.execute_and_filter(mtr_source_router, dst_ip)
            
            if not filtered_mtr_hops:
                # Special case: mtr tool executed successfully but no Linux routers found in path
                # This indicates network connectivity exists but path goes through non-Linux infrastructure
                # Check if destination was actually reached in MTR results
                destination_reached = False
                destination_rtt = 0.0
                if all_mtr_hops:
                    # Check if any hop actually reached the destination IP
                    for hop in all_mtr_hops:
                        if hop.get('ip') == dst_ip:
                            destination_reached = True
                            destination_rtt = hop.get('rtt', 0.0)
                            break
                
                # If destination was not reached, this should be treated as unreachable
                if not destination_reached:
                    raise ValueError(f"Destination {dst_ip} not reachable via mtr tool")
                
                # Return simple source->destination path with timing information
                # Check if source IP belongs to a router
                src_router_name = self._find_router_by_ip(src_ip)
                # Try to resolve source and destination to FQDNs
                src_label = src_router_name if src_router_name else self._resolve_ip_to_fqdn(src_ip)
                dst_label = self._resolve_ip_to_fqdn(dst_ip)
                src_is_router_owned = src_router_name is not None
                
                simple_path = [
                    (1, src_label, src_ip, "", src_is_router_owned, "", "", 0.0),
                    (2, dst_label, dst_ip, "", False, "", "", destination_rtt)
                ]
                return simple_path, True  # Simple path, but MTR was used
            
            return (all_mtr_hops, filtered_mtr_hops, src_ip, dst_ip), True  # mtr tool results with context
            
        except Exception as e:
            raise ValueError(f"mtr tool execution failed: {e}")


def format_path_json(path: List[Tuple]) -> str:
    """Convert path to JSON format."""
    json_path = []
    for hop_data in path:
        # Handle both 7-tuple and 8-tuple formats (with optional RTT)
        if len(hop_data) == 8:
            hop_num, router_name, ip_addr, interface, is_router_owned, connected_router, outgoing_interface, rtt = hop_data
        else:
            hop_num, router_name, ip_addr, interface, is_router_owned, connected_router, outgoing_interface = hop_data
            rtt = None
        
        hop_json = {
            "hop": hop_num,
            "router_name": router_name,
            "ip_address": ip_addr,
            "interface": interface,
            "is_router_owned": is_router_owned,
            "connected_router": connected_router,
            "outgoing_interface": outgoing_interface
        }
        
        # Add RTT if available
        if rtt is not None:
            hop_json["rtt"] = rtt
        
        json_path.append(hop_json)
    
    return json.dumps({"traceroute_path": json_path}, indent=2)


def format_path_text(path: List[Tuple]) -> List[str]:
    """Convert path to text format lines."""
    lines = []
    for hop_data in path:
        # Handle both 7-tuple and 8-tuple formats (with optional RTT)
        if len(hop_data) == 8:
            hop_num, router_name, ip_addr, interface, is_router_owned, connected_router, outgoing_interface, rtt = hop_data
        else:
            hop_num, router_name, ip_addr, interface, is_router_owned, connected_router, outgoing_interface = hop_data
            rtt = None
        if router_name == "* * *":
            lines.append(f" {hop_num:2d}  {ip_addr}")
        elif " -> " in router_name:  # Single router scenario
            lines.append(f" {hop_num:2d}  {router_name} ({ip_addr}) {interface}")
        else:
            if router_name in ["source", "destination"]:
                # Source and destination use "via interface on router"
                if interface:
                    connector = "on" if is_router_owned else "via"
                    interface_str = f" {connector} {interface}"
                else:
                    interface_str = ""
                
                if connected_router:
                    router_str = f" on {connected_router}"
                else:
                    router_str = ""
                
                # Add timing information if available
                timing_str = f" {rtt:.1f}ms" if rtt is not None and rtt > 0 else ""
                lines.append(f" {hop_num:2d}  {router_name} ({ip_addr}){interface_str}{router_str}{timing_str}")
            else:
                # Router lines use "from incoming to outgoing"
                if interface and outgoing_interface:
                    interface_str = f" from {interface} to {outgoing_interface}"
                elif interface:
                    connector = "on" if is_router_owned else "via"
                    interface_str = f" {connector} {interface}"
                else:
                    interface_str = ""
                
                # Add timing information if available
                timing_str = f" {rtt:.1f}ms" if rtt is not None and rtt > 0 else ""
                lines.append(f" {hop_num:2d}  {router_name} ({ip_addr}){interface_str}{timing_str}")
    return lines


def main():
    """
    Main entry point for the traceroute simulator command-line interface.
    
    Handles argument parsing, input validation, simulator initialization,
    and output formatting. Supports multiple output modes and exit codes
    for integration with automation scripts.
    """
    parser = argparse.ArgumentParser(
        description='Simulate traceroute between two IP addresses using collected routing data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration File Support:
  Options can be configured in a YAML file. Location precedence:
  1. $TRACEROUTE_SIMULATOR_CONF environment variable
  2. ~/traceroute_simulator.yaml (user's home directory)
  3. ./traceroute_simulator.yaml (current directory)
  
  Command line arguments override configuration file values.
  
  Note: Reverse path tracing requires 'controller_ip' to be set in configuration file.

Exit codes (for -q/--quiet mode):
  0: Path found successfully
  1: Source and destination found, but no path between them
  2: Source not found in router network or destination not reachable
  4: MTR executed but no Linux routers found in path
  10: Other errors

Examples:
  %(prog)s -s 10.1.1.1 -d 10.2.1.1                    # HQ to Branch routing
  %(prog)s -s 10.1.1.1 -d 10.2.1.1 -v                 # Verbose output (basic)
  %(prog)s -s 10.1.1.1 -d 10.2.1.1 -vv                # Detailed debugging output
  %(prog)s -s 10.1.1.1 -d 10.2.1.1 -vvv               # Configuration details
  %(prog)s -s 10.1.1.1 -d 10.2.1.1 -q                 # Quiet mode (check $?)
  %(prog)s -s 10.100.1.1 -d 10.100.1.3 -j             # JSON output (WireGuard tunnel)
  %(prog)s --routing-dir tests/routing_facts -s 10.1.10.1 -d 10.3.20.1  # Complex multi-hop
  %(prog)s -s 10.1.1.1 -d 192.168.1.1 --reverse-trace # Enable reverse path tracing
        """)
    parser.add_argument('-s', '--source', required=True, help='Source IP address')
    parser.add_argument('-d', '--destination', required=True, help='Destination IP address')
    parser.add_argument('--routing-dir', 
                       help='Directory containing routing facts (default: routing_facts)')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Enable verbose output (-v for basic, -vv for detailed debugging, -vvv for configuration details)')
    parser.add_argument('-q', '--quiet', action='store_true',
                       help='Quiet mode (no output, exit code indicates result)')
    parser.add_argument('-j', '--json', action='store_true',
                       help='Output traceroute path in JSON format')
    parser.add_argument('--no-mtr', action='store_true',
                       help='Disable MTR fallback (simulation only)')
    parser.add_argument('--reverse-trace', action='store_true',
                       help='Enable reverse path tracing when forward simulation fails')
    parser.add_argument('--controller-ip', 
                       help='Ansible controller IP address (for reverse tracing; can also be set in config file)')
    
    args = parser.parse_args()
    
    # Load configuration with proper precedence
    defaults = get_default_config()
    config_file = load_configuration()
    config = merge_config(defaults, config_file, args)
    
    try:
        # Validate IP addresses
        ipaddress.ip_address(args.source)
        ipaddress.ip_address(args.destination)
    except (ipaddress.AddressValueError, ValueError) as e:
        if not config['quiet']:
            print(f"Error: Invalid IP address - {e}", file=sys.stderr)
        sys.exit(EXIT_ERROR)
    
    try:
        simulator = TracerouteSimulator(config['routing_dir'], verbose=config['verbose'], verbose_level=config['verbose_level'])
        
        # Decide which simulation method to use
        path = None
        used_mtr = False
        used_reverse = False
        
        if not config['enable_mtr_fallback'] or not MTR_AVAILABLE:
            # Use original simulation only
            path = simulator.simulate_traceroute(args.source, args.destination)
            used_mtr = False
        else:
            # Use enhanced simulation with MTR fallback
            try:
                path_data, used_mtr = simulator.simulate_traceroute_with_fallback(args.source, args.destination)
                path = path_data
            except ValueError as e:
                # If both simulation and MTR failed, try reverse path tracing
                if config['enable_reverse_trace'] and REVERSE_TRACER_AVAILABLE:
                    if config['verbose']:
                        print(f"Forward methods failed ({e}), attempting reverse path tracing", file=sys.stderr)
                    
                    # Check if controller IP is provided for reverse tracing
                    if not config.get('controller_ip'):
                        if not config['quiet']:
                            print("Error: Reverse path tracing requires controller_ip to be set in configuration file", file=sys.stderr)
                        sys.exit(EXIT_ERROR)
                    
                    # Initialize reverse path tracer
                    try:
                        reverse_tracer = ReversePathTracer(
                            simulator, 
                            config['controller_ip'], 
                            verbose=config['verbose'], 
                            verbose_level=config['verbose_level']
                        )
                    except ValueError as rev_e:
                        if not config['quiet']:
                            print(f"Error: {rev_e}", file=sys.stderr)
                        sys.exit(EXIT_ERROR)
                    
                    # Perform reverse path tracing
                    success, reverse_path, reverse_exit_code = reverse_tracer.perform_reverse_trace(
                        args.source, args.destination
                    )
                    
                    if success:
                        path = reverse_path
                        used_reverse = True
                        if config['verbose']:
                            print("Reverse path tracing successful", file=sys.stderr)
                    else:
                        # All methods failed
                        if not config['quiet']:
                            print(f"Error: All tracing methods failed - {e}", file=sys.stderr)
                        sys.exit(reverse_exit_code)
                else:
                    # Re-raise original error if reverse tracing not enabled
                    raise
        
        # Check if path was found successfully (handle both formats)
        has_no_route = False
        mtr_no_linux_routers = False
        
        if used_mtr:
            # MTR results - distinguish between execution failure and no Linux routers found
            if isinstance(path, tuple) and len(path) == 4:
                all_mtr_hops, filtered_mtr_hops, src_ip, dst_ip = path
                # MTR executed successfully if all_mtr_hops has data
                mtr_executed_successfully = bool(all_mtr_hops)
                if mtr_executed_successfully and not filtered_mtr_hops:
                    # MTR executed successfully but no Linux routers found in path
                    mtr_no_linux_routers = True
                    has_no_route = False  # Don't treat as route failure
                else:
                    # Either MTR failed or Linux routers were found
                    has_no_route = not filtered_mtr_hops
            else:
                # Simple path format - this happens when MTR executed successfully 
                # but no Linux routers were found, so a simple source->destination path was created
                if path and len(path) == 2:
                    # Check if this is a simple source->destination path created due to no Linux routers
                    # This indicates MTR executed successfully but found no Linux routers
                    mtr_no_linux_routers = True
                    has_no_route = False  # Don't treat as route failure
                else:
                    # Other simple path scenarios (actual failures)
                    has_no_route = not path
        elif used_reverse:
            # Reverse path tracing results - check for route failures
            has_no_route = not path or any("No route" in str(item) for item in path)
        else:
            # Simulated results - check for route failures
            has_no_route = any("No route" in str(item) for item in path)
        
        # Determine exit code first
        exit_code = EXIT_SUCCESS
        if mtr_no_linux_routers:
            # MTR executed successfully but no Linux routers found in path
            exit_code = EXIT_NO_LINUX
        elif has_no_route:
            # Determine if destination is reachable by any router
            dst_reachable = simulator._validate_ip_reachability(args.destination)
            if dst_reachable:
                # Both source and destination are in network but no path exists (misconfiguration)
                exit_code = EXIT_NO_PATH
            else:
                # Destination is not in network (external IP)
                exit_code = EXIT_NOT_FOUND
        
        # Handle output and exit based on mode
        if config['quiet']:
            sys.exit(exit_code)
        
        # Non-quiet output
        if not config['json_output']:
            trace_info = f"traceroute to {args.destination} from {args.source}"
            if used_mtr:
                trace_info += " (using forward path tracing with mtr tool)"
            elif used_reverse:
                trace_info += " (using reverse path tracing with mtr tool)"
            print(trace_info)
        
        # Format output using appropriate formatter
        if used_mtr and simulator.route_formatter:
            # Use route formatter for MTR results
            if isinstance(path, tuple) and len(path) == 4:
                all_mtr_hops, filtered_mtr_hops, src_ip, dst_ip = path
                if config['json_output']:
                    print(simulator.route_formatter.format_complete_mtr_path(all_mtr_hops, filtered_mtr_hops, src_ip, dst_ip, "json", simulator._find_router_by_ip, simulator._resolve_ip_to_fqdn))
                else:
                    for line in simulator.route_formatter.format_complete_mtr_path(all_mtr_hops, filtered_mtr_hops, src_ip, dst_ip, "text", simulator._find_router_by_ip, simulator._resolve_ip_to_fqdn):
                        print(line)
            else:
                # Special case: MTR was used but returned simple path format (no Linux routers found)
                # Use original formatting for simple path results
                if config['json_output']:
                    print(format_path_json(path))
                else:
                    for line in format_path_text(path):
                        print(line)
        elif used_reverse:
            # Use original formatting for reverse path tracing results (they use simulation format)
            if config['json_output']:
                print(format_path_json(path))
            else:
                for line in format_path_text(path):
                    print(line)
        else:
            # Use original formatting for simulated results
            if config['json_output']:
                print(format_path_json(path))
            else:
                for line in format_path_text(path):
                    print(line)
        
        # Exit with determined code for non-quiet mode
        if exit_code != EXIT_SUCCESS:
            sys.exit(exit_code)
                
    except ValueError as e:
        error_msg = str(e)
        if not config['quiet']:
            print(f"Error: {error_msg}", file=sys.stderr)
        
        # Determine appropriate exit code based on error message
        if "not configured on any router" in error_msg or "not in any directly connected network" in error_msg:
            sys.exit(EXIT_NOT_FOUND)
        elif "not reachable via mtr tool" in error_msg:
            sys.exit(EXIT_NOT_FOUND)
        elif "MTR_NO_LINUX_ROUTERS" in error_msg:
            sys.exit(EXIT_NO_LINUX)
        else:
            sys.exit(EXIT_ERROR)
            
    except Exception as e:
        if not args.quiet:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(EXIT_ERROR)


if __name__ == '__main__':
    main()