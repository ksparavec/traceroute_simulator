#!/usr/bin/env -S python3 -B -u
"""
Get test configuration for prefilling form
"""
import json
import os
import sys

# Add lib directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from config import Config

def main():
    # Load configuration
    config = Config()
    
    # Prepare response
    response = {
        'mode': config.config.get('traceroute_simulator_mode', 'prod'),
        'test_ips': None
    }
    
    # If in test mode, read the test trace file
    if response['mode'] == 'test':
        test_file = config.config.get('traceroute_simulator_test_trace_file', '')
        if test_file and os.path.exists(test_file):
            try:
                with open(test_file, 'r') as f:
                    trace_data = json.load(f)
                    response['test_ips'] = {
                        'source': trace_data.get('source', ''),
                        'destination': trace_data.get('destination', '')
                    }
            except:
                pass
    
    # Output JSON response
    print("Content-Type: application/json")
    print()
    print(json.dumps(response))

if __name__ == "__main__":
    main()