#!/usr/bin/env -S python3 -B -u
"""
Host management tests for make targets (Chunk 2).

Tests: hostadd, hostdel, hostlist, hostclean
"""

import os
import sys
import subprocess
import time
import json
import unittest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class HostMakeTargetsTest(unittest.TestCase):
    """Host management tests for make targets."""
    
    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).parent.parent
        os.chdir(cls.project_root)
        
        if os.geteuid() != 0:
            raise unittest.SkipTest("Tests require root privileges")
        
        facts_dir = Path("/tmp/traceroute_test_output")
        if not facts_dir.exists() or not list(facts_dir.glob("*.json")):
            raise unittest.SkipTest("Test facts not available. Run 'make test' first.")
        
        cls.host_registry = Path("/tmp/traceroute_hosts_registry.json")
        
    def setUp(self):
        # Ensure complete cleanup including any temporary hosts
        # The updated netclean now handles all simulation namespaces
        self.run_make("hostclean", check=False, timeout=15)
        self.run_make("netclean", ["-f"], check=False, timeout=15)
        # Setup network for host tests
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
    
    def get_host_count(self) -> int:
        """Get number of registered hosts."""
        if self.host_registry.exists():
            try:
                with open(self.host_registry, 'r') as f:
                    return len(json.load(f))
            except:
                return 0
        return 0
    
    def test_hostlist_empty(self):
        """Test listing when no hosts exist."""
        result = self.run_make("hostlist")
        self.assertEqual(result.returncode, 0)
        self.assertIn("No hosts", result.stdout)
        
    def test_hostadd_basic(self):
        """Test basic host addition."""
        result = self.run_make("hostadd", [
            "--host", "test1", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw", "-v"
        ])
        self.assertEqual(result.returncode, 0)
        self.assertIn("created successfully", result.stdout)
        
        # Verify host exists
        ns_result = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True)
        self.assertIn("test1", ns_result.stdout)
        self.assertEqual(self.get_host_count(), 1)
        
    def test_hostadd_with_secondary_ips(self):
        """Test host with secondary IPs."""
        result = self.run_make("hostadd", [
            "--host", "test2", "--primary-ip", "10.2.1.100/24",
            "--secondary-ips", "192.168.100.1/24", "--connect-to", "br-gw"
        ])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.get_host_count(), 1)
        
    def test_hostdel_basic(self):
        """Test host deletion."""
        # Add host first
        self.run_make("hostadd", [
            "--host", "test3", "--primary-ip", "10.1.1.101/24", "--connect-to", "hq-gw", "-v"
        ])
        
        # Delete host
        result = self.run_make("hostdel", ["--host", "test3", "--remove", "-v"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("removed successfully", result.stdout)
        
        # Verify removal
        ns_result = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True)
        self.assertNotIn("test3", ns_result.stdout)
        self.assertEqual(self.get_host_count(), 0)
        
    def test_hostlist_with_hosts(self):
        """Test listing with hosts."""
        # Add two hosts
        self.run_make("hostadd", [
            "--host", "web", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        self.run_make("hostadd", [
            "--host", "db", "--primary-ip", "10.2.1.100/24", "--connect-to", "br-gw"
        ])
        
        # List hosts
        result = self.run_make("hostlist")
        self.assertEqual(result.returncode, 0)
        self.assertIn("web", result.stdout)
        self.assertIn("db", result.stdout)
        self.assertEqual(self.get_host_count(), 2)
        
    def test_hostclean(self):
        """Test cleaning all hosts."""
        # Add hosts
        self.run_make("hostadd", [
            "--host", "test4", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        self.run_make("hostadd", [
            "--host", "test5", "--primary-ip", "10.2.1.100/24", "--connect-to", "br-gw"
        ])
        
        # Clean all
        result = self.run_make("hostclean")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.get_host_count(), 0)
        
    def test_hostadd_errors(self):
        """Test host addition errors."""
        # Invalid IP
        result = self.run_make("hostadd", [
            "--host", "test", "--primary-ip", "invalid-ip", "--connect-to", "hq-gw"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # Invalid router
        result = self.run_make("hostadd", [
            "--host", "test", "--primary-ip", "10.1.1.100/24", "--connect-to", "invalid-router"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)


def main():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(HostMakeTargetsTest)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print(f"\nHOST TESTS: {result.testsRun} run, {len(result.failures)} failures, {len(result.errors)} errors")
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()