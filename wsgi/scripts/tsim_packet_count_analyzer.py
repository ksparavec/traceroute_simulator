#!/usr/bin/env -S python3 -B -u
"""
TSIM Packet Count Analyzer - Class wrapper for analyze_packet_counts functionality
"""

import sys
import json
from typing import Dict, Any, Optional, List


class TsimPacketCountAnalyzer:
    """Class wrapper for packet count analysis functionality"""
    
    def __init__(self, verbose: bool = False):
        """Initialize the analyzer"""
        self.verbose = verbose
    
    def extract_rule_details(self, rule: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key details from a rule for better analysis."""
        details = {}
        
        # Extract source/destination info
        if 'source' in rule:
            details['source'] = rule['source']
        if 'destination' in rule:
            details['destination'] = rule['destination']
        
        # Extract protocol info
        if 'protocol' in rule:
            details['protocol'] = rule['protocol']
        
        # Extract port info from matches
        if 'matches' in rule:
            for match in rule['matches']:
                if isinstance(match, dict):
                    if 'dport' in match:
                        details['dport'] = match['dport']
                    if 'sport' in match:
                        details['sport'] = match['sport']
                    if 'dports' in match:
                        details['dports'] = match['dports']
                    if 'sports' in match:
                        details['sports'] = match['sports']
        
        return details
    
    def extract_iptables_rules(self, iptables_data: Any) -> tuple[List[Dict], Dict[str, str]]:
        """Extract all rules from iptables data structure."""
        rules = []
        chain_policies = {}
        
        # Handle different possible JSON structures
        if isinstance(iptables_data, dict):
            # Check if it's wrapped in a router name
            for router_name, router_data in iptables_data.items():
                if isinstance(router_data, dict) and 'iptables' in router_data:
                    iptables_data = router_data['iptables']
                    break
            
            # Now process the iptables data
            if 'filter' in iptables_data:
                filter_table = iptables_data['filter']
                
                # Process each chain
                for chain_name, chain_data in filter_table.items():
                    if isinstance(chain_data, dict):
                        # Store chain policy
                        if 'policy' in chain_data:
                            chain_policies[chain_name] = chain_data['policy']
                        
                        # Process rules
                        if 'rules' in chain_data:
                            for rule in chain_data['rules']:
                                rule_entry = {
                                    'chain': chain_name,
                                    'packet-count': rule.get('packet-count', 0),
                                    'byte-count': rule.get('byte-count', 0),
                                    'target': rule.get('target', 'UNKNOWN'),
                                    'protocol': rule.get('protocol', 'all'),
                                    'rule': rule
                                }
                                
                                # Add source/destination if present
                                if 'source' in rule:
                                    rule_entry['source'] = rule['source']
                                if 'destination' in rule:
                                    rule_entry['destination'] = rule['destination']
                                
                                rules.append(rule_entry)
        
        return rules, chain_policies
    
    def compare_packet_counts(self, before_data: Any, after_data: Any, 
                            router_name: str = None, verbose: bool = False, 
                            mode: str = 'blocking') -> Dict[str, Any]:
        """
        Compare packet counts between before and after states.
        
        Args:
            before_data: iptables data before test
            after_data: iptables data after test
            router_name: Name of the router being analyzed
            verbose: Enable verbose output
            mode: 'blocking' or 'allowing' - determines what to look for
        
        Returns:
            Analysis results dictionary
        """
        if verbose or self.verbose:
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"Analyzing router: {router_name or 'Unknown'} (Mode: {mode})", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)
        
        before_rules, before_policies = self.extract_iptables_rules(before_data)
        after_rules, after_policies = self.extract_iptables_rules(after_data)
        
        # Create lookup for after rules
        after_lookup = {}
        for rule in after_rules:
            # Create a unique key for the rule (excluding counts)
            key_parts = [
                rule['chain'],
                rule.get('source', ''),
                rule.get('destination', ''),
                rule.get('protocol', ''),
                rule['target']
            ]
            key = '|'.join(str(p) for p in key_parts)
            after_lookup[key] = rule
        
        # Find rules with increased packet counts
        significant_rules = []
        
        for before_rule in before_rules:
            # Create matching key
            key_parts = [
                before_rule['chain'],
                before_rule.get('source', ''),
                before_rule.get('destination', ''),
                before_rule.get('protocol', ''),
                before_rule['target']
            ]
            key = '|'.join(str(p) for p in key_parts)
            
            if key in after_lookup:
                after_rule = after_lookup[key]
                
                before_count = before_rule['packet-count']
                after_count = after_rule['packet-count']
                
                if after_count > before_count:
                    diff = after_count - before_count
                    
                    # Extract rule details for analysis
                    details = self.extract_rule_details(after_rule['rule'])
                    
                    rule_info = {
                        'chain': after_rule['chain'],
                        'target': after_rule['target'],
                        'before_count': before_count,
                        'after_count': after_count,
                        'difference': diff,
                        'details': details,
                        'rule_text': self.format_rule_text(after_rule)
                    }
                    
                    significant_rules.append(rule_info)
                    
                    if verbose or self.verbose:
                        print(f"\n[+] Rule with increased packet count:", file=sys.stderr)
                        print(f"    Chain: {after_rule['chain']}", file=sys.stderr)
                        print(f"    Target: {after_rule['target']}", file=sys.stderr)
                        print(f"    Packets: {before_count} -> {after_count} (+{diff})", file=sys.stderr)
                        if details:
                            print(f"    Details: {details}", file=sys.stderr)
        
        # Determine the final verdict based on mode
        if mode == 'blocking':
            # In blocking mode, look for DROP/REJECT rules that fired
            blocking_rules = [r for r in significant_rules 
                            if r['target'] in ['DROP', 'REJECT']]
            
            if blocking_rules:
                result = {
                    'router': router_name,
                    'mode': mode,
                    'verdict': 'BLOCKED',
                    'blocking_rules': blocking_rules,
                    'all_rules': significant_rules,
                    'chain_policies': after_policies
                }
            else:
                # Check if default policy would block
                forward_policy = after_policies.get('FORWARD', 'ACCEPT')
                if forward_policy in ['DROP', 'REJECT']:
                    result = {
                        'router': router_name,
                        'mode': mode,
                        'verdict': 'BLOCKED',
                        'reason': f'Default FORWARD policy is {forward_policy}',
                        'all_rules': significant_rules,
                        'chain_policies': after_policies
                    }
                else:
                    result = {
                        'router': router_name,
                        'mode': mode,
                        'verdict': 'ALLOWED',
                        'all_rules': significant_rules,
                        'chain_policies': after_policies
                    }
        else:
            # In allowing mode, look for ACCEPT rules that fired
            accept_rules = [r for r in significant_rules 
                          if r['target'] == 'ACCEPT']
            
            if accept_rules:
                result = {
                    'router': router_name,
                    'mode': mode,
                    'verdict': 'ALLOWED',
                    'accept_rules': accept_rules,
                    'all_rules': significant_rules,
                    'chain_policies': after_policies
                }
            else:
                # In allowing mode, check if there are no blocking rules
                blocking_rules = [r for r in significant_rules 
                                if r['target'] in ['DROP', 'REJECT']]
                if blocking_rules:
                    result = {
                        'router': router_name,
                        'mode': mode,
                        'verdict': 'BLOCKED',
                        'blocking_rules': blocking_rules,
                        'all_rules': significant_rules,
                        'chain_policies': after_policies
                    }
                else:
                    result = {
                        'router': router_name,
                        'mode': mode,
                        'verdict': 'ALLOWED',
                        'reason': 'No blocking rules fired',
                        'all_rules': significant_rules,
                        'chain_policies': after_policies
                    }
        
        if verbose or self.verbose:
            print(f"\nFinal verdict: {result['verdict']}", file=sys.stderr)
        
        return result
    
    def format_rule_text(self, rule: Dict[str, Any]) -> str:
        """Format a rule as readable text."""
        parts = []
        parts.append(f"-A {rule['chain']}")
        
        if rule.get('protocol') and rule['protocol'] != 'all':
            parts.append(f"-p {rule['protocol']}")
        
        if rule.get('source') and rule['source'] != '0.0.0.0/0':
            parts.append(f"-s {rule['source']}")
        
        if rule.get('destination') and rule['destination'] != '0.0.0.0/0':
            parts.append(f"-d {rule['destination']}")
        
        # Add match details
        if 'rule' in rule and 'matches' in rule['rule']:
            for match in rule['rule']['matches']:
                if isinstance(match, dict):
                    if 'dport' in match:
                        parts.append(f"--dport {match['dport']}")
                    if 'sport' in match:
                        parts.append(f"--sport {match['sport']}")
        
        parts.append(f"-j {rule['target']}")
        
        return ' '.join(parts)