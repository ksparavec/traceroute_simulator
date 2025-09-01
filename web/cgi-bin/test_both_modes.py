#!/usr/bin/env -S python3 -B -u
"""Test both input modes to see if they produce the same results"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from port_parser import PortParser

def test_modes():
    parser = PortParser()
    
    print("Testing Quick Mode vs Manual Mode")
    print("=" * 60)
    
    # Test case 1: Single port with protocol
    print("\nTest 1: Single port 22/tcp")
    quick_spec = "22/tcp"  # What dropdown sends
    manual_spec = "22/tcp"  # What user types
    
    quick_result = parser.parse_port_spec(quick_spec, 'tcp')
    manual_result = parser.parse_port_spec(manual_spec, 'tcp')
    
    print(f"Quick mode:  {quick_spec} -> {quick_result}")
    print(f"Manual mode: {manual_spec} -> {manual_result}")
    print(f"Match: {quick_result == manual_result}")
    
    # Test case 2: Multiple ports
    print("\nTest 2: Multiple ports")
    quick_spec = "22/tcp,80/tcp,443/tcp"  # What dropdown sends when multiple selected
    manual_spec = "22/tcp,80/tcp,443/tcp"  # What user types
    
    quick_result = parser.parse_port_spec(quick_spec, 'tcp')
    manual_result = parser.parse_port_spec(manual_spec, 'tcp')
    
    print(f"Quick mode:  {quick_spec} -> {quick_result}")
    print(f"Manual mode: {manual_spec} -> {manual_result}")
    print(f"Match: {quick_result == manual_result}")
    
    # Test case 3: Manual mode with ranges
    print("\nTest 3: Manual mode with ranges")
    manual_spec = "22/tcp,80-82,443/tcp,1000-1002/udp"
    
    manual_result = parser.parse_port_spec(manual_spec, 'tcp')
    print(f"Manual mode: {manual_spec}")
    print(f"Result: {manual_result}")
    print(f"Total ports: {len(manual_result)}")
    
    # Test case 4: Check formatting
    print("\nTest 4: Formatting")
    for spec in ["22/tcp,80,443/tcp", "8000-8010/tcp", "22/tcp,53/udp,80-90"]:
        parsed = parser.parse_port_spec(spec, 'tcp')
        formatted = parser.format_port_list(parsed)
        print(f"Input:     {spec}")
        print(f"Parsed:    {parsed[:3]}..." if len(parsed) > 3 else f"Parsed:    {parsed}")
        print(f"Formatted: {formatted}")
        print()

if __name__ == "__main__":
    test_modes()