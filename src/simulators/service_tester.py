#!/usr/bin/env -S python3 -B -u
"""
Service Tester with IP-based Interface

This script provides a simplified interface for testing services that matches
the nettest pattern. Users specify source and destination IPs, and the script
automatically determines the appropriate namespaces.

Usage:
    service_tester.py -s <source_ip[:port]> -d <dest_ip:port> [-p tcp|udp] [-v]
"""

import os
import sys
import json
import argparse
import subprocess
import re
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Set

# Use absolute imports for installed package
from tsim.simulators.service_manager import ServiceClient, ServiceProtocol, ServiceConfig, ServiceManager
from tsim.core.exceptions import NetworkError, ConfigurationError
from tsim.core.config_loader import get_registry_paths


class ServiceTester:
    """Service tester with automatic namespace detection."""
    
    def __init__(self, facts_dir: str, verbose: int = 0):
        self.facts_dir = Path(facts_dir)
        self.verbose = verbose
        self.known_routers = self._load_known_routers()
        self.known_hosts = self._load_known_hosts()
        self.ip_to_namespaces = self._build_ip_namespace_map()  # Now returns Dict[str, List[str]]
        
    def _load_known_routers(self) -> set:
        """Load list of active routers from bridge registry."""
        # Load registry paths
        registry_paths = get_registry_paths()
        
        routers = set()
        try:
            registry_file = Path(registry_paths['bridges'])
            if registry_file.exists():
                with open(registry_file, 'r') as f:
                    bridge_registry = json.load(f)
                
                for bridge_name, bridge_info in bridge_registry.items():
                    router_data = bridge_info.get('routers', {})
                    for router_name in router_data.keys():
                        routers.add(router_name)
                        
        except (json.JSONDecodeError, IOError) as e:
            if self.verbose >= 1:
                print(f"Warning: Error loading bridge registry: {e}")
        
        return routers
        
    def _load_known_hosts(self) -> Dict[str, Dict]:
        """Load registered hosts from host registry."""
        # Load registry paths
        registry_paths = get_registry_paths()
        
        hosts = {}
        try:
            host_registry_file = Path(registry_paths['hosts'])
            if host_registry_file.exists():
                with open(host_registry_file, 'r') as f:
                    hosts = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            if self.verbose >= 1:
                print(f"Warning: Error loading host registry: {e}")
        
        return hosts
        
    def _is_user_namespace(self, namespace: str) -> bool:
        """Check if namespace is a known router or host (not a system namespace)."""
        return namespace in self.known_routers or namespace in self.known_hosts
        
    def _build_ip_namespace_map(self) -> Dict[str, List[str]]:
        """Build a map of IP addresses to list of namespace names using bridge and host registries."""
        ip_map: Dict[str, List[str]] = {}
        
        # Get router IPs from bridge registry
        try:
            # Load registry paths
            registry_paths = get_registry_paths()
            registry_file = Path(registry_paths['bridges'])
            if registry_file.exists():
                with open(registry_file, 'r') as f:
                    bridge_registry = json.load(f)
                
                for bridge_name, bridge_info in bridge_registry.items():
                    # Get router IPs
                    routers = bridge_info.get('routers', {})
                    for router_name, router_info in routers.items():
                        ip_address = router_info.get('ipv4', '')
                        if ip_address and '/' in ip_address:
                            ip = ip_address.split('/')[0]
                            if ip and ip != "127.0.0.1":
                                if ip not in ip_map:
                                    ip_map[ip] = []
                                if router_name not in ip_map[ip]:
                                    ip_map[ip].append(router_name)
                                if self.verbose >= 3:
                                    print(f"Found router IP {ip} in namespace {router_name}")
                    
                    # Get host IPs from bridge registry
                    hosts = bridge_info.get('hosts', {})
                    for host_name, host_info in hosts.items():
                        ip_address = host_info.get('ipv4', '')
                        if ip_address and '/' in ip_address:
                            ip = ip_address.split('/')[0]
                            if ip and ip != "127.0.0.1":
                                if ip not in ip_map:
                                    ip_map[ip] = []
                                if host_name not in ip_map[ip]:
                                    ip_map[ip].append(host_name)
                                if self.verbose >= 3:
                                    print(f"Found host IP {ip} in namespace {host_name}")
                                    
        except (json.JSONDecodeError, IOError) as e:
            if self.verbose >= 1:
                print(f"Warning: Error loading bridge registry: {e}")
        
        # Get additional host IPs from host registry (for secondary IPs)
        try:
            host_registry_file = Path(registry_paths['hosts'])
            if host_registry_file.exists():
                with open(host_registry_file, 'r') as f:
                    host_registry = json.load(f)
                
                for host_name, host_info in host_registry.items():
                    # Add primary IP (might override bridge registry, but should be same)
                    primary_ip = host_info.get('primary_ip', '')
                    if primary_ip and '/' in primary_ip:
                        ip = primary_ip.split('/')[0]
                        if ip and ip != "127.0.0.1":
                            if ip not in ip_map:
                                ip_map[ip] = []
                            if host_name not in ip_map[ip]:
                                ip_map[ip].append(host_name)
                            if self.verbose >= 3:
                                print(f"Found host primary IP {ip} in namespace {host_name}")
                    
                    # Add secondary IPs (only available in host registry)
                    secondary_ips = host_info.get('secondary_ips', [])
                    for secondary_ip in secondary_ips:
                        if secondary_ip and '/' in secondary_ip:
                            ip = secondary_ip.split('/')[0]
                            if ip and ip != "127.0.0.1":
                                if ip not in ip_map:
                                    ip_map[ip] = []
                                if host_name not in ip_map[ip]:
                                    ip_map[ip].append(host_name)
                                if self.verbose >= 3:
                                    print(f"Found host secondary IP {ip} in namespace {host_name}")
                                    
        except (json.JSONDecodeError, IOError) as e:
            if self.verbose >= 1:
                print(f"Warning: Error loading host registry: {e}")
                
        return ip_map
    
    def find_namespaces_for_ip(self, ip: str) -> List[str]:
        """Find all namespaces that own the given IP address."""
        return self.ip_to_namespaces.get(ip, [])
    
    def _get_next_hop_router(self, src_namespace: str, dest_ip: str) -> str:
        """Get the next hop router from source namespace to destination IP."""
        # For hosts, check the host registry for connected router
        if src_namespace in self.known_hosts:
            host_info = self.known_hosts.get(src_namespace, {})
            connected_to = host_info.get('connected_to', 'unknown')
            return connected_to
        
        # For routers, would need routing table lookup
        if src_namespace in self.known_routers:
            return f"{src_namespace}"
            
        return "unknown"
    
    def _get_router_interfaces(self, src_namespace: str, dest_namespace: str) -> Tuple[str, str]:
        """Get incoming and outgoing interfaces on router for the path."""
        incoming_iface = "unknown"
        outgoing_iface = "unknown"
        
        # Incoming interface from source host entry
        if src_namespace in self.known_hosts:
            src_info = self.known_hosts.get(src_namespace, {})
            incoming_iface = src_info.get('router_interface', 'unknown')
        
        # Outgoing interface from destination host entry
        if dest_namespace in self.known_hosts:
            dest_info = self.known_hosts.get(dest_namespace, {})
            outgoing_iface = dest_info.get('router_interface', 'unknown')
            
        return incoming_iface, outgoing_iface
    
    def parse_endpoint(self, endpoint: str) -> Tuple[str, Optional[int]]:
        """Parse endpoint in format ip[:port]."""
        if ':' in endpoint:
            parts = endpoint.rsplit(':', 1)
            try:
                return parts[0], int(parts[1])
            except ValueError:
                raise ValueError(f"Invalid port number in {endpoint}")
        return endpoint, None
    
    def test_service(
        self,
        source_endpoint: str,
        dest_endpoint: str,
        protocol: str = "tcp",
        message: str = "Test",
        timeout: int = 5,
        json_output: bool = False
    ) -> Tuple[bool, str, Optional[List[Dict]]]:
        """Test service connectivity from all source namespaces to all destination services."""
        # Parse endpoints
        src_ip, src_port = self.parse_endpoint(source_endpoint)
        dest_ip, dest_port = self.parse_endpoint(dest_endpoint)
        
        if not dest_port:
            raise ValueError("Destination port is required (use -d ip:port)")
            
        # Find source namespaces
        src_namespaces = self.find_namespaces_for_ip(src_ip)
        if not src_namespaces:
            # Use host namespace if IP not found
            src_namespaces = ["host"]
            if self.verbose >= 1 and not json_output:
                print(f"Source IP {src_ip} not found in any namespace, using host")
        else:
            # Sort source namespaces for consistent pairing
            src_namespaces.sort()
            if len(src_namespaces) > 1 and self.verbose >= 1 and not json_output:
                print(f"Source IP {src_ip} found in {len(src_namespaces)} namespaces: {', '.join(src_namespaces)}")
        
        # Find destination namespaces (to get all services with this IP)
        dest_namespaces = self.find_namespaces_for_ip(dest_ip)
        if not dest_namespaces:
            if self.verbose >= 1 and not json_output:
                print(f"Destination IP {dest_ip} not found in any namespace")
            # If no destination namespaces found, we'll test to the IP directly
            dest_namespaces = [None]  # Placeholder for direct IP testing
        else:
            # Sort destination namespaces for consistent pairing
            dest_namespaces.sort()
            if len(dest_namespaces) > 1 and self.verbose >= 1 and not json_output:
                print(f"Destination IP {dest_ip} found in {len(dest_namespaces)} namespaces: {', '.join(dest_namespaces)}")
        
        # Create client
        client = ServiceClient(self.verbose if not json_output else 0)
        
        # Track test results
        test_results = []
        successful_tests = 0
        failed_tests = 0
        
        # Ensure we have matching pairs - only test corresponding indices
        num_tests = min(len(src_namespaces), len(dest_namespaces))
        if len(src_namespaces) != len(dest_namespaces) and self.verbose >= 1 and not json_output:
            print(f"Warning: Unequal number of source ({len(src_namespaces)}) and destination ({len(dest_namespaces)}) namespaces")
            print(f"Will only test {num_tests} matching pairs")
        
        # Print table header in verbose mode
        if self.verbose >= 1 and not json_output:
            print()  # Empty line before table
            # Calculate column widths for alignment
            max_src_len = max(len(f"{ns} {src_ip}:ephemeral/{protocol}") for ns in src_namespaces[:num_tests])
            max_dst_len = max(len(f"{dest_namespaces[i] if i < len(dest_namespaces) else 'unknown'} {dest_ip}:{dest_port}/{protocol}") 
                            for i in range(num_tests))
            max_router_len = 15  # Reasonable width for router names
            
            # Print header with extra spacing
            print(f"{'Source':<{max_src_len}}  ->  {'Destination':<{max_dst_len}}  {'via Router (in -> out)':<{max_router_len + 20}}  : Status")
            print("-" * (max_src_len + max_dst_len + max_router_len + 40))
        
        # Test only matching pairs (same index)
        for i in range(num_tests):
            src_namespace = src_namespaces[i]
            dest_namespace = dest_namespaces[i] if dest_namespaces[i] else "unknown"
            # Default source port before test
            if not src_port:
                src_port_used = "ephemeral"
            else:
                src_port_used = src_port
            
            try:
                success, response = client.test_service(
                    src_namespace,
                    dest_ip,
                    dest_port,
                    ServiceProtocol(protocol.lower()),
                    message,
                    timeout
                )
                # Try to parse actual local port from response marker
                try:
                    import re as _re
                    m = _re.search(r"LOCAL_PORT:(\d+)", response or "")
                    if m:
                        src_port_used = int(m.group(1))
                except Exception:
                    pass
                
                # Determine the router used for this path
                via_router = self._get_next_hop_router(src_namespace, dest_ip)
                incoming_iface, outgoing_iface = self._get_router_interfaces(src_namespace, dest_namespace)
                
                # Build detailed result
                result = {
                    'source_host': src_namespace,
                    'source_ip': src_ip,
                    'source_port': src_port_used,
                    'protocol': protocol,
                    'destination_host': dest_namespace,
                    'destination_ip': dest_ip,
                    'destination_port': dest_port,
                    'via_router': via_router,
                    'incoming_interface': incoming_iface,
                    'outgoing_interface': outgoing_iface,
                    'status': 'OK' if success else 'FAIL',
                    'message': response
                }
                
                test_results.append(result)
                
                if success:
                    successful_tests += 1
                else:
                    failed_tests += 1
                
                # Output is handled after all tests complete
                    
            except Exception as e:
                failed_tests += 1
                # Still get router info for failed tests
                via_router = self._get_next_hop_router(src_namespace, dest_ip)
                incoming_iface, outgoing_iface = self._get_router_interfaces(src_namespace, dest_namespace)
                
                # Even on error, try to parse local port
                try:
                    import re as _re
                    m = _re.search(r"LOCAL_PORT:(\d+)", str(e))
                    if m:
                        src_port_used = int(m.group(1))
                except Exception:
                    pass
                result = {
                    'source_host': src_namespace,
                    'source_ip': src_ip,
                    'source_port': src_port_used,
                    'protocol': protocol,
                    'destination_host': dest_namespace,
                    'destination_ip': dest_ip,
                    'destination_port': dest_port,
                    'via_router': via_router,
                    'incoming_interface': incoming_iface,
                    'outgoing_interface': outgoing_iface,
                    'status': 'FAIL',
                    'message': str(e)
                }
                test_results.append(result)
                
                # Output is handled after all tests complete
        
        # Print test results table in verbose mode
        if self.verbose >= 1 and not json_output and test_results:
            # Use the same column widths calculated earlier
            max_src_len = max(len(f"{r['source_host']} {r['source_ip']}:{r['source_port']}/{r['protocol']}") for r in test_results)
            max_dst_len = max(len(f"{r['destination_host']} {r['destination_ip']}:{r['destination_port']}/{r['protocol']}") for r in test_results)
            max_router_len = max(len(r.get('via_router', 'unknown')) for r in test_results)
            max_router_len = max(max_router_len, 15)  # Minimum width
            
            for result in test_results:
                src_str = f"{result['source_host']} {result['source_ip']}:{result['source_port']}/{result['protocol']}"
                dst_str = f"{result['destination_host']} {result['destination_ip']}:{result['destination_port']}/{result['protocol']}"
                router = result.get('via_router', 'unknown')
                status = result['status']
                
                # Add interface info to router column
                incoming = result.get('incoming_interface', 'unknown')
                outgoing = result.get('outgoing_interface', 'unknown')
                router_with_ifaces = f"{router} ({incoming} -> {outgoing})"
                
                print(f"{src_str:<{max_src_len}}  ->  {dst_str:<{max_dst_len}}  {router_with_ifaces:<{max_router_len + 20}}  : {status}")
                
                if self.verbose >= 2 and result['message']:
                    print(f"{'':>{max_src_len}}      {'':>{max_dst_len}}  {'':>{max_router_len + 20}}    Message: {result['message']}")
        
        # Prepare return values
        if json_output:
            # Return raw data for JSON formatting
            overall_success = successful_tests > 0
            summary = {
                'total_tests': num_tests,
                'successful': successful_tests,
                'failed': failed_tests,
                'overall_status': 'OK' if overall_success else 'FAIL'
            }
            return overall_success, json.dumps({'summary': summary, 'tests': test_results}, indent=2), test_results
        else:
            # Simple summary: X/Y tests succeeded
            summary = f"{successful_tests}/{num_tests} tests succeeded"
            overall_success = successful_tests > 0
            return overall_success, summary, None
    
    def start_service(
        self,
        endpoint: str,
        protocol: str = "tcp",
        name: Optional[str] = None
    ) -> None:
        """Start a service at the given endpoint on all namespaces that have this IP."""
        ip, port = self.parse_endpoint(endpoint)
        
        if not port:
            raise ValueError("Port is required for starting service (use ip:port)")
            
        # Find all namespaces for IP
        namespaces = self.find_namespaces_for_ip(ip)
        if not namespaces:
            raise ConfigurationError(
                f"Cannot start service: IP {ip} not found in any namespace",
                "Check IP address or ensure namespace simulation is set up"
            )
        
        # Create and start service on each namespace
        manager = ServiceManager(self.verbose)
        started_count = 0
        failed_namespaces = []
        
        for idx, namespace in enumerate(namespaces):
            # Create unique name if multiple namespaces
            service_name = name or f"svc-{port}"
            if len(namespaces) > 1:
                service_name = f"{service_name}-{namespace}"
            
            # Create service config
            config = ServiceConfig(
                name=service_name,
                port=port,
                protocol=ServiceProtocol(protocol.lower()),
                namespace=namespace,
                bind_address=ip
            )
            
            try:
                # Start service
                manager.start_service(config)
                started_count += 1
                
                if self.verbose >= 1:
                    print(f"Service started on {ip}:{port}/{protocol} in namespace {namespace}")
            except Exception as e:
                failed_namespaces.append((namespace, str(e)))
                if self.verbose >= 1:
                    print(f"Failed to start service in namespace {namespace}: {e}")
        
        # Report results
        if started_count == 0:
            raise ConfigurationError(
                f"Failed to start service on any namespace",
                f"All {len(namespaces)} namespace(s) failed"
            )
        elif failed_namespaces and self.verbose >= 1:
            print(f"\nStarted service on {started_count}/{len(namespaces)} namespace(s)")
            for ns, err in failed_namespaces:
                print(f"  Failed on {ns}: {err}")
    
    def stop_service(self, endpoint: str) -> None:
        """Stop services at the given endpoint on all namespaces."""
        ip, port = self.parse_endpoint(endpoint)
        
        if not port:
            raise ValueError("Port is required for stopping service (use ip:port)")
            
        # Find all namespaces for IP
        namespaces = self.find_namespaces_for_ip(ip)
        if not namespaces:
            raise ConfigurationError(
                f"Cannot stop service: IP {ip} not found in any namespace",
                "Check IP address or ensure namespace simulation is set up"
            )
            
        # Load service registry to find the service names
        # Load registry paths
        registry_paths = get_registry_paths()
        registry_file = Path(registry_paths['services'])
        if not registry_file.exists():
            raise ConfigurationError(
                "No services found",
                "Service registry is empty"
            )
            
        try:
            with open(registry_file, 'r') as f:
                registry = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigurationError(
                "Failed to read service registry",
                str(e)
            )
        
        # Find and stop services on all matching namespaces
        manager = ServiceManager(self.verbose)
        stopped_count = 0
        failed_namespaces = []
        not_found_namespaces = []
        
        for namespace in namespaces:
            # Find service with matching namespace, IP and port
            service_found = False
            service_name = None
            service_protocol = None
            
            for key, config in registry.items():
                if (config.get('namespace') == namespace and 
                    config.get('bind_address') == ip and 
                    config.get('port') == port):
                    service_found = True
                    service_name = config.get('name', f'svc-{port}')
                    service_protocol = config.get('protocol', 'tcp')
                    break
            
            if not service_found:
                not_found_namespaces.append(namespace)
                if self.verbose >= 2:
                    print(f"No service found on {ip}:{port} in namespace {namespace}")
                continue
            
            try:
                # Stop the service
                manager.stop_service(namespace, service_name, port, service_protocol)
                stopped_count += 1
                
                if self.verbose >= 1:
                    print(f"Service stopped on {ip}:{port} in namespace {namespace}")
            except Exception as e:
                failed_namespaces.append((namespace, str(e)))
                if self.verbose >= 1:
                    print(f"Failed to stop service in namespace {namespace}: {e}")
        
        # Report results
        if stopped_count == 0:
            if not_found_namespaces:
                raise ConfigurationError(
                    f"No services found on {ip}:{port}",
                    f"Service not running on any of the {len(namespaces)} namespace(s)"
                )
            else:
                raise ConfigurationError(
                    f"Failed to stop service on any namespace",
                    f"All {len(namespaces)} namespace(s) failed"
                )
        elif (failed_namespaces or not_found_namespaces) and self.verbose >= 1:
            print(f"\nStopped service on {stopped_count}/{len(namespaces)} namespace(s)")
            for ns in not_found_namespaces:
                print(f"  Not found on {ns}")
            for ns, err in failed_namespaces:
                print(f"  Failed on {ns}: {err}")


