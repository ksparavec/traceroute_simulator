#!/usr/bin/env -S python3 -B -u
"""
Comprehensive Test Suite for Error Handling

This module tests all error conditions and verifies that:
1. Errors are handled gracefully without stack traces (unless -vvv)
2. User-friendly messages are shown
3. Helpful suggestions are provided
4. Correct exit codes are returned
"""

import unittest
import subprocess
import sys
import os
import json
import tempfile
import shutil
from pathlib import Path
from typing import Tuple, Dict, Any
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.exceptions import (
    TracerouteError, ConfigurationError, FactsDirectoryError, NoRouterDataError,
    IPNotFoundError, NoRouteError, InvalidIPError, RouterNotFoundError,
    RouterDataError, NoLinuxRoutersError, SSHConnectionError, CommandExecutionError,
    PermissionError as TraceroutePermissionError, ResourceError, ValidationError,
    PortValidationError, ProtocolValidationError, ErrorHandler, ErrorCode
)
from src.core.models import Route, RouterMetadata, TraceroutePath
from src.core.logging import get_logger, setup_logging


class TestErrorMessages(unittest.TestCase):
    """Test error message formatting at different verbosity levels."""
    
    def test_basic_error_message(self):
        """Test basic error message without verbosity."""
        error = IPNotFoundError(
            "192.168.1.1",
            "Source",
            available_networks=["10.1.0.0/16", "10.2.0.0/16"]
        )
        
        message = error.format_error(verbose_level=0)
        
        # Should contain user-friendly message
        self.assertIn("Error: Source address 192.168.1.1 is not configured", message)
        self.assertIn("Suggestion:", message)
        self.assertIn("verify the source IP address", message)
        
        # Should NOT contain technical details
        self.assertNotIn("Details:", message)
        self.assertNotIn("Stack trace:", message)
        
    def test_verbose_error_message(self):
        """Test error message with -v verbosity."""
        error = NoRouteError(
            "10.1.1.1",
            "10.2.1.1", 
            last_hop="hq-router"
        )
        
        message = error.format_error(verbose_level=1)
        
        # Should contain details
        self.assertIn("Details:", message)
        self.assertIn("source: 10.1.1.1", message)
        self.assertIn("destination: 10.2.1.1", message)
        self.assertIn("last_successful_hop: hq-router", message)
        
    def test_debug_error_message(self):
        """Test error message with -vv verbosity."""
        cause = ValueError("Invalid format")
        error = InvalidIPError("999.999.999.999", cause=cause)
        
        message = error.format_error(verbose_level=2)
        
        # Should show cause
        self.assertIn("Caused by: ValueError", message)
        self.assertIn("Invalid format", message)
        
    def test_trace_error_message(self):
        """Test error message with -vvv verbosity."""
        try:
            raise ValueError("Test error")
        except ValueError as e:
            error = ConfigurationError("Config failed", cause=e)
            
        message = error.format_error(verbose_level=3)
        
        # Should show full stack trace
        self.assertIn("Stack trace:", message)
        self.assertIn("raise ValueError", message)


