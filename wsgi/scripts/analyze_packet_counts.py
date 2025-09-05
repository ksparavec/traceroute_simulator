#!/usr/bin/env -S python3 -B -u
"""
Analyze iptables packet count differences to identify blocking rules.
"""

import sys
import json
import argparse


def extract_rule_details(rule):
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


def extract_iptables_rules(iptables_data):
    """Extract all rules from iptables data structure."""
    rules = []
    chain_policies = {}
    
    # Handle different possible JSON structures
    if isinstance(iptables_data, dict):
        # Check if it's wrapped in a router name
        for router_name, router_data in iptables_data.items():
            if isinstance(router_data, dict) and 'iptables' in router_data:
                iptables = router_data['iptables']
            elif 'filter' in router_data:
                iptables = router_data
            else:
                continue
                
            # Extract rules from filter table
            if 'filter' in iptables:
                filter_table = iptables['filter']
                
                # Check if we have a 'chains' key (new structure)
                if 'chains' in filter_table:
                    chains = filter_table['chains']
                    for chain_name, chain_data in chains.items():
                        # Store chain policy
                        if isinstance(chain_data, dict):
                            chain_policies[chain_name] = chain_data.get('policy', '-')
                            if 'rules' in chain_data:
                                for idx, rule in enumerate(chain_data['rules']):
                                    if isinstance(rule, dict):
                                        rules.append({
                                            'chain': chain_name,
                                            'rule_number': idx + 1,
                                            'rule': rule
                                        })
                else:
                    # Old structure - rules directly under chain names
                    for chain_name, chain_rules in filter_table.items():
                        if isinstance(chain_rules, list):
                            for idx, rule in enumerate(chain_rules):
                                if isinstance(rule, dict):
                                    rules.append({
                                        'chain': chain_name,
                                        'rule_number': idx + 1,
                                        'rule': rule
                                    })
    
    return rules, chain_policies


