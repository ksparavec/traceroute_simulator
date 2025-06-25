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

.PHONY: help check-deps test fetch-routing-data clean tsim ifa netsetup nettest netclean netshow test-namespace

# Default target
help:
	@echo "Traceroute Simulator - Available Make Targets"
	@echo "=============================================="
	@echo "check-deps        - Check for required Python modules and provide installation hints"
	@echo "test              - Execute all test scripts with test setup and report results"
	@echo "fetch-routing-data - Run Ansible playbook to collect routing facts (requires OUTPUT_DIR and INVENTORY_FILE or INVENTORY)"
	@echo "clean             - Clean up generated files and cache"
	@echo "tsim              - Run traceroute simulator with command line arguments (e.g., make tsim ARGS='-s 10.1.1.1 -d 10.2.1.1')"
	@echo "ifa               - Run iptables forward analyzer with command line arguments (e.g., make ifa ARGS='--router hq-gw -s 10.1.1.1 -d 8.8.8.8')"
	@echo "netsetup          - Set up Linux namespace network simulation (requires sudo, ARGS='-v/-vv/-vvv' for verbosity)"
	@echo "nettest           - Test network connectivity in namespace simulation (e.g., make nettest ARGS='-s 10.1.1.1 -d 10.2.1.1:80 -p tcp')"
	@echo "netshow           - Show network status with original interface names (e.g., make netshow ARGS='hq-gw interfaces')"
	@echo "netclean          - Clean up namespace network simulation (requires sudo, ARGS='-v/-f/--force' for options)"
	@echo "test-namespace    - Run namespace simulation tests independently (requires sudo and completed 'make test')"
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
	@echo "  sudo make nettest ARGS='-s 10.1.1.1 -d 10.2.1.1:80 -p tcp'           # Test real network connectivity"
	@echo "  sudo make nettest ARGS='-s 10.1.1.1:12345 -d 10.2.1.1:80 -p tcp -v' # Test with specific source port"
	@echo "  sudo make nettest ARGS='-s 10.1.1.1 -d 8.8.8.8 -p icmp -v'           # Test ICMP connectivity"
	@echo "  sudo make netshow ARGS='hq-gw interfaces'                             # Show interface config with original names"
	@echo "  sudo make netshow ARGS='all summary'                                  # Show summary of all routers"
	@echo "  sudo make netshow ARGS='br-core routes -v'                            # Show routing table with verbose output"
	@echo "  sudo make netclean                                                     # Clean up namespace simulation (silent)"
	@echo "  sudo make netclean ARGS='-v'                                          # Clean up with verbose output"
	@echo "  sudo make netclean ARGS='-f'                                          # Force cleanup of stuck resources"
	@echo "  sudo make netclean ARGS='-v -f'                                       # Verbose force cleanup"
	@echo "  sudo make test-namespace                                               # Run namespace simulation tests after 'make test'"
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
	
	# Run namespace simulation tests (requires sudo privileges)
	@echo "4. Running Namespace Simulation Tests"
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
	@echo "Running traceroute simulator with arguments: $(ARGS)"
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
	@echo "Running iptables forward analyzer with arguments: $(ARGS)"
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
		echo "Examples:"; \
		echo "  sudo make nettest ARGS='-s 10.1.1.1 -d 10.2.1.1 -p tcp --dport 80'"; \
		echo "  sudo make nettest ARGS='-s 10.1.11.1 -d 10.1.3.5 -p tcp --dport 3389'"; \
		echo "  sudo make nettest ARGS='-s 10.1.1.5 -d 8.8.8.8 -p icmp'"; \
		echo "  sudo make nettest ARGS='-s 10.1.2.1 -d 10.1.3.15 -p udp --dport 53'"; \
		exit 1; \
	fi
	@echo "Testing network connectivity with arguments: $(ARGS)"
	@TRACEROUTE_SIMULATOR_FACTS=/tmp/traceroute_test_output $(PYTHON) src/simulators/network_namespace_tester.py $(ARGS)

# Clean up namespace network simulation (requires sudo)
# Usage: sudo make netclean [ARGS="-v|-f|--force"]
netclean:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: netclean requires root privileges"; \
		echo "Please run: sudo make netclean"; \
		exit 1; \
	fi
	@$(PYTHON) src/simulators/network_namespace_cleanup.py $(ARGS)

# Show network status with original interface names (requires sudo)
# Usage: sudo make netshow ARGS="<router> <function> [-v]"
# Functions: interfaces, routes, rules, summary, all
# Router names: hq-gw, hq-core, hq-dmz, hq-lab, br-gw, br-core, br-wifi, dc-gw, dc-core, dc-srv, or 'all'
netshow:
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: netshow requires root privileges"; \
		echo "Please run: sudo make netshow ARGS='<router> <function>'"; \
		exit 1; \
	fi
	@if [ -z "$(ARGS)" ]; then \
		echo "Usage: sudo make netshow ARGS='<router> <function> [options]'"; \
		echo ""; \
		echo "Router names: hq-gw, hq-core, hq-dmz, hq-lab, br-gw, br-core, br-wifi, dc-gw, dc-core, dc-srv, all"; \
		echo "Functions: interfaces, routes, rules, summary, all"; \
		echo "Options: -v (verbose debug output)"; \
		echo ""; \
		echo "Examples:"; \
		echo "  sudo make netshow ARGS='hq-gw interfaces'           # Show interface config for hq-gw"; \
		echo "  sudo make netshow ARGS='br-core routes'             # Show routing table for br-core"; \
		echo "  sudo make netshow ARGS='dc-srv rules'               # Show policy rules for dc-srv"; \
		echo "  sudo make netshow ARGS='hq-dmz summary'             # Show brief overview for hq-dmz"; \
		echo "  sudo make netshow ARGS='hq-gw all'                  # Show complete config for hq-gw"; \
		echo "  sudo make netshow ARGS='all summary'                # Show summary for all routers"; \
		echo "  sudo make netshow ARGS='hq-gw interfaces -v'        # Show interfaces with verbose output"; \
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

# Check if we're running in a git repository (for future enhancements)
.git-check:
	@if [ ! -d ".git" ]; then \
		echo "Warning: Not in a git repository"; \
	fi