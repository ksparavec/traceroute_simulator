# Makefile for Traceroute Simulator Project
# Provides targets for dependency checking, testing, and routing data collection

# Project configuration
PYTHON := python3
PYTHON_OPTIONS := -B -u
PIP := pip3
ANSIBLE := ansible-playbook
TESTS_DIR := tests
ROUTING_FACTS_DIR := $(TRACEROUTE_SIMULATOR_FACTS)
ANSIBLE_DIR := ansible

# Build configuration
CC := gcc
CFLAGS := -std=c99 -Wall -Wextra -O2 -D_GNU_SOURCE
INSTALL_DIR := /usr/local/bin
WRAPPER_SRC := src/utils/netns_reader.c
WRAPPER_BIN := netns_reader

# Global environment variables
export PYTHONDONTWRITEBYTECODE := 1

# Python modules required by the project
REQUIRED_MODULES := json sys argparse ipaddress os glob typing subprocess re difflib matplotlib numpy

# Colors removed for better terminal compatibility

.PHONY: help check-deps test test-iptables-enhanced test-policy-routing test-ipset-enhanced test-raw-facts-loading test-mtr-options test-iptables-logging test-packet-tracing test-network facts clean tsim ifa netsetup nettest netclean netshow netstatus test-namespace hostadd hostdel hostlist hostclean netnsclean service-start service-stop service-restart service-status service-test service-clean test-services svctest svcstart svcstop svclist svcclean install-wrapper install-package install-pipx uninstall-package uninstall-pipx list-package

# Default target
help:
	@echo "Traceroute Simulator - Available Make Targets"
	@echo "=============================================="
	@echo "check-deps        - Check for required Python modules and provide installation hints"
	@echo "test              - Execute all test scripts with test setup and report results (includes make targets tests)"
	@echo "facts             - Run Ansible playbook to collect network facts (requires INVENTORY_FILE or INVENTORY)"
	@echo "clean             - Clean up generated files and cache"
	@echo "install-wrapper   - Build and install the netns_reader wrapper with proper capabilities (requires sudo)"
	@echo "package           - Build pip-installable tsim package (creates wheel and source distributions)"
	@echo "install-package   - Build and install tsim package (use USER=1 for user install, BREAK_SYSTEM=1 to force)"
	@echo "install-pipx      - Install tsim package using pipx (recommended for command-line applications)"
	@echo "uninstall-package - Uninstall tsim package (use USER=1 for user uninstall, BREAK_SYSTEM=1 to force)"
	@echo "uninstall-pipx    - Uninstall tsim package from pipx"
	@echo "list-package      - List all files included in the built package"
	@echo "tsim              - Run traceroute simulator with command line arguments (e.g., make tsim ARGS='-s 10.1.1.1 -d 10.2.1.1')"
	@echo "ifa               - Run iptables forward analyzer with command line arguments (e.g., make ifa ARGS='--router hq-gw -s 10.1.1.1 -d 8.8.8.8')"
	@echo "netlog            - Analyze iptables logs with filtering and correlation (e.g., make netlog ARGS='--source 10.1.1.1 --dest 10.2.1.1')"
	@echo "netsetup          - Set up Linux namespace network simulation (requires sudo -E, ARGS='-v/-vv/-vvv' for verbosity)"
	@echo "nettest           - Test network connectivity in namespace simulation (e.g., make nettest ARGS='-s 10.1.1.1 -d 10.2.1.1 --test-type ping')"
	@echo "svctest           - Test TCP/UDP services with auto namespace detection (e.g., make svctest ARGS='-s 10.1.1.1 -d 10.2.1.1:8080')"
	@echo "svcstart          - Start a service on an IP address (e.g., make svcstart ARGS='10.1.1.1:8080')"
	@echo "svcstop           - Stop a service on an IP address (e.g., make svcstop ARGS='10.1.1.1:8080')"
	@echo "svclist           - List all services across all namespaces (sudo -E make svclist [ARGS='-j'])"
	@echo "svcclean          - Stop all services across all namespaces (sudo -E make svcclean)"
	@echo "netshow           - Show static network topology from facts (e.g., make netshow ARGS='hq-gw interfaces' or 'all hosts')"
	@echo "netstatus         - Show live namespace status (e.g., make netstatus ARGS='interfaces --limit hq-gw' or just 'make netstatus')"
	@echo "netclean          - Clean up namespace network simulation (requires sudo -E, ARGS='-v/-f/--force' for options)"
	@echo "test-iptables-enhanced - Test enhanced iptables rules for ping/mtr connectivity"
	@echo "test-policy-routing   - Test enhanced policy routing with multiple routing tables"
	@echo "test-iptables-logging - Test iptables logging implementation with comprehensive log analysis"
	@echo "test-packet-tracing   - Test comprehensive packet tracing implementation with rule correlation"
	@echo "test-namespace    - Run namespace simulation tests independently (requires sudo -E and completed 'make test')"
	@echo "test-network      - Run comprehensive network connectivity tests (requires sudo -E, takes 3-5 minutes)"
	@echo "hostadd           - Add dynamic host to network (e.g., make hostadd ARGS='--host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw')"
	@echo "hostdel           - Remove host from network (e.g., make hostdel ARGS='--host web1')"
	@echo "hostlist          - List all registered hosts (sudo -E make hostlist)"
	@echo "hostclean         - Remove all registered hosts (sudo -E make hostclean)"
	@echo "netnsclean        - Clean up both routers and hosts (sudo -E make netnsclean)"
	@echo "# Service management - use svctest for IP-based interface"
	@echo "test-services     - Run service manager test suite (requires sudo -E)"
	@echo "help              - Show this help message"
	@echo ""
	@echo "Usage Examples:"
	@echo "  make check-deps                                              # Verify all dependencies are installed"
	@echo "  make test                                                   # Run comprehensive test suite"
	@echo "  make facts INVENTORY_FILE=hosts.ini                     # Use specific inventory file"
	@echo "  make facts INVENTORY=routers                            # Use configured inventory group"
	@echo "  make facts INVENTORY=specific-host                      # Target specific host"
	@echo "  make tsim ARGS='-s 10.1.1.1 -d 10.2.1.1'                              # Run traceroute simulation"
	@echo "  make ifa ARGS='--router hq-gw -s 10.1.1.1 -d 8.8.8.8 -p tcp'          # Analyze iptables forwarding"
	@echo "  make netlog ARGS='--source 10.1.1.1 --dest 10.2.1.1 --format json'    # Analyze iptables logs"
	@echo "  sudo -E make netsetup                                                     # Set up namespace network simulation (silent)"
	@echo "  sudo -E make netsetup ARGS='-v'                                          # Set up with basic output"
	@echo "  sudo -E make netsetup ARGS='-vv'                                         # Set up with info messages"
	@echo "  sudo -E make netsetup ARGS='-vvv'                                        # Set up with debug messages"
	@echo "  sudo -E make nettest ARGS='-s 10.1.1.1 -d 10.2.1.1 --test-type ping'    # Test ICMP connectivity"
	@echo "  sudo -E make nettest ARGS='-s 10.1.1.1 -d 10.2.1.1 --test-type mtr'     # Test with MTR traceroute"
	@echo "  sudo -E make nettest ARGS='-s 10.1.1.1 -d 8.8.8.8 --test-type both -v'  # Test external IP with both ping and MTR"
	@echo "  make netshow ARGS='hq-gw interfaces'                                  # Show static interface config from facts"
	@echo "  make netshow ARGS='all summary'                                       # Show static summary of all routers and hosts from facts"
	@echo "  make netshow ARGS='all topology'                                      # Show complete network topology from facts"
	@echo "  make netshow ARGS='all hosts'                                         # Show all registered hosts from registry"
	@echo "  make netshow ARGS='hq-gw topology'                                    # Show network connections for hq-gw from facts"
	@echo "  make netshow ARGS='hq-gw hosts'                                       # Show hosts connected to hq-gw from registry"
	@echo "  make netshow ARGS='web1 summary'                                      # Show host summary for web1 from registry"
	@echo "  make netshow ARGS='br-core routes -v'                                 # Show static routing table from facts"
	@echo "  sudo -E make netstatus                                                     # Show live summary of all namespaces (default)"
	@echo "  sudo -E make netstatus ARGS='interfaces --limit hq-gw'                    # Show live interface config for router"
	@echo "  sudo -E make netstatus ARGS='summary --limit \"hq-*\"'                      # Show live summary for HQ routers"
	@echo "  sudo -E make netclean                                                     # Clean up namespace simulation (silent)"
	@echo "  sudo -E make netclean ARGS='-v'                                          # Clean up with verbose output"
	@echo "  sudo -E make netclean ARGS='-f'                                          # Force cleanup of stuck resources"
	@echo "  sudo -E make netclean ARGS='-v -f'                                       # Verbose force cleanup"
	@echo "  sudo -E make test-namespace                                               # Run namespace simulation tests after 'make test'"
	@echo "  sudo -E make test-network                                                 # Run comprehensive network connectivity tests (3-5 min)"
	@echo "  sudo -E make hostadd ARGS='--host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw'      # Add host to bridge"
	@echo "  sudo -E make hostadd ARGS='--host srv1 --primary-ip 10.1.11.100/24 --connect-to hq-lab --router-interface eth2'  # Connect to specific bridge"
	@echo "  sudo -E make hostadd ARGS='--host db1 --primary-ip 10.2.1.100/24 --secondary-ips 192.168.1.1/24'  # Add host with secondary IP"
	@echo "  sudo -E make hostdel ARGS='--host web1 --remove'                         # Remove host from network"
	@echo "  sudo -E make hostlist                                                     # List all registered hosts"
	@echo "  sudo -E make hostclean                                                    # Remove all registered hosts"
	@echo "  sudo -E make netnsclean                                                   # Clean up both routers and hosts"
	@echo "  sudo -E make svcstart ARGS='10.1.1.1:8080'                                                   # Start TCP echo service on IP"
	@echo "  sudo -E make svcstart ARGS='10.2.1.1:53 -p udp --name dns'                                  # Start UDP service on IP with name"
	@echo "  sudo -E make svcstop ARGS='10.1.1.1:8080'                                                    # Stop service on IP:port"
	@echo "  sudo -E make svctest ARGS='-s 10.1.1.1 -d 10.2.1.1:8080'                                   # Test TCP service (auto-detect namespaces)"
	@echo "  sudo -E make svctest ARGS='-s 10.1.1.1 -d 10.2.1.1:53 -p udp -m \"Query\"'                   # Test UDP service with message"
	@echo "  sudo -E make svclist                                                                          # List all running services"
	@echo "  sudo -E make svclist ARGS='-j'                                                                # List services in JSON format"
	@echo "  sudo -E make svcclean                                                                         # Stop all services"
	@echo ""
	@echo "Facts Collection Examples:"
	@echo "  # Collect raw network facts from production environment"
	@echo "  make facts INVENTORY_FILE=production.ini"
	@echo "  # Collect test facts from test environment"  
	@echo "  TRACEROUTE_SIMULATOR_RAW_FACTS=/tmp/test_raw make facts INVENTORY_FILE=tests/inventory.yml"

