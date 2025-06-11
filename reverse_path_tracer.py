"""
Reverse Path Tracer Module - Bidirectional Path Discovery

This module implements reverse path tracing functionality for scenarios where
traditional forward simulation fails to find complete paths. It provides
three-step path discovery by tracing from Ansible controller to destination
and then reversing the path from destination back to original source.

The reverse tracing process:
1. Replace source with Ansible controller IP and trace to destination
2. Find last Linux router in path and trace from destination to original source
3. Reverse the obtained path and combine results

This approach is particularly useful in mixed Linux/non-Linux environments
where the forward path may traverse non-Linux routers that lack routing data.

Author: Network Analysis Tool
License: MIT
"""

import json
import sys
import ipaddress
import os
from typing import Dict, List, Optional, Tuple, Any
import socket

# Import from existing modules
try:
    from mtr_executor import MTRExecutor
    from route_formatter import RouteFormatter
    MTR_AVAILABLE = True
except ImportError:
    MTR_AVAILABLE = False


class ReversePathTracer:
    """
    Implements reverse path tracing for comprehensive path discovery.
    
    This class handles complex routing scenarios where traditional forward
    simulation cannot complete due to non-Linux routers in the path. It
    implements a three-step approach to discover bidirectional paths by
    leveraging Ansible controller connectivity and path reversal.
    
    Attributes:
        simulator: Reference to main TracerouteSimulator instance
        ansible_controller_ip: IP address of Ansible controller
        verbose: Enable verbose output for debugging
        verbose_level: Verbosity level (1=basic, 2=detailed debugging)
        mtr_executor: MTR executor instance for real traceroute execution
        route_formatter: Route formatter for consistent output formatting
    """
    
    def __init__(self, simulator, ansible_controller_ip: str = None, verbose: bool = False, verbose_level: int = 1):
        """
        Initialize reverse path tracer with simulator reference.
        
        Args:
            simulator: TracerouteSimulator instance for routing operations
            ansible_controller_ip: IP address of Ansible controller (auto-detected if None)
            verbose: Enable verbose output for debugging operations
            verbose_level: Verbosity level (1=basic, 2=detailed debugging)
        """
        self.simulator = simulator
        self.verbose = verbose
        self.verbose_level = verbose_level
        self.ansible_controller_ip = ansible_controller_ip or self._detect_controller_ip()
        
        # Initialize MTR executor and route formatter if available
        if MTR_AVAILABLE:
            linux_routers = set(simulator.routers.keys()) if simulator.routers else set()
            self.mtr_executor = MTRExecutor(linux_routers, verbose, verbose_level)
            self.route_formatter = RouteFormatter(verbose)
        else:
            self.mtr_executor = None
            self.route_formatter = None
    
    def _detect_controller_ip(self) -> str:
        """
        Detect the IP address of the Ansible controller.
        
        Attempts to determine the controller IP by connecting to a public
        DNS server and checking the local IP used for the connection.
        This provides a reasonable default for controller-based tracing.
        
        Returns:
            String representation of controller IP address
            
        Raises:
            RuntimeError: If controller IP cannot be determined
        """
        try:
            # Connect to public DNS to determine local IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                controller_ip = s.getsockname()[0]
                
            if self.verbose:
                print(f"Detected Ansible controller IP: {controller_ip}")
                
            return controller_ip
        except Exception as e:
            raise RuntimeError(f"Failed to detect Ansible controller IP: {e}")
    
    def perform_reverse_trace(self, original_src: str, original_dst: str) -> Tuple[bool, List[Tuple], int]:
        """
        Perform complete reverse path tracing using three-step approach.
        
        This is the main entry point for reverse path tracing. It implements
        the complete three-step process:
        1. Trace from controller to destination
        2. Find last Linux router and trace back to original source
        3. Reverse and combine paths
        
        Args:
            original_src: Original source IP address
            original_dst: Original destination IP address
            
        Returns:
            Tuple containing:
            - success (bool): Whether complete reverse path was found
            - path (List[Tuple]): Complete bidirectional path information
            - exit_code (int): Appropriate exit code for the operation
        """
        if self.verbose:
            print(f"\n=== Starting Reverse Path Tracing ===")
            print(f"Original route: {original_src} -> {original_dst}")
            print(f"Using Ansible controller: {self.ansible_controller_ip}")
        
        # Step 1: Trace from controller to destination
        step1_success, step1_path, step1_exit_code = self._step1_controller_to_destination(original_dst)
        
        if not step1_success:
            if self.verbose:
                print("Step 1 failed: Cannot reach destination from controller")
            return False, [], step1_exit_code
        
        # Step 2: Find last Linux router and trace from destination to original source
        step2_success, step2_path, step2_exit_code = self._step2_destination_to_source(
            step1_path, original_src, original_dst
        )
        
        if not step2_success:
            if self.verbose:
                print("Step 2 failed: Cannot trace from destination to original source")
            return False, [], step2_exit_code
        
        # Step 3: Reverse path and combine results
        step3_success, final_path = self._step3_reverse_and_combine(step1_path, step2_path, original_src, original_dst)
        
        if not step3_success:
            if self.verbose:
                print("Step 3 failed: Cannot combine reverse paths")
            return False, [], 1  # No path found
        
        if self.verbose:
            print("=== Reverse Path Tracing Completed Successfully ===")
        
        return True, final_path, 0
    
    def _step1_controller_to_destination(self, destination: str) -> Tuple[bool, List[Tuple], int]:
        """
        Step 1: Trace from Ansible controller to destination.
        
        Replaces the original source IP with the Ansible controller IP and
        performs simulation or MTR tracing to the destination. This establishes
        the forward path that will be used to identify the last Linux router.
        
        Args:
            destination: Target destination IP address
            
        Returns:
            Tuple containing:
            - success (bool): Whether trace was successful
            - path (List[Tuple]): Path from controller to destination
            - exit_code (int): Exit code from tracing operation
        """
        if self.verbose >= 2:
            print(f"\n--- Step 1: Controller ({self.ansible_controller_ip}) -> Destination ({destination}) ---")
        
        # First try simulation from controller to destination
        path = self.simulator.simulate_traceroute(self.ansible_controller_ip, destination)
        
        # Check if simulation was successful (no "No route" or "* * *" entries)
        if self._is_path_complete(path):
            if self.verbose >= 2:
                print(f"Simulation successful: {len(path)} hops from controller to destination")
            return True, path, 0
        
        # If simulation failed, try MTR fallback
        if MTR_AVAILABLE and self.mtr_executor:
            if self.verbose >= 2:
                print("Simulation incomplete, attempting mtr tool fallback...")
            
            # Find the router that owns the Ansible controller IP
            source_router = self.simulator._find_router_by_ip(self.ansible_controller_ip)
            if not source_router:
                if self.verbose:
                    print(f"Ansible controller IP {self.ansible_controller_ip} not found in router inventory")
                return False, [], 2  # Controller not reachable
            
            # Execute MTR from the Ansible controller and filter for Linux routers
            try:
                all_mtr_hops, filtered_mtr_hops = self.mtr_executor.execute_and_filter(source_router, destination)
                mtr_success = bool(filtered_mtr_hops)
                # Convert MTR dictionaries to simulator tuple format
                mtr_path = self._convert_mtr_to_simulator_format(filtered_mtr_hops)
                mtr_exit_code = 0 if mtr_success else 1
            except Exception as e:
                mtr_success = False
                mtr_path = []
                mtr_exit_code = 2
            
            if mtr_success and mtr_path:
                # Add destination hop with timing from all_mtr_hops if not already included
                destination_in_path = any(hop[2] == destination for hop in mtr_path)
                if not destination_in_path and all_mtr_hops:
                    # Check if destination was actually reached in MTR results
                    destination_reached = False
                    destination_rtt = 0.0
                    for hop in all_mtr_hops:
                        if hop.get('ip') == destination:
                            destination_reached = True
                            destination_rtt = hop.get('rtt', 0.0)
                            break
                    
                    # If destination was reached, add it as final hop
                    if destination_reached:
                        dest_hop_num = len(mtr_path) + 1
                        mtr_path.append((dest_hop_num, "destination", destination, "", False, "", "", destination_rtt))
                    else:
                        # Destination not reached by MTR - this should fail
                        raise ValueError(f"Destination {destination} not reachable via mtr tool")
                
                if self.verbose >= 2:
                    print(f"mtr tool successful: {len(mtr_path)} hops from {source_router} to destination")
                return True, mtr_path, 0
            else:
                if self.verbose:
                    print(f"mtr tool failed with exit code: {mtr_exit_code}")
                return False, [], mtr_exit_code
        
        # Both simulation and mtr tool failed
        if self.verbose:
            print("Both simulation and mtr tool failed to reach destination from controller")
        return False, [], 1  # No path found
    
    def _step2_destination_to_source(self, forward_path: List[Tuple], original_src: str, original_dst: str) -> Tuple[bool, List[Tuple], int]:
        """
        Step 2: Find last Linux router and trace from destination to original source.
        
        Analyzes the forward path to find the last Linux router, then performs
        reverse tracing from the destination to the original source IP. This
        establishes the return path that will be reversed in step 3.
        
        Args:
            forward_path: Path from controller to destination (from step 1)
            original_src: Original source IP address
            original_dst: Original destination IP address
            
        Returns:
            Tuple containing:
            - success (bool): Whether reverse trace was successful
            - path (List[Tuple]): Path from destination to original source
            - exit_code (int): Exit code from reverse tracing operation
        """
        if self.verbose >= 2:
            print(f"\n--- Step 2: Destination ({original_dst}) -> Original Source ({original_src}) ---")
        
        # Find the last Linux router in the forward path
        last_linux_router = self._find_last_linux_router(forward_path)
        
        if not last_linux_router:
            if self.verbose:
                print("No Linux routers found in forward path")
            return False, [], 4  # No Linux routers found
        
        if self.verbose >= 2:
            print(f"Last Linux router identified: {last_linux_router}")
        
        # Get the IP address of the last Linux router
        last_router_ip = self._get_router_ip(last_linux_router)
        
        if not last_router_ip:
            if self.verbose:
                print(f"Cannot determine IP address for router: {last_linux_router}")
            return False, [], 2  # Router not found
        
        if self.verbose >= 2:
            print(f"Using router IP {last_router_ip} as new source for reverse trace")
        
        # Perform reverse trace from destination to original source
        # We simulate as if we're tracing from the last router IP to original source
        reverse_path = self.simulator.simulate_traceroute(last_router_ip, original_src)
        
        # Check if reverse simulation was successful
        if self._is_path_complete(reverse_path):
            if self.verbose >= 2:
                print(f"Reverse simulation successful: {len(reverse_path)} hops")
            return True, reverse_path, 0
        
        # If reverse simulation failed, try mtr tool fallback
        if MTR_AVAILABLE and self.mtr_executor:
            if self.verbose >= 2:
                print("Reverse simulation incomplete, attempting mtr tool fallback...")
            
            try:
                all_mtr_hops, filtered_mtr_hops = self.mtr_executor.execute_and_filter(last_linux_router, original_src)
                
                # Check if mtr tool executed successfully (even if no Linux routers found)
                if all_mtr_hops:  # mtr tool executed and got some path
                    if filtered_mtr_hops:
                        # Normal case: Linux routers found in path
                        mtr_path = self._convert_mtr_to_simulator_format(filtered_mtr_hops)
                        if self.verbose >= 2:
                            print(f"Reverse mtr tool successful: {len(mtr_path)} hops with Linux routers")
                        return True, mtr_path, 0
                    else:
                        # Special case: mtr tool successful but no Linux routers in path
                        # Check if destination was actually reached in MTR results
                        destination_reached = False
                        destination_rtt = 0.0
                        if all_mtr_hops:
                            # Check if any hop actually reached the destination IP
                            for hop in all_mtr_hops:
                                if hop.get('ip') == original_src:
                                    destination_reached = True
                                    destination_rtt = hop.get('rtt', 0.0)
                                    break
                        
                        # If destination was not reached, this should be treated as unreachable
                        if not destination_reached:
                            raise ValueError(f"Destination {original_src} not reachable via mtr tool")
                        
                        # Create simple destination path with timing information
                        # Note: Don't include last_linux_router here as it's already in forward_path
                        simple_path = [
                            (1, "destination", original_src, "", False, "", "", destination_rtt)
                        ]
                        if self.verbose >= 2:
                            print("Reverse mtr tool successful: direct path (no Linux routers found)")
                        return True, simple_path, 0
                else:
                    # mtr tool execution failed
                    if self.verbose:
                        print("Reverse mtr tool failed: no path found")
                    return False, [], 2
                    
            except Exception as e:
                if "MTR_NO_LINUX_ROUTERS" in str(e):
                    # mtr tool executed successfully but no Linux routers found
                    # Note: In this exception case, we don't have access to all_mtr_hops timing data
                    # so we create a simple path without timing information
                    # Create simple destination path without timing information
                    # Note: Don't include last_linux_router here as it's already in forward_path
                    simple_path = [
                        (1, "destination", original_src, "", False, "", "", 0.0)
                    ]
                    if self.verbose >= 2:
                        print("Reverse mtr tool successful: direct path (no Linux routers found)")
                    return True, simple_path, 0
                else:
                    if self.verbose:
                        print(f"Reverse mtr tool failed with exception: {e}")
                    return False, [], 2
        
        # Both reverse simulation and mtr tool failed
        if self.verbose:
            print("Both reverse simulation and mtr tool failed")
        return False, [], 1  # No path found
    
    def _step3_reverse_and_combine(self, forward_path: List[Tuple], reverse_path: List[Tuple], 
                                  original_src: str, original_dst: str) -> Tuple[bool, List[Tuple]]:
        """
        Step 3: Reverse the path and combine results.
        
        Takes the reverse path from step 2 and reverses it to create the
        final path from original source to destination. Combines this with
        the forward path information to provide a complete bidirectional view.
        
        Args:
            forward_path: Path from controller to destination
            reverse_path: Path from destination to original source  
            original_src: Original source IP address
            original_dst: Original destination IP address
            
        Returns:
            Tuple containing:
            - success (bool): Whether path combination was successful
            - final_path (List[Tuple]): Complete reversed path from source to destination
        """
        if self.verbose >= 2:
            print(f"\n--- Step 3: Reversing Path from Original Source to Destination ---")
        
        if not reverse_path:
            if self.verbose:
                print("No reverse path to process")
            return False, []
        
        # Reverse the reverse_path to get original_src -> original_dst path
        final_path = []
        
        # The reverse_path goes from last_router -> original_src
        # We need to reverse it to go from original_src -> last_router
        # Then we need to connect to the forward path portion that reaches destination
        
        # Start with original source
        hop_counter = 1
        
        # Add the original source as the first hop
        # Check if original source belongs to a router
        src_router_name = self.simulator._find_router_by_ip(original_src)
        src_label = src_router_name if src_router_name else "source"
        src_is_router_owned = src_router_name is not None
        
        final_path.append((hop_counter, src_label, original_src, "", src_is_router_owned, "", "", 0.0))
        hop_counter += 1
        
        # Reverse the reverse path (excluding the first hop which is the router)
        # and excluding any destination hops
        filtered_reverse = []
        for hop_data in reverse_path:
            # Handle both 7-tuple and 8-tuple formats (with optional RTT)
            if len(hop_data) == 8:
                hop_num, router_name, ip, interface, is_router, connected_to, outgoing, rtt = hop_data
            else:
                hop_num, router_name, ip, interface, is_router, connected_to, outgoing = hop_data
            # Skip source/destination entries and the starting router
            if router_name not in ["source", "destination"] and not router_name.startswith("*"):
                filtered_reverse.append(hop_data)
        
        # Reverse the filtered path
        for hop_data in reversed(filtered_reverse):
            # Handle both 7-tuple and 8-tuple formats (with optional RTT)
            if len(hop_data) == 8:
                hop_num, router_name, ip, interface, is_router, connected_to, outgoing, rtt = hop_data
                final_path.append((hop_counter, router_name, ip, interface, is_router, connected_to, outgoing, rtt))
            else:
                hop_num, router_name, ip, interface, is_router, connected_to, outgoing = hop_data
                final_path.append((hop_counter, router_name, ip, interface, is_router, connected_to, outgoing))
            hop_counter += 1
        
        # Find where the paths converge and add the forward path to destination
        last_linux_router = self._find_last_linux_router(forward_path)
        
        # Add remaining hops from forward path after the last Linux router
        adding_forward_hops = False
        for hop_data in forward_path:
            # Handle both 7-tuple and 8-tuple formats (with optional RTT)
            if len(hop_data) == 8:
                hop_num, router_name, ip, interface, is_router, connected_to, outgoing, rtt = hop_data
            else:
                hop_num, router_name, ip, interface, is_router, connected_to, outgoing = hop_data
                rtt = None
            
            if router_name == last_linux_router:
                adding_forward_hops = True
                # Include the last Linux router itself with timing information
                if rtt is not None:
                    final_path.append((hop_counter, router_name, ip, interface, is_router, connected_to, outgoing, rtt))
                else:
                    final_path.append((hop_counter, router_name, ip, interface, is_router, connected_to, outgoing))
                hop_counter += 1
                continue
            
            if adding_forward_hops:
                if rtt is not None:
                    final_path.append((hop_counter, router_name, ip, interface, is_router, connected_to, outgoing, rtt))
                else:
                    final_path.append((hop_counter, router_name, ip, interface, is_router, connected_to, outgoing))
                hop_counter += 1
        
        # Ensure we end with the destination
        def get_ip_from_hop(hop_data):
            return hop_data[2]  # IP is always the 3rd element regardless of tuple length
            
        if final_path and not any(get_ip_from_hop(hop_data) == original_dst for hop_data in final_path):
            # Extract timing information for destination from forward_path if available
            destination_rtt = 0.0
            for hop_data in forward_path:
                if len(hop_data) >= 8 and hop_data[2] == original_dst:  # Check if this hop reaches the destination
                    destination_rtt = hop_data[7] if len(hop_data) == 8 else 0.0
                    break
                elif len(hop_data) >= 3 and hop_data[2] == original_dst:  # Destination found but no timing
                    destination_rtt = 0.0
                    break
            
            final_path.append((hop_counter, "destination", original_dst, "", False, "", "", destination_rtt))
        
        if self.verbose >= 2:
            print(f"Final combined path has {len(final_path)} hops")
        
        return True, final_path
    
    def _is_path_complete(self, path: List[Tuple]) -> bool:
        """
        Check if a path is complete (no missing routes or failures).
        
        Args:
            path: List of path tuples to check
            
        Returns:
            True if path is complete, False if there are routing failures
        """
        if not path:
            return False
        
        for hop_data in path:
            # Handle both 7-tuple and 8-tuple formats (with optional RTT)
            if len(hop_data) == 8:
                hop_num, router_name, ip, interface, is_router, connected_to, outgoing, rtt = hop_data
            else:
                hop_num, router_name, ip, interface, is_router, connected_to, outgoing = hop_data
            if "No route" in ip or "* * *" in router_name or "(loop detected)" in ip:
                return False
        
        return True
    
    def _find_best_source_router(self, controller_ip: str) -> Optional[str]:
        """
        Find the best Linux router to execute mtr tool from based on controller connectivity.
        
        Args:
            controller_ip: IP address of Ansible controller
            
        Returns:
            Name of best source router, or None if not found
        """
        # For now, return the first available router
        # In future, could implement more sophisticated selection logic
        if self.simulator.routers:
            return list(self.simulator.routers.keys())[0]
        return None
    
    def _find_last_linux_router(self, path: List[Tuple]) -> Optional[str]:
        """
        Find the last Linux router in a given path.
        
        Args:
            path: List of path tuples to analyze
            
        Returns:
            Name of last Linux router, or None if no Linux routers found
        """
        last_linux_router = None
        
        for hop_data in path:
            # Handle both 7-tuple and 8-tuple formats (with optional RTT)
            if len(hop_data) == 8:
                hop_num, router_name, ip, interface, is_router, connected_to, outgoing, rtt = hop_data
            else:
                hop_num, router_name, ip, interface, is_router, connected_to, outgoing = hop_data
            
            # Check if this is a Linux router (not source/destination/failure)
            if (is_router and router_name in self.simulator.routers and 
                router_name not in ["source", "destination"] and 
                not router_name.startswith("*")):
                last_linux_router = router_name
        
        return last_linux_router
    
    def _get_router_ip(self, router_name: str) -> Optional[str]:
        """
        Get a representative IP address for a given router.
        
        Args:
            router_name: Name of the router
            
        Returns:
            IP address of the router, or None if not found
        """
        if router_name not in self.simulator.routers:
            return None
        
        # Return the first available interface IP
        interfaces = self.simulator.routers[router_name].interfaces
        if interfaces:
            return list(interfaces.values())[0]
        
        return None
    
    def _convert_mtr_to_simulator_format(self, mtr_hops: List[Dict]) -> List[Tuple]:
        """
        Convert mtr tool hop dictionaries to simulator tuple format.
        
        mtr tool dictionaries have format: {'hop', 'ip', 'hostname', 'rtt', 'loss'}
        Simulator tuples have format: (hop_num, router_name, ip, interface, is_router, connected_to, outgoing, rtt)
        
        Args:
            mtr_hops: List of mtr tool hop dictionaries
            
        Returns:
            List of tuples in simulator format
        """
        simulator_hops = []
        
        for mtr_hop in mtr_hops:
            hop_num = mtr_hop.get('hop', 1)
            ip = mtr_hop.get('ip', '')
            hostname = mtr_hop.get('hostname', '')
            rtt = mtr_hop.get('rtt', 0.0)
            
            # Use hostname as router_name if available, otherwise use IP
            router_name = hostname if hostname else ip
            
            # For mtr tool hops, we don't have interface information
            interface = ""
            is_router = True  # mtr tool filtered hops are Linux routers
            connected_to = ""
            outgoing = ""
            
            simulator_hop = (hop_num, router_name, ip, interface, is_router, connected_to, outgoing, rtt)
            simulator_hops.append(simulator_hop)
        
        return simulator_hops