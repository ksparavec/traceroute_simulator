# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Test Commands
- **Run comprehensive test suite**: `cd testing && python3 test_traceroute_simulator.py`
- **Test specific functionality**: `python3 traceroute_simulator.py --routing-dir testing/routing_facts 10.1.1.1 10.2.1.1`
- **Test complex routing**: `python3 traceroute_simulator.py --routing-dir testing/routing_facts 10.1.10.1 10.3.20.1`
- **Test JSON output**: `python3 traceroute_simulator.py --routing-dir testing/routing_facts -j 10.100.1.1 10.100.1.3`
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
- **Test suite**: `testing/test_traceroute_simulator.py` (57 test cases)

### Using Test Data
Always use the testing directory data when developing or testing:
```bash
# Correct usage
python3 traceroute_simulator.py --routing-dir testing/routing_facts <source> <dest>

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
- **Comprehensive coverage**: 57 test cases covering all routing scenarios
- **Network topology testing**: Tests for intra-location, inter-location, and multi-hop routing
- **Test documentation**: Comment test purposes and expected outcomes
- **Error testing**: Include tests for all error conditions and edge cases
- **Integration tests**: Test real-world scenarios with enterprise network topology
- **Automation friendly**: Support for CI/CD and automated testing
- **Performance validation**: Ensure all tests complete within reasonable time
- **Data integrity**: Validate JSON structure and routing table consistency

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
│   ├── test_traceroute_simulator.py   # Test suite (57 cases)
│   ├── NETWORK_TOPOLOGY.md           # Network documentation
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
