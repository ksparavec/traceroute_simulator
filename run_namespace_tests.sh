#!/bin/bash
"""
Comprehensive test runner for namespace make targets.

Runs all test chunks sequentially to provide complete coverage of:
- netsetup, nettest, netshow, netstatus, netclean
- hostadd, hostdel, hostlist, hostclean, netnsclean

Usage: sudo ./run_namespace_tests.sh
"""

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}NAMESPACE MAKE TARGETS COMPREHENSIVE TEST SUITE${NC}"
echo -e "${BLUE}=================================================${NC}"
echo ""

# Check root privileges
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script requires root privileges${NC}"
    echo "Please run: sudo ./run_namespace_tests.sh"
    exit 1
fi

# Check test facts availability
if [ ! -d "/tmp/traceroute_test_output" ] || [ -z "$(ls -A /tmp/traceroute_test_output/*.json 2>/dev/null)" ]; then
    echo -e "${RED}Error: Test facts not available${NC}"
    echo "Please run 'make test' first to generate test facts"
    exit 1
fi

echo -e "${GREEN}✓ Root privileges confirmed${NC}"
echo -e "${GREEN}✓ Test facts available: $(ls /tmp/traceroute_test_output/*.json | wc -l) JSON files${NC}"
echo ""

# Function to run a test script
run_test() {
    local test_name="$1"
    local test_script="$2"
    local description="$3"
    
    echo -e "${YELLOW}Running $test_name: $description${NC}"
    echo "Script: $test_script"
    echo "----------------------------------------"
    
    if python3 -B "$test_script"; then
        echo -e "${GREEN}✓ $test_name PASSED${NC}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo -e "${RED}✗ $test_name FAILED${NC}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    echo ""
}

# Test 1: Quick basic functionality
run_test "QUICK TESTS" \
         "tests/test_make_targets_quick.py" \
         "Basic netshow and hostlist functionality"

# Test 2: Basic make targets
run_test "BASIC TESTS" \
         "tests/test_make_targets_basic.py" \
         "netshow, netsetup, netclean operations"

# Test 3: Host management
run_test "HOST TESTS" \
         "tests/test_make_targets_hosts.py" \
         "hostadd, hostdel, hostlist, hostclean operations"

# Test 4: Network testing
run_test "NETWORK TESTS" \
         "tests/test_make_targets_network.py" \
         "nettest, netstatus, netnsclean operations"

# Test 5: Error handling and edge cases
run_test "ERROR TESTS" \
         "tests/test_make_targets_errors.py" \
         "Error conditions, invalid inputs, edge cases"

# Test 6: Integration scenarios
run_test "INTEGRATION TESTS" \
         "tests/test_make_targets_integration.py" \
         "Complete workflows and realistic scenarios"

# Final cleanup to ensure clean state
echo -e "${BLUE}Performing final cleanup...${NC}"
make netnsclean ARGS="-f" > /dev/null 2>&1 || true

# Summary
echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}TEST SUMMARY${NC}"
echo -e "${BLUE}=================================================${NC}"
echo "Total test suites: $TOTAL_TESTS"
echo -e "Passed: ${GREEN}$PASSED_TESTS${NC}"
echo -e "Failed: ${RED}$FAILED_TESTS${NC}"

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}✓ ALL TESTS PASSED!${NC}"
    echo ""
    echo "Namespace make targets are working correctly:"
    echo "  ✓ netshow - Static topology viewing"
    echo "  ✓ netsetup - Network namespace setup"
    echo "  ✓ netclean - Network cleanup"
    echo "  ✓ nettest - Connectivity testing"
    echo "  ✓ netstatus - Live status monitoring"
    echo "  ✓ hostadd - Dynamic host addition"
    echo "  ✓ hostdel - Host removal"
    echo "  ✓ hostlist - Host listing"
    echo "  ✓ hostclean - All hosts cleanup"
    echo "  ✓ netnsclean - Complete cleanup"
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED${NC}"
    echo ""
    echo "Please review the failed test output above for details."
    exit 1
fi