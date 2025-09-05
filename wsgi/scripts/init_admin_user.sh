#!/bin/bash
# Initialize admin user for TSIM WSGI
# This script directly creates the users.json file without loading the auth service

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WSGI_ROOT="$(dirname "$SCRIPT_DIR")"

# Determine config location
if [ -f "$WSGI_ROOT/conf/config.json" ]; then
    USERS_FILE="$WSGI_ROOT/conf/users.json"
else
    echo "Error: Cannot find config.json"
    exit 1
fi

# Check if users.json already exists
if [ -f "$USERS_FILE" ]; then
    echo "Users file already exists at $USERS_FILE"
    echo "Use ./change_password.sh to change passwords"
    exit 0
fi

echo "Creating admin user..."
echo -n "Password for admin user: "
read -s PASSWORD
echo
echo -n "Confirm password: "
read -s PASSWORD_CONFIRM
echo

if [ "$PASSWORD" != "$PASSWORD_CONFIRM" ]; then
    echo "Passwords do not match"
    exit 1
fi

if [ ${#PASSWORD} -lt 8 ]; then
    echo "Password must be at least 8 characters long"
    exit 1
fi

# Create users.json with Python
python3 -c "
import json
import hashlib
import secrets
from datetime import datetime

password = '$PASSWORD'
salt = secrets.token_hex(16)
hash_value = hashlib.sha256(f'{salt}{password}'.encode()).hexdigest()

users = {
    'admin': {
        'username': 'admin',
        'password_hash': f'{salt}\${hash_value}',
        'role': 'admin',
        'active': True,
        'created': datetime.utcnow().isoformat() + 'Z'
    }
}

with open('$USERS_FILE', 'w') as f:
    json.dump(users, f, indent=2)

print(f'Admin user created successfully')
print(f'Users file: $USERS_FILE')
"

# Set restrictive permissions
chmod 600 "$USERS_FILE"
if [ "$(id -u)" = "0" ]; then
    chown www-data:www-data "$USERS_FILE" 2>/dev/null || chown apache:apache "$USERS_FILE"
fi

echo "You can now log in with username: admin"