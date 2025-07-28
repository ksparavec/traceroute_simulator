# Traceroute Simulator Shell (tsimsh)

The Traceroute Simulator Shell (`tsimsh`) is an interactive command-line interface that provides a comprehensive environment for network simulation, analysis, and management. Built on top of the `cmd2` framework, it offers advanced features including command completion, persistent history, and organized command structure.

## 🚀 Quick Start

### Launching the Shell

```bash
# Launch interactive shell
./tsimsh

# Or with specific facts directory
TRACEROUTE_SIMULATOR_FACTS=custom_facts ./tsimsh
```

The shell provides an interactive prompt with a welcome message and command completion:

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                        Traceroute Simulator Shell v1.0                              ║
║                    Interactive Network Simulation Interface                         ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

Type 'help' for available commands, 'help <command>' for specific command help.
Press Tab for command completion.
tsimsh> 
```

### Basic Navigation

- **Tab Completion**: Press Tab for command completion and argument suggestions
- **Command History**: Use Up/Down arrows to navigate command history
- **Help System**: Type `help` for command overview, `help <command>` for specific help
- **Exit**: Type `exit`, `quit`, or press Ctrl+D to exit

## 📋 Command Structure

The shell organizes commands into logical groups with subcommands:

### Command Categories

1. **MTR Commands** (`mtr`): Traceroute simulation and analysis
2. **Network Commands** (`network`): Namespace simulation management  
3. **Service Commands** (`service`): TCP/UDP service management
4. **Host Commands** (`host`): Dynamic host creation and management
5. **Facts Commands** (`facts`): Data collection and processing

### Command Syntax

```bash
tsimsh> <command> <subcommand> [options] [arguments]
```

Examples:
```bash
tsimsh> mtr route -s 10.1.1.1 -d 10.2.1.1
tsimsh> network setup --verbose
tsimsh> service start --ip 10.1.1.1 --port 8080
```

## 📋 Standardized Command Options

All commands follow a consistent option format for common parameters:

| Option | Short | Long | Description | Commands |
|--------|-------|------|-------------|----------|
| Source IP | `-s` | `--source` | Source IP address | `host`, `mtr`, `ping`, `service`, `trace` |
| Destination IP | `-d` | `--destination` | Destination IP address | `host`, `mtr`, `ping`, `service`, `trace` |
| Protocol | `-p` | `--protocol` | Network protocol (tcp/udp/icmp) | `host`, `mtr`, `ping`, `service`, `trace` |
| JSON Output | `-j` | `--json` | Output in JSON format | `host`, `mtr`, `ping`, `service`, `trace` |
| Verbose | `-v` | `--verbose` | Increase verbosity (can repeat) | `host`, `mtr`, `ping`, `service`, `trace` |
| Force | `-f` | `--force` | Force operation without prompts | `host`, `service` |

## 🔄 MTR Commands

The `mtr` command group provides traceroute simulation and analysis capabilities.

### Available Subcommands

#### `mtr route` - Basic Traceroute Simulation

```bash
# Basic traceroute between two IPs
tsimsh> mtr route -s 10.1.1.1 -d 10.2.1.1

# Verbose output with detailed information
tsimsh> mtr route -s 10.1.1.1 -d 10.2.1.1 -v

# JSON output for programmatic processing
tsimsh> mtr route -s 10.1.1.1 -d 10.2.1.1 -j

# Quiet mode (exit code only)
tsimsh> mtr route -s 10.1.1.1 -d 10.2.1.1 -q

# Simulation only (no MTR fallback)
tsimsh> mtr route -s 10.1.1.1 -d 10.2.1.1 --no-mtr
```

#### `mtr analyze` - Iptables Forward Analysis

```bash
# Analyze packet forwarding through specific router
tsimsh> mtr analyze --router hq-gw -s 10.1.1.1 -d 10.2.1.1

# Analyze with specific ports and protocol
tsimsh> mtr analyze --router hq-gw -s 10.1.1.1 -sp 80,443 -d 10.2.1.1 -dp 8080 -p tcp

