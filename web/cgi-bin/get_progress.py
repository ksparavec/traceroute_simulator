#!/usr/bin/env -S python3 -B -u
import cgi
import cgitb
import os
import sys
import json
import time
from datetime import datetime, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from session import SessionManager
from logger import AuditLogger
from config import Config

# Enable error logging but not display
cgitb.enable(display=0, logdir="/var/www/traceroute-web/logs")

def send_json_response(data):
    """Send JSON response"""
    print("Content-Type: application/json\n")
    print(json.dumps(data))

def parse_timing_log(run_id):
    """Parse the timing log to get the latest phase for a run"""
    log_file = "/var/www/traceroute-web/logs/timings.log"
    
    if not os.path.exists(log_file):
        return None
    
    latest_phase = None
    latest_details = None
    
    try:
        # Read the file in reverse to get the latest entries first
        with open(log_file, 'r') as f:
            lines = f.readlines()
            
        # Process lines in reverse order
        for line in reversed(lines):
            if f"[{run_id}]" in line:
                # Parse the line format: [timestamp] [session] duration | checkpoint | details
                parts = line.strip().split(' | ')
                if len(parts) >= 2:
                    checkpoint = parts[1].replace('REACHABILITY_', '')
                    details = parts[2] if len(parts) > 2 else ''
                    return checkpoint, details
                    
    except Exception as e:
        pass
    
    return None, None

def parse_audit_log(run_id):
    """Parse audit log for progress information"""
    log_file = "/var/www/traceroute-web/logs/audit.log"
    
    if not os.path.exists(log_file):
        return None
    
    latest_info = {}
    
    try:
        with open(log_file, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    
                    # Check if this is a progress log entry
                    if isinstance(entry, dict):
                        # Check for run_id in the entry or message
                        if entry.get('run_id') == run_id:
                            latest_info = entry
                        elif 'message' in entry and isinstance(entry['message'], str):
                            # Try to parse message as JSON for nested progress info
                            try:
                                msg_data = json.loads(entry['message'])
                                if msg_data.get('run_id') == run_id:
                                    latest_info = msg_data
                            except:
                                pass
                except:
                    pass
                    
    except Exception as e:
        pass
    
    return latest_info

def main():
    try:
        # Get query parameters
        form = cgi.FieldStorage()
        run_id = form.getvalue('run_id', '').strip()
        
        if not run_id:
            send_json_response({
                "error": "Missing run_id parameter"
            })
            return
        
        # Check timing log first (for reachability script phases)
        phase, details = parse_timing_log(run_id)
        
        # Also check audit log for additional info
        audit_info = parse_audit_log(run_id)
        
        response = {}
        
        if phase:
            response['phase'] = phase
            response['details'] = details
            
        if audit_info:
            if 'phase' in audit_info:
                response['phase'] = audit_info['phase']
            if 'message' in audit_info:
                response['message'] = audit_info['message']
            if 'error' in audit_info:
                response['error'] = audit_info['error']
            if 'redirect_url' in audit_info:
                response['redirect_url'] = audit_info['redirect_url']
                response['complete'] = True
            
            # Check for completion
            if audit_info.get('phase') == 'COMPLETE':
                response['complete'] = True
                
        # If no progress found, return a default
        if not response:
            response = {
                'phase': 'START',
                'message': 'Test in progress...'
            }
            
        send_json_response(response)
        
    except Exception as e:
        send_json_response({
            "error": str(e)
        })

if __name__ == "__main__":
    main()