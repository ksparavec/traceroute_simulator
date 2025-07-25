#!/usr/bin/env -S python3 -B -u
"""
Enhanced Policy Routing Generator for Raw Facts Files

This script augments all raw fact files with complex policy routing rules
and additional routing tables for advanced enterprise network scenarios.
"""

import os
import sys
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple
import json

# Network topology configuration
NETWORK_CONFIG = {
    'hq-gw': {
        'location': 'hq',
        'type': 'gateway',
        'primary_ip': '10.1.1.1',
        'external_ip': '203.0.113.10',
        'networks': ['10.1.1.0/24', '10.1.2.0/24'],
        'interfaces': {'eth0': '203.0.113.10/24', 'eth1': '10.1.1.1/24', 'wg0': '10.100.1.1/24'}
    },
    'hq-core': {
        'location': 'hq',
        'type': 'core',
        'primary_ip': '10.1.1.2',
        'networks': ['10.1.1.0/24', '10.1.2.0/24', '10.1.10.0/24', '10.1.11.0/24'],
        'interfaces': {'eth0': '10.1.1.2/24', 'eth1': '10.1.10.1/24', 'eth2': '10.1.11.1/24'}
    },
    'hq-dmz': {
        'location': 'hq',
        'type': 'access',
        'primary_ip': '10.1.2.3',
        'networks': ['10.1.2.0/24', '10.1.3.0/24'],
        'interfaces': {'eth0': '10.1.2.3/24', 'eth1': '10.1.3.1/24'}
    },
    'hq-lab': {
        'location': 'hq',
        'type': 'access',
        'primary_ip': '10.1.11.2',
        'networks': ['10.1.11.0/24'],
        'interfaces': {'eth0': '10.1.11.2/24'}
    },
    'br-gw': {
        'location': 'branch',
        'type': 'gateway',
        'primary_ip': '10.2.1.1',
        'external_ip': '198.51.100.10',
        'networks': ['10.2.1.0/24', '10.2.2.0/24'],
        'interfaces': {'eth0': '198.51.100.10/24', 'eth1': '10.2.1.1/24', 'wg0': '10.100.1.2/24'}
    },
    'br-core': {
        'location': 'branch',
        'type': 'core',
        'primary_ip': '10.2.1.2',
        'networks': ['10.2.1.0/24', '10.2.2.0/24', '10.2.10.0/24'],
        'interfaces': {'eth0': '10.2.1.2/24', 'eth1': '10.2.10.1/24'}
    },
    'br-wifi': {
        'location': 'branch',
        'type': 'access',
        'primary_ip': '10.2.2.3',
        'networks': ['10.2.2.0/24', '10.2.20.0/24'],
        'interfaces': {'eth0': '10.2.2.3/24', 'eth1': '10.2.20.1/24'}
    },
    'dc-gw': {
        'location': 'datacenter',
        'type': 'gateway',
        'primary_ip': '10.3.1.1',
        'external_ip': '192.0.2.10',
        'networks': ['10.3.1.0/24', '10.3.2.0/24'],
        'interfaces': {'eth0': '192.0.2.10/24', 'eth1': '10.3.1.1/24', 'wg0': '10.100.1.3/24'}
    },
    'dc-core': {
        'location': 'datacenter',
        'type': 'core',
        'primary_ip': '10.3.1.2',
        'networks': ['10.3.1.0/24', '10.3.2.0/24', '10.3.10.0/24', '10.3.20.0/24'],
        'interfaces': {'eth0': '10.3.1.2/24', 'eth1': '10.3.10.1/24', 'eth2': '10.3.20.1/24'}
    },
    'dc-srv': {
        'location': 'datacenter',
        'type': 'server',
        'primary_ip': '10.3.20.3',
        'networks': ['10.3.20.0/24'],
        'interfaces': {'eth0': '10.3.20.3/24'}
    }
}

# Additional routing tables
ROUTING_TABLES = {
    'priority_table': 100,
    'service_table': 200,
    'backup_table': 300,
    'qos_table': 400,
    'management_table': 500,
    'database_table': 600,
    'web_table': 700,
    'emergency_table': 800
}

# Service ports for policy routing
SERVICE_PORTS = {
    'ssh': 22,
    'http': 80,
    'https': 443,
    'snmp': 161,
    'syslog': 514,
    'mysql': 3306,
    'postgres': 5432,
    'redis': 6379,
    'mongodb': 27017,
    'ldap': 389,
    'ntp': 123,
    'dns': 53
}

