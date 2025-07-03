#!/usr/bin/env python3
"""
extract_interfaces.py - Extract interface information from JSON facts files

This utility script provides easy access to interface information from processed
JSON facts files using the FactsProcessor class methods.

Usage:
    # List all interfaces
    python3 extract_interfaces.py /path/to/router.json
    
    # Get specific interface details
    python3 extract_interfaces.py /path/to/router.json --interface eth0
    
    # Get only IP addresses (all families)
    python3 extract_interfaces.py /path/to/router.json --ips-only
    
    # Get only IPv4 addresses
    python3 extract_interfaces.py /path/to/router.json --ips-only --family inet
    
    # Get only IPv6 addresses
    python3 extract_interfaces.py /path/to/router.json --ips-only --family inet6
    
    # Output as JSON
    python3 extract_interfaces.py /path/to/router.json --json
"""

import sys
import json
import argparse
from pathlib import Path

# Import FactsProcessor
try:
    from process_facts import FactsProcessor
except ImportError:
    print("Error: Could not import FactsProcessor from process_facts.py")
    print("Make sure process_facts.py is in the same directory")
    sys.exit(1)


def format_interface_summary(interfaces_data: dict) -> str:
    """Format interface data as a human-readable summary."""
    if not interfaces_data.get('available', False):
        return f"Error: {interfaces_data.get('error', 'Interface data not available')}"
    
    lines = []
    lines.append(f"Total interfaces: {interfaces_data['count']}")
    lines.append("")
    
    for name, data in interfaces_data['interfaces'].items():
        lines.append(f"Interface: {name}")
        lines.append(f"  Index: {data.get('index', 'unknown')}")
        lines.append(f"  State: {data.get('state', 'unknown')}")
        lines.append(f"  MTU: {data.get('mtu', 'unknown')}")
        lines.append(f"  Flags: {', '.join(data.get('flags', []))}")
        
        if 'link_type' in data:
            lines.append(f"  Link type: {data['link_type']}")
        if 'mac_address' in data:
            lines.append(f"  MAC address: {data['mac_address']}")
        
        addresses = data.get('addresses', [])
        if addresses:
            lines.append(f"  Addresses ({len(addresses)}):")
            for addr in addresses:
                addr_str = f"    {addr['family']}: {addr['address']}"
                if 'prefixlen' in addr:
                    addr_str += f"/{addr['prefixlen']}"
                if 'scope' in addr:
                    addr_str += f" (scope: {addr['scope']})"
                lines.append(addr_str)
        else:
            lines.append("  Addresses: none")
        
        lines.append("")
    
    return "\n".join(lines)


def format_single_interface(interface_data: dict) -> str:
    """Format single interface data as human-readable text."""
    if not interface_data.get('available', False):
        return f"Error: {interface_data.get('error', 'Interface not found')}"
    
    name = interface_data['interface']
    data = interface_data['data']
    
    lines = []
    lines.append(f"Interface: {name}")
    lines.append(f"Index: {data.get('index', 'unknown')}")
    lines.append(f"State: {data.get('state', 'unknown')}")
    lines.append(f"MTU: {data.get('mtu', 'unknown')}")
    lines.append(f"Flags: {', '.join(data.get('flags', []))}")
    
    if 'link_type' in data:
        lines.append(f"Link type: {data['link_type']}")
    if 'mac_address' in data:
        lines.append(f"MAC address: {data['mac_address']}")
    if 'qdisc' in data:
        lines.append(f"Queue discipline: {data['qdisc']}")
    if 'group' in data:
        lines.append(f"Group: {data['group']}")
    if 'qlen' in data:
        lines.append(f"Queue length: {data['qlen']}")
    
    addresses = data.get('addresses', [])
    if addresses:
        lines.append(f"Addresses ({len(addresses)}):")
        for addr in addresses:
            addr_str = f"  {addr['family']}: {addr['address']}"
            if 'prefixlen' in addr:
                addr_str += f"/{addr['prefixlen']}"
            if 'scope' in addr:
                addr_str += f" (scope: {addr['scope']})"
            if 'label' in addr:
                addr_str += f" [label: {addr['label']}]"
            if addr.get('secondary'):
                addr_str += " [secondary]"
            if addr.get('dynamic'):
                addr_str += " [dynamic]"
            lines.append(addr_str)
    else:
        lines.append("Addresses: none")
    
    return "\n".join(lines)


def format_ip_list(ip_data: dict, family: str = 'all') -> str:
    """Format IP address list as human-readable text."""
    if 'error' in ip_data:
        return f"Error: {ip_data['error']}"
    
    lines = []
    family_label = f"IP addresses ({family})" if family != 'all' else "IP addresses (all families)"
    lines.append(family_label)
    lines.append("=" * len(family_label))
    
    for interface, ips in ip_data.items():
        if ips:  # Only show interfaces with addresses
            lines.append(f"{interface}: {', '.join(ips)}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Extract interface information from JSON facts files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # List all interfaces with details
    python3 extract_interfaces.py router.json
    
    # Get specific interface
    python3 extract_interfaces.py router.json --interface eth0
    
    # Get IP addresses only
    python3 extract_interfaces.py router.json --ips-only
    
    # Get only IPv4 addresses
    python3 extract_interfaces.py router.json --ips-only --family inet
    
    # Output as JSON
    python3 extract_interfaces.py router.json --json
        """
    )
    
    parser.add_argument('json_file', help='Path to JSON facts file')
    parser.add_argument('--interface', '-i', help='Extract specific interface only')
    parser.add_argument('--ips-only', action='store_true', help='Extract IP addresses only')
    parser.add_argument('--family', choices=['all', 'inet', 'inet6'], default='all',
                        help='IP family to extract (default: all)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    args = parser.parse_args()
    
    # Check if file exists
    if not Path(args.json_file).exists():
        print(f"Error: File not found: {args.json_file}")
        return 1
    
    try:
        if args.ips_only:
            # Extract IP addresses only
            result = FactsProcessor.extract_interface_ips(args.json_file, args.family)
            
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(format_ip_list(result, args.family))
                
        elif args.interface:
            # Extract specific interface
            result = FactsProcessor.extract_interface_info(args.json_file, args.interface)
            
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(format_single_interface(result))
                
        else:
            # Extract all interfaces
            result = FactsProcessor.extract_interface_info(args.json_file)
            
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(format_interface_summary(result))
        
        return 0
        
    except Exception as e:
        print(f"Error processing file: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())