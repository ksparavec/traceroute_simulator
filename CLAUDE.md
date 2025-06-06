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
- **Run comprehensive test suite**: `cd testing && python3 test_traceroute_simulator.py`
- **Test IP JSON wrapper**: `cd testing && python3 test_ip_json_comparison.py`
- **Test specific functionality**: `python3 traceroute_simulator.py --routing-dir testing/routing_facts -s 10.1.1.1 -d 10.2.1.1`
- **Test complex routing**: `python3 traceroute_simulator.py --routing-dir testing/routing_facts -s 10.1.10.1 -d 10.3.20.1`
- **Test JSON output**: `python3 traceroute_simulator.py --routing-dir testing/routing_facts -j -s 10.100.1.1 -d 10.100.1.3`
- **Generate network topology diagram**: `cd testing && python3 network_topology_diagram.py`

### Data Collection and Validation
- **Collect with Ansible**: `make fetch-routing-data OUTPUT_DIR=testing/routing_facts INVENTORY_FILE=inventory.ini`
- **Validate collected JSON**: `python3 -m json.tool testing/routing_facts/*.json`
- **Test IP wrapper compatibility**: `python3 ip_json_wrapper.py route show`

## Test Network Environment

The project includes a comprehensive test network with realistic enterprise topology:
- **10 routers** across 3 locations (HQ, Branch, Data Center)
- **Complex routing scenarios**: Intra-location, inter-location, multi-hop
- **WireGuard VPN mesh**: 10.100.1.0/24 connecting all locations
- **Multiple network segments**: 14 different subnets across all locations
- **Realistic IP addressing**: 10.1.0.0/16 (HQ), 10.2.0.0/16 (Branch), 10.3.0.0/16 (DC)

### Test Data Location
- **Primary test data**: `testing/routing_facts/` (20 JSON files)
- **Network documentation**: `testing/NETWORK_TOPOLOGY.md`
- **Network visualization**: `testing/network_topology_diagram.py` (matplotlib-based diagram generator)
- **Generated diagrams**: `testing/network_topology.png` and `testing/network_topology.pdf`
- **Main test suite**: `testing/test_traceroute_simulator.py` (64 test cases with 100% pass rate)
- **IP wrapper tests**: `testing/test_ip_json_comparison.py` (7 test cases validating wrapper compatibility)
- **IP JSON wrapper**: `ip_json_wrapper.py` (compatibility layer for older Red Hat systems)
- **Build automation**: `Makefile` (comprehensive build system with dependency checking)

### Using Test Data
Always use the testing directory data when developing or testing:
```bash
# Correct usage (note: -s/-d flags are required)
python3 traceroute_simulator.py --routing-dir testing/routing_facts -s <source> -d <dest>

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
- **Comprehensive coverage**: 64 test cases providing near-complete code coverage
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
- **Testing isolation**: All test data and scripts in `testing/` directory
- **Modularity**: Design for reusability and extensibility
- **Configuration**: Use external configuration files where appropriate
- **Data format**: Maintain consistent JSON structure for routing data
- **Backward compatibility**: Preserve existing interfaces when adding features

### Directory Organization
```
traceroute_simulator/
├── traceroute_simulator.py               # Main application
├── ip_json_wrapper.py                    # IP JSON compatibility wrapper (NEW)
├── get_routing_info.yml                  # Enhanced data collection playbook
├── Makefile                              # Build system with dependency checking (NEW)
├── testing/                              # Complete test environment
│   ├── test_traceroute_simulator.py         # Main test suite (64 cases, 100% pass rate)
│   ├── test_ip_json_comparison.py           # Wrapper validation tests (7 cases) (NEW)
│   ├── NETWORK_TOPOLOGY.md                 # Network documentation
│   ├── network_topology_diagram.py         # Professional diagram generator
│   ├── network_topology.png                # High-resolution network diagram
│   ├── network_topology.pdf                # Vector network diagram
│   └── routing_facts/                      # Test routing data (20 files)
├── CLAUDE.md                             # Development guidelines
└── README.md                             # User documentation
```

### Development Guidelines
- **Use test data**: Always test with `testing/routing_facts/` data
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
- **Automated testing**: `make test` runs 71 total tests (64 main + 7 wrapper validation + integration tests)
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

### Key Files Added/Modified (2025)
- **IP JSON wrapper**: `ip_json_wrapper.py` (NEW - compatibility layer for older Red Hat systems)
- **Wrapper tests**: `testing/test_ip_json_comparison.py` (NEW - 7 tests validating wrapper accuracy)
- **Build system**: `Makefile` (NEW - comprehensive build automation with dependency checking)
- **Enhanced playbook**: `get_routing_info.yml` (UPDATED - text-only remote execution with controller-side JSON conversion)
- **Documentation**: `README.md` and `CLAUDE.md` (UPDATED - comprehensive documentation of all new features)

### Previous Key Files Modified (2024)
- **Routing data**: `testing/routing_facts/*.json` (corrected routing tables and gateway IPs)
- **Core logic**: `traceroute_simulator.py` (improved interface determination, new argument format, enhanced exit codes)
- **Test suite**: `testing/test_traceroute_simulator.py` (expanded to 64 tests with comprehensive coverage)
- **Visualization**: `testing/network_topology_diagram.py` (professional diagram system)
- **Documentation**: `testing/NETWORK_TOPOLOGY.md` and `README.md` (updated with all improvements)
- **Development guide**: `CLAUDE.md` (comprehensive documentation of all enhancements)
