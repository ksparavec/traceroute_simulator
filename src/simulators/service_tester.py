#!/usr/bin/env python3
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
from typing import Optional, Tuple, Dict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.simulators.service_manager import ServiceClient, ServiceProtocol, ServiceConfig, ServiceManager
from src.core.exceptions import NetworkError, ConfigurationError


class ServiceTester:
    """Service tester with automatic namespace detection."""
    
    def __init__(self, facts_dir: str, verbose: int = 0):
        self.facts_dir = Path(facts_dir)
        self.verbose = verbose
        self.known_routers = self._load_known_routers()
        self.known_hosts = self._load_known_hosts()
        self.ip_to_namespace = self._build_ip_namespace_map()
        
    def _load_known_routers(self) -> set:
        """Load list of active routers from bridge registry."""
        routers = set()
        try:
            registry_file = Path("/tmp/traceroute_bridges_registry.json")
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
        hosts = {}
        try:
            host_registry_file = Path("/tmp/traceroute_hosts_registry.json")
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
        
    def _build_ip_namespace_map(self) -> Dict[str, str]:
        """Build a map of IP addresses to namespace names using bridge and host registries."""
        ip_map = {}
        
        # Get router IPs from bridge registry
        try:
            registry_file = Path("/tmp/traceroute_bridges_registry.json")
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
                                ip_map[ip] = router_name
                                if self.verbose >= 3:
                                    print(f"Found router IP {ip} in namespace {router_name}")
                    
                    # Get host IPs from bridge registry
                    hosts = bridge_info.get('hosts', {})
                    for host_name, host_info in hosts.items():
                        ip_address = host_info.get('ipv4', '')
                        if ip_address and '/' in ip_address:
                            ip = ip_address.split('/')[0]
                            if ip and ip != "127.0.0.1":
                                ip_map[ip] = host_name
                                if self.verbose >= 3:
                                    print(f"Found host IP {ip} in namespace {host_name}")
                                    
        except (json.JSONDecodeError, IOError) as e:
            if self.verbose >= 1:
                print(f"Warning: Error loading bridge registry: {e}")
        
        # Get additional host IPs from host registry (for secondary IPs)
        try:
            host_registry_file = Path("/tmp/traceroute_hosts_registry.json")
            if host_registry_file.exists():
                with open(host_registry_file, 'r') as f:
                    host_registry = json.load(f)
                
                for host_name, host_info in host_registry.items():
                    # Add primary IP (might override bridge registry, but should be same)
                    primary_ip = host_info.get('primary_ip', '')
                    if primary_ip and '/' in primary_ip:
                        ip = primary_ip.split('/')[0]
                        if ip and ip != "127.0.0.1":
                            ip_map[ip] = host_name
                            if self.verbose >= 3:
                                print(f"Found host primary IP {ip} in namespace {host_name}")
                    
                    # Add secondary IPs (only available in host registry)
                    secondary_ips = host_info.get('secondary_ips', [])
                    for secondary_ip in secondary_ips:
                        if secondary_ip and '/' in secondary_ip:
                            ip = secondary_ip.split('/')[0]
                            if ip and ip != "127.0.0.1":
                                ip_map[ip] = host_name
                                if self.verbose >= 3:
                                    print(f"Found host secondary IP {ip} in namespace {host_name}")
                                    
        except (json.JSONDecodeError, IOError) as e:
            if self.verbose >= 1:
                print(f"Warning: Error loading host registry: {e}")
                
        return ip_map
    
    def find_namespace_for_ip(self, ip: str) -> Optional[str]:
        """Find namespace that owns the given IP address."""
        return self.ip_to_namespace.get(ip)
    
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
        message: str = "Test"
    ) -> Tuple[bool, str]:
        """Test service connectivity."""
        # Parse endpoints
        src_ip, src_port = self.parse_endpoint(source_endpoint)
        dest_ip, dest_port = self.parse_endpoint(dest_endpoint)
        
        if not dest_port:
            raise ValueError("Destination port is required (use -d ip:port)")
            
        # Find source namespace
        src_namespace = self.find_namespace_for_ip(src_ip)
        if not src_namespace:
            # Try host namespace
            src_namespace = None
            if self.verbose >= 1:
                print(f"Source IP {src_ip} not found in any namespace, using host")
        else:
            if self.verbose >= 1:
                print(f"Source IP {src_ip} belongs to namespace: {src_namespace}")
        
        # Create client and test
        client = ServiceClient(self.verbose)
        return client.test_service(
            src_namespace or "host",
            dest_ip,
            dest_port,
            ServiceProtocol(protocol.lower()),
            message
        )
    
    def start_service(
        self,
        endpoint: str,
        protocol: str = "tcp",
        name: Optional[str] = None
    ) -> None:
        """Start a service at the given endpoint."""
        ip, port = self.parse_endpoint(endpoint)
        
        if not port:
            raise ValueError("Port is required for starting service (use ip:port)")
            
        # Find namespace for IP
        namespace = self.find_namespace_for_ip(ip)
        if not namespace:
            raise ConfigurationError(
                f"Cannot start service: IP {ip} not found in any namespace",
                "Check IP address or ensure namespace simulation is set up"
            )
            
        # Create service config
        config = ServiceConfig(
            name=name or f"svc-{port}",
            port=port,
            protocol=ServiceProtocol(protocol.lower()),
            namespace=namespace,
            bind_address=ip
        )
        
        # Start service
        manager = ServiceManager(self.verbose)
        manager.start_service(config)
        
        if self.verbose >= 1:
            print(f"Service started on {ip}:{port}/{protocol} in namespace {namespace}")
    
    def stop_service(self, endpoint: str) -> None:
        """Stop a service at the given endpoint."""
        ip, port = self.parse_endpoint(endpoint)
        
        if not port:
            raise ValueError("Port is required for stopping service (use ip:port)")
            
        # Find namespace for IP
        namespace = self.find_namespace_for_ip(ip)
        if not namespace:
            raise ConfigurationError(
                f"Cannot stop service: IP {ip} not found in any namespace",
                "Check IP address or ensure namespace simulation is set up"
            )
            
        # Load service registry to find the service name
        registry_file = Path("/tmp/traceroute_services_registry.json")
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
            raise ConfigurationError(
                f"No service found on {ip}:{port}",
                f"Check if service is running with 'make svclist'"
            )
            
        # Stop the service
        manager = ServiceManager(self.verbose)
        manager.stop_service(namespace, service_name, port, service_protocol)
        
        if self.verbose >= 1:
            print(f"Service stopped on {ip}:{port} in namespace {namespace}")


