# Network Traceroute Simulator

A powerful tool that helps network administrators understand how data packets travel through complex networks. By simulating network paths and analyzing real router configurations, it provides insights into routing decisions, firewall rules, and connectivity issues.

## 🎯 Why Use This Tool?

Network troubleshooting often requires understanding the exact path packets take through your infrastructure. Traditional tools like `traceroute` only show you the hops, not why packets take that path or where they might be blocked. This simulator bridges that gap by:

- **Visualizing Complete Paths**: See every router hop with incoming/outgoing interfaces
- **Analyzing Firewall Rules**: Understand which iptables rules allow or block traffic
- **Testing Without Risk**: Simulate changes before implementing them in production
- **Generating Reports**: Create PDF documentation of network paths and test results
- **Learning Tool**: Understand complex routing scenarios in a safe environment

## 🌟 Key Features

### For Network Administrators
- **Interactive Shell (`tsimsh`)**: User-friendly command interface with tab completion
- **Web Interface**: Browser-based testing with authentication and PDF reports
- **Real Router Data**: Works with actual routing tables and firewall rules
- **Network Visualization**: Generates clear network topology diagrams
- **Comprehensive Testing**: Verify connectivity before making changes

### For DevOps Teams
- **Automation Friendly**: Full CLI support with JSON output
- **Ansible Integration**: Automated data collection from multiple routers
- **Exit Codes**: Script-friendly status reporting
- **Batch Processing**: Test multiple scenarios efficiently

### For Security Teams
- **Firewall Analysis**: See which iptables rules match specific traffic
- **Access Control Testing**: Verify security policies work as intended
- **Audit Reports**: Generate compliance documentation
- **Service Testing**: Validate TCP/UDP service accessibility

## 📋 Table of Contents

