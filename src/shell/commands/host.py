#!/usr/bin/env -S python3 -B -u
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
    
    def get_subcommand_names(self) -> List[str]:
        """Get list of host subcommands."""
        return ['add', 'list', 'remove', 'clean']
    
    @choices_provider
    def router_choices(self) -> List[str]:
        """Provide router name choices for completion."""
        if hasattr(self.shell, 'completers'):
            return self.shell.completers._get_router_names()
        return []
    
    @choices_provider
    def host_choices(self) -> List[str]:
        """Provide existing host names for completion."""
        import subprocess
        try:
            # Get list of network namespaces and filter for host namespaces
            result = subprocess.run(['ip', 'netns', 'list'], 
                                  capture_output=True, text=True, check=False)
            if result.returncode == 0:
                # Host namespaces typically have a specific prefix or pattern
                # Filter out router namespaces and system namespaces
                hosts = []
                for line in result.stdout.strip().split('\n'):
                    if line:
                        ns_name = line.split()[0]
                        # Assuming host namespaces don't match router patterns
                        # and don't start with 'cni-' or 'ts-hidden'
                        if (not ns_name.startswith('cni-') and 
                            not ns_name.startswith('ts-hidden') and
                            ns_name not in self.router_choices()):
                            hosts.append(ns_name)
                return hosts
        except Exception:
            pass
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
        add_parser.add_argument('--no-delay', action='store_true',
                              help='Skip stabilization delays for faster host creation')
        add_parser.add_argument('-v', '--verbose', action='count', default=0,
                              help='Increase verbosity (-v for info, -vv for debug, -vvv for trace)')
        
        # List subcommand
        list_parser = subparsers.add_parser('list', help='List all hosts')
        list_parser.add_argument('-j', '--json', action='store_true',
                               help='Output in JSON format')
        list_parser.add_argument('-v', '--verbose', action='count', default=0,
                               help='Increase verbosity (-v for info, -vv for debug, -vvv for trace)')
        
        # Remove subcommand
        remove_parser = subparsers.add_parser('remove', help='Remove a host from the network')
        remove_parser.add_argument('--name', required=True,
                                 choices_provider=self.host_choices,
                                 help='Host name to remove')
        remove_parser.add_argument('-f', '--force', action='store_true',
                                 help='Force removal without confirmation')
        remove_parser.add_argument('-v', '--verbose', action='count', default=0,
                                 help='Increase verbosity (-v for info, -vv for debug, -vvv for trace)')
        
        # Clean subcommand
        clean_parser = subparsers.add_parser('clean', help='Remove all hosts')
        clean_parser.add_argument('-f', '--force', action='store_true',
                                help='Force cleanup without confirmation')
        clean_parser.add_argument('-v', '--verbose', action='count', default=0,
                                help='Increase verbosity (-v for info, -vv for debug, -vvv for trace)')
        
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
        """Handle host command with subcommands."""
        # Check for help flags first
        args_list = args.strip().split() if args.strip() else []
        if not args.strip() or '--help' in args_list or '-h' in args_list:
            self.shell.help_host()
            return 0
            
        # This method is kept for backward compatibility
        parser = self.create_parser()
        try:
            parsed_args = parser.parse_args(self._split_args(args))
            return self.handle_parsed_command(parsed_args)
        except SystemExit:
            # Show help on parser error
            self.shell.help_host()
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
        
        if args.no_delay:
            cmd_args.append('--no-delay')
        
        # Add verbose flags based on count
        for _ in range(args.verbose):
            cmd_args.append('-v')
        
        # Run script (sudo will be added by script for specific commands)
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=False)
        
        if returncode == 0:
            self.success(f"Host {args.name} added successfully")
        else:
            self.error(f"Failed to add host {args.name}")
        
        return returncode
    
    def _list_hosts(self, args: argparse.Namespace) -> int:
        """List all hosts."""
        # Store current args for JSON output detection
        self.current_args = args
        
        # Only show info message if not JSON output
        if not args.json:
            self.info("Listing all hosts...")
        
        # Run the host listing script
        script_path = self.get_script_path('src/simulators/host_namespace_setup.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = ['--list']
        
        if args.json:
            cmd_args.append('--json')
        
        # Add verbose flags based on count
        for _ in range(args.verbose):
            cmd_args.append('-v')
        
        # Run script (sudo will be added by script for specific commands)
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=False)
        
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
        
        # Add verbose flags based on count
        for _ in range(args.verbose):
            cmd_args.append('-v')
        
        # Run script (sudo will be added by script for specific commands)
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=False)
        
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
        script_path = self.get_script_path('src/utils/host_cleanup.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments - host_cleanup.py doesn't need any arguments
        cmd_args = []
        
        # Add verbose flags based on count
        if hasattr(args, 'verbose'):
            for _ in range(args.verbose):
                cmd_args.append('-v')
        
        # Run script (sudo will be added by script for specific commands)
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=False)
        
        if returncode == 0:
            self.success("All hosts removed successfully")
        else:
            self.error("Failed to remove all hosts")
        
        return returncode
    
    def complete_command(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Provide completion for host command arguments."""
        # Parse the line to understand what we're completing
        args = line.split()
        
        # If we're typing the second word (the subcommand)
        if len(args) == 1 or (len(args) == 2 and not line.endswith(' ')):
            subcommands = self.get_subcommand_names()
            if len(args) == 1:
                # Just "host" typed, return all subcommands
                return subcommands
            else:
                # "host <partial>", return matching subcommands
                return [cmd for cmd in subcommands if cmd.startswith(args[1])]
        
        # We have a subcommand, now handle argument completion
        subcommand = args[1]
        
        # For specific subcommands, provide appropriate completions
        if subcommand == 'add':
            # Check what argument we're completing
            if '--connect-to' in args:
                # If we're after --connect-to, provide router names
                if args[-1] == '--connect-to':
                    return self.router_choices()
                elif args[-2] == '--connect-to' and text:
                    # Partial router name typed
                    return [r for r in self.router_choices() if r.startswith(text)]
            
            # Provide argument names that haven't been used yet
            used_args = set(args)
            available_args = ['--name', '--primary-ip', '--connect-to', '--secondary-ips', '--no-delay', '-v', '--verbose']
            return [arg for arg in available_args if arg not in used_args and arg.startswith(text)]
        
        elif subcommand == 'remove':
            # Check if we're completing --name
            if '--name' in args:
                if args[-1] == '--name':
                    return self.host_choices()
                elif args[-2] == '--name' and text:
                    return [h for h in self.host_choices() if h.startswith(text)]
            
            # Provide argument names
            used_args = set(args)
            available_args = ['--name', '-f', '--force', '-v', '--verbose']
            return [arg for arg in available_args if arg not in used_args and arg.startswith(text)]
        
        elif subcommand in ['list', 'clean']:
            # These subcommands have simpler arguments
            used_args = set(args)
            if subcommand == 'list':
                available_args = ['-j', '--json', '-v', '--verbose']
            else:  # clean
                available_args = ['-f', '--force', '-v', '--verbose']
            return [arg for arg in available_args if arg not in used_args and arg.startswith(text)]
        
        return []