def main():
    parser = argparse.ArgumentParser(
        description="Test services with automatic namespace detection"
    )
    
    # Connection test mode
    parser.add_argument('-s', '--source', help='Source IP[:port]')
    parser.add_argument('-d', '--dest', help='Destination IP:port')
    parser.add_argument('-p', '--protocol', choices=['tcp', 'udp'], default='tcp',
                       help='Protocol type (default: tcp)')
    parser.add_argument('-m', '--message', default='Test', help='Test message')
    
    # Service start mode
    parser.add_argument('--start', help='Start service at IP:port')
    parser.add_argument('--name', help='Service name (for --start)')
    
    # Service stop mode
    parser.add_argument('--stop', help='Stop service at IP:port')
    
    # Common options
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity')
    
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
            success, response = tester.test_service(
                args.source,
                args.dest,
                args.protocol,
                args.message
            )
            
            if success:
                if args.verbose >= 1:
                    print(f"Success: {response}")
                return 0
            else:
                if args.verbose >= 1:
                    print(f"Failed: {response}")
                else:
                    # Even in silent mode, print error to stderr
                    print(f"Failed: {response}", file=sys.stderr)
                return 1
        else:
            parser.print_help()
            return 2
            
    except Exception as e:
        # Check if it's a service-related error (should return 1) vs configuration error (should return 2)
        from src.simulators.service_manager import ServiceError
        
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