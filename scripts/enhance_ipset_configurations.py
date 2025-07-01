#!/usr/bin/env python3
"""
Enhanced Ipset Configurations Generator for Raw Facts Files

This script augments all raw fact files with comprehensive ipset examples
covering all possible valid syntax types from the ipset documentation.
Creates the most complex and comprehensive ipset configurations possible.
"""

import os
import sys
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Set
import json
import random

# Network topology configuration
NETWORK_CONFIG = {
    'hq-gw': {
        'location': 'hq',
        'type': 'gateway',
        'networks': ['10.1.1.0/24', '10.1.2.0/24'],
        'external_ip': '203.0.113.10/24',
        'role': 'internet_gateway'
    },
    'hq-core': {
        'location': 'hq',
        'type': 'core',
        'networks': ['10.1.1.0/24', '10.1.2.0/24', '10.1.10.0/24', '10.1.11.0/24'],
        'role': 'core_router'
    },
    'hq-dmz': {
        'location': 'hq',
        'type': 'access',
        'networks': ['10.1.2.0/24', '10.1.3.0/24'],
        'role': 'dmz_access'
    },
    'hq-lab': {
        'location': 'hq',
        'type': 'access',
        'networks': ['10.1.11.0/24'],
        'role': 'lab_access'
    },
    'br-gw': {
        'location': 'branch',
        'type': 'gateway',
        'networks': ['10.2.1.0/24', '10.2.2.0/24'],
        'external_ip': '198.51.100.10/24',
        'role': 'branch_gateway'
    },
    'br-core': {
        'location': 'branch',
        'type': 'core',
        'networks': ['10.2.1.0/24', '10.2.2.0/24', '10.2.10.0/24'],
        'role': 'branch_core'
    },
    'br-wifi': {
        'location': 'branch',
        'type': 'access',
        'networks': ['10.2.2.0/24', '10.2.20.0/24'],
        'role': 'wifi_access'
    },
    'dc-gw': {
        'location': 'datacenter',
        'type': 'gateway',
        'networks': ['10.3.1.0/24', '10.3.2.0/24'],
        'external_ip': '192.0.2.10/24',
        'role': 'datacenter_gateway'
    },
    'dc-core': {
        'location': 'datacenter',
        'type': 'core',
        'networks': ['10.3.1.0/24', '10.3.2.0/24', '10.3.10.0/24', '10.3.20.0/24'],
        'role': 'datacenter_core'
    },
    'dc-srv': {
        'location': 'datacenter',
        'type': 'server',
        'networks': ['10.3.20.0/24'],
        'role': 'server_access'
    }
}

# Predefined MAC addresses for different device types
DEVICE_MACS = {
    'infrastructure': [
        '52:54:00:12:34:56', '52:54:00:12:34:57', '52:54:00:12:34:58',
        '52:54:00:12:34:59', '52:54:00:12:34:5a', '52:54:00:12:34:5b'
    ],
    'workstations': [
        '52:54:00:ab:cd:01', '52:54:00:ab:cd:02', '52:54:00:ab:cd:03',
        '52:54:00:ab:cd:04', '52:54:00:ab:cd:05', '52:54:00:ab:cd:06'
    ],
    'servers': [
        '52:54:00:ef:12:01', '52:54:00:ef:12:02', '52:54:00:ef:12:03',
        '52:54:00:ef:12:04', '52:54:00:ef:12:05', '52:54:00:ef:12:06'
    ],
    'wireless': [
        '52:54:00:wi:fi:01', '52:54:00:wi:fi:02', '52:54:00:wi:fi:03',
        '52:54:00:wi:fi:04', '52:54:00:wi:fi:05', '52:54:00:wi:fi:06'
    ]
}

# Service port definitions
SERVICE_PORTS = {
    'web': [80, 443, 8080, 8443],
    'database': [3306, 5432, 6379, 27017],
    'management': [22, 161, 443, 514, 8080],
    'dns': [53, 853],
    'mail': [25, 110, 143, 465, 587, 993, 995],
    'ldap': [389, 636],
    'monitoring': [161, 162, 9090, 9100, 3000],
    'backup': [873, 10080],
    'file_sharing': [445, 2049],
    'vpn': [1194, 4500, 500]
}

