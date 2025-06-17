"""
IP Command JSON Wrapper for Older Red Hat Distributions

This script provides a transparent wrapper around the 'ip' command that converts
text output to JSON format for distributions that don't support the --json flag.
It mimics the behavior of 'ip --json' by parsing the standard text output.

Usage:
    python3 ip_json_wrapper.py [ip_command_args...]
    
Examples:
    python3 ip_json_wrapper.py route show
    python3 ip_json_wrapper.py addr show
    python3 ip_json_wrapper.py link show
    python3 ip_json_wrapper.py rule show
"""

import sys
import subprocess
import json
import re
from typing import List, Dict, Any, Optional


class IPCommandParser:
    """Parser for converting IP command text output to JSON format."""
    
    def __init__(self):
        """Initialize the parser."""
        pass
    
    def parse_route_output(self, output: str) -> List[Dict[str, Any]]:
        """
        Parse 'ip route show' output into JSON format.
        
        Args:
            output: Raw text output from ip route show
            
        Returns:
            List of route dictionaries in JSON format
        """
        routes = []
        for line in output.strip().split('\n'):
            if not line.strip():
                continue
                
            route = {'flags': []}  # Initialize with empty flags array like native output
            parts = line.split()
            if not parts:
                continue
            
            # Parse destination - match native format exactly
            if parts[0] == 'default':
                route['dst'] = 'default'
                idx = 1
            elif '/' in parts[0]:
                # Keep dst in CIDR format to match native output
                route['dst'] = parts[0]
                idx = 1
            else:
                # Host route (no prefix) - keep as single IP
                route['dst'] = parts[0]
                idx = 1
            
            # Parse remaining attributes
            i = idx
            while i < len(parts):
                if parts[i] == 'via' and i + 1 < len(parts):
                    route['gateway'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'dev' and i + 1 < len(parts):
                    route['dev'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'proto' and i + 1 < len(parts):
                    route['protocol'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'scope' and i + 1 < len(parts):
                    route['scope'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'src' and i + 1 < len(parts):
                    route['prefsrc'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'metric' and i + 1 < len(parts):
                    route['metric'] = int(parts[i + 1])
                    i += 2
                elif parts[i] in ['linkdown', 'onlink']:
                    route['flags'].append(parts[i])
                    i += 1
                else:
                    i += 1
            
            routes.append(route)
        
        return routes
    
    def parse_addr_output(self, output: str) -> List[Dict[str, Any]]:
        """
        Parse 'ip addr show' output into JSON format.
        
        Args:
            output: Raw text output from ip addr show
            
        Returns:
            List of interface dictionaries in JSON format
        """
        interfaces = []
        current_interface = None
        
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Interface line (starts with number)
            if re.match(r'^\d+:', line):
                if current_interface:
                    interfaces.append(current_interface)
                
                parts = line.split()
                ifindex = int(parts[0].rstrip(':'))
                ifname = parts[1].rstrip(':')
                
                # Parse interface name and peer
                if '@' in ifname:
                    ifname, link = ifname.split('@', 1)
                    if link.startswith('if'):
                        link = int(link[2:])
                else:
                    link = None
                
                # Parse flags
                flags_match = re.search(r'<([^>]+)>', line)
                flags = flags_match.group(1).split(',') if flags_match else []
                
                # Parse other attributes
                mtu = None
                qdisc = None
                state = None
                group = None
                qlen = None
                master = None
                
                for i, part in enumerate(parts):
                    if part == 'mtu' and i + 1 < len(parts):
                        mtu = int(parts[i + 1])
                    elif part == 'qdisc' and i + 1 < len(parts):
                        qdisc = parts[i + 1]
                    elif part == 'state' and i + 1 < len(parts):
                        state = parts[i + 1]
                    elif part == 'group' and i + 1 < len(parts):
                        group = parts[i + 1]
                    elif part == 'qlen' and i + 1 < len(parts):
                        qlen = int(parts[i + 1])
                    elif part == 'master' and i + 1 < len(parts):
                        master = parts[i + 1]
                
                current_interface = {
                    'ifindex': ifindex,
                    'ifname': ifname,
                    'flags': flags,
                    'mtu': mtu,
                    'qdisc': qdisc,
                    'operstate': state,
                    'group': group,
                    'link_type': 'ether',  # Default, will be updated if found
                    'addr_info': []
                }
                
                if link is not None:
                    current_interface['link'] = link
                if qlen is not None:
                    current_interface['txqlen'] = qlen
                if master is not None:
                    current_interface['master'] = master
            
            # Link line
            elif line.startswith('link/'):
                if current_interface:
                    parts = line.split()
                    link_type = parts[0].split('/', 1)[1]
                    current_interface['link_type'] = link_type
                    
                    if len(parts) > 1 and parts[1] != '':
                        current_interface['address'] = parts[1]
                    if len(parts) > 3 and parts[2] == 'brd':
                        current_interface['broadcast'] = parts[3]
                    
                    # Check for link-netnsid and master in the link line
                    for i, part in enumerate(parts):
                        if part == 'link-netnsid' and i + 1 < len(parts):
                            if 'link' in current_interface:
                                current_interface['link_index'] = current_interface['link']
                                current_interface['link_netnsid'] = int(parts[i + 1])
                                del current_interface['link']
                        elif part == 'master' and i + 1 < len(parts):
                            current_interface['master'] = parts[i + 1]
            
            # Address line (inet/inet6)
            elif line.startswith(('inet ', 'inet6 ')):
                if current_interface:
                    parts = line.split()
                    family = 'inet' if parts[0] == 'inet' else 'inet6'
                    
                    if '/' in parts[1]:
                        local, prefixlen = parts[1].split('/')
                        prefixlen = int(prefixlen)
                    else:
                        local = parts[1]
                        prefixlen = 32 if family == 'inet' else 128
                    
                    addr_info = {
                        'family': family,
                        'local': local,
                        'prefixlen': prefixlen,
                        'scope': 'global',  # Default scope
                        'valid_life_time': 4294967295,  # Forever
                        'preferred_life_time': 4294967295  # Forever
                    }
                    
                    # Add label for IPv4 addresses
                    if family == 'inet':
                        addr_info['label'] = current_interface['ifname']
                    
                    # Parse additional address attributes
                    i = 2
                    while i < len(parts):
                        if parts[i] == 'brd' and i + 1 < len(parts):
                            addr_info['broadcast'] = parts[i + 1]
                            i += 2
                        elif parts[i] == 'scope' and i + 1 < len(parts):
                            addr_info['scope'] = parts[i + 1]
                            i += 2
                        elif parts[i] in ['global', 'host', 'link']:
                            addr_info['scope'] = parts[i]
                            i += 1
                        elif parts[i] == 'dynamic':
                            addr_info['dynamic'] = True
                            i += 1
                        elif parts[i] == 'noprefixroute':
                            addr_info['noprefixroute'] = True
                            i += 1
                        else:
                            i += 1
                    
                    current_interface['addr_info'].append(addr_info)
        
        # Add the last interface
        if current_interface:
            interfaces.append(current_interface)
        
        return interfaces
    
    def parse_link_output(self, output: str) -> List[Dict[str, Any]]:
        """
        Parse 'ip link show' output into JSON format.
        
        Args:
            output: Raw text output from ip link show
            
        Returns:
            List of link dictionaries in JSON format
        """
        links = []
        current_link = None
        
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Interface line (starts with number)
            if re.match(r'^\d+:', line):
                if current_link:
                    links.append(current_link)
                
                parts = line.split()
                ifindex = int(parts[0].rstrip(':'))
                ifname = parts[1].rstrip(':')
                
                # Parse interface name and peer
                if '@' in ifname:
                    ifname, link = ifname.split('@', 1)
                    if link.startswith('if'):
                        link = int(link[2:])
                else:
                    link = None
                
                # Parse flags
                flags_match = re.search(r'<([^>]+)>', line)
                flags = flags_match.group(1).split(',') if flags_match else []
                
                # Parse other attributes
                mtu = None
                qdisc = None
                state = None
                mode = None
                group = None
                qlen = None
                master = None
                
                for i, part in enumerate(parts):
                    if part == 'mtu' and i + 1 < len(parts):
                        mtu = int(parts[i + 1])
                    elif part == 'qdisc' and i + 1 < len(parts):
                        qdisc = parts[i + 1]
                    elif part == 'state' and i + 1 < len(parts):
                        state = parts[i + 1]
                    elif part == 'mode' and i + 1 < len(parts):
                        mode = parts[i + 1]
                    elif part == 'group' and i + 1 < len(parts):
                        group = parts[i + 1]
                    elif part == 'qlen' and i + 1 < len(parts):
                        qlen = int(parts[i + 1])
                    elif part == 'master' and i + 1 < len(parts):
                        master = parts[i + 1]
                
                current_link = {
                    'ifindex': ifindex,
                    'ifname': ifname,
                    'flags': flags,
                    'mtu': mtu,
                    'qdisc': qdisc,
                    'operstate': state,
                    'linkmode': mode,
                    'group': group
                }
                
                if link is not None:
                    current_link['link'] = link
                        
                if qlen is not None:
                    current_link['txqlen'] = qlen
                if master is not None:
                    current_link['master'] = master
            
            # Link line (contains MAC address info)
            elif line.startswith('link/') and current_link:
                parts = line.split()
                link_type = parts[0].split('/', 1)[1]
                current_link['link_type'] = link_type
                
                if len(parts) > 1 and parts[1] != '':
                    current_link['address'] = parts[1]
                if len(parts) > 3 and parts[2] == 'brd':
                    current_link['broadcast'] = parts[3]
                
                # Check for link-netnsid
                for i, part in enumerate(parts):
                    if part == 'link-netnsid' and i + 1 < len(parts):
                        # If we have a peer link, use link_index format
                        if 'link' in current_link:
                            current_link['link_index'] = current_link['link']
                            current_link['link_netnsid'] = int(parts[i + 1])
                            del current_link['link']
                        break
        
        # Add the last link
        if current_link:
            links.append(current_link)
        
        return links
    
    def parse_rule_output(self, output: str) -> List[Dict[str, Any]]:
        """
        Parse 'ip rule show' output into JSON format.
        
        Args:
            output: Raw text output from ip rule show
            
        Returns:
            List of rule dictionaries in JSON format
        """
        rules = []
        
        for line in output.strip().split('\n'):
            if not line.strip():
                continue
            
            parts = line.split()
            if not parts:
                continue
            
            rule = {}
            
            # Parse priority
            priority_match = re.match(r'^(\d+):', parts[0])
            if priority_match:
                rule['priority'] = int(priority_match.group(1))
                parts = parts[1:]
            
            # Parse remaining attributes
            i = 0
            while i < len(parts):
                if parts[i] == 'from' and i + 1 < len(parts):
                    rule['src'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'to' and i + 1 < len(parts):
                    rule['dst'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'lookup' and i + 1 < len(parts):
                    rule['table'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'iif' and i + 1 < len(parts):
                    rule['iif'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'oif' and i + 1 < len(parts):
                    rule['oif'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'fwmark' and i + 1 < len(parts):
                    rule['fwmark'] = parts[i + 1]
                    i += 2
                else:
                    i += 1
            
            rules.append(rule)
        
        return rules


def run_ip_command(args: List[str]) -> str:
    """
    Run the ip command with given arguments and return output.
    
    Args:
        args: List of command arguments
        
    Returns:
        Command output as string
        
    Raises:
        subprocess.CalledProcessError: If command fails
    """
    cmd = ['ip'] + args
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


def main():
    """Main entry point for the IP JSON wrapper."""
    if len(sys.argv) < 2:
        print("Usage: ip_json_wrapper.py [ip_command_args...]", file=sys.stderr)
        print("Examples:", file=sys.stderr)
        print("  ip_json_wrapper.py route show", file=sys.stderr)
        print("  ip_json_wrapper.py addr show", file=sys.stderr)
        print("  ip_json_wrapper.py link show", file=sys.stderr)
        print("  ip_json_wrapper.py rule show", file=sys.stderr)
        sys.exit(1)
    
    # Remove script name and process arguments
    args = sys.argv[1:]
    
    # Check if JSON flags are already in args (for newer systems)
    if '--json' in args or '-json' in args or '-j' in args:
        # Just pass through to ip command
        try:
            result = subprocess.run(['ip'] + args, check=True)
            sys.exit(result.returncode)
        except subprocess.CalledProcessError as e:
            sys.exit(e.returncode)
        except FileNotFoundError:
            print("Error: 'ip' command not found", file=sys.stderr)
            sys.exit(1)
    
    try:
        # Run the ip command without --json
        output = run_ip_command(args)
        
        # Parse based on subcommand
        parser = IPCommandParser()
        json_output = None
        
        if len(args) >= 1:
            subcommand = args[0]
            
            if subcommand == 'route' or (subcommand == 'r' and len(args) > 1):
                json_output = parser.parse_route_output(output)
            elif subcommand == 'addr' or subcommand == 'address' or subcommand == 'a':
                json_output = parser.parse_addr_output(output)
            elif subcommand == 'link' or subcommand == 'l':
                json_output = parser.parse_link_output(output)
            elif subcommand == 'rule':
                json_output = parser.parse_rule_output(output)
            else:
                # Unsupported subcommand, return original output
                print(output, end='')
                return
        
        if json_output is not None:
            print(json.dumps(json_output, indent=2))
        else:
            print(output, end='')
    
    except subprocess.CalledProcessError as e:
        print(f"Error running ip command: {e}", file=sys.stderr)
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        sys.exit(e.returncode)
    except FileNotFoundError:
        print("Error: 'ip' command not found", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()