def main():
    parser = argparse.ArgumentParser(
        description="Test services with automatic namespace detection"
    )
    
    # Connection test mode
    parser.add_argument('-s', '--source', help='Source IP[:port] (port is optional)')
    parser.add_argument('-d', '--dest', help='Destination IP:port (port is required)')
    parser.add_argument('-p', '--protocol', choices=['tcp', 'udp'], default='tcp',
                       help='Protocol type (default: tcp)')
    parser.add_argument('-m', '--message', default='Test', help='Test message')
    parser.add_argument('--timeout', type=int, default=5, help='Connection timeout in seconds')
    
    # Service start mode
    parser.add_argument('--start', help='Start service at IP:port')
    parser.add_argument('--name', help='Service name (for --start)')
    
    # Service stop mode
    parser.add_argument('--stop', help='Stop service at IP:port')
    
    # Common options
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity')
    parser.add_argument('-j', '--json', action='store_true',
                       help='Output results in JSON format')
    
    args = parser.parse_args()
    
    # Determine facts directory
    facts_dir = os.environ.get('TRACEROUTE_SIMULATOR_FACTS')
    if not facts_dir:
        print("Error: TRACEROUTE_SIMULATOR_FACTS environment variable must be set")
        sys.exit(1)
    
    if not os.path.exists(facts_dir):
        print(f"Error: Facts directory not found: {facts_dir}")
        print("Run 'make netsetup' first to create namespace simulation")
        return 2
        
    tester = ServiceTester(facts_dir, args.verbose)
    
    try:
        if args.start:
            # Start service mode
            tester.start_service(args.start, args.protocol, args.name)
            
        elif args.stop:
            # Stop service mode
            tester.stop_service(args.stop)
            
        elif args.source and args.dest:
            # Test mode
            success, response, raw_results = tester.test_service(
                args.source,
                args.dest,
                args.protocol,
                args.message,
                args.timeout,
                args.json
            )
            
            if args.json:
                # JSON output - just print the response (already formatted)
                print(response)
            else:
                # Text output - show summary
                if not args.verbose:
                    print(f"\nResult: {response}")
                else:
                    # Verbose mode shows detailed output inline, just add summary
                    print(f"\nSummary: {response}")
            
            return 0 if success else 1
        else:
            parser.print_help()
            return 2
            
    except Exception as e:
        # Check if it's a service-related error (should return 1) vs configuration error (should return 2)
        from .service_manager import ServiceError
        
        if isinstance(e, ServiceError):
            exit_code = 1  # Service operation failed
        else:
            exit_code = 2  # Configuration or system error
            
        if args.verbose >= 2:
            import traceback
            traceback.print_exc()
        elif args.verbose >= 1:
            print(f"Error: {e}")
        else:
            # In silent mode, print minimal error to stderr
            print(f"Error: {e}", file=sys.stderr)
        return exit_code


if __name__ == "__main__":
    sys.exit(main())