# Network ranges for different purposes
NETWORK_RANGES = {
    'internal': ['10.1.0.0/16', '10.2.0.0/16', '10.3.0.0/16', '10.100.1.0/24'],
    'external': ['8.8.8.0/24', '1.1.1.0/24', '208.67.222.0/24', '149.112.112.0/24'],
    'partner': ['172.16.1.0/24', '172.16.2.0/24', '172.16.3.0/24'],
    'guest': ['192.168.100.0/24', '192.168.101.0/24'],
    'management': ['10.1.10.0/24', '10.2.10.0/24', '10.3.10.0/24'],
    'dmz': ['10.1.3.0/24', '10.2.3.0/24', '10.3.3.0/24']
}


def generate_bitmap_ip_sets(router_name: str, config: Dict) -> List[str]:
    """Generate bitmap:ip type ipsets."""
    sets = []
    location = config['location']
    router_type = config['type']
    
    # Internal network hosts (bitmap:ip)
    for network in config.get('networks', []):
        network_name = network.replace('.', '_').replace('/', '_')
        set_name = f"{location}_{network_name}_hosts"
        sets.append(f"create {set_name} bitmap:ip range {network} timeout 3600 counters comment")
    
    # Management networks
    if location == 'hq':
        sets.append("create hq_mgmt_networks bitmap:ip range 10.1.2.0-10.1.5.255 counters comment")
        sets.append("create hq_admin_workstations bitmap:ip range 10.1.3.10-10.1.3.20 timeout 7200")
    elif location == 'branch':
        sets.append("create br_mgmt_networks bitmap:ip range 10.2.2.0-10.2.5.255 counters")
        sets.append("create br_admin_workstations bitmap:ip range 10.2.10.10-10.2.10.20 timeout 7200")
    elif location == 'datacenter':
        sets.append("create dc_mgmt_networks bitmap:ip range 10.3.1.0-10.3.5.255 counters comment")
        sets.append("create dc_admin_workstations bitmap:ip range 10.3.10.10-10.3.10.20 timeout 3600")
    
    # Router type specific sets
    if router_type == 'gateway':
        sets.append(f"create {location}_internet_ranges bitmap:ip range 8.8.8.0/24 timeout 1800")
        sets.append(f"create {location}_dns_servers bitmap:ip range 1.1.1.0-1.1.1.10 counters")
        sets.append(f"create {location}_ntp_servers bitmap:ip range 129.6.15.28-129.6.15.30")
    elif router_type == 'core':
        sets.append(f"create {location}_core_services bitmap:ip range 10.{location[0]}.10.0/24 timeout 3600")
        sets.append(f"create {location}_load_balancers bitmap:ip range 10.{location[0]}.1.10-10.{location[0]}.1.20")
    elif router_type == 'access' or router_type == 'server':
        sets.append(f"create {location}_access_clients bitmap:ip range 10.{location[0]}.20.0/24 timeout 1800")
        sets.append(f"create {location}_guest_range bitmap:ip range 192.168.100.0/24 timeout 900")
    
    return sets


