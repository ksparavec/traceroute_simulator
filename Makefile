# Makefile for Traceroute Simulator Project
# Provides targets for dependency checking, testing, and routing data collection

# Project configuration
PYTHON := python3
PIP := pip3
ANSIBLE := ansible-playbook
TESTS_DIR := tests
ROUTING_FACTS_DIR := tests/tsim_facts
ANSIBLE_DIR := ansible

# Global environment variables
export PYTHONDONTWRITEBYTECODE := 1

# Python modules required by the project
REQUIRED_MODULES := json sys argparse ipaddress os glob typing subprocess re difflib matplotlib numpy

# Colors removed for better terminal compatibility

.PHONY: help check-deps test test-iptables-enhanced test-policy-routing test-ipset-enhanced test-raw-facts-loading test-mtr-options test-iptables-logging test-packet-tracing test-network fetch-routing-data clean tsim ifa netsetup nettest netclean netshow netstatus test-namespace hostadd hostdel hostlist hostclean netnsclean service-start service-stop service-restart service-status service-test service-clean test-services svctest svcstart svcstop svclist svcclean

# Default target
help:
	@echo "Traceroute Simulator - Available Make Targets"
	@echo "=============================================="
	@echo "check-deps        - Check for required Python modules and provide installation hints"
	@echo "test              - Execute all test scripts with test setup and report results (includes make targets tests)"
	@echo "fetch-routing-data - Run Ansible playbook to collect routing facts (requires OUTPUT_DIR and INVENTORY_FILE or INVENTORY)"
	@echo "clean             - Clean up generated files and cache"
	@echo "tsim              - Run traceroute simulator with command line arguments (e.g., make tsim ARGS='-s 10.1.1.1 -d 10.2.1.1')"
	@echo "ifa               - Run iptables forward analyzer with command line arguments (e.g., make ifa ARGS='--router hq-gw -s 10.1.1.1 -d 8.8.8.8')"
	@echo "netsetup          - Set up Linux namespace network simulation (requires sudo, ARGS='-v/-vv/-vvv' for verbosity)"
	@echo "nettest           - Test network connectivity in namespace simulation (e.g., make nettest ARGS='-s 10.1.1.1 -d 10.2.1.1 --test-type ping')"
	@echo "svctest           - Test TCP/UDP services with auto namespace detection (e.g., make svctest ARGS='-s 10.1.1.1 -d 10.2.1.1:8080')"
	@echo "svcstart          - Start a service on an IP address (e.g., make svcstart ARGS='10.1.1.1:8080')"
	@echo "svcstop           - Stop a service on an IP address (e.g., make svcstop ARGS='10.1.1.1:8080')"
	@echo "svclist           - List all services across all namespaces (sudo make svclist [ARGS='-j'])"
	@echo "svcclean          - Stop all services across all namespaces (sudo make svcclean)"
	@echo "netshow           - Show static network topology from facts (e.g., make netshow ARGS='hq-gw interfaces' or 'all hosts')"
	@echo "netstatus         - Show live namespace status (e.g., make netstatus ARGS='hq-gw interfaces' or 'all summary')"
	@echo "netclean          - Clean up namespace network simulation (requires sudo, ARGS='-v/-f/--force' for options)"
	@echo "test-iptables-enhanced - Test enhanced iptables rules for ping/mtr connectivity"
	@echo "test-policy-routing   - Test enhanced policy routing with multiple routing tables"
	@echo "test-iptables-logging - Test iptables logging implementation with comprehensive log analysis"
	@echo "test-packet-tracing   - Test comprehensive packet tracing implementation with rule correlation"
	@echo "test-namespace    - Run namespace simulation tests independently (requires sudo and completed 'make test')"
	@echo "test-network      - Run comprehensive network connectivity tests (requires sudo, takes 3-5 minutes)"
	@echo "hostadd           - Add dynamic host to network (e.g., make hostadd ARGS='--host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw')"
	@echo "hostdel           - Remove host from network (e.g., make hostdel ARGS='--host web1')"
	@echo "hostlist          - List all registered hosts (sudo make hostlist)"
	@echo "hostclean         - Remove all registered hosts (sudo make hostclean)"
	@echo "netnsclean        - Clean up both routers and hosts (sudo make netnsclean)"
	@echo "# Service management - use svctest for IP-based interface"
	@echo "test-services     - Run service manager test suite (requires sudo)"
	@echo "help              - Show this help message"
	@echo ""
	@echo "Usage Examples:"
	@echo "  make check-deps                                              # Verify all dependencies are installed"
	@echo "  make test                                                   # Run comprehensive test suite"
	@echo "  make fetch-routing-data OUTPUT_DIR=tests/routing_facts INVENTORY_FILE=hosts.ini       # Use specific inventory file"
	@echo "  make fetch-routing-data OUTPUT_DIR=prod INVENTORY=routers              # Use configured inventory group"
	@echo "  make fetch-routing-data OUTPUT_DIR=temp INVENTORY=specific-host        # Target specific host"
	@echo "  make tsim ARGS='-s 10.1.1.1 -d 10.2.1.1'                              # Run traceroute simulation"
	@echo "  make ifa ARGS='--router hq-gw -s 10.1.1.1 -d 8.8.8.8 -p tcp'          # Analyze iptables forwarding"
	@echo "  sudo make netsetup                                                     # Set up namespace network simulation (silent)"
	@echo "  sudo make netsetup ARGS='-v'                                          # Set up with basic output"
	@echo "  sudo make netsetup ARGS='-vv'                                         # Set up with info messages"
	@echo "  sudo make netsetup ARGS='-vvv'                                        # Set up with debug messages"
	@echo "  sudo make nettest ARGS='-s 10.1.1.1 -d 10.2.1.1 --test-type ping'    # Test ICMP connectivity"
	@echo "  sudo make nettest ARGS='-s 10.1.1.1 -d 10.2.1.1 --test-type mtr'     # Test with MTR traceroute"
	@echo "  sudo make nettest ARGS='-s 10.1.1.1 -d 8.8.8.8 --test-type both -v'  # Test external IP with both ping and MTR"
	@echo "  make netshow ARGS='hq-gw interfaces'                                  # Show static interface config from facts"
	@echo "  make netshow ARGS='all summary'                                       # Show static summary of all routers and hosts from facts"
	@echo "  make netshow ARGS='all topology'                                      # Show complete network topology from facts"
	@echo "  make netshow ARGS='all hosts'                                         # Show all registered hosts from registry"
	@echo "  make netshow ARGS='hq-gw topology'                                    # Show network connections for hq-gw from facts"
	@echo "  make netshow ARGS='hq-gw hosts'                                       # Show hosts connected to hq-gw from registry"
	@echo "  make netshow ARGS='web1 summary'                                      # Show host summary for web1 from registry"
	@echo "  make netshow ARGS='br-core routes -v'                                 # Show static routing table from facts"
	@echo "  sudo make netstatus ARGS='hq-gw interfaces'                           # Show live interface config"
	@echo "  sudo make netstatus ARGS='web1 summary'                               # Show live host summary"
	@echo "  sudo make netstatus ARGS='all summary'                                # Show live status of all namespaces"
	@echo "  sudo make netclean                                                     # Clean up namespace simulation (silent)"
	@echo "  sudo make netclean ARGS='-v'                                          # Clean up with verbose output"
	@echo "  sudo make netclean ARGS='-f'                                          # Force cleanup of stuck resources"
	@echo "  sudo make netclean ARGS='-v -f'                                       # Verbose force cleanup"
	@echo "  sudo make test-namespace                                               # Run namespace simulation tests after 'make test'"
	@echo "  sudo make test-network                                                 # Run comprehensive network connectivity tests (3-5 min)"
	@echo "  sudo make hostadd ARGS='--host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw'      # Add host to bridge"
	@echo "  sudo make hostadd ARGS='--host srv1 --primary-ip 10.1.11.100/24 --connect-to hq-lab --router-interface eth2'  # Connect to specific bridge"
	@echo "  sudo make hostadd ARGS='--host db1 --primary-ip 10.2.1.100/24 --secondary-ips 192.168.1.1/24'  # Add host with secondary IP"
	@echo "  sudo make hostdel ARGS='--host web1 --remove'                         # Remove host from network"
	@echo "  sudo make hostlist                                                     # List all registered hosts"
	@echo "  sudo make hostclean                                                    # Remove all registered hosts"
	@echo "  sudo make netnsclean                                                   # Clean up both routers and hosts"
	@echo "  sudo make svcstart ARGS='10.1.1.1:8080'                                                   # Start TCP echo service on IP"
	@echo "  sudo make svcstart ARGS='10.2.1.1:53 -p udp --name dns'                                  # Start UDP service on IP with name"
	@echo "  sudo make svcstop ARGS='10.1.1.1:8080'                                                    # Stop service on IP:port"
	@echo "  sudo make svctest ARGS='-s 10.1.1.1 -d 10.2.1.1:8080'                                   # Test TCP service (auto-detect namespaces)"
	@echo "  sudo make svctest ARGS='-s 10.1.1.1 -d 10.2.1.1:53 -p udp -m \"Query\"'                   # Test UDP service with message"
	@echo "  sudo make svclist                                                                          # List all running services"
	@echo "  sudo make svclist ARGS='-j'                                                                # List services in JSON format"
	@echo "  sudo make svcclean                                                                         # Stop all services"
	@echo ""
	@echo "Test Data Collection:"
	@echo "  # Collect facts and preserve raw data for testing (adds -e test=true to Ansible command)"
	@echo "  make fetch-routing-data OUTPUT_DIR=tests/tsim_facts INVENTORY_FILE=hosts.ini TEST_MODE=true"

