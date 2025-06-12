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
- **Test specific functionality**: `python3 traceroute_simulator.py --routing-dir tests/routing_facts -s 10.1.1.1 -d 10.2.1.1`
- **Test complex routing**: `python3 traceroute_simulator.py --routing-dir tests/routing_facts -s 10.1.10.1 -d 10.3.20.1`
- **Test JSON output**: `python3 traceroute_simulator.py --routing-dir tests/routing_facts -j -s 10.100.1.1 -d 10.100.1.3`
- **Test MTR fallback**: `python3 traceroute_simulator.py --routing-dir tests/routing_facts -s 10.1.1.1 -d 8.8.8.8 -vv`
- **Test reverse path tracing**: `python3 traceroute_simulator.py --routing-dir tests/routing_facts -s 10.1.1.1 -d 8.8.8.8 --reverse-trace -vv`
- **Test timing information**: `python3 traceroute_simulator.py --routing-dir tests/routing_facts -s 10.1.1.1 -d 8.8.8.8` (shows RTT data)
- **Test YAML configuration**: `TRACEROUTE_SIMULATOR_CONF=tests/test_config.yaml python3 traceroute_simulator.py -s 10.1.1.1 -d 10.2.1.1`
- **Test FQDN resolution**: `python3 traceroute_simulator.py --routing-dir tests/routing_facts -s 10.1.1.1 -d 8.8.8.8` (shows dns.google)
- **Generate network topology diagram**: `cd docs && python3 network_topology_diagram.py`

### Data Collection and Validation
- **Collect with Ansible**: `make fetch-routing-data OUTPUT_DIR=tests/routing_facts INVENTORY_FILE=inventory.ini`
- **Validate collected JSON**: `python3 -m json.tool tests/routing_facts/*.json`
- **Test IP wrapper compatibility**: `python3 ip_json_wrapper.py route show`

## Test Network Environment

The project includes a comprehensive test network with realistic enterprise topology:
- **10 routers** across 3 locations (HQ, Branch, Data Center)
- **Complex routing scenarios**: Intra-location, inter-location, multi-hop
- **WireGuard VPN mesh**: 10.100.1.0/24 connecting all locations
- **Multiple network segments**: 14 different subnets across all locations
- **Realistic IP addressing**: 10.1.0.0/16 (HQ), 10.2.0.0/16 (Branch), 10.3.0.0/16 (DC)

### Test Data Location
- **Primary test data**: `tests/routing_facts/` (20 JSON files)
- **Network documentation**: `docs/NETWORK_TOPOLOGY.md`
- **Network visualization**: `docs/network_topology_diagram.py` (matplotlib-based diagram generator)
- **Generated diagrams**: `docs/network_topology.png` and `docs/network_topology.pdf`
- **Main test suite**: `tests/test_traceroute_simulator.py` (64 test cases with 100% pass rate)
- **IP wrapper tests**: `tests/test_ip_json_comparison.py` (7 test cases validating wrapper compatibility)
- **MTR integration tests**: `tests/test_mtr_integration.py` (8 test cases validating MTR fallback functionality)
- **IP JSON wrapper**: `ip_json_wrapper.py` (compatibility layer for older Red Hat systems)
- **Build automation**: `Makefile` (comprehensive build system with dependency checking)

