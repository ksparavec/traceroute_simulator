# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Test Commands

### Automated Make Targets (Recommended)
- **Check dependencies**: `make check-deps` (validates all Python modules with installation hints)
- **Run all tests**: `make test` (comprehensive test suite with environment validation)
- **Clean artifacts**: `make clean` (removes cache files while preserving routing data)
- **Collect routing data**: `make fetch-routing-data OUTPUT_DIR=data INVENTORY_FILE=hosts.ini`
- **Show help**: `make help` (displays all available targets and examples)

### Direct Testing Commands
- **Run comprehensive test suite**: `cd tests && python3 test_traceroute_simulator.py`
- **Test IP JSON wrapper**: `cd tests && python3 test_ip_json_comparison.py`
- **Test MTR integration**: `cd tests && python3 test_mtr_integration.py`
- **Test facts processing and analyzer**: `cd tests && python3 test_comprehensive_facts_processing.py`
- **Test specific functionality**: `python3 traceroute_simulator.py --tsim-facts tests/tsim_facts -s 10.1.1.1 -d 10.2.1.1`
- **Test complex routing**: `python3 traceroute_simulator.py --tsim-facts tests/tsim_facts -s 10.1.10.1 -d 10.3.20.1`
- **Test JSON output**: `python3 traceroute_simulator.py --tsim-facts tests/tsim_facts -j -s 10.100.1.1 -d 10.100.1.3`
- **Test gateway internet access**: `python3 traceroute_simulator.py --tsim-facts tests/tsim_facts -s 10.1.1.1 -d 1.1.1.1` (gateway to Cloudflare DNS)
- **Test multi-hop internet access**: `python3 traceroute_simulator.py --tsim-facts tests/tsim_facts -s 10.1.10.1 -d 8.8.8.8` (internal network to Google DNS)
- **Test MTR fallback**: `python3 traceroute_simulator.py --tsim-facts tests/tsim_facts -s 10.1.1.1 -d 192.168.1.1 -vv` (triggers MTR for unreachable)
- **Test reverse path tracing**: `python3 traceroute_simulator.py --tsim-facts tests/tsim_facts -s 10.1.1.1 -d 192.168.1.1 --reverse-trace -vv` (auto-detects controller IP)
- **Test timing information**: `python3 traceroute_simulator.py --tsim-facts tests/tsim_facts -s 10.1.1.1 -d 8.8.8.8` (shows RTT data)
- **Test YAML configuration**: `TRACEROUTE_SIMULATOR_CONF=tests/test_config.yaml python3 traceroute_simulator.py -s 10.1.1.1 -d 10.2.1.1`
- **Test FQDN resolution**: `python3 traceroute_simulator.py --tsim-facts tests/tsim_facts -s 10.1.1.1 -d 8.8.8.8` (shows dns.google)
- **Test verbose levels**: `python3 traceroute_simulator.py --tsim-facts tests/tsim_facts -s 10.1.1.1 -d 10.2.1.1 -v` (basic), `-vv` (debug), `-vvv` (config)
- **Test metadata loading**: `python3 traceroute_simulator.py --tsim-facts tests/tsim_facts -s 10.1.1.1 -d 10.2.1.1 -vvv` (shows router types)
- **Test iptables analyzer**: `python3 iptables_forward_analyzer.py --router hq-gw --tsim-facts tests/tsim_facts -s 10.1.1.1 -d 10.2.1.1 -p tcp -vv`
- **Generate network topology diagram**: `cd docs && python3 network_topology_diagram.py`

### Data Collection and Validation

#### **Production Data Collection**
- **Collect with Ansible**: `make fetch-routing-data OUTPUT_DIR=custom_facts INVENTORY_FILE=inventory.ini`
- **Environment-based collection**: `TRACEROUTE_SIMULATOR_FACTS=custom_facts make fetch-routing-data INVENTORY_FILE=inventory.ini`

