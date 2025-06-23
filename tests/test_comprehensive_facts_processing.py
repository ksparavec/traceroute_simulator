#!/usr/bin/env python3
"""
test_comprehensive_facts_processing.py - Comprehensive test suite for facts processing and iptables analysis

This test suite covers two main areas:
1. Testing the process_facts.py script with all router raw facts data
2. Testing the iptables_forward_analyzer.py with comprehensive rule scenarios

All generated JSON files are stored in /tmp/traceroute_test_output to avoid overwriting
the production files in tests/tsim_facts.
"""

import unittest
import subprocess
import os
import sys
import json
import tempfile
import shutil
import ipaddress
from pathlib import Path

# Add the project root to Python path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'ansible'))

class TestFactsProcessing(unittest.TestCase):
    """Test cases for the facts processing functionality (process_facts.py)."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        cls.test_output_dir = Path("/tmp/traceroute_test_output")
        cls.test_output_dir.mkdir(exist_ok=True)
        
        cls.raw_facts_dir = PROJECT_ROOT / "tests" / "raw_facts"
        cls.process_facts_script = PROJECT_ROOT / "ansible" / "process_facts.py"
        
        # List of all router fact files we created
        cls.router_facts_files = [
            "hq-gw_facts.txt",
            "br-gw_facts.txt", 
            "hq-dmz_facts.txt",
            "dc-srv_facts.txt",
            "hq-core_facts.txt",
            "br-core_facts.txt",
            "dc-core_facts.txt",
            "hq-lab_facts.txt",
            "br-wifi_facts.txt",
            "dc-gw_facts.txt"
        ]
        
        # Verify all files exist
        cls.available_files = []
        for filename in cls.router_facts_files:
            filepath = cls.raw_facts_dir / filename
            if filepath.exists():
                cls.available_files.append(filename)
        
        print(f"Found {len(cls.available_files)} router facts files for testing")
    
    def test_facts_processing_basic_functionality(self):
        """Test basic facts processing for each router."""
        for filename in self.available_files:
            with self.subTest(router_file=filename):
                input_file = self.raw_facts_dir / filename
                output_file = self.test_output_dir / f"{filename.replace('.txt', '.json')}"
                
                # Run process_facts.py
                result = subprocess.run([
                    sys.executable, str(self.process_facts_script),
                    str(input_file), str(output_file)
                ], capture_output=True, text=True)
                
                # Check command succeeded
                self.assertEqual(result.returncode, 0, 
                    f"process_facts.py failed for {filename}: {result.stderr}")
                
                # Verify output file was created
                self.assertTrue(output_file.exists(), 
                    f"Output JSON file not created for {filename}")
                
                # Verify JSON is valid
                with open(output_file, 'r') as f:
                    facts_data = json.load(f)
                
                # Basic structure validation
                self.assertIn('metadata', facts_data)
                self.assertIn('routing', facts_data) 
                self.assertIn('network', facts_data)
                self.assertIn('firewall', facts_data)
                self.assertIn('system', facts_data)
                
                # Verify metadata contains expected fields
                metadata = facts_data['metadata']
                self.assertIn('hostname', metadata)
                self.assertIn('collection_timestamp', metadata)
                self.assertIn('sections_available', metadata)
                
                # Verify firewall data structure
                firewall = facts_data['firewall']
                self.assertIn('iptables', firewall)
                self.assertIn('ipset', firewall)
                
                print(f"✓ Successfully processed {filename} -> {output_file.name}")
    
    def test_facts_processing_with_raw_data(self):
        """Test facts processing with --raw flag to store all raw data."""
        # Test with one complex router (hq-core has extensive rules)
        if "hq-core_facts.txt" in self.available_files:
            input_file = self.raw_facts_dir / "hq-core_facts.txt"
            output_file = self.test_output_dir / "hq-core_raw.json"
            
            # Run with --raw flag
            result = subprocess.run([
                sys.executable, str(self.process_facts_script),
                "--raw", str(input_file), str(output_file)
            ], capture_output=True, text=True)
            
            self.assertEqual(result.returncode, 0, 
                f"process_facts.py --raw failed: {result.stderr}")
            
            # Verify raw data is included
            with open(output_file, 'r') as f:
                facts_data = json.load(f)
            
            # Check for raw config in iptables
            if facts_data['firewall']['iptables']['available']:
                self.assertIn('raw_config', facts_data['firewall']['iptables'])
            
            print(f"✓ Successfully processed with --raw flag")
    
    def test_facts_processing_pretty_output(self):
        """Test facts processing with --pretty flag for human-readable output."""
        if "br-gw_facts.txt" in self.available_files:
            input_file = self.raw_facts_dir / "br-gw_facts.txt"
            output_file = self.test_output_dir / "br-gw_pretty.json"
            
            # Run with --pretty flag
            result = subprocess.run([
                sys.executable, str(self.process_facts_script),
                "--pretty", str(input_file), str(output_file)
            ], capture_output=True, text=True)
            
            self.assertEqual(result.returncode, 0,
                f"process_facts.py --pretty failed: {result.stderr}")
            
            # Verify the output is properly formatted (contains newlines and indentation)
            with open(output_file, 'r') as f:
                content = f.read()
            
            self.assertIn('\n', content, "Pretty output should contain newlines")
            self.assertIn('  ', content, "Pretty output should contain indentation")
            
            print(f"✓ Successfully processed with --pretty flag")
    
    def test_facts_processing_verbose_mode(self):
        """Test facts processing with --verbose flag."""
        if "dc-gw_facts.txt" in self.available_files:
            input_file = self.raw_facts_dir / "dc-gw_facts.txt"
            output_file = self.test_output_dir / "dc-gw_verbose.json"
            
            # Run with --verbose flag
            result = subprocess.run([
                sys.executable, str(self.process_facts_script),
                "--verbose", str(input_file), str(output_file)
            ], capture_output=True, text=True)
            
            self.assertEqual(result.returncode, 0,
                f"process_facts.py --verbose failed: {result.stderr}")
            
            # Verbose mode should produce additional output
            self.assertTrue(len(result.stdout) > 0 or len(result.stderr) > 0,
                "Verbose mode should produce debug output")
            
            print(f"✓ Successfully processed with --verbose flag")
    
    def test_facts_validation_mode(self):
        """Test the --validate mode on generated JSON files."""
        # First generate a JSON file
        if "hq-dmz_facts.txt" in self.available_files:
            input_file = self.raw_facts_dir / "hq-dmz_facts.txt"
            output_file = self.test_output_dir / "hq-dmz_for_validation.json"
            
            # Generate JSON
            result = subprocess.run([
                sys.executable, str(self.process_facts_script),
                str(input_file), str(output_file)
            ], capture_output=True, text=True)
            
            self.assertEqual(result.returncode, 0)
            
            # Now validate it
            result = subprocess.run([
                sys.executable, str(self.process_facts_script),
                "--validate", str(output_file)
            ], capture_output=True, text=True)
            
            self.assertEqual(result.returncode, 0,
                f"JSON validation failed: {result.stderr}")
            
            self.assertIn("is valid", result.stdout)
            
            print(f"✓ Successfully validated generated JSON file")
    
    def test_iptables_parsing_completeness(self):
        """Test that iptables parsing handles complex rule structures."""
        # Test with routers that have complex iptables rules
        complex_routers = ["hq-core_facts.txt", "dc-core_facts.txt", "br-wifi_facts.txt"]
        
        for filename in complex_routers:
            if filename in self.available_files:
                with self.subTest(router_file=filename):
                    input_file = self.raw_facts_dir / filename
                    output_file = self.test_output_dir / f"{filename.replace('.txt', '_complex.json')}"
                    
                    result = subprocess.run([
                        sys.executable, str(self.process_facts_script),
                        "--raw", str(input_file), str(output_file)
                    ], capture_output=True, text=True)
                    
                    self.assertEqual(result.returncode, 0)
                    
                    with open(output_file, 'r') as f:
                        facts_data = json.load(f)
                    
                    # Verify iptables data was parsed
                    firewall = facts_data['firewall']
                    self.assertTrue(firewall['iptables']['available'])
                    
                    # Check that filter table exists and has chains
                    if 'filter' in firewall['iptables']:
                        filter_table = firewall['iptables']['filter']
                        self.assertIsInstance(filter_table, list)
                        self.assertGreater(len(filter_table), 0)
                        
                        # Verify FORWARD chain exists (important for our analyzer)
                        chain_names = []
                        for chain_dict in filter_table:
                            chain_names.extend(chain_dict.keys())
                        
                        self.assertIn('FORWARD', chain_names,
                            f"FORWARD chain not found in {filename}")
                    
                    print(f"✓ Complex iptables parsing successful for {filename}")
    
    def test_ipset_parsing_completeness(self):
        """Test that ipset parsing handles various ipset types."""
        # Test with routers that have complex ipsets
        ipset_routers = ["hq-core_facts.txt", "br-wifi_facts.txt", "dc-gw_facts.txt"]
        
        for filename in ipset_routers:
            if filename in self.available_files:
                with self.subTest(router_file=filename):
                    input_file = self.raw_facts_dir / filename
                    output_file = self.test_output_dir / f"{filename.replace('.txt', '_ipsets.json')}"
                    
                    result = subprocess.run([
                        sys.executable, str(self.process_facts_script),
                        str(input_file), str(output_file)
                    ], capture_output=True, text=True)
                    
                    self.assertEqual(result.returncode, 0)
                    
                    with open(output_file, 'r') as f:
                        facts_data = json.load(f)
                    
                    # Verify ipset data was parsed
                    firewall = facts_data['firewall']
                    self.assertTrue(firewall['ipset']['available'])
                    
                    # Check ipset lists structure
                    ipset_lists = firewall['ipset']['lists']
                    if isinstance(ipset_lists, list):
                        self.assertGreater(len(ipset_lists), 0,
                            f"No ipsets found in {filename}")
                        
                        # Verify ipset structure
                        for ipset_entry in ipset_lists:
                            self.assertIsInstance(ipset_entry, dict)
                            # Each entry should have one key (the ipset name)
                            self.assertEqual(len(ipset_entry), 1)
                    
                    print(f"✓ Ipset parsing successful for {filename}")


class TestIptablesForwardAnalyzer(unittest.TestCase):
    """Test cases for the iptables forward analyzer functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment for forward analyzer tests."""
        cls.test_output_dir = Path("/tmp/traceroute_test_output")
        cls.raw_facts_dir = PROJECT_ROOT / "tests" / "raw_facts"
        cls.analyzer_script = PROJECT_ROOT / "iptables_forward_analyzer.py"
        
        # Generate JSON files for all routers first
        cls.process_facts_script = PROJECT_ROOT / "ansible" / "process_facts.py"
        
        cls.router_names = [
            "hq-gw", "br-gw", "hq-dmz", "dc-srv", "hq-core",
            "br-core", "dc-core", "hq-lab", "br-wifi", "dc-gw"
        ]
        
        cls.generated_json_files = {}
        
        # Generate JSON files for testing
        for router_name in cls.router_names:
            facts_file = cls.raw_facts_dir / f"{router_name}_facts.txt"
            if facts_file.exists():
                json_file = cls.test_output_dir / f"{router_name}.json"
                
                result = subprocess.run([
                    sys.executable, str(cls.process_facts_script),
                    "--raw", str(facts_file), str(json_file)
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    cls.generated_json_files[router_name] = json_file
        
        print(f"Generated {len(cls.generated_json_files)} JSON files for forward analysis testing")
    
    def test_forward_analyzer_basic_functionality(self):
        """Test basic forward analyzer functionality with simple allow/deny cases."""
        if "hq-gw" in self.generated_json_files:
            # Test case 1: Basic TCP traffic that should be allowed
            env = os.environ.copy()
            env['TRACEROUTE_SIMULATOR_FACTS'] = str(self.test_output_dir)
            
            result = subprocess.run([
                sys.executable, str(self.analyzer_script),
                "--router", "hq-gw",
                "-s", "10.1.1.10",
                "-d", "8.8.8.8",
                "-p", "tcp",
                "-dp", "80",
                "-v"
            ], capture_output=True, text=True, env=env)
            
            # Should not fail with error code 2 (missing files/invalid args)
            self.assertNotEqual(result.returncode, 2,
                f"Analyzer failed with missing files/args: {result.stderr}")
            
            print(f"✓ Basic forward analyzer test completed (exit code: {result.returncode})")
    
    def test_forward_analyzer_complex_rulesets(self):
        """Test forward analyzer with complex iptables rulesets."""
        complex_routers = ["hq-core", "dc-core", "br-wifi"]
        
        for router_name in complex_routers:
            if router_name in self.generated_json_files:
                with self.subTest(router=router_name):
                    # Test various traffic scenarios
                    test_cases = [
                        # Internal to internal traffic
                        {
                            "src": "10.1.10.10", "dst": "10.1.11.10", 
                            "protocol": "tcp", "dport": "22",
                            "description": "SSH between lab networks"
                        },
                        # Internal to external traffic  
                        {
                            "src": "10.1.2.10", "dst": "8.8.8.8",
                            "protocol": "tcp", "dport": "443", 
                            "description": "HTTPS to internet"
                        },
                        # Multi-port traffic
                        {
                            "src": "10.1.10.15", "dst": "10.1.2.100",
                            "protocol": "tcp", "dport": "8080",
                            "description": "Application traffic"
                        },
                        # UDP traffic
                        {
                            "src": "10.1.11.20", "dst": "8.8.8.8",
                            "protocol": "udp", "dport": "53",
                            "description": "DNS query"
                        }
                    ]
                    
                    for test_case in test_cases:
                        with self.subTest(test_case=test_case["description"]):
                            env = os.environ.copy()
                            env['TRACEROUTE_SIMULATOR_FACTS'] = str(self.test_output_dir)
                            
                            cmd = [
                                sys.executable, str(self.analyzer_script),
                                "--router", router_name,
                                "-s", test_case["src"],
                                "-d", test_case["dst"],
                                "-p", test_case["protocol"]
                            ]
                            
                            if "dport" in test_case:
                                cmd.extend(["-dp", test_case["dport"]])
                            
                            cmd.append("-v")
                            
                            result = subprocess.run(cmd, capture_output=True, text=True, env=env)
                            
                            # Should not fail with error code 2
                            self.assertNotEqual(result.returncode, 2,
                                f"Analyzer failed for {router_name} {test_case['description']}: {result.stderr}")
                            
                            print(f"✓ {router_name}: {test_case['description']} -> exit code {result.returncode}")
    
    def test_forward_analyzer_match_set_rules(self):
        """Test forward analyzer with match-set (ipset) rules."""
        # Test routers with extensive ipset usage
        ipset_routers = ["hq-core", "br-wifi", "dc-gw"]
        
        for router_name in ipset_routers:
            if router_name in self.generated_json_files:
                with self.subTest(router=router_name):
                    # Test scenarios that would hit match-set rules
                    test_cases = [
                        {
                            "src": "10.1.10.10", "dst": "10.1.10.11",
                            "protocol": "tcp", "dport": "80",
                            "description": "Lab network inter-communication"
                        },
                        {
                            "src": "192.168.10.10", "dst": "10.2.2.1", 
                            "protocol": "tcp", "dport": "443",
                            "description": "WiFi client to infrastructure"
                        },
                        {
                            "src": "10.3.2.10", "dst": "8.8.8.8",
                            "protocol": "tcp", "dport": "443",
                            "description": "Data center to internet"
                        }
                    ]
                    
                    for test_case in test_cases:
                        with self.subTest(test_case=test_case["description"]):
                            env = os.environ.copy()
                            env['TRACEROUTE_SIMULATOR_FACTS'] = str(self.test_output_dir)
                            
                            result = subprocess.run([
                                sys.executable, str(self.analyzer_script),
                                "--router", router_name,
                                "-s", test_case["src"],
                                "-d", test_case["dst"],
                                "-p", test_case["protocol"],
                                "-dp", test_case["dport"],
                                "-vv"  # Detailed rule checking
                            ], capture_output=True, text=True, env=env)
                            
                            self.assertNotEqual(result.returncode, 2,
                                f"Match-set analysis failed for {router_name}: {result.stderr}")
                            
                            print(f"✓ {router_name}: Match-set test {test_case['description']} -> exit code {result.returncode}")
    
    def test_forward_analyzer_multiport_ranges(self):
        """Test forward analyzer with multiport and port range scenarios."""
        if "br-core" in self.generated_json_files:
            # Test port ranges and multiport scenarios
            test_cases = [
                {
                    "src": "10.2.2.10", "dst": "10.2.5.10",
                    "protocol": "tcp", "dport": "80,443,8080",
                    "description": "Multiport HTTP services"
                },
                {
                    "src": "10.2.6.10", "dst": "10.2.5.20",
                    "protocol": "tcp", "dport": "3000:4000",
                    "description": "Port range application services"
                },
                {
                    "src": "10.2.3.10", "dst": "8.8.8.8",
                    "protocol": "udp", "dport": "53,123",
                    "description": "DNS and NTP services"
                }
            ]
            
            for test_case in test_cases:
                with self.subTest(test_case=test_case["description"]):
                    env = os.environ.copy()
                    env['TRACEROUTE_SIMULATOR_FACTS'] = str(self.test_output_dir)
                    
                    result = subprocess.run([
                        sys.executable, str(self.analyzer_script),
                        "--router", "br-core",
                        "-s", test_case["src"],
                        "-d", test_case["dst"],
                        "-p", test_case["protocol"],
                        "-dp", test_case["dport"],
                        "-v"
                    ], capture_output=True, text=True, env=env)
                    
                    self.assertNotEqual(result.returncode, 2,
                        f"Multiport analysis failed: {result.stderr}")
                    
                    print(f"✓ Multiport test: {test_case['description']} -> exit code {result.returncode}")
    
    def test_forward_analyzer_ip_ranges_and_cidrs(self):
        """Test forward analyzer with IP ranges and CIDR notations."""
        if "dc-gw" in self.generated_json_files:
            # Test various IP format scenarios
            test_cases = [
                {
                    "src": "10.3.0.0/16", "dst": "8.8.8.8",
                    "protocol": "tcp", "dport": "443",
                    "description": "CIDR source to internet"
                },
                {
                    "src": "10.3.2.10,10.3.2.11", "dst": "10.3.20.10",
                    "protocol": "tcp", "dport": "80",
                    "description": "Multiple source IPs"
                },
                {
                    "src": "10.100.1.1", "dst": "10.3.0.0/16",
                    "protocol": "tcp", "dport": "22",
                    "description": "VPN to internal network"
                }
            ]
            
            for test_case in test_cases:
                with self.subTest(test_case=test_case["description"]):
                    env = os.environ.copy()
                    env['TRACEROUTE_SIMULATOR_FACTS'] = str(self.test_output_dir)
                    
                    result = subprocess.run([
                        sys.executable, str(self.analyzer_script),
                        "--router", "dc-gw",
                        "-s", test_case["src"],
                        "-d", test_case["dst"],
                        "-p", test_case["protocol"],
                        "-dp", test_case["dport"],
                        "-v"
                    ], capture_output=True, text=True, env=env)
                    
                    self.assertNotEqual(result.returncode, 2,
                        f"IP range analysis failed: {result.stderr}")
                    
                    print(f"✓ IP range test: {test_case['description']} -> exit code {result.returncode}")
    
    def test_forward_analyzer_protocol_variations(self):
        """Test forward analyzer with different protocol types."""
        if "hq-lab" in self.generated_json_files:
            # Test different protocol scenarios
            test_cases = [
                {
                    "src": "10.1.10.10", "dst": "10.1.11.10",
                    "protocol": "tcp", "dport": "22",
                    "description": "TCP SSH traffic"
                },
                {
                    "src": "10.1.10.15", "dst": "8.8.8.8",
                    "protocol": "udp", "dport": "53",
                    "description": "UDP DNS traffic"
                },
                {
                    "src": "10.1.11.20", "dst": "10.1.10.20",
                    "protocol": "icmp",
                    "description": "ICMP ping traffic"
                },
                {
                    "src": "10.1.10.25", "dst": "10.1.11.25",
                    "protocol": "all",
                    "description": "All protocols traffic"
                }
            ]
            
            for test_case in test_cases:
                with self.subTest(test_case=test_case["description"]):
                    env = os.environ.copy()
                    env['TRACEROUTE_SIMULATOR_FACTS'] = str(self.test_output_dir)
                    
                    cmd = [
                        sys.executable, str(self.analyzer_script),
                        "--router", "hq-lab",
                        "-s", test_case["src"],
                        "-d", test_case["dst"],
                        "-p", test_case["protocol"],
                        "-v"
                    ]
                    
                    if "dport" in test_case:
                        cmd.extend(["-dp", test_case["dport"]])
                    
                    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
                    
                    self.assertNotEqual(result.returncode, 2,
                        f"Protocol analysis failed: {result.stderr}")
                    
                    print(f"✓ Protocol test: {test_case['description']} -> exit code {result.returncode}")
    
    def test_forward_analyzer_verbose_levels(self):
        """Test forward analyzer with different verbosity levels."""
        if "hq-core" in self.generated_json_files:
            env = os.environ.copy()
            env['TRACEROUTE_SIMULATOR_FACTS'] = str(self.test_output_dir)
            
            base_cmd = [
                sys.executable, str(self.analyzer_script),
                "--router", "hq-core",
                "-s", "10.1.10.10",
                "-d", "10.1.11.10",
                "-p", "tcp",
                "-dp", "80"
            ]
            
            # Test different verbosity levels
            verbosity_levels = [
                ([], "no verbosity"),
                (["-v"], "basic verbosity"),
                (["-vv"], "detailed verbosity"),
                (["-vvv"], "maximum verbosity")
            ]
            
            for verbose_flags, description in verbosity_levels:
                with self.subTest(verbosity=description):
                    cmd = base_cmd + verbose_flags
                    
                    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
                    
                    self.assertNotEqual(result.returncode, 2,
                        f"Verbosity test failed for {description}: {result.stderr}")
                    
                    # Higher verbosity should produce more output
                    if verbose_flags:
                        self.assertTrue(len(result.stdout) > 0 or len(result.stderr) > 0,
                            f"Verbose mode {description} should produce output")
                    
                    print(f"✓ Verbosity test: {description} -> exit code {result.returncode}")
    
    def test_forward_analyzer_error_conditions(self):
        """Test forward analyzer with various error conditions."""
        # Test missing router
        env = os.environ.copy()
        env['TRACEROUTE_SIMULATOR_FACTS'] = str(self.test_output_dir)
        
        result = subprocess.run([
            sys.executable, str(self.analyzer_script),
            "--router", "nonexistent-router",
            "-s", "10.1.1.1",
            "-d", "10.1.1.2"
        ], capture_output=True, text=True, env=env)
        
        self.assertEqual(result.returncode, 2,
            "Should return error code 2 for missing router")
        
        # Test invalid IP addresses
        if "hq-gw" in self.generated_json_files:
            env = os.environ.copy()
            env['TRACEROUTE_SIMULATOR_FACTS'] = str(self.test_output_dir)
            
            result = subprocess.run([
                sys.executable, str(self.analyzer_script),
                "--router", "hq-gw", 
                "-s", "invalid.ip.address",
                "-d", "10.1.1.2"
            ], capture_output=True, text=True, env=env)
            
            self.assertEqual(result.returncode, 2,
                "Should return error code 2 for invalid IP address")
        
        print("✓ Error condition tests completed")
    
    def test_forward_analyzer_comprehensive_scenarios(self):
        """Test comprehensive real-world scenarios across all available routers."""
        # Define realistic traffic scenarios that should test complex rule chains
        comprehensive_scenarios = [
            # Development lab scenarios
            {
                "router": "hq-lab",
                "scenarios": [
                    {"src": "10.1.10.10", "dst": "10.1.11.10", "protocol": "tcp", "dport": "22", "desc": "Dev to test SSH"},
                    {"src": "10.1.10.15", "dst": "10.1.2.100", "protocol": "tcp", "dport": "8080", "desc": "Dev to CI/CD"},
                    {"src": "10.1.11.20", "dst": "8.8.8.8", "protocol": "udp", "dport": "53", "desc": "Test DNS lookup"}
                ]
            },
            # WiFi access scenarios
            {
                "router": "br-wifi",
                "scenarios": [
                    {"src": "192.168.10.10", "dst": "10.2.2.1", "protocol": "tcp", "dport": "443", "desc": "WiFi to infrastructure"},
                    {"src": "10.2.4.10", "dst": "8.8.8.8", "protocol": "tcp", "dport": "80", "desc": "Guest internet access"},
                    {"src": "192.168.10.15", "dst": "192.168.10.16", "protocol": "tcp", "dport": "22", "desc": "Client isolation test"}
                ]
            },
            # Data center gateway scenarios
            {
                "router": "dc-gw",
                "scenarios": [
                    {"src": "10.3.2.10", "dst": "8.8.8.8", "protocol": "tcp", "dport": "443", "desc": "Server to internet"},
                    {"src": "10.100.1.1", "dst": "10.3.20.10", "protocol": "tcp", "dport": "22", "desc": "VPN to production"},
                    {"src": "10.3.21.10", "dst": "10.3.2.10", "protocol": "tcp", "dport": "3306", "desc": "Storage to database"}
                ]
            }
        ]
        
        for router_config in comprehensive_scenarios:
            router_name = router_config["router"]
            if router_name in self.generated_json_files:
                for scenario in router_config["scenarios"]:
                    with self.subTest(router=router_name, scenario=scenario["desc"]):
                        env = os.environ.copy()
                        env['TRACEROUTE_SIMULATOR_FACTS'] = str(self.test_output_dir)
                        
                        cmd = [
                            sys.executable, str(self.analyzer_script),
                            "--router", router_name,
                            "-s", scenario["src"],
                            "-d", scenario["dst"],
                            "-p", scenario["protocol"],
                            "-v"
                        ]
                        
                        if "dport" in scenario:
                            cmd.extend(["-dp", scenario["dport"]])
                        
                        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
                        
                        self.assertNotEqual(result.returncode, 2,
                            f"Comprehensive scenario failed for {router_name} {scenario['desc']}: {result.stderr}")
                        
                        print(f"✓ {router_name}: {scenario['desc']} -> exit code {result.returncode}")


class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests combining facts processing and forward analysis."""
    
    @classmethod
    def setUpClass(cls):
        """Set up integration test environment."""
        cls.test_output_dir = Path("/tmp/traceroute_test_output")
        cls.raw_facts_dir = PROJECT_ROOT / "tests" / "raw_facts"
        cls.process_facts_script = PROJECT_ROOT / "ansible" / "process_facts.py"
        cls.analyzer_script = PROJECT_ROOT / "iptables_forward_analyzer.py"
    
    def test_end_to_end_workflow(self):
        """Test complete end-to-end workflow from raw facts to forward analysis."""
        # Pick a complex router for end-to-end testing
        router_name = "hq-core"
        facts_file = self.raw_facts_dir / f"{router_name}_facts.txt"
        
        if facts_file.exists():
            json_file = self.test_output_dir / f"{router_name}_e2e.json"
            
            # Step 1: Process facts
            result = subprocess.run([
                sys.executable, str(self.process_facts_script),
                "--raw", "--pretty", str(facts_file), str(json_file)
            ], capture_output=True, text=True)
            
            self.assertEqual(result.returncode, 0,
                f"Facts processing failed: {result.stderr}")
            
            # Step 2: Validate JSON structure
            with open(json_file, 'r') as f:
                facts_data = json.load(f)
            
            self.assertIn('firewall', facts_data)
            self.assertTrue(facts_data['firewall']['iptables']['available'])
            
            # Step 3: Run forward analysis
            env = os.environ.copy()
            env['TRACEROUTE_SIMULATOR_FACTS'] = str(self.test_output_dir)
            
            result = subprocess.run([
                sys.executable, str(self.analyzer_script),
                "--router", router_name,
                "-s", "10.1.10.10",
                "-d", "10.1.11.10", 
                "-p", "tcp",
                "-dp", "80",
                "-vv"
            ], capture_output=True, text=True, env=env)
            
            self.assertNotEqual(result.returncode, 2,
                f"Forward analysis failed: {result.stderr}")
            
            print(f"✓ End-to-end workflow completed successfully for {router_name}")
    
    def test_batch_processing_all_routers(self):
        """Test batch processing of all available router facts."""
        router_files = list(self.raw_facts_dir.glob("*_facts.txt"))
        processed_count = 0
        
        for facts_file in router_files:
            router_name = facts_file.stem.replace("_facts", "")
            json_file = self.test_output_dir / f"{router_name}_batch.json"
            
            # Process facts
            result = subprocess.run([
                sys.executable, str(self.process_facts_script),
                str(facts_file), str(json_file)
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                processed_count += 1
                
                # Quick forward analysis test
                env = os.environ.copy()
                env['TRACEROUTE_SIMULATOR_FACTS'] = str(self.test_output_dir)
                
                result2 = subprocess.run([
                    sys.executable, str(self.analyzer_script),
                    "--router", router_name,
                    "-s", "10.1.1.1",
                    "-d", "10.1.1.2",
                    "-p", "tcp"
                ], capture_output=True, text=True, env=env)
                
                # Should not fail with missing files error
                self.assertNotEqual(result2.returncode, 2,
                    f"Forward analysis failed for {router_name}")
        
        self.assertGreater(processed_count, 0,
            "No router facts files were successfully processed")
        
        print(f"✓ Batch processing completed for {processed_count} routers")


def main():
    """Main test runner with comprehensive output."""
    # Set up test environment
    test_output_dir = Path("/tmp/traceroute_test_output")
    test_output_dir.mkdir(exist_ok=True)
    
    print("=" * 80)
    print("COMPREHENSIVE FACTS PROCESSING AND IPTABLES ANALYSIS TEST SUITE")
    print("=" * 80)
    print(f"Test output directory: {test_output_dir}")
    print(f"Project root: {PROJECT_ROOT}")
    print()
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestFactsProcessing))
    suite.addTests(loader.loadTestsFromTestCase(TestIptablesForwardAnalyzer))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegrationScenarios))
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, buffer=False)
    result = runner.run(suite)
    
    print()
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print("\nFAILURES:")
        for test, traceback in result.failures:
            failure_msg = traceback.split('AssertionError: ')[-1].split('\n')[0]
            print(f"- {test}: {failure_msg}")
    
    if result.errors:
        print("\nERRORS:")
        for test, traceback in result.errors:
            error_msg = traceback.split('\n')[-2]
            print(f"- {test}: {error_msg}")
    
    print(f"\nGenerated files can be found in: {test_output_dir}")
    
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())