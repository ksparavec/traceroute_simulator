#!/usr/bin/env -S python3 -B -u
"""
Network test command handlers for ping and mtr operations.
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


class NetTestCommands(BaseCommandHandler):
    """Handler for network test commands (ping and mtr)."""
    
    @choices_provider
    def ip_choices(self) -> List[str]:
        """Provide IP address choices for completion."""
        if hasattr(self.shell, 'completers'):
            return self.shell.completers._get_all_ips()
        return []
    
    def create_ping_parser(self) -> Cmd2ArgumentParser:
        """Create the argument parser for ping command."""
        parser = Cmd2ArgumentParser(
            prog='ping',
            description='Test connectivity between IPs using ping'
        )
        
        parser.add_argument('-s', '--source', required=True,
                          choices_provider=self.ip_choices,
                          help='Source IP address')
        parser.add_argument('-d', '--destination', required=True,
                          choices_provider=self.ip_choices,
                          help='Destination IP address')
        parser.add_argument('-v', '--verbose', action='count', default=1,
                          help='Increase verbosity (default: show ping output)')
        
        return parser
    
    def create_mtr_parser(self) -> Cmd2ArgumentParser:
        """Create the argument parser for mtr command."""
        parser = Cmd2ArgumentParser(
            prog='mtr',
            description='Test connectivity between IPs using MTR (My TraceRoute)'
        )
        
        parser.add_argument('-s', '--source', required=True,
                          choices_provider=self.ip_choices,
                          help='Source IP address')
        parser.add_argument('-d', '--destination', required=True,
                          choices_provider=self.ip_choices,
                          help='Destination IP address')
        parser.add_argument('-v', '--verbose', action='count', default=1,
                          help='Increase verbosity (default: show MTR output)')
        
        return parser
    
    def handle_ping_command(self, args: str) -> Optional[int]:
        """Handle ping command."""
        # Check for help flags first
        args_list = args.strip().split() if args.strip() else []
        if not args or args.strip() == '' or '--help' in args_list or '-h' in args_list:
            self.shell.help_ping()
            return 0
            
        parser = self.create_ping_parser()
        try:
            parsed_args = parser.parse_args(self._split_args(args))
            return self._run_nettest(parsed_args, 'ping')
        except SystemExit:
            # Parser error (e.g., missing required args) - show help instead
            self.shell.help_ping()
            return 1
        except Exception as e:
            self.error(f"Error running ping: {e}")
            return 1
    
    def handle_mtr_command(self, args: str) -> Optional[int]:
        """Handle mtr command."""
        # Check for help flags first
        args_list = args.strip().split() if args.strip() else []
        if not args or args.strip() == '' or '--help' in args_list or '-h' in args_list:
            self.shell.help_mtr()
            return 0
            
        parser = self.create_mtr_parser()
        try:
            parsed_args = parser.parse_args(self._split_args(args))
            return self._run_nettest(parsed_args, 'mtr')
        except SystemExit:
            # Parser error (e.g., missing required args) - show help instead
            self.shell.help_mtr()
            return 1
        except Exception as e:
            self.error(f"Error running mtr: {e}")
            return 1
    
    def _run_nettest(self, args: argparse.Namespace, test_type: str) -> int:
        """Run network test with specified type."""
        try:
            self.info(f"Testing connectivity from {args.source} to {args.destination} using {test_type.upper()}")
            
            # Run the network namespace tester script
            script_path = self.get_script_path('src/simulators/network_namespace_tester.py')
            if not self.check_script_exists(script_path):
                return 1
            
            # Build command arguments
            cmd_args = [
                '-s', args.source,
                '-d', args.destination,
                '--test-type', test_type
            ]
            
            # Add verbose flags (default is 1, so only add if > 1)
            if args.verbose > 1:
                for _ in range(args.verbose - 1):
                    cmd_args.append('-v')
            
            # Run with sudo since we need namespace access
            returncode = self.run_script_with_output(script_path, cmd_args, use_sudo=True)
            
            return returncode
            
        except Exception as e:
            self.error(f"Failed to run {test_type}: {e}")
            return 1
    
    def complete_ping_command(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Provide completion for ping command."""
        # Parse the line to understand what we're completing
        args = line.split()
        
        # Get all available IPs for completion
        ip_choices = self.ip_choices()
        
        # Debug output at -vvv level
        if hasattr(self.shell, 'verbose') and self.shell.verbose >= 3:
            print(f"[DEBUG] Args: {args}, IP choices count: {len(ip_choices)}")
        
        # Check if we're completing a value for -s or -d
        if len(args) >= 2:
            if args[-1] in ['-s', '--source']:
                return [ip for ip in ip_choices if ip.startswith(text)]
            elif args[-1] in ['-d', '--destination']:
                return [ip for ip in ip_choices if ip.startswith(text)]
            elif args[-2] in ['-s', '--source', '-d', '--destination'] and text:
                # Partial IP typed
                return [ip for ip in ip_choices if ip.startswith(text)]
        
        # Provide argument names that haven't been used yet
        used_args = set(args)
        available_args = []
        
        # Check which required arguments are missing
        has_source = any(arg in used_args for arg in ['-s', '--source'])
        has_dest = any(arg in used_args for arg in ['-d', '--destination'])
        
        if not has_source:
            available_args.extend(['-s', '--source'])
        if not has_dest:
            available_args.extend(['-d', '--destination'])
        
        # Optional arguments
        if '-v' not in used_args and '--verbose' not in used_args:
            available_args.extend(['-v', '--verbose'])
        
        # Debug output at -vvv level
        if hasattr(self.shell, 'verbose') and self.shell.verbose >= 3:
            print(f"[DEBUG] Returning completions: {[arg for arg in available_args if arg.startswith(text)]}")
        
        return [arg for arg in available_args if arg.startswith(text)]
    
    def complete_mtr_command(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Provide completion for mtr command."""
        # Debug output at -vvv level
        if hasattr(self.shell, 'verbose') and self.shell.verbose >= 3:
            print(f"[DEBUG] complete_mtr_command called: text='{text}', line='{line}'")
        
        # Parse the line to understand what we're completing
        args = line.split()
        
        # Get all available IPs for completion
        ip_choices = self.ip_choices()
        
        # Debug output at -vvv level
        if hasattr(self.shell, 'verbose') and self.shell.verbose >= 3:
            print(f"[DEBUG] Args: {args}, IP choices count: {len(ip_choices)}")
        
        # Check if we're completing a value for -s or -d
        if len(args) >= 2:
            if args[-1] in ['-s', '--source']:
                return [ip for ip in ip_choices if ip.startswith(text)]
            elif args[-1] in ['-d', '--destination']:
                return [ip for ip in ip_choices if ip.startswith(text)]
            elif args[-2] in ['-s', '--source', '-d', '--destination'] and text:
                # Partial IP typed
                return [ip for ip in ip_choices if ip.startswith(text)]
        
        # Provide argument names that haven't been used yet
        used_args = set(args)
        available_args = []
        
        # Check which required arguments are missing
        has_source = any(arg in used_args for arg in ['-s', '--source'])
        has_dest = any(arg in used_args for arg in ['-d', '--destination'])
        
        if not has_source:
            available_args.extend(['-s', '--source'])
        if not has_dest:
            available_args.extend(['-d', '--destination'])
        
        # Optional arguments
        if '-v' not in used_args and '--verbose' not in used_args:
            available_args.extend(['-v', '--verbose'])
        
        # Debug output at -vvv level
        if hasattr(self.shell, 'verbose') and self.shell.verbose >= 3:
            print(f"[DEBUG] Returning completions: {[arg for arg in available_args if arg.startswith(text)]}")
        
        return [arg for arg in available_args if arg.startswith(text)]
    
    def _handle_command_impl(self, args: str) -> Optional[int]:
        """Handle command - not used for ping/mtr as they have their own handlers."""
        # This method is required by BaseCommandHandler but not used
        # since ping and mtr have their own specific handlers
        return None