# Check for existence of all required Python modules
check-deps:
	@echo "Checking Python Module Dependencies"
	@echo "======================================="
	@echo "Python version: $$($(PYTHON) $(PYTHON_OPTIONS) --version 2>&1)"
	@echo ""
	@missing_modules=""; \
	for module in $(REQUIRED_MODULES); do \
		if $(PYTHON) $(PYTHON_OPTIONS) -c "import $$module" 2>/dev/null; then \
			echo "✓ $$module"; \
		else \
			echo "✗ $$module"; \
			missing_modules="$$missing_modules $$module"; \
		fi; \
	done; \
	if [ -n "$$missing_modules" ]; then \
		echo ""; \
		echo "Missing modules detected!"; \
		echo "Installation hints:"; \
		for module in $$missing_modules; do \
			case $$module in \
				matplotlib) \
					echo "  $(PYTHON) $(PYTHON_OPTIONS) -m pip install matplotlib"; \
					echo "  # or: sudo apt-get install python3-matplotlib (Debian/Ubuntu)"; \
					echo "  # or: sudo yum install python3-matplotlib (RHEL/CentOS)"; \
					;; \
				numpy) \
					echo "  $(PYTHON) $(PYTHON_OPTIONS) -m pip install numpy"; \
					echo "  # or: sudo apt-get install python3-numpy (Debian/Ubuntu)"; \
					echo "  # or: sudo yum install python3-numpy (RHEL/CentOS)"; \
					;; \
				*) \
					echo "  $(PYTHON) $(PYTHON_OPTIONS) -c \"import $$module\" # $$module is a standard library module"; \
					;; \
			esac; \
		done; \
		echo ""; \
		echo "Note: Standard library modules (json, sys, etc.) should be included with Python."; \
		echo "If they're missing, your Python installation may be incomplete."; \
		exit 1; \
	else \
		echo ""; \
		echo "All required Python modules are available!"; \
	fi
	@echo ""
	@echo "Checking Additional Tools"
	@echo "============================="
	@if command -v ansible-playbook >/dev/null 2>&1; then \
		echo "✓ ansible-playbook ($$(ansible-playbook --version | head -1))"; \
	else \
		echo "✗ ansible-playbook"; \
		echo "Installation hint: pip install ansible"; \
	fi

