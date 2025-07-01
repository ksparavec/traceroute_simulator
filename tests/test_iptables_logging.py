#!/usr/bin/env python3
"""
Test suite for Task 2.3: Iptables Logging Implementation

This test suite validates the comprehensive iptables logging implementation
including log processing, filtering, and the netlog command-line tool.

Test Categories:
1. Log Processing Tests - Verify log parsing functionality
2. Log Filter Tests - Validate filtering capabilities
3. NetLog CLI Tests - Test command-line interface
4. Integration Tests - Test with enhanced raw facts
5. Output Format Tests - Validate text and JSON output
6. Real-time Processing Tests - Test live log processing
"""

import unittest
import os
import sys
import tempfile
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from analyzers.iptables_log_processor import IptablesLogProcessor, LogEntry, LogFilter as ProcessorLogFilter
from core.log_filter import LogFilter, FilterCriteria


class TestIptablesLogProcessor(unittest.TestCase):
    """Test suite for iptables log processor functionality."""

    def setUp(self):
        """Set up test environment."""
        self.processor = IptablesLogProcessor(verbose=False)
        self.test_log_data = [
            "Jul  1 10:30:15 hq-gw kernel: IN-ALLOW: IN=eth0 OUT=eth1 SRC=10.1.1.1 DST=10.2.1.1 LEN=84 TTL=64 PROTO=ICMP TYPE=8 CODE=0",
            "Jul  1 10:30:16 hq-gw kernel: FWD-ALLOW: IN=eth0 OUT=eth1 SRC=10.1.1.1 DST=10.2.1.1 LEN=84 TTL=63 PROTO=TCP SPT=12345 DPT=80",
            "Jul  1 10:30:17 br-gw kernel: FWD-DROP: IN=eth0 OUT= SRC=192.168.1.1 DST=10.1.1.1 LEN=60 TTL=64 PROTO=TCP SPT=54321 DPT=22",
            "Jul  1 10:30:18 dc-gw kernel: IN-ALLOW: IN=eth0 OUT= SRC=10.3.1.1 DST=10.3.1.2 LEN=64 TTL=64 PROTO=UDP SPT=53 DPT=12345"
        ]

    def test_01_processor_initialization(self):
        """Test iptables log processor initialization."""
        # Test default initialization
        processor = IptablesLogProcessor()
        self.assertFalse(processor.verbose)
        self.assertEqual(processor.verbose_level, 1)
        self.assertEqual(len(processor.routers), 0)
        self.assertIsInstance(processor.rule_database, dict)
        
        # Test with parameters
        processor_verbose = IptablesLogProcessor(verbose=True, verbose_level=2)
        self.assertTrue(processor_verbose.verbose)
        self.assertEqual(processor_verbose.verbose_level, 2)

    def test_02_log_line_parsing(self):
        """Test parsing of individual log lines."""
        test_line = "Jul  1 10:30:15 hq-gw kernel: FWD-ALLOW: IN=eth0 OUT=eth1 SRC=10.1.1.1 DST=10.2.1.1 LEN=84 TTL=64 PROTO=TCP SPT=12345 DPT=80"
        
        entry = self.processor.parse_log_line(test_line, "hq-gw")
        
        self.assertIsNotNone(entry)
        self.assertEqual(entry.router, "hq-gw")
        self.assertEqual(entry.prefix, "FWD-ALLOW")
        self.assertEqual(entry.protocol, "tcp")
        self.assertEqual(entry.source_ip, "10.1.1.1")
        self.assertEqual(entry.dest_ip, "10.2.1.1")
        self.assertEqual(entry.source_port, 12345)
        self.assertEqual(entry.dest_port, 80)
        self.assertEqual(entry.interface_in, "eth0")
        self.assertEqual(entry.interface_out, "eth1")
        self.assertEqual(entry.ttl, 64)
        self.assertEqual(entry.action, "ACCEPT")

    def test_03_icmp_log_parsing(self):
        """Test parsing of ICMP log entries."""
        icmp_line = "Jul  1 10:30:15 hq-gw kernel: IN-ALLOW: IN=eth0 OUT= SRC=10.1.1.1 DST=10.2.1.1 LEN=84 TTL=64 PROTO=ICMP TYPE=8 CODE=0"
        
        entry = self.processor.parse_log_line(icmp_line, "hq-gw")
        
        self.assertIsNotNone(entry)
        self.assertEqual(entry.protocol, "icmp")
        self.assertEqual(entry.source_ip, "10.1.1.1")
        self.assertEqual(entry.dest_ip, "10.2.1.1")
        self.assertIsNone(entry.source_port)
        self.assertIsNone(entry.dest_port)
        self.assertEqual(entry.action, "ACCEPT")

    def test_04_drop_log_parsing(self):
        """Test parsing of DROP log entries."""
        drop_line = "Jul  1 10:30:17 br-gw kernel: FWD-DROP: IN=eth0 OUT= SRC=192.168.1.1 DST=10.1.1.1 LEN=60 TTL=64 PROTO=TCP SPT=54321 DPT=22"
        
        entry = self.processor.parse_log_line(drop_line, "br-gw")
        
        self.assertIsNotNone(entry)
        self.assertEqual(entry.prefix, "FWD-DROP")
        self.assertEqual(entry.action, "DROP")
        self.assertEqual(entry.source_ip, "192.168.1.1")
        self.assertEqual(entry.dest_ip, "10.1.1.1")
        self.assertEqual(entry.dest_port, 22)

    def test_05_invalid_log_parsing(self):
        """Test parsing of invalid log lines."""
        invalid_lines = [
            "",
            "not a log line",
            "Jul  1 10:30:15 hq-gw sshd: Connection from 10.1.1.1",
            "incomplete log line"
        ]
        
        for line in invalid_lines:
            with self.subTest(line=line):
                entry = self.processor.parse_log_line(line)
                self.assertIsNone(entry)

    def test_06_log_file_parsing(self):
        """Test parsing logs from a file."""
        # Create temporary log file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            for line in self.test_log_data:
                f.write(line + '\n')
            temp_file = Path(f.name)
        
        try:
            entries = self.processor.parse_logs_from_file(temp_file, "test-router")
            
            self.assertEqual(len(entries), 4)
            self.assertTrue(all(isinstance(e, LogEntry) for e in entries))
            self.assertTrue(all(e.router == "test-router" for e in entries))
            
            # Check specific entries
            self.assertEqual(entries[0].protocol, "icmp")
            self.assertEqual(entries[1].protocol, "tcp")
            self.assertEqual(entries[1].dest_port, 80)
            self.assertEqual(entries[2].action, "DROP")
            self.assertEqual(entries[3].protocol, "udp")
            
        finally:
            temp_file.unlink()

    def test_07_router_management(self):
        """Test router management functionality."""
        processor = IptablesLogProcessor()
        
        # Add routers
        processor.add_router("hq-gw")
        processor.add_router("br-gw")
        
        self.assertIn("hq-gw", processor.routers)
        self.assertIn("br-gw", processor.routers)
        self.assertEqual(len(processor.routers), 2)

    def test_08_rule_database_loading(self):
        """Test rule database loading."""
        test_rules = {
            "hq-gw": {"iptables": {"filter": {"INPUT": ["rule1", "rule2"]}}},
            "br-gw": {"iptables": {"filter": {"FORWARD": ["rule3", "rule4"]}}}
        }
        
        self.processor.load_rule_database(test_rules)
        
        self.assertEqual(self.processor.rule_database, test_rules)

    def test_09_log_filtering(self):
        """Test log filtering functionality."""
        # Create test entries
        entries = []
        for line in self.test_log_data:
            entry = self.processor.parse_log_line(line)
            if entry:
                entries.append(entry)
        
        # Test protocol filter
        log_filter = ProcessorLogFilter(protocol="tcp")
        tcp_entries = self.processor.filter_entries(entries, log_filter)
        self.assertEqual(len(tcp_entries), 2)
        self.assertTrue(all(e.protocol == "tcp" for e in tcp_entries))
        
        # Test IP filter
        log_filter_ip = ProcessorLogFilter(source_ip="10.1.1.1")
        ip_entries = self.processor.filter_entries(entries, log_filter_ip)
        self.assertEqual(len(ip_entries), 2)
        self.assertTrue(all(e.source_ip == "10.1.1.1" for e in ip_entries))

    def test_10_report_generation_text(self):
        """Test text report generation."""
        # Create test entries
        entries = []
        for line in self.test_log_data:
            entry = self.processor.parse_log_line(line)
            if entry:
                entries.append(entry)
        
        report = self.processor.generate_report(entries, "text")
        
        self.assertIn("Iptables Log Analysis Report", report)
        self.assertIn("Total entries: 4", report)
        self.assertIn("Summary:", report)
        self.assertIn("Protocols:", report)
        self.assertIn("Actions:", report)
        self.assertIn("Log Entries:", report)

    def test_11_report_generation_json(self):
        """Test JSON report generation."""
        # Create test entries
        entries = []
        for line in self.test_log_data:
            entry = self.processor.parse_log_line(line)
            if entry:
                entries.append(entry)
        
        report = self.processor.generate_report(entries, "json")
        
        # Should be valid JSON
        parsed_report = json.loads(report)
        self.assertIsInstance(parsed_report, list)
        self.assertEqual(len(parsed_report), 4)
        
        # Check structure
        for entry in parsed_report:
            self.assertIn('timestamp', entry)
            self.assertIn('router', entry)
            self.assertIn('source_ip', entry)
            self.assertIn('dest_ip', entry)
            self.assertIn('protocol', entry)

    def test_12_namespace_log_parsing(self):
        """Test parsing logs from network namespace."""
        # Mock subprocess.run for namespace dmesg
        with patch('subprocess.run') as mock_run:
            # Create proper dmesg format with kernel log lines
            mock_output = '\n'.join([
                "Jul  1 10:30:15 test-ns kernel: IN-ALLOW: IN=eth0 OUT=eth1 SRC=10.1.1.1 DST=10.2.1.1 LEN=84 TTL=64 PROTO=ICMP TYPE=8 CODE=0",
                "Jul  1 10:30:16 test-ns kernel: FWD-ALLOW: IN=eth0 OUT=eth1 SRC=10.1.1.1 DST=10.2.1.1 LEN=84 TTL=63 PROTO=TCP SPT=12345 DPT=80"
            ])
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = mock_output
            
            entries = self.processor.parse_logs_from_namespace("test-ns")
            
            self.assertGreater(len(entries), 0)
            mock_run.assert_called_once()

    def test_13_journalctl_log_parsing(self):
        """Test parsing logs from systemd journal."""
        # Mock subprocess.run for journalctl
        with patch('subprocess.run') as mock_run:
            mock_output = '\n'.join(self.test_log_data)
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = mock_output
            
            entries = self.processor.parse_logs_from_journalctl("test-router", "1 hour ago")
            
            self.assertEqual(len(entries), 4)
            mock_run.assert_called_once()

    def test_14_log_correlation(self):
        """Test log correlation with rule database."""
        # Create test entries
        entries = []
        for line in self.test_log_data:
            entry = self.processor.parse_log_line(line)
            if entry:
                entries.append(entry)
        
        # Load test rule database
        test_rules = {
            "hq-gw": {"iptables": {"filter": {"INPUT": ["test rule"]}}},
            "br-gw": {"iptables": {"filter": {"FORWARD": ["test rule"]}}}
        }
        self.processor.load_rule_database(test_rules)
        
        # Test correlation
        correlated = self.processor.correlate_with_rules(entries)
        
        self.assertEqual(len(correlated), 4)
        for entry in correlated:
            self.assertIn('matched_rules', entry)
            self.assertIsInstance(entry['matched_rules'], list)


