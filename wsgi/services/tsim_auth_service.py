#!/usr/bin/env -S python3 -B -u
"""
TSIM Authentication Service
Handles user authentication and password management
"""

import os
import json
import hashlib
import secrets
import logging
import subprocess
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

# Try to import pam - will be preloaded by app.wsgi
try:
    import pam
    PAM_AVAILABLE = True
except ImportError:
    PAM_AVAILABLE = False


class TsimAuthService:
    """Authentication service for TSIM application"""
    
    def __init__(self, config_service):
        """Initialize authentication service
        
        Args:
            config_service: TsimConfigService instance
        """
        self.config = config_service
        self.logger = logging.getLogger('tsim.auth')
        
        # Get users file path
        self.users_file = Path(config_service.get('users_file', '/opt/tsim/conf/users.json'))
        
        # Get external auth configuration
        self.external_auth_enabled = config_service.get('external_auth_enabled', True)  # Default to True for PAM
        self.external_auth_type = config_service.get('external_auth_type', 'pam')  # pam or ldap
        self.pam_service = config_service.get('pam_service', 'login')
        self.ldap_server = config_service.get('ldap_server')
        self.ldap_base_dn = config_service.get('ldap_base_dn')
        
        # Get Unix group for admin privileges from traceroute_simulator.yaml
        # Default to None - PAM users won't be admins unless explicitly configured
        self.admin_unix_group = self._load_unix_group_from_yaml()
        if self.admin_unix_group:
            self.logger.info(f"Admin Unix group configured: {self.admin_unix_group}")
        else:
            self.logger.info("No admin Unix group configured - PAM users will not get admin privileges")
        
        # Load users if file exists, otherwise initialize empty
        if self.users_file.exists():
            self.users = self._load_users()
        else:
            self.users = {}
            self.logger.warning(f"No users file found at {self.users_file}")
            self.logger.warning("Please run scripts/create_user.sh to create an admin user")
        
        self.logger.info(f"Auth service initialized (external: {self.external_auth_enabled}, type: {self.external_auth_type})")
    
    def _load_unix_group_from_yaml(self) -> Optional[str]:
        """Load Unix group from traceroute_simulator.yaml configuration
        
        Returns:
            Unix group name or None if not configured
        """
        # Get the traceroute_simulator.yaml path from config service
        yaml_path = self.config.get('traceroute_simulator_conf')
        if not yaml_path:
            self.logger.info("No traceroute_simulator_conf path configured in config.json - PAM users will not get admin privileges")
            return None
        
        config_file = Path(yaml_path)
        if not config_file.exists():
            self.logger.warning(f"traceroute_simulator.yaml not found at configured path: {yaml_path}")
            return None
        
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f) or {}
            
            # Get system.unix_group from config
            system_config = config.get('system', {})
            unix_group = system_config.get('unix_group')
            
            if unix_group:
                self.logger.info(f"Loaded Unix group '{unix_group}' from {config_file}")
                return unix_group
            else:
                self.logger.debug(f"No unix_group found in system section of {config_file}")
                
        except Exception as e:
            self.logger.error(f"Failed to load config from {config_file}: {e}")
        
        return None
    
    def _load_users(self) -> Dict[str, Dict[str, Any]]:
        """Load users from JSON file
        
        Returns:
            Dictionary of users
        """
        try:
            with open(self.users_file, 'r') as f:
                users = json.load(f)
            self.logger.info(f"Loaded {len(users)} users from {self.users_file}")
            return users
        except Exception as e:
            self.logger.error(f"Failed to load users file: {e}")
            return {}
    
    def _save_users(self) -> bool:
        """Save users to JSON file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            self.users_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            
            # Write to temp file first
            temp_file = self.users_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(self.users, f, indent=2)
            
            # Atomic rename
            temp_file.rename(self.users_file)
            
            # Set restrictive permissions
            os.chmod(self.users_file, 0o600)
            
            self.logger.info("Users file saved successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save users file: {e}")
            return False
    
    
    def _hash_password(self, password: str, salt: Optional[str] = None) -> str:
        """Hash a password using SHA256 with salt
        
        Args:
            password: Plain text password
            salt: Optional salt (generated if not provided)
            
        Returns:
            Salted password hash in format: salt$hash
        """
        if salt is None:
            salt = secrets.token_hex(16)
        
        # Create salted hash
        salted = f"{salt}{password}".encode('utf-8')
        hash_value = hashlib.sha256(salted).hexdigest()
        
        return f"{salt}${hash_value}"
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against a hash
        
        Args:
            password: Plain text password
            password_hash: Stored password hash
            
        Returns:
            True if password matches, False otherwise
        """
        try:
            # Extract salt from hash
            salt, _ = password_hash.split('$')
            
            # Hash the provided password with the same salt
            test_hash = self._hash_password(password, salt)
            
            # Compare hashes (constant time comparison)
            return secrets.compare_digest(test_hash, password_hash)
        except Exception as e:
            self.logger.error(f"Error verifying password: {e}")
            return False
    
    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Authenticate a user
        
        Args:
            username: Username
            password: Password
            
        Returns:
            Tuple of (success, error_message, user_data)
        """
        # Try local authentication first
        if username in self.users:
            user = self.users[username]
            
            # Check if user is active
            if not user.get('active', True):
                self.logger.warning(f"Authentication failed - user inactive: {username}")
                return False, "Account is disabled", None
            
            # Verify password
            if self._verify_password(password, user['password_hash']):
                # Authentication successful
                self.logger.info(f"Authentication successful (local) for user: {username}")
                
                # Return user data (without password hash)
                user_data = {
                    'username': user['username'],
                    'role': user.get('role', 'user'),
                    'active': user.get('active', True),
                    'auth_type': 'local'
                }
                return True, None, user_data
        
        # Try external authentication if enabled
        if self.external_auth_enabled:
            success, ext_user_data = self._authenticate_external(username, password)
            if success:
                self.logger.info(f"Authentication successful (external) for user: {username}")
                return True, None, ext_user_data
        
        # Authentication failed
        self.logger.warning(f"Authentication failed for user: {username}")
        return False, "Invalid username or password", None
    
    def _authenticate_external(self, username: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Authenticate via external system
        
        Args:
            username: Username
            password: Password
            
        Returns:
            Tuple of (success, user_data)
        """
        if self.external_auth_type == 'pam':
            return self._authenticate_pam(username, password)
        elif self.external_auth_type == 'ldap':
            return self._authenticate_ldap(username, password)
        else:
            self.logger.error(f"Unknown external auth type: {self.external_auth_type}")
            return False, None
    
    def _is_user_in_group(self, username: str, group_name: str) -> bool:
        """Check if a user is a member of a Unix group
        
        Args:
            username: Username to check
            group_name: Unix group name
            
        Returns:
            True if user is in group, False otherwise
        """
        try:
            import grp
            import pwd
            
            self.logger.debug(f"Checking if user '{username}' is in group '{group_name}'")
            
            # Get the group info
            group_info = grp.getgrnam(group_name)
            self.logger.debug(f"Group '{group_name}' members: {group_info.gr_mem}")
            
            # Check if user is in the group's member list
            if username in group_info.gr_mem:
                self.logger.debug(f"User '{username}' found in group '{group_name}' member list")
                return True
            
            # Also check if this is the user's primary group
            try:
                user_info = pwd.getpwnam(username)
                if user_info.pw_gid == group_info.gr_gid:
                    self.logger.debug(f"Group '{group_name}' is primary group for user '{username}'")
                    return True
            except KeyError:
                self.logger.debug(f"User '{username}' not found in passwd database")
                pass
            
            self.logger.debug(f"User '{username}' is NOT in group '{group_name}'")
            return False
            
        except KeyError:
            self.logger.warning(f"Group '{group_name}' not found in system")
            return False
        except Exception as e:
            self.logger.error(f"Error checking group membership: {e}")
            return False
    
    def _authenticate_pam(self, username: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Authenticate via PAM
        
        Args:
            username: Username
            password: Password
            
        Returns:
            Tuple of (success, user_data)
        """
        if not PAM_AVAILABLE:
            self.logger.error("PAM module not available")
            return False, None
            
        try:
            p = pam.pam()
            if p.authenticate(username, password, service=self.pam_service):
                # Check if user should have admin role based on group membership
                role = 'user'
                if self.admin_unix_group:
                    self.logger.debug(f"Checking admin group membership for PAM user '{username}'")
                    if self._is_user_in_group(username, self.admin_unix_group):
                        role = 'admin'
                        self.logger.info(f"PAM user '{username}' granted admin role (member of {self.admin_unix_group})")
                    else:
                        self.logger.info(f"PAM user '{username}' authenticated with user role (not member of {self.admin_unix_group})")
                else:
                    self.logger.debug(f"No admin group configured, PAM user '{username}' gets user role")
                
                user_data = {
                    'username': username,
                    'role': role,
                    'active': True,
                    'auth_type': 'pam'
                }
                self.logger.info(f"PAM authentication successful for '{username}' with role '{role}'")
                return True, user_data
            return False, None
            
        except Exception as e:
            self.logger.error(f"PAM authentication error: {e}")
            return False, None
    
    def _authenticate_ldap(self, username: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Authenticate via LDAP
        
        Args:
            username: Username
            password: Password
            
        Returns:
            Tuple of (success, user_data)
        """
        if not self.ldap_server or not self.ldap_base_dn:
            self.logger.error("LDAP configuration missing")
            return False, None
        
        try:
            import ldap3
            
            user_dn = f"uid={username},{self.ldap_base_dn}"
            server = ldap3.Server(self.ldap_server)
            conn = ldap3.Connection(server, user=user_dn, password=password)
            
            if conn.bind():
                user_data = {
                    'username': username,
                    'role': 'user',
                    'active': True,
                    'auth_type': 'ldap'
                }
                conn.unbind()
                return True, user_data
            
            return False, None
            
        except ImportError:
            self.logger.error("ldap3 module not available")
            return False, None
        except Exception as e:
            self.logger.error(f"LDAP authentication error: {e}")
            return False, None
    
    def create_user(self, username: str, password: str, role: str = 'user') -> Tuple[bool, Optional[str]]:
        """Create a new user
        
        Args:
            username: Username
            password: Password
            role: User role (user/admin)
            
        Returns:
            Tuple of (success, error_message)
        """
        # Check if user already exists
        if username in self.users:
            return False, "User already exists"
        
        # Validate username
        if not username or len(username) < 3:
            return False, "Username must be at least 3 characters"
        
        # Validate password
        if not password or len(password) < 8:
            return False, "Password must be at least 8 characters"
        
        # Create user
        self.users[username] = {
            'username': username,
            'password_hash': self._hash_password(password),
            'role': role,
            'active': True,
            'created': datetime.now().isoformat()
        }
        
        # Save users
        if self._save_users():
            self.logger.info(f"Created new user: {username} with role: {role}")
            return True, None
        else:
            # Rollback
            del self.users[username]
            return False, "Failed to save user"
    
    def change_password(self, username: str, old_password: str, 
                       new_password: str) -> Tuple[bool, Optional[str]]:
        """Change a user's password
        
        Args:
            username: Username
            old_password: Current password
            new_password: New password
            
        Returns:
            Tuple of (success, error_message)
        """
        # Authenticate with old password
        success, error, _ = self.authenticate(username, old_password)
        if not success:
            return False, error
        
        # Validate new password
        if not new_password or len(new_password) < 8:
            return False, "New password must be at least 8 characters"
        
        # Update password
        self.users[username]['password_hash'] = self._hash_password(new_password)
        
        # Save users
        if self._save_users():
            self.logger.info(f"Password changed for user: {username}")
            return True, None
        else:
            return False, "Failed to save password change"
    
    def reset_password(self, username: str, new_password: str) -> Tuple[bool, Optional[str]]:
        """Reset a user's password (admin only)
        
        Args:
            username: Username
            new_password: New password
            
        Returns:
            Tuple of (success, error_message)
        """
        # Check if user exists
        if username not in self.users:
            return False, "User not found"
        
        # Validate new password
        if not new_password or len(new_password) < 8:
            return False, "Password must be at least 8 characters"
        
        # Update password
        self.users[username]['password_hash'] = self._hash_password(new_password)
        
        # Save users
        if self._save_users():
            self.logger.info(f"Password reset for user: {username}")
            return True, None
        else:
            return False, "Failed to save password reset"
    
    def delete_user(self, username: str) -> Tuple[bool, Optional[str]]:
        """Delete a user
        
        Args:
            username: Username
            
        Returns:
            Tuple of (success, error_message)
        """
        # Check if user exists
        if username not in self.users:
            return False, "User not found"
        
        # Don't delete the last admin
        if self.users[username].get('role') == 'admin':
            admin_count = sum(1 for u in self.users.values() if u.get('role') == 'admin')
            if admin_count <= 1:
                return False, "Cannot delete the last admin user"
        
        # Delete user
        del self.users[username]
        
        # Save users
        if self._save_users():
            self.logger.info(f"Deleted user: {username}")
            return True, None
        else:
            return False, "Failed to save user deletion"
    
    def list_users(self) -> list:
        """List all users
        
        Returns:
            List of user summaries (without password hashes)
        """
        users = []
        for username, user in self.users.items():
            users.append({
                'username': username,
                'role': user.get('role', 'user'),
                'active': user.get('active', True),
                'created': user.get('created', 'unknown')
            })
        return users
    
    def is_admin(self, username: str) -> bool:
        """Check if user is admin
        
        Args:
            username: Username
            
        Returns:
            True if admin, False otherwise
        """
        # Check local users first
        if username in self.users:
            return self.users[username].get('role') == 'admin'
        
        # For PAM users, check group membership
        if self.external_auth_enabled and self.external_auth_type == 'pam':
            if self.admin_unix_group and self._is_user_in_group(username, self.admin_unix_group):
                return True
        
        return False