### Using Test Data
Always use the tests directory data when developing or testing:
```bash
# Correct usage (note: -s/-d flags are required)
python3 traceroute_simulator.py --routing-dir tests/routing_facts -s <source> -d <dest>

# For new features, ensure compatibility with test network topology
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
- **Comprehensive coverage**: 79 total test cases (64 main + 8 MTR + 7 IP wrapper) providing near-complete code coverage
- **Network topology testing**: Tests for intra-location, inter-location, and multi-hop routing
- **Test documentation**: Comment test purposes and expected outcomes
- **Error testing**: Include tests for all error conditions and edge cases
- **Edge case coverage**: Corrupted JSON, missing files, IPv6 handling, loop detection
- **Integration tests**: Test real-world scenarios with enterprise network topology
- **Routing misconfiguration testing**: Realistic scenarios simulating network issues
- **Automation friendly**: Support for CI/CD and automated testing
- **Performance validation**: Ensure all tests complete within reasonable time
- **Data integrity**: Validate JSON structure and routing table consistency
- **100% pass rate**: All 64 tests consistently pass with comprehensive validation

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
├── ip_json_wrapper.py                    # IP JSON compatibility wrapper
├── reverse_path_tracer.py                # Reverse path tracing functionality
├── Makefile                              # Build system with dependency checking
├── tests/                                # Complete test environment
│   ├── test_traceroute_simulator.py         # Main test suite (64 cases, 100% pass rate)
│   ├── test_ip_json_comparison.py           # Wrapper validation tests (7 cases)
│   ├── test_mtr_integration.py              # MTR integration tests (8 cases)
│   ├── test_config.yaml                     # Test-specific configuration
│   └── routing_facts/                      # Test routing data (20 files)
├── docs/                                 # Documentation and visualization
│   ├── NETWORK_TOPOLOGY.md                 # Network documentation
│   ├── network_topology_diagram.py         # Professional diagram generator
│   ├── network_topology.png                # High-resolution network diagram
│   └── network_topology.pdf                # Vector network diagram
├── ansible/                              # Data collection automation
│   └── get_routing_info.yml                # Enhanced data collection playbook
├── CLAUDE.md                             # Development guidelines
└── README.md                             # User documentation
```

### Development Guidelines
- **Use test data**: Always test with `tests/routing_facts/` data
- **Update tests**: Add tests for new features using realistic network scenarios
- **Document changes**: Update both code comments and README.md
- **Validate thoroughly**: Run full test suite before submitting changes
- **Maintain topology**: Keep test network topology realistic and comprehensive

## Recent Improvements (2024)

### Routing Data Fixes
The routing data has been comprehensively fixed to ensure accurate traceroute simulation:
- **Invalid gateway IPs corrected**: Fixed gateway references to use actual router interface IPs
- **Removed invalid scope:link routes**: Eliminated overly broad /16 scope:link routes that caused incorrect routing
- **Added missing network routes**: Included routes for all network segments (10.1.11.0/24, 10.2.6.0/24, 10.3.21.0/24)
- **Consistent routing behavior**: All routers now have proper routing tables that reflect real network topology

### Interface Logic Improvements
Enhanced the traceroute simulator's interface determination logic:
- **Added `_get_incoming_interface()` method**: Properly determines incoming interfaces based on network topology
- **Fixed interface name determination**: Uses network-based lookup rather than assumptions
- **Improved hop-by-hop accuracy**: More precise tracking of traffic flow through router interfaces
- **Better network segment handling**: Correctly identifies interfaces for directly connected networks

### Professional Network Visualization
Replaced problematic ASCII diagrams with professional matplotlib-based visualization:
- **Clean hierarchical layout**: Proper spacing and positioning to avoid overlaps
- **No crossing connections**: Optimized connection routing for visual clarity
- **Adaptive box sizing**: Router boxes automatically scale based on interface count
- **Multiple output formats**: High-resolution PNG (300 DPI) and vector PDF formats
- **Comprehensive information**: All router names, IP addresses, and interface details
- **Easy customization**: Simple modification of positions, colors, and styling

### Argument Format Enhancement
Updated command-line interface for improved usability and clarity:
- **Required flags**: Changed from positional arguments to required `-s`/`--source` and `-d`/`--destination` flags
- **Improved clarity**: Explicit flag names make commands more self-documenting
- **Better error handling**: Enhanced argument validation with clear error messages
- **Backward compatibility**: All existing functionality preserved with new interface
- **Updated test suite**: All 64 tests updated to use new argument format

### Exit Code Refinements
Enhanced exit code behavior for better automation and error handling:
- **Consistent exit codes**: Unified behavior across quiet and non-quiet modes
- **Semantic exit codes**: Clear distinction between routing misconfiguration (1) and unreachable destinations (2)
- **Improved error classification**: Better differentiation between configuration issues and network topology limitations
- **Automation friendly**: Reliable exit codes for script integration

### Comprehensive Code Coverage Analysis
Achieved near-complete code coverage through systematic testing expansion:
- **64 comprehensive test cases**: Expanded from 57 to 64 tests covering all code paths
- **Edge case coverage**: Added tests for corrupted JSON, empty directories, missing files
- **Error condition testing**: IPv6 handling, loop detection, timeout scenarios
- **Routing misconfiguration**: Realistic scenarios simulating administrative errors
- **File I/O edge cases**: Comprehensive testing of all file system interactions
- **100% pass rate**: All tests consistently pass with thorough validation

