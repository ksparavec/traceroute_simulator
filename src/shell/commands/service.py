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
        start_parser.add_argument('--verbose', '-v', action='store_true',
                                help='Verbose output')
        
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
        test_parser.add_argument('--verbose', '-v', action='store_true',
                               help='Verbose output')
        
        # List subcommand
        list_parser = subparsers.add_parser('list', help='List all active services')
        list_parser.add_argument('--format', '-f', choices=['text', 'json'], default='text',
                               help='Output format')
        list_parser.add_argument('--verbose', '-v', action='store_true',
                               help='Verbose output')
        
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
        stop_parser.add_argument('--verbose', '-v', action='store_true',
                               help='Verbose output')
        
        # Clean subcommand
        clean_parser = subparsers.add_parser('clean', help='Stop all services')
        clean_parser.add_argument('--force', '-f', action='store_true',
                                help='Force cleanup without confirmation')
        clean_parser.add_argument('--verbose', '-v', action='store_true',
                                help='Verbose output')
        
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
    
    def handle_command(self, args: str) -> Optional[int]:
        """Handle service command with subcommands (legacy support)."""
        # This method is kept for backward compatibility
        parser = self.create_parser()
        try:
            parsed_args = parser.parse_args(self._split_args(args))
            return self.handle_parsed_command(parsed_args)
        except SystemExit:
            return 1
    
    
    def _start_service(self, args: argparse.Namespace) -> int:
        """Start a TCP/UDP service."""
        # Always show info for start operations
        self.info(f"Starting {args.protocol} service on {args.ip}:{args.port}")
        
        # Run the service manager script
        script_path = self.get_script_path('src/simulators/service_manager.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = [
            '--start',
            '--ip', args.ip,
            '--port', str(args.port),
            '--protocol', args.protocol
        ]
        
        if args.name:
            cmd_args.extend(['--name', args.name])
        
        if args.verbose:
            cmd_args.append('--verbose')
        
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
        
        if args.verbose:
            cmd_args.append('--verbose')
        
        # Run with sudo
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=True)
        
        if returncode == 0:
            self.success("Service test completed successfully")
        else:
            self.error("Service test failed")
        
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
            cmd_args.append('--json')
        
        if args.verbose:
            cmd_args.append('--verbose')
        
        # Run with sudo
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=True)
        
        return returncode
    
    def _stop_service(self, args: argparse.Namespace) -> int:
        """Stop a service."""
        self.info(f"Stopping {args.protocol} service on {args.ip}:{args.port}")
        
        # Run the service manager script
        script_path = self.get_script_path('src/simulators/service_manager.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = [
            '--stop',
            '--ip', args.ip,
            '--port', str(args.port),
            '--protocol', args.protocol
        ]
        
        if args.verbose:
            cmd_args.append('--verbose')
        
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
        cmd_args = ['--clean-all']
        
        if args.verbose:
            cmd_args.append('--verbose')
        
        # Run with sudo
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=True)
        
        if returncode == 0:
            self.success("All services stopped successfully")
        else:
            self.error("Failed to stop all services")
        
        return returncode