def generate_bitmap_ip_mac_sets(router_name: str, config: Dict) -> List[str]:
    """Generate bitmap:ip,mac type ipsets."""
    sets = []
    location = config['location']
    router_type = config['type']
    
    # Secure client authentication
    for network in config.get('networks', []):
        network_name = network.replace('.', '_').replace('/', '_')
        set_name = f"{location}_{network_name}_secure_clients"
        sets.append(f"create {set_name} bitmap:ip,mac range {network} timeout 7200 counters comment")
    
    # Trusted devices
    sets.append(f"create {location}_trusted_devices bitmap:ip,mac range 10.{location[0]}.1.0/24 counters comment")
    
    # DHCP reservations
    if router_type == 'access' or 'wifi' in config.get('role', ''):
        sets.append(f"create {location}_dhcp_reservations bitmap:ip,mac range 10.{location[0]}.20.0/24 timeout 86400")
        sets.append(f"create {location}_static_assignments bitmap:ip,mac range 10.{location[0]}.10.0/24")
    
    # Infrastructure devices
    if router_type == 'core':
        sets.append(f"create {location}_infrastructure_devices bitmap:ip,mac range 10.{location[0]}.1.0/24 comment")
        sets.append(f"create {location}_switch_management bitmap:ip,mac range 10.{location[0]}.10.0/24 timeout 3600")
    
    # Guest network devices
    if 'wifi' in config.get('role', '') or router_type == 'access':
        sets.append(f"create {location}_guest_devices bitmap:ip,mac range 192.168.100.0/24 timeout 1800")
        sets.append(f"create {location}_temp_access bitmap:ip,mac range 192.168.101.0/24 timeout 900")
    
    return sets


def generate_bitmap_port_sets(router_name: str, config: Dict) -> List[str]:
    """Generate bitmap:port type ipsets."""
    sets = []
    location = config['location']
    router_type = config['type']
    
    # Service port groups
    sets.append(f"create {location}_web_ports bitmap:port range 80-8080 timeout 1800 comment")
    sets.append(f"create {location}_database_ports bitmap:port range 3306-5432 counters comment")
    sets.append(f"create {location}_management_ports bitmap:port range 22-443 comment")
    sets.append(f"create {location}_monitoring_ports bitmap:port range 161-162 timeout 3600")
    
    # Extended service ranges
    sets.append(f"create {location}_mail_ports bitmap:port range 25-995 timeout 7200")
    sets.append(f"create {location}_file_ports bitmap:port range 445-2049 counters")
    sets.append(f"create {location}_backup_ports bitmap:port range 873-10080 timeout 3600")
    
    # Dynamic port ranges
    sets.append(f"create {location}_ephemeral_ports bitmap:port range 32768-65535 timeout 300")
    sets.append(f"create {location}_high_ports bitmap:port range 8000-9999 timeout 1800 counters")
    
    # Router type specific ports
    if router_type == 'gateway':
        sets.append(f"create {location}_vpn_ports bitmap:port range 500-4500 counters comment")
        sets.append(f"create {location}_tunnel_ports bitmap:port range 1194-1200 timeout 7200")
    elif router_type == 'core':
        sets.append(f"create {location}_routing_ports bitmap:port range 179-520 comment")
        sets.append(f"create {location}_cluster_ports bitmap:port range 2379-2380 timeout 3600")
    elif 'server' in config.get('role', ''):
        sets.append(f"create {location}_app_ports bitmap:port range 3000-3999 timeout 1800 counters")
        sets.append(f"create {location}_db_cluster_ports bitmap:port range 4567-4568 comment")
    
    return sets


def generate_hash_ip_sets(router_name: str, config: Dict) -> List[str]:
    """Generate hash:ip type ipsets."""
    sets = []
    location = config['location']
    router_type = config['type']
    
    # Network categorization
    sets.append(f"create {location}_management_ips hash:ip family inet timeout 3600 counters comment")
    sets.append(f"create {location}_trusted_sources hash:ip family inet hashsize 1024 comment")
    sets.append(f"create {location}_monitoring_agents hash:ip family inet timeout 1800 counters")
    sets.append(f"create {location}_admin_workstations hash:ip family inet timeout 7200 comment")
    
    # Security lists
    sets.append(f"create {location}_blacklisted_ips hash:ip family inet comment maxelem 65536")
    sets.append(f"create {location}_suspicious_sources hash:ip family inet timeout 3600 maxelem 4096")
    sets.append(f"create {location}_rate_limited_ips hash:ip family inet timeout 900 counters")
    
    # Service-specific IPs
    sets.append(f"create {location}_dns_resolvers hash:ip family inet comment maxelem 256")
    sets.append(f"create {location}_ntp_servers hash:ip family inet timeout 86400")
    sets.append(f"create {location}_log_collectors hash:ip family inet timeout 3600 counters")
    
    # Router type specific
    if router_type == 'gateway':
        sets.append(f"create {location}_external_partners hash:ip family inet timeout 7200 comment")
        sets.append(f"create {location}_cdn_networks hash:ip family inet maxelem 1024")
        sets.append(f"create {location}_vpn_endpoints hash:ip family inet timeout 3600 counters")
    elif router_type == 'core':
        sets.append(f"create {location}_core_switches hash:ip family inet comment")
        sets.append(f"create {location}_vlan_gateways hash:ip family inet timeout 3600")
        sets.append(f"create {location}_load_balancer_vips hash:ip family inet counters")
    elif 'server' in config.get('role', ''):
        sets.append(f"create {location}_database_servers hash:ip family inet comment")
        sets.append(f"create {location}_app_servers hash:ip family inet timeout 1800 counters")
        sets.append(f"create {location}_backup_agents hash:ip family inet timeout 3600")
    
    return sets


