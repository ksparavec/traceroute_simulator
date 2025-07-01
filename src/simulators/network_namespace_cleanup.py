#!/usr/bin/env python3
"""
Network Namespace Cleanup Script

Safely removes all network namespaces, veth pairs, and other resources
created by the network namespace simulation system.

Features:
- Identifies and removes all simulation-related namespaces
- Cleans up router namespaces (hq-*, br-*, dc-*)
- Removes temporary hosts (test*, web*, db*, app*, etc.)
- Removes temporary public IP hosts (pub*, p*)
- Cleans up orphaned veth interfaces
- Handles cleanup even if setup was incomplete
- Provides safe, idempotent cleanup operation
- Supports force cleanup for stuck resources

Usage:
    python3 network_namespace_cleanup.py [--force] [--verbose]
    
Safety:
- Only removes namespaces that match expected simulation patterns
- Includes router namespaces, test hosts, and temporary hosts
- Preserves system namespaces and other network configurations
- Can be run multiple times safely (idempotent)
"""

import argparse
import logging
import os
import subprocess
import sys
import re
from typing import List, Set
from pathlib import Path


class NetworkNamespaceCleanup:
    """
    Safely cleans up network namespace simulation resources.
    
    Removes namespaces, veth pairs, and other simulation artifacts
    while preserving system network configuration.
    """
    
    def __init__(self, force: bool = False, verbose: int = 0):
        """
        Initialize the cleanup system.
        
        Args:
            force: Force removal of stuck resources
            verbose: Verbosity level (0=silent, 1=basic, 2=info, 3=debug)
        """
        self.force = force
        self.verbose = verbose
        self.setup_logging()
        
        # Dynamic router discovery from facts
        self.known_routers: Set[str] = set()
        self.load_router_names_from_facts()
        
        # General namespace patterns (no hardcoded router names)
        self.namespace_patterns = [
            r'^netsim$',      # Simulation namespace
            r'^hidden-mesh$', # Hidden mesh infrastructure namespace
            r'^pub[a-f0-9]+-.*$',  # Temporary public IP hosts (pub{hash}-{router})
            r'^p[a-f0-9]+$',  # Temporary public IP hosts (shortened format)
            r'^h[a-f0-9]+$',  # Temporary dynamic hosts
            r'^web\d*$',      # Test web hosts
            r'^db\d*$',       # Test database hosts  
            r'^app\d*$',      # Test application hosts
            r'^srv\d*$',      # Test server hosts
            r'^client\d*$',   # Test client hosts
            r'^test\d*$',     # Generic test hosts
            r'^test-.*$'      # Test hosts with descriptive names
        ]
        
        # Track what we find and clean up
        self.found_namespaces: Set[str] = set()
        self.found_veths: Set[str] = set()
        self.found_mesh_bridges: Set[str] = set()
        self.cleanup_errors: List[str] = []
        
    def setup_logging(self):
        """Configure logging based on verbosity level."""
        # Configure logging levels based on verbosity
        if self.verbose == 0:
            level = logging.CRITICAL  # Silent mode - only critical errors
        elif self.verbose == 1:
            level = logging.ERROR     # Basic mode - errors only (summary printed separately)
        elif self.verbose == 2:
            level = logging.INFO      # Info mode - info and errors
        else:  # verbose >= 3
            level = logging.DEBUG     # Debug mode - everything
            
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)
        
    def load_router_names_from_facts(self):
        """Load router names dynamically from facts directories."""
        self.known_routers = set()
        
        # Check multiple possible facts locations
        facts_locations = [
            os.environ.get('TRACEROUTE_SIMULATOR_FACTS', 'tests/tsim_facts'),
            os.environ.get('TRACEROUTE_SIMULATOR_RAW_FACTS', 'tests/raw_facts'),
            '/tmp/traceroute_test_output',
            'tests/tsim_facts',
            'tests/raw_facts'
        ]
        
        for facts_dir in facts_locations:
            if not facts_dir:
                continue
                
            facts_path = Path(facts_dir)
            if not facts_path.exists():
                continue
                
            self.logger.debug(f"Checking facts directory: {facts_path}")
            
            # Look for JSON facts files
            for json_file in facts_path.glob("*.json"):
                if json_file.name.endswith('_metadata.json'):
                    continue  # Skip metadata files
                router_name = json_file.stem
                self.known_routers.add(router_name)
                self.logger.debug(f"Found router from JSON: {router_name}")
            
            # Look for raw facts files
            for raw_file in facts_path.glob("*_facts.txt"):
                router_name = raw_file.stem.replace('_facts', '')
                self.known_routers.add(router_name)
                self.logger.debug(f"Found router from raw facts: {router_name}")
        
        self.logger.info(f"Discovered {len(self.known_routers)} routers from facts: {sorted(self.known_routers)}")
        
    def check_command_availability(self, command: str) -> bool:
        """Check if a command is available on the system."""
        try:
            result = subprocess.run(
                f"which {command}",
                shell=True,
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode == 0
        except Exception:
            return False
            
    def run_command(self, command: str, check: bool = True) -> subprocess.CompletedProcess:
        """
        Execute a shell command with error handling.
        
        Args:
            command: Shell command to execute
            check: Whether to raise exception on command failure
            
        Returns:
            CompletedProcess result
        """
        self.logger.debug(f"Running: {command}")
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                check=check
            )
            return result
        except subprocess.CalledProcessError as e:
            self.logger.debug(f"Command failed: {command}")
            self.logger.debug(f"Exit code: {e.returncode}")
            self.logger.debug(f"Stderr: {e.stderr}")
            if check:
                raise
            return e
            
    def is_simulation_namespace(self, namespace: str) -> bool:
        """
        Check if a namespace belongs to our simulation.
        
        Args:
            namespace: Namespace name to check
            
        Returns:
            True if namespace is part of our simulation
        """
        # Check if it's a known router from facts
        if namespace in self.known_routers:
            return True
            
        # Check general patterns
        for pattern in self.namespace_patterns:
            if re.match(pattern, namespace):
                return True
        return False
        
    def discover_namespaces(self):
        """Discover simulation namespaces that need cleanup."""
        self.logger.info("Discovering simulation namespaces")
        
        try:
            result = self.run_command("ip netns list", check=False)
            if result.returncode != 0:
                self.logger.warning("Failed to list namespaces - may already be clean")
                return
                
            # Parse namespace list
            for line in result.stdout.split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                # Extract namespace name (format: "namespace_name (id: X)")
                ns_match = re.match(r'^([^\s(]+)', line)
                if ns_match:
                    namespace = ns_match.group(1)
                    if self.is_simulation_namespace(namespace):
                        self.found_namespaces.add(namespace)
                        self.logger.debug(f"Found simulation namespace: {namespace}")
                        
        except Exception as e:
            self.logger.error(f"Error discovering namespaces: {e}")
            
        self.logger.info(f"Found {len(self.found_namespaces)} simulation namespaces")
        
    def discover_veth_interfaces(self):
        """Discover veth and bridge interfaces that may need cleanup."""
        self.logger.info("Discovering veth and bridge interfaces")
        
        try:
            # Look for veth interfaces in the main namespace
            result = self.run_command("ip link show type veth", check=False)
            if result.returncode == 0:
                # Parse veth interface list
                for line in result.stdout.split('\n'):
                    # Look for lines like: "123: veth-name@if124: <BROADCAST,MULTICAST> ..."
                    veth_match = re.search(r'^\d+:\s+([^@:]+)', line)
                    if veth_match:
                        interface = veth_match.group(1)
                        # Check if it looks like a simulation interface
                        # Dynamic router detection + hidden mesh patterns
                        is_simulation_veth = False
                        
                        # Check if interface belongs to known routers
                        for router_name in self.known_routers:
                            if interface.startswith(f"{router_name}-"):
                                is_simulation_veth = True
                                break
                        
                        # Check general simulation patterns
                        if not is_simulation_veth:
                            if (re.match(r'^b\d+r\d+$', interface) or
                                re.match(r'^wg-[a-z]+-[a-z]+$', interface) or  # WireGuard veth interfaces
                                re.match(r'^v\d{3}$', interface) or
                                re.match(r'^r\d{2}\w+[rh]$', interface) or  # New compressed naming: r00eth0r, r01wg0h, etc.
                                '-router' in interface or '-hidden' in interface):  # Legacy hidden mesh veth pairs
                                is_simulation_veth = True
                        
                        if is_simulation_veth:
                            self.found_veths.add(interface)
                            self.logger.debug(f"Found simulation veth: {interface}")
            else:
                self.logger.debug("No veth interfaces found in main namespace")
                
            # Look for bridge interfaces in the main namespace
            bridge_result = self.run_command("ip link show type bridge", check=False)
            if bridge_result.returncode == 0:
                # Parse bridge interface list
                for line in bridge_result.stdout.split('\n'):
                    # Look for lines like: "123: bridge-name: <BROADCAST,MULTICAST> ..."
                    bridge_match = re.search(r'^\d+:\s+([^:]+)', line)
                    if bridge_match:
                        interface = bridge_match.group(1)
                        # Check if it looks like a simulation bridge
                        # New patterns: sim-bridge and legacy patterns
                        if (interface == 'sim-bridge' or              # Host-to-simulation bridge
                            re.match(r'^br1\d{2}$', interface) or     # br100, br101, etc. (legacy)
                            interface == 'wg-mesh' or                 # WireGuard mesh bridge (legacy)
                            re.match(r'^v\d{3}$', interface)):        # old pattern for backward compatibility
                            self.found_veths.add(interface)  # Add to same cleanup list
                            self.logger.debug(f"Found simulation bridge: {interface}")
            else:
                self.logger.debug("No bridge interfaces found in main namespace")
                        
        except Exception as e:
            self.logger.error(f"Error discovering veth/bridge interfaces: {e}")
            
        self.logger.info(f"Found {len(self.found_veths)} simulation veth/bridge interfaces")
        
    def discover_mesh_bridges(self):
        """Discover mesh bridges created by the unified mesh architecture."""
        self.logger.debug("Discovering mesh bridges in host namespace")
        
        try:
            # List all interfaces in the main namespace
            result = self.run_command("ip link show", check=False)
            if result.returncode != 0:
                self.logger.warning("Could not list interfaces in main namespace")
                return
                
            for line in result.stdout.split('\n'):
                # Look for mesh bridge pattern: m100, m101, m102, etc.
                match = re.match(r'^\d+:\s+(m\d+):', line)
                if match:
                    mesh_bridge = match.group(1)
                    self.found_mesh_bridges.add(mesh_bridge)
                    self.logger.debug(f"Found mesh bridge: {mesh_bridge}")
                    
        except Exception as e:
            self.logger.error(f"Error discovering mesh bridges: {e}")
            
        self.logger.info(f"Found {len(self.found_mesh_bridges)} mesh bridges")
        
    def cleanup_mesh_bridge(self, bridge: str) -> bool:
        """
        Clean up a mesh bridge from the host namespace.
        
        Args:
            bridge: Bridge name to clean up
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.debug(f"Removing mesh bridge: {bridge}")
            self.run_command(f"ip link del {bridge}", check=True)
            if self.verbose >= 2:
                print(f"  Removed mesh bridge: {bridge}")
            return True
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to remove mesh bridge {bridge}: {e}"
            self.logger.error(error_msg)
            self.cleanup_errors.append(error_msg)
            if self.verbose >= 1:
                print(f"  Error removing mesh bridge {bridge}: {e}")
            return False
        
    def cleanup_namespace(self, namespace: str) -> bool:
        """
        Clean up a single namespace.
        
        Args:
            namespace: Namespace name to clean up
            
        Returns:
            True if cleanup succeeded
        """
        self.logger.debug(f"Cleaning up namespace: {namespace}")
        
        try:
            # First, try to kill any processes in the namespace
            if self.force:
                self.run_command(f"ip netns pids {namespace} | xargs -r kill -9", check=False)
                
            # Remove the namespace
            result = self.run_command(f"ip netns delete {namespace}", check=False)
            if result.returncode == 0:
                self.logger.debug(f"Successfully removed namespace: {namespace}")
                return True
            else:
                error_msg = f"Failed to remove namespace {namespace}: {result.stderr.strip()}"
                self.logger.warning(error_msg)
                self.cleanup_errors.append(error_msg)
                return False
                
        except Exception as e:
            error_msg = f"Error cleaning up namespace {namespace}: {e}"
            self.logger.error(error_msg)
            self.cleanup_errors.append(error_msg)
            return False
            
    def cleanup_veth_interface(self, interface: str) -> bool:
        """
        Clean up a single veth or bridge interface.
        
        Args:
            interface: Interface name to clean up (veth or bridge)
            
        Returns:
            True if cleanup succeeded
        """
        self.logger.debug(f"Cleaning up interface: {interface}")
        
        try:
            # Check if interface still exists
            check_result = self.run_command(f"ip link show {interface}", check=False)
            if check_result.returncode != 0:
                self.logger.debug(f"Interface {interface} already gone")
                return True
                
            # Remove the interface
            result = self.run_command(f"ip link delete {interface}", check=False)
            if result.returncode == 0:
                self.logger.debug(f"Successfully removed interface: {interface}")
                return True
            else:
                error_msg = f"Failed to remove interface {interface}: {result.stderr.strip()}"
                self.logger.warning(error_msg)
                self.cleanup_errors.append(error_msg)
                return False
                
        except Exception as e:
            error_msg = f"Error cleaning up interface {interface}: {e}"
            self.logger.error(error_msg)
            self.cleanup_errors.append(error_msg)
            return False
            
    def cleanup_ipsets(self):
        """Clean up any simulation-related ipsets."""
        self.logger.info("Cleaning up ipsets")
        
        try:
            # List ipsets to see what exists
            result = self.run_command("ipset list -n", check=False)
            if result.returncode != 0:
                self.logger.debug("No ipsets found or ipset not available")
                return
                
            # Look for simulation-related ipsets
            simulation_ipsets = []
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line and ('HQ_' in line or 'BR_' in line or 'DC_' in line or 'VPN_' in line):
                    simulation_ipsets.append(line)
                    
            # Remove simulation ipsets
            for ipset_name in simulation_ipsets:
                self.logger.debug(f"Removing ipset: {ipset_name}")
                self.run_command(f"ipset destroy {ipset_name}", check=False)
                
            if simulation_ipsets:
                self.logger.info(f"Cleaned up {len(simulation_ipsets)} ipsets")
                
        except Exception as e:
            self.logger.debug(f"Error cleaning up ipsets: {e}")
            
    def perform_cleanup(self):
        """Execute the complete cleanup process."""
        # Print initial message for basic verbosity and above
        if self.verbose >= 1:
            print("Cleaning up Linux namespace network simulation")
            
        self.logger.info("Starting network namespace cleanup")
        
        # Check for mandatory tools
        if not self.check_command_availability("ip"):
            error_msg = "Error: 'ip' command not available - required for namespace operations"
            if self.verbose >= 1:
                print(error_msg)
                print("Install with: sudo apt-get install iproute2")
            self.logger.error(error_msg)
            return 1  # Error exit code
        
        # Check for optional tools
        ipset_available = self.check_command_availability("ipset")
        if not ipset_available:
            self.logger.warning("ipset not available - skipping ipset cleanup")
            if self.verbose >= 1:
                print("Warning: ipset not available - ipset cleanup skipped")
        
        # Discover what needs cleanup
        self.discover_namespaces()
        self.discover_veth_interfaces()
        self.discover_mesh_bridges()
        
        cleanup_count = 0
        
        # Clean up namespaces first (this should remove their interfaces automatically)
        if self.found_namespaces:
            self.logger.info(f"Cleaning up {len(self.found_namespaces)} namespaces")
            for namespace in self.found_namespaces:
                if self.cleanup_namespace(namespace):
                    cleanup_count += 1
                    
        # Clean up any remaining veth interfaces
        if self.found_veths:
            self.logger.info(f"Cleaning up {len(self.found_veths)} veth interfaces")
            for interface in self.found_veths:
                if self.cleanup_veth_interface(interface):
                    cleanup_count += 1
                    
        # Clean up mesh bridges from host namespace
        if self.found_mesh_bridges:
            self.logger.info(f"Cleaning up {len(self.found_mesh_bridges)} mesh bridges")
            for bridge in self.found_mesh_bridges:
                if self.cleanup_mesh_bridge(bridge):
                    cleanup_count += 1
                    
        # Clean up ipsets (only if ipset is available)
        if ipset_available:
            self.cleanup_ipsets()
        
        # Final verification
        self.verify_cleanup()
        
        # Print success message and summary for basic verbosity and above
        if self.verbose >= 1:
            if self.cleanup_errors:
                print("Network namespace cleanup completed with errors")
            else:
                print("Network namespace cleanup completed successfully")
            self.print_summary(cleanup_count)
        
        # Return appropriate exit code
        return 1 if self.cleanup_errors else 0
        
    def verify_cleanup(self):
        """Verify that cleanup was successful."""
        self.logger.debug("Verifying cleanup completion")
        
        # Check for remaining simulation namespaces
        try:
            result = self.run_command("ip netns list", check=False)
            if result.returncode == 0:
                remaining_ns = []
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line:
                        ns_match = re.match(r'^([^\s(]+)', line)
                        if ns_match:
                            namespace = ns_match.group(1)
                            if self.is_simulation_namespace(namespace):
                                remaining_ns.append(namespace)
                                
                if remaining_ns:
                    self.logger.warning(f"Some namespaces remain: {remaining_ns}")
                    
        except Exception as e:
            self.logger.debug(f"Error verifying namespace cleanup: {e}")
            
    def print_summary(self, cleanup_count: int):
        """Print cleanup summary."""
        print("\n" + "="*60)
        print("NETWORK NAMESPACE CLEANUP SUMMARY")
        print("="*60)
        
        print(f"Found namespaces: {len(self.found_namespaces)}")
        if self.found_namespaces:
            for ns in sorted(self.found_namespaces):
                print(f"  - {ns}")
                
        print(f"Found veth interfaces: {len(self.found_veths)}")
        if self.found_veths:
            for veth in sorted(self.found_veths):
                print(f"  - {veth}")
                
        print(f"Found mesh bridges: {len(self.found_mesh_bridges)}")
        if self.found_mesh_bridges:
            for bridge in sorted(self.found_mesh_bridges):
                print(f"  - {bridge}")
                
        print(f"\nSuccessfully cleaned up: {cleanup_count} items")
        
        if self.cleanup_errors:
            print(f"Cleanup errors: {len(self.cleanup_errors)}")
            for error in self.cleanup_errors:
                print(f"  - {error}")
            print("\nSome cleanup operations failed. You may need to:")
            print("1. Run with --force flag")
            print("2. Manually remove stuck resources")
            print("3. Check for running processes in namespaces")
        else:
            print("All cleanup operations completed successfully!")
            
        print("="*60)


def main():
    """Main entry point for network namespace cleanup."""
    parser = argparse.ArgumentParser(
        description="Clean up network namespace simulation resources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Silent cleanup (no output except errors)
  %(prog)s -v                 # Basic cleanup with status messages
  %(prog)s -vv                # Info cleanup with detailed messages
  %(prog)s -vvv               # Debug cleanup with full logging
  %(prog)s --force            # Force cleanup of stuck resources
  %(prog)s -v --force         # Verbose force cleanup
  
Verbosity Levels:
  (none)  - Silent mode: no output except on error, exit code 0/1
  -v      - Basic mode: cleanup status and summary only
  -vv     - Info mode: basic + INFO level messages  
  -vvv    - Debug mode: info + DEBUG level messages
  
Safety:
  This script only removes namespaces matching simulation patterns:
  - Router namespaces discovered from facts files
  - Simulation infrastructure namespaces (hidden-mesh, netsim)
  - Test and temporary host namespaces
  
  System namespaces and other network configuration are preserved.
        """
    )
    
    parser.add_argument(
        '-f', '--force',
        action='store_true',
        help='Force removal of stuck resources'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='count',
        default=0,
        help='Increase verbosity: -v (basic), -vv (info), -vvv (debug)'
    )
    
    args = parser.parse_args()
    
    # Check for root privileges
    if os.geteuid() != 0:
        print("Error: This script requires root privileges to manage network namespaces")
        print("Please run with sudo:")
        print(f"  sudo {' '.join(sys.argv)}")
        sys.exit(1)
        
    try:
        cleanup = NetworkNamespaceCleanup(args.force, args.verbose)
        exit_code = cleanup.perform_cleanup()
        sys.exit(exit_code)
        
    except Exception as e:
        # In silent mode, don't print anything
        if args.verbose > 0:
            print(f"Cleanup failed: {e}")
        sys.exit(2)


if __name__ == '__main__':
    main()