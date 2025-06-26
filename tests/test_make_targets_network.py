#!/usr/bin/env python3
"""
Network testing and status tests for make targets (Chunk 3).

Tests: nettest, netstatus, netnsclean
"""

import os
import sys
import subprocess
import time
import unittest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class NetworkMakeTargetsTest(unittest.TestCase):
    """Network testing and status tests."""
    
    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).parent.parent
        os.chdir(cls.project_root)
        
        if os.geteuid() != 0:
            raise unittest.SkipTest("Tests require root privileges")
        
        facts_dir = Path("/tmp/traceroute_test_output")
        if not facts_dir.exists() or not list(facts_dir.glob("*.json")):
            raise unittest.SkipTest("Test facts not available. Run 'make test' first.")
        
    def setUp(self):
        # Ensure complete cleanup using improved netclean
        self.run_make("hostclean", check=False, timeout=15)
        self.run_make("netclean", ["-f"], check=False, timeout=15)
        # Setup network for tests
        self.run_make("netsetup", timeout=60)
        time.sleep(0.5)
        
    def tearDown(self):
        self.run_make("hostclean", check=False, timeout=15)
        self.run_make("netclean", ["-f"], check=False, timeout=15)
        
    def run_make(self, target: str, args: list = None, check: bool = True, 
                 timeout: int = 30) -> subprocess.CompletedProcess:
        cmd = ["make", target]
        if args:
            cmd.extend(["ARGS=" + " ".join(args)])
            
        try:
            return subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                check=check, cwd=self.project_root
            )
        except subprocess.CalledProcessError as e:
            if check:
                raise
            return e
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(cmd, 124, "", f"Timeout after {timeout}s")
    
    def test_nettest_basic_ping(self):
        """Test basic ping connectivity within location."""
        result = self.run_make("nettest", ["-s", "10.1.1.1", "-d", "10.1.2.1"])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_basic_mtr(self):
        """Test basic MTR traceroute within location."""
        result = self.run_make("nettest", [
            "-s", "10.1.1.1", "-d", "10.1.2.1", "--test-type", "mtr"
        ])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_inter_location_ping(self):
        """Test ping between different locations (HQ to Branch)."""
        result = self.run_make("nettest", ["-s", "10.1.1.1", "-d", "10.2.1.1"])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_inter_location_mtr(self):
        """Test MTR between different locations (HQ to Branch)."""
        result = self.run_make("nettest", [
            "-s", "10.1.1.1", "-d", "10.2.1.1", "--test-type", "mtr"
        ])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_multi_hop_ping(self):
        """Test multi-hop ping (HQ internal to DC internal)."""
        result = self.run_make("nettest", ["-s", "10.1.10.1", "-d", "10.3.20.1"])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_multi_hop_mtr(self):
        """Test multi-hop MTR (HQ internal to DC internal)."""
        result = self.run_make("nettest", [
            "-s", "10.1.10.1", "-d", "10.3.20.1", "--test-type", "mtr"
        ])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_vpn_mesh_ping(self):
        """Test ping over VPN mesh (gateway to gateway via WireGuard)."""
        result = self.run_make("nettest", ["-s", "10.100.1.1", "-d", "10.100.1.2"])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_vpn_mesh_mtr(self):
        """Test MTR over VPN mesh (gateway to gateway via WireGuard)."""
        result = self.run_make("nettest", [
            "-s", "10.100.1.1", "-d", "10.100.1.2", "--test-type", "mtr"
        ])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_complex_path_ping(self):
        """Test complex path ping (Branch WiFi to DC Server)."""
        result = self.run_make("nettest", ["-s", "10.2.5.1", "-d", "10.3.21.1"])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_complex_path_mtr(self):
        """Test complex path MTR (Branch WiFi to DC Server)."""
        result = self.run_make("nettest", [
            "-s", "10.2.5.1", "-d", "10.3.21.1", "--test-type", "mtr"
        ])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_both_methods(self):
        """Test both ping and MTR methods on same path."""
        result = self.run_make("nettest", [
            "-s", "10.1.1.1", "-d", "10.3.1.1", "--test-type", "both", "-v"
        ])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_external_ip_ping(self):
        """Test external IP connectivity via gateway (ping)."""
        result = self.run_make("nettest", [
            "-s", "10.1.1.1", "-d", "8.8.8.8", "--test-type", "ping"
        ], timeout=40)
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_external_ip_mtr(self):
        """Test external IP connectivity via gateway (MTR)."""
        result = self.run_make("nettest", [
            "-s", "10.1.1.1", "-d", "1.1.1.1", "--test-type", "mtr"
        ], timeout=40)
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_external_from_internal_ping(self):
        """Test external connectivity from internal network (multi-hop)."""
        result = self.run_make("nettest", [
            "-s", "10.1.10.1", "-d", "8.8.8.8", "--test-type", "ping"
        ], timeout=40)
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_external_from_internal_mtr(self):
        """Test external connectivity from internal network via MTR."""
        result = self.run_make("nettest", [
            "-s", "10.3.20.1", "-d", "1.1.1.1", "--test-type", "mtr"
        ], timeout=40)
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_all_locations_ping(self):
        """Test ping connectivity across all three locations."""
        # HQ to Branch
        result = self.run_make("nettest", ["-s", "10.1.1.1", "-d", "10.2.1.1"])
        self.assertEqual(result.returncode, 0)
        
        # HQ to DC
        result = self.run_make("nettest", ["-s", "10.1.1.1", "-d", "10.3.1.1"])
        self.assertEqual(result.returncode, 0)
        
        # Branch to DC
        result = self.run_make("nettest", ["-s", "10.2.1.1", "-d", "10.3.1.1"])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_all_locations_mtr(self):
        """Test MTR traceroute across all three locations."""
        # HQ to Branch
        result = self.run_make("nettest", [
            "-s", "10.1.1.1", "-d", "10.2.1.1", "--test-type", "mtr"
        ])
        self.assertEqual(result.returncode, 0)
        
        # HQ to DC  
        result = self.run_make("nettest", [
            "-s", "10.1.1.1", "-d", "10.3.1.1", "--test-type", "mtr"
        ])
        self.assertEqual(result.returncode, 0)
        
        # Branch to DC
        result = self.run_make("nettest", [
            "-s", "10.2.1.1", "-d", "10.3.1.1", "--test-type", "mtr"
        ])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_internal_networks_ping(self):
        """Test ping between internal network segments."""
        # HQ internal segments
        result = self.run_make("nettest", ["-s", "10.1.10.1", "-d", "10.1.11.1"])
        self.assertEqual(result.returncode, 0)
        
        # Branch WiFi networks
        result = self.run_make("nettest", ["-s", "10.2.5.1", "-d", "10.2.6.1"])
        self.assertEqual(result.returncode, 0)
        
        # DC server networks
        result = self.run_make("nettest", ["-s", "10.3.10.1", "-d", "10.3.20.1"])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_internal_networks_mtr(self):
        """Test MTR between internal network segments."""
        # HQ internal segments
        result = self.run_make("nettest", [
            "-s", "10.1.10.1", "-d", "10.1.11.1", "--test-type", "mtr"
        ])
        self.assertEqual(result.returncode, 0)
        
        # Branch WiFi networks
        result = self.run_make("nettest", [
            "-s", "10.2.5.1", "-d", "10.2.6.1", "--test-type", "mtr"
        ])
        self.assertEqual(result.returncode, 0)
        
        # DC server networks
        result = self.run_make("nettest", [
            "-s", "10.3.10.1", "-d", "10.3.20.1", "--test-type", "mtr"
        ])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_longest_paths(self):
        """Test the longest possible paths in the network."""
        # Longest path: HQ-LAB eth1 to DC-SRV eth3 (crosses all locations)
        result = self.run_make("nettest", [
            "-s", "10.1.10.1", "-d", "10.3.21.1", "--test-type", "both", "-v"
        ], timeout=50)
        self.assertEqual(result.returncode, 0)
        
        # Another long path: Branch WiFi to HQ DMZ
        result = self.run_make("nettest", [
            "-s", "10.2.6.1", "-d", "10.1.3.1", "--test-type", "both", "-v"
        ], timeout=50)
        self.assertEqual(result.returncode, 0)
        
    def test_netstatus_interfaces(self):
        """Test showing live interfaces."""
        result = self.run_make("netstatus", ["hq-gw", "interfaces"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("eth1", result.stdout)
        self.assertIn("10.1.1.1", result.stdout)
        
    def test_netstatus_routes(self):
        """Test showing live routes."""
        result = self.run_make("netstatus", ["br-core", "routes"])
        self.assertEqual(result.returncode, 0)
        
    def test_netstatus_summary(self):
        """Test live summary."""
        result = self.run_make("netstatus", ["all", "summary"], timeout=40)
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_errors(self):
        """Test nettest error conditions."""
        # No arguments
        result = self.run_make("nettest", [], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # Invalid test type
        result = self.run_make("nettest", [
            "-s", "10.1.1.1", "-d", "10.2.1.1", "--test-type", "invalid"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_netstatus_errors(self):
        """Test netstatus error conditions."""
        # Invalid namespace
        result = self.run_make("netstatus", ["invalid-ns", "interfaces"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_netnsclean_complete(self):
        """Test complete namespace cleanup."""
        # Add a host to make cleanup more comprehensive
        self.run_make("hostadd", [
            "--host", "cleanup-test", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        
        # Clean everything
        result = self.run_make("netnsclean", ["-v"], timeout=40)
        self.assertEqual(result.returncode, 0)
        self.assertIn("cleanup completed", result.stdout)
        
        # Verify complete cleanup
        ns_result = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True)
        self.assertNotIn("hq-gw", ns_result.stdout)
        self.assertNotIn("cleanup-test", ns_result.stdout)


def main():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(NetworkMakeTargetsTest)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print(f"\nNETWORK TESTS: {result.testsRun} run, {len(result.failures)} failures, {len(result.errors)} errors")
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()