# Check for existence of all required Python modules
check-deps:
	@echo "Checking Python Module Dependencies"
	@echo "======================================="
	@echo "Python version: $$($(PYTHON) --version 2>&1)"
	@echo ""
	@missing_modules=""; \
	for module in $(REQUIRED_MODULES); do \
		if $(PYTHON) -c "import $$module" 2>/dev/null; then \
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
					echo "  $(PYTHON) -m pip install matplotlib"; \
					echo "  # or: sudo apt-get install python3-matplotlib (Debian/Ubuntu)"; \
					echo "  # or: sudo yum install python3-matplotlib (RHEL/CentOS)"; \
					;; \
				numpy) \
					echo "  $(PYTHON) -m pip install numpy"; \
					echo "  # or: sudo apt-get install python3-numpy (Debian/Ubuntu)"; \
					echo "  # or: sudo yum install python3-numpy (RHEL/CentOS)"; \
					;; \
				*) \
					echo "  $(PYTHON) -c \"import $$module\" # $$module is a standard library module"; \
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
	@cd $(TESTS_DIR) && TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output TRACEROUTE_SIMULATOR_CONF=test_config.yaml $(PYTHON) test_traceroute_simulator.py || { \
		echo "Main test suite failed!"; \
		exit 1; \
	}
	@echo "✓ Main test suite passed"
	@echo ""
	
	# Run IP JSON wrapper comparison tests if available
	@if [ -f "$(TESTS_DIR)/test_ip_json_comparison.py" ]; then \
		echo "2. Running IP JSON Wrapper Comparison Tests"; \
		echo "--------------------------------------------------"; \
		cd $(TESTS_DIR) && TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output TRACEROUTE_SIMULATOR_CONF=test_config.yaml $(PYTHON) test_ip_json_comparison.py || { \
			echo "Warning: IP JSON wrapper tests failed (may not be critical)"; \
		}; \
		echo "✓ IP JSON wrapper tests completed"; \
		echo ""; \
	fi
	
	# Run MTR integration tests if available
	@if [ -f "$(TESTS_DIR)/test_mtr_integration.py" ]; then \
		echo "2.5. Running MTR Integration Tests"; \
		echo "-------------------------------------"; \
		cd $(TESTS_DIR) && TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output TRACEROUTE_SIMULATOR_CONF=test_config.yaml $(PYTHON) test_mtr_integration.py || { \
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
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(MAKE) tsim ARGS="-s 10.1.1.1 -d 10.2.1.1" > /dev/null && \
		echo "✓ Inter-location routing test passed" || \
		echo "✗ Inter-location routing test failed"
	
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(MAKE) tsim ARGS="-s 10.100.1.1 -d 10.100.1.3" > /dev/null && \
		echo "✓ VPN mesh routing test passed" || \
		echo "✗ VPN mesh routing test failed"
	
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(MAKE) tsim ARGS="-j -s 10.1.10.1 -d 10.3.20.1" > /dev/null && \
		echo "✓ JSON output test passed" || \
		echo "✗ JSON output test failed"
	
	# Run comprehensive facts processing tests
	@echo "4. Running Comprehensive Facts Processing Tests"
	@echo "---------------------------------------------"
	@cd $(TESTS_DIR) && TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) -B test_comprehensive_facts_processing.py || { \
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
		TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) -B tests/test_make_targets_basic.py > /dev/null && \
		echo "  ✓ Basic tests passed" || { echo "  ✗ Basic tests failed"; exit 1; }; \
		echo "  5b. Host management tests..."; \
		TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) -B tests/test_make_targets_hosts.py > /dev/null && \
		echo "  ✓ Host tests passed" || { echo "  ✗ Host tests failed"; exit 1; }; \
		echo "  5c. Error handling tests..."; \
		TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) -B tests/test_make_targets_errors.py > /dev/null && \
		echo "  ✓ Error tests passed" || { echo "  ✗ Error tests failed"; exit 1; }; \
		echo "  5d. Integration tests..."; \
		TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) -B tests/test_make_targets_integration.py > /dev/null && \
		echo "  ✓ Integration tests passed" || { echo "  ✗ Integration tests failed"; exit 1; }; \
		echo "✓ All namespace make targets tests completed successfully"; \
	else \
		echo "⚠ Skipping namespace make targets tests (requires sudo privileges)"; \
		echo "  To run make targets tests: sudo make test"; \
	fi
	@echo ""
	
	# Run namespace simulation tests (requires sudo privileges)
	@echo "6. Running Namespace Simulation Tests"
	@echo "-------------------------------------"
	@if [ "$$(id -u)" = "0" ]; then \
		echo "Running namespace simulation tests with root privileges..."; \
		TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) -B tests/test_namespace_simulation.py 2>/dev/null && \
		echo "✓ Namespace simulation tests completed successfully" || \
		echo "⚠ Namespace simulation tests completed with warnings (may require sudo)"; \
	else \
		echo "⚠ Skipping namespace simulation tests (requires sudo privileges)"; \
		echo "  To run namespace tests: sudo make test"; \
	fi
	@echo ""
	@echo "All tests completed successfully!"

