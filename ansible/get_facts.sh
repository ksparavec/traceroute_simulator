#!/bin/bash
#
# get_facts.sh - Unified facts collection script for Traceroute Simulator
#
# This script collects all network-related facts needed for the traceroute simulator:
# - IP routing tables and policy rules (text format for JSON conversion on controller)
# - Complete iptables configuration and network information
# - Ipset definitions and membership (if available)
# - Basic network interface and system information
#
# Usage: ./get_facts.sh [output_file]
# If no output file specified, prints to stdout
# Must be executed as root user for complete access to iptables and ipset
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

# Function to execute command and format output with section markers
exec_section() {
    local section_name="$1"
    local title="$2"
    local full_cmd="$3"
    local cmd_name="${full_cmd%% *}"
    
    echo "=== TSIM_SECTION_START:$section_name ==="
    echo "TITLE: $title"
    echo "COMMAND: $full_cmd"
    echo "TIMESTAMP: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "---"
    
    if [ -n "$cmd_name" ] && [ -x "$cmd_name" ]; then
        eval "$full_cmd" 2>&1
        local exit_code=$?
        echo ""
        echo "EXIT_CODE: $exit_code"
    else
        echo "ERROR: Command '$cmd_name' not found or not executable"
        echo "EXIT_CODE: 127"
    fi
    
    echo "=== TSIM_SECTION_END:$section_name ==="
    echo ""
}