# Network segments by location
LOCATION_NETWORKS = {
    'hq': ['10.1.1.0/24', '10.1.2.0/24', '10.1.3.0/24', '10.1.10.0/24', '10.1.11.0/24'],
    'branch': ['10.2.1.0/24', '10.2.2.0/24', '10.2.10.0/24', '10.2.20.0/24'],
    'datacenter': ['10.3.1.0/24', '10.3.2.0/24', '10.3.10.0/24', '10.3.20.0/24'],
    'vpn': ['10.100.1.0/24']
}


def generate_policy_rules(router_name: str, config: Dict) -> List[str]:
    """Generate complex policy routing rules for a router."""
    
    rules = []
    priority = 50  # Start with high priority
    
    # 1. Source-based policies - Network segment isolation
    location = config['location']
    local_networks = LOCATION_NETWORKS.get(location, [])
    
    # Local traffic uses priority table
    for network in local_networks:
        rules.append(f"{priority}:\tfrom {network} lookup priority_table")
        priority += 1
    
    # Management network gets highest priority
    if location == 'hq':
        rules.append(f"{priority}:\tfrom 10.1.3.0/24 lookup management_table")
        priority += 1
        rules.append(f"{priority}:\tfrom 10.1.3.5/32 lookup priority_table")  # Admin workstation
        priority += 1
    elif location == 'datacenter':
        rules.append(f"{priority}:\tfrom 10.3.20.0/24 lookup management_table")
        priority += 1
    
    # 2. Service-based policies - Port/protocol routing
    
    # Database traffic uses dedicated table
    rules.append(f"{priority}:\tdport 3306 lookup database_table")
    priority += 1
    rules.append(f"{priority}:\tdport 5432 lookup database_table")
    priority += 1
    rules.append(f"{priority}:\tsport 3306 lookup database_table")
    priority += 1
    
    # Web services use web table
    rules.append(f"{priority}:\tdport 80 lookup web_table")
    priority += 1
    rules.append(f"{priority}:\tdport 443 lookup web_table")
    priority += 1
    rules.append(f"{priority}:\tsport 80 lookup web_table")
    priority += 1
    
    # Management protocols use priority table
    rules.append(f"{priority}:\tdport 22 lookup priority_table")
    priority += 1
    rules.append(f"{priority}:\tdport 161 lookup priority_table")
    priority += 1
    rules.append(f"{priority}:\tdport 443 lookup priority_table")
    priority += 1
    
    # 3. QoS-based policies - Packet marking integration
    
    # High priority marked packets
    rules.append(f"{priority}:\tfwmark 0x1 lookup priority_table")
    priority += 1
    rules.append(f"{priority}:\tfwmark 0x2 lookup service_table")
    priority += 1
    rules.append(f"{priority}:\tfwmark 0x3 lookup backup_table")
    priority += 1
    
    # TOS-based routing for real-time traffic
    rules.append(f"{priority}:\ttos 0x10 lookup priority_table")  # High priority
    priority += 1
    rules.append(f"{priority}:\ttos 0x08 lookup qos_table")       # Low delay
    priority += 1
    
    # 4. Advanced combination policies
    
    # Source/destination specific routing
    if config['type'] == 'gateway':
        # Internet-bound traffic
        rules.append(f"{priority}:\tto 0.0.0.0/0 lookup service_table")
        priority += 1
        # VPN traffic prioritization
        rules.append(f"{priority}:\tfrom 10.100.1.0/24 lookup priority_table")
        priority += 1
    
    # Cross-location traffic policies
    if location == 'hq':
        # HQ to DC traffic uses priority paths
        rules.append(f"{priority}:\tto 10.3.0.0/16 lookup priority_table")
        priority += 1
        # HQ to Branch uses service table
        rules.append(f"{priority}:\tto 10.2.0.0/16 lookup service_table")
        priority += 1
    elif location == 'branch':
        # Branch to HQ prioritized
        rules.append(f"{priority}:\tto 10.1.0.0/16 lookup priority_table")
        priority += 1
        # Branch to DC uses backup table
        rules.append(f"{priority}:\tto 10.3.0.0/16 lookup backup_table")
        priority += 1
    elif location == 'datacenter':
        # DC to anywhere uses service optimization
        rules.append(f"{priority}:\tto 10.1.0.0/16 lookup service_table")
        priority += 1
        rules.append(f"{priority}:\tto 10.2.0.0/16 lookup service_table")
        priority += 1
    
    # 5. Router type specific policies
    
    if config['type'] == 'core':
        # Core routers handle inter-VLAN routing
        rules.append(f"{priority}:\tiif lo lookup priority_table")
        priority += 1
        # Load balancing between interfaces
        rules.append(f"{priority}:\toif eth1 lookup service_table")
        priority += 1
        if 'eth2' in config.get('interfaces', {}):
            rules.append(f"{priority}:\toif eth2 lookup backup_table")
            priority += 1
    
    if config['type'] == 'access':
        # Access routers implement security policies
        rules.append(f"{priority}:\tfrom {config['primary_ip']}/32 lookup management_table")
        priority += 1
        # User traffic segmentation
        for network in config.get('networks', []):
            if 'access' in network or '20.0' in network:  # Access networks
                rules.append(f"{priority}:\tfrom {network} lookup qos_table")
                priority += 1
    
    # 6. Emergency and failover policies
    
    # Emergency management access
    rules.append(f"{priority}:\tfrom 192.168.1.0/24 lookup emergency_table")
    priority += 1
    
    # Backup interface policies
    if config['type'] == 'gateway' and 'wg0' in config.get('interfaces', {}):
        rules.append(f"{priority}:\toif wg0 lookup backup_table")
        priority += 1
    
    # 7. Time-sensitive and protocol-specific policies
    
    # ICMP uses priority routing for network diagnostics
    rules.append(f"{priority}:\tipproto icmp lookup priority_table")
    priority += 1
    
    # UDP traffic uses QoS table for real-time apps
    rules.append(f"{priority}:\tipproto udp lookup qos_table")
    priority += 1
    
    # Default fallback to main table
    rules.append("32766:\tfrom all lookup main")
    rules.append("32767:\tfrom all lookup default")
    
    return rules


