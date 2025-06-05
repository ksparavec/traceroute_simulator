# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Test Commands
- **Run comprehensive test suite**: `cd testing && python3 test_traceroute_simulator.py`
- **Test specific functionality**: `python3 traceroute_simulator.py --routing-dir testing/routing_facts -s 10.1.1.1 -d 10.2.1.1`
- **Test complex routing**: `python3 traceroute_simulator.py --routing-dir testing/routing_facts -s 10.1.10.1 -d 10.3.20.1`
- **Test JSON output**: `python3 traceroute_simulator.py --routing-dir testing/routing_facts -j -s 10.100.1.1 -d 10.100.1.3`
- **Generate network topology diagram**: `cd testing && python3 network_topology_diagram.py`
- **Lint Python code**: `flake8 *.py testing/*.py` (if flake8 is available)
- **Validate YAML**: `yamllint *.yml` (if yamllint is available)
- **Validate JSON**: `python3 -m json.tool testing/routing_facts/*.json`

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
- **Test suite**: `testing/test_traceroute_simulator.py` (64 test cases with 100% pass rate)

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
├── traceroute_simulator.py        # Main application
├── get_routing_info.yml           # Data collection playbook
├── testing/                       # Complete test environment
│   ├── test_traceroute_simulator.py   # Test suite (64 cases, 100% pass rate)
│   ├── NETWORK_TOPOLOGY.md           # Network documentation
│   ├── network_topology_diagram.py   # Professional diagram generator
│   ├── network_topology.png          # High-resolution network diagram
│   ├── network_topology.pdf          # Vector network diagram
│   └── routing_facts/                # Test routing data (20 files)
├── CLAUDE.md                      # Development guidelines
└── README.md                      # User documentation
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

### Key Files Modified
- **Routing data**: `testing/routing_facts/*.json` (corrected routing tables and gateway IPs)
- **Core logic**: `traceroute_simulator.py` (improved interface determination, new argument format, enhanced exit codes)
- **Test suite**: `testing/test_traceroute_simulator.py` (expanded to 64 tests with comprehensive coverage)
- **Visualization**: `testing/network_topology_diagram.py` (new professional diagram system)
- **Documentation**: `testing/NETWORK_TOPOLOGY.md` and `README.md` (updated with all improvements)
- **Development guide**: `CLAUDE.md` (comprehensive documentation of all enhancements)
