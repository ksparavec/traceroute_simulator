#!/usr/bin/env python3
"""
Rule Database System

Comprehensive database system for storing and correlating iptables rules,
routing tables, and policy configurations for packet tracing analysis.

Key Features:
- Iptables rule indexing and correlation
- Routing table management
- Policy rule tracking
- Performance optimized lookups
- Rule matching and evaluation
- Change detection and versioning

Author: Network Analysis Tool
License: MIT
"""

import json
import hashlib
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Set, Union
from pathlib import Path
import re


@dataclass
class IptablesRule:
    """Represents a single iptables rule."""
    rule_id: str
    router: str
    table: str
    chain: str
    rule_number: int
    raw_rule: str
    target: str = ""
    
    # Parsed components
    protocol: Optional[str] = None
    source_ip: Optional[str] = None
    dest_ip: Optional[str] = None
    source_port: Optional[int] = None
    dest_port: Optional[int] = None
    interface_in: Optional[str] = None
    interface_out: Optional[str] = None
    
    # Rule matching
    match_conditions: Dict[str, Any] = field(default_factory=dict)
    extensions: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    created_time: datetime = field(default_factory=datetime.now)
    last_matched: Optional[datetime] = None
    match_count: int = 0
    
    def __post_init__(self):
        """Parse rule components after initialization."""
        if not self.rule_id:
            # Generate rule ID from content hash
            rule_content = f"{self.router}:{self.table}:{self.chain}:{self.raw_rule}"
            self.rule_id = hashlib.md5(rule_content.encode()).hexdigest()[:16]
        
        self._parse_rule()
    
    def _parse_rule(self):
        """Parse iptables rule into components."""
        if not self.raw_rule:
            return
        
        parts = self.raw_rule.split()
        i = 0
        
        while i < len(parts):
            part = parts[i]
            
            # Protocol
            if part in ['-p', '--protocol'] and i + 1 < len(parts):
                self.protocol = parts[i + 1]
                i += 2
                continue
            
            # Source IP
            elif part in ['-s', '--source'] and i + 1 < len(parts):
                self.source_ip = parts[i + 1]
                i += 2
                continue
            
            # Destination IP
            elif part in ['-d', '--destination'] and i + 1 < len(parts):
                self.dest_ip = parts[i + 1]
                i += 2
                continue
            
            # Input interface
            elif part in ['-i', '--in-interface'] and i + 1 < len(parts):
                self.interface_in = parts[i + 1]
                i += 2
                continue
            
            # Output interface
            elif part in ['-o', '--out-interface'] and i + 1 < len(parts):
                self.interface_out = parts[i + 1]
                i += 2
                continue
            
            # Target/Jump
            elif part in ['-j', '--jump'] and i + 1 < len(parts):
                self.target = parts[i + 1]
                i += 2
                continue
            
            # Source port
            elif part == '--sport' and i + 1 < len(parts):
                try:
                    self.source_port = int(parts[i + 1])
                except ValueError:
                    pass
                i += 2
                continue
            
            # Destination port
            elif part == '--dport' and i + 1 < len(parts):
                try:
                    self.dest_port = int(parts[i + 1])
                except ValueError:
                    pass
                i += 2
                continue
            
            # TCP multiport (--dports)
            elif part == '--dports' and i + 1 < len(parts):
                # Handle multiport ranges
                ports_str = parts[i + 1]
                if ',' in ports_str:
                    # Multiple ports, use first one
                    try:
                        self.dest_port = int(ports_str.split(',')[0])
                    except ValueError:
                        pass
                elif ':' in ports_str:
                    # Port range, use first port
                    try:
                        self.dest_port = int(ports_str.split(':')[0])
                    except ValueError:
                        pass
                i += 2
                continue
            
            # Store other match conditions
            elif part.startswith('--'):
                if i + 1 < len(parts) and not parts[i + 1].startswith('-'):
                    self.match_conditions[part] = parts[i + 1]
                    i += 2
                else:
                    self.match_conditions[part] = True
                    i += 1
                continue
            
            i += 1
    
    def matches_packet(self, packet_info: Dict[str, Any]) -> bool:
        """Check if this rule matches a packet."""
        # Protocol check
        if self.protocol and packet_info.get('protocol', '').lower() != self.protocol.lower():
            return False
        
        # Source IP check
        if self.source_ip and not self._ip_matches(packet_info.get('source_ip', ''), self.source_ip):
            return False
        
        # Destination IP check
        if self.dest_ip and not self._ip_matches(packet_info.get('dest_ip', ''), self.dest_ip):
            return False
        
        # Source port check
        if self.source_port and packet_info.get('source_port') != self.source_port:
            return False
        
        # Destination port check
        if self.dest_port and packet_info.get('dest_port') != self.dest_port:
            return False
        
        # Interface checks
        if self.interface_in and packet_info.get('interface_in') != self.interface_in:
            return False
        
        if self.interface_out and packet_info.get('interface_out') != self.interface_out:
            return False
        
        return True
    
    def _ip_matches(self, packet_ip: str, rule_ip: str) -> bool:
        """Check if packet IP matches rule IP (including CIDR)."""
        if not packet_ip or not rule_ip:
            return False
        
        # Exact match
        if packet_ip == rule_ip:
            return True
        
        # CIDR match
        if '/' in rule_ip:
            try:
                import ipaddress
                packet_addr = ipaddress.ip_address(packet_ip)
                rule_network = ipaddress.ip_network(rule_ip, strict=False)
                return packet_addr in rule_network
            except ValueError:
                return False
        
        return False
    
    def record_match(self):
        """Record that this rule was matched."""
        self.last_matched = datetime.now()
        self.match_count += 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'rule_id': self.rule_id,
            'router': self.router,
            'table': self.table,
            'chain': self.chain,
            'rule_number': self.rule_number,
            'raw_rule': self.raw_rule,
            'target': self.target,
            'protocol': self.protocol,
            'source_ip': self.source_ip,
            'dest_ip': self.dest_ip,
            'source_port': self.source_port,
            'dest_port': self.dest_port,
            'interface_in': self.interface_in,
            'interface_out': self.interface_out,
            'match_conditions': self.match_conditions,
            'extensions': self.extensions,
            'created_time': self.created_time.isoformat(),
            'last_matched': self.last_matched.isoformat() if self.last_matched else None,
            'match_count': self.match_count
        }