def generate_routing_table_content(table_name: str, table_id: int, router_name: str, config: Dict) -> List[str]:
    """Generate routing table content for additional tables."""
    
    routes = []
    location = config['location']
    router_type = config['type']
    primary_ip = config['primary_ip']
    
    if table_name == 'priority_table':
        # High-priority routes with optimized paths
        if router_type == 'gateway':
            # Gateway priority routes
            routes.append("default via 203.0.113.1 dev eth0 metric 1")
            routes.append("10.100.1.0/24 dev wg0 proto kernel scope link src 10.100.1.1 metric 1")
        
        # Local high-priority routes
        for network in config.get('networks', []):
            interface = 'eth1' if '10.1.1.0' in network or '10.2.1.0' in network or '10.3.1.0' in network else 'eth0'
            routes.append(f"{network} dev {interface} proto kernel scope link metric 1")
        
        # Cross-location priority paths
        if location == 'hq':
            routes.append("10.2.0.0/16 via 10.1.1.1 dev eth0 metric 5")
            routes.append("10.3.0.0/16 via 10.1.1.1 dev eth0 metric 5")
        elif location == 'branch':
            routes.append("10.1.0.0/16 via 10.2.1.1 dev eth0 metric 5")
            routes.append("10.3.0.0/16 via 10.2.1.1 dev eth0 metric 10")
        elif location == 'datacenter':
            routes.append("10.1.0.0/16 via 10.3.1.1 dev eth0 metric 5")
            routes.append("10.2.0.0/16 via 10.3.1.1 dev eth0 metric 5")
    
    elif table_name == 'service_table':
        # Service-optimized routes
        if router_type == 'gateway':
            routes.append("default via 203.0.113.1 dev eth0 metric 10")
        
        # Service-specific routes with load balancing
        for network in config.get('networks', []):
            routes.append(f"{network} dev eth1 proto kernel scope link metric 10")
        
        # Database service routes
        if location == 'datacenter':
            routes.append("10.3.20.0/24 dev eth2 proto kernel scope link metric 5")
            routes.append("10.1.0.0/16 via 10.3.1.1 dev eth0 metric 15")
            routes.append("10.2.0.0/16 via 10.3.1.1 dev eth0 metric 15")
        
        # Web service routes
        if location == 'hq':
            routes.append("10.1.3.0/24 dev eth1 proto kernel scope link metric 5")
            routes.append("10.2.0.0/16 via 10.1.1.1 dev eth0 metric 15")
            routes.append("10.3.0.0/16 via 10.1.1.1 dev eth0 metric 15")
    
    elif table_name == 'backup_table':
        # Backup and failover routes
        if router_type == 'gateway':
            # Backup internet route
            routes.append("default via 203.0.113.1 dev eth0 metric 20")
            # VPN backup paths
            routes.append("10.100.1.0/24 dev wg0 proto kernel scope link metric 20")
        
        # Backup paths with higher metrics
        for network in config.get('networks', []):
            routes.append(f"{network} dev eth1 proto kernel scope link metric 20")
        
        # Cross-location backup routes
        if location == 'hq':
            routes.append("10.2.0.0/16 via 10.100.1.2 dev wg0 metric 25")  # Via VPN
            routes.append("10.3.0.0/16 via 10.100.1.3 dev wg0 metric 25")
        elif location == 'branch':
            routes.append("10.1.0.0/16 via 10.100.1.1 dev wg0 metric 25")
            routes.append("10.3.0.0/16 via 10.100.1.3 dev wg0 metric 25")
        elif location == 'datacenter':
            routes.append("10.1.0.0/16 via 10.100.1.1 dev wg0 metric 25")
            routes.append("10.2.0.0/16 via 10.100.1.2 dev wg0 metric 25")
    
    elif table_name == 'qos_table':
        # QoS-optimized routes with specific metrics
        for network in config.get('networks', []):
            routes.append(f"{network} dev eth1 proto kernel scope link metric 8")
        
        # Real-time traffic optimization
        if location == 'hq':
            routes.append("10.2.0.0/16 via 10.1.1.1 dev eth0 metric 8")
            routes.append("10.3.0.0/16 via 10.1.1.1 dev eth0 metric 8")
        elif location == 'branch':
            routes.append("10.1.0.0/16 via 10.2.1.1 dev eth0 metric 8")
            routes.append("10.3.0.0/16 via 10.2.1.1 dev eth0 metric 12")
        elif location == 'datacenter':
            routes.append("10.1.0.0/16 via 10.3.1.1 dev eth0 metric 8")
            routes.append("10.2.0.0/16 via 10.3.1.1 dev eth0 metric 8")
    
    elif table_name == 'management_table':
        # Management-specific routes
        for network in config.get('networks', []):
            routes.append(f"{network} dev eth0 proto kernel scope link metric 1")
        
        # Management access routes
        if location == 'hq':
            routes.append("10.1.3.0/24 dev eth1 proto kernel scope link metric 1")
            routes.append("10.2.0.0/16 via 10.1.1.1 dev eth0 metric 5")
            routes.append("10.3.0.0/16 via 10.1.1.1 dev eth0 metric 5")
        elif location == 'datacenter':
            routes.append("10.3.20.0/24 dev eth2 proto kernel scope link metric 1")
            routes.append("10.1.0.0/16 via 10.3.1.1 dev eth0 metric 5")
            routes.append("10.2.0.0/16 via 10.3.1.1 dev eth0 metric 5")
    
    elif table_name == 'database_table':
        # Database-specific routing
        if location == 'datacenter':
            routes.append("10.3.20.0/24 dev eth2 proto kernel scope link metric 1")
            routes.append("10.3.10.0/24 dev eth1 proto kernel scope link metric 1")
        
        # Database client routes
        routes.append("10.1.0.0/16 via 10.3.1.1 dev eth0 metric 5")
        routes.append("10.2.0.0/16 via 10.3.1.1 dev eth0 metric 10")
        
        # Backup database routes
        if router_type == 'core':
            for network in config.get('networks', []):
                routes.append(f"{network} dev eth1 proto kernel scope link metric 5")
    
    elif table_name == 'web_table':
        # Web service routing
        if location == 'hq':
            routes.append("10.1.3.0/24 dev eth1 proto kernel scope link metric 1")  # DMZ
        elif location == 'datacenter':
            routes.append("10.3.2.0/24 dev eth0 proto kernel scope link metric 1")   # Web servers
        
        # Client access routes
        for network in config.get('networks', []):
            routes.append(f"{network} dev eth1 proto kernel scope link metric 5")
        
        # Inter-location web access
        if location == 'hq':
            routes.append("10.2.0.0/16 via 10.1.1.1 dev eth0 metric 10")
            routes.append("10.3.0.0/16 via 10.1.1.1 dev eth0 metric 10")
    
    elif table_name == 'emergency_table':
        # Emergency access routes
        routes.append("192.168.1.0/24 dev eth0 proto kernel scope link metric 1")
        
        # Emergency paths to all networks
        for network in config.get('networks', []):
            routes.append(f"{network} dev eth1 proto kernel scope link metric 1")
        
        # Emergency default route
        if router_type == 'gateway':
            routes.append("default via 203.0.113.1 dev eth0 metric 1")
    
    return routes


