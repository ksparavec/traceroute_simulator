#!/usr/bin/env python3
"""
Host Cleanup Script

Removes all registered hosts from the network simulation.
This provides a clean way to remove all hosts without affecting router infrastructure.

Usage:
    sudo python3 host_cleanup.py [--verbose]
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any


class HostCleanup:
    """Manages cleanup of all registered hosts."""
    
    def __init__(self, verbose: int = 0):
        self.verbose = verbose
        self.setup_logging()
        self.host_registry_file = Path("/tmp/traceroute_hosts_registry.json")
        
    def setup_logging(self):
        """Configure logging based on verbosity level."""
        if self.verbose == 0:
            level = logging.WARNING
        elif self.verbose == 1:
            level = logging.INFO
        else:
            level = logging.DEBUG
            
        logging.basicConfig(
            level=level,
            format='%(levelname)s: %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
    def load_host_registry(self) -> Dict[str, Dict]:
        """Load registry of existing hosts."""
        if not self.host_registry_file.exists():
            return {}
            
        try:
            with open(self.host_registry_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Could not load host registry: {e}")
            return {}
            
    def run_command(self, command: str, check: bool = True) -> subprocess.CompletedProcess:
        """Execute command."""
        self.logger.debug(f"Running: {command}")
        
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, check=check
        )
        
        if result.returncode != 0 and check:
            self.logger.error(f"Command failed: {command}")
            self.logger.error(f"Error: {result.stderr}")
            raise subprocess.CalledProcessError(result.returncode, command, result.stderr)
            
        return result
        
    def cleanup_host_resources(self, host_name: str, host_config: Dict):
        """Clean up all resources associated with a host."""
        try:
            # Remove namespace (this automatically removes all interfaces in it)
            self.run_command(f"ip netns del {host_name}", check=False)
            
            # Remove mesh-side veth interfaces based on connection type
            connection_type = host_config.get("connection_type", "")
            
            if connection_type == "sim_mesh_direct":
                # Remove mesh veth from simulation namespace (direct mesh connection)
                mesh_veth = host_config.get("mesh_veth")
                if mesh_veth:
                    self.run_command(f"ip netns exec netsim ip link del {mesh_veth}", check=False)
            elif connection_type == "sim_namespace":
                # Remove sim veth from host namespace (simulation bridge connection) - legacy
                sim_veth = host_config.get("sim_veth")
                if sim_veth:
                    self.run_command(f"ip link del {sim_veth}", check=False)
            elif connection_type == "mesh_direct":
                # Remove mesh veth from host namespace (shared mesh) - legacy
                mesh_veth = host_config.get("mesh_veth")
                if mesh_veth:
                    self.run_command(f"ip link del {mesh_veth}", check=False)
            elif connection_type == "bridge_direct":
                # Remove bridge veth from router namespace (legacy)
                connected_router = host_config.get("connected_to")
                bridge_veth = host_config.get("bridge_veth")
                if connected_router and bridge_veth:
                    self.run_command(f"ip netns exec {connected_router} ip link del {bridge_veth}", check=False)
            elif connection_type == "veth_pair":
                # Remove legacy veth pair
                connected_router = host_config.get("connected_to")
                router_veth = host_config.get("router_veth")
                if connected_router and router_veth:
                    self.run_command(f"ip netns exec {connected_router} ip link del {router_veth}", check=False)
                    
        except Exception as e:
            self.logger.debug(f"Error during cleanup of {host_name}: {e}")
            
    def clean_all_hosts(self) -> bool:
        """Remove all registered hosts."""
        registry = self.load_host_registry()
        
        if not registry:
            if self.verbose >= 1:
                print("No hosts currently registered")
            return True
            
        success_count = 0
        total_count = len(registry)
        
        if self.verbose >= 1:
            print(f"Removing {total_count} registered hosts...")
            
        for host_name, host_config in registry.items():
            try:
                self.cleanup_host_resources(host_name, host_config)
                success_count += 1
                if self.verbose >= 1:
                    print(f"✓ Removed host {host_name}")
            except Exception as e:
                self.logger.error(f"Failed to remove host {host_name}: {e}")
                
        # Remove the registry file
        try:
            if self.host_registry_file.exists():
                self.host_registry_file.unlink()
                if self.verbose >= 1:
                    print("✓ Removed host registry file")
        except Exception as e:
            self.logger.error(f"Failed to remove host registry file: {e}")
            
        if self.verbose >= 1:
            print(f"Host cleanup completed: {success_count}/{total_count} hosts removed successfully")
            
        return success_count == total_count
        
    def check_prerequisites(self) -> bool:
        """Check that required tools and conditions are met."""
        # Check for root privileges
        if os.geteuid() != 0:
            self.logger.error("Root privileges required for host cleanup")
            return False
            
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Clean up all registered hosts from network simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Remove all hosts silently
  sudo %(prog)s
  
  # Remove all hosts with progress output
  sudo %(prog)s -v
  
  # Remove all hosts with detailed output
  sudo %(prog)s -vv
        """
    )
    
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity (-v for info, -vv for debug)')
    parser.add_argument('-f', '--force', action='store_true',
                       help='Force removal (compatibility flag, always forces)')
    
    args = parser.parse_args()
    
    cleanup = HostCleanup(args.verbose)
    
    if not cleanup.check_prerequisites():
        sys.exit(1)
        
    try:
        success = cleanup.clean_all_hosts()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()