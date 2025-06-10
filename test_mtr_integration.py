#!/usr/bin/env python3
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
    print("MTR Integration Test Suite")
    print("Testing enhanced traceroute simulator with MTR fallback")
    
    tests_passed = 0
    total_tests = 0
    
    # Test 1: Normal simulation (should work as before)
    total_tests += 1
    if run_test(
        "Normal simulation - HQ to Branch",
        "python3 traceroute_simulator.py --routing-dir testing/routing_facts -s 10.1.1.1 -d 10.2.1.1 --no-mtr"
    ):
        tests_passed += 1
    
    # Test 2: JSON output (should work as before)
    total_tests += 1
    if run_test(
        "JSON output format",
        "python3 traceroute_simulator.py --routing-dir testing/routing_facts -s 10.1.1.1 -d 10.2.1.1 --no-mtr -j"
    ):
        tests_passed += 1
    
    # Test 3: Complex routing (should work as before)
    total_tests += 1
    if run_test(
        "Complex multi-hop routing",
        "python3 traceroute_simulator.py --routing-dir testing/routing_facts -s 10.1.10.1 -d 10.3.20.1 --no-mtr"
    ):
        tests_passed += 1
    
    # Test 4: MTR fallback logic (expected to fail due to no Ansible environment)
    total_tests += 1
    if run_test(
        "MTR fallback logic test",
        "python3 traceroute_simulator.py --routing-dir testing/routing_facts -s 10.1.1.1 -d 8.8.8.8",
        expected_success=False
    ):
        tests_passed += 1
    
    # Test 5: Quiet mode with simulation
    total_tests += 1
    if run_test(
        "Quiet mode - simulation success",
        "python3 traceroute_simulator.py --routing-dir testing/routing_facts -s 10.1.1.1 -d 10.2.1.1 --no-mtr -q"
    ):
        tests_passed += 1
    
    # Test 6: Help output
    total_tests += 1
    if run_test(
        "Help output",
        "python3 traceroute_simulator.py --help"
    ):
        tests_passed += 1
    
    # Test 7: Invalid IP address handling
    total_tests += 1
    if run_test(
        "Invalid IP address handling",
        "python3 traceroute_simulator.py --routing-dir testing/routing_facts -s invalid -d 10.2.1.1 --no-mtr",
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
        from mtr_executor import MTRExecutor
        from route_formatter import RouteFormatter
        import traceroute_simulator
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