# Verbose analysis with rule details
tsimsh> mtr analyze --router hq-gw -s 10.1.1.0/24 -d 10.2.1.0/24 -vv
```

#### `mtr real` - Real MTR Execution

```bash
# Execute real MTR from specified router
tsimsh> mtr real --router hq-gw -d 8.8.8.8

# MTR with custom options
tsimsh> mtr real --router hq-gw -d 8.8.8.8 --count 5 --timeout 10
```

#### `mtr reverse` - Reverse Path Tracing

```bash
# Reverse path tracing with auto-detected controller
tsimsh> mtr reverse -s 10.1.1.1 -d 8.8.8.8

# Reverse path with custom controller IP
tsimsh> mtr reverse -s 10.1.1.1 -d 8.8.8.8 --controller-ip 192.168.1.100

# Verbose reverse tracing
tsimsh> mtr reverse -s 10.1.1.1 -d 8.8.8.8 -v
```

### MTR Command Options

| Option | Description |
|--------|-------------|
| `-s, --source` | Source IP address (required) |
| `-d, --destination` | Destination IP address (required) |
| `--router` | Router name for analysis or execution |
| `-v, --verbose` | Enable verbose output |
| `-q, --quiet` | Quiet mode (exit codes only) |
| `-j, --json` | JSON output format |
| `--no-mtr` | Disable MTR fallback |
| `--controller-ip` | Ansible controller IP for reverse tracing |
| `-sp, --source-port` | Source port(s) for analysis |
| `-dp, --dest-port` | Destination port(s) for analysis |
| `-p, --protocol` | Protocol (tcp, udp, icmp, all) |

## 🌐 Network Commands

The `network` command group manages the Linux namespace simulation infrastructure.

### Available Subcommands

#### `network setup` - Initialize Network Simulation

```bash
# Setup complete network simulation
tsimsh> network setup

# Setup with verbose output
tsimsh> network setup --verbose

# Setup with custom facts directory
tsimsh> network setup --facts-dir custom_facts
```

#### `network status` - Show Network Status

```bash
# Show status of all namespaces
tsimsh> network status all summary

# Show specific router interfaces
tsimsh> network status hq-gw interfaces

# Show routing table for specific router
tsimsh> network status br-core routes

# Show iptables rules for router
tsimsh> network status dc-srv rules

# Show complete configuration
tsimsh> network status hq-dmz all
```

#### `network test` - Test Network Connectivity

```bash
# ICMP ping test
tsimsh> network test -s 10.1.1.1 -d 10.2.1.1 --test-type ping

# MTR traceroute test
tsimsh> network test -s 10.1.1.1 -d 8.8.8.8 --test-type mtr

# Both ping and MTR
tsimsh> network test -s 10.1.1.1 -d 10.2.1.1 --test-type both

# Verbose testing
tsimsh> network test -s 10.1.1.1 -d 10.2.1.1 --test-type ping -v
```

#### `network clean` - Cleanup Network Simulation

```bash
# Clean up all network namespaces
tsimsh> network clean

# Clean with verbose output
tsimsh> network clean -v

# Force cleanup (ignore errors)
tsimsh> network clean -f
```

### Network Command Options

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Enable verbose output |
| `--facts-dir` | Custom facts directory |
| `-s, --source` | Source IP for testing |
| `-d, --destination` | Destination IP for testing |
| `--test-type` | Test type (ping, mtr, both) |
| `-f, --force` | Force operation (ignore errors) |

## 🔌 Network Testing Commands

### `ping` - Test Network Connectivity

```bash
# Basic ping test
tsimsh> ping -s 10.1.1.1 -d 10.2.1.1

# Verbose ping with detailed output
tsimsh> ping -s 10.1.1.1 -d 10.2.1.1 -v

# Very verbose output
tsimsh> ping -s 10.1.1.1 -d 10.2.1.1 -vv
```

### `mtr` - Interactive Traceroute

```bash
# Basic MTR test
tsimsh> mtr -s 10.1.1.1 -d 10.2.1.1

