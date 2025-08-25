# System Administrator Guide

## Table of Contents

1. [System Overview](#system-overview)
2. [Installation and Setup](#installation-and-setup)
3. [tsimsh - The Interactive Shell](#tsimsh---the-interactive-shell)
4. [Network Configuration](#network-configuration)
5. [Data Collection with Ansible](#data-collection-with-ansible)
6. [Linux Namespace Simulation](#linux-namespace-simulation)
7. [Security Configuration](#security-configuration)
8. [Make Targets Reference](#make-targets-reference)
9. [Python Scripts Direct Usage](#python-scripts-direct-usage)
10. [Troubleshooting and Maintenance](#troubleshooting-and-maintenance)

## System Overview

### Architecture Components

The Traceroute Simulator consists of several integrated subsystems:

```
┌─────────────────────────────────────────────────────────┐
│                    User Interfaces                       │
├──────────────┬──────────────┬──────────────┬───────────┤
│   tsimsh     │ Web Interface│ Command Line │  Ansible  │
│ Interactive  │   (Apache)   │   (Direct)   │ Playbooks │
└──────┬───────┴──────┬───────┴──────┬───────┴─────┬─────┘
       │              │              │             │
┌──────▼───────────────▼──────────────▼─────────────▼─────┐
│                  Core Engine (Python)                    │
│  • TracerouteSimulator  • IptablesAnalyzer              │
│  • NamespaceManager     • ServiceManager                │
│  • PacketTracer         • MTRExecutor                   │
└───────────────────────┬──────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────────┐
│                    Data Layer                            │
│  • Router Facts (JSON)  • Raw Facts (Text)              │
│  • Network Topology     • Host Registry                  │
└──────────────────────────────────────────────────────────┘
```

### Key Directories

```bash
/home/user/traceroute-simulator/
├── src/                  # Core Python modules
├── web/                  # Web interface components
├── ansible/              # Data collection playbooks
├── tests/                # Test suites and test data
├── docs/                 # Documentation
└── scripts/              # Utility scripts
```

### Environment Variables

Critical environment variables that control system behavior:

```bash
# Required: Points to router facts directory
export TRACEROUTE_SIMULATOR_FACTS=/path/to/facts

# Optional: Raw facts for enhanced analysis
export TRACEROUTE_SIMULATOR_RAW_FACTS=/path/to/raw_facts

# Optional: Custom configuration file
export TRACEROUTE_SIMULATOR_CONF=/path/to/config.yaml
```

## Installation and Setup

### System Requirements

```bash
# Operating System
- Linux (Ubuntu 20.04+, Debian 11+, RHEL 8+, Fedora 34+)
- Kernel with namespace support (3.8+)

# Python
- Python 3.7 or higher
- pip3 package manager

# System Packages
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    iproute2 \
    iptables \
    ipset \
    socat \
    gcc \
    make
```

### Python Dependencies Installation

```bash
# Core dependencies
pip3 install matplotlib numpy PyYAML

# Interactive shell
pip3 install cmd2 colorama tabulate

# Web interface (optional)
pip3 install networkx pyhyphen

# Development/Testing
pip3 install pytest pytest-cov
```

### Building System Components

```bash
# Check all dependencies
make check-deps

# Build netns_reader wrapper (for namespace operations)
sudo make install-wrapper

# Verify installation
which netns_reader
getcap $(which netns_reader)
```

### Web Interface Setup

1. **Apache Configuration**:
```bash
# Copy template
sudo cp web/conf/apache-site.conf.template \
    /etc/apache2/sites-available/traceroute-sim.conf

# Edit configuration
sudo nano /etc/apache2/sites-available/traceroute-sim.conf

# Enable required modules
sudo a2enmod cgi rewrite auth_basic

# Enable site
sudo a2ensite traceroute-sim
sudo systemctl reload apache2
```

2. **Application Configuration**:
```bash
# Create configuration from template
cp web/conf/config.json.example web/conf/config.json

# Edit configuration
nano web/conf/config.json
```

3. **User Management**:
```bash
# Create web user
./web/scripts/create_user.sh username

# Change password
./web/scripts/change_password.sh username
```

### SSSD Authentication (Optional)

For enterprise integration with Active Directory or LDAP:

```bash
# Configure PAM
sudo make pam-config

# Verify SSSD is running
systemctl status sssd

# Test authentication
pamtester traceroute-web username authenticate
```

## tsimsh - The Interactive Shell

### Overview

tsimsh is the primary interface for system administrators, providing:
- Tab completion for commands and IP addresses
- Command history and search
- Scripting capabilities
- Variable support
- Batch processing

### Basic Usage

```bash
# Launch interactive shell
./tsimsh

# Quick mode (skip network checks)
./tsimsh -q

# Execute single command
echo "trace -s 10.1.1.1 -d 10.2.1.1" | ./tsimsh

# Run script file
./tsimsh < commands.tsim

# Batch processing with error handling
cat script.tsim | ./tsimsh
echo $?  # Check exit code
```

### Command Categories

#### Trace Commands
```bash
# Basic trace
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1

# With port and protocol
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1 -p tcp -dp 443

# JSON output
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1 -j

# Verbose mode
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1 -v

# With MTR execution
tsimsh> trace -s 10.1.1.1 -d 8.8.8.8 --controller-ip 10.1.2.3
```

#### Network Management
```bash
# Setup namespace network
tsimsh> network setup
tsimsh> network setup -v      # Verbose
tsimsh> network setup -vv     # More verbose
tsimsh> network setup -vvv    # Debug level

# Check status
tsimsh> network status all
tsimsh> network status hq-gw
tsimsh> network status interfaces --limit hq-gw,br-gw

# Clean up
tsimsh> network clean
tsimsh> network clean --force  # Skip confirmation
```

#### Service Management
```bash
# Start services
tsimsh> service start --ip 10.1.1.1 --port 8080
tsimsh> service start --ip 10.2.1.1 --port 53 --protocol udp

# List services
tsimsh> service list
tsimsh> service list -j  # JSON output

# Test connectivity
tsimsh> service test --source 10.1.1.1 --destination 10.2.1.1:8080
tsimsh> service test --source 10.1.1.1 --destination 10.2.1.1:53 --protocol udp

# Stop services
tsimsh> service stop --ip 10.1.1.1 --port 8080
tsimsh> service stop all  # Stop all services
```

#### Host Management
```bash
# Add dynamic host
tsimsh> host add --name web1 --ip 10.1.1.100/24 --connect-to hq-gw
tsimsh> host add --name db1 --ip 10.2.1.50/24 --connect-to br-core --gateway 10.2.1.1

# List hosts
tsimsh> host list
tsimsh> host list -j  # JSON output

# Remove host
tsimsh> host del --name web1
tsimsh> host del all  # Remove all hosts
```

#### Facts Management
```bash
# Process raw facts
tsimsh> facts process --input /path/to/raw --output /path/to/json

# Update facts
tsimsh> facts update --router hq-gw --facts-file new_facts.json

# Show facts
tsimsh> facts show --router hq-gw
tsimsh> facts show --router hq-gw --section interfaces
```

### Advanced Shell Features

#### Variables and Scripting
```bash
# Set variables
tsimsh> set SOURCE 10.1.1.1
tsimsh> set DEST 10.2.1.1
tsimsh> trace -s $SOURCE -d $DEST

# Conditional execution
tsimsh> if trace -s 10.1.1.1 -d 10.2.1.1 -q; then
tsimsh>   echo "Path exists"
tsimsh> else
tsimsh>   echo "No path"
tsimsh> fi

# Loops
tsimsh> for ip in 10.1.1.1 10.2.1.1 10.3.1.1; do
tsimsh>   trace -s $ip -d 8.8.8.8 -j > trace_$ip.json
tsimsh> done
```

#### Shell Configuration

Create `.tsimrc` in home directory for startup commands:
```bash
# ~/.tsimrc
# Set default variables
set CONTROLLER_IP 10.1.2.3
set DEFAULT_SOURCE 10.1.1.1

# Aliases
alias t trace
alias ns network status
alias sl service list

# Auto-complete custom IPs
_custom_ips 10.1.1.1 10.2.1.1 10.3.1.1
```

## Network Configuration

### Understanding the Test Network

The included test network represents a typical enterprise setup:

```
Headquarters (HQ)
├── hq-gw (10.1.1.1)      - Edge router/firewall
├── hq-core (10.1.2.1)    - Core switch/router
├── hq-dmz (10.1.3.1)     - DMZ network router
└── hq-lab (10.1.4.1)     - Lab network router

Branch Office
├── br-gw (10.2.1.1)      - Edge router/firewall
├── br-core (10.2.1.2)    - Core switch/router
└── br-wifi (10.2.1.3)    - WiFi access router

Data Center
├── dc-gw (10.3.1.1)      - Edge router/firewall
├── dc-core (10.3.1.2)    - Core switch/router
└── dc-srv (10.3.1.3)     - Server network router
```

### Network Interconnections

#### WireGuard VPN Tunnels
```bash
# HQ to Branch tunnel
HQ (10.100.1.1) <---wg0---> Branch (10.100.1.2)

# HQ to DC tunnel  
HQ (10.100.2.1) <---wg1---> DC (10.100.2.2)

# Branch to DC tunnel
Branch (10.100.3.1) <---wg1---> DC (10.100.3.2)
```

### Modifying Network Topology

#### Adding a New Router

1. **Create Facts File**:
```json
{
  "hostname": "new-router",
  "metadata": {
    "linux": true,
    "type": "router",
    "location": "branch"
  },
  "interfaces": {
    "eth0": {
      "addresses": ["10.4.1.1/24"],
      "state": "UP"
    }
  },
  "routes": [
    {
      "destination": "default",
      "gateway": "10.4.1.254",
      "interface": "eth0"
    }
  ]
}
```

2. **Update Network Setup**:
```bash
# Regenerate namespace configuration
./src/simulators/network_namespace_setup.py --setup

# Verify
sudo ip netns exec new-router ip addr show
```

#### Modifying Firewall Rules

1. **Edit Router Facts**:
```bash
# Extract current rules
python3 src/utils/extract_iptables.py hq-gw > hq-gw-iptables.json

# Edit rules
nano hq-gw-iptables.json

# Update facts
python3 src/utils/update_facts.py \
    --router hq-gw \
    --iptables hq-gw-iptables.json
```

2. **Apply to Namespace**:
```bash
# Recreate namespace with new rules
sudo -E make netclean
sudo -E make netsetup
```

### Policy-Based Routing

Configure multiple routing tables for advanced routing:

```bash
# Example: Add policy routing to facts
{
  "ip_rules": [
    {
      "priority": 100,
      "from": "10.1.100.0/24",
      "table": "mgmt"
    }
  ],
  "routing_tables": {
    "mgmt": [
      {
        "destination": "default",
        "gateway": "10.1.1.254",
        "interface": "eth0"
      }
    ]
  }
}
```

## Data Collection with Ansible

### Setting Up Ansible Inventory

1. **Create Inventory File** (`inventory.yml`):
```yaml
all:
  vars:
    ansible_user: admin
    ansible_ssh_private_key_file: ~/.ssh/id_rsa
    
  children:
    routers:
      hosts:
        hq-gw:
          ansible_host: 192.168.1.1
          location: headquarters
          
        br-gw:
          ansible_host: 192.168.2.1
          location: branch
          
        dc-gw:
          ansible_host: 192.168.3.1
          location: datacenter
```

### Collecting Router Data

```bash
# Collect from all routers
make facts INVENTORY_FILE=inventory.yml

# Collect from specific group
make facts INVENTORY=routers

# Collect from single host
make facts INVENTORY=hq-gw

# With custom output directory
TRACEROUTE_SIMULATOR_FACTS=/custom/path make facts INVENTORY_FILE=inventory.yml
```

### Manual Data Collection

For routers without Ansible access:

```bash
# On the router (via SSH)
curl -O https://your-server/ansible/get_facts.sh
sudo bash get_facts.sh > router_facts.txt

# On your workstation
scp router:router_facts.txt ./
python3 ansible/process_facts.py router_facts.txt router.json
cp router.json $TRACEROUTE_SIMULATOR_FACTS/
```

### Raw Facts Collection

For enhanced analysis with packet counts:

```bash
# Collect raw facts on router
sudo iptables -L -n -v -x > iptables_raw.txt
sudo ip route show table all > routes_raw.txt
sudo ip rule show > rules_raw.txt
sudo ipset list > ipsets_raw.txt

# Store in raw facts directory
mkdir -p $TRACEROUTE_SIMULATOR_RAW_FACTS/router-name
cp *_raw.txt $TRACEROUTE_SIMULATOR_RAW_FACTS/router-name/
```

### Tracersh Setup for Restricted SSH

Configure restricted SSH access for remote tracing:

```bash
# Install tracersh on router
scp ansible/tracersh router:/usr/local/bin/
ssh router chmod +x /usr/local/bin/tracersh

# Configure SSH key with restriction
ssh router 'echo "command=\"/usr/local/bin/tracersh\" $(cat ~/.ssh/trace_key.pub)" >> ~/.ssh/authorized_keys'

# Test restricted access
ssh -i ~/.ssh/trace_key router
# Should see: Restricted shell - only traceroute commands allowed
```

## Linux Namespace Simulation

### Understanding Namespaces

Linux namespaces provide isolated network stacks, allowing multiple virtual routers on a single host:

```bash
# Each namespace has independent:
- Network interfaces
- Routing tables  
- Firewall rules
- ARP tables
- Network sockets
```

### Creating the Simulation

```bash
# Full setup with all routers
sudo -E make netsetup

# Verbose output for debugging
sudo -E make netsetup ARGS='-vvv'

# Verify creation
sudo ip netns list | wc -l  # Should show 10 namespaces

# Check specific namespace
sudo ip netns exec hq-gw ip addr show
sudo ip netns exec hq-gw ip route show
sudo ip netns exec hq-gw iptables -L -n
```

### Managing Virtual Networks

#### Namespace Operations
```bash
# Enter namespace shell
sudo ip netns exec hq-gw bash

# Run command in namespace
sudo ip netns exec hq-gw ping 10.2.1.1

# Monitor traffic
sudo ip netns exec hq-gw tcpdump -i eth0

# Check connections
sudo ip netns exec hq-gw ss -tuln
```

#### Network Testing
```bash
# Test connectivity
sudo -E make nettest ARGS='-s 10.1.1.1 -d 10.2.1.1 --test-type ping'

# MTR trace in namespace
sudo -E make nettest ARGS='-s 10.1.1.1 -d 8.8.8.8 --test-type mtr'

# Combined testing
sudo -E make nettest ARGS='-s 10.1.1.1 -d 10.3.1.1 --test-type both -v'
```

#### Service Testing
```bash
# Start service in namespace
sudo -E make svcstart ARGS='10.1.1.1:8080'

# Test from another namespace
sudo -E make svctest ARGS='-s 10.2.1.1 -d 10.1.1.1:8080'

# List all services
sudo -E make svclist

# Clean up services
sudo -E make svcclean
```

### Advanced Namespace Features

#### Adding Virtual Hosts
```bash
# Create host connected to router
sudo -E make hostadd ARGS='--host web1 --primary-ip 10.1.10.100/24 --connect-to hq-core'

# With custom routes
sudo -E make hostadd ARGS='--host db1 --primary-ip 10.2.10.50/24 --connect-to br-core --gateway 10.2.1.1 --routes "10.0.0.0/8 via 10.2.1.1"'

# List hosts
sudo -E make hostlist

# Remove host
sudo -E make hostdel ARGS='--host web1'
```

#### Bridge Networks
```bash
# Bridges are automatically created for multi-connected networks
# Example: hq-core bridge connecting DMZ and LAB networks

# Check bridge
sudo ip netns exec hq-core bridge link show

# Monitor bridge traffic
sudo ip netns exec hq-core tcpdump -i br0
```

### Troubleshooting Namespaces

```bash
# Check namespace resources
sudo ip netns exec hq-gw ip link show
sudo ip netns exec hq-gw ip addr show
sudo ip netns exec hq-gw ip route show
sudo ip netns exec hq-gw ip neigh show

# Debug connectivity issues
sudo ip netns exec hq-gw ping -c 1 10.1.1.2
sudo ip netns exec hq-gw traceroute 10.2.1.1
sudo ip netns exec hq-gw tcpdump -i any icmp

# Clean up stuck namespaces
sudo -E make netclean --force
sudo ip netns delete hq-gw  # If needed
```

## Security Configuration

### Sudoers Configuration

Required sudo permissions for namespace operations:

```bash
# Display recommended sudoers configuration
make show-sudoers

# Add to /etc/sudoers.d/traceroute-simulator
%netadmins ALL=(root) NOPASSWD: /usr/sbin/ip netns *, \
    /usr/bin/make netsetup*, \
    /usr/bin/make netclean*, \
    /usr/bin/make nettest*, \
    /usr/bin/make svc*
```

### Capability-Based Security

Using capabilities instead of full sudo:

```bash
# Build and install netns_reader with capabilities
sudo make install-wrapper

# Verify capabilities
getcap /usr/local/bin/netns_reader
# Should show: cap_sys_admin,cap_net_admin,cap_dac_override=ep

# Use without sudo
/usr/local/bin/netns_reader list
```

### Web Interface Security

#### Apache Security Headers
```apache
# In apache-site.conf
Header always set X-Frame-Options "DENY"
Header always set X-Content-Type-Options "nosniff"
Header always set X-XSS-Protection "1; mode=block"
Header always set Referrer-Policy "strict-origin-when-cross-origin"
```

#### Session Security
```json
// web/conf/config.json
{
  "session": {
    "timeout": 1800,
    "secure_cookie": true,
    "httponly": true,
    "samesite": "strict"
  }
}
```

#### File Permissions
```bash
# Set proper ownership
sudo chown -R www-data:www-data web/
sudo chmod 750 web/cgi-bin/
sudo chmod 640 web/conf/config.json
sudo chmod 600 web/conf/.htpasswd

# Protect sensitive directories
echo "Deny from all" > web/conf/.htaccess
```

### Firewall Considerations

Protect the simulator server:

```bash
# Allow web interface
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# Allow SSH from management network only
sudo iptables -A INPUT -s 10.100.0.0/24 -p tcp --dport 22 -j ACCEPT

# Default deny
sudo iptables -P INPUT DROP
```

## Make Targets Reference

### Essential Targets

```bash
# Dependency checking
make check-deps              # Verify all requirements

# Testing
make test                    # Run complete test suite
make test-namespace          # Test namespace operations (needs sudo)
make test-network           # Comprehensive network tests (3-5 min)

# Tracing
make tsim ARGS='-s IP -d IP'              # Basic trace
make tsim ARGS='-s IP -d IP -j'           # JSON output
make tsim ARGS='-s IP -d IP -v'           # Verbose

# Firewall analysis
make ifa ARGS='--router NAME -s IP -d IP -p tcp -dp 80'

# Namespace management
sudo -E make netsetup        # Create simulation
sudo -E make netstatus       # Show status
sudo -E make netclean        # Remove simulation
```

### Advanced Targets

```bash
# Service management
sudo -E make svcstart ARGS='IP:PORT'
sudo -E make svctest ARGS='-s SRC_IP -d DST_IP:PORT'
sudo -E make svclist
sudo -E make svcclean

# Host management
sudo -E make hostadd ARGS='--host NAME --primary-ip IP/MASK --connect-to ROUTER'
sudo -E make hostlist
sudo -E make hostdel ARGS='--host NAME'
sudo -E make hostclean

# Data collection
make facts INVENTORY_FILE=hosts.ini
make facts INVENTORY=group-name

# Package management
make package                 # Build distribution
make install-package         # Install as package
make install-pipx           # Install with pipx
```

### Target Arguments

Most targets accept ARGS for options:

```bash
# Verbosity levels
ARGS='-v'    # Basic verbosity
ARGS='-vv'   # Info level
ARGS='-vvv'  # Debug level

# Output formats
ARGS='-j'    # JSON output
ARGS='-q'    # Quiet mode (exit code only)

# Force/Skip confirmations
ARGS='--force'
ARGS='-f'
```

## Python Scripts Direct Usage

### Core Scripts

```bash
# Traceroute simulator
python3 src/core/traceroute_simulator.py \
    -s 10.1.1.1 -d 10.2.1.1 \
    -p tcp -sp 1234 -dp 80 \
    -j  # JSON output

# Iptables analyzer
python3 src/analyzers/iptables_forward_analyzer.py \
    --router hq-gw \
    -s 10.1.1.0/24 -d 10.2.0.0/16 \
    -p all \
    -v

# Namespace setup
sudo python3 src/simulators/network_namespace_setup.py \
    --setup \
    --verbose

# Service manager
sudo python3 src/simulators/service_manager.py \
    start --namespace hq-gw \
    --ip 10.1.1.1 --port 8080 \
    --protocol tcp
```

### Utility Scripts

```bash
# Process raw facts
python3 ansible/process_facts.py \
    input_file.txt output.json

# Extract interfaces
python3 ansible/extract_interfaces.py \
    router_facts.json

# Update facts
python3 src/utils/update_tsim_facts.py \
    --router hq-gw \
    --field iptables \
    --data new_rules.json

# Verify setup
python3 src/utils/verify_network_setup.py \
    --check all
```

### Analysis Scripts

```bash
# Analyze packet counts
python3 src/scripts/analyze_packet_counts.py \
    --router hq-gw \
    --chain FORWARD

# Process iptables logs
python3 src/analyzers/iptables_log_processor.py \
    --log-file /var/log/iptables.log \
    --source 10.1.1.1 \
    --dest 10.2.1.1

# Visualize network
python3 src/scripts/visualize_reachability.py \
    --trace trace.json \
    --output network.pdf
```

### Script Environment

Set environment for scripts:

```bash
# Required environment
export TRACEROUTE_SIMULATOR_FACTS=/path/to/facts
export TRACEROUTE_SIMULATOR_RAW_FACTS=/path/to/raw_facts

# Python path for imports
export PYTHONPATH=/path/to/traceroute-simulator/src:$PYTHONPATH

# Disable bytecode generation
export PYTHONDONTWRITEBYTECODE=1

# Unbuffered output
export PYTHONUNBUFFERED=1
```

## Troubleshooting and Maintenance

### Common Issues

#### "No router data found"
```bash
# Check environment variable
echo $TRACEROUTE_SIMULATOR_FACTS

# Verify directory exists
ls -la $TRACEROUTE_SIMULATOR_FACTS

# Check JSON files are valid
for f in $TRACEROUTE_SIMULATOR_FACTS/*.json; do
    python3 -m json.tool "$f" > /dev/null || echo "Invalid: $f"
done
```

#### "Permission denied" for namespaces
```bash
# Check sudo configuration
sudo -l | grep netns

# Verify capability binary
getcap /usr/local/bin/netns_reader

# Test with explicit sudo
sudo -E ip netns list
```

#### Namespace operations hang
```bash
# Check for stuck processes
ps aux | grep netns

# Force cleanup
sudo -E make netclean --force

# Manual cleanup if needed
for ns in $(sudo ip netns list | awk '{print $1}'); do
    sudo ip netns delete "$ns"
done
```

#### Web interface errors
```bash
# Check Apache error log
sudo tail -f /var/log/apache2/error.log

# Verify CGI execution
sudo -u www-data python3 web/cgi-bin/test_me.py

# Check permissions
ls -la web/cgi-bin/
ls -la web/conf/

# Test configuration
python3 -c "import json; json.load(open('web/conf/config.json'))"
```

### Performance Tuning

#### System Limits
```bash
# Increase file descriptors
ulimit -n 65536

# For permanent change
echo "* soft nofile 65536" >> /etc/security/limits.conf
echo "* hard nofile 65536" >> /etc/security/limits.conf
```

#### Network Performance
```bash
# Enable IP forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward

# Increase network buffers
sysctl -w net.core.rmem_max=134217728
sysctl -w net.core.wmem_max=134217728
```

#### Namespace Limits
```bash
# Increase max namespaces
echo 50000 > /proc/sys/user/max_net_namespaces

# Monitor namespace usage
ls /var/run/netns/ | wc -l
```

### Maintenance Tasks

#### Regular Cleanup
```bash
# Clean test artifacts
make clean

# Remove old namespace setups
sudo -E make netclean

# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null

# Clean old logs
find /var/log -name "traceroute-sim*.log" -mtime +30 -delete
```

#### Backup Important Data
```bash
# Backup facts
tar czf facts_backup_$(date +%Y%m%d).tar.gz $TRACEROUTE_SIMULATOR_FACTS/

# Backup configuration
cp -r web/conf/ web/conf.backup.$(date +%Y%m%d)/

# Backup user scripts
tar czf scripts_backup_$(date +%Y%m%d).tar.gz ~/.tsimrc *.tsim
```

#### Update Procedures
```bash
# Pull latest code
git pull origin main

# Update dependencies
pip3 install -r requirements.txt --upgrade

# Rebuild components
make clean
make check-deps
sudo make install-wrapper

# Run tests
make test

# Restart services
sudo systemctl restart apache2
```

### Monitoring and Logging

#### System Monitoring
```bash
# Monitor namespace memory usage
ps aux | grep netns | awk '{sum+=$6} END {print sum/1024 " MB"}'

# Check network namespace count
sudo ip netns list | wc -l

# Monitor socat services
ps aux | grep socat | wc -l
```

#### Application Logging
```bash
# Enable debug logging in tsimsh
export TRACEROUTE_SIMULATOR_DEBUG=1
./tsimsh

# Web interface logs
tail -f /var/log/apache2/access.log
tail -f /var/log/apache2/error.log

# Custom logging
export TRACEROUTE_SIMULATOR_LOG=/var/log/tsim.log
```

#### Audit Trail
```bash
# Track namespace operations
sudo auditctl -w /var/run/netns -p rwxa

# Monitor iptables changes
sudo auditctl -w /sbin/iptables -p x

# Review audit logs
sudo aureport --executable
sudo ausearch -c iptables
```

### Emergency Procedures

#### System Recovery
```bash
# If namespace system is corrupted
sudo rm -rf /var/run/netns/*
sudo systemctl restart systemd-networkd

# If web interface is down
sudo systemctl restart apache2
sudo apache2ctl configtest

# If facts are corrupted
# Restore from backup
tar xzf facts_backup_YYYYMMDD.tar.gz
export TRACEROUTE_SIMULATOR_FACTS=/path/to/restored/facts
```

#### Data Recovery
```bash
# Recreate facts from routers
make facts INVENTORY_FILE=emergency_inventory.yml

# Rebuild from raw facts
for router in $TRACEROUTE_SIMULATOR_RAW_FACTS/*; do
    python3 ansible/process_facts.py \
        "$router/complete_facts.txt" \
        "$TRACEROUTE_SIMULATOR_FACTS/$(basename $router).json"
done
```