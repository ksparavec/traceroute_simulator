#!/usr/bin/env python3
"""
Error handling and edge case tests for make targets (Chunk 4).

Tests error conditions, invalid inputs, and exception handling.
"""

import os
import sys
import subprocess
import time
import unittest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class ErrorMakeTargetsTest(unittest.TestCase):
    """Error handling and edge case tests."""
    
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
        # Ensure clean state
        self.run_make("netnsclean", ["-f"], check=False, timeout=15)
        time.sleep(0.3)
        
    def tearDown(self):
        self.run_make("netnsclean", ["-f"], check=False, timeout=15)
        
    def run_make(self, target: str, args: list = None, check: bool = True, 
                 timeout: int = 20) -> subprocess.CompletedProcess:
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
    
    def test_operations_without_setup(self):
        """Test operations when network not set up."""
        # nettest should fail without network setup
        result = self.run_make("nettest", ["-s", "10.1.1.1", "-d", "10.2.1.1"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # netstatus should fail without namespaces
        result = self.run_make("netstatus", ["hq-gw", "interfaces"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # hostadd should fail without network setup
        result = self.run_make("hostadd", [
            "--host", "test", "--primary-ip", "10.1.1.100/24"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_invalid_arguments(self):
        """Test invalid argument handling."""
        # Setup network for some tests
        self.run_make("netsetup", timeout=30)
        
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
        
        # Invalid netstatus arguments
        result = self.run_make("netstatus", ["invalid-ns", "interfaces"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_duplicate_operations(self):
        """Test duplicate and conflicting operations."""
        self.run_make("netsetup", timeout=30)
        
        # Add host
        self.run_make("hostadd", [
            "--host", "test", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        
        # Try to add same host again (should fail)
        result = self.run_make("hostadd", [
            "--host", "test", "--primary-ip", "10.1.1.101/24", "--connect-to", "hq-gw"
        ], check=False)
        self.assertNotEqual(result.returncode, 0)
        
    def test_cleanup_robustness(self):
        """Test cleanup in various states."""
        # Clean when nothing exists (should succeed gracefully)
        result = self.run_make("netclean", check=False)
        # Either succeeds or fails gracefully - both acceptable
        self.assertIn(result.returncode, [0, 1])
        
        # Clean hosts when none exist (should succeed)
        result = self.run_make("hostclean")
        self.assertEqual(result.returncode, 0)
        
        # Force cleanup (should always work)
        result = self.run_make("netnsclean", ["-f"])
        self.assertEqual(result.returncode, 0)
        
    def test_edge_case_ips(self):
        """Test edge cases with IP addresses."""
        self.run_make("netsetup", timeout=30)
        
        # Try various invalid IP formats
        invalid_ips = [
            "999.999.999.999/24",
            "10.1.1.1/99",
            "not-an-ip/24",
            "10.1.1.1",  # missing prefix
            ""  # empty
        ]
        
        for invalid_ip in invalid_ips:
            result = self.run_make("hostadd", [
                "--host", f"test-{invalid_ip.replace('/', '-').replace('.', '-')}", 
                "--primary-ip", invalid_ip
            ], check=False)
            self.assertNotEqual(result.returncode, 0, f"Should reject invalid IP: {invalid_ip}")
            
    def test_missing_arguments(self):
        """Test missing required arguments."""
        # netshow without arguments
        result = self.run_make("netshow", [], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # hostadd without required args
        result = self.run_make("hostadd", ["--host", "test"], check=False)
        self.assertNotEqual(result.returncode, 0)
        
        # hostdel without --remove
        result = self.run_make("hostdel", ["--host", "test"], check=False)
        self.assertNotEqual(result.returncode, 0)


def main():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(ErrorMakeTargetsTest)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print(f"\nERROR TESTS: {result.testsRun} run, {len(result.failures)} failures, {len(result.errors)} errors")
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()