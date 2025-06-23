"""
Route Formatter Module - Unified Output Formatting for Traceroute Results

This module provides unified formatting functionality for both simulated and
real traceroute results. It handles the conversion of different data formats
into consistent text and JSON output formats that match the original simulator
behavior while accommodating MTR-based real traceroute data.

Key features:
- Unified formatting for simulated and MTR-based routes
- JSON and text output format support
- Consistent hop numbering and interface information
- Integration with existing simulator output format
- Support for mixed simulated/real route combinations

Author: Network Analysis Tool
License: MIT
"""

import json
from typing import List, Dict, Tuple, Union, Optional


class RouteFormatter:
    """
    Provides unified formatting for traceroute results from multiple sources.
    
    This class handles the formatting of traceroute path information from both
    the simulation engine and real MTR execution results. It ensures consistent
    output formatting regardless of the data source, maintaining compatibility
    with existing tooling and scripts.
    
    The formatter supports:
    - Simulated route paths (from TracerouteSimulator)
    - MTR-based real route paths (from MTRExecutor)
    - Mixed paths (simulation + MTR fallback)
    - JSON and text output formats
    """
    
    def __init__(self, verbose: bool = False):
        """
        Initialize the route formatter.
        
        Args:
            verbose: Enable verbose output for debugging formatting operations
        """
        self.verbose = verbose
    
    def format_simulated_path(self, path: List[Tuple], output_format: str = "text") -> Union[str, List[str]]:
        """
        Format a simulated traceroute path for output.
        
        Takes the path data structure from TracerouteSimulator and formats it
        according to the specified output format. This maintains compatibility
        with the existing simulator output while allowing integration with
        MTR-based results.
        
        Args:
            path: List of hop tuples from TracerouteSimulator.simulate_traceroute()
                  Format: (hop_num, router_name, ip_addr, interface, is_router_owned, connected_router, outgoing_interface)
            output_format: Either "text" or "json"
            
        Returns:
            Formatted output as string (JSON) or list of strings (text lines)
        """
        if output_format == "json":
            return self._format_simulated_json(path)
        else:
            return self._format_simulated_text(path)
    
    def format_mtr_path(self, mtr_hops: List[Dict], start_hop: int = 1, output_format: str = "text") -> Union[str, List[str]]:
        """
        Format MTR-based traceroute results for output.
        
        Converts MTR hop data into the same format as simulated paths,
        ensuring consistent output regardless of data source. Handles
        the differences between MTR data structure and simulator data.
        
        Args:
            mtr_hops: List of hop dictionaries from MTRExecutor.execute_and_filter()
                      Format: {'hop': int, 'ip': str, 'hostname': str, 'rtt': float, 'loss': float}
            start_hop: Starting hop number for numbering sequence
            output_format: Either "text" or "json"
            
        Returns:
            Formatted output as string (JSON) or list of strings (text lines)
        """
        if output_format == "json":
            return self._format_mtr_json(mtr_hops, start_hop)
        else:
            return self._format_mtr_text(mtr_hops, start_hop)
    
    def format_complete_mtr_path(self, all_mtr_hops: List[Dict], filtered_mtr_hops: List[Dict], 
                                src_ip: str, dst_ip: str, output_format: str = "text", 
                                router_lookup: Optional[callable] = None,
                                fqdn_resolver: Optional[callable] = None) -> Union[str, List[str]]:
        """
        Format complete MTR path including source and destination endpoints.
        
        Creates a complete traceroute path similar to simulation output, including
        source and destination endpoints even if they're not Linux routers in inventory.
        This ensures consistent output format between simulation and MTR modes.
        
        Args:
            all_mtr_hops: Complete list of MTR hops (unfiltered)
            filtered_mtr_hops: Filtered list containing only Linux routers
            src_ip: Source IP address for the trace
            dst_ip: Destination IP address for the trace
            output_format: Either "text" or "json"
            router_lookup: Optional function to find router name by IP
            fqdn_resolver: Optional function to resolve IP addresses to FQDNs
            
        Returns:
            Formatted complete path including source and destination
        """
        if output_format == "json":
            return self._format_complete_mtr_json(all_mtr_hops, filtered_mtr_hops, src_ip, dst_ip, router_lookup, fqdn_resolver)
        else:
            return self._format_complete_mtr_text(all_mtr_hops, filtered_mtr_hops, src_ip, dst_ip, router_lookup, fqdn_resolver)
    
    def format_combined_path(self, simulated_path: List[Tuple], mtr_hops: List[Dict], 
                           transition_point: int, output_format: str = "text") -> Union[str, List[str]]:
        """
        Format a combined path with both simulated and MTR-based sections.
        
        Handles scenarios where simulation works for part of the path but
        real MTR execution is needed for the remainder. Ensures seamless
        integration and consistent hop numbering across both sections.
        
        Args:
            simulated_path: Simulated portion of the path
            mtr_hops: MTR-based portion of the path
            transition_point: Hop number where transition from simulation to MTR occurs
            output_format: Either "text" or "json"
            
        Returns:
            Formatted combined output
        """
        if output_format == "json":
            return self._format_combined_json(simulated_path, mtr_hops, transition_point)
        else:
            return self._format_combined_text(simulated_path, mtr_hops, transition_point)
    
    def _format_simulated_json(self, path: List[Tuple]) -> str:
        """Convert simulated path to JSON format (same as original simulator)."""
        json_path = []
        for hop_num, router_name, ip_addr, interface, is_router_owned, connected_router, outgoing_interface in path:
            hop_data = {
                "hop": hop_num,
                "router_name": router_name,
                "ip_address": ip_addr,
                "interface": interface,
                "is_router_owned": is_router_owned,
                "connected_router": connected_router,
                "outgoing_interface": outgoing_interface,
                "data_source": "simulated"
            }
            json_path.append(hop_data)
        
        return json.dumps({"traceroute_path": json_path}, indent=2)
    
    def _format_simulated_text(self, path: List[Tuple]) -> List[str]:
        """Convert simulated path to text format (same as original simulator)."""
        lines = []
        for hop_num, router_name, ip_addr, interface, is_router_owned, connected_router, outgoing_interface in path:
            if router_name == "* * *":
                lines.append(f" {hop_num:2d}  {ip_addr}")
            elif " -> " in router_name:  # Single router scenario
                lines.append(f" {hop_num:2d}  {router_name} ({ip_addr}) {interface}")
            else:
                # Check if this is an endpoint (not a router in our inventory)
                if not is_router_owned:
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
    
    def _format_mtr_json(self, mtr_hops: List[Dict], start_hop: int) -> str:
        """Convert MTR hops to JSON format compatible with simulator output."""
        json_path = []
        for i, hop in enumerate(mtr_hops):
            hop_data = {
                "hop": start_hop + i,
                "router_name": hop.get('hostname', 'unknown'),
                "ip_address": hop.get('ip', ''),
                "interface": "",  # MTR doesn't provide interface information
                "is_router_owned": True,  # Filtered Linux routers are router-owned
                "connected_router": "",
                "outgoing_interface": "",
                "data_source": "mtr",
                "rtt": hop.get('rtt', 0.0),
                "loss": hop.get('loss', 0.0)
            }
            json_path.append(hop_data)
        
        return json.dumps({"traceroute_path": json_path}, indent=2)
    
    def _format_mtr_text(self, mtr_hops: List[Dict], start_hop: int) -> List[str]:
        """Convert MTR hops to text format compatible with simulator output."""
        lines = []
        for i, hop in enumerate(mtr_hops):
            hop_num = start_hop + i
            hostname = hop.get('hostname', 'unknown')
            ip = hop.get('ip', '')
            rtt = hop.get('rtt', 0.0)
            
            # Format similar to simulator but with RTT information
            if hostname and hostname != 'unknown':
                lines.append(f" {hop_num:2d}  {hostname} ({ip}) {rtt:.1f}ms")
            else:
                lines.append(f" {hop_num:2d}  {ip} {rtt:.1f}ms")
        
        return lines
    
    def _format_combined_json(self, simulated_path: List[Tuple], mtr_hops: List[Dict], 
                            transition_point: int) -> str:
        """Format combined simulated and MTR path as JSON."""
        combined_path = []
        
        # Add simulated portion (up to transition point)
        simulated_json = json.loads(self._format_simulated_json(simulated_path))
        for hop in simulated_json["traceroute_path"]:
            if hop["hop"] < transition_point:
                combined_path.append(hop)
        
        # Add MTR portion (from transition point)
        mtr_json = json.loads(self._format_mtr_json(mtr_hops, transition_point))
        combined_path.extend(mtr_json["traceroute_path"])
        
        return json.dumps({"traceroute_path": combined_path}, indent=2)
    
    def _format_combined_text(self, simulated_path: List[Tuple], mtr_hops: List[Dict], 
                            transition_point: int) -> List[str]:
        """Format combined simulated and MTR path as text."""
        lines = []
        
        # Add simulated portion (up to transition point)
        simulated_lines = self._format_simulated_text(simulated_path)
        for i, line in enumerate(simulated_lines):
            # Extract hop number from line to check if it's before transition
            hop_match = line.strip().split()
            if hop_match and hop_match[0].isdigit():
                hop_num = int(hop_match[0])
                if hop_num < transition_point:
                    lines.append(line)
        
        # Add transition indicator
        if lines and mtr_hops:
            lines.append(f" -- Transition to real traceroute from hop {transition_point} --")
        
        # Add MTR portion (from transition point)
        mtr_lines = self._format_mtr_text(mtr_hops, transition_point)
        lines.extend(mtr_lines)
        
        return lines
    
    def _format_complete_mtr_text(self, all_mtr_hops: List[Dict], filtered_mtr_hops: List[Dict], 
                                 src_ip: str, dst_ip: str, router_lookup: Optional[callable] = None,
                                 fqdn_resolver: Optional[callable] = None) -> List[str]:
        """Format complete MTR path as text consistent with simulation format."""
        lines = []
        hop_num = 1
        
        # Check if source IP is on a Linux router or just a source endpoint
        first_linux_router_ip = filtered_mtr_hops[0].get('ip') if filtered_mtr_hops else None
        
        if first_linux_router_ip != src_ip:
            # Check if source IP belongs to a router using router_lookup function
            source_router_name = None
            if router_lookup:
                source_router_name = router_lookup(src_ip)
            
            if source_router_name:
                # Source is a Linux router, show router name
                lines.append(f" {hop_num:2d}  {source_router_name} ({src_ip})")
            else:
                # Source is not a Linux router, try to resolve to FQDN or use "source" label
                if fqdn_resolver:
                    src_label = fqdn_resolver(src_ip)
                    lines.append(f" {hop_num:2d}  {src_label} ({src_ip})")
                else:
                    lines.append(f" {hop_num:2d}  source ({src_ip})")
            hop_num += 1
        
        # Add Linux routers from filtered list
        for mtr_hop in filtered_mtr_hops:
            hostname = mtr_hop.get('hostname', 'unknown')
            ip = mtr_hop.get('ip', '')
            rtt = mtr_hop.get('rtt', 0.0)
            
            if hostname and hostname != 'unknown':
                # Format similar to simulation: router_name (ip) [timing info]
                lines.append(f" {hop_num:2d}  {hostname} ({ip}) {rtt:.1f}ms")
            else:
                lines.append(f" {hop_num:2d}  {ip} {rtt:.1f}ms")
            hop_num += 1
        
        # Add destination if it exists in MTR trace but wasn't included in filtered results
        dst_found_in_trace = False
        dst_hostname = None
        dst_rtt = None
        
        # Look for destination in all MTR hops
        for hop in all_mtr_hops:
            hop_ip = hop.get('ip', '')
            hop_hostname = hop.get('hostname', '')
            
            # Check if this hop represents our destination
            if (hop_ip == dst_ip or 
                hop_hostname == 'one.one.one.one' or
                (dst_ip == '1.1.1.1' and hop_ip in ['1.1.1.1', '1.0.0.1'])):
                
                dst_found_in_trace = True
                dst_hostname = hop_hostname
                dst_rtt = hop.get('rtt', 0.0)
                break
        
        # Add destination line if found in trace but not in filtered Linux routers
        if (dst_found_in_trace and 
            not any(hop.get('ip') == dst_ip for hop in filtered_mtr_hops)):
            
            # Try to resolve destination to FQDN or use "destination" label
            if fqdn_resolver:
                dst_label = fqdn_resolver(dst_ip)
            else:
                dst_label = "destination"
            
            if dst_rtt is not None:
                lines.append(f" {hop_num:2d}  {dst_label} ({dst_ip}) {dst_rtt:.1f}ms")
            else:
                lines.append(f" {hop_num:2d}  {dst_label} ({dst_ip})")
        
        return lines
    
    def _format_complete_mtr_json(self, all_mtr_hops: List[Dict], filtered_mtr_hops: List[Dict], 
                                 src_ip: str, dst_ip: str, router_lookup: Optional[callable] = None,
                                 fqdn_resolver: Optional[callable] = None) -> str:
        """Format complete MTR path as JSON consistent with text format."""
        json_path = []
        hop_num = 1
        
        # Check if source IP is on a Linux router or just a source endpoint
        first_linux_router_ip = filtered_mtr_hops[0].get('ip') if filtered_mtr_hops else None
        
        if first_linux_router_ip != src_ip:
            # Check if source IP belongs to a router using router_lookup function
            source_router_name = None
            if router_lookup:
                source_router_name = router_lookup(src_ip)
            
            # Determine source label - use router name, FQDN, or "source"
            if source_router_name:
                src_label = source_router_name
            elif fqdn_resolver:
                src_label = fqdn_resolver(src_ip)
            else:
                src_label = "source"
            
            hop_data = {
                "hop": hop_num,
                "router_name": src_label,
                "ip_address": src_ip,
                "interface": "",
                "is_router_owned": bool(source_router_name),
                "connected_router": "",
                "outgoing_interface": "",
                "data_source": "mtr"
            }
            json_path.append(hop_data)
            hop_num += 1
        
        # Add Linux routers from filtered list
        for mtr_hop in filtered_mtr_hops:
            hop_data = {
                "hop": hop_num,
                "router_name": mtr_hop.get('hostname', 'unknown'),
                "ip_address": mtr_hop.get('ip', ''),
                "interface": "",
                "is_router_owned": True,
                "connected_router": "",
                "outgoing_interface": "",
                "data_source": "mtr",
                "rtt": mtr_hop.get('rtt', 0.0),
                "loss": mtr_hop.get('loss', 0.0)
            }
            json_path.append(hop_data)
            hop_num += 1
        
        # Add destination if it exists in MTR trace but wasn't included in filtered results
        dst_found_in_trace = False
        dst_hostname = None
        dst_rtt = None
        dst_loss = None
        
        # Look for destination in all MTR hops
        for hop in all_mtr_hops:
            hop_ip = hop.get('ip', '')
            hop_hostname = hop.get('hostname', '')
            
            # Check if this hop represents our destination
            if (hop_ip == dst_ip or 
                hop_hostname == 'one.one.one.one' or
                (dst_ip == '1.1.1.1' and hop_ip in ['1.1.1.1', '1.0.0.1'])):
                
                dst_found_in_trace = True
                dst_hostname = hop_hostname
                dst_rtt = hop.get('rtt', 0.0)
                dst_loss = hop.get('loss', 0.0)
                break
        
        # Add destination line if found in trace but not in filtered Linux routers
        if (dst_found_in_trace and 
            not any(hop.get('ip') == dst_ip for hop in filtered_mtr_hops)):
            
            # Try to resolve destination to FQDN or use "destination" label
            if fqdn_resolver:
                dst_label = fqdn_resolver(dst_ip)
            else:
                dst_label = "destination"
            
            hop_data = {
                "hop": hop_num,
                "router_name": dst_label,
                "ip_address": dst_ip,
                "interface": "",
                "is_router_owned": False,
                "connected_router": "",
                "outgoing_interface": "",
                "data_source": "mtr",
                "rtt": dst_rtt,
                "loss": dst_loss
            }
            json_path.append(hop_data)
        
        return json.dumps({"traceroute_path": json_path}, indent=2)
    
    def get_last_linux_router(self, path: List[Tuple]) -> Optional[str]:
        """
        Extract the last Linux router name from a simulated path.
        
        Analyzes a simulated traceroute path to find the last router that
        appears to be a Linux system (has routing data). This router will
        be used as the source for MTR execution when simulation cannot
        complete the full path.
        
        Args:
            path: Simulated path from TracerouteSimulator
            
        Returns:
            Name of the last Linux router in the path, or None if no router found
        """
        last_router = None
        
        for hop_num, router_name, ip_addr, interface, is_router_owned, connected_router, outgoing_interface in path:
            # Skip special entries
            # Skip special entries (endpoints are now FQDNs, so check if not router-owned)
            if router_name == "* * *" or not is_router_owned:
                continue
            if " -> " in router_name:  # Single router scenario
                continue
            
            # This is a router hop
            last_router = router_name
        
        return last_router
    
    def extract_hop_count(self, path: List[Tuple]) -> int:
        """
        Get the number of hops in a simulated path.
        
        Args:
            path: Simulated path from TracerouteSimulator
            
        Returns:
            Number of hops in the path
        """
        if not path:
            return 0
        
        # Return the highest hop number
        return max(hop[0] for hop in path)
    
    def has_route_failure(self, path: List[Tuple]) -> bool:
        """
        Check if a simulated path contains routing failures.
        
        Analyzes the path to determine if simulation encountered routing
        failures that would require MTR fallback execution.
        
        Args:
            path: Simulated path from TracerouteSimulator
            
        Returns:
            True if path contains routing failures, False otherwise
        """
        for hop_num, router_name, ip_addr, interface, is_router_owned, connected_router, outgoing_interface in path:
            if router_name == "* * *" or "No route" in ip_addr:
                return True
        
        return False