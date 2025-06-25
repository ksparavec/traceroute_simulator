#!/usr/bin/env python3
"""
Sequential Network Connectivity and Path Tester

Tests connectivity and path analysis between routers using ICMP ping and/or MTR traceroute.
Tests one router at a time to avoid overwhelming the system. Supports any destination IP
(internal, external, or unknown) - follows routing tables and gateway behavior.

Features:
- ICMP ping connectivity testing (default)
- MTR traceroute path analysis with hop-by-hop data
- Combined testing with both ping and MTR
- Sequential testing to avoid network congestion
- Configurable verbosity and timing
- Supports any destination IP (follows routing)

Routing Behavior:
- Internal IPs: Routes according to configured routing tables
- External IPs: Gateway routers handle public IPs via default routes
- Unknown IPs: Follows default gateway or gets blackholed based on router type

Usage:
    # Test all routers with ping (default)
    python3 network_namespace_tester.py --all
    
    # Test all routers with MTR traceroute
    python3 network_namespace_tester.py --all --test-type mtr

    # Test specific source to any destination with both ping and MTR
    python3 network_namespace_tester.py -s 10.1.1.1 -d 8.8.8.8 --test-type both

    # Test path to external IP with MTR
    python3 network_namespace_tester.py -s 10.1.1.1 -d 1.1.1.1 --test-type mtr

Environment Variables:
    TRACEROUTE_SIMULATOR_FACTS - Directory containing router JSON facts files
"""

import argparse
import json
import os
import subprocess
import sys
import time
import ipaddress
from pathlib import Path
from typing import Dict, List, Tuple, Set


