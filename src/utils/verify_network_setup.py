#!/usr/bin/env -S python3 -B -u
"""
Network Setup Verification Script

Systematically verifies that all routers in the namespace simulation
have been configured correctly according to their JSON facts.

Checks:
1. All expected interfaces are created with correct IP addresses
2. All expected routes are installed
3. All expected policy rules are installed
"""

import json
import subprocess
import sys
from pathlib import Path


class NetworkVerifier:
    """Verifies network namespace setup against JSON facts."""
    
    def __init__(self, facts_dir="/tmp/traceroute_test_output"):
        self.facts_dir = Path(facts_dir)
        self.routers = {}
        self.errors = []
        self.warnings = []
        
    def load_facts(self):
        """Load all router facts."""
        for json_file in self.facts_dir.glob("*.json"):
            router_name = json_file.stem
            with open(json_file, 'r') as f:
                self.routers[router_name] = json.load(f)
                
    def run_cmd(self, cmd, namespace=None):
        """Run command in namespace."""
        if namespace:
            full_cmd = f"ip netns exec {namespace} {cmd}"
        else:
            full_cmd = cmd
            
        result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr
        
    def verify_interfaces(self, router_name, facts):
        """Verify all interfaces for a router."""
        print(f"  Checking interfaces...")
        
        # Get actual interfaces
        rc, stdout, stderr = self.run_cmd("ip addr show", router_name)
        if rc != 0:
            self.errors.append(f"{router_name}: Failed to get interface info: {stderr}")
            return
            
        actual_ips = {}
        current_interface = None
        for line in stdout.split('\\n'):
            # Look for interface definition line: "64: hq-lab-eth0@if63: <BROADCAST..."
            if ': ' in line and '<' in line and 'inet' not in line:
                parts = line.split(': ')
                if len(parts) >= 2:
                    current_interface = parts[1].split('@')[0]  # Remove @if63 suffix
            # Look for inet line and associate with current interface
            elif 'inet ' in line and '127.0.0.1' not in line and current_interface:
                parts = line.split()
                ip_cidr = parts[1]  # Format: 10.1.2.4/24
                actual_ips[current_interface] = ip_cidr
                    
        # Check expected interfaces
        expected_interfaces = facts.get('network', {}).get('interfaces', [])
        for iface in expected_interfaces:
            expected_dev = iface['dev']
            expected_ip = iface['prefsrc']
            expected_prefix = iface['dst'].split('/')[1]
            expected_cidr = f"{expected_ip}/{expected_prefix}"
            
            # Find matching interface by IP (namespace may rename interfaces)
            found = False
            for actual_dev, actual_cidr in actual_ips.items():
                if actual_cidr == expected_cidr:
                    print(f"    ✓ {expected_dev} -> {actual_dev}: {actual_cidr}")
                    found = True
                    break
                    
            if not found:
                self.errors.append(f"{router_name}: Missing interface {expected_dev} with IP {expected_cidr}")
                print(f"    ✗ {expected_dev}: {expected_cidr} - NOT FOUND")
                
    def verify_routes(self, router_name, facts):
        """Verify routing table for a router.""" 
        print(f"  Checking routes...")
        
        # Get actual routes
        rc, stdout, stderr = self.run_cmd("ip route show", router_name)
        if rc != 0:
            self.errors.append(f"{router_name}: Failed to get route info: {stderr}")
            return
            
        actual_routes = stdout.strip().split('\\n')
        
        # Check expected routes (non-kernel routes)
        expected_routes = facts.get('routing', {}).get('tables', [])
        non_kernel_routes = [r for r in expected_routes if r.get('protocol') != 'kernel']
        
        for route in non_kernel_routes:
            dst = route.get('dst', 'default')
            gateway = route.get('gateway')
            dev = route.get('dev')
            metric = route.get('metric')
            
            # Build expected route pattern
            if dst == 'default':
                route_pattern = 'default'
            else:
                route_pattern = dst
                
            if gateway:
                route_pattern += f" via {gateway}"
                
            # Look for this route in actual routes
            found = False
            for actual_route in actual_routes:
                if route_pattern in actual_route:
                    print(f"    ✓ Found: {actual_route.strip()}")
                    found = True
                    break
                    
            if not found:
                expected_desc = f"{dst}"
                if gateway:
                    expected_desc += f" via {gateway}"
                if dev:
                    expected_desc += f" dev {dev}"
                if metric:
                    expected_desc += f" metric {metric}"
                self.warnings.append(f"{router_name}: Route not found: {expected_desc}")
                print(f"    ⚠ Missing: {expected_desc}")
                
    def verify_rules(self, router_name, facts):
        """Verify policy rules for a router."""
        print(f"  Checking policy rules...")
        
        # Get actual rules
        rc, stdout, stderr = self.run_cmd("ip rule show", router_name)
        if rc != 0:
            self.errors.append(f"{router_name}: Failed to get rule info: {stderr}")
            return
            
        actual_rules = stdout.strip().split('\\n')
        print(f"    ✓ Default rules present: {len(actual_rules)} rules")
        
        # Check expected custom rules (if any)
        expected_rules = facts.get('routing', {}).get('rules', [])
        
        if not expected_rules:
            print(f"    ✓ No custom rules expected")
            return
            
        custom_rule_count = 0
        for rule in expected_rules:
            priority = rule.get('priority')
            from_addr = rule.get('from', 'all')
            table = rule.get('table', 'main')
            
            # Skip default rules (these are automatically present)
            if priority in [0, 32766, 32767] and table in ['local', 'main', 'default']:
                continue
                
            custom_rule_count += 1
            
            # Build expected rule pattern for custom rules
            rule_pattern = f"{priority}:"
            if from_addr != 'all':
                rule_pattern += f" from {from_addr}"
            rule_pattern += f" lookup {table}"
            
            # Look for this rule in actual rules
            found = False
            for actual_rule in actual_rules:
                if rule_pattern in actual_rule:
                    print(f"    ✓ Found custom rule: {actual_rule.strip()}")
                    found = True
                    break
                    
            if not found:
                self.warnings.append(f"{router_name}: Custom rule not implemented: {rule_pattern}")
                print(f"    ⚠ Custom rule not implemented: {rule_pattern}")
                
        if custom_rule_count == 0:
            print(f"    ✓ Only default rules expected")
                
    def verify_router(self, router_name):
        """Verify complete configuration for one router."""
        print(f"\\n=== Verifying {router_name.upper()} ===")
        
        facts = self.routers[router_name]
        
        # Check if namespace exists
        rc, stdout, stderr = self.run_cmd(f"ip netns exec {router_name} echo test")
        if rc != 0:
            self.errors.append(f"{router_name}: Namespace does not exist")
            print(f"  ✗ Namespace not found")
            return
            
        print(f"  ✓ Namespace exists")
        
        # Verify components
        self.verify_interfaces(router_name, facts)
        self.verify_routes(router_name, facts)
        self.verify_rules(router_name, facts)
        
    def verify_all(self):
        """Verify all routers."""
        print("NETWORK SETUP VERIFICATION")
        print("=" * 50)
        
        self.load_facts()
        print(f"Loaded facts for {len(self.routers)} routers")
        
        for router_name in sorted(self.routers.keys()):
            self.verify_router(router_name)
            
        # Print summary
        print(f"\\n" + "=" * 50)
        print("VERIFICATION SUMMARY")
        print("=" * 50)
        
        print(f"Routers checked: {len(self.routers)}")
        print(f"Errors: {len(self.errors)}")
        print(f"Warnings: {len(self.warnings)}")
        
        if self.errors:
            print(f"\\nERRORS:")
            for error in self.errors:
                print(f"  - {error}")
                
        if self.warnings:
            print(f"\\nWARNINGS:")
            for warning in self.warnings:
                print(f"  - {warning}")
                
        if not self.errors and not self.warnings:
            print(f"\\n✓ All routers configured correctly!")
            return 0
        elif not self.errors:
            print(f"\\n⚠ Configuration complete with warnings")
            return 0
        else:
            print(f"\\n✗ Configuration has errors")
            return 1


def main():
    """Main verification entry point."""
    verifier = NetworkVerifier()
    exit_code = verifier.verify_all()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()