@dataclass
class RoutingEntry:
    """Represents a routing table entry."""
    router: str
    table: str
    destination: str
    gateway: Optional[str]
    interface: str
    metric: int
    scope: Optional[str] = None
    protocol: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'router': self.router,
            'table': self.table,
            'destination': self.destination,
            'gateway': self.gateway,
            'interface': self.interface,
            'metric': self.metric,
            'scope': self.scope,
            'protocol': self.protocol
        }


@dataclass
class PolicyRule:
    """Represents a policy routing rule."""
    router: str
    priority: int
    selector: str
    table: str
    action: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'router': self.router,
            'priority': self.priority,
            'selector': self.selector,
            'table': self.table,
            'action': self.action
        }


class RuleDatabase:
    """
    Comprehensive database system for network rules and policies.
    
    Provides storage, indexing, and correlation capabilities for iptables rules,
    routing tables, and policy configurations across the network topology.
    """
    
    def __init__(self, facts_dir: str = None, verbose: bool = False):
        """
        Initialize rule database.
        
        Args:
            facts_dir: Directory containing network facts
            verbose: Enable verbose output
        """
        self.facts_dir = facts_dir
        self.verbose = verbose
        
        # Rule storage
        self.iptables_rules: Dict[str, List[IptablesRule]] = {}
        self.routing_entries: Dict[str, Dict[str, List[RoutingEntry]]] = {}
        self.policy_rules: Dict[str, List[PolicyRule]] = {}
        
        # Indexes for fast lookup
        self.rule_index: Dict[str, IptablesRule] = {}
        self.chain_index: Dict[str, Dict[str, List[IptablesRule]]] = {}
        self.target_index: Dict[str, List[IptablesRule]] = {}
        self.port_index: Dict[int, List[IptablesRule]] = {}
        
        # Metadata
        self.last_updated: Optional[datetime] = None
        self.version: str = "1.0"
        
        if self.verbose:
            print(f"RuleDatabase initialized with facts_dir: {facts_dir}")
    
    def load_from_facts(self, facts_dir: str = None) -> bool:
        """
        Load rules from network facts directory.
        
        Args:
            facts_dir: Directory containing facts files
            
        Returns:
            True if successful, False otherwise
        """
        if facts_dir:
            self.facts_dir = facts_dir
        
        if not self.facts_dir:
            if self.verbose:
                print("No facts directory specified")
            return False
        
        facts_path = Path(self.facts_dir)
        if not facts_path.exists():
            if self.verbose:
                print(f"Facts directory not found: {facts_path}")
            return False
        
        success_count = 0
        total_files = 0
        
        # Load from JSON files
        for json_file in facts_path.glob("*.json"):
            total_files += 1
            router_name = json_file.stem
            
            try:
                with open(json_file, 'r') as f:
                    facts = json.load(f)
                
                if self._load_router_facts(router_name, facts):
                    success_count += 1
                    if self.verbose:
                        print(f"Loaded rules for {router_name}")
                        
            except Exception as e:
                if self.verbose:
                    print(f"Error loading {json_file}: {e}")
        
        # Build indexes
        self._build_indexes()
        self.last_updated = datetime.now()
        
        if self.verbose:
            print(f"Loaded rules from {success_count}/{total_files} routers")
            print(f"Total iptables rules: {len(self.rule_index)}")
            print(f"Total routing entries: {sum(len(tables) for tables in self.routing_entries.values())}")
            print(f"Total policy rules: {sum(len(rules) for rules in self.policy_rules.values())}")
        
        return success_count > 0
    
    def _load_router_facts(self, router_name: str, facts: Dict[str, Any]) -> bool:
        """Load facts for a single router."""
        try:
            # Load iptables rules
            iptables_data = facts.get('iptables', {})
            self._load_iptables_rules(router_name, iptables_data)
            
            # Load routing tables
            routing_data = facts.get('routing', {})
            self._load_routing_tables(router_name, routing_data)
            
            # Load policy rules
            policy_data = facts.get('policy_rules', [])
            self._load_policy_rules(router_name, policy_data)
            
            return True
            
        except Exception as e:
            if self.verbose:
                print(f"Error loading facts for {router_name}: {e}")
            return False
    
    def _load_iptables_rules(self, router_name: str, iptables_data: Dict[str, Any]):
        """Load iptables rules for a router."""
        if router_name not in self.iptables_rules:
            self.iptables_rules[router_name] = []
        
        for table_name, table_data in iptables_data.items():
            if not isinstance(table_data, dict):
                continue
            
            for chain_name, chain_rules in table_data.items():
                if not isinstance(chain_rules, list):
                    continue
                
                for rule_num, rule_text in enumerate(chain_rules, 1):
                    if isinstance(rule_text, str) and rule_text.strip():
                        rule = IptablesRule(
                            rule_id="",  # Will be generated
                            router=router_name,
                            table=table_name,
                            chain=chain_name,
                            rule_number=rule_num,
                            raw_rule=rule_text.strip(),
                            target=""  # Will be parsed from raw_rule
                        )
                        self.iptables_rules[router_name].append(rule)
    
    def _load_routing_tables(self, router_name: str, routing_data: Dict[str, Any]):
        """Load routing tables for a router."""
        if router_name not in self.routing_entries:
            self.routing_entries[router_name] = {}
        
        for table_name, routes in routing_data.items():
            if not isinstance(routes, list):
                continue
            
            if table_name not in self.routing_entries[router_name]:
                self.routing_entries[router_name][table_name] = []
            
            for route_data in routes:
                if isinstance(route_data, dict):
                    entry = RoutingEntry(
                        router=router_name,
                        table=table_name,
                        destination=route_data.get('destination', ''),
                        gateway=route_data.get('gateway'),
                        interface=route_data.get('interface', ''),
                        metric=route_data.get('metric', 0),
                        scope=route_data.get('scope'),
                        protocol=route_data.get('protocol')
                    )
                    self.routing_entries[router_name][table_name].append(entry)
    
    def _load_policy_rules(self, router_name: str, policy_data: List[Dict[str, Any]]):
        """Load policy rules for a router."""
        if router_name not in self.policy_rules:
            self.policy_rules[router_name] = []
        
        for rule_data in policy_data:
            if isinstance(rule_data, dict):
                rule = PolicyRule(
                    router=router_name,
                    priority=rule_data.get('priority', 0),
                    selector=rule_data.get('selector', ''),
                    table=rule_data.get('table', ''),
                    action=rule_data.get('action')
                )
                self.policy_rules[router_name].append(rule)
    
    def _build_indexes(self):
        """Build indexes for fast rule lookups."""
        self.rule_index.clear()
        self.chain_index.clear()
        self.target_index.clear()
        self.port_index.clear()
        
        for router_name, rules in self.iptables_rules.items():
            for rule in rules:
                # Rule ID index
                self.rule_index[rule.rule_id] = rule
                
                # Chain index
                if router_name not in self.chain_index:
                    self.chain_index[router_name] = {}
                if rule.chain not in self.chain_index[router_name]:
                    self.chain_index[router_name][rule.chain] = []
                self.chain_index[router_name][rule.chain].append(rule)
                
                # Target index
                if rule.target:
                    if rule.target not in self.target_index:
                        self.target_index[rule.target] = []
                    self.target_index[rule.target].append(rule)
                
                # Port index
                if rule.dest_port:
                    if rule.dest_port not in self.port_index:
                        self.port_index[rule.dest_port] = []
                    self.port_index[rule.dest_port].append(rule)
    
    def find_matching_rules(self, router: str, packet_info: Dict[str, Any]) -> List[IptablesRule]:
        """
        Find iptables rules that match a packet.
        
        Args:
            router: Router name
            packet_info: Packet information dictionary
            
        Returns:
            List of matching rules in order
        """
        matching_rules = []
        
        if router not in self.iptables_rules:
            return matching_rules
        
        for rule in self.iptables_rules[router]:
            if rule.matches_packet(packet_info):
                rule.record_match()
                matching_rules.append(rule)
        
        return matching_rules
    
    def get_routing_decision(self, router: str, dest_ip: str, table: str = "main") -> Optional[RoutingEntry]:
        """
        Get routing decision for a destination.
        
        Args:
            router: Router name
            dest_ip: Destination IP address
            table: Routing table name
            
        Returns:
            Best matching routing entry or None
        """
        if router not in self.routing_entries:
            return None
        
        if table not in self.routing_entries[router]:
            return None
        
        best_match = None
        best_prefix_len = -1
        
        for entry in self.routing_entries[router][table]:
            if self._route_matches(dest_ip, entry.destination):
                prefix_len = self._get_prefix_length(entry.destination)
                if prefix_len > best_prefix_len:
                    best_match = entry
                    best_prefix_len = prefix_len
        
        return best_match
    
    def _route_matches(self, dest_ip: str, route_dest: str) -> bool:
        """Check if destination IP matches route destination."""
        try:
            import ipaddress
            dest_addr = ipaddress.ip_address(dest_ip)
            
            if route_dest == "default" or route_dest == "0.0.0.0/0":
                return True
            
            if '/' in route_dest:
                route_network = ipaddress.ip_network(route_dest, strict=False)
                return dest_addr in route_network
            else:
                route_addr = ipaddress.ip_address(route_dest)
                return dest_addr == route_addr
                
        except ValueError:
            return False
    
    def _get_prefix_length(self, route_dest: str) -> int:
        """Get prefix length for route priority."""
        if route_dest == "default" or route_dest == "0.0.0.0/0":
            return 0
        
        if '/' in route_dest:
            try:
                return int(route_dest.split('/')[1])
            except ValueError:
                return 32
        else:
            return 32
    
    def get_policy_table(self, router: str, packet_info: Dict[str, Any]) -> str:
        """
        Get policy routing table for a packet.
        
        Args:
            router: Router name
            packet_info: Packet information
            
        Returns:
            Routing table name
        """
        if router not in self.policy_rules:
            return "main"
        
        for rule in sorted(self.policy_rules[router], key=lambda r: r.priority):
            if self._policy_matches(rule, packet_info):
                return rule.table
        
        return "main"
    
    def _policy_matches(self, rule: PolicyRule, packet_info: Dict[str, Any]) -> bool:
        """Check if policy rule matches packet."""
        import re
        selector = rule.selector.lower().strip()
        
        # Source-based rules (from X.X.X.X/YY or from X.X.X.X)
        if "from" in selector:
            source_ip = packet_info.get('source_ip', '')
            if source_ip:
                # Extract IP/network from selector
                from_match = re.search(r'from\s+([0-9./]+)', selector)
                if from_match:
                    network_str = from_match.group(1)
                    try:
                        if '/' in network_str:
                            # CIDR notation
                            import ipaddress
                            source_addr = ipaddress.ip_address(source_ip)
                            network = ipaddress.ip_network(network_str, strict=False)
                            if source_addr in network:
                                return True
                        else:
                            # Exact IP match
                            if source_ip == network_str:
                                return True
                    except ValueError:
                        pass
        
        # Destination-based rules (to X.X.X.X/YY or to X.X.X.X)
        if "to" in selector:
            dest_ip = packet_info.get('dest_ip', '')
            if dest_ip:
                # Extract IP/network from selector
                to_match = re.search(r'to\s+([0-9./]+)', selector)
                if to_match:
                    network_str = to_match.group(1)
                    try:
                        if '/' in network_str:
                            # CIDR notation
                            import ipaddress
                            dest_addr = ipaddress.ip_address(dest_ip)
                            network = ipaddress.ip_network(network_str, strict=False)
                            if dest_addr in network:
                                return True
                        else:
                            # Exact IP match
                            if dest_ip == network_str:
                                return True
                    except ValueError:
                        pass
        
        # Protocol-based rules
        if "ipproto" in selector:
            protocol = packet_info.get('protocol', '')
            if protocol and protocol in selector:
                return True
        
        # Port-based rules
        if "dport" in selector:
            dest_port = packet_info.get('dest_port')
            if dest_port and str(dest_port) in selector:
                return True
        
        return False
    
    def get_router_rules(self, router: str) -> List[IptablesRule]:
        """Get all iptables rules for a router."""
        return self.iptables_rules.get(router, [])
    
    def get_rules_by_chain(self, router: str, chain: str) -> List[IptablesRule]:
        """Get rules for a specific chain."""
        if router in self.chain_index and chain in self.chain_index[router]:
            return self.chain_index[router][chain]
        return []
    
    def get_rules_by_target(self, target: str) -> List[IptablesRule]:
        """Get rules with specific target."""
        return self.target_index.get(target, [])
    
    def get_rules_by_port(self, port: int) -> List[IptablesRule]:
        """Get rules affecting specific port."""
        return self.port_index.get(port, [])
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics."""
        total_rules = len(self.rule_index)
        total_routing = sum(
            len(tables) 
            for router_tables in self.routing_entries.values() 
            for tables in router_tables.values()
        )
        total_policies = sum(len(rules) for rules in self.policy_rules.values())
        
        # Rule usage statistics
        used_rules = sum(1 for rule in self.rule_index.values() if rule.match_count > 0)
        total_matches = sum(rule.match_count for rule in self.rule_index.values())
        
        return {
            'total_routers': len(self.iptables_rules),
            'total_iptables_rules': total_rules,
            'total_routing_entries': total_routing,
            'total_policy_rules': total_policies,
            'used_rules': used_rules,
            'total_matches': total_matches,
            'usage_percentage': (used_rules / total_rules * 100) if total_rules > 0 else 0,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'version': self.version
        }
    
    def export_database(self, output_file: str, format: str = "json") -> bool:
        """
        Export database to file.
        
        Args:
            output_file: Output file path
            format: Export format (json, csv)
            
        Returns:
            True if successful
        """
        try:
            if format.lower() == "json":
                data = {
                    'metadata': {
                        'version': self.version,
                        'last_updated': self.last_updated.isoformat() if self.last_updated else None,
                        'export_time': datetime.now().isoformat()
                    },
                    'statistics': self.get_statistics(),
                    'iptables_rules': {
                        router: [rule.to_dict() for rule in rules]
                        for router, rules in self.iptables_rules.items()
                    },
                    'routing_entries': {
                        router: {
                            table: [entry.to_dict() for entry in entries]
                            for table, entries in tables.items()
                        }
                        for router, tables in self.routing_entries.items()
                    },
                    'policy_rules': {
                        router: [rule.to_dict() for rule in rules]
                        for router, rules in self.policy_rules.items()
                    }
                }
                
                with open(output_file, 'w') as f:
                    json.dump(data, f, indent=2)
                
                if self.verbose:
                    print(f"Database exported to {output_file}")
                return True
            
            else:
                if self.verbose:
                    print(f"Unsupported export format: {format}")
                return False
                
        except Exception as e:
            if self.verbose:
                print(f"Error exporting database: {e}")
            return False
    
    def clear_database(self):
        """Clear all database contents."""
        self.iptables_rules.clear()
        self.routing_entries.clear()
        self.policy_rules.clear()
        self.rule_index.clear()
        self.chain_index.clear()
        self.target_index.clear()
        self.port_index.clear()
        self.last_updated = None
        
        if self.verbose:
            print("Database cleared")


def main():
    """Test the rule database system."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Rule Database System Test')
    parser.add_argument('--facts-dir', help='Facts directory')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--export', help='Export database to file')
    parser.add_argument('--stats', action='store_true', help='Show statistics')
    
    args = parser.parse_args()
    
    # Create rule database
    db = RuleDatabase(facts_dir=args.facts_dir, verbose=args.verbose)
    
    # Load rules
    if args.facts_dir:
        success = db.load_from_facts()
        if not success:
            print("Failed to load rules from facts")
            return 1
    
    # Show statistics
    if args.stats:
        stats = db.get_statistics()
        print("\nRule Database Statistics:")
        print("=" * 30)
        for key, value in stats.items():
            print(f"{key}: {value}")
    
    # Export database
    if args.export:
        success = db.export_database(args.export)
        if not success:
            print(f"Failed to export database to {args.export}")
            return 1
    
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())