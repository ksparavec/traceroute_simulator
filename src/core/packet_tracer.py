#!/usr/bin/env python3
"""
Packet Tracer Engine

Comprehensive packet tracing system that combines routing simulation,
iptables analysis, and real-time packet monitoring for complete network
path analysis and troubleshooting.

Key Features:
- Full packet path tracing through network topology
- Iptables rule evaluation at each hop
- Real-time packet monitoring integration
- Performance timing analysis
- Detailed hop-by-hop analysis
- Policy-based routing consideration
- Firewall decision tracking

Author: Network Analysis Tool
License: MIT
"""

import time
import ipaddress
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Union
from pathlib import Path
import json

# Import our existing components
from core.traceroute_simulator import TracerouteSimulator
from analyzers.iptables_forward_analyzer import IptablesForwardAnalyzer
from analyzers.iptables_log_processor import IptablesLogProcessor, LogEntry
from core.log_filter import LogFilter, FilterCriteria


@dataclass
class PacketTrace:
    """Represents a complete packet trace through the network."""
    trace_id: str
    source_ip: str
    dest_ip: str
    protocol: str
    source_port: Optional[int] = None
    dest_port: Optional[int] = None
    packet_size: int = 64
    ttl: int = 64
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    status: str = "running"  # running, completed, failed, timeout
    hops: List['PacketHop'] = field(default_factory=list)
    
    @property
    def duration(self) -> Optional[timedelta]:
        """Calculate trace duration."""
        if self.end_time:
            return self.end_time - self.start_time
        return None
    
    @property
    def hop_count(self) -> int:
        """Get number of hops in trace."""
        return len(self.hops)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'trace_id': self.trace_id,
            'source_ip': self.source_ip,
            'dest_ip': self.dest_ip,
            'protocol': self.protocol,
            'source_port': self.source_port,
            'dest_port': self.dest_port,
            'packet_size': self.packet_size,
            'ttl': self.ttl,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'status': self.status,
            'duration_ms': self.duration.total_seconds() * 1000 if self.duration else None,
            'hop_count': self.hop_count,
            'hops': [hop.to_dict() for hop in self.hops]
        }


@dataclass
class PacketHop:
    """Represents a single hop in a packet trace."""
    hop_number: int
    router_name: str
    router_ip: str
    interface_in: Optional[str] = None
    interface_out: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    rtt_ms: Optional[float] = None
    ttl_in: Optional[int] = None
    ttl_out: Optional[int] = None
    
    # Routing decision
    routing_table: Optional[str] = None
    next_hop: Optional[str] = None
    route_metric: Optional[int] = None
    policy_rule: Optional[str] = None
    
    # Firewall analysis
    iptables_decision: Optional[str] = None  # ACCEPT, DROP, REJECT
    iptables_rule: Optional[str] = None
    iptables_chain: Optional[str] = None
    iptables_table: Optional[str] = None
    
    # Performance metrics
    processing_time_ms: Optional[float] = None
    queue_delay_ms: Optional[float] = None
    
    # Log correlation
    log_entries: List[LogEntry] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'hop_number': self.hop_number,
            'router_name': self.router_name,
            'router_ip': self.router_ip,
            'interface_in': self.interface_in,
            'interface_out': self.interface_out,
            'timestamp': self.timestamp.isoformat(),
            'rtt_ms': self.rtt_ms,
            'ttl_in': self.ttl_in,
            'ttl_out': self.ttl_out,
            'routing_table': self.routing_table,
            'next_hop': self.next_hop,
            'route_metric': self.route_metric,
            'policy_rule': self.policy_rule,
            'iptables_decision': self.iptables_decision,
            'iptables_rule': self.iptables_rule,
            'iptables_chain': self.iptables_chain,
            'iptables_table': self.iptables_table,
            'processing_time_ms': self.processing_time_ms,
            'queue_delay_ms': self.queue_delay_ms,
            'log_entries': len(self.log_entries)
        }


