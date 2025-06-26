#!/usr/bin/env python3
"""
Integration tests for make targets (Chunk 5).

Tests complete workflows and realistic scenarios.
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


class IntegrationMakeTargetsTest(unittest.TestCase):
    """Integration tests for complete workflows."""
    
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
        self.run_make("netnsclean", ["-f"], check=False, timeout=20)
        time.sleep(0.5)
        
    def tearDown(self):
        self.run_make("netnsclean", ["-f"], check=False, timeout=20)
        
    def run_make(self, target: str, args: list = None, check: bool = True, 
                 timeout: int = 40) -> subprocess.CompletedProcess:
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
    
    def test_complete_workflow(self):
        """Test complete end-to-end workflow."""
        # 1. Setup network
        result = self.run_make("netsetup", ["-v"], timeout=60)
        self.assertEqual(result.returncode, 0, "Network setup failed")
        
        # Verify namespaces created
        ns_result = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True)
        self.assertIn("netsim", ns_result.stdout)
        self.assertIn("hq-gw", ns_result.stdout)
        
        # 2. Check static topology
        result = self.run_make("netshow", ["all", "summary"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("Total routers: 10", result.stdout)
        
        # 3. Check live status
        result = self.run_make("netstatus", ["hq-gw", "interfaces"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("eth1", result.stdout)
        
        # 4. Test basic connectivity
        result = self.run_make("nettest", ["-s", "10.1.1.1", "-d", "10.2.1.1"])
        self.assertEqual(result.returncode, 0, "Basic connectivity test failed")
        
        # 5. Add hosts
        result = self.run_make("hostadd", [
            "--host", "web", "--primary-ip", "10.1.1.100/24", "--connect-to", "hq-gw"
        ])
        self.assertEqual(result.returncode, 0, "Host addition failed")
        
        result = self.run_make("hostadd", [
            "--host", "db", "--primary-ip", "10.2.1.100/24", 
            "--secondary-ips", "192.168.100.1/24", "--connect-to", "br-gw"
        ])
        self.assertEqual(result.returncode, 0, "Host with secondary IP failed")
        
        # 6. Verify hosts
        result = self.run_make("hostlist")
        self.assertEqual(result.returncode, 0)
        self.assertIn("web", result.stdout)
        self.assertIn("db", result.stdout)
        self.assertEqual(self.get_host_count(), 2)
        
        # 7. Test external connectivity (with public IP handling)
        result = self.run_make("nettest", [
            "-s", "10.1.1.1", "-d", "8.8.8.8", "--test-type", "ping"
        ], timeout=45)
        self.assertEqual(result.returncode, 0, "External connectivity failed")
        
        # 8. Remove one host
        result = self.run_make("hostdel", ["--host", "web", "--remove"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.get_host_count(), 1)
        
        # 9. Clean all hosts
        result = self.run_make("hostclean")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.get_host_count(), 0)
        
        # 10. Final cleanup
        result = self.run_make("netnsclean", ["-v"], timeout=45)
        self.assertEqual(result.returncode, 0)
        
        # Verify complete cleanup
        ns_result = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True)
        self.assertNotIn("hq-gw", ns_result.stdout)
        self.assertNotIn("web", ns_result.stdout)
        
    def test_multiple_hosts_scenario(self):
        """Test scenario with multiple hosts across different routers."""
        # Setup
        self.run_make("netsetup", timeout=60)
        
        # Add hosts on different routers
        hosts = [
            ("web1", "10.1.1.100/24", "hq-gw"),
            ("web2", "10.1.1.101/24", "hq-gw"),
            ("db1", "10.2.1.100/24", "br-gw"),
            ("app1", "10.3.1.100/24", "dc-gw"),
        ]
        
        for host_name, ip, router in hosts:
            result = self.run_make("hostadd", [
                "--host", host_name, "--primary-ip", ip, "--connect-to", router
            ])
            self.assertEqual(result.returncode, 0, f"Failed to add {host_name}")
            
        # Verify all hosts
        self.assertEqual(self.get_host_count(), 4)
        
        # Test connectivity between different locations
        result = self.run_make("nettest", ["-s", "10.1.1.1", "-d", "10.3.1.1"])
        self.assertEqual(result.returncode, 0)
        
        # Clean all hosts at once
        result = self.run_make("hostclean")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.get_host_count(), 0)
        
    def test_verbosity_levels(self):
        """Test different verbosity levels work correctly."""
        # Test setup with different verbosity
        result = self.run_make("netsetup", ["-v"], timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertIn("INFO:", result.stdout)
        
        # Clean and test debug verbosity
        self.run_make("netclean", ["-f"], check=False)
        result = self.run_make("netsetup", ["-vv"], timeout=60)
        self.assertEqual(result.returncode, 0)
        
        # Test host operations with verbosity
        result = self.run_make("hostadd", [
            "--host", "verbose-test", "--primary-ip", "10.1.1.100/24", 
            "--connect-to", "hq-gw", "-v"
        ])
        self.assertEqual(result.returncode, 0)
        self.assertIn("INFO:", result.stdout)


def main():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(IntegrationMakeTargetsTest)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print(f"\nINTEGRATION TESTS: {result.testsRun} run, {len(result.failures)} failures, {len(result.errors)} errors")
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()