# Verbose MTR with detailed output
tsimsh> mtr -s 10.1.1.1 -d 10.2.1.1 -v

# Very verbose output
tsimsh> mtr -s 10.1.1.1 -d 10.2.1.1 -vv
```

### `trace` - Reverse Path Tracing

```bash
# Basic reverse path trace
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1

# JSON output
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1 -j

# Verbose output
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1 -v

# With custom controller IP
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1 --controller-ip 192.168.1.100
```

## 🔧 Service Commands

The `service` command group manages TCP/UDP services in the network simulation.

### Available Subcommands

#### `service start` - Start Network Services

```bash
# Start TCP service
tsimsh> service start --ip 10.1.1.1 --port 8080

# Start UDP service with name
tsimsh> service start --ip 10.2.1.1 --port 53 -p udp --name dns

# Start service with verbose output
tsimsh> service start --ip 10.1.1.1 --port 80 -v
```

#### `service stop` - Stop Network Services

```bash
# Stop specific service
tsimsh> service stop --ip 10.1.1.1 --port 8080

# Stop service with verbose output
tsimsh> service stop --ip 10.1.1.1 --port 8080 -v
```

#### `service list` - List Running Services

```bash
# List all services
tsimsh> service list

# List services in JSON format
tsimsh> service list -j

# List services with verbose output
tsimsh> service list -v
```

#### `service test` - Test Service Connectivity

```bash
# Test TCP service connectivity
tsimsh> service test -s 10.1.1.1 -d 10.2.1.1:8080

# Test UDP service with message
tsimsh> service test -s 10.1.1.1 -d 10.2.1.1:53 -p udp -m "Test query"

# Test with verbose output
tsimsh> service test -s 10.1.1.1 -d 10.2.1.1:8080 -v

# Test with JSON output
tsimsh> service test -s 10.1.1.1 -d 10.2.1.1:8080 -j
```

#### `service clean` - Stop All Services

```bash
# Stop all running services (prompts for confirmation)
tsimsh> service clean

# Force clean without confirmation
tsimsh> service clean -f

# Clean with verbose output
tsimsh> service clean -v
```

### Service Command Options

| Option | Description |
|--------|-------------|
| `--ip` | IP address for service |
| `--port` | Port number |
| `-p, --protocol` | Protocol (tcp, udp) |
| `--name` | Service name |
| `-s, --source` | Source IP for testing |
| `-d, --destination` | Destination IP:port for testing |
| `-m, --message` | Test message for UDP |
| `-j, --json` | JSON output format |
| `-v, --verbose` | Enable verbose output |
| `-f, --force` | Force operation without confirmation |

## 🏠 Host Commands

The `host` command group manages dynamic host creation and removal in the network simulation.

### Available Subcommands

#### `host add` - Add Dynamic Host

```bash
# Add host with primary IP
tsimsh> host add --name web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw

# Add host with secondary IPs
tsimsh> host add --name db1 --primary-ip 10.3.20.100/24 --connect-to dc-srv --secondary-ips 192.168.1.1/24

# Add host with verbose output
tsimsh> host add --name app1 --primary-ip 10.2.1.50/24 --connect-to br-gw -v
```

#### `host remove` - Remove Dynamic Host

```bash
# Remove specific host (prompts for confirmation)
tsimsh> host remove --name web1

# Force remove without confirmation
tsimsh> host remove --name web1 -f

# Remove with verbose output
tsimsh> host remove --name web1 -v
```

#### `host list` - List Dynamic Hosts

```bash
# List all hosts
tsimsh> host list

# List hosts in JSON format
tsimsh> host list -j

# List with verbose output
tsimsh> host list -v
```

#### `host clean` - Remove All Hosts

```bash
# Remove all dynamic hosts (prompts for confirmation)
tsimsh> host clean

# Force clean without confirmation
tsimsh> host clean -f

