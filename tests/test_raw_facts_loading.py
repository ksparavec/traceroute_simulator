#!/usr/bin/env python3
"""
Test suite for Task 2.1: Raw Facts Direct Loading

This test suite validates the new raw facts parser and its integration
with the network namespace simulator, ensuring proper loading and parsing
of raw facts files without requiring intermediate JSON processing.

Test Categories:
1. Raw Facts Parser Tests - Validate parsing functionality
2. Data Structure Tests - Ensure output format compatibility
3. Network Interface Tests - Verify network configuration extraction
4. Routing Table Tests - Validate routing data parsing
5. Firewall Rules Tests - Ensure iptables/ipset parsing
6. Integration Tests - Test namespace simulator integration
"""

import unittest
import os
import sys
from pathlib import Path
from typing import Dict, Any

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.raw_facts_parser import RawFactsParser, load_raw_facts_directory


class TestRawFactsLoading(unittest.TestCase):
    """Test suite for raw facts loading functionality."""

    def setUp(self):
        """Set up test environment."""
        self.raw_facts_dir = Path("tests/raw_facts")
        self.test_files = [
            "hq-gw_facts.txt", "hq-core_facts.txt", "hq-dmz_facts.txt", "hq-lab_facts.txt",
            "br-gw_facts.txt", "br-core_facts.txt", "br-wifi_facts.txt",
            "dc-gw_facts.txt", "dc-core_facts.txt", "dc-srv_facts.txt"
        ]
        
        # Ensure test files exist
        for test_file in self.test_files:
            self.assertTrue(
                (self.raw_facts_dir / test_file).exists(),
                f"Test file {test_file} not found in {self.raw_facts_dir}"
            )

    def test_01_parser_initialization(self):
        """Test raw facts parser initialization."""
        # Test default initialization
        parser = RawFactsParser()
        self.assertEqual(parser.verbose, 0)
        self.assertFalse(parser.debug)
        self.assertFalse(parser.info)
        
        # Test verbose initialization
        parser_verbose = RawFactsParser(verbose=2)
        self.assertEqual(parser_verbose.verbose, 2)
        self.assertTrue(parser_verbose.debug)
        self.assertTrue(parser_verbose.info)

    def test_02_single_file_parsing(self):
        """Test parsing a single raw facts file."""
        parser = RawFactsParser()
        test_file = self.raw_facts_dir / "hq-gw_facts.txt"
        
        parsed_data = parser.parse_file(test_file)
        
        # Check basic structure
        self.assertIsInstance(parsed_data, dict)
        self.assertIn('header', parsed_data)
        self.assertIn('sections', parsed_data)
        self.assertIn('network', parsed_data)
        self.assertIn('firewall', parsed_data)
        
        # Check header information
        header = parsed_data['header']
        self.assertIn('hostname', header)
        self.assertEqual(header['hostname'], 'hq-gw')
        self.assertIn('kernel', header)
        self.assertIn('generated_on', header)

    def test_03_section_extraction(self):
        """Test extraction of TSIM sections."""
        parser = RawFactsParser()
        test_file = self.raw_facts_dir / "hq-gw_facts.txt"
        
        parsed_data = parser.parse_file(test_file)
        sections = parsed_data['sections']
        
        # Check that all expected sections are present
        expected_sections = [
            'routing_table', 'policy_rules', 'iptables_filter',
            'iptables_nat', 'ipset_save', 'ipset_list'
        ]
        
        for section in expected_sections:
            self.assertIn(section, sections, f"Missing section: {section}")
            
            section_data = sections[section]
            self.assertIn('title', section_data)
            self.assertIn('command', section_data)
            self.assertIn('content', section_data)
            self.assertIn('exit_code', section_data)

    def test_04_routing_table_parsing(self):
        """Test routing table parsing."""
        parser = RawFactsParser()
        test_file = self.raw_facts_dir / "hq-gw_facts.txt"
        
        parsed_data = parser.parse_file(test_file)
        
        # Check network interfaces (converted from routes)
        network_data = parsed_data['network']
        self.assertIn('interfaces', network_data)
        self.assertIn('routes', network_data)
        
        interfaces = network_data['interfaces']
        routes = network_data['routes']
        
        # Should have some interfaces/routes
        self.assertGreater(len(interfaces), 0, "No interfaces found")
        self.assertGreater(len(routes), 0, "No routes found")
        
        # Check interface structure
        for interface in interfaces:
            if interface.get('proto') == 'kernel' and interface.get('scope') == 'link':
                self.assertIn('dst', interface)
                self.assertIn('dev', interface)
                self.assertIn('prefsrc', interface)

    def test_05_policy_rules_parsing(self):
        """Test policy rules parsing."""
        parser = RawFactsParser()
        test_file = self.raw_facts_dir / "hq-gw_facts.txt"
        
        parsed_data = parser.parse_file(test_file)
        
        # Check policy rules
        network_data = parsed_data['network']
        self.assertIn('policy_rules', network_data)
        
        policy_rules = network_data['policy_rules']
        self.assertGreater(len(policy_rules), 0, "No policy rules found")
        
        # Check rule structure
        for rule in policy_rules:
            self.assertIn('priority', rule)
            self.assertIn('selector', rule)
            self.assertIsInstance(rule['priority'], int)

    def test_06_iptables_parsing(self):
        """Test iptables rules parsing."""
        parser = RawFactsParser()
        test_file = self.raw_facts_dir / "hq-gw_facts.txt"
        
        parsed_data = parser.parse_file(test_file)
        
        # Check iptables data
        firewall_data = parsed_data['firewall']
        self.assertIn('iptables', firewall_data)
        
        iptables_data = firewall_data['iptables']
        
        # Should have filter and nat tables
        expected_tables = ['filter', 'nat']
        for table in expected_tables:
            if table in iptables_data:
                self.assertIsInstance(iptables_data[table], dict)
                # Each table should have chains
                for chain, rules in iptables_data[table].items():
                    self.assertIsInstance(rules, list)

    def test_07_ipset_parsing(self):
        """Test ipset configurations parsing."""
        parser = RawFactsParser()
        test_file = self.raw_facts_dir / "hq-gw_facts.txt"
        
        parsed_data = parser.parse_file(test_file)
        
        # Check ipset data
        firewall_data = parsed_data['firewall']
        
        # Should have both save and list formats
        if 'ipsets_save' in firewall_data:
            ipsets_save = firewall_data['ipsets_save']
            self.assertIsInstance(ipsets_save, dict)
            
            # Check structure of save format
            for set_name, set_data in ipsets_save.items():
                self.assertIn('type', set_data)
                self.assertIn('members', set_data)
                self.assertIsInstance(set_data['members'], list)

    def test_08_additional_routing_tables(self):
        """Test parsing of additional routing tables."""
        parser = RawFactsParser()
        test_file = self.raw_facts_dir / "hq-gw_facts.txt"
        
        parsed_data = parser.parse_file(test_file)
        
        # Check additional routing tables
        network_data = parsed_data['network']
        if 'additional_routes' in network_data:
            additional_routes = network_data['additional_routes']
            self.assertIsInstance(additional_routes, dict)
            
            # Should have various routing tables
            expected_tables = ['priority_table', 'service_table', 'backup_table']
            for table in expected_tables:
                if table in additional_routes:
                    routes = additional_routes[table]
                    self.assertIsInstance(routes, list)
                    
                    # Check route structure
                    for route in routes:
                        self.assertIn('dst', route)
                        self.assertIn('table', route)
                        self.assertEqual(route['table'], table)

    def test_09_directory_loading(self):
        """Test loading all raw facts files from directory."""
        routers = load_raw_facts_directory(self.raw_facts_dir, verbose=0)
        
        # Should load all routers
        expected_routers = [
            'hq-gw', 'hq-core', 'hq-dmz', 'hq-lab',
            'br-gw', 'br-core', 'br-wifi',
            'dc-gw', 'dc-core', 'dc-srv'
        ]
        
        for router in expected_routers:
            self.assertIn(router, routers, f"Router {router} not loaded")
            
            router_data = routers[router]
            self.assertIn('header', router_data)
            self.assertIn('network', router_data)
            self.assertEqual(router_data['header']['hostname'], router)

    def test_10_data_format_compatibility(self):
        """Test that parsed data format is compatible with existing code."""
        parser = RawFactsParser()
        test_file = self.raw_facts_dir / "hq-gw_facts.txt"
        
        parsed_data = parser.parse_file(test_file)
        
        # Check required fields for namespace simulator
        self.assertIn('network', parsed_data)
        self.assertIn('interfaces', parsed_data['network'])
        self.assertIn('router_type', parsed_data)
        
        # Check interface format compatibility
        interfaces = parsed_data['network']['interfaces']
        for interface in interfaces:
            if interface.get('proto') == 'kernel' and interface.get('scope') == 'link':
                # These fields are required by namespace setup
                required_fields = ['dst', 'dev', 'prefsrc']
                for field in required_fields:
                    self.assertIn(field, interface, 
                        f"Interface missing required field: {field}")

    def test_11_error_handling(self):
        """Test error handling for invalid files."""
        parser = RawFactsParser()
        
        # Test non-existent file
        with self.assertRaises(FileNotFoundError):
            parser.parse_file(Path("non_existent_file.txt"))
        
        # Test empty directory loading
        empty_dir = Path("/tmp/empty_test_dir")
        empty_dir.mkdir(exist_ok=True)
        
        routers = load_raw_facts_directory(empty_dir, verbose=0)
        self.assertEqual(len(routers), 0, "Should return empty dict for empty directory")
        
        # Clean up
        empty_dir.rmdir()

    def test_12_management_ip_extraction(self):
        """Test extraction of management IP addresses."""
        parser = RawFactsParser()
        
        for test_file in self.test_files[:3]:  # Test first 3 files
            with self.subTest(file=test_file):
                parsed_data = parser.parse_file(self.raw_facts_dir / test_file)
                
                # Should have a management IP extracted
                management_ip = parsed_data.get('management_ip')
                if management_ip:
                    # Should be a valid IP address
                    import ipaddress
                    ipaddress.ip_address(management_ip)

    def test_13_verbose_output(self):
        """Test verbose output functionality."""
        # Test with different verbosity levels
        for verbose_level in [0, 1, 2]:
            with self.subTest(verbose=verbose_level):
                parser = RawFactsParser(verbose=verbose_level)
                test_file = self.raw_facts_dir / "hq-gw_facts.txt"
                
                # Should not raise exceptions regardless of verbosity
                parsed_data = parser.parse_file(test_file)
                self.assertIsInstance(parsed_data, dict)

    def test_14_section_completeness(self):
        """Test that all sections are properly captured."""
        parser = RawFactsParser()
        
        for test_file in self.test_files:
            with self.subTest(file=test_file):
                parsed_data = parser.parse_file(self.raw_facts_dir / test_file)
                sections = parsed_data['sections']
                
                # Should have minimum expected sections
                minimum_sections = ['routing_table', 'policy_rules']
                for section in minimum_sections:
                    self.assertIn(section, sections, 
                        f"File {test_file} missing section {section}")

    def test_15_data_consistency(self):
        """Test data consistency across parsing operations."""
        parser = RawFactsParser()
        test_file = self.raw_facts_dir / "hq-gw_facts.txt"
        
        # Parse the same file multiple times
        parsed_data1 = parser.parse_file(test_file)
        parsed_data2 = parser.parse_file(test_file)
        
        # Results should be identical
        self.assertEqual(parsed_data1['header'], parsed_data2['header'])
        self.assertEqual(len(parsed_data1['sections']), len(parsed_data2['sections']))
        self.assertEqual(len(parsed_data1['network']['interfaces']), 
                        len(parsed_data2['network']['interfaces']))


def main():
    """Run the test suite."""
    # Change to script directory for relative paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(os.path.dirname(script_dir))
    
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()