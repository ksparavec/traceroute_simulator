#!/usr/bin/env -S python3 -B -u
"""Test form submission handling"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from port_parser import PortParser
from validator import InputValidator

# Simulate form data
class MockForm:
    def __init__(self, data):
        self.data = data
    
    def getvalue(self, key, default=''):
        return self.data.get(key, default)
    
    def getlist(self, key):
        val = self.data.get(key, [])
        if isinstance(val, list):
            return val
        return [val] if val else []

def test_quick_mode():
    print("Testing Quick Mode (dropdown selection):")
    print("-" * 60)
    
    form_data = {
        'source_ip': '10.1.1.1',
        'dest_ip': '10.2.1.1',
        'port_mode': 'quick',
        'quick_ports': ['22/tcp', '80/tcp', '443/tcp'],  # Multiple selections
        'default_protocol': 'tcp'
    }
    
    form = MockForm(form_data)
    port_parser = PortParser()
    validator = InputValidator()
    
    # Process form like main.py does
    port_mode = form.getvalue('port_mode', 'quick')
    
    if port_mode == 'quick':
        quick_ports = form.getlist('quick_ports')
        if not quick_ports:
            print("ERROR: No services selected")
            return
        dest_port_spec = ','.join(quick_ports)
    else:
        dest_port_spec = form.getvalue('dest_ports', '').strip()
    
    default_protocol = form.getvalue('default_protocol', 'tcp').lower()
    
    print(f"Port specification: {dest_port_spec}")
    print(f"Default protocol: {default_protocol}")
    
    # Parse ports
    try:
        port_protocol_list = port_parser.parse_port_spec(dest_port_spec, default_protocol)
        print(f"Parsed ports: {port_protocol_list}")
        
        # Format for display
        port_list_str = port_parser.format_port_list(port_protocol_list)
        print(f"Formatted: {port_list_str}")
        
        # Show what would be tested
        print("\nServices to test:")
        for port, protocol in port_protocol_list:
            desc = port_parser.get_service_description(port, protocol)
            print(f"  - {port}/{protocol}: {desc}")
            
    except ValueError as e:
        print(f"ERROR: {e}")

def test_manual_mode():
    print("\n\nTesting Manual Mode (text input):")
    print("-" * 60)
    
    form_data = {
        'source_ip': '10.1.1.1',
        'dest_ip': '10.2.1.1',
        'port_mode': 'manual',
        'dest_ports': '22/tcp,80,443/tcp,8000-8002/udp',
        'default_protocol': 'tcp'
    }
    
    form = MockForm(form_data)
    port_parser = PortParser()
    
    # Process form
    port_mode = form.getvalue('port_mode', 'quick')
    
    if port_mode == 'quick':
        quick_ports = form.getlist('quick_ports')
        dest_port_spec = ','.join(quick_ports)
    else:
        dest_port_spec = form.getvalue('dest_ports', '').strip()
    
    default_protocol = form.getvalue('default_protocol', 'tcp').lower()
    
    print(f"Port specification: {dest_port_spec}")
    print(f"Default protocol: {default_protocol}")
    
    # Parse ports
    try:
        port_protocol_list = port_parser.parse_port_spec(dest_port_spec, default_protocol)
        print(f"Parsed ports: {port_protocol_list}")
        
        # Format for display
        port_list_str = port_parser.format_port_list(port_protocol_list)
        print(f"Formatted: {port_list_str}")
        
        print(f"\nTotal services to test: {len(port_protocol_list)}")
        
    except ValueError as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_quick_mode()
    test_manual_mode()