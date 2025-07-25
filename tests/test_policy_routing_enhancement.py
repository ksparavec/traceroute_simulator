#!/usr/bin/env -S python3 -B -u
"""
Test Suite for Enhanced Policy Routing

This test suite validates that all raw fact files contain comprehensive
policy routing rules and additional routing tables for advanced
enterprise network scenarios.
"""

import unittest
import re
from pathlib import Path
from typing import Dict, List, Set


class TestPolicyRoutingEnhancement(unittest.TestCase):
    """Test enhanced policy routing in raw facts files."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        cls.test_dir = Path(__file__).parent
        cls.raw_facts_dir = cls.test_dir / "raw_facts"
        
        cls.router_files = {}
        for file_path in cls.raw_facts_dir.glob("*_facts.txt"):
            router_name = file_path.stem.replace("_facts", "")
            cls.router_files[router_name] = file_path
        
        # Expected routing tables
        cls.expected_tables = [
            'priority_table',
            'service_table', 
            'backup_table',
            'qos_table',
            'management_table',
            'database_table',
            'web_table',
            'emergency_table'
        ]
        
        # Expected policy rule types
        cls.expected_policy_types = [
            'from',      # Source-based
            'to',        # Destination-based  
            'dport',     # Destination port
            'sport',     # Source port
            'fwmark',    # Firewall mark
            'tos',       # Type of service
            'ipproto',   # IP protocol
        ]
    
    def read_facts_file(self, router_name: str) -> str:
        """Read a raw facts file."""
        file_path = self.router_files[router_name]
        with open(file_path, 'r') as f:
            return f.read()
    
    def extract_policy_rules_section(self, content: str) -> str:
        """Extract the policy rules section from raw facts."""
        pattern = r'=== TSIM_SECTION_START:policy_rules ===.*?---\n(.*?)\n\nEXIT_CODE: 0\n=== TSIM_SECTION_END:policy_rules ==='
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1) if match else ""
    
    def extract_routing_table_sections(self, content: str) -> Dict[str, str]:
        """Extract all routing table sections from raw facts."""
        tables = {}
        
        # Find all routing table sections
        pattern = r'=== TSIM_SECTION_START:routing_table_(\w+) ===.*?---\n(.*?)\n\nEXIT_CODE: 0\n=== TSIM_SECTION_END:routing_table_\w+ ==='
        matches = re.findall(pattern, content, re.DOTALL)
        
        for table_name, table_content in matches:
            tables[table_name] = table_content
            
        return tables
    
    def test_all_routers_have_policy_rules(self):
        """Test that all routers have enhanced policy rules."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                policy_section = self.extract_policy_rules_section(content)
                
                self.assertNotEqual(policy_section.strip(), "",
                                  f"{router_name}: No policy rules section found")
                
                # Count policy rules (exclude local, main, default)
                policy_lines = policy_section.strip().split('\n')
                policy_rules = [line for line in policy_lines 
                               if not line.strip().startswith(('0:', '32766:', '32767:'))]
                
                self.assertGreater(len(policy_rules), 15,
                                 f"{router_name}: Insufficient policy rules ({len(policy_rules)}, expected >15)")
    
    def test_source_based_policy_rules(self):
        """Test that all routers have source-based policy rules."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                policy_section = self.extract_policy_rules_section(content)
                
                # Check for source-based rules (from X.X.X.X)
                source_rules = re.findall(r'\d+:\s+from\s+\d+\.\d+\.\d+\.\d+', policy_section)
                self.assertGreater(len(source_rules), 3,
                                 f"{router_name}: Insufficient source-based rules ({len(source_rules)})")
    
    def test_service_based_policy_rules(self):
        """Test that all routers have service-based policy rules."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                policy_section = self.extract_policy_rules_section(content)
                
                # Check for port-based rules
                dport_rules = re.findall(r'\d+:\s+dport\s+\d+', policy_section)
                sport_rules = re.findall(r'\d+:\s+sport\s+\d+', policy_section)
                
                total_port_rules = len(dport_rules) + len(sport_rules)
                self.assertGreater(total_port_rules, 5,
                                 f"{router_name}: Insufficient service-based rules ({total_port_rules})")
                
                # Check for specific critical services
                ssh_rules = re.findall(r'dport 22 lookup', policy_section)
                self.assertGreater(len(ssh_rules), 0,
                                 f"{router_name}: Missing SSH policy rules")
                
                http_rules = re.findall(r'dport (80|443) lookup', policy_section)
                self.assertGreater(len(http_rules), 0,
                                 f"{router_name}: Missing HTTP/HTTPS policy rules")
    
    def test_qos_based_policy_rules(self):
        """Test that all routers have QoS-based policy rules."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                policy_section = self.extract_policy_rules_section(content)
                
                # Check for firewall mark rules
                fwmark_rules = re.findall(r'\d+:\s+fwmark\s+0x\d+', policy_section)
                self.assertGreater(len(fwmark_rules), 2,
                                 f"{router_name}: Insufficient firewall mark rules ({len(fwmark_rules)})")
                
                # Check for TOS rules
                tos_rules = re.findall(r'\d+:\s+tos\s+0x\d+', policy_section)
                self.assertGreater(len(tos_rules), 1,
                                 f"{router_name}: Insufficient TOS rules ({len(tos_rules)})")
    
    def test_protocol_based_policy_rules(self):
        """Test that all routers have protocol-based policy rules."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                policy_section = self.extract_policy_rules_section(content)
                
                # Check for IP protocol rules
                icmp_rules = re.findall(r'ipproto icmp lookup', policy_section)
                self.assertGreater(len(icmp_rules), 0,
                                 f"{router_name}: Missing ICMP protocol rules")
                
                udp_rules = re.findall(r'ipproto udp lookup', policy_section)
                self.assertGreater(len(udp_rules), 0,
                                 f"{router_name}: Missing UDP protocol rules")
    
    def test_additional_routing_tables_exist(self):
        """Test that all routers have additional routing tables."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                routing_tables = self.extract_routing_table_sections(content)
                
                # Should have most of the expected tables
                found_tables = set(routing_tables.keys())
                expected_tables = set(self.expected_tables)
                
                # Require at least 6 out of 8 tables
                intersection = found_tables.intersection(expected_tables)
                self.assertGreaterEqual(len(intersection), 6,
                                      f"{router_name}: Insufficient routing tables ({len(intersection)}/8). Found: {found_tables}")
    
    def test_routing_table_content_quality(self):
        """Test that routing tables contain meaningful content."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                routing_tables = self.extract_routing_table_sections(content)
                
                # Check that tables have routes
                tables_with_routes = 0
                for table_name, table_content in routing_tables.items():
                    # Count routes (lines that look like routes)
                    routes = re.findall(r'\d+\.\d+\.\d+\.\d+[/\w\s]+', table_content)
                    if len(routes) > 0:
                        tables_with_routes += 1
                
                self.assertGreater(tables_with_routes, 4,
                                 f"{router_name}: Too few tables with actual routes ({tables_with_routes})")
    
    def test_specific_table_purposes(self):
        """Test that specific tables serve their intended purposes."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                routing_tables = self.extract_routing_table_sections(content)
                
                # Priority table should exist and have priority routes
                if 'priority_table' in routing_tables:
                    priority_content = routing_tables['priority_table']
                    priority_routes = re.findall(r'metric [1-9]\b', priority_content)
                    self.assertGreater(len(priority_routes), 0,
                                     f"{router_name}: Priority table missing low-metric routes")
                
                # Backup table should have higher metrics
                if 'backup_table' in routing_tables:
                    backup_content = routing_tables['backup_table']
                    backup_routes = re.findall(r'metric [12]\d+', backup_content)
                    self.assertGreater(len(backup_routes), 0,
                                     f"{router_name}: Backup table missing high-metric routes")
    
    def test_gateway_specific_features(self):
        """Test that gateway routers have specific policy features."""
        gateway_routers = ['hq-gw', 'br-gw', 'dc-gw']
        
        for router_name in gateway_routers:
            if router_name in self.router_files:
                with self.subTest(router=router_name):
                    content = self.read_facts_file(router_name)
                    policy_section = self.extract_policy_rules_section(content)
                    
                    # Gateway routers should have internet routing policies
                    internet_rules = re.findall(r'to 0\.0\.0\.0/0 lookup', policy_section)
                    self.assertGreater(len(internet_rules), 0,
                                     f"{router_name}: Gateway missing internet routing policies")
                    
                    # Should have VPN-related policies
                    vpn_rules = re.findall(r'10\.100\.1\.0/24', policy_section)
                    self.assertGreater(len(vpn_rules), 0,
                                     f"{router_name}: Gateway missing VPN policies")
    
    def test_policy_rule_priorities(self):
        """Test that policy rules have appropriate priorities."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                policy_section = self.extract_policy_rules_section(content)
                
                # Extract all rule priorities
                priorities = re.findall(r'^(\d+):', policy_section, re.MULTILINE)
                priorities = [int(p) for p in priorities if int(p) not in [0, 32766, 32767]]
                
                # Should have rules in priority range
                self.assertGreater(len(priorities), 10,
                                 f"{router_name}: Insufficient priority rules ({len(priorities)})")
                
                # Should have high priority rules (< 100)
                high_priority = [p for p in priorities if p < 100]
                self.assertGreater(len(high_priority), 5,
                                 f"{router_name}: Insufficient high-priority rules ({len(high_priority)})")
    
    def test_cross_location_policies(self):
        """Test that routers have cross-location routing policies."""
        location_networks = {
            'hq': '10.1.0.0/16',
            'branch': '10.2.0.0/16', 
            'datacenter': '10.3.0.0/16'
        }
        
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                policy_section = self.extract_policy_rules_section(content)
                
                # Count cross-location rules
                cross_location_rules = 0
                for network in location_networks.values():
                    if f'to {network}' in policy_section:
                        cross_location_rules += 1
                
                self.assertGreater(cross_location_rules, 0,
                                 f"{router_name}: Missing cross-location routing policies")
    
    def test_emergency_and_management_policies(self):
        """Test that routers have emergency and management policies."""
        for router_name, file_path in self.router_files.items():
            with self.subTest(router=router_name):
                content = self.read_facts_file(router_name)
                policy_section = self.extract_policy_rules_section(content)
                
                # Emergency network rules
                emergency_rules = re.findall(r'from 192\.168\.1\.0/24', policy_section)
                self.assertGreater(len(emergency_rules), 0,
                                 f"{router_name}: Missing emergency network policies")
                
                # Management table usage (optional for some router types)
                mgmt_rules = re.findall(r'lookup management_table', policy_section)
                # Only require management policies for specific router types
                if router_name in ['hq-gw', 'hq-core', 'hq-dmz', 'hq-lab', 'dc-gw', 'dc-core', 'dc-srv']:
                    self.assertGreater(len(mgmt_rules), 0,
                                     f"{router_name}: Missing management table policies")


