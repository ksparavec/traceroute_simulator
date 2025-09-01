#!/usr/bin/env -S python3 -B -u
"""Debug form submission to see what's being sent"""
import cgi
import cgitb
import os
import sys
import json

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

# Enable error logging
cgitb.enable(display=1)

def main():
    print("Content-Type: text/plain\n")
    
    # Get form data
    form = cgi.FieldStorage()
    
    print("=== FORM DEBUG ===\n")
    print(f"REQUEST_METHOD: {os.environ.get('REQUEST_METHOD', 'N/A')}")
    print(f"CONTENT_TYPE: {os.environ.get('CONTENT_TYPE', 'N/A')}")
    print(f"HTTP_COOKIE: {os.environ.get('HTTP_COOKIE', 'N/A')}\n")
    
    print("=== FORM FIELDS ===")
    for key in form.keys():
        if key == 'quick_ports':
            # Handle multi-select
            values = form.getlist(key)
            print(f"{key}: {values} (list)")
        else:
            value = form.getvalue(key, '')
            print(f"{key}: {value}")
    
    print("\n=== PORT PARSING TEST ===")
    
    from port_parser import PortParser
    
    port_mode = form.getvalue('port_mode', 'quick')
    port_parser = PortParser()
    
    print(f"Port mode: {port_mode}")
    
    if port_mode == 'quick':
        quick_ports = form.getlist('quick_ports')
        print(f"Quick ports selected: {quick_ports}")
        dest_port_spec = ','.join(quick_ports)
    else:
        dest_port_spec = form.getvalue('dest_ports', '').strip()
        print(f"Manual port spec: {dest_port_spec}")
    
    default_protocol = form.getvalue('default_protocol', 'tcp').lower()
    
    print(f"Port specification to parse: {dest_port_spec}")
    print(f"Default protocol: {default_protocol}")
    
    try:
        port_protocol_list = port_parser.parse_port_spec(dest_port_spec, default_protocol)
        print(f"\nParsed successfully: {port_protocol_list}")
        print(f"Total ports to test: {len(port_protocol_list)}")
        
        # Show formatted version
        formatted = port_parser.format_port_list(port_protocol_list)
        print(f"Formatted: {formatted}")
        
    except Exception as e:
        print(f"\nParsing error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()