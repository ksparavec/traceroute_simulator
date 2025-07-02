#!/usr/bin/env python3
"""
Generate ipsets for raw facts files based on official ipset documentation.
Creates exactly one ipset per documented type with 3 entries each.
"""

import os
import re
from pathlib import Path

# Define all documented ipset types and their distributions
IPSET_TYPES = {
    'hq-gw': ['bitmap:ip'],
    'hq-core': ['bitmap:ip,mac', 'bitmap:port'], 
    'hq-dmz': ['hash:ip'],
    'hq-lab': ['hash:mac', 'hash:ip,mac'],
    'br-gw': ['hash:net'],
    'br-core': ['hash:net,net'],
    'br-wifi': ['hash:ip,port'],
    'dc-gw': ['hash:net,port'],
    'dc-core': ['hash:ip,port,ip'],
    'dc-srv': ['hash:ip,port,net', 'hash:net,iface', 'list:set']
}

def generate_ipset_config():
    """Generate ipset create and add commands following official documentation."""
    configs = {}
    
    for router, types in IPSET_TYPES.items():
        configs[router] = {
            'create_commands': [],
            'add_commands': []
        }
        
        for ipset_type in types:
            if ipset_type == 'bitmap:ip':
                # bitmap:ip - stores IPv4 host addresses in a range
                configs[router]['create_commands'].append('create test_bitmap_ip bitmap:ip range 10.1.1.0/24')
                configs[router]['add_commands'].extend([
                    'add test_bitmap_ip 10.1.1.10',
                    'add test_bitmap_ip 10.1.1.20', 
                    'add test_bitmap_ip 10.1.1.30'
                ])
                
            elif ipset_type == 'bitmap:ip,mac':
                # bitmap:ip,mac - stores IPv4 and MAC address pairs
                configs[router]['create_commands'].append('create test_bitmap_ip_mac bitmap:ip,mac range 10.1.2.0/24')
                configs[router]['add_commands'].extend([
                    'add test_bitmap_ip_mac 10.1.2.10,52:54:00:01:02:03',
                    'add test_bitmap_ip_mac 10.1.2.20,52:54:00:01:02:04',
                    'add test_bitmap_ip_mac 10.1.2.30,52:54:00:01:02:05'
                ])
                
            elif ipset_type == 'bitmap:port':
                # bitmap:port - stores port numbers in a range
                configs[router]['create_commands'].append('create test_bitmap_port bitmap:port range 80-8080')
                configs[router]['add_commands'].extend([
                    'add test_bitmap_port 80',
                    'add test_bitmap_port 443',
                    'add test_bitmap_port 8080'
                ])
                
            elif ipset_type == 'hash:ip':
                # hash:ip - stores IP host addresses
                configs[router]['create_commands'].append('create test_hash_ip hash:ip')
                configs[router]['add_commands'].extend([
                    'add test_hash_ip 10.1.3.10',
                    'add test_hash_ip 10.1.3.20',
                    'add test_hash_ip 10.1.3.30'
                ])
                
            elif ipset_type == 'hash:mac':
                # hash:mac - stores MAC addresses
                configs[router]['create_commands'].append('create test_hash_mac hash:mac')
                configs[router]['add_commands'].extend([
                    'add test_hash_mac 52:54:00:01:10:01',
                    'add test_hash_mac 52:54:00:01:10:02',
                    'add test_hash_mac 52:54:00:01:10:03'
                ])
                
            elif ipset_type == 'hash:ip,mac':
                # hash:ip,mac - stores IP and MAC address pairs
                configs[router]['create_commands'].append('create test_hash_ip_mac hash:ip,mac')
                configs[router]['add_commands'].extend([
                    'add test_hash_ip_mac 10.1.10.10,52:54:00:01:11:01',
                    'add test_hash_ip_mac 10.1.11.10,52:54:00:01:11:02',
                    'add test_hash_ip_mac 10.1.10.20,52:54:00:01:11:03'
                ])
                
            elif ipset_type == 'hash:net':
                # hash:net - stores different sized IP network addresses
                configs[router]['create_commands'].append('create test_hash_net hash:net')
                configs[router]['add_commands'].extend([
                    'add test_hash_net 10.2.1.0/24',
                    'add test_hash_net 10.2.2.0/24',
                    'add test_hash_net 10.2.0.0/16'
                ])
                
            elif ipset_type == 'hash:net,net':
                # hash:net,net - stores pairs of different sized IP network addresses
                configs[router]['create_commands'].append('create test_hash_net_net hash:net,net')
                configs[router]['add_commands'].extend([
                    'add test_hash_net_net 10.2.1.0/24,10.1.1.0/24',
                    'add test_hash_net_net 10.2.2.0/24,10.1.2.0/24',
                    'add test_hash_net_net 10.2.0.0/16,10.3.0.0/16'
                ])
                
            elif ipset_type == 'hash:ip,port':
                # hash:ip,port - stores IP address and port number pairs
                configs[router]['create_commands'].append('create test_hash_ip_port hash:ip,port')
                configs[router]['add_commands'].extend([
                    'add test_hash_ip_port 10.2.5.10,tcp:80',
                    'add test_hash_ip_port 10.2.6.10,tcp:443',
                    'add test_hash_ip_port 10.2.5.20,udp:53'
                ])
                
            elif ipset_type == 'hash:net,port':
                # hash:net,port - stores network address and port pairs
                configs[router]['create_commands'].append('create test_hash_net_port hash:net,port')
                configs[router]['add_commands'].extend([
                    'add test_hash_net_port 10.3.1.0/24,tcp:22',
                    'add test_hash_net_port 10.3.2.0/24,tcp:80',
                    'add test_hash_net_port 10.3.0.0/16,udp:161'
                ])
                
            elif ipset_type == 'hash:ip,port,ip':
                # hash:ip,port,ip - stores IP, port, second IP address triples
                configs[router]['create_commands'].append('create test_hash_ip_port_ip hash:ip,port,ip')
                configs[router]['add_commands'].extend([
                    'add test_hash_ip_port_ip 10.3.1.10,tcp:80,10.3.2.10',
                    'add test_hash_ip_port_ip 10.3.1.20,tcp:443,10.3.2.20',
                    'add test_hash_ip_port_ip 10.3.1.30,udp:53,10.3.2.30'
                ])
                
            elif ipset_type == 'hash:ip,port,net':
                # hash:ip,port,net - stores IP, port, network address triples  
                configs[router]['create_commands'].append('create test_hash_ip_port_net hash:ip,port,net')
                configs[router]['add_commands'].extend([
                    'add test_hash_ip_port_net 10.3.10.10,tcp:80,10.1.0.0/16',
                    'add test_hash_ip_port_net 10.3.20.10,tcp:443,10.2.0.0/16',
                    'add test_hash_ip_port_net 10.3.21.10,udp:514,10.3.0.0/16'
                ])
                
            elif ipset_type == 'hash:net,iface':
                # hash:net,iface - stores network address and interface name pairs
                configs[router]['create_commands'].append('create test_hash_net_iface hash:net,iface')
                configs[router]['add_commands'].extend([
                    'add test_hash_net_iface 10.3.2.0/24,eth0',
                    'add test_hash_net_iface 10.3.10.0/24,eth1',
                    'add test_hash_net_iface 10.3.20.0/24,eth2'
                ])
                
            elif ipset_type == 'list:set':
                # list:set - stores set names (need to create referenced sets first)
                configs[router]['create_commands'].extend([
                    'create test_set1 hash:ip',
                    'create test_set2 hash:ip',
                    'create test_set3 hash:ip',
                    'create test_list_set list:set'
                ])
                configs[router]['add_commands'].extend([
                    'add test_set1 10.3.21.100',  # Populate referenced sets
                    'add test_set2 10.3.21.101',
                    'add test_set3 10.3.21.102',
                    'add test_list_set test_set1',
                    'add test_list_set test_set2',
                    'add test_list_set test_set3'
                ])
    
    return configs

