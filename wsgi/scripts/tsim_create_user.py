#!/usr/bin/env -S python3 -B -u
"""
TSIM Create User Script
Creates a new user for the WSGI web interface
"""

import sys
import os
import getpass
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.tsim_config_service import TsimConfigService
from services.tsim_auth_service import TsimAuthService

def main():
    """Main function to create a new user"""
    try:
        # Initialize services
        config = TsimConfigService()
        auth = TsimAuthService(config)
        
        # Get username
        username = input('Username: ').strip()
        if not username:
            print('Error: Username cannot be empty')
            return 1
        
        # Check if user already exists
        if username in auth.users:
            print(f'Error: User {username} already exists')
            return 1
        
        # Get role
        role = input('Role (admin/user) [user]: ').strip().lower() or 'user'
        if role not in ['admin', 'user']:
            print('Error: Role must be either "admin" or "user"')
            return 1
        
        # Get password
        password = getpass.getpass('Password: ')
        password_confirm = getpass.getpass('Confirm password: ')
        
        if password != password_confirm:
            print('Error: Passwords do not match')
            return 1
        
        if len(password) < 8:
            print('Error: Password must be at least 8 characters long')
            return 1
        
        # Create user
        success, message = auth.create_user(username, password, role)
        
        if success:
            print(f'User {username} created successfully with role {role}')
            return 0
        else:
            print(f'Error: {message}')
            return 1
            
    except KeyboardInterrupt:
        print('\nCancelled')
        return 1
    except Exception as e:
        print(f'Error: {e}')
        return 1

if __name__ == '__main__':
    sys.exit(main())