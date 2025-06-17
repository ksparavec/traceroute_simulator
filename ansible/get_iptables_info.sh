#!/bin/bash
#
# get_iptables_info.sh - Collect iptables and network information for packet forwarding analysis
#
# Usage: ./get_iptables_info.sh [output_file]
# If no output file specified, prints to stdout
# Must be executed as root user for complete iptables access
#

OUTPUT_FILE="$1"

# Function to find command in standard paths
find_command() {
    local cmd_name="$1"
    local cmd_path=""
    
    for path in "/sbin/${cmd_name}" "/usr/sbin/${cmd_name}" "/bin/${cmd_name}" "/usr/bin/${cmd_name}" "/usr/local/sbin/${cmd_name}" "/usr/local/bin/${cmd_name}"; do
        if [ -x "$path" ]; then
            cmd_path="$path"
            break
        fi
    done
    
    if [ -z "$cmd_path" ]; then
        # Fallback to PATH search
        if command -v "$cmd_name" >/dev/null 2>&1; then
            cmd_path=$(command -v "$cmd_name")
        fi
    fi
    
    echo "$cmd_path"
}

# Function to execute command and format output
exec_cmd() {
    local title="$1"
    local full_cmd="$2"
    local cmd_name="${full_cmd%% *}"
    
    echo "=== $title ==="
    echo "COMMAND: $full_cmd"
    echo "TIMESTAMP: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "---"
    
    if [ -n "$cmd_name" ] && [ -x "$cmd_name" ]; then
        eval "$full_cmd" 2>&1
    else
        echo "ERROR: Command '$cmd_name' not found or not executable"
    fi
    
    echo ""
}

# Function to collect all information
collect_info() {
    echo "# Router Information Collection"
    echo "# Generated on: $(date)"
    echo "# Hostname: $(hostname)"
    echo "# Kernel: $(uname -r)"
    echo ""
    
    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        echo "ERROR: Must be executed as root user for complete iptables access"
        echo "Current user: $(whoami) (UID: $EUID)"
        exit 1
    fi
    
    # Find required commands
    echo "# Locating required commands in standard paths"
    IP_CMD=$(find_command "ip")
    IPTABLES_CMD=$(find_command "iptables")
    IPTABLES_SAVE_CMD=$(find_command "iptables-save")
    LSMOD_CMD=$(find_command "lsmod")
    GREP_CMD=$(find_command "grep")
    HEAD_CMD=$(find_command "head")
    CAT_CMD=$(find_command "cat")
    HOSTNAME_CMD=$(find_command "hostname")
    DATE_CMD=$(find_command "date")
    
    echo "# Found commands:"
    echo "# IP: $IP_CMD"
    echo "# IPTABLES: $IPTABLES_CMD"
    echo "# IPTABLES-SAVE: $IPTABLES_SAVE_CMD"
    echo "# LSMOD: $LSMOD_CMD"
    echo ""
    
    # Check critical commands
    if [ -z "$IP_CMD" ]; then
        echo "ERROR: 'ip' command not found in standard paths"
        exit 1
    fi
    
    if [ -z "$IPTABLES_CMD" ]; then
        echo "ERROR: 'iptables' command not found in standard paths"
        exit 1
    fi
    
    # IP forwarding status
    exec_cmd "IP Forwarding Status" "${CAT_CMD:-cat} /proc/sys/net/ipv4/ip_forward"
    
    # Network interfaces and IP addresses
    exec_cmd "Network Interfaces (ip addr)" "$IP_CMD addr show"
    
    # Routing table
    exec_cmd "Routing Table" "$IP_CMD route show"
    
    # Iptables rules - filter table (contains FORWARD chain)
    exec_cmd "Iptables Filter Table" "$IPTABLES_CMD -t filter -L -n -v --line-numbers"
    
    # Iptables rules - nat table (may affect packet modification)
    exec_cmd "Iptables NAT Table" "$IPTABLES_CMD -t nat -L -n -v --line-numbers"
    
    # Iptables rules - mangle table (may affect packet modification) 
    exec_cmd "Iptables Mangle Table" "$IPTABLES_CMD -t mangle -L -n -v --line-numbers"
    
    # Complete iptables dump (most reliable format)
    if [ -n "$IPTABLES_SAVE_CMD" ]; then
        exec_cmd "Complete Iptables Configuration" "$IPTABLES_SAVE_CMD"
    else
        echo "=== Complete Iptables Configuration ==="
        echo "WARNING: iptables-save command not found"
        echo ""
    fi
    
    # Network interface statistics
    exec_cmd "Interface Statistics" "${CAT_CMD:-cat} /proc/net/dev"
    
    # Connection tracking info (if available)
    if [ -f /proc/net/nf_conntrack ]; then
        exec_cmd "Connection Tracking Entries (first 10)" "${HEAD_CMD:-head} -10 /proc/net/nf_conntrack"
    fi
    
    # Netfilter modules loaded
    if [ -n "$LSMOD_CMD" ] && [ -n "$GREP_CMD" ]; then
        exec_cmd "Loaded Netfilter Modules" "$LSMOD_CMD | $GREP_CMD -E '(iptable|netfilter|conntrack|nf_)'"
    fi
    
    echo "=== Collection Complete ==="
    echo "TIMESTAMP: $(${DATE_CMD:-date} '+%Y-%m-%d %H:%M:%S')"
}

# Main execution
if [ -n "$OUTPUT_FILE" ]; then
    echo "Collecting router information to: $OUTPUT_FILE"
    collect_info > "$OUTPUT_FILE" 2>&1
    echo "Collection complete. File size: $(du -h "$OUTPUT_FILE" | cut -f1)"
else
    collect_info
fi