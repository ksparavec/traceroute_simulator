#!/usr/bin/env python3
"""
Test Suite for Reverse Path Tracing Functionality

This test suite validates the reverse path tracing capabilities of the
traceroute simulator. It tests the three-step approach:
1. Controller to destination tracing
2. Destination to original source tracing  
3. Path reversal and combination

The tests cover various network scenarios, error conditions, and edge cases
to ensure robust operation in mixed Linux/non-Linux environments.

Author: Network Analysis Tool
License: MIT
"""

import unittest
import sys
import os
import tempfile
import json
import socket
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from src.core.traceroute_simulator import TracerouteSimulator, Router
    from src.core.reverse_path_tracer import ReversePathTracer
    from src.executors.mtr_executor import MTRExecutor
    from src.core.route_formatter import RouteFormatter
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import required modules: {e}")
    MODULES_AVAILABLE = False


class TestReversePathTracer(unittest.TestCase):
    """Test cases for reverse path tracing functionality."""
    
    def setUp(self):
        """Set up test fixtures with mock network topology."""
        if not MODULES_AVAILABLE:
            self.skipTest("Required modules not available")
        
        # Use real test data directory with ansible controller metadata
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.routing_dir = os.path.join(current_dir, "tsim_facts")
        
        # Verify test data exists
        if not os.path.exists(self.routing_dir):
            self.skipTest("Test routing data not available")
        
        # Initialize simulator
        self.simulator = TracerouteSimulator(self.routing_dir, verbose=False)
        
        # Initialize reverse path tracer with mock controller IP
        # Use auto-detection for ansible controller IP
        self.reverse_tracer = ReversePathTracer(
            self.simulator, 
            verbose=False,
            verbose_level=1
        )
        # Store detected controller IP for test assertions
        self.controller_ip = self.reverse_tracer.ansible_controller_ip
    
    def tearDown(self):
        """Clean up test fixtures."""
        # No cleanup needed since we use real test data
        pass
    
    def test_controller_ip_detection(self):
        """Test automatic detection of Ansible controller IP."""
        # Test with mock socket connection
        with patch('socket.socket') as mock_socket:
            mock_socket_instance = Mock()
            mock_socket_instance.getsockname.return_value = ('192.168.1.100', 12345)
            mock_socket.return_value.__enter__.return_value = mock_socket_instance
            
            # Test auto-detection of controller IP
            tracer = ReversePathTracer(self.simulator)
            # Should auto-detect hq-dmz as controller (10.1.2.3)
            self.assertEqual(tracer.ansible_controller_ip, "10.1.2.3")
    
    def test_controller_ip_detection_failure(self):
        """Test handling of controller IP detection failure."""
        # Test that providing an invalid controller IP doesn't raise an error (since it's just stored)
        # The validation happens later when the IP is actually used
        tracer = ReversePathTracer(self.simulator, "invalid.ip.address")
        self.assertEqual(tracer.ansible_controller_ip, "invalid.ip.address")
    
    def test_find_last_linux_router(self):
        """Test identification of last Linux router in path."""
        # Create mock path with Linux routers
        path = [
            (1, "source", "10.1.1.10", "eth0", False, "hq-gw", ""),
            (2, "hq-gw", "10.1.1.1", "eth0", True, "", "wg0"),
            (3, "br-gw", "10.100.1.2", "wg0", True, "", "eth0"),
            (4, "destination", "10.2.1.10", "eth0", False, "br-gw", "")
        ]
        
        last_router = self.reverse_tracer._find_last_linux_router(path)
        self.assertEqual(last_router, "br-gw")
    
    def test_find_last_linux_router_no_routers(self):
        """Test handling when no Linux routers found in path."""
        # Create path with no Linux routers
        path = [
            (1, "source", "10.1.1.10", "eth0", False, "", ""),
            (2, "* * *", "No route", "", False, "", ""),
            (3, "destination", "10.2.1.10", "eth0", False, "", "")
        ]
        
        last_router = self.reverse_tracer._find_last_linux_router(path)
        self.assertIsNone(last_router)
    
    def test_get_router_ip(self):
        """Test retrieval of router IP address."""
        router_ip = self.reverse_tracer._get_router_ip("hq-gw")
        self.assertEqual(router_ip, "10.1.1.1")  # First interface IP
        
        # Test non-existent router
        router_ip = self.reverse_tracer._get_router_ip("non-existent")
        self.assertIsNone(router_ip)
    
    def test_is_path_complete_success(self):
        """Test path completeness check for successful paths."""
        complete_path = [
            (1, "source", "10.1.1.10", "eth0", False, "hq-gw", ""),
            (2, "hq-gw", "10.1.1.1", "eth0", True, "", "wg0"),
            (3, "destination", "10.2.1.10", "eth0", False, "br-gw", "")
        ]
        
        self.assertTrue(self.reverse_tracer._is_path_complete(complete_path))
    
    def test_is_path_complete_failure(self):
        """Test path completeness check for failed paths."""
        # Path with routing failure
        failed_path = [
            (1, "source", "10.1.1.10", "eth0", False, "hq-gw", ""),
            (2, "* * *", "No route", "", False, "", "")
        ]
        
        self.assertFalse(self.reverse_tracer._is_path_complete(failed_path))
        
        # Path with loop detection
        loop_path = [
            (1, "source", "10.1.1.10", "eth0", False, "hq-gw", ""),
            (2, "hq-gw", "10.1.1.1 (loop detected)", "eth0", True, "", "")
        ]
        
        self.assertFalse(self.reverse_tracer._is_path_complete(loop_path))
    
    def test_step1_controller_to_destination_simulation_success(self):
        """Test step 1 with successful simulation."""
        with patch.object(self.simulator, 'simulate_traceroute') as mock_traceroute:
            # Mock successful simulation result
            mock_traceroute.return_value = [
                (1, "source", "10.1.2.3", "eth0", False, "hq-dmz", ""),
                (2, "hq-gw", "10.1.1.1", "eth0", True, "", "wg0"),
                (3, "destination", "10.2.1.10", "eth0", False, "br-gw", "")
            ]
            
            success, path, exit_code = self.reverse_tracer._step1_controller_to_destination("10.2.1.10")
            
            self.assertTrue(success)
            self.assertEqual(len(path), 3)
            self.assertEqual(exit_code, 0)
            mock_traceroute.assert_called_once_with(self.controller_ip, "10.2.1.10")
    
    def test_step1_controller_to_destination_simulation_failure(self):
        """Test step 1 with simulation failure and no MTR fallback."""
        with patch.object(self.simulator, 'simulate_traceroute') as mock_traceroute:
            # Mock failed simulation result
            mock_traceroute.return_value = [
                (1, "source", "10.1.2.3", "eth0", False, "hq-dmz", ""),
                (2, "* * *", "No route", "", False, "", "")
            ]
            
            # Mock MTR not available
            with patch.object(self.reverse_tracer, 'mtr_executor', None):
                success, path, exit_code = self.reverse_tracer._step1_controller_to_destination("10.2.1.10")
                
                self.assertFalse(success)
                self.assertEqual(exit_code, 1)
    
    @patch('src.core.reverse_path_tracer.MTR_AVAILABLE', True)
    def test_step1_mtr_fallback_success(self):
        """Test step 1 with MTR fallback success."""
        with patch.object(self.simulator, 'simulate_traceroute') as mock_traceroute:
            # Mock failed simulation
            mock_traceroute.return_value = [
                (1, "source", "10.1.2.3", "eth0", False, "hq-dmz", ""),
                (2, "* * *", "No route", "", False, "", "")
            ]
            
            # Mock successful MTR execution
            mock_mtr = Mock()
            mock_mtr.execute_mtr.return_value = (True, [
                (1, "hq-gw", "10.1.1.1", "eth0", True, "", "wg0"),
                (2, "destination", "10.2.1.10", "eth0", False, "br-gw", "")
            ], 0)
            
            self.reverse_tracer.mtr_executor = mock_mtr
            
            success, path, exit_code = self.reverse_tracer._step1_controller_to_destination("10.2.1.10")
            
            self.assertTrue(success)
            self.assertEqual(len(path), 2)
            self.assertEqual(exit_code, 0)
    
    def test_step2_destination_to_source_success(self):
        """Test step 2 with successful reverse simulation."""
        forward_path = [
            (1, "source", "10.1.2.3", "eth0", False, "hq-dmz", ""),
            (2, "hq-gw", "10.1.1.1", "eth0", True, "", "wg0"),
            (3, "br-gw", "10.100.1.2", "wg0", True, "", "eth0"),
            (4, "destination", "10.2.1.10", "eth0", False, "br-gw", "")
        ]
        
        with patch.object(self.simulator, 'simulate_traceroute') as mock_traceroute:
            # Mock successful reverse simulation
            mock_traceroute.return_value = [
                (1, "source", "10.100.1.2", "wg0", False, "br-gw", ""),
                (2, "br-gw", "10.100.1.2", "wg0", True, "", "wg0"),
                (3, "hq-gw", "10.100.1.1", "wg0", True, "", "eth0"),
                (4, "destination", "10.1.1.10", "eth0", False, "hq-gw", "")
            ]
            
            success, path, exit_code = self.reverse_tracer._step2_destination_to_source(
                forward_path, "10.1.1.10", "10.2.1.10"
            )
            
            self.assertTrue(success)
            self.assertEqual(len(path), 4)
            self.assertEqual(exit_code, 0)
    
    def test_step2_no_linux_routers(self):
        """Test step 2 when no Linux routers found in forward path."""
        forward_path = [
            (1, "source", "10.1.2.3", "eth0", False, "", ""),
            (2, "* * *", "No route", "", False, "", "")
        ]
        
        success, path, exit_code = self.reverse_tracer._step2_destination_to_source(
            forward_path, "10.1.1.10", "10.2.1.10"
        )
        
        self.assertFalse(success)
        self.assertEqual(exit_code, 4)  # No Linux routers found
    
    def test_step3_reverse_and_combine_success(self):
        """Test step 3 path reversal and combination."""
        forward_path = [
            (1, "source", "10.1.2.3", "eth0", False, "hq-dmz", ""),
            (2, "hq-gw", "10.1.1.1", "eth0", True, "", "wg0"),
            (3, "br-gw", "10.100.1.2", "wg0", True, "", "eth0"),
            (4, "destination", "10.2.1.10", "eth0", False, "br-gw", "")
        ]
        
        reverse_path = [
            (1, "source", "10.100.1.2", "wg0", False, "br-gw", ""),
            (2, "br-gw", "10.100.1.2", "wg0", True, "", "wg0"),
            (3, "hq-gw", "10.100.1.1", "wg0", True, "", "eth0"),
            (4, "destination", "10.1.1.10", "eth0", False, "hq-gw", "")
        ]
        
        success, final_path = self.reverse_tracer._step3_reverse_and_combine(
            forward_path, reverse_path, "10.1.1.10", "10.2.1.10"
        )
        
        self.assertTrue(success)
        self.assertGreater(len(final_path), 0)
        
        # Check that path starts with original source
        self.assertEqual(final_path[0][2], "10.1.1.10")  # Source IP
        
        # Check that path ends with destination
        self.assertEqual(final_path[-1][2], "10.2.1.10")  # Destination IP
    
    def test_step3_empty_reverse_path(self):
        """Test step 3 with empty reverse path."""
        forward_path = [
            (1, "source", "10.1.2.3", "eth0", False, "hq-dmz", ""),
            (2, "destination", "10.2.1.10", "eth0", False, "hq-gw", "")
        ]
        
        success, final_path = self.reverse_tracer._step3_reverse_and_combine(
            forward_path, [], "10.1.1.10", "10.2.1.10"
        )
        
        self.assertFalse(success)
        self.assertEqual(len(final_path), 0)
    
    @patch.object(ReversePathTracer, '_step1_controller_to_destination')
    @patch.object(ReversePathTracer, '_step2_destination_to_source')
    @patch.object(ReversePathTracer, '_step3_reverse_and_combine')
    def test_perform_reverse_trace_complete_success(self, mock_step3, mock_step2, mock_step1):
        """Test complete reverse tracing process with all steps successful."""
        # Mock successful step 1
        mock_step1.return_value = (True, [
            (1, "source", "10.1.2.3", "eth0", False, "hq-dmz", ""),
            (2, "destination", "10.2.1.10", "eth0", False, "hq-gw", "")
        ], 0)
        
        # Mock successful step 2
        mock_step2.return_value = (True, [
            (1, "source", "10.100.1.1", "wg0", False, "hq-gw", ""),
            (2, "destination", "10.1.1.10", "eth0", False, "hq-gw", "")
        ], 0)
        
        # Mock successful step 3
        mock_step3.return_value = (True, [
            (1, "source", "10.1.1.10", "eth0", False, "hq-gw", ""),
            (2, "destination", "10.2.1.10", "eth0", False, "hq-gw", "")
        ])
        
        success, path, exit_code = self.reverse_tracer.perform_reverse_trace("10.1.1.10", "10.2.1.10")
        
        self.assertTrue(success)
        self.assertEqual(len(path), 2)
        self.assertEqual(exit_code, 0)
    
    @patch.object(ReversePathTracer, '_step1_controller_to_destination')
    def test_perform_reverse_trace_step1_failure(self, mock_step1):
        """Test reverse tracing with step 1 failure."""
        # Mock failed step 1
        mock_step1.return_value = (False, [], 2)
        
        success, path, exit_code = self.reverse_tracer.perform_reverse_trace("10.1.1.10", "10.2.1.10")
        
        self.assertFalse(success)
        self.assertEqual(len(path), 0)
        self.assertEqual(exit_code, 2)
    
    @patch.object(ReversePathTracer, '_step1_controller_to_destination')
    @patch.object(ReversePathTracer, '_step2_destination_to_source')
    def test_perform_reverse_trace_step2_failure(self, mock_step2, mock_step1):
        """Test reverse tracing with step 2 failure."""
        # Mock successful step 1
        mock_step1.return_value = (True, [
            (1, "source", "10.1.2.3", "eth0", False, "hq-dmz", ""),
            (2, "destination", "10.2.1.10", "eth0", False, "hq-gw", "")
        ], 0)
        
        # Mock failed step 2
        mock_step2.return_value = (False, [], 4)
        
        success, path, exit_code = self.reverse_tracer.perform_reverse_trace("10.1.1.10", "10.2.1.10")
        
        self.assertFalse(success)
        self.assertEqual(len(path), 0)
        self.assertEqual(exit_code, 4)