class TestLogFilter(unittest.TestCase):
    """Test suite for log filter functionality."""

    def setUp(self):
        """Set up test environment."""
        self.log_filter = LogFilter(verbose=False)
        self.test_entries = [
            {
                'timestamp': '2025-07-01 10:30:15',
                'router': 'hq-gw',
                'source_ip': '10.1.1.1',
                'dest_ip': '10.2.1.1',
                'protocol': 'tcp',
                'dest_port': 80,
                'action': 'ACCEPT'
            },
            {
                'timestamp': '2025-07-01 10:31:15',
                'router': 'br-gw',
                'source_ip': '192.168.1.1',
                'dest_ip': '10.1.1.1',
                'protocol': 'tcp',
                'dest_port': 22,
                'action': 'DROP'
            },
            {
                'timestamp': '2025-07-01 10:32:15',
                'router': 'dc-gw',
                'source_ip': '10.3.1.1',
                'dest_ip': '8.8.8.8',
                'protocol': 'udp',
                'dest_port': 53,
                'action': 'ACCEPT'
            }
        ]

    def test_01_filter_initialization(self):
        """Test log filter initialization."""
        # Test default initialization
        log_filter = LogFilter()
        self.assertFalse(log_filter.verbose)
        self.assertFalse(log_filter.case_sensitive)
        self.assertIsInstance(log_filter.compiled_patterns, dict)
        
        # Test with parameters
        log_filter_custom = LogFilter(verbose=True, case_sensitive=True)
        self.assertTrue(log_filter_custom.verbose)
        self.assertTrue(log_filter_custom.case_sensitive)

    def test_02_time_string_parsing(self):
        """Test time string parsing."""
        # Test absolute times
        abs_time = self.log_filter.parse_time_string("2025-07-01 10:30:15")
        self.assertEqual(abs_time.year, 2025)
        self.assertEqual(abs_time.month, 7)
        self.assertEqual(abs_time.day, 1)
        self.assertEqual(abs_time.hour, 10)
        
        # Test relative times
        rel_time = self.log_filter.parse_time_string("1 hour ago")
        now = datetime.now()
        expected = now - timedelta(hours=1)
        self.assertAlmostEqual(rel_time.timestamp(), expected.timestamp(), delta=60)

    def test_03_ip_network_matching(self):
        """Test IP network matching."""
        # Test exact IP match
        self.assertTrue(self.log_filter.match_ip_network("10.1.1.1", ["10.1.1.1"]))
        self.assertFalse(self.log_filter.match_ip_network("10.1.1.2", ["10.1.1.1"]))
        
        # Test CIDR match
        self.assertTrue(self.log_filter.match_ip_network("10.1.1.1", ["10.1.1.0/24"]))
        self.assertTrue(self.log_filter.match_ip_network("10.1.1.255", ["10.1.1.0/24"]))
        self.assertFalse(self.log_filter.match_ip_network("10.1.2.1", ["10.1.1.0/24"]))
        
        # Test empty list (should match all)
        self.assertTrue(self.log_filter.match_ip_network("10.1.1.1", []))

    def test_04_pattern_matching(self):
        """Test pattern matching."""
        # Test simple pattern matching
        self.assertTrue(self.log_filter.match_pattern_list("FWD-ALLOW", ["ALLOW"]))
        self.assertFalse(self.log_filter.match_pattern_list("FWD-DROP", ["ALLOW"]))
        
        # Test case sensitivity
        case_sensitive_filter = LogFilter(case_sensitive=True)
        self.assertFalse(case_sensitive_filter.match_pattern_list("fwd-allow", ["ALLOW"]))
        
        case_insensitive_filter = LogFilter(case_sensitive=False)
        self.assertTrue(case_insensitive_filter.match_pattern_list("fwd-allow", ["ALLOW"]))

    def test_05_network_filters(self):
        """Test network-based filtering."""
        criteria = FilterCriteria(
            source_networks=["10.1.1.0/24"],
            protocols=["tcp"]
        )
        
        filtered = self.log_filter.filter_entries(self.test_entries, criteria)
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['source_ip'], '10.1.1.1')
        self.assertEqual(filtered[0]['protocol'], 'tcp')

    def test_06_infrastructure_filters(self):
        """Test infrastructure-based filtering."""
        criteria = FilterCriteria(
            routers=["hq-gw", "dc-gw"]
        )
        
        filtered = self.log_filter.filter_entries(self.test_entries, criteria)
        
        self.assertEqual(len(filtered), 2)
        router_names = [entry['router'] for entry in filtered]
        self.assertIn('hq-gw', router_names)
        self.assertIn('dc-gw', router_names)
        self.assertNotIn('br-gw', router_names)

    def test_07_content_filters(self):
        """Test content-based filtering."""
        criteria = FilterCriteria(
            actions=["DROP"]
        )
        
        filtered = self.log_filter.filter_entries(self.test_entries, criteria)
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['action'], 'DROP')

    def test_08_advanced_filters(self):
        """Test advanced filtering options."""
        criteria = FilterCriteria(
            exclude_internal=True
        )
        
        # Mock IP classification methods
        with patch.object(self.log_filter, 'is_internal_ip') as mock_internal:
            mock_internal.side_effect = lambda ip: ip.startswith('10.') or ip.startswith('192.168.')
            
            filtered = self.log_filter.filter_entries(self.test_entries, criteria)
            
            # Should exclude entries where both source and dest are internal
            self.assertLess(len(filtered), len(self.test_entries))

    def test_09_entry_grouping(self):
        """Test log entry grouping."""
        grouped = self.log_filter.group_entries(self.test_entries, ['protocol'])
        
        self.assertIn('tcp', grouped)
        self.assertIn('udp', grouped)
        self.assertEqual(len(grouped['tcp']), 2)
        self.assertEqual(len(grouped['udp']), 1)

    def test_10_entry_deduplication(self):
        """Test log entry deduplication."""
        # Create duplicate entries
        duplicate_entries = self.test_entries + [self.test_entries[0].copy()]
        
        unique_entries = self.log_filter.deduplicate_entries(
            duplicate_entries, 
            ['timestamp', 'source_ip', 'dest_ip']
        )
        
        self.assertEqual(len(unique_entries), len(self.test_entries))

    def test_11_ip_classification(self):
        """Test IP address classification."""
        # Test internal IP detection
        self.assertTrue(self.log_filter.is_internal_ip("10.1.1.1"))
        self.assertTrue(self.log_filter.is_internal_ip("192.168.1.1"))
        self.assertTrue(self.log_filter.is_internal_ip("172.16.1.1"))
        self.assertFalse(self.log_filter.is_internal_ip("8.8.8.8"))
        
        # Test multicast IP detection
        self.assertTrue(self.log_filter.is_multicast_ip("224.0.0.1"))
        self.assertFalse(self.log_filter.is_multicast_ip("10.1.1.1"))

    def test_12_regex_patterns(self):
        """Test regex pattern matching."""
        patterns = ["FWD-.*", "IN-.*"]
        
        self.assertTrue(self.log_filter.match_regex_patterns("FWD-ALLOW", patterns))
        self.assertTrue(self.log_filter.match_regex_patterns("IN-DROP", patterns))
        self.assertFalse(self.log_filter.match_regex_patterns("OUT-ACCEPT", patterns))