1. [Getting Started](#getting-started)
   - [Installation](#installation)
   - [Quick Start](#quick-start)
   - [Basic Usage](#basic-usage)
2. [User Interfaces](#user-interfaces)
   - [Interactive Shell (tsimsh)](#interactive-shell-tsimsh)
   - [Web Interface](#web-interface)
   - [Command Line](#command-line)
3. [Core Concepts](#core-concepts)
   - [How It Works](#how-it-works)
   - [Network Topology](#network-topology)
   - [Router Metadata](#router-metadata)
4. [Features Guide](#features-guide)
   - [Path Tracing](#path-tracing)
   - [Firewall Analysis](#firewall-analysis)
   - [Service Testing](#service-testing)
   - [Report Generation](#report-generation)
5. [Advanced Topics](#advanced-topics)
   - [Linux Namespace Simulation](#linux-namespace-simulation)
   - [Data Collection](#data-collection)
   - [Configuration](#configuration)
   - [Automation](#automation)
6. [Technical Reference](#technical-reference)
   - [Architecture Overview](#architecture-overview)
   - [Project Structure](#project-structure)
   - [API Reference](#api-reference)
7. [Appendix](#appendix)
   - [Troubleshooting](#troubleshooting)
   - [Contributing](#contributing)
   - [Technologies Used](#technologies-used)

---

## 🚀 Getting Started

### Installation

The simulator requires a Linux environment with Python 3.7 or higher.

#### Quick Install

```bash
# Clone the repository
git clone <repository-url>
cd traceroute-simulator

# Check dependencies
make check-deps

# Install Python packages
pip3 install matplotlib PyYAML cmd2
```

#### Full Installation

For complete functionality including the web interface:

```bash
# Core dependencies
pip3 install matplotlib numpy PyYAML

# Interactive shell dependencies
pip3 install cmd2 colorama tabulate

# Web interface dependencies (optional)
pip3 install networkx pyhyphen

# Network simulation (requires root)
sudo apt-get install iproute2 iptables ipset socat
```

### Quick Start

#### 1. Test with Example Network

The project includes a complete test network with 10 routers:

```bash
# Set the test data directory
export TRACEROUTE_SIMULATOR_FACTS=tests/tsim_facts

# Run a simple trace
make trace ARGS="-s 10.1.1.1 -d 10.2.1.1"
```

Output:
```
traceroute to 10.2.1.1 from 10.1.1.1
  1  hq-gw (10.1.1.1) from eth1 to wg0
  2  br-gw (10.100.1.2) from wg0 to eth1
  3  br-gw (10.2.1.1) on eth1
```

#### 2. Use the Interactive Shell

Launch the user-friendly shell interface:

```bash
./tsimsh

tsimsh> trace -s 10.1.1.1 -d 10.2.1.1
tsimsh> help
```

#### 3. Set Up Network Simulation (Optional)

Create a real network simulation with Linux namespaces:

```bash
# Create the network (requires sudo)
sudo make netsetup

# Test connectivity
sudo make nettest ARGS="-s 10.1.1.1 -d 10.2.1.1"

# Clean up when done
sudo make netclean
```

### Basic Usage

#### Simple Path Tracing

Find the path between two IP addresses:

```bash
# Using make
make trace ARGS="-s SOURCE_IP -d DESTINATION_IP"

# Using tsimsh
./tsimsh
tsimsh> trace -s SOURCE_IP -d DESTINATION_IP

# Direct command (after setup)
./src/core/traceroute_simulator.py -s SOURCE_IP -d DESTINATION_IP
```

#### Firewall Analysis

Check if traffic is allowed through firewalls:

```bash
# Analyze packet forwarding
make ifa ARGS="--router hq-gw -s 10.1.1.1 -d 10.2.1.1 -p tcp -dp 80"
```

#### Service Testing

Test TCP/UDP service connectivity:

```bash
./tsimsh
tsimsh> service start --ip 10.2.1.1 --port 80 --protocol tcp
tsimsh> service test --source 10.1.1.1 --destination 10.2.1.1:80
```

---

## 🖥️ User Interfaces

### Interactive Shell (tsimsh)

The interactive shell provides a user-friendly command-line interface with intelligent features.

#### Key Features
- **Tab Completion**: Press TAB to complete commands, IP addresses, and options
- **Command History**: Use arrow keys to navigate previous commands
- **Organized Commands**: Commands grouped by function (trace, network, service, host, facts)
- **Colored Output**: Enhanced readability with color-coded messages
- **Scripting Support**: Run commands from files for automation

#### Basic Commands

```bash
# Launch the shell
./tsimsh

# Get help
tsimsh> help                    # Show all commands
tsimsh> help trace              # Show trace command help

# Trace a path
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1

# Manage services
tsimsh> service start --ip 10.1.1.1 --port 8080
tsimsh> service list
tsimsh> service stop --ip 10.1.1.1 --port 8080

# Network simulation
tsimsh> network setup           # Create network
tsimsh> network status all      # Show status
tsimsh> network clean          # Remove network
```

#### Advanced Shell Features

```bash
# Use variables
tsimsh> set SOURCE_IP 10.1.1.1
tsimsh> trace -s $SOURCE_IP -d 10.2.1.1

# Run scripts
./tsimsh < my_commands.script

# Pipe commands
echo "trace -s 10.1.1.1 -d 10.2.1.1" | ./tsimsh
```

### Web Interface

The web interface provides a browser-based testing environment with visual reports.

#### Features
- **Authentication**: Secure login system
- **Test Forms**: Easy-to-use forms for network testing
- **PDF Reports**: Professional reports with network diagrams
- **Trace File Upload**: Test with custom network data
- **Result Sharing**: Shareable links for test results

#### Setup

1. **Configure Apache**:
```bash
cp web/conf/apache-site.conf.template /etc/apache2/sites-available/traceroute-sim.conf
a2enmod cgi rewrite
a2ensite traceroute-sim
systemctl reload apache2
```

2. **Configure Application**:
```bash
cp web/conf/config.json.example web/conf/config.json
./web/scripts/create_user.sh username
```

3. **Access Interface**:
Navigate to `http://your-server/login.html`

#### Using the Web Interface

1. **Login** with your credentials
2. **Fill Test Form**:
   - Source IP: Starting point
   - Destination IP: Target endpoint
   - Port: Service port to test
   - Protocol: TCP or UDP
3. **Run Test** and wait for results
4. **View Report**: Download PDF with complete analysis

Example report available at: `docs/report_example.pdf`

### Command Line

For automation and scripting, use the command-line interface directly.

#### Basic Syntax

```bash
# Trace path
python3 src/core/traceroute_simulator.py -s SOURCE -d DEST

# JSON output
python3 src/core/traceroute_simulator.py -s SOURCE -d DEST -j

# Quiet mode (exit codes only)
python3 src/core/traceroute_simulator.py -s SOURCE -d DEST -q
```

#### Exit Codes

- `0`: Path found successfully
- `1`: No path available
- `2`: IP not reachable
- `4`: No Linux routers in path
- `10`: Input error

---

## 🔍 Core Concepts

### How It Works

The simulator operates in several modes to provide comprehensive network analysis:

1. **Simulation Mode**: Uses collected router data to calculate paths
2. **MTR Mode**: Executes real traceroute on actual network
3. **Namespace Mode**: Creates virtual network for testing
4. **Hybrid Mode**: Combines simulation with real network execution

#### Path Discovery Process

```
1. Load router configurations (routing tables, firewall rules)
2. Find source router that owns the source IP
3. Calculate next hop using Linux routing logic
4. Check firewall rules (iptables FORWARD chain)
5. Repeat until destination is reached
6. Report complete path with interfaces
```

### Network Topology

The included test network demonstrates a realistic enterprise setup:

```
Headquarters (HQ)          Branch Office           Data Center
┌─────────────┐           ┌─────────────┐        ┌─────────────┐
│   hq-gw     │ ========= │   br-gw     │ ====== │   dc-gw     │
│ 10.1.1.1    │ WireGuard │ 10.2.1.1    │  VPN   │ 10.3.1.1    │
└─────┬───────┘ Tunnels   └─────┬───────┘        └─────┬───────┘
      │                         │                       │
┌─────┴───────┐           ┌─────┴───────┐        ┌─────┴───────┐
│  hq-core    │           │  br-core    │        │  dc-core    │
│ 10.1.2.1    │           │ 10.2.1.2    │        │ 10.3.1.2    │
└─┬─────────┬─┘           └─────┬───────┘        └─────┬───────┘
  │         │                   │                       │
┌─┴───┐ ┌───┴─┐           ┌─────┴───────┐        ┌─────┴───────┐
│dmz  │ │ lab │           │  br-wifi    │        │  dc-srv     │
└─────┘ └─────┘           └─────────────┘        └─────────────┘
```

- **10 Routers**: Across 3 locations
- **WireGuard VPN**: Secure site-to-site tunnels
- **Multiple Networks**: 14 different subnets
- **Realistic Routing**: Complex paths with policy routing

### Router Metadata

Each router has metadata defining its capabilities:

```json
{
  "linux": true,              // Can run Linux commands
  "type": "gateway",          // Router type
  "location": "hq",           // Physical location
  "ansible_controller": false // Is Ansible controller
}
```

This enables:
- **MTR Execution**: Only on Linux routers
- **Internet Access**: Only through gateway routers
- **Automated Discovery**: Controller IP detection

---

## 📚 Features Guide

### Path Tracing

Discover how packets travel through your network with detailed hop information.

#### Basic Tracing

```bash
# Simple trace
./tsimsh
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1

# With JSON output
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1 -j

# Verbose mode
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1 -v
```

#### Understanding Output

```
traceroute to 10.2.1.1 from 10.1.1.1
  1  hq-gw (10.1.1.1) from eth1 to wg0
  2  br-gw (10.100.1.2) from wg0 to eth1
  3  br-gw (10.2.1.1) on eth1
```

- **Hop Number**: Sequence in path
- **Router Name**: Which router handles packet
- **IP Address**: Router's IP
- **Interfaces**: Incoming "from" and outgoing "to"

#### Advanced Options

```bash
# Specify controller for MTR execution
tsimsh> trace -s 10.1.1.1 -d 8.8.8.8 --controller-ip 10.1.2.3

# Disable MTR fallback
./src/core/traceroute_simulator.py -s 10.1.1.1 -d 10.2.1.1 --no-mtr
```

### Firewall Analysis

Analyze iptables rules to understand packet filtering decisions.

#### Check Packet Forwarding

```bash
# Will TCP traffic be allowed?
make ifa ARGS="--router hq-gw -s 10.1.1.1 -d 10.2.1.1 -p tcp -dp 80"

# Check specific source port
make ifa ARGS="--router hq-gw -s 10.1.1.1 -sp 12345 -d 10.2.1.1 -dp 443 -p tcp"

# Analyze IP ranges
make ifa ARGS="--router br-core -s 10.1.0.0/16 -d 10.2.0.0/16 -p all -v"
```

#### Understanding Results

```
Analyzing packet: 10.1.1.1 -> 10.2.1.1 (tcp/80)
Router: hq-gw

✓ ALLOWED by rule:
  -A FORWARD -i eth1 -o wg0 -j ACCEPT
  
Packet will be FORWARDED
```

### Service Testing

Test actual network services using the simulation environment.

#### Start Services

```bash
./tsimsh
# Start TCP service
tsimsh> service start --ip 10.1.1.1 --port 8080

# Start UDP service
tsimsh> service start --ip 10.2.1.1 --port 53 --protocol udp

# List running services
tsimsh> service list
```

#### Test Connectivity

```bash
# Test TCP connection
tsimsh> service test --source 10.1.1.1 --destination 10.2.1.1:8080

# Test UDP with message
tsimsh> service test --source 10.1.1.1 --destination 10.2.1.1:53 \
        --protocol udp --message "test"

# Stop service
tsimsh> service stop --ip 10.1.1.1 --port 8080
```

### Report Generation

Generate comprehensive PDF reports documenting network paths and test results.

#### Using Web Interface

1. Login to web interface
2. Enter test parameters
3. Click "Run Test"
4. Download PDF report

#### Report Contents

- **Network Visualization**: GraphViz diagram of path
- **Router Analysis**: For each router:
  - Interfaces and IPs
  - Firewall rules
  - Packet counts
  - Rule matches
- **Test Results**:
  - Ping results
  - MTR analysis
  - Service connectivity
- **Timing Information**: Performance metrics

#### Using Command Line

```bash
# Run reachability test
./src/scripts/network_reachability_test.sh \
  -s 10.1.1.1 -d 10.2.1.1 -P 80 -t tcp \
  -o results.json

# Generate visualization
python3 src/scripts/visualize_reachability.py \
  --trace trace.json --results results.json \
  --output report.pdf
```

---

## 🔧 Advanced Topics

### Linux Namespace Simulation

The project can create a complete virtual network using Linux namespaces for realistic testing.

#### What are Network Namespaces?

Linux namespaces provide isolated network environments within a single system. Each namespace has its own:
- Network interfaces
- Routing tables
- Firewall rules
- Network connections

This allows creating multiple virtual routers on one machine.

#### Creating the Simulation

```bash
# Set up complete network (requires sudo)
sudo make netsetup

# Verify creation
sudo ip netns list

# Enter a namespace
sudo ip netns exec hq-gw bash
```

#### Exploring the Network

```bash
# Show interfaces in namespace
sudo ip netns exec hq-gw ip addr show

# Check routing table
sudo ip netns exec hq-gw ip route show

# View firewall rules
sudo ip netns exec hq-gw iptables -L -n

# Test connectivity
sudo ip netns exec hq-core ping 10.1.1.1
```

#### How Routers are Simulated

The simulation recreates each router with:

1. **Interfaces**: Virtual ethernet pairs connecting namespaces
2. **IP Addresses**: All configured IPs from real routers
3. **Routing Tables**: Complete routing configuration
4. **Policy Rules**: Linux policy-based routing
5. **Firewall Rules**: Full iptables configuration
6. **IP Sets**: Hash sets for efficient matching
7. **Special Features**: WireGuard tunnels, bridges

This creates an environment where real network tools work authentically.

### Data Collection

Gather routing information from production routers for simulation.

#### Using Ansible

```bash
# Configure inventory
cat > inventory.yml << EOF
all:
  children:
    routers:
      hosts:
        router1:
          ansible_host: 192.168.1.1
        router2:
          ansible_host: 192.168.1.2
EOF

# Collect data
make fetch-routing-data INVENTORY_FILE=inventory.yml
```

#### Manual Collection

For single routers:

```bash
# On the router
sudo bash ansible/get_facts.sh > router_facts.txt

# Process to JSON
python3 ansible/process_facts.py router_facts.txt router.json
```

#### Data Format

Unified JSON facts include:
- Routing tables
- Policy rules
- Iptables rules
- Ipset configurations
- Interface information
- System metadata

### Configuration

Customize behavior using YAML configuration files.

#### Configuration Locations

1. Environment variable: `TRACEROUTE_SIMULATOR_CONF`
2. Home directory: `~/traceroute_simulator.yaml`
3. Current directory: `./traceroute_simulator.yaml`

#### Example Configuration

```yaml
# Network data location
tsim_facts: "/path/to/router/data"

# Output preferences
verbose: false
json_output: false

# Feature toggles
enable_mtr_fallback: true
enable_reverse_trace: false

# Network settings
controller_ip: "10.1.2.3"
```

### Automation

Integrate the simulator into your automation workflows.

#### Bash Scripting

```bash
#!/bin/bash
# Check network path availability

if make trace ARGS="-q -s $1 -d $2"; then
    echo "Path available"
    exit 0
else
    echo "No path found"
    exit 1
fi
```

#### Python Integration

```python
import subprocess
import json

def trace_path(source, dest):
    cmd = ['python3', 'traceroute_simulator.py', 
           '-s', source, '-d', dest, '-j']
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        return json.loads(result.stdout)
    else:
        raise Exception(f"Trace failed: {result.stderr}")
```

#### CI/CD Pipeline

```yaml
# .gitlab-ci.yml
test_network_paths:
  script:
    - make test
    - make trace ARGS="-s 10.1.1.1 -d 10.2.1.1 -q"
    - make trace ARGS="-s 10.1.1.1 -d 10.3.1.1 -q"
```

---

## 📖 Technical Reference

### Architecture Overview

The Traceroute Simulator consists of several integrated components:

**Core Engine** (`src/core/`): Implements routing logic, path calculation, and network simulation using real router data.

**Interactive Shell** (`src/shell/`): Provides user-friendly command interface with completion and scripting support.

**Namespace Simulator** (`src/simulators/`): Creates virtual networks using Linux namespaces for realistic testing.

**Analysis Tools** (`src/analyzers/`): Analyzes firewall rules and determines packet forwarding decisions.

**Data Collection** (`ansible/`): Gathers routing and firewall data from production routers.

**Web Interface** (`web/`): Browser-based testing with authentication and PDF report generation.

**Testing Suite** (`tests/`): Comprehensive test coverage with 228 tests.

### Project Structure

```
traceroute-simulator/
├── tsimsh                       # Interactive shell entry point
├── src/                         # Core application code
│   ├── core/                    # Main simulator components
│   ├── shell/                   # Interactive shell
│   ├── analyzers/              # Analysis tools
│   ├── executors/              # External command execution
│   ├── simulators/             # Network simulation
│   ├── scripts/                # Automation scripts
│   └── utils/                  # Utility functions
├── web/                         # Web interface
│   ├── cgi-bin/                # Backend scripts
│   └── htdocs/                 # Frontend files
├── ansible/                     # Data collection
├── tests/                       # Test suite
├── docs/                        # Documentation
└── Makefile                     # Build automation
```

### API Reference

#### TracerouteSimulator Class

```python
from src.core.traceroute_simulator import TracerouteSimulator

# Initialize simulator
sim = TracerouteSimulator('path/to/facts')

# Trace path
path = sim.simulate_traceroute('10.1.1.1', '10.2.1.1')

# Get router by IP
router = sim._find_router_by_ip('10.1.1.1')
```

#### Key Methods

- `simulate_traceroute(source, dest)`: Calculate path between IPs
- `_find_next_hop(router, dest_ip)`: Determine next hop
- `_find_router_by_ip(ip)`: Find router owning an IP
- `_validate_ip_reachability(ip)`: Check if IP is reachable

### Command Reference

#### Make Targets

```bash
make help                    # Show all targets
make check-deps             # Verify dependencies
make trace ARGS="..."       # Run traceroute
make ifa ARGS="..."         # Analyze firewall
make test                   # Run test suite
make netsetup              # Create simulation
make netclean              # Remove simulation
```

#### Shell Commands

```bash
trace      # Path tracing
network    # Namespace management
service    # Service testing
host       # Host management
facts      # Data collection
```

---

## 📎 Appendix

### Troubleshooting

#### Common Issues

**"No router data found"**
- Ensure facts directory exists
- Check `TRACEROUTE_SIMULATOR_FACTS` environment variable
- Verify JSON files are valid

**"IP not configured on any router"**
- Use IPs from the test topology
- Check router interface configurations
- Verify data collection was successful

**"Permission denied" for namespace operations**
- Run with sudo: `sudo make netsetup`
- Check user is in appropriate groups
- Verify namespace support in kernel

#### Debug Mode

```bash
# Maximum verbosity
make trace ARGS="-s 10.1.1.1 -d 10.2.1.1 -vvv"

# Check configuration loading
TRACEROUTE_SIMULATOR_CONF=debug.yaml make trace ARGS="-vvv"
```

### Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Update documentation
5. Submit a pull request

Follow the coding standards in `CLAUDE.md`.

### Technologies Used

**Core Technologies:**
- [Python 3.7+](https://python.org) - Main implementation language
- [NetworkX](https://networkx.org/) - Graph algorithms and visualization
- [Matplotlib](https://matplotlib.org/) - PDF report generation
- [cmd2](https://cmd2.readthedocs.io/) - Interactive shell framework
- [Ansible](https://www.ansible.com/) - Remote data collection

**Linux Networking:**
- iproute2 - Core routing commands
- iptables/netfilter - Firewall processing
- ipset - Efficient IP set matching
- [MTR](https://github.com/traviscross/mtr) - Network diagnostic tool
- socat - Network service relay

**Related Projects:**
- [WireGuard](https://www.wireguard.com/) - VPN tunnel support
- Apache HTTP Server - Web interface hosting

For more details, see:
- `docs/TSIM_SHELL.md` - Shell documentation
- `docs/NETWORK_TOPOLOGY.md` - Network design
- `CLAUDE.md` - Development guidelines

---

**Happy Network Analysis! 🚀**