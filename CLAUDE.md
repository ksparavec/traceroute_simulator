# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Test Commands

### Automated Make Targets (Recommended)
- **Check dependencies**: `make check-deps` (validates all Python modules with installation hints)
- **Run all tests**: `make test` (comprehensive test suite with environment validation)
- **Run namespace tests**: `sudo make test-namespace` (namespace simulation tests requiring root)
- **Clean artifacts**: `make clean` (removes cache files while preserving routing data)
- **Collect routing data**: `make fetch-routing-data OUTPUT_DIR=data INVENTORY_FILE=hosts.ini`
- **Show help**: `make help` (displays all available targets and examples)

### Direct Testing Commands

**Important**: When running test scripts directly (not via make), always use the `-B` flag to prevent bytecode generation:

- **Run comprehensive test suite**: `cd tests && python3 -B test_traceroute_simulator.py`
- **Test IP JSON wrapper**: `cd tests && python3 -B test_ip_json_comparison.py`
- **Test MTR integration**: `cd tests && python3 -B test_mtr_integration.py`
- **Test iptables analyzer standalone**: `cd tests && python3 -B test_comprehensive_facts_processing.py` (analyzer tests only)
- **Test namespace simulation**: `sudo python3 -B tests/test_namespace_simulation.py` (requires root)
- **Test specific functionality**: `make tsim ARGS="-s 10.1.1.1 -d 10.2.1.1"`
- **Test complex routing**: `make tsim ARGS="-s 10.1.10.1 -d 10.3.20.1"`
- **Test JSON output**: `make tsim ARGS="-j -s 10.100.1.1 -d 10.100.1.3"`
- **Test gateway internet access**: `make tsim ARGS="-s 10.1.1.1 -d 1.1.1.1"` (gateway to Cloudflare DNS)
- **Test multi-hop internet access**: `make tsim ARGS="-s 10.1.10.1 -d 8.8.8.8"` (internal network to Google DNS)
- **Test MTR fallback**: `make tsim ARGS="-s 10.1.1.1 -d 192.168.1.1 -vv"` (triggers MTR for unreachable)
- **Test reverse path tracing**: `make tsim ARGS="-s 10.1.1.1 -d 192.168.1.1 --reverse-trace -vv"` (auto-detects controller IP)
- **Test timing information**: `make tsim ARGS="-s 10.1.1.1 -d 8.8.8.8"` (shows RTT data)
- **Test YAML configuration**: `TRACEROUTE_SIMULATOR_CONF=tests/test_config.yaml make tsim ARGS="-s 10.1.1.1 -d 10.2.1.1"`
- **Test FQDN resolution**: `make tsim ARGS="-s 10.1.1.1 -d 8.8.8.8"` (shows dns.google)
- **Test verbose levels**: `make tsim ARGS="-s 10.1.1.1 -d 10.2.1.1 -v"` (basic), `ARGS="-vv"` (debug), `ARGS="-vvv"` (config)
- **Test metadata loading**: `make tsim ARGS="-s 10.1.1.1 -d 10.2.1.1 -vvv"` (shows router types)
- **Test iptables analyzer**: `make ifa ARGS="--router hq-gw -s 10.1.1.1 -d 10.2.1.1 -p tcp -vv"`
- **Generate network topology diagram**: `cd docs && python3 -B network_topology_diagram.py`

### Linux Namespace Network Simulation

The project includes a complete Linux namespace-based network simulation system that creates real network infrastructure for testing:

#### **Namespace Network Commands**
- **Setup simulation**: `sudo make netsetup` (creates 10 router namespaces with full connectivity)
- **Test connectivity**: `sudo make nettest ARGS="-s 10.1.1.1 -d 10.2.1.1 -p icmp"` (real packet testing)
- **Show network status**: `sudo make netshow ROUTER=hq-gw FUNC=interfaces` (displays config with original names)
- **Cleanup simulation**: `sudo make netclean` (removes all namespaces and veth pairs)

#### **Network Status Viewing**
- **Show all routers summary**: `sudo make netshow ROUTER=all FUNC=summary`
- **Show interface configuration**: `sudo make netshow ROUTER=hq-gw FUNC=interfaces`
- **Show routing table**: `sudo make netshow ROUTER=br-core FUNC=routes`
- **Show policy rules**: `sudo make netshow ROUTER=dc-srv FUNC=rules`
- **Show complete configuration**: `sudo make netshow ROUTER=hq-dmz FUNC=all`

#### **Network Testing Examples**
- **ICMP ping test**: `sudo make nettest ARGS="-s 10.1.1.1 -d 10.2.1.1 -p icmp"`
- **TCP connectivity test**: `sudo make nettest ARGS="-s 10.1.1.1 -d 10.2.1.1 -p tcp --dport 80"`
- **UDP connectivity test**: `sudo make nettest ARGS="-s 10.1.1.1 -d 10.2.1.1 -p udp --dport 53"`
- **Cross-location test**: `sudo make nettest ARGS="-s 10.1.1.1 -d 10.3.1.1 -p icmp"` (HQ to DC)
- **VPN mesh test**: `sudo make nettest ARGS="-s 10.100.1.1 -d 10.100.1.2 -p icmp"` (WireGuard)

