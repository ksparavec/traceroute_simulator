#!/usr/bin/env -S python3 -B -u
"""
Host Cleanup Script

Removes all registered hosts from the network simulation.
This script uses the individual host removal logic to ensure proper cleanup,
including removal of router IPs that were added during host creation.

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
from typing import Dict, List

# Import the host namespace setup module to use its removal logic
from tsim.simulators.host_namespace_setup import HostNamespaceManager


class HostCleanup:
    """Manages cleanup of all registered hosts."""
    
    def __init__(self, verbose: int = 0):
        self.verbose = verbose
        self.setup_logging()
        # Set up logging for the simulators module as well
        simulators_logger = logging.getLogger('simulators.host_namespace_setup')
        if self.verbose == 0:
            simulators_logger.setLevel(logging.WARNING)
        elif self.verbose == 1:
            simulators_logger.setLevel(logging.INFO)
        else:
            simulators_logger.setLevel(logging.DEBUG)
        self.host_setup = HostNamespaceManager(verbose=verbose)
        # Load routing facts and discover namespaces so router IP cleanup works
        self.host_setup.discover_namespaces()
        
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
        
    def get_all_hosts(self) -> List[str]:
        """Get list of all registered hosts."""
        registry = self.host_setup.load_host_registry()
        return list(registry.keys())
        
    def clean_all_hosts(self) -> bool:
        """Remove all registered hosts using individual removal logic."""
        hosts = self.get_all_hosts()
        
        if not hosts:
            if self.verbose >= 1:
                print("No hosts currently registered")
            return True
            
        success_count = 0
        total_count = len(hosts)
        
        if self.verbose >= 1:
            print(f"Removing {total_count} registered hosts...")
            
        # Remove each host individually using the proper removal logic
        for host_name in hosts:
            try:
                if self.host_setup.remove_host(host_name):
                    success_count += 1
                    if self.verbose >= 1:
                        print(f"✓ Removed host {host_name}")
                else:
                    self.logger.error(f"Failed to remove host {host_name}")
            except Exception as e:
                self.logger.error(f"Error removing host {host_name}: {e}")
                
        if self.verbose >= 1:
            print(f"Host cleanup completed: {success_count}/{total_count} hosts removed successfully")
            
        return success_count == total_count
        
    def check_prerequisites(self) -> bool:
        """Check that required tools and conditions are met."""
        # Check for tsim-users group membership
        if os.geteuid() != 0:
            import grp
            import pwd
            try:
                username = pwd.getpwuid(os.getuid()).pw_name
                tsim_group = grp.getgrnam('tsim-users')
                if username not in tsim_group.gr_mem:
                    self.logger.warning("User not in tsim-users group. Operations may fail.")
            except KeyError:
                self.logger.warning("tsim-users group not found. Operations may fail.")
            
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