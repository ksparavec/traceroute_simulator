#!/usr/bin/env -S python3 -B -u
import warnings
warnings.filterwarnings("ignore", message="'cgi' is deprecated")
warnings.filterwarnings("ignore", message="'cgitb' is deprecated")
import cgi
import cgitb
import os
import sys
import json
import hashlib
import hmac
import tempfile
import subprocess
import uuid
from http import cookies

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from session import SessionManager
from validator import InputValidator
from executor import CommandExecutor
from logger import AuditLogger
from config import Config
from timing import TimingLogger
from port_parser import PortParser

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
        
        # Handle port selection modes
        port_mode = form.getvalue('port_mode', 'quick')
        port_parser = PortParser()
        
        # Debug logging
        logger.log_info(f"Port mode: {port_mode}")
        
        if port_mode == 'quick':
            # Get selected services from quick select
            quick_ports = form.getlist('quick_ports')
            logger.log_info(f"Quick ports selected: {quick_ports}")
            if not quick_ports:
                raise ValueError("No services selected")
            # Join selected ports
            dest_port_spec = ','.join(quick_ports)
        else:
            # Manual entry mode
            dest_port_spec = form.getvalue('dest_ports', '').strip()
            logger.log_info(f"Manual port spec: {dest_port_spec}")
            if not dest_port_spec:
                raise ValueError("No destination ports specified")
        
        default_protocol = form.getvalue('default_protocol', 'tcp').lower()
        user_trace_data = form.getvalue('user_trace_data', '').strip()
        
        # Validate inputs
        if not validator.validate_ip(source_ip):
            raise ValueError("Invalid source IP")
        if not validator.validate_ip(dest_ip):
            raise ValueError("Invalid destination IP")
        if source_port and not validator.validate_port(source_port):
            raise ValueError("Invalid source port")
        if not validator.validate_protocol(default_protocol):
            raise ValueError("Invalid default protocol")
        
        # Parse port specifications with service limit
        try:
            logger.log_info(f"Parsing port spec: {dest_port_spec} with default protocol: {default_protocol}")
            port_protocol_list = port_parser.parse_port_spec(dest_port_spec, default_protocol, max_services=10)
            logger.log_info(f"Parsed port list: {port_protocol_list}, count: {len(port_protocol_list)}")
            if not port_protocol_list:
                raise ValueError("No valid port/protocol combinations")
        except ValueError as e:
            logger.log_error("Port parsing failed", f"Spec: {dest_port_spec}, Error: {str(e)}")
            # Check if it's a service limit error
            if "Too many services" in str(e):
                show_error(str(e) + "\n\nPlease go back and reduce the number of services to 10 or less.")
                return
            raise ValueError(f"Invalid port specification: {str(e)}")
        
        # Validate user trace data if provided
        if user_trace_data:
            try:
                json.loads(user_trace_data)
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON format in trace data")
        
        # Sanitize inputs
        source_ip = validator.sanitize_input(source_ip)
        dest_ip = validator.sanitize_input(dest_ip)
        source_port = validator.sanitize_input(source_port) if source_port else None
        
        # Format port list for display
        port_list_str = port_parser.format_port_list(port_protocol_list)
        
        # Generate run ID first
        run_id = str(uuid.uuid4())
        
        # Save form data to session
        form_data = {
            'source_ip': source_ip,
            'source_port': source_port,
            'dest_ip': dest_ip,
            'port_protocol_list': port_protocol_list,  # List of (port, protocol) tuples
            'port_list_str': port_list_str,  # Formatted string for display
            'user_trace_data': user_trace_data,
            'run_id': run_id
        }
        session_mgr.update_form_data(session_id, form_data)
        
        # Start the test in background using a subprocess
        worker_script = f"""#!/usr/bin/env -S python3 -B -u
import sys
import os
sys.path.append('{os.path.join(os.path.dirname(__file__), 'lib')}')

from executor import CommandExecutor
from logger import AuditLogger
from config import Config
from timing import TimingLogger
import json
import hashlib
import hmac

# Set RUN_ID environment variable for reachability script
os.environ['RUN_ID'] = {repr(run_id)}

session_id = {repr(session_id)}
username = {repr(session['username'])}
source_ip = {repr(source_ip)}
source_port = {repr(source_port) if source_port else 'None'}
dest_ip = {repr(dest_ip)}
port_protocol_list = {repr(port_protocol_list)}
port_list_str = {repr(port_list_str)}
user_trace_data = {repr(user_trace_data)}
run_id = {repr(run_id)}

try:
    config = Config()
    logger = AuditLogger()
    executor = CommandExecutor(config, logger)
    # Use run_id for timing logger to match what the progress page expects
    timer = TimingLogger(session_id=run_id, operation_name="web_request")
    
    # Log progress
    logger.log_info(json.dumps({{
        "run_id": run_id,
        "phase": "START",
        "message": "Starting test execution"
    }}))
    
    # 1. Execute trace
    _, trace_file = executor.execute_trace(
        session_id, username, run_id, source_ip, dest_ip, 
        user_trace_data if user_trace_data else None
    )
    timer.log_operation("execute_trace", f"run_id={{run_id}}")
    
    logger.log_info(json.dumps({{
        "run_id": run_id,
        "phase": "TRACE_COMPLETE",
        "message": "Trace execution completed"
    }}))
    
    # 2. Execute optimized multi-service reachability test
    logger.log_info(json.dumps({{
        "run_id": run_id,
        "phase": "SERVICE_TESTS",
        "message": f"Testing {{len(port_protocol_list)}} services"
    }}))
    
    results_files = executor.execute_reachability_multi(
        session_id, username, run_id, trace_file,
        source_ip, source_port, dest_ip, port_protocol_list
    )
    timer.log_operation(f"network_reachability_test_multi_{{len(port_protocol_list)}}_services")
    
    logger.log_info(json.dumps({{
        "run_id": run_id,
        "phase": "PDF_GENERATION",
        "message": "Generating PDF report"
    }}))
    
    # 3. Generate multi-page PDF with all results
    pdf_file = executor.generate_multi_page_pdf(
        session_id, username, run_id, trace_file, results_files
    )
    timer.log_operation("generate_multi_page_pdf")
    
    # Generate shareable link
    secret = config.config['secret_key']
    token = hmac.new(
        key=secret.encode(),
        msg=run_id.encode(),
        digestmod=hashlib.sha256
    ).hexdigest()
    base_url = os.environ.get('HTTP_HOST', 'localhost')
    share_link = f"https://{{base_url}}/cgi-bin/pdf_viewer.py?id={{run_id}}&token={{token}}"
    timer.log_operation("generate_share_link")
    
    timer.log_operation("prepare_redirect")
    timer.finish("success")
    
    logger.log_info(json.dumps({{
        "run_id": run_id,
        "phase": "COMPLETE",
        "message": "Test completed successfully",
        "redirect_url": f"/pdf_viewer_final.html?id={{run_id}}&session={{session_id}}"
    }}))
    
except Exception as e:
    logger.log_error(
        error_type=type(e).__name__,
        error_msg=str(e),
        session_id=session_id,
        traceback=True
    )
    logger.log_info(json.dumps({{
        "run_id": run_id,
        "phase": "ERROR",
        "error": str(e)
    }}))
"""
        
        # Write worker script to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            worker_file = f.name
            f.write(worker_script)
        
        # Make it executable
        os.chmod(worker_file, 0o755)
        
        # Start the worker as a background process
        subprocess.Popen([sys.executable, worker_file], 
                        stdout=subprocess.DEVNULL, 
                        stderr=subprocess.DEVNULL,
                        start_new_session=True)
        
        # Redirect to progress page immediately
        print("Status: 302 Found")
        print(f"Location: /progress.html?run_id={run_id}&session={session_id}")
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