def generate_hash_mac_sets(router_name: str, config: Dict) -> List[str]:
    """Generate hash:mac type ipsets."""
    sets = []
    location = config['location']
    router_type = config['type']
    
    # Device tracking
    sets.append(f"create {location}_known_devices hash:mac timeout 86400 counters comment")
    sets.append(f"create {location}_infrastructure_macs hash:mac maxelem 1024 comment")
    sets.append(f"create {location}_approved_devices hash:mac timeout 7200 counters")
    
    # Wireless specific
    if 'wifi' in config.get('role', '') or router_type == 'access':
        sets.append(f"create {location}_wireless_clients hash:mac timeout 3600 comment maxelem 2048")
        sets.append(f"create {location}_guest_devices hash:mac timeout 1800 counters")
        sets.append(f"create {location}_corporate_devices hash:mac timeout 7200 comment")
    
    # Security tracking
    sets.append(f"create {location}_quarantined_macs hash:mac timeout 3600 comment")
    sets.append(f"create {location}_blocked_devices hash:mac comment maxelem 4096")
    
    # Management devices
    if router_type == 'core':
        sets.append(f"create {location}_switch_macs hash:mac comment maxelem 256")
        sets.append(f"create {location}_ap_macs hash:mac timeout 3600 counters")
        sets.append(f"create {location}_router_macs hash:mac comment")
    
    return sets


def generate_hash_net_sets(router_name: str, config: Dict) -> List[str]:
    """Generate hash:net type ipsets."""
    sets = []
    location = config['location']
    router_type = config['type']
    
    # Network groups
    sets.append(f"create {location}_internal_networks hash:net family inet maxelem 256 comment")
    sets.append(f"create {location}_trusted_networks hash:net family inet timeout 7200 counters")
    sets.append(f"create {location}_management_networks hash:net family inet comment")
    
    # External networks
    sets.append(f"create {location}_external_partners hash:net family inet timeout 7200 comment")
    sets.append(f"create {location}_cloud_networks hash:net family inet maxelem 1024")
    sets.append(f"create {location}_cdn_ranges hash:net family inet timeout 3600")
    
    # VPN networks
    sets.append(f"create {location}_vpn_networks hash:net family inet counters comment")
    sets.append(f"create {location}_site_networks hash:net family inet timeout 1800")
    
    # Security networks
    sets.append(f"create {location}_blocked_networks hash:net family inet comment maxelem 4096")
    sets.append(f"create {location}_quarantine_networks hash:net family inet timeout 3600")
    
    # Router type specific
    if router_type == 'gateway':
        sets.append(f"create {location}_internet_ranges hash:net family inet maxelem 2048")
        sets.append(f"create {location}_isp_networks hash:net family inet comment")
        sets.append(f"create {location}_peering_networks hash:net family inet timeout 7200")
    elif router_type == 'core':
        sets.append(f"create {location}_vlan_networks hash:net family inet comment")
        sets.append(f"create {location}_subnet_ranges hash:net family inet counters")
    
    return sets


