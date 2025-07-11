"""
MTR command handler for traceroute simulation and analysis.
"""

import argparse
import os
from typing import Optional

from .base import BaseCommandHandler


class MTRCommands(BaseCommandHandler):
    """Handler for MTR (traceroute) commands."""
    
    def handle_command(self, args: str) -> Optional[int]:
        """Handle mtr command with subcommands."""
        if not args.strip():
            self.shell.help_mtr()
            return None
        
        # Parse the subcommand
        args_list = self._split_args(args)
        if not args_list:
            self.shell.help_mtr()
            return None
        
        subcommand = args_list[0]
        remaining_args = args_list[1:]
        
        # Handle help specially
        if subcommand == 'help':
            self.shell.help_mtr()
            return None
        
        if subcommand == 'route':
            return self._mtr_route(remaining_args)
        elif subcommand == 'analyze':
            return self._analyze_forward(remaining_args)
        elif subcommand == 'real':
            return self._real_mtr(remaining_args)
        elif subcommand == 'reverse':
            return self._reverse_trace(remaining_args)
        else:
            self.error(f"Unknown mtr subcommand: {subcommand}")
            self.shell.help_mtr()
            return 1
    
    def complete_command(self, text: str, line: str, begidx: int, endidx: int) -> list:
        """Provide completion for mtr command arguments."""
        # Parse the line to understand what we're completing
        args = line.split()
        
        # If we're typing the second word (the subcommand)
        if len(args) == 1 or (len(args) == 2 and not line.endswith(' ')):
            # Completing the subcommand
            subcommands = ['route', 'analyze', 'real', 'reverse']
            return [cmd for cmd in subcommands if cmd.startswith(text)]
        elif len(args) >= 2:
            # Completing arguments for a subcommand
            subcommand = args[1]
            
            # Handle previous argument completion
            if len(args) >= 3:
                prev_arg = args[-2]
                if prev_arg in ['--source', '-s', '--dest', '-d']:
                    # Complete with IP addresses
                    if hasattr(self.shell, 'completers'):
                        return self.shell.completers.ip_addresses(text, '', 0, 0)
                elif prev_arg in ['--router', '-r']:
                    # Complete with router names
                    if hasattr(self.shell, 'completers'):
                        return self.shell.completers.router_names(text, '', 0, 0)
                elif prev_arg in ['--protocol', '-p']:
                    # Complete with protocols
                    protocols = ['tcp', 'udp', 'icmp']
                    return [p for p in protocols if p.startswith(text)]
                elif prev_arg in ['--format', '-f']:
                    # Complete with formats
                    formats = ['text', 'json']
                    return [f for f in formats if f.startswith(text)]
            
            # Complete with available options based on subcommand
            if text.startswith('--'):
                if subcommand == 'route':
                    options = ['--source', '-s', '--dest', '-d', '--verbose', '-v', '--json', '-j', '--reverse-trace']
                    return [opt for opt in options if opt.startswith(text)]
                elif subcommand == 'analyze':
                    options = ['--router', '-r', '--source', '-s', '--dest', '-d', '--protocol', '-p', '--sport', '--dport', '--verbose', '-v']
                    return [opt for opt in options if opt.startswith(text)]
                elif subcommand == 'real':
                    options = ['--router', '-r', '--dest', '-d', '--verbose', '-v']
                    return [opt for opt in options if opt.startswith(text)]
                elif subcommand == 'reverse':
                    options = ['--source', '-s', '--dest', '-d', '--verbose', '-v', '--json', '-j']
                    return [opt for opt in options if opt.startswith(text)]
        
        return []
    
    def _mtr_route(self, args: list) -> int:
        """Perform traceroute simulation."""
        parser = argparse.ArgumentParser(prog='mtr route',
                                       description='Simulate traceroute path')
        parser.add_argument('--source', '-s', required=True,
                          help='Source IP address')
        parser.add_argument('--dest', '-d', required=True,
                          help='Destination IP address')
        parser.add_argument('--verbose', '-v', action='count', default=0,
                          help='Increase verbosity')
        parser.add_argument('--json', '-j', action='store_true',
                          help='Output in JSON format')
        parser.add_argument('--reverse-trace', action='store_true',
                          help='Include reverse path trace')
        
        try:
            parsed_args = parser.parse_args(args)
        except SystemExit:
            return 1
        
        # Check if facts directory exists
        if not self.check_facts_directory():
            return 1
        
        self.info(f"Simulating traceroute from {parsed_args.source} to {parsed_args.dest}")
        
        # Run the traceroute simulator
        script_path = self.get_script_path('src/core/traceroute_simulator.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = [
            '--source', parsed_args.source,
            '--destination', parsed_args.dest
        ]
        
        if parsed_args.verbose:
            cmd_args.append('-' + 'v' * parsed_args.verbose)
        
        if parsed_args.json:
            cmd_args.append('--json')
        
        if parsed_args.reverse_trace:
            cmd_args.append('--reverse-trace')
        
        # Run the script
        returncode = self.run_script_with_output(script_path, cmd_args)
        
        return returncode
    
    def _analyze_forward(self, args: list) -> int:
        """Analyze iptables forward rules."""
        parser = argparse.ArgumentParser(prog='mtr analyze',
                                       description='Analyze packet forwarding through iptables')
        parser.add_argument('--router', '-r', required=True,
                          help='Router to analyze')
        parser.add_argument('--source', '-s', required=True,
                          help='Source IP address')
        parser.add_argument('--dest', '-d', required=True,
                          help='Destination IP address')
        parser.add_argument('--protocol', '-p', default='icmp',
                          choices=['tcp', 'udp', 'icmp'],
                          help='Protocol (default: icmp)')
        parser.add_argument('--sport', type=int,
                          help='Source port (for TCP/UDP)')
        parser.add_argument('--dport', type=int,
                          help='Destination port (for TCP/UDP)')
        parser.add_argument('--verbose', '-v', action='count', default=0,
                          help='Increase verbosity')
        
        try:
            parsed_args = parser.parse_args(args)
        except SystemExit:
            return 1
        
        # Check if facts directory exists
        if not self.check_facts_directory():
            return 1
        
        # Validate port requirements
        if parsed_args.protocol in ['tcp', 'udp']:
            if not parsed_args.dport:
                self.error(f"Destination port required for {parsed_args.protocol.upper()}")
                return 1
        
        self.info(f"Analyzing {parsed_args.protocol.upper()} forwarding on {parsed_args.router}")
        
        # Run the iptables analyzer
        script_path = self.get_script_path('src/analyzers/iptables_forward_analyzer.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = [
            '--router', parsed_args.router,
            '--source', parsed_args.source,
            '--destination', parsed_args.dest,
            '--protocol', parsed_args.protocol
        ]
        
        if parsed_args.sport:
            cmd_args.extend(['--sport', str(parsed_args.sport)])
        
        if parsed_args.dport:
            cmd_args.extend(['--dport', str(parsed_args.dport)])
        
        if parsed_args.verbose:
            cmd_args.append('-' + 'v' * parsed_args.verbose)
        
        # Run the script
        returncode = self.run_script_with_output(script_path, cmd_args)
        
        return returncode
    
    def _real_mtr(self, args: list) -> int:
        """Execute real MTR command on a router."""
        parser = argparse.ArgumentParser(prog='mtr real',
                                       description='Execute real MTR on a router')
        parser.add_argument('--router', '-r', required=True,
                          help='Router to run MTR from')
        parser.add_argument('--dest', '-d', required=True,
                          help='Destination IP address')
        parser.add_argument('--verbose', '-v', action='store_true',
                          help='Verbose output')
        
        try:
            parsed_args = parser.parse_args(args)
        except SystemExit:
            return 1
        
        self.info(f"Executing MTR from {parsed_args.router} to {parsed_args.dest}")
        
        # Check if we have an inventory file
        inventory_path = os.path.join(self.project_root, 'inventory.ini')
        if not os.path.exists(inventory_path):
            self.error("No inventory.ini found. Please create one with router SSH details.")
            return 1
        
        # Build SSH command
        try:
            import subprocess
            cmd = [
                'ssh',
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'ConnectTimeout=10',
                parsed_args.router,
                f'mtr -r -n -c 1 {parsed_args.dest}'
            ]
            
            if parsed_args.verbose:
                self.info(f"Running: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.stdout:
                self.shell.poutput(result.stdout)
            if result.stderr:
                self.shell.poutput(result.stderr)
            
            return result.returncode
            
        except Exception as e:
            self.error(f"Failed to execute MTR: {e}")
            return 1
    
    def _reverse_trace(self, args: list) -> int:
        """Perform reverse path tracing."""
        parser = argparse.ArgumentParser(prog='mtr reverse',
                                       description='Trace reverse path from destination to source')
        parser.add_argument('--source', '-s', required=True,
                          help='Source IP address')
        parser.add_argument('--dest', '-d', required=True,
                          help='Destination IP address')
        parser.add_argument('--verbose', '-v', action='count', default=0,
                          help='Increase verbosity')
        parser.add_argument('--json', '-j', action='store_true',
                          help='Output in JSON format')
        
        try:
            parsed_args = parser.parse_args(args)
        except SystemExit:
            return 1
        
        # Check if facts directory exists
        if not self.check_facts_directory():
            return 1
        
        self.info(f"Tracing reverse path from {parsed_args.dest} to {parsed_args.source}")
        
        # Run the reverse path tracer
        script_path = self.get_script_path('src/core/reverse_path_tracer.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = [
            '--source', parsed_args.source,
            '--destination', parsed_args.dest
        ]
        
        if parsed_args.verbose:
            cmd_args.append('-' + 'v' * parsed_args.verbose)
        
        if parsed_args.json:
            cmd_args.append('--json')
        
        # Run the script
        returncode = self.run_script_with_output(script_path, cmd_args)
        
        return returncode