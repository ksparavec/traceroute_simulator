#!/usr/bin/env -S python3 -B -u
"""
Validate that generated ipsets comply with official ipset documentation.
Checks each entry type against documented formats.
"""

import re
import ipaddress
from pathlib import Path

def validate_bitmap_ip_entry(entry: str, range_spec: str) -> bool:
    """Validate bitmap:ip entry against range specification."""
    try:
        # Extract range from create command
        if '/24' in range_spec:
            # CIDR notation
            network = ipaddress.IPv4Network(range_spec.split()[-1], strict=False)
            ip = ipaddress.IPv4Address(entry)
            return ip in network
        elif '-' in range_spec:
            # Range notation
            range_part = range_spec.split('range')[-1].strip()
            start_ip, end_ip = range_part.split('-')
            start = ipaddress.IPv4Address(start_ip)
            end = ipaddress.IPv4Address(end_ip)
            ip = ipaddress.IPv4Address(entry)
            return start <= ip <= end
    except:
        return False
    return True

def validate_mac_address(mac: str) -> bool:
    """Validate MAC address format."""
    mac_pattern = r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$'
    return bool(re.match(mac_pattern, mac))

def validate_port_entry(entry: str) -> bool:
    """Validate port number or protocol:port entry."""
    if ':' in entry:
        proto, port = entry.split(':', 1)
        if proto not in ['tcp', 'udp', 'sctp', 'udplite', 'icmp', 'icmpv6']:
            return False
        entry = port
    
    try:
        port = int(entry)
        return 0 <= port <= 65535
    except:
        return False

def validate_network_entry(entry: str) -> bool:
    """Validate network address entry."""
    try:
        ipaddress.IPv4Network(entry, strict=False)
        return True
    except:
        return False

def validate_interface_name(iface: str) -> bool:
    """Validate interface name."""
    # Common interface patterns
    valid_patterns = [
        r'^eth\d+$',      # eth0, eth1, etc.
        r'^wlan\d+$',     # wlan0, wlan1, etc.
        r'^wg\d+$',       # wg0, wg1, etc.
        r'^lo$',          # loopback
        r'^br-\w+$'       # bridge interfaces
    ]
    return any(re.match(pattern, iface) for pattern in valid_patterns)

def validate_ipset_entries():
    """Validate all ipset entries against documentation standards."""
    facts_dir = Path('/home/sparavec/git/traceroute_simulator/tests/raw_facts')
    results = {}
    
    for facts_file in facts_dir.glob('*_facts.txt'):
        router = facts_file.stem.replace('_facts', '')
        results[router] = {'valid': 0, 'invalid': 0, 'details': []}
        
        with open(facts_file, 'r') as f:
            content = f.read()
        
        # Extract ipset section
        ipset_match = re.search(r'=== TSIM_SECTION_START:ipset_save ===.*?^---$(.*?)^EXIT_CODE:', content, re.MULTILINE | re.DOTALL)
        if not ipset_match:
            results[router]['details'].append("No ipset section found")
            continue
        
        ipset_content = ipset_match.group(1).strip()
        lines = [line.strip() for line in ipset_content.split('\n') if line.strip()]
        
        # Parse create and add commands
        creates = {}
        for line in lines:
            if line.startswith('create '):
                parts = line.split()
                if len(parts) >= 3:
                    set_name = parts[1]
                    set_type = parts[2]
                    create_opts = ' '.join(parts[3:]) if len(parts) > 3 else ''
                    creates[set_name] = (set_type, create_opts)
        
        # Validate add commands
        for line in lines:
            if line.startswith('add '):
                parts = line.split()
                if len(parts) < 3:
                    results[router]['invalid'] += 1
                    results[router]['details'].append(f"Invalid add command: {line}")
                    continue
                
                set_name = parts[1]
                entry = ' '.join(parts[2:])
                
                if set_name not in creates:
                    results[router]['invalid'] += 1
                    results[router]['details'].append(f"Add to undefined set: {set_name}")
                    continue
                
                set_type, create_opts = creates[set_name]
                
                # Validate entry based on set type
                valid = validate_entry_for_type(set_type, entry, create_opts)
                
                if valid:
                    results[router]['valid'] += 1
                    results[router]['details'].append(f"✓ Valid {set_type}: {entry}")
                else:
                    results[router]['invalid'] += 1
                    results[router]['details'].append(f"✗ Invalid {set_type}: {entry}")
    
    return results