def generate_hash_ip_port_sets(router_name: str, config: Dict) -> List[str]:
    """Generate hash:ip,port type ipsets."""
    sets = []
    location = config['location']
    router_type = config['type']
    
    # Service-specific access
    sets.append(f"create {location}_web_services hash:ip,port family inet timeout 7200 counters comment")
    sets.append(f"create {location}_database_access hash:ip,port family inet counters comment")
    sets.append(f"create {location}_management_access hash:ip,port family inet comment maxelem 1024")
    sets.append(f"create {location}_monitoring_endpoints hash:ip,port family inet timeout 1800")
    
    # Application services
    sets.append(f"create {location}_api_endpoints hash:ip,port family inet timeout 3600 counters")
    sets.append(f"create {location}_file_services hash:ip,port family inet comment")
    sets.append(f"create {location}_backup_services hash:ip,port family inet timeout 7200")
    
    # Security services
    sets.append(f"create {location}_auth_services hash:ip,port family inet timeout 1800 counters")
    sets.append(f"create {location}_log_services hash:ip,port family inet comment")
    
    # Router type specific
    if router_type == 'gateway':
        sets.append(f"create {location}_vpn_services hash:ip,port family inet timeout 3600 comment")
        sets.append(f"create {location}_public_services hash:ip,port family inet counters")
    elif 'server' in config.get('role', ''):
        sets.append(f"create {location}_app_instances hash:ip,port family inet timeout 1800 counters")
        sets.append(f"create {location}_db_instances hash:ip,port family inet comment")
        sets.append(f"create {location}_cluster_endpoints hash:ip,port family inet timeout 3600")
    
    return sets


def generate_hash_net_iface_sets(router_name: str, config: Dict) -> List[str]:
    """Generate hash:net,iface type ipsets."""
    sets = []
    location = config['location']
    router_type = config['type']
    
    # Interface-specific networks
    sets.append(f"create {location}_interface_networks hash:net,iface family inet comment")
    sets.append(f"create {location}_vlan_interfaces hash:net,iface family inet timeout 1800 counters")
    sets.append(f"create {location}_trusted_vlans hash:net,iface family inet comment")
    
    # Security zones
    sets.append(f"create {location}_dmz_interfaces hash:net,iface family inet counters comment")
    sets.append(f"create {location}_secure_zones hash:net,iface family inet timeout 3600")
    
    # Router type specific
    if router_type == 'gateway':
        sets.append(f"create {location}_external_interfaces hash:net,iface family inet comment")
        sets.append(f"create {location}_vpn_interfaces hash:net,iface family inet timeout 7200")
    elif router_type == 'core':
        sets.append(f"create {location}_trunk_interfaces hash:net,iface family inet comment")
        sets.append(f"create {location}_access_interfaces hash:net,iface family inet counters")
    elif router_type == 'access':
        sets.append(f"create {location}_client_interfaces hash:net,iface family inet timeout 1800")
        sets.append(f"create {location}_guest_interfaces hash:net,iface family inet timeout 900 comment")
    
    return sets


def generate_advanced_hash_sets(router_name: str, config: Dict) -> List[str]:
    """Generate advanced multi-dimensional hash sets."""
    sets = []
    location = config['location']
    router_type = config['type']
    
    # Complex matching rules (hash:ip,port,net)
    sets.append(f"create {location}_service_matrix hash:ip,port,net family inet timeout 600 maxelem 2048")
    sets.append(f"create {location}_access_rules hash:ip,port,net family inet counters comment")
    
    # Advanced filtering (hash:ip,port,ip)
    sets.append(f"create {location}_proxy_rules hash:ip,port,ip family inet timeout 1800 counters")
    sets.append(f"create {location}_nat_rules hash:ip,port,ip family inet comment maxelem 4096")
    
    # Network service mapping (hash:net,port,net)
    sets.append(f"create {location}_routing_matrix hash:net,port,net family inet counters comment")
    
    # Router type specific advanced sets
    if router_type == 'gateway':
        sets.append(f"create {location}_firewall_rules hash:ip,port,net family inet timeout 3600 comment")
        sets.append(f"create {location}_load_balance_rules hash:ip,port,ip family inet counters")
    elif router_type == 'core':
        sets.append(f"create {location}_switching_matrix hash:ip,port,net family inet comment")
        sets.append(f"create {location}_vlan_rules hash:net,port,net family inet timeout 1800")
    
    return sets