class TestPolicyRoutingIntegration(unittest.TestCase):
    """Integration tests for policy routing enhancement."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = Path(__file__).parent
        self.raw_facts_dir = self.test_dir / "raw_facts"
    
    def test_all_routers_enhanced(self):
        """Test that all routers have been enhanced with policy routing."""
        enhanced_count = 0
        total_files = 0
        
        for file_path in self.raw_facts_dir.glob("*_facts.txt"):
            total_files += 1
            router_name = file_path.stem.replace("_facts", "")
            
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Check for enhancement indicators
            has_policy_rules = 'lookup priority_table' in content
            has_additional_tables = 'routing_table_service_table' in content
            has_complex_rules = 'fwmark' in content and 'dport' in content
            
            if has_policy_rules and has_additional_tables and has_complex_rules:
                enhanced_count += 1
        
        self.assertEqual(enhanced_count, total_files,
                        f"Only {enhanced_count}/{total_files} routers have policy routing enhancements")
    
    def test_policy_routing_coverage_stats(self):
        """Test overall policy routing coverage statistics."""
        total_rules = 0
        total_tables = 0
        
        for file_path in self.raw_facts_dir.glob("*_facts.txt"):
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Count policy rules
            policy_rules = len(re.findall(r'^\d+:', content, re.MULTILINE))
            total_rules += policy_rules
            
            # Count routing tables
            routing_tables = len(re.findall(r'routing_table_\w+', content))
            total_tables += routing_tables
        
        # Verify minimum thresholds
        self.assertGreater(total_rules, 250,
                          f"Insufficient total policy rules ({total_rules}, expected >250)")
        self.assertGreater(total_tables, 60,
                          f"Insufficient total routing tables ({total_tables}, expected >60)")


def main():
    """Main test runner."""
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()