def update_raw_facts_file(file_path: str, router_name: str):
    """Update a raw facts file with enhanced policy routing."""
    
    print(f"Processing {router_name} ({file_path})")
    
    if router_name not in NETWORK_CONFIG:
        print(f"Warning: {router_name} not in network configuration")
        return
    
    config = NETWORK_CONFIG[router_name]
    
    # Read the original file
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Generate policy rules
    policy_rules = generate_policy_rules(router_name, config)
    
    # Generate additional routing tables
    routing_tables_content = {}
    for table_name, table_id in ROUTING_TABLES.items():
        routes = generate_routing_table_content(table_name, table_id, router_name, config)
        if routes:  # Only add tables that have routes
            routing_tables_content[table_name] = routes
    
    # Create enhanced policy rules section
    policy_rules_section = "\\n".join(policy_rules)
    
    # Replace policy_rules section
    policy_pattern = r'=== TSIM_SECTION_START:policy_rules ===.*?=== TSIM_SECTION_END:policy_rules ==='
    policy_replacement = f"""=== TSIM_SECTION_START:policy_rules ===
TITLE: IP Policy Rules
COMMAND: /sbin/ip rule show
TIMESTAMP: 2025-07-01 10:00:00
---
0:\tfrom all lookup local
{policy_rules_section}

EXIT_CODE: 0
=== TSIM_SECTION_END:policy_rules ==="""
    
    content = re.sub(policy_pattern, policy_replacement, content, flags=re.DOTALL)
    
    # Add additional routing table sections
    insert_point = content.find("=== TSIM_SECTION_START:interfaces ===")
    if insert_point != -1:
        additional_sections = []
        
        for table_name, routes in routing_tables_content.items():
            table_content = "\\n".join(routes)
            section = f"""
=== TSIM_SECTION_START:routing_table_{table_name} ===
TITLE: IP Routing Table {table_name.title().replace('_', ' ')} ({ROUTING_TABLES[table_name]})
COMMAND: /sbin/ip route show table {ROUTING_TABLES[table_name]}
TIMESTAMP: 2025-07-01 10:00:00
---
{table_content}

EXIT_CODE: 0
=== TSIM_SECTION_END:routing_table_{table_name} ===
"""
            additional_sections.append(section)
        
        # Insert additional sections before interfaces
        if additional_sections:
            content = content[:insert_point] + "\\n".join(additional_sections) + "\\n" + content[insert_point:]
    
    # Write the updated content
    with open(file_path, 'w') as f:
        f.write(content)
    
    print(f"Updated {router_name} with {len(policy_rules)} policy rules and {len(routing_tables_content)} routing tables")


