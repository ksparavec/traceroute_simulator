#!/usr/bin/env -S python3 -B -u
"""
Network command handler for managing network namespace simulation.
"""

import argparse
from typing import Optional

from .base import BaseCommandHandler


class NetworkCommands(BaseCommandHandler):
    """Handler for network-related commands."""
    
    def get_subcommand_names(self) -> list:
        """Get list of network subcommands."""
        return ['setup', 'setup-serial', 'status', 'clean', 'clean-serial', 'test']
    
    def _handle_command_impl(self, args: str) -> Optional[int]:
        """Handle network command with subcommands."""
        # Check for help flags first
        args_list = args.strip().split() if args.strip() else []
        if not args.strip() or '--help' in args_list or '-h' in args_list:
            self.shell.help_network()
            return 0
        
        # Parse the subcommand
        args_list = self._split_args(args)
        if not args_list:
            self.shell.help_network()
            return None
        
        subcommand = args_list[0]
        remaining_args = args_list[1:]
        
        return self._handle_subcommand(subcommand, remaining_args)
    
    def handle_context_command(self, args: str) -> Optional[int]:
        """Handle network commands in context mode."""
        if not args.strip():
            self.shell.help_network()
            return None
        
        # Check for exit commands
        if self._handle_context_exit(args):
            return None  # Signal to exit context
        
        # Parse the command (no subcommand prefix needed in context)
        args_list = self._split_args(args)
        if not args_list:
            self.shell.help_network()
            return None
        
        subcommand = args_list[0]
        remaining_args = args_list[1:]
        
        return self._handle_subcommand(subcommand, remaining_args)
    
    def _handle_subcommand(self, subcommand: str, args: list) -> Optional[int]:
        """Handle a specific subcommand."""
        # Handle help specially
        if subcommand == 'help':
            self.shell.help_network()
            return None
        
        if subcommand == 'setup':
            return self._setup_network(args)
        elif subcommand == 'setup-serial':
            return self._setup_network_serial(args)
        elif subcommand == 'status':
            return self._network_status(args)
        elif subcommand == 'clean':
            return self._clean_network(args)
        elif subcommand == 'clean-serial':
            return self._clean_network_serial(args)
        elif subcommand == 'test':
            return self._test_network(args)
        else:
            self.error(f"Unknown network subcommand: {subcommand}")
            self.shell.help_network()
            return 1
    
    def get_context_completions(self, text: str) -> list:
        """Get completions for network context."""
        subcommands = self.get_subcommand_names()
        return [cmd for cmd in subcommands if cmd.startswith(text)]
    
    def complete_command(self, text: str, line: str, begidx: int, endidx: int) -> list:
        """Provide completion for network command arguments."""
        # Parse the line to understand what we're completing
        args = line.split()
        
        # If we're typing the second word (the subcommand)
        if len(args) == 1 or (len(args) == 2 and not line.endswith(' ')):
            # Completing the subcommand
            return self.get_context_completions(text)
        elif len(args) >= 2:
            # Completing arguments for a subcommand
            subcommand = args[1]
            return self.complete_context_arguments(subcommand, text, line, begidx, endidx)
        
        return []
    
    def complete_context_arguments(self, subcommand: str, text: str, line: str, begidx: int, endidx: int) -> list:
        """Complete arguments for network subcommands in context mode."""
        # Parse the line to understand what we're completing
        parts = line.split()
        
        if len(parts) >= 2:
            # If line ends with a space, we're completing a new argument
            # Otherwise, we're completing the current partial argument
            if line.endswith(' '):
                # We're starting a new argument, check what the previous complete word was
                prev_part = parts[-1] if parts else ''
            else:
                # We're in the middle of typing, check the word before the current partial
                prev_part = parts[-2] if len(parts) > 1 else ''
            
            # Common argument completions
            if prev_part in ['--router', '-r']:
                # Complete with router names
                return self._get_router_completions(text)
            elif prev_part in ['--limit', '-l']:
                # Complete with router names from TSIM_NETWORK_ROUTERS
                return self._get_limit_completions(text)
            elif prev_part in ['--source', '-s', '--dest', '-d']:
                # Complete with IP addresses
                return self._get_ip_completions(text)
            elif prev_part in ['--protocol', '-p']:
                # Complete with protocols
                return self._get_protocol_completions(text)
            elif prev_part in ['--function', '-f']:
                # Complete with function names
                functions = ['interfaces', 'routes', 'rules', 'all', 'summary']
                return [f for f in functions if f.startswith(text)]
            elif prev_part in ['--format']:
                # Complete with output formats
                formats = ['text', 'json']
                return [f for f in formats if f.startswith(text)]
        
        # Complete with available options based on subcommand
        if subcommand == 'setup':
            options = ['--create', '--clean', '--verify', '--keep-batch-files', '--verbose', '-v']
        elif subcommand == 'setup-serial':
            options = ['--limit', '-l', '--verify', '--verbose', '-v']
        elif subcommand == 'status':
            # The function is a positional argument, not an option
            if not any(arg.startswith('--') for arg in parts[2:]):
                # Complete function names if no -- flag yet
                functions = ['interfaces', 'routes', 'rules', 'iptables', 'ipsets', 'all', 'summary']
                return [f for f in functions if f.startswith(text)]
            options = ['--limit', '-l', '--json', '-j', '--verbose', '-v']
        elif subcommand == 'clean':
            options = ['--force', '-f', '--verbose', '-v']
        elif subcommand == 'clean-serial':
            options = ['--force', '-f', '--limit', '-l', '--verbose', '-v']
        elif subcommand == 'test':
            options = ['--source', '-s', '--destination', '-d', '--all', '--test-type', '--wait', '--verbose', '-v']
        else:
            options = []
        
        return [opt for opt in options if opt.startswith(text)]
    
    def _get_router_completions(self, text: str) -> list:
        """Get router name completions."""
        if hasattr(self.shell, 'completers'):
            return self.shell.completers.router_names(text, '', 0, 0)
        return []
    
    def _get_ip_completions(self, text: str) -> list:
        """Get IP address completions."""
        if hasattr(self.shell, 'completers'):
            return self.shell.completers.ip_addresses(text, '', 0, 0)
        return []
    
    def _get_protocol_completions(self, text: str) -> list:
        """Get protocol completions."""
        if hasattr(self.shell, 'completers'):
            return self.shell.completers.protocols(text, '', 0, 0)
        return []
    
    def _get_limit_completions(self, text: str) -> list:
        """Get router name completions from TSIM_NETWORK_ROUTERS variable."""
        # Get the TSIM_NETWORK_ROUTERS variable
        router_names = self.shell.variable_manager.get_variable('TSIM_NETWORK_ROUTERS')
        if router_names and isinstance(router_names, list):
            # Support glob patterns - show all routers and let user add wildcards
            completions = [name for name in router_names if name.startswith(text)]
            # Also suggest common patterns if text includes wildcard characters
            if '*' in text or '?' in text:
                # Just return what user typed if they're using wildcards
                return [text]
            return completions
        return []
    
    def _setup_network(self, args: list) -> int:
        """Setup network namespace simulation using batch command generator."""
        parser = argparse.ArgumentParser(prog='network setup',
                                       description='Setup network namespace simulation (batch mode)')
        parser.add_argument('--create', action='store_true',
                          help='Create the network setup')
        parser.add_argument('--clean', action='store_true',
                          help='Clean existing setup before creating')
        parser.add_argument('--verify', action='store_true',
                          help='Verify network setup')
        parser.add_argument('--keep-batch-files', action='store_true',
                          help='Keep batch files for debugging')
        parser.add_argument('--verbose', '-v', action='count', default=0,
                          help='Increase verbosity (-v, -vv, -vvv)')
        
        try:
            parsed_args = parser.parse_args(args)
        except SystemExit:
            return 1
        
        # If no action specified, show help
        if not parsed_args.create and not parsed_args.clean and not parsed_args.verify:
            parser.print_help()
            return 1
        
        # Check if facts directory exists
        if not self.check_facts_directory():
            return 1
        
        # Build description of what we're doing
        actions = []
        if parsed_args.clean:
            actions.append("clean")
        if parsed_args.create:
            actions.append("create")
        if parsed_args.verify:
            actions.append("verify")
        
        self.info(f"Network namespace operation: {', '.join(actions)}")
        
        # Run the batch command generator script
        script_path = self.get_script_path('src/simulators/batch_command_generator.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments based on what user wants
        cmd_args = []
        
        if parsed_args.clean:
            cmd_args.append('--clean')
        
        if parsed_args.create:
            cmd_args.append('--create')
        
        if parsed_args.verify:
            cmd_args.append('--verify')
        
        if parsed_args.keep_batch_files:
            cmd_args.append('--keep-batch-files')
        
        if parsed_args.verbose:
            cmd_args.append('-' + 'v' * parsed_args.verbose)
        
        # Run script (sudo will be added by script for specific commands)
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=False)
        
        if returncode == 0:
            self.success("Network operation completed successfully")
            if parsed_args.create:
                self.info("Use 'network status' to check the setup")
        else:
            self.error("Network operation failed")
        
        return returncode
    
    def _network_status(self, args: list) -> int:
        """Show network namespace status."""
        parser = argparse.ArgumentParser(prog='network status',
                                       description='Show network namespace status')
        parser.add_argument('--limit', '-l',
                          help='Limit to specific namespaces (supports glob patterns)')
        parser.add_argument('function', nargs='?',
                          choices=['interfaces', 'routes', 'rules', 'iptables', 'ipsets', 'all', 'summary'],
                          default='summary',
                          help='Information to display')
        parser.add_argument('--json', '-j', action='store_true',
                          help='Output in JSON format')
        parser.add_argument('--verbose', '-v', action='count', default=0,
                          help='Increase verbosity (-v, -vv, -vvv)')
        
        try:
            parsed_args = parser.parse_args(args)
        except SystemExit:
            return 1
        
        # Store current args for JSON output detection
        self.current_args = parsed_args
        
        # Only show info message if not using JSON output
        if not parsed_args.json:
            self.info("Checking network namespace status...")
        
        # Run the network status script
        script_path = self.get_script_path('src/simulators/network_namespace_status.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments - the script expects function as positional argument
        cmd_args = [parsed_args.function]
        
        if parsed_args.limit:
            cmd_args.extend(['--limit', parsed_args.limit])
        
        if parsed_args.json:
            cmd_args.append('--json')
        
        if parsed_args.verbose:
            cmd_args.append('-' + 'v' * parsed_args.verbose)
        
        # Run script (sudo will be added by script for specific commands)
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=False)
        
        return returncode
    
    def _clean_network(self, args: list) -> int:
        """Clean up network namespaces using batch command generator."""
        parser = argparse.ArgumentParser(prog='network clean',
                                       description='Clean up network namespaces (batch mode)')
        parser.add_argument('--force', '-f', action='store_true',
                          help='Skip confirmation prompt')
        parser.add_argument('--verbose', '-v', action='count', default=0,
                          help='Increase verbosity (-v, -vv, -vvv)')
        
        try:
            parsed_args = parser.parse_args(args)
        except SystemExit:
            return 1
        
        # Confirmation (unless --force is used)
        if not parsed_args.force:
            try:
                response = input("Are you sure you want to clean up all network namespaces? (y/N): ")
                if response.lower() not in ['y', 'yes']:
                    self.info("Cleanup cancelled")
                    return 0
            except KeyboardInterrupt:
                self.info("\nCleanup cancelled")
                return 0
        
        self.info("Cleaning up network namespaces (batch mode)...")
        
        # Run the batch command generator script with --clean
        script_path = self.get_script_path('src/simulators/batch_command_generator.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments for cleanup
        cmd_args = ['--clean']
        
        if parsed_args.verbose:
            cmd_args.append('-' + 'v' * parsed_args.verbose)
        
        # Run script (sudo will be added by script for specific commands)
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=False)
        
        if returncode == 0:
            self.success("Network cleanup completed successfully")
        else:
            self.error("Network cleanup failed")
        
        return returncode
    
    def _test_network(self, args: list) -> int:
        """Test network connectivity."""
        parser = argparse.ArgumentParser(prog='network test',
                                       description='Test network connectivity')
        parser.add_argument('--source', '-s',
                          help='Source IP address')
        parser.add_argument('--destination', '-d',
                          help='Destination IP address')
        parser.add_argument('--all', action='store_true',
                          help='Test all routers sequentially (comprehensive)')
        parser.add_argument('--test-type', 
                          choices=['ping', 'mtr', 'both'], default='ping',
                          help='Test type: ping (default), mtr, or both')
        parser.add_argument('--wait', type=float, default=0.1,
                          help='Wait time between tests in seconds')
        parser.add_argument('--verbose', '-v', action='count', default=0,
                          help='Increase verbosity (-v, -vv)')
        
        try:
            parsed_args = parser.parse_args(args)
        except SystemExit:
            return 1
        
        # Validate arguments
        if not parsed_args.all and (not parsed_args.source or not parsed_args.destination):
            self.error("Either --all or both --source and --destination must be specified")
            return 1
        
        if parsed_args.all:
            self.info("Testing all routers sequentially...")
        else:
            self.info(f"Testing connectivity from {parsed_args.source} to {parsed_args.destination}")
        
        # Run the network tester script
        script_path = self.get_script_path('src/simulators/network_namespace_tester.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = []
        
        if parsed_args.all:
            cmd_args.append('--all')
        else:
            cmd_args.extend(['--source', parsed_args.source])
            cmd_args.extend(['--destination', parsed_args.destination])
        
        cmd_args.extend(['--test-type', parsed_args.test_type])
        
        if parsed_args.wait != 0.1:
            cmd_args.extend(['--wait', str(parsed_args.wait)])
        
        if parsed_args.verbose:
            cmd_args.append('-' + 'v' * parsed_args.verbose)
        
        # Run script (sudo will be added by script for specific commands)
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=False)
        
        if returncode == 0:
            self.success("Network test completed successfully")
        else:
            self.error("Network test failed")
        
        return returncode
    
    def _setup_network_serial(self, args: list) -> int:
        """Setup network namespace simulation using serial (old) method."""
        parser = argparse.ArgumentParser(prog='network setup-serial',
                                       description='Setup network namespace simulation (serial/sequential mode)')
        parser.add_argument('--limit', '-l',
                          help='Limit routers to create (supports glob patterns)')
        parser.add_argument('--verify', action='store_true',
                          help='Verify setup after creation')
        parser.add_argument('--verbose', '-v', action='count', default=0,
                          help='Increase verbosity (-v, -vv, -vvv)')
        
        try:
            parsed_args = parser.parse_args(args)
        except SystemExit:
            return 1
        
        # Check if facts directory exists
        if not self.check_facts_directory():
            return 1
        
        
        self.info("Setting up network namespace simulation (serial mode)...")
        
        # Run the old network setup script
        script_path = self.get_script_path('src/simulators/network_namespace_setup.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = []
        
        if parsed_args.limit:
            cmd_args.extend(['--limit', parsed_args.limit])
        
        if parsed_args.verify:
            cmd_args.append('--verify')
        
        if parsed_args.verbose:
            cmd_args.append('-' + 'v' * parsed_args.verbose)
        
        # Run script (sudo will be added by script for specific commands)
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=False)
        
        if returncode == 0:
            self.success("Network namespace setup completed successfully")
            self.info("Use 'network status' to check the setup")
        else:
            self.error("Network setup failed")
        
        return returncode
    
    def _clean_network_serial(self, args: list) -> int:
        """Clean up network namespaces using serial (old) method."""
        parser = argparse.ArgumentParser(prog='network clean-serial',
                                       description='Clean up network namespaces (serial/sequential mode)')
        parser.add_argument('--force', '-f', action='store_true',
                          help='Skip confirmation prompt and force removal of stuck resources')
        parser.add_argument('--limit', '-l',
                          help='Limit cleanup to specific routers (supports glob patterns)')
        parser.add_argument('--verbose', '-v', action='count', default=0,
                          help='Increase verbosity (-v, -vv, -vvv)')
        
        try:
            parsed_args = parser.parse_args(args)
        except SystemExit:
            return 1
        
        # Confirmation (unless --force is used)
        if not parsed_args.force:
            try:
                response = input("Are you sure you want to clean up all network namespaces? (y/N): ")
                if response.lower() not in ['y', 'yes']:
                    self.info("Cleanup cancelled")
                    return 0
            except KeyboardInterrupt:
                self.info("\nCleanup cancelled")
                return 0
        
        self.info("Cleaning up network namespaces (serial mode)...")
        
        # Run the old network cleanup script
        script_path = self.get_script_path('src/simulators/network_namespace_cleanup.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments for cleanup
        cmd_args = []
        
        if parsed_args.force:
            cmd_args.append('--force')
        
        if parsed_args.limit:
            cmd_args.extend(['--limit', parsed_args.limit])
        
        if parsed_args.verbose:
            cmd_args.append('-' + 'v' * parsed_args.verbose)
        
        # Run script (sudo will be added by script for specific commands)
        returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=False)
        
        if returncode == 0:
            self.success("Network cleanup completed successfully")
        else:
            self.error("Network cleanup failed")
        
        return returncode