def compare_packet_counts(before_data, after_data, router_name, verbose=False, mode='blocking'):
    """Compare packet counts and find rules with increased counts.
    
    Args:
        mode: 'blocking' to find DROP/REJECT rules, 'allowing' to find ACCEPT rules
    """
    before_rules, before_policies = extract_iptables_rules(before_data)
    after_rules, after_policies = extract_iptables_rules(after_data)
    
    if verbose:
        print(f"Found {len(before_rules)} rules in before data", file=sys.stderr)
        print(f"Found {len(after_rules)} rules in after data", file=sys.stderr)
        print(f"Mode: {mode}", file=sys.stderr)
        
        # Show all chains found
        chains_found = set()
        for rule_info in after_rules:
            chains_found.add(rule_info['chain'])
        print(f"Chains found: {sorted(chains_found)}", file=sys.stderr)
        print(f"Chain policies: {after_policies}", file=sys.stderr)
    
    triggered_rules = []
    all_triggered = []
    
    # Create lookup map for before rules
    before_map = {}
    for rule_info in before_rules:
        key = (rule_info['chain'], rule_info['rule_number'])
        before_map[key] = rule_info['rule'].get('packets', 0)
    
    # Compare with after rules
    custom_chain_rules_checked = 0
    for rule_info in after_rules:
        key = (rule_info['chain'], rule_info['rule_number'])
        rule = rule_info['rule']
        
        # Count custom chain rules being checked
        if rule_info['chain'] not in ['INPUT', 'FORWARD', 'OUTPUT']:
            custom_chain_rules_checked += 1
        
        before_count = before_map.get(key, 0)
        after_count = rule.get('packets', 0)
        
        # Check if packet count increased
        if after_count > before_count:
            target = rule.get('target', '')
            rule_text = rule.get('raw', rule.get('rule', ''))
            
            # Extract rule details
            rule_details = extract_rule_details(rule)
            
            trigger_info = {
                'chain': rule_info['chain'],
                'rule_number': rule_info['rule_number'],
                'rule_text': rule_text,
                'target': target,
                'packets_before': before_count,
                'packets_after': after_count,
                'packets_diff': after_count - before_count,
                'packet_info': f"{before_count} -> {after_count} (+{after_count - before_count})"
            }
            
            # Add rule details if available
            if rule_details:
                trigger_info['details'] = rule_details
            
            all_triggered.append(trigger_info)
            
            # Check based on mode
            if mode == 'blocking':
                # Check if it's a blocking rule (DROP or REJECT)
                if target in ['DROP', 'REJECT', 'RETURN']:
                    triggered_rules.append(trigger_info)
            elif mode == 'allowing':
                # Check if it's an allowing rule (ACCEPT)
                if target == 'ACCEPT':
                    triggered_rules.append(trigger_info)
    
    if verbose:
        print(f"Custom chain rules checked: {custom_chain_rules_checked}", file=sys.stderr)
        if all_triggered:
            print(f"\nAll rules with increased packet counts:", file=sys.stderr)
            chain_targets = {}
            
            # Group rules by chain for better readability
            rules_by_chain = {}
            for rule in all_triggered:
                chain = rule['chain']
                if chain not in rules_by_chain:
                    rules_by_chain[chain] = []
                rules_by_chain[chain].append(rule)
                
                # Track which chains were jumped to
                if rule['target'] not in ['ACCEPT', 'DROP', 'REJECT', 'RETURN', 'LOG']:
                    chain_targets[rule['target']] = rule['chain']
            
            # Print rules grouped by chain
            for chain, rules in sorted(rules_by_chain.items()):
                chain_policy = after_policies.get(chain, '-')
                print(f"\n=== Chain: {chain} (Policy: {chain_policy}) ===", file=sys.stderr)
                for rule in rules:
                    print(f"  Rule #: {rule['rule_number']}", file=sys.stderr)
                    print(f"  Target: {rule['target']}", file=sys.stderr)
                    print(f"  Packets: {rule['packets_before']} -> {rule['packets_after']} (+{rule['packets_diff']})", file=sys.stderr)
                    if 'details' in rule and rule['details']:
                        details = rule['details']
                        if 'source' in details:
                            print(f"  Source: {details['source']}", file=sys.stderr)
                        if 'destination' in details:
                            print(f"  Destination: {details['destination']}", file=sys.stderr)
                        if 'protocol' in details:
                            print(f"  Protocol: {details['protocol']}", file=sys.stderr)
                        if 'dport' in details:
                            print(f"  Dest Port: {details['dport']}", file=sys.stderr)
                        if 'sport' in details:
                            print(f"  Source Port: {details['sport']}", file=sys.stderr)
                    print(f"  Rule: {rule['rule_text'][:200]}", file=sys.stderr)
                    print(f"  ---", file=sys.stderr)
            
            # Check chain policies for custom chains that were jumped to
            if chain_targets:
                print(f"\nCustom chains jumped to: {list(chain_targets.keys())}", file=sys.stderr)
                print(f"\nChain policies:", file=sys.stderr)
                for chain in chain_targets.keys():
                    policy = after_policies.get(chain, 'unknown')
                    print(f"  {chain}: {policy}", file=sys.stderr)
                
                # Check if any jumped-to chain has DROP policy
                blocking_chains = [chain for chain in chain_targets.keys() 
                                 if after_policies.get(chain) == 'DROP']
                if blocking_chains and mode == 'blocking':
                    print(f"\nChains with DROP policy: {blocking_chains}", file=sys.stderr)
                    print(f"Packets likely dropped by default policy of chain(s): {', '.join(blocking_chains)}", file=sys.stderr)
            
            # Show packet flow through chains
            print(f"\n=== Packet Flow Analysis ===", file=sys.stderr)
            chain_sequence = []
            seen_chains = set()
            
            # Start with FORWARD chain
            if 'FORWARD' in rules_by_chain:
                for rule in rules_by_chain['FORWARD']:
                    if rule['target'] not in ['ACCEPT', 'DROP', 'REJECT', 'RETURN', 'LOG'] and rule['target'] not in seen_chains:
                        chain_sequence.append(('FORWARD', rule['rule_number'], rule['target']))
                        seen_chains.add(rule['target'])
            
            print(f"Chain traversal:", file=sys.stderr)
            for from_chain, rule_num, to_chain in chain_sequence:
                print(f"  {from_chain} (rule #{rule_num}) -> {to_chain}", file=sys.stderr)
                
            # Check for chains that were entered but had no rule matches
            print(f"\nChains entered but no rules matched:", file=sys.stderr)
            chains_without_matches = []
            for chain in seen_chains:
                if chain not in rules_by_chain:
                    print(f"  {chain}: No rules with increased packet counts", file=sys.stderr)
                    # Try to find why no rules matched
                    chain_rules_count = 0
                    for rule_info in after_rules:
                        if rule_info['chain'] == chain:
                            chain_rules_count += 1
                    print(f"    Total rules in chain: {chain_rules_count}", file=sys.stderr)
                    chain_policy = after_policies.get(chain, None)
                    print(f"    Chain policy: {chain_policy}", file=sys.stderr)
                    
                    # Track chains without matches
                    chains_without_matches.append({
                        'chain': chain,
                        'rules_count': chain_rules_count,
                        'policy': chain_policy
                    })
            
            # Explain what happens to packets in chains without matches
            if chains_without_matches and mode == 'allowing':
                print(f"\nPacket disposition for chains without matches:", file=sys.stderr)
                for chain_info in chains_without_matches:
                    if chain_info['policy'] is None:
                        # Check parent chain policy (usually FORWARD)
                        parent_policy = after_policies.get('FORWARD', 'ACCEPT')
                        print(f"  {chain_info['chain']}: Custom chain (no policy), implicit RETURN to calling chain", file=sys.stderr)
                        print(f"    → Packets returned to FORWARD chain", file=sys.stderr)
                        if parent_policy == 'ACCEPT':
                            print(f"    → Packets ACCEPTED by FORWARD chain default policy: {parent_policy}", file=sys.stderr)
            
            # Show which rules matched our mode
            if mode == 'blocking':
                blocking_count = len([r for r in all_triggered if r['target'] in ['DROP', 'REJECT', 'RETURN']])
                print(f"\nFound {blocking_count} blocking rules (DROP/REJECT/RETURN)", file=sys.stderr)
            else:
                allowing_count = len([r for r in all_triggered if r['target'] == 'ACCEPT'])
                print(f"\nFound {allowing_count} allowing rules (ACCEPT)", file=sys.stderr)
        else:
            print(f"\nNo rules with increased packet counts found", file=sys.stderr)
    
    # Check if packets were dropped by default policy
    if all_triggered and not triggered_rules:
        # Find which chain likely dropped/allowed the packets
        # First check custom chains that were jumped to
        chain_targets = {}
        for rule in all_triggered:
            if rule['target'] not in ['ACCEPT', 'DROP', 'REJECT', 'RETURN', 'LOG']:
                chain_targets[rule['target']] = rule['chain']
        
        # Check policies of jumped-to chains
        blocking_chain = None
        allowing_chain = None
        
        for chain in chain_targets.keys():
            policy = after_policies.get(chain, '-')
            if policy == 'DROP' and mode == 'blocking':
                blocking_chain = chain
                break
            elif policy == 'ACCEPT' and mode == 'allowing':
                allowing_chain = chain
                break
        
        # If no custom chain found, check FORWARD chain
        if not blocking_chain and not allowing_chain:
            forward_policy = after_policies.get('FORWARD', 'ACCEPT')
            if forward_policy == 'DROP' and mode == 'blocking':
                blocking_chain = 'FORWARD'
            elif forward_policy == 'ACCEPT' and mode == 'allowing':
                allowing_chain = 'FORWARD'
        
        if blocking_chain:
            # Packets were dropped by default policy
            return {
                'router': router_name,
                'mode': mode,
                'result': {
                    'status': 'blocked',
                    'reason': 'default_policy',
                    'description': f"Blocked by {blocking_chain} chain default DROP policy",
                    'details': f"No matching ACCEPT rules found in {blocking_chain} chain, packets dropped by default policy",
                    'rules_found': 0
                },
                'blocking_rules': [{
                    'chain': blocking_chain,
                    'rule_number': 'default',
                    'rule_text': f'Default policy: DROP',
                    'target': 'DROP',
                    'packets_before': 0,
                    'packets_after': 0,
                    'packets_diff': 0,
                    'note': f'Packets dropped by {blocking_chain} chain default policy (no matching ACCEPT rule)'
                }],
                'allowing_rules': []
            }
        elif allowing_chain:
            # Packets were allowed by default policy
            return {
                'router': router_name,
                'mode': mode,
                'result': {
                    'status': 'allowed',
                    'reason': 'default_policy',
                    'description': f"Allowed by {allowing_chain} chain default ACCEPT policy",
                    'details': f"No specific rules needed in {allowing_chain} chain, packets accepted by default policy",
                    'rules_found': 0
                },
                'blocking_rules': [],
                'allowing_rules': [{
                    'chain': allowing_chain,
                    'rule_number': 'default',
                    'rule_text': f'Default policy: ACCEPT',
                    'target': 'ACCEPT',
                    'packets_before': 0,
                    'packets_after': 0,
                    'packets_diff': 0,
                    'note': f'Packets allowed by {allowing_chain} chain default policy (no specific rule needed)'
                }]
            }
    
    # Check for implicit allows/blocks from chains without matches
    implicit_rules = []
    
    # Find chains that were jumped to but had no matching rules
    jumped_chains = set()
    for rule in all_triggered:
        if rule['target'] not in ['ACCEPT', 'DROP', 'REJECT', 'RETURN', 'LOG']:
            jumped_chains.add(rule['target'])
    
    # Check each jumped chain
    for chain in jumped_chains:
        # Check if this chain had any rules that matched
        chain_had_matches = any(r['chain'] == chain for r in all_triggered)
        
        if not chain_had_matches:
            # No rules matched in this chain
            chain_policy = after_policies.get(chain, None)
            if chain_policy is None:
                # Chain has no default policy, falls through to parent
                parent_policy = after_policies.get('FORWARD', 'ACCEPT')
                if mode == 'allowing' and parent_policy == 'ACCEPT':
                    implicit_rules.append({
                        'chain': chain,
                        'rule_number': 'implicit-return',
                        'rule_text': f'No rules matched in {chain}, implicit RETURN to calling chain',
                        'target': 'RETURN',
                        'packets_before': 0,
                        'packets_after': 0,
                        'packets_diff': 0,
                        'note': f'Custom chain {chain} has no policy. Packets returned to FORWARD chain and were allowed by FORWARD policy: {parent_policy}'
                    })
    
    # Determine the analysis result
    result = {
        'router': router_name,
        'mode': mode,
        'result': {}
    }
    
    if mode == 'blocking':
        result['blocking_rules'] = triggered_rules
        result['allowing_rules'] = []
        
        if triggered_rules:
            # Found specific blocking rules
            rule_summary = []
            for rule in triggered_rules:
                rule_summary.append(f"{rule['chain']} rule #{rule['rule_number']} ({rule['target']})")
            result['result'] = {
                'status': 'blocked',
                'reason': 'explicit_rules',
                'description': f"Blocked by {len(triggered_rules)} firewall rule(s)",
                'details': f"Blocking rules: {', '.join(rule_summary)}",
                'rules_found': len(triggered_rules)
            }
        else:
            # Check if blocked by default policy (from earlier logic)
            # Find which chain likely dropped the packets
            chain_targets = {}
            for rule in all_triggered:
                if rule['target'] not in ['ACCEPT', 'DROP', 'REJECT', 'RETURN', 'LOG']:
                    chain_targets[rule['target']] = rule['chain']
            
            # Check policies of jumped-to chains
            blocking_chain = None
            for chain in chain_targets.keys():
                policy = after_policies.get(chain, '-')
                if policy == 'DROP':
                    blocking_chain = chain
                    break
            
            # If no custom chain found, check FORWARD chain
            if not blocking_chain:
                forward_policy = after_policies.get('FORWARD', 'ACCEPT')
                if forward_policy == 'DROP':
                    blocking_chain = 'FORWARD'
            
            if blocking_chain:
                # Blocked by default policy
                result['result'] = {
                    'status': 'blocked',
                    'reason': 'default_policy',
                    'description': f"Blocked by {blocking_chain} chain default DROP policy",
                    'details': "No specific blocking rules found, packets dropped by chain default policy",
                    'rules_found': 0
                }
            else:
                # No blocking found (shouldn't happen in blocking mode)
                result['result'] = {
                    'status': 'unknown',
                    'reason': 'no_blocking_found',
                    'description': "No blocking rules or policies found",
                    'details': "Service failed but no firewall blocking detected",
                    'rules_found': 0
                }
    else:  # allowing mode
        result['blocking_rules'] = []
        result['allowing_rules'] = triggered_rules + implicit_rules
        
        if triggered_rules:
            # Check if we only have RELATED,ESTABLISHED rules
            only_established = all(
                'RELATED' in rule.get('rule_text', '') and 'ESTABLISHED' in rule.get('rule_text', '')
                for rule in triggered_rules
            )
            
            if only_established and implicit_rules:
                # NEW packets were allowed by implicit rules, only ESTABLISHED by explicit
                result['result'] = {
                    'status': 'allowed',
                    'reason': 'default_policy_new',
                    'description': f"NEW connections allowed by FORWARD chain default policy",
                    'details': f"Initial SYN packet traversed custom chain(s) without matching any rules, returned to FORWARD chain and was allowed by FORWARD default ACCEPT policy. Subsequent packets matched RELATED,ESTABLISHED rule.",
                    'rules_found': 0
                }
            else:
                # Found specific allowing rules for NEW connections
                rule_summary = []
                for rule in triggered_rules:
                    rule_summary.append(f"{rule['chain']} rule #{rule['rule_number']} ({rule['target']})")
                result['result'] = {
                    'status': 'allowed',
                    'reason': 'explicit_rules',
                    'description': f"Allowed by {len(triggered_rules)} firewall rule(s)",
                    'details': f"Allowing rules: {', '.join(rule_summary)}",
                    'rules_found': len(triggered_rules)
                }
        elif implicit_rules:
            # Allowed by implicit return from custom chains
            result['result'] = {
                'status': 'allowed',
                'reason': 'implicit_return',
                'description': f"Allowed by FORWARD chain default ACCEPT policy after implicit RETURN",
                'details': f"No rules matched in custom chain(s), packets returned to FORWARD chain via implicit RETURN and were allowed by FORWARD default ACCEPT policy",
                'rules_found': 0
            }
        else:
            # Check if allowed by default policy
            # Find which chain likely allowed the packets
            chain_targets = {}
            for rule in all_triggered:
                if rule['target'] not in ['ACCEPT', 'DROP', 'REJECT', 'RETURN', 'LOG']:
                    chain_targets[rule['target']] = rule['chain']
            
            # Check policies of jumped-to chains
            allowing_chain = None
            for chain in chain_targets.keys():
                policy = after_policies.get(chain, '-')
                if policy == 'ACCEPT':
                    allowing_chain = chain
                    break
            
            # If no custom chain found, check FORWARD chain
            if not allowing_chain:
                forward_policy = after_policies.get('FORWARD', 'ACCEPT')
                if forward_policy == 'ACCEPT':
                    allowing_chain = 'FORWARD'
            
            if allowing_chain:
                # Allowed by default policy
                result['result'] = {
                    'status': 'allowed',
                    'reason': 'default_policy',
                    'description': f"Allowed by {allowing_chain} chain default ACCEPT policy",
                    'details': "No specific allowing rules found, packets accepted by chain default policy",
                    'rules_found': 0
                }
            else:
                # No allowing found (shouldn't happen in allowing mode)
                result['result'] = {
                    'status': 'unknown',
                    'reason': 'no_allowing_found',
                    'description': "No allowing rules or policies found",
                    'details': "Service succeeded but no firewall allowing detected",
                    'rules_found': 0
                }
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Analyze iptables packet counts')
    parser.add_argument('router_name', help='Name of the router')
    parser.add_argument('before_file', help='JSON file with before packet counts')
    parser.add_argument('after_file', help='JSON file with after packet counts')
    parser.add_argument('-m', '--mode', choices=['blocking', 'allowing'], default='blocking',
                       help='Analysis mode: blocking (find DROP/REJECT) or allowing (find ACCEPT)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    try:
        # Read before data
        with open(args.before_file, 'r') as f:
            before_data = json.load(f)
            
        # Read after data
        with open(args.after_file, 'r') as f:
            after_data = json.load(f)
            
        if args.verbose:
            print(f"Analyzing packet counts for router: {args.router_name}", file=sys.stderr)
            print(f"Before data keys: {list(before_data.keys())}", file=sys.stderr)
            print(f"After data keys: {list(after_data.keys())}", file=sys.stderr)
        
        # Compare packet counts
        result = compare_packet_counts(before_data, after_data, args.router_name, args.verbose, args.mode)
        
        if result:
            print(json.dumps(result))
        else:
            if args.verbose:
                print(f"No blocking rules triggered on {args.router_name}", file=sys.stderr)
        
    except Exception as e:
        if args.verbose:
            import traceback
            traceback.print_exc()
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()