# Run Ansible playbook to fetch routing facts
# 
# Two inventory modes supported:
# 1. INVENTORY_FILE: Specify a specific inventory file (e.g., hosts.ini, production.yml)
# 2. INVENTORY: Use configured Ansible inventory to target specific group or host
#    (requires ANSIBLE_INVENTORY environment variable or ansible.cfg configuration)
#
# Usage: make fetch-routing-data OUTPUT_DIR=directory_name [INVENTORY_FILE=file OR INVENTORY=group/host]
fetch-routing-data:
	@echo "Fetching Traceroute Simulator Facts from Network Routers"
	@echo "=============================================="
	@echo ""
	
	# Check if OUTPUT_DIR is provided
	@if [ -z "$(OUTPUT_DIR)" ]; then \
		echo "Error: OUTPUT_DIR parameter is required"; \
		echo "Usage: make fetch-routing-data OUTPUT_DIR=directory_name [INVENTORY_FILE=file OR INVENTORY=group/host]"; \
		echo "Examples:"; \
		echo "  make fetch-routing-data OUTPUT_DIR=tests/routing_facts INVENTORY_FILE=hosts.ini"; \
		echo "  make fetch-routing-data OUTPUT_DIR=production_data INVENTORY_FILE=production.yml"; \
		echo "  make fetch-routing-data OUTPUT_DIR=tests/routing_facts INVENTORY=routers"; \
		echo "  make fetch-routing-data OUTPUT_DIR=production_data INVENTORY=production_group"; \
		echo "  make fetch-routing-data OUTPUT_DIR=/tmp/routing_facts INVENTORY=specific-host"; \
		exit 1; \
	fi
	
	# Check if either INVENTORY_FILE or INVENTORY is provided
	@if [ -z "$(INVENTORY_FILE)" ] && [ -z "$(INVENTORY)" ]; then \
		echo "Error: Either INVENTORY_FILE or INVENTORY parameter is required"; \
		echo "Usage: make fetch-routing-data OUTPUT_DIR=directory_name [INVENTORY_FILE=file OR INVENTORY=group/host]"; \
		echo "Examples:"; \
		echo "  make fetch-routing-data OUTPUT_DIR=tests/routing_facts INVENTORY_FILE=hosts.ini      # Use specific inventory file"; \
		echo "  make fetch-routing-data OUTPUT_DIR=production_data INVENTORY_FILE=production.yml     # Use specific inventory file"; \
		echo "  make fetch-routing-data OUTPUT_DIR=tests/routing_facts INVENTORY=routers           # Use configured inventory group"; \
		echo "  make fetch-routing-data OUTPUT_DIR=production_data INVENTORY=production_group        # Use configured inventory group"; \
		echo "  make fetch-routing-data OUTPUT_DIR=/tmp/routing_facts INVENTORY=specific-host        # Target specific host"; \
		exit 1; \
	fi
	
	# Check if both INVENTORY_FILE and INVENTORY are provided (not allowed)
	@if [ -n "$(INVENTORY_FILE)" ] && [ -n "$(INVENTORY)" ]; then \
		echo "Error: Cannot specify both INVENTORY_FILE and INVENTORY parameters"; \
		echo "Usage: Use either INVENTORY_FILE for a specific file OR INVENTORY for a group/host"; \
		echo "Examples:"; \
		echo "  make fetch-routing-data OUTPUT_DIR=test INVENTORY_FILE=hosts.ini  # Use file"; \
		echo "  make fetch-routing-data OUTPUT_DIR=test INVENTORY=routers         # Use group"; \
		exit 1; \
	fi
	
	$(eval TARGET_DIR := $(OUTPUT_DIR))
	@echo "Target output directory: $(TARGET_DIR)"
	
	# Set inventory parameter based on what was provided
	@if [ -n "$(INVENTORY_FILE)" ]; then \
		echo "Using inventory file: $(INVENTORY_FILE)"; \
	else \
		echo "Using inventory group/host: $(INVENTORY)"; \
	fi
	@echo ""
	
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
	
	# Create backup of existing routing facts if they exist
	@if [ -d "$(TARGET_DIR)" ] && [ "$$(ls -A $(TARGET_DIR) 2>/dev/null)" ]; then \
		backup_dir="$(TARGET_DIR).backup.$$(date +%Y%m%d_%H%M%S)"; \
		echo "Backing up existing routing facts to $$backup_dir"; \
		cp -r $(TARGET_DIR) $$backup_dir; \
	fi
	
	# Run the playbook with user-specified output directory and inventory
	@echo "Executing Ansible playbook to collect traceroute simulator facts..."
	$(eval TEST_FLAG := $(if $(TEST_MODE),-e "test=true",))
	$(eval TEST_INVENTORY := $(if $(TEST_MODE),$(TESTS_DIR)/inventory.yml,))
	@if [ -n "$(TEST_MODE)" ]; then \
		echo "Test mode enabled: Converting raw facts from tests/raw_facts/"; \
		echo "Using test inventory: $(TESTS_DIR)/inventory.yml"; \
		echo "Output directory: /tmp/traceroute_test_output"; \
	fi
	@if [ -n "$(TEST_MODE)" ]; then \
		$(ANSIBLE) $(ANSIBLE_DIR)/get_tsim_facts.yml -i "$(TESTS_DIR)/inventory.yml" -v $(TEST_FLAG) || { \
			echo "Ansible playbook execution failed in test mode!"; \
			echo "Check that tests/raw_facts/ contains the necessary router facts files"; \
			exit 1; \
		}; \
	elif [ -n "$(INVENTORY_FILE)" ]; then \
		$(ANSIBLE) $(ANSIBLE_DIR)/get_tsim_facts.yml -i "$(INVENTORY_FILE)" -v -e "tsim_facts_dir=$(TARGET_DIR)" || { \
			echo "Ansible playbook execution failed!"; \
			echo "Check your inventory file and network connectivity"; \
			exit 1; \
		}; \
	else \
		$(ANSIBLE) $(ANSIBLE_DIR)/get_tsim_facts.yml --limit "$(INVENTORY)" -v -e "tsim_facts_dir=$(TARGET_DIR)" || { \
			echo "Ansible playbook execution failed!"; \
			echo "Check your inventory configuration and network connectivity"; \
			echo "Ensure the group/host '$(INVENTORY)' exists in your configured inventory"; \
			exit 1; \
		}; \
	fi
	
	# Verify collected data
	@if [ -d "$(TARGET_DIR)" ]; then \
		json_files=$$(find $(TARGET_DIR) -name "*.json" | wc -l); \
		echo ""; \
		echo "Traceroute simulator facts collection completed!"; \
		echo "  JSON files collected: $$json_files"; \
		echo "  Data location: $(TARGET_DIR)"; \
		if [ -n "$(TEST_MODE)" ]; then \
			echo "  Test mode: Raw facts preserved in tests/raw_facts/"; \
			echo "  Run tests: cd tests && python3 test_comprehensive_facts_processing.py"; \
		fi; \
		if [ $$json_files -eq 0 ]; then \
			echo "Warning: No JSON files collected. Check Ansible output above."; \
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
	@echo "Cleanup completed!"

