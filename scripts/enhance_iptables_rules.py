#!/usr/bin/env -S python3 -B -u
"""
Enhanced Iptables Rules Generator for Raw Facts Files

This script augments all raw fact files with comprehensive iptables rules
that enable full connectivity for ping/mtr between all routers and hosts,
while implementing advanced logging for packet tracing capabilities.
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
        'networks': ['10.1.1.0/24', '10.1.2.0/24'],
        'interfaces': {'eth0': '203.0.113.10/24', 'eth1': '10.1.1.1/24', 'wg0': '10.100.1.1/24'},
        'type': 'gateway',
        'location': 'hq'
    },
    'hq-core': {
        'networks': ['10.1.1.0/24', '10.1.2.0/24', '10.1.10.0/24', '10.1.11.0/24'],
        'interfaces': {'eth0': '10.1.1.2/24', 'eth1': '10.1.10.1/24', 'eth2': '10.1.11.1/24'},
        'type': 'core',
        'location': 'hq'
    },
    'hq-dmz': {
        'networks': ['10.1.2.0/24', '10.1.3.0/24'],
        'interfaces': {'eth0': '10.1.2.3/24', 'eth1': '10.1.3.1/24'},
        'type': 'access',
        'location': 'hq'
    },
    'hq-lab': {
        'networks': ['10.1.11.0/24'],
        'interfaces': {'eth0': '10.1.11.2/24'},
        'type': 'access',
        'location': 'hq'
    },
    'br-gw': {
        'networks': ['10.2.1.0/24', '10.2.2.0/24'],
        'interfaces': {'eth0': '198.51.100.10/24', 'eth1': '10.2.1.1/24', 'wg0': '10.100.1.2/24'},
        'type': 'gateway',
        'location': 'branch'
    },
    'br-core': {
        'networks': ['10.2.1.0/24', '10.2.2.0/24', '10.2.10.0/24'],
        'interfaces': {'eth0': '10.2.1.2/24', 'eth1': '10.2.10.1/24'},
        'type': 'core',
        'location': 'branch'
    },
    'br-wifi': {
        'networks': ['10.2.2.0/24', '10.2.20.0/24'],
        'interfaces': {'eth0': '10.2.2.3/24', 'eth1': '10.2.20.1/24'},
        'type': 'access',
        'location': 'branch'
    },
    'dc-gw': {
        'networks': ['10.3.1.0/24', '10.3.2.0/24'],
        'interfaces': {'eth0': '192.0.2.10/24', 'eth1': '10.3.1.1/24', 'wg0': '10.100.1.3/24'},
        'type': 'gateway',
        'location': 'datacenter'
    },
    'dc-core': {
        'networks': ['10.3.1.0/24', '10.3.2.0/24', '10.3.10.0/24', '10.3.20.0/24'],
        'interfaces': {'eth0': '10.3.1.2/24', 'eth1': '10.3.10.1/24', 'eth2': '10.3.20.1/24'},
        'type': 'core',
        'location': 'datacenter'
    },
    'dc-srv': {
        'networks': ['10.3.20.0/24'],
        'interfaces': {'eth0': '10.3.20.3/24'},
        'type': 'server',
        'location': 'datacenter'
    }
}

ALL_INTERNAL_NETWORKS = [
    '10.1.0.0/16',   # HQ networks
    '10.2.0.0/16',   # Branch networks  
    '10.3.0.0/16',   # DC networks
    '10.100.1.0/24'  # VPN network
]

MANAGEMENT_PORTS = ['22', '161', '443', '8080', '514']
ICMP_TYPES = ['0', '3', '8', '11']  # Echo reply, unreachable, echo request, time exceeded


def generate_iptables_filter_rules(router_name: str, config: Dict) -> str:
    """Generate comprehensive filter table rules for a router."""
    
    rules = []
    rules.append("Chain INPUT (policy DROP 0 packets, 0 bytes)")
    rules.append("num   pkts bytes target     prot opt in     out     source               destination")
    
    # INPUT chain rules
    rule_num = 1
    
    # Allow loopback
    rules.append(f"{rule_num:2d}      123  9876 ACCEPT     all  --  lo     *       0.0.0.0/0            0.0.0.0/0")
    rule_num += 1
    
    # Drop invalid connections
    rules.append(f"{rule_num:2d}     4567 123456 DROP      all  --  *      *       0.0.0.0/0            0.0.0.0/0            ctstate INVALID")
    rule_num += 1
    
    # Allow established/related connections
    rules.append(f"{rule_num:2d}     2345 234567 ACCEPT     all  --  *      *       0.0.0.0/0            0.0.0.0/0            ctstate RELATED,ESTABLISHED")
    rule_num += 1
    
    # Allow ICMP for ping/mtr from all internal networks
    for network in ALL_INTERNAL_NETWORKS:
        for icmp_type in ICMP_TYPES:
            rules.append(f"{rule_num:2d}     1234 456789 LOG        icmp --  *      *       {network:<16} 0.0.0.0/0            icmp-type {icmp_type} LOG flags 0 level 4 prefix \"INPUT-ICMP-{icmp_type}: \"")
            rule_num += 1
            rules.append(f"{rule_num:2d}     1234 456789 ACCEPT     icmp --  *      *       {network:<16} 0.0.0.0/0            icmp-type {icmp_type}")
            rule_num += 1
    
    # Allow management protocols from all internal networks
    for network in ALL_INTERNAL_NETWORKS:
        for port in MANAGEMENT_PORTS:
            rules.append(f"{rule_num:2d}      789  34567 LOG        tcp  --  *      *       {network:<16} 0.0.0.0/0            tcp dpt:{port} ctstate NEW LOG flags 0 level 4 prefix \"INPUT-MGMT-{port}: \"")
            rule_num += 1
            rules.append(f"{rule_num:2d}      789  34567 ACCEPT     tcp  --  *      *       {network:<16} 0.0.0.0/0            tcp dpt:{port} ctstate NEW,ESTABLISHED")
            rule_num += 1
    
    # Allow UDP for MTR and traceroute (ports 33434-33534)
    for network in ALL_INTERNAL_NETWORKS:
        rules.append(f"{rule_num:2d}      456  23456 LOG        udp  --  *      *       {network:<16} 0.0.0.0/0            udp dpts:33434:33534 LOG flags 0 level 4 prefix \"INPUT-MTR-UDP: \"")
        rule_num += 1
        rules.append(f"{rule_num:2d}      456  23456 ACCEPT     udp  --  *      *       {network:<16} 0.0.0.0/0            udp dpts:33434:33534")
        rule_num += 1
    
    # WireGuard for gateway routers
    if config['type'] == 'gateway':
        rules.append(f"{rule_num:2d}      234  12345 ACCEPT     udp  --  wg0    *       0.0.0.0/0            0.0.0.0/0            udp dpt:51820")
        rule_num += 1
    
    # Log and drop everything else
    rules.append(f"{rule_num:2d}       89   5678 LOG        all  --  *      *       0.0.0.0/0            0.0.0.0/0            LOG flags 0 level 4 prefix \"INPUT-DROP: \"")
    rule_num += 1
    rules.append(f"{rule_num:2d}       56   2345 DROP       all  --  *      *       0.0.0.0/0            0.0.0.0/0")
    
    rules.append("")
    
    # FORWARD chain rules
    rules.append("Chain FORWARD (policy DROP 0 packets, 0 bytes)")
    rules.append("num   pkts bytes target     prot opt in     out     source               destination")
    
    rule_num = 1
    
    # Allow loopback
    rules.append(f"{rule_num:2d}     8765 876543 ACCEPT     all  --  lo     *       0.0.0.0/0            0.0.0.0/0")
    rule_num += 1
    
    # Allow established/related connections
    rules.append(f"{rule_num:2d}     5432 543210 ACCEPT     all  --  *      *       0.0.0.0/0            0.0.0.0/0            ctstate RELATED,ESTABLISHED")
    rule_num += 1
    
    # Allow all ICMP between internal networks with logging
    for src_net in ALL_INTERNAL_NETWORKS:
        for dst_net in ALL_INTERNAL_NETWORKS:
            if src_net != dst_net:
                rules.append(f"{rule_num:2d}     3456 345678 LOG        icmp --  *      *       {src_net:<16} {dst_net:<16} LOG flags 0 level 4 prefix \"FWD-ICMP-{src_net.split('/')[0].replace('.', '_')}-{dst_net.split('/')[0].replace('.', '_')}: \"")
                rule_num += 1
                rules.append(f"{rule_num:2d}     3456 345678 ACCEPT     icmp --  *      *       {src_net:<16} {dst_net:<16}")
                rule_num += 1
    
    # Allow UDP for MTR between internal networks with logging
    for src_net in ALL_INTERNAL_NETWORKS:
        for dst_net in ALL_INTERNAL_NETWORKS:
            if src_net != dst_net:
                rules.append(f"{rule_num:2d}     2345 234567 LOG        udp  --  *      *       {src_net:<16} {dst_net:<16} udp dpts:33434:33534 LOG flags 0 level 4 prefix \"FWD-MTR-{src_net.split('/')[0].replace('.', '_')}-{dst_net.split('/')[0].replace('.', '_')}: \"")
                rule_num += 1
                rules.append(f"{rule_num:2d}     2345 234567 ACCEPT     udp  --  *      *       {src_net:<16} {dst_net:<16} udp dpts:33434:33534")
                rule_num += 1
    
    # Allow TCP for management protocols between internal networks
    for src_net in ALL_INTERNAL_NETWORKS:
        for dst_net in ALL_INTERNAL_NETWORKS:
            if src_net != dst_net:
                for port in MANAGEMENT_PORTS:
                    rules.append(f"{rule_num:2d}     1234 123456 LOG        tcp  --  *      *       {src_net:<16} {dst_net:<16} tcp dpt:{port} LOG flags 0 level 4 prefix \"FWD-TCP-{port}-{src_net.split('/')[0].replace('.', '_')}-{dst_net.split('/')[0].replace('.', '_')}: \"")
                    rule_num += 1
                    rules.append(f"{rule_num:2d}     1234 123456 ACCEPT     tcp  --  *      *       {src_net:<16} {dst_net:<16} tcp dpt:{port}")
                    rule_num += 1
    
    # For gateway routers, allow internet access
    if config['type'] == 'gateway':
        # Allow internal to internet
        for network in ['10.1.0.0/16', '10.2.0.0/16', '10.3.0.0/16']:
            rules.append(f"{rule_num:2d}      987  98765 LOG        all  --  *      eth0    {network:<16} 0.0.0.0/0            LOG flags 0 level 4 prefix \"FWD-INET-OUT-{network.split('/')[0].replace('.', '_')}: \"")
            rule_num += 1
            rules.append(f"{rule_num:2d}      987  98765 ACCEPT     all  --  *      eth0    {network:<16} 0.0.0.0/0")
            rule_num += 1
    
    # Log and drop everything else
    rules.append(f"{rule_num:2d}      654  65432 LOG        all  --  *      *       0.0.0.0/0            0.0.0.0/0            LOG flags 0 level 4 prefix \"FORWARD-DROP: \"")
    rule_num += 1
    rules.append(f"{rule_num:2d}      321  32123 DROP       all  --  *      *       0.0.0.0/0            0.0.0.0/0")
    
    rules.append("")
    
    # OUTPUT chain rules
    rules.append("Chain OUTPUT (policy ACCEPT 0 packets, 0 bytes)")
    rules.append("num   pkts bytes target     prot opt in     out     source               destination")
    
    rule_num = 1
    
    # Allow loopback
    rules.append(f"{rule_num:2d}      987  98765 ACCEPT     all  --  *      lo      0.0.0.0/0            0.0.0.0/0")
    rule_num += 1
    
    # Allow established/related connections
    rules.append(f"{rule_num:2d}      654  65432 ACCEPT     all  --  *      *       0.0.0.0/0            0.0.0.0/0            ctstate RELATED,ESTABLISHED")
    rule_num += 1
    
    # Allow all ICMP outbound
    rules.append(f"{rule_num:2d}      321  32123 ACCEPT     icmp --  *      *       0.0.0.0/0            0.0.0.0/0")
    rule_num += 1
    
    # Allow UDP for MTR/traceroute outbound
    rules.append(f"{rule_num:2d}      123  12345 ACCEPT     udp  --  *      *       0.0.0.0/0            0.0.0.0/0            udp dpts:33434:33534")
    rule_num += 1
    
    # Allow management protocols outbound
    for port in MANAGEMENT_PORTS:
        rules.append(f"{rule_num:2d}       98   9876 ACCEPT     tcp  --  *      *       0.0.0.0/0            0.0.0.0/0            tcp spt:{port}")
        rule_num += 1
        rules.append(f"{rule_num:2d}       87   8765 ACCEPT     tcp  --  *      *       0.0.0.0/0            0.0.0.0/0            tcp dpt:{port}")
        rule_num += 1
    
    return "\\n".join(rules)


def generate_iptables_nat_rules(router_name: str, config: Dict) -> str:
    """Generate NAT table rules for a router."""
    
    rules = []
    rules.append("Chain PREROUTING (policy ACCEPT 0 packets, 0 bytes)")
    rules.append("num   pkts bytes target     prot opt in     out     source               destination")
    
    rule_num = 1
    
    # DNAT rules for service access (example web services)
    if config['type'] == 'gateway':
        # External to internal service mapping
        rules.append(f"{rule_num:2d}      123  12345 LOG        tcp  --  eth0   *       0.0.0.0/0            0.0.0.0/0            tcp dpt:80 LOG flags 0 level 4 prefix \"NAT-DNAT-HTTP: \"")
        rule_num += 1
        rules.append(f"{rule_num:2d}      123  12345 DNAT       tcp  --  eth0   *       0.0.0.0/0            0.0.0.0/0            tcp dpt:80 to:10.{config['location'][0]}.1.10")
        rule_num += 1
        
        rules.append(f"{rule_num:2d}       87   8765 LOG        tcp  --  eth0   *       0.0.0.0/0            0.0.0.0/0            tcp dpt:443 LOG flags 0 level 4 prefix \"NAT-DNAT-HTTPS: \"")
        rule_num += 1
        rules.append(f"{rule_num:2d}       87   8765 DNAT       tcp  --  eth0   *       0.0.0.0/0            0.0.0.0/0            tcp dpt:443 to:10.{config['location'][0]}.1.10")
        rule_num += 1
    
    rules.append("")
    
    rules.append("Chain INPUT (policy ACCEPT 0 packets, 0 bytes)")
    rules.append("num   pkts bytes target     prot opt in     out     source               destination")
    
    rules.append("")
    
    rules.append("Chain OUTPUT (policy ACCEPT 0 packets, 0 bytes)")
    rules.append("num   pkts bytes target     prot opt in     out     source               destination")
    
    rules.append("")
    
    rules.append("Chain POSTROUTING (policy ACCEPT 0 packets, 0 bytes)")
    rules.append("num   pkts bytes target     prot opt in     out     source               destination")
    
    rule_num = 1
    
    # SNAT/Masquerading for internet access
    if config['type'] == 'gateway':
        # Masquerade internal networks to internet
        for network in ['10.1.0.0/16', '10.2.0.0/16', '10.3.0.0/16']:
            rules.append(f"{rule_num:2d}     1234 123456 LOG        all  --  *      eth0    {network:<16} 0.0.0.0/0            LOG flags 0 level 4 prefix \"NAT-MASQ-{network.split('/')[0].replace('.', '_')}: \"")
            rule_num += 1
            rules.append(f"{rule_num:2d}     1234 123456 MASQUERADE  all  --  *      eth0    {network:<16} 0.0.0.0/0")
            rule_num += 1
    
    return "\\n".join(rules)


def generate_iptables_mangle_rules(router_name: str, config: Dict) -> str:
    """Generate mangle table rules for a router."""
    
    rules = []
    rules.append("Chain PREROUTING (policy ACCEPT 0 packets, 0 bytes)")
    rules.append("num   pkts bytes target     prot opt in     out     source               destination")
    
    rule_num = 1
    
    # Mark high-priority traffic (ICMP, SSH, management)
    rules.append(f"{rule_num:2d}      123  12345 LOG        icmp --  *      *       0.0.0.0/0            0.0.0.0/0            LOG flags 0 level 4 prefix \"MANGLE-MARK-ICMP: \"")
    rule_num += 1
    rules.append(f"{rule_num:2d}      123  12345 MARK       icmp --  *      *       0.0.0.0/0            0.0.0.0/0            MARK set 0x1")
    rule_num += 1
    
    for port in ['22', '161', '443']:
        rules.append(f"{rule_num:2d}       87   8765 LOG        tcp  --  *      *       0.0.0.0/0            0.0.0.0/0            tcp dpt:{port} LOG flags 0 level 4 prefix \"MANGLE-MARK-{port}: \"")
        rule_num += 1
        rules.append(f"{rule_num:2d}       87   8765 MARK       tcp  --  *      *       0.0.0.0/0            0.0.0.0/0            tcp dpt:{port} MARK set 0x1")
        rule_num += 1
    
    rules.append("")
    
    rules.append("Chain INPUT (policy ACCEPT 0 packets, 0 bytes)")
    rules.append("num   pkts bytes target     prot opt in     out     source               destination")
    
    rules.append("")
    
    rules.append("Chain FORWARD (policy ACCEPT 0 packets, 0 bytes)")
    rules.append("num   pkts bytes target     prot opt in     out     source               destination")
    
    rule_num = 1
    
    # TTL adjustments for advanced scenarios
    rules.append(f"{rule_num:2d}      234  23456 LOG        all  --  *      *       10.100.1.0/24        0.0.0.0/0            LOG flags 0 level 4 prefix \"MANGLE-TTL-VPN: \"")
    rule_num += 1
    rules.append(f"{rule_num:2d}      234  23456 TTL        all  --  *      *       10.100.1.0/24        0.0.0.0/0            TTL set 64")
    rule_num += 1
    
    rules.append("")
    
    rules.append("Chain OUTPUT (policy ACCEPT 0 packets, 0 bytes)")
    rules.append("num   pkts bytes target     prot opt in     out     source               destination")
    
    rules.append("")
    
    rules.append("Chain POSTROUTING (policy ACCEPT 0 packets, 0 bytes)")
    rules.append("num   pkts bytes target     prot opt in     out     source               destination")
    
    return "\\n".join(rules)


def generate_iptables_save_rules(router_name: str, config: Dict) -> str:
    """Generate iptables-save format rules."""
    
    rules = []
    rules.append("# Generated by iptables-save v1.8.7 on Mon Jul  1 10:00:00 2025")
    rules.append("*filter")
    rules.append(":INPUT DROP [0:0]")
    rules.append(":FORWARD DROP [0:0]")
    rules.append(":OUTPUT ACCEPT [0:0]")
    
    # Custom chains
    rules.append(f":{router_name.upper().replace('-', '_')}_MGMT_ACCESS - [0:0]")
    rules.append(f":{router_name.upper().replace('-', '_')}_LAN_FORWARD - [0:0]")
    
    # INPUT rules
    rules.append("-A INPUT -i lo -j ACCEPT")
    rules.append("-A INPUT -m conntrack --ctstate INVALID -j DROP")
    rules.append("-A INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT")
    
    # Allow ICMP from all internal networks
    for network in ALL_INTERNAL_NETWORKS:
        for icmp_type in ICMP_TYPES:
            rules.append(f"-A INPUT -s {network} -p icmp --icmp-type {icmp_type} -j LOG --log-prefix \"INPUT-ICMP-{icmp_type}: \"")
            rules.append(f"-A INPUT -s {network} -p icmp --icmp-type {icmp_type} -j ACCEPT")
    
    # Allow management from all internal networks
    for network in ALL_INTERNAL_NETWORKS:
        for port in MANAGEMENT_PORTS:
            rules.append(f"-A INPUT -s {network} -p tcp --dport {port} -m conntrack --ctstate NEW -j LOG --log-prefix \"INPUT-MGMT-{port}: \"")
            rules.append(f"-A INPUT -s {network} -p tcp --dport {port} -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT")
    
    # Allow MTR UDP
    for network in ALL_INTERNAL_NETWORKS:
        rules.append(f"-A INPUT -s {network} -p udp --dport 33434:33534 -j LOG --log-prefix \"INPUT-MTR-UDP: \"")
        rules.append(f"-A INPUT -s {network} -p udp --dport 33434:33534 -j ACCEPT")
    
    # Drop and log everything else
    rules.append("-A INPUT -j LOG --log-prefix \"INPUT-DROP: \"")
    rules.append("-A INPUT -j DROP")
    
    # FORWARD rules
    rules.append("-A FORWARD -i lo -j ACCEPT")
    rules.append("-A FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT")
    
    # Allow ICMP between all internal networks
    for src_net in ALL_INTERNAL_NETWORKS:
        for dst_net in ALL_INTERNAL_NETWORKS:
            if src_net != dst_net:
                log_prefix = f"FWD-ICMP-{src_net.split('/')[0].replace('.', '_')}-{dst_net.split('/')[0].replace('.', '_')}"
                rules.append(f"-A FORWARD -s {src_net} -d {dst_net} -p icmp -j LOG --log-prefix \"{log_prefix}: \"")
                rules.append(f"-A FORWARD -s {src_net} -d {dst_net} -p icmp -j ACCEPT")
    
    # Allow UDP MTR between all internal networks
    for src_net in ALL_INTERNAL_NETWORKS:
        for dst_net in ALL_INTERNAL_NETWORKS:
            if src_net != dst_net:
                log_prefix = f"FWD-MTR-{src_net.split('/')[0].replace('.', '_')}-{dst_net.split('/')[0].replace('.', '_')}"
                rules.append(f"-A FORWARD -s {src_net} -d {dst_net} -p udp --dport 33434:33534 -j LOG --log-prefix \"{log_prefix}: \"")
                rules.append(f"-A FORWARD -s {src_net} -d {dst_net} -p udp --dport 33434:33534 -j ACCEPT")
    
    # Gateway internet access
    if config['type'] == 'gateway':
        for network in ['10.1.0.0/16', '10.2.0.0/16', '10.3.0.0/16']:
            log_prefix = f"FWD-INET-OUT-{network.split('/')[0].replace('.', '_')}"
            rules.append(f"-A FORWARD -s {network} -o eth0 -j LOG --log-prefix \"{log_prefix}: \"")
            rules.append(f"-A FORWARD -s {network} -o eth0 -j ACCEPT")
    
    rules.append("-A FORWARD -j LOG --log-prefix \"FORWARD-DROP: \"")
    rules.append("-A FORWARD -j DROP")
    
    rules.append("COMMIT")
    
    # NAT table
    rules.append("# Completed on Mon Jul  1 10:00:00 2025")
    rules.append("# Generated by iptables-save v1.8.7 on Mon Jul  1 10:00:00 2025")
    rules.append("*nat")
    rules.append(":PREROUTING ACCEPT [0:0]")
    rules.append(":INPUT ACCEPT [0:0]")
    rules.append(":OUTPUT ACCEPT [0:0]")
    rules.append(":POSTROUTING ACCEPT [0:0]")
    
    if config['type'] == 'gateway':
        # DNAT for services
        rules.append("-A PREROUTING -i eth0 -p tcp --dport 80 -j LOG --log-prefix \"NAT-DNAT-HTTP: \"")
        rules.append(f"-A PREROUTING -i eth0 -p tcp --dport 80 -j DNAT --to-destination 10.{config['location'][0]}.1.10")
        
        # SNAT for internet
        for network in ['10.1.0.0/16', '10.2.0.0/16', '10.3.0.0/16']:
            log_prefix = f"NAT-MASQ-{network.split('/')[0].replace('.', '_')}"
            rules.append(f"-A POSTROUTING -s {network} -o eth0 -j LOG --log-prefix \"{log_prefix}: \"")
            rules.append(f"-A POSTROUTING -s {network} -o eth0 -j MASQUERADE")
    
    rules.append("COMMIT")
    
    # Mangle table
    rules.append("# Completed on Mon Jul  1 10:00:00 2025")
    rules.append("# Generated by iptables-save v1.8.7 on Mon Jul  1 10:00:00 2025")
    rules.append("*mangle")
    rules.append(":PREROUTING ACCEPT [0:0]")
    rules.append(":INPUT ACCEPT [0:0]")
    rules.append(":FORWARD ACCEPT [0:0]")
    rules.append(":OUTPUT ACCEPT [0:0]")
    rules.append(":POSTROUTING ACCEPT [0:0]")
    
    # Mark high-priority traffic
    rules.append("-A PREROUTING -p icmp -j LOG --log-prefix \"MANGLE-MARK-ICMP: \"")
    rules.append("-A PREROUTING -p icmp -j MARK --set-mark 0x1")
    
    for port in ['22', '161', '443']:
        rules.append(f"-A PREROUTING -p tcp --dport {port} -j LOG --log-prefix \"MANGLE-MARK-{port}: \"")
        rules.append(f"-A PREROUTING -p tcp --dport {port} -j MARK --set-mark 0x1")
    
    rules.append("COMMIT")
    rules.append("# Completed on Mon Jul  1 10:00:00 2025")
    
    return "\\n".join(rules)


def update_raw_facts_file(file_path: str, router_name: str):
    """Update a raw facts file with enhanced iptables rules."""
    
    print(f"Processing {router_name} ({file_path})")
    
    if router_name not in NETWORK_CONFIG:
        print(f"Warning: {router_name} not in network configuration")
        return
    
    config = NETWORK_CONFIG[router_name]
    
    # Read the original file
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Generate new iptables rules
    filter_rules = generate_iptables_filter_rules(router_name, config)
    nat_rules = generate_iptables_nat_rules(router_name, config)
    mangle_rules = generate_iptables_mangle_rules(router_name, config)
    save_rules = generate_iptables_save_rules(router_name, config)
    
    # Replace iptables sections
    patterns = [
        (r'=== TSIM_SECTION_START:iptables_filter ===.*?=== TSIM_SECTION_END:iptables_filter ===',
         f"""=== TSIM_SECTION_START:iptables_filter ===
