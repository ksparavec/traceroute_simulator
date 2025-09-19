# Network Traceroute Simulator

A comprehensive network path discovery tool that simulates traceroute behavior using real routing information collected from multiple Linux routers. This tool helps network administrators understand packet flow paths through complex network topologies including VPN tunnels, multi-homed connections, and policy-based routing.

## 🌟 Features

- **Interactive Shell (tsimsh)**: Comprehensive command-line interface with tab completion, persistent history, and organized command structure
- **Real Routing Data**: Uses actual routing tables and policy rules from Linux routers
- **Router Metadata System**: Comprehensive router classification with Linux/non-Linux differentiation
- **Gateway Internet Connectivity**: Realistic internet access simulation for gateway routers only
- **Automatic Controller Detection**: Intelligent Ansible controller IP detection from metadata
- **Iptables Forward Analysis**: Comprehensive packet forwarding analysis using actual iptables configurations
- **Ipset Integration**: Full support for ipset match-set conditions with efficient Python set-based lookups
- **YAML Configuration Support**: Flexible configuration with environment variables and precedence handling
- **FQDN Resolution**: Automatically resolves source and destination IPs to hostnames when possible
- **MTR Fallback**: Automatic fallback to real MTR execution when simulation cannot complete paths
- **Reverse Path Tracing**: Advanced three-step bidirectional path discovery for complex topologies
- **Timing Information**: Real round-trip time (RTT) data from MTR execution for performance analysis
- **Router Name Consistency**: Shows actual router names instead of generic labels when possible
- **Unreachable Destination Detection**: Proper validation and reporting of truly unreachable targets
- **Multiple Output Formats**: Text, JSON, and verbose modes with consistent formatting and timing data
- **Complex Network Support**: Handles VPN tunnels, WireGuard, multi-interface scenarios
- **Error Detection**: Identifies routing loops, blackhole routes, and unreachable destinations
- **Automation Friendly**: Comprehensive exit codes and quiet mode for script integration
- **Linux Namespace Simulation**: Real packet testing with complete network infrastructure
- **Service Management**: TCP/UDP echo services with IP-based interface and multi-client support
- **Dynamic Host Management**: Add/remove hosts to running network simulation
- **System Namespace Protection**: Automatic filtering of non-user namespaces
- **Enhanced Error Handling**: User-friendly error messages with progressive verbosity
- **Comprehensive Testing**: Full test suite with 228 tests across all modules
- **Professional Visualization**: High-quality network topology diagrams with metadata-aware color coding
- **Accurate Interface Tracking**: Precise incoming/outgoing interface determination

