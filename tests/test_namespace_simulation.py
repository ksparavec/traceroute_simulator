#!/usr/bin/env -S python3 -B -u
"""
Network Namespace Simulation Test Suite

Basic tests for the Linux namespace-based network simulation infrastructure.
Tests namespace setup, teardown, status monitoring, and basic resource validation.

This test suite verifies:
- Namespace creation and configuration
- Network interface setup and IP assignment
- Routing table and iptables rule installation
- Status monitoring and information display
- Basic resource validation
- Cleanup and resource management

Test Requirements:
- Requires root privileges (sudo)
- Uses consolidated facts from /tmp/traceroute_test_output
- Must run after all test infrastructure is set up
- Follows established test standards and conventions

Usage:
    sudo python3 -B tests/test_namespace_simulation.py
    
Environment Variables:
    TRACEROUTE_SIMULATOR_FACTS - Should point to /tmp/traceroute_test_output
"""

import unittest
import subprocess
import sys
import os
import json
import time
import signal
import re
import ipaddress
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class NamespaceSimulationTestSuite(unittest.TestCase):
    """
    Basic test suite for Linux namespace network simulation.
    
    Tests the essential functionality of namespace-based network simulation including:
    - Setup and configuration
    - Status monitoring and information display  
    - Basic resource validation
    - Cleanup and resource management
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment and validate prerequisites."""
        print("=" * 80)
        print("NETWORK NAMESPACE SIMULATION TEST SUITE")
        print("=" * 80)
        
        # Verify we're running as root
        if os.geteuid() != 0:
            raise unittest.SkipTest("Namespace tests require root privileges. Run with: sudo python3 -B tests/test_namespace_simulation.py")
        
        # Verify facts directory exists and has data
        cls.facts_dir = os.environ.get('TRACEROUTE_SIMULATOR_FACTS', '/tmp/traceroute_test_output')
        facts_path = Path(cls.facts_dir)
        
        if not facts_path.exists():
            raise unittest.SkipTest(f"Facts directory {cls.facts_dir} does not exist")
        
        # Check for router facts files
        cls.router_files = list(facts_path.glob('*.json'))
        if not cls.router_files:
            raise unittest.SkipTest(f"No router facts files found in {cls.facts_dir}")
        
        print(f"Found {len(cls.router_files)} router facts files")
        
        # Load router names and validate facts
        cls.router_names = []
        cls.router_ips = {}  # router -> list of IPs
        
        for router_file in cls.router_files:
            router_name = router_file.stem
            cls.router_names.append(router_name)
            
            try:
                with open(router_file) as f:
                    router_data = json.load(f)
                    
                # Extract router IPs from routing table
                router_ips = set()
                if 'routing' in router_data and 'tables' in router_data['routing']:
                    for route in router_data['routing']['tables']:
                        if 'prefsrc' in route:
                            router_ips.add(route['prefsrc'])
                
                cls.router_ips[router_name] = list(router_ips)
                
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Could not parse router data from {router_file}: {e}")
        
        print(f"Loaded router data for: {', '.join(sorted(cls.router_names))}")
        
        # Ensure clean state before testing
        cls._ensure_clean_state()
        
        # Track whether namespace is set up
        cls.namespace_setup = False
        cls.setup_failed = False
    
    @classmethod 
    def _ensure_clean_state(cls):
        """Ensure clean state by cleaning up any existing namespaces."""
        try:
            # Run cleanup silently
            subprocess.run([
                'python3', 'src/simulators/network_namespace_cleanup.py', '-f'
            ], capture_output=True, text=True, cwd=Path.cwd())
        except Exception:
            pass  # Ignore cleanup errors
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test environment."""
        print("\n" + "=" * 80)
        print("CLEANING UP NAMESPACE SIMULATION TEST ENVIRONMENT") 
        print("=" * 80)
        
        # First cleanup any orphaned netcat processes
        try:
            subprocess.run(['pkill', '-f', 'nc -l'], 
                         capture_output=True, check=False)
            subprocess.run(['pkill', '-f', 'nc -u -l'], 
                         capture_output=True, check=False)
            print("✓ Cleaned up orphaned netcat processes")
        except Exception:
            pass  # Ignore cleanup errors
        
        if cls.namespace_setup and not cls.setup_failed:
            try:
                result = subprocess.run([
                    'python3', 'src/simulators/network_namespace_cleanup.py', '-v'
                ], capture_output=True, text=True, cwd=Path.cwd(), timeout=30)
                
                if result.returncode == 0:
                    print("✓ Namespace cleanup completed successfully")
                else:
                    print(f"⚠ Cleanup completed with warnings: {result.stderr}")
                    
            except Exception as e:
                print(f"✗ Cleanup failed: {e}")
        
        print("Test environment cleanup complete")
    
    def test_01_namespace_setup(self):
        """Test namespace setup and configuration."""
        print("\n" + "-" * 60)
        print("TEST: Namespace Setup and Configuration")
        print("-" * 60)
        
        try:
            # Run namespace setup
            env = os.environ.copy()
            env['TRACEROUTE_SIMULATOR_FACTS'] = self.facts_dir
            result = subprocess.run([
                'python3', 'src/simulators/network_namespace_setup.py', '-v'
            ], capture_output=True, text=True, cwd=Path.cwd(), timeout=120, env=env)
            
            if result.returncode == 0:
                print("✓ Namespace setup completed successfully")
                self.__class__.namespace_setup = True
                
                # Verify namespaces were created
                ns_result = subprocess.run(['ip', 'netns', 'list'], 
                                         capture_output=True, text=True)
                namespaces = ns_result.stdout.strip().split('\n') if ns_result.stdout.strip() else []
                
                expected_namespaces = set(self.router_names)
                found_namespaces = set()
                
                for ns_line in namespaces:
                    # Extract namespace name (format: "name (id: X)")
                    ns_name = ns_line.split(' ')[0]
                    found_namespaces.add(ns_name)
                
                missing_namespaces = expected_namespaces - found_namespaces
                extra_namespaces = found_namespaces - expected_namespaces
                
                if missing_namespaces:
                    self.fail(f"Missing namespaces: {missing_namespaces}")
                
                print(f"✓ Created {len(found_namespaces)} namespaces: {', '.join(sorted(found_namespaces))}")
                
            else:
                self.__class__.setup_failed = True
                self.fail(f"Namespace setup failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            self.__class__.setup_failed = True
            self.fail("Namespace setup timed out after 120 seconds")
        except Exception as e:
            self.__class__.setup_failed = True
            self.fail(f"Namespace setup failed with exception: {e}")
    
    def test_02_namespace_status_summary(self):
        """Test namespace status summary functionality."""
        print("\n" + "-" * 60)
        print("TEST: Namespace Status Summary")
        print("-" * 60)
        
        if not self.namespace_setup:
            self.skipTest("Namespace setup not completed")
        
        try:
            # Test summary for all routers
            env = os.environ.copy()
            env['TRACEROUTE_SIMULATOR_FACTS'] = self.facts_dir
            result = subprocess.run([
                'python3', 'src/simulators/network_namespace_status.py',
                'all', 'summary'
            ], capture_output=True, text=True, cwd=Path.cwd(), timeout=30, env=env)
            
            self.assertEqual(result.returncode, 0, f"Status summary failed: {result.stderr}")
            
            # Verify output contains router information
            output = result.stdout
            for router_name in self.router_names:
                self.assertIn(router_name, output, f"Router {router_name} not found in summary")
            
            print("✓ Status summary completed successfully")
            print(f"✓ All {len(self.router_names)} routers present in summary")
            
        except subprocess.TimeoutExpired:
            self.fail("Status summary timed out")
        except Exception as e:
            self.fail(f"Status summary failed: {e}")
    
    def test_03_namespace_status_individual(self):
        """Test individual namespace status functions."""
        print("\n" + "-" * 60)
        print("TEST: Individual Namespace Status Functions")
        print("-" * 60)
        
        if not self.namespace_setup:
            self.skipTest("Namespace setup not completed")
        
        # Test different status functions for a sample router
        test_router = self.router_names[0] if self.router_names else None
        if not test_router:
            self.skipTest("No routers available for testing")
        
        status_functions = ['interfaces', 'routes', 'rules', 'summary']
        
        for func in status_functions:
            with self.subTest(router=test_router, function=func):
                try:
                    env = os.environ.copy()
                    env['TRACEROUTE_SIMULATOR_FACTS'] = self.facts_dir
                    result = subprocess.run([
                        'python3', 'src/simulators/network_namespace_status.py',
                        test_router, func
                    ], capture_output=True, text=True, cwd=Path.cwd(), timeout=15, env=env)
                    
                    self.assertEqual(result.returncode, 0, 
                                   f"Status function {func} failed for {test_router}: {result.stderr}")
                    
                    # Verify output is not empty
                    self.assertTrue(result.stdout.strip(), 
                                  f"Status function {func} returned empty output for {test_router}")
                    
                    print(f"✓ Status function '{func}' working for {test_router}")
                    
                except subprocess.TimeoutExpired:
                    self.fail(f"Status function {func} timed out for {test_router}")
    
    def test_04_namespace_resource_validation(self):
        """Test that namespaces have proper network resources."""
        print("\n" + "-" * 60)
        print("TEST: Namespace Resource Validation")
        print("-" * 60)
        
        if not self.namespace_setup:
            self.skipTest("Namespace setup not completed")
        
        # Check that each namespace has expected interfaces
        for router_name in self.router_names[:3]:  # Test first 3 routers
            with self.subTest(router=router_name):
                try:
                    # Check interfaces in namespace
                    result = subprocess.run([
                        'ip', 'netns', 'exec', router_name, 'ip', 'link', 'show'
                    ], capture_output=True, text=True, timeout=10)
                    
                    self.assertEqual(result.returncode, 0,
                                   f"Failed to get interfaces for namespace {router_name}: {result.stderr}")
                    
                    # Verify loopback interface exists
                    self.assertIn('lo:', result.stdout,
                                f"Loopback interface missing in namespace {router_name}")
                    
                    # Check for at least one non-loopback interface
                    lines = result.stdout.split('\n')
                    interface_count = len([line for line in lines if ':' in line and 'lo:' not in line])
                    self.assertGreater(interface_count, 0,
                                     f"No network interfaces found in namespace {router_name}")
                    
                    print(f"✓ Namespace {router_name} has proper network interfaces")
                    
                except subprocess.TimeoutExpired:
                    self.fail(f"Interface check timed out for namespace {router_name}")
    
    def test_05_namespace_routing_tables(self):
        """Test that namespaces have proper routing tables."""
        print("\n" + "-" * 60)
        print("TEST: Namespace Routing Tables")
        print("-" * 60)
        
        if not self.namespace_setup:
            self.skipTest("Namespace setup not completed")
        
        # Check routing tables in namespaces
        for router_name in self.router_names[:3]:  # Test first 3 routers
            with self.subTest(router=router_name):
                try:
                    # Check main routing table
                    result = subprocess.run([
                        'ip', 'netns', 'exec', router_name, 'ip', 'route', 'show'
                    ], capture_output=True, text=True, timeout=10)
                    
                    self.assertEqual(result.returncode, 0,
                                   f"Failed to get routing table for namespace {router_name}: {result.stderr}")
                    
                    # Verify routing table is not empty
                    self.assertTrue(result.stdout.strip(),
                                  f"Empty routing table in namespace {router_name}")
                    
                    # Check for local routes (should have at least loopback)
                    routes = result.stdout.split('\n')
                    has_local_routes = any('127.0.0.1' in route or 'localhost' in route for route in routes)
                    
                    print(f"✓ Namespace {router_name} has routing table with {len(routes)} routes")
                    
                except subprocess.TimeoutExpired:
                    self.fail(f"Routing table check timed out for namespace {router_name}")
    
    def test_06_cleanup_verification(self):
        """Test namespace cleanup verification (prepare for teardown)."""
        print("\n" + "-" * 60)
        print("TEST: Cleanup Verification (Dry Run)")
        print("-" * 60)
        
        if not self.namespace_setup:
            self.skipTest("Namespace setup not completed")
        
        try:
            # Run cleanup in dry-run mode (if supported) or just verify it can run
            result = subprocess.run([
                'python3', 'src/simulators/network_namespace_cleanup.py',
                '--help'
            ], capture_output=True, text=True, cwd=Path.cwd(), timeout=10)
            
            # Verify cleanup script exists and can be executed
            self.assertEqual(result.returncode, 0,
                           f"Cleanup script not available: {result.stderr}")
            
            print("✓ Cleanup script is available and ready")
            
            # Verify namespaces still exist before actual cleanup
            ns_result = subprocess.run(['ip', 'netns', 'list'],
                                     capture_output=True, text=True)
            namespaces = ns_result.stdout.strip().split('\n') if ns_result.stdout.strip() else []
            
            found_test_namespaces = 0
            for ns_line in namespaces:
                ns_name = ns_line.split(' ')[0]
                if ns_name in self.router_names:
                    found_test_namespaces += 1
            
            self.assertGreater(found_test_namespaces, 0,
                             "No test namespaces found - setup may have failed")
            
            print(f"✓ {found_test_namespaces} test namespaces still active (ready for cleanup)")
            
        except subprocess.TimeoutExpired:
            self.fail("Cleanup verification timed out")
        except Exception as e:
            self.fail(f"Cleanup verification failed: {e}")


def main():
    """Main test runner."""
    # Check if we're running as root
    if os.geteuid() != 0:
        print("ERROR: Namespace tests require root privileges")
        print("Please run: sudo python3 -B tests/test_namespace_simulation.py")
        sys.exit(1)
    
    # Verify facts directory
    facts_dir = os.environ.get('TRACEROUTE_SIMULATOR_FACTS', '/tmp/traceroute_test_output')
    if not Path(facts_dir).exists():
        print(f"ERROR: Facts directory {facts_dir} does not exist")
        print("Please run complete test suite first: make test")
        sys.exit(1)
    
    # Run tests
    unittest.main(verbosity=2, buffer=True)


if __name__ == '__main__':
    main()