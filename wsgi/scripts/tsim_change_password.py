#!/usr/bin/env -S python3 -B -u
"""
TSIM Change Password Script
Changes password for an existing WSGI web interface user
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
    """Main function to change user password"""
    try:
        # Initialize services
        config = TsimConfigService()
        auth = TsimAuthService(config)
        
        # Get username
        username = input('Username: ').strip()
        if not username:
            print('Error: Username cannot be empty')
            return 1
        
        # Check if user exists
        if username not in auth.users:
            print(f'Error: User {username} does not exist')
            return 1
        
        # For security, verify current password first (unless running as root)
        if os.geteuid() != 0:  # Not running as root
            current_password = getpass.getpass('Current password: ')
            success, error_msg, user_data = auth.authenticate(username, current_password)
            if not success:
                print('Error: Current password is incorrect')
                return 1
        else:
            print('Running as root, skipping current password verification')
        
        # Get new password
        new_password = getpass.getpass('New password: ')
        password_confirm = getpass.getpass('Confirm new password: ')
        
        if new_password != password_confirm:
            print('Error: Passwords do not match')
            return 1
        
        if len(new_password) < 8:
            print('Error: Password must be at least 8 characters long')
            return 1
        
        # Change password
        success, message = auth.change_password(username, new_password)
        
        if success:
            print(f'Password for user {username} changed successfully')
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