# CLAUDE\_CLEAN.md

This file provides guidance for Claude Code (claude.ai/code) when working with code in this repository, focusing on usage, automation, and development standards.

## Build and Automation Commands

### Automated Make Targets (Recommended)

- **Check dependencies**: `make check-deps` (validates all Python modules)
- **Clean artifacts**: `make clean` (removes cache files while preserving routing data)
- **Collect routing data**: `make fetch-routing-data OUTPUT_DIR=data INVENTORY_FILE=hosts.ini`
- **Show help**: `make help` (displays all available targets)

### Linux Namespace Network Simulation

This project includes a Linux namespace-based network simulation system that creates real network infrastructure:

#### **Namespace Network Commands**

- **Setup simulation**: `sudo make netsetup` (creates router namespaces with full connectivity)
- **Show network status**: `sudo make netshow ROUTER=hq-gw FUNC=interfaces`
- **Cleanup simulation**: `sudo make netclean`

#### **Network Status Viewing**

- **Show all routers summary**: `sudo make netshow ROUTER=all FUNC=summary`
- **Show interface configuration**: `sudo make netshow ROUTER=hq-gw FUNC=interfaces`
- **Show routing table**: `sudo make netshow ROUTER=br-core FUNC=routes`
- **Show policy rules**: `sudo make netshow ROUTER=dc-srv FUNC=rules`
- **Show complete configuration**: `sudo make netshow ROUTER=hq-dmz FUNC=all`

#### **Service Management Commands**

- **Start TCP service**: `sudo make svcstart ARGS='10.1.1.1:8080'`
- **Start UDP service**: `sudo make svcstart ARGS='10.2.1.1:53 -p udp --name dns'`
- **Test service connectivity**: `sudo make svctest ARGS='-s 10.1.1.1 -d 10.2.1.1:8080'`
- **Test UDP with message**: `sudo make svctest ARGS='-s 10.1.1.1 -d 10.2.1.1:53 -p udp -m "Query"'`
- **Stop service**: `sudo make svcstop ARGS='10.1.1.1:8080'`
- **List all services**: `sudo make svclist`
- **List services as JSON**: `sudo make svclist ARGS='-j'`
- **Stop all services**: `sudo make svcclean`

#### **Host Management Commands**

- **Add host to network**: `sudo make hostadd ARGS='--host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw'`
- **Add host with secondary IPs**: `sudo make hostadd ARGS='--host db1 --primary-ip 10.3.20.100/24 --connect-to dc-srv --secondary-ips 192.168.1.1/24'`
- **List all hosts**: `sudo make hostlist`
- **Remove specific host**: `sudo make hostdel ARGS='--host web1 --remove'`
- **Remove all hosts**: `sudo make hostclean`
- **Clean routers and hosts**: `sudo make netnsclean`

### Data Collection and Validation

#### **Production Data Collection**

- **Collect with Ansible**: `make fetch-routing-data OUTPUT_DIR=custom_facts INVENTORY_FILE=inventory.ini`
- **Environment-based collection**: `TRACEROUTE_SIMULATOR_FACTS=custom_facts make fetch-routing-data INVENTORY_FILE=inventory.ini`

#### **Facts Processing**

- **Process all raw facts to JSON**: `python3 -B ansible/process_all_facts.py --verbose --create-dirs`
- **Process raw facts via Ansible**: `ansible-playbook -i inventory.ini get_tsim_facts.yml --tags process`
- **Process single raw facts file**: `python3 -B ansible/process_facts.py raw_facts.txt output.json --verbose`

#### **Interface Information Extraction**

- **Extract all interface information**: `python3 -B ansible/extract_interfaces.py router.json`
- **Extract specific interface**: `python3 -B ansible/extract_interfaces.py router.json --interface eth0`
- **Extract IP addresses only**: `python3 -B ansible/extract_interfaces.py router.json --ips-only --family inet`
- **Extract interfaces as JSON**: `python3 -B ansible/extract_interfaces.py router.json --json`

#### **Utility Scripts**

- **Update interface data in JSON facts**: `python3 -B src/utils/update_tsim_facts.py`
- **Verify namespace setup**: `sudo python3 -B src/utils/verify_network_setup.py`

## Router Metadata System

The traceroute simulator includes a metadata system that classifies routers based on their network role, capabilities, and properties. This enables advanced features like Linux/non-Linux router differentiation, gateway internet connectivity, and automatic Ansible controller detection.

### Metadata File Structure

Each router can have an optional `*_metadata.json` file with properties:

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

