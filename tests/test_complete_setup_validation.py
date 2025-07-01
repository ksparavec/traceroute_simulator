#!/usr/bin/env python3
"""
Test suite for Complete Network Setup Validation

This test suite validates the complete implementation of the raw facts block loader
and network namespace setup, ensuring all components work together to create
a fully functional network simulation with ALL configuration elements loaded.

Test Categories:
1. Raw Facts Block Loader Tests - Validate section extraction and loading
2. Network Namespace Setup Tests - Verify complete router configuration
3. Configuration Application Tests - Test iptables, ipsets, routing tables
4. Status Display Tests - Validate netstatus shows all elements
5. Integration Tests - End-to-end functionality validation

Requirements:
- Must be run as root for namespace operations
- Requires raw facts files in tests/raw_facts/
- Validates that netstatus shows complete configuration
"""

import unittest
import subprocess
import os
import sys
import tempfile
import json
from pathlib import Path
from typing import Dict, List, Set, Any

# Add project directories to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'src'))
sys.path.insert(0, str(PROJECT_ROOT))

from core.raw_facts_block_loader import RawFactsBlockLoader, RouterRawFacts
from simulators.network_namespace_setup import CompleteNetworkSetup
from simulators.network_namespace_status import NetworkNamespaceStatus


class TestCompleteSetupValidation(unittest.TestCase):
    """Comprehensive test suite for complete network setup validation."""

    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        cls.raw_facts_dir = PROJECT_ROOT / "tests" / "raw_facts"
        cls.json_facts_dir = PROJECT_ROOT / "tests" / "tsim_facts"
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="complete_setup_test_"))
        
        # Check if running as root
        cls.is_root = os.geteuid() == 0
        
        # Required test files
        cls.required_raw_facts = [
            "hq-gw_facts.txt", "hq-core_facts.txt", "hq-dmz_facts.txt", "hq-lab_facts.txt",
            "br-gw_facts.txt", "br-core_facts.txt", "br-wifi_facts.txt",
            "dc-gw_facts.txt", "dc-core_facts.txt", "dc-srv_facts.txt"
        ]
        
        # Verify test prerequisites
        if not cls.raw_facts_dir.exists():
            raise unittest.SkipTest(f"Raw facts directory not found: {cls.raw_facts_dir}")
        
        for facts_file in cls.required_raw_facts:
            if not (cls.raw_facts_dir / facts_file).exists():
                raise unittest.SkipTest(f"Required raw facts file missing: {facts_file}")

    @classmethod
    def tearDownClass(cls):
        """Clean up test environment."""
        import shutil
        if cls.temp_dir.exists():
            shutil.rmtree(cls.temp_dir)

    def setUp(self):
        """Set up individual test."""
        self.loader = RawFactsBlockLoader(verbose=1)

    def test_01_raw_facts_block_loader_initialization(self):
        """Test raw facts block loader initialization."""
        self.assertIsInstance(self.loader, RawFactsBlockLoader)
        self.assertEqual(self.loader.verbose, 1)
        self.assertIsInstance(self.loader.routers, dict)

    def test_02_raw_facts_directory_loading(self):
        """Test loading all raw facts files from directory."""
        routers = self.loader.load_raw_facts_directory(self.raw_facts_dir)
        
        # Verify all routers loaded
        self.assertEqual(len(routers), 10, "Should load 10 routers")
        
        expected_routers = {"hq-gw", "hq-core", "hq-dmz", "hq-lab", 
                           "br-gw", "br-core", "br-wifi", 
                           "dc-gw", "dc-core", "dc-srv"}
        actual_routers = set(routers.keys())
        self.assertEqual(actual_routers, expected_routers, "Router names should match expected set")
        
        # Verify each router has sections
        for router_name, router_facts in routers.items():
            with self.subTest(router=router_name):
                self.assertIsInstance(router_facts, RouterRawFacts)
                self.assertGreater(len(router_facts.sections), 0, f"Router {router_name} should have sections")

    def test_03_section_extraction_validation(self):
        """Test that all expected sections are extracted from raw facts."""
        routers = self.loader.load_raw_facts_directory(self.raw_facts_dir)
        
        # Test hq-gw specifically as it has comprehensive configuration
        hq_gw = routers.get("hq-gw")
        self.assertIsNotNone(hq_gw, "hq-gw router should be loaded")
        
        # Verify essential sections exist
        essential_sections = [
            "routing_table",
            "policy_rules", 
            "iptables_save",
            "ipset_save"
        ]
        
        for section_name in essential_sections:
            with self.subTest(section=section_name):
                section = hq_gw.get_section(section_name)
                self.assertIsNotNone(section, f"Section {section_name} should exist")
                self.assertGreater(len(section.content), 0, f"Section {section_name} should have content")

    def test_04_routing_sections_extraction(self):
        """Test extraction of routing-related sections."""
        routers = self.loader.load_raw_facts_directory(self.raw_facts_dir)
        hq_gw = routers.get("hq-gw")
        
        routing_sections = hq_gw.get_routing_sections()
        self.assertGreater(len(routing_sections), 0, "Should have routing sections")
        
        # Check for main routing table
        main_routing = hq_gw.get_section("routing_table")
        self.assertIsNotNone(main_routing)
        self.assertIn("10.1.1.0/24", main_routing.content, "Should contain expected network")

    def test_05_iptables_sections_extraction(self):
        """Test extraction of iptables sections."""
        routers = self.loader.load_raw_facts_directory(self.raw_facts_dir)
        hq_gw = routers.get("hq-gw")
        
        iptables_sections = hq_gw.get_iptables_sections()
        self.assertGreater(len(iptables_sections), 0, "Should have iptables sections")
        
        # Check iptables-save content
        iptables_save = hq_gw.get_section("iptables_save")
        self.assertIsNotNone(iptables_save)
        self.assertIn("*filter", iptables_save.content, "Should contain filter table")

    def test_06_ipset_sections_extraction(self):
        """Test extraction of ipset sections."""
        routers = self.loader.load_raw_facts_directory(self.raw_facts_dir)
        hq_gw = routers.get("hq-gw")
        
        ipset_sections = hq_gw.get_ipset_sections()
        self.assertGreater(len(ipset_sections), 0, "Should have ipset sections")
        
        # Check ipset save content
        ipset_save = hq_gw.get_section("ipset_save")
        self.assertIsNotNone(ipset_save)
        self.assertIn("create", ipset_save.content, "Should contain ipset create commands")

    def test_07_section_content_validation(self):
        """Test that section content is properly extracted."""
        routers = self.loader.load_raw_facts_directory(self.raw_facts_dir)
        
        for router_name, router_facts in routers.items():
            with self.subTest(router=router_name):
                for section_name, section in router_facts.sections.items():
                    # Each section should have proper metadata
                    self.assertIsNotNone(section.name)
                    self.assertIsNotNone(section.title)
                    self.assertIsNotNone(section.command)
                    self.assertIsNotNone(section.timestamp)
                    self.assertIsInstance(section.content, str)
                    self.assertIsInstance(section.exit_code, int)

    @unittest.skipUnless(os.geteuid() == 0, "Requires root privileges for namespace operations")
    def test_08_network_setup_initialization(self):
        """Test network setup initialization with raw facts."""
        # Set environment for raw facts
        os.environ['TRACEROUTE_SIMULATOR_RAW_FACTS'] = str(self.raw_facts_dir)
        os.environ['TRACEROUTE_SIMULATOR_FACTS'] = str(self.json_facts_dir)
        
        setup = CompleteNetworkSetup(verbose=1)
        
        # Load facts
        setup.load_facts()
        
        # Verify routers loaded
        self.assertEqual(len(setup.routers), 10, "Should load 10 routers")
        self.assertGreater(len(setup.subnets), 0, "Should extract subnets from routing tables")

    @unittest.skipUnless(os.geteuid() == 0, "Requires root privileges for namespace operations")
    def test_09_complete_network_setup_dry_run(self):
        """Test complete network setup without actually creating namespaces."""
        # Set environment for raw facts
        os.environ['TRACEROUTE_SIMULATOR_RAW_FACTS'] = str(self.raw_facts_dir)
        os.environ['TRACEROUTE_SIMULATOR_FACTS'] = str(self.json_facts_dir)
        
        setup = CompleteNetworkSetup(verbose=1)
        setup.load_facts()
        
        # Verify topology extraction
        self.assertGreater(len(setup.router_interfaces), 0, "Should extract interface information")
        
        # Verify metadata loading
        self.assertIsInstance(setup.router_metadata, dict, "Should load metadata")

    @unittest.skipUnless(os.geteuid() == 0, "Requires root privileges for namespace operations")
    def test_10_namespace_status_tool_initialization(self):
        """Test network namespace status tool initialization."""
        # Set environment for facts
        os.environ['TRACEROUTE_SIMULATOR_FACTS'] = str(self.json_facts_dir)
        
        status_tool = NetworkNamespaceStatus(str(self.json_facts_dir), verbose=1)
        
        # Verify initialization
        self.assertIsInstance(status_tool.known_routers, set)
        self.assertIsInstance(status_tool.hosts, dict)
        self.assertIsInstance(status_tool.available_namespaces, set)

    def test_11_configuration_application_methods(self):
        """Test configuration application methods exist and are callable."""
        loader = RawFactsBlockLoader(verbose=0)
        routers = loader.load_raw_facts_directory(self.raw_facts_dir)
        hq_gw = routers.get("hq-gw")
        
        # Test method existence
        self.assertTrue(hasattr(loader, 'apply_routing_to_namespace'))
        self.assertTrue(hasattr(loader, 'apply_iptables_to_namespace'))
        self.assertTrue(hasattr(loader, 'apply_ipsets_to_namespace'))
        
        # Test methods are callable
        self.assertTrue(callable(loader.apply_routing_to_namespace))
        self.assertTrue(callable(loader.apply_iptables_to_namespace))
        self.assertTrue(callable(loader.apply_ipsets_to_namespace))

    def test_12_status_display_methods(self):
        """Test that status display methods exist for comprehensive display."""
        # Set environment for facts
        os.environ['TRACEROUTE_SIMULATOR_FACTS'] = str(self.json_facts_dir)
        
        status_tool = NetworkNamespaceStatus(str(self.json_facts_dir), verbose=0)
        
        # Test comprehensive display methods exist
        comprehensive_methods = [
            'show_interfaces',
            'show_routes', 
            'show_rules',
            'show_iptables',
            'show_iptables_nat',
            'show_iptables_mangle',
            'show_ipsets',
            'show_routing_tables',
            'show_all_configuration'
        ]
        
        for method_name in comprehensive_methods:
            with self.subTest(method=method_name):
                self.assertTrue(hasattr(status_tool, method_name), f"Method {method_name} should exist")
                self.assertTrue(callable(getattr(status_tool, method_name)), f"Method {method_name} should be callable")

    def test_13_environment_variable_handling(self):
        """Test proper handling of environment variables."""
        # Test with raw facts environment
        original_raw_facts = os.environ.get('TRACEROUTE_SIMULATOR_RAW_FACTS')
        original_facts = os.environ.get('TRACEROUTE_SIMULATOR_FACTS')
        
        try:
            # Set test environment
            os.environ['TRACEROUTE_SIMULATOR_RAW_FACTS'] = str(self.raw_facts_dir)
            if 'TRACEROUTE_SIMULATOR_FACTS' in os.environ:
                del os.environ['TRACEROUTE_SIMULATOR_FACTS']
            
            # Test setup can handle raw facts only
            setup = CompleteNetworkSetup(verbose=0)
            self.assertIsNotNone(setup.raw_loader)
            
        finally:
            # Restore environment
            if original_raw_facts:
                os.environ['TRACEROUTE_SIMULATOR_RAW_FACTS'] = original_raw_facts
            elif 'TRACEROUTE_SIMULATOR_RAW_FACTS' in os.environ:
                del os.environ['TRACEROUTE_SIMULATOR_RAW_FACTS']
            
            if original_facts:
                os.environ['TRACEROUTE_SIMULATOR_FACTS'] = original_facts

    def test_14_section_summary_generation(self):
        """Test generation of section summaries for debugging."""
        routers = self.loader.load_raw_facts_directory(self.raw_facts_dir)
        summary = self.loader.get_section_summary()
        
        # Verify summary structure
        self.assertIsInstance(summary, dict)
        self.assertEqual(len(summary), 10, "Should have summary for all 10 routers")
        
        # Verify each router has section counts
        for router_name, section_counts in summary.items():
            with self.subTest(router=router_name):
                self.assertIsInstance(section_counts, dict)
                self.assertGreater(len(section_counts), 0, f"Router {router_name} should have section counts")

    def test_15_error_handling_validation(self):
        """Test error handling in various scenarios."""
        # Test with non-existent directory
        with self.assertRaises(FileNotFoundError):
            self.loader.load_raw_facts_directory(Path("/nonexistent/directory"))
        
        # Test with empty directory
        empty_dir = self.temp_dir / "empty"
        empty_dir.mkdir()
        with self.assertRaises(FileNotFoundError):
            self.loader.load_raw_facts_directory(empty_dir)

    def test_16_data_integrity_validation(self):
        """Test data integrity across all routers."""
        routers = self.loader.load_raw_facts_directory(self.raw_facts_dir)
        
        # Verify each router has essential data
        for router_name, router_facts in routers.items():
            with self.subTest(router=router_name):
                # Should have hostname
                self.assertIsNotNone(router_facts.hostname)
                
                # Should have facts file reference
                self.assertIsNotNone(router_facts.facts_file)
                self.assertTrue(router_facts.facts_file.exists())
                
                # Should have at least basic sections
                self.assertGreater(len(router_facts.sections), 5, f"Router {router_name} should have multiple sections")

    def test_17_content_format_validation(self):
        """Test that content formats are valid for system tools."""
        routers = self.loader.load_raw_facts_directory(self.raw_facts_dir)
        hq_gw = routers.get("hq-gw")
        
        # Test iptables-save format
        iptables_save = hq_gw.get_section("iptables_save")
        if iptables_save:
            content = iptables_save.content
            # Should start with table definitions
            self.assertTrue("*filter" in content or "*nat" in content or "*mangle" in content,
                          "iptables-save should contain table definitions")
            
        # Test ipset save format
        ipset_save = hq_gw.get_section("ipset_save")
        if ipset_save:
            content = ipset_save.content
            # Should contain create commands
            self.assertIn("create", content, "ipset save should contain create commands")

    def test_18_router_classification_support(self):
        """Test support for router classification from metadata."""
        # Test metadata loading without requiring it
        setup = CompleteNetworkSetup(verbose=0)
        self.assertIsInstance(setup.router_metadata, dict)
        
        # Should handle missing metadata gracefully
        self.assertIsNotNone(setup.router_metadata)