#### **Test Data Collection and Processing**
- **Generate test facts**: `make fetch-routing-data TEST_MODE=true` (converts raw_facts to /tmp/traceroute_test_output)
- **Direct test mode**: `ansible-playbook -i tests/inventory.yml ansible/get_tsim_facts.yml -e test=true`
- **Run comprehensive test suite**: `make test` (auto-generates fresh test facts and runs all tests)

#### **Individual Testing Commands**
- **Process raw facts**: `python3 ansible/process_facts.py tests/raw_facts/router_facts.txt output.json --verbose`
- **Validate facts processing**: `python3 ansible/process_facts.py --validate output.json`
- **Test with generated facts**: `TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output python3 tests/test_comprehensive_facts_processing.py`
- **Test simulator**: `TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output python3 traceroute_simulator.py -s 10.1.1.1 -d 10.2.1.1`
- **Test iptables analyzer**: `TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output python3 iptables_forward_analyzer.py --router hq-gw -s 10.1.1.1 -d 8.8.8.8 -p tcp -vv`

#### **Data Validation**
- **Validate collected JSON**: `python3 -m json.tool /tmp/traceroute_test_output/*.json`
- **Test IP wrapper compatibility**: `python3 ansible/ip_json_wrapper.py route show`
- **Convert legacy data**: `python3 convert_legacy_facts.py tests/routing_facts tests/tsim_facts`

## Test Network Environment

The project includes a comprehensive test network with realistic enterprise topology:
- **10 routers** across 3 locations (HQ, Branch, Data Center)
- **Complex routing scenarios**: Intra-location, inter-location, multi-hop
- **WireGuard VPN mesh**: 10.100.1.0/24 connecting all locations
- **Multiple network segments**: 14 different subnets across all locations
- **Realistic IP addressing**: 10.1.0.0/16 (HQ), 10.2.0.0/16 (Branch), 10.3.0.0/16 (DC)

### Test Data Location
- **Primary test data**: `tests/tsim_facts/` (10 unified JSON files with complete network facts)
- **Router metadata**: `tests/tsim_facts/*_metadata.json` (router classification and properties - optional)
- **Unified facts files**: `tests/tsim_facts/*.json` (complete routing, iptables, and system information)
- **Network documentation**: `docs/NETWORK_TOPOLOGY.md`
- **Network visualization**: `docs/network_topology_diagram.py` (matplotlib-based diagram generator)
- **Generated diagrams**: `docs/network_topology.png` and `docs/network_topology.pdf`
- **Main test suite**: `tests/test_traceroute_simulator.py` (64 test cases with 100% pass rate)
- **IP wrapper tests**: `tests/test_ip_json_comparison.py` (7 test cases validating wrapper compatibility)
- **MTR integration tests**: `tests/test_mtr_integration.py` (8 test cases validating MTR fallback functionality)
- **IP JSON wrapper**: `ansible/ip_json_wrapper.py` (compatibility layer for older Red Hat systems)
- **Iptables analyzer**: `iptables_forward_analyzer.py` (packet forwarding decision analysis)
- **Legacy converter**: `convert_legacy_facts.py` (converts old 3-file format to unified JSON)
- **Build automation**: `Makefile` (comprehensive build system with dependency checking)

### Using Test Data
Always use the tests directory data when developing or testing:
```bash
# Correct usage (note: -s/-d flags are required)
python3 traceroute_simulator.py --tsim-facts tests/tsim_facts -s <source> -d <dest>

# For new features, ensure compatibility with test network topology
```

## Router Metadata System

The traceroute simulator now includes a comprehensive metadata system that classifies routers based on their network role, capabilities, and properties. This enables advanced features like Linux/non-Linux router differentiation, gateway internet connectivity, and automatic Ansible controller detection.

### Metadata File Structure

Each router can have an optional `*_metadata.json` file that defines its properties:

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

