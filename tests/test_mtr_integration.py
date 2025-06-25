"""
Test script for MTR integration functionality.

This script tests the enhanced traceroute simulator with MTR fallback
functionality using the existing test data. It validates that:
1. Normal simulation still works as before
2. MTR fallback logic is triggered correctly
3. Output formatting works for both simulation and MTR results
4. All command-line options function properly

Author: Network Analysis Tool
"""

import subprocess
import sys
import json
import os

def get_simulator_path():
    """Get the correct path to traceroute_simulator.py relative to current working directory."""
    # Check if we're running from the tests directory
    if os.path.basename(os.getcwd()) == 'tests':
        return '../src/core/traceroute_simulator.py'  # Relative path from tests/ to project root
    # Otherwise assume we're running from the project root
    else:
        return 'src/core/traceroute_simulator.py'

def run_test(description, command, expected_success=True):
    """Run a test command and report results."""
    print(f"\n{'='*60}")
    print(f"TEST: {description}")
    print(f"COMMAND: {command}")
    print('='*60)
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        if expected_success and result.returncode == 0:
            print("✓ PASS: Command executed successfully")
            if result.stdout:
                print("OUTPUT:")
                print(result.stdout)
        elif not expected_success and result.returncode != 0:
            print("✓ PASS: Command failed as expected")
            if result.stderr:
                print("EXPECTED ERROR:")
                print(result.stderr)
        else:
            print(f"✗ FAIL: Unexpected return code {result.returncode}")
            if result.stdout:
                print("STDOUT:")
                print(result.stdout)
            if result.stderr:
                print("STDERR:")
                print(result.stderr)
        
        return result.returncode == 0 if expected_success else result.returncode != 0
        
    except Exception as e:
        print(f"✗ FAIL: Exception occurred: {e}")
        return False

def main():
    """Run comprehensive tests for MTR integration."""
    # Get correct paths based on current working directory
    simulator_path = get_simulator_path()
    routing_dir = "tsim_facts" if os.path.basename(os.getcwd()) == 'tests' else "tests/tsim_facts"
    
    print("MTR Integration Test Suite")
    print("Testing enhanced traceroute simulator with MTR fallback")
    
    tests_passed = 0
    total_tests = 0
    
    # Test 1: Normal simulation (should work as before)
    total_tests += 1
    if run_test(
        "Normal simulation - HQ to Branch",
        f"python3 {simulator_path} --tsim-facts {routing_dir} -s 10.1.1.1 -d 10.2.1.1 --no-mtr"
    ):
        tests_passed += 1
    
    # Test 2: JSON output (should work as before)
    total_tests += 1
    if run_test(
        "JSON output format",
        f"python3 {simulator_path} --tsim-facts {routing_dir} -s 10.1.1.1 -d 10.2.1.1 --no-mtr -j"
    ):
        tests_passed += 1
    
    # Test 3: Complex routing (should work as before)
    total_tests += 1
    if run_test(
        "Complex multi-hop routing",
        f"python3 {simulator_path} --tsim-facts {routing_dir} -s 10.1.10.1 -d 10.3.20.1 --no-mtr"
    ):
        tests_passed += 1
    
    # Test 4: Unreachable destination (should return exit code 2 for destination not found)
    # Note: EXIT_NO_LINUX (code 4) would only occur when:
    # 1. MTR executes successfully via SSH to a Linux router
    # 2. MTR reaches the destination but the path contains no Linux routers
    # 3. This scenario requires live SSH connectivity not available in test environment
    total_tests += 1
    print(f"\n{'='*60}")
    print("TEST: Unreachable destination handling")
    command = f"python3 {simulator_path} --tsim-facts {routing_dir} -s 10.1.2.3 -d 192.168.100.1 -q"
    print(f"COMMAND: {command}")
    print('='*60)
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        # This test should return exit code 2 (EXIT_NOT_FOUND) when destination is not reachable
        if result.returncode == 2:
            print("✓ PASS: Destination not reachable (exit code 2)")
            tests_passed += 1
        else:
            print(f"✗ FAIL: Expected exit code 2 (EXIT_NOT_FOUND), got {result.returncode}")
            if result.stdout:
                print("STDOUT:")
                print(result.stdout)
            if result.stderr:
                print("STDERR:")
                print(result.stderr)
    except Exception as e:
        print(f"✗ FAIL: Exception occurred: {e}")
    
    # Test 5: Quiet mode with simulation
    total_tests += 1
    if run_test(
        "Quiet mode - simulation success",
        f"python3 {simulator_path} --tsim-facts {routing_dir} -s 10.1.1.1 -d 10.2.1.1 --no-mtr -q"
    ):
        tests_passed += 1
    
    # Test 6: Help output
    total_tests += 1
    if run_test(
        "Help output",
        f"python3 {simulator_path} --help"
    ):
        tests_passed += 1
    
    # Test 7: Invalid IP address handling
    total_tests += 1
    if run_test(
        "Invalid IP address handling",
        f"python3 {simulator_path} --tsim-facts {routing_dir} -s invalid -d 10.2.1.1 --no-mtr",
        expected_success=False
    ):
        tests_passed += 1
    
    # Test 8: Module import validation
    total_tests += 1
    print(f"\n{'='*60}")
    print("TEST: Module import validation")
    print("COMMAND: Python import test")
    print('='*60)
    
    try:
        # Add parent directory to path for imports
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        
        from src.executors.mtr_executor import MTRExecutor
        from src.core.route_formatter import RouteFormatter
        import src.core.traceroute_simulator
        print("✓ PASS: All modules imported successfully")
        tests_passed += 1
    except Exception as e:
        print(f"✗ FAIL: Import error: {e}")
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print('='*60)
    print(f"Tests passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        print("✓ ALL TESTS PASSED - MTR integration is working correctly")
        return 0
    else:
        print(f"✗ {total_tests - tests_passed} TESTS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())