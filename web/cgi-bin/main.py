#!/usr/bin/env -S python3 -B -u
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
        user_trace_data = form.getvalue('user_trace_data', '').strip()
        
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
        
        # Validate user trace data if provided
        if user_trace_data:
            try:
                json.loads(user_trace_data)
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON format in trace data")
        
        # Sanitize inputs
        source_ip = validator.sanitize_input(source_ip)
        dest_ip = validator.sanitize_input(dest_ip)
        dest_port = validator.sanitize_input(dest_port)
        source_port = validator.sanitize_input(source_port) if source_port else None
        
        # Generate run ID first
        run_id = str(uuid.uuid4())
        
        # Save form data to session
        form_data = {
            'source_ip': source_ip,
            'source_port': source_port,
            'dest_ip': dest_ip,
            'dest_port': dest_port,
            'protocol': protocol,
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
os.environ['RUN_ID'] = '{run_id}'

session_id = '{session_id}'
username = '{session['username']}'
source_ip = '{source_ip}'
source_port = {f'"{source_port}"' if source_port else 'None'}
dest_ip = '{dest_ip}'
dest_port = '{dest_port}'
protocol = '{protocol}'
user_trace_data = '''{user_trace_data}'''
run_id = '{run_id}'

try:
    config = Config()
    logger = AuditLogger()
    executor = CommandExecutor(config, logger)
    timer = TimingLogger(session_id=session_id, operation_name="web_request")
    
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
    
    # 2. Execute reachability test (this will log its own progress)
    results_file = executor.execute_reachability_test(
        session_id, username, run_id, trace_file,
        source_ip, source_port, dest_ip, dest_port, protocol
    )
    timer.log_operation("network_reachability_test.sh")
    
    logger.log_info(json.dumps({{
        "run_id": run_id,
        "phase": "PDF_GENERATION",
        "message": "Generating PDF report"
    }}))
    
    # 3. Generate PDF
    pdf_file = executor.generate_pdf(
        session_id, username, run_id, trace_file, results_file
    )
    timer.log_operation("generate_pdf.sh")
    
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