class SequentialConnectivityTester:
    """Sequential network connectivity testing for namespace simulation."""
    
    def __init__(self, verbose: int = 0, wait_time: float = 0.1, test_type: str = 'ping'):
        self.facts_dir = Path(os.environ.get('TRACEROUTE_SIMULATOR_FACTS', '/tmp/traceroute_test_output'))
        self.verbose = verbose
        self.wait_time = wait_time
        self.test_type = test_type
        
        self.routers = {}
        self.router_ips = {}  # router_name -> [list of IPs]
        self.ip_to_router = {}  # IP -> router_name
        self.gateway_routers = set()  # Gateway routers that can handle public IPs
        self.added_dummy_ips = set()  # Track IPs added to dummy interfaces
        
        self.total_tests = 0
        self.passed_tests = 0
        self.failed_tests = 0
        self.failed_pairs = []
        
    def load_facts(self):
        """Load all router facts and build IP mappings."""
        if not self.facts_dir.exists():
            raise FileNotFoundError(f"Facts directory not found: {self.facts_dir}")
            
        json_files = list(self.facts_dir.glob("*.json"))
        if not json_files:
            raise FileNotFoundError(f"No JSON files found in {self.facts_dir}")
            
        for json_file in json_files:
            router_name = json_file.stem
            with open(json_file, 'r') as f:
                facts = json.load(f)
                self.routers[router_name] = facts
                
                # Extract all IP addresses for this router
                interfaces = facts.get('network', {}).get('interfaces', [])
                router_ips = []
                
                for iface in interfaces:
                    if (iface.get('protocol') == 'kernel' and 
                        iface.get('scope') == 'link' and
                        iface.get('prefsrc')):
                        
                        ip = iface['prefsrc']
                        if not ip.startswith('127.'):  # Skip loopback
                            router_ips.append(ip)
                            self.ip_to_router[ip] = router_name
                            
                self.router_ips[router_name] = router_ips
                
                # Identify gateway routers using metadata.type field
                metadata = facts.get('metadata', {})
                if metadata.get('type') == 'gateway':
                    self.gateway_routers.add(router_name)
                    
        if self.verbose >= 1:
            print(f"Loaded {len(self.routers)} routers:")
            for router, ips in self.router_ips.items():
                location = "HQ" if router.startswith('hq-') else "Branch" if router.startswith('br-') else "DC"
                gateway_marker = " [GATEWAY]" if router in self.gateway_routers else ""
                print(f"  {router} ({location}): {', '.join(ips)}{gateway_marker}")
                
    def is_public_routable_ip(self, ip_str: str) -> bool:
        """Check if an IP address is publicly routable (not RFC 1918 or other private ranges)."""
        try:
            ip = ipaddress.IPv4Address(ip_str)
            
            # Check for documentation/test ranges (RFC 5737) FIRST
            # These are our test "public" IPs and should be treated as public
            doc_ranges = [
                ipaddress.IPv4Network('192.0.2.0/24'),    # TEST-NET-1
                ipaddress.IPv4Network('198.51.100.0/24'), # TEST-NET-2  
                ipaddress.IPv4Network('203.0.113.0/24'),  # TEST-NET-3
            ]
            
            for doc_range in doc_ranges:
                if ip in doc_range:
                    return True  # These are our test "public" IPs
            
            # Check for other non-routable ranges
            if (ip.is_loopback or ip.is_multicast or ip.is_reserved or 
                ip.is_unspecified or ip.is_link_local):
                return False
                
            # Check for private networks (RFC 1918)
            if ip.is_private:
                return False
                    
            # For real public IPs, return True
            return True
            
        except ipaddress.AddressValueError:
            return False
            
    def add_public_ip_to_gateways(self, public_ip: str):
        """Add public IP to gateways - simple approach that works."""
        if not self.is_public_routable_ip(public_ip):
            return
            
        if public_ip in self.added_dummy_ips:
            return  # Already added
            
        if self.verbose >= 2:
            print(f"Setting up public IP {public_ip} on gateways...")
            
        # Simple approach: Add the public IP to all gateway routers
        # This simulates that the public IP is reachable from any internet gateway
        for gateway_router in self.gateway_routers:
            try:
                dummy_name = f"dummy-{public_ip.replace('.', '-')}"
                subprocess.run(f"ip netns exec {gateway_router} ip link add {dummy_name} type dummy", 
                             shell=True, check=True, capture_output=True)
                subprocess.run(f"ip netns exec {gateway_router} ip addr add {public_ip}/32 dev {dummy_name}", 
                             shell=True, check=True, capture_output=True)
                subprocess.run(f"ip netns exec {gateway_router} ip link set {dummy_name} up", 
                             shell=True, check=True, capture_output=True)
                             
                if self.verbose >= 2:
                    print(f"  Added {public_ip} to {gateway_router}")
                    
            except subprocess.CalledProcessError as e:
                if self.verbose >= 1:
                    print(f"Warning: Failed to add {public_ip} to {gateway_router}: {e}")
                    
        self.added_dummy_ips.add(public_ip)
        
    def remove_public_ip_from_gateways(self, public_ip: str):
        """Remove public IP dummy interfaces from gateways."""
        if public_ip not in self.added_dummy_ips:
            return
            
        if self.verbose >= 2:
            print(f"Cleaning up public IP {public_ip} from gateways...")
            
        # Remove dummy interfaces from all gateways
        for gateway_router in self.gateway_routers:
            try:
                dummy_name = f"dummy-{public_ip.replace('.', '-')}"
                subprocess.run(f"ip netns exec {gateway_router} ip link del {dummy_name}", 
                             shell=True, check=False, capture_output=True)
                             
                if self.verbose >= 2:
                    print(f"  Removed {public_ip} from {gateway_router}")
                    
            except subprocess.CalledProcessError:
                pass  # Ignore errors during cleanup
                
        self.added_dummy_ips.discard(public_ip)
        
    def cleanup_all_added_ips(self):
        """Remove all added public IP dummy interfaces."""
        for public_ip in list(self.added_dummy_ips):
            self.remove_public_ip_from_gateways(public_ip)
                
    def ping_test(self, source_ip: str, dest_ip: str, timeout: int = 3) -> Tuple[bool, str, str]:
        """Perform ping test from source IP to destination IP.
        
        Allows any destination IP - follows routing tables and gateway behavior.
        
        Returns:
            Tuple[bool, str, str]: (success, summary, full_output)
        """
        source_router = self.ip_to_router.get(source_ip)
        
        if not source_router:
            return False, f"Source IP {source_ip} not found", ""
            
        # Allow any destination IP - let routing decide where packets go
        # Run ping from source router namespace
        cmd = f"ip netns exec {source_router} ping -c 1 -W {timeout} {dest_ip}"
        
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout+2
            )
            
            # Prepare full output with command and result
            full_output = f"Command: {cmd}\n"
            full_output += f"Exit code: {result.returncode}\n"
            if result.stdout.strip():
                full_output += f"STDOUT:\n{result.stdout.strip()}"
            if result.stderr.strip():
                full_output += f"\nSTDERR:\n{result.stderr.strip()}"
            
            if result.returncode == 0:
                # Extract RTT from ping output for summary
                for line in result.stdout.split('\n'):
                    if 'time=' in line and 'ms' in line:
                        time_part = line.split('time=')[-1]
                        rtt = time_part.split()[0]
                        return True, f"{rtt}", full_output
                return True, "Success", full_output
            else:
                # Parse common error messages for summary
                if "Destination Host Unreachable" in result.stdout:
                    summary = "Host unreachable"
                elif "Network is unreachable" in result.stdout:
                    summary = "Network unreachable"
                elif "timeout" in result.stdout.lower() or result.returncode == 1:
                    summary = "Timeout"
                else:
                    summary = f"Error {result.returncode}"
                    
                return False, summary, full_output
                    
        except subprocess.TimeoutExpired:
            timeout_output = f"Command: {cmd}\nExit code: timeout\nCommand timed out after {timeout+2} seconds"
            return False, "Command timeout", timeout_output
        except Exception as e:
            exception_output = f"Command: {cmd}\nExit code: exception\nException occurred: {str(e)}"
            return False, f"Exception: {str(e)[:50]}", exception_output
            
    def mtr_test(self, source_ip: str, dest_ip: str, timeout: int = 10) -> Tuple[bool, str, str]:
        """Perform MTR traceroute test from source IP to destination IP.
        
        Allows any destination IP - follows routing tables and gateway behavior.
        
        Returns:
            Tuple[bool, str, str]: (success, summary, full_output)
        """
        source_router = self.ip_to_router.get(source_ip)
        
        if not source_router:
            return False, f"Source IP {source_ip} not found", ""
            
        # Allow any destination IP - let routing decide where packets go
        # Run MTR from source router namespace
        cmd = f"ip netns exec {source_router} mtr --report --no-dns -c 1 {dest_ip}"
        
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout+2
            )
            
            # Prepare full output with command and result
            full_output = f"Command: {cmd}\n"
            full_output += f"Exit code: {result.returncode}\n"
            if result.stdout.strip():
                full_output += f"STDOUT:\n{result.stdout.strip()}"
            if result.stderr.strip():
                full_output += f"\nSTDERR:\n{result.stderr.strip()}"
            
            if result.returncode == 0:
                # Extract summary from MTR output
                lines = result.stdout.strip().split('\n')
                
                # Look for the final hop that shows the destination IP or last reachable hop
                final_hop_reached = False
                dest_reachable = False
                last_good_latency = None
                
                for line in lines:
                    # Skip header lines
                    if 'HOST:' in line or 'Start:' in line or not '|--' in line:
                        continue
                        
                    parts = line.split()
                    if len(parts) >= 4:
                        # Extract loss percentage (should be in format like "0.0%" or "100.0")
                        loss_found = False
                        for part in parts:
                            if '%' in part:
                                loss_percentage = part
                                loss_found = True
                                break
                        
                        if loss_found:
                            # Check if this line contains the destination IP
                            if dest_ip in line:
                                dest_reachable = (loss_percentage == '0.0%')
                                if dest_reachable:
                                    # Try to extract latency
                                    for i, part in enumerate(parts):
                                        if '%' in part and i + 3 < len(parts):
                                            try:
                                                latency = float(parts[i + 3])
                                                return True, f"{latency}ms", full_output
                                            except ValueError:
                                                pass
                                    return True, "Success", full_output
                                else:
                                    return False, f"Destination unreachable (Loss: {loss_percentage})", full_output
                            
                            # If not destination line, check if it's a reachable intermediate hop
                            elif loss_percentage == '0.0%':
                                final_hop_reached = True
                                # Try to extract latency for summary
                                for i, part in enumerate(parts):
                                    if '%' in part and i + 3 < len(parts):
                                        try:
                                            last_good_latency = float(parts[i + 3])
                                        except ValueError:
                                            pass
                
                # If we didn't find the destination IP in any line, but had reachable hops,
                # it means the destination is unreachable (blackholed)
                if final_hop_reached and not dest_reachable:
                    return False, "Destination unreachable (blackholed)", full_output
                
                # Fallback - if we can't parse properly but exit code is 0
                return False, "Path incomplete", full_output
            else:
                # Parse common error messages for summary
                if "mtr: command not found" in result.stderr:
                    summary = "MTR not installed"
                elif "Name or service not known" in result.stderr:
                    summary = "DNS resolution failed"
                elif "Network is unreachable" in result.stderr:
                    summary = "Network unreachable"
                elif result.returncode == 1:
                    summary = "MTR failed"
                else:
                    summary = f"Error {result.returncode}"
                    
                return False, summary, full_output
                    
        except subprocess.TimeoutExpired:
            timeout_output = f"Command: {cmd}\nExit code: timeout\nCommand timed out after {timeout+2} seconds"
            return False, "Command timeout", timeout_output
        except Exception as e:
            exception_output = f"Command: {cmd}\nExit code: exception\nException occurred: {str(e)}"
            return False, f"Exception: {str(e)[:50]}", exception_output
            
    def _handle_test_result(self, source_router: str, dest_router: str, source_ip: str, dest_ip: str,
                           success: bool, summary: str, full_output: str, test_type: str,
                           router_passed: int, router_failed: int) -> Tuple[int, int]:
        """Handle test result output and statistics."""
        # Handle verbosity levels  
        if self.verbose == 1:
            # -v: compact single line format
            status = f"PASS: {summary}" if success else f"FAIL: {summary}"
            dest_display = dest_router if dest_router else "external"
            print(f"    {source_router} ({source_ip}) -> {dest_display} ({dest_ip}) [{test_type}] {status}")
        elif self.verbose >= 2:
            # -vv: show full output
            print(f"\n    Testing {source_ip} → {dest_ip} [{test_type}]:")
            if full_output:
                # Indent each line of the full output
                indented_output = "\n".join([f"      {line}" for line in full_output.split("\n")])
                print(indented_output)
            else:
                print(f"      No output captured")
            
            status_symbol = "✓" if success else "✗"
            print(f"      {status_symbol} Result: {summary}")
        
        if success:
            self.passed_tests += 1
            router_passed += 1
        else:
            self.failed_tests += 1
            router_failed += 1
            self.failed_pairs.append((source_router, dest_router, source_ip, dest_ip, f"{test_type}: {summary}"))
            
        return router_passed, router_failed
            
    def test_router_to_all_others(self, source_router: str):
        """Test one router to all other routers with configurable verbosity."""
        source_ips = self.router_ips[source_router]
        other_routers = [r for r in self.routers.keys() if r != source_router]
        
        if self.verbose >= 1:
            print(f"\n=== Testing {source_router.upper()} ===")
            print(f"Source IPs: {', '.join(source_ips)}")
        
        router_passed = 0
        router_failed = 0
        
        for dest_router in sorted(other_routers):
            dest_ips = self.router_ips[dest_router]
            
            # Determine location relationship
            src_loc = "HQ" if source_router.startswith('hq-') else "Branch" if source_router.startswith('br-') else "DC"
            dst_loc = "HQ" if dest_router.startswith('hq-') else "Branch" if dest_router.startswith('br-') else "DC"
            relationship = "Intra-location" if src_loc == dst_loc else f"{src_loc}-to-{dst_loc}"
            
            if self.verbose >= 2:
                print(f"\n  → {dest_router} ({relationship})")
                print(f"    Target IPs: {', '.join(dest_ips)}")
            elif self.verbose == 1:
                print(f"\n  → {dest_router} ({relationship})")
            
            # Test from first source IP to all destination IPs
            source_ip = source_ips[0]  # Use first IP to keep it simple
            
            dest_results = []
            for dest_ip in dest_ips:
                # Run tests based on test_type
                if self.test_type in ['ping', 'both']:
                    self.total_tests += 1
                    success, summary, full_output = self.ping_test(source_ip, dest_ip)
                    dest_router_name = self.ip_to_router.get(dest_ip, "external")
                    router_passed, router_failed = self._handle_test_result(source_router, dest_router_name, source_ip, dest_ip, 
                                                                           success, summary, full_output, "PING", router_passed, router_failed)
                    
                    # Add wait time between tests
                    if self.wait_time > 0:
                        time.sleep(self.wait_time)
                
                if self.test_type in ['mtr', 'both']:
                    self.total_tests += 1
                    success, summary, full_output = self.mtr_test(source_ip, dest_ip)
                    dest_router_name = self.ip_to_router.get(dest_ip, "external")
                    router_passed, router_failed = self._handle_test_result(source_router, dest_router_name, source_ip, dest_ip, 
                                                                           success, summary, full_output, "MTR", router_passed, router_failed)
                    
                    # Add wait time between tests
                    if self.wait_time > 0:
                        time.sleep(self.wait_time)
                
        # Print summary for this source router (only with verbosity)
        if self.verbose >= 1:
            total_router_tests = router_passed + router_failed
            success_rate = (router_passed / total_router_tests * 100) if total_router_tests > 0 else 0
            print(f"\n  {source_router} Summary: {router_passed}/{total_router_tests} passed ({success_rate:.1f}%)")
            
            if router_failed > 0:
                print(f"  ⚠ {source_router} has {router_failed} failures - CRITICAL ISSUE!")
            
    def test_specific_pair(self, source_ip: str, dest_ip: str):
        """Test specific source to destination."""
        if self.verbose >= 1:
            print(f"\n=== Testing {source_ip} → {dest_ip} ===")
        
        source_router = self.ip_to_router.get(source_ip)
        dest_router = self.ip_to_router.get(dest_ip)  # May be None for external IPs
        
        if not source_router:
            if self.verbose >= 1:
                print(f"✗ Source IP {source_ip} not found in any router")
            return False
            
        # Add public IP to gateways if needed
        if self.is_public_routable_ip(dest_ip):
            self.add_public_ip_to_gateways(dest_ip)
            
        try:
            if self.verbose >= 1:
                print(f"Source router: {source_router}")
                if dest_router:
                    print(f"Destination router: {dest_router}")
                else:
                    public_marker = " [PUBLIC IP]" if self.is_public_routable_ip(dest_ip) else ""
                    print(f"Destination IP: {dest_ip} (external/unknown){public_marker}")
            
            overall_success = True
            
            # Run tests based on test_type
            if self.test_type in ['ping', 'both']:
                success, summary, full_output = self.ping_test(source_ip, dest_ip)
                
                if self.verbose >= 2:
                    print(f"\nFull PING output:")
                    if full_output:
                        # Indent each line of the full output
                        indented_output = "\n".join([f"  {line}" for line in full_output.split("\n")])
                        print(indented_output)
                    else:
                        print("  No output captured")
                
                if self.verbose == 1:
                    # -v: compact single line format
                    status = f"PASS: {summary}" if success else f"FAIL: {summary}"
                    dest_display = dest_router if dest_router else "external"
                    print(f"{source_router} ({source_ip}) -> {dest_display} ({dest_ip}) [PING] {status}")
                elif self.verbose >= 2:
                    # -vv: traditional format with pass/fail
                    if success:
                        print(f"\n✓ PING PASS: {summary}")
                    else:
                        print(f"\n✗ PING FAIL: {summary}")
                
                overall_success = overall_success and success
            
            if self.test_type in ['mtr', 'both']:
                success, summary, full_output = self.mtr_test(source_ip, dest_ip)
                
                if self.verbose >= 2:
                    print(f"\nFull MTR output:")
                    if full_output:
                        # Indent each line of the full output
                        indented_output = "\n".join([f"  {line}" for line in full_output.split("\n")])
                        print(indented_output)
                    else:
                        print("  No output captured")
                
                if self.verbose == 1:
                    # -v: compact single line format
                    status = f"PASS: {summary}" if success else f"FAIL: {summary}"
                    dest_display = dest_router if dest_router else "external"
                    print(f"{source_router} ({source_ip}) -> {dest_display} ({dest_ip}) [MTR] {status}")
                elif self.verbose >= 2:
                    # -vv: traditional format with pass/fail
                    if success:
                        print(f"\n✓ MTR PASS: {summary}")
                    else:
                        print(f"\n✗ MTR FAIL: {summary}")
                
                overall_success = overall_success and success
            
            return overall_success
            
        finally:
            # Clean up public IP if we added it
            if self.is_public_routable_ip(dest_ip):
                self.remove_public_ip_from_gateways(dest_ip)
            
    def test_all_connectivity(self):
        """Test all routers sequentially."""
        if self.verbose >= 1:
            print("\n" + "="*60)
            print("SEQUENTIAL NETWORK CONNECTIVITY TEST")
            print("="*60)
            print("Testing each router to all others, one router at a time...")
        
        all_routers = sorted(self.routers.keys())
        
        for i, source_router in enumerate(all_routers, 1):
            if self.verbose >= 1:
                print(f"\n[{i}/{len(all_routers)}] ", end="")
            self.test_router_to_all_others(source_router)
            
    def print_final_summary(self):
        """Print final test summary."""
        print("\n" + "="*60)
        print("FINAL CONNECTIVITY TEST SUMMARY")
        print("="*60)
        
        print(f"Total ping tests: {self.total_tests}")
        print(f"Passed: {self.passed_tests}")
        print(f"Failed: {self.failed_tests}")
        
        if self.total_tests > 0:
            success_rate = (self.passed_tests / self.total_tests) * 100
            print(f"Overall success rate: {success_rate:.1f}%")
            
        if self.failed_tests > 0:
            print(f"\n⚠ CRITICAL: {self.failed_tests} connectivity failures detected!")
            
            # Only show detailed failures in verbose mode
            if self.verbose >= 1:
                print(f"\nFailed connections:")
                
                # Group failures by router pair
                router_failures = {}
                for src_router, dst_router, src_ip, dst_ip, error in self.failed_pairs:
                    pair = f"{src_router} → {dst_router}"
                    if pair not in router_failures:
                        router_failures[pair] = []
                    router_failures[pair].append(f"{src_ip} → {dst_ip}: {error}")
                    
                for pair, failures in router_failures.items():
                    print(f"\n  {pair}:")
                    for failure in failures:
                        print(f"    ✗ {failure}")
            else:
                print(f"(Run with -v to see detailed failure information)")
                    
            print(f"\n⚠ Network has routing or configuration issues that must be fixed!")
            print(f"⚠ Every router must be able to ping every other router for proper functionality.")
            return False
        else:
            print(f"\n✓ SUCCESS: All routers can reach all other routers!")
            print(f"✓ Network connectivity is fully functional.")
            return True
            
    def run_tests(self, source_ip: str = None, dest_ip: str = None, test_all: bool = False):
        """Run the appropriate tests."""
        try:
            self.load_facts()
            
            if test_all:
                self.test_all_connectivity()
                return self.print_final_summary()
            elif source_ip and dest_ip:
                return self.test_specific_pair(source_ip, dest_ip)
            else:
                print("Error: Use --all for comprehensive test, or -s and -d for specific test")
                return False
                
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # Always clean up any remaining dummy IPs
            self.cleanup_all_added_ips()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sequential network connectivity tester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --all                                    # Test all routers with ping (default)
  %(prog)s --all --test-type mtr                    # Test all routers with MTR traceroute
  %(prog)s --all --test-type both                   # Test all routers with both ping and MTR
  %(prog)s --all -v                                 # With basic verbosity (OK/NOT OK)
  %(prog)s --all -vv                                # With full verbosity (detailed output)
  %(prog)s --all -v --wait 0.2                     # With 0.2s wait between tests
  %(prog)s -s 10.1.1.1 -d 10.2.1.1                # Test specific source to destination with ping
  %(prog)s -s 10.1.1.1 -d 8.8.8.8 --test-type mtr  # Test external IP with MTR traceroute
  %(prog)s -s 10.1.1.1 -d 1.1.1.1 --test-type both # Test any IP with both ping and MTR