class TestSetupIntegration(unittest.TestCase):
    """Integration tests for complete setup workflow."""

    def setUp(self):
        """Set up integration test."""
        self.raw_facts_dir = PROJECT_ROOT / "tests" / "raw_facts"
        self.json_facts_dir = PROJECT_ROOT / "tests" / "tsim_facts"

    @unittest.skipUnless(os.geteuid() == 0, "Requires root privileges")
    def test_end_to_end_workflow(self):
        """Test complete end-to-end workflow."""
        # Set environment
        os.environ['TRACEROUTE_SIMULATOR_RAW_FACTS'] = str(self.raw_facts_dir)
        os.environ['TRACEROUTE_SIMULATOR_FACTS'] = str(self.json_facts_dir)
        
        # Step 1: Load raw facts
        loader = RawFactsBlockLoader(verbose=1)
        routers = loader.load_raw_facts_directory(self.raw_facts_dir)
        self.assertEqual(len(routers), 10)
        
        # Step 2: Initialize setup
        setup = CompleteNetworkSetup(verbose=1)
        setup.load_facts()
        self.assertEqual(len(setup.routers), 10)
        
        # Step 3: Initialize status tool
        status_tool = NetworkNamespaceStatus(str(self.json_facts_dir), verbose=1)
        self.assertIsNotNone(status_tool)


def main():
    """Run the test suite."""
    # Check if running as root for namespace tests
    if os.geteuid() != 0:
        print("WARNING: Some tests require root privileges and will be skipped")
        print("Run with 'sudo python3 test_complete_setup_validation.py' for full test coverage")
    
    # Set up test environment
    os.environ.setdefault('TRACEROUTE_SIMULATOR_RAW_FACTS', 'tests/raw_facts')
    os.environ.setdefault('TRACEROUTE_SIMULATOR_FACTS', 'tests/tsim_facts')
    
    # Run tests
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()