TITLE: Iptables Filter Table
COMMAND: /sbin/iptables -t filter -L -n -v --line-numbers
TIMESTAMP: 2025-07-01 10:00:00
---
{filter_rules}

EXIT_CODE: 0
=== TSIM_SECTION_END:iptables_filter ==="""),
        
        (r'=== TSIM_SECTION_START:iptables_nat ===.*?=== TSIM_SECTION_END:iptables_nat ===',
         f"""=== TSIM_SECTION_START:iptables_nat ===
TITLE: Iptables NAT Table
COMMAND: /sbin/iptables -t nat -L -n -v --line-numbers
TIMESTAMP: 2025-07-01 10:00:00
---
{nat_rules}

EXIT_CODE: 0
=== TSIM_SECTION_END:iptables_nat ==="""),
        
        (r'=== TSIM_SECTION_START:iptables_mangle ===.*?=== TSIM_SECTION_END:iptables_mangle ===',
         f"""=== TSIM_SECTION_START:iptables_mangle ===
TITLE: Iptables Mangle Table
COMMAND: /sbin/iptables -t mangle -L -n -v --line-numbers
TIMESTAMP: 2025-07-01 10:00:00
---
{mangle_rules}

EXIT_CODE: 0
=== TSIM_SECTION_END:iptables_mangle ==="""),
        
        (r'=== TSIM_SECTION_START:iptables_save ===.*?=== TSIM_SECTION_END:iptables_save ===',
         f"""=== TSIM_SECTION_START:iptables_save ===
TITLE: Iptables Save Output
COMMAND: /sbin/iptables-save
TIMESTAMP: 2025-07-01 10:00:00
---
{save_rules}

EXIT_CODE: 0
=== TSIM_SECTION_END:iptables_save ===""")
    ]
    
    # Apply replacements
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    # Write the updated content
    with open(file_path, 'w') as f:
        f.write(content)
    
    print(f"Updated {router_name} with enhanced iptables rules")


def main():
    """Main function to process all raw facts files."""
    
    script_dir = Path(__file__).parent
    raw_facts_dir = script_dir.parent / "tests" / "raw_facts"
    
    if not raw_facts_dir.exists():
        print(f"Error: Raw facts directory not found: {raw_facts_dir}")
        sys.exit(1)
    
    # Process all raw facts files
    for file_path in raw_facts_dir.glob("*_facts.txt"):
        router_name = file_path.stem.replace("_facts", "")
        update_raw_facts_file(str(file_path), router_name)
    
    print("\\nEnhanced iptables rules generation completed!")
    print("All raw facts files have been updated with comprehensive iptables rules")
    print("that enable full ping/mtr connectivity and advanced logging.")


if __name__ == "__main__":
    main()