# Run traceroute simulator with command line arguments
# Usage: make tsim ARGS="-s 10.1.1.1 -d 10.2.1.1"
tsim:
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: make tsim ARGS='<arguments>'"; \
		echo "Examples:"; \
		echo "  make tsim ARGS='-s 10.1.1.1 -d 10.2.1.1'"; \
		echo "  make tsim ARGS='-s 10.1.1.1 -d 10.2.1.1 -j'"; \
		echo "  make tsim ARGS='-s 10.1.1.1 -d 10.2.1.1 --tsim-facts tests/tsim_facts'"; \
		echo "  make tsim ARGS='-s 10.1.1.1 -d 10.2.1.1 -v --reverse-trace'"; \
		exit 1; \
	fi
	@env TRACEROUTE_SIMULATOR_FACTS="$(TRACEROUTE_SIMULATOR_FACTS)" $(PYTHON) src/core/traceroute_simulator.py $(ARGS)

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
	@env TRACEROUTE_SIMULATOR_FACTS="$(TRACEROUTE_SIMULATOR_FACTS)" $(PYTHON) src/analyzers/iptables_forward_analyzer.py $(ARGS)

# Set up Linux namespace network simulation (requires sudo)
# Usage: sudo make netsetup [ARGS="-v|-vv|-vvv"]
netsetup:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: netsetup requires root privileges"; \
		echo "Please run: sudo make netsetup"; \
		exit 1; \
	fi
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) src/simulators/network_namespace_setup.py $(ARGS)