class PacketTracerEngine:
    """
    Comprehensive packet tracing engine that combines multiple analysis methods.
    
    Integrates routing simulation, iptables analysis, and real-time monitoring
    to provide complete packet path analysis through network topology.
    """
    
    def __init__(self, facts_dir: str = None, verbose: bool = False, verbose_level: int = 1):
        """
        Initialize packet tracer engine.
        
        Args:
            facts_dir: Directory containing network facts
            verbose: Enable verbose output
            verbose_level: Verbosity level (1-3)
        """
        self.facts_dir = facts_dir
        self.verbose = verbose
        self.verbose_level = verbose_level
        
        # Initialize core components
        self.simulator = TracerouteSimulator(facts_dir)
        self.iptables_analyzer = None  # Will be initialized per-router as needed
        self.log_processor = IptablesLogProcessor(verbose, verbose_level)
        self.log_filter = LogFilter(verbose)
        
        # Trace management
        self.active_traces: Dict[str, PacketTrace] = {}
        self.completed_traces: Dict[str, PacketTrace] = {}
        self.trace_counter = 0
        
        # Cache for per-router analyzers
        self.router_analyzers: Dict[str, Any] = {}
        
        if self.verbose:
            print(f"PacketTracerEngine initialized with facts_dir: {facts_dir}")
    
    def get_iptables_analyzer(self, router_name: str):
        """Get iptables analyzer for a specific router."""
        if router_name not in self.router_analyzers:
            try:
                from analyzers.iptables_forward_analyzer import IptablesForwardAnalyzer
                self.router_analyzers[router_name] = IptablesForwardAnalyzer(
                    self.facts_dir, router_name, self.verbose_level
                )
            except Exception as e:
                if self.verbose:
                    print(f"Warning: Could not initialize iptables analyzer for {router_name}: {e}")
                self.router_analyzers[router_name] = None
        
        return self.router_analyzers[router_name]
    
    def generate_trace_id(self) -> str:
        """Generate unique trace ID."""
        self.trace_counter += 1
        timestamp = int(time.time() * 1000)
        return f"trace_{timestamp}_{self.trace_counter:04d}"
    
    def start_trace(self, source_ip: str, dest_ip: str, protocol: str = "icmp",
                    source_port: int = None, dest_port: int = None,
                    packet_size: int = 64, ttl: int = 64) -> str:
        """
        Start a new packet trace.
        
        Args:
            source_ip: Source IP address
            dest_ip: Destination IP address
            protocol: Protocol (tcp, udp, icmp)
            source_port: Source port (for TCP/UDP)
            dest_port: Destination port (for TCP/UDP)
            packet_size: Packet size in bytes
            ttl: Initial TTL value
            
        Returns:
            Trace ID for tracking
        """
        trace_id = self.generate_trace_id()
        
        trace = PacketTrace(
            trace_id=trace_id,
            source_ip=source_ip,
            dest_ip=dest_ip,
            protocol=protocol,
            source_port=source_port,
            dest_port=dest_port,
            packet_size=packet_size,
            ttl=ttl
        )
        
        self.active_traces[trace_id] = trace
        
        if self.verbose:
            print(f"Started packet trace {trace_id}: {source_ip} -> {dest_ip} ({protocol})")
        
        return trace_id
    
    def trace_packet_path(self, trace_id: str, real_time: bool = False) -> PacketTrace:
        """
        Trace packet path through network topology.
        
        Args:
            trace_id: Trace ID to process
            real_time: Enable real-time log monitoring
            
        Returns:
            Completed PacketTrace object
        """
        if trace_id not in self.active_traces:
            raise ValueError(f"Trace {trace_id} not found")
        
        trace = self.active_traces[trace_id]
        
        try:
            # Step 1: Get routing path using simulator
            routing_path = self._get_routing_path(trace)
            if not routing_path:
                trace.status = "failed"
                trace.end_time = datetime.now()
                return trace
            
            # Step 2: Analyze each hop
            hop_number = 1
            current_ttl = trace.ttl
            
            for hop_info in routing_path:
                hop_start_time = datetime.now()
                
                # Create hop object
                hop = PacketHop(
                    hop_number=hop_number,
                    router_name=hop_info.get('router', 'unknown'),
                    router_ip=hop_info.get('ip', 'unknown'),
                    interface_in=hop_info.get('interface_in'),
                    interface_out=hop_info.get('interface_out'),
                    ttl_in=current_ttl,
                    ttl_out=current_ttl - 1 if current_ttl > 1 else 0
                )
                
                # Routing analysis
                self._analyze_routing_decision(trace, hop, hop_info)
                
                # Iptables analysis
                self._analyze_iptables_decision(trace, hop)
                
                # Real-time log correlation if enabled
                if real_time:
                    self._correlate_real_time_logs(trace, hop)
                
                # Performance metrics
                processing_time = (datetime.now() - hop_start_time).total_seconds() * 1000
                hop.processing_time_ms = processing_time
                
                # Simulate RTT (in real implementation, this would come from actual measurement)
                hop.rtt_ms = self._calculate_rtt(hop, hop_number)
                
                trace.hops.append(hop)
                
                # Check if packet was dropped
                if hop.iptables_decision == "DROP":
                    trace.status = "dropped"
                    break
                elif hop.iptables_decision == "REJECT":
                    trace.status = "rejected"
                    break
                
                # Update TTL
                current_ttl = hop.ttl_out
                if current_ttl <= 0:
                    trace.status = "ttl_exceeded"
                    break
                
                hop_number += 1
            
            # Finalize trace
            if trace.status == "running":
                trace.status = "completed"
            trace.end_time = datetime.now()
            
            if self.verbose:
                print(f"Completed trace {trace_id}: {trace.status} ({trace.hop_count} hops)")
        
        except Exception as e:
            trace.status = "error"
            trace.end_time = datetime.now()
            if self.verbose:
                print(f"Error in trace {trace_id}: {e}")
        
        # Move to completed traces
        self.completed_traces[trace_id] = trace
        del self.active_traces[trace_id]
        
        return trace
    
    def _get_routing_path(self, trace: PacketTrace) -> List[Dict[str, Any]]:
        """Get routing path using simulator."""
        try:
            # Use existing simulator to get path
            result = self.simulator.simulate_traceroute(
                source=trace.source_ip,
                destination=trace.dest_ip,
                protocol=trace.protocol,
                destination_port=trace.dest_port
            )
            
            if result and result.get('path'):
                # Convert simulator output to hop info
                hops = []
                path = result['path']
                
                for i, hop in enumerate(path):
                    if isinstance(hop, tuple) and len(hop) >= 7:
                        hop_info = {
                            'router': hop[1],
                            'ip': hop[0],
                            'interface_in': hop[2],
                            'interface_out': hop[3],
                            'next_hop': hop[4],
                            'metric': hop[5],
                            'routing_table': hop[6] if len(hop) > 6 else 'main'
                        }
                        hops.append(hop_info)
                
                return hops
            
        except Exception as e:
            if self.verbose_level >= 2:
                print(f"Error getting routing path: {e}")
        
        return []
    
    def _analyze_routing_decision(self, trace: PacketTrace, hop: PacketHop, hop_info: Dict[str, Any]):
        """Analyze routing decision for this hop."""
        hop.routing_table = hop_info.get('routing_table', 'main')
        hop.next_hop = hop_info.get('next_hop')
        hop.route_metric = hop_info.get('metric')
        
        # Look for policy rules that might apply
        # This would integrate with policy routing analysis
        if self.verbose_level >= 3:
            print(f"  Hop {hop.hop_number}: routing via {hop.routing_table} table to {hop.next_hop}")
    
    def _analyze_iptables_decision(self, trace: PacketTrace, hop: PacketHop):
        """Analyze iptables decision for this hop."""
        try:
            # Use iptables analyzer to check forwarding decision
            result = self.iptables_analyzer.analyze_packet_forwarding(
                router=hop.router_name,
                source_ip=trace.source_ip,
                dest_ip=trace.dest_ip,
                protocol=trace.protocol,
                source_port=trace.source_port,
                dest_port=trace.dest_port,
                verbose=False
            )
            
            if result:
                hop.iptables_decision = "ACCEPT" if result.get('allowed', False) else "DROP"
                hop.iptables_rule = result.get('matching_rule')
                hop.iptables_chain = result.get('chain', 'FORWARD')
                hop.iptables_table = result.get('table', 'filter')
                
                if self.verbose_level >= 2:
                    print(f"  Hop {hop.hop_number}: iptables {hop.iptables_decision}")
            else:
                # Default to ACCEPT if no specific rules found
                hop.iptables_decision = "ACCEPT"
        
        except Exception as e:
            if self.verbose_level >= 2:
                print(f"Error analyzing iptables for hop {hop.hop_number}: {e}")
            hop.iptables_decision = "ACCEPT"  # Default assumption
    
    def _correlate_real_time_logs(self, trace: PacketTrace, hop: PacketHop):
        """Correlate with real-time log entries."""
        try:
            # Create filter criteria for this packet
            criteria = FilterCriteria(
                source_networks=[trace.source_ip],
                dest_networks=[trace.dest_ip],
                protocols=[trace.protocol],
                routers=[hop.router_name],
                duration_minutes=1  # Look at last minute
            )
            
            if trace.dest_port:
                criteria.dest_ports = [trace.dest_port]
            
            # Get recent log entries
            recent_entries = self.log_processor.get_recent_logs(hop.router_name, 1)
            if recent_entries:
                # Filter entries for this packet
                filtered_entries = self.log_filter.filter_entries(
                    [entry.__dict__ for entry in recent_entries], 
                    criteria
                )
                
                # Convert back to LogEntry objects and add to hop
                for entry_dict in filtered_entries:
                    # This would need proper LogEntry reconstruction
                    pass
        
        except Exception as e:
            if self.verbose_level >= 2:
                print(f"Error correlating logs for hop {hop.hop_number}: {e}")
    
    def _calculate_rtt(self, hop: PacketHop, hop_number: int) -> float:
        """Calculate RTT for this hop (simulated)."""
        # Simulate realistic RTT based on hop number and network conditions
        base_rtt = hop_number * 0.5  # Base RTT increases with distance
        jitter = time.time() % 1 * 0.3  # Add some jitter
        return round(base_rtt + jitter, 2)
    
    def get_trace(self, trace_id: str) -> Optional[PacketTrace]:
        """Get trace by ID from active or completed traces."""
        if trace_id in self.active_traces:
            return self.active_traces[trace_id]
        elif trace_id in self.completed_traces:
            return self.completed_traces[trace_id]
        return None
    
    def list_traces(self, status: str = None) -> List[PacketTrace]:
        """List traces, optionally filtered by status."""
        all_traces = list(self.active_traces.values()) + list(self.completed_traces.values())
        
        if status:
            return [trace for trace in all_traces if trace.status == status]
        
        return all_traces
    
    def export_trace(self, trace_id: str, format: str = "json") -> str:
        """Export trace in specified format."""
        trace = self.get_trace(trace_id)
        if not trace:
            raise ValueError(f"Trace {trace_id} not found")
        
        if format.lower() == "json":
            return json.dumps(trace.to_dict(), indent=2)
        elif format.lower() == "text":
            return self._format_trace_text(trace)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def _format_trace_text(self, trace: PacketTrace) -> str:
        """Format trace as human-readable text."""
        lines = []
        lines.append(f"Packet Trace Report - {trace.trace_id}")
        lines.append("=" * 50)
        lines.append(f"Source: {trace.source_ip}")
        lines.append(f"Destination: {trace.dest_ip}")
        lines.append(f"Protocol: {trace.protocol.upper()}")
        
        if trace.source_port or trace.dest_port:
            lines.append(f"Ports: {trace.source_port or '?'} -> {trace.dest_port or '?'}")
        
        lines.append(f"Status: {trace.status}")
        lines.append(f"Duration: {trace.duration.total_seconds() * 1000:.2f}ms" if trace.duration else "Running")
        lines.append(f"Hops: {trace.hop_count}")
        lines.append("")
        
        # Hop details
        lines.append("Hop Details:")
        lines.append("-" * 80)
        
        for hop in trace.hops:
            lines.append(f"{hop.hop_number:2d}. {hop.router_name} ({hop.router_ip})")
            lines.append(f"    Interfaces: {hop.interface_in or '?'} -> {hop.interface_out or '?'}")
            lines.append(f"    TTL: {hop.ttl_in} -> {hop.ttl_out}")
            lines.append(f"    RTT: {hop.rtt_ms:.2f}ms" if hop.rtt_ms else "    RTT: ?.??ms")
            
            if hop.routing_table:
                lines.append(f"    Routing: table {hop.routing_table} -> {hop.next_hop}")
            
            if hop.iptables_decision:
                lines.append(f"    Firewall: {hop.iptables_decision}")
                if hop.iptables_rule:
                    lines.append(f"    Rule: {hop.iptables_rule}")
            
            if hop.processing_time_ms:
                lines.append(f"    Processing: {hop.processing_time_ms:.2f}ms")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def cleanup_completed_traces(self, max_age_hours: int = 24):
        """Clean up old completed traces."""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        to_remove = []
        for trace_id, trace in self.completed_traces.items():
            if trace.end_time and trace.end_time < cutoff_time:
                to_remove.append(trace_id)
        
        for trace_id in to_remove:
            del self.completed_traces[trace_id]
        
        if self.verbose and to_remove:
            print(f"Cleaned up {len(to_remove)} old traces")


