#!/usr/bin/env -S python3 -B -u
"""
Test Suite for Enhanced Iptables Rules - Final Version

This test suite validates that all raw fact files contain comprehensive
iptables rules that enable full connectivity for ping/mtr between all
routers and hosts, with proper logging configuration.

This version handles both individual table sections and iptables-save format.
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
        # Pattern to match the actual format
        pattern = rf'=== TSIM_SECTION_START:{section_name} ===.*?---\n(.*?)\n\nEXIT_CODE: 0\n=== TSIM_SECTION_END:{section_name} ==='
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1) if match else ""
    
    def get_iptables_rules(self, router_name: str) -> str:
        """Get iptables rules from either individual sections or iptables-save."""
        content = self.read_facts_file(router_name)
        
        # First try to get individual sections
        filter_section = self.extract_iptables_section(content, 'iptables_filter')
        nat_section = self.extract_iptables_section(content, 'iptables_nat')
        mangle_section = self.extract_iptables_section(content, 'iptables_mangle')
        
        # If individual sections exist, combine them
        if filter_section or nat_section or mangle_section:
            return filter_section + "\\n" + nat_section + "\\n" + mangle_section
        
        # Otherwise, use iptables-save section
        save_section = self.extract_iptables_section(content, 'iptables_save')
        return save_section
    
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
    
    def test_iptables_rules_exist(self):
        """Test that all routers have iptables rules."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                iptables_rules = self.get_iptables_rules(router_name)
                self.assertNotEqual(iptables_rules.strip(), "",
                                  f"{router_name}: No iptables rules found")
    
    def test_icmp_connectivity_rules(self):
        """Test that ICMP connectivity rules exist for all networks."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                iptables_rules = self.get_iptables_rules(router_name)
                
                if not iptables_rules.strip():
                    self.fail(f"{router_name}: No iptables rules found")
                
                # Check for ICMP ACCEPT rules
                icmp_rules = re.findall(r'ACCEPT.*icmp', iptables_rules)
                self.assertGreater(len(icmp_rules), 0,
                                 f"{router_name}: No ICMP ACCEPT rules found")
                
                # Check for ICMP logging rules
                icmp_log_rules = re.findall(r'LOG.*icmp.*INPUT-ICMP', iptables_rules)
                self.assertGreater(len(icmp_log_rules), 0,
                                 f"{router_name}: No ICMP LOG rules found")
                
                # Check that we have rules for multiple ICMP types
                icmp_types_found = set()
                for icmp_type in self.icmp_types:
                    if f'icmp-type {icmp_type}' in iptables_rules:
                        icmp_types_found.add(icmp_type)
                
                self.assertGreaterEqual(len(icmp_types_found), 3,
                                      f"{router_name}: Insufficient ICMP types covered (found {icmp_types_found})")
    
    def test_mtr_udp_rules(self):
        """Test that MTR UDP rules exist."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                iptables_rules = self.get_iptables_rules(router_name)
                
                if not iptables_rules.strip():
                    self.fail(f"{router_name}: No iptables rules found")
                
                # Check for MTR UDP rules (port range 33434:33534)
                mtr_rules = re.findall(r'ACCEPT.*udp.*33434:33534', iptables_rules)
                self.assertGreater(len(mtr_rules), 0,
                                 f"{router_name}: No MTR UDP ACCEPT rules found")
                
                # Check for MTR logging rules
                mtr_log_rules = re.findall(r'LOG.*udp.*33434:33534', iptables_rules)
                self.assertGreater(len(mtr_log_rules), 0,
                                 f"{router_name}: No MTR UDP LOG rules found")
    
    def test_management_protocol_rules(self):
        """Test that management protocol rules exist."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                iptables_rules = self.get_iptables_rules(router_name)
                
                if not iptables_rules.strip():
                    self.fail(f"{router_name}: No iptables rules found")
                
                # Check for SSH rules (port 22) - most important management protocol
                ssh_rules = re.findall(r'ACCEPT.*tcp.*dpt:22', iptables_rules)
                self.assertGreater(len(ssh_rules), 0,
                                 f"{router_name}: No SSH management rules found")
                
                # Check for management logging rules
                mgmt_log_rules = re.findall(r'LOG.*tcp.*(22|161|443)', iptables_rules)
                self.assertGreater(len(mgmt_log_rules), 0,
                                 f"{router_name}: No management protocol LOG rules found")
    
    def test_comprehensive_logging(self):
        """Test that comprehensive logging rules exist."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                iptables_rules = self.get_iptables_rules(router_name)
                
                if not iptables_rules.strip():
                    self.fail(f"{router_name}: No iptables rules found")
                
                # Check for INPUT drop logging
                input_drop_log = re.search(r'LOG.*INPUT-DROP', iptables_rules)
                self.assertIsNotNone(input_drop_log,
                                   f"{router_name}: Missing INPUT-DROP logging rule")
                
                # Check for FORWARD drop logging
                forward_drop_log = re.search(r'LOG.*FORWARD-DROP', iptables_rules)
                self.assertIsNotNone(forward_drop_log,
                                   f"{router_name}: Missing FORWARD-DROP logging rule")
                
                # Count total LOG rules
                total_log_rules = len(re.findall(r'-j LOG|target.*LOG', iptables_rules))
                self.assertGreater(total_log_rules, 10,
                                 f"{router_name}: Insufficient logging rules (found {total_log_rules})")
    
    def test_gateway_nat_rules(self):
        """Test that gateway routers have NAT rules."""
        
        gateway_routers = ['hq-gw', 'br-gw', 'dc-gw']
        
        for router_name in gateway_routers:
            with self.subTest(router=router_name):
                iptables_rules = self.get_iptables_rules(router_name)
                
                if not iptables_rules.strip():
                    self.fail(f"{router_name}: No iptables rules found")
                
                # Check for NAT table presence
                self.assertRegex(iptables_rules, r'\*nat',
                               f"{router_name}: Missing NAT table")
                
                # Check for MASQUERADE rules (for internet access)
                masq_rules = re.findall(r'MASQUERADE', iptables_rules)
                self.assertGreater(len(masq_rules), 0,
                                 f"{router_name}: No MASQUERADE rules found")
    
    def test_packet_marking_rules(self):
        """Test that packet marking rules exist."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                iptables_rules = self.get_iptables_rules(router_name)
                
                if not iptables_rules.strip():
                    self.fail(f"{router_name}: No iptables rules found")
                
                # Check for mangle table
                if '*mangle' in iptables_rules:
                    # Check for MARK rules
                    mark_rules = re.findall(r'MARK.*set.*0x1', iptables_rules)
                    self.assertGreater(len(mark_rules), 0,
                                     f"{router_name}: No packet MARK rules found in mangle table")
    
    def test_network_connectivity_matrix(self):
        """Test that rules support comprehensive network connectivity."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                iptables_rules = self.get_iptables_rules(router_name)
                
                if not iptables_rules.strip():
                    self.fail(f"{router_name}: No iptables rules found")
                
                # Count ICMP rules for different networks
                network_icmp_coverage = set()
                for network in self.all_networks:
                    network_base = network.split('/')[0].replace('.0', '')  # e.g., '10.1' from '10.1.0.0/16'
                    if network_base in iptables_rules:
                        network_icmp_coverage.add(network)
                
                self.assertGreaterEqual(len(network_icmp_coverage), 3,
                                      f"{router_name}: Insufficient network coverage (found {len(network_icmp_coverage)} networks)")
                
                # Count total connectivity rules (ICMP + UDP MTR + TCP management)
                icmp_count = len(re.findall(r'ACCEPT.*icmp', iptables_rules))
                udp_count = len(re.findall(r'ACCEPT.*udp.*33434:33534', iptables_rules))
                tcp_count = len(re.findall(r'ACCEPT.*tcp.*(22|161|443)', iptables_rules))
                
                total_connectivity = icmp_count + udp_count + tcp_count
                self.assertGreaterEqual(total_connectivity, 15,
                                      f"{router_name}: Insufficient total connectivity rules (found {total_connectivity})")
    
    def test_iptables_syntax_validation(self):
        """Test that iptables rules have valid syntax."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                iptables_save = self.extract_iptables_section(content, 'iptables_save')
                
                if not iptables_save.strip():
                    self.fail(f"{router_name}: No iptables_save section found")
                
                # Basic syntax validation
                self.assertRegex(iptables_save, r'\*filter',
                               f"{router_name}: Missing *filter table")
                
                # Check for proper chain policies
                self.assertRegex(iptables_save, r':INPUT DROP \[0:0\]',
                               f"{router_name}: Invalid INPUT chain policy")
                self.assertRegex(iptables_save, r':FORWARD DROP \[0:0\]',
                               f"{router_name}: Invalid FORWARD chain policy")
                
                # Check for COMMIT statements
                table_count = len(re.findall(r'\*\w+', iptables_save))
                commit_count = len(re.findall(r'COMMIT', iptables_save))
                self.assertEqual(table_count, commit_count,
                               f"{router_name}: Unbalanced table/commit count ({table_count} tables, {commit_count} commits)")
    
    def test_logging_prefix_coverage(self):
        """Test that logging prefixes provide good coverage."""
        
        for router_name in self.router_files:
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                
                # Extract all log prefixes
                log_prefixes = re.findall(r'--log-prefix "([^"]+)"', content)
                
                self.assertGreater(len(log_prefixes), 5,
                                 f"{router_name}: Insufficient logging rules (found {len(log_prefixes)})")
                
                # Check for key prefix patterns
                required_patterns = ['INPUT-ICMP', 'INPUT-DROP', 'FORWARD-DROP']
                found_patterns = set()
                
                for prefix in log_prefixes:
                    for pattern in required_patterns:
                        if pattern in prefix:
                            found_patterns.add(pattern)
                
                missing_patterns = set(required_patterns) - found_patterns
                self.assertEqual(len(missing_patterns), 0,
                               f"{router_name}: Missing required log patterns: {missing_patterns}")


class TestEnhancedRulesIntegration(unittest.TestCase):
    """Integration tests for enhanced iptables rules."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = Path(__file__).parent
        self.raw_facts_dir = self.test_dir / "raw_facts"
    
    def test_all_routers_enhanced(self):
        """Test that all routers have been enhanced."""
        
        enhanced_count = 0
        total_files = 0
        
        for file_path in self.raw_facts_dir.glob("*_facts.txt"):
            total_files += 1
            router_name = file_path.stem.replace("_facts", "")
            
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Check for enhanced rules indicators
            has_enhanced_icmp = 'INPUT-ICMP-' in content
            has_enhanced_mtr = 'INPUT-MTR-UDP' in content or '33434:33534' in content
            has_enhanced_logging = 'FORWARD-DROP' in content
            
            if has_enhanced_icmp and has_enhanced_mtr and has_enhanced_logging:
                enhanced_count += 1
        
        self.assertEqual(enhanced_count, total_files,
                        f"Only {enhanced_count}/{total_files} routers have been enhanced")
    
    def test_router_type_specific_rules(self):
        """Test that different router types have appropriate rules."""
        
        gateway_routers = ['hq-gw', 'br-gw', 'dc-gw']
        
        for file_path in self.raw_facts_dir.glob("*_facts.txt"):
            router_name = file_path.stem.replace("_facts", "")
            
            with open(file_path, 'r') as f:
                content = f.read()
            
            if router_name in gateway_routers:
                # Gateway routers should have MASQUERADE rules
                self.assertRegex(content, r'MASQUERADE',
                               f"{router_name}: Gateway router missing MASQUERADE rules")
                
                # Gateway routers should have NAT table
                self.assertRegex(content, r'\*nat',
                               f"{router_name}: Gateway router missing NAT table")


def main():
    """Main test runner."""
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()