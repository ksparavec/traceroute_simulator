#!/usr/bin/env -S python3 -B -u
import cgi
import cgitb
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from auth import AuthManager
from session import SessionManager
from logger import AuditLogger

# Enable error logging but not display
cgitb.enable(display=0, logdir="/var/www/traceroute-web/logs")

def show_login_form(error=None):
    print("Content-Type: text/html\n")
    print(f"""<!DOCTYPE html>
<html>
<head>
    <title>Login - Network Reachability Test</title>
    <link rel="stylesheet" href="/css/style.css">
</head>
<body>
    <div class="login-container">
        <h1>Network Reachability Test</h1>
        <h2>Login</h2>
        {f'<div class="error">{error}</div>' if error else ''}
        <form method="POST" action="/cgi-bin/login.py">
            <label>Username: <input type="text" name="username" required></label>
            <label>Password: <input type="password" name="password" required></label>
            <button type="submit">Login</button>
        </form>
    </div>
</body>
</html>""")

def main():
    form = cgi.FieldStorage()
    auth_mgr = AuthManager()
    session_mgr = SessionManager()
    logger = AuditLogger()
    
    # Get form data
    username = form.getvalue('username', '').strip()
    password = form.getvalue('password', '')
    
    if not username or not password:
        show_login_form()
        return
    
    # Verify credentials
    if auth_mgr.verify_user(username, password):
        # Create session
        session_id, cookie = session_mgr.create_session(username)
        
        # Log successful login
        logger.log_access(
            username=username,
            action="login_success",
            ip_address=os.environ.get('REMOTE_ADDR', ''),
            user_agent=os.environ.get('HTTP_USER_AGENT', '')
        )
        
        # Redirect to form with session cookie
        print(f"{cookie}")
        print("Status: 302 Found")
        print("Location: /form.html")
        print()
    else:
        # Log failed login
        logger.log_access(
            username=username,
            action="login_failed",
            ip_address=os.environ.get('REMOTE_ADDR', ''),
            user_agent=os.environ.get('HTTP_USER_AGENT', '')
        )
        show_login_form("Invalid username or password")

if __name__ == "__main__":
    main()