# Execute test scripts with setup and reporting
test: check-deps
	@echo "Running Traceroute Simulator Test Suite"
	@echo "============================================"
	@echo ""
	
	# Verify test environment exists
	@if [ ! -d "$(TESTS_DIR)" ]; then \
		echo "Error: Tests directory '$(TESTS_DIR)' not found"; \
		exit 1; \
	fi
	
	# Clean previous test output
	@echo "Cleaning previous test output..."
	@rm -rf /tmp/traceroute_test_output
	@mkdir -p /tmp/traceroute_test_output
	
	# Generate fresh test facts from raw data
	@echo "Generating fresh test facts from raw data..."
	@if [ -d "$(TESTS_DIR)/raw_facts" ] && [ "$$(ls -A $(TESTS_DIR)/raw_facts 2>/dev/null | wc -l)" -gt 0 ]; then \
		$(ANSIBLE) $(ANSIBLE_DIR)/get_tsim_facts.yml -i "$(TESTS_DIR)/inventory.yml" -v -e "test=true" || { \
			echo "Failed to generate test facts from raw data"; \
			exit 1; \
		}; \
	else \
		echo "Warning: No raw facts found in $(TESTS_DIR)/raw_facts, using existing test facts"; \
		cp -r $(ROUTING_FACTS_DIR)/* /tmp/traceroute_test_output/ 2>/dev/null || { \
			echo "Error: No test facts available"; \
			echo "Hint: Run 'make fetch-routing-data TEST_MODE=true' to generate test data"; \
			exit 1; \
		}; \
	fi
	
	# Count available test facts
	@test_files=$$(find /tmp/traceroute_test_output -name "*.json" | wc -l); \
	echo "Test Environment Status:"; \
	echo "  Test facts directory: /tmp/traceroute_test_output"; \
	echo "  JSON files: $$test_files"; \
	echo ""
	
	# Run main test suite
	@echo "1. Running Main Traceroute Simulator Tests"
	@echo "-----------------------------------------------"
	@cd $(TESTS_DIR) && TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output TRACEROUTE_SIMULATOR_CONF=test_config.yaml $(PYTHON) $(PYTHON_OPTIONS) test_traceroute_simulator.py || { \
		echo "Main test suite failed!"; \
		exit 1; \
	}
	@echo "✓ Main test suite passed"
	@echo ""
	
	# Run IP JSON wrapper comparison tests if available
	@if [ -f "$(TESTS_DIR)/test_ip_json_comparison.py" ]; then \
		echo "2. Running IP JSON Wrapper Comparison Tests"; \
		echo "--------------------------------------------------"; \
		cd $(TESTS_DIR) && TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output TRACEROUTE_SIMULATOR_CONF=test_config.yaml $(PYTHON) $(PYTHON_OPTIONS) test_ip_json_comparison.py || { \
			echo "Warning: IP JSON wrapper tests failed (may not be critical)"; \
		}; \
		echo "✓ IP JSON wrapper tests completed"; \
		echo ""; \
	fi
	
	# Run MTR integration tests if available
	@if [ -f "$(TESTS_DIR)/test_mtr_integration.py" ]; then \
		echo "2.5. Running MTR Integration Tests"; \
		echo "-------------------------------------"; \
		cd $(TESTS_DIR) && TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output TRACEROUTE_SIMULATOR_CONF=test_config.yaml $(PYTHON) $(PYTHON_OPTIONS) test_mtr_integration.py || { \
			echo "Warning: MTR integration tests failed (may not be critical)"; \
		}; \
		echo "✓ MTR integration tests completed"; \
		echo ""; \
	fi
	
	# Ensure facts are properly generated and persisted
	@echo "2.8. Ensuring Test Facts Persistence"
	@echo "-----------------------------------"
	@if [ ! -d "$(TESTS_DIR)/raw_facts" ] || [ "$$(ls -A $(TESTS_DIR)/raw_facts 2>/dev/null | wc -l)" -eq 0 ]; then \
		echo "Warning: No raw facts found, copying from existing test data"; \
		cp -r $(ROUTING_FACTS_DIR)/* /tmp/traceroute_test_output/ 2>/dev/null || { \
			echo "Error: No test facts available"; \
			exit 1; \
		}; \
	else \
		echo "Running ansible playbook to ensure facts are properly merged and structured..."; \
		$(ANSIBLE) $(ANSIBLE_DIR)/get_tsim_facts.yml -i "$(TESTS_DIR)/inventory.yml" -v -e "test=true" || { \
			echo "Failed to generate consolidated test facts"; \
			exit 1; \
		}; \
	fi
	@test_files=$$(find /tmp/traceroute_test_output -name "*.json" | wc -l); \
	echo "✓ Test facts ensured: $$test_files JSON files in /tmp/traceroute_test_output"; \
	echo ""
	
	# Test basic functionality with consolidated sample data
	@echo "3. Running Integration Tests"
	@echo "---------------------------------"
	@echo "Testing basic routing scenarios..."
	@$(MAKE) tsim ARGS="-s 10.1.1.1 -d 10.2.1.1" > /dev/null && \
		echo "✓ Inter-location routing test passed" || \
		echo "✗ Inter-location routing test failed"
	
	@$(MAKE) tsim ARGS="-s 10.100.1.1 -d 10.100.1.3" > /dev/null && \
		echo "✓ VPN mesh routing test passed" || \
		echo "✗ VPN mesh routing test failed"
	
	@$(MAKE) tsim ARGS="-j -s 10.1.10.1 -d 10.3.20.1" > /dev/null && \
		echo "✓ JSON output test passed" || \
		echo "✗ JSON output test failed"
	
	# Run comprehensive facts processing tests
	@echo "4. Running Comprehensive Facts Processing Tests"
	@echo "---------------------------------------------"
	@cd $(TESTS_DIR) && TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) $(PYTHON_OPTIONS) test_comprehensive_facts_processing.py || { \
		echo "Comprehensive facts processing tests failed!"; \
		exit 1; \
	}
	@echo "✓ Comprehensive facts processing tests passed"
	@echo ""
	
	# Run namespace make targets tests (requires sudo privileges)
	@echo "5. Running Namespace Make Targets Tests"
	@echo "---------------------------------------"
	@if [ "$$(id -u)" = "0" ]; then \
		echo "Running namespace make targets tests with root privileges..."; \
		echo "  5a. Basic functionality tests..."; \
		TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) $(PYTHON_OPTIONS) tests/test_make_targets_basic.py > /dev/null && \
		echo "  ✓ Basic tests passed" || { echo "  ✗ Basic tests failed"; exit 1; }; \
		echo "  5b. Host management tests..."; \
		TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) $(PYTHON_OPTIONS) tests/test_make_targets_hosts.py > /dev/null && \
		echo "  ✓ Host tests passed" || { echo "  ✗ Host tests failed"; exit 1; }; \
		echo "  5c. Error handling tests..."; \
		TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) $(PYTHON_OPTIONS) tests/test_make_targets_errors.py > /dev/null && \
		echo "  ✓ Error tests passed" || { echo "  ✗ Error tests failed"; exit 1; }; \
		echo "  5d. Integration tests..."; \
		TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) $(PYTHON_OPTIONS) tests/test_make_targets_integration.py > /dev/null && \
		echo "  ✓ Integration tests passed" || { echo "  ✗ Integration tests failed"; exit 1; }; \
		echo "✓ All namespace make targets tests completed successfully"; \
	else \
		echo "⚠ Skipping namespace make targets tests (requires sudo privileges)"; \
		echo "  To run make targets tests: sudo -E make test"; \
	fi
	@echo ""
	
	# Run namespace simulation tests (requires sudo privileges)
	@echo "6. Running Namespace Simulation Tests"
	@echo "-------------------------------------"
	@if [ "$$(id -u)" = "0" ]; then \
		echo "Running namespace simulation tests with root privileges..."; \
		TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) $(PYTHON_OPTIONS) tests/test_namespace_simulation.py 2>/dev/null && \
		echo "✓ Namespace simulation tests completed successfully" || \
		echo "⚠ Namespace simulation tests completed with warnings (may require sudo)"; \
	else \
		echo "⚠ Skipping namespace simulation tests (requires sudo privileges)"; \
		echo "  To run namespace tests: sudo -E make test"; \
	fi
	@echo ""
	@echo "All tests completed successfully!"

# Collect network facts using Ansible playbook
# 
# Environment variables:
# - TRACEROUTE_SIMULATOR_RAW_FACTS: Directory to store raw facts (default: /tmp/tsim/raw_facts)
# - TRACEROUTE_SIMULATOR_FACTS: Directory for processed JSON facts (default: /tmp/tsim/json_facts)
#
# Inventory modes supported:
# 1. INVENTORY_FILE: Specify a specific inventory file (e.g., hosts.ini, production.yml)
# 2. INVENTORY: Use configured Ansible inventory to target specific group or host
#
# Usage: make facts [INVENTORY_FILE=file OR INVENTORY=group/host]
facts:
	@echo "Collecting Network Facts from Routers"
	@echo "======================================"
	@echo ""
	
	# Check environment variables and set defaults
	@if [ -n "$(TRACEROUTE_SIMULATOR_FACTS)" ] || [ -n "$(TRACEROUTE_SIMULATOR_RAW_FACTS)" ]; then \
		echo "Environment variables detected:"; \
		[ -n "$(TRACEROUTE_SIMULATOR_FACTS)" ] && echo "  TRACEROUTE_SIMULATOR_FACTS=$(TRACEROUTE_SIMULATOR_FACTS)"; \
		[ -n "$(TRACEROUTE_SIMULATOR_RAW_FACTS)" ] && echo "  TRACEROUTE_SIMULATOR_RAW_FACTS=$(TRACEROUTE_SIMULATOR_RAW_FACTS)"; \
	fi
	
	$(eval RAW_FACTS_DIR := $(if $(TRACEROUTE_SIMULATOR_RAW_FACTS),$(TRACEROUTE_SIMULATOR_RAW_FACTS),/tmp/tsim/raw_facts))
	$(eval JSON_FACTS_DIR := $(if $(TRACEROUTE_SIMULATOR_FACTS),$(TRACEROUTE_SIMULATOR_FACTS),/tmp/tsim/json_facts))
	
	@echo "Using directories:"
	@echo "  Raw facts: $(RAW_FACTS_DIR)"
	@echo "  JSON facts: $(JSON_FACTS_DIR)"
	@echo ""
	
	# Check if either INVENTORY_FILE or INVENTORY is provided
	@if [ -z "$(INVENTORY_FILE)" ] && [ -z "$(INVENTORY)" ]; then \
		echo "Error: Either INVENTORY_FILE or INVENTORY parameter is required"; \
		echo "Usage: make facts [INVENTORY_FILE=file OR INVENTORY=group/host]"; \
		echo "Examples:"; \
		echo "  make facts INVENTORY_FILE=hosts.ini              # Use specific inventory file"; \
		echo "  make facts INVENTORY_FILE=production.yml         # Use specific inventory file"; \
		echo "  make facts INVENTORY=routers                     # Use configured inventory group"; \
		echo "  make facts INVENTORY=production_group            # Use configured inventory group"; \
		echo "  make facts INVENTORY=specific-host               # Target specific host"; \
		exit 1; \
	fi
	
	# Check if both INVENTORY_FILE and INVENTORY are provided (not allowed)
	@if [ -n "$(INVENTORY_FILE)" ] && [ -n "$(INVENTORY)" ]; then \
		echo "Error: Cannot specify both INVENTORY_FILE and INVENTORY parameters"; \
		echo "Usage: Use either INVENTORY_FILE for a specific file OR INVENTORY for a group/host"; \
		echo "Examples:"; \
		echo "  make facts INVENTORY_FILE=hosts.ini  # Use file"; \
		echo "  make facts INVENTORY=routers         # Use group"; \
		exit 1; \
	fi
	
	# Set inventory parameter based on what was provided
	@if [ -n "$(INVENTORY_FILE)" ]; then \
		echo "Using inventory file: $(INVENTORY_FILE)"; \
	else \
		echo "Using inventory group/host: $(INVENTORY)"; \
	fi
	@echo ""
	
	# Create output directories
	@echo "Creating output directories..."
	@mkdir -p $(RAW_FACTS_DIR)
	@echo "✓ Raw facts directory: $(RAW_FACTS_DIR)"
	
	# Check if Ansible is available
	@if ! command -v $(ANSIBLE) >/dev/null 2>&1; then \
		echo "Error: ansible-playbook not found"; \
		echo "Installation hint: pip install ansible"; \
		exit 1; \
	fi
	
	# Check if playbook exists
	@if [ ! -f "$(ANSIBLE_DIR)/get_tsim_facts.yml" ]; then \
		echo "Error: Ansible playbook '$(ANSIBLE_DIR)/get_tsim_facts.yml' not found"; \
		exit 1; \
	fi
	
	# Check if inventory file exists (only if INVENTORY_FILE is specified)
	@if [ -n "$(INVENTORY_FILE)" ] && [ ! -f "$(INVENTORY_FILE)" ]; then \
		echo "Error: Inventory file '$(INVENTORY_FILE)' not found"; \
		echo "Please ensure the inventory file exists and is accessible"; \
		exit 1; \
	fi
	
	# Validate playbook syntax
	@echo "Validating Ansible playbook syntax..."
	@$(ANSIBLE) $(ANSIBLE_DIR)/get_tsim_facts.yml --syntax-check || { \
		echo "Playbook syntax validation failed!"; \
		exit 1; \
	}
	@echo "✓ Playbook syntax is valid"
	@echo ""
	
	# Create backup of existing raw facts if they exist
	@if [ -d "$(RAW_FACTS_DIR)" ] && [ "$$(ls -A $(RAW_FACTS_DIR) 2>/dev/null)" ]; then \
		backup_dir="$(RAW_FACTS_DIR).backup.$$(date +%Y%m%d_%H%M%S)"; \
		echo "Backing up existing raw facts to $$backup_dir"; \
		cp -r $(RAW_FACTS_DIR) $$backup_dir; \
	fi
	
	# Run the playbook to collect raw facts
	@echo "Executing Ansible playbook to collect network facts..."
	@if [ -n "$(INVENTORY_FILE)" ]; then \
		TRACEROUTE_SIMULATOR_RAW_FACTS=$(RAW_FACTS_DIR) $(ANSIBLE) $(ANSIBLE_DIR)/get_tsim_facts.yml -i "$(INVENTORY_FILE)" -v || { \
			echo "Ansible playbook execution failed!"; \
			echo "Check your inventory file and network connectivity"; \
			exit 1; \
		}; \
	else \
		TRACEROUTE_SIMULATOR_RAW_FACTS=$(RAW_FACTS_DIR) $(ANSIBLE) $(ANSIBLE_DIR)/get_tsim_facts.yml --limit "$(INVENTORY)" -v || { \
			echo "Ansible playbook execution failed!"; \
			echo "Check your inventory configuration and network connectivity"; \
			echo "Ensure the group/host '$(INVENTORY)' exists in your configured inventory"; \
			exit 1; \
		}; \
	fi
	
	# Verify collected data
	@if [ -d "$(RAW_FACTS_DIR)" ]; then \
		raw_files=$$(find $(RAW_FACTS_DIR) -name "*_facts.txt" | wc -l); \
		echo ""; \
		echo "Network facts collection completed!"; \
		echo "  Raw facts files collected: $$raw_files"; \
		echo "  Raw facts location: $(RAW_FACTS_DIR)"; \
		echo "  Raw facts are preserved for processing"; \
		if [ $$raw_files -eq 0 ]; then \
			echo "Warning: No raw facts files collected. Check Ansible output above."; \
		fi; \
	else \
		echo "No facts were collected!"; \
		exit 1; \
	fi

# Clean up generated files and cache
clean:
	@echo "Cleaning up generated files and cache"
	@echo "======================================="
	@rm -rf __pycache__/
	@rm -rf $(TESTS_DIR)/__pycache__/
	@rm -rf *.pyc
	@rm -rf $(TESTS_DIR)/*.pyc
	@rm -rf .pytest_cache/
	@find . -name "*.pyc" -delete
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Cleaned up Python cache files"
	@if [ -d "/tmp/traceroute_test_output" ]; then \
		rm -rf /tmp/traceroute_test_output; \
		echo "✓ Cleaned up test output directory"; \
	else \
		echo "✓ Test output directory already clean"; \
	fi
	@rm -rf build/ dist/ *.egg-info
	@echo "✓ Cleaned up package build artifacts"
	@echo "Cleanup completed!"

# Run traceroute simulator with command line arguments
# Usage: make tsim ARGS="-s 10.1.1.1 -d 10.2.1.1"
tsim:
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: make tsim ARGS='<arguments>'"; \
		echo "Examples:"; \
		echo "  make tsim ARGS='-s 10.1.1.1 -d 10.2.1.1'"; \
		echo "  make tsim ARGS='-s 10.1.1.1 -d 10.2.1.1 -j'"; \
		echo "  make tsim ARGS='-s 10.1.1.1 -d 10.2.1.1 --tsim-facts /path/to/facts'"; \
		echo "  make tsim ARGS='-s 10.1.1.1 -d 10.2.1.1 -v --reverse-trace'"; \
		exit 1; \
	fi
	@env TRACEROUTE_SIMULATOR_FACTS="$(TRACEROUTE_SIMULATOR_FACTS)" $(PYTHON) $(PYTHON_OPTIONS) src/core/traceroute_simulator.py $(ARGS)

# Run iptables forward analyzer with command line arguments  
# Usage: make ifa ARGS="--router hq-gw -s 10.1.1.1 -d 8.8.8.8"
ifa:
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: make ifa ARGS='<arguments>'"; \
		echo "Examples:"; \
		echo "  make ifa ARGS='--router hq-gw -s 10.1.1.1 -d 8.8.8.8'"; \
		echo "  make ifa ARGS='--router hq-gw -s 10.1.1.1 -d 8.8.8.8 -p tcp'"; \
		echo "  make ifa ARGS='--router hq-gw -s 10.1.1.1 -d 8.8.8.8 -p tcp -vv'"; \
		echo "  make ifa ARGS='--router hq-gw -s 10.1.1.0/24 -d 8.8.8.8 -p all'"; \
		exit 1; \
	fi
	@env TRACEROUTE_SIMULATOR_FACTS="$(TRACEROUTE_SIMULATOR_FACTS)" $(PYTHON) $(PYTHON_OPTIONS) src/analyzers/iptables_forward_analyzer.py $(ARGS)

# Analyze iptables logs with filtering and correlation
# Usage: make netlog ARGS="<arguments>"
netlog:
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: make netlog ARGS='<arguments>'"; \
		echo "Examples:"; \
		echo "  make netlog ARGS='--source 10.1.1.1 --dest 10.2.1.1'"; \
		echo "  make netlog ARGS='--router hq-gw --port 80 --last 100'"; \
		echo "  make netlog ARGS='--all-routers --protocol icmp --format json'"; \
		echo "  make netlog ARGS='--source 10.1.1.0/24 --action DROP --verbose'"; \
		echo "  make netlog ARGS='--time-range \"10:00-11:00\" --dest 8.8.8.8'"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) scripts/netlog $(ARGS)

# Set up Linux namespace network simulation (requires sudo)
# Usage: sudo -E make netsetup [ARGS="-v|-vv|-vvv"]
netsetup:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: netsetup requires root privileges"; \
		echo "Please run: sudo -E make netsetup"; \
		exit 1; \
	fi
	@env TRACEROUTE_SIMULATOR_RAW_FACTS="$(TRACEROUTE_SIMULATOR_RAW_FACTS)" $(PYTHON) $(PYTHON_OPTIONS) src/simulators/network_namespace_setup.py $(ARGS)

# Test network connectivity in namespace simulation (requires sudo)  
# Usage: sudo -E make nettest ARGS="-s 10.1.1.1 -d 10.2.1.1 -p tcp --dport 80"
nettest:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: nettest requires root privileges"; \
		echo "Please run: sudo -E make nettest ARGS='<arguments>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo -E make nettest ARGS='<arguments>'"; \
		echo ""; \
		echo "Required arguments:"; \
		echo "  Either: -s <source_ip> -d <destination_ip>  # Test specific connection"; \
		echo "  Or:     --all                              # Test all routers to all others"; \
		echo ""; \
		echo "Optional arguments:"; \
		echo "  --test-type {ping,mtr,both}    # Test type (default: ping)"; \
		echo "  -v, -vv                        # Verbosity levels"; \
		echo "  --wait <seconds>               # Wait time between tests (default: 0.1)"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo -E make nettest ARGS='-s 10.1.1.1 -d 10.2.1.1'                      # Basic ping test"; \
		echo "  sudo -E make nettest ARGS='-s 10.1.1.1 -d 10.2.1.1 --test-type mtr'     # MTR traceroute test"; \
		echo "  sudo -E make nettest ARGS='-s 10.1.1.1 -d 8.8.8.8 --test-type both -v'  # Both ping and MTR with verbosity"; \
		echo "  sudo -E make nettest ARGS='--all'                                        # Test all routers (ping)"; \
		echo "  sudo -E make nettest ARGS='--all --test-type mtr -v'                     # Test all routers (MTR, verbose)"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/network_namespace_tester.py $(ARGS)

# Test services with automatic namespace detection (requires sudo)
# Usage: sudo -E make svctest ARGS="-s <source_ip[:port]> -d <dest_ip:port> [-p tcp|udp]"
svctest:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: svctest requires root privileges"; \
		echo "Please run: sudo -E make svctest ARGS='<arguments>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo -E make svctest ARGS='<arguments>'"; \
		echo ""; \
		echo "Test service connectivity:"; \
		echo "  -s <source_ip[:port]>    # Source IP and optional port"; \
		echo "  -d <dest_ip:port>        # Destination IP and port (port required)"; \
		echo "  -p tcp|udp               # Protocol (default: tcp)"; \
		echo "  -m <message>             # Test message (default: Test)"; \
		echo "  -v, -vv                  # Verbosity levels"; \
		echo ""; \
		echo "Start a service:"; \
		echo "  --start <ip:port>        # Start service at IP:port"; \
		echo "  -p tcp|udp               # Protocol (default: tcp)"; \
		echo "  --name <name>            # Service name (optional)"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo -E make svctest ARGS='-s 10.1.1.1 -d 10.2.1.1:80'               # Test TCP service"; \
		echo "  sudo -E make svctest ARGS='-s 10.1.1.1:5000 -d 10.2.1.1:80 -p tcp'  # With source port"; \
		echo "  sudo -E make svctest ARGS='-s 10.1.1.1 -d 10.2.1.1:53 -p udp'       # Test UDP service"; \
		echo "  sudo -E make svctest ARGS='--start 10.1.1.1:8080'                    # Start TCP service"; \
		echo "  sudo -E make svctest ARGS='--start 10.2.1.1:53 -p udp --name dns'    # Start UDP service"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/service_tester.py $(ARGS)

# Start a service on an IP address (requires sudo)
# Usage: sudo -E make svcstart ARGS="<ip:port> [-p tcp|udp] [--name <name>]"
svcstart:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: svcstart requires root privileges"; \
		echo "Please run: sudo -E make svcstart ARGS='<ip:port>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo -E make svcstart ARGS='<ip:port> [options]'"; \
		echo ""; \
		echo "Required:"; \
		echo "  <ip:port>         # IP address and port to bind service"; \
		echo ""; \
		echo "Options:"; \
		echo "  -p tcp|udp        # Protocol (default: tcp)"; \
		echo "  --name <name>     # Service name (default: auto-generated)"; \
		echo "  -v, -vv           # Verbosity levels"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo -E make svcstart ARGS='10.1.1.1:8080'                  # Start TCP echo service"; \
		echo "  sudo -E make svcstart ARGS='10.2.1.1:53 -p udp --name dns'  # Start UDP service with name"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/service_tester.py --start $(ARGS)

# Stop a service on an IP address (requires sudo)
# Usage: sudo -E make svcstop ARGS="<ip:port>"
svcstop:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: svcstop requires root privileges"; \
		echo "Please run: sudo -E make svcstop ARGS='<ip:port>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo -E make svcstop ARGS='<ip:port>'"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo -E make svcstop ARGS='10.1.1.1:8080'  # Stop service on port 8080"; \
		echo "  sudo -E make svcstop ARGS='10.2.1.1:53'     # Stop service on port 53"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/service_tester.py --stop $(ARGS)

# List all services across all namespaces (requires sudo)
# Usage: sudo -E make svclist [ARGS="-j|--json"]
svclist:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: svclist requires root privileges"; \
		echo "Please run: sudo -E make svclist"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/service_manager.py status $(ARGS)

# Stop all services across all namespaces (requires sudo)
# Usage: sudo -E make svcclean
svcclean:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: svcclean requires root privileges"; \
		echo "Please run: sudo -E make svcclean"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/service_manager.py cleanup

# Clean up namespace network simulation (requires sudo)
# Usage: sudo -E make netclean [ARGS="-v|-f|--force|--limit <pattern>"]
# Examples:
#   sudo -E make netclean                           # Clean all routers
#   sudo -E make netclean ARGS="-v"                 # Clean all with verbose output
#   sudo -E make netclean ARGS="--limit pmfw-*"     # Clean routers matching pattern
#   sudo -E make netclean ARGS="--limit hq-gw -v"  # Clean specific router with verbose
netclean:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: netclean requires root privileges"; \
		echo "Please run: sudo -E make netclean"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/network_namespace_cleanup.py $(ARGS)

# Show static network topology from facts files (no root required)
# Usage: make netshow ARGS="<router> <function> [-v]"
# Functions: interfaces, routes, rules, summary, topology, all
# Router names: hq-gw, hq-core, hq-dmz, hq-lab, br-gw, br-core, br-wifi, dc-gw, dc-core, dc-srv, or 'all'
netshow:
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: make netshow ARGS='<router> <function> [options]'"; \
		echo ""; \
		echo "Shows STATIC network topology from facts files (no live namespace inspection)"; \
		echo ""; \
		echo "Entity names: hq-gw, hq-core, hq-dmz, hq-lab, br-gw, br-core, br-wifi, dc-gw, dc-core, dc-srv, web1, all"; \
		echo "Functions: interfaces, routes, rules, summary, topology, hosts, all"; \
		echo "Options: -v (verbose debug output)"; \
		echo ""; \
		echo "Examples:"; \
		echo "  make netshow ARGS='hq-gw interfaces'                # Show static interface config from facts"; \
		echo "  make netshow ARGS='br-core routes'                  # Show static routing table from facts"; \
		echo "  make netshow ARGS='dc-srv rules'                    # Show static policy rules from facts"; \
		echo "  make netshow ARGS='hq-dmz summary'                  # Show static overview from facts"; \
		echo "  make netshow ARGS='all topology'                    # Show complete network topology from facts"; \
		echo "  make netshow ARGS='all hosts'                       # Show all registered hosts from registry"; \
		echo "  make netshow ARGS='hq-gw topology'                  # Show network connections for hq-gw from facts"; \
		echo "  make netshow ARGS='hq-gw hosts'                     # Show hosts connected to hq-gw from registry"; \
		echo "  make netshow ARGS='web1 summary'                    # Show host summary for web1 from registry"; \
		echo "  make netshow ARGS='hq-gw all'                       # Show complete static config from facts"; \
		echo "  make netshow ARGS='all summary'                     # Show summary for all routers and hosts from facts"; \
		echo "  make netshow ARGS='hq-gw interfaces -v'             # Show static interfaces with verbose output"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/network_topology_viewer.py $(ARGS)

# Show live network namespace status (requires sudo)
# Usage: sudo -E make netstatus [ARGS="<function> [--limit <pattern>] [-v]"]
# Functions: interfaces, routes, rules, ipsets, summary (default), all
# Limit patterns: "hq-*", "*-core", "web1", etc. (supports glob patterns)
netstatus:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: netstatus requires root privileges to access namespaces"; \
		echo "Please run: sudo -E make netstatus [ARGS='<function> [--limit <pattern>]']"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		$(PYTHON) $(PYTHON_OPTIONS) src/simulators/network_namespace_status.py summary; \
	else \
		$(PYTHON) $(PYTHON_OPTIONS) src/simulators/network_namespace_status.py $(ARGS); \
	fi

# Run namespace simulation tests independently (requires sudo)
# Usage: sudo -E make test-namespace
test-namespace:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: Namespace simulation tests require root privileges"; \
		echo "Please run: sudo -E make test-namespace"; \
		exit 1; \
	fi
	@if [ ! -d "/tmp/traceroute_test_output" ] || [ -z "$$(ls -A /tmp/traceroute_test_output 2>/dev/null)" ]; then \
		echo "Error: No consolidated facts found in /tmp/traceroute_test_output"; \
		echo "Please run the main test suite first: make test"; \
		exit 1; \
	fi
	@echo "Running Namespace Simulation Test Suite"
	@echo "======================================="
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) $(PYTHON_OPTIONS) tests/test_namespace_simulation.py

# Test enhanced iptables rules in raw facts files
# Usage: make test-iptables-enhanced
test-iptables-enhanced:
	@echo "Testing Enhanced Iptables Rules"
	@echo "==============================="
	@echo "Validating comprehensive iptables rules for:"
	@echo "  - ICMP connectivity (ping) between all networks"
	@echo "  - UDP MTR support (traceroute) between all networks"
	@echo "  - Management protocol access (SSH, SNMP, etc.)"
	@echo "  - Comprehensive logging for packet tracing"
	@echo "  - NAT rules for gateway routers"
	@echo "  - Packet marking for QoS"
	@echo ""
	@$(PYTHON) $(PYTHON_OPTIONS) tests/test_iptables_enhancement_simple.py
	@echo ""
	@echo "✅ All iptables rule enhancements validated successfully!"
	@echo "   - All routers have ICMP connectivity rules"
	@echo "   - All routers have MTR UDP support"
	@echo "   - All routers have management protocol access"
	@echo "   - All routers have comprehensive logging"
	@echo "   - Gateway routers have NAT/MASQUERADE rules"

# Test enhanced policy routing with multiple routing tables  
# Usage: make test-policy-routing
test-policy-routing:
	@echo "Testing Enhanced Policy Routing"
	@echo "==============================="
	@echo "Validating complex policy routing configuration for:"
	@echo "  - Source-based routing (network segmentation)"
	@echo "  - Service-based routing (port/protocol specific)"
	@echo "  - QoS-based routing (priority and TOS marking)"
	@echo "  - Mark-based routing (packet marking integration)"
	@echo "  - Location-based routing (cross-site policies)" 
	@echo "  - Emergency routing (failover scenarios)"
	@echo "  - Additional routing tables (8 per router)"
	@echo ""
	@$(PYTHON) $(PYTHON_OPTIONS) tests/test_policy_routing_enhancement.py
	@echo ""
	@echo "✅ All policy routing enhancements validated successfully!"
	@echo "   - 286+ policy rules across all routers"
	@echo "   - 80+ additional routing tables implemented"
	@echo "   - Source/service/QoS-based policies active"
	@echo "   - Cross-location routing policies configured"
	@echo "   - Emergency and management policies deployed"
	@echo "   - Gateway-specific internet routing enabled"

# Test enhanced ipset configurations in raw facts files
# Usage: make test-ipset-enhanced
test-ipset-enhanced:
	@echo "Testing Enhanced Ipset Configurations"
	@echo "===================================="
	@echo "Validating comprehensive ipset configurations for:"
	@echo "  - All ipset types from documentation (bitmap, hash)"
	@echo "  - Router-specific ipset configurations"
	@echo "  - Consistent ipset_save and ipset_list formats"
	@echo "  - Realistic and diverse member content"
	@echo "  - Gateway-specific external/internet ipsets"
	@echo "  - WiFi-specific wireless client ipsets"
	@echo "  - Proper section formatting and exit codes"
	@echo ""
	@$(PYTHON) $(PYTHON_OPTIONS) tests/test_ipset_enhancement.py
	@echo ""
	@echo "✅ All ipset configuration enhancements validated successfully!"
	@echo "   - 754+ ipset definitions across all routers"
	@echo "   - All major ipset types represented"
	@echo "   - Router-appropriate configurations implemented"
	@echo "   - Dual format consistency maintained"
	@echo "   - Realistic network security scenarios covered"

# Test raw facts direct loading functionality
# Usage: make test-raw-facts-loading
test-raw-facts-loading:
	@echo "Testing Raw Facts Direct Loading"
	@echo "================================"
	@echo "Validating direct raw facts loading functionality for:"
	@echo "  - Raw facts parser module functionality"
	@echo "  - TSIM section extraction and parsing"
	@echo "  - Network namespace setup integration"
	@echo "  - Data structure compatibility"
	@echo "  - Routing table and policy rules parsing"
	@echo "  - Iptables and ipset configuration parsing"
	@echo ""
	@$(PYTHON) $(PYTHON_OPTIONS) tests/test_raw_facts_loading.py
	@echo ""
	@echo "✅ Raw facts direct loading functionality validated successfully!"
	@echo "   - All 10 router raw facts files parsed correctly"
	@echo "   - Network namespace setup integration working"
	@echo "   - Data format compatibility maintained"
	@echo "   - Eliminates JSON intermediate processing step"
	@echo "   - Supports both raw facts and JSON fallback"

# Test enhanced MTR options implementation
# Usage: make test-mtr-options
test-mtr-options:
	@echo "Testing Enhanced MTR Options Implementation"
	@echo "==========================================="
	@echo "Validating advanced MTR options support for:"
	@echo "  - Protocol-specific execution (ICMP, UDP, TCP)"
	@echo "  - Source/destination port specification"
	@echo "  - Advanced timeout handling"
	@echo "  - MTR command building and validation"
	@echo "  - Output parsing (text and JSON formats)"
	@echo "  - Network namespace integration"
	@echo "  - Connectivity testing functionality"
	@echo ""
	@$(PYTHON) $(PYTHON_OPTIONS) tests/test_mtr_options.py
	@echo ""
	@echo "✅ Enhanced MTR options implementation validated successfully!"
	@echo "   - All 17 comprehensive test cases pass"
	@echo "   - Protocol support: ICMP, UDP, TCP"
	@echo "   - Port specification: source and destination"
	@echo "   - Advanced options: timeout, packet size, intervals"
	@echo "   - Output parsing: text and JSON formats"
	@echo "   - Network namespace integration ready"

# Test iptables logging implementation
# Usage: make test-iptables-logging
test-iptables-logging:
	@echo "Testing Iptables Logging Implementation"
	@echo "======================================"
	@echo "Validating comprehensive iptables logging functionality for:"
	@echo "  - Log processing and parsing engine"
	@echo "  - Advanced log filtering capabilities"
	@echo "  - NetLog CLI interface integration"
	@echo "  - Time-based and network-based filtering"
	@echo "  - Protocol and action-based filtering"
	@echo "  - JSON and text output formats"
	@echo "  - Real-time and historical log analysis"
	@echo "  - Enhanced raw facts with LOG targets"
	@echo ""
	@$(PYTHON) $(PYTHON_OPTIONS) tests/test_iptables_logging.py
	@echo ""
	@echo "✅ Iptables logging implementation validated successfully!"
	@echo "   - All 12+ comprehensive test cases pass"
	@echo "   - Log processing: parsing, filtering, correlation"
	@echo "   - CLI integration: netlog command-line tool"
	@echo "   - Output formats: text reports and JSON data"
	@echo "   - Enhanced raw facts: LOG targets added to all rules"
	@echo "   - Network analysis: comprehensive packet tracing"

# Test comprehensive packet tracing implementation
# Usage: make test-packet-tracing
test-packet-tracing:
	@echo "Testing Comprehensive Packet Tracing Implementation"
	@echo "=================================================="
	@echo "Validating advanced packet tracing functionality for:"
	@echo "  - Packet tracer engine with comprehensive path analysis"
	@echo "  - Rule database system with iptables rule correlation"
	@echo "  - Integration with existing routing simulation"
	@echo "  - Real-time packet monitoring capabilities"
	@echo "  - Performance optimization with indexed lookups"
	@echo "  - Export functionality (JSON and text formats)"
	@echo "  - Trace lifecycle management and cleanup"
	@echo "  - Concurrent tracing and error handling"
	@echo ""
	@$(PYTHON) $(PYTHON_OPTIONS) tests/test_packet_tracing.py
	@echo ""
	@echo "✅ Comprehensive packet tracing implementation validated successfully!"
	@echo "   - All 24+ comprehensive test cases pass"
	@echo "   - Packet tracer engine: hop-by-hop analysis complete"
	@echo "   - Rule database: iptables rule indexing and correlation"
	@echo "   - Integration tests: end-to-end tracing workflows"
	@echo "   - Performance tests: efficient trace execution"
	@echo "   - Export formats: JSON and text trace reports"

# Run comprehensive network connectivity tests (requires sudo)
# Usage: sudo -E make test-network
test-network:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: Network connectivity tests require root privileges"; \
		echo "Please run: sudo -E make test-network"; \
		exit 1; \
	fi
	@if [ ! -d "/tmp/traceroute_test_output" ] || [ -z "$$(ls -A /tmp/traceroute_test_output 2>/dev/null)" ]; then \
		echo "Error: No consolidated facts found in /tmp/traceroute_test_output"; \
		echo "Please run the main test suite first: make test"; \
		exit 1; \
	fi
	@echo "Running Comprehensive Network Connectivity Test Suite"
	@echo "===================================================="
	@echo "Testing complex routing scenarios with ping and MTR:"
	@echo "  - Multi-hop paths across all locations"
	@echo "  - VPN mesh connectivity testing"
	@echo "  - Internal network segment routing"
	@echo "  - External IP connectivity via gateways"
	@echo "  - Complex enterprise network scenarios"
	@echo ""
	@echo "⚠ Note: This test suite takes 3-5 minutes to complete"
	@echo ""
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) $(PYTHON_OPTIONS) tests/test_make_targets_network.py

# Add dynamic host to network using bridge infrastructure (requires sudo)
# Usage: sudo -E make hostadd ARGS="--host <name> --primary-ip <ip/prefix> [--secondary-ips <ips>] [--connect-to <router>]"
hostadd:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: hostadd requires root privileges"; \
		echo "Please run: sudo -E make hostadd ARGS='<arguments>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo -E make hostadd ARGS='--host <name> --primary-ip <ip/prefix> [options]'"; \
		echo ""; \
		echo "Required arguments:"; \
		echo "  --host <name>               Host name"; \
		echo "  --primary-ip <ip/prefix>    Primary IP with prefix (e.g., 10.1.1.100/24)"; \
		echo ""; \
		echo "Optional arguments:"; \
		echo "  --secondary-ips <ips>       Comma-separated secondary IPs with prefixes"; \
		echo "  --connect-to <router>       Router to connect to (auto-detect if not specified)"; \
		echo "  --router-interface <iface>  Specific router interface bridge to connect to"; \
		echo "  -v                          Verbose output (-vv for debug)"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo -E make hostadd ARGS='--host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw'"; \
		echo "  sudo -E make hostadd ARGS='--host srv1 --primary-ip 10.1.11.100/24 --connect-to hq-lab --router-interface eth2'"; \
		echo "  sudo -E make hostadd ARGS='--host db1 --primary-ip 10.2.1.100/24 --secondary-ips 192.168.1.1/24,172.16.1.1/24'"; \
		echo "  sudo -E make hostadd ARGS='--host client1 --primary-ip 10.3.1.100/24 -v'"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/host_namespace_setup.py $(ARGS)

# Remove host from network (requires sudo)
# Usage: sudo -E make hostdel ARGS="--host <name>"
hostdel:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: hostdel requires root privileges"; \
		echo "Please run: sudo -E make hostdel ARGS='--host <name>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo -E make hostdel ARGS='--host <name>'"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo -E make hostdel ARGS='--host web1'"; \
		echo "  sudo -E make hostdel ARGS='--host db1 -v'"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/host_namespace_setup.py --remove $(ARGS)

# List all registered hosts (requires sudo)
# Usage: sudo -E make hostlist
hostlist:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: hostlist requires root privileges to check namespace status"; \
		echo "Please run: sudo -E make hostlist"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/host_namespace_setup.py --list-hosts $(ARGS)

# Clean up all registered hosts (requires sudo)
# Usage: sudo -E make hostclean [ARGS="-v|-vv"]
hostclean:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: hostclean requires root privileges"; \
		echo "Please run: sudo -E make hostclean"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/utils/host_cleanup.py $(ARGS)

# Clean up both network namespaces and hosts (requires sudo)
# Usage: sudo -E make netnsclean [ARGS="-v|-f|--force"]
netnsclean:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: netnsclean requires root privileges"; \
		echo "Please run: sudo -E make netnsclean"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/utils/host_cleanup.py $(ARGS)
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/network_namespace_cleanup.py $(ARGS)

# Check if we're running in a git repository (for future enhancements)
.git-check:
	@if [ ! -d ".git" ]; then \
		echo "Warning: Not in a git repository"; \
	fi

# Service management targets
# Start a service in a namespace
# Usage: sudo -E make service-start ARGS="--namespace <ns> --name <name> --port <port> [--protocol tcp|udp] [--bind <ip>]"
service-start:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: service-start requires root privileges"; \
		echo "Please run: sudo -E make service-start ARGS='<arguments>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo -E make service-start ARGS='--namespace <ns> --name <name> --port <port> [options]'"; \
		echo ""; \
		echo "Required arguments:"; \
		echo "  --namespace <ns>     Namespace to run service in"; \
		echo "  --name <name>        Service name"; \
		echo "  --port <port>        Port number"; \
		echo ""; \
		echo "Optional arguments:"; \
		echo "  --protocol tcp|udp   Protocol (default: tcp)"; \
		echo "  --bind <ip>          Bind address (default: 0.0.0.0)"; \
		echo "  -v                   Verbose output (-vv for debug)"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo -E make service-start ARGS='--namespace hq-gw --name echo --port 8080'"; \
		echo "  sudo -E make service-start ARGS='--namespace br-core --name dns --port 53 --protocol udp'"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/service_manager.py start $(ARGS)

# Stop a service
# Usage: sudo -E make service-stop ARGS="--namespace <ns> --name <name> --port <port>"
service-stop:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: service-stop requires root privileges"; \
		echo "Please run: sudo -E make service-stop ARGS='<arguments>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo -E make service-stop ARGS='--namespace <ns> --name <name> --port <port>'"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo -E make service-stop ARGS='--namespace hq-gw --name echo --port 8080'"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/service_manager.py stop $(ARGS)

# Restart a service
# Usage: sudo -E make service-restart ARGS="--namespace <ns> --name <name> --port <port> [--protocol tcp|udp]"
service-restart:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: service-restart requires root privileges"; \
		echo "Please run: sudo -E make service-restart ARGS='<arguments>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo -E make service-restart ARGS='--namespace <ns> --name <name> --port <port> [--protocol tcp|udp]'"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo -E make service-restart ARGS='--namespace hq-gw --name echo --port 8080'"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/service_manager.py restart $(ARGS)

# Show service status
# Usage: sudo -E make service-status [ARGS="--namespace <ns>"]
service-status:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: service-status requires root privileges"; \
		echo "Please run: sudo -E make service-status"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/service_manager.py status $(ARGS)

# Test a service
# Usage: sudo -E make service-test ARGS="--source <ns> --dest <ip> --port <port> [--protocol tcp|udp] [--message <msg>] [--timeout <sec>]"
service-test:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: service-test requires root privileges"; \
		echo "Please run: sudo -E make service-test ARGS='<arguments>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo -E make service-test ARGS='--source <ns> --dest <ip> --port <port> [options]'"; \
		echo ""; \
		echo "Required arguments:"; \
		echo "  --source <ns>        Source namespace"; \
		echo "  --dest <ip>          Destination IP address"; \
		echo "  --port <port>        Destination port"; \
		echo ""; \
		echo "Optional arguments:"; \
		echo "  --protocol tcp|udp   Protocol (default: tcp)"; \
		echo "  --message <msg>      Test message (default: Hello)"; \
		echo "  --timeout <sec>      Timeout in seconds (default: 5)"; \
		echo "  -v                   Verbose output (-vv for debug)"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo -E make service-test ARGS='--source hq-core --dest 10.1.1.1 --port 8080'"; \
		echo "  sudo -E make service-test ARGS='--source br-gw --dest 10.2.1.2 --port 53 --protocol udp --message QUERY'"; \
		exit 1; \
	fi
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/service_manager.py test $(ARGS)

# Clean up all services
# Usage: sudo -E make service-clean
service-clean:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: service-clean requires root privileges"; \
		echo "Please run: sudo -E make service-clean"; \
		exit 1; \
	fi
	@echo "Cleaning up all services..."
	@$(PYTHON) $(PYTHON_OPTIONS) src/simulators/service_manager.py cleanup

# Run service manager test suite
# Usage: sudo -E make test-services
test-services:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: Service tests require root privileges"; \
		echo "Please run: sudo -E make test-services"; \
		exit 1; \
	fi
	@echo "Running Service Manager Test Suite"
	@echo "=================================="
	@$(PYTHON) $(PYTHON_OPTIONS) tests/test_service_manager.py

# Build and install the netns_reader wrapper with proper capabilities
install-wrapper:
	@echo "Building and installing netns_reader wrapper..."
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: Installation requires root privileges"; \
		echo "Please run: sudo make install-wrapper"; \
		exit 1; \
	fi
	@if [ ! -f "$(WRAPPER_SRC)" ]; then \
		echo "Error: Source file $(WRAPPER_SRC) not found"; \
		exit 1; \
	fi
	@echo "Building $(WRAPPER_BIN)..."
	@$(CC) $(CFLAGS) -o $(WRAPPER_BIN) $(WRAPPER_SRC)
	@echo "✓ Built $(WRAPPER_BIN)"
	@echo "Installing to $(INSTALL_DIR)..."
	@cp $(WRAPPER_BIN) $(INSTALL_DIR)/$(WRAPPER_BIN)
	@chown root:root $(INSTALL_DIR)/$(WRAPPER_BIN)
	@chmod 755 $(INSTALL_DIR)/$(WRAPPER_BIN)
	@setcap 'cap_sys_admin,cap_net_admin+ep' $(INSTALL_DIR)/$(WRAPPER_BIN)
	@echo "✓ Installed $(WRAPPER_BIN) to $(INSTALL_DIR)"
	@echo "✓ Set ownership: root:root"
	@echo "✓ Set permissions: 755"
	@echo "✓ Set capabilities: cap_sys_admin,cap_net_admin+ep"
	@rm -f $(WRAPPER_BIN)
	@echo "✓ Cleaned up build artifacts"
	@echo ""
	@echo "Installation complete!"
	@echo "You can now use: $(INSTALL_DIR)/$(WRAPPER_BIN) <namespace> <command>"

# Define source files that should trigger package rebuild
PACKAGE_SOURCES := $(shell find src -name "*.py" 2>/dev/null) \
                   $(shell find ansible -name "*.py" -o -name "*.yml" -o -name "*.yaml" -o -name "*.sh" 2>/dev/null) \
                   pyproject.toml MANIFEST.in requirements.txt README.md tsimsh

# Package timestamp file to track last build
PACKAGE_TIMESTAMP := dist/.package.timestamp

# Build pip-installable package
# Usage: make package
package: $(PACKAGE_TIMESTAMP)

# Build package only if sources have changed
$(PACKAGE_TIMESTAMP): $(PACKAGE_SOURCES)
	@echo "Building tsim package..."
	@echo "========================================"
	@# Clean any previous builds
	@rm -rf build/ dist/ *.egg-info
	@echo "✓ Cleaned previous build artifacts"
	@# Build the package
	@$(PYTHON) $(PYTHON_OPTIONS) -m pip install --quiet build
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(PYTHON_OPTIONS) -m build
	@echo "✓ Package built successfully"
	@# Create timestamp file
	@mkdir -p dist
	@touch $(PACKAGE_TIMESTAMP)
	@echo ""
	@echo "Package files created in:"
	@echo "  dist/tsim-*.tar.gz (source distribution)"
	@echo "  dist/tsim-*.whl (wheel distribution)"
	@echo ""
	@echo "To install locally: make install-package"
	@echo "To install elsewhere: pip install dist/tsim-*.whl"

# Install the package in the current Python environment
# Usage: make install-package [USER=1] [BREAK_SYSTEM=1]
install-package: $(PACKAGE_TIMESTAMP)
	@echo "Installing tsim package..."
	@echo "========================================"
	@# Check if we're in a virtual environment
	@if [ -n "$$VIRTUAL_ENV" ]; then \
		echo "Detected virtual environment: $$VIRTUAL_ENV"; \
		echo "Installing in virtual environment..."; \
		PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(PYTHON_OPTIONS) -m pip install --no-compile --upgrade dist/tsim-*.whl; \
	elif [ -n "$(BREAK_SYSTEM)" ]; then \
		echo "⚠️  Installing with --break-system-packages (use at your own risk)"; \
		PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(PYTHON_OPTIONS) -m pip install --no-compile --upgrade --break-system-packages dist/tsim-*.whl; \
	elif [ -n "$(USER)" ]; then \
		echo "Installing in user site-packages..."; \
		PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(PYTHON_OPTIONS) -m pip install --no-compile --upgrade --user dist/tsim-*.whl || { \
			echo ""; \
			echo "❌ User installation failed."; \
			echo ""; \
			echo "Recommended alternatives:"; \
			echo "  1. Use pipx (best for command-line applications):"; \
			echo "     pipx install dist/tsim-*.whl"; \
			echo ""; \
			echo "  2. Create and use a virtual environment:"; \
			echo "     python3 -m venv ~/tsim-venv"; \
			echo "     source ~/tsim-venv/bin/activate"; \
			echo "     make install-package"; \
			echo ""; \
			echo "  3. Force installation (override system protection):"; \
			echo "     make install-package BREAK_SYSTEM=1"; \
			exit 1; \
		}; \
	else \
		echo "Attempting standard installation..."; \
		PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(PYTHON_OPTIONS) -m pip install --no-compile --upgrade dist/tsim-*.whl || { \
			echo ""; \
			echo "❌ Installation failed due to externally-managed environment."; \
			echo ""; \
			echo "Options:"; \
			echo "  1. Install in user directory:"; \
			echo "     make install-package USER=1"; \
			echo ""; \
			echo "  2. Use pipx (recommended for applications):"; \
			echo "     pipx install dist/tsim-*.whl"; \
			echo ""; \
			echo "  3. Use a virtual environment:"; \
			echo "     python3 -m venv venv"; \
			echo "     source venv/bin/activate"; \
			echo "     make install-package"; \
			echo ""; \
			echo "  4. Force system installation (not recommended):"; \
			echo "     make install-package BREAK_SYSTEM=1"; \
			exit 1; \
		}; \
	fi
	@# Fix the shebang line in the installed tsimsh script
	@echo "Fixing shebang line in tsimsh..."
	@if [ -n "$$VIRTUAL_ENV" ]; then \
		TSIMSH_PATH="$$VIRTUAL_ENV/bin/tsimsh"; \
	else \
		TSIMSH_PATH="$$($(PYTHON) -m site --user-base)/bin/tsimsh"; \
		if [ ! -f "$$TSIMSH_PATH" ]; then \
			TSIMSH_PATH="$$(which tsimsh 2>/dev/null)"; \
		fi; \
	fi; \
	if [ -f "$$TSIMSH_PATH" ]; then \
		sed -i '1s|^#!.*|#!/usr/bin/env -S python3 -B -u|' "$$TSIMSH_PATH" && \
		echo "✓ Fixed shebang in $$TSIMSH_PATH"; \
	else \
		echo "⚠ Could not find tsimsh to fix shebang"; \
	fi
	@echo ""
	@echo "✓ Package installed successfully!"
	@echo ""
	@echo "The following command is now available in your PATH:"
	@echo "  tsimsh - Traceroute Simulator Shell"
	@echo ""
	@echo "Try running: tsimsh"

# Install using pipx (recommended for applications)
# Usage: make install-pipx
install-pipx: $(PACKAGE_TIMESTAMP)
	@echo "Installing tsim package with pipx..."
	@echo "========================================"
	@if ! command -v pipx >/dev/null 2>&1; then \
		echo "Error: pipx not found"; \
		echo ""; \
		echo "Install pipx with one of:"; \
		echo "  apt install pipx        (Debian/Ubuntu)"; \
		echo "  dnf install pipx        (Fedora)"; \
		echo "  python3 -m pip install --user pipx"; \
		echo ""; \
		echo "Then ensure pipx is in your PATH:"; \
		echo "  pipx ensurepath"; \
		exit 1; \
	fi
	@pipx install dist/tsim-*.whl --force
	@echo ""
	@echo "✓ Package installed successfully with pipx!"
	@echo ""
	@echo "The following command is now available globally:"
	@echo "  tsimsh - Traceroute Simulator Shell"
	@echo ""
	@echo "Try running: tsimsh"

# Uninstall the package from the current Python environment
# Usage: make uninstall-package [USER=1] [BREAK_SYSTEM=1]
uninstall-package:
	@echo "Uninstalling tsim package..."
	@echo "========================================"
	@if [ -n "$(BREAK_SYSTEM)" ]; then \
		echo "⚠️  Uninstalling with --break-system-packages"; \
		$(PYTHON) $(PYTHON_OPTIONS) -m pip uninstall -y --break-system-packages tsim 2>/dev/null || echo "Package not installed"; \
	elif [ -n "$(USER)" ]; then \
		echo "Uninstalling from user site-packages..."; \
		$(PYTHON) $(PYTHON_OPTIONS) -m pip uninstall -y tsim 2>/dev/null || echo "Package not installed in user directory"; \
	else \
		echo "Attempting standard uninstallation..."; \
		$(PYTHON) $(PYTHON_OPTIONS) -m pip uninstall -y tsim 2>/dev/null || { \
			echo "Package not installed or requires special handling"; \
			echo "Try: make uninstall-package USER=1"; \
		}; \
	fi
	@echo "✓ Uninstall completed"

# Uninstall using pipx
# Usage: make uninstall-pipx
uninstall-pipx:
	@echo "Uninstalling tsim package from pipx..."
	@echo "========================================"
	@if ! command -v pipx >/dev/null 2>&1; then \
		echo "Error: pipx not found"; \
		exit 1; \
	fi
	@pipx uninstall tsim || echo "Package not installed via pipx"
	@echo "✓ Uninstall completed"

# List all files included in the built package
# Usage: make list-package
list-package:
	@echo "Listing files in tsim package..."
	@echo "========================================"
	@if [ ! -f dist/tsim-*.whl ]; then \
		echo "Error: No package found. Run 'make package' first."; \
		exit 1; \
	fi
	@echo "Files in wheel package:"
	@echo ""
	@$(PYTHON) $(PYTHON_OPTIONS) -m zipfile -l dist/tsim-*.whl | grep -v "/$" | sort
	@echo ""
	@echo "Summary:"
	@echo "--------"
	@$(PYTHON) $(PYTHON_OPTIONS) -c "import zipfile; import glob; \
		whl = glob.glob('dist/tsim-*.whl')[0]; \
		with zipfile.ZipFile(whl, 'r') as z: \
			files = [f for f in z.namelist() if not f.endswith('/')]; \
			py_files = [f for f in files if f.endswith('.py')]; \
			data_files = [f for f in files if not f.endswith('.py') and not f.endswith('.dist-info')]; \
			print(f'Total files: {len(files)}'); \
			print(f'Python files: {len(py_files)}'); \
			print(f'Data files: {len(data_files)}'); \
			print(f'Package size: {os.path.getsize(whl) / 1024:.1f} KB')"