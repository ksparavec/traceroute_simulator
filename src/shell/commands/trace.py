"""
Trace command handler for reverse path tracing.
"""

import os
import sys
import argparse
from typing import Optional, List, Dict, Tuple, Any

try:
    from cmd2 import Cmd2ArgumentParser
except ImportError:
    # Fallback for older cmd2 versions
    from argparse import ArgumentParser as Cmd2ArgumentParser

from .base import BaseCommandHandler

# Add parent directories to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
grandparent_dir = os.path.dirname(parent_dir)
project_root = os.path.dirname(grandparent_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.traceroute_simulator import TracerouteSimulator, load_configuration
from src.core.reverse_path_tracer import ReversePathTracer


class TraceCommands(BaseCommandHandler):
    """Handler for reverse path tracing commands."""
    
    def create_parser(self) -> Cmd2ArgumentParser:
        """Create the argument parser for trace command."""
        parser = Cmd2ArgumentParser(
            prog='trace',
            description='Perform reverse path tracing between source and destination'
        )
        
        parser.add_argument('-s', '--source', required=True,
                          help='Source IP address')
        parser.add_argument('-d', '--destination', required=True,
                          help='Destination IP address')
        parser.add_argument('-j', '--json', action='store_true',
                          help='Output in JSON format')
        parser.add_argument('-v', '--verbose', action='count', default=0,
                          help='Verbose output (can be used multiple times)')
        parser.add_argument('--controller-ip',
                          help='Ansible controller IP (auto-detected if not provided)')
        
        return parser
    
    def handle_parsed_command(self, args: argparse.Namespace) -> Optional[int]:
        """Handle parsed trace command."""
        try:
            # Initialize the simulator
            facts_dir = self.shell.facts_dir
            if not facts_dir:
                facts_dir = os.path.join(self.shell.project_root, 'facts')
            
            if not os.path.exists(facts_dir):
                self.error(f"Facts directory not found: {facts_dir}")
                self.info("Run 'network setup' first to create the network simulation")
                return None  # Return None to keep shell running
            
            # Load configuration to get ansible_controller_ip if not provided
            config = load_configuration(verbose=args.verbose > 0, verbose_level=args.verbose)
            controller_ip = args.controller_ip
            if not controller_ip and config:
                # Try both possible config keys
                controller_ip = config.get('ansible_controller_ip') or config.get('controller_ip')
                if args.verbose >= 2 and controller_ip:
                    print(f"Using controller IP from config: {controller_ip}")
            # Create simulator instance
            simulator = TracerouteSimulator(
                tsim_facts=facts_dir,
                verbose=args.verbose > 0,
                verbose_level=args.verbose
            )
            
            # Initialize reverse path tracer
            tracer = ReversePathTracer(
                simulator=simulator,
                ansible_controller_ip=controller_ip,
                verbose=args.verbose > 0,
                verbose_level=args.verbose
            )
            
            # Perform reverse path tracing
            success, path, exit_code = tracer.perform_reverse_trace(
                args.source,
                args.destination
            )
            
            if not success:
                if not args.json:
                    self.error(f"Failed to trace path from {args.source} to {args.destination}")
                else:
                    # Output empty JSON on failure
                    import json
                    self.shell.poutput(json.dumps({
                        "success": False,
                        "source": args.source,
                        "destination": args.destination,
                        "path": []
                    }))
                return None  # Return None to keep shell running
            
            # Format and display the path
            if args.json:
                self._output_json(args.source, args.destination, path)
            else:
                self._output_text(args.source, args.destination, path)
            
            return 0
            
        except SystemExit:
            # Catch sys.exit() calls from the traceroute simulator
            self.error("Trace command failed")
            return None  # Return None to keep shell running
        except Exception as e:
            if args.verbose:
                import traceback
                self.error(f"Error during reverse path tracing: {e}")
                traceback.print_exc()
            else:
                self.error(f"Error: {e}")
            return None  # Return None to keep shell running
    
    def _output_json(self, source: str, destination: str, path: List[Tuple]):
        """Output path in JSON format."""
        import json
        
        # Convert path tuples to dictionaries
        json_path = []
        for i, hop_data in enumerate(path):
            if len(hop_data) >= 9:
                hop_num, router_name, ip, incoming, is_router, prev_hop, next_hop, outgoing, rtt = hop_data
            elif len(hop_data) == 8:
                hop_num, router_name, ip, incoming, is_router, next_hop, outgoing, rtt = hop_data
                prev_hop = ""
            else:
                hop_num, router_name, ip, incoming, is_router, next_hop, outgoing = hop_data
                rtt = 0.0
                prev_hop = ""
            
            hop_dict = {
                "hop": hop_num,
                "name": router_name,
                "ip": ip,
                "incoming": incoming,
                "is_router": is_router,
                "prev_hop": prev_hop,
                "next_hop": next_hop,
                "outgoing": outgoing,
                "rtt": rtt
            }
            json_path.append(hop_dict)
        
        output = {
            "success": True,
            "source": source,
            "destination": destination,
            "path": json_path
        }
        
        self.shell.poutput(json.dumps(output, indent=2))
    
    def _output_text(self, source: str, destination: str, path: List[Tuple]):
        """Output path in text format."""
        self.success(f"Reverse path trace from {source} to {destination}:")
        self.shell.poutput("")
        
        # Format path output
        for hop_data in path:
            if len(hop_data) >= 9:
                hop_num, router_name, ip, incoming, is_router, prev_hop, next_hop, outgoing, rtt = hop_data
            elif len(hop_data) == 8:
                hop_num, router_name, ip, incoming, is_router, next_hop, outgoing, rtt = hop_data
            else:
                hop_num, router_name, ip, incoming, is_router, next_hop, outgoing = hop_data
                rtt = 0.0
            
            # Format hop output
            hop_str = f"{hop_num:2d}. "
            
            # Add router/host name
            if router_name and router_name != ip:
                hop_str += f"{router_name} ({ip})"
            else:
                hop_str += ip
            
            # Add incoming interface info if available
            if incoming:
                hop_str += f" [{incoming}]"
            
            # Add RTT if available
            if rtt > 0:
                hop_str += f" {rtt:.2f}ms"
            
            # Add connection info if available
            if next_hop:
                hop_str += f" -> {next_hop}"
                if outgoing:
                    hop_str += f" [{outgoing}]"
            
            self.shell.poutput(hop_str)
    
    def _handle_command_impl(self, args: str) -> Optional[int]:
        """Handle trace command implementation."""
        parser = self.create_parser()
        parsed_args = self.parse_arguments(args, parser)
        if parsed_args is None:
            # parse_arguments already printed the error/usage
            return None  # Return None instead of error code to prevent shell exit
        return self.handle_parsed_command(parsed_args)