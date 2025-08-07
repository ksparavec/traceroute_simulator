#!/usr/bin/env -S python3 -B -u
"""
Format the network reachability test output into proper JSON.
"""

import sys
import json
import os

def safe_json_loads(data_str, default=None):
    """Safely parse JSON, returning default value on error."""
    if not data_str:
        return default
    try:
        return json.loads(data_str)
    except (json.JSONDecodeError, ValueError):
        # Log the error to stderr for debugging
        print(f"Warning: Failed to parse JSON: {data_str[:100]}...", file=sys.stderr)
        return default

def safe_int(value_str, default=None):
    """Safely convert to int, returning default value on error."""
    if not value_str:
        return default
    try:
        return int(value_str)
    except (ValueError, TypeError):
        return default

def main():
    # Read environment variables passed from bash script
    env_data = {}
    
    # Basic info
    env_data['source_ip'] = os.environ.get('SOURCE_IP', '')
    env_data['source_port'] = os.environ.get('SOURCE_PORT', '')
    env_data['dest_ip'] = os.environ.get('DEST_IP', '')
    env_data['dest_port'] = os.environ.get('DEST_PORT', '')
    env_data['protocol'] = os.environ.get('PROTOCOL', 'tcp')
    env_data['version'] = os.environ.get('VERSION', '1.0.0')
    env_data['timestamp'] = os.environ.get('TIMESTAMP', '')
    
    # Test results
    env_data['ping_result'] = os.environ.get('PING_RESULT', '')
    env_data['ping_return_code'] = os.environ.get('PING_RETURN_CODE', '')
    env_data['traceroute_result'] = os.environ.get('TRACEROUTE_RESULT', '')
    env_data['traceroute_return_code'] = os.environ.get('TRACEROUTE_RETURN_CODE', '')
    env_data['service_result'] = os.environ.get('SERVICE_RESULT', '')
    env_data['service_return_code'] = os.environ.get('SERVICE_RETURN_CODE', '')
    
    # Other data
    env_data['trace_result'] = os.environ.get('TRACE_RESULT', '')
    env_data['routers_in_path'] = os.environ.get('ROUTERS_IN_PATH', '')
    env_data['packet_count_analysis'] = os.environ.get('PACKET_COUNT_ANALYSIS', '')
    env_data['router_service_results'] = os.environ.get('ROUTER_SERVICE_RESULTS', '')
    env_data['execution_trace'] = os.environ.get('EXECUTION_TRACE', '')
    
    # Setup status
    env_data['source_host_added'] = os.environ.get('SOURCE_HOST_ADDED', 'false')
    env_data['dest_host_added'] = os.environ.get('DEST_HOST_ADDED', 'false')
    env_data['service_started'] = os.environ.get('SERVICE_STARTED', 'false')
    
    # Build output structure
    output = {
        'timestamp': env_data['timestamp'],
        'version': env_data['version'],
        'summary': {
            'source_ip': env_data['source_ip'],
            'source_port': env_data['source_port'] if env_data['source_port'] else 'ephemeral',
            'destination_ip': env_data['dest_ip'],
            'destination_port': env_data['dest_port'],
            'protocol': env_data['protocol']
        },
        'setup_status': {
            'source_host_added': env_data['source_host_added'].lower() == 'true',
            'destination_host_added': env_data['dest_host_added'].lower() == 'true',
            'service_started': env_data['service_started'].lower() == 'true'
        },
        'reachability_tests': {
            'ping': {
                'result': safe_json_loads(env_data['ping_result'], None),
                'return_code': safe_int(env_data['ping_return_code'], None)
            },
            'traceroute': {
                'result': safe_json_loads(env_data['traceroute_result'], None),
                'return_code': safe_int(env_data['traceroute_return_code'], None)
            },
            'service': {
                'result': safe_json_loads(env_data['service_result'], None),
                'return_code': safe_int(env_data['service_return_code'], None)
            }
        },
        'packet_count_analysis': safe_json_loads(env_data['packet_count_analysis'], []),
        'router_service_results': safe_json_loads(env_data['router_service_results'], {})
    }
    
    # Process execution trace - filter out steps < 0.01s and remove result field
    raw_trace = safe_json_loads(env_data['execution_trace'], [])
    operational_summary = []
    total_duration = 0.0
    
    for step in raw_trace:
        duration = step.get('duration_seconds', 0)
        if duration >= 0.01:
            # Round to 2 decimal places
            duration = round(duration, 2)
            total_duration += duration
            operational_summary.append({
                'step': step['step'],
                'duration_seconds': duration
            })
    
    # Add operational summary with total duration
    output['operational_summary'] = operational_summary
    output['total_duration_seconds'] = round(total_duration, 2)
    
    # Add reachability summary based on router service results
    if output['router_service_results']:
        reachable_via = []
        unreachable_via = []
        total_routers = len(output['router_service_results'])
        
        for router, status in output['router_service_results'].items():
            if status == 'OK':
                reachable_via.append(router)
            else:
                unreachable_via.append(router)
        
        # Service is only reachable if ALL routers allow it
        service_reachable = len(reachable_via) == total_routers and total_routers > 0
        
        output['reachability_summary'] = {
            'service_reachable': service_reachable,
            'reachable_via_routers': reachable_via,
            'blocked_by_routers': unreachable_via
        }
    
    print(json.dumps(output, indent=2))

if __name__ == '__main__':
    main()