#### **Connectivity and Path Testing**
- **Ping connectivity test all routers**: `sudo python3 -B src/simulators/network_namespace_tester.py --all`
- **MTR traceroute test all routers**: `sudo python3 -B src/simulators/network_namespace_tester.py --all --test-type mtr`
- **Combined ping and MTR testing**: `sudo python3 -B src/simulators/network_namespace_tester.py --all --test-type both`
- **Test specific router pair with ping**: `sudo python3 -B src/simulators/network_namespace_tester.py -s 10.3.2.3 -d 10.1.1.1`
- **Test path to public IP with MTR**: `sudo python3 -B src/simulators/network_namespace_tester.py -s 10.3.2.3 -d 1.1.1.1 --test-type mtr -vv`
- **Test external connectivity**: `sudo python3 -B src/simulators/network_namespace_tester.py -s 10.1.1.1 -d 8.8.8.8 --test-type both -v`
- **Test with verbose output**: `sudo python3 -B src/simulators/network_namespace_tester.py -s 10.2.2.3 -d 10.3.1.1 -vv`
- **Test blackholed destinations**: `sudo python3 -B src/simulators/network_namespace_tester.py -s 10.1.1.1 -d 10.2.6.2 --test-type mtr -vv`

### Data Collection and Validation

#### **Production Data Collection**
- **Collect with Ansible**: `make fetch-routing-data OUTPUT_DIR=custom_facts INVENTORY_FILE=inventory.ini`
- **Environment-based collection**: `TRACEROUTE_SIMULATOR_FACTS=custom_facts make fetch-routing-data INVENTORY_FILE=inventory.ini`

#### **Test Data Collection and Processing**
- **Generate test facts**: `make fetch-routing-data TEST_MODE=true` (converts raw_facts to /tmp/traceroute_test_output)
- **Direct test mode**: `ansible-playbook -i tests/inventory.yml ansible/get_tsim_facts.yml -e test=true`
- **Run comprehensive test suite**: `make test` (auto-generates fresh test facts and runs all tests)

#### **Individual Testing Commands**
- **Process raw facts**: `python3 -B ansible/process_facts.py tests/raw_facts/router_facts.txt output.json --verbose`
- **Validate facts processing**: `python3 -B ansible/process_facts.py --validate output.json`
- **Test with generated facts**: `TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output python3 -B tests/test_comprehensive_facts_processing.py`
- **Test simulator**: `TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output make tsim ARGS="-s 10.1.1.1 -d 10.2.1.1"`
- **Test iptables analyzer**: `TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output make ifa ARGS="--router hq-gw -s 10.1.1.1 -d 8.8.8.8 -p tcp -vv"`

#### **Data Validation**
- **Validate collected JSON**: `python3 -m json.tool /tmp/traceroute_test_output/*.json`
- **Test IP wrapper compatibility**: `python3 -B ansible/ip_json_wrapper.py route show`

#### **Utility Scripts**
- **Update interface data in JSON facts**: `python3 -B src/utils/update_tsim_facts.py` (extracts interfaces from routing tables)
- **Verify namespace setup**: `sudo python3 -B src/utils/verify_network_setup.py` (comprehensive configuration verification)
- **Verify specific namespace**: `TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output sudo python3 -B src/utils/verify_network_setup.py`

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
- **Build automation**: `Makefile` (comprehensive build system with dependency checking)