### Test Categories (64 Total Tests)
1. **Intra-Location Routing** (11 tests): Communication within each location
2. **Inter-Location Routing** (12 tests): Cross-site communication via WireGuard
3. **Network Segment Routing** (9 tests): Host-to-host communication across subnets
4. **Command Line Options** (4 tests): All flags and output formats
5. **Error Conditions** (14 tests): Invalid inputs, missing files, network errors
6. **Exit Codes** (4 tests): Verification of all return codes
7. **Edge Cases** (6 tests): Corrupted JSON, empty directories, IPv6, loops
8. **Complex Scenarios** (8 tests): Multi-hop routing and advanced paths

## Recent Improvements (2025) - NEW

### MTR Integration for Enhanced Path Discovery
Implemented comprehensive MTR (My TraceRoute) fallback functionality for mixed Linux/non-Linux networks:
- **Automatic fallback logic**: Seamlessly transitions from simulation to real MTR when simulation cannot complete paths
- **SSH-based execution**: Direct SSH execution of MTR commands on remote Linux routers without Ansible dependency
- **Linux router filtering**: Filters MTR results to show only Linux routers from inventory using reverse DNS lookup
- **Consistent output formatting**: Unified output format between simulation and MTR results in both text and JSON
- **Two-level verbose debugging**: `-v` for basic output, `-vv` for detailed debugging including MTR command details
- **Enhanced exit codes**: New exit code 4 for MTR traces with no Linux routers found
- **Comprehensive testing**: 8 dedicated MTR integration tests validating all functionality
- **Router name detection**: Proper source router name display vs "source" label based on router ownership

### IP JSON Wrapper for Legacy System Compatibility
Created comprehensive wrapper tool for older Red Hat systems without native `ip --json` support:
- **Transparent replacement**: `ip_json_wrapper.py` serves as drop-in replacement for `ip --json` commands
- **Identical output**: Produces byte-for-byte identical JSON to native commands (validated with 7 comprehensive tests)
- **Complete subcommand support**: Handles route, addr, link, and rule subcommands with full parsing
- **Automatic detection**: Uses native JSON support when available, falls back to parsing when needed
- **Complex parsing logic**: Handles MAC addresses, VPN interfaces, network namespaces, bridge masters
- **Comprehensive validation**: 100% test coverage ensures output accuracy with `test_ip_json_comparison.py`

### Professional Build System Integration
Implemented comprehensive Makefile for automated development workflows:
- **Dependency validation**: `make check-deps` checks all Python modules with helpful installation hints
- **Automated testing**: `make test` runs 79 total tests (64 main + 8 MTR + 7 wrapper validation + integration tests)
- **Data collection automation**: `make fetch-routing-data` with flexible inventory support
- **Dual inventory modes**: Support for both inventory files and configured Ansible inventory groups
- **Environment validation**: Verifies test data availability and routing facts before testing
- **Clean builds**: Removes cache files while preserving valuable routing data

### Enhanced Ansible Playbook for Maximum Compatibility
Updated `get_routing_info.yml` for enterprise deployment on diverse Linux environments:
- **Text-only remote execution**: Executes only basic `ip route show` and `ip rule show` commands on remote hosts
- **Automatic path discovery**: Searches standard utility paths (`/sbin`, `/usr/sbin`, `/bin`, `/usr/bin`) for `ip` command
- **Full path execution**: Uses complete path to `ip` command for maximum reliability across Linux distributions
- **Controller-side JSON conversion**: Transfers text output to Ansible controller for JSON transformation
- **No remote Python dependencies**: Remote hosts only need the standard `ip` command available
- **IP JSON wrapper on controller**: Uses `ip_json_wrapper.py` on the controller to convert text to JSON
- **Comprehensive error handling**: Graceful failure with detailed troubleshooting information
- **Automatic cleanup**: Removes temporary text files from controller after processing
- **Collection statistics**: Reports number of routing entries collected from each host

### Advanced Test Infrastructure
Expanded testing capabilities with professional validation tools:
- **IP wrapper validation**: `test_ip_json_comparison.py` ensures wrapper produces identical output to native commands
- **Cross-platform testing**: Validates compatibility across different Linux distributions and versions
- **Automated comparison**: Uses JSON normalization and unified diff reporting for accuracy verification
- **Integration testing**: End-to-end validation of data collection and processing workflows
- **Build system testing**: Validates Makefile targets and dependency checking functionality

