#!/usr/bin/env -S python3 -B -u
"""
Test suite for Task 2.4: Packet Tracing Implementation

This test suite validates the comprehensive packet tracing system including
packet tracer engine, rule database, and integration with existing components.

Test Categories:
1. Packet Tracer Engine Tests - Core tracing functionality
2. Rule Database Tests - Rule storage and correlation
3. Integration Tests - End-to-end packet tracing
4. Performance Tests - Tracing efficiency and scale
5. Real-time Tests - Live packet monitoring
6. Export Tests - Trace data export functionality

Author: Network Analysis Tool
License: MIT
"""

import unittest
import os
import sys
import tempfile
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.packet_tracer import PacketTracerEngine, PacketTrace, PacketHop
from core.rule_database import RuleDatabase, IptablesRule, RoutingEntry, PolicyRule


class TestPacketTracerEngine(unittest.TestCase):
    """Test suite for packet tracer engine functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.facts_dir = os.environ.get('TRACEROUTE_SIMULATOR_FACTS', 'tests/tsim_facts')
        self.tracer = PacketTracerEngine(
            facts_dir=self.facts_dir,
            verbose=False,
            verbose_level=1
        )
        
        # Mock data for testing
        self.test_packet_info = {
            'source_ip': '10.1.1.1',
            'dest_ip': '10.2.1.1',
            'protocol': 'tcp',
            'dest_port': 80
        }
    
    def test_01_tracer_initialization(self):
        """Test packet tracer engine initialization."""
        self.assertIsInstance(self.tracer.simulator, object)
        self.assertIsNone(self.tracer.iptables_analyzer)  # Initialized per-router as needed
        self.assertIsInstance(self.tracer.log_processor, object)
        self.assertIsInstance(self.tracer.log_filter, object)
        
        self.assertEqual(len(self.tracer.active_traces), 0)
        self.assertEqual(len(self.tracer.completed_traces), 0)
        self.assertEqual(self.tracer.trace_counter, 0)
    
    def test_02_trace_id_generation(self):
        """Test trace ID generation."""
        trace_id1 = self.tracer.generate_trace_id()
        trace_id2 = self.tracer.generate_trace_id()
        
        self.assertIsInstance(trace_id1, str)
        self.assertIsInstance(trace_id2, str)
        self.assertNotEqual(trace_id1, trace_id2)
        self.assertTrue(trace_id1.startswith('trace_'))
        self.assertTrue(trace_id2.startswith('trace_'))
    
    def test_03_start_trace(self):
        """Test starting a new packet trace."""
        trace_id = self.tracer.start_trace(
            source_ip='10.1.1.1',
            dest_ip='10.2.1.1',
            protocol='tcp',
            dest_port=80
        )
        
        self.assertIsInstance(trace_id, str)
        self.assertIn(trace_id, self.tracer.active_traces)
        
        trace = self.tracer.active_traces[trace_id]
        self.assertEqual(trace.source_ip, '10.1.1.1')
        self.assertEqual(trace.dest_ip, '10.2.1.1')
        self.assertEqual(trace.protocol, 'tcp')
        self.assertEqual(trace.dest_port, 80)
        self.assertEqual(trace.status, 'running')
    
    def test_04_packet_hop_creation(self):
        """Test packet hop creation and properties."""
        hop = PacketHop(
            hop_number=1,
            router_name='hq-gw',
            router_ip='10.1.1.1',
            interface_in='eth0',
            interface_out='eth1',
            ttl_in=64,
            ttl_out=63
        )
        
        self.assertEqual(hop.hop_number, 1)
        self.assertEqual(hop.router_name, 'hq-gw')
        self.assertEqual(hop.router_ip, '10.1.1.1')
        self.assertEqual(hop.interface_in, 'eth0')
        self.assertEqual(hop.interface_out, 'eth1')
        self.assertEqual(hop.ttl_in, 64)
        self.assertEqual(hop.ttl_out, 63)
        self.assertIsInstance(hop.timestamp, datetime)
    
    def test_05_packet_trace_properties(self):
        """Test packet trace properties and methods."""
        trace = PacketTrace(
            trace_id='test_trace_001',
            source_ip='10.1.1.1',
            dest_ip='10.2.1.1',
            protocol='tcp',
            dest_port=80
        )
        
        self.assertEqual(trace.trace_id, 'test_trace_001')
        self.assertEqual(trace.source_ip, '10.1.1.1')
        self.assertEqual(trace.dest_ip, '10.2.1.1')
        self.assertEqual(trace.protocol, 'tcp')
        self.assertEqual(trace.dest_port, 80)
        self.assertEqual(trace.status, 'running')
        self.assertEqual(trace.hop_count, 0)
        self.assertIsNone(trace.duration)
        
        # Add a hop
        hop = PacketHop(1, 'test-router', '10.1.1.1')
        trace.hops.append(hop)
        self.assertEqual(trace.hop_count, 1)
        
        # Complete trace
        trace.end_time = datetime.now()
        trace.status = 'completed'
        self.assertIsNotNone(trace.duration)
    
    def test_06_trace_execution_mock(self):
        """Test trace execution with mocked components."""
        with patch.object(self.tracer, '_get_routing_path') as mock_routing:
            # Mock routing path
            mock_routing.return_value = [
                {
                    'router': 'hq-gw',
                    'ip': '10.1.1.1',
                    'interface_in': 'eth0',
                    'interface_out': 'eth1',
                    'next_hop': '10.1.2.1',
                    'metric': 1,
                    'routing_table': 'main'
                },
                {
                    'router': 'br-gw',
                    'ip': '10.2.1.1',
                    'interface_in': 'eth0',
                    'interface_out': 'eth1',
                    'next_hop': None,
                    'metric': 0,
                    'routing_table': 'main'
                }
            ]
            
            # Start and execute trace
            trace_id = self.tracer.start_trace('10.1.1.1', '10.2.1.1', 'tcp', dest_port=80)
            trace = self.tracer.trace_packet_path(trace_id)
            
            self.assertIsInstance(trace, PacketTrace)
            self.assertIn(trace.status, ['completed', 'failed', 'error'])
            self.assertIsNotNone(trace.end_time)
            
            if trace.status == 'completed':
                self.assertGreater(trace.hop_count, 0)
    
    def test_07_trace_retrieval(self):
        """Test trace retrieval methods."""
        # Start a trace
        trace_id = self.tracer.start_trace('10.1.1.1', '10.2.1.1', 'icmp')
        
        # Test get_trace
        trace = self.tracer.get_trace(trace_id)
        self.assertIsNotNone(trace)
        self.assertEqual(trace.trace_id, trace_id)
        
        # Test list_traces
        all_traces = self.tracer.list_traces()
        self.assertEqual(len(all_traces), 1)
        self.assertEqual(all_traces[0].trace_id, trace_id)
        
        # Test status filtering
        running_traces = self.tracer.list_traces(status='running')
        self.assertEqual(len(running_traces), 1)
        
        completed_traces = self.tracer.list_traces(status='completed')
        self.assertEqual(len(completed_traces), 0)
    
    def test_08_trace_export(self):
        """Test trace export functionality."""
        # Start and complete a mock trace
        trace_id = self.tracer.start_trace('10.1.1.1', '10.2.1.1', 'icmp')
        trace = self.tracer.active_traces[trace_id]
        
        # Add mock hop
        hop = PacketHop(1, 'test-router', '10.1.1.1')
        hop.rtt_ms = 1.5
        hop.iptables_decision = 'ACCEPT'
        trace.hops.append(hop)
        
        # Complete trace
        trace.end_time = datetime.now()
        trace.status = 'completed'
        self.tracer.completed_traces[trace_id] = trace
        del self.tracer.active_traces[trace_id]
        
        # Test JSON export
        json_output = self.tracer.export_trace(trace_id, 'json')
        self.assertIsInstance(json_output, str)
        
        # Validate JSON structure
        trace_data = json.loads(json_output)
        self.assertEqual(trace_data['trace_id'], trace_id)
        self.assertEqual(trace_data['source_ip'], '10.1.1.1')
        self.assertEqual(trace_data['dest_ip'], '10.2.1.1')
        self.assertEqual(trace_data['status'], 'completed')
        self.assertEqual(len(trace_data['hops']), 1)
        
        # Test text export
        text_output = self.tracer.export_trace(trace_id, 'text')
        self.assertIsInstance(text_output, str)
        self.assertIn('Packet Trace Report', text_output)
        self.assertIn(trace_id, text_output)
        self.assertIn('10.1.1.1', text_output)
        self.assertIn('10.2.1.1', text_output)
    
    def test_09_trace_cleanup(self):
        """Test trace cleanup functionality."""
        # Create old completed trace
        old_trace = PacketTrace(
            trace_id='old_trace',
            source_ip='10.1.1.1',
            dest_ip='10.2.1.1',
            protocol='icmp'
        )
        old_trace.end_time = datetime.now() - timedelta(hours=25)
        old_trace.status = 'completed'
        self.tracer.completed_traces['old_trace'] = old_trace
        
        # Create recent completed trace
        recent_trace = PacketTrace(
            trace_id='recent_trace',
            source_ip='10.1.1.1',
            dest_ip='10.2.1.1',
            protocol='icmp'
        )
        recent_trace.end_time = datetime.now() - timedelta(minutes=30)
        recent_trace.status = 'completed'
        self.tracer.completed_traces['recent_trace'] = recent_trace
        
        # Cleanup old traces
        self.tracer.cleanup_completed_traces(max_age_hours=24)
        
        # Verify cleanup
        self.assertNotIn('old_trace', self.tracer.completed_traces)
        self.assertIn('recent_trace', self.tracer.completed_traces)
    
    def test_10_rtt_calculation(self):
        """Test RTT calculation."""
        hop = PacketHop(1, 'test-router', '10.1.1.1')
        
        # Test RTT calculation
        rtt = self.tracer._calculate_rtt(hop, 1)
        self.assertIsInstance(rtt, float)
        self.assertGreater(rtt, 0)
        self.assertLess(rtt, 100)  # Reasonable RTT range
        
        # Test different hop numbers
        rtt1 = self.tracer._calculate_rtt(hop, 1)
        rtt3 = self.tracer._calculate_rtt(hop, 3)
        self.assertLess(rtt1, rtt3)  # RTT should increase with distance


class TestRuleDatabase(unittest.TestCase):
    """Test suite for rule database functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.facts_dir = os.environ.get('TRACEROUTE_SIMULATOR_FACTS', 'tests/tsim_facts')
        self.db = RuleDatabase(facts_dir=self.facts_dir, verbose=False)
        
        # Test data
        self.test_rule_data = {
            'iptables': {
                'filter': {
                    'FORWARD': [
                        '-s 10.1.1.0/24 -d 10.2.1.0/24 -p tcp --dport 80 -j ACCEPT',
                        '-s 10.1.1.0/24 -d 10.2.1.0/24 -p icmp -j ACCEPT',
                        '-j DROP'
                    ]
                }
            },
            'routing': {
                'main': [
                    {
                        'destination': '10.2.1.0/24',
                        'gateway': '10.1.2.1',
                        'interface': 'eth0',
                        'metric': 1
                    }
                ]
            },
            'policy_rules': [
                {
                    'priority': 100,
                    'selector': 'from 10.1.1.0/24',
                    'table': 'priority_table'
                }
            ]
        }
    
    def test_01_database_initialization(self):
        """Test rule database initialization."""
        self.assertEqual(len(self.db.iptables_rules), 0)
        self.assertEqual(len(self.db.routing_entries), 0)
        self.assertEqual(len(self.db.policy_rules), 0)
        self.assertEqual(len(self.db.rule_index), 0)
        self.assertIsNone(self.db.last_updated)
    
    def test_02_iptables_rule_creation(self):
        """Test iptables rule creation and parsing."""
        rule = IptablesRule(
            rule_id="test_rule_001",
            router="test-router",
            table="filter",
            chain="FORWARD",
            rule_number=1,
            raw_rule="-s 10.1.1.1 -d 10.2.1.1 -p tcp --dport 80 -j ACCEPT",
            target="ACCEPT"
        )
        
        self.assertEqual(rule.router, "test-router")
        self.assertEqual(rule.table, "filter")
        self.assertEqual(rule.chain, "FORWARD")
        self.assertEqual(rule.protocol, "tcp")
        self.assertEqual(rule.source_ip, "10.1.1.1")
        self.assertEqual(rule.dest_ip, "10.2.1.1")
        self.assertEqual(rule.dest_port, 80)
        self.assertEqual(rule.target, "ACCEPT")
        self.assertEqual(rule.match_count, 0)
    
    def test_03_rule_packet_matching(self):
        """Test rule packet matching functionality."""
        rule = IptablesRule(
            rule_id="test_rule_001",
            router="test-router",
            table="filter",
            chain="FORWARD",
            rule_number=1,
            raw_rule="-s 10.1.1.0/24 -d 10.2.1.0/24 -p tcp --dport 80 -j ACCEPT",
            target="ACCEPT"
        )
        
        # Matching packet
        matching_packet = {
            'source_ip': '10.1.1.5',
            'dest_ip': '10.2.1.10',
            'protocol': 'tcp',
            'dest_port': 80
        }
        self.assertTrue(rule.matches_packet(matching_packet))
        
        # Non-matching packet (wrong protocol)
        non_matching_packet = {
            'source_ip': '10.1.1.5',
            'dest_ip': '10.2.1.10',
            'protocol': 'udp',
            'dest_port': 80
        }
        self.assertFalse(rule.matches_packet(non_matching_packet))
        
        # Non-matching packet (wrong port)
        non_matching_packet2 = {
            'source_ip': '10.1.1.5',
            'dest_ip': '10.2.1.10',
            'protocol': 'tcp',
            'dest_port': 443
        }
        self.assertFalse(rule.matches_packet(non_matching_packet2))
    
    def test_04_load_router_facts(self):
        """Test loading router facts into database."""
        success = self.db._load_router_facts('test-router', self.test_rule_data)
        self.assertTrue(success)
        
        # Verify iptables rules loaded
        self.assertIn('test-router', self.db.iptables_rules)
        self.assertEqual(len(self.db.iptables_rules['test-router']), 3)
        
        # Verify routing entries loaded
        self.assertIn('test-router', self.db.routing_entries)
        self.assertIn('main', self.db.routing_entries['test-router'])
        self.assertEqual(len(self.db.routing_entries['test-router']['main']), 1)
        
        # Verify policy rules loaded
        self.assertIn('test-router', self.db.policy_rules)
        self.assertEqual(len(self.db.policy_rules['test-router']), 1)
    
    def test_05_build_indexes(self):
        """Test index building functionality."""
        # Load test data
        self.db._load_router_facts('test-router', self.test_rule_data)
        self.db._build_indexes()
        
        # Verify rule index
        self.assertEqual(len(self.db.rule_index), 3)
        
        # Verify chain index
        self.assertIn('test-router', self.db.chain_index)
        self.assertIn('FORWARD', self.db.chain_index['test-router'])
        self.assertEqual(len(self.db.chain_index['test-router']['FORWARD']), 3)
        
        # Verify target index
        self.assertIn('ACCEPT', self.db.target_index)
        self.assertIn('DROP', self.db.target_index)
        self.assertEqual(len(self.db.target_index['ACCEPT']), 2)
        self.assertEqual(len(self.db.target_index['DROP']), 1)
        
        # Verify port index
        self.assertIn(80, self.db.port_index)
        self.assertEqual(len(self.db.port_index[80]), 1)
    
    def test_06_find_matching_rules(self):
        """Test finding matching rules for packets."""
        # Load test data and build indexes
        self.db._load_router_facts('test-router', self.test_rule_data)
        self.db._build_indexes()
        
        # Test packet matching
        packet_info = {
            'source_ip': '10.1.1.5',
            'dest_ip': '10.2.1.10',
            'protocol': 'tcp',
            'dest_port': 80
        }
        
        matching_rules = self.db.find_matching_rules('test-router', packet_info)
        self.assertGreater(len(matching_rules), 0)
        
        # Verify rule match recording
        for rule in matching_rules:
            if rule.target == 'ACCEPT':
                self.assertGreater(rule.match_count, 0)
                self.assertIsNotNone(rule.last_matched)
    
    def test_07_routing_decision(self):
        """Test routing decision functionality."""
        # Load test data
        self.db._load_router_facts('test-router', self.test_rule_data)
        
        # Test routing decision
        decision = self.db.get_routing_decision('test-router', '10.2.1.5', 'main')
        self.assertIsNotNone(decision)
        self.assertEqual(decision.destination, '10.2.1.0/24')
        self.assertEqual(decision.gateway, '10.1.2.1')
        self.assertEqual(decision.interface, 'eth0')
        
        # Test non-matching destination
        no_decision = self.db.get_routing_decision('test-router', '192.168.1.1', 'main')
        self.assertIsNone(no_decision)
    
    def test_08_policy_table_selection(self):
        """Test policy-based routing table selection."""
        # Load test data
        self.db._load_router_facts('test-router', self.test_rule_data)
        
        # Test policy matching
        packet_info = {
            'source_ip': '10.1.1.5',
            'dest_ip': '10.2.1.10',
            'protocol': 'tcp'
        }
        
        table = self.db.get_policy_table('test-router', packet_info)
        # Should match policy rule and return priority_table
        self.assertEqual(table, 'priority_table')
        
        # Test non-matching packet
        non_matching_packet = {
            'source_ip': '192.168.1.5',
            'dest_ip': '10.2.1.10',
            'protocol': 'tcp'
        }
        
        table = self.db.get_policy_table('test-router', non_matching_packet)
        self.assertEqual(table, 'main')
    
    def test_09_database_statistics(self):
        """Test database statistics functionality."""
        # Load test data
        self.db._load_router_facts('test-router', self.test_rule_data)
        self.db._build_indexes()
        
        # Generate some rule matches
        packet_info = {
            'source_ip': '10.1.1.5',
            'dest_ip': '10.2.1.10',
            'protocol': 'tcp',
            'dest_port': 80
        }
        self.db.find_matching_rules('test-router', packet_info)
        
        # Get statistics
        stats = self.db.get_statistics()
        
        self.assertEqual(stats['total_routers'], 1)
        self.assertEqual(stats['total_iptables_rules'], 3)
        self.assertEqual(stats['total_routing_entries'], 1)
        self.assertEqual(stats['total_policy_rules'], 1)
        self.assertGreater(stats['used_rules'], 0)
        self.assertGreater(stats['total_matches'], 0)
        self.assertGreater(stats['usage_percentage'], 0)
    
    def test_10_database_export(self):
        """Test database export functionality."""
        # Load test data
        self.db._load_router_facts('test-router', self.test_rule_data)
        self.db._build_indexes()
        
        # Test JSON export
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name
        
        try:
            success = self.db.export_database(temp_file, 'json')
            self.assertTrue(success)
            
            # Verify exported data
            with open(temp_file, 'r') as f:
                exported_data = json.load(f)
            
            self.assertIn('metadata', exported_data)
            self.assertIn('statistics', exported_data)
            self.assertIn('iptables_rules', exported_data)
            self.assertIn('routing_entries', exported_data)
            self.assertIn('policy_rules', exported_data)
            
            # Verify content
            self.assertIn('test-router', exported_data['iptables_rules'])
            self.assertEqual(len(exported_data['iptables_rules']['test-router']), 3)
            
        finally:
            os.unlink(temp_file)


