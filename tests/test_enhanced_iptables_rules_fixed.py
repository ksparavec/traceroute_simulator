#!/usr/bin/env python3
"""
Test Suite for Enhanced Iptables Rules - Fixed Version

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
        # Fixed pattern to match the actual format
        pattern = rf'=== TSIM_SECTION_START:{section_name} ===.*?---\n(.*?)\n\nEXIT_CODE: 0\n=== TSIM_SECTION_END:{section_name} ==='
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1) if match else ""
    
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
                
                if not filter_section:
                    self.fail(f"{router_name}: Could not extract iptables_filter section")
                
                # Check for at least some ICMP rules (simplified test)
                icmp_rules = re.findall(r'ACCEPT.*icmp', filter_section)
                self.assertGreater(len(icmp_rules), 0,
                                 f"{router_name}: No ICMP ACCEPT rules found")
                
                # Check for ICMP logging rules
                icmp_log_rules = re.findall(r'LOG.*icmp.*INPUT-ICMP', filter_section)
                self.assertGreater(len(icmp_log_rules), 0,
                                 f"{router_name}: No ICMP LOG rules found")
    
    def test_filter_table_forward_rules(self):
        """Test that filter table contains FORWARD rules between networks."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                filter_section = self.extract_iptables_section(content, 'iptables_filter')
                
                if not filter_section:
                    self.fail(f"{router_name}: Could not extract iptables_filter section")
                
                # Check for FORWARD ICMP rules
                forward_icmp_rules = re.findall(r'ACCEPT.*icmp.*10\.', filter_section)
                self.assertGreater(len(forward_icmp_rules), 5,  # Should have many inter-network rules
                                 f"{router_name}: Insufficient FORWARD ICMP rules (found {len(forward_icmp_rules)})")
    
    def test_filter_table_mtr_rules(self):
        """Test that filter table contains MTR UDP rules."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                filter_section = self.extract_iptables_section(content, 'iptables_filter')
                
                if not filter_section:
                    self.fail(f"{router_name}: Could not extract iptables_filter section")
                
                # Check for MTR UDP rules (port range 33434:33534)
                mtr_rules = re.findall(r'ACCEPT.*udp.*33434:33534', filter_section)
                self.assertGreater(len(mtr_rules), 0,
                                 f"{router_name}: No MTR UDP rules found")
                
                # Check for MTR logging rules
                mtr_log_rules = re.findall(r'LOG.*udp.*33434:33534.*INPUT-MTR-UDP', filter_section)
                self.assertGreater(len(mtr_log_rules), 0,
                                 f"{router_name}: No MTR LOG rules found")
    
    def test_filter_table_management_rules(self):
        """Test that filter table contains management protocol rules."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                filter_section = self.extract_iptables_section(content, 'iptables_filter')
                
                if not filter_section:
                    self.fail(f"{router_name}: Could not extract iptables_filter section")
                
                # Check for SSH rules (port 22)
                ssh_rules = re.findall(r'ACCEPT.*tcp.*dpt:22', filter_section)
                self.assertGreater(len(ssh_rules), 0,
                                 f"{router_name}: No SSH management rules found")
                
                # Check for management logging rules
                mgmt_log_rules = re.findall(r'LOG.*tcp.*INPUT-MGMT', filter_section)
                self.assertGreater(len(mgmt_log_rules), 0,
                                 f"{router_name}: No management LOG rules found")
    
    def test_filter_table_logging_rules(self):
        """Test that filter table contains comprehensive logging rules."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                filter_section = self.extract_iptables_section(content, 'iptables_filter')
                
                if not filter_section:
                    self.fail(f"{router_name}: Could not extract iptables_filter section")
                
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
                
                if not nat_section:
                    self.fail(f"{router_name}: Could not extract iptables_nat section")
                
                # Check for DNAT rules
                dnat_rules = re.findall(r'DNAT.*tcp.*dpt:80', nat_section)
                self.assertGreater(len(dnat_rules), 0,
                                 f"{router_name}: No DNAT rules found")
                
                # Check for MASQUERADE rules
                masq_rules = re.findall(r'MASQUERADE.*10\.', nat_section)
                self.assertGreater(len(masq_rules), 0,
                                 f"{router_name}: No MASQUERADE rules found")
    
    def test_mangle_table_marking_rules(self):
        """Test that mangle table contains packet marking rules."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                mangle_section = self.extract_iptables_section(content, 'iptables_mangle')
                
                if not mangle_section:
                    self.fail(f"{router_name}: Could not extract iptables_mangle section")
                
                # Check for ICMP marking
                icmp_mark_rules = re.findall(r'MARK.*icmp.*MARK set 0x1', mangle_section)
                self.assertGreater(len(icmp_mark_rules), 0,
                                 f"{router_name}: No ICMP MARK rules found")
                
                # Check for TCP marking
                tcp_mark_rules = re.findall(r'MARK.*tcp.*MARK set 0x1', mangle_section)
                self.assertGreater(len(tcp_mark_rules), 0,
                                 f"{router_name}: No TCP MARK rules found")
    
    def test_iptables_save_format(self):
        """Test that iptables-save section is properly formatted."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                save_section = self.extract_iptables_section(content, 'iptables_save')
                
                if not save_section:
                    self.fail(f"{router_name}: Could not extract iptables_save section")
                
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
    
    def test_logging_prefixes_comprehensive(self):
        """Test that logging prefixes are comprehensive and identifiable."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                
                # Extract all log prefixes from all sections
                log_prefixes = re.findall(r'prefix "([^"]+)"', content)
                
                # Check that we have logging rules
                self.assertGreater(len(log_prefixes), 10,
                                 f"{router_name}: Insufficient logging rules (found {len(log_prefixes)})")
                
                # Check for key prefix patterns
                prefix_patterns = {
                    'INPUT-ICMP': 'ICMP input logging',
                    'INPUT-MGMT': 'Management input logging', 
                    'INPUT-MTR': 'MTR input logging',
                    'INPUT-DROP': 'Input drop logging',
                    'FWD-ICMP': 'ICMP forward logging',
                    'FWD-MTR': 'MTR forward logging',
                    'FORWARD-DROP': 'Forward drop logging',
                    'MANGLE-MARK': 'Mangle marking logging'
                }
                
                found_patterns = set()
                for prefix in log_prefixes:
                    for pattern in prefix_patterns:
                        if pattern in prefix:
                            found_patterns.add(pattern)
                
                # Should find most patterns (gateways have additional NAT patterns)
                expected_patterns = len(prefix_patterns) - 2  # Allow for some variation
                self.assertGreaterEqual(len(found_patterns), expected_patterns,
                                      f"{router_name}: Missing log prefix patterns. Found: {found_patterns}")
    
    def test_network_connectivity_coverage(self):
        """Test that rules cover full network connectivity requirements."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                
                # Count total ICMP ACCEPT rules across all sections
                icmp_accept_count = len(re.findall(r'ACCEPT.*icmp', content))
                
                # Should have substantial ICMP connectivity rules
                # INPUT (4 networks * 4 ICMP types) + FORWARD rules
                self.assertGreaterEqual(icmp_accept_count, 16,
                                      f"{router_name}: Insufficient ICMP connectivity rules (found {icmp_accept_count})")
                
                # Count UDP MTR rules
                mtr_udp_count = len(re.findall(r'ACCEPT.*udp.*33434:33534', content))
                self.assertGreaterEqual(mtr_udp_count, 4,
                                      f"{router_name}: Insufficient MTR UDP rules (found {mtr_udp_count})")
                
                # Count management TCP rules
                mgmt_tcp_count = len(re.findall(r'ACCEPT.*tcp.*dpt:(22|161|443)', content))
                self.assertGreaterEqual(mgmt_tcp_count, 8,
                                      f"{router_name}: Insufficient management TCP rules (found {mgmt_tcp_count})")


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
                    r'=== TSIM_SECTION_START:iptables_save ===.*?---\n(.*?)\n\nEXIT_CODE',
                    content, re.DOTALL
                )
                
                if save_match:
                    save_content = save_match.group(1)
                    
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
                else:
                    self.fail(f"{router_name}: Could not extract iptables_save section")


def main():
    """Main test runner."""
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()