def main():
    """Main function to process all raw facts files."""
    
    script_dir = Path(__file__).parent
    raw_facts_dir = script_dir.parent / "tests" / "raw_facts"
    
    if not raw_facts_dir.exists():
        print(f"Error: Raw facts directory not found: {raw_facts_dir}")
        sys.exit(1)
    
    print("Enhanced Policy Routing Generator")
    print("================================")
    print(f"Processing {len(NETWORK_CONFIG)} routers...")
    print(f"Adding {len(ROUTING_TABLES)} additional routing tables per router")
    print()
    
    total_rules = 0
    total_tables = 0
    
    # Process all raw facts files
    for file_path in raw_facts_dir.glob("*_facts.txt"):
        router_name = file_path.stem.replace("_facts", "")
        if router_name in NETWORK_CONFIG:
            update_raw_facts_file(str(file_path), router_name)
            # Count rules for this router
            rules = generate_policy_rules(router_name, NETWORK_CONFIG[router_name])
            tables = len([t for t in ROUTING_TABLES.keys() 
                         if generate_routing_table_content(t, ROUTING_TABLES[t], router_name, NETWORK_CONFIG[router_name])])
            total_rules += len(rules)
            total_tables += tables
        else:
            print(f"Skipping {router_name} (not in configuration)")
    
    print()
    print("Enhanced policy routing generation completed!")
    print("=" * 50)
    print(f"✅ Total policy rules added: {total_rules}")
    print(f"✅ Total routing tables added: {total_tables}")
    print(f"✅ Average rules per router: {total_rules // len(NETWORK_CONFIG)}")
    print(f"✅ Average tables per router: {total_tables // len(NETWORK_CONFIG)}")
    print()
    print("Policy routing features implemented:")
    print("  • Source-based routing (network segmentation)")
    print("  • Service-based routing (port/protocol specific)")
    print("  • QoS-based routing (priority and TOS)")
    print("  • Mark-based routing (packet marking integration)")
    print("  • Location-based routing (cross-site policies)")
    print("  • Type-based routing (router role specific)")
    print("  • Emergency routing (failover scenarios)")
    print("  • Load balancing routing (multi-path)")


if __name__ == "__main__":
    main()