## Latest Improvements (June 2025) - MOST RECENT

### YAML Configuration Support (Latest)
Complete YAML configuration file support for flexible enterprise deployment:
- **Comprehensive Configuration**: Full YAML configuration file support with proper precedence handling
- **Environment Variable Support**: `TRACEROUTE_SIMULATOR_CONF` environment variable for custom configuration file paths
- **Precedence Handling**: Command line arguments → Configuration file values → Hard-coded defaults
- **Positive Logic Configuration**: All options use intuitive positive logic (e.g., `enable_mtr_fallback: true` instead of `--no-mtr`)
- **Production Ready**: Graceful degradation when PyYAML module is not available
- **Complete Coverage**: All command line options configurable except source/destination IPs (which must be provided via CLI)
- **Multiple Locations**: Support for `~/traceroute_simulator.yaml`, `./traceroute_simulator.yaml`, and environment variable paths

### FQDN Resolution for Endpoints (Latest)
Enhanced hostname resolution for improved network troubleshooting:
- **Automatic DNS Resolution**: Automatically resolves source and destination IP addresses to FQDNs when possible
- **Smart Fallback**: Falls back to original IP address if reverse DNS resolution fails
- **Consistent Methodology**: Uses same `getent hosts` approach as MTR executor for consistency
- **Router Priority**: Router-owned IP addresses still display router names instead of FQDNs
- **Fast Resolution**: 2-second timeout for responsive UI experience in production environments
- **Production Examples**: Shows `dns.google (8.8.8.8)` instead of generic `destination (8.8.8.8)`
- **Backward Compatibility**: All existing functionality preserved with enhanced labeling

### Enhanced MTR Integration and Timing Information
Comprehensive improvements to MTR functionality and output consistency:
- **Timing Data Collection**: All MTR results now include round-trip time (RTT) information for performance analysis and latency troubleshooting
- **Router Name Consistency**: Source IPs that belong to router interfaces now display the actual router name instead of generic "source" label
- **Unreachable Destination Detection**: Enhanced validation ensures destinations are actually reached by MTR, preventing false positive reachability reports
- **Forward Tracing Consistency**: Forward tracing with no Linux routers now returns EXIT_SUCCESS with timing information instead of EXIT_NO_LINUX
- **Enhanced Output Formatting**: Consistent timing display across all tracing methods (simulation, MTR forward, MTR reverse)

### Reverse Path Tracing Enhancements
Major improvements to reverse path tracing functionality:
- **Timing Information Integration**: Reverse path tracing now includes timing data for both intermediate Linux routers and final destinations
- **Improved Path Construction**: Better handling of tuple formats (7-tuple vs 8-tuple) with and without RTT data throughout the codebase
- **Router Duplication Prevention**: Fixed issues where the last Linux router appeared twice in final combined paths
- **Enhanced Error Handling**: Proper detection and reporting of unreachable destinations in reverse tracing scenarios
- **Comprehensive Tuple Support**: All code paths now safely handle both 7-tuple (simulation) and 8-tuple (MTR with RTT) formats

### Code Quality and Testing Improvements
Enhanced reliability and maintainability:
- **Tuple Format Handling**: Implemented safe tuple unpacking throughout `reverse_path_tracer.py` and `traceroute_simulator.py`
- **100% Test Suite Pass Rate**: All 79 tests continue to pass with enhanced functionality (64 main + 8 MTR + 7 IP wrapper)
- **Improved Error Classification**: Better distinction between routing misconfigurations and unreachable destinations
- **Enhanced Exit Code Logic**: Consistent exit code behavior across quiet and non-quiet modes
- **Test Regression Fixes**: Updated test expectations to reflect working MTR fallback functionality

### Critical Bug Fixes
Resolved key issues affecting functionality:
- **MTR Parsing Errors**: Fixed "too many values to unpack" errors when processing MTR results with timing information
- **Router Name Display**: Corrected logic to show actual router names when source IP belongs to a router interface
- **Unreachable Detection**: Fixed false positive cases where unreachable destinations were reported as reachable due to timing extraction from intermediate hops
- **Forward Tracing Exit Codes**: Fixed inconsistency where forward tracing returned failure instead of success when no Linux routers found but destination reachable
- **Test Regressions**: Updated "Max hops/loop handling" test to use `--no-mtr` flag for pure simulation testing