Test types:
  ping       Default - ICMP ping connectivity test
  mtr        MTR traceroute path analysis with hop-by-hop data
  both       Run both ping and MTR tests for comprehensive analysis

Verbosity levels:
  (default)  Silent mode - only shows final summary
  -v         Basic mode - shows OK/NOT OK for each test
  -vv        Full mode - shows detailed command output

The comprehensive test (--all) performs:
- Tests each router to all other routers sequentially
- Configurable wait time between tests (default: 0.1s)
- Shows progress based on verbosity level
- Identifies any connectivity failures immediately
- Supports ping, MTR traceroute, or both test types
        """
    )
    
    parser.add_argument('-s', '--source', type=str, 
                       help='Source IP address')
    parser.add_argument('-d', '--destination', type=str,
                       help='Destination IP address')
    parser.add_argument('--all', action='store_true',
                       help='Test all routers sequentially (comprehensive)')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity: -v (show OK/NOT OK), -vv (show full details)')
    parser.add_argument('--wait', type=float, default=0.1,
                       help='Wait time between tests in seconds (default: 0.1)')
    parser.add_argument('--test-type', type=str, choices=['ping', 'mtr', 'both'], default='ping',
                       help='Test type: ping (default), mtr (traceroute), or both')
    
    args = parser.parse_args()
    
    # Check for root privileges (needed for namespace access)
    if os.geteuid() != 0:
        print("Error: This script requires root privileges to access network namespaces")
        print("Please run with sudo")
        sys.exit(1)
        
    # Validate arguments
    if not args.all and not (args.source and args.destination):
        parser.print_help()
        sys.exit(1)
        
    tester = SequentialConnectivityTester(args.verbose, args.wait, args.test_type)
    success = tester.run_tests(args.source, args.destination, args.all)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()