class TestExceptionTypes(unittest.TestCase):
    """Test specific exception types and their properties."""
    
    def test_facts_directory_error(self):
        """Test FactsDirectoryError suggestions."""
        error = FactsDirectoryError("/invalid/path")
        
        self.assertEqual(error.error_code, ErrorCode.CONFIGURATION_ERROR)
        self.assertIn("Facts directory not found", error.message)
        self.assertIn("export TRACEROUTE_SIMULATOR_FACTS", error.suggestion)
        self.assertIn("make fetch-routing-data", error.suggestion)
        
    def test_no_router_data_error(self):
        """Test NoRouterDataError suggestions."""
        error = NoRouterDataError("/empty/directory")
        
        self.assertIn("No router data files found", error.message)
        self.assertIn("make fetch-routing-data", error.suggestion)
        self.assertIn("Check file permissions", error.suggestion)
        
    def test_ip_not_found_with_networks(self):
        """Test IPNotFoundError with available networks."""
        networks = ["10.1.0.0/16", "10.2.0.0/16", "10.3.0.0/16"]
        error = IPNotFoundError("192.168.1.1", "Source", available_networks=networks)
        
        message = error.format_error(verbose_level=0)
        self.assertIn("Available networks:", message)
        self.assertIn("10.1.0.0/16", message)
        
    def test_router_not_found_error(self):
        """Test RouterNotFoundError with available routers."""
        routers = ["hq-gw", "hq-core", "br-gw"]
        error = RouterNotFoundError("hq-dmz", available_routers=routers)
        
        message = error.format_error(verbose_level=0)
        self.assertIn("Router 'hq-dmz' not found", message)
        self.assertIn("Available routers: br-gw, hq-core, hq-gw", message)
        
    def test_ssh_connection_error(self):
        """Test SSHConnectionError suggestions."""
        error = SSHConnectionError("10.1.1.1", "Connection refused")
        
        self.assertIn("Failed to connect to 10.1.1.1 via SSH", error.message)
        self.assertIn("SSH service is running", error.suggestion)
        self.assertIn("SSH key is authorized", error.suggestion)
        
    def test_permission_error(self):
        """Test PermissionError suggestions."""
        error = TraceroutePermissionError("namespace creation", "/var/run/netns")
        
        self.assertIn("Permission denied", error.message)
        self.assertIn("Run with sudo:", error.suggestion)
        
    def test_validation_errors(self):
        """Test validation error messages."""
        # Port validation
        port_error = PortValidationError("99999")
        self.assertIn("Invalid port: 99999", port_error.message)
        self.assertIn("between 1 and 65535", port_error.suggestion)
        
        # Protocol validation
        proto_error = ProtocolValidationError("xyz")
        self.assertIn("Invalid protocol: xyz", proto_error.message)
        self.assertIn("tcp, udp, icmp, all", proto_error.suggestion)


class TestErrorHandler(unittest.TestCase):
    """Test the ErrorHandler utility class."""
    
    def test_handle_traceroute_error(self):
        """Test handling of TracerouteError."""
        error = InvalidIPError("bad-ip")
        
        # Capture stderr
        old_stderr = sys.stderr
        sys.stderr = StringIO()
        
        try:
            exit_code = ErrorHandler.handle_error(error, verbose_level=0)
            output = sys.stderr.getvalue()
            
            self.assertEqual(exit_code, ErrorCode.INVALID_INPUT)
            self.assertIn("Invalid IP address format", output)
            self.assertNotIn("Stack trace:", output)
            
        finally:
            sys.stderr = old_stderr
            
    def test_handle_unexpected_error(self):
        """Test handling of unexpected errors."""
        error = RuntimeError("Unexpected failure")
        
        # Capture stderr
        old_stderr = sys.stderr
        sys.stderr = StringIO()
        
        try:
            # Without verbosity
            exit_code = ErrorHandler.handle_error(error, verbose_level=0)
            output = sys.stderr.getvalue()
            
            self.assertEqual(exit_code, ErrorCode.INTERNAL_ERROR)
            self.assertIn("An unexpected error occurred", output)
            self.assertIn("report it with the full error output", output)
            self.assertNotIn("RuntimeError", output)
            
        finally:
            sys.stderr = old_stderr
            
    def test_handle_unexpected_error_verbose(self):
        """Test handling of unexpected errors with verbosity."""
        error = RuntimeError("Unexpected failure")
        
        # Capture stderr
        old_stderr = sys.stderr
        sys.stderr = StringIO()
        
        try:
            # With verbosity
            exit_code = ErrorHandler.handle_error(error, verbose_level=1)
            output = sys.stderr.getvalue()
            
            self.assertIn("Error type: RuntimeError", output)
            self.assertIn("Error message: Unexpected failure", output)
            
        finally:
            sys.stderr = old_stderr