- **`linux`** (boolean): Whether the router runs Linux OS (enables MTR execution capability)
- **`type`** (string): Router type - `"gateway"`, `"core"`, `"access"`, or `"none"`
- **`location`** (string): Physical/logical location - `"hq"`, `"branch"`, `"datacenter"`, or `"none"`
- **`role`** (string): Network role - `"gateway"`, `"distribution"`, `"server"`, `"wifi"`, `"dmz"`, etc.
- **`vendor`** (string): Router vendor/platform - `"linux"`, `"cisco"`, `"juniper"`, etc.
- **`manageable`** (boolean): Whether router is manageable via automation tools
- **`ansible_controller`** (boolean): Whether this router serves as the Ansible controller

### Default Metadata Values

When metadata files don't exist, routers use these default values:
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

### Router Classification in Test Network

**Linux Routers** (MTR-capable):
- `hq-core`, `hq-dmz`, `hq-lab` (HQ location)
- `br-wifi` (Branch location)
- `dc-gw` (Data Center location)

**Non-Linux Routers** (simulation-only):
- `hq-gw`, `br-gw`, `br-core` (gateways and core)
- `dc-core`, `dc-srv` (data center infrastructure)

**Gateway Routers** (internet-capable):
- `hq-gw` (203.0.113.10 → Internet)
- `br-gw` (198.51.100.10 → Internet)
- `dc-gw` (192.0.2.10 → Internet)

**Ansible Controller**:
- `hq-dmz` (10.1.2.3) - automatically detected for reverse path tracing

### Enhanced Features Enabled by Metadata

1. **MTR Fallback**: Only executed on Linux routers (`linux: true`)
2. **Gateway Internet Access**: Routers with `type: "gateway"` can reach public IP addresses
3. **Automatic Controller Detection**: Router with `ansible_controller: true` provides controller IP
4. **Network Visualization**: Diagram colors routers based on Linux/non-Linux classification
5. **Realistic Simulation**: Different router types behave according to real-world capabilities

### File Naming Convention

For each router, unified JSON files are used:
- `{router_name}.json` - Complete network facts including routing, rules, iptables, and system information
- `{router_name}_metadata.json` - Router metadata (optional, uses defaults if missing)

**Legacy Format**: The old 3-file format (`*_route.json`, `*_rule.json`, `*_metadata.json`) can be converted using `convert_legacy_facts.py`.

### Metadata API Methods

Router objects provide convenient access to metadata:
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
- **Indentation**: 4-space indentation, no tabs
- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Line length**: Prefer 88 characters max, hard limit 100 characters
- **Imports**: Standard library first, then third-party, then local imports
- **Variable naming**: Use descriptive names that indicate purpose and type

### Documentation Standards
- **Docstrings**: Use triple double-quotes (`"""`) with comprehensive descriptions
- **Function docstrings**: Include Args, Returns, and Raises sections
- **Class docstrings**: Include purpose, key attributes, and usage examples  
- **Module docstrings**: Include overview, main functionality, and examples
- **Inline comments**: Explain complex logic, algorithms, and non-obvious code
- **Code comments**: Add comments for any non-trivial code sections

### Documentation Requirements
- **README.md**: Comprehensive user documentation with examples
- **Code comments**: Extensive inline documentation for maintainability
- **Type hints**: Use typing module for function signatures where beneficial
- **Error handling**: Document expected exceptions and error conditions

### Comment Guidelines
- **Purpose**: Explain WHY, not just what the code does
- **Algorithms**: Document the approach and key steps
- **Complex logic**: Break down multi-step operations
- **Edge cases**: Note special handling and corner cases
- **External dependencies**: Document assumptions about input data
- **Performance considerations**: Note any optimization decisions

### Testing Standards
- **Comprehensive coverage**: 95+ total test cases providing near-complete code coverage
  - **Main simulator tests**: 63 test cases (100% pass rate)
  - **MTR integration tests**: 8 test cases (87.5% pass rate)
  - **IP wrapper tests**: 7 test cases (validation and compatibility)
  - **Facts processing tests**: 18 test cases (100% pass rate) covering shell output parsing and JSON generation
