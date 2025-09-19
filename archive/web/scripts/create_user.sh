#!/bin/bash
# create_user.sh - Create a new user for the web interface

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CGI_DIR="$SCRIPT_DIR/../cgi-bin"

cd "$CGI_DIR"

python3 -B -u -c "
import sys
import getpass
sys.path.append('lib')
from auth import AuthManager

username = input('Username: ')
password = getpass.getpass('Password: ')
password_confirm = getpass.getpass('Confirm password: ')

if password != password_confirm:
    print('Passwords do not match')
    sys.exit(1)

auth = AuthManager()
if auth.create_user(username, password):
    print(f'User {username} created successfully')
else:
    print(f'User {username} already exists')
"