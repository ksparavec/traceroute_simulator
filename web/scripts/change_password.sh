#!/bin/bash
# change_password.sh - Change password for an existing web interface user

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CGI_DIR="$SCRIPT_DIR/../cgi-bin"

# First get the username
echo -n "Username: "
read USERNAME

# Check if user exists
USERS_DIR="/var/www/traceroute-web/data/users"
USER_FILE="$USERS_DIR/${USERNAME}.json"

if [ ! -f "$USER_FILE" ]; then
    echo "User $USERNAME does not exist"
    exit 1
fi

# Now run the Python script with the username
cd "$CGI_DIR"

python3 -B -u -c "
import sys
import os
import json
import getpass
from datetime import datetime
sys.path.append('lib')
from auth import AuthManager

username = '$USERNAME'
users_dir = '/var/www/traceroute-web/data/users'
user_file = os.path.join(users_dir, f'{username}.json')

# For local users only - verify current password first
current_password = getpass.getpass('Current password: ')
auth = AuthManager()
if not auth._verify_local_user(username, current_password):
    print('Current password is incorrect')
    sys.exit(1)

# Get new password
new_password = getpass.getpass('New password: ')
password_confirm = getpass.getpass('Confirm new password: ')

if new_password != password_confirm:
    print('Passwords do not match')
    sys.exit(1)

if len(new_password) < 8:
    print('Password must be at least 8 characters long')
    sys.exit(1)

# Update password
try:
    # Read existing user data
    with open(user_file, 'r') as f:
        user_data = json.load(f)
    
    # Generate new salt and hash
    salt, pwd_hash = auth.hash_password(new_password)
    
    # Update user data
    user_data['salt'] = salt
    user_data['password_hash'] = pwd_hash
    user_data['password_changed'] = datetime.utcnow().isoformat()
    
    # Write back to file
    with open(user_file, 'w') as f:
        json.dump(user_data, f, indent=2)
    
    print(f'Password for user {username} changed successfully')
except Exception as e:
    print(f'Error changing password: {e}')
    sys.exit(1)
"