- **Network topology testing**: Tests for intra-location, inter-location, and multi-hop routing
- **Facts processing validation**: Comprehensive testing of raw shell output to structured JSON conversion
- **Iptables analysis testing**: Complete coverage of forward analyzer with complex rulesets, ipsets, multiport scenarios
- **Test documentation**: Comment test purposes and expected outcomes
- **Error testing**: Include tests for all error conditions and edge cases
- **Edge case coverage**: Corrupted JSON, missing files, IPv6 handling, loop detection, ipset parsing
- **Integration tests**: Test real-world scenarios with enterprise network topology
- **Routing misconfiguration testing**: Realistic scenarios simulating network issues
- **Automation friendly**: Support for CI/CD and automated testing
- **Performance validation**: Ensure all tests complete within reasonable time
- **Data integrity**: Validate JSON structure and routing table consistency
- **Facts processing reliability**: 100% success rate for all 10 routers with comprehensive ipset parsing

## Project Structure Standards
- **Separation of concerns**: Keep routing logic, testing, and data collection separate
- **Testing isolation**: All test data and scripts in `tests/` directory
- **Modularity**: Design for reusability and extensibility
- **Configuration**: Use external configuration files where appropriate
- **Data format**: Maintain consistent JSON structure for routing data
- **Backward compatibility**: Preserve existing interfaces when adding features

### Directory Organization
```
traceroute_simulator/
├── traceroute_simulator.py               # Main application
├── mtr_executor.py                       # MTR execution and SSH management
├── route_formatter.py                    # Output formatting for simulation and MTR results
├── reverse_path_tracer.py                # Reverse path tracing functionality
├── iptables_forward_analyzer.py          # Packet forwarding analysis using iptables rules
├── Makefile                              # Build system with dependency checking
├── tests/                                # Complete test environment
│   ├── test_traceroute_simulator.py         # Main test suite (63 cases, 100% pass rate)
│   ├── test_ip_json_comparison.py           # Wrapper validation tests (7 cases)
│   ├── test_mtr_integration.py              # MTR integration tests (8 cases)
│   ├── test_comprehensive_facts_processing.py # Facts processing and analyzer tests (18 cases, 100% pass rate)
│   ├── test_config.yaml                     # Test-specific configuration
│   ├── inventory.yml                        # Test router inventory (10 routers across 3 locations)
│   ├── tsim_facts/                          # Production test routing data (unified JSON files)
│   └── raw_facts/                           # Raw shell output test data (10 router facts files)
├── docs/                                 # Documentation and visualization
│   ├── NETWORK_TOPOLOGY.md                 # Network documentation
│   ├── network_topology_diagram.py         # Professional diagram generator
│   ├── network_topology.png                # High-resolution network diagram
│   └── network_topology.pdf                # Vector network diagram
├── ansible/                              # Data collection automation
│   ├── get_tsim_facts.yml                  # Unified facts collection playbook
│   ├── get_facts.sh                       # Unified facts collection script
│   ├── process_facts.py                   # Facts processing and JSON conversion
│   └── ip_json_wrapper.py                 # IP JSON compatibility wrapper
├── CLAUDE.md                             # Development guidelines
└── README.md                             # User documentation
```

### Development Guidelines
- **Use test data**: Always test with `tests/tsim_facts/` data
- **Update tests**: Add tests for new features using realistic network scenarios
- **Document changes**: Update both code comments and README.md
- **Validate thoroughly**: Run full test suite before submitting changes
- **Maintain topology**: Keep test network topology realistic and comprehensive

## Current Feature Set

### Core Capabilities
The traceroute simulator provides comprehensive network path simulation:
- **Accurate routing simulation**: Uses actual routing tables and policy rules from Linux routers
- **Interface determination**: Proper incoming/outgoing interface tracking based on network topology
- **Professional visualization**: High-quality network topology diagrams with metadata-aware color coding
- **Command-line interface**: Required `-s`/`--source` and `-d`/`--destination` flags for explicit operation
- **Multiple output formats**: Text, JSON, and verbose modes with comprehensive information
- **Robust error handling**: Clear exit codes and error classification for automation integration