def validate_entry_for_type(set_type: str, entry: str, create_opts: str) -> bool:
    """Validate entry format for specific ipset type."""
    try:
        if set_type == 'bitmap:ip':
            return validate_bitmap_ip_entry(entry, create_opts)
            
        elif set_type == 'bitmap:ip,mac':
            if ',' not in entry:
                return False
            ip, mac = entry.split(',', 1)
            return validate_bitmap_ip_entry(ip, create_opts) and validate_mac_address(mac)
            
        elif set_type == 'bitmap:port':
            return validate_port_entry(entry)
            
        elif set_type == 'hash:ip':
            try:
                ipaddress.IPv4Address(entry)
                return True
            except:
                return False
                
        elif set_type == 'hash:mac':
            return validate_mac_address(entry)
            
        elif set_type == 'hash:ip,mac':
            if ',' not in entry:
                return False
            ip, mac = entry.split(',', 1)
            try:
                ipaddress.IPv4Address(ip)
                return validate_mac_address(mac)
            except:
                return False
                
        elif set_type == 'hash:net':
            return validate_network_entry(entry)
            
        elif set_type == 'hash:net,net':
            if ',' not in entry:
                return False
            net1, net2 = entry.split(',', 1)
            return validate_network_entry(net1) and validate_network_entry(net2)
            
        elif set_type == 'hash:ip,port':
            if ',' not in entry:
                return False
            ip, port = entry.split(',', 1)
            try:
                ipaddress.IPv4Address(ip)
                return validate_port_entry(port)
            except:
                return False
                
        elif set_type == 'hash:net,port':
            if ',' not in entry:
                return False
            net, port = entry.split(',', 1)
            return validate_network_entry(net) and validate_port_entry(port)
            
        elif set_type == 'hash:ip,port,ip':
            parts = entry.split(',')
            if len(parts) != 3:
                return False
            try:
                ipaddress.IPv4Address(parts[0])
                ipaddress.IPv4Address(parts[2])
                return validate_port_entry(parts[1])
            except:
                return False
                
        elif set_type == 'hash:ip,port,net':
            parts = entry.split(',')
            if len(parts) != 3:
                return False
            try:
                ipaddress.IPv4Address(parts[0])
                return validate_port_entry(parts[1]) and validate_network_entry(parts[2])
            except:
                return False
                
        elif set_type == 'hash:net,iface':
            if ',' not in entry:
                return False
            net, iface = entry.split(',', 1)
            return validate_network_entry(net) and validate_interface_name(iface)
            
        elif set_type == 'list:set':
            # For list:set, entry should be a set name (simple string)
            return bool(re.match(r'^[a-zA-Z0-9_]+$', entry))
            
    except Exception as e:
        return False
    
    return False

def main():
    """Main validation function."""
    print("Validating ipset entries against official documentation...")
    print("=" * 70)
    
    results = validate_ipset_entries()
    
    total_valid = 0
    total_invalid = 0
    
    for router, result in results.items():
        print(f"\n{router.upper()}:")
        print(f"  Valid entries: {result['valid']}")
        print(f"  Invalid entries: {result['invalid']}")
        
        # Show details
        for detail in result['details']:
            if detail.startswith('✓'):
                print(f"    {detail}")
            elif detail.startswith('✗'):
                print(f"    {detail}")
            else:
                print(f"    {detail}")
        
        total_valid += result['valid']
        total_invalid += result['invalid']
    
    print("\n" + "=" * 70)
    print(f"SUMMARY:")
    print(f"  Total valid entries: {total_valid}")
    print(f"  Total invalid entries: {total_invalid}")
    print(f"  Overall compliance rate: {total_valid/(total_valid+total_invalid)*100:.1f}%")
    
    if total_invalid == 0:
        print(f"\n✅ ALL ENTRIES COMPLY WITH OFFICIAL IPSET DOCUMENTATION")
    else:
        print(f"\n❌ {total_invalid} entries need correction")

if __name__ == '__main__':
    main()