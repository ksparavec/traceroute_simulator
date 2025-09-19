#!/usr/bin/env -S python3 -B -u
import warnings
warnings.filterwarnings("ignore", message="'cgi' is deprecated")
warnings.filterwarnings("ignore", message="'cgitb' is deprecated")
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
    <style>
        .password-container {{
            position: relative;
            display: inline-block;
            width: 100%;
        }}
        .password-container input {{
            width: 100%;
            padding-right: 40px;
        }}
        .password-toggle {{
            position: absolute;
            right: 10px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            cursor: pointer;
            padding: 5px;
            font-size: 18px;
            color: #666;
        }}
        .password-toggle:hover {{
            color: #333;
        }}
        .eye-icon {{
            width: 20px;
            height: 20px;
            display: inline-block;
        }}
    </style>
    <script>
        function togglePassword() {{
            var passwordInput = document.getElementById('password');
            var toggleBtn = document.getElementById('toggleBtn');
            
            if (passwordInput.type === 'password') {{
                passwordInput.type = 'text';
                toggleBtn.innerHTML = '<svg class="eye-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle><line x1="1" y1="1" x2="23" y2="23"></line></svg>';
                toggleBtn.title = 'Hide password';
            }} else {{
                passwordInput.type = 'password';
                toggleBtn.innerHTML = '<svg class="eye-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>';
                toggleBtn.title = 'Show password';
            }}
        }}
    </script>
</head>
<body>
    <div class="login-container">
        <h1>Network Reachability Test</h1>
        <h2>Login</h2>
        {f'<div class="error">{error}</div>' if error else ''}
        <form method="POST" action="/cgi-bin/login.py">
            <label>Username: <input type="text" name="username" required></label>
            <label>Password: 
                <div class="password-container">
                    <input type="password" id="password" name="password" required>
                    <button type="button" id="toggleBtn" class="password-toggle" onclick="togglePassword()" title="Show password">
                        <svg class="eye-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                            <circle cx="12" cy="12" r="3"></circle>
                        </svg>
                    </button>
                </div>
            </label>
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
    
    # Verify credentials with support for dual authentication sources
    # Use extended method if available, otherwise fall back to legacy
    if hasattr(auth_mgr, 'verify_user_extended'):
        success, auth_source = auth_mgr.verify_user_extended(username, password)
    else:
        # Backward compatibility for legacy AuthManager
        success = auth_mgr.verify_user(username, password)
        auth_source = 'local' if success else None
    
    if success:
        # Create session
        session_id, cookie = session_mgr.create_session(username)
        
        # Log successful login with authentication source
        logger.log_access(
            username=username,
            action=f"login_success_{auth_source}",
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