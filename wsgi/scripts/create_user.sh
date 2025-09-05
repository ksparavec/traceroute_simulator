#!/bin/bash
# Create a new user for the TSIM WSGI web interface

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WSGI_ROOT="$(dirname "$SCRIPT_DIR")"

# Check if running from installed location or development
if [ -f "$WSGI_ROOT/conf/config.json" ]; then
    # Installed location
    export TSIM_WEB_ROOT="$WSGI_ROOT"
elif [ -f "$WSGI_ROOT/config.json" ]; then
    # Development location
    export TSIM_WEB_ROOT="$WSGI_ROOT"
else
    echo "Error: Cannot find config.json"
    echo "Please run from the WSGI installation directory"
    exit 1
fi

# Run the Python script
exec python3 "$SCRIPT_DIR/tsim_create_user.py" "$@"