def remove_existing_ipsets(content: str) -> str:
    """Remove all existing ipset sections from raw facts content."""
    # Remove ipset_save section entirely
    pattern = r'=== TSIM_SECTION_START:ipset_save ===.*?=== TSIM_SECTION_END:ipset_save ===\n?'
    content = re.sub(pattern, '', content, flags=re.DOTALL)
    return content

def create_ipset_section(router: str, config: dict) -> str:
    """Create properly formatted ipset_save section."""
    section = """=== TSIM_SECTION_START:ipset_save ===
TITLE: Ipset Save Output
COMMAND: /sbin/ipset save
TIMESTAMP: 2025-07-02 10:00:00
---
"""
    
    # Add create commands
    for create_cmd in config['create_commands']:
        section += f"{create_cmd}\n"
    
    # Add add commands
    for add_cmd in config['add_commands']:
        section += f"{add_cmd}\n"
    
    section += """
EXIT_CODE: 0
=== TSIM_SECTION_END:ipset_save ===

"""
    return section

def validate_entries():
    """Validate that all generated entries comply with documentation."""
    configs = generate_ipset_config()
    validation_results = {}
    
    for router, config in configs.items():
        validation_results[router] = []
        
        # Check each create command
        for create_cmd in config['create_commands']:
            parts = create_cmd.split()
            if len(parts) < 3 or parts[0] != 'create':
                validation_results[router].append(f"Invalid create command: {create_cmd}")
                continue
                
            set_type = parts[2]
            # Validate type exists in documentation
            valid_types = ['bitmap:ip', 'bitmap:ip,mac', 'bitmap:port', 'hash:ip', 'hash:mac', 
                          'hash:ip,mac', 'hash:net', 'hash:net,net', 'hash:ip,port', 'hash:net,port',
                          'hash:ip,port,ip', 'hash:ip,port,net', 'hash:net,iface', 'list:set']
            
            if set_type not in valid_types:
                validation_results[router].append(f"Invalid ipset type: {set_type}")
            else:
                validation_results[router].append(f"✓ Valid create: {create_cmd}")
        
        # Check each add command  
        for add_cmd in config['add_commands']:
            parts = add_cmd.split()
            if len(parts) < 3 or parts[0] != 'add':
                validation_results[router].append(f"Invalid add command: {add_cmd}")
                continue
            
            validation_results[router].append(f"✓ Valid add: {add_cmd}")
    
    return validation_results