## 📋 Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Interactive Shell (tsimsh)](#-interactive-shell-tsimsh)
- [Configuration](#configuration)
- [Router Metadata System](#router-metadata-system)
- [Gateway Internet Connectivity](#gateway-internet-connectivity)
- [Iptables Forward Analysis](#iptables-forward-analysis)
- [Usage](#usage)
- [Command Line Options](#command-line-options)
- [MTR Integration](#mtr-integration)
- [Reverse Path Tracing](#reverse-path-tracing)
- [FQDN Resolution](#fqdn-resolution)
- [Data Collection](#data-collection)
- [Linux Namespace Simulation](#-linux-namespace-simulation)
- [Service Management](#-service-management)
- [Host Management](#-host-management)
- [Network Scenarios](#network-scenarios)
- [Network Visualization](#network-visualization)
- [Output Formats](#output-formats)
- [Exit Codes](#exit-codes)
- [Testing](#testing)
- [Examples](#examples)
- [Web Interface](#-web-interface)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## 🚀 Installation

### Prerequisites

- Python 3.7 or higher
- Linux environment (for data collection)
- Ansible (for multi-router data collection)
- matplotlib and numpy (for network topology visualization)
- Make (for automated build tasks)

### Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd traceroute_simulator
   ```

2. **Check dependencies and install requirements**:
   ```bash
   make check-deps  # Verify all dependencies and get installation hints
   ```

3. **Install Python dependencies** (if not already installed):
   ```bash
   # Install matplotlib for network visualization
   pip3 install matplotlib
   
   # Install PyYAML for configuration file support (optional)
   pip3 install PyYAML
   
   # Verify Python version
   python3 --version  # Ensure Python 3.7+
   ```


## 🏃 Quick Start

1. **Use the provided test network** (see [Network Topology](#network-topology) for details):
   ```bash
   # Complex test network with 10 routers across 3 locations
   ls tests/tsim_facts/
   # hq-gw.json  hq-core.json  br-gw.json  dc-gw.json  ... (10 unified JSON files)
   ```

2. **Run a basic trace command**:
   ```bash
   make trace ARGS="-s 10.1.1.1 -d 10.2.1.1"
   ```
   
   💡 **Tip**: For multiple commands, export once: `export TRACEROUTE_SIMULATOR_FACTS=tests/tsim_facts`

3. **Or use the interactive shell**:
   ```bash
   # Launch interactive shell
   ./tsimsh
   
   # Run commands in shell
   tsimsh> trace -s 10.1.1.1 -d 10.2.1.1
   tsimsh> network setup --verbose
   tsimsh> service start --ip 10.1.1.1 --port 8080
   ```

4. **View results**:
   ```
   traceroute to 10.2.1.1 from 10.1.1.1
     1  hq-gw (10.1.1.1) from eth1 to wg0
     2  br-gw (10.100.1.2) from wg0 to eth1
     3  br-gw (10.2.1.1) on eth1
   ```

## 🖥️ Interactive Shell (tsimsh)

The project includes a comprehensive interactive shell (`tsimsh`) built on the `cmd2` framework, providing a user-friendly command-line interface for all simulator operations.

### Key Features

- **Interactive Command Environment**: Full-featured shell with command completion and history
- **Organized Command Structure**: Commands grouped by functionality (mtr, network, service, host, facts)
- **Tab Completion**: Intelligent completion for IP addresses, router names, and options
- **Persistent History**: Command history preserved across sessions (`~/.tsimsh_history.json`)
- **Context Mode**: Streamlined operation with command contexts
- **Colored Output**: Enhanced readability with color-coded messages
- **Comprehensive Help**: Built-in help system for all commands and options

### Quick Start with Shell

```bash
# Launch the interactive shell
./tsimsh

# Basic usage examples
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1
tsimsh> network setup --verbose
tsimsh> service start --ip 10.1.1.1 --port 8080
tsimsh> host add --name web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw
tsimsh> help                    # Show all available commands
tsimsh> help trace               # Show help for specific command group
```

### Shell Dependencies

The shell requires additional Python packages:

```bash
# Install shell dependencies
pip install cmd2 colorama tabulate

# Optional: For enhanced YAML configuration support
pip install pyyaml
```

### Command Categories

1. **Trace Commands** (`trace`): Reverse path tracing with real MTR execution (always enabled)
2. **Network Commands** (`network`): Namespace simulation setup, status, testing, and cleanup
3. **Service Commands** (`service`): TCP/UDP service management and testing
4. **Host Commands** (`host`): Dynamic host creation, removal, and management
5. **Facts Commands** (`facts`): Data collection, processing, and validation

### Scripting Support

The shell supports automation through various methods:

```bash
# Execute single command
echo "trace -s 10.1.1.1 -d 10.2.1.1" | ./tsimsh

# Execute script file
./tsimsh < network_setup.script

# Create reusable scripts
cat > deploy.script << EOF
network setup --verbose
service start --ip 10.1.1.1 --port 80
service start --ip 10.2.1.1 --port 53 --protocol udp
host add --name web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw
EOF
```

For complete shell documentation including all commands, options, and scripting examples, see [TSIM_SHELL.md](TSIM_SHELL.md).

## ⚙️ Configuration

The traceroute simulator supports comprehensive YAML configuration files for flexible deployment scenarios.

### Configuration File Locations (by precedence)

1. **Environment Variable**: `TRACEROUTE_SIMULATOR_CONF` (highest precedence)
2. **User Home Directory**: `~/traceroute_simulator.yaml`
3. **Current Directory**: `./traceroute_simulator.yaml` (lowest precedence)

### Configuration Options

Create a `traceroute_simulator.yaml` file with your preferred settings:

```yaml
# Network and routing configuration
tsim_facts: "tsim_facts"                        # Directory containing unified facts files

# Output configuration  
verbose: false                                  # Enable verbose output (-v flag)
verbose_level: 1                               # Verbosity level (1=basic, 2=detailed)
quiet: false                                   # Quiet mode (no output, exit codes only)
json_output: false                             # Output results in JSON format

# Tracing behavior
enable_mtr_fallback: true                      # Enable MTR fallback for incomplete paths
enable_reverse_trace: false                    # Enable reverse path tracing when forward fails

# Network discovery
controller_ip: null                            # Ansible controller IP (auto-detect if null)
```

### Configuration Examples

**Production Environment:**
```yaml
tsim_facts: "/etc/traceroute-simulator/tsim_facts"
enable_mtr_fallback: true
enable_reverse_trace: true
verbose: false
controller_ip: "192.168.1.100"
```

**Development/Testing:**
```yaml
tsim_facts: "tests/tsim_facts"
enable_mtr_fallback: false  # Simulation only
verbose: true
verbose_level: 2
json_output: true
```

### Precedence Rules

Configuration values are resolved in this order (highest to lowest):
1. **Command line arguments** (e.g., `-v`, `--json`)
2. **Configuration file values**
3. **Hard-coded defaults**

```bash
# Example: Override config file settings via command line
TRACEROUTE_SIMULATOR_CONF=production.yaml make trace ARGS="--tsim-facts custom_facts -s 10.1.1.1 -d 10.2.1.1 -v"
# Uses production.yaml settings but overrides facts directory and enables verbose mode
```

## 🏷️ Router Metadata System

The traceroute simulator includes a comprehensive metadata system that classifies routers based on their network role, capabilities, and properties. This enables advanced features like Linux/non-Linux router differentiation, gateway internet connectivity, and automatic Ansible controller detection.

### Metadata File Structure

Each router can have an optional `*_metadata.json` file alongside its routing data:

```json
{
  "linux": true,
  "type": "gateway", 
  "location": "hq",
  "role": "gateway",
  "vendor": "linux",
  "manageable": true,
  "ansible_controller": false
}
```

### Metadata Properties

- **`linux`** (boolean): Whether the router runs Linux OS (enables MTR execution)
- **`type`** (string): Router type - `"gateway"`, `"core"`, `"access"`, or `"none"`
- **`location`** (string): Physical location - `"hq"`, `"branch"`, `"datacenter"`, etc.
- **`role`** (string): Network role - `"gateway"`, `"distribution"`, `"server"`, `"wifi"`, etc.
- **`vendor`** (string): Router vendor - `"linux"`, `"cisco"`, `"juniper"`, etc.
- **`manageable`** (boolean): Whether manageable via automation tools
- **`ansible_controller`** (boolean): Whether this router is the Ansible controller

### Enhanced Features

1. **MTR Execution**: Only available on Linux routers (`linux: true`)
2. **Gateway Internet Access**: Only gateway routers (`type: "gateway"`) can reach public IPs
3. **Auto Controller Detection**: Router with `ansible_controller: true` provides controller IP
4. **Network Visualization**: Diagrams color-coded by router type
5. **Iptables Analysis**: Packet forwarding decisions based on actual firewall rules
6. **Unified Facts Collection**: Single JSON file per router with all routing, metadata, and firewall data

### Default Values

When metadata files don't exist, routers use these defaults:
```json
{
  "linux": true,
  "type": "none", 
  "location": "none",
  "role": "none",
  "vendor": "linux",
  "manageable": true,
  "ansible_controller": false
}
```

## 🌐 Gateway Internet Connectivity

Gateway routers with `type: "gateway"` can reach public internet IP addresses, providing realistic enterprise network simulation.

### Internet Access Examples

```bash
# Gateway router direct internet access
make trace ARGS="-s 10.1.1.1 -d 1.1.1.1"
# Output: hq-gw (10.1.1.1) → one.one.one.one (1.1.1.1)

# Multi-hop internet access from internal network
make trace ARGS="-s 10.1.10.1 -d 8.8.8.8"
# Output: hq-lab → hq-core → hq-gw → dns.google (8.8.8.8)
```

### Supported Internet Destinations

- **DNS Servers**: 1.1.1.1, 8.8.8.8, 208.67.222.222
- **Any Public IP**: Automatically detected using RFC standards
- **FQDN Resolution**: Shows hostnames like `dns.google` when available

### Gateway Routers in Test Network

- **hq-gw**: 203.0.113.10 (HQ location)
- **br-gw**: 198.51.100.10 (Branch location) 
- **dc-gw**: 192.0.2.10 (Data Center location)

## 🔥 Iptables Forward Analysis

The project includes a comprehensive iptables analysis tool that determines whether packets will be forwarded by specific routers based on their actual firewall configurations.

### Key Features

- **Real Iptables Rules**: Analyzes actual iptables FORWARD chain rules from live routers
- **Ipset Integration**: Full support for ipset match-set conditions with efficient lookups
- **Multi-format Input**: Supports IP ranges (CIDR), comma-separated lists, and port ranges
- **Protocol Support**: Handles tcp, udp, icmp, and all protocols
- **Verbose Analysis**: Three verbosity levels for detailed rule evaluation
- **Exit Code Integration**: Returns clear exit codes for automation (0=allowed, 1=denied, 2=error)

### Usage Examples

```bash
# Basic packet forwarding analysis
make ifa ARGS="--router hq-gw -s 10.1.1.1 -d 10.2.1.1 -p tcp"

# Analyze specific ports with verbose output
make ifa ARGS="--router hq-gw -s 10.1.1.1 -sp 80,443 -d 10.2.1.1 -dp 8080:8090 -p tcp -vv"

# Analyze IP ranges and show ipset structure
make ifa ARGS="--router br-core -s 10.1.0.0/16 -d 10.2.0.0/16,10.3.0.0/16 -p all -vvv"
```

### Command Line Options

- `-s, --source`: Source IP address (supports CIDR, lists: `10.1.1.1,10.1.1.2` or `10.1.1.0/24`)
- `-sp, --source-port`: Source port (supports ranges: `80,443` or `8000:8080`)
- `-d, --dest`: Destination IP address (supports CIDR, lists)
- `-dp, --dest-port`: Destination port (supports ranges)
- `-p, --protocol`: Protocol type (`tcp`, `udp`, `icmp`, `all`)
- `--router`: Router name to analyze (must have unified facts file)
- `--tsim-facts`: Directory containing unified facts files with iptables and ipset data
- `-v, -vv, -vvv`: Verbosity levels (basic decisions, detailed rules, ipset structure)

### Integration with Data Collection

The iptables analyzer uses data from unified facts files collected by the enhanced Ansible playbook:
- `{router}.json`: Complete unified facts including iptables configuration and ipset data
- Structured firewall data with comprehensive rule parsing
- Automatically collected during `make fetch-routing-data`

## 💻 Usage

### Basic Syntax

```bash
TRACEROUTE_SIMULATOR_FACTS=<facts_directory> make trace ARGS="[OPTIONS] -s SOURCE_IP -d DESTINATION_IP"
```

💡 **Tip**: Export the environment variable once to avoid repetition:
```bash
export TRACEROUTE_SIMULATOR_FACTS=tests/tsim_facts
make trace ARGS="-s 10.1.1.1 -d 10.2.1.1"
make ifa ARGS="--router hq-gw -s 10.1.1.1 -d 8.8.8.8 -p tcp"
```

### Simple Examples

```bash
# Basic trace between router interfaces (HQ to Branch)
make trace ARGS="-s 10.1.1.1 -d 10.2.1.1"

# Gateway internet access (gateway to Cloudflare DNS)
make trace ARGS="-s 10.1.1.1 -d 1.1.1.1"

# Multi-hop internet access (internal network to Google DNS)
make trace ARGS="-s 10.1.10.1 -d 8.8.8.8"

# JSON output for programmatic processing (WireGuard tunnel)
make trace ARGS="-j -s 10.100.1.1 -d 10.100.1.3"

# Verbose output with configuration debugging
make trace ARGS="-vvv -s 10.1.1.1 -d 10.2.1.1"

# Specify custom controller IP for SSH access
make trace ARGS="--controller-ip 10.1.2.3 -s 10.1.1.1 -d 192.168.1.1"

# Quiet mode for scripts (check exit code)
make trace ARGS="-q -s 10.1.1.1 -d 10.2.1.1"
echo "Exit code: $?"
```

## 🔧 Command Line Options

| Option | Long Form | Description |
|--------|-----------|-------------|
| `-h` | `--help` | Show help message and exit |
| `-s IP` | `--source IP` | **Required:** Source IP address for traceroute |
| `-d IP` | `--destination IP` | **Required:** Destination IP address for traceroute |
| `-v` | `--verbose` | Enable verbose output (-v basic, -vv detailed, -vvv config debugging) |
| `-q` | `--quiet` | Quiet mode - no output, use exit codes only |
| `-j` | `--json` | Output results in JSON format |
| | `--tsim-facts DIR` | Directory containing unified facts files (default: `tsim_facts`) |
| | `--no-mtr` | Disable MTR fallback (simulation only) |
| | `--reverse-trace` | Enable reverse path tracing when forward simulation fails |
| | `--controller-ip IP` | Ansible controller IP address (auto-detected if not specified) |

### Detailed Option Descriptions

- **Verbose Mode (`-v`)**: Shows router loading process and additional debugging information
  - `-v`: Basic verbose output with router loading information
  - `-vv`: Detailed debugging including MTR execution and SSH command details
  - `-vvv`: Configuration file loading debug output
- **Quiet Mode (`-q`)**: Suppresses all output, useful for automation scripts that check exit codes
- **JSON Mode (`-j`)**: Outputs structured data with all 9 fields for comprehensive path information
- **Custom Directory**: Allows using different sets of unified facts for testing or multiple environments (default: `tsim_facts`)
- **MTR Fallback (`--no-mtr`)**: Disable automatic MTR fallback for simulation-only mode
- **Reverse Path Tracing (`--reverse-trace`)**: Enable three-step reverse path discovery when forward simulation fails
- **Controller IP (`--controller-ip`)**: Specify Ansible controller IP for SSH-based interface detection

## 🔄 Trace Command

The trace command implements comprehensive reverse path tracing using real MTR execution. Unlike the previous simulator, tracing is **always enabled** and not optional.

### How the Trace Algorithm Works

The trace command uses a sophisticated 5-step algorithm:

1. **Step 1: MTR Execution** - Executes MTR from source to destination, capturing all hops including timing data
2. **Step 2: Router Identification** - Identifies which hops are routers vs external hosts based on inventory
3. **Step 3: Interface Detection** - Determines incoming/outgoing interfaces for each router using local routing tables
4. **Step 4: Hop Connectivity** - Establishes prev_hop and next_hop relationships between consecutive hops
5. **Step 5: Remote Interface Detection** - SSH to each router to detect interfaces via `ip route get` commands

### Remote Interface Detection

Step 5 implements intelligent SSH-based interface detection:
- **Direct SSH**: When running from a router, directly SSH to other routers
- **Nested SSH**: When running from controller, SSH via controller to reach routers
- **Relaxed Security**: Uses relaxed host key checking for router connections only
- **Command Execution**: Runs `ip route get <source>` and `ip route get <dest>` on each router
- **Interface Parsing**: Extracts incoming/outgoing interface names from route output

### Command Line Options

| Option | Long Form | Description |
|--------|-----------|-------------|
| `-s IP` | `--source IP` | **Required:** Source IP address for tracing |
| `-d IP` | `--destination IP` | **Required:** Destination IP address for tracing |
| `-j` | `--json` | Output results in JSON format with all 9 fields |
| `-v` | `--verbose` | Enable verbose output (can be used multiple times for more verbosity) |
| | `--controller-ip IP` | Ansible controller IP address (auto-detected if not specified) |

### Output Formats

#### Text Format (Default)
```
# Shows hop name, IP, RTT, and interfaces
hq-dmz (10.1.2.3) 0.34ms [eth0 -> eth1]
hq-core (10.1.2.1) 0.52ms [eth1 -> eth0]
hq-gw (10.1.1.1) 0.71ms [eth0 -> wg0]
```

#### JSON Format (`-j`)
The JSON output includes 9 fields for comprehensive path information:
- `hop`: Hop number in the path
- `name`: Router/host name (empty for non-routers)
- `ip`: IP address of the hop
- `incoming`: Incoming interface name (renamed from "interface")
- `is_router`: Boolean indicating if hop is a known router
- `prev_hop`: Name of the previous hop (new field)
- `next_hop`: Name of the next hop (renamed from "connected_to")
- `outgoing`: Outgoing interface name
- `rtt`: Round-trip time in milliseconds

### Key Features

- **Always Enabled**: Reverse path tracing is always active, not optional
- **Real Network Execution**: Uses actual MTR on network, not simulation
- **Complete Path Information**: All hops included with full interface details
- **Two-Phase Construction**: Handles edge cases with proper path assembly
- **Enhanced Field Names**: More intuitive field naming (incoming/outgoing, prev_hop/next_hop)
- **Comprehensive JSON**: All fields populated for every hop, not just routers

**Note**: The trace command in tsimsh uses the enhanced field names mentioned above. The main traceroute simulator (when run directly) uses legacy field names: `interface`, `is_router_owned`, `connected_router`, and `outgoing_interface`.

### Configuration Loading

The trace command supports enhanced configuration file loading:
- **Verbose Debugging**: Use `-vvv` to see detailed config file loading
- **Key Flexibility**: Supports both 'ansible_controller_ip' and 'controller_ip' keys
- **YAML Handling**: Graceful degradation when PyYAML is not available
- **Error Reporting**: Clear messages for configuration issues

### Use Cases
- **Path Analysis**: Complete forward path discovery with interface details
- **Performance Monitoring**: RTT data for every hop in the path
- **Network Troubleshooting**: Interface-level visibility for packet flow
- **Automation**: JSON output for programmatic processing

### Requirements
- SSH access to Linux routers (passwordless recommended)
- MTR installed on target routers: `sudo apt-get install mtr-tiny`
- Proper hostname resolution for router identification
- Network connectivity from routers to destination targets

## 🌐 FQDN Resolution

The simulator automatically resolves IP addresses to Fully Qualified Domain Names (FQDNs) for improved readability and network troubleshooting.

### How It Works

1. **Automatic Resolution**: Uses reverse DNS lookup via `getent hosts` for consistency with MTR executor
2. **Smart Fallback**: Falls back to original IP address if resolution fails
3. **Router Priority**: Router-owned IPs still show router names (not FQDNs)
4. **Fast Resolution**: Uses 2-second timeout for UI responsiveness

### Before and After

**Before (Generic Labels):**
```
traceroute to 8.8.8.8 from 10.1.1.1
  1  hq-gw (10.1.1.1)
  2  destination (8.8.8.8) 45.9ms
```

**After (FQDN Resolution):**
```
traceroute to 8.8.8.8 from 10.1.1.1
  1  hq-gw (10.1.1.1)
  2  dns.google (8.8.8.8) 45.9ms
```

### Configuration

FQDN resolution is enabled by default and works automatically. No configuration required.

### Benefits

- **Better Clarity**: `dns.google (8.8.8.8)` instead of `destination (8.8.8.8)`
- **Easier Troubleshooting**: Real hostnames help identify network endpoints
- **Consistent Behavior**: Uses same DNS resolution approach as MTR filtering
- **Production Ready**: Graceful fallback ensures reliability

## 🔄 Reverse Path Tracing

The simulator includes advanced reverse path tracing functionality for scenarios where traditional forward simulation and MTR fallback cannot determine complete paths. This is particularly useful in mixed Linux/non-Linux environments.

### How Reverse Path Tracing Works

Reverse path tracing implements a sophisticated three-step approach:

1. **Step 1: Controller to Destination**
   - Replaces original source IP with Ansible controller IP
   - Performs simulation or MTR tracing from controller to destination
   - Establishes the forward path and identifies the last Linux router
   - Extracts timing information for destination reachability validation

2. **Step 2: Destination to Original Source**
   - Finds the last Linux router from Step 1 path
   - Performs reverse simulation/MTR from destination back to original source
   - Uses the last Linux router as the execution point for MTR if needed
   - Includes timing information for intermediate Linux routers when available

3. **Step 3: Path Reversal and Combination**
   - Reverses the path from Step 2 to create original source → destination path
   - Combines bidirectional path information for complete routing picture
   - Preserves timing data from both forward and reverse traces
   - Provides comprehensive view of both forward and reverse connectivity

### Use Cases

- **Complex Network Topologies**: Multi-vendor environments with mixed routing platforms
- **Non-Linux Infrastructure**: Networks where only some routers provide routing data
- **Internet Connectivity**: Tracing paths that traverse external networks
- **Asymmetric Routing**: Scenarios where forward and reverse paths differ significantly
- **Network Troubleshooting**: Understanding bidirectional connectivity issues

### Configuration

```bash
# Enable reverse path tracing with auto-detected controller IP
make trace ARGS="-s 10.1.1.1 -d 192.168.1.1 --reverse-trace"

# Specify custom controller IP for reverse tracing
make trace ARGS="-s 10.1.1.1 -d 192.168.1.1 --reverse-trace --controller-ip 192.168.100.1"

# Verbose mode shows all three steps in detail
make trace ARGS="-s 10.1.1.1 -d 192.168.1.1 --reverse-trace -vv"
```

### Requirements

- Ansible controller connectivity to target networks
- At least one Linux router reachable from both source and destination networks
- SSH access to Linux routers for MTR execution
- Proper network connectivity for bidirectional path discovery

## 🌐 Network Topology

The project includes a comprehensive test network with 10 routers across 3 locations:

### Test Network Overview

- **Location A (Headquarters)**: 4 routers covering 5 network segments (10.1.0.0/16)
  - `hq-gw`: Gateway router with internet and WireGuard connectivity
  - `hq-core`: Core distribution router
  - `hq-dmz`: DMZ services router
  - `hq-lab`: Development lab router with multiple networks

- **Location B (Branch Office)**: 3 routers covering 4 network segments (10.2.0.0/16)
  - `br-gw`: Branch gateway with WireGuard to HQ/DC
  - `br-core`: Branch distribution router
  - `br-wifi`: WiFi controller with multiple wireless networks

- **Location C (Data Center)**: 3 routers covering 5 network segments (10.3.0.0/16)
  - `dc-gw`: Data center gateway with WireGuard connectivity
  - `dc-core`: DC distribution router
  - `dc-srv`: Server farm router with multiple server networks

### WireGuard VPN Mesh
- **10.100.1.0/24**: Full mesh VPN connecting all three locations
- Inter-location traffic flows through encrypted tunnels
- Realistic enterprise network design with redundancy

### Network Diagram

![Network Topology](docs/network_topology.png)

The complete network topology diagram shows all 10 routers with their interface assignments and connections. High-resolution versions are available as `docs/network_topology.png` and `docs/network_topology.pdf`.

For complete topology details, see `docs/NETWORK_TOPOLOGY.md`.

## 📊 Data Collection

### Automated Data Collection with Make

The project provides automated tools for collecting routing information from network devices:

```bash
# Check all dependencies first
make check-deps

# Collect routing data using inventory file
make fetch-routing-data OUTPUT_DIR=production_data INVENTORY_FILE=hosts.yml

# Collect from configured inventory group
make fetch-routing-data OUTPUT_DIR=test_data INVENTORY=routers

# Run comprehensive test suite
make test
```

### Using Ansible Playbook Directly

The project includes an enhanced Ansible playbook that executes basic `ip` commands on remote hosts and converts text output to JSON on the controller:

1. **Configure your inventory** (`hosts.yml`):
   ```yaml
   all:
     children:
       linux_routers:
         hosts:
           hq-gw:
             ansible_host: 10.1.1.1
           br-gw:
             ansible_host: 10.2.1.1
   ```

2. **Run the data collection playbook**:
   ```bash
   # Using inventory file
   ansible-playbook -i hosts.yml ansible/get_tsim_facts.yml -e "tsim_facts_dir=my_data"
   
   # Using configured inventory with group targeting
   ansible-playbook ansible/get_tsim_facts.yml --limit routers -e "tsim_facts_dir=my_data"
   ```

3. **Verify collected data**:
   ```bash
   ls my_data/
   # hq-gw.json  br-gw.json  dc-gw.json  ... (unified JSON files)
   ```

### Enhanced Compatibility Features

- **Comprehensive data collection**: Executes `ip route show`, `ip rule show`, `iptables` commands, and `ipset list` on remote hosts
- **Automatic path discovery**: Searches standard utility paths (`/sbin`, `/usr/sbin`, `/bin`, `/usr/bin`) for commands
- **Full path execution**: Uses complete path to commands for maximum reliability across Linux distributions
- **Root access management**: Proper sudo/root access for complete iptables and ipset visibility
- **Controller-side JSON conversion**: Transfers text output to Ansible controller for JSON transformation
- **No remote Python dependencies**: Remote hosts only need standard Linux commands available
- **IP JSON wrapper on controller**: Uses `ansible/ip_json_wrapper.py` on the controller to convert text to JSON
- **Graceful degradation**: Continues operation even when ipset command is not available
- **Automatic cleanup**: Removes temporary text files after processing
- **Detailed logging**: Provides collection statistics and troubleshooting information

### Manual Collection

For single routers or custom setups:

```bash
# Create output directory
mkdir -p tsim_facts

# Run unified facts collection script
sudo bash ansible/get_facts.sh > tsim_facts/hostname_raw_facts.txt

# Convert to structured JSON
python3 ansible/process_facts.py tsim_facts/hostname_raw_facts.txt tsim_facts/hostname.json
```

### Data Format

The project uses a unified JSON format for comprehensive network analysis:

- **Unified JSON files** (`*.json`): Complete network facts including routing, rules, iptables, and system information
- **Metadata files** (`*_metadata.json`): Router classification and properties (optional)

File naming convention: `{hostname}.json` (e.g., `hq-gw.json`, `br-gw.json`)

### IP JSON Wrapper for Legacy Systems

The project includes `ansible/ip_json_wrapper.py`, a compatibility tool for older Red Hat systems that don't support `ip --json`:

```bash
# Use wrapper script on systems without native JSON support
python3 ansible/ip_json_wrapper.py route show
python3 ansible/ip_json_wrapper.py addr show  
python3 ansible/ip_json_wrapper.py link show
python3 ansible/ip_json_wrapper.py rule show

# Wrapper automatically detects and uses native JSON if available
python3 ansible/ip_json_wrapper.py --json route show  # Passes through to native command
```

**Key Features:**
- **Transparent replacement**: Drop-in replacement for `ip --json` commands
- **Identical output**: Produces byte-for-byte identical JSON to native commands
- **Automatic detection**: Uses native JSON support when available
- **Comprehensive coverage**: Supports route, addr, link, and rule subcommands
- **Validated compatibility**: 100% test coverage ensures output accuracy

## 🐧 Linux Namespace Simulation

The project includes a comprehensive Linux namespace-based network simulation system that creates real network infrastructure for testing. This enables actual packet testing with real networking components instead of just simulation.

### Understanding Linux Network Namespaces

Linux network namespaces provide isolated network environments within a single Linux system. Each namespace has its own network interfaces, routing tables, firewall rules, and network connections, completely isolated from other namespaces and the host system. This allows multiple virtual network stacks to coexist on the same machine.

**Basic `ip netns` Commands**:

```bash
# List all network namespaces
sudo ip netns list

# Execute a command in a specific namespace
sudo ip netns exec hq-gw ip addr show        # Show interfaces in hq-gw namespace
sudo ip netns exec hq-gw ip route show       # Show routing table
sudo ip netns exec hq-gw iptables -L -n     # Show firewall rules

# Enter a namespace shell for interactive exploration
sudo ip netns exec hq-gw bash
# Now you're inside the namespace - all commands run in isolated network
ip addr show                                 # Shows only namespace interfaces
ping 10.2.1.1                               # Ping from within namespace
exit                                        # Return to host system

# Show interfaces and their peer connections
sudo ip netns exec hq-gw ip link show        # List all interfaces
sudo ip netns exec hq-gw ip -d link show eth0  # Detailed view of eth0

# Check connectivity between namespaces
sudo ip netns exec hq-core ping -c 1 10.1.1.1  # Ping hq-gw from hq-core

# Monitor traffic in a namespace
sudo ip netns exec hq-gw tcpdump -i eth0 -n    # Capture packets on eth0

# Show namespace-specific network statistics
sudo ip netns exec hq-gw ss -tulpn          # Show listening ports
sudo ip netns exec hq-gw netstat -rn        # Routing table (alternative view)
```

**Exploring the Simulated Network**:

After running `sudo make netsetup`, you can explore the created network topology directly:

```bash
# See all created router namespaces
sudo ip netns list | grep -E '^(hq|br|dc)-'

# Trace the path from hq-lab to dc-srv manually
sudo ip netns exec hq-lab ip route get 10.3.1.1      # Next hop: 10.1.10.1
sudo ip netns exec hq-core ip route get 10.3.1.1     # Next hop: 10.1.1.1
sudo ip netns exec hq-gw ip route get 10.3.1.1       # Next hop: 10.100.1.3
sudo ip netns exec dc-gw ip route get 10.3.1.1       # Next hop: 10.3.1.2
sudo ip netns exec dc-core ip route get 10.3.1.1     # Next hop: 10.3.1.1

# Verify WireGuard tunnels on gateway routers
sudo ip netns exec hq-gw wg show                     # WireGuard status
sudo ip netns exec hq-gw ip addr show wg0            # WireGuard interface

# Check firewall rules and packet counts
sudo ip netns exec hq-gw iptables -L FORWARD -v -n   # Forward chain with packet counts
sudo ip netns exec hq-gw ipset list                  # Show ipset configurations
```

This direct access via `ip netns` commands allows you to understand and debug the network setup without the tsimsh abstraction layer, providing full visibility into the Linux networking stack.

### Implementation of Router Simulation

The project implements a sophisticated router simulation by creating Linux network namespaces that mirror real production routers. Each simulated router namespace is configured with the exact networking state collected from actual Linux routers through the Ansible facts gathering system.

**Complete Network Stack Replication**:

When `network_namespace_setup.py` creates a router namespace, it replicates the following components from the unified JSON facts files:

1. **Network Interfaces**: Creates veth pairs to simulate physical interfaces, assigns all IP addresses (primary and secondary), and sets up bridge interfaces for host connectivity

2. **Routing Tables**: Installs all routes from the main routing table including default routes, connected routes, static routes, and dynamically learned routes. Routes are added with correct metrics, preferred source addresses, and next-hop information

3. **Policy Routing Rules**: Implements Linux policy-based routing by creating all ip rules with proper priorities, selectors (source/destination/fwmark), and target routing tables. This enables complex routing decisions based on packet attributes

4. **Firewall Rules (iptables)**: Recreates the complete iptables ruleset including:
   - FORWARD chain rules for packet forwarding decisions
   - Custom chains with jump targets
   - Match conditions (source/dest IPs, ports, interfaces, protocols)
   - Connection tracking states
   - Packet marking rules

5. **IP Sets (ipset)**: Creates all ipset configurations used by iptables rules:
   - Hash:net sets for CIDR blocks
   - Hash:ip sets for individual IPs
   - Bitmap:port sets for port ranges
   - Nested sets with proper memberships

6. **Special Interfaces**: Configures advanced networking features:
   - WireGuard tunnels on gateway routers with proper keys and peers
   - Bridge interfaces for connecting host namespaces
   - Loopback interfaces with additional IPs

**Example of Facts-to-Namespace Translation**:

```python
# From hq-gw.json facts file:
"interfaces": {
  "eth0": ["10.1.1.1/24"],
  "eth1": ["10.1.2.2/24"],
  "wg0": ["10.100.1.1/24"]
}

# Becomes in namespace:
ip netns exec hq-gw ip addr show
# 2: eth0: <BROADCAST,MULTICAST,UP> mtu 1500
#     inet 10.1.1.1/24 scope global eth0
# 3: eth1: <BROADCAST,MULTICAST,UP> mtu 1500  
#     inet 10.1.2.2/24 scope global eth1
# 4: wg0: <POINTOPOINT,NOARP,UP> mtu 1420
#     inet 10.100.1.1/24 scope global wg0
```

This comprehensive replication ensures that the simulated network behaves identically to the production network, allowing accurate testing of routing decisions, firewall rules, and service connectivity without accessing the actual infrastructure. The simulation is so complete that you can run real network tools (ping, traceroute, mtr, tcpdump) and get authentic results.

### Namespace Simulation Features

- **Real Network Infrastructure**: Creates actual Linux namespaces with full network topology
- **Complete Configuration**: Routing tables, iptables rules, ipsets, and interface setup
- **Multi-Protocol Testing**: ICMP ping, TCP, and UDP connectivity testing
- **Real Packet Validation**: Uses netcat servers/clients for end-to-end connectivity verification  
- **Firewall Testing**: Verifies iptables rules properly block or allow traffic as expected
- **Public IP Simulation**: Automatic setup on gateway routers for realistic internet testing
- **MTR Integration**: Real traceroute testing with hop-by-hop analysis
- **Comprehensive Management**: Setup, status monitoring, testing, and cleanup automation

### Namespace Make Targets

```bash
# Setup complete network simulation (requires sudo)
sudo make netsetup

# Test connectivity between any two IPs
sudo make nettest ARGS="-s 10.1.1.1 -d 10.2.1.1 --test-type ping"
sudo make nettest ARGS="-s 10.1.1.1 -d 8.8.8.8 --test-type mtr -v"
sudo make nettest ARGS="-s 10.1.1.1 -d 10.2.1.1 --test-type both"

# Show network status and configuration
sudo make netstatus ARGS="all summary"                    # All namespaces
sudo make netstatus ARGS="hq-gw interfaces"              # Specific router
make netshow ARGS="all topology"                         # Static topology from facts

# Host management (dynamic hosts)
sudo make hostadd ARGS="--host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw"
sudo make hostdel ARGS="--host web1"
sudo make hostlist                                        # List all hosts
sudo make hostclean                                       # Remove all hosts

# Cleanup simulation
sudo make netclean                                        # Remove all namespaces
sudo make netnsclean                                      # Clean both routers and hosts
```

### Testing Integration

```bash
# Run basic namespace tests (part of main test suite)
sudo make test-namespace                                  # 6 basic functionality tests

# Run comprehensive network connectivity tests (separate target)  
sudo make test-network                                    # Deep connectivity testing (3-5 min)
```

### Network Architecture

The namespace simulation creates a complete enterprise network topology:

- **10 Router Namespaces**: Each router gets its own network namespace
- **Real Network Interfaces**: veth pairs connecting namespaces 
- **Actual Routing Tables**: All routes from router facts installed
- **Live Iptables Rules**: All firewall rules and ipsets configured
- **WireGuard VPN**: Real encrypted tunnels between gateway routers
- **Public IP Access**: Gateway routers can reach external destinations
- **Dynamic Host Management**: Add/remove hosts connected to any router bridge

### Benefits Over Pure Simulation

1. **Real Packet Testing**: Actual network packets flow through real interfaces
2. **Firewall Validation**: Iptables rules actually block or allow traffic
3. **MTR Integration**: Real traceroute testing with timing information
4. **Protocol Coverage**: Test TCP/UDP services, not just routing logic
5. **Complex Scenarios**: Multi-hop routing with real network latency
6. **Production Fidelity**: Network behavior matches real-world conditions

## 🔧 Service Management

The simulator includes comprehensive TCP/UDP service management with an IP-based interface. Services are implemented using `socat` for reliable multi-client echo functionality.

### Service Features

- **IP-Based Interface**: Work with IP addresses directly, no namespace knowledge required
- **Multi-Client Support**: Services handle multiple simultaneous connections
- **TCP and UDP Support**: Both protocols supported for comprehensive testing
- **Silent Operation**: Commands are silent by default for automation (use -v for output)
- **Automatic Namespace Detection**: System determines namespace from IP address
- **System Namespace Protection**: Cannot start services on non-user namespaces
- **JSON Output**: Service listing supports JSON format for programmatic access

### Service Commands

```bash
# Start services
sudo make svcstart ARGS='10.1.1.1:8080'                    # TCP echo service
sudo make svcstart ARGS='10.2.1.1:53 -p udp --name dns'    # UDP service with name

# Test services
sudo make svctest ARGS='-s 10.1.1.1 -d 10.2.1.1:8080'      # Test connectivity
sudo make svctest ARGS='-s 10.1.1.1 -d 10.2.1.1:53 -p udp -m "Query"'  # UDP with message

# Manage services
sudo make svcstop ARGS='10.1.1.1:8080'                     # Stop specific service
sudo make svclist                                          # List all services
sudo make svclist ARGS='-j'                                # JSON output
sudo make svcclean                                         # Stop all services
```

### Service Output Format

Services are displayed in separate tables for routers and hosts:

```
=== Services on Routers ===
Router          Listen IP            Port     Protocol Status    
----------------------------------------------------------------------
hq-gw           10.1.1.1             8080     tcp      running   
br-gw           10.2.1.1             53       udp      running   

=== Services on Hosts ===
Host            Listen IP            Port     Protocol Status    
----------------------------------------------------------------------
web1            10.1.1.100           80       tcp      running
```

## 🏠 Host Management

Dynamic host management allows adding and removing hosts to the running network simulation. Hosts are regular namespaces with simplified networking that connect to router bridges.

### Host Features

- **Dynamic Creation**: Add hosts to running network without restart
- **Bridge Connectivity**: Hosts connect to router bridge interfaces
- **Multiple IPs**: Support for primary and secondary IP addresses
- **Persistent Registry**: Hosts survive across commands
- **Gateway Configuration**: Automatic default route setup
- **Full Network Access**: Hosts can reach any destination via connected router

### Host Commands

```bash
# Add hosts
sudo make hostadd ARGS='--host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw'
sudo make hostadd ARGS='--host db1 --primary-ip 10.3.20.100/24 --connect-to dc-srv --secondary-ips 192.168.1.1/24'

# Manage hosts  
sudo make hostlist                                          # List all hosts
sudo make hostdel ARGS='--host web1 --remove'              # Remove specific host
sudo make hostclean                                         # Remove all hosts
```

### Host Configuration Example

```
Host: web1 [running]
  Primary IP: 10.1.1.100/24
  Connected to: hq-gw (gateway: 10.1.1.1)
  Created: Fri 27 Jun 2025 18:07:19 CEST
```

## 🛡️ System Namespace Protection

The simulator automatically distinguishes between user namespaces (routers and hosts) and system namespaces, ensuring clean separation and protection:

### Protection Features

- **Automatic Filtering**: Only known routers (from facts) and registered hosts are shown
- **Command Protection**: System namespaces cannot be used with user commands
- **Hidden from Output**: System namespaces don't appear in status or list commands
- **No Hardcoded Lists**: Dynamic detection based on configuration, not naming patterns
- **Third-Party Safety**: Any namespace not explicitly configured is considered system

### Examples

```bash
# System namespaces (test-debug, netsim, etc.) are:
- Hidden from 'sudo make netstatus ARGS="all summary"'
- Cannot be used with svcstart, svctest, or nettest
- Not counted in namespace totals
- Protected from accidental modification
```

## 🌐 Network Scenarios

The simulator handles various complex network scenarios using the realistic test topology:

### Supported Routing Scenarios

1. **Intra-Location Routing**: Communication within each location through distribution layers
2. **Inter-Location Routing**: Cross-site communication via WireGuard VPN tunnels
3. **Multi-Hop Routing**: Complex paths through multiple routers and network layers
4. **Network Segment Routing**: Host-to-host communication across different subnets
5. **VPN Tunnel Routing**: Encrypted traffic flows between remote locations
6. **Internet Gateway Routing**: Access to external destinations through location gateways

### Example Routing Scenarios

```bash
# Intra-location: HQ internal routing
10.1.10.1 (hq-lab) → 10.1.3.1 (hq-dmz)
Path: hq-lab → hq-core → hq-dmz

# Inter-location: HQ to Branch via WireGuard  
10.1.1.1 (hq-gw) → 10.2.1.1 (br-gw)
Path: hq-gw[wg0] → br-gw[wg0]

# Complex multi-hop: Lab to Data Center servers
10.1.11.100 (HQ lab host) → 10.3.21.200 (DC server host)
Path: lab-network → hq-lab → hq-core → hq-gw → [WireGuard] → dc-gw → dc-core → dc-srv → server-network
```

## 🎨 Network Visualization

The project includes a professional network topology visualization system that generates high-quality diagrams of the test network.

### Generating Network Diagrams

```bash
# Generate network topology diagram
cd docs
python3 network_topology_diagram.py

# Generated files:
# - network_topology.png (300 DPI raster image)
# - network_topology.pdf (vector format for printing)
```

### Visualization Features

- **Professional Layout**: Clean hierarchical design with proper spacing
- **No Crossing Connections**: Optimized routing to avoid visual clutter  
- **Adaptive Sizing**: Router boxes automatically scale based on interface count
- **Color Coding**: Different colors for gateway, core, and access routers
- **Comprehensive Information**: All router names, IP addresses, and interfaces
- **Multiple Formats**: High-resolution PNG and scalable PDF output

### Customization Options

The visualization can be customized by editing `docs/network_topology_diagram.py`:

- **Router Positions**: Modify coordinates in `gateways`, `cores`, and `access` arrays
- **Colors**: Update the `colors` dictionary for different themes
- **Font Sizes**: Adjust text sizing for different display requirements
- **Box Sizing**: Automatic scaling based on interface count (2-4 interfaces)
- **Export Formats**: PNG (300 DPI) and PDF (vector) formats supported

### Use Cases

- **Documentation**: Professional network diagrams for technical documentation
- **Presentations**: High-quality visuals for network architecture presentations  
- **Training**: Visual aids for understanding complex network topologies
- **Planning**: Reference diagrams for network expansion or modifications

## 📄 Output Formats

### Text Format (Default)

Human-readable output showing hop-by-hop path information:

```
# Normal simulation (no timing information)
traceroute to 10.3.20.1 from 10.1.10.1
  1  hq-lab (10.1.10.1) from eth1 to eth0
  2  hq-core (10.1.2.1) from eth0 to eth0
  3  hq-gw (10.1.1.1) from eth0 to wg0
  4  dc-gw (10.100.1.3) from wg0 to eth1
  5  destination (10.3.20.1) via eth1 on dc-gw

# MTR fallback with timing information
traceroute to 8.8.8.8 from 10.1.1.1 (using forward path tracing with mtr tool)
  1  hq-gw (10.1.1.1)
  2  destination (8.8.8.8) 45.6ms

# Reverse path tracing with timing
traceroute to 8.8.8.8 from 10.10.0.2 (using reverse path tracing with mtr tool)
  1  source (10.10.0.2)
  2  hq-gw (10.1.1.1) 55.2ms
  3  destination (8.8.8.8) 52.1ms
```

### JSON Format (`-j`)

Structured output for programmatic processing:

```json
{
  "traceroute_path": [
    {
      "hop": 1,
      "name": "hq-gw",
      "ip": "10.1.1.1",
      "incoming": "eth0",
      "is_router": true,
      "prev_hop": "",
      "next_hop": "hq-core",
      "outgoing": "eth1",
      "rtt": 0.34
    },
    {
      "hop": 2,
      "name": "hq-core",
      "ip": "10.1.2.1",
      "incoming": "eth1",
      "is_router": true,
      "prev_hop": "hq-gw",
      "next_hop": "destination",
      "outgoing": "eth0",
      "rtt": 0.52
    },
    {
      "hop": 3,
      "name": "",
      "ip": "8.8.8.8",
      "incoming": "",
      "is_router": false,
      "prev_hop": "hq-core",
      "next_hop": "",
      "outgoing": "",
      "rtt": 45.6
    }
  ]
}
```

**Key JSON Fields:**
- `name`: Router/host name (empty for non-routers)
- `ip`: IP address of the hop
- `incoming`: Incoming interface name (renamed from "interface")
- `is_router`: Boolean indicating if hop is a known router (renamed from "is_router_owned")
- `prev_hop`: Name of the previous hop in the path (new field)
- `next_hop`: Name of the next hop in the path (renamed from "connected_to")
- `outgoing`: Outgoing interface name (renamed from "outgoing_interface")
- `rtt`: Round-trip time in milliseconds (always included with trace command)

### Verbose Format (`-v`)

Includes debugging information:

```
Loaded router: hq-gw
Loaded router: hq-core
Loaded router: hq-lab
Loaded router: br-gw
Loaded router: dc-gw
[... additional router loading messages ...]
traceroute to 10.2.5.1 from 10.1.11.1
  1  hq-lab (10.1.11.1) from eth2 to eth0
  2  hq-core (10.1.2.1) from eth0 to eth0
  3  hq-gw (10.1.1.1) from eth0 to wg0
  4  br-gw (10.100.1.2) from wg0 to eth1
  5  br-core (10.2.1.2) from eth1 to eth1
  6  br-wifi (10.2.2.3) from eth1 to wlan0
  7  br-wifi (10.2.5.1) on wlan0
```

## 🚦 Exit Codes

The simulator uses standard exit codes for automation and error handling:

| Code | Meaning | Description |
|------|---------|-------------|
| `0` | **Success** | Path found successfully between source and destination |
| `1` | **No Path** | Source and destination found, but no routing path exists |
| `2` | **Not Found** | Source or destination IP not reachable by any router |
| `4` | **No Linux Routers** | MTR executed but no Linux routers found in path |
| `10` | **Error** | Input validation error or system error |

### Using Exit Codes in Scripts

```bash
#!/bin/bash
make trace ARGS="--tsim-facts tsim_facts -q -s "$1" -d "$2"
case $? in
    0) echo "Route found" ;;
    1) echo "No path available" ;;
    2) echo "IP not reachable" ;;
    4) echo "No Linux routers found" ;;
    10) echo "Invalid input or error" ;;
esac
```

## 🧪 Testing

The project includes comprehensive test suites covering all functionality:

### Automated Testing with Make

```bash
# Run all tests (recommended) - includes namespace make targets tests
make test

# Run namespace simulation tests only (requires sudo)
sudo make test-namespace

# Run comprehensive network connectivity tests (requires sudo, 3-5 minutes)
sudo make test-network

# Check dependencies before testing
make check-deps

# Clean up test artifacts
make clean
```

### Test Coverage Summary

- **Namespace & Network Tests**: 103 test cases
  - Namespace make targets: 55 tests
  - Network make targets: 26 tests  
  - Bridge architecture: 7 tests
  - Host management: 7 tests
  - Namespace simulation: 6 tests
  - Basic/quick tests: 8 tests
- **Core Functionality Tests**: 27 test cases
  - Main simulator: 9 tests
  - Reverse path tracing: 18 tests
- **Error Handling Tests**: 35 test cases
  - Error handling: 29 tests
  - Make targets errors: 6 tests
- **Integration & Services Tests**: 47 test cases
  - Facts processing: 18 tests
  - Service manager: 14 tests
  - Make targets focused: 13 tests
  - Integration tests: 3 tests
- **MTR Integration Tests**: 8 test scenarios (script-based)
- **IP Wrapper Tests**: 1 test method (runs 5-6 internal cases)

**Total**: 228 test cases with near-complete code coverage

### Individual Test Suites

```bash
# Main traceroute simulator tests
cd tests && python3 -B test_traceroute_simulator.py

# MTR integration tests
cd tests && python3 -B test_mtr_integration.py

# IP JSON wrapper validation
cd tests && python3 -B test_ip_json_comparison.py

# Iptables analyzer and facts processing
cd tests && python3 -B test_comprehensive_facts_processing.py

# Namespace simulation tests (requires sudo)
sudo python3 -B tests/test_namespace_simulation.py

# Service manager tests (requires sudo)
sudo python3 -B tests/test_service_manager.py

# Error handling tests
sudo python3 -B tests/test_make_targets_errors.py

# Integration workflow tests
sudo python3 -B tests/test_make_targets_integration.py
```

**Namespace Simulation Tests (6 test cases - requires sudo)**:
```bash
sudo python3 -B tests/test_namespace_simulation.py
```

**Comprehensive Network Connectivity Tests (requires sudo)**:
```bash
sudo python3 -B tests/test_make_targets_network.py
```

### Running Tests

```bash
# Run comprehensive test suite
cd tests
python3 test_traceroute_simulator.py

# Expected output
Total tests: 9
Passed: 9 (100%)
Failed: 0
Pass rate: 100.0%

NETWORK TOPOLOGY:
- Location A (HQ): 4 routers, 5 networks (10.1.0.0/16)
- Location B (Branch): 3 routers, 4 networks (10.2.0.0/16)
- Location C (DC): 3 routers, 5 networks (10.3.0.0/16)
- WireGuard mesh: 10.100.1.0/24 interconnecting all locations
```

**MTR Integration Tests (8 test cases)**:
```bash
cd tests  
python3 test_mtr_integration.py
```

### Test Categories

The test suite includes 228 tests across multiple modules:
- **Namespace & Network**: 103 tests for namespace operations, network setup, and bridge architecture
- **Core Functionality**: 27 tests (simulator: 9, reverse path tracing: 18)
- **Error Handling**: 35 tests for exception scenarios and error conditions
- **Integration & Services**: 47 tests (facts processing: 18, service manager: 14, make targets: 15)
- **MTR Integration**: 8 test scenarios for fallback testing
- **IP Wrapper**: 1 test method with 5-6 internal test cases

### Test Coverage

- ✅ **228 comprehensive test cases** covering all functionality
- ✅ **100% pass rate** with complete functionality validation
- ✅ **Comprehensive make targets testing** - All namespace and host management operations (NEW!)
- ✅ **Separated test complexity** - Fast basic tests in main suite, deep network tests in separate target
- ✅ **10-router topology** with realistic routing configurations across 3 locations
- ✅ **All command-line options** tested including new required flags (-s/-d)  
- ✅ **Comprehensive error handling** including corrupted JSON, missing files, and invalid inputs
- ✅ **Complete exit code verification** across all modes (quiet, verbose, JSON)
- ✅ **Facts persistence** ensures test data remains available for namespace testing after `make test`
- ✅ **Edge case coverage** including IPv6 handling, loop detection, and timeout scenarios
- ✅ **Routing misconfiguration testing** with realistic failure scenarios
- ✅ **JSON output format validation** with structured data verification
- ✅ **WireGuard VPN tunnel routing** with full mesh connectivity testing
- ✅ **Multi-location network testing** covering all inter-site communication paths
- ✅ **Real packet testing** with Linux namespaces and network connectivity validation
- ✅ **Enhanced cleanup systems** for comprehensive namespace resource management

## 🔧 Build System

The project includes a comprehensive Makefile for automated development tasks:

### Available Make Targets

```bash
make help                    # Show all available targets and usage examples
make check-deps             # Verify Python modules and provide installation hints  
make test                   # Run comprehensive test suite with environment validation
make clean                  # Clean up Python cache files and temporary artifacts
```

### Data Collection Targets

```bash
# Collect routing data using inventory file
make fetch-routing-data OUTPUT_DIR=my_data INVENTORY_FILE=hosts.ini

# Collect from configured Ansible inventory group  
make fetch-routing-data OUTPUT_DIR=production INVENTORY=routers

# Target specific host from configured inventory
make fetch-routing-data OUTPUT_DIR=temp INVENTORY=router-01
```

### Build System Features

- **Dependency validation**: Checks all required Python modules with helpful installation hints
- **Comprehensive testing**: Integrated test suite with 228 tests across all modules
- **Privileged test management**: Automatic detection and execution of sudo-required tests
- **Test separation**: Fast core tests in main suite, comprehensive network tests in separate target
- **Ansible integration**: Automated data collection with inventory validation and error handling
- **Environment verification**: Validates test data availability and routing facts
- **Clean builds**: Removes cache files while preserving valuable routing data
- **Namespace management**: Complete Linux namespace simulation lifecycle with proper cleanup

## 📝 Examples

### Basic Router Communication

```bash
# Intra-location routing (HQ internal)
make trace ARGS="-s 10.1.1.1 -d 10.1.2.1"
# Output: HQ gateway to core router

# Inter-location routing (HQ to Branch)
make trace ARGS="-s 10.1.1.1 -d 10.2.1.1"
# Output: Cross-site via WireGuard tunnel
```

### Network Segment Routing

```bash
# From HQ lab network to DC server network
make trace ARGS="-s 10.1.10.100 -d 10.3.20.200"
# Output: Complex multi-hop path through multiple locations

# Branch WiFi to Data Center servers  
make trace ARGS="-s 10.2.5.50 -d 10.3.21.100"
# Output: Cross-location routing via distribution layers
```

### Automation Examples

```bash
# Check connectivity in script
if make trace ARGS="-q -s 10.1.1.1 -d 10.3.1.1"; then
    echo "HQ to DC route available"
else
    echo "No route found"
fi

# JSON processing with jq
make trace ARGS="-j -s 10.1.10.1 -d 10.3.20.1" | \
    jq '.traceroute_path[].name'
```

### Complex Scenarios

```bash
# WireGuard tunnel mesh routing
make trace ARGS="-s 10.100.1.1 -d 10.100.1.3"
# Output: Direct VPN tunnel communication

# Multi-hop cross-location routing
make trace ARGS="-v -s 10.1.11.1 -d 10.2.6.1"
# Output: HQ lab to Branch WiFi with detailed hop information

# Maximum complexity: End-to-end across all 3 locations
make trace ARGS="-s 10.1.11.100 -d 10.3.21.200"
# Output: Lab host → HQ → Branch → DC → Server host
```

### Trace Command Examples

```bash
# Basic trace with interface detection
make trace ARGS="-s 10.1.1.1 -d 8.8.8.8"
# Output: Shows each hop with [incoming -> outgoing] interfaces

# JSON output with all 9 fields
make trace ARGS="-j -s 10.1.1.1 -d 8.8.8.8"
# Output: Complete path information including prev_hop/next_hop relationships

# Detailed debugging with SSH commands
make trace ARGS="-s 10.1.1.1 -d 203.0.113.1 -vv"
# Output: Shows MTR execution and SSH interface detection commands

# Configuration debugging
make trace ARGS="-s 10.1.1.1 -d 10.2.1.1 -vvv"
# Output: Shows YAML config file loading and parsing details
```

## 🌐 Web Interface

The project includes a comprehensive web interface for network reachability testing with authentication and report generation capabilities.

### Web Interface Features

- **Authentication System**: Secure login with session management
- **Network Reachability Testing**: Web form for testing service connectivity
- **User-Provided Trace Files**: Support for uploading custom trace JSON data
- **PDF Report Generation**: Comprehensive network analysis reports in PDF format
- **Interactive Testing**: Real-time execution of network tests via tsimsh
- **Visual Network Diagrams**: Integration with network topology visualization

### Web Interface Setup

1. **Configure Apache** (see `web/conf/apache-site.conf.template`):
   ```bash
   # Copy and customize the Apache configuration
   cp web/conf/apache-site.conf.template /etc/apache2/sites-available/traceroute-sim.conf
   
   # Enable required Apache modules
   a2enmod cgi
   a2enmod rewrite
   
   # Enable the site
   a2ensite traceroute-sim
   systemctl reload apache2
   ```

2. **Configure the Application**:
   ```bash
   # Copy and customize the configuration
   cp web/conf/config.json.example web/conf/config.json
   
   # Create users for authentication
   ./web/scripts/create_user.sh username
   ```

3. **Set Up Permissions**:
   ```bash
   # Follow the group permissions setup guide
   # See web/docs/group-permissions-setup.md for details
   ```

### Web Interface Usage

1. **Access the Login Page**: Navigate to `http://your-server/login.html`

2. **Network Reachability Test Form**:
   - **Source IP**: Starting point for the test
   - **Source Port**: Optional source port
   - **Destination IP**: Target endpoint
   - **Destination Port**: Required service port
   - **Protocol**: TCP or UDP
   - **Trace File Input**: Optional custom trace data

3. **Test Results Include**:
   - Network path trace analysis
   - Connectivity tests (ping, MTR, service)
   - Firewall rule analysis
   - Visual network diagram
   - Comprehensive PDF report (see example at `docs/report_example.pdf`)

### Network Reachability Script

The web interface uses `network_reachability_test.sh` which provides:
- JSON-formatted test results
- Integration with tsimsh commands
- Comprehensive network analysis
- Support for both interactive and batch modes

### PDF Report Generation

The system generates comprehensive PDF reports that include:

1. **Network Path Visualization**: NetworkX-based graph showing the complete path from source to destination
2. **Router Details**: For each router in the path:
   - Router name and IP addresses
   - Firewall rules (iptables FORWARD chain)
   - Packet counts before and after testing
   - Rule analysis showing which rules would match the test traffic
3. **Test Results Summary**: 
   - ICMP ping test results
   - MTR (My TraceRoute) hop-by-hop analysis
   - Service connectivity test results
   - Overall reachability verdict
4. **Timing Information**: Execution time for each test phase

**Example Report**: See `docs/report_example.pdf` for a complete example of the generated report format.

#### Report Generation Process

The PDF generation involves several components working together:

1. **network_reachability_test.sh**: Main test orchestration script that:
   - Sets up test environment using tsimsh commands
   - Executes connectivity tests (ping, MTR, service test)
   - Captures iptables packet counts before and after tests
   - Outputs comprehensive JSON results

2. **analyze_packet_counts.py**: Analyzes iptables rules and packet count changes:
   - Parses iptables rules from each router
   - Compares packet counts before and after tests
   - Identifies which rules matched the test traffic
   - Provides detailed firewall analysis

3. **visualize_reachability.py**: Creates the PDF report using:
   - **NetworkX**: For network graph layout and visualization
   - **Matplotlib**: For rendering the network diagram
   - **PyHyphen** (optional): For better text wrapping in tables
   - Combines trace data and test results into a visual report

4. **Web Interface Integration**:
   - `web/cgi-bin/main.py`: Handles form submission and orchestrates the test
   - `web/cgi-bin/lib/executor.py`: Manages command execution with proper environment
   - `web/cgi-bin/generate_pdf.sh`: CGI wrapper for PDF generation
   - Results are stored in `/var/www/traceroute-web/data/pdfs/`

### Security Considerations

- Authentication required for all operations
- Session management with secure cookies
- Input validation on all form fields
- Audit logging of all operations
- Network locking to prevent concurrent tests

## 🔍 Troubleshooting

### Common Issues

**1. "No router data found" Error**
```bash
Error: No router data found in tests/tsim_facts
```
- **Solution**: Ensure routing JSON files exist in the tests/tsim_facts directory
- **Check**: `ls tests/tsim_facts/*.json` (should show 10 files)

**2. "IP not configured on any router" Error**
```bash
Error: Source IP 1.2.3.4 is not configured on any router or in any directly connected network
```
- **Solution**: Use IP addresses from the test topology (10.1.x.x, 10.2.x.x, 10.3.x.x, 10.100.1.x)
- **Check**: See `docs/NETWORK_TOPOLOGY.md` for complete IP address listing

**3. Invalid IP Address Error**
```bash
Error: Invalid IP address - '999.999.999.999' does not appear to be an IPv4 or IPv6 address
```
- **Solution**: Use valid IP address format (IPv4 or IPv6)
- **Example**: `10.1.1.1` instead of `999.999.999.999`

### Debugging Tips

1. **Use Verbose Mode**: Add `-v` flag to see router loading information
2. **Check JSON Files**: Ensure routing data files are valid JSON
3. **Verify IP Addresses**: Use IPs that appear in your routing tables
4. **Test with Known Good IPs**: Start with router interface IPs

### Validation Commands

```bash
# Validate JSON files
for file in tests/tsim_facts/*.json; do
    echo "Checking $file"
    python3 -m json.tool "$file" > /dev/null && echo "✓ Valid" || echo "✗ Invalid"
done

# List available router IPs
python3 -c "
import json, glob
for f in glob.glob('tests/tsim_facts/*.json'):
    with open(f) as file:
        data = json.load(file)
        if 'routing_table' in data:
            routes = data['routing_table']
            print(f'{f}:')
            for r in routes:
                if 'prefsrc' in r:
                    print(f'  {r[\"prefsrc\"]} on {r.get(\"dev\", \"unknown\")}')
"

# Quick test with known good IPs
make trace ARGS="-s 10.1.1.1 -d 10.2.1.1"
```

## 🤝 Contributing

We welcome contributions to improve the traceroute simulator!

### Development Setup

1. **Fork and clone the repository**
2. **Create a feature branch**: `git checkout -b feature-name`
3. **Make changes and add tests**
4. **Run the test suite**: `python3 test_traceroute_simulator.py`
5. **Submit a pull request**

### Code Standards

- **Python Style**: Follow PEP 8 guidelines
- **Comments**: Add comprehensive docstrings and inline comments
- **Testing**: Include tests for new functionality
- **Documentation**: Update README for new features

### Project Structure

```
traceroute-simulator/
├── tsimsh                       # Interactive shell entry point
├── tsim-completion.bash         # Bash completion for tsimsh
├── src/                         # Core application code
│   ├── core/                    # Main simulator components
│   │   ├── traceroute_simulator.py  # Main application
│   │   ├── route_formatter.py       # Output formatting
│   │   ├── reverse_path_tracer.py   # Reverse path tracing
│   │   ├── packet_tracer.py         # Packet path tracing
│   │   ├── config_loader.py         # Configuration management
│   │   └── models.py                # Data models
│   ├── shell/                   # Interactive shell implementation
│   │   ├── tsim_shell.py            # Main shell class
│   │   ├── commands/                # Command handlers (trace, network, service, host, facts)
│   │   ├── completers/              # Tab completion system
│   │   └── utils/                   # Shell utilities (variables, scripting)
│   ├── analyzers/               # Analysis tools
│   │   ├── iptables_forward_analyzer.py  # Packet forwarding analysis
│   │   └── iptables_log_processor.py     # Iptables log processing
│   ├── executors/               # External command executors
│   │   ├── mtr_executor.py          # MTR execution and SSH management
│   │   └── enhanced_mtr_executor.py # Enhanced MTR with options
│   ├── simulators/              # Network simulation tools
│   │   ├── network_namespace_setup.py    # Namespace creation
│   │   ├── network_namespace_status.py   # Status monitoring
│   │   ├── network_namespace_tester.py   # Connectivity testing
│   │   ├── service_manager.py            # TCP/UDP service management
│   │   └── host_namespace_setup.py       # Dynamic host management
│   ├── scripts/                 # Automation scripts
│   │   ├── network_reachability_test.sh  # Main test orchestration
│   │   ├── analyze_packet_counts.py      # Firewall analysis
│   │   └── visualize_reachability.py     # PDF report generation
│   └── utils/                   # Utility scripts
│       ├── update_tsim_facts.py     # Facts file updater
│       └── verify_network_setup.py  # Network setup verification
├── web/                         # Web interface
│   ├── cgi-bin/                     # CGI scripts and libraries
│   │   ├── main.py                  # Main form handler
│   │   ├── lib/                     # Session, auth, executor modules
│   │   └── generate_pdf.sh          # PDF generation wrapper
│   ├── htdocs/                      # Static web content
│   │   ├── form.html                # Reachability test form
│   │   └── login.html               # Authentication page
│   ├── conf/                        # Configuration templates
│   └── scripts/                     # Web service scripts
├── ansible/                     # Data collection automation
│   ├── get_tsim_facts.yml           # Unified facts collection playbook
│   ├── get_facts.sh                 # Facts collection script
│   ├── process_facts.py             # Facts processor
│   └── ip_json_wrapper.py           # IP JSON compatibility wrapper
├── tests/                       # Comprehensive test suite
│   ├── tsim_facts/                  # Test routing data (10 routers)
│   ├── test_*.py                    # 228 unit and integration tests
│   └── tsimsh/                      # Shell script examples
├── docs/                        # Documentation and visualization
│   ├── NETWORK_TOPOLOGY.md          # Detailed network documentation
│   ├── TSIM_SHELL.md                # Interactive shell documentation
│   ├── network_topology_diagram.py  # Network visualization generator
│   ├── network_topology.png/pdf     # Network diagrams
│   └── report_example.pdf           # Example PDF report
├── scripts/                     # Enhancement scripts
│   ├── enhance_iptables_rules.py    # Iptables rules enhancement
│   ├── enhance_ipset_configurations.py # Ipset configuration enhancement
│   └── netlog                       # Network logging utility
├── etc/                         # System configuration
│   └── sudoers.d/                   # Namespace permissions
├── Makefile                     # Comprehensive build system
├── pyproject.toml               # Python package configuration
├── requirements.txt             # Python dependencies
├── traceroute_simulator.yaml    # Example configuration
├── CLAUDE.md                    # Development guidelines
├── LICENSE                      # MIT License
└── README.md                    # This documentation
```

## 🏗️ Architecture Overview

The Traceroute Simulator is a comprehensive network analysis toolkit composed of several integrated functional blocks:

**Core Simulation Engine**: The main traceroute simulator (`src/core/`) implements Linux routing logic with longest prefix matching, policy-based routing, and multi-interface scenarios. It reads unified JSON facts files containing routing tables, policy rules, iptables configurations, and ipset data to simulate packet paths through complex network topologies.

**Interactive Shell (tsimsh)**: A full-featured command-line interface (`src/shell/`) built on cmd2 that provides organized command groups (trace, network, service, host, facts) with tab completion, persistent history, variable management, and scripting support. Commands execute network simulations, manage services, and perform comprehensive testing.

**Linux Namespace Simulation**: The simulators module (`src/simulators/`) creates real Linux network namespaces that mirror production router configurations. This enables actual packet testing with real networking components, TCP/UDP services, dynamic host management, and comprehensive connectivity validation beyond pure simulation.

**Network Analysis Tools**: The analyzers module (`src/analyzers/`) provides iptables forward chain analysis with ipset integration, packet count tracking, and firewall rule evaluation. It determines which rules match specific traffic patterns and identifies blocking points in complex firewall configurations.

**Data Collection System**: The Ansible-based collection framework (`ansible/`) executes commands on remote routers, collects routing/firewall data, and processes it into unified JSON facts. The IP JSON wrapper provides compatibility for systems without native JSON support, ensuring broad Linux distribution coverage.

**Web Interface**: A complete web application (`web/`) with authentication, session management, and network reachability testing forms. It orchestrates tests via the reachability script, generates comprehensive PDF reports with NetworkX visualizations, and provides shareable links for results.

**Testing & Automation**: The project includes 228 comprehensive tests covering all functionality, Make targets for common operations, enhancement scripts for processing routing data, and extensive documentation with examples. The test network spans 10 routers across 3 locations with realistic enterprise topology.

## 🔗 Technologies and References

**Core Technologies**:
- **Python 3.7+**: Main implementation language with type hints
- **NetworkX**: Graph algorithms and network visualization ([networkx.org](https://networkx.org/))
- **Matplotlib**: PDF report generation and plotting ([matplotlib.org](https://matplotlib.org/))
- **cmd2**: Interactive shell framework ([cmd2.readthedocs.io](https://cmd2.readthedocs.io/))
- **Ansible**: Remote data collection automation ([ansible.com](https://www.ansible.com/))
- **PyYAML**: Configuration file support ([pyyaml.org](https://pyyaml.org/))
- **PyHyphen**: Enhanced text wrapping in reports ([pyphen.org](https://pyphen.org/))

**Linux Networking**:
- **iproute2**: Core routing commands (`ip route`, `ip rule`, `ip addr`)
- **Linux Namespaces**: Network isolation and simulation
- **iptables/netfilter**: Firewall rule processing
- **ipset**: Efficient IP set matching
- **MTR (My TraceRoute)**: Network diagnostic tool ([github.com/traviscross/mtr](https://github.com/traviscross/mtr))
- **socat**: Multi-purpose network relay for services

**Related Projects**:
- **WireGuard**: VPN tunnel support ([wireguard.com](https://www.wireguard.com/))
- **Apache HTTP Server**: Web interface hosting with CGI
- **Bash**: Shell scripting for automation
- **Make**: Build automation and task management

For detailed documentation on specific components, see `docs/TSIM_SHELL.md` for the interactive shell, `docs/NETWORK_TOPOLOGY.md` for the test network design, and `CLAUDE.md` for development guidelines.

---

## 📞 Support

If you encounter issues or have questions:

1. **Check the [Troubleshooting](#troubleshooting) section**
2. **Review existing issues in the repository**
3. **Run the test suite to verify your setup**
4. **Create a detailed issue report with example commands and output**

---

**Happy Network Analysis! 🚀**