#!/usr/bin/env python3
"""
Test Suite for Enhanced Iptables Rules

This test suite validates that all raw fact files contain comprehensive
iptables rules that enable full connectivity for ping/mtr between all
routers and hosts, with proper logging configuration.
"""

import unittest
import re
import os
from pathlib import Path
from typing import Dict, List, Set


class TestEnhancedIptablesRules(unittest.TestCase):
    """Test enhanced iptables rules in raw facts files."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        cls.test_dir = Path(__file__).parent
        cls.raw_facts_dir = cls.test_dir / "raw_facts"
        cls.all_networks = [
            '10.1.0.0/16',   # HQ networks
            '10.2.0.0/16',   # Branch networks  
            '10.3.0.0/16',   # DC networks
            '10.100.1.0/24'  # VPN network
        ]
        cls.management_ports = ['22', '161', '443', '8080', '514']
        cls.icmp_types = ['0', '3', '8', '11']
        
        cls.router_files = {}
        for file_path in cls.raw_facts_dir.glob("*_facts.txt"):
            router_name = file_path.stem.replace("_facts", "")
            cls.router_files[router_name] = file_path
    
    def read_facts_file(self, router_name: str) -> str:
        """Read a raw facts file."""
        file_path = self.router_files[router_name]
        with open(file_path, 'r') as f:
            return f.read()
    
    def extract_iptables_section(self, content: str, section_name: str) -> str:
        """Extract a specific iptables section from raw facts."""
        pattern = rf'=== TSIM_SECTION_START:{section_name} ===.*?=== TSIM_SECTION_END:{section_name} ==='
        match = re.search(pattern, content, re.DOTALL)
        return match.group(0) if match else ""
    
    def test_all_files_exist(self):
        """Test that all expected raw facts files exist."""
        expected_routers = [
            'hq-gw', 'hq-core', 'hq-dmz', 'hq-lab',
            'br-gw', 'br-core', 'br-wifi',
            'dc-gw', 'dc-core', 'dc-srv'
        ]
        
        for router in expected_routers:
            self.assertIn(router, self.router_files, 
                         f"Raw facts file missing for {router}")
    
    def test_filter_table_icmp_rules(self):
        """Test that filter table contains ICMP rules for all networks."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                filter_section = self.extract_iptables_section(content, 'iptables_filter')
                
                # Check INPUT ICMP rules
                for network in self.all_networks:
                    for icmp_type in self.icmp_types:
                        # Check for LOG rule
                        log_pattern = rf'LOG.*icmp.*{re.escape(network)}.*icmp-type {icmp_type}.*INPUT-ICMP-{icmp_type}'
                        self.assertRegex(filter_section, log_pattern,
                                       f"{router_name}: Missing INPUT ICMP LOG rule for {network} type {icmp_type}")
                        
                        # Check for ACCEPT rule
                        accept_pattern = rf'ACCEPT.*icmp.*{re.escape(network)}.*icmp-type {icmp_type}'
                        self.assertRegex(filter_section, accept_pattern,
                                       f"{router_name}: Missing INPUT ICMP ACCEPT rule for {network} type {icmp_type}")
    
    def test_filter_table_forward_rules(self):
        """Test that filter table contains FORWARD rules between networks."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                filter_section = self.extract_iptables_section(content, 'iptables_filter')
                
                # Check FORWARD ICMP rules between different networks
                for src_net in self.all_networks:
                    for dst_net in self.all_networks:
                        if src_net != dst_net:
                            # Check for LOG rule
                            log_pattern = rf'LOG.*icmp.*{re.escape(src_net)}.*{re.escape(dst_net)}.*FWD-ICMP'
                            self.assertRegex(filter_section, log_pattern,
                                           f"{router_name}: Missing FORWARD ICMP LOG rule from {src_net} to {dst_net}")
                            
                            # Check for ACCEPT rule
                            accept_pattern = rf'ACCEPT.*icmp.*{re.escape(src_net)}.*{re.escape(dst_net)}'
                            self.assertRegex(filter_section, accept_pattern,
                                           f"{router_name}: Missing FORWARD ICMP ACCEPT rule from {src_net} to {dst_net}")
    
    def test_filter_table_mtr_rules(self):
        """Test that filter table contains MTR UDP rules."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                filter_section = self.extract_iptables_section(content, 'iptables_filter')
                
                # Check INPUT MTR rules
                for network in self.all_networks:
                    # Check for LOG rule
                    log_pattern = rf'LOG.*udp.*{re.escape(network)}.*33434:33534.*INPUT-MTR-UDP'
                    self.assertRegex(filter_section, log_pattern,
                                   f"{router_name}: Missing INPUT MTR LOG rule for {network}")
                    
                    # Check for ACCEPT rule
                    accept_pattern = rf'ACCEPT.*udp.*{re.escape(network)}.*33434:33534'
                    self.assertRegex(filter_section, accept_pattern,
                                   f"{router_name}: Missing INPUT MTR ACCEPT rule for {network}")
                
                # Check FORWARD MTR rules between different networks
                for src_net in self.all_networks:
                    for dst_net in self.all_networks:
                        if src_net != dst_net:
                            # Check for LOG rule
                            log_pattern = rf'LOG.*udp.*{re.escape(src_net)}.*{re.escape(dst_net)}.*33434:33534.*FWD-MTR'
                            self.assertRegex(filter_section, log_pattern,
                                           f"{router_name}: Missing FORWARD MTR LOG rule from {src_net} to {dst_net}")
                            
                            # Check for ACCEPT rule
                            accept_pattern = rf'ACCEPT.*udp.*{re.escape(src_net)}.*{re.escape(dst_net)}.*33434:33534'
                            self.assertRegex(filter_section, accept_pattern,
                                           f"{router_name}: Missing FORWARD MTR ACCEPT rule from {src_net} to {dst_net}")
    
    def test_filter_table_management_rules(self):
        """Test that filter table contains management protocol rules."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                filter_section = self.extract_iptables_section(content, 'iptables_filter')
                
                # Check INPUT management rules
                for network in self.all_networks:
                    for port in self.management_ports:
                        # Check for LOG rule
                        log_pattern = rf'LOG.*tcp.*{re.escape(network)}.*tcp dpt:{port}.*INPUT-MGMT-{port}'
                        self.assertRegex(filter_section, log_pattern,
                                       f"{router_name}: Missing INPUT MGMT LOG rule for {network} port {port}")
                        
                        # Check for ACCEPT rule
                        accept_pattern = rf'ACCEPT.*tcp.*{re.escape(network)}.*tcp dpt:{port}'
                        self.assertRegex(filter_section, accept_pattern,
                                       f"{router_name}: Missing INPUT MGMT ACCEPT rule for {network} port {port}")
    
    def test_filter_table_logging_rules(self):
        """Test that filter table contains comprehensive logging rules."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                filter_section = self.extract_iptables_section(content, 'iptables_filter')
                
                # Check for INPUT-DROP logging
                self.assertRegex(filter_section, r'LOG.*INPUT-DROP',
                               f"{router_name}: Missing INPUT-DROP logging rule")
                
                # Check for FORWARD-DROP logging
                self.assertRegex(filter_section, r'LOG.*FORWARD-DROP',
                               f"{router_name}: Missing FORWARD-DROP logging rule")
    
    def test_nat_table_gateway_rules(self):
        """Test that gateway routers have proper NAT rules."""
        
        gateway_routers = ['hq-gw', 'br-gw', 'dc-gw']
        
        for router_name in gateway_routers:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                nat_section = self.extract_iptables_section(content, 'iptables_nat')
                
                # Check for DNAT rules
                self.assertRegex(nat_section, r'DNAT.*tcp.*dpt:80',
                               f"{router_name}: Missing DNAT rule for HTTP")
                
                # Check for MASQUERADE rules
                for network in ['10.1.0.0/16', '10.2.0.0/16', '10.3.0.0/16']:
                    masq_pattern = rf'MASQUERADE.*{re.escape(network)}'
                    self.assertRegex(nat_section, masq_pattern,
                                   f"{router_name}: Missing MASQUERADE rule for {network}")
    
    def test_mangle_table_marking_rules(self):
        """Test that mangle table contains packet marking rules."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                mangle_section = self.extract_iptables_section(content, 'iptables_mangle')
                
                # Check for ICMP marking
                self.assertRegex(mangle_section, r'MARK.*icmp.*MARK set 0x1',
                               f"{router_name}: Missing ICMP MARK rule")
                
                # Check for management port marking
                for port in ['22', '161', '443']:
                    mark_pattern = rf'MARK.*tcp.*dpt:{port}.*MARK set 0x1'
                    self.assertRegex(mangle_section, mark_pattern,
                                   f"{router_name}: Missing MARK rule for port {port}")
    
    def test_iptables_save_format(self):
        """Test that iptables-save section is properly formatted."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                save_section = self.extract_iptables_section(content, 'iptables_save')
                
                # Check for proper table headers
                self.assertRegex(save_section, r'\*filter',
                               f"{router_name}: Missing *filter table in iptables-save")
                self.assertRegex(save_section, r'\*nat',
                               f"{router_name}: Missing *nat table in iptables-save")
                self.assertRegex(save_section, r'\*mangle',
                               f"{router_name}: Missing *mangle table in iptables-save")
                
                # Check for COMMIT statements
                commit_count = len(re.findall(r'COMMIT', save_section))
                self.assertEqual(commit_count, 3,
                               f"{router_name}: Expected 3 COMMIT statements, found {commit_count}")
    
    def test_logging_prefixes_unique(self):
        """Test that logging prefixes are unique and identifiable."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                
                # Extract all log prefixes
                log_prefixes = re.findall(r'--log-prefix "([^"]+)"', content)
                
                # Check that we have logging rules
                self.assertGreater(len(log_prefixes), 0,
                                 f"{router_name}: No logging rules found")
                
                # Check for specific prefix patterns
                expected_patterns = [
                    'INPUT-ICMP-', 'INPUT-MGMT-', 'INPUT-MTR-', 'INPUT-DROP',
                    'FWD-ICMP-', 'FWD-MTR-', 'FORWARD-DROP',
                    'NAT-DNAT-', 'NAT-MASQ-',
                    'MANGLE-MARK-'
                ]
                
                for pattern in expected_patterns:
                    pattern_found = any(pattern in prefix for prefix in log_prefixes)
                    if pattern in ['NAT-DNAT-', 'NAT-MASQ-'] and router_name not in ['hq-gw', 'br-gw', 'dc-gw']:
                        continue  # Skip NAT patterns for non-gateway routers
                    
                    self.assertTrue(pattern_found,
                                  f"{router_name}: Missing log prefix pattern '{pattern}'")
    
    def test_connectivity_matrix(self):
        """Test that rules support full connectivity matrix."""
        
        test_networks = [
            '10.1.1.0/24', '10.1.2.0/24', '10.1.10.0/24',  # HQ
            '10.2.1.0/24', '10.2.2.0/24', '10.2.10.0/24',  # Branch
            '10.3.1.0/24', '10.3.2.0/24', '10.3.20.0/24',  # DC
            '10.100.1.0/24'  # VPN
        ]
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                filter_section = self.extract_iptables_section(content, 'iptables_filter')
                save_section = self.extract_iptables_section(content, 'iptables_save')
                
                # Count ICMP ACCEPT rules in both sections
                icmp_accept_count = len(re.findall(r'ACCEPT.*icmp', filter_section + save_section))
                
                # Should have rules for INPUT + FORWARD between different networks
                # INPUT: 4 networks * 4 ICMP types = 16 rules
                # FORWARD: 4 networks * 3 other networks = 12 network pairs (for major networks)
                expected_minimum = 16  # At least INPUT rules
                
                self.assertGreaterEqual(icmp_accept_count, expected_minimum,
                                      f"{router_name}: Insufficient ICMP ACCEPT rules (found {icmp_accept_count}, expected >= {expected_minimum})")


class TestIptablesRuleValidation(unittest.TestCase):
    """Test iptables rule syntax validation."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = Path(__file__).parent
        self.raw_facts_dir = self.test_dir / "raw_facts"
    
    def test_iptables_syntax_validation(self):
        """Test that iptables rules have valid syntax."""
        
        for file_path in self.raw_facts_dir.glob("*_facts.txt"):
            router_name = file_path.stem.replace("_facts", "")
            
            with self.subTest(router=router_name):
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Extract iptables-save section for syntax validation
                save_match = re.search(
                    r'=== TSIM_SECTION_START:iptables_save ===.*?---\\n(.*?)\\nEXIT_CODE',
                    content, re.DOTALL
                )
                
                if save_match:
                    save_content = save_match.group(1).replace('\\n', '\n')
                    
                    # Basic syntax checks
                    self.assertRegex(save_content, r'\*filter',
                                   f"{router_name}: Invalid filter table syntax")
                    self.assertRegex(save_content, r':INPUT DROP \[0:0\]',
                                   f"{router_name}: Invalid INPUT chain policy")
                    self.assertRegex(save_content, r':FORWARD DROP \[0:0\]',
                                   f"{router_name}: Invalid FORWARD chain policy")
                    
                    # Check for balanced table declarations and commits
                    table_count = len(re.findall(r'\*\w+', save_content))
                    commit_count = len(re.findall(r'COMMIT', save_content))
                    self.assertEqual(table_count, commit_count,
                                   f"{router_name}: Unbalanced table/commit count")


def main():
    """Main test runner."""
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()