### Test Coverage
Comprehensive test suite covering all functionality:
- **95+ total test cases**: 63 main simulator + 8 MTR integration + 7 IP wrapper + 18 facts processing tests
- **100% pass rate**: All critical tests consistently pass with thorough validation
- **Complete coverage**: Intra-location, inter-location, multi-hop routing, error conditions, edge cases
- **Facts processing validation**: Shell output parsing, JSON generation, ipset extraction, iptables analysis
- **Forward analyzer testing**: Complex rulesets, match-set rules, multiport scenarios, protocol variations
- **Automation testing**: All command-line options, output formats, and exit codes validated
- **Integration testing**: End-to-end workflows from raw facts collection to network analysis

## Advanced Features

### MTR Integration
Comprehensive MTR (My TraceRoute) fallback functionality:
- **Automatic fallback**: Seamlessly transitions from simulation to real MTR when simulation cannot complete paths
- **SSH-based execution**: Direct execution of MTR commands on remote Linux routers
- **Linux router filtering**: Shows only Linux routers from inventory using reverse DNS lookup
- **Unified output**: Consistent formatting between simulation and MTR results in text and JSON
- **Timing information**: Includes round-trip time (RTT) data for performance analysis
- **Router name consistency**: Displays actual router names when source IP belongs to router interface

### IP JSON Wrapper
Compatibility tool for legacy systems without native `ip --json` support:
- **Transparent replacement**: Drop-in replacement for `ip --json` commands
- **Identical output**: Produces byte-for-byte identical JSON to native commands
- **Complete subcommand support**: Handles route, addr, link, and rule subcommands
- **Automatic detection**: Uses native JSON when available, falls back to parsing when needed
- **Complex parsing**: Handles MAC addresses, VPN interfaces, network namespaces, bridge masters

### Build System
Comprehensive Makefile for automated development workflows:
- **Dependency validation**: Checks all Python modules with installation hints
- **Automated testing**: Runs complete test suite with environment validation
- **Data collection**: Flexible inventory support for multi-router environments
- **Environment validation**: Verifies test data availability before testing
- **Clean builds**: Removes cache files while preserving routing data

### Enhanced Data Collection
Dual-mode facts collection system for production and testing:

#### **Production Mode (Default)**
- **Live network collection**: Executes `get_facts.sh` script on remote hosts via Ansible
- **Secure script deployment**: Copy → Execute → Remove pattern with unique temporary filenames
- **Collision-resistant naming**: Timestamp + hostname-based unique script names for parallel execution safety
- **Selective privilege escalation**: `become: yes` only for script execution, regular user for file operations
- **Text-only remote execution**: Minimal dependencies on remote hosts
- **Controller-side processing**: JSON conversion happens on Ansible controller
- **Flexible output**: Configurable facts directory via environment variables or command line

#### **Test Mode (`-e test=true`)**
- **Raw facts conversion**: Processes existing raw facts from `tests/raw_facts/` directory
- **No network access**: Operates entirely on local controller using test inventory
- **No authentication**: Simplified inventory without SSH keys or user credentials
- **Isolated output**: Generates test facts in `/tmp/traceroute_test_output/`
- **Test data merging**: Combines converted raw facts with existing test data for complete dataset
- **Gateway-only WireGuard**: Only gateway routers have WireGuard VPN configuration

#### **Simplified Test Inventory**
- **Streamlined configuration**: Only essential connection settings (localhost, Python interpreter)
- **Realistic network topology**: 10 routers across 3 locations with proper role classification
- **Gateway focus**: WireGuard mesh limited to gateway routers (hq-gw, br-gw, dc-gw)
- **Metadata-driven**: Router classification by type (gateway, core, access), location, and role

#### **Common Features**
- **Comprehensive data**: Routing, iptables, ipset, and system information
- **Enhanced ipset parsing**: Supports both `ipset list` and `ipset save` formats with comprehensive member extraction
- **Graceful degradation**: Continues operation when optional tools unavailable
- **Robust error handling**: Fallback mechanisms for parsing failures with detailed error reporting
- **Secure script handling**: Temporary files with unique names prevent conflicts and improve auditability