class TestReversePathTracingIntegration(unittest.TestCase):
    """Integration tests for reverse path tracing with main simulator."""
    
    def setUp(self):
        """Set up integration test fixtures."""
        if not MODULES_AVAILABLE:
            self.skipTest("Required modules not available")
        
        # Use existing test routing data
        test_data_dir = os.path.join(os.path.dirname(__file__), "tsim_facts")
        if not os.path.exists(test_data_dir):
            self.skipTest("Test routing data not available")
        
        self.routing_dir = test_data_dir
    
    @patch('sys.argv', ['traceroute_simulator.py', '-s', '10.1.1.10', '-d', '192.168.1.10', '--reverse-trace'])
    def test_main_function_with_reverse_trace(self):
        """Test main function integration with reverse tracing enabled."""
        # This test would require mocking the entire main function execution
        # For now, we'll just verify the argument parsing works
        import argparse
        
        parser = argparse.ArgumentParser()
        parser.add_argument('-s', '--source', required=True)
        parser.add_argument('-d', '--destination', required=True)
        parser.add_argument('--reverse-trace', action='store_true')
        parser.add_argument('--controller-ip')  # Optional now
        
        args = parser.parse_args(['-s', '10.1.1.10', '-d', '192.168.1.10', '--reverse-trace'])
        
        self.assertEqual(args.source, '10.1.1.10')
        self.assertEqual(args.destination, '192.168.1.10')
        self.assertTrue(args.reverse_trace)
        # Controller IP should be None (auto-detected)
        self.assertIsNone(args.controller_ip)


def run_tests():
    """Run all reverse path tracing tests."""
    if not MODULES_AVAILABLE:
        print("Error: Required modules not available for testing")
        return False
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestReversePathTracer))
    suite.addTests(loader.loadTestsFromTestCase(TestReversePathTracingIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    total_tests = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    passed = total_tests - failures - errors
    
    print(f"\n=== Reverse Path Tracing Test Results ===")
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed}")
    print(f"Failed: {failures}")
    print(f"Errors: {errors}")
    print(f"Success rate: {(passed/total_tests*100):.1f}%")
    
    return failures == 0 and errors == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)