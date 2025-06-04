#!/usr/bin/env python3
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
from typing import Dict, List, Optional, Tuple

# Exit codes for quiet mode operation
# These codes allow automated scripts to determine the result without parsing output
EXIT_SUCCESS = 0        # Path found successfully between source and destination
EXIT_NO_PATH = 1        # Source and destination found, but no path between them
EXIT_NOT_FOUND = 2      # Either source or destination not found in any router network
EXIT_ERROR = 3          # Input validation errors or system errors


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


class TracerouteSimulator:
    """
    Simulates traceroute behavior using collected routing data from multiple routers.
    
    This class orchestrates the entire traceroute simulation process:
    1. Loads routing data from JSON files for all routers
    2. Builds lookup tables for efficient IP-to-router mapping
    3. Implements traceroute path discovery algorithm
    4. Handles various network scenarios (VPN, multi-homed, etc.)
    
    The simulation follows standard traceroute behavior:
    - Starts from source IP
    - Follows routing decisions hop by hop
    - Tracks interfaces and next-hop routers
    - Handles both router-owned and network-segment IPs
    
    Attributes:
        verbose (bool): Enable debug output during router loading
        routers (Dict[str, Router]): All loaded router objects by name
        router_lookup (Dict[str, str]): IP address to router name mapping
    """
    
    def __init__(self, routing_facts_dir: str = 'routing_facts', verbose: bool = False):
        """
        Initialize the traceroute simulator.
        
        Args:
            routing_facts_dir: Directory containing *_route.json and *_rule.json files
            verbose: Enable verbose output for debugging router loading
        """
        self.verbose = verbose
        # Load all router data from JSON files
        self.routers = self._load_routers(routing_facts_dir)
        # Build fast lookup table for IP-to-router mapping
        self.router_lookup = self._build_router_lookup()
    
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
                    if self.verbose:
                        print(f"Warning: Rule file for {name} not found, using empty rules", file=sys.stderr)
                
                # Create router object with loaded data
                routers[name] = Router(name, routes, rules)
                if self.verbose:
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
            dst_ip: Destination IP address (must be reachable by some router)
            
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
            ValueError: If source or destination IP not reachable by any router
        """
        # Validate source IP reachability
        if not self._validate_ip_reachability(src_ip):
            raise ValueError(f"Source IP {src_ip} is not configured on any router or in any directly connected network")
        
        # Validate destination IP reachability
        if not self._validate_ip_reachability(dst_ip):
            raise ValueError(f"Destination IP {dst_ip} is not configured on any router or in any directly connected network")
        
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
            path.append((hop, "source", src_ip, src_interface or "", False, current_router, ""))
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
                        path.append((hop, "destination", dst_ip, dst_interface, False, current_router, ""))
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
            next_incoming_interface = outgoing_interface  # The outgoing interface becomes the incoming interface on next router
            
            path.append((hop, next_router, next_ip, next_incoming_interface or "", next_is_owned, "", ""))
            visited.add(next_router)
            current_router = next_router
            incoming_interface = next_incoming_interface
            hop += 1
            
            # Check if we've reached destination exactly
            if next_ip == dst_ip:
                break
        
        return path


def format_path_json(path: List[Tuple]) -> str:
    """Convert path to JSON format."""
    json_path = []
    for hop_num, router_name, ip_addr, interface, is_router_owned, connected_router, outgoing_interface in path:
        hop_data = {
            "hop": hop_num,
            "router_name": router_name,
            "ip_address": ip_addr,
            "interface": interface,
            "is_router_owned": is_router_owned,
            "connected_router": connected_router,
            "outgoing_interface": outgoing_interface
        }
        json_path.append(hop_data)
    
    return json.dumps({"traceroute_path": json_path}, indent=2)


def format_path_text(path: List[Tuple]) -> List[str]:
    """Convert path to text format lines."""
    lines = []
    for hop_num, router_name, ip_addr, interface, is_router_owned, connected_router, outgoing_interface in path:
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
                
                lines.append(f" {hop_num:2d}  {router_name} ({ip_addr}){interface_str}{router_str}")
            else:
                # Router lines use "from incoming to outgoing"
                if interface and outgoing_interface:
                    interface_str = f" from {interface} to {outgoing_interface}"
                elif interface:
                    connector = "on" if is_router_owned else "via"
                    interface_str = f" {connector} {interface}"
                else:
                    interface_str = ""
                
                lines.append(f" {hop_num:2d}  {router_name} ({ip_addr}){interface_str}")
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
Exit codes (for -q/--quiet mode):
  0: Path found successfully
  1: Source and destination found, but no path between them
  2: Either source or destination not found
  3: Other errors

Examples:
  %(prog)s 192.168.1.1 10.0.0.1
  %(prog)s -v 192.168.1.1 10.0.0.1        # Verbose output
  %(prog)s -q 192.168.1.1 10.0.0.1        # Quiet mode (check $?)
  %(prog)s -j 192.168.1.1 10.0.0.1        # JSON output
        """)
    parser.add_argument('source_ip', help='Source IP address')
    parser.add_argument('destination_ip', help='Destination IP address')
    parser.add_argument('--routing-dir', default='routing_facts',
                       help='Directory containing routing facts (default: routing_facts)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose output (show router loading messages)')
    parser.add_argument('-q', '--quiet', action='store_true',
                       help='Quiet mode (no output, exit code indicates result)')
    parser.add_argument('-j', '--json', action='store_true',
                       help='Output traceroute path in JSON format')
    
    args = parser.parse_args()
    
    try:
        # Validate IP addresses
        ipaddress.ip_address(args.source_ip)
        ipaddress.ip_address(args.destination_ip)
    except (ipaddress.AddressValueError, ValueError) as e:
        if not args.quiet:
            print(f"Error: Invalid IP address - {e}", file=sys.stderr)
        sys.exit(EXIT_ERROR)
    
    try:
        simulator = TracerouteSimulator(args.routing_dir, verbose=args.verbose)
        
        path = simulator.simulate_traceroute(args.source_ip, args.destination_ip)
        
        # Check if path was found successfully
        has_no_route = any("No route" in str(item) for item in path)
        
        if args.quiet:
            if has_no_route:
                sys.exit(EXIT_NO_PATH)
            else:
                sys.exit(EXIT_SUCCESS)
        
        # Non-quiet output
        if not args.json:
            print(f"traceroute to {args.destination_ip} from {args.source_ip}")
        
        if args.json:
            print(format_path_json(path))
        else:
            for line in format_path_text(path):
                print(line)
                
    except ValueError as e:
        error_msg = str(e)
        if not args.quiet:
            print(f"Error: {error_msg}", file=sys.stderr)
        
        # Determine appropriate exit code based on error message
        if "not configured on any router" in error_msg or "not in any directly connected network" in error_msg:
            sys.exit(EXIT_NOT_FOUND)
        else:
            sys.exit(EXIT_ERROR)
            
    except Exception as e:
        if not args.quiet:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(EXIT_ERROR)


if __name__ == '__main__':
    main()