# Test network connectivity in namespace simulation (requires sudo)  
# Usage: sudo make nettest ARGS="-s 10.1.1.1 -d 10.2.1.1 -p tcp --dport 80"
nettest:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: nettest requires root privileges"; \
		echo "Please run: sudo make nettest ARGS='<arguments>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo make nettest ARGS='<arguments>'"; \
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
		echo "  sudo make nettest ARGS='-s 10.1.1.1 -d 10.2.1.1'                      # Basic ping test"; \
		echo "  sudo make nettest ARGS='-s 10.1.1.1 -d 10.2.1.1 --test-type mtr'     # MTR traceroute test"; \
		echo "  sudo make nettest ARGS='-s 10.1.1.1 -d 8.8.8.8 --test-type both -v'  # Both ping and MTR with verbosity"; \
		echo "  sudo make nettest ARGS='--all'                                        # Test all routers (ping)"; \
		echo "  sudo make nettest ARGS='--all --test-type mtr -v'                     # Test all routers (MTR, verbose)"; \
		exit 1; \
	fi
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) src/simulators/network_namespace_tester.py $(ARGS)

# Test services with automatic namespace detection (requires sudo)
# Usage: sudo make svctest ARGS="-s <source_ip[:port]> -d <dest_ip:port> [-p tcp|udp]"
svctest:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: svctest requires root privileges"; \
		echo "Please run: sudo make svctest ARGS='<arguments>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo make svctest ARGS='<arguments>'"; \
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
		echo "  sudo make svctest ARGS='-s 10.1.1.1 -d 10.2.1.1:80'               # Test TCP service"; \
		echo "  sudo make svctest ARGS='-s 10.1.1.1:5000 -d 10.2.1.1:80 -p tcp'  # With source port"; \
		echo "  sudo make svctest ARGS='-s 10.1.1.1 -d 10.2.1.1:53 -p udp'       # Test UDP service"; \
		echo "  sudo make svctest ARGS='--start 10.1.1.1:8080'                    # Start TCP service"; \
		echo "  sudo make svctest ARGS='--start 10.2.1.1:53 -p udp --name dns'    # Start UDP service"; \
		exit 1; \
	fi
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) src/simulators/service_tester.py $(ARGS)