# Clean with verbose output
tsimsh> host clean -v
```

### Host Command Options

| Option | Description |
|--------|-------------|
| `--name` | Host name |
| `--primary-ip` | Primary IP with CIDR |
| `--connect-to` | Router to connect to |
| `--secondary-ips` | Additional IP addresses |
| `-f, --force` | Force operation without confirmation |
| `-j, --json` | JSON output format |
| `-v, --verbose` | Enable verbose output |

## 📊 Facts Commands

The `facts` command group handles data collection and processing operations.

### Available Subcommands

#### `facts process` - Process Raw Facts

```bash
# Process single facts file
tsimsh> facts process input.txt output.json

# Process with validation
tsimsh> facts process input.txt output.json --validate

# Process with verbose output
tsimsh> facts process input.txt output.json -v
```

#### `facts validate` - Validate Facts Data

```bash
# Validate facts directory
tsimsh> facts validate

# Validate specific file
tsimsh> facts validate --file router.json

# Validate with detailed output
tsimsh> facts validate -v
```

#### `facts extract` - Extract Interface Information

```bash
# Extract all interfaces
tsimsh> facts extract router.json

# Extract specific interface
tsimsh> facts extract router.json --interface eth0

# Extract IPs only
tsimsh> facts extract router.json --ips-only --family inet

# Extract as JSON
tsimsh> facts extract router.json -j
```

### Facts Command Options

| Option | Description |
|--------|-------------|
| `--validate` | Enable validation |
| `--file` | Specific file to process |
| `--interface` | Specific interface |
| `--ips-only` | Extract IP addresses only |
| `--family` | IP family (inet, inet6) |
| `-j, --json` | JSON output format |
| `-v, --verbose` | Enable verbose output |

## 🔧 Advanced Features

### Tab Completion

The shell provides intelligent tab completion for:

- **Command Names**: Complete command and subcommand names
- **IP Addresses**: Complete with known router and network IPs
- **Router Names**: Complete with configured router names
- **File Paths**: Complete file and directory paths
- **Options**: Complete command options and flags

Examples:
```bash
tsimsh> mtr <TAB>
route  analyze  real  reverse  help

tsimsh> mtr route -s 10.1.<TAB>
10.1.1.1  10.1.2.1  10.1.3.1  10.1.10.1  10.1.11.1

tsimsh> network status <TAB>
all  hq-gw  hq-core  br-gw  dc-gw
```

### Persistent History

The shell maintains persistent command history across sessions:

- **History File**: `~/.tsimsh_history.json`
- **Navigation**: Use Up/Down arrows to browse history
- **Search**: Use Ctrl+R for reverse history search
- **Session Persistence**: History survives shell restarts

### Context Mode

Some commands support context mode for streamlined operations:

```bash
# Enter network context
tsimsh> network
network> setup -v
network> status all summary
network> test -s 10.1.1.1 -d 10.2.1.1 --test-type ping
network> exit

# Enter service context
tsimsh> service
service> start --ip 10.1.1.1 --port 8080
service> list -j
service> test -s 10.1.1.1 -d 10.2.1.1:8080 -v
service> exit
```

### Error Handling

The shell provides comprehensive error handling:

- **Input Validation**: Validates IP addresses, ports, and options
- **Command Errors**: Clear error messages for invalid commands
- **Exit Codes**: Consistent exit codes for automation
- **Help Integration**: Automatic help display for invalid syntax

## 🤖 Scripting with tsimsh

The shell supports automation and scripting through several methods:

### Command-Line Execution

```bash
# Execute single command
echo "mtr route -s 10.1.1.1 -d 10.2.1.1" | ./tsimsh

# Execute command file
./tsimsh < commands.txt
```

### Script Files

Create script files with shell commands:

```bash
# network_setup.tsim
network setup -v
network status all summary
service start --ip 10.1.1.1 --port 8080
service start --ip 10.2.1.1 --port 80 -p tcp
host add --name web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw

# Execute script
./tsimsh < network_setup.tsim
```

### Automation Examples

#### Network Validation Script

```bash
#!/bin/bash
# validate_network.sh