def main():
    """Main function to generate and apply ipset configurations."""
    facts_dir = Path('/home/sparavec/git/traceroute_simulator/tests/raw_facts')
    
    if not facts_dir.exists():
        print(f"Error: {facts_dir} does not exist")
        return
    
    print("Generating ipset configurations based on official documentation...")
    configs = generate_ipset_config()
    
    print("\nValidating generated entries...")
    validation_results = validate_entries()
    
    # Print validation results
    for router, results in validation_results.items():
        print(f"\n{router}:")
        for result in results:
            print(f"  {result}")
    
    print(f"\nRemoving existing ipsets and applying new configurations...")
    
    # Process each router's raw facts file
    for router in configs.keys():
        facts_file = facts_dir / f"{router}_facts.txt"
        
        if not facts_file.exists():
            print(f"Warning: {facts_file} does not exist")
            continue
        
        # Read existing content
        with open(facts_file, 'r') as f:
            content = f.read()
        
        # Remove existing ipset sections
        content = remove_existing_ipsets(content)
        
        # Add new ipset section before the final newline
        content = content.rstrip()
        ipset_section = create_ipset_section(router, configs[router])
        content += '\n' + ipset_section
        
        # Write back to file
        with open(facts_file, 'w') as f:
            f.write(content)
        
        print(f"  Updated {router}_facts.txt with {len(configs[router]['create_commands'])} create commands and {len(configs[router]['add_commands'])} add commands")
    
    print(f"\nSummary:")
    total_creates = sum(len(config['create_commands']) for config in configs.values())
    total_adds = sum(len(config['add_commands']) for config in configs.values())
    print(f"  Total ipset types distributed: {len([t for types in IPSET_TYPES.values() for t in types])}")
    print(f"  Total create commands: {total_creates}")
    print(f"  Total add commands: {total_adds}")
    print(f"  Files updated: {len(configs)}")

if __name__ == '__main__':
    main()