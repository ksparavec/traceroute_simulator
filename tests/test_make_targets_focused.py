#!/usr/bin/env -S python3 -B -u
"""
Focused test suite for namespace and host management make targets.

Tests core functionality and error conditions for:
- netsetup, nettest, netshow, netstatus, netclean
- hostadd, hostdel, hostlist, hostclean, netnsclean

Designed to run quickly while ensuring comprehensive code coverage.
"""

import os
import sys
import subprocess
import time
import json
import unittest
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class FocusedMakeTargetsTest(unittest.TestCase):
    """Focused test suite for make targets with essential coverage."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        cls.project_root = Path(__file__).parent.parent
        os.chdir(cls.project_root)
        
        # Check root privileges
        if os.geteuid() != 0:
            raise unittest.SkipTest("Tests require root privileges")
        
        # Ensure test facts exist
        cls.facts_dir = Path("/tmp/traceroute_test_output")
        if not cls.facts_dir.exists() or not list(cls.facts_dir.glob("*.json")):
            raise unittest.SkipTest("Test facts not available. Run 'make test' first.")
        
        cls.host_registry = Path("/tmp/traceroute_hosts_registry.json")
        print(f"Starting focused make targets tests")
        
    def setUp(self):
        """Clean state before each test."""
        self.run_make("netnsclean", ["-f"], check=False, timeout=30)
        time.sleep(0.5)
        
    def tearDown(self):
        """Clean state after each test."""
        self.run_make("netnsclean", ["-f"], check=False, timeout=30)
        
    def run_make(self, target: str, args: list = None, check: bool = True, 
                 timeout: int = 60) -> subprocess.CompletedProcess:
        """Run make target with arguments."""
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
            
    def check_namespace_exists(self, namespace: str) -> bool:
        """Check if namespace exists."""
        try:
            result = subprocess.run(
                ["ip", "netns", "list"], capture_output=True, text=True, check=True
            )
            return namespace in result.stdout
        except:
            return False
            
    def get_host_count(self) -> int:
        """Get number of registered hosts."""
        if self.host_registry.exists():
            try:
                with open(self.host_registry, 'r') as f:
                    return len(json.load(f))
            except:
                return 0
        return 0
    
    # ========================
    # CORE FUNCTIONALITY TESTS
    # ========================
    
    def test_netshow_basic(self):
        """Test netshow basic functionality (no sudo required)."""
        # Test valid router
        result = self.run_make("netshow", ["hq-gw", "interfaces"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("HQ-GW INTERFACE", result.stdout)
        
        # Test all summary
        result = self.run_make("netshow", ["all", "summary"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("NETWORK SUMMARY", result.stdout)
        
    def test_netshow_errors(self):
        """Test netshow error conditions."""
        # Invalid router
        result = self.run_make("netshow", ["invalid-router", "interfaces"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # Invalid function
        result = self.run_make("netshow", ["hq-gw", "invalid-function"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # No arguments
        result = self.run_make("netshow", [], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_network_setup_cleanup_cycle(self):
        """Test complete network setup and cleanup cycle."""
        # Setup network
        result = self.run_make("netsetup", ["-v"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("Network setup completed", result.stdout)
        
        # Verify namespaces exist
        self.assertTrue(self.check_namespace_exists("netsim"))
        self.assertTrue(self.check_namespace_exists("hq-gw"))
        self.assertTrue(self.check_namespace_exists("br-core"))
        
        # Test live status
        result = self.run_make("netstatus", ["hq-gw", "interfaces"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("eth1", result.stdout)
        
        # Test connectivity
        result = self.run_make("nettest", ["-s", "10.1.1.1", "-d", "10.2.1.1"])
        self.assertEqual(result.returncode, 0)
        
        # Clean up
        result = self.run_make("netclean", ["-v"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("cleanup completed", result.stdout)
        
        # Verify cleanup
        self.assertFalse(self.check_namespace_exists("hq-gw"))
        self.assertFalse(self.check_namespace_exists("netsim"))
        
    def test_host_management_cycle(self):
        """Test complete host management cycle."""
        # Setup network first
        self.run_make("netsetup")
        
        # Test empty host list
        result = self.run_make("hostlist")
        self.assertEqual(result.returncode, 0)
        self.assertIn("No hosts", result.stdout)
        
        # Add host
        result = self.run_make("hostadd", [
            "--host", "test1", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        self.assertEqual(result.returncode, 0)
        self.assertIn("created successfully", result.stdout)
        self.assertTrue(self.check_namespace_exists("test1"))
        
        # Add host with secondary IPs
        result = self.run_make("hostadd", [
            "--host", "test2", "--primary-ip", "10.2.1.100/24",
            "--secondary-ips", "192.168.100.1/24", "--connect-to", "br-gw"
        ])
        self.assertEqual(result.returncode, 0)
        
        # List hosts
        result = self.run_make("hostlist")
        self.assertEqual(result.returncode, 0)
        self.assertIn("test1", result.stdout)
        self.assertIn("test2", result.stdout)
        self.assertEqual(self.get_host_count(), 2)
        
        # Remove one host
        result = self.run_make("hostdel", ["--host", "test1", "--remove"])
        self.assertEqual(result.returncode, 0)
        self.assertFalse(self.check_namespace_exists("test1"))
        self.assertEqual(self.get_host_count(), 1)
        
        # Clean all hosts
        result = self.run_make("hostclean")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.get_host_count(), 0)
        
    def test_nettest_variants(self):
        """Test different nettest scenarios."""
        self.run_make("netsetup")
        
        # Basic ping test
        result = self.run_make("nettest", ["-s", "10.1.1.1", "-d", "10.2.1.1"])
        self.assertEqual(result.returncode, 0)
        
        # MTR test
        result = self.run_make("nettest", [
            "-s", "10.1.1.1", "-d", "10.2.1.1", "--test-type", "mtr"
        ])
        self.assertEqual(result.returncode, 0)
        
        # External IP test (should work with public IP handling)
        result = self.run_make("nettest", [
            "-s", "10.1.1.1", "-d", "8.8.8.8", "--test-type", "ping"
        ], timeout=30)
        self.assertEqual(result.returncode, 0)
        
    def test_netstatus_variants(self):
        """Test netstatus with different options."""
        self.run_make("netsetup")
        
        # Router interfaces
        result = self.run_make("netstatus", ["hq-gw", "interfaces"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("eth1", result.stdout)
        
        # Router routes
        result = self.run_make("netstatus", ["br-core", "routes"])
        self.assertEqual(result.returncode, 0)
        
        # All summary
        result = self.run_make("netstatus", ["all", "summary"])
        self.assertEqual(result.returncode, 0)
        
    # ========================
    # ERROR CONDITION TESTS
    # ========================
    
    def test_operations_without_setup(self):
        """Test operations when network not set up."""
        # nettest without setup
        result = self.run_make("nettest", ["-s", "10.1.1.1", "-d", "10.2.1.1"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # netstatus without setup
        result = self.run_make("netstatus", ["hq-gw", "interfaces"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # hostadd without setup
        result = self.run_make("hostadd", [
            "--host", "test", "--primary-ip", "10.1.1.100/24"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_invalid_arguments(self):
        """Test various invalid argument scenarios."""
        self.run_make("netsetup")
        
        # Invalid nettest arguments
        result = self.run_make("nettest", [], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        result = self.run_make("nettest", [
            "-s", "10.1.1.1", "-d", "10.2.1.1", "--test-type", "invalid"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # Invalid hostadd arguments
        result = self.run_make("hostadd", [
            "--host", "test", "--primary-ip", "invalid-ip"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        result = self.run_make("hostadd", [
            "--host", "test", "--primary-ip", "10.1.1.100/24", "--connect-to", "invalid-router"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # Invalid hostdel arguments
        result = self.run_make("hostdel", ["--host", "nonexistent", "--remove"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_duplicate_operations(self):
        """Test duplicate and conflicting operations."""
        self.run_make("netsetup")
        
        # Add host
        self.run_make("hostadd", [
            "--host", "test", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        
        # Try to add same host again
        result = self.run_make("hostadd", [
            "--host", "test", "--primary-ip", "10.1.1.101/24", "--connect-to", "hq-gw"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # Setup when already set up (should handle gracefully)
        result = self.run_make("netsetup", check=False)
        # Either succeeds (cleanup and recreate) or fails gracefully
        self.assertIn(result.returncode, [0, 1])
        
    def test_cleanup_robustness(self):
        """Test cleanup operations in various states."""
        # Clean when nothing exists
        result = self.run_make("netclean", check=False)
        self.assertIn(result.returncode, [0, 1])  # Should handle gracefully
        
        # Clean hosts when none exist
        result = self.run_make("hostclean")
        self.assertEqual(result.returncode, 0)
        
        # Force cleanup
        result = self.run_make("netnsclean", ["-f"])
        self.assertEqual(result.returncode, 0)
        
    def test_verbosity_levels(self):
        """Test different verbosity levels."""
        # Netsetup with different verbosity
        result = self.run_make("netsetup", ["-v"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("INFO:", result.stdout)
        
        self.run_make("netclean", ["-f"], check=False)
        
        result = self.run_make("netsetup", ["-vv"])
        self.assertEqual(result.returncode, 0)
        
        # Host operations with verbosity
        result = self.run_make("hostadd", [
            "--host", "test", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw", "-v"
        ])
        self.assertEqual(result.returncode, 0)
        self.assertIn("INFO:", result.stdout)
        
    def test_complex_host_scenarios(self):
        """Test complex host management scenarios."""
        self.run_make("netsetup")
        
        # Host with auto-detected router
        result = self.run_make("hostadd", [
            "--host", "auto", "--primary-ip", "10.3.1.100/24"
        ])
        self.assertEqual(result.returncode, 0)
        
        # Host with specific interface
        result = self.run_make("hostadd", [
            "--host", "specific", "--primary-ip", "10.1.11.100/24",
            "--connect-to", "hq-lab", "--router-interface", "eth2"
        ])
        self.assertEqual(result.returncode, 0)
        
        # Multiple secondary IPs
        result = self.run_make("hostadd", [
            "--host", "multi", "--primary-ip", "10.2.1.100/24",
            "--secondary-ips", "192.168.1.1/24,172.16.1.1/24,10.99.1.1/24"
        ])
        self.assertEqual(result.returncode, 0)
        
        # Verify all hosts
        result = self.run_make("hostlist")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.get_host_count(), 3)
        
    # ========================
    # INTEGRATION TESTS
    # ========================
    
    def test_end_to_end_workflow(self):
        """Test complete end-to-end workflow."""
        # 1. Setup network
        result = self.run_make("netsetup", ["-v"])
        self.assertEqual(result.returncode, 0)
        
        # 2. Add hosts
        self.run_make("hostadd", [
            "--host", "web", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        self.run_make("hostadd", [
            "--host", "db", "--primary-ip", "10.2.1.100/24", "--connect-to", "br-gw"
        ])
        
        # 3. Test connectivity between routers
        result = self.run_make("nettest", ["-s", "10.1.1.1", "-d", "10.2.1.1"])
        self.assertEqual(result.returncode, 0)
        
        # 4. Test external connectivity
        result = self.run_make("nettest", [
            "-s", "10.1.1.1", "-d", "8.8.8.8", "--test-type", "ping"
        ], timeout=30)
        self.assertEqual(result.returncode, 0)
        
        # 5. Check network status
        result = self.run_make("netstatus", ["all", "summary"])
        self.assertEqual(result.returncode, 0)
        
        # 6. Verify static topology view
        result = self.run_make("netshow", ["all", "topology"])
        self.assertEqual(result.returncode, 0)
        
        # 7. List hosts
        result = self.run_make("hostlist")
        self.assertEqual(result.returncode, 0)
        self.assertIn("web", result.stdout)
        self.assertIn("db", result.stdout)
        
        # 8. Clean everything
        result = self.run_make("netnsclean", ["-v"])
        self.assertEqual(result.returncode, 0)
        
        # 9. Verify complete cleanup
        self.assertFalse(self.check_namespace_exists("web"))
        self.assertFalse(self.check_namespace_exists("db"))
        self.assertFalse(self.check_namespace_exists("hq-gw"))
        self.assertEqual(self.get_host_count(), 0)


def main():
    """Run the focused test suite."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(FocusedMakeTargetsTest)
    
    runner = unittest.TextTestRunner(verbosity=2, buffer=False)
    result = runner.run(suite)
    
    print(f"\n{'='*60}")
    print("FOCUSED MAKE TARGETS TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.failures or result.errors:
        print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    else:
        print("Success rate: 100.0%")
        
    exit_code = 0 if result.wasSuccessful() else 1
    sys.exit(exit_code)


if __name__ == '__main__':
    main()