class TestPacketTracingIntegration(unittest.TestCase):
    """Test suite for packet tracing integration tests."""
    
    def setUp(self):
        """Set up test environment."""
        self.facts_dir = os.environ.get('TRACEROUTE_SIMULATOR_FACTS', 'tests/tsim_facts')
        
    def test_01_tracer_database_integration(self):
        """Test integration between tracer and rule database."""
        # Create tracer and database
        tracer = PacketTracerEngine(facts_dir=self.facts_dir, verbose=False)
        db = RuleDatabase(facts_dir=self.facts_dir, verbose=False)
        
        # Verify components are initialized
        self.assertIsNotNone(tracer.simulator)
        self.assertIsNone(tracer.iptables_analyzer)  # Per-router analyzers
        self.assertIsNotNone(db)
        
        # Test database loading if facts available
        if os.path.exists(self.facts_dir):
            success = db.load_from_facts()
            if success:
                stats = db.get_statistics()
                self.assertGreater(stats['total_routers'], 0)
    
    def test_02_end_to_end_tracing(self):
        """Test end-to-end packet tracing workflow."""
        tracer = PacketTracerEngine(facts_dir=self.facts_dir, verbose=False)
        
        # Mock the routing path to avoid dependency on actual facts
        with patch.object(tracer, '_get_routing_path') as mock_routing:
            mock_routing.return_value = [
                {
                    'router': 'hq-gw',
                    'ip': '10.1.1.1',
                    'interface_in': 'eth0',
                    'interface_out': 'eth1',
                    'next_hop': '10.2.1.1',
                    'metric': 1,
                    'routing_table': 'main'
                }
            ]
            
            # Start trace
            trace_id = tracer.start_trace(
                source_ip='10.1.1.1',
                dest_ip='10.2.1.1',
                protocol='tcp',
                dest_port=80
            )
            
            # Execute trace
            trace = tracer.trace_packet_path(trace_id)
            
            # Verify trace completion
            self.assertIsInstance(trace, PacketTrace)
            self.assertIn(trace.status, ['completed', 'failed', 'error'])
            self.assertIsNotNone(trace.end_time)
            
            # Export trace
            if trace.status == 'completed':
                json_output = tracer.export_trace(trace_id, 'json')
                self.assertIsInstance(json_output, str)
                
                text_output = tracer.export_trace(trace_id, 'text')
                self.assertIsInstance(text_output, str)
    
    def test_03_performance_test(self):
        """Test packet tracing performance."""
        tracer = PacketTracerEngine(facts_dir=self.facts_dir, verbose=False)
        
        # Mock routing to control test execution
        with patch.object(tracer, '_get_routing_path') as mock_routing:
            mock_routing.return_value = [
                {'router': 'test-router', 'ip': '10.1.1.1', 'interface_in': 'eth0', 'interface_out': 'eth1'}
            ]
            
            # Time multiple trace executions
            start_time = time.time()
            num_traces = 5
            
            for i in range(num_traces):
                trace_id = tracer.start_trace(
                    source_ip='10.1.1.1',
                    dest_ip=f'10.2.1.{i+1}',
                    protocol='icmp'
                )
                tracer.trace_packet_path(trace_id)
            
            end_time = time.time()
            total_time = end_time - start_time
            avg_time = total_time / num_traces
            
            # Verify reasonable performance (should be fast with mocked data)
            self.assertLess(avg_time, 1.0)  # Less than 1 second per trace
            self.assertEqual(len(tracer.completed_traces), num_traces)
    
    def test_04_concurrent_tracing(self):
        """Test concurrent packet tracing capability."""
        tracer = PacketTracerEngine(facts_dir=self.facts_dir, verbose=False)
        
        # Start multiple traces
        trace_ids = []
        for i in range(3):
            trace_id = tracer.start_trace(
                source_ip='10.1.1.1',
                dest_ip=f'10.2.1.{i+1}',
                protocol='icmp'
            )
            trace_ids.append(trace_id)
        
        # Verify all traces are active
        self.assertEqual(len(tracer.active_traces), 3)
        
        # Verify each trace is independent
        for trace_id in trace_ids:
            trace = tracer.get_trace(trace_id)
            self.assertIsNotNone(trace)
            self.assertEqual(trace.status, 'running')
    
    def test_05_error_handling(self):
        """Test error handling in packet tracing."""
        tracer = PacketTracerEngine(facts_dir=self.facts_dir, verbose=False)
        
        # Test invalid trace ID
        invalid_trace = tracer.get_trace('invalid_trace_id')
        self.assertIsNone(invalid_trace)
        
        # Test export of non-existent trace
        with self.assertRaises(ValueError):
            tracer.export_trace('invalid_trace_id', 'json')
        
        # Test trace with no routing path
        with patch.object(tracer, '_get_routing_path') as mock_routing:
            mock_routing.return_value = []
            
            trace_id = tracer.start_trace('10.1.1.1', '10.2.1.1', 'icmp')
            trace = tracer.trace_packet_path(trace_id)
            
            self.assertEqual(trace.status, 'failed')
    
    def test_06_trace_data_structures(self):
        """Test trace data structure conversion."""
        # Create a trace with hops
        trace = PacketTrace(
            trace_id='test_trace',
            source_ip='10.1.1.1',
            dest_ip='10.2.1.1',
            protocol='tcp',
            dest_port=80
        )
        
        hop = PacketHop(
            hop_number=1,
            router_name='test-router',
            router_ip='10.1.1.1'
        )
        hop.rtt_ms = 1.5
        hop.iptables_decision = 'ACCEPT'
        trace.hops.append(hop)
        
        trace.end_time = datetime.now()
        trace.status = 'completed'
        
        # Test dictionary conversion
        trace_dict = trace.to_dict()
        self.assertIsInstance(trace_dict, dict)
        self.assertEqual(trace_dict['trace_id'], 'test_trace')
        self.assertEqual(trace_dict['source_ip'], '10.1.1.1')
        self.assertEqual(trace_dict['dest_ip'], '10.2.1.1')
        self.assertEqual(trace_dict['protocol'], 'tcp')
        self.assertEqual(trace_dict['dest_port'], 80)
        self.assertEqual(trace_dict['status'], 'completed')
        self.assertEqual(len(trace_dict['hops']), 1)
        
        # Test hop dictionary conversion
        hop_dict = hop.to_dict()
        self.assertIsInstance(hop_dict, dict)
        self.assertEqual(hop_dict['hop_number'], 1)
        self.assertEqual(hop_dict['router_name'], 'test-router')
        self.assertEqual(hop_dict['router_ip'], '10.1.1.1')
        self.assertEqual(hop_dict['rtt_ms'], 1.5)
        self.assertEqual(hop_dict['iptables_decision'], 'ACCEPT')


def main():
    """Run the test suite."""
    # Change to script directory for relative paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(os.path.dirname(script_dir))
    
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()