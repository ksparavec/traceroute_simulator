#!/usr/bin/env python3
"""
Basic functionality tests for make targets (Chunk 1).

Tests: netshow, netsetup, netclean basic operations
"""

import os
import sys
import subprocess
import time
import unittest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class BasicMakeTargetsTest(unittest.TestCase):
    """Basic tests for core make targets."""
    
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
        # Ensure complete cleanup including any temporary hosts
        # The updated netclean now handles all simulation namespaces
        self.run_make("hostclean", check=False, timeout=15)
        self.run_make("netclean", ["-f"], check=False, timeout=15)
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
    
    def test_netshow_router_interfaces(self):
        """Test showing router interfaces."""
        result = self.run_make("netshow", ["hq-gw", "interfaces"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("HQ-GW INTERFACE", result.stdout)
        self.assertIn("eth0", result.stdout)
        self.assertIn("eth1", result.stdout)
        
    def test_netshow_all_summary(self):
        """Test network summary."""
        result = self.run_make("netshow", ["all", "summary"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("NETWORK SUMMARY", result.stdout)
        self.assertIn("Total routers: 10", result.stdout)
        
    def test_netshow_errors(self):
        """Test netshow error handling."""
        # Invalid router
        result = self.run_make("netshow", ["invalid-router", "interfaces"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # No arguments
        result = self.run_make("netshow", [], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_netsetup_basic(self):
        """Test basic network setup."""
        result = self.run_make("netsetup", timeout=60)
        self.assertEqual(result.returncode, 0)
        
        # Check if namespaces were created
        ns_result = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True)
        self.assertIn("netsim", ns_result.stdout)
        self.assertIn("hq-gw", ns_result.stdout)
        
    def test_netclean_basic(self):
        """Test basic network cleanup."""
        # Setup first
        self.run_make("netsetup", timeout=60)
        
        # Verify setup worked
        ns_result = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True)
        self.assertIn("hq-gw", ns_result.stdout)
        
        # Then clean
        result = self.run_make("netclean", timeout=30)
        self.assertEqual(result.returncode, 0)
        
        # Verify cleanup - check that the main router namespaces are gone
        # (ignore any temporary public IP hosts that might still be around)
        ns_result = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True)
        namespaces = ns_result.stdout.split('\n')
        
        # Filter out any temporary public IP hosts (they start with 'pub')
        router_namespaces = [ns.strip() for ns in namespaces if ns.strip() and not ns.strip().startswith('pub')]
        
        # Main router namespaces should be gone
        self.assertNotIn("hq-gw", router_namespaces)
        self.assertNotIn("netsim", router_namespaces)


def main():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(BasicMakeTargetsTest)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print(f"\nBASIC TESTS: {result.testsRun} run, {len(result.failures)} failures, {len(result.errors)} errors")
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()