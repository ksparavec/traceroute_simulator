#!/usr/bin/env -S python3 -B -u
"""Test script for port parser functionality"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from port_parser import PortParser
from validator import InputValidator

def test_port_parser():
    parser = PortParser()
    validator = InputValidator()
    
    # Test cases
    test_cases = [
        ("22/tcp", "tcp", [(22, 'tcp')]),
        ("80", "tcp", [(80, 'tcp')]),
        ("22/tcp,80,443/tcp", "tcp", [(22, 'tcp'), (80, 'tcp'), (443, 'tcp')]),
        ("1000-1005", "udp", [(1000, 'udp'), (1001, 'udp'), (1002, 'udp'), (1003, 'udp'), (1004, 'udp'), (1005, 'udp')]),
        ("22/tcp,53/udp,80-82", "tcp", [(22, 'tcp'), (53, 'udp'), (80, 'tcp'), (81, 'tcp'), (82, 'tcp')]),
        ("8080-8082/tcp,9000/udp", "tcp", [(8080, 'tcp'), (8081, 'tcp'), (8082, 'tcp'), (9000, 'udp')])
    ]
    
    print("Testing PortParser.parse_port_spec():")
    print("-" * 60)
    
    for port_spec, default_proto, expected in test_cases:
        try:
            result = parser.parse_port_spec(port_spec, default_proto)
            success = result == expected
            status = "✓" if success else "✗"
            print(f"{status} Input: '{port_spec}' (default: {default_proto})")
            print(f"  Expected: {expected}")
            print(f"  Got:      {result}")
            if not success:
                print("  ERROR: Results don't match!")
        except Exception as e:
            print(f"✗ Input: '{port_spec}' - Exception: {e}")
        print()
    
    # Test validation
    print("\nTesting InputValidator.validate_port_spec():")
    print("-" * 60)
    
    valid_specs = [
        "22/tcp",
        "80",
        "22/tcp,80,443/tcp",
        "1000-2000/udp",
        "53/tcp,53/udp",
        "8080-8082/tcp,9000/udp"
    ]
    
    invalid_specs = [
        "",
        "abc",
        "22/xyz",
        "70000",
        "-1",
        "2000-1000",  # Invalid range
        "22/tcp,",  # Trailing comma
        "22//tcp"  # Double slash
    ]
    
    for spec in valid_specs:
        result = validator.validate_port_spec(spec)
        status = "✓" if result else "✗"
        print(f"{status} Valid spec: '{spec}' - Result: {result}")
        if not result:
            print("  ERROR: Should be valid!")
    
    print()
    
    for spec in invalid_specs:
        result = validator.validate_port_spec(spec)
        status = "✓" if not result else "✗"
        print(f"{status} Invalid spec: '{spec}' - Result: {result}")
        if result:
            print("  ERROR: Should be invalid!")
    
    # Test service lookup
    print("\nTesting service descriptions:")
    print("-" * 60)
    
    common_ports = [(22, 'tcp'), (80, 'tcp'), (443, 'tcp'), (53, 'udp'), (3306, 'tcp')]
    
    for port, protocol in common_ports:
        desc = parser.get_service_description(port, protocol)
        print(f"Port {port}/{protocol}: {desc}")
    
    # Test formatting
    print("\nTesting port list formatting:")
    print("-" * 60)
    
    port_lists = [
        [(22, 'tcp'), (23, 'tcp'), (24, 'tcp'), (25, 'tcp')],  # Should become 22-25/tcp
        [(80, 'tcp'), (443, 'tcp'), (8080, 'tcp')],  # Should stay separate
        [(1000, 'udp'), (1001, 'udp'), (1002, 'udp'), (2000, 'tcp')]  # Mixed
    ]
    
    for ports in port_lists:
        formatted = parser.format_port_list(ports)
        print(f"Input:  {ports}")
        print(f"Output: {formatted}")
        print()

if __name__ == "__main__":
    test_port_parser()