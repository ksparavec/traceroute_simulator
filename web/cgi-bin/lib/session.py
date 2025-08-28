#!/usr/bin/env -S python3 -B -u
"""Session management for web service"""
import os
import time
import json
import secrets
from http import cookies
from datetime import datetime, timedelta

class SessionManager:
    def __init__(self, session_dir="/var/www/traceroute-web/data/sessions", 
                 timeout=3600):
        self.session_dir = session_dir
        self.timeout = timeout
        os.makedirs(session_dir, exist_ok=True, mode=0o775)
    
    def create_session(self, username):
        session_id = secrets.token_urlsafe(32)
        session_file = os.path.join(self.session_dir, f"{session_id}.json")
        
        session_data = {
            'session_id': session_id,
            'username': username,
            'created': time.time(),
            'last_access': time.time(),
            'form_data': {},
            'ip_address': os.environ.get('REMOTE_ADDR', '')
        }
        
        with open(session_file, 'w') as f:
            json.dump(session_data, f)
        
        # Create cookie
        cookie = cookies.SimpleCookie()
        cookie['session_id'] = session_id
        cookie['session_id']['httponly'] = True
        cookie['session_id']['secure'] = True
        cookie['session_id']['samesite'] = 'Strict'
        cookie['session_id']['max-age'] = self.timeout
        
        return session_id, cookie
    
    def get_session(self, session_id):
        if not session_id:
            return None
            
        session_file = os.path.join(self.session_dir, f"{session_id}.json")
        if not os.path.exists(session_file):
            return None
        
        with open(session_file, 'r') as f:
            session_data = json.load(f)
        
        # Check timeout
        if time.time() - session_data['last_access'] > self.timeout:
            os.remove(session_file)
            return None
        
        # Update last access
        session_data['last_access'] = time.time()
        with open(session_file, 'w') as f:
            json.dump(session_data, f)
        
        return session_data
    
    def update_form_data(self, session_id, form_data):
        session_file = os.path.join(self.session_dir, f"{session_id}.json")
        if os.path.exists(session_file):
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            
            session_data['form_data'] = form_data
            session_data['last_access'] = time.time()
            
            with open(session_file, 'w') as f:
                json.dump(session_data, f)
    
    def destroy_session(self, session_id):
        session_file = os.path.join(self.session_dir, f"{session_id}.json")
        if os.path.exists(session_file):
            os.remove(session_file)
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions"""
        current_time = time.time()
        for filename in os.listdir(self.session_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.session_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        session_data = json.load(f)
                    if current_time - session_data['last_access'] > self.timeout:
                        os.remove(filepath)
                except:
                    pass