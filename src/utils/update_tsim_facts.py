#!/usr/bin/env python3
"""
Update tsim_facts JSON files to extract interfaces from routing tables
"""

import json
import os
import sys
from pathlib import Path

def extract_interfaces_from_routing(router_data):
    """Extract interface information from routing tables - same logic as get_router_interfaces"""
    interfaces = []
    routing_data = router_data.get('routing', {})
    routes = routing_data.get('tables', [])
    
    # Extract routes with protocol: kernel and scope: link
    for route in routes:
        if (route.get('protocol') == 'kernel' and 
            route.get('scope') == 'link' and
            'prefsrc' in route and 'dev' in route):
            
            interface = route['dev']
            ip_addr = route['prefsrc']
            dst = route['dst']
            
            # Skip loopback addresses
            if ip_addr.startswith('127.'):
                continue
                
            # Create interface entry
            interface_entry = {
                'dev': interface,
                'dst': dst,
                'prefsrc': ip_addr,
                'protocol': 'kernel',
                'scope': 'link'
            }
            interfaces.append(interface_entry)
    
    return interfaces

def update_tsim_facts():
    """Update all tsim_facts files"""
    facts_path = os.environ.get('TRACEROUTE_SIMULATOR_FACTS')
    if not facts_path:
        print("Error: TRACEROUTE_SIMULATOR_FACTS environment variable must be set")
        sys.exit(1)
    facts_dir = Path(facts_path)
    
    for facts_file in facts_dir.glob('*.json'):
        if '_metadata' in facts_file.name:
            continue
            
        print(f"Processing {facts_file.name}...")
        
        # Load router data
        with open(facts_file, 'r') as f:
            router_data = json.load(f)
        
        # Extract interfaces from routing tables
        interfaces = extract_interfaces_from_routing(router_data)
        
        # Update network.interfaces section
        router_data['network']['interfaces'] = interfaces
        
        # Write back to file
        with open(facts_file, 'w') as f:
            json.dump(router_data, f, indent=2)
        
        print(f"  Extracted {len(interfaces)} interfaces")

if __name__ == '__main__':
    update_tsim_facts()
    print("All tsim_facts files updated!")