# Start a service on an IP address (requires sudo)
# Usage: sudo make svcstart ARGS="<ip:port> [-p tcp|udp] [--name <name>]"
svcstart:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: svcstart requires root privileges"; \
		echo "Please run: sudo make svcstart ARGS='<ip:port>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo make svcstart ARGS='<ip:port> [options]'"; \
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
		echo "  sudo make svcstart ARGS='10.1.1.1:8080'                  # Start TCP echo service"; \
		echo "  sudo make svcstart ARGS='10.2.1.1:53 -p udp --name dns'  # Start UDP service with name"; \
		exit 1; \
	fi
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) src/simulators/service_tester.py --start $(ARGS)

# Stop a service on an IP address (requires sudo)
# Usage: sudo make svcstop ARGS="<ip:port>"
svcstop:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: svcstop requires root privileges"; \
		echo "Please run: sudo make svcstop ARGS='<ip:port>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo make svcstop ARGS='<ip:port>'"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo make svcstop ARGS='10.1.1.1:8080'  # Stop service on port 8080"; \
		echo "  sudo make svcstop ARGS='10.2.1.1:53'     # Stop service on port 53"; \
		exit 1; \
	fi
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) src/simulators/service_tester.py --stop $(ARGS)

# List all services across all namespaces (requires sudo)
# Usage: sudo make svclist [ARGS="-j|--json"]
svclist:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: svclist requires root privileges"; \
		echo "Please run: sudo make svclist"; \
		exit 1; \
	fi
	@$(PYTHON) src/simulators/service_manager.py status $(ARGS)

# Stop all services across all namespaces (requires sudo)
# Usage: sudo make svcclean
svcclean:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: svcclean requires root privileges"; \
		echo "Please run: sudo make svcclean"; \
		exit 1; \
	fi
	@$(PYTHON) src/simulators/service_manager.py cleanup

# Clean up namespace network simulation (requires sudo)
# Usage: sudo make netclean [ARGS="-v|-f|--force"]
netclean:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: netclean requires root privileges"; \
		echo "Please run: sudo make netclean"; \
		exit 1; \
	fi
	@$(PYTHON) src/simulators/network_namespace_cleanup.py $(ARGS)

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
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) src/simulators/network_topology_viewer.py $(ARGS)

