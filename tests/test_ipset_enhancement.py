#!/usr/bin/env python3
"""
Test suite for Task 1.3: Ipset Configurations Enhancement

This test suite validates that all raw facts files have been properly enhanced
with comprehensive ipset configurations covering all ipset types from the documentation.

Test Categories:
1. File Structure Tests - Verify ipset sections exist
2. Ipset Save Format Tests - Validate ipset save output format
3. Ipset List Format Tests - Validate ipset list output format  
4. Ipset Type Coverage Tests - Ensure all ipset types are represented
5. Router-Specific Tests - Verify router-appropriate ipset configurations
6. Content Quality Tests - Validate realistic and diverse ipset content
"""

import unittest
import os
import re
import json
from typing import Dict, List, Set, Tuple


class TestIpsetEnhancement(unittest.TestCase):
    """Test suite for ipset configurations enhancement validation."""

    def setUp(self):
        """Set up test environment."""
        self.raw_facts_dir = "tests/raw_facts"
        self.router_files = [
            "hq-gw_facts.txt", "hq-core_facts.txt", "hq-dmz_facts.txt", "hq-lab_facts.txt",
            "br-gw_facts.txt", "br-core_facts.txt", "br-wifi_facts.txt",
            "dc-gw_facts.txt", "dc-core_facts.txt", "dc-srv_facts.txt"
        ]
        
        # Expected ipset types from documentation
        self.expected_ipset_types = {
            'bitmap:ip', 'bitmap:ip,mac', 'bitmap:port',
            'hash:ip', 'hash:mac', 'hash:net', 'hash:ip,port',
            'hash:net,iface', 'hash:ip,port,ip', 'hash:ip,port,net'
        }
        
        # Router classifications for type-specific validation
        self.gateway_routers = ['hq-gw', 'br-gw', 'dc-gw']
        self.wifi_routers = ['br-wifi']
        self.dmz_routers = ['hq-dmz']
        self.server_routers = ['dc-srv']
        
    def _load_router_facts(self, router_file: str) -> str:
        """Load router facts file content."""
        file_path = os.path.join(self.raw_facts_dir, router_file)
        with open(file_path, 'r') as f:
            return f.read()
    
    def _extract_section(self, content: str, section_name: str) -> str:
        """Extract a specific section from facts content."""
        pattern = rf'=== TSIM_SECTION_START:{section_name} ===.*?=== TSIM_SECTION_END:{section_name} ==='
        match = re.search(pattern, content, re.DOTALL)
        return match.group(0) if match else ""
    
    def _extract_ipset_definitions(self, section_content: str) -> List[str]:
        """Extract individual ipset definitions from section content."""
        # Split by 'create' statements to get individual definitions
        definitions = []
        lines = section_content.split('\n')
        current_def = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('create '):
                if current_def:
                    definitions.append('\n'.join(current_def))
                current_def = [line]
            elif line and not line.startswith('=== ') and not line.startswith('TITLE:') and not line.startswith('COMMAND:') and not line.startswith('TIMESTAMP:') and not line.startswith('EXIT_CODE:') and line != '---':
                current_def.append(line)
        
        if current_def:
            definitions.append('\n'.join(current_def))
            
        return definitions

    def test_01_ipset_sections_exist(self):
        """Test that all router files have ipset sections."""
        for router_file in self.router_files:
            with self.subTest(router=router_file):
                content = self._load_router_facts(router_file)
                
                # Check for ipset_save section
                ipset_save_section = self._extract_section(content, 'ipset_save')
                self.assertTrue(ipset_save_section, 
                    f"Missing ipset_save section in {router_file}")
                
                # Check for ipset_list section  
                ipset_list_section = self._extract_section(content, 'ipset_list')
                self.assertTrue(ipset_list_section,
                    f"Missing ipset_list section in {router_file}")

    def test_02_ipset_save_format_validation(self):
        """Test that ipset_save sections have proper format."""
        for router_file in self.router_files:
            with self.subTest(router=router_file):
                content = self._load_router_facts(router_file)
                ipset_save_section = self._extract_section(content, 'ipset_save')
                
                # Should contain 'create' statements
                self.assertIn('create ', ipset_save_section,
                    f"No 'create' statements found in ipset_save section of {router_file}")
                
                # Should contain 'add' statements
                self.assertIn('add ', ipset_save_section,
                    f"No 'add' statements found in ipset_save section of {router_file}")
                
                # Check for proper command header
                self.assertIn('COMMAND: /sbin/ipset save', ipset_save_section,
                    f"Missing proper command header in ipset_save section of {router_file}")

    def test_03_ipset_list_format_validation(self):
        """Test that ipset_list sections have proper format."""
        for router_file in self.router_files:
            with self.subTest(router=router_file):
                content = self._load_router_facts(router_file)
                ipset_list_section = self._extract_section(content, 'ipset_list')
                
                # Should contain 'Name:' entries
                self.assertIn('Name: ', ipset_list_section,
                    f"No 'Name:' entries found in ipset_list section of {router_file}")
                
                # Should contain 'Type:' entries
                self.assertIn('Type: ', ipset_list_section,
                    f"No 'Type:' entries found in ipset_list section of {router_file}")
                
                # Should contain 'Members:' entries
                self.assertIn('Members:', ipset_list_section,
                    f"No 'Members:' entries found in ipset_list section of {router_file}")
                
                # Check for proper command header
                self.assertIn('COMMAND: /sbin/ipset list', ipset_list_section,
                    f"Missing proper command header in ipset_list section of {router_file}")

    def test_04_ipset_type_coverage(self):
        """Test that all expected ipset types are represented across routers."""
        all_types_found = set()
        
        for router_file in self.router_files:
            content = self._load_router_facts(router_file)
            ipset_save_section = self._extract_section(content, 'ipset_save')
            
            # Extract types from create statements
            create_pattern = r'create \S+ (bitmap:\S+|hash:\S+)'
            matches = re.findall(create_pattern, ipset_save_section)
            all_types_found.update(matches)
        
        # Check that we have good coverage of ipset types
        covered_types = all_types_found.intersection(self.expected_ipset_types)
        coverage_ratio = len(covered_types) / len(self.expected_ipset_types)
        
        self.assertGreaterEqual(coverage_ratio, 0.7,
            f"Insufficient ipset type coverage. Found: {covered_types}, Expected at least 70% of: {self.expected_ipset_types}")

    def test_05_bitmap_ip_validation(self):
        """Test bitmap:ip ipset configurations."""
        bitmap_ip_found = False
        
        for router_file in self.router_files:
            content = self._load_router_facts(router_file)
            ipset_save_section = self._extract_section(content, 'ipset_save')
            
            if 'bitmap:ip' in ipset_save_section:
                bitmap_ip_found = True
                
                # Check for proper range specification
                self.assertTrue(
                    re.search(r'create \S+ bitmap:ip range \d+\.\d+\.\d+\.\d+[-/]\d+', ipset_save_section),
                    f"bitmap:ip sets should have proper range specification in {router_file}"
                )
        
        self.assertTrue(bitmap_ip_found, "No bitmap:ip ipsets found across all routers")

    def test_06_hash_ip_port_validation(self):
        """Test hash:ip,port ipset configurations."""
        hash_ip_port_found = False
        
        for router_file in self.router_files:
            content = self._load_router_facts(router_file)
            ipset_save_section = self._extract_section(content, 'ipset_save')
            
            if 'hash:ip,port' in ipset_save_section:
                hash_ip_port_found = True
                
                # Check for IP,port format in add statements
                self.assertTrue(
                    re.search(r'add \S+ \d+\.\d+\.\d+\.\d+,\d+', ipset_save_section),
                    f"hash:ip,port sets should have IP,port format in add statements in {router_file}"
                )
        
        self.assertTrue(hash_ip_port_found, "No hash:ip,port ipsets found across all routers")

    def test_07_gateway_specific_ipsets(self):
        """Test that gateway routers have internet-related ipsets."""
        for router_file in self.router_files:
            router_name = router_file.replace('_facts.txt', '')
            
            if router_name in self.gateway_routers:
                with self.subTest(router=router_name):
                    content = self._load_router_facts(router_file)
                    ipset_save_section = self._extract_section(content, 'ipset_save')
                    
                    # Gateway routers should have external/internet-related sets
                    internet_indicators = ['external', 'internet', 'public', 'wan', 'cloud']
                    has_internet_sets = any(indicator in ipset_save_section.lower() 
                                          for indicator in internet_indicators)
                    
                    self.assertTrue(has_internet_sets,
                        f"Gateway router {router_name} should have internet-related ipsets")

    def test_08_wifi_router_ipsets(self):
        """Test that WiFi routers have wireless-specific ipsets."""
        for router_file in self.router_files:
            router_name = router_file.replace('_facts.txt', '')
            
            if router_name in self.wifi_routers:
                with self.subTest(router=router_name):
                    content = self._load_router_facts(router_file)
                    ipset_save_section = self._extract_section(content, 'ipset_save')
                    
                    # WiFi routers should have wireless-related sets
                    wifi_indicators = ['wifi', 'wireless', 'guest', 'client']
                    has_wifi_sets = any(indicator in ipset_save_section.lower() 
                                      for indicator in wifi_indicators)
                    
                    self.assertTrue(has_wifi_sets,
                        f"WiFi router {router_name} should have wireless-related ipsets")

    def test_09_ipset_consistency_between_formats(self):
        """Test consistency between ipset_save and ipset_list formats."""
        for router_file in self.router_files:
            with self.subTest(router=router_file):
                content = self._load_router_facts(router_file)
                ipset_save_section = self._extract_section(content, 'ipset_save')
                ipset_list_section = self._extract_section(content, 'ipset_list')
                
                # Extract set names from save format
                save_names = set(re.findall(r'create (\S+)', ipset_save_section))
                
                # Extract set names from list format
                list_names = set(re.findall(r'Name: (\S+)', ipset_list_section))
                
                # Should have some overlap (allowing for different formatting)
                if save_names and list_names:
                    # At least 50% of sets should be consistent between formats
                    common_names = save_names.intersection(list_names)
                    consistency_ratio = len(common_names) / max(len(save_names), len(list_names))
                    
                    self.assertGreaterEqual(consistency_ratio, 0.5,
                        f"Low consistency between ipset formats in {router_file}. "
                        f"Save names: {save_names}, List names: {list_names}")

    def test_10_ipset_member_diversity(self):
        """Test that ipsets have diverse and realistic member content."""
        for router_file in self.router_files:
            with self.subTest(router=router_file):
                content = self._load_router_facts(router_file)
                ipset_save_section = self._extract_section(content, 'ipset_save')
                
                # Count unique IP addresses in add statements
                ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
                ip_addresses = set(re.findall(ip_pattern, ipset_save_section))
                
                # Should have diverse IP addresses (at least 10 unique IPs)
                self.assertGreaterEqual(len(ip_addresses), 10,
                    f"Insufficient IP diversity in ipsets for {router_file}. Found {len(ip_addresses)} unique IPs")
                
                # Count port numbers
                port_pattern = r',(\d{1,5})\b'
                ports = set(re.findall(port_pattern, ipset_save_section))
                
                # Should have multiple port numbers if using hash:ip,port
                if 'hash:ip,port' in ipset_save_section:
                    self.assertGreaterEqual(len(ports), 5,
                        f"Insufficient port diversity in hash:ip,port sets for {router_file}")

    def test_11_section_exit_codes(self):
        """Test that ipset sections have proper exit codes."""
        for router_file in self.router_files:
            with self.subTest(router=router_file):
                content = self._load_router_facts(router_file)
                
                # Check ipset_save exit code
                ipset_save_section = self._extract_section(content, 'ipset_save')
                self.assertIn('EXIT_CODE: 0', ipset_save_section,
                    f"ipset_save section should have EXIT_CODE: 0 in {router_file}")
                
                # Check ipset_list exit code
                ipset_list_section = self._extract_section(content, 'ipset_list')
                self.assertIn('EXIT_CODE: 0', ipset_list_section,
                    f"ipset_list section should have EXIT_CODE: 0 in {router_file}")

    def test_12_ipset_quantity_validation(self):
        """Test that each router has a reasonable number of ipset definitions."""
        for router_file in self.router_files:
            with self.subTest(router=router_file):
                content = self._load_router_facts(router_file)
                ipset_save_section = self._extract_section(content, 'ipset_save')
                
                # Count create statements
                create_count = len(re.findall(r'create \S+', ipset_save_section))
                
                # Each router should have multiple ipsets (at least 5)
                self.assertGreaterEqual(create_count, 5,
                    f"Router {router_file} should have at least 5 ipset definitions, found {create_count}")
                
                # But not excessive (less than 200)
                self.assertLessEqual(create_count, 200,
                    f"Router {router_file} has excessive ipset definitions: {create_count}")


def main():
    """Run the test suite."""
    # Change to script directory for relative paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(os.path.dirname(script_dir))
    
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()