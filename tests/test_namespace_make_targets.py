#!/usr/bin/env python3
"""
Comprehensive test suite for namespace and host management make targets.

Tests all make targets related to namespace simulation and host management:
- netsetup: Network namespace setup
- nettest: Network connectivity testing  
- netshow: Static network topology viewing
- netstatus: Live namespace status
- netclean: Network namespace cleanup
- hostadd: Dynamic host addition
- hostdel: Host removal
- hostlist: Host registry listing
- hostclean: All hosts cleanup
- netnsclean: Complete cleanup

Includes basic functionality tests, complex scenarios, error conditions,
and exception handling to ensure comprehensive code coverage.
"""

import os
import sys
import subprocess
import time
import json
import tempfile
import shutil
import unittest
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class NamespaceMakeTargetsTest(unittest.TestCase):
    """Comprehensive test suite for namespace make targets."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment before running tests."""
        cls.project_root = Path(__file__).parent.parent
        cls.makefile = cls.project_root / "Makefile"
        
        # Ensure we're in project directory
        os.chdir(cls.project_root)
        
        # Check if running as root (required for namespace tests)
        if os.geteuid() != 0:
            raise unittest.SkipTest("Namespace tests require root privileges")
        
        # Ensure test facts are available
        cls.facts_dir = Path("/tmp/traceroute_test_output")
        if not cls.facts_dir.exists() or not list(cls.facts_dir.glob("*.json")):
            raise unittest.SkipTest("Test facts not available. Run 'make test' first.")
        
        # Test registry file for hosts
        cls.host_registry = Path("/tmp/traceroute_hosts_registry.json")
        
        # Initialize test counters
        cls.test_count = 0
        cls.success_count = 0
        cls.failure_count = 0
        
        print(f"Starting namespace make targets tests in {cls.project_root}")
        print(f"Test facts directory: {cls.facts_dir}")
        print(f"Available JSON files: {len(list(cls.facts_dir.glob('*.json')))}")
        
    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        print(f"\nTest Summary:")
        print(f"  Total tests: {cls.test_count}")
        print(f"  Successes: {cls.success_count}")
        print(f"  Failures: {cls.failure_count}")
        
        # Ensure complete cleanup
        try:
            cls.run_make_target("netnsclean", args=["-f"], check=False, timeout=30)
        except Exception:
            pass
            
    def setUp(self):
        """Set up before each test."""
        self.__class__.test_count += 1
        
        # Ensure clean state before each test
        self.run_make_target("netnsclean", args=["-f"], check=False, timeout=30)
        time.sleep(1)  # Brief pause for cleanup to complete
        
    def tearDown(self):
        """Clean up after each test."""
        # Clean up any test resources
        self.run_make_target("netnsclean", args=["-f"], check=False, timeout=30)
        time.sleep(0.5)
        
    def run_make_target(self, target: str, args: List[str] = None, 
                       check: bool = True, timeout: int = 60, 
                       capture_output: bool = True) -> subprocess.CompletedProcess:
        """Run a make target with arguments."""
        cmd = ["make", target]
        if args:
            cmd.extend(["ARGS=" + " ".join(args)])
            
        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                check=check,
                cwd=self.project_root
            )
            if result.returncode == 0:
                self.__class__.success_count += 1
            else:
                self.__class__.failure_count += 1
            return result
        except subprocess.CalledProcessError as e:
            self.__class__.failure_count += 1
            if check:
                raise
            return e
        except subprocess.TimeoutExpired as e:
            self.__class__.failure_count += 1
            if check:
                raise
            # Return a mock result for timeout cases
            return subprocess.CompletedProcess(cmd, 124, "", f"Timeout after {timeout}s")
            
    def check_namespace_exists(self, namespace: str) -> bool:
        """Check if a namespace exists."""
        try:
            result = subprocess.run(
                ["ip", "netns", "list"],
                capture_output=True,
                text=True,
                check=True
            )
            return namespace in result.stdout
        except:
            return False
            
    def get_host_registry(self) -> Dict[str, Any]:
        """Get current host registry."""
        if self.host_registry.exists():
            try:
                with open(self.host_registry, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
        
    def count_json_facts(self) -> int:
        """Count available JSON facts files."""
        return len(list(self.facts_dir.glob("*.json")))
        
    # ========================
    # NETSETUP Tests
    # ========================
    
    def test_netsetup_basic(self):
        """Test basic network namespace setup."""
        result = self.run_make_target("netsetup")
        self.assertEqual(result.returncode, 0)
        
        # Verify namespaces were created
        self.assertTrue(self.check_namespace_exists("netsim"))
        self.assertTrue(self.check_namespace_exists("hq-gw"))
        self.assertTrue(self.check_namespace_exists("br-core"))
        self.assertTrue(self.check_namespace_exists("dc-srv"))
        
    def test_netsetup_verbose_levels(self):
        """Test network setup with different verbosity levels."""
        # Test basic verbosity
        result = self.run_make_target("netsetup", args=["-v"])
        self.assertEqual(result.returncode, 0)
        
        # Clean and test info verbosity
        self.run_make_target("netclean", args=["-f"], check=False)
        result = self.run_make_target("netsetup", args=["-vv"])
        self.assertEqual(result.returncode, 0)
        
        # Clean and test debug verbosity
        self.run_make_target("netclean", args=["-f"], check=False)
        result = self.run_make_target("netsetup", args=["-vvv"])
        self.assertEqual(result.returncode, 0)
        
    def test_netsetup_already_exists(self):
        """Test setup when namespaces already exist."""
        # First setup
        result = self.run_make_target("netsetup")
        self.assertEqual(result.returncode, 0)
        
        # Second setup should handle existing namespaces
        result = self.run_make_target("netsetup", check=False)
        # Should either succeed (cleanup and recreate) or fail gracefully
        self.assertIn(result.returncode, [0, 1])
        
    def test_netsetup_invalid_args(self):
        """Test setup with invalid arguments."""
        result = self.run_make_target("netsetup", args=["--invalid-flag"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    # ========================
    # NETCLEAN Tests  
    # ========================
    
    def test_netclean_basic(self):
        """Test basic network cleanup."""
        # Setup first
        self.run_make_target("netsetup")
        self.assertTrue(self.check_namespace_exists("hq-gw"))
        
        # Clean
        result = self.run_make_target("netclean")
        self.assertEqual(result.returncode, 0)
        
        # Verify cleanup
        self.assertFalse(self.check_namespace_exists("hq-gw"))
        self.assertFalse(self.check_namespace_exists("netsim"))
        
    def test_netclean_verbose(self):
        """Test cleanup with verbose output."""
        self.run_make_target("netsetup")
        result = self.run_make_target("netclean", args=["-v"])
        self.assertEqual(result.returncode, 0)
        
    def test_netclean_force(self):
        """Test force cleanup."""
        self.run_make_target("netsetup")
        result = self.run_make_target("netclean", args=["-f"])
        self.assertEqual(result.returncode, 0)
        
    def test_netclean_no_namespaces(self):
        """Test cleanup when no namespaces exist."""
        result = self.run_make_target("netclean", check=False)
        # Should succeed even if nothing to clean
        self.assertIn(result.returncode, [0, 1])
        
    # ========================
    # NETTEST Tests
    # ========================
    
    def test_nettest_basic_ping(self):
        """Test basic ping connectivity."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("nettest", args=["-s", "10.1.1.1", "-d", "10.2.1.1"])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_mtr(self):
        """Test MTR traceroute."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("nettest", args=[
            "-s", "10.1.1.1", "-d", "10.2.1.1", "--test-type", "mtr"
        ])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_both_types(self):
        """Test both ping and MTR."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("nettest", args=[
            "-s", "10.1.1.1", "-d", "10.2.1.1", "--test-type", "both", "-v"
        ])
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_all_routers(self):
        """Test connectivity between all routers."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("nettest", args=["--all"], timeout=120)
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_external_ip(self):
        """Test connectivity to external IP."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("nettest", args=[
            "-s", "10.1.1.1", "-d", "8.8.8.8", "--test-type", "both", "-v"
        ], timeout=30)
        self.assertEqual(result.returncode, 0)
        
    def test_nettest_invalid_args(self):
        """Test with invalid arguments."""
        self.run_make_target("netsetup")
        
        # Missing required arguments
        result = self.run_make_target("nettest", args=[], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # Invalid test type
        result = self.run_make_target("nettest", args=[
            "-s", "10.1.1.1", "-d", "10.2.1.1", "--test-type", "invalid"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_nettest_no_namespaces(self):
        """Test when namespaces don't exist."""
        result = self.run_make_target("nettest", args=[
            "-s", "10.1.1.1", "-d", "10.2.1.1"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    # ========================
    # NETSHOW Tests (no sudo required)
    # ========================
    
    def test_netshow_router_interfaces(self):
        """Test showing router interfaces from facts."""
        result = self.run_make_target("netshow", args=["hq-gw", "interfaces"])
        self.assertEqual(result.returncode, 0)
        
    def test_netshow_router_routes(self):
        """Test showing router routes from facts."""
        result = self.run_make_target("netshow", args=["br-core", "routes"])
        self.assertEqual(result.returncode, 0)
        
    def test_netshow_router_summary(self):
        """Test showing router summary from facts."""
        result = self.run_make_target("netshow", args=["hq-dmz", "summary"])
        self.assertEqual(result.returncode, 0)
        
    def test_netshow_all_topology(self):
        """Test showing complete network topology."""
        result = self.run_make_target("netshow", args=["all", "topology"])
        self.assertEqual(result.returncode, 0)
        
    def test_netshow_all_summary(self):
        """Test showing summary of all routers."""
        result = self.run_make_target("netshow", args=["all", "summary"])
        self.assertEqual(result.returncode, 0)
        
    def test_netshow_verbose(self):
        """Test netshow with verbose output."""
        result = self.run_make_target("netshow", args=["hq-gw", "interfaces", "-v"])
        self.assertEqual(result.returncode, 0)
        
    def test_netshow_invalid_router(self):
        """Test with invalid router name."""
        result = self.run_make_target("netshow", args=["invalid-router", "interfaces"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_netshow_invalid_function(self):
        """Test with invalid function."""
        result = self.run_make_target("netshow", args=["hq-gw", "invalid-function"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_netshow_no_args(self):
        """Test netshow without arguments."""
        result = self.run_make_target("netshow", args=[], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    # ========================
    # NETSTATUS Tests
    # ========================
    
    def test_netstatus_router_interfaces(self):
        """Test showing live router interfaces."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("netstatus", args=["hq-gw", "interfaces"])
        self.assertEqual(result.returncode, 0)
        
    def test_netstatus_router_routes(self):
        """Test showing live router routes."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("netstatus", args=["br-core", "routes"])
        self.assertEqual(result.returncode, 0)
        
    def test_netstatus_all_summary(self):
        """Test showing live summary of all namespaces."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("netstatus", args=["all", "summary"])
        self.assertEqual(result.returncode, 0)
        
    def test_netstatus_verbose(self):
        """Test netstatus with verbose output."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("netstatus", args=["hq-gw", "summary", "-v"])
        self.assertEqual(result.returncode, 0)
        
    def test_netstatus_no_namespaces(self):
        """Test when no namespaces exist."""
        result = self.run_make_target("netstatus", args=["hq-gw", "interfaces"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_netstatus_invalid_namespace(self):
        """Test with invalid namespace."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("netstatus", args=["invalid-ns", "interfaces"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    # ========================
    # HOSTADD Tests
    # ========================
    
    def test_hostadd_basic(self):
        """Test basic host addition."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("hostadd", args=[
            "--host", "web1", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        self.assertEqual(result.returncode, 0)
        
        # Verify host was created
        self.assertTrue(self.check_namespace_exists("web1"))
        registry = self.get_host_registry()
        self.assertIn("web1", registry)
        
    def test_hostadd_with_secondary_ips(self):
        """Test host addition with secondary IPs."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("hostadd", args=[
            "--host", "db1", "--primary-ip", "10.2.1.100/24",
            "--secondary-ips", "192.168.100.1/24,172.16.1.1/24",
            "--connect-to", "br-gw"
        ])
        self.assertEqual(result.returncode, 0)
        
        registry = self.get_host_registry()
        self.assertIn("db1", registry)
        self.assertEqual(len(registry["db1"]["secondary_ips"]), 2)
        
    def test_hostadd_auto_detect_router(self):
        """Test host addition with auto-detected router."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("hostadd", args=[
            "--host", "client1", "--primary-ip", "10.3.1.100/24"
        ])
        self.assertEqual(result.returncode, 0)
        
        registry = self.get_host_registry()
        self.assertIn("client1", registry)
        
    def test_hostadd_specific_interface(self):
        """Test host addition to specific router interface."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("hostadd", args=[
            "--host", "srv1", "--primary-ip", "10.1.11.100/24",
            "--connect-to", "hq-lab", "--router-interface", "eth2"
        ])
        self.assertEqual(result.returncode, 0)
        
    def test_hostadd_verbose(self):
        """Test host addition with verbose output."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("hostadd", args=[
            "--host", "web2", "--primary-ip", "10.1.1.101/24",
            "--connect-to", "hq-gw", "-vv"
        ])
        self.assertEqual(result.returncode, 0)
        
    def test_hostadd_duplicate_host(self):
        """Test adding duplicate host."""
        self.run_make_target("netsetup")
        
        # Add first host
        self.run_make_target("hostadd", args=[
            "--host", "web1", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        
        # Try to add same host again
        result = self.run_make_target("hostadd", args=[
            "--host", "web1", "--primary-ip", "10.1.1.101/24", "--connect-to", "hq-gw"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_hostadd_invalid_ip(self):
        """Test host addition with invalid IP."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("hostadd", args=[
            "--host", "web1", "--primary-ip", "invalid-ip", "--connect-to", "hq-gw"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_hostadd_invalid_router(self):
        """Test host addition with invalid router."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("hostadd", args=[
            "--host", "web1", "--primary-ip", "10.1.1.100/24", "--connect-to", "invalid-router"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_hostadd_no_namespaces(self):
        """Test host addition when network not set up."""
        result = self.run_make_target("hostadd", args=[
            "--host", "web1", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    # ========================
    # HOSTDEL Tests
    # ========================
    
    def test_hostdel_basic(self):
        """Test basic host deletion."""
        self.run_make_target("netsetup")
        
        # Add host first
        self.run_make_target("hostadd", args=[
            "--host", "web1", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        
        # Delete host
        result = self.run_make_target("hostdel", args=["--host", "web1", "--remove"])
        self.assertEqual(result.returncode, 0)
        
        # Verify host was removed
        self.assertFalse(self.check_namespace_exists("web1"))
        registry = self.get_host_registry()
        self.assertNotIn("web1", registry)
        
    def test_hostdel_verbose(self):
        """Test host deletion with verbose output."""
        self.run_make_target("netsetup")
        
        self.run_make_target("hostadd", args=[
            "--host", "web1", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        
        result = self.run_make_target("hostdel", args=["--host", "web1", "--remove", "-v"])
        self.assertEqual(result.returncode, 0)
        
    def test_hostdel_nonexistent_host(self):
        """Test deleting non-existent host."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("hostdel", args=["--host", "nonexistent", "--remove"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_hostdel_invalid_args(self):
        """Test host deletion with invalid arguments."""
        result = self.run_make_target("hostdel", args=["--host", "web1"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    # ========================
    # HOSTLIST Tests
    # ========================
    
    def test_hostlist_empty(self):
        """Test listing hosts when none exist."""
        result = self.run_make_target("hostlist")
        self.assertEqual(result.returncode, 0)
        
    def test_hostlist_with_hosts(self):
        """Test listing hosts when some exist."""
        self.run_make_target("netsetup")
        
        # Add some hosts
        self.run_make_target("hostadd", args=[
            "--host", "web1", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        self.run_make_target("hostadd", args=[
            "--host", "db1", "--primary-ip", "10.2.1.100/24", "--connect-to", "br-gw"
        ])
        
        result = self.run_make_target("hostlist")
        self.assertEqual(result.returncode, 0)
        self.assertIn("web1", result.stdout)
        self.assertIn("db1", result.stdout)
        
    # ========================
    # HOSTCLEAN Tests
    # ========================
    
    def test_hostclean_basic(self):
        """Test cleaning all hosts."""
        self.run_make_target("netsetup")
        
        # Add some hosts
        self.run_make_target("hostadd", args=[
            "--host", "web1", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        self.run_make_target("hostadd", args=[
            "--host", "db1", "--primary-ip", "10.2.1.100/24", "--connect-to", "br-gw"
        ])
        
        # Clean all hosts
        result = self.run_make_target("hostclean")
        self.assertEqual(result.returncode, 0)
        
        # Verify hosts were removed
        self.assertFalse(self.check_namespace_exists("web1"))
        self.assertFalse(self.check_namespace_exists("db1"))
        registry = self.get_host_registry()
        self.assertEqual(len(registry), 0)
        
    def test_hostclean_verbose(self):
        """Test host cleanup with verbose output."""
        self.run_make_target("netsetup")
        
        self.run_make_target("hostadd", args=[
            "--host", "web1", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        
        result = self.run_make_target("hostclean", args=["-v"])
        self.assertEqual(result.returncode, 0)
        
    def test_hostclean_no_hosts(self):
        """Test cleaning when no hosts exist."""
        result = self.run_make_target("hostclean")
        self.assertEqual(result.returncode, 0)
        
    # ========================
    # NETNSCLEAN Tests
    # ========================
    
    def test_netnsclean_basic(self):
        """Test complete namespace and host cleanup."""
        self.run_make_target("netsetup")
        
        # Add some hosts
        self.run_make_target("hostadd", args=[
            "--host", "web1", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        
        # Clean everything
        result = self.run_make_target("netnsclean")
        self.assertEqual(result.returncode, 0)
        
        # Verify everything was cleaned
        self.assertFalse(self.check_namespace_exists("web1"))
        self.assertFalse(self.check_namespace_exists("hq-gw"))
        self.assertFalse(self.check_namespace_exists("netsim"))
        registry = self.get_host_registry()
        self.assertEqual(len(registry), 0)
        
    def test_netnsclean_force(self):
        """Test force cleanup."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("netnsclean", args=["-f"])
        self.assertEqual(result.returncode, 0)
        
    def test_netnsclean_verbose(self):
        """Test cleanup with verbose output."""
        self.run_make_target("netsetup")
        
        result = self.run_make_target("netnsclean", args=["-v"])
        self.assertEqual(result.returncode, 0)
        
    # ========================
    # Complex Integration Tests
    # ========================
    
    def test_complete_workflow(self):
        """Test complete workflow: setup -> add hosts -> test -> cleanup."""
        # Setup network
        result = self.run_make_target("netsetup", args=["-v"])
        self.assertEqual(result.returncode, 0)
        
        # Add multiple hosts
        self.run_make_target("hostadd", args=[
            "--host", "web1", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        self.run_make_target("hostadd", args=[
            "--host", "db1", "--primary-ip", "10.2.1.100/24",
            "--secondary-ips", "192.168.100.1/24", "--connect-to", "br-gw"
        ])
        
        # Test connectivity
        result = self.run_make_target("nettest", args=["-s", "10.1.1.1", "-d", "10.2.1.1"])
        self.assertEqual(result.returncode, 0)
        
        # Show status
        result = self.run_make_target("netstatus", args=["all", "summary"])
        self.assertEqual(result.returncode, 0)
        
        # List hosts
        result = self.run_make_target("hostlist")
        self.assertEqual(result.returncode, 0)
        
        # Remove one host
        result = self.run_make_target("hostdel", args=["--host", "web1", "--remove"])
        self.assertEqual(result.returncode, 0)
        
        # Clean everything
        result = self.run_make_target("netnsclean", args=["-v"])
        self.assertEqual(result.returncode, 0)
        
    def test_error_recovery(self):
        """Test error recovery scenarios."""
        # Try operations without setup
        result = self.run_make_target("nettest", args=["-s", "10.1.1.1", "-d", "10.2.1.1"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # Setup and test partial failures
        self.run_make_target("netsetup")
        
        # Try to add invalid host
        result = self.run_make_target("hostadd", args=[
            "--host", "invalid", "--primary-ip", "999.999.999.999/24"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # Network should still be functional
        result = self.run_make_target("nettest", args=["-s", "10.1.1.1", "-d", "10.2.1.1"])
        self.assertEqual(result.returncode, 0)
        
    def test_concurrent_hosts(self):
        """Test adding multiple hosts rapidly."""
        self.run_make_target("netsetup")
        
        # Add multiple hosts quickly
        hosts = [
            ("web1", "10.1.1.100/24", "hq-gw"),
            ("web2", "10.1.1.101/24", "hq-gw"),
            ("db1", "10.2.1.100/24", "br-gw"),
            ("app1", "10.3.1.100/24", "dc-gw"),
        ]
        
        for host_name, ip, router in hosts:
            result = self.run_make_target("hostadd", args=[
                "--host", host_name, "--primary-ip", ip, "--connect-to", router
            ])
            self.assertEqual(result.returncode, 0)
            
        # Verify all hosts exist
        registry = self.get_host_registry()
        self.assertEqual(len(registry), 4)
        
        # Test connectivity from each host
        for host_name, _, _ in hosts:
            self.assertTrue(self.check_namespace_exists(host_name))
            
    def test_stress_testing(self):
        """Test system under stress conditions."""
        self.run_make_target("netsetup")
        
        # Add many hosts
        for i in range(5):
            self.run_make_target("hostadd", args=[
                "--host", f"host{i}", "--primary-ip", f"10.1.1.{100+i}/24", "--connect-to", "hq-gw"
            ])
            
        # Test all routers connectivity
        result = self.run_make_target("nettest", args=["--all"], timeout=180)
        self.assertEqual(result.returncode, 0)
        
        # Clean up rapidly
        result = self.run_make_target("hostclean", args=["-v"])
        self.assertEqual(result.returncode, 0)


def main():
    """Run the test suite."""
    # Configure test discovery and execution
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(NamespaceMakeTargetsTest)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(
        verbosity=2,
        stream=sys.stdout,
        buffer=False,
        failfast=False
    )
    
    result = runner.run(suite)
    
    # Exit with appropriate code
    exit_code = 0 if result.wasSuccessful() else 1
    
    print(f"\n{'='*60}")
    print("NAMESPACE MAKE TARGETS TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print(f"\nFailures:")
        for test, traceback in result.failures:
            newline = '\n'
            print(f"  - {test}: {traceback.split('AssertionError: ')[-1].split(newline)[0]}")
            
    if result.errors:
        print(f"\nErrors:")
        for test, traceback in result.errors:
            newline = '\n'
            print(f"  - {test}: {traceback.split(newline)[-2]}")
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()