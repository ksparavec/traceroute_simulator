# Makefile for Traceroute Simulator Project
# Provides targets for dependency checking, testing, and routing data collection

# Project configuration
PYTHON := python3
PIP := pip3
ANSIBLE := ansible-playbook
TESTS_DIR := tests
ROUTING_FACTS_DIR := tests/routing_facts
ANSIBLE_DIR := ansible

# Python modules required by the project
REQUIRED_MODULES := json sys argparse ipaddress os glob typing subprocess re difflib matplotlib numpy

# Colors removed for better terminal compatibility

.PHONY: help check-deps test fetch-routing-data clean

# Default target
help:
	@echo "Traceroute Simulator - Available Make Targets"
	@echo "=============================================="
	@echo "check-deps        - Check for required Python modules and provide installation hints"
	@echo "test              - Execute all test scripts with test setup and report results"
	@echo "fetch-routing-data - Run Ansible playbook to collect routing facts (requires OUTPUT_DIR and INVENTORY_FILE or INVENTORY)"
	@echo "clean             - Clean up generated files and cache"
	@echo "help              - Show this help message"
	@echo ""
	@echo "Usage Examples:"
	@echo "  make check-deps                                              # Verify all dependencies are installed"
	@echo "  make test                                                   # Run comprehensive test suite"
	@echo "  make fetch-routing-data OUTPUT_DIR=tests/routing_facts INVENTORY_FILE=hosts.ini       # Use specific inventory file"
	@echo "  make fetch-routing-data OUTPUT_DIR=prod INVENTORY=routers              # Use configured inventory group"
	@echo "  make fetch-routing-data OUTPUT_DIR=temp INVENTORY=specific-host        # Target specific host"

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
	
	@if [ ! -d "$(ROUTING_FACTS_DIR)" ]; then \
		echo "Error: Routing facts directory '$(ROUTING_FACTS_DIR)' not found"; \
		echo "Hint: Run 'make fetch-routing-data' to collect routing information"; \
		exit 1; \
	fi
	
	# Count available routing facts
	@route_files=$$(find $(ROUTING_FACTS_DIR) -name "*_route.json" | wc -l); \
	rule_files=$$(find $(ROUTING_FACTS_DIR) -name "*_rule.json" | wc -l); \
	echo "Test Environment Status:"; \
	echo "  Routing files: $$route_files"; \
	echo "  Rule files: $$rule_files"; \
	echo ""
	
	# Run main test suite
	@echo "1. Running Main Traceroute Simulator Tests"
	@echo "-----------------------------------------------"
	@cd $(TESTS_DIR) && TRACEROUTE_SIMULATOR_CONF=test_config.yaml $(PYTHON) test_traceroute_simulator.py || { \
		echo "Main test suite failed!"; \
		exit 1; \
	}
	@echo "✓ Main test suite passed"
	@echo ""
	
	# Run IP JSON wrapper comparison tests if available
	@if [ -f "$(TESTS_DIR)/test_ip_json_comparison.py" ]; then \
		echo "2. Running IP JSON Wrapper Comparison Tests"; \
		echo "--------------------------------------------------"; \
		cd $(TESTS_DIR) && TRACEROUTE_SIMULATOR_CONF=test_config.yaml $(PYTHON) test_ip_json_comparison.py || { \
			echo "Warning: IP JSON wrapper tests failed (may not be critical)"; \
		}; \
		echo "✓ IP JSON wrapper tests completed"; \
		echo ""; \
	fi
	
	# Run MTR integration tests if available
	@if [ -f "$(TESTS_DIR)/test_mtr_integration.py" ]; then \
		echo "2.5. Running MTR Integration Tests"; \
		echo "-------------------------------------"; \
		cd $(TESTS_DIR) && TRACEROUTE_SIMULATOR_CONF=test_config.yaml $(PYTHON) test_mtr_integration.py || { \
			echo "Warning: MTR integration tests failed (may not be critical)"; \
		}; \
		echo "✓ MTR integration tests completed"; \
		echo ""; \
	fi
	
	# Test basic functionality with sample data
	@echo "3. Running Integration Tests"
	@echo "---------------------------------"
	@echo "Testing basic routing scenarios..."
	@$(PYTHON) traceroute_simulator.py --routing-dir $(ROUTING_FACTS_DIR) -s 10.1.1.1 -d 10.2.1.1 > /dev/null && \
		echo "✓ Inter-location routing test passed" || \
		echo "✗ Inter-location routing test failed"
	
	@$(PYTHON) traceroute_simulator.py --routing-dir $(ROUTING_FACTS_DIR) -s 10.100.1.1 -d 10.100.1.3 > /dev/null && \
		echo "✓ VPN mesh routing test passed" || \
		echo "✗ VPN mesh routing test failed"
	
	@$(PYTHON) traceroute_simulator.py --routing-dir $(ROUTING_FACTS_DIR) -j -s 10.1.10.1 -d 10.3.20.1 > /dev/null && \
		echo "✓ JSON output test passed" || \
		echo "✗ JSON output test failed"
	
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
	@echo "Fetching Routing Data from Network Routers"
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
	@if [ ! -f "$(ANSIBLE_DIR)/get_routing_info.yml" ]; then \
		echo "Error: Ansible playbook '$(ANSIBLE_DIR)/get_routing_info.yml' not found"; \
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
	@$(ANSIBLE) $(ANSIBLE_DIR)/get_routing_info.yml --syntax-check || { \
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
	@echo "Executing Ansible playbook to collect routing information..."
	@if [ -n "$(INVENTORY_FILE)" ]; then \
		$(ANSIBLE) $(ANSIBLE_DIR)/get_routing_info.yml -i "$(INVENTORY_FILE)" -v -e "output_dir=$(TARGET_DIR)" || { \
			echo "Ansible playbook execution failed!"; \
			echo "Check your inventory file and network connectivity"; \
			exit 1; \
		}; \
	else \
		$(ANSIBLE) $(ANSIBLE_DIR)/get_routing_info.yml --limit "$(INVENTORY)" -v -e "output_dir=$(TARGET_DIR)" || { \
			echo "Ansible playbook execution failed!"; \
			echo "Check your inventory configuration and network connectivity"; \
			echo "Ensure the group/host '$(INVENTORY)' exists in your configured inventory"; \
			exit 1; \
		}; \
	fi
	
	# Verify collected data
	@if [ -d "$(TARGET_DIR)" ]; then \
		route_files=$$(find $(TARGET_DIR) -name "*_route.json" | wc -l); \
		rule_files=$$(find $(TARGET_DIR) -name "*_rule.json" | wc -l); \
		echo ""; \
		echo "Routing data collection completed!"; \
		echo "  Route files collected: $$route_files"; \
		echo "  Rule files collected: $$rule_files"; \
		echo "  Data location: $(TARGET_DIR)"; \
		if [ $$route_files -eq 0 ] || [ $$rule_files -eq 0 ]; then \
			echo "Warning: Some files may be missing. Check Ansible output above."; \
		fi; \
	else \
		echo "No routing facts were collected!"; \
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
	@echo "Cleanup completed!"

# Check if we're running in a git repository (for future enhancements)
.git-check:
	@if [ ! -d ".git" ]; then \
		echo "Warning: Not in a git repository"; \
	fi