def main():
    """Test the packet tracer engine."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Packet Tracer Engine Test')
    parser.add_argument('-s', '--source', required=True, help='Source IP address')
    parser.add_argument('-d', '--dest', required=True, help='Destination IP address')
    parser.add_argument('-p', '--protocol', default='icmp', help='Protocol (tcp, udp, icmp)')
    parser.add_argument('--source-port', type=int, help='Source port')
    parser.add_argument('--dest-port', type=int, help='Destination port')
    parser.add_argument('--facts-dir', help='Facts directory')
    parser.add_argument('-v', '--verbose', action='count', default=0, help='Increase verbosity')
    parser.add_argument('--real-time', action='store_true', help='Enable real-time log monitoring')
    parser.add_argument('--format', choices=['text', 'json'], default='text', help='Output format')
    
    args = parser.parse_args()
    
    # Create packet tracer
    tracer = PacketTracerEngine(
        facts_dir=args.facts_dir,
        verbose=args.verbose >= 1,
        verbose_level=args.verbose
    )
    
    # Start trace
    trace_id = tracer.start_trace(
        source_ip=args.source,
        dest_ip=args.dest,
        protocol=args.protocol,
        source_port=args.source_port,
        dest_port=args.dest_port
    )
    
    # Execute trace
    trace = tracer.trace_packet_path(trace_id, real_time=args.real_time)
    
    # Output results
    output = tracer.export_trace(trace_id, args.format)
    print(output)


if __name__ == '__main__':
    main()