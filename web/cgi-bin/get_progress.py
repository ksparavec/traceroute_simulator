#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Get progress status for a running test
"""

import os
import sys
import json
import cgi
import cgitb
from pathlib import Path

# Enable error logging but not display
cgitb.enable(display=0, logdir="/var/www/traceroute-web/logs")

def send_json_response(data):
    """Send JSON response"""
    print("Content-Type: application/json\n")
    print(json.dumps(data))

def parse_timing_log(run_id):
    """Parse the timing log to get all phases for a run"""
    log_file = "/var/www/traceroute-web/logs/timings.log"
    
    if not os.path.exists(log_file):
        return None, None, [], f"Log file not found: {log_file}"
    
    latest_phase = None
    latest_details = None
    all_phases = []
    error_msg = None
    
    try:
        # Read the file to get all entries for this run
        with open(log_file, 'r') as f:
            lines = f.readlines()
            
        # Process lines to collect all phases with their details
        found_any = False
        for line in lines:
            # Check for the run_id only
            if f"[{run_id}]" in line:
                found_any = True
                # Parse the line format: [timestamp] [session] duration | checkpoint | details
                parts = line.strip().split(' | ')
                if len(parts) >= 2:
                    checkpoint = parts[1]
                    details = parts[2] if len(parts) > 2 else ''
                    
                    # Handle different phase prefixes
                    if checkpoint.startswith('REACHABILITY_'):
                        # Remove REACHABILITY_ prefix for standard phases
                        phase = checkpoint.replace('REACHABILITY_', '')
                    elif checkpoint.startswith('web_request_'):
                        # Keep web_request_ prefix for these phases
                        phase = checkpoint
                    elif checkpoint.startswith('PDF_GEN_'):
                        # Keep PDF_GEN_ prefix for PDF generation phases
                        phase = checkpoint
                    else:
                        # Keep as-is for other phases
                        phase = checkpoint
                    
                    # Skip unimportant phases that shouldn't be shown to user
                    if phase in ['PDF_GEN_venv_activate', 'TOTAL']:
                        continue
                    
                    # Track all phases with their details as a tuple
                    phase_info = {
                        "phase": phase,
                        "details": details
                    }
                    all_phases.append(phase_info)
                    
                    # Keep the latest as current phase
                    latest_phase = phase
                    latest_details = details
        
        if not found_any:
            error_msg = f"No entries found for run_id: {run_id}"
                    
    except Exception as e:
        error_msg = f"Error reading log: {str(e)}"
    
    return latest_phase, latest_details, all_phases, error_msg

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

def check_completion(run_id):
    """Check if the test has completed"""
    # Check for completion markers
    trace_file = f"/tmp/traceroute_{run_id}.json"
    pdf_file = f"/var/www/traceroute-web/data/pdfs/{run_id}_report.pdf"
    
    # If PDF exists, test is complete
    if os.path.exists(pdf_file):
        return True, pdf_file
    
    # Check if trace file exists and has results
    if os.path.exists(trace_file):
        try:
            with open(trace_file, 'r') as f:
                data = json.load(f)
                if 'test_completed' in data or 'results' in data:
                    return True, None
        except:
            pass
    
    return False, None

def main():
    try:
        # Get query parameters
        form = cgi.FieldStorage()
        run_id = form.getvalue('run_id', '').strip()
        session_id = form.getvalue('session', '').strip()
        
        if not run_id:
            send_json_response({
                "error": "Missing run_id parameter"
            })
            return
        
        # Parse timing log for current phase and all phases
        phase, details, all_phases, log_error = parse_timing_log(run_id)
        
        # Parse audit log for additional info
        audit_info = parse_audit_log(run_id)
        
        # Check if test is complete
        is_complete, pdf_path = check_completion(run_id)
        
        # Build response
        response = {
            "run_id": run_id,
            "phase": phase,
            "details": details,
            "all_phases": all_phases,  # Send all phases seen
            "complete": is_complete
        }
        
        # Add debug info if there was an error
        if log_error:
            response["debug_error"] = log_error
        
        # Add audit info if available
        if audit_info:
            response["message"] = audit_info.get("message", "")
            response["type"] = audit_info.get("type", "info")
        
        # Add redirect URL if complete
        if is_complete:
            if pdf_path and session_id:
                response["redirect_url"] = f"/pdf_viewer_final.html?id={run_id}&session={session_id}"
            elif pdf_path:
                response["redirect_url"] = f"/pdf_viewer_final.html?id={run_id}"
            else:
                response["redirect_url"] = "/"  # Go back to main page
        
        send_json_response(response)
        
    except Exception as e:
        send_json_response({
            "error": str(e)
        })

if __name__ == "__main__":
    main()