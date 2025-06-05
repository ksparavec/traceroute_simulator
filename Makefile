# Makefile for Traceroute Simulator Project
# Provides targets for dependency checking, testing, and routing data collection

# Project configuration
PYTHON := python3
PIP := pip3
ANSIBLE := ansible-playbook
TESTING_DIR := testing
ROUTING_FACTS_DIR := testing/routing_facts

# Python modules required by the project
REQUIRED_MODULES := json sys argparse ipaddress os glob typing subprocess re difflib matplotlib numpy

# Colors for output formatting
GREEN := \033[0;32m
RED := \033[0;31m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

.PHONY: help check-deps test fetch-routing-data clean

# Default target
help:
	@echo "$(BLUE)Traceroute Simulator - Available Make Targets$(NC)"
	@echo "=============================================="
	@echo "$(GREEN)check-deps$(NC)        - Check for required Python modules and provide installation hints"
	@echo "$(GREEN)test$(NC)              - Execute all test scripts with test setup and report results"
	@echo "$(GREEN)fetch-routing-data$(NC) - Run Ansible playbook to collect routing facts (requires OUTPUT_DIR and INVENTORY_FILE or INVENTORY)"
	@echo "$(GREEN)clean$(NC)             - Clean up generated files and cache"
	@echo "$(GREEN)help$(NC)              - Show this help message"
	@echo ""
	@echo "$(YELLOW)Usage Examples:$(NC)"
	@echo "  make check-deps                                              # Verify all dependencies are installed"
	@echo "  make test                                                   # Run comprehensive test suite"
	@echo "  make fetch-routing-data OUTPUT_DIR=test INVENTORY_FILE=hosts.ini       # Use specific inventory file"
	@echo "  make fetch-routing-data OUTPUT_DIR=prod INVENTORY=routers              # Use configured inventory group"
	@echo "  make fetch-routing-data OUTPUT_DIR=temp INVENTORY=specific-host        # Target specific host"

# Check for existence of all required Python modules
check-deps:
	@echo "$(BLUE)Checking Python Module Dependencies$(NC)"
	@echo "======================================="
	@echo "Python version: $$($(PYTHON) --version 2>&1)"
	@echo ""
	@missing_modules=""; \
	for module in $(REQUIRED_MODULES); do \
		if $(PYTHON) -c "import $$module" 2>/dev/null; then \
			echo "$(GREEN)✓$(NC) $$module"; \
		else \
			echo "$(RED)✗$(NC) $$module"; \
			missing_modules="$$missing_modules $$module"; \
		fi; \
	done; \
	if [ -n "$$missing_modules" ]; then \
		echo ""; \
		echo "$(RED)Missing modules detected!$(NC)"; \
		echo "$(YELLOW)Installation hints:$(NC)"; \
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
		echo "$(YELLOW)Note:$(NC) Standard library modules (json, sys, etc.) should be included with Python."; \
		echo "If they're missing, your Python installation may be incomplete."; \
		exit 1; \
	else \
		echo ""; \
		echo "$(GREEN)All required Python modules are available!$(NC)"; \
	fi
	@echo ""
	@echo "$(BLUE)Checking Additional Tools$(NC)"
	@echo "============================="
	@if command -v ansible-playbook >/dev/null 2>&1; then \
		echo "$(GREEN)✓$(NC) ansible-playbook ($$(ansible-playbook --version | head -1))"; \
	else \
		echo "$(RED)✗$(NC) ansible-playbook"; \
		echo "$(YELLOW)Installation hint:$(NC) pip install ansible"; \
	fi

# Execute test scripts with setup and reporting
test: check-deps
	@echo "$(BLUE)Running Traceroute Simulator Test Suite$(NC)"
	@echo "============================================"
	@echo ""
	
	# Verify test environment exists
	@if [ ! -d "$(TESTING_DIR)" ]; then \
		echo "$(RED)Error:$(NC) Testing directory '$(TESTING_DIR)' not found"; \
		exit 1; \
	fi
	
	@if [ ! -d "$(ROUTING_FACTS_DIR)" ]; then \
		echo "$(RED)Error:$(NC) Routing facts directory '$(ROUTING_FACTS_DIR)' not found"; \
		echo "$(YELLOW)Hint:$(NC) Run 'make fetch-routing-data' to collect routing information"; \
		exit 1; \
	fi
	
	# Count available routing facts
	@route_files=$$(find $(ROUTING_FACTS_DIR) -name "*_route.json" | wc -l); \
	rule_files=$$(find $(ROUTING_FACTS_DIR) -name "*_rule.json" | wc -l); \
	echo "$(BLUE)Test Environment Status:$(NC)"; \
	echo "  Routing files: $$route_files"; \
	echo "  Rule files: $$rule_files"; \
	echo ""
	
	# Run main test suite
	@echo "$(BLUE)1. Running Main Traceroute Simulator Tests$(NC)"
	@echo "-----------------------------------------------"
	@cd $(TESTING_DIR) && $(PYTHON) test_traceroute_simulator.py || { \
		echo "$(RED)Main test suite failed!$(NC)"; \
		exit 1; \
	}
	@echo "$(GREEN)✓ Main test suite passed$(NC)"
	@echo ""
	
	# Run IP JSON wrapper comparison tests if available
	@if [ -f "$(TESTING_DIR)/test_ip_json_comparison.py" ]; then \
		echo "$(BLUE)2. Running IP JSON Wrapper Comparison Tests$(NC)"; \
		echo "--------------------------------------------------"; \
		cd $(TESTING_DIR) && $(PYTHON) test_ip_json_comparison.py || { \
			echo "$(YELLOW)Warning:$(NC) IP JSON wrapper tests failed (may not be critical)"; \
		}; \
		echo "$(GREEN)✓ IP JSON wrapper tests completed$(NC)"; \
		echo ""; \
	fi
	
	# Test basic functionality with sample data
	@echo "$(BLUE)3. Running Integration Tests$(NC)"
	@echo "---------------------------------"
	@echo "Testing basic routing scenarios..."
	@$(PYTHON) traceroute_simulator.py --routing-dir $(ROUTING_FACTS_DIR) -s 10.1.1.1 -d 10.2.1.1 > /dev/null && \
		echo "$(GREEN)✓$(NC) Inter-location routing test passed" || \
		echo "$(RED)✗$(NC) Inter-location routing test failed"
	
	@$(PYTHON) traceroute_simulator.py --routing-dir $(ROUTING_FACTS_DIR) -s 10.100.1.1 -d 10.100.1.3 > /dev/null && \
		echo "$(GREEN)✓$(NC) VPN mesh routing test passed" || \
		echo "$(RED)✗$(NC) VPN mesh routing test failed"
	
	@$(PYTHON) traceroute_simulator.py --routing-dir $(ROUTING_FACTS_DIR) -j -s 10.1.10.1 -d 10.3.20.1 > /dev/null && \
		echo "$(GREEN)✓$(NC) JSON output test passed" || \
		echo "$(RED)✗$(NC) JSON output test failed"
	
	@echo ""
	@echo "$(GREEN)All tests completed successfully!$(NC)"

# Run Ansible playbook to fetch routing facts
# 
# Two inventory modes supported:
# 1. INVENTORY_FILE: Specify a specific inventory file (e.g., hosts.ini, production.yml)
# 2. INVENTORY: Use configured Ansible inventory to target specific group or host
#    (requires ANSIBLE_INVENTORY environment variable or ansible.cfg configuration)
#
# Usage: make fetch-routing-data OUTPUT_DIR=directory_name [INVENTORY_FILE=file OR INVENTORY=group/host]
fetch-routing-data:
	@echo "$(BLUE)Fetching Routing Data from Network Routers$(NC)"
	@echo "=============================================="
	@echo ""
	
	# Check if OUTPUT_DIR is provided
	@if [ -z "$(OUTPUT_DIR)" ]; then \
		echo "$(RED)Error:$(NC) OUTPUT_DIR parameter is required"; \
		echo "$(YELLOW)Usage:$(NC) make fetch-routing-data OUTPUT_DIR=directory_name [INVENTORY_FILE=file OR INVENTORY=group/host]"; \
		echo "$(YELLOW)Examples:$(NC)"; \
		echo "  make fetch-routing-data OUTPUT_DIR=testing/routing_facts INVENTORY_FILE=hosts.ini"; \
		echo "  make fetch-routing-data OUTPUT_DIR=production_data INVENTORY_FILE=production.yml"; \
		echo "  make fetch-routing-data OUTPUT_DIR=testing/routing_facts INVENTORY=routers"; \
		echo "  make fetch-routing-data OUTPUT_DIR=production_data INVENTORY=production_group"; \
		echo "  make fetch-routing-data OUTPUT_DIR=/tmp/routing_facts INVENTORY=specific-host"; \
		exit 1; \
	fi
	
	# Check if either INVENTORY_FILE or INVENTORY is provided
	@if [ -z "$(INVENTORY_FILE)" ] && [ -z "$(INVENTORY)" ]; then \
		echo "$(RED)Error:$(NC) Either INVENTORY_FILE or INVENTORY parameter is required"; \
		echo "$(YELLOW)Usage:$(NC) make fetch-routing-data OUTPUT_DIR=directory_name [INVENTORY_FILE=file OR INVENTORY=group/host]"; \
		echo "$(YELLOW)Examples:$(NC)"; \
		echo "  make fetch-routing-data OUTPUT_DIR=testing/routing_facts INVENTORY_FILE=hosts.ini      # Use specific inventory file"; \
		echo "  make fetch-routing-data OUTPUT_DIR=production_data INVENTORY_FILE=production.yml     # Use specific inventory file"; \
		echo "  make fetch-routing-data OUTPUT_DIR=testing/routing_facts INVENTORY=routers           # Use configured inventory group"; \
		echo "  make fetch-routing-data OUTPUT_DIR=production_data INVENTORY=production_group        # Use configured inventory group"; \
		echo "  make fetch-routing-data OUTPUT_DIR=/tmp/routing_facts INVENTORY=specific-host        # Target specific host"; \
		exit 1; \
	fi
	
	# Check if both INVENTORY_FILE and INVENTORY are provided (not allowed)
	@if [ -n "$(INVENTORY_FILE)" ] && [ -n "$(INVENTORY)" ]; then \
		echo "$(RED)Error:$(NC) Cannot specify both INVENTORY_FILE and INVENTORY parameters"; \
		echo "$(YELLOW)Usage:$(NC) Use either INVENTORY_FILE for a specific file OR INVENTORY for a group/host"; \
		echo "$(YELLOW)Examples:$(NC)"; \
		echo "  make fetch-routing-data OUTPUT_DIR=test INVENTORY_FILE=hosts.ini  # Use file"; \
		echo "  make fetch-routing-data OUTPUT_DIR=test INVENTORY=routers         # Use group"; \
		exit 1; \
	fi
	
	$(eval TARGET_DIR := $(OUTPUT_DIR))
	@echo "$(BLUE)Target output directory: $(TARGET_DIR)$(NC)"
	
	# Set inventory parameter based on what was provided
	@if [ -n "$(INVENTORY_FILE)" ]; then \
		echo "$(BLUE)Using inventory file: $(INVENTORY_FILE)$(NC)"; \
	else \
		echo "$(BLUE)Using inventory group/host: $(INVENTORY)$(NC)"; \
	fi
	@echo ""
	
	# Check if Ansible is available
	@if ! command -v $(ANSIBLE) >/dev/null 2>&1; then \
		echo "$(RED)Error:$(NC) ansible-playbook not found"; \
		echo "$(YELLOW)Installation hint:$(NC) pip install ansible"; \
		exit 1; \
	fi
	
	# Check if playbook exists
	@if [ ! -f "get_routing_info.yml" ]; then \
		echo "$(RED)Error:$(NC) Ansible playbook 'get_routing_info.yml' not found"; \
		exit 1; \
	fi
	
	# Check if inventory file exists (only if INVENTORY_FILE is specified)
	@if [ -n "$(INVENTORY_FILE)" ] && [ ! -f "$(INVENTORY_FILE)" ]; then \
		echo "$(RED)Error:$(NC) Inventory file '$(INVENTORY_FILE)' not found"; \
		echo "$(YELLOW)Please ensure the inventory file exists and is accessible$(NC)"; \
		exit 1; \
	fi
	
	# Validate playbook syntax
	@echo "$(BLUE)Validating Ansible playbook syntax...$(NC)"
	@$(ANSIBLE) get_routing_info.yml --syntax-check || { \
		echo "$(RED)Playbook syntax validation failed!$(NC)"; \
		exit 1; \
	}
	@echo "$(GREEN)✓ Playbook syntax is valid$(NC)"
	@echo ""
	
	# Create backup of existing routing facts if they exist
	@if [ -d "$(TARGET_DIR)" ] && [ "$$(ls -A $(TARGET_DIR) 2>/dev/null)" ]; then \
		backup_dir="$(TARGET_DIR).backup.$$(date +%Y%m%d_%H%M%S)"; \
		echo "$(YELLOW)Backing up existing routing facts to $$backup_dir$(NC)"; \
		cp -r $(TARGET_DIR) $$backup_dir; \
	fi
	
	# Run the playbook with user-specified output directory and inventory
	@echo "$(BLUE)Executing Ansible playbook to collect routing information...$(NC)"
	@if [ -n "$(INVENTORY_FILE)" ]; then \
		$(ANSIBLE) get_routing_info.yml -i "$(INVENTORY_FILE)" -v -e "output_dir=$(TARGET_DIR)" || { \
			echo "$(RED)Ansible playbook execution failed!$(NC)"; \
			echo "$(YELLOW)Check your inventory file and network connectivity$(NC)"; \
			exit 1; \
		}; \
	else \
		$(ANSIBLE) get_routing_info.yml --limit "$(INVENTORY)" -v -e "output_dir=$(TARGET_DIR)" || { \
			echo "$(RED)Ansible playbook execution failed!$(NC)"; \
			echo "$(YELLOW)Check your inventory configuration and network connectivity$(NC)"; \
			echo "$(YELLOW)Ensure the group/host '$(INVENTORY)' exists in your configured inventory$(NC)"; \
			exit 1; \
		}; \
	fi
	
	# Verify collected data
	@if [ -d "$(TARGET_DIR)" ]; then \
		route_files=$$(find $(TARGET_DIR) -name "*_route.json" | wc -l); \
		rule_files=$$(find $(TARGET_DIR) -name "*_rule.json" | wc -l); \
		echo ""; \
		echo "$(GREEN)Routing data collection completed!$(NC)"; \
		echo "  Route files collected: $$route_files"; \
		echo "  Rule files collected: $$rule_files"; \
		echo "  Data location: $(TARGET_DIR)"; \
		if [ $$route_files -eq 0 ] || [ $$rule_files -eq 0 ]; then \
			echo "$(YELLOW)Warning:$(NC) Some files may be missing. Check Ansible output above."; \
		fi; \
	else \
		echo "$(RED)No routing facts were collected!$(NC)"; \
		exit 1; \
	fi

# Clean up generated files and cache
clean:
	@echo "$(BLUE)Cleaning up generated files and cache$(NC)"
	@echo "======================================="
	@rm -rf __pycache__/
	@rm -rf $(TESTING_DIR)/__pycache__/
	@rm -rf *.pyc
	@rm -rf $(TESTING_DIR)/*.pyc
	@rm -rf .pytest_cache/
	@find . -name "*.pyc" -delete
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)✓ Cleaned up Python cache files$(NC)"
	@echo "$(GREEN)Cleanup completed!$(NC)"

# Check if we're running in a git repository (for future enhancements)
.git-check:
	@if [ ! -d ".git" ]; then \
		echo "$(YELLOW)Warning:$(NC) Not in a git repository"; \
	fi