def generate_ipset_entries(router_name: str, config: Dict) -> List[str]:
    """Generate sample ipset entries for population."""
    entries = []
    location = config['location']
    
    # Add sample entries for bitmap:ip sets
    entries.append(f"add {location}_10_1_1_0_24_hosts 10.1.1.10")
    entries.append(f"add {location}_10_1_1_0_24_hosts 10.1.1.11") 
    entries.append(f"add {location}_10_1_1_0_24_hosts 10.1.1.12")
    
    # Add sample entries for hash:ip sets
    entries.append(f"add {location}_management_ips 10.{location[0]}.10.5")
    entries.append(f"add {location}_management_ips 10.{location[0]}.10.6")
    entries.append(f"add {location}_trusted_sources 8.8.8.8")
    entries.append(f"add {location}_trusted_sources 1.1.1.1")
    
    # Add sample entries for hash:net sets
    entries.append(f"add {location}_internal_networks 10.{location[0]}.0.0/16")
    entries.append(f"add {location}_vpn_networks 10.100.1.0/24")
    
    # Add sample entries for bitmap:ip,mac sets
    if location == 'hq':
        entries.append(f"add {location}_trusted_devices 10.1.1.10,52:54:00:12:34:56")
        entries.append(f"add {location}_trusted_devices 10.1.1.11,52:54:00:12:34:57")
    elif location == 'branch':
        entries.append(f"add {location}_trusted_devices 10.2.1.10,52:54:00:ab:cd:01")
        entries.append(f"add {location}_trusted_devices 10.2.1.11,52:54:00:ab:cd:02")
    elif location == 'datacenter':
        entries.append(f"add {location}_trusted_devices 10.3.1.10,52:54:00:ef:12:01")
        entries.append(f"add {location}_trusted_devices 10.3.1.11,52:54:00:ef:12:02")
    
    # Add sample entries for hash:ip,port sets
    entries.append(f"add {location}_web_services 10.{location[0]}.3.10,80")
    entries.append(f"add {location}_web_services 10.{location[0]}.3.10,443")
    entries.append(f"add {location}_database_access 10.{location[0]}.20.5,3306")
    entries.append(f"add {location}_database_access 10.{location[0]}.20.5,5432")
    
    # Add sample entries for bitmap:port sets
    entries.append(f"add {location}_web_ports 80")
    entries.append(f"add {location}_web_ports 443")
    entries.append(f"add {location}_web_ports 8080")
    entries.append(f"add {location}_database_ports 3306")
    entries.append(f"add {location}_database_ports 5432")
    
    return entries


def generate_ipset_lists_section(router_name: str, config: Dict) -> str:
    """Generate the complete ipset list section."""
    
    # Generate all ipset types
    all_sets = []
    all_sets.extend(generate_bitmap_ip_sets(router_name, config))
    all_sets.extend(generate_bitmap_ip_mac_sets(router_name, config))
    all_sets.extend(generate_bitmap_port_sets(router_name, config))
    all_sets.extend(generate_hash_ip_sets(router_name, config))
    all_sets.extend(generate_hash_mac_sets(router_name, config))
    all_sets.extend(generate_hash_net_sets(router_name, config))
    all_sets.extend(generate_hash_ip_port_sets(router_name, config))
    all_sets.extend(generate_hash_net_iface_sets(router_name, config))
    all_sets.extend(generate_advanced_hash_sets(router_name, config))
    
    # Format as ipset list output
    output_lines = []
    for ipset_cmd in all_sets:
        set_name = ipset_cmd.split()[1]
        set_type = ' '.join(ipset_cmd.split()[2:4])  # e.g., "bitmap:ip range"
        
        # Format as "ipset list" output
        output_lines.append(f"Name: {set_name}")
        output_lines.append(f"Type: {set_type.split()[0]}")
        output_lines.append("Revision: 3")
        output_lines.append("Header: " + ' '.join(ipset_cmd.split()[2:]))
        output_lines.append("Size in memory: 1048")
        output_lines.append("References: 1")
        output_lines.append("Default binding: ")
        output_lines.append("Number of entries: 0")
        output_lines.append("Members:")
        output_lines.append("")  # Empty line between sets
    
    return "\\n".join(output_lines)