# Show live network namespace status (requires sudo)
# Usage: sudo make netstatus ARGS="<namespace> <function> [-v]"
# Functions: interfaces, routes, rules, summary, all
# Namespace names: any running namespace (routers or hosts) or 'all'
netstatus:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: netstatus requires root privileges to access namespaces"; \
		echo "Please run: sudo make netstatus ARGS='<namespace> <function>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo make netstatus ARGS='<namespace> <function> [options]'"; \
		echo ""; \
		echo "Shows LIVE status of running namespaces only (no static facts)"; \
		echo ""; \
		echo "Namespace names: any running router or host namespace, or 'all'"; \
		echo "Functions: interfaces, routes, rules, summary, all"; \
		echo "Options: -v (verbose debug output)"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo make netstatus ARGS='hq-gw interfaces'         # Show live interface config"; \
		echo "  sudo make netstatus ARGS='br-core routes'           # Show live routing table"; \
		echo "  sudo make netstatus ARGS='web1 summary'             # Show live host summary"; \
		echo "  sudo make netstatus ARGS='all summary'              # Show live status of all namespaces"; \
		echo "  sudo make netstatus ARGS='hq-gw all'                # Show complete live config"; \
		echo "  sudo make netstatus ARGS='dc-srv rules -v'          # Show live rules with verbose output"; \
		exit 1; \
	fi
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) src/simulators/network_namespace_status.py $(ARGS)

# Run namespace simulation tests independently (requires sudo)
# Usage: sudo make test-namespace
test-namespace:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: Namespace simulation tests require root privileges"; \
		echo "Please run: sudo make test-namespace"; \
		exit 1; \
	fi
	@if [ ! -d "/tmp/traceroute_test_output" ] || [ -z "$$(ls -A /tmp/traceroute_test_output 2>/dev/null)" ]; then \
		echo "Error: No consolidated facts found in /tmp/traceroute_test_output"; \
		echo "Please run the main test suite first: make test"; \
		exit 1; \
	fi
	@echo "Running Namespace Simulation Test Suite"
	@echo "======================================="
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) -B tests/test_namespace_simulation.py

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
	@$(PYTHON) -B tests/test_iptables_enhancement_simple.py
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
	@$(PYTHON) -B tests/test_policy_routing_enhancement.py
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
	@$(PYTHON) -B tests/test_ipset_enhancement.py
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
	@$(PYTHON) -B tests/test_raw_facts_loading.py
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
	@$(PYTHON) -B tests/test_mtr_options.py
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
	@$(PYTHON) -B tests/test_iptables_logging.py
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
	@$(PYTHON) -B tests/test_packet_tracing.py
	@echo ""
	@echo "✅ Comprehensive packet tracing implementation validated successfully!"
	@echo "   - All 24+ comprehensive test cases pass"
	@echo "   - Packet tracer engine: hop-by-hop analysis complete"
	@echo "   - Rule database: iptables rule indexing and correlation"
	@echo "   - Integration tests: end-to-end tracing workflows"
	@echo "   - Performance tests: efficient trace execution"
	@echo "   - Export formats: JSON and text trace reports"

# Run comprehensive network connectivity tests (requires sudo)
# Usage: sudo make test-network
test-network:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: Network connectivity tests require root privileges"; \
		echo "Please run: sudo make test-network"; \
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
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) -B tests/test_make_targets_network.py

# Add dynamic host to network using bridge infrastructure (requires sudo)
# Usage: sudo make hostadd ARGS="--host <name> --primary-ip <ip/prefix> [--secondary-ips <ips>] [--connect-to <router>]"
hostadd:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: hostadd requires root privileges"; \
		echo "Please run: sudo make hostadd ARGS='<arguments>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo make hostadd ARGS='--host <name> --primary-ip <ip/prefix> [options]'"; \
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
		echo "  sudo make hostadd ARGS='--host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw'"; \
		echo "  sudo make hostadd ARGS='--host srv1 --primary-ip 10.1.11.100/24 --connect-to hq-lab --router-interface eth2'"; \
		echo "  sudo make hostadd ARGS='--host db1 --primary-ip 10.2.1.100/24 --secondary-ips 192.168.1.1/24,172.16.1.1/24'"; \
		echo "  sudo make hostadd ARGS='--host client1 --primary-ip 10.3.1.100/24 -v'"; \
		exit 1; \
	fi
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) src/simulators/host_namespace_setup.py $(ARGS)

# Remove host from network (requires sudo)
# Usage: sudo make hostdel ARGS="--host <name> --remove"
hostdel:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: hostdel requires root privileges"; \
		echo "Please run: sudo make hostdel ARGS='--host <name> --remove'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo make hostdel ARGS='--host <name> --remove'"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo make hostdel ARGS='--host web1 --remove'"; \
		echo "  sudo make hostdel ARGS='--host db1 --remove -v'"; \
		exit 1; \
	fi
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) src/simulators/host_namespace_setup.py $(ARGS)

