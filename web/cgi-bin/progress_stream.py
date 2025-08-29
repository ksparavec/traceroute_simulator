#!/usr/bin/env -S python3 -B -u
"""Server-Sent Events endpoint for real-time progress streaming"""
import os
import sys
import time
import json
import re
from pathlib import Path
from datetime import datetime

# Disable output buffering
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)

def parse_timing_log_entry(line):
    """Parse a timing log entry"""
    # Format: [timestamp] [session_id] duration | phase | details
    pattern = r'\[(.*?)\] \[(.*?)\] \s*([\d.]+)s \| (.*?) \| (.*)'
    match = re.match(pattern, line)
    if match:
        timestamp, session_id, duration, phase, details = match.groups()
        return {
            'timestamp': timestamp,
            'session_id': session_id,
            'duration': float(duration),
            'phase': phase,
            'details': details.strip() if details else ''
        }
    return None

def parse_audit_log_entry(line):
    """Parse an audit log entry for JSON progress messages"""
    try:
        # Audit log is JSON format
        log_entry = json.loads(line)
        
        # Check if it's an INFO message
        if log_entry.get('type') == 'info':
            # Parse the message field which contains the actual progress JSON
            message = log_entry.get('message', '')
            try:
                data = json.loads(message)
                if 'run_id' in data and 'phase' in data:
                    return data
            except:
                pass
    except:
        pass
    return None

def stream_progress(run_id, session_id=None):
    """Stream progress updates for a given run_id"""
    timing_log = Path("/var/www/traceroute-web/logs/timings.log")
    audit_log = Path("/var/www/traceroute-web/logs/audit.log")
    processed_timing_lines = set()
    processed_audit_lines = set()
    all_phases = []
    
    # Track completion - don't set from phases, only from PDF existence
    is_complete = False
    redirect_url = None
    
    while True:
        try:
            # Read from timings.log
            if timing_log.exists():
                with open(timing_log, 'r') as f:
                    for line in f:
                        # Skip if we've already processed this line
                        line_hash = hash(line)
                        if line_hash in processed_timing_lines:
                            continue
                        
                        processed_timing_lines.add(line_hash)
                        
                        # Parse the log entry
                        entry = parse_timing_log_entry(line)
                        if entry and entry['session_id'] == run_id:
                            # Add to all phases
                            phase_info = {
                                'phase': entry['phase'],
                                'details': entry['details'],
                                'duration': entry['duration']
                            }
                            all_phases.append(phase_info)
                            
                            # Don't set completion from timing logs anymore
                            
                            # Send SSE event
                            data = {
                                'phase': entry['phase'],
                                'details': entry['details'],
                                'duration': entry['duration'],
                                'all_phases': all_phases,
                                'complete': is_complete,
                                'redirect_url': redirect_url
                            }
                            
                            # SSE format: "data: json\n\n"
                            print(f"data: {json.dumps(data)}\n\n", flush=True)
            
            # Read from audit.log for JSON progress messages
            if audit_log.exists():
                with open(audit_log, 'r') as f:
                    for line in f:
                        # Skip if we've already processed this line
                        line_hash = hash(line)
                        if line_hash in processed_audit_lines:
                            continue
                        
                        processed_audit_lines.add(line_hash)
                        
                        # Parse the audit log entry
                        entry = parse_audit_log_entry(line)
                        if entry and entry.get('run_id') == run_id:
                            # Add to all phases
                            phase_info = {
                                'phase': entry.get('phase', 'UNKNOWN'),
                                'details': entry.get('message', ''),
                                'duration': 0  # No duration in audit logs
                            }
                            all_phases.append(phase_info)
                            
                            # Don't set completion from audit logs either
                            
                            # Send SSE event
                            data = {
                                'phase': entry.get('phase', 'UNKNOWN'),
                                'details': entry.get('message', ''),
                                'duration': 0,
                                'all_phases': all_phases,
                                'complete': is_complete,
                                'redirect_url': redirect_url
                            }
                            
                            # SSE format: "data: json\n\n"
                            print(f"data: {json.dumps(data)}\n\n", flush=True)
                            
                            # Don't send duplicate complete event here - it's already in the data
            
            # Check for completion exactly like the polling script
            pdf_file = Path(f"/var/www/traceroute-web/data/pdfs/{run_id}_report.pdf")
            if pdf_file.exists():
                # PDF exists, test is complete
                is_complete = True
                # Use session_id if provided, otherwise just run_id
                if session_id:
                    redirect_url = f"/pdf_viewer_final.html?id={run_id}&session={session_id}"
                else:
                    redirect_url = f"/pdf_viewer_final.html?id={run_id}"
                
                # Send final complete message with redirect URL
                data = {
                    'phase': 'COMPLETE',
                    'details': 'Test completed successfully',
                    'duration': 0,
                    'all_phases': all_phases,
                    'complete': True,
                    'redirect_url': redirect_url
                }
                print(f"data: {json.dumps(data)}\n\n", flush=True)
                
                # Exit the loop
                return
            
            # Send heartbeat to keep connection alive
            print(": heartbeat\n\n", flush=True)
            
            # Sleep before next check
            time.sleep(0.5)  # Check more frequently than polling (500ms vs 2s)
            
        except Exception as e:
            # Send error event
            print(f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n", flush=True)
            return

def main():
    """Main entry point"""
    # Get query parameters
    query_string = os.environ.get('QUERY_STRING', '')
    params = {}
    if query_string:
        for param in query_string.split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                params[key] = value
    
    run_id = params.get('run_id', '')
    session_id = params.get('session', '')
    
    # SSE headers
    print("Content-Type: text/event-stream")
    print("Cache-Control: no-cache")
    print("Connection: keep-alive")
    print("Access-Control-Allow-Origin: *")
    print()
    
    if not run_id:
        print(f"event: error\ndata: {json.dumps({'error': 'Missing run_id parameter'})}\n\n")
        return
    
    # Start streaming progress
    try:
        stream_progress(run_id, session_id)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n")

if __name__ == "__main__":
    main()