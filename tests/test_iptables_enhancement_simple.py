#!/usr/bin/env python3
"""
Simple Test Suite for Enhanced Iptables Rules

This test suite validates the core functionality of enhanced iptables rules
with simple, reliable tests that work with the actual rule format.
"""

import unittest
import re
from pathlib import Path


class TestIptablesEnhancement(unittest.TestCase):
    """Simple tests for iptables rule enhancement."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        cls.test_dir = Path(__file__).parent
        cls.raw_facts_dir = cls.test_dir / "raw_facts"
        
        cls.router_files = {}
        for file_path in cls.raw_facts_dir.glob("*_facts.txt"):
            router_name = file_path.stem.replace("_facts", "")
            cls.router_files[router_name] = file_path
    
    def test_all_routers_have_icmp_rules(self):
        """Test that all routers have ICMP rules."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Check for ICMP ACCEPT rules (both table format and iptables-save format)
                icmp_accepts = len(re.findall(r'ACCEPT.*icmp|icmp.*-j ACCEPT', content))
                self.assertGreater(icmp_accepts, 5,
                                 f"{router_name}: Insufficient ICMP ACCEPT rules ({icmp_accepts})")
                
                # Check for ICMP logging
                icmp_logs = len(re.findall(r'INPUT-ICMP-', content))
                self.assertGreater(icmp_logs, 5,
                                 f"{router_name}: Insufficient ICMP LOG rules ({icmp_logs})")
    
    def test_all_routers_have_mtr_rules(self):
        """Test that all routers have MTR UDP rules."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Check for MTR port range
                mtr_rules = len(re.findall(r'33434:33534', content))
                self.assertGreater(mtr_rules, 5,
                                 f"{router_name}: Insufficient MTR rules ({mtr_rules})")
                
                # Check for MTR logging
                mtr_logs = len(re.findall(r'INPUT-MTR-UDP', content))
                self.assertGreater(mtr_logs, 2,
                                 f"{router_name}: Insufficient MTR LOG rules ({mtr_logs})")
    
    def test_all_routers_have_management_rules(self):
        """Test that all routers have management protocol rules."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Check for SSH (port 22)
                ssh_rules = len(re.findall(r'dpt:22|--dport 22', content))
                self.assertGreater(ssh_rules, 2,
                                 f"{router_name}: Insufficient SSH rules ({ssh_rules})")
                
                # Check for management logging
                mgmt_logs = len(re.findall(r'INPUT-MGMT-', content))
                self.assertGreater(mgmt_logs, 5,
                                 f"{router_name}: Insufficient management LOG rules ({mgmt_logs})")
    
    def test_all_routers_have_comprehensive_logging(self):
        """Test that all routers have comprehensive logging."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Check for drop logging
                drop_logs = len(re.findall(r'INPUT-DROP|FORWARD-DROP', content))
                self.assertGreaterEqual(drop_logs, 2,
                                      f"{router_name}: Missing drop logging ({drop_logs})")
                
                # Check for forward logging
                forward_logs = len(re.findall(r'FWD-ICMP-|FWD-MTR-', content))
                self.assertGreater(forward_logs, 10,
                                 f"{router_name}: Insufficient forward logging ({forward_logs})")
    
    def test_gateway_routers_have_nat_rules(self):
        """Test that gateway routers have NAT rules."""
        gateway_routers = ['hq-gw', 'br-gw', 'dc-gw']
        
        for router_name in gateway_routers:
            with self.subTest(router=router_name):
                file_path = self.router_files[router_name]
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Check for NAT table
                self.assertRegex(content, r'\*nat',
                               f"{router_name}: Missing NAT table")
                
                # Check for MASQUERADE
                masq_count = len(re.findall(r'MASQUERADE', content))
                self.assertGreater(masq_count, 0,
                                 f"{router_name}: No MASQUERADE rules ({masq_count})")
    
    def test_all_routers_have_basic_iptables_structure(self):
        """Test that all routers have basic iptables structure."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Check for filter table
                self.assertRegex(content, r'\*filter',
                               f"{router_name}: Missing filter table")
                
                # Check for INPUT/FORWARD/OUTPUT chains
                self.assertRegex(content, r':INPUT DROP',
                               f"{router_name}: Missing INPUT chain policy")
                self.assertRegex(content, r':FORWARD DROP',
                               f"{router_name}: Missing FORWARD chain policy")
                
                # Check for COMMIT
                commits = len(re.findall(r'COMMIT', content))
                self.assertGreaterEqual(commits, 1,
                                      f"{router_name}: Missing COMMIT statements ({commits})")
    
    def test_network_connectivity_coverage(self):
        """Test that rules cover major network segments."""
        networks_to_check = ['10.1.', '10.2.', '10.3.', '10.100.']
        
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Count network coverage
                covered_networks = 0
                for network in networks_to_check:
                    if network in content:
                        covered_networks += 1
                
                self.assertGreaterEqual(covered_networks, 3,
                                      f"{router_name}: Insufficient network coverage ({covered_networks}/4)")
    
    def test_total_rule_counts(self):
        """Test that routers have sufficient total rules."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                with open(file_path, 'r') as f:
                    content = f.read()
                
                # Count total ACCEPT rules (both formats)
                accept_rules = len(re.findall(r'ACCEPT|-j ACCEPT', content))
                self.assertGreater(accept_rules, 20,
                                 f"{router_name}: Insufficient ACCEPT rules ({accept_rules})")
                
                # Count total LOG rules
                log_rules = len(re.findall(r'LOG.*prefix', content))
                self.assertGreater(log_rules, 15,
                                 f"{router_name}: Insufficient LOG rules ({log_rules})")


def main():
    """Main test runner."""
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()