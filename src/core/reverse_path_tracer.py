#!/usr/bin/env -S python3 -B -u
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
        from tsim.executors.mtr_executor import MTRExecutor
        from tsim.core.route_formatter import RouteFormatter
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

            # Load SSH configuration
            ssh_config = None
            try:
                from tsim.core.config_loader import get_ssh_config
                ssh_config = get_ssh_config()
            except ImportError:
                pass

            self.mtr_executor = MTRExecutor(linux_routers, verbose, verbose_level, ssh_config)
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
        if self.verbose_level >= 2:
            print(f"\n--- Step 1: Controller ({self.ansible_controller_ip}) -> Destination ({destination}) ---")
        
        # Debug: Always show this
        if self.verbose and self.verbose_level >= 3:
            print(f"STEP1 DEBUG: Starting controller to destination trace", file=sys.stderr)
        
        # For trace command, always use real MTR execution from the controller
        # No simulation - this is for real network tracing only
        
        if self.verbose_level >= 2:
            print(f"Using controller {self.ansible_controller_ip} for MTR execution (real network)")
            print(f"MTR_AVAILABLE: {MTR_AVAILABLE}")
            print(f"mtr_executor: {self.mtr_executor}")
            if self.simulator.routers:
                print(f"Total routers: {len(self.simulator.routers)}")
                linux_routers = [name for name, router in self.simulator.routers.items() if router.is_linux()]
                print(f"Linux routers: {len(linux_routers)}")
        
        if MTR_AVAILABLE and self.mtr_executor:
            # Use the controller IP directly for SSH
            source_router = self.ansible_controller_ip
            if self.verbose and self.verbose_level >= 3:
                print(f"Using controller {source_router} for MTR execution")
            
            # Execute MTR from controller
            try:
                all_mtr_hops, filtered_mtr_hops = self.mtr_executor.execute_and_filter(source_router, destination)
                mtr_success = bool(all_mtr_hops)  # Success if we got ANY hops, not just Linux routers
                
                if mtr_success:
                    # Create path starting from controller
                    mtr_path = []
                    # Add controller as first hop
                    controller_label = self.simulator._resolve_ip_to_name(self.ansible_controller_ip)
                    mtr_path.append((1, controller_label, self.ansible_controller_ip, "", False, "", "", "", 0.0))
                    
                    # Add ALL MTR hops starting from hop 2 (DO NOT FILTER IN STEP 1!)
                    for i, hop_dict in enumerate(all_mtr_hops):
                        hop_num = i + 2
                        ip = hop_dict.get('ip', '')
                        hostname = hop_dict.get('hostname', '')
                        rtt = hop_dict.get('rtt', 0.0)
                        
                        # Use hostname as router_name if available, otherwise use IP
                        router_name = hostname if hostname else ip
                        
                        # Check if this is a Linux router
                        router_found = self.simulator._find_router_by_ip(ip)
                        is_router = False
                        if router_found and router_found in self.simulator.routers:
                            router_obj = self.simulator.routers[router_found]
                            is_router = router_obj.is_linux()
                        
                        mtr_path.append((hop_num, router_name, ip, "", is_router, "", "", "", rtt))
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
                print("MTR not available")
            return False, [], 2
    
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
        if self.verbose_level >= 2:
            print(f"\n--- Step 2: Destination ({original_dst}) -> Original Source ({original_src}) ---")
        
        # Find the last Linux router in the forward path
        last_linux_router = self._find_last_linux_router(forward_path)
        
        if not last_linux_router:
            if self.verbose:
                print("No Linux routers found in forward path")
            return False, [], 4  # No Linux routers found
        
        if self.verbose_level >= 2:
            print(f"Last Linux router identified: {last_linux_router}")
        
        if self.verbose_level >= 2:
            print(f"Using router {last_linux_router} for reverse trace")
        
        # Use MTR tool for real network tracing
        if MTR_AVAILABLE and self.mtr_executor:
            if self.verbose_level >= 2:
                print("Executing MTR from last Linux router...")
            
            try:
                all_mtr_hops, filtered_mtr_hops = self.mtr_executor.execute_and_filter(last_linux_router, original_src)
                
                # Check if mtr tool executed successfully (even if no Linux routers found)
                if all_mtr_hops:  # mtr tool executed and got some path
                    if filtered_mtr_hops:
                        # Normal case: Linux routers found in path
                        mtr_path = self._convert_mtr_to_simulator_format(filtered_mtr_hops)
                        if self.verbose_level >= 2:
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
                        if self.verbose_level >= 2:
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
                    if self.verbose_level >= 2:
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
        
        Simplified approach:
        1. Add all hops from reverse path in reverse order to temporary path
        2. Add all hops from forward path starting with last Linux router (inclusive)
        3. Filter for Linux routers between source and destination to create final path
        
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
        if self.verbose_level >= 2:
            print(f"\n--- Step 3: Combining Paths ---")
            print(f"Reverse path has {len(reverse_path)} hops")
            print(f"Forward path has {len(forward_path)} hops")
        
        # Find last Linux router in forward path
        last_linux_router = self._find_last_linux_router(forward_path)
        if self.verbose_level >= 2:
            print(f"Last Linux router: {last_linux_router}")
        
        # Initialize
        temp_path = []
        final_path = []
        hop_counter = 1
        
        if last_linux_router:
            # Case 1: Linux router found
            
            # 1. Insert original source IP (create a minimal hop tuple)
            temp_path.append((1, original_src, original_src, "", False, "", "", "", 0.0))
            if self.verbose_level >= 3:
                print(f"After step 1 (added source), temp_path has {len(temp_path)} entries:")
                for i, hop in enumerate(temp_path):
                    if len(hop) >= 8:
                        print(f"  [{i}]: {hop[1]} ({hop[2]}) RTT={hop[7]}ms")
                    else:
                        print(f"  [{i}]: {hop}")
            
            # 2. Insert reverse path from last Linux router in reverse order without original source IP
            for hop_data in reversed(reverse_path):
                try:
                    if hop_data[2] != original_src:  # Skip source IP
                        temp_path.append(hop_data)
                        if self.verbose_level >= 3:
                            print(f"Added from reverse_path: {hop_data}")
                except IndexError as e:
                    raise RuntimeError(f"Malformed hop data in reverse_path: {hop_data}. Expected at least 3 elements, got {len(hop_data)}") from e
            
            if self.verbose_level >= 3:
                print(f"After step 2 (added reverse path), temp_path has {len(temp_path)} entries:")
                for i, hop in enumerate(temp_path):
                    if len(hop) >= 8:
                        print(f"  [{i}]: {hop[1]} ({hop[2]}) RTT={hop[7]}ms")
                    else:
                        print(f"  [{i}]: {hop}")
            
            # 3. Insert last Linux router (find it in forward path)
            # We need to find the hop that corresponds to last_linux_router by comparing IPs
            for hop_data in forward_path:
                try:
                    hop_ip = hop_data[2]  # IP is at position 2
                    # Check if this hop's IP belongs to the last Linux router
                    router_by_ip = self.simulator._find_router_by_ip(hop_ip)
                    if router_by_ip == last_linux_router:
                        temp_path.append(hop_data)
                        if self.verbose_level >= 3:
                            print(f"Added last Linux router from forward_path: {hop_data}")
                        break
                except IndexError as e:
                    raise RuntimeError(f"Malformed hop data in forward_path: {hop_data}. Expected at least 3 elements, got {len(hop_data)}") from e
            
            if self.verbose_level >= 3:
                print(f"After step 3 (added last Linux router), temp_path has {len(temp_path)} entries:")
                for i, hop in enumerate(temp_path):
                    if len(hop) >= 8:
                        print(f"  [{i}]: {hop[1]} ({hop[2]}) RTT={hop[7]}ms")
                    else:
                        print(f"  [{i}]: {hop}")
            
            # 4. Insert destination IP (create a minimal hop tuple)
            # Get destination RTT from forward path if available
            destination_rtt = 0.0
            for hop_data in forward_path:
                try:
                    if hop_data[2] == original_dst:
                        if len(hop_data) >= 9:
                            destination_rtt = hop_data[8]
                        break
                except IndexError as e:
                    raise RuntimeError(f"Malformed hop data in forward_path: {hop_data}. Expected at least 3 elements, got {len(hop_data)}") from e
            temp_path.append((1, original_dst, original_dst, "", False, "", "", "", destination_rtt))
            if self.verbose_level >= 3:
                print(f"After step 4 (added destination), temp_path has {len(temp_path)} entries:")
                for i, hop in enumerate(temp_path):
                    if len(hop) >= 8:
                        print(f"  [{i}]: {hop[1]} ({hop[2]}) RTT={hop[7]}ms")
                    else:
                        print(f"  [{i}]: {hop}")
            
            # 5. Resolve IPs and remove remaining non-Linux routers from path
            if self.verbose_level >= 3:
                print(f"\nStep 5: Processing temp_path to create final_path...")
            for hop_data in temp_path:
                # Extract IP (always at position 2)
                ip = hop_data[2]
                # Extract router name (at position 1)
                try:
                    hop_router_name = hop_data[1]
                except IndexError as e:
                    raise RuntimeError(f"Malformed hop data in temp_path: {hop_data}. Expected at least 2 elements, got {len(hop_data)}") from e
                
                if ip == original_src or ip == original_dst:
                    # Always include source and destination
                    resolved_name = self._resolve_ip(ip)
                    is_router = self.simulator._find_router_by_ip(ip) is not None
                    
                    # Preserve RTT if available (element 8 in 9-element tuple)
                    rtt = hop_data[8] if len(hop_data) >= 9 else 0.0
                    final_path.append((hop_counter, resolved_name, ip, "", is_router, "", "", "", rtt))
                    hop_counter += 1
                else:
                    # Check if this is the last Linux router (NEVER filter it out)
                    if hop_router_name == last_linux_router:
                        # Always include the last Linux router
                        if len(hop_data) >= 9:
                            _, router_name, ip, incoming, is_router, prev_hop, next_hop, outgoing, rtt = hop_data
                            final_path.append((hop_counter, router_name, ip, incoming, is_router, "", next_hop, outgoing, rtt))
                        else:
                            _, router_name, ip, incoming, is_router, next_hop, outgoing = hop_data
                            final_path.append((hop_counter, router_name, ip, incoming, is_router, "", next_hop, outgoing, 0.0))
                        hop_counter += 1
                    else:
                        # For other hops, check if Linux router
                        router_name = self.simulator._find_router_by_ip(ip)
                        if router_name and router_name in self.simulator.routers:
                            router_obj = self.simulator.routers[router_name]
                            if router_obj.is_linux():
                                # Extract all hop data
                                if len(hop_data) >= 9:
                                    _, _, ip, incoming, is_router, prev_hop, next_hop, outgoing, rtt = hop_data
                                    final_path.append((hop_counter, router_name, ip, incoming, is_router, "", next_hop, outgoing, rtt))
                                else:
                                    _, _, ip, incoming, is_router, next_hop, outgoing = hop_data
                                    final_path.append((hop_counter, router_name, ip, incoming, is_router, "", next_hop, outgoing, 0.0))
                                hop_counter += 1
        
        else:
            # Case 2: No Linux router found - just source and destination
            
            # Insert source IP
            resolved_src = self._resolve_ip(original_src)
            src_is_router = self.simulator._find_router_by_ip(original_src) is not None
            final_path.append((hop_counter, resolved_src, original_src, "", src_is_router, "", "", "", 0.0))
            hop_counter += 1
            
            # Insert destination IP
            resolved_dst = self._resolve_ip(original_dst)
            dst_is_router = self.simulator._find_router_by_ip(original_dst) is not None
            # Get destination RTT from forward path if available
            destination_rtt = 0.0
            for hop_data in forward_path:
                try:
                    if hop_data[2] == original_dst:
                        if len(hop_data) >= 9:
                            destination_rtt = hop_data[8]
                        break
                except IndexError as e:
                    raise RuntimeError(f"Malformed hop data in forward_path: {hop_data}. Expected at least 3 elements, got {len(hop_data)}") from e
            final_path.append((hop_counter, resolved_dst, original_dst, "", dst_is_router, "", "", "", destination_rtt))
        
        
        if self.verbose_level >= 2:
            print(f"Final path has {len(final_path)} hops")
            for hop in final_path:
                if len(hop) >= 8:
                    print(f"  Hop {hop[0]}: {hop[1]} ({hop[2]}) RTT={hop[7]}ms")
                else:
                    print(f"  Hop {hop[0]}: {hop[1]} ({hop[2]})")
        
        # Step 4: Populate prev_hop and next_hop fields
        if self.verbose_level >= 2:
            print(f"\n--- Step 4: Populating prev_hop and next_hop fields ---")
        
        # First pass: Set prev_hop for each router (forward direction)
        updated_path = []
        prev_hop_name = None
        
        for hop_data in final_path:
            # Unpack the hop data (now includes empty prev_hop)
            if len(hop_data) >= 9:
                hop_num, router_name, ip, incoming, is_router, prev_hop, next_hop, outgoing, rtt = hop_data
            else:
                # Handle old format (8 elements) for backward compatibility
                hop_num, router_name, ip, incoming, is_router, next_hop, outgoing, rtt = hop_data
                prev_hop = ""
            
            # Set prev_hop for all hops
            prev_hop_value = prev_hop_name if prev_hop_name else ""
            
            # Create updated hop with prev_hop set (next_hop will be set in second pass)
            updated_hop = (hop_num, router_name, ip, incoming, is_router, prev_hop_value, next_hop, outgoing, rtt)
            updated_path.append(updated_hop)
            
            # Update prev_hop_name for next iteration
            prev_hop_name = router_name
        
        # Second pass: Set next_hop for each router (reverse direction)
        final_updated_path = []
        next_hop_name = None
        
        for hop_data in reversed(updated_path):
            # Unpack the hop data (now includes prev_hop from first pass)
            hop_num, router_name, ip, incoming, is_router, prev_hop, _, outgoing, rtt = hop_data
            
            # Set next_hop for all hops
            next_hop_value = next_hop_name if next_hop_name else ""
            
            # Create final hop with both prev_hop and next_hop set
            final_hop = (hop_num, router_name, ip, incoming, is_router, prev_hop, next_hop_value, outgoing, rtt)
            final_updated_path.insert(0, final_hop)  # Insert at beginning since we're going in reverse
            
            # Update next_hop_name for next iteration
            next_hop_name = router_name
        
        if self.verbose_level >= 2:
            print(f"Updated path with prev_hop and next_hop:")
            for hop in final_updated_path:
                print(f"  Hop {hop[0]}: {hop[1]} prev_hop={hop[5]}, next_hop={hop[6]}")
        
        # Step 5: Detect router interfaces via remote SSH
        if self.verbose_level >= 2:
            print(f"\n--- Step 5: Detecting router interfaces via SSH ---")
        
        final_path_with_interfaces = self._detect_router_interfaces(
            final_updated_path, original_src, original_dst
        )
        
        return True, final_path_with_interfaces
    
    def _resolve_ip(self, ip: str) -> str:
        """
        Resolve IP address to a name.
        
        First tries router lookup, then reverse DNS, falls back to IP.
        
        Args:
            ip: IP address to resolve
            
        Returns:
            Resolved name or IP address
        """
        # First try router lookup
        router_name = self.simulator._find_router_by_ip(ip)
        if router_name:
            return router_name
        
        # Then try reverse DNS
        try:
            import socket
            return socket.gethostbyaddr(ip)[0]
        except:
            return ip  # Return IP if DNS fails
    
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
            # Handle both old and new tuple formats
            if len(hop_data) >= 9:
                hop_num, router_name, ip, incoming, is_router, prev_hop, next_hop, outgoing, rtt = hop_data
            elif len(hop_data) == 8:
                hop_num, router_name, ip, incoming, is_router, next_hop, outgoing, rtt = hop_data
            else:
                hop_num, router_name, ip, incoming, is_router, next_hop, outgoing = hop_data
                rtt = 0.0
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
            # Handle both old and new tuple formats
            if len(hop_data) >= 9:
                hop_num, router_name, ip, incoming, is_router, prev_hop, next_hop, outgoing, rtt = hop_data
            elif len(hop_data) == 8:
                hop_num, router_name, ip, incoming, is_router, next_hop, outgoing, rtt = hop_data
            else:
                hop_num, router_name, ip, incoming, is_router, next_hop, outgoing = hop_data
                rtt = 0.0
            
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
        Simulator tuples have format: (hop_num, router_name, ip, incoming, is_router, prev_hop, next_hop, outgoing, rtt)
        
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
            
            # For mtr tool hops, we don't have incoming interface information
            incoming = ""
            is_router = True  # mtr tool filtered hops are Linux routers
            next_hop = ""
            outgoing = ""
            
            simulator_hop = (hop_num, router_name, ip, incoming, is_router, "", next_hop, outgoing, rtt)
            simulator_hops.append(simulator_hop)
        
        return simulator_hops
    
    def _detect_router_interfaces(self, path: List[Tuple], source_ip: str, destination_ip: str) -> List[Tuple]:
        """
        Detect incoming and outgoing interfaces for routers via SSH.
        
        For each router in the path, executes:
        - ip route get <source_ip> to find incoming interface
        - ip route get <destination_ip> to find outgoing interface
        
        Args:
            path: List of path tuples
            source_ip: Original source IP address
            destination_ip: Original destination IP address
            
        Returns:
            Updated path with interface information
        """
        import subprocess
        import socket
        
        # Load configuration to determine if we're on the ansible controller
        on_controller = False
        try:
            from tsim.core.config_loader import load_traceroute_config
            config = load_traceroute_config()
            on_controller = config.get('ansible_controller', False)
        except ImportError:
            # Default to False if config loader not available
            on_controller = False

        if self.verbose_level >= 2:
            try:
                hostname = socket.gethostname()
                print(f"Current host: {hostname}")
            except:
                print(f"Current host: unknown")
            print(f"Ansible controller IP: {self.ansible_controller_ip}")
            print(f"Running on controller (configured): {on_controller}")
        
        # Load SSH configuration from config file for routers
        ssh_config = {}
        try:
            from tsim.core.config_loader import get_ssh_config
            ssh_config = get_ssh_config()
        except ImportError:
            # Fallback to defaults if config loader not available
            ssh_config = {
                'ssh_mode': 'standard',
                'ssh_user': None,
                'ssh_key': None,
                'ssh_options': {
                    'BatchMode': 'yes',
                    'LogLevel': 'ERROR',
                    'ConnectTimeout': '5',
                    'StrictHostKeyChecking': 'no',
                    'UserKnownHostsFile': '/dev/null'
                }
            }

        ssh_mode = ssh_config.get('ssh_mode', 'standard')
        ssh_user = ssh_config.get('ssh_user')
        ssh_key = ssh_config.get('ssh_key')

        # Build SSH options from configuration for router connections
        ssh_opts_routers = []
        for option, value in ssh_config.get('ssh_options', {}).items():
            ssh_opts_routers.extend(['-o', f'{option}={value}'])

        # Add user and key options for user mode (routers)
        if ssh_mode == 'user' and ssh_user and ssh_key:
            ssh_opts_routers.extend(['-i', ssh_key, '-l', ssh_user])

        # Load SSH configuration for controller connections
        ssh_controller_config = {}
        try:
            from tsim.core.config_loader import get_ssh_controller_config
            ssh_controller_config = get_ssh_controller_config()
        except ImportError:
            # Fallback to defaults if config loader not available
            ssh_controller_config = {
                'ssh_mode': 'standard',
                'ssh_user': None,
                'ssh_key': None,
                'ssh_options': {
                    'BatchMode': 'yes',
                    'ConnectTimeout': '10',
                    'StrictHostKeyChecking': 'yes',
                    'UserKnownHostsFile': '~/.ssh/known_hosts'
                }
            }

        ssh_controller_mode = ssh_controller_config.get('ssh_mode', 'standard')
        ssh_controller_user = ssh_controller_config.get('ssh_user')
        ssh_controller_key = ssh_controller_config.get('ssh_key')

        # Build SSH options from configuration for controller connections
        ssh_opts_controller = []
        for option, value in ssh_controller_config.get('ssh_options', {}).items():
            ssh_opts_controller.extend(['-o', f'{option}={value}'])

        # Add user and key options for user mode (controller)
        if ssh_controller_mode == 'user' and ssh_controller_user and ssh_controller_key:
            ssh_opts_controller.extend(['-i', ssh_controller_key, '-l', ssh_controller_user])
        
        updated_path = []
        
        for hop_data in path:
            # Unpack the hop data
            if len(hop_data) >= 9:
                hop_num, router_name, ip, incoming, is_router, prev_hop, next_hop, outgoing, rtt = hop_data
            else:
                # Skip malformed hops
                updated_path.append(hop_data)
                continue
            
            # Only process routers
            if not is_router:
                updated_path.append(hop_data)
                continue
            
            if self.verbose_level >= 2:
                print(f"\nProcessing router: {router_name} ({ip})")
            
            # Initialize interface names
            incoming_interface = ""
            outgoing_interface = ""
            
            try:
                # Build commands to get interfaces
                cmd_incoming = f"ip route get {source_ip} | head -1"
                cmd_outgoing = f"ip route get {destination_ip} | head -1"
                
                if on_controller:
                    # ansible_controller=true: Direct SSH to routers
                    ssh_cmd_incoming = ["ssh"] + ssh_opts_routers + [ip, cmd_incoming]
                    ssh_cmd_outgoing = ["ssh"] + ssh_opts_routers + [ip, cmd_outgoing]
                else:
                    # ansible_controller=false: Route through controller using nested SSH
                    # Escape the command for nested execution
                    escaped_cmd_incoming = cmd_incoming.replace('"', '\\"')
                    escaped_cmd_outgoing = cmd_outgoing.replace('"', '\\"')
                    
                    # Build inner SSH command with router options
                    inner_ssh_opts = ' '.join(ssh_opts_routers)
                    inner_ssh_incoming = f"ssh {inner_ssh_opts} {ip} \"{escaped_cmd_incoming}\""
                    inner_ssh_outgoing = f"ssh {inner_ssh_opts} {ip} \"{escaped_cmd_outgoing}\""
                    
                    # Outer SSH to controller uses controller options
                    ssh_cmd_incoming = ["ssh"] + ssh_opts_controller + [self.ansible_controller_ip, inner_ssh_incoming]
                    ssh_cmd_outgoing = ["ssh"] + ssh_opts_controller + [self.ansible_controller_ip, inner_ssh_outgoing]
                
                # Execute commands
                if self.verbose_level >= 3:
                    print(f"Getting incoming interface: {' '.join(ssh_cmd_incoming)}")
                
                result_incoming = subprocess.run(ssh_cmd_incoming, capture_output=True, text=True, timeout=10)
                if result_incoming.returncode == 0:
                    incoming_interface = self._extract_interface_from_route(result_incoming.stdout)
                    if self.verbose_level >= 2:
                        print(f"  Incoming interface: {incoming_interface}")
                elif self.verbose:
                    print(f"  Failed to get incoming interface: {result_incoming.stderr.strip()}")
                
                if self.verbose_level >= 3:
                    print(f"Getting outgoing interface: {' '.join(ssh_cmd_outgoing)}")
                
                result_outgoing = subprocess.run(ssh_cmd_outgoing, capture_output=True, text=True, timeout=10)
                if result_outgoing.returncode == 0:
                    outgoing_interface = self._extract_interface_from_route(result_outgoing.stdout)
                    if self.verbose_level >= 2:
                        print(f"  Outgoing interface: {outgoing_interface}")
                elif self.verbose:
                    print(f"  Failed to get outgoing interface: {result_outgoing.stderr.strip()}")
                    
            except subprocess.TimeoutExpired:
                if self.verbose:
                    print(f"  SSH timeout for router {router_name}")
            except Exception as e:
                if self.verbose:
                    print(f"  Error detecting interfaces for {router_name}: {e}")
            
            # Create updated hop with interface information
            updated_hop = (hop_num, router_name, ip, incoming_interface, is_router, 
                          prev_hop, next_hop, outgoing_interface, rtt)
            updated_path.append(updated_hop)
        
        return updated_path
    
    def _extract_interface_from_route(self, route_output: str) -> str:
        """
        Extract interface name from 'ip route get' output.
        
        Example output:
        10.1.1.1 via 10.2.1.1 dev eth0 src 10.2.1.2
        
        Args:
            route_output: Output from 'ip route get' command
            
        Returns:
            Interface name or empty string if not found
        """
        import re
        
        # Look for "dev <interface_name>" pattern
        match = re.search(r'dev\s+(\S+)', route_output)
        if match:
            return match.group(1)
        return ""