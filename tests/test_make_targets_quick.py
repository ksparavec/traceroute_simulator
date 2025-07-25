#!/usr/bin/env -S python3 -B -u
"""
Quick test for make targets - minimal but comprehensive.

Tests essential functionality quickly to avoid CLI timeout.
"""

import os
import sys
import subprocess
import unittest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class QuickMakeTargetsTest(unittest.TestCase):
    """Quick essential tests for make targets."""
    
    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).parent.parent
        os.chdir(cls.project_root)
        
        if os.geteuid() != 0:
            raise unittest.SkipTest("Tests require root privileges")
        
        facts_dir = Path("/tmp/traceroute_test_output")
        if not facts_dir.exists() or not list(facts_dir.glob("*.json")):
            raise unittest.SkipTest("Test facts not available. Run 'make test' first.")
        
    def run_make(self, target: str, args: list = None, check: bool = True, 
                 timeout: int = 15) -> subprocess.CompletedProcess:
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
    
    def test_netshow_works(self):
        """Test netshow basic functionality."""
        result = self.run_make("netshow", ["hq-gw", "interfaces"], timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertIn("HQ-GW INTERFACE", result.stdout)
        
    def test_netshow_error_handling(self):
        """Test netshow handles errors correctly."""
        result = self.run_make("netshow", ["invalid-router", "interfaces"], check=False, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        
    def test_hostlist_empty(self):
        """Test hostlist when no hosts exist."""
        # Clean first
        self.run_make("netnsclean", ["-f"], check=False, timeout=10)
        
        result = self.run_make("hostlist", timeout=5)
        self.assertEqual(result.returncode, 0)
        

def main():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(QuickMakeTargetsTest)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print(f"QUICK TESTS: {result.testsRun} run, {len(result.failures)} failures, {len(result.errors)} errors")
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())