### Using Test Data
Always use the tests directory data when developing or testing:
```bash
# Correct usage (note: -s/-d flags are required)
make tsim ARGS="-s <source> -d <dest>"

# Tip: Export once to avoid repetition
export TRACEROUTE_SIMULATOR_FACTS=tests/tsim_facts
make tsim ARGS="-s <source> -d <dest>"
make ifa ARGS="--router <router> -s <source> -d <dest> -p <protocol>"

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
- **Comprehensive coverage**: 85+ total test cases providing near-complete code coverage
  - **Main simulator tests**: 63 test cases (100% pass rate)
  - **MTR integration tests**: 8 test cases (87.5% pass rate)
  - **IP wrapper tests**: 7 test cases (validation and compatibility)
  - **Namespace simulation tests**: 10 test cases (real network testing with Linux namespaces)
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
- **Test workflow integrity**: Facts files persist in `/tmp/traceroute_test_output` after `make test` for namespace testing

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
├── src/                                  # Core application code
│   ├── core/                             # Main simulator components
│   │   ├── traceroute_simulator.py          # Main application
│   │   ├── route_formatter.py               # Output formatting for simulation and MTR results
│   │   ├── reverse_path_tracer.py           # Reverse path tracing functionality
│   │   └── create_final_json.py             # Final JSON consolidation for build system
│   ├── analyzers/                        # Analysis tools  
│   │   └── iptables_forward_analyzer.py     # Packet forwarding analysis using iptables rules
│   ├── executors/                        # External command executors
│   │   └── mtr_executor.py                  # MTR execution and SSH management
│   ├── simulators/                       # Network simulation tools
│   │   ├── network_namespace_tester.py      # Multi-protocol connectivity and path testing (ping/MTR)
│   │   ├── network_namespace_setup.py       # Network namespace creation and configuration
│   │   └── network_namespace_status.py      # Network namespace status monitoring
│   └── utils/                            # Utility scripts for maintenance and debugging
│       ├── update_tsim_facts.py             # Update existing JSON facts files with interface data
│       └── verify_network_setup.py          # Comprehensive namespace configuration verification
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
- **103+ total test cases**: 63 main simulator + 8 MTR integration + 7 IP wrapper + 18 comprehensive facts processing + 10 namespace simulation + connectivity testing
- **100% pass rate**: All critical tests consistently pass with thorough validation
- **Complete coverage**: Intra-location, inter-location, multi-hop routing, error conditions, edge cases
- **Facts processing validation**: Ansible-based shell output parsing with proper data structure merging
- **Forward analyzer testing**: Complex rulesets, match-set rules, multiport scenarios, protocol variations
- **Comprehensive facts processing**: Isolated testing of facts processing and iptables analysis with temporary directories
- **Namespace simulation testing**: Real packet testing with Linux namespaces, setup/teardown, connectivity validation
- **Multi-protocol testing**: ICMP ping and MTR traceroute testing with public IP simulation
- **Connectivity validation**: Comprehensive router-to-router testing with flexible destination handling
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

### Namespace Simulation Testing
Comprehensive Linux namespace-based network simulation for real packet testing:
- **Real network simulation**: Creates actual Linux namespaces with full network topology
- **Complete infrastructure**: Routing tables, iptables rules, ipsets, and interface configuration
- **Multi-protocol testing**: ICMP ping and MTR traceroute testing with configurable test types
- **Real packet testing**: Uses netcat servers/clients to verify end-to-end connectivity
- **Protocol coverage**: TCP, UDP, and ICMP connectivity testing with port-specific validation
- **Firewall validation**: Verifies iptables rules properly block or allow traffic as expected
- **Flexible destination handling**: Supports any destination IP (internal, external, public) following routing tables
- **Public IP simulation**: Automatic public IP setup on gateway routers for realistic internet connectivity testing
- **Metadata-driven gateway detection**: Uses JSON metadata.type field for accurate gateway identification
- **MTR path analysis**: Comprehensive traceroute testing with hop-by-hop analysis and blackhole detection
- **Sequential testing**: One-router-at-a-time testing to avoid network congestion
- **Setup/teardown automation**: Complete lifecycle management with proper resource cleanup
- **Status monitoring**: Comprehensive namespace status display with interface and routing information
- **Root privilege handling**: Automatic privilege detection with graceful fallback for non-root execution
- **Integration with facts**: Uses consolidated JSON facts from `/tmp/traceroute_test_output` exclusively
- **Test scenarios**: Intra-location, inter-location, VPN mesh, public IP access, and firewall blocking scenarios

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
- **Core simulator**: `src/core/traceroute_simulator.py` - Main application with routing logic
- **MTR executor**: `src/executors/mtr_executor.py` - Real MTR execution via SSH
- **Route formatter**: `src/core/route_formatter.py` - Unified output formatting
- **Reverse tracer**: `src/core/reverse_path_tracer.py` - Bidirectional path discovery
- **JSON consolidator**: `src/core/create_final_json.py` - Final JSON consolidation for build system
- **Iptables analyzer**: `src/analyzers/iptables_forward_analyzer.py` - Packet forwarding analysis with comprehensive ipset support
- **Namespace tester**: `src/simulators/network_namespace_tester.py` - Multi-protocol connectivity and path testing with MTR support
- **Namespace setup**: `src/simulators/network_namespace_setup.py` - Complete network simulation infrastructure creation
- **Namespace status**: `src/simulators/network_namespace_status.py` - Real-time network namespace monitoring and status display
- **Facts updater**: `src/utils/update_tsim_facts.py` - Update existing JSON facts files with interface data from routing tables
- **Setup verifier**: `src/utils/verify_network_setup.py` - Comprehensive namespace configuration verification and debugging
- **Facts processor**: `ansible/process_facts.py` - Enhanced shell output parsing with dual ipset format support
- **Build system**: `Makefile` - Automated development workflows with integrated comprehensive testing
- **Data collection**: `ansible/get_tsim_facts.yml`, `ansible/get_facts.sh` - Dual-mode facts collection with secure script deployment
- **IP wrapper**: `ansible/ip_json_wrapper.py` - Legacy system compatibility
- **Standalone analyzer tests**: `tests/test_comprehensive_facts_processing.py` - 18 test cases for iptables analyzer (run independently)
