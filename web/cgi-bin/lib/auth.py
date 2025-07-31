#!/usr/bin/env -S python3 -B -u
"""Authentication system for web service"""
import hashlib
import json
import os
import secrets
from datetime import datetime

class AuthManager:
    def __init__(self, users_dir="/var/www/traceroute-web/data/users"):
        self.users_dir = users_dir
        os.makedirs(users_dir, exist_ok=True)
    
    def hash_password(self, password, salt=None):
        if salt is None:
            salt = secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac('sha256', 
                                       password.encode('utf-8'), 
                                       salt.encode('utf-8'), 
                                       100000)
        return salt, pwd_hash.hex()
    
    def create_user(self, username, password):
        user_file = os.path.join(self.users_dir, f"{username}.json")
        if os.path.exists(user_file):
            return False
        
        salt, pwd_hash = self.hash_password(password)
        user_data = {
            "username": username,
            "salt": salt,
            "password_hash": pwd_hash,
            "created": datetime.utcnow().isoformat()
        }
        
        with open(user_file, 'w') as f:
            json.dump(user_data, f)
        return True
    
    def verify_user(self, username, password):
        user_file = os.path.join(self.users_dir, f"{username}.json")
        if not os.path.exists(user_file):
            return False
        
        with open(user_file, 'r') as f:
            user_data = json.load(f)
        
        _, pwd_hash = self.hash_password(password, user_data['salt'])
        return pwd_hash == user_data['password_hash']