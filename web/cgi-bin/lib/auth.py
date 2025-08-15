#!/usr/bin/env -S python3 -B -u
"""Authentication system for web service with SSSD fallback support"""
import hashlib
import json
import os
import secrets
import sys
from datetime import datetime
from typing import Tuple, Optional

# Try to import PAM module, but make it optional
# Note: python-pam is only required for SSSD authentication in the web interface
# Install via: sudo pip3 install python-pam
# Or via: sudo make pam-config
PAM_AVAILABLE = False
pam = None

try:
    import pam
    PAM_AVAILABLE = True
except ImportError:
    PAM_AVAILABLE = False

class AuthManager:
    def __init__(self, users_dir="/var/www/traceroute-web/data/users",
                 enable_sssd=True, pam_service='traceroute-web',
                 log_dir="/var/www/traceroute-web/logs"):
        """Initialize AuthManager with optional SSSD support.
        
        Args:
            users_dir: Directory for local user JSON files
            enable_sssd: Enable SSSD/PAM authentication fallback
            pam_service: PAM service name to use for authentication
            log_dir: Directory for authentication logs
        """
        self.users_dir = users_dir
        self.enable_sssd = enable_sssd and PAM_AVAILABLE
        self.pam_service = pam_service
        self.log_dir = log_dir
        os.makedirs(users_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)
        
        # Log initialization status
        if enable_sssd and not PAM_AVAILABLE:
            self._log_auth_event('warning', 'SSSD authentication requested but python-pam not available')
    
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
    
    def verify_user_extended(self, username: str, password: str) -> Tuple[bool, Optional[str]]:
        """Verify user credentials using local database first, then SSSD if enabled.
        
        Args:
            username: Username to authenticate
            password: Password to verify
            
        Returns:
            Tuple of (success: bool, auth_source: str or None)
            auth_source is 'local', 'sssd', or None if authentication failed
        """
        # First try local database authentication
        try:
            if self._verify_local_user(username, password):
                self._log_auth_event('info', f'Local authentication successful for user: {username}')
                return True, 'local'
        except Exception as e:
            self._log_auth_event('error', f'Local authentication error for user {username}: {str(e)}')
        
        # If local fails and SSSD is enabled, try PAM/SSSD
        if self.enable_sssd:
            try:
                if self._verify_sssd_user(username, password):
                    self._log_auth_event('info', f'SSSD authentication successful for user: {username}')
                    return True, 'sssd'
                else:
                    self._log_auth_event('info', f'SSSD authentication failed for user: {username}')
            except Exception as e:
                self._log_auth_event('error', f'SSSD authentication error for user {username}: {str(e)}')
        
        self._log_auth_event('warning', f'All authentication methods failed for user: {username}')
        return False, None
    
    def verify_user(self, username: str, password: str) -> bool:
        """Legacy method for backward compatibility.
        
        Returns only boolean success status.
        """
        success, _ = self.verify_user_extended(username, password)
        return success
    
    def _verify_local_user(self, username: str, password: str) -> bool:
        """Verify user against local JSON database.
        
        Args:
            username: Username to authenticate
            password: Password to verify
            
        Returns:
            True if authentication successful, False otherwise
        """
        user_file = os.path.join(self.users_dir, f"{username}.json")
        if not os.path.exists(user_file):
            return False
        
        try:
            with open(user_file, 'r') as f:
                user_data = json.load(f)
            
            _, pwd_hash = self.hash_password(password, user_data['salt'])
            return pwd_hash == user_data['password_hash']
        except (IOError, json.JSONDecodeError, KeyError) as e:
            self._log_auth_event('error', f'Error reading local user file for {username}: {str(e)}')
            return False
    
    def _verify_sssd_user(self, username: str, password: str) -> bool:
        """Verify user using PAM/SSSD authentication.
        
        Args:
            username: Username to authenticate
            password: Password to verify
            
        Returns:
            True if authentication successful, False otherwise
        """
        if not PAM_AVAILABLE or pam is None:
            return False
        
        try:
            # Use the pip python-pam module API
            self._log_auth_event('debug', f'Starting PAM auth for {username} with service {self.pam_service}')
            
            p = pam.pam()
            result = p.authenticate(username, password, service=self.pam_service)
            
            if result:
                self._log_auth_event('debug', f'PAM auth successful for {username}')
                return True
            else:
                # Log PAM error details if available
                if hasattr(p, 'code') and hasattr(p, 'reason'):
                    self._log_auth_event('debug', f'PAM auth failed for {username}: {p.reason} (code={p.code})')
                else:
                    self._log_auth_event('debug', f'PAM auth failed for {username}')
                return False
                
        except Exception as e:
            self._log_auth_event('error', f'PAM authentication exception for {username}: {str(e)}')
            return False
    
    def _log_auth_event(self, level: str, message: str):
        """Log authentication events to file.
        
        Args:
            level: Log level (debug, info, warning, error)
            message: Log message
        """
        try:
            log_file = os.path.join(self.log_dir, 'auth.log')
            timestamp = datetime.utcnow().isoformat()
            with open(log_file, 'a') as f:
                f.write(f"[{timestamp}] [{level.upper()}] {message}\n")
        except Exception:
            # Silently fail if logging fails to avoid breaking authentication
            pass