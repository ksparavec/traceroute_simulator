#!/usr/bin/env -S python3 -B -u
"""
Test Suite for Service Manager

This module tests the service management functionality including:
- Service lifecycle (start/stop/restart)
- TCP and UDP echo services
- Error conditions and handling
- Multi-client support
- Integration with namespace infrastructure
"""

import unittest
import subprocess
import time
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.simulators.service_manager import (
    ServiceManager, ServiceClient, ServiceConfig, ServiceProtocol,
    ServiceStatus, ServiceStartError, ServiceConnectionError,
    ServiceResponseError
)
from src.core.exceptions import ErrorCode


class TestServiceManager(unittest.TestCase):
    """Test service manager functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test namespace environment."""
        # Check if running as root
        if os.geteuid() != 0:
            raise unittest.SkipTest("Service tests require root privileges")
        
        # Create test namespaces
        cls.test_ns1 = "test-svc-ns1"
        cls.test_ns2 = "test-svc-ns2"
        
        for ns in [cls.test_ns1, cls.test_ns2]:
            subprocess.run(["ip", "netns", "delete", ns], 
                          capture_output=True)
            subprocess.run(["ip", "netns", "add", ns], check=True)
            
            # Create loopback
            subprocess.run(["ip", "netns", "exec", ns, "ip", "link", "set", "lo", "up"], 
                          check=True)
        
        # Create veth pair to connect namespaces
        subprocess.run([
            "ip", "link", "add", "veth1", "type", "veth", "peer", "name", "veth2"
        ], check=True)
        
        # Move interfaces to namespaces
        subprocess.run(["ip", "link", "set", "veth1", "netns", cls.test_ns1], check=True)
        subprocess.run(["ip", "link", "set", "veth2", "netns", cls.test_ns2], check=True)
        
        # Configure interfaces
        subprocess.run([
            "ip", "netns", "exec", cls.test_ns1,
            "ip", "addr", "add", "10.99.1.1/24", "dev", "veth1"
        ], check=True)
        subprocess.run([
            "ip", "netns", "exec", cls.test_ns1,
            "ip", "link", "set", "veth1", "up"
        ], check=True)
        
        subprocess.run([
            "ip", "netns", "exec", cls.test_ns2,
            "ip", "addr", "add", "10.99.1.2/24", "dev", "veth2"
        ], check=True)
        subprocess.run([
            "ip", "netns", "exec", cls.test_ns2,
            "ip", "link", "set", "veth2", "up"
        ], check=True)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test namespaces."""
        for ns in [cls.test_ns1, cls.test_ns2]:
            subprocess.run(["ip", "netns", "delete", ns], 
                          capture_output=True)
    
    def setUp(self):
        """Set up each test."""
        self.manager = ServiceManager(verbose_level=0)
        self.client = ServiceClient(verbose_level=0)
        
        # Clean any existing services
        self.manager.cleanup_all_services()
    
    def tearDown(self):
        """Clean up after each test."""
        self.manager.cleanup_all_services()
    
    def test_tcp_service_lifecycle(self):
        """Test TCP service start/stop/restart."""
        config = ServiceConfig(
            name="test-tcp",
            port=8080,
            protocol=ServiceProtocol.TCP,
            namespace=self.test_ns1
        )
        
        # Start service
        self.manager.start_service(config)
        self.assertEqual(
            self.manager.get_service_status(self.test_ns1, "test-tcp", 8080),
            ServiceStatus.RUNNING
        )
        
        # Test service
        success, response = self.client.test_service(
            self.test_ns1,
            "127.0.0.1",
            8080,
            ServiceProtocol.TCP,
            "Hello TCP"
        )
        self.assertTrue(success)
        self.assertEqual(response, "Hello TCP")
        
        # Stop service
        self.manager.stop_service(self.test_ns1, "test-tcp", 8080)
        self.assertEqual(
            self.manager.get_service_status(self.test_ns1, "test-tcp", 8080),
            ServiceStatus.UNKNOWN
        )
        
        # Restart service
        self.manager.restart_service(config)
        self.assertEqual(
            self.manager.get_service_status(self.test_ns1, "test-tcp", 8080),
            ServiceStatus.RUNNING
        )
    
    def test_udp_service_lifecycle(self):
        """Test UDP service start/stop/restart."""
        config = ServiceConfig(
            name="test-udp",
            port=8081,
            protocol=ServiceProtocol.UDP,
            namespace=self.test_ns1
        )
        
        # Start service
        self.manager.start_service(config)
        
        # Test service
        success, response = self.client.test_service(
            self.test_ns1,
            "127.0.0.1",
            8081,
            ServiceProtocol.UDP,
            "Hello UDP"
        )
        self.assertTrue(success)
        self.assertEqual(response, "Hello UDP")
    
    def test_cross_namespace_communication(self):
        """Test service communication across namespaces."""
        config = ServiceConfig(
            name="cross-ns",
            port=9000,
            protocol=ServiceProtocol.TCP,
            namespace=self.test_ns2
        )
        
        self.manager.start_service(config)
        
        # Test from ns1 to ns2
        success, response = self.client.test_service(
            self.test_ns1,
            "10.99.1.2",
            9000,
            ServiceProtocol.TCP,
            "Cross namespace"
        )
        self.assertTrue(success)
        self.assertEqual(response, "Cross namespace")
    
    def test_multiple_services(self):
        """Test multiple services on different ports."""
        services = [
            ServiceConfig("svc1", 9001, ServiceProtocol.TCP, self.test_ns1),
            ServiceConfig("svc2", 9002, ServiceProtocol.TCP, self.test_ns1),
            ServiceConfig("svc3", 9003, ServiceProtocol.UDP, self.test_ns1),
        ]
        
        # Start all services
        for config in services:
            self.manager.start_service(config)
        
        # List services
        service_list = self.manager.list_services(self.test_ns1)
        self.assertEqual(len(service_list), 3)
        
        # Test each service
        for i, config in enumerate(services):
            success, response = self.client.test_service(
                self.test_ns1,
                "127.0.0.1",
                config.port,
                config.protocol,
                f"Service {i+1}"
            )
            self.assertTrue(success)
            self.assertEqual(response, f"Service {i+1}")
    
    def test_port_already_in_use(self):
        """Test error when port is already in use."""
        config1 = ServiceConfig("svc1", 8082, ServiceProtocol.TCP, self.test_ns1)
        config2 = ServiceConfig("svc2", 8082, ServiceProtocol.TCP, self.test_ns1)
        
        # Start first service
        self.manager.start_service(config1)
        
        # Try to start second service on same port
        with self.assertRaises(ServiceStartError) as cm:
            self.manager.start_service(config2)
        
        self.assertIn("Port 8082 is already in use", str(cm.exception))
    
    def test_connection_refused(self):
        """Test connection refused error."""
        # No service running
        with self.assertRaises(ServiceConnectionError) as cm:
            self.client.test_service(
                self.test_ns1,
                "127.0.0.1",
                8083,
                ServiceProtocol.TCP,
                "Test"
            )
        
        error = cm.exception
        self.assertIn("Connection was refused", error.suggestion)
        self.assertIn("Service is not running", error.suggestion)
    
    def test_connection_timeout(self):
        """Test connection timeout error."""
        # This would require a firewall rule to drop packets
        # For now, test timeout handling with non-routable IP
        with self.assertRaises(ServiceConnectionError) as cm:
            self.client.test_service(
                self.test_ns1,
                "10.255.255.255",  # Non-existent IP
                8084,
                ServiceProtocol.TCP,
                "Test",
                timeout=2  # Short timeout
            )
        
        error = cm.exception
        # Should be a connection error - exact message depends on network config
        self.assertIsInstance(error, ServiceConnectionError)
        self.assertIn("10.255.255.255", str(error))
    
    def test_invalid_response(self):
        """Test invalid service response error."""
        # This would require a mock service that returns wrong data
        # For this test, we'll create a simple netcat listener that echoes wrong data
        
        # Start a netcat listener with wrong echo format
        wrong_echo_cmd = [
            "ip", "netns", "exec", self.test_ns1,
            "sh", "-c",
            "echo 'WRONG: response' | nc -l -p 8085"
        ]
        
        # Run in background
        proc = subprocess.Popen(wrong_echo_cmd)
        time.sleep(0.5)  # Let it start
        
        try:
            with self.assertRaises(ServiceResponseError) as cm:
                self.client.test_service(
                    self.test_ns1,
                    "127.0.0.1",
                    8085,
                    ServiceProtocol.TCP,
                    "Test"
                )
            
            error = cm.exception
            self.assertIn("unexpected response", str(error))
            self.assertIn("Expected: Test", error.suggestion)
            self.assertIn("WRONG: response", error.suggestion)
        finally:
            # Clean up
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except:
                proc.kill()
    
    def test_multi_client_tcp(self):
        """Test multiple simultaneous TCP clients."""
        config = ServiceConfig(
            name="multi-tcp",
            port=8086,
            protocol=ServiceProtocol.TCP,
            namespace=self.test_ns1
        )
        
        self.manager.start_service(config)
        
        # Function to test service in thread
        results = []
        def test_client(client_id):
            try:
                success, response = self.client.test_service(
                    self.test_ns1,
                    "127.0.0.1",
                    8086,
                    ServiceProtocol.TCP,
                    f"Client {client_id}"
                )
                results.append((client_id, success, response))
            except Exception as e:
                results.append((client_id, False, str(e)))
        
        # Start multiple clients
        threads = []
        for i in range(5):
            t = threading.Thread(target=test_client, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all to complete
        for t in threads:
            t.join()
        
        # Check results
        self.assertEqual(len(results), 5)
        for client_id, success, response in results:
            self.assertTrue(success, f"Client {client_id} failed: {response}")
            self.assertEqual(response, f"Client {client_id}")
    
    def test_service_persistence(self):
        """Test that services persist across manager instances."""
        config = ServiceConfig(
            name="persistent",
            port=8087,
            protocol=ServiceProtocol.TCP,
            namespace=self.test_ns1
        )
        
        # Start service with one manager
        self.manager.start_service(config)
        
        # Create new manager instance
        new_manager = ServiceManager(verbose_level=0)
        
        # Check service is still registered
        services = new_manager.list_services(self.test_ns1)
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0]['name'], 'persistent')
        self.assertEqual(services[0]['status'], 'running')
        
        # Test service still works
        success, response = self.client.test_service(
            self.test_ns1,
            "127.0.0.1",
            8087,
            ServiceProtocol.TCP,
            "Still working"
        )
        self.assertTrue(success)
        self.assertEqual(response, "Still working")
    
    def test_cleanup_all_services(self):
        """Test cleanup of all services."""
        # Start multiple services
        for i in range(3):
            config = ServiceConfig(
                name=f"cleanup{i}",
                port=8090 + i,
                protocol=ServiceProtocol.TCP,
                namespace=self.test_ns1
            )
            self.manager.start_service(config)
        
        # Verify all running
        services = self.manager.list_services()
        self.assertEqual(len(services), 3)
        
        # Cleanup all
        self.manager.cleanup_all_services()
        
        # Verify all stopped
        services = self.manager.list_services()
        self.assertEqual(len(services), 0)
        
        # Verify services actually stopped
        for i in range(3):
            with self.assertRaises(ServiceConnectionError):
                self.client.test_service(
                    self.test_ns1,
                    "127.0.0.1",
                    8090 + i,
                    ServiceProtocol.TCP,
                    "Test"
                )


class TestServiceErrorHandling(unittest.TestCase):
    """Test error handling with different verbosity levels."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_ns = "test-error-ns"
        
        # Create namespace if not exists
        subprocess.run(["ip", "netns", "delete", self.test_ns], 
                      capture_output=True)
        subprocess.run(["ip", "netns", "add", self.test_ns], check=True)
        subprocess.run(["ip", "netns", "exec", self.test_ns, "ip", "link", "set", "lo", "up"], 
                      check=True)
    
    def tearDown(self):
        """Clean up."""
        subprocess.run(["ip", "netns", "delete", self.test_ns], 
                      capture_output=True)
    
    @unittest.skipIf(os.geteuid() != 0, "Requires root")
    def test_verbose_error_output(self):
        """Test error output at different verbosity levels."""
        # Test with non-existent namespace
        for verbose_level in [0, 1, 2]:
            manager = ServiceManager(verbose_level=verbose_level)
            config = ServiceConfig(
                name="test",
                port=8080,
                protocol=ServiceProtocol.TCP,
                namespace="non-existent-ns"
            )
            
            with self.assertRaises(Exception) as cm:
                manager.start_service(config)
            
            # At all levels, user should get friendly message
            error_str = str(cm.exception)
            self.assertIn("Namespace", error_str)
            self.assertNotIn("Traceback", error_str)
    
    @unittest.skipIf(os.geteuid() != 0, "Requires root")
    def test_service_validation_errors(self):
        """Test service configuration validation."""
        manager = ServiceManager()
        
        # Invalid port
        with self.assertRaises(Exception) as cm:
            config = ServiceConfig(
                name="invalid-port",
                port=99999,  # Invalid port
                protocol=ServiceProtocol.TCP,
                namespace=self.test_ns
            )
        
        self.assertIn("port", str(cm.exception).lower())


if __name__ == '__main__':
    # Check for root early
    if os.geteuid() != 0:
        print("Service tests require root privileges. Run with sudo.")
        sys.exit(1)
    
    unittest.main()