#!/usr/bin/env -S python3 -B -u
"""
Test Suite for Bridge-Based Network Architecture

Tests the new bridge-based network setup where all router interfaces
are created as bridges immediately during netsetup, and hosts connect
directly to these bridges without requiring new veth pairs.

Test coverage:
- Bridge creation during netsetup
- Host connection to existing bridges
- Network connectivity through bridges
- Host-to-router communication
- Cleanup and teardown procedures
"""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


class TestBridgeArchitecture(unittest.TestCase):
    """Test bridge-based network architecture implementation."""

    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        # Ensure we're running as root
        if os.geteuid() != 0:
            raise unittest.SkipTest("Root privileges required for namespace testing")
            
        # Set up test environment
        os.environ['TRACEROUTE_SIMULATOR_FACTS'] = '/tmp/traceroute_test_output'
        
        # Ensure test facts are available
        facts_dir = Path('/tmp/traceroute_test_output')
        if not facts_dir.exists() or not list(facts_dir.glob('*.json')):
            raise unittest.SkipTest("Test facts not available. Run 'make test' first.")
            
    def setUp(self):
        """Set up each test."""
        # Clean up any existing namespaces/hosts
        subprocess.run("sudo make netclean ARGS='-f'", shell=True, capture_output=True)
        
        # Remove any existing host registry
        host_registry = Path("/var/opt/traceroute-simulator/traceroute_hosts_registry.json")
        if host_registry.exists():
            host_registry.unlink()
            
        # Wait a moment for cleanup
        time.sleep(0.5)
        
    def tearDown(self):
        """Clean up after each test."""
        # Clean up namespaces and hosts
        subprocess.run("sudo make netclean ARGS='-f'", shell=True, capture_output=True)
        
        # Remove host registry
        host_registry = Path("/var/opt/traceroute-simulator/traceroute_hosts_registry.json")
        if host_registry.exists():
            host_registry.unlink()
            
    def test_netsetup_creates_bridges(self):
        """Test that netsetup creates bridge interfaces for all router interfaces."""
        # Run netsetup
        result = subprocess.run("sudo make netsetup", shell=True, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"netsetup failed: {result.stderr}")
        
        # Check that bridges are created for sample routers
        test_cases = [
            ("hq-gw", "br-eth0"),  # External interface should have bridge
            ("hq-core", "br-eth1"), # Point-to-point interface should have bridge
        ]
        
        for router, expected_bridge in test_cases:
            # Check if bridge exists in router namespace
            check_cmd = f"ip netns exec {router} ip link show {expected_bridge}"
            bridge_result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            self.assertEqual(bridge_result.returncode, 0, 
                           f"Bridge {expected_bridge} not found in {router}: {bridge_result.stderr}")
            
            # Verify it's actually a bridge
            self.assertIn("bridge", bridge_result.stdout.lower(), 
                         f"{expected_bridge} is not a bridge interface")
    
    def test_host_connects_to_bridge(self):
        """Test that hosts can connect directly to existing bridges."""
        # Set up network
        setup_result = subprocess.run("sudo make netsetup", shell=True, capture_output=True, text=True)
        self.assertEqual(setup_result.returncode, 0, f"netsetup failed: {setup_result.stderr}")
        
        # Add a host that should connect to an existing bridge
        host_cmd = "sudo make hostadd ARGS='--host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw'"
        host_result = subprocess.run(host_cmd, shell=True, capture_output=True, text=True)
        self.assertEqual(host_result.returncode, 0, f"Host creation failed: {host_result.stderr}")
        
        # Verify host namespace exists
        ns_check = subprocess.run("ip netns list", shell=True, capture_output=True, text=True)
        self.assertIn("web1", ns_check.stdout, "Host namespace not created")
        
        # Verify host has eth0 interface with correct IP
        eth0_check = subprocess.run("ip netns exec web1 ip addr show eth0", 
                                  shell=True, capture_output=True, text=True)
        self.assertEqual(eth0_check.returncode, 0, "Host eth0 interface not found")
        self.assertIn("10.1.1.100/24", eth0_check.stdout, "Host IP not configured correctly")
        
    def test_host_to_router_connectivity(self):
        """Test connectivity between host and router through bridge."""
        # Set up network
        setup_result = subprocess.run("sudo make netsetup", shell=True, capture_output=True, text=True)
        self.assertEqual(setup_result.returncode, 0, f"netsetup failed: {setup_result.stderr}")
        
        # Add host
        host_cmd = "sudo make hostadd ARGS='--host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw'"
        host_result = subprocess.run(host_cmd, shell=True, capture_output=True, text=True)
        self.assertEqual(host_result.returncode, 0, f"Host creation failed: {host_result.stderr}")
        
        # Wait for network to settle
        time.sleep(1)
        
        # Test connectivity from host to router IP
        ping_cmd = "ip netns exec web1 ping -c 1 -W 2 10.1.1.1"  # hq-gw IP in this subnet
        ping_result = subprocess.run(ping_cmd, shell=True, capture_output=True, text=True)
        self.assertEqual(ping_result.returncode, 0, 
                        f"Host to router ping failed: {ping_result.stderr}")
        
    def test_host_list_functionality(self):
        """Test that hostlist correctly shows registered hosts."""
        # Set up network and add host
        subprocess.run("sudo make netsetup", shell=True, capture_output=True)
        subprocess.run("sudo make hostadd ARGS='--host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw'", 
                      shell=True, capture_output=True)
        
        # Test hostlist
        list_result = subprocess.run("sudo make hostlist", shell=True, capture_output=True, text=True)
        self.assertEqual(list_result.returncode, 0, f"hostlist failed: {list_result.stderr}")
        self.assertIn("web1", list_result.stdout, "Host not shown in hostlist")
        self.assertIn("10.1.1.100/24", list_result.stdout, "Host IP not shown in hostlist")
        
    def test_host_removal(self):
        """Test that hosts can be properly removed."""
        # Set up network and add host
        subprocess.run("sudo make netsetup", shell=True, capture_output=True)
        subprocess.run("sudo make hostadd ARGS='--host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw'", 
                      shell=True, capture_output=True)
        
        # Verify host exists
        ns_check = subprocess.run("ip netns list", shell=True, capture_output=True, text=True)
        self.assertIn("web1", ns_check.stdout, "Host not created")
        
        # Remove host
        remove_result = subprocess.run("sudo make hostdel ARGS='--remove-host web1'", 
                                     shell=True, capture_output=True, text=True)
        self.assertEqual(remove_result.returncode, 0, f"Host removal failed: {remove_result.stderr}")
        
        # Verify host namespace is gone
        ns_check_after = subprocess.run("ip netns list", shell=True, capture_output=True, text=True)
        self.assertNotIn("web1", ns_check_after.stdout, "Host namespace not removed")
        
    def test_multiple_hosts_same_bridge(self):
        """Test multiple hosts connecting to the same bridge."""
        # Set up network
        subprocess.run("sudo make netsetup", shell=True, capture_output=True)
        
        # Add multiple hosts to same subnet
        host1_cmd = "sudo make hostadd ARGS='--host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw'"
        host2_cmd = "sudo make hostadd ARGS='--host web2 --primary-ip 10.1.1.101/24 --connect-to hq-gw'"
        
        result1 = subprocess.run(host1_cmd, shell=True, capture_output=True, text=True)
        result2 = subprocess.run(host2_cmd, shell=True, capture_output=True, text=True)
        
        self.assertEqual(result1.returncode, 0, f"Host1 creation failed: {result1.stderr}")
        self.assertEqual(result2.returncode, 0, f"Host2 creation failed: {result2.stderr}")
        
        # Test connectivity between hosts
        time.sleep(1)
        ping_result = subprocess.run("ip netns exec web1 ping -c 1 -W 2 10.1.1.101", 
                                   shell=True, capture_output=True, text=True)
        self.assertEqual(ping_result.returncode, 0, 
                        f"Host-to-host ping failed: {ping_result.stderr}")
        
    def test_netshow_with_hosts(self):
        """Test that netshow works correctly with hosts."""
        # Set up network and add host
        subprocess.run("sudo make netsetup", shell=True, capture_output=True)
        subprocess.run("sudo make hostadd ARGS='--host web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw'", 
                      shell=True, capture_output=True)
        
        # Test netshow for host
        show_result = subprocess.run("sudo make netshow ARGS='web1 summary'", 
                                   shell=True, capture_output=True, text=True)
        self.assertEqual(show_result.returncode, 0, f"netshow failed: {show_result.stderr}")
        self.assertIn("web1", show_result.stdout, "Host not shown in netshow")
        self.assertIn("HOST", show_result.stdout, "Host type not shown")


def main():
    """Run the test suite."""
    # Check prerequisites
    if os.geteuid() != 0:
        print("Error: Root privileges required for bridge architecture tests")
        print("Please run: sudo python3 tests/test_bridge_architecture.py")
        sys.exit(1)
        
    # Check for test facts
    facts_dir = Path('/tmp/traceroute_test_output')
    if not facts_dir.exists() or not list(facts_dir.glob('*.json')):
        print("Error: Test facts not available")
        print("Please run 'make test' first to generate test facts")
        sys.exit(1)
        
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()