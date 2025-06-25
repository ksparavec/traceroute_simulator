#!/usr/bin/env python3
"""
Network Namespace Cleanup Script

Safely removes all network namespaces, veth pairs, and other resources
created by the network namespace simulation system.

Features:
- Identifies and removes all simulation-related namespaces
- Cleans up orphaned veth interfaces
- Handles cleanup even if setup was incomplete
- Provides safe, idempotent cleanup operation
- Supports force cleanup for stuck resources

Usage:
    python3 network_namespace_cleanup.py [--force] [--verbose]
    
Safety:
- Only removes namespaces that match expected router naming patterns
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
        
        # Expected router name patterns from the test network
        self.router_patterns = [
            r'^hq-\w+$',      # hq-gw, hq-core, hq-dmz, hq-lab
            r'^br-\w+$',      # br-gw, br-core, br-wifi  
            r'^dc-\w+$'       # dc-gw, dc-core, dc-srv
        ]
        
        # Track what we find and clean up
        self.found_namespaces: Set[str] = set()
        self.found_veths: Set[str] = set()
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
        for pattern in self.router_patterns:
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
                        # New patterns: router-interface (hq-gw-eth1, dc-srv-eth0, etc.) or bridge veths (b100r0, b101r1, etc.)
                        if (any(router in interface for router in ['hq-', 'br-', 'dc-']) or 
                            re.match(r'^b\d+r\d+$', interface) or
                            re.match(r'^wg-[a-z]+-[a-z]+$', interface) or  # WireGuard veth interfaces
                            re.match(r'^v\d{3}$', interface)):
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
                        # New patterns: br100, br101, etc. (our clean setup creates these)
                        if (re.match(r'^br1\d{2}$', interface) or  # br100, br101, etc.
                            interface == 'wg-mesh' or              # WireGuard mesh bridge
                            re.match(r'^v\d{3}$', interface)):      # old pattern for backward compatibility
                            self.found_veths.add(interface)  # Add to same cleanup list
                            self.logger.debug(f"Found simulation bridge: {interface}")
            else:
                self.logger.debug("No bridge interfaces found in main namespace")
                        
        except Exception as e:
            self.logger.error(f"Error discovering veth/bridge interfaces: {e}")
            
        self.logger.info(f"Found {len(self.found_veths)} simulation veth/bridge interfaces")
        
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
  - hq-* (hq-gw, hq-core, hq-dmz, hq-lab)
  - br-* (br-gw, br-core, br-wifi)
  - dc-* (dc-gw, dc-core, dc-srv)
  
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