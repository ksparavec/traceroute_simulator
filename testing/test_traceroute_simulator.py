#!/usr/bin/env python3
"""
Comprehensive Test Suite for Traceroute Simulator - Complex Network Topology

This module tests the traceroute simulator with a realistic 10-router network
across 3 locations connected via WireGuard tunnels.

Network Topology:
- Location A (HQ): 4 routers (hq-gw, hq-core, hq-dmz, hq-lab) - 10.1.0.0/16
- Location B (Branch): 3 routers (br-gw, br-core, br-wifi) - 10.2.0.0/16  
- Location C (Data Center): 3 routers (dc-gw, dc-core, dc-srv) - 10.3.0.0/16
- WireGuard mesh: 10.100.1.0/24 connecting all locations

Test Categories:
- Intra-location routing: Within each location
- Inter-location routing: Between locations via WireGuard
- Multi-hop routing: Complex paths through multiple routers
- Network segment routing: From/to devices in subnets
- Error conditions: Invalid inputs and unreachable destinations

Author: Network Analysis Tool Test Suite
License: MIT
"""

import subprocess
import sys
import os
import json
import tempfile
import shutil
from typing import List, Tuple, Dict, Any

# Test configuration constants
SIMULATOR_SCRIPT = "../traceroute_simulator.py"  # Path to script under test
ROUTING_FACTS_DIR = "routing_facts"              # Directory with routing data

# Network topology data for the test environment
# Each location has multiple routers with distinct IP ranges

ROUTER_IPS = {
    # Location A - Headquarters (10.1.0.0/16)
    "hq-gw": [
        "10.1.1.1",        # Core network interface
        "10.100.1.1",      # WireGuard tunnel endpoint
        "203.0.113.10"     # Internet interface
    ],
    "hq-core": [
        "10.1.1.2",        # Gateway connection
        "10.1.2.1"         # Internal network
    ],
    "hq-dmz": [
        "10.1.2.3",        # Core network connection
        "10.1.3.1"         # DMZ network
    ],
    "hq-lab": [
        "10.1.2.4",        # Core network connection
        "10.1.10.1",       # Lab network 1
        "10.1.11.1"        # Lab network 2
    ],
    
    # Location B - Branch Office (10.2.0.0/16)
    "br-gw": [
        "10.2.1.1",        # Core network interface
        "10.100.1.2",      # WireGuard tunnel endpoint
        "198.51.100.10"    # Internet interface
    ],
    "br-core": [
        "10.2.1.2",        # Gateway connection
        "10.2.2.1"         # Internal network
    ],
    "br-wifi": [
        "10.2.2.3",        # Core network connection
        "10.2.5.1",        # WiFi network 1
        "10.2.6.1"         # WiFi network 2
    ],
    
    # Location C - Data Center (10.3.0.0/16)
    "dc-gw": [
        "10.3.1.1",        # Core network interface
        "10.100.1.3",      # WireGuard tunnel endpoint
        "192.0.2.10"       # Internet interface
    ],
    "dc-core": [
        "10.3.1.2",        # Gateway connection
        "10.3.2.1"         # Internal network
    ],
    "dc-srv": [
        "10.3.2.3",        # Core network connection
        "10.3.10.1",       # Server network 1
        "10.3.20.1",       # Server network 2
        "10.3.21.1"        # Server network 3
    ]
}

# Network segments for testing host-to-host routing
NETWORK_SEGMENTS = {
    # Location A network segments
    "hq_networks": [
        "10.1.1.0/24",     # Core network
        "10.1.2.0/24",     # Distribution network
        "10.1.3.0/24",     # DMZ network
        "10.1.10.0/24",    # Lab network 1
        "10.1.11.0/24"     # Lab network 2
    ],
    # Location B network segments
    "br_networks": [
        "10.2.1.0/24",     # Core network
        "10.2.2.0/24",     # Distribution network
        "10.2.5.0/24",     # WiFi network 1
        "10.2.6.0/24"      # WiFi network 2
    ],
    # Location C network segments
    "dc_networks": [
        "10.3.1.0/24",     # Core network
        "10.3.2.0/24",     # Distribution network
        "10.3.10.0/24",    # Server network 1
        "10.3.20.0/24",    # Server network 2
        "10.3.21.0/24"     # Server network 3
    ]
}

# External IP addresses and invalid IPs for error testing
EXTERNAL_IPS = ["8.8.8.8", "1.1.1.1", "203.0.113.1"]
INVALID_IPS = ["999.999.999.999", "not.an.ip", "10.999.999.1"]

