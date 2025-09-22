#!/usr/bin/env -S python3 -B -u
"""
KSMS Tester command handler (Kernel-Space Multi-Service Tester)

Runs fast yes/no FORWARD reachability checks per router using PREROUTING/POSTROUTING counters
and a single userspace probe helper inside the source netns.
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


class KsmsTesterCommand(BaseCommandHandler):
    """Handler for ksms_tester command."""

    @choices_provider
    def ip_choices(self) -> List[str]:
        if hasattr(self.shell, 'completers'):
            return self.shell.completers._get_all_ips()
        return []

    def create_parser(self) -> Cmd2ArgumentParser:
        parser = Cmd2ArgumentParser(
            prog='ksms_tester',
            description='Kernel-space multi-service tester (fast YES/NO per router)'
        )
        parser.add_argument('-s', '--source', required=True,
                            choices_provider=self.ip_choices,
                            help='Source IP address')
        parser.add_argument('-d', '--destination', required=True,
                            choices_provider=self.ip_choices,
                            help='Destination IP address')
        parser.add_argument('-P', '--ports', required=True,
                            help='Service spec (e.g., "80,443/tcp,53/udp,22-25")')
        parser.add_argument('--default-proto', choices=['tcp', 'udp'], default='tcp',
                            help='Default protocol if not specified in port spec (default: tcp)')
        parser.add_argument('--max-services', type=int, default=10,
                            help='Maximum number of services (default: 10)')
        parser.add_argument('--tcp-timeout', type=float, default=1.0,
                            help='TCP SYN connect timeout in seconds (default: 1.0)')
        parser.add_argument('-j', '--json', action='store_true',
                            help='Output in JSON format')
        parser.add_argument('-v', '--verbose', action='count', default=0,
                            help='Increase verbosity (-v, -vv)')
        return parser

    def handle_parsed_command(self, args: argparse.Namespace) -> Optional[int]:
        # Defer execution to simulator script
        script_path = self.get_script_path('src/simulators/ksms_tester.py')
        if not self.check_script_exists(script_path):
            return 1

        cmd_args = [
            '--source', args.source,
            '--destination', args.destination,
            '--ports', args.ports,
            '--default-proto', args.default_proto,
            '--max-services', str(args.max_services),
            '--tcp-timeout', str(args.tcp_timeout)
        ]
        if args.json:
            cmd_args.append('--json')
        for _ in range(args.verbose):
            cmd_args.append('-v')

        return self.run_script_with_output(script_path, cmd_args, use_sudo=False)

    def _handle_command_impl(self, args: str) -> Optional[int]:
        # help handling
        args_list = args.strip().split() if args.strip() else []
        if not args.strip() or '--help' in args_list or '-h' in args_list:
            self.shell.help_ksms_tester()
            return 0

        parser = self.create_parser()
        parsed_args = self.parse_arguments(args, parser)
        if parsed_args is None:
            return None
        return self.handle_parsed_command(parsed_args)

    def complete_command(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        args = line.split()
        # complete argument names
        available_args = ['-s', '--source', '-d', '--destination', '-P', '--ports',
                          '--default-proto', '--max-services', '--tcp-timeout', '-j', '--json', '-v', '--verbose']
        if len(args) >= 2 and args[-2] in ['-s', '--source', '-d', '--destination']:
            return [ip for ip in self.ip_choices() if ip.startswith(text)]
        if len(args) >= 2 and args[-2] == '--default-proto':
            return [p for p in ['tcp', 'udp'] if p.startswith(text)]
        return [a for a in available_args if a.startswith(text)]