def generate_ipset_save_section(router_name: str, config: Dict) -> str:
    """Generate the ipset save section."""
    
    # Generate all ipset types
    all_sets = []
    all_sets.extend(generate_bitmap_ip_sets(router_name, config))
    all_sets.extend(generate_bitmap_ip_mac_sets(router_name, config))
    all_sets.extend(generate_bitmap_port_sets(router_name, config))
    all_sets.extend(generate_hash_ip_sets(router_name, config))
    all_sets.extend(generate_hash_mac_sets(router_name, config))
    all_sets.extend(generate_hash_net_sets(router_name, config))
    all_sets.extend(generate_hash_ip_port_sets(router_name, config))
    all_sets.extend(generate_hash_net_iface_sets(router_name, config))
    all_sets.extend(generate_advanced_hash_sets(router_name, config))
    
    # Generate sample entries
    entries = generate_ipset_entries(router_name, config)
    
    # Format as ipset save output
    output_lines = []
    
    # Create commands
    for ipset_cmd in all_sets:
        output_lines.append(ipset_cmd)
    
    # Add commands
    for entry_cmd in entries:
        output_lines.append(entry_cmd)
    
    output_lines.append("COMMIT")
    
    return "\\n".join(output_lines)


def update_raw_facts_file(file_path: str, router_name: str):
    """Update a raw facts file with enhanced ipset configurations."""
    
    print(f"Processing {router_name} ({file_path})")
    
    if router_name not in NETWORK_CONFIG:
        print(f"Warning: {router_name} not in network configuration")
        return
    
    config = NETWORK_CONFIG[router_name]
    
    # Read the original file
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Generate ipset content
    ipset_list_content = generate_ipset_lists_section(router_name, config)
    ipset_save_content = generate_ipset_save_section(router_name, config)
    
    # Replace or add ipset sections
    patterns = [
        (r'=== TSIM_SECTION_START:ipset_list ===.*?=== TSIM_SECTION_END:ipset_list ===',
         f"""=== TSIM_SECTION_START:ipset_list ===
TITLE: Ipset List Output
COMMAND: /sbin/ipset list
TIMESTAMP: 2025-07-01 10:00:00
---
{ipset_list_content}

EXIT_CODE: 0
=== TSIM_SECTION_END:ipset_list ==="""),
        
        (r'=== TSIM_SECTION_START:ipset_save ===.*?=== TSIM_SECTION_END:ipset_save ===',
         f"""=== TSIM_SECTION_START:ipset_save ===
TITLE: Ipset Save Output
COMMAND: /sbin/ipset save
TIMESTAMP: 2025-07-01 10:00:00
---
{ipset_save_content}

EXIT_CODE: 0
=== TSIM_SECTION_END:ipset_save ===""")
    ]
    
    # Apply replacements or add new sections
    for pattern, replacement in patterns:
        if re.search(pattern, content, re.DOTALL):
            content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        else:
            # Add new section before conntrack if ipset section doesn't exist
            insert_point = content.find("=== TSIM_SECTION_START:conntrack ===")
            if insert_point != -1:
                content = content[:insert_point] + replacement + "\\n\\n" + content[insert_point:]
    
    # Write the updated content
    with open(file_path, 'w') as f:
        f.write(content)
    
    # Count generated sets
    all_sets = []
    all_sets.extend(generate_bitmap_ip_sets(router_name, config))
    all_sets.extend(generate_bitmap_ip_mac_sets(router_name, config))
    all_sets.extend(generate_bitmap_port_sets(router_name, config))
    all_sets.extend(generate_hash_ip_sets(router_name, config))
    all_sets.extend(generate_hash_mac_sets(router_name, config))
    all_sets.extend(generate_hash_net_sets(router_name, config))
    all_sets.extend(generate_hash_ip_port_sets(router_name, config))
    all_sets.extend(generate_hash_net_iface_sets(router_name, config))
    all_sets.extend(generate_advanced_hash_sets(router_name, config))
    
    print(f"Updated {router_name} with {len(all_sets)} ipset definitions")