class TestNetLogIntegration(unittest.TestCase):
    """Test suite for netlog CLI integration."""

    def setUp(self):
        """Set up test environment."""
        # Import NetLogCLI here to avoid import issues
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
            from netlog import NetLogCLI
            self.netlog_cli = NetLogCLI()
        except ImportError:
            self.skipTest("NetLog CLI not available")

    def test_01_cli_initialization(self):
        """Test NetLog CLI initialization."""
        self.assertIsInstance(self.netlog_cli.processor, IptablesLogProcessor)
        self.assertIsInstance(self.netlog_cli.filter, LogFilter)

    def test_02_time_range_parsing(self):
        """Test time range parsing in CLI."""
        start, end = self.netlog_cli.parse_time_range("10:00-11:00")
        
        self.assertEqual(start.hour, 10)
        self.assertEqual(start.minute, 0)
        self.assertEqual(end.hour, 11)
        self.assertEqual(end.minute, 0)

    def test_03_filter_criteria_creation(self):
        """Test filter criteria creation from CLI args."""
        # Mock command line arguments
        class MockArgs:
            source = "10.1.1.1"
            dest = "10.2.1.1"
            protocol = "tcp"
            port = 80
            source_port = None
            router = "hq-gw"
            all_routers = False
            interface_in = None
            interface_out = None
            time_range = None
            since = None
            last = 60
            action = "ACCEPT"
            prefix = None
            exclude_internal = False
            exclude_broadcast = False
            exclude_multicast = False
            errors_only = False
        
        criteria = self.netlog_cli.create_filter_criteria(MockArgs())
        
        self.assertEqual(criteria.source_networks, ["10.1.1.1"])
        self.assertEqual(criteria.dest_networks, ["10.2.1.1"])
        self.assertEqual(criteria.protocols, ["tcp"])
        self.assertEqual(criteria.dest_ports, [80])
        self.assertEqual(criteria.routers, ["hq-gw"])
        self.assertEqual(criteria.duration_minutes, 60)


def main():
    """Run the test suite."""
    # Change to script directory for relative paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(os.path.dirname(script_dir))
    
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()