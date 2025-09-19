#!/usr/bin/env -S python3 -B -u
import warnings
warnings.filterwarnings("ignore", message="'cgi' is deprecated")
warnings.filterwarnings("ignore", message="'cgitb' is deprecated")
import cgi
import cgitb
import os
import sys
import hashlib
import hmac

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from session import SessionManager
from config import Config
from logger import AuditLogger

# Enable error logging but not display
cgitb.enable(display=0, logdir="/var/www/traceroute-web/logs")

def verify_token(run_id, token, config):
    """Verify shareable link token"""
    secret = config.config['secret_key']
    expected_token = hmac.new(
        key=secret.encode(),
        msg=run_id.encode(),
        digestmod=hashlib.sha256
    ).hexdigest()
    return token == expected_token

def serve_pdf(pdf_path, download=False):
    """Serve PDF file for inline display or download"""
    if not os.path.exists(pdf_path):
        print("Status: 404 Not Found")
        print("Content-Type: text/plain")
        print()
        print("PDF not found")
        return
    
    # Get file size
    file_size = os.path.getsize(pdf_path)
    
    # Send PDF headers
    print("Content-Type: application/pdf")
    print(f"Content-Length: {file_size}")
    
    if download:
        filename = os.path.basename(pdf_path)
        print(f"Content-Disposition: attachment; filename=\"{filename}\"")
    else:
        print("Content-Disposition: inline")
    
    print("Cache-Control: no-cache")
    print()
    
    # Send PDF content
    sys.stdout.flush()
    with open(pdf_path, 'rb') as f:
        sys.stdout.buffer.write(f.read())

def main():
    try:
        form = cgi.FieldStorage()
        config = Config()
        logger = AuditLogger()
        
        # Get parameters
        run_id = form.getvalue('id', '').strip()
        token = form.getvalue('token', '').strip()
        session_param = form.getvalue('session', '').strip()
        download = form.getvalue('download', '').strip() == '1'
        
        if not run_id:
            print("Status: 400 Bad Request")
            print("Content-Type: text/plain")
            print()
            print("Missing ID parameter")
            return
        
        # Check if accessing via session or shareable link
        authenticated = False
        username = "anonymous"
        
        if session_param:
            # Session-based access
            session_mgr = SessionManager()
            session = session_mgr.get_session(session_param)
            if session:
                authenticated = True
                username = session['username']
        elif token:
            # Token-based access (shareable link)
            if verify_token(run_id, token, config):
                authenticated = True
                username = "shared_link"
        
        if not authenticated:
            print("Status: 403 Forbidden")
            print("Content-Type: text/plain")
            print()
            print("Access denied")
            return
        
        # Log access
        logger.log_access(
            username=username,
            action=f"pdf_view_{run_id}",
            ip_address=os.environ.get('REMOTE_ADDR', ''),
            user_agent=os.environ.get('HTTP_USER_AGENT', '')
        )
        
        # Construct PDF path
        pdf_path = os.path.join("/var/www/traceroute-web/data/pdfs", 
                               f"{run_id}_report.pdf")
        
        # Serve PDF
        serve_pdf(pdf_path, download)
        
    except Exception as e:
        logger.log_error(
            error_type=type(e).__name__,
            error_msg=str(e),
            session_id=None,
            traceback=True
        )
        print("Status: 500 Internal Server Error")
        print("Content-Type: text/plain")
        print()
        print("An error occurred")

if __name__ == "__main__":
    main()