# Function to collect all facts
collect_facts() {
    echo "# Traceroute Simulator Facts Collection"
    echo "# Generated on: $(date)"
    echo "# Hostname: $(hostname)"
    echo "# Kernel: $(uname -r)"
    echo "# Collection Script Version: 1.0"
    echo ""
    
    # Check if running as root for iptables/ipset access
    local is_root=0
    if [ "$EUID" -eq 0 ]; then
        is_root=1
    fi
    
    # Find required commands
    echo "# Locating required commands in standard paths"
    IP_CMD=$(find_command "ip")
    IPTABLES_CMD=$(find_command "iptables")
    IPTABLES_SAVE_CMD=$(find_command "iptables-save")
    IPSET_CMD=$(find_command "ipset")
    LSMOD_CMD=$(find_command "lsmod")
    GREP_CMD=$(find_command "grep")
    HEAD_CMD=$(find_command "head")
    CAT_CMD=$(find_command "cat")
    HOSTNAME_CMD=$(find_command "hostname")
    DATE_CMD=$(find_command "date")
    UNAME_CMD=$(find_command "uname")
    
    echo "# Found commands:"
    echo "# IP: $IP_CMD"
    echo "# IPTABLES: $IPTABLES_CMD"
    echo "# IPTABLES-SAVE: $IPTABLES_SAVE_CMD"
    echo "# IPSET: $IPSET_CMD"
    echo "# LSMOD: $LSMOD_CMD"
    echo "# Running as root: $is_root"
    echo ""
    
    # Check critical commands
    if [ -z "$IP_CMD" ]; then
        echo "ERROR: 'ip' command not found in standard paths"
        exit 1
    fi
    
    # === ROUTING INFORMATION ===
    # These are collected as text for JSON conversion on the controller
    exec_section "routing_table" "IP Routing Table" "$IP_CMD route show"
    exec_section "policy_rules" "IP Policy Rules" "$IP_CMD rule show"
    
    # === NETWORK INTERFACE INFORMATION ===
    exec_section "interfaces" "Network Interfaces" "$IP_CMD addr show"
    exec_section "interface_stats" "Interface Statistics" "${CAT_CMD:-cat} /proc/net/dev"
    
    # === SYSTEM INFORMATION ===
    exec_section "ip_forwarding" "IP Forwarding Status" "${CAT_CMD:-cat} /proc/sys/net/ipv4/ip_forward"
    exec_section "kernel_version" "Kernel Version" "${UNAME_CMD:-uname} -r"
    exec_section "hostname" "System Hostname" "${HOSTNAME_CMD:-hostname}"
    
    # === IPTABLES INFORMATION ===
    # Only collect if we have iptables and appropriate permissions
    if [ -n "$IPTABLES_CMD" ]; then
        if [ $is_root -eq 1 ]; then
            # Iptables rules - filter table (contains FORWARD chain)
            exec_section "iptables_filter" "Iptables Filter Table" "$IPTABLES_CMD -t filter -L -n -v --line-numbers"
            
            # Iptables rules - nat table (may affect packet modification)
            exec_section "iptables_nat" "Iptables NAT Table" "$IPTABLES_CMD -t nat -L -n -v --line-numbers"
            
            # Iptables rules - mangle table (may affect packet modification) 
            exec_section "iptables_mangle" "Iptables Mangle Table" "$IPTABLES_CMD -t mangle -L -n -v --line-numbers"
            
            # Complete iptables dump (most reliable format for parsing)
            if [ -n "$IPTABLES_SAVE_CMD" ]; then
                exec_section "iptables_save" "Complete Iptables Configuration" "$IPTABLES_SAVE_CMD"
            fi
        else
            echo "=== TSIM_SECTION_START:iptables_warning ==="
            echo "TITLE: Iptables Access Warning"
            echo "COMMAND: N/A"
            echo "TIMESTAMP: $(date '+%Y-%m-%d %H:%M:%S')"
            echo "---"
            echo "WARNING: Not running as root - iptables information not available"
            echo "Current user: $(whoami) (UID: $EUID)"
            echo "EXIT_CODE: 0"
            echo "=== TSIM_SECTION_END:iptables_warning ==="
            echo ""
        fi
    else
        echo "=== TSIM_SECTION_START:iptables_missing ==="
        echo "TITLE: Iptables Command Missing"
        echo "COMMAND: N/A"
        echo "TIMESTAMP: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "---"
        echo "WARNING: iptables command not found in standard paths"
        echo "EXIT_CODE: 127"
        echo "=== TSIM_SECTION_END:iptables_missing ==="
        echo ""
    fi
    
    # === IPSET INFORMATION ===
    # Only collect if we have ipset and appropriate permissions
    if [ -n "$IPSET_CMD" ]; then
        if [ $is_root -eq 1 ]; then
            exec_section "ipset_list" "Ipset Lists and Membership" "$IPSET_CMD list"
        else
            echo "=== TSIM_SECTION_START:ipset_warning ==="
            echo "TITLE: Ipset Access Warning"
            echo "COMMAND: N/A"
            echo "TIMESTAMP: $(date '+%Y-%m-%d %H:%M:%S')"
            echo "---"
            echo "WARNING: Not running as root - ipset information not available"
            echo "Current user: $(whoami) (UID: $EUID)"
            echo "EXIT_CODE: 0"
            echo "=== TSIM_SECTION_END:ipset_warning ==="
            echo ""
        fi
    else
        echo "=== TSIM_SECTION_START:ipset_missing ==="
        echo "TITLE: Ipset Command Missing"
        echo "COMMAND: N/A"
        echo "TIMESTAMP: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "---"
        echo "WARNING: ipset command not found - match-set rules cannot be fully analyzed"
        echo "EXIT_CODE: 127"
        echo "=== TSIM_SECTION_END:ipset_missing ==="
        echo ""
    fi
    
    # === CONNECTION TRACKING INFORMATION ===
    # Connection tracking info (if available)
    if [ -f /proc/net/nf_conntrack ]; then
        exec_section "conntrack" "Connection Tracking Entries (first 10)" "${HEAD_CMD:-head} -10 /proc/net/nf_conntrack"
    else
        echo "=== TSIM_SECTION_START:conntrack_unavailable ==="
        echo "TITLE: Connection Tracking Unavailable"
        echo "COMMAND: N/A"
        echo "TIMESTAMP: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "---"
        echo "INFO: /proc/net/nf_conntrack not available"
        echo "EXIT_CODE: 0"
        echo "=== TSIM_SECTION_END:conntrack_unavailable ==="
        echo ""
    fi
    
    # === NETFILTER MODULE INFORMATION ===
    # Netfilter modules loaded
    if [ -n "$LSMOD_CMD" ] && [ -n "$GREP_CMD" ]; then
        exec_section "netfilter_modules" "Loaded Netfilter Modules" "$LSMOD_CMD | $GREP_CMD -E '(iptable|netfilter|conntrack|nf_)'"
    fi
    
    echo "=== TSIM_FACTS_COLLECTION_COMPLETE ==="
    echo "TIMESTAMP: $(${DATE_CMD:-date} '+%Y-%m-%d %H:%M:%S')"
    echo "HOSTNAME: $(${HOSTNAME_CMD:-hostname})"
    echo "SECTIONS_COLLECTED: routing_table,policy_rules,interfaces,interface_stats,ip_forwarding,kernel_version,hostname,iptables_*,ipset_*,conntrack,netfilter_modules"
}

# Main execution
if [ -n "$OUTPUT_FILE" ]; then
    echo "Collecting traceroute simulator facts to: $OUTPUT_FILE"
    collect_facts > "$OUTPUT_FILE" 2>&1
    echo "Collection complete. File size: $(du -h "$OUTPUT_FILE" 2>/dev/null | cut -f1 || echo 'unknown')"
else
    collect_facts
fi