TSIMSH="./tsimsh"

# Test key network paths
echo "Testing HQ to Branch connectivity..."
echo "mtr route -s 10.1.1.1 -d 10.2.1.1 -q" | $TSIMSH
if [ $? -eq 0 ]; then
    echo "✓ HQ to Branch: OK"
else
    echo "✗ HQ to Branch: FAILED"
fi

echo "Testing internet connectivity..."
echo "mtr route -s 10.1.1.1 -d 8.8.8.8 -q" | $TSIMSH
if [ $? -eq 0 ]; then
    echo "✓ Internet access: OK"
else
    echo "✗ Internet access: FAILED"
fi
```

#### Service Deployment Script

```bash
#!/bin/bash
# deploy_services.sh

SERVICES=(
    "10.1.1.1:80:tcp:web"
    "10.1.1.1:443:tcp:web-ssl"
    "10.2.1.1:53:udp:dns"
    "10.3.1.1:3306:tcp:mysql"
)

for service in "${SERVICES[@]}"; do
    IFS=':' read -r ip port proto name <<< "$service"
    echo "service start --ip $ip --port $port -p $proto --name $name" | ./tsimsh
done

echo "service list -j" | ./tsimsh
```

### Configuration Integration

The shell respects environment variables and configuration files:

```bash
# Set facts directory
export TRACEROUTE_SIMULATOR_FACTS=production_facts
./tsimsh

# Use configuration file
export TRACEROUTE_SIMULATOR_CONF=production.yaml
./tsimsh
```

## 🔍 Troubleshooting

### Common Issues

#### Shell Won't Start

```bash
Error: cmd2 is required. Install with: pip install cmd2
```

**Solution**: Install required dependencies:
```bash
pip install cmd2 colorama tabulate pyyaml
```

#### Command Not Found

```bash
✗ Unknown command: 'xyz'
```

**Solution**: Use `help` to see available commands or check for typos.

#### Permission Denied

```bash
Error: Permission denied accessing network namespaces
```

**Solution**: Some commands require sudo privileges:
```bash
sudo ./tsimsh
```

#### Facts Directory Not Found

```bash
Error: Facts directory not found: /path/to/facts
```

**Solution**: Set correct facts directory:
```bash
export TRACEROUTE_SIMULATOR_FACTS=tests/tsim_facts
./tsimsh
```

### Debug Mode

Enable verbose output for troubleshooting:

```bash
tsimsh> mtr route -s 10.1.1.1 -d 10.2.1.1 -v
tsimsh> network setup -v
tsimsh> service start --ip 10.1.1.1 --port 8080 -v
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1 -vv
```

### Getting Help

- **General Help**: `help`
- **Command Help**: `help <command>`
- **Subcommand Help**: `<command> help`
- **Option Help**: `<command> <subcommand> --help`

## 🚀 Best Practices

### Efficient Workflow

1. **Set Environment**: Configure facts directory once
2. **Use Tab Completion**: Leverage completion for faster input
3. **Context Mode**: Use context mode for repetitive operations
4. **Script Automation**: Create scripts for common workflows
5. **History Usage**: Use command history for repeated operations

### Network Management

1. **Setup First**: Always run `network setup` before testing
2. **Check Status**: Use `network status` to verify setup
3. **Test Incrementally**: Test basic connectivity before complex scenarios
4. **Clean Resources**: Use `network clean` to reset environment
5. **Monitor Services**: Use `service list` to track running services

### Performance Optimization

1. **Quiet Mode**: Use `-q` for automation scripts
2. **JSON Output**: Use `-j` for programmatic processing
3. **Targeted Testing**: Test specific components instead of full setup
4. **Resource Cleanup**: Clean up unused hosts and services
5. **Batch Operations**: Group related commands in scripts

The Traceroute Simulator Shell provides a comprehensive, user-friendly interface for network simulation and analysis. With its rich command set, intelligent completion, and automation capabilities, it serves as a powerful tool for network engineers, administrators, and developers working with complex network topologies.