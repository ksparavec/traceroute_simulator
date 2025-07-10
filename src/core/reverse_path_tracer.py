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

# Import from existing modules
try:
    from ..executors.mtr_executor import MTRExecutor
    from .route_formatter import RouteFormatter
    MTR_AVAILABLE = True
except ImportError:
    # Try absolute imports for direct script execution
    try:
        import sys
        import os
        # Add parent directories to path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        
        from executors.mtr_executor import MTRExecutor
        from core.route_formatter import RouteFormatter
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
    
    def __init__(self, simulator, ansible_controller_ip: Optional[str] = None, verbose: bool = False, verbose_level: int = 1):
        """
        Initialize reverse path tracer with simulator reference.
        
        Args:
            simulator: TracerouteSimulator instance for routing operations
            ansible_controller_ip: IP address of Ansible controller (external controllers allowed)
            verbose: Enable verbose output for debugging operations
            verbose_level: Verbosity level (1=basic, 2=detailed debugging)
            
        Raises:
            RuntimeError: If ansible_controller_ip is not provided and auto-detection fails
        """
        self.simulator = simulator
        self.verbose = verbose
        self.verbose_level = verbose_level
        
        # Use provided controller IP or try auto-detection
        if ansible_controller_ip:
            self.ansible_controller_ip = ansible_controller_ip
        else:
            detected_ip = simulator.get_ansible_controller_ip()
            if not detected_ip:
                raise RuntimeError("No Ansible controller IP provided and none found in router metadata. "
                                 "Provide controller_ip or ensure at least one router has 'ansible_controller': true in its metadata.")
            self.ansible_controller_ip = detected_ip
        
        # Initialize MTR executor and route formatter if available
        if MTR_AVAILABLE:
            linux_routers = set(simulator.routers.keys()) if simulator.routers else set()
            self.mtr_executor = MTRExecutor(linux_routers, verbose, verbose_level)
            # Set comprehensive IP lookup table for proper router identification
            if hasattr(simulator, 'comprehensive_ip_lookup'):
                self.mtr_executor.set_ip_lookup(simulator.comprehensive_ip_lookup)
            self.route_formatter = RouteFormatter(verbose)
        else:
            self.mtr_executor = None
            self.route_formatter = None
    
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
        
        # Debug: Always show this
        if self.verbose and self.verbose_level >= 3:
            print(f"STEP1 DEBUG: Starting controller to destination trace", file=sys.stderr)
        
        # Check if controller IP is in router inventory
        controller_router = self.simulator._find_router_by_ip(self.ansible_controller_ip)
        
        if self.verbose and self.verbose_level >= 3:
            print(f"STEP1 DEBUG: Controller router lookup: {self.ansible_controller_ip} -> {controller_router}", file=sys.stderr)
        
        if controller_router:
            # Controller is internal - try simulation first
            if self.verbose >= 2:
                print(f"Controller {self.ansible_controller_ip} is internal router {controller_router}")
            
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
                
                # Execute MTR from the controller router
                try:
                    all_mtr_hops, filtered_mtr_hops = self.mtr_executor.execute_and_filter(controller_router, destination)
                    mtr_success = bool(filtered_mtr_hops)
                    if self.verbose >= 2:
                        print(f"MTR execution result: all_hops={len(all_mtr_hops)}, filtered_hops={len(filtered_mtr_hops)}, success={mtr_success}")
                    # Convert MTR dictionaries to simulator tuple format
                    mtr_path = self._convert_mtr_to_simulator_format(filtered_mtr_hops)
                    mtr_exit_code = 0 if mtr_success else 1
                except Exception as e:
                    if self.verbose >= 2:
                        print(f"MTR execution failed with exception: {e}")
                    mtr_success = False
                    mtr_path = []
                    mtr_exit_code = 2
                
                if self.verbose >= 2:
                    print(f"MTR success: {mtr_success}, path length: {len(mtr_path) if mtr_path else 0}")
                    if mtr_path:
                        print(f"MTR path: {mtr_path}")
                
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
                            # Try to resolve destination IP to name
                            dst_label = self.simulator._resolve_ip_to_name(destination)
                            mtr_path.append((dest_hop_num, dst_label, destination, "", False, "", "", destination_rtt))
                        else:
                            # Destination not reached by MTR - this should fail
                            raise ValueError(f"Destination {destination} not reachable via mtr tool")
                    
                    if self.verbose >= 2:
                        print(f"mtr tool successful: {len(mtr_path)} hops from {controller_router} to destination")
                    return True, mtr_path, 0
                else:
                    if self.verbose:
                        print(f"mtr tool failed with exit code: {mtr_exit_code}")
                    return False, [], mtr_exit_code
        else:
            # Controller is external - try MTR from any available router
            if self.verbose and self.verbose_level >= 3:
                print(f"STEP1 DEBUG: Controller {self.ansible_controller_ip} is external, finding best router for MTR", file=sys.stderr)
            
            # Debug: Let's see what MTR and available routers we have
            if self.verbose >= 2:
                print(f"MTR_AVAILABLE: {MTR_AVAILABLE}")
                print(f"mtr_executor: {self.mtr_executor}")
                print(f"routers available: {bool(self.simulator.routers)}")
                if self.simulator.routers:
                    print(f"Total routers: {len(self.simulator.routers)}")
                    linux_routers = [name for name, router in self.simulator.routers.items() if router.is_linux()]
                    print(f"Linux routers: {len(linux_routers)}")
                    if linux_routers:
                        print(f"First Linux router: {linux_routers[0]}")
            
            if self.verbose and self.verbose_level >= 3:
                print(f"External controller path: MTR_AVAILABLE={MTR_AVAILABLE}, mtr_executor={self.mtr_executor}")
            
            if MTR_AVAILABLE and self.mtr_executor:
                # For external controller, use the controller IP directly for SSH
                source_router = self.ansible_controller_ip
                if self.verbose and self.verbose_level >= 3:
                    print(f"Using external controller {source_router} for MTR execution")
            
                # Execute MTR and create path that simulates from controller
                try:
                    all_mtr_hops, filtered_mtr_hops = self.mtr_executor.execute_and_filter(source_router, destination)
                    mtr_success = bool(filtered_mtr_hops)
                    
                    if mtr_success:
                        # Create path starting from external controller
                        mtr_path = []
                        # Add controller as first hop
                        controller_label = self.simulator._resolve_ip_to_name(self.ansible_controller_ip)
                        mtr_path.append((1, controller_label, self.ansible_controller_ip, "", False, "", "", 0.0))
                        
                        # Add MTR hops starting from hop 2
                        for i, hop_dict in enumerate(filtered_mtr_hops):
                            hop_num = i + 2
                            ip = hop_dict.get('ip', '')
                            hostname = hop_dict.get('hostname', '')
                            rtt = hop_dict.get('rtt', 0.0)
                            
                            # Use hostname as router_name if available, otherwise use IP
                            router_name = hostname if hostname else ip
                            is_router = True  # MTR filtered hops are Linux routers
                            
                            mtr_path.append((hop_num, router_name, ip, "", is_router, "", "", rtt))
                    else:
                        mtr_path = []
                    mtr_exit_code = 0 if mtr_success else 1
                except Exception as e:
                    if self.verbose and self.verbose_level >= 3:
                        print(f"STEP1 DEBUG: MTR exception: {e}", file=sys.stderr)
                    mtr_success = False
                    mtr_path = []
                    mtr_exit_code = 2
                
                if self.verbose and self.verbose_level >= 3:
                    print(f"STEP1 DEBUG: mtr_success={mtr_success}, path_length={len(mtr_path) if mtr_path else 0}", file=sys.stderr)
                
                # Check what happens next
                if mtr_success and mtr_path:
                    if self.verbose and self.verbose_level >= 3:
                        print(f"STEP1 DEBUG: MTR successful, should return success", file=sys.stderr)
                    return True, mtr_path, 0
                else:
                    if self.verbose and self.verbose_level >= 3:
                        print(f"STEP1 DEBUG: MTR failed, should return failure", file=sys.stderr)
                    return False, [], mtr_exit_code
            else:
                # MTR not available
                if self.verbose:
                    print("MTR not available for external controller")
                return False, [], 2
        
        # This point should not be reached, but handle it gracefully
        if self.verbose:
            print("No valid path found")
        return False, [], 2
        
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
                        # Try to resolve original source IP to name
                        src_label = self.simulator._resolve_ip_to_name(original_src)
                        simple_path = [
                            (1, src_label, original_src, "", False, "", "", destination_rtt)
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
                    # Try to resolve original source IP to name
                    src_label = self.simulator._resolve_ip_to_name(original_src)
                    simple_path = [
                        (1, src_label, original_src, "", False, "", "", 0.0)
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
        # Try to resolve source IP to name using comprehensive resolution
        src_label = self.simulator._resolve_ip_to_name(original_src)
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
            # Skip source/destination entries (router_name could be FQDN now) and the starting router
            # Check if this is an endpoint by seeing if is_router is False (endpoints are not routers)
            # Also skip if this IP is the same as original source (to avoid duplication)
            if is_router and not router_name.startswith("*") and ip != original_src:
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
                # Re-resolve IP to name using comprehensive lookup for better names
                resolved_name = self.simulator._resolve_ip_to_name(ip)
                if resolved_name != ip:  # If resolution found a better name
                    router_name = resolved_name
                
                if rtt is not None:
                    final_path.append((hop_counter, router_name, ip, interface, is_router, connected_to, outgoing, rtt))
                else:
                    final_path.append((hop_counter, router_name, ip, interface, is_router, connected_to, outgoing))
                hop_counter += 1
        
        # Ensure we end with the destination
        def get_ip_from_hop(hop_data):
            return hop_data[2]  # IP is always the 3rd element regardless of tuple length
        
        # Debug: check if destination is already in the path
        destination_already_present = any(get_ip_from_hop(hop_data) == original_dst for hop_data in final_path)
        if self.verbose >= 2:
            print(f"Destination {original_dst} already in path: {destination_already_present}")
            if destination_already_present:
                for i, hop_data in enumerate(final_path):
                    if get_ip_from_hop(hop_data) == original_dst:
                        print(f"Destination found at hop {i+1}: {hop_data}")
            
        if final_path and not destination_already_present:
            # Extract timing information for destination from forward_path if available
            destination_rtt = 0.0
            for hop_data in forward_path:
                if len(hop_data) >= 8 and hop_data[2] == original_dst:  # Check if this hop reaches the destination
                    destination_rtt = hop_data[7] if len(hop_data) == 8 else 0.0
                    break
                elif len(hop_data) >= 3 and hop_data[2] == original_dst:  # Destination found but no timing
                    destination_rtt = 0.0
                    break
            
            # Try to resolve destination IP to name
            dst_label = self.simulator._resolve_ip_to_name(original_dst)
            # Check if destination is a router
            dst_router_name = self.simulator._find_router_by_ip(original_dst)
            dst_is_router = dst_router_name is not None
            if self.verbose >= 2:
                print(f"Adding destination: {original_dst} -> {dst_label}, is_router: {dst_is_router}")
            final_path.append((hop_counter, dst_label, original_dst, "", dst_is_router, "", "", destination_rtt))
        
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
        Find the last Linux router in a given path that's closest to the destination.
        
        For reverse path tracing, we want the Linux router that's closest to the destination
        and can perform the reverse trace back to the source.
        
        Args:
            path: List of path tuples to analyze
            
        Returns:
            Name of last Linux router, or None if no Linux routers found
        """
        last_linux_router = None
        
        # Iterate through path in reverse order to find the router closest to destination
        for hop_data in reversed(path):
            # Handle both 7-tuple and 8-tuple formats (with optional RTT)
            if len(hop_data) == 8:
                hop_num, router_name, ip, interface, is_router, connected_to, outgoing, rtt = hop_data
            else:
                hop_num, router_name, ip, interface, is_router, connected_to, outgoing = hop_data
            
            # Check if this is a Linux router using IP lookup (not just router inventory)
            # This handles cases where router_name might be FQDN from MTR
            if ip and self.simulator._find_router_by_ip(ip):
                router_found = self.simulator._find_router_by_ip(ip)
                if router_found and router_found in self.simulator.routers:
                    router_obj = self.simulator.routers[router_found]
                    if router_obj.is_linux():
                        last_linux_router = router_found
                        break  # Return the first (closest to destination) Linux router
        
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