#!/usr/bin/env -S python3 -B -u
import os
import sys
from http import cookies

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from session import SessionManager
from logger import AuditLogger

def get_session_id():
    """Extract session ID from cookie"""
    cookie_str = os.environ.get('HTTP_COOKIE', '')
    cookie = cookies.SimpleCookie(cookie_str)
    if 'session_id' in cookie:
        return cookie['session_id'].value
    return None

def main():
    session_mgr = SessionManager()
    logger = AuditLogger()
    
    # Get session ID
    session_id = get_session_id()
    
    if session_id:
        # Get session info for logging
        session = session_mgr.get_session(session_id)
        if session:
            logger.log_access(
                username=session['username'],
                action="logout",
                ip_address=os.environ.get('REMOTE_ADDR', ''),
                user_agent=os.environ.get('HTTP_USER_AGENT', '')
            )
        
        # Destroy session
        session_mgr.destroy_session(session_id)
    
    # Clear cookie and redirect to login
    cookie = cookies.SimpleCookie()
    cookie['session_id'] = ''
    cookie['session_id']['expires'] = 'Thu, 01 Jan 1970 00:00:00 GMT'
    cookie['session_id']['httponly'] = True
    cookie['session_id']['secure'] = True
    
    print(f"{cookie}")
    print("Status: 302 Found")
    print("Location: /login.html")
    print()

if __name__ == "__main__":
    main()