class TestErrorConditions(unittest.TestCase):
    """Test actual error conditions in the simulator."""
    
    def setUp(self):
        """Create test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.facts_dir = os.path.join(self.test_dir, "facts")
        os.makedirs(self.facts_dir)
        
    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir)
        
    def create_test_router(self, name: str, routes: list = None):
        """Create a test router JSON file."""
        router_data = {
            "routing": {
                "routes": routes or [
                    {
                        "dst": "10.1.0.0/24",
                        "dev": "eth0",
                        "protocol": "kernel",
                        "scope": "link",
                        "prefsrc": "10.1.0.1"
                    }
                ],
                "rules": []
            },
            "metadata": {
                "linux": True,
                "type": "core"
            }
        }
        
        with open(os.path.join(self.facts_dir, f"{name}.json"), 'w') as f:
            json.dump(router_data, f)
            
    def test_missing_facts_directory(self):
        """Test error when facts directory doesn't exist."""
        from src.core.traceroute_simulator_v2 import EnhancedTracerouteSimulator
        
        with self.assertRaises(FactsDirectoryError) as cm:
            simulator = EnhancedTracerouteSimulator(
                tsim_facts="/nonexistent/path",
                verbose_level=0
            )
            
        error = cm.exception
        self.assertIn("Facts directory not found", str(error))
        
    def test_empty_facts_directory(self):
        """Test error when facts directory is empty."""
        from src.core.traceroute_simulator_v2 import EnhancedTracerouteSimulator
        
        with self.assertRaises(NoRouterDataError) as cm:
            simulator = EnhancedTracerouteSimulator(
                tsim_facts=self.facts_dir,
                verbose_level=0
            )
            
        error = cm.exception
        self.assertIn("No router data files found", str(error))
        
    def test_corrupted_router_file(self):
        """Test error when router file is corrupted."""
        # Create corrupted JSON
        with open(os.path.join(self.facts_dir, "bad-router.json"), 'w') as f:
            f.write("{ invalid json }")
            
        from src.core.traceroute_simulator_v2 import EnhancedTracerouteSimulator
        
        with self.assertRaises(RouterDataError) as cm:
            simulator = EnhancedTracerouteSimulator(
                tsim_facts=self.facts_dir,
                verbose_level=0
            )
            
        error = cm.exception
        self.assertIn("Failed to load data for router", str(error))
        self.assertIn("Invalid JSON", error.suggestion)
        
    def test_invalid_source_ip(self):
        """Test error with invalid source IP."""
        self.create_test_router("test-router")
        
        from src.core.traceroute_simulator_v2 import EnhancedTracerouteSimulator
        
        simulator = EnhancedTracerouteSimulator(
            tsim_facts=self.facts_dir,
            verbose_level=0
        )
        
        with self.assertRaises(InvalidIPError) as cm:
            simulator.simulate_traceroute("999.999.999.999", "10.1.0.2")
            
        error = cm.exception
        self.assertIn("Invalid IP address format", str(error))
        self.assertIn("999.999.999.999", str(error))
        
    def test_source_ip_not_found(self):
        """Test error when source IP is not in network."""
        self.create_test_router("test-router")
        
        from src.core.traceroute_simulator_v2 import EnhancedTracerouteSimulator
        
        simulator = EnhancedTracerouteSimulator(
            tsim_facts=self.facts_dir,
            verbose_level=0
        )
        
        with self.assertRaises(IPNotFoundError) as cm:
            simulator.simulate_traceroute("192.168.1.1", "10.1.0.2")
            
        error = cm.exception
        self.assertIn("Source address 192.168.1.1 is not configured", str(error))
        self.assertIn("Available networks: 10.1.0.0/24", error.format_error(0))
        
    def test_no_route_to_destination(self):
        """Test error when no route exists."""
        self.create_test_router("router1", [
            {
                "dst": "10.1.0.0/24",
                "dev": "eth0",
                "protocol": "kernel",
                "scope": "link",
                "prefsrc": "10.1.0.1"
            }
        ])
        
        from src.core.traceroute_simulator_v2 import EnhancedTracerouteSimulator
        
        simulator = EnhancedTracerouteSimulator(
            tsim_facts=self.facts_dir,
            verbose_level=0
        )
        
        with self.assertRaises(NoRouteError) as cm:
            simulator.simulate_traceroute("10.1.0.2", "192.168.1.1")
            
        error = cm.exception
        self.assertIn("No route found from 10.1.0.2 to 192.168.1.1", str(error))
        self.assertIn("Missing routes in the routing table", error.suggestion)