- \`\` (boolean): Whether the router runs Linux OS
- \`\` (string): Router type
- \`\` (string): Physical/logical location
- \`\` (string): Network role
- \`\` (string): Router vendor/platform
- \`\` (boolean): Manageable via automation tools
- \`\` (boolean): Is this the Ansible controller?

### Default Metadata Values

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

### Router Classification

- **Linux Routers**: MTR-capable (e.g., `hq-core`, `hq-dmz`, `hq-lab`, `br-wifi`, `dc-gw`)
- **Non-Linux Routers**: Simulation-only (e.g., `hq-gw`, `br-gw`, `br-core`, `dc-core`, `dc-srv`)
- **Gateway Routers**: Internet-capable (e.g., `hq-gw`, `br-gw`, `dc-gw`)
- **Ansible Controller**: e.g., `hq-dmz` (10.1.2.3)

### Metadata API Methods

```python
router.is_linux()              # Boolean: Linux OS
router.get_type()               # String: gateway, core, access, none
router.get_location()           # String: hq, branch, datacenter, none
router.get_role()               # String: distribution, server, wifi, etc.
router.get_vendor()             # String: vendor information
router.is_manageable()          # Boolean: automation capability
router.is_ansible_controller()  # Boolean: controller status
```

## Code Style Guidelines

### Python Code

- **Indentation**: 4-space indentation
- **Naming**: snake\_case for functions/variables, PascalCase for classes
- **Line length**: Prefer 88 characters max, hard limit 100
- **Imports**: Standard library first, then third-party, then local imports
- **Variable naming**: Use descriptive names

### Documentation Standards

- **Docstrings**: Triple double-quotes (`"""`) with comprehensive descriptions
- **Function docstrings**: Args, Returns, Raises
- **Class docstrings**: Purpose, key attributes, usage examples
- **Module docstrings**: Overview, main functionality, examples
- **Inline comments**: Explain complex logic, algorithms, and non-obvious code
- **Code comments**: For any non-trivial code sections

### Documentation Requirements

- **README.md**: User documentation with examples
- **Code comments**: Extensive inline documentation
- **Type hints**: Use typing module for function signatures
- **Error handling**: Document expected exceptions and error conditions

### Comment Guidelines

- **Purpose**: Explain WHY, not just what code does
- **Algorithms**: Document approach and key steps
- **Complex logic**: Break down multi-step operations
- **Edge cases**: Note special handling and corner cases
- **External dependencies**: Document assumptions about input data
- **Performance considerations**: Note optimization decisions

## Project Structure Standards

- **Separation of concerns**: Routing logic and data collection separate
- **Modularity**: Reusable and extensible design
- **Configuration**: External configuration files where appropriate
- **Data format**: Consistent JSON structure for routing data
- **Backward compatibility**: Preserve interfaces when adding features

### Directory Organization

```
traceroute_simulator/
├── src/                    # Core application code
│   ├── core/               # Main simulator components
│   ├── analyzers/          # Analysis tools  
│   ├── executors/          # External command executors
│   ├── simulators/         # Network simulation tools
│   └── utils/              # Utility scripts for maintenance
├── Makefile                # Build system
├── tests/                  # Isolated environment
├── docs/                   # Documentation and visualization
├── ansible/                # Data collection automation
├── CLAUDE.md               # Development guidelines
└── README.md               # User documentation
```

### Development Guidelines

- **Document changes**: Update comments and README.md
- **Validate thoroughly**: Run suite before submitting changes
- **Maintain topology**: Keep network topology realistic and comprehensive

## Current Feature Set

### Core Capabilities

The traceroute simulator provides:

- **Accurate routing simulation**: Uses real routing tables and policy rules
- **Interface determination**: Incoming/outgoing interface tracking
- **Professional visualization**: High-quality network topology diagrams
- **Command-line interface**: Required `-s`/`--source` and `-d`/`--destination` flags
- **Multiple output formats**: Text, JSON, verbose modes
- **Enhanced error handling**: User-friendly messages, progressive verbosity
- **System namespace protection**: Filtering of non-user namespaces
- **Service management**: TCP/UDP services, multi-client support
- **Dynamic host management**: Add/remove hosts to simulation

## Advanced Features

### MTR Integration

- **Automatic fallback**: Seamlessly transitions to real MTR if simulation can't complete
- **SSH-based execution**: Runs MTR commands on remote Linux routers
- **Linux router filtering**: Shows only Linux routers via reverse DNS lookup
- **Unified output**: Consistent simulation/MTR formatting
- **Timing info**: RTT data for performance analysis
- **Router name consistency**: Displays router names when applicable

### IP JSON Wrapper

- **Transparent replacement**: Drop-in for `ip --json` commands
- **Identical output**: Matches native output
- **Complete subcommand support**: Route, addr, link, rule
- **Automatic detection**: Uses native if available, falls back to parsing
- **Complex parsing**: Handles MAC, VPN, bridge, etc.

### Namespace Simulation

- **Creates real Linux namespaces**
- **Complete infrastructure**: Routing tables, iptables, ipsets, interface config
- **Multi-protocol**: ICMP ping, MTR traceroute
- **Protocol coverage**: TCP, UDP, ICMP
- **Firewall validation**: Verifies rules for allow/block
- **Flexible destinations**: Any destination IP
- **Public IP simulation**: Auto-setup for realistic internet connectivity
- **Metadata-driven gateway detection**
- **MTR path analysis**: Hop-by-hop and blackhole detection
- **Setup/teardown automation**: Complete resource management
- **Status monitoring**: Namespace/interface/routing info
- **Root privilege handling**: Automatic detection with fallback
- **Integration with facts**: Uses consolidated JSON facts

### Build System

- **Dependency validation**
- **Automated build**
- **Data collection**
- **Clean builds**

### Data Collection

- **Live network collection**: Executes script on remote hosts via Ansible
- **Secure script deployment**: Copy → Execute → Remove
- **Selective privilege escalation**: Become root only for execution
- **Minimal dependencies**: Text-only remote execution
- **Controller-side processing**: JSON conversion happens on controller
- **Flexible output**: Configurable via env vars or CLI

### Iptables Forward Analysis

- **Real iptables rules**: Analyzes FORWARD chain rules
- **Ipset integration**: Full support
- **Multi-format input**: CIDR, lists, port ranges
- **Verbose analysis**: Three verbosity levels
- **Automation friendly**: Clear exit codes
- **Live router data**: Uses actual configs

### Project Organization

- **Ansible integration**: All automation in `ansible/`
- **Documentation**: Diagrams and docs
- **Modular design**: Separate modules for routing, MTR, formatting, analysis

### Configuration Management

- **YAML configuration**: File support with precedence
- **Env variables**: Custom config paths
- **Precedence**: CLI > Config file > Defaults
- **Multiple locations**: Config file locations

### Output Features

- **FQDN resolution**
- **Timing info**
- **Router name consistency**
- **Unreachable detection**

### Reverse Path Tracing

- **Bidirectional path discovery**
- **Timing integration**
- **Error detection**
- **Automatic controller detection**

## Development Notes

### Key Implementation Details

- **Tuple format consistency**
- **Timing info**
- **Router name logic**
- **Error handling**

### Key Components

- **Core simulator**: `src/core/traceroute_simulator.py`
- **MTR executor**: `src/executors/mtr_executor.py`
- **Route formatter**: `src/core/route_formatter.py`
- **Reverse tracer**: `src/core/reverse_path_tracer.py`
- **Iptables analyzer**: `src/analyzers/iptables_forward_analyzer.py`
- **Service manager**: `src/simulators/service_manager.py`
- **Service tester**: `src/simulators/service_tester.py`
- **Host manager**: `src/simulators/host_namespace_setup.py`
- **Namespace tester**: `src/simulators/network_namespace_tester.py`
- **Namespace setup**: `src/simulators/network_namespace_setup.py`
- **Namespace status**: `src/simulators/network_namespace_status.py`
- **Exceptions**: `src/core/exceptions.py`
- **Logging**: `src/core/logging.py`
- **Data models**: `src/core/models.py`
- **Facts updater**: `src/utils/update_tsim_facts.py`
- **Setup verifier**: `src/utils/verify_network_setup.py`
- **Facts processor**: `ansible/process_facts.py`
- **Build system**: `Makefile`
- **Data collection**: `ansible/get_tsim_facts.yml`, `ansible/get_facts.sh`
- **IP wrapper**: `ansible/ip_json_wrapper.py`

## Development Memory

- Do not commit anything yourself without asking
- Always run sudo with '-E' argument to pick up environment
- Do not print any informational or summary messages from any command when -j option has been set, unless verbose option has been set too
- Always execute tsimsh from top level directory and pipe script via stdin to it
- Always cat script to stdout and pipe to tsimsh:  'cat script.tsim | ./tsimsh'
- Never use operating system commands to start/stop/kill processes or do anything else related to namespaces and their corresponding objects. ALWAYS use tsimsh commands or make targets instead.
- When creating new python script, set shebang line to: '#!/usr/bin/env -S python3 -B -u'