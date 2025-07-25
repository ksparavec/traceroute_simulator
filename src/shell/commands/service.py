#!/usr/bin/env -S python3 -B -u
"""
Service command handler for managing TCP/UDP services in network simulation.
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


class ServiceCommands(BaseCommandHandler):
    """Handler for service management commands."""
    
    def get_subcommand_names(self) -> List[str]:
        """Get list of service subcommands."""
        return ['start', 'test', 'list', 'stop', 'clean']
    
    @choices_provider
    def ip_choices(self) -> List[str]:
        """Provide IP address choices for completion."""
        if hasattr(self.shell, 'completers'):
            return self.shell.completers._get_all_ips()
        return []
    
    @choices_provider
    def port_choices(self) -> List[str]:
        """Provide port choices for completion."""
        return ['22', '80', '443', '53', '8080', '8443', '3306', '5432']
    
    def create_parser(self) -> Cmd2ArgumentParser:
        """Create the argument parser for service commands."""
        parser = Cmd2ArgumentParser(prog='service', description='Manage TCP/UDP services in network simulation')
        subparsers = parser.add_subparsers(dest='subcommand', help='Service subcommands')
        
        # Start subcommand
        start_parser = subparsers.add_parser('start', help='Start a TCP/UDP service')
        start_parser.add_argument('--ip', required=True,
                                choices_provider=self.ip_choices,
                                help='IP address to bind to')
        start_parser.add_argument('--port', type=int, required=True,
                                choices_provider=self.port_choices,
                                help='Port number')
        start_parser.add_argument('--protocol', '-p', choices=['tcp', 'udp'], default='tcp',
                                help='Protocol (default: tcp)')
        start_parser.add_argument('--name', help='Service name')
        start_parser.add_argument('--verbose', '-v', action='count', default=0,
                                help='Increase verbosity (-v, -vv)')
        
        # Test subcommand
        test_parser = subparsers.add_parser('test', help='Test service connectivity')
        test_parser.add_argument('--source', '-s', required=True,
                               choices_provider=self.ip_choices,
                               help='Source IP address')
        test_parser.add_argument('--dest', '-d', required=True,
                               help='Destination IP:PORT')
        test_parser.add_argument('--protocol', '-p', choices=['tcp', 'udp'], default='tcp',
                               help='Protocol (default: tcp)')
        test_parser.add_argument('--message', '-m',
                               help='Message to send (for UDP)')
        test_parser.add_argument('--timeout', type=int, default=5,
                               help='Connection timeout in seconds')
        test_parser.add_argument('--verbose', '-v', action='count', default=0,
                               help='Increase verbosity (-v, -vv)')
        test_parser.add_argument('--json', '-j', action='store_true',
                               help='Output in JSON format')
        
        # List subcommand
        list_parser = subparsers.add_parser('list', help='List all active services')
        list_parser.add_argument('--format', '-f', choices=['text', 'json'], default='text',
                               help='Output format')
        list_parser.add_argument('--verbose', '-v', action='count', default=0,
                               help='Increase verbosity (-v, -vv)')
        
        # Stop subcommand
        stop_parser = subparsers.add_parser('stop', help='Stop a service')
        stop_parser.add_argument('--ip', required=True,
                               choices_provider=self.ip_choices,
                               help='IP address')
        stop_parser.add_argument('--port', type=int, required=True,
                               choices_provider=self.port_choices,
                               help='Port number')
        stop_parser.add_argument('--protocol', '-p', choices=['tcp', 'udp'], default='tcp',
                               help='Protocol (default: tcp)')
        stop_parser.add_argument('--verbose', '-v', action='count', default=0,
                               help='Increase verbosity (-v, -vv)')
        
        # Clean subcommand
        clean_parser = subparsers.add_parser('clean', help='Stop all services')
        clean_parser.add_argument('--force', '-f', action='store_true',
                                help='Force cleanup without confirmation')
        clean_parser.add_argument('--verbose', '-v', action='count', default=0,
                                help='Increase verbosity (-v, -vv)')
        
        return parser
    
    def handle_parsed_command(self, args: argparse.Namespace) -> Optional[int]:
        """Handle parsed service command."""
        if not args.subcommand:
            self.shell.help_service()
            return None
        
        # Handle help specially
        if args.subcommand == 'help':
            self.shell.help_service()
            return None
        
        if args.subcommand == 'start':
            return self._start_service(args)
        elif args.subcommand == 'test':
            return self._test_service(args)
        elif args.subcommand == 'list':
            return self._list_services(args)
        elif args.subcommand == 'stop':
            return self._stop_service(args)
        elif args.subcommand == 'clean':
            return self._clean_services(args)
        else:
            self.error(f"Unknown service subcommand: {args.subcommand}")
            self.shell.help_service()
            return 1
    
    def _handle_command_impl(self, args: str) -> Optional[int]:
        """Handle service command with subcommands (legacy support)."""
        # Check for help flags first
        args_list = args.strip().split() if args.strip() else []
        if not args.strip() or '--help' in args_list or '-h' in args_list:
            self.shell.help_service()
            return 0
            
        # This method is kept for backward compatibility
        parser = self.create_parser()
        try:
            parsed_args = parser.parse_args(self._split_args(args))
            return self.handle_parsed_command(parsed_args)
        except SystemExit:
            # Show help on parser error
            self.shell.help_service()
            return 1
    
    
    def _start_service(self, args: argparse.Namespace) -> int:
        """Start a TCP/UDP service."""
        # Always show info for start operations
        self.info(f"Starting {args.protocol} service on {args.ip}:{args.port}")
        
        # Run the service tester script (which handles IP-based operations)
        script_path = self.get_script_path('src/simulators/service_tester.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = [
            '--start', f'{args.ip}:{args.port}',
            '-p', args.protocol
        ]
        
        if args.name:
            cmd_args.extend(['--name', args.name])
        
        # Pass verbose count
        for _ in range(args.verbose):
            cmd_args.append('-v')
        
        # Run with sudo
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=True)
        
        if returncode == 0:
            self.success(f"Service started on {args.ip}:{args.port}")
        else:
            self.error("Failed to start service")
        
        return returncode
    
    def _test_service(self, args: argparse.Namespace) -> int:
        """Test service connectivity."""
        self.info(f"Testing {args.protocol} connectivity from {args.source} to {args.dest}")
        
        # Run the service tester script
        script_path = self.get_script_path('src/simulators/service_tester.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = [
            '--source', args.source,
            '--dest', args.dest,
            '--protocol', args.protocol,
            '--timeout', str(args.timeout)
        ]
        
        if args.message:
            cmd_args.extend(['--message', args.message])
        
        # Pass verbose count
        for _ in range(args.verbose):
            cmd_args.append('-v')
            
        # Pass JSON flag if requested
        if hasattr(args, 'json') and args.json:
            cmd_args.append('-j')
        
        # Run with sudo
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=True)
        
        # Don't print success/error messages here - service_tester.py handles all output
        
        return returncode
    
    def _list_services(self, args: argparse.Namespace) -> int:
        """List all active services."""
        
        # Only show info message if not JSON output
        if args.format != 'json':
            self.info("Listing all active services...")
        
        # Run the service manager script
        script_path = self.get_script_path('src/simulators/service_manager.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = ['status']
        
        if args.format == 'json':
            cmd_args.append('-j')
        
        # Pass verbose count
        for _ in range(args.verbose):
            cmd_args.append('-v')
        
        # Run with sudo
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=True)
        
        return returncode
    
    def _stop_service(self, args: argparse.Namespace) -> int:
        """Stop a service."""
        self.info(f"Stopping {args.protocol} service on {args.ip}:{args.port}")
        
        # Run the service tester script (which handles IP-based operations)
        script_path = self.get_script_path('src/simulators/service_tester.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = [
            '--stop', f'{args.ip}:{args.port}'
        ]
        
        # Pass verbose count
        for _ in range(args.verbose):
            cmd_args.append('-v')
        
        # Run with sudo
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=True)
        
        if returncode == 0:
            self.success(f"Service stopped on {args.ip}:{args.port}")
        else:
            self.error("Failed to stop service")
        
        return returncode
    
    def _clean_services(self, args: argparse.Namespace) -> int:
        """Stop all services."""
        # Confirmation if not forced
        if not args.force:
            try:
                response = input("Are you sure you want to stop all services? (y/N): ")
                if response.lower() not in ['y', 'yes']:
                    self.info("Service cleanup cancelled")
                    return 0
            except KeyboardInterrupt:
                self.info("\nService cleanup cancelled")
                return 0
        
        self.info("Stopping all services...")
        
        # Run the service manager script
        script_path = self.get_script_path('src/simulators/service_manager.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = ['cleanup']
        
        # Pass verbose count
        for _ in range(args.verbose):
            cmd_args.append('-v')
        
        # Run with sudo
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=True)
        
        if returncode == 0:
            self.success("All services stopped successfully")
        else:
            self.error("Failed to stop all services")
        
        return returncode
    
    def complete_command(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Provide completion for service command arguments."""
        # Parse the line to understand what we're completing
        args = line.split()
        
        # If we're typing the second word (the subcommand)
        if len(args) == 1 or (len(args) == 2 and not line.endswith(' ')):
            subcommands = self.get_subcommand_names()
            if len(args) == 1:
                # Just "service" typed, return all subcommands
                return subcommands
            else:
                # "service <partial>", return matching subcommands
                return [cmd for cmd in subcommands if cmd.startswith(args[1])]
        
        # We have a subcommand, now handle argument completion
        subcommand = args[1]
        
        # For specific subcommands, provide appropriate completions
        if subcommand == 'start':
            # Provide argument names that haven't been used yet
            used_args = set(args)
            available_args = ['--ip', '--port', '--protocol', '--name', '--verbose']
            
            # Check if we're completing a value for a specific argument
            if len(args) >= 2 and args[-2] == '--ip':
                return self.ip_choices()
            elif len(args) >= 2 and args[-2] == '--port':
                return self.port_choices()
            elif len(args) >= 2 and args[-2] == '--protocol':
                return ['tcp', 'udp']
            
            return [arg for arg in available_args if arg not in used_args and arg.startswith(text)]
        
        elif subcommand == 'test':
            used_args = set(args)
            available_args = ['--src', '--dest', '--protocol', '--message', '--timeout', '--verbose']
            
            # Check if we're completing IP addresses
            if len(args) >= 2 and args[-2] in ['--src', '--dest']:
                return self.ip_choices()
            elif len(args) >= 2 and args[-2] == '--protocol':
                return ['tcp', 'udp']
            
            return [arg for arg in available_args if arg not in used_args and arg.startswith(text)]
        
        elif subcommand == 'stop':
            used_args = set(args)
            available_args = ['--ip', '--port', '--protocol', '--verbose']
            
            # Check if we're completing values
            if len(args) >= 2 and args[-2] == '--ip':
                return self.ip_choices()
            elif len(args) >= 2 and args[-2] == '--port':
                return self.port_choices()
            elif len(args) >= 2 and args[-2] == '--protocol':
                return ['tcp', 'udp']
            
            return [arg for arg in available_args if arg not in used_args and arg.startswith(text)]
        
        elif subcommand == 'list':
            used_args = set(args)
            available_args = ['--format', '--verbose']
            
            if len(args) >= 2 and args[-2] == '--format':
                return ['text', 'json']
            
            return [arg for arg in available_args if arg not in used_args and arg.startswith(text)]
        
        elif subcommand == 'clean':
            used_args = set(args)
            available_args = ['--force', '--verbose']
            return [arg for arg in available_args if arg not in used_args and arg.startswith(text)]
        
        return []