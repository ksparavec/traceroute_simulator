#!/usr/bin/env -S python3 -B -u
import cgi
import cgitb
import os
import sys
import json
import hashlib
import hmac
from http import cookies

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from session import SessionManager
from validator import InputValidator
from executor import CommandExecutor
from logger import AuditLogger
from config import Config

# Enable error logging but not display
cgitb.enable(display=0, logdir="/var/www/traceroute-web/logs")

def get_session_id():
    """Extract session ID from cookie"""
    cookie_str = os.environ.get('HTTP_COOKIE', '')
    cookie = cookies.SimpleCookie(cookie_str)
    if 'session_id' in cookie:
        return cookie['session_id'].value
    return None

def show_error(message="An error occurred. Please try again."):
    """Show generic error message to user"""
    print("Content-Type: text/html\n")
    print(f"""<!DOCTYPE html>
<html>
<head>
    <title>Error - Network Reachability Test</title>
    <link rel="stylesheet" href="/css/style.css">
</head>
<body>
    <div class="error-container">
        <h1>Error</h1>
        <p>{message}</p>
        <a href="/form.html">Back to form</a>
    </div>
</body>
</html>""")

def generate_shareable_link(run_id, config):
    """Generate secure shareable link"""
    secret = config.config['secret_key']
    token = hmac.new(
        key=secret.encode(),
        msg=run_id.encode(),
        digestmod=hashlib.sha256
    ).hexdigest()
    
    base_url = os.environ.get('HTTP_HOST', 'localhost')
    return f"https://{base_url}/cgi-bin/pdf_viewer.py?id={run_id}&token={token}"

def main():
    try:
        # Initialize components
        config = Config()
        session_mgr = SessionManager()
        logger = AuditLogger()
        validator = InputValidator()
        
        # Check session
        session_id = get_session_id()
        session = session_mgr.get_session(session_id)
        
        if not session:
            print("Status: 302 Found")
            print("Location: /login.html")
            print()
            return
        
        # Get form data
        form = cgi.FieldStorage()
        source_ip = form.getvalue('source_ip', '').strip()
        source_port = form.getvalue('source_port', '').strip()
        dest_ip = form.getvalue('dest_ip', '').strip()
        dest_port = form.getvalue('dest_port', '').strip()
        protocol = form.getvalue('protocol', 'tcp').lower()
        
        # Validate inputs
        if not validator.validate_ip(source_ip):
            raise ValueError("Invalid source IP")
        if not validator.validate_ip(dest_ip):
            raise ValueError("Invalid destination IP")
        if not validator.validate_port(dest_port):
            raise ValueError("Invalid destination port")
        if source_port and not validator.validate_port(source_port):
            raise ValueError("Invalid source port")
        if not validator.validate_protocol(protocol):
            raise ValueError("Invalid protocol")
        
        # Sanitize inputs
        source_ip = validator.sanitize_input(source_ip)
        dest_ip = validator.sanitize_input(dest_ip)
        dest_port = validator.sanitize_input(dest_port)
        source_port = validator.sanitize_input(source_port) if source_port else None
        
        # Save form data to session
        form_data = {
            'source_ip': source_ip,
            'source_port': source_port,
            'dest_ip': dest_ip,
            'dest_port': dest_port,
            'protocol': protocol
        }
        session_mgr.update_form_data(session_id, form_data)
        
        # Execute commands
        executor = CommandExecutor(config, logger)
        
        # 1. Execute trace
        run_id, trace_file = executor.execute_trace(
            session_id, session['username'], source_ip, dest_ip
        )
        
        # 2. Execute reachability test
        results_file = executor.execute_reachability_test(
            session_id, session['username'], run_id, trace_file,
            source_ip, source_port, dest_ip, dest_port, protocol
        )
        
        # 3. Generate PDF
        pdf_file = executor.generate_pdf(
            session_id, session['username'], run_id, trace_file, results_file
        )
        
        # Generate shareable link
        share_link = generate_shareable_link(run_id, config)
        
        # Redirect to PDF viewer HTML page
        print("Status: 302 Found")
        print(f"Location: /pdf_viewer_final.html?id={run_id}&session={session_id}")
        print()
        
    except Exception as e:
        # Log detailed error
        logger.log_error(
            error_type=type(e).__name__,
            error_msg=str(e),
            session_id=session_id if 'session_id' in locals() else None,
            traceback=True
        )
        # Show generic error to user
        show_error()

if __name__ == "__main__":
    main()