def main():
    """Main function to process all raw facts files."""
    
    script_dir = Path(__file__).parent
    raw_facts_dir = script_dir.parent / "tests" / "raw_facts"
    
    if not raw_facts_dir.exists():
        print(f"Error: Raw facts directory not found: {raw_facts_dir}")
        sys.exit(1)
    
    print("Enhanced Ipset Configurations Generator")
    print("=====================================")
    print(f"Processing {len(NETWORK_CONFIG)} routers...")
    print("Implementing comprehensive ipset examples covering all syntax types:")
    print("  • bitmap:ip - IPv4 host/network addresses")
    print("  • bitmap:ip,mac - IP and MAC address pairs")  
    print("  • bitmap:port - Port number ranges")
    print("  • hash:ip - IP address lists")
    print("  • hash:mac - MAC address lists")
    print("  • hash:net - Network address lists")
    print("  • hash:ip,port - IP and port combinations")
    print("  • hash:net,iface - Network and interface combinations")
    print("  • hash:ip,port,net - Advanced multi-dimensional sets")
    print()
    
    total_sets = 0
    
    # Process all raw facts files
    for file_path in raw_facts_dir.glob("*_facts.txt"):
        router_name = file_path.stem.replace("_facts", "")
        if router_name in NETWORK_CONFIG:
            update_raw_facts_file(str(file_path), router_name)
            
            # Count sets for this router
            config = NETWORK_CONFIG[router_name]
            router_sets = 0
            router_sets += len(generate_bitmap_ip_sets(router_name, config))
            router_sets += len(generate_bitmap_ip_mac_sets(router_name, config))
            router_sets += len(generate_bitmap_port_sets(router_name, config))
            router_sets += len(generate_hash_ip_sets(router_name, config))
            router_sets += len(generate_hash_mac_sets(router_name, config))
            router_sets += len(generate_hash_net_sets(router_name, config))
            router_sets += len(generate_hash_ip_port_sets(router_name, config))
            router_sets += len(generate_hash_net_iface_sets(router_name, config))
            router_sets += len(generate_advanced_hash_sets(router_name, config))
            
            total_sets += router_sets
        else:
            print(f"Skipping {router_name} (not in configuration)")
    
    print()
    print("Enhanced ipset configurations generation completed!")
    print("=" * 55)
    print(f"✅ Total ipset definitions created: {total_sets}")
    print(f"✅ Average sets per router: {total_sets // len(NETWORK_CONFIG)}")
    print()
    print("Ipset types implemented:")
    print("  • bitmap:ip - Host/network IP address ranges")
    print("  • bitmap:ip,mac - IP and MAC address pair authentication")
    print("  • bitmap:port - Service port range definitions")
    print("  • hash:ip - Dynamic IP address lists")
    print("  • hash:mac - Device MAC address tracking")
    print("  • hash:net - Network range categorization")
    print("  • hash:ip,port - Service endpoint definitions")
    print("  • hash:net,iface - Interface-specific network rules")
    print("  • hash:ip,port,net - Advanced multi-dimensional filtering")
    print()
    print("Features implemented:")
    print("  • Timeout management (300s to 86400s)")
    print("  • Packet/byte counters for statistics")
    print("  • Comments for documentation")
    print("  • Size optimization (maxelem, hashsize)")
    print("  • Router type-specific configurations")
    print("  • Network location-based sets")
    print("  • Security and access control sets")
    print("  • Integration with enhanced iptables rules")


if __name__ == "__main__":
    main()