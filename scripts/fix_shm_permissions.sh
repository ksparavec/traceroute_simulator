#!/usr/bin/env bash
#
# Fix permissions for /dev/shm/tsim directory
# This script ensures the directory has proper permissions and group ownership
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Target directory
SHM_DIR="/dev/shm/tsim"
REQUIRED_GROUP="tsim-users"
REQUIRED_PERMS="2775"

echo "Fixing permissions for $SHM_DIR"
echo "========================================"

# Check if running with sufficient privileges
if [[ $EUID -ne 0 ]] && ! groups | grep -q "$REQUIRED_GROUP"; then
    echo -e "${YELLOW}Warning: Not running as root and not in $REQUIRED_GROUP group${NC}"
    echo "You may need to run this script with sudo to fix group ownership"
fi

# Check if tsim-users group exists
if ! getent group "$REQUIRED_GROUP" > /dev/null 2>&1; then
    echo -e "${RED}Error: Group '$REQUIRED_GROUP' does not exist${NC}"
    echo "Please create it first with: sudo groupadd $REQUIRED_GROUP"
    exit 1
fi

# Create directory if it doesn't exist
if [[ ! -d "$SHM_DIR" ]]; then
    echo "Creating directory: $SHM_DIR"
    mkdir -p "$SHM_DIR"
fi

# Fix group ownership
echo -n "Setting group ownership to $REQUIRED_GROUP... "
if chgrp "$REQUIRED_GROUP" "$SHM_DIR" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}Failed (need sudo?)${NC}"
fi

# Fix permissions (2775 = drwxrwsr-x)
echo -n "Setting permissions to $REQUIRED_PERMS... "
if chmod "$REQUIRED_PERMS" "$SHM_DIR" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}Failed (need sudo?)${NC}"
fi

# Verify the results
echo ""
echo "Current status:"
echo "---------------"
ls -ld "$SHM_DIR"

# Check if permissions are correct
CURRENT_PERMS=$(stat -c "%a" "$SHM_DIR")
CURRENT_GROUP=$(stat -c "%G" "$SHM_DIR")

echo ""
if [[ "$CURRENT_PERMS" == "$REQUIRED_PERMS" ]] && [[ "$CURRENT_GROUP" == "$REQUIRED_GROUP" ]]; then
    echo -e "${GREEN}✓ Permissions are correctly set${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠ Permissions may need adjustment:${NC}"
    if [[ "$CURRENT_PERMS" != "$REQUIRED_PERMS" ]]; then
        echo "  - Permissions are $CURRENT_PERMS, should be $REQUIRED_PERMS"
    fi
    if [[ "$CURRENT_GROUP" != "$REQUIRED_GROUP" ]]; then
        echo "  - Group is $CURRENT_GROUP, should be $REQUIRED_GROUP"
    fi
    echo ""
    echo "Try running: sudo $0"
    exit 1
fi