class TestCommandLineErrorHandling(unittest.TestCase):
    """Test error handling via command line execution."""
    
    def setUp(self):
        """Set up test environment."""
        self.script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "core", "traceroute_simulator_v2.py"
        )
        self.test_facts = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "tsim_facts"
        )
        
    def run_simulator(self, args: list) -> Tuple[int, str, str]:
        """Run simulator and capture output."""
        cmd = [sys.executable, self.script_path] + args
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        return result.returncode, result.stdout, result.stderr
        
    def test_invalid_ip_error_cli(self):
        """Test invalid IP error via CLI."""
        exit_code, stdout, stderr = self.run_simulator([
            "-s", "not-an-ip",
            "-d", "10.1.1.1",
            "--tsim-facts", self.test_facts
        ])
        
        self.assertEqual(exit_code, ErrorCode.INVALID_INPUT)
        self.assertIn("Error: Invalid IP address format", stderr)
        self.assertIn("Suggestion:", stderr)
        self.assertNotIn("Stack trace:", stderr)
        self.assertNotIn("Traceback", stderr)
        
    def test_missing_directory_cli(self):
        """Test missing directory error via CLI."""
        exit_code, stdout, stderr = self.run_simulator([
            "-s", "10.1.1.1",
            "-d", "10.2.1.1",
            "--tsim-facts", "/nonexistent/path"
        ])
        
        self.assertEqual(exit_code, ErrorCode.CONFIGURATION_ERROR)
        self.assertIn("Facts directory not found", stderr)
        self.assertIn("export TRACEROUTE_SIMULATOR_FACTS", stderr)
        
    def test_verbose_error_output(self):
        """Test verbose error output."""
        # Test with -v
        exit_code, stdout, stderr = self.run_simulator([
            "-s", "not-an-ip",
            "-d", "10.1.1.1",
            "--tsim-facts", self.test_facts,
            "-v"
        ])
        
        self.assertIn("Details:", stderr)
        self.assertNotIn("Stack trace:", stderr)
        
    def test_trace_error_output(self):
        """Test trace-level error output."""
        # Test with -vvv
        exit_code, stdout, stderr = self.run_simulator([
            "-s", "not-an-ip",
            "-d", "10.1.1.1",
            "--tsim-facts", self.test_facts,
            "-vvv"
        ])
        
        self.assertIn("Stack trace:", stderr)
        self.assertIn("Traceback", stderr)
        
    def test_quiet_mode_errors(self):
        """Test error handling in quiet mode."""
        exit_code, stdout, stderr = self.run_simulator([
            "-s", "not-an-ip",
            "-d", "10.1.1.1",
            "--tsim-facts", self.test_facts,
            "-q"
        ])
        
        # Should still get exit code but no output
        self.assertEqual(exit_code, ErrorCode.INVALID_INPUT)
        self.assertEqual(stdout, "")
        # Errors should still go to stderr even in quiet mode
        self.assertIn("Error:", stderr)


class TestErrorSuggestions(unittest.TestCase):
    """Test that error suggestions are helpful and actionable."""
    
    def test_network_error_suggestions(self):
        """Test network-related error suggestions."""
        # No route error
        error = NoRouteError("10.1.1.1", "10.2.1.1", "router1")
        suggestion = error.suggestion
        
        self.assertIn("Missing routes", suggestion)
        self.assertIn("Firewall blocking", suggestion)
        self.assertIn("Check routing tables", suggestion)
        
    def test_configuration_error_suggestions(self):
        """Test configuration error suggestions."""
        # Facts directory error
        error = FactsDirectoryError("/path/to/facts")
        suggestion = error.suggestion
        
        self.assertIn("export TRACEROUTE_SIMULATOR_FACTS", suggestion)
        self.assertIn("make fetch-routing-data", suggestion)
        self.assertIn("--tsim-facts", suggestion)
        
    def test_execution_error_suggestions(self):
        """Test execution error suggestions."""
        # SSH error
        error = SSHConnectionError("host1", "Connection refused")
        suggestion = error.suggestion
        
        self.assertIn("SSH service is running", suggestion)
        self.assertIn("SSH key is authorized", suggestion)
        self.assertIn("Network connectivity", suggestion)
        self.assertIn("Firewall rules", suggestion)
        
    def test_permission_error_suggestions(self):
        """Test permission error suggestions."""
        error = TraceroutePermissionError("create namespace", "/var/run/netns")
        suggestion = error.suggestion
        
        self.assertIn("sudo", suggestion)
        self.assertIn("Check file/directory permissions", suggestion)


if __name__ == '__main__':
    unittest.main()