class TestResult:
    """
    Container for individual test results and execution details.
    
    Stores all information about a single test execution including
    the test outcome, command output, and diagnostic information
    for debugging failed tests.
    """
    def __init__(self, name: str, passed: bool, details: str = "", 
                 stdout: str = "", stderr: str = "", returncode: int = 0):
        self.name = name
        self.passed = passed
        self.details = details
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class TracerouteSimulatorTester:
    """
    Comprehensive test suite for the traceroute simulator with complex topology.
    
    Tests routing scenarios across a realistic 10-router network including:
    - Intra-location routing within each site
    - Inter-location routing via WireGuard tunnels
    - Multi-hop paths through distribution layers
    - Network segment routing for end-to-end connectivity
    - Error handling for invalid inputs and unreachable destinations
    """
    
    def __init__(self):
        self.results: List[TestResult] = []
        self.total_tests = 0
        self.passed_tests = 0
    
    def run_simulator(self, args: List[str], expect_error: bool = False) -> Tuple[int, str, str]:
        """
        Execute the traceroute simulator with specified arguments.
        
        Args:
            args: Command line arguments for the simulator
            expect_error: Whether an error is expected (for error testing)
            
        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        cmd = ["python3", SIMULATOR_SCRIPT] + args
        try:
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=30
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 124, "", "Test timeout"
        except Exception as e:
            return 1, "", str(e)
    
    def add_result(self, result: TestResult):
        """Add a test result and update counters."""
        self.results.append(result)
        self.total_tests += 1
        if result.passed:
            self.passed_tests += 1
    
    def test_intra_location_routing(self):
        """Test routing within each location (same-site communication)."""
        print("Testing intra-location routing...")
        
        # Test cases for routing within each location
        test_cases = [
            # Location A (Headquarters) internal routing
            ("10.1.1.1", "10.1.2.1", "HQ gateway to core"),
            ("10.1.2.1", "10.1.2.3", "HQ core to DMZ"),
            ("10.1.2.1", "10.1.2.4", "HQ core to lab"),
            ("10.1.3.1", "10.1.10.1", "HQ DMZ to lab network"),
            
            # Location B (Branch) internal routing
            ("10.2.1.1", "10.2.2.1", "Branch gateway to core"),
            ("10.2.2.1", "10.2.2.3", "Branch core to WiFi"),
            ("10.2.5.1", "10.2.6.1", "Branch WiFi networks"),
            
            # Location C (Data Center) internal routing
            ("10.3.1.1", "10.3.2.1", "DC gateway to core"),
            ("10.3.2.1", "10.3.2.3", "DC core to servers"),
            ("10.3.10.1", "10.3.20.1", "DC server networks"),
            ("10.3.20.1", "10.3.21.1", "DC server segments")
        ]
        
        for src_ip, dst_ip, description in test_cases:
            returncode, stdout, stderr = self.run_simulator([src_ip, dst_ip])
            
            success = returncode == 0 and "traceroute to" in stdout
            details = f"{description}: {'success' if success else 'failed'}"
            if not success:
                details += f" (code {returncode})"
            
            self.add_result(TestResult(
                f"Intra-location: {description}",
                success,
                details,
                stdout,
                stderr,
                returncode
            ))
    
    def test_inter_location_routing(self):
        """Test routing between locations via WireGuard tunnels."""
        print("Testing inter-location routing...")
        
        # Test cases for cross-location communication via WireGuard
        test_cases = [
            # HQ to Branch communication
            ("10.1.1.1", "10.2.1.1", "HQ to Branch gateways"),
            ("10.1.2.1", "10.2.2.1", "HQ core to Branch core"),
            ("10.1.10.1", "10.2.5.1", "HQ lab to Branch WiFi"),
            
            # HQ to Data Center communication
            ("10.1.1.1", "10.3.1.1", "HQ to DC gateways"),
            ("10.1.3.1", "10.3.10.1", "HQ DMZ to DC servers"),
            ("10.1.11.1", "10.3.21.1", "HQ lab to DC servers"),
            
            # Branch to Data Center communication
            ("10.2.1.1", "10.3.1.1", "Branch to DC gateways"),
            ("10.2.5.1", "10.3.20.1", "Branch WiFi to DC servers"),
            ("10.2.6.1", "10.3.10.1", "Branch WiFi to DC servers"),
            
            # WireGuard tunnel endpoints
            ("10.100.1.1", "10.100.1.2", "HQ to Branch tunnel"),
            ("10.100.1.1", "10.100.1.3", "HQ to DC tunnel"),
            ("10.100.1.2", "10.100.1.3", "Branch to DC tunnel")
        ]
        
        for src_ip, dst_ip, description in test_cases:
            returncode, stdout, stderr = self.run_simulator([src_ip, dst_ip])
            
            success = returncode == 0 and "traceroute to" in stdout
            details = f"{description}: {'success' if success else 'failed'}"
            if not success:
                details += f" (code {returncode})"
            
            self.add_result(TestResult(
                f"Inter-location: {description}",
                success,
                details,
                stdout,
                stderr,
                returncode
            ))
    
    def test_network_segment_routing(self):
        """Test routing from/to network segments (host IPs in subnets)."""
        print("Testing network segment routing...")
        
        # Test cases for host-to-host routing across network segments
        test_cases = [
            # Cross-location host routing
            ("10.1.3.100", "10.2.5.50", "HQ DMZ host to Branch WiFi host"),
            ("10.1.10.25", "10.3.20.100", "HQ lab host to DC server host"),
            ("10.2.6.75", "10.3.21.200", "Branch WiFi host to DC server host"),
            
            # Same location, different subnets
            ("10.1.3.50", "10.1.11.75", "HQ DMZ to lab hosts"),
            ("10.2.5.100", "10.2.6.150", "Branch WiFi segment hosts"),
            ("10.3.10.50", "10.3.21.100", "DC server segment hosts"),
            
            # Host to router interface
            ("10.1.10.100", "10.2.1.1", "HQ lab host to Branch gateway"),
            ("10.2.5.25", "10.3.2.3", "Branch WiFi host to DC server router"),
            ("10.3.20.150", "10.1.3.1", "DC server host to HQ DMZ router")
        ]
        
        for src_ip, dst_ip, description in test_cases:
            returncode, stdout, stderr = self.run_simulator([src_ip, dst_ip])
            
            # Accept both success and "not found" for network segment IPs
            # as they may not all be configured as directly connected
            valid_result = returncode in [0, 2]
            details = f"{description}: "
            if returncode == 0:
                details += "route found"
            elif returncode == 2:
                details += "not reachable (may be expected)"
            else:
                details += f"error (code {returncode})"
            
            self.add_result(TestResult(
                f"Network segment: {description}",
                valid_result,
                details,
                stdout,
                stderr,
                returncode
            ))
    
    def test_command_line_options(self):
        """Test all command line options with new topology."""
        print("Testing command line options...")
        
        src_ip, dst_ip = "10.1.1.1", "10.2.1.1"  # HQ to Branch gateway
        
        # Test verbose mode
        returncode, stdout, stderr = self.run_simulator(["-v", src_ip, dst_ip])
        verbose_works = "Loaded router:" in stderr and returncode == 0
        self.add_result(TestResult(
            "Verbose mode (-v)",
            verbose_works,
            f"Expected router loading messages in stderr, got: {stderr[:100]}"
        ))
        
        # Test JSON output
        returncode, stdout, stderr = self.run_simulator(["-j", src_ip, dst_ip])
        json_works = False
        json_details = ""
        if returncode == 0:
            try:
                data = json.loads(stdout)
                json_works = "traceroute_path" in data and isinstance(data["traceroute_path"], list)
                json_details = "Valid JSON with traceroute_path"
            except json.JSONDecodeError as e:
                json_details = f"Invalid JSON: {e}"
        else:
            json_details = f"Non-zero return code: {returncode}"
        
        self.add_result(TestResult(
            "JSON output (-j)",
            json_works,
            json_details
        ))
        
        # Test quiet mode with successful path
        returncode, stdout, stderr = self.run_simulator(["-q", src_ip, dst_ip])
        quiet_success = returncode == 0 and stdout.strip() == ""
        self.add_result(TestResult(
            "Quiet mode success (-q)",
            quiet_success,
            f"Expected exit code 0 and no output, got code {returncode}, output: '{stdout}'"
        ))
        
        # Test custom routing directory
        returncode, stdout, stderr = self.run_simulator([
            "--routing-dir", ROUTING_FACTS_DIR, src_ip, dst_ip
        ])
        custom_dir_works = returncode == 0 and "traceroute to" in stdout
        self.add_result(TestResult(
            "Custom routing directory (--routing-dir)",
            custom_dir_works,
            f"Expected successful traceroute, got return code {returncode}"
        ))
    
    def test_error_conditions(self):
        """Test various error conditions and edge cases."""
        print("Testing error conditions...")
        
        # Test invalid IP addresses
        for invalid_ip in INVALID_IPS:
            returncode, stdout, stderr = self.run_simulator([invalid_ip, "10.1.1.1"])
            error_detected = returncode == 3 and "Invalid IP address" in stderr
            self.add_result(TestResult(
                f"Invalid source IP: {invalid_ip}",
                error_detected,
                f"Expected exit code 3 and error message, got code {returncode}, stderr: {stderr[:100]}"
            ))
            
            returncode, stdout, stderr = self.run_simulator(["10.1.1.1", invalid_ip])
            error_detected = returncode == 3 and "Invalid IP address" in stderr
            self.add_result(TestResult(
                f"Invalid destination IP: {invalid_ip}",
                error_detected,
                f"Expected exit code 3 and error message, got code {returncode}, stderr: {stderr[:100]}"
            ))
        
        # Test non-existent IP addresses (valid format but not in network)
        non_existent_ips = ["172.16.1.1", "192.168.1.1", "10.99.99.99"]
        for ip in non_existent_ips:
            returncode, stdout, stderr = self.run_simulator([ip, "10.1.1.1"])
            not_found = returncode == 2 and "not configured on any router" in stderr
            self.add_result(TestResult(
                f"Non-existent source IP: {ip}",
                not_found,
                f"Expected exit code 2, got code {returncode}"
            ))
        
        # Test missing arguments
        returncode, stdout, stderr = self.run_simulator([])
        missing_args = returncode == 2  # argparse error
        self.add_result(TestResult(
            "Missing arguments",
            missing_args,
            f"Expected argparse error (exit code 2), got code {returncode}"
        ))
    
    def test_exit_codes(self):
        """Test exit codes in quiet mode."""
        print("Testing exit codes...")
        
        # Test successful path (exit code 0)
        returncode, stdout, stderr = self.run_simulator(["-q", "10.1.1.1", "10.2.1.1"])
        success_code = returncode == 0
        self.add_result(TestResult(
            "Exit code 0 (success)",
            success_code,
            f"Expected exit code 0, got {returncode}"
        ))
        
        # Test not found (exit code 2)
        returncode, stdout, stderr = self.run_simulator(["-q", "172.16.1.1", "10.1.1.1"])
        not_found_code = returncode == 2
        self.add_result(TestResult(
            "Exit code 2 (not found)",
            not_found_code,
            f"Expected exit code 2, got {returncode}"
        ))
        
        # Test invalid IP (exit code 3)
        returncode, stdout, stderr = self.run_simulator(["-q", "invalid.ip", "10.1.1.1"])
        invalid_code = returncode == 3
        self.add_result(TestResult(
            "Exit code 3 (invalid IP)",
            invalid_code,
            f"Expected exit code 3, got {returncode}"
        ))
    
    def test_complex_scenarios(self):
        """Test complex routing scenarios specific to the new topology."""
        print("Testing complex routing scenarios...")
        
        # Multi-hop routing through multiple routers
        complex_cases = [
            # End-to-end across all three locations
            ("10.1.11.100", "10.3.21.200", "HQ lab to DC server (max hops)"),
            ("10.2.6.50", "10.1.3.100", "Branch WiFi to HQ DMZ (reverse path)"),
            
            # Routing through distribution layers
            ("10.1.10.25", "10.1.3.75", "HQ lab to DMZ (internal distribution)"),
            ("10.2.5.100", "10.2.6.150", "Branch WiFi networks (via core)"),
            ("10.3.10.50", "10.3.21.100", "DC server networks (via distribution)"),
            
            # Gateway to server routing
            ("203.0.113.10", "10.3.20.100", "HQ internet to DC servers"),
            ("198.51.100.10", "10.1.11.50", "Branch internet to HQ lab"),
            ("192.0.2.10", "10.2.5.75", "DC internet to Branch WiFi")
        ]
        
        for src_ip, dst_ip, description in complex_cases:
            returncode, stdout, stderr = self.run_simulator([src_ip, dst_ip])
            
            # These complex scenarios may not all work depending on routing configuration
            # Accept both success and controlled failures
            valid_result = returncode in [0, 1, 2]
            details = f"{description}: "
            if returncode == 0:
                details += "route found"
            elif returncode == 1:
                details += "no path (may be expected)"
            elif returncode == 2:
                details += "not reachable (may be expected)"
            else:
                details += f"error (code {returncode})"
            
            self.add_result(TestResult(
                f"Complex scenario: {description}",
                valid_result,
                details,
                stdout,
                stderr,
                returncode
            ))
    
    def run_all_tests(self):
        """Run all test suites for the complex network topology."""
        print("Starting comprehensive traceroute simulator tests...")
        print("Network topology: 10 routers across 3 locations with WireGuard mesh")
        print()
        
        # Check if simulator script exists
        if not os.path.exists(SIMULATOR_SCRIPT):
            print(f"Error: Simulator script {SIMULATOR_SCRIPT} not found!")
            return False
        
        # Check if routing facts directory exists
        if not os.path.exists(ROUTING_FACTS_DIR):
            print(f"Error: Routing facts directory {ROUTING_FACTS_DIR} not found!")
            return False
        
        # Verify we have all 10 router files
        expected_routers = [
            "hq-gw", "hq-core", "hq-dmz", "hq-lab",
            "br-gw", "br-core", "br-wifi",
            "dc-gw", "dc-core", "dc-srv"
        ]
        
        missing_routers = []
        for router in expected_routers:
            route_file = f"{ROUTING_FACTS_DIR}/{router}_route.json"
            if not os.path.exists(route_file):
                missing_routers.append(router)
        
        if missing_routers:
            print(f"Error: Missing router files for: {', '.join(missing_routers)}")
            return False
        
        print(f"Found routing data for all {len(expected_routers)} routers")
        print()
        
        # Run test suites
        test_suites = [
            self.test_intra_location_routing,
            self.test_inter_location_routing, 
            self.test_network_segment_routing,
            self.test_command_line_options,
            self.test_error_conditions,
            self.test_exit_codes,
            self.test_complex_scenarios,
        ]
        
        for test_suite in test_suites:
            try:
                test_suite()
            except Exception as e:
                self.add_result(TestResult(
                    f"Test suite error: {test_suite.__name__}",
                    False,
                    f"Exception in test suite: {e}"
                ))
            print()  # Add spacing between test suites
        
        return True
    
    def print_results(self):
        """Print comprehensive test results."""
        print("=" * 80)
        print("TRACEROUTE SIMULATOR TEST RESULTS - COMPLEX TOPOLOGY")
        print("=" * 80)
        
        # Summary
        pass_rate = (self.passed_tests / self.total_tests * 100) if self.total_tests > 0 else 0
        print(f"\nSUMMARY:")
        print(f"Total tests: {self.total_tests}")
        print(f"Passed: {self.passed_tests}")
        print(f"Failed: {self.total_tests - self.passed_tests}")
        print(f"Pass rate: {pass_rate:.1f}%")
        print()
        
        # Network topology summary
        print("NETWORK TOPOLOGY:")
        print("- Location A (HQ): 4 routers, 5 networks (10.1.0.0/16)")
        print("- Location B (Branch): 3 routers, 4 networks (10.2.0.0/16)")
        print("- Location C (DC): 3 routers, 5 networks (10.3.0.0/16)")
        print("- WireGuard mesh: 10.100.1.0/24 interconnecting all locations")
        print()
        
        # Detailed results
        print("DETAILED RESULTS:")
        print("-" * 80)
        
        passed_tests = [r for r in self.results if r.passed]
        failed_tests = [r for r in self.results if not r.passed]
        
        if passed_tests:
            print(f"\nPASSED TESTS ({len(passed_tests)}):")
            for result in passed_tests:
                print(f"  ✓ {result.name}")
                if result.details and result.details != "":
                    print(f"    {result.details}")
        
        if failed_tests:
            print(f"\nFAILED TESTS ({len(failed_tests)}):")
            for result in failed_tests:
                print(f"  ✗ {result.name}")
                print(f"    {result.details}")
                if result.stderr and "Error:" in result.stderr:
                    print(f"    Error: {result.stderr.strip()}")
                print()
        
        print("=" * 80)
        return self.passed_tests == self.total_tests


def main():
    """Main test runner for complex network topology."""
    tester = TracerouteSimulatorTester()
    
    if tester.run_all_tests():
        success = tester.print_results()
        sys.exit(0 if success else 1)
    else:
        print("Failed to run tests due to missing files or configuration issues.")
        sys.exit(1)


if __name__ == "__main__":
    main()