### Iptables Forward Analysis
Comprehensive packet forwarding analysis using actual firewall configurations:
- **Real iptables rules**: Analyzes FORWARD chain rules to determine packet forwarding decisions
- **Ipset integration**: Full support for ipset match-set conditions with efficient lookups
- **Multi-format input**: Supports IP ranges (CIDR), lists, and port ranges
- **Verbose analysis**: Three verbosity levels for detailed rule evaluation
- **Automation friendly**: Clear exit codes (0=allowed, 1=denied, 2=error)
- **Live router data**: Uses actual iptables configurations from network devices

### Project Organization
Well-organized codebase with clear separation of concerns:
- **Ansible integration**: All automation scripts consolidated in `ansible/` directory
- **Test isolation**: Complete test environment in `tests/` directory
- **Documentation**: Professional network diagrams and comprehensive documentation
- **Modular design**: Separate modules for routing, MTR execution, formatting, and analysis

### Configuration Management
Flexible configuration system for enterprise deployment:
- **YAML configuration**: Complete configuration file support with precedence handling
- **Environment variables**: Support for `TRACEROUTE_SIMULATOR_CONF` custom configuration paths
- **Precedence handling**: Command line → Configuration file → Hard-coded defaults
- **Production ready**: Graceful degradation when PyYAML unavailable
- **Multiple locations**: Support for various configuration file locations

### Enhanced Output Features
Improved network troubleshooting capabilities:
- **FQDN resolution**: Automatically resolves IP addresses to hostnames when possible
- **Smart fallback**: Uses IP address if reverse DNS resolution fails
- **Timing information**: RTT data from MTR execution for performance analysis
- **Router name consistency**: Shows actual router names when applicable
- **Unreachable detection**: Proper validation and reporting of unreachable destinations

### Reverse Path Tracing
Advanced bidirectional path discovery:
- **Three-step approach**: Controller to destination, destination to source, path combination
- **Timing integration**: Includes timing data for both intermediate and final destinations
- **Tuple format handling**: Supports both 7-tuple (simulation) and 8-tuple (MTR with RTT) formats
- **Error detection**: Proper reporting of unreachable destinations
- **Automatic controller detection**: Uses router metadata to find Ansible controller

## Development Notes

### Key Implementation Details
- **Tuple format consistency**: Handle both 7-tuple (simulation) and 8-tuple (MTR with RTT) path data formats
- **Timing information**: RTT data available as last element in 8-tuple format
- **Router name logic**: Use `simulator._find_router_by_ip(src_ip)` to determine router ownership
- **Error handling**: Distinguish between routing failures (EXIT_NO_PATH) and unreachable destinations (EXIT_NOT_FOUND)
- **Testing requirement**: Always run full test suite (`make test`) to ensure 100% pass rate

### Key Components
- **Core simulator**: `traceroute_simulator.py` - Main application with routing logic
- **MTR executor**: `mtr_executor.py` - Real MTR execution via SSH
- **Route formatter**: `route_formatter.py` - Unified output formatting
- **Reverse tracer**: `reverse_path_tracer.py` - Bidirectional path discovery
- **Iptables analyzer**: `iptables_forward_analyzer.py` - Packet forwarding analysis with comprehensive ipset support
- **Facts processor**: `ansible/process_facts.py` - Enhanced shell output parsing with dual ipset format support
- **Facts converter**: `convert_legacy_facts.py` - Migration from legacy format
- **Build system**: `Makefile` - Automated development workflows with integrated comprehensive testing
- **Data collection**: `ansible/get_tsim_facts.yml`, `ansible/get_facts.sh` - Dual-mode facts collection with secure script deployment
- **IP wrapper**: `ansible/ip_json_wrapper.py` - Legacy system compatibility
- **Comprehensive tests**: `tests/test_comprehensive_facts_processing.py` - 18 test cases covering facts processing and analyzer functionality
