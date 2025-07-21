"""
Host command handler for managing dynamic host creation and removal.
"""

import argparse
from typing import Optional, List

try:
    from cmd2 import Cmd2ArgumentParser, choices_provider
except ImportError:
    # Fallback for older cmd2 versions
    from argparse import ArgumentParser as Cmd2ArgumentParser
    def choices_provider(func):
        return func

from .base import BaseCommandHandler


class HostCommands(BaseCommandHandler):
    """Handler for host management commands."""
    
    @choices_provider
    def router_choices(self) -> List[str]:
        """Provide router name choices for completion."""
        if hasattr(self.shell, 'completers'):
            return self.shell.completers._get_router_names()
        return []
    
    @choices_provider
    def host_choices(self) -> List[str]:
        """Provide existing host names for completion."""
        # This would need to query existing hosts
        # For now, return empty list
        return []
    
    def create_parser(self) -> Cmd2ArgumentParser:
        """Create the argument parser for host commands."""
        parser = Cmd2ArgumentParser(prog='host', description='Manage dynamic host creation and removal')
        subparsers = parser.add_subparsers(dest='subcommand', help='Host subcommands')
        
        # Add subcommand
        add_parser = subparsers.add_parser('add', help='Add a new host to the network')
        add_parser.add_argument('--name', required=True,
                              help='Host name')
        add_parser.add_argument('--primary-ip', required=True,
                              help='Primary IP address with CIDR (e.g., 10.1.1.100/24)')
        add_parser.add_argument('--connect-to', required=True,
                              choices_provider=self.router_choices,
                              help='Router to connect to')
        add_parser.add_argument('--secondary-ips', nargs='*',
                              help='Secondary IP addresses')
        add_parser.add_argument('--verbose', '-v', action='store_true',
                              help='Verbose output')
        
        # List subcommand
        list_parser = subparsers.add_parser('list', help='List all hosts')
        list_parser.add_argument('--format', '-f', choices=['text', 'json'], default='text',
                               help='Output format')
        list_parser.add_argument('--verbose', '-v', action='store_true',
                               help='Verbose output')
        
        # Remove subcommand
        remove_parser = subparsers.add_parser('remove', help='Remove a host from the network')
        remove_parser.add_argument('--name', required=True,
                                 choices_provider=self.host_choices,
                                 help='Host name to remove')
        remove_parser.add_argument('--force', '-f', action='store_true',
                                 help='Force removal without confirmation')
        
        # Clean subcommand
        clean_parser = subparsers.add_parser('clean', help='Remove all hosts')
        clean_parser.add_argument('--force', '-f', action='store_true',
                                help='Force cleanup without confirmation')
        
        return parser
    
    def handle_parsed_command(self, args: argparse.Namespace) -> Optional[int]:
        """Handle parsed host command."""
        if not args.subcommand:
            self.shell.help_host()
            return None
        
        # Handle help specially
        if args.subcommand == 'help':
            self.shell.help_host()
            return None
        
        if args.subcommand == 'add':
            return self._add_host(args)
        elif args.subcommand == 'list':
            return self._list_hosts(args)
        elif args.subcommand == 'remove':
            return self._remove_host(args)
        elif args.subcommand == 'clean':
            return self._clean_hosts(args)
        else:
            self.error(f"Unknown host subcommand: {args.subcommand}")
            self.shell.help_host()
            return 1
    
    def _handle_command_impl(self, args: str) -> Optional[int]:
        """Handle host command with subcommands (legacy support)."""
        # This method is kept for backward compatibility
        parser = self.create_parser()
        try:
            parsed_args = parser.parse_args(self._split_args(args))
            return self.handle_parsed_command(parsed_args)
        except SystemExit:
            return 1
    
    
    def _add_host(self, args: argparse.Namespace) -> int:
        """Add a new host to the network."""
        self.info(f"Adding host {args.name} with IP {args.primary_ip}")
        
        # Run the host setup script
        script_path = self.get_script_path('src/simulators/host_namespace_setup.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = [
            '--host', args.name,
            '--primary-ip', args.primary_ip,
            '--connect-to', args.connect_to
        ]
        
        if args.secondary_ips:
            cmd_args.extend(['--secondary-ips'] + args.secondary_ips)
        
        if args.verbose:
            cmd_args.append('--verbose')
        
        # Run with sudo
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=True)
        
        if returncode == 0:
            self.success(f"Host {args.name} added successfully")
        else:
            self.error(f"Failed to add host {args.name}")
        
        return returncode
    
    def _list_hosts(self, args: argparse.Namespace) -> int:
        """List all hosts."""
        # Only show info message if not JSON output
        if args.format != 'json':
            self.info("Listing all hosts...")
        
        # Run the host listing script
        script_path = self.get_script_path('src/simulators/host_namespace_setup.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = ['--list']
        
        if args.format == 'json':
            cmd_args.append('--json')
        
        if args.verbose:
            cmd_args.append('--verbose')
        
        # Run with sudo
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=True)
        
        return returncode
    
    def _remove_host(self, args: argparse.Namespace) -> int:
        """Remove a host from the network."""
        # Confirmation if not forced
        if not args.force:
            try:
                response = input(f"Are you sure you want to remove host {args.name}? (y/N): ")
                if response.lower() not in ['y', 'yes']:
                    self.info("Host removal cancelled")
                    return 0
            except KeyboardInterrupt:
                self.info("\nHost removal cancelled")
                return 0
        
        self.info(f"Removing host {args.name}")
        
        # Run the host removal script
        script_path = self.get_script_path('src/simulators/host_namespace_setup.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = [
            '--host', args.name,
            '--remove'
        ]
        
        if args.verbose:
            cmd_args.append('--verbose')
        
        # Run with sudo
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=True)
        
        if returncode == 0:
            self.success(f"Host {args.name} removed successfully")
        else:
            self.error(f"Failed to remove host {args.name}")
        
        return returncode
    
    def _clean_hosts(self, args: argparse.Namespace) -> int:
        """Remove all hosts."""
        # Confirmation if not forced
        if not args.force:
            try:
                response = input("Are you sure you want to remove all hosts? (y/N): ")
                if response.lower() not in ['y', 'yes']:
                    self.info("Host cleanup cancelled")
                    return 0
            except KeyboardInterrupt:
                self.info("\nHost cleanup cancelled")
                return 0
        
        self.info("Removing all hosts...")
        
        # Run the host cleanup script
        script_path = self.get_script_path('src/simulators/host_namespace_setup.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = ['--clean-all']
        
        if args.verbose:
            cmd_args.append('--verbose')
        
        # Run with sudo
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=True)
        
        if returncode == 0:
            self.success("All hosts removed successfully")
        else:
            self.error("Failed to remove all hosts")
        
        return returncode