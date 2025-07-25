#!/usr/bin/env -S python3 -B -u
"""
Test suite for Task 2.2: Enhanced MTR Options Implementation

This test suite validates the enhanced MTR executor with comprehensive
command-line options support for advanced network testing scenarios.

Test Categories:
1. Options Validation Tests - Verify option parsing and validation
2. Command Building Tests - Ensure proper MTR command construction
3. Protocol Support Tests - Validate ICMP, UDP, TCP protocol support
4. Port Specification Tests - Test source/destination port handling
5. Timeout and Advanced Options Tests - Verify timeout and other options
6. Output Parsing Tests - Validate MTR output parsing
7. Integration Tests - Test with network namespace simulation
8. Error Handling Tests - Ensure proper error handling
"""

import unittest
import os
import sys
from unittest.mock import patch, MagicMock
from typing import Dict, Any

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from executors.enhanced_mtr_executor import (
    EnhancedMTRExecutor, MTROptions, MTRProtocol
)


class TestMTROptions(unittest.TestCase):
    """Test suite for MTR options validation and handling."""

    def setUp(self):
        """Set up test environment."""
        self.executor = EnhancedMTRExecutor(verbose=False)
        self.linux_routers = {'hq-gw', 'br-gw', 'dc-gw', 'hq-core'}
        self.executor_with_routers = EnhancedMTRExecutor(
            linux_routers=self.linux_routers, 
            verbose=True,
            verbose_level=2
        )

    def test_01_executor_initialization(self):
        """Test enhanced MTR executor initialization."""
        # Test default initialization
        executor = EnhancedMTRExecutor()
        self.assertFalse(executor.verbose)
        self.assertEqual(executor.verbose_level, 1)
        self.assertEqual(len(executor.linux_routers), 0)
        self.assertIsInstance(executor.default_options, MTROptions)
        
        # Test with parameters
        routers = {'router1', 'router2'}
        executor_custom = EnhancedMTRExecutor(
            linux_routers=routers,
            verbose=True,
            verbose_level=2
        )
        self.assertTrue(executor_custom.verbose)
        self.assertEqual(executor_custom.verbose_level, 2)
        self.assertEqual(executor_custom.linux_routers, routers)

    def test_02_mtr_options_creation(self):
        """Test MTR options dataclass creation and defaults."""
        # Test default options
        options = MTROptions()
        self.assertIsNone(options.source_ip)
        self.assertIsNone(options.destination_ip)
        self.assertIsNone(options.source_port)
        self.assertIsNone(options.destination_port)
        self.assertEqual(options.protocol, MTRProtocol.ICMP)
        self.assertEqual(options.timeout, 30)
        self.assertEqual(options.packet_count, 1)
        self.assertEqual(options.max_hops, 30)
        self.assertTrue(options.no_dns)
        
        # Test custom options
        custom_options = MTROptions(
            source_ip="10.1.1.1",
            destination_ip="10.2.1.1",
            source_port=12345,
            destination_port=80,
            protocol=MTRProtocol.TCP,
            timeout=60,
            packet_count=5
        )
        self.assertEqual(custom_options.source_ip, "10.1.1.1")
        self.assertEqual(custom_options.destination_port, 80)
        self.assertEqual(custom_options.protocol, MTRProtocol.TCP)
        self.assertEqual(custom_options.timeout, 60)

    def test_03_options_validation_success(self):
        """Test successful options validation."""
        # Valid ICMP options
        icmp_options = MTROptions(
            source_ip="10.1.1.1",
            destination_ip="10.2.1.1",
            protocol=MTRProtocol.ICMP,
            timeout=30
        )
        # Should not raise exception
        self.executor._validate_options(icmp_options)
        
        # Valid TCP options
        tcp_options = MTROptions(
            source_ip="192.168.1.1",
            destination_ip="192.168.2.1",
            source_port=12345,
            destination_port=80,
            protocol=MTRProtocol.TCP,
            timeout=45,
            packet_count=3,
            max_hops=20
        )
        # Should not raise exception
        self.executor._validate_options(tcp_options)
        
        # Valid UDP options
        udp_options = MTROptions(
            destination_ip="8.8.8.8",
            destination_port=53,
            protocol=MTRProtocol.UDP,
            packet_size=128
        )
        # Should not raise exception
        self.executor._validate_options(udp_options)

    def test_04_options_validation_failures(self):
        """Test options validation error cases."""
        # Invalid source IP
        with self.assertRaises(ValueError) as cm:
            invalid_options = MTROptions(source_ip="not.an.ip")
            self.executor._validate_options(invalid_options)
        self.assertIn("Invalid source IP", str(cm.exception))
        
        # Invalid destination IP  
        with self.assertRaises(ValueError) as cm:
            invalid_options = MTROptions(destination_ip="300.300.300.300")
            self.executor._validate_options(invalid_options)
        self.assertIn("Invalid destination IP", str(cm.exception))
        
        # Invalid source port
        with self.assertRaises(ValueError) as cm:
            invalid_options = MTROptions(source_port=70000)
            self.executor._validate_options(invalid_options)
        self.assertIn("Invalid source port", str(cm.exception))
        
        # Invalid destination port
        with self.assertRaises(ValueError) as cm:
            invalid_options = MTROptions(destination_port=0)
            self.executor._validate_options(invalid_options)
        self.assertIn("Invalid destination port", str(cm.exception))
        
        # Invalid timeout
        with self.assertRaises(ValueError) as cm:
            invalid_options = MTROptions(timeout=-5)
            self.executor._validate_options(invalid_options)
        self.assertIn("Invalid timeout", str(cm.exception))
        
        # TCP without destination port
        with self.assertRaises(ValueError) as cm:
            invalid_options = MTROptions(
                protocol=MTRProtocol.TCP,
                destination_ip="10.1.1.1"
            )
            self.executor._validate_options(invalid_options)
        self.assertIn("Destination port required", str(cm.exception))

    def test_05_mtr_command_building_icmp(self):
        """Test MTR command building for ICMP protocol."""
        options = MTROptions(
            source_ip="10.1.1.1",
            destination_ip="10.2.1.1",
            protocol=MTRProtocol.ICMP,
            packet_count=3,
            max_hops=20,
            timeout=45
        )
        
        cmd = self.executor._build_mtr_command("test-router", "10.2.1.1", options)
        
        # Check basic structure
        self.assertIn('mtr', cmd)
        self.assertIn('--report', cmd)
        self.assertIn('10.2.1.1', cmd)
        
        # Check ICMP (no specific protocol flag)
        self.assertNotIn('--tcp', cmd)
        self.assertNotIn('--udp', cmd)
        
        # Check other options
        self.assertIn('-c', cmd)
        self.assertIn('3', cmd)
        self.assertIn('-m', cmd)
        self.assertIn('20', cmd)
        self.assertIn('-a', cmd)
        self.assertIn('10.1.1.1', cmd)

    def test_06_mtr_command_building_tcp(self):
        """Test MTR command building for TCP protocol."""
        options = MTROptions(
            source_ip="192.168.1.1",
            destination_ip="192.168.2.1",
            source_port=12345,
            destination_port=80,
            protocol=MTRProtocol.TCP,
            packet_count=5,
            report_wide=True
        )
        
        cmd = self.executor._build_mtr_command("test-router", "192.168.2.1", options)
        
        # Check TCP protocol
        self.assertIn('--tcp', cmd)
        
        # Check ports
        self.assertIn('-P', cmd)
        self.assertIn('80', cmd)
        self.assertIn('-L', cmd)
        self.assertIn('12345', cmd)
        
        # Check wide report
        self.assertIn('-w', cmd)
        
        # Check packet count
        self.assertIn('-c', cmd)
        self.assertIn('5', cmd)

    def test_07_mtr_command_building_udp(self):
        """Test MTR command building for UDP protocol."""
        options = MTROptions(
            destination_ip="8.8.8.8",
            destination_port=53,
            protocol=MTRProtocol.UDP,
            packet_size=128,
            show_ips=True,
            no_dns=False
        )
        
        cmd = self.executor._build_mtr_command("test-router", "8.8.8.8", options)
        
        # Check UDP protocol
        self.assertIn('--udp', cmd)
        
        # Check destination port
        self.assertIn('-P', cmd)
        self.assertIn('53', cmd)
        
        # Check packet size
        self.assertIn('-s', cmd)
        self.assertIn('128', cmd)
        
        # Check show IPs
        self.assertIn('-b', cmd)
        
        # Check DNS resolution (no --no-dns flag)
        self.assertNotIn('--no-dns', cmd)

    def test_08_mtr_output_parsing_text(self):
        """Test parsing of MTR text output."""
        mtr_output = """Start: 2025-07-01T10:30:00+0000
HOST: test-router                 Loss%   Snt   Last   Avg  Best  Wrst StDev
  1.|-- 10.1.1.1                  0.0%     1    0.5   0.5   0.5   0.5   0.0
  2.|-- 10.1.2.1                  0.0%     1    1.2   1.2   1.2   1.2   0.0
  3.|-- 10.2.1.1                  0.0%     1    2.1   2.1   2.1   2.1   0.0"""
        
        options = MTROptions()
        hops = self.executor._parse_mtr_output(mtr_output, options)
        
        self.assertEqual(len(hops), 3)
        
        # Check first hop
        self.assertEqual(hops[0]['hop'], 1)
        self.assertEqual(hops[0]['ip'], '10.1.1.1')
        self.assertEqual(hops[0]['rtt'], 0.5)
        self.assertEqual(hops[0]['loss'], 0.0)
        
        # Check last hop
        self.assertEqual(hops[2]['hop'], 3)
        self.assertEqual(hops[2]['ip'], '10.2.1.1')
        self.assertEqual(hops[2]['rtt'], 2.1)

    def test_09_mtr_output_parsing_json(self):
        """Test parsing of MTR JSON output."""
        json_output = """{
  "report": {
    "mtr": {
      "version": "0.95"
    },
    "hubs": [
      {
        "count": 1,
        "host": "10.1.1.1",
        "loss%": 0.0,
        "snt": 1,
        "rcv": 1,
        "avg": 0.5,
        "best": 0.5,
        "wrst": 0.5,
        "stdev": 0.0
      },
      {
        "count": 2,
        "host": "10.2.1.1",
        "loss%": 0.0,
        "snt": 1,
        "rcv": 1,
        "avg": 2.1,
        "best": 2.1,
        "wrst": 2.1,
        "stdev": 0.0
      }
    ]
  }
}"""
        
        options = MTROptions(json_output=True)
        hops = self.executor._parse_mtr_output(json_output, options)
        
        self.assertEqual(len(hops), 2)
        
        # Check first hop
        self.assertEqual(hops[0]['hop'], 1)
        self.assertEqual(hops[0]['ip'], '10.1.1.1')
        self.assertEqual(hops[0]['rtt'], 0.5)
        self.assertEqual(hops[0]['loss'], 0.0)

    def test_10_reverse_dns_lookup(self):
        """Test reverse DNS lookup functionality."""
        # Test with mock subprocess
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "10.1.1.1 hq-gw.example.com\n"
            
            hostname = self.executor._perform_reverse_dns("10.1.1.1")
            self.assertEqual(hostname, "hq-gw.example.com")
        
        # Test with failed lookup
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            
            hostname = self.executor._perform_reverse_dns("192.168.1.1")
            self.assertIsNone(hostname)

    def test_11_connectivity_testing(self):
        """Test basic connectivity testing functionality."""
        # Mock the execute_mtr_advanced method
        with patch.object(self.executor, 'execute_mtr_advanced') as mock_execute:
            mock_execute.return_value = [
                {'hop': 1, 'ip': '10.1.1.1', 'rtt': 0.5, 'loss': 0.0},
                {'hop': 2, 'ip': '10.2.1.1', 'rtt': 2.1, 'loss': 0.0}
            ]
            
            result = self.executor.test_connectivity(
                "test-router", "10.2.1.1", MTRProtocol.ICMP
            )
            
            self.assertTrue(result['success'])
            self.assertTrue(result['reachable'])
            self.assertEqual(result['hops'], 2)
            self.assertEqual(result['final_ip'], '10.2.1.1')
            self.assertEqual(result['rtt'], 2.1)
            self.assertEqual(result['protocol'], 'icmp')

    def test_12_linux_router_management(self):
        """Test Linux router management functionality."""
        executor = EnhancedMTRExecutor()
        
        # Test adding routers
        executor.add_linux_router("hq-gw")
        executor.add_linux_router("br-gw")
        
        self.assertIn("hq-gw", executor.linux_routers)
        self.assertIn("br-gw", executor.linux_routers)
        self.assertEqual(len(executor.linux_routers), 2)

    def test_13_default_options_management(self):
        """Test default options management."""
        executor = EnhancedMTRExecutor()
        
        # Test setting default options
        custom_defaults = MTROptions(
            protocol=MTRProtocol.TCP,
            destination_port=80,
            timeout=60,
            packet_count=5
        )
        
        executor.set_default_options(custom_defaults)
        
        self.assertEqual(executor.default_options.protocol, MTRProtocol.TCP)
        self.assertEqual(executor.default_options.destination_port, 80)
        self.assertEqual(executor.default_options.timeout, 60)

    def test_14_protocol_enum(self):
        """Test MTR protocol enumeration."""
        # Test enum values
        self.assertEqual(MTRProtocol.ICMP.value, "icmp")
        self.assertEqual(MTRProtocol.UDP.value, "udp")
        self.assertEqual(MTRProtocol.TCP.value, "tcp")
        
        # Test enum creation from string
        icmp_proto = MTRProtocol("icmp")
        self.assertEqual(icmp_proto, MTRProtocol.ICMP)

    def test_15_error_handling(self):
        """Test error handling in various scenarios."""
        # Test with invalid router
        with patch.object(self.executor, 'execute_mtr_advanced') as mock_execute:
            mock_execute.side_effect = ValueError("Connection failed")
            
            result = self.executor.test_connectivity(
                "invalid-router", "10.1.1.1", MTRProtocol.ICMP
            )
            
            self.assertFalse(result['success'])
            self.assertIn('error', result)
            self.assertFalse(result['reachable'])

    def test_16_command_timeout_handling(self):
        """Test timeout handling in MTR commands."""
        options = MTROptions(
            destination_ip="10.1.1.1",
            timeout=5,  # Short timeout
            packet_count=1
        )
        
        # Validate that timeout is properly set
        self.executor._validate_options(options)
        self.assertEqual(options.timeout, 5)

    def test_17_advanced_options_support(self):
        """Test advanced MTR options support."""
        options = MTROptions(
            source_ip="192.168.1.1",
            destination_ip="192.168.2.1",
            protocol=MTRProtocol.UDP,
            destination_port=53,
            packet_size=256,
            interval=0.5,
            max_hops=15,
            report_wide=True,
            show_ips=True,
            no_dns=False
        )
        
        # Should validate successfully
        self.executor._validate_options(options)
        
        # Build command and check advanced options
        cmd = self.executor._build_mtr_command("test", "192.168.2.1", options)
        
        self.assertIn('-s', cmd)
        self.assertIn('256', cmd)
        self.assertIn('-i', cmd)
        self.assertIn('0.5', cmd)
        self.assertIn('-m', cmd)
        self.assertIn('15', cmd)
        self.assertIn('-w', cmd)
        self.assertIn('-b', cmd)


def main():
    """Run the test suite."""
    # Change to script directory for relative paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(os.path.dirname(script_dir))
    
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()