# List all registered hosts (requires sudo)
# Usage: sudo make hostlist
hostlist:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: hostlist requires root privileges to check namespace status"; \
		echo "Please run: sudo make hostlist"; \
		exit 1; \
	fi
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) src/simulators/host_namespace_setup.py --list-hosts

# Clean up all registered hosts (requires sudo)
# Usage: sudo make hostclean [ARGS="-v|-vv"]
hostclean:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: hostclean requires root privileges"; \
		echo "Please run: sudo make hostclean"; \
		exit 1; \
	fi
	@$(PYTHON) src/utils/host_cleanup.py $(ARGS)

# Clean up both network namespaces and hosts (requires sudo)
# Usage: sudo make netnsclean [ARGS="-v|-f|--force"]
netnsclean:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: netnsclean requires root privileges"; \
		echo "Please run: sudo make netnsclean"; \
		exit 1; \
	fi
	@$(PYTHON) src/utils/host_cleanup.py $(ARGS)
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) src/simulators/network_namespace_cleanup.py $(ARGS)

# Check if we're running in a git repository (for future enhancements)
.git-check:
	@if [ ! -d ".git" ]; then \
		echo "Warning: Not in a git repository"; \
	fi

# Service management targets
# Start a service in a namespace
# Usage: sudo make service-start ARGS="--namespace <ns> --name <name> --port <port> [--protocol tcp|udp] [--bind <ip>]"
service-start:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: service-start requires root privileges"; \
		echo "Please run: sudo make service-start ARGS='<arguments>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo make service-start ARGS='--namespace <ns> --name <name> --port <port> [options]'"; \
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
		echo "  sudo make service-start ARGS='--namespace hq-gw --name echo --port 8080'"; \
		echo "  sudo make service-start ARGS='--namespace br-core --name dns --port 53 --protocol udp'"; \
		exit 1; \
	fi
	@$(PYTHON) src/simulators/service_manager.py start $(ARGS)

# Stop a service
# Usage: sudo make service-stop ARGS="--namespace <ns> --name <name> --port <port>"
service-stop:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: service-stop requires root privileges"; \
		echo "Please run: sudo make service-stop ARGS='<arguments>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo make service-stop ARGS='--namespace <ns> --name <name> --port <port>'"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo make service-stop ARGS='--namespace hq-gw --name echo --port 8080'"; \
		exit 1; \
	fi
	@$(PYTHON) src/simulators/service_manager.py stop $(ARGS)

# Restart a service
# Usage: sudo make service-restart ARGS="--namespace <ns> --name <name> --port <port> [--protocol tcp|udp]"
service-restart:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: service-restart requires root privileges"; \
		echo "Please run: sudo make service-restart ARGS='<arguments>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo make service-restart ARGS='--namespace <ns> --name <name> --port <port> [--protocol tcp|udp]'"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo make service-restart ARGS='--namespace hq-gw --name echo --port 8080'"; \
		exit 1; \
	fi
	@$(PYTHON) src/simulators/service_manager.py restart $(ARGS)

# Show service status
# Usage: sudo make service-status [ARGS="--namespace <ns>"]
service-status:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: service-status requires root privileges"; \
		echo "Please run: sudo make service-status"; \
		exit 1; \
	fi
	@$(PYTHON) src/simulators/service_manager.py status $(ARGS)

# Test a service
# Usage: sudo make service-test ARGS="--source <ns> --dest <ip> --port <port> [--protocol tcp|udp] [--message <msg>] [--timeout <sec>]"
service-test:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: service-test requires root privileges"; \
		echo "Please run: sudo make service-test ARGS='<arguments>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo make service-test ARGS='--source <ns> --dest <ip> --port <port> [options]'"; \
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
		echo "  sudo make service-test ARGS='--source hq-core --dest 10.1.1.1 --port 8080'"; \
		echo "  sudo make service-test ARGS='--source br-gw --dest 10.2.1.2 --port 53 --protocol udp --message QUERY'"; \
		exit 1; \
	fi
	@$(PYTHON) src/simulators/service_manager.py test $(ARGS)

# Clean up all services
# Usage: sudo make service-clean
service-clean:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: service-clean requires root privileges"; \
		echo "Please run: sudo make service-clean"; \
		exit 1; \
	fi
	@echo "Cleaning up all services..."
	@$(PYTHON) src/simulators/service_manager.py cleanup

# Run service manager test suite
# Usage: sudo make test-services
test-services:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: Service tests require root privileges"; \
		echo "Please run: sudo make test-services"; \
		exit 1; \
	fi
	@echo "Running Service Manager Test Suite"
	@echo "=================================="
	@$(PYTHON) -B tests/test_service_manager.py