### Testing and Validation
Comprehensive testing of new functionality:
- **All existing tests maintained**: 79/79 tests pass with 100% success rate
- **Enhanced MTR integration testing**: Verified timing information extraction and router name consistency
- **Reverse path tracing validation**: Confirmed proper tuple handling and timing data preservation
- **Error condition testing**: Validated unreachable destination detection and proper exit code behavior
- **Output format verification**: Ensured consistent formatting across all tracing methods

### Key Files Modified (December 2025)
- **Core simulator**: `traceroute_simulator.py` (UPDATED - enhanced MTR fallback with timing, router name consistency, unreachable detection)
- **Reverse tracer**: `reverse_path_tracer.py` (UPDATED - comprehensive tuple handling, timing integration, path construction improvements)
- **Main test suite**: `tests/test_traceroute_simulator.py` (UPDATED - fixed test regressions for MTR fallback functionality)
- **MTR integration tests**: `tests/test_mtr_integration.py` (UPDATED - corrected expectations for working SSH environment)
- **Documentation**: `README.md` and `CLAUDE.md` (UPDATED - comprehensive documentation of timing features and improvements)

### Development Notes for Recent Changes
- **Tuple Format Consistency**: When working with path data, always check tuple length before unpacking to handle both 7-tuple and 8-tuple formats
- **Timing Information**: RTT data is now available in 8-tuple format as the last element: `(hop, router, ip, interface, is_owned, connected, outgoing, rtt)`
- **Router Name Logic**: Use `simulator._find_router_by_ip(src_ip)` to determine if source IP belongs to a router for proper naming
- **Error Handling**: Distinguish between routing failures (EXIT_NO_PATH) and unreachable destinations (EXIT_NOT_FOUND) based on MTR validation
- **Testing**: Always run full test suite (`make test`) after modifications to ensure 100% pass rate is maintained

### Key Files Added/Modified (2025)
- **YAML configuration file**: `traceroute_simulator.yaml` (NEW - example configuration file with comprehensive options)
- **Configuration system**: Added YAML configuration loading to `traceroute_simulator.py` (UPDATED - complete configuration management)
- **FQDN resolution**: Enhanced `traceroute_simulator.py`, `reverse_path_tracer.py`, `route_formatter.py` (UPDATED - automatic hostname resolution)
- **MTR executor**: `mtr_executor.py` (UPDATED - enhanced hostname matching and debug output for production troubleshooting)
- **Route formatter**: `route_formatter.py` (NEW - unified output formatting for simulation and MTR results)
- **Reverse tracer**: `reverse_path_tracer.py` (NEW - three-step bidirectional path discovery)
- **MTR integration tests**: `tests/test_mtr_integration.py` (NEW - 8 tests validating MTR fallback functionality)
- **IP JSON wrapper**: `ip_json_wrapper.py` (NEW - compatibility layer for older Red Hat systems)
- **Wrapper tests**: `tests/test_ip_json_comparison.py` (NEW - 7 tests validating wrapper accuracy)
- **Build system**: `Makefile` (NEW - comprehensive build automation with dependency checking)
- **Enhanced playbook**: `ansible/get_routing_info.yml` (UPDATED - text-only remote execution with controller-side JSON conversion)
- **Core simulator**: `traceroute_simulator.py` (UPDATED - enhanced with YAML config, FQDN resolution, MTR fallback, reverse tracing, timing)
- **Test corrections**: `tests/test_traceroute_simulator.py` (UPDATED - corrected exit code expectations for logical behavior)
- **Documentation**: `README.md` and `CLAUDE.md` (UPDATED - comprehensive documentation including configuration and FQDN features)

### Previous Key Files Modified (2024)
- **Routing data**: `tests/routing_facts/*.json` (corrected routing tables and gateway IPs)
- **Core logic**: `traceroute_simulator.py` (improved interface determination, new argument format, enhanced exit codes)
- **Test suite**: `tests/test_traceroute_simulator.py` (expanded to 64 tests with comprehensive coverage)
- **Visualization**: `docs/network_topology_diagram.py` (professional diagram system)
- **Documentation**: `docs/NETWORK_TOPOLOGY.md` and `README.md` (updated with all improvements)
- **Development guide**: `CLAUDE.md` (comprehensive documentation of all enhancements)
