#!/usr/bin/env python3
"""
Service Manager for Network Namespace Simulation

This module provides service management capabilities for routers and hosts
in the namespace simulation. Services are implemented using netcat (nc) for 
simplicity and availability.

Key Features:
- TCP and UDP echo services
- Multiple simultaneous client support
- Persistent services with proper lifecycle management
- Comprehensive error handling and logging
- Integration with existing namespace infrastructure
"""

import os
import sys
import json
import subprocess
import time
import signal
import psutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import socket

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.exceptions import (
    ExecutionError, NetworkError, ValidationError, 
    PortValidationError, ConfigurationError, ErrorHandler
)
from src.core.models import IptablesRule
from src.core.structured_logging import get_logger, setup_logging


class ServiceProtocol(str, Enum):
    """Supported service protocols."""
    TCP = "tcp"
    UDP = "udp"


class ServiceStatus(str, Enum):
    """Service operational status."""
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ServiceError(NetworkError):
    """Base class for service-related errors."""
    pass


class ServiceStartError(ServiceError):
    """Raised when service fails to start."""
    
    def __init__(self, service_name: str, reason: str, **kwargs):
        super().__init__(
            message=f"Failed to start service '{service_name}': {reason}",
            **kwargs
        )
        self.suggestion = (
            f"Service startup failed: {reason}\n"
            "Check:\n"
            "  1. Port is not already in use\n"
            "  2. socat is installed (apt-get install socat)\n"
            "  3. Namespace exists and is accessible\n"
            "  4. No firewall rules blocking the port"
        )


class ServiceConnectionError(ServiceError):
    """Raised when connection to service fails."""
    
    def __init__(self, host: str, port: int, protocol: str, reason: str, **kwargs):
        super().__init__(
            message=f"Failed to connect to {protocol} service on {host}:{port}",
            **kwargs
        )
        
        if "Connection refused" in reason:
            self.suggestion = (
                "Connection was refused. This usually means:\n"
                "  1. Service is not running on the target\n"
                "  2. Service is bound to a different interface\n"
                "  3. Check service status with: make service-status"
            )
        elif "timeout" in reason.lower():
            self.suggestion = (
                "Connection timed out. This could mean:\n"
                "  1. Firewall is dropping packets (no response)\n"
                "  2. Network routing issue\n"
                "  3. Service is overloaded\n"
                "  4. Check firewall rules and routing"
            )
        elif "No route to host" in reason:
            self.suggestion = (
                "No route to destination. Check:\n"
                "  1. Routing tables in namespace\n"
                "  2. Network connectivity\n"
                "  3. Interface configuration"
            )
        else:
            self.suggestion = f"Connection failed: {reason}"


class ServiceResponseError(ServiceError):
    """Raised when service response is invalid."""
    
    def __init__(self, expected: str, received: str, **kwargs):
        super().__init__(
            message="Service returned unexpected response",
            **kwargs
        )
        self.suggestion = (
            "The service is running but returned incorrect data.\n"
            f"Expected: {expected}\n"
            f"Received: {received}\n"
            "This could indicate:\n"
            "  1. Service misconfiguration\n"
            "  2. Network data corruption\n"
            "  3. Wrong service type"
        )


@dataclass
class ServiceConfig:
    """Configuration for a network service."""
    name: str
    port: int
    protocol: ServiceProtocol
    namespace: str
    bind_address: str = "0.0.0.0"
    echo_prefix: str = "ECHO: "
    timeout: int = 30
    pid_file: Optional[str] = None
    log_file: Optional[str] = None
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        # Validate port
        if not 1 <= self.port <= 65535:
            raise PortValidationError(str(self.port))
            
        # Set default paths if not provided
        if not self.pid_file:
            self.pid_file = f"/tmp/traceroute_service_{self.namespace}_{self.name}_{self.port}.pid"
        if not self.log_file:
            self.log_file = f"/tmp/traceroute_service_{self.namespace}_{self.name}_{self.port}.log"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['protocol'] = self.protocol.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServiceConfig":
        """Create from dictionary representation."""
        data['protocol'] = ServiceProtocol(data['protocol'])
        return cls(**data)


class ServiceManager:
    """Manages services running in network namespaces."""
    
    def __init__(self, verbose_level: int = 0):
        """Initialize service manager."""
        self.verbose_level = verbose_level
        setup_logging(verbose_level)
        self.logger = get_logger(__name__, verbose_level)
        
        # Service registry
        self.registry_file = Path("/tmp/traceroute_services_registry.json")
        self.services: Dict[str, ServiceConfig] = self._load_registry()
        
    def _load_registry(self) -> Dict[str, ServiceConfig]:
        """Load service registry from disk."""
        if not self.registry_file.exists():
            return {}
            
        try:
            with open(self.registry_file, 'r') as f:
                data = json.load(f)
            
            services = {}
            for key, config in data.items():
                services[key] = ServiceConfig.from_dict(config)
            return services
            
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"Failed to load service registry", error=str(e))
            return {}
    
    def _save_registry(self) -> None:
        """Save service registry to disk."""
        data = {}
        for key, config in self.services.items():
            data[key] = config.to_dict()
            
        with open(self.registry_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _get_service_key(self, namespace: str, name: str, port: int, protocol: str = None) -> str:
        """Generate unique service key."""
        if protocol:
            return f"{namespace}:{name}:{port}:{protocol}"
        return f"{namespace}:{name}:{port}"
    
    def _check_socat_available(self) -> None:
        """Check if socat is available on the system."""
        try:
            subprocess.run(["which", "socat"], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            raise ExecutionError(
                "socat is not installed",
                suggestion="Install socat: sudo apt-get install socat"
            )
    
    def _check_namespace_exists(self, namespace: str) -> None:
        """Check if namespace exists."""
        try:
            subprocess.run(
                ["ip", "netns", "exec", namespace, "true"],
                check=True,
                capture_output=True
            )
        except subprocess.CalledProcessError:
            raise ConfigurationError(
                f"Namespace '{namespace}' does not exist",
                f"Create namespace first or check name spelling"
            )
    
    def _is_port_available(self, namespace: str, port: int, protocol: str) -> bool:
        """Check if port is available for the specific protocol in namespace."""
        # Use ss to check specific protocol listeners on the specified port
        protocol_flag = "-t" if protocol.lower() == "tcp" else "-u"
        cmd = [
            "ip", "netns", "exec", namespace,
            "sh", "-c", f"ss {protocol_flag}nl | grep ':{port}\\s'"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            # If grep finds anything, the port is in use for this protocol
            return result.returncode != 0  # grep returns 0 if found, 1 if not found
        except subprocess.CalledProcessError:
            # If command fails, assume port is available
            return True
    
    def start_service(self, config: ServiceConfig) -> None:
        """
        Start a service in the specified namespace.
        
        Args:
            config: Service configuration
            
        Raises:
            ServiceStartError: If service fails to start
        """
        self.logger.info(f"Starting service {config.name}", 
                        namespace=config.namespace,
                        port=config.port,
                        protocol=config.protocol.value)
        
        # Validations
        self._check_socat_available()
        self._check_namespace_exists(config.namespace)
        
        # Check if service already running
        key = self._get_service_key(config.namespace, config.name, config.port, config.protocol.value)
        if key in self.services and self.is_service_running(config):
            raise ServiceStartError(
                config.name,
                f"Service already running on {config.namespace}:{config.port}/{config.protocol.value}"
            )
        
        # Check port availability
        if not self._is_port_available(config.namespace, config.port, config.protocol.value):
            raise ServiceStartError(
                config.name,
                f"Port {config.port} is already in use"
            )
        
        # Build socat command based on protocol
        if config.protocol == ServiceProtocol.TCP:
            # TCP: TCP4-LISTEN with fork for multiple connections
            listen_spec = f"TCP4-LISTEN:{config.port},bind={config.bind_address},reuseaddr,fork"
        else:
            # UDP: UDP4-LISTEN with fork for multiple clients
            listen_spec = f"UDP4-LISTEN:{config.port},bind={config.bind_address},reuseaddr,fork"
        
        # Simple echo using EXEC:cat
        cmd = [
            "ip", "netns", "exec", config.namespace,
            "socat", listen_spec, "EXEC:cat"
        ]
        
        self.logger.debug(f"Starting socat service", command=" ".join(cmd))
        
        # Start service
        try:
            # Open log file
            with open(config.log_file, 'w') as log_file:
                process = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=log_file,
                    start_new_session=True  # Detach from parent
                )
            
            # Give it a moment to start
            time.sleep(0.5)
            
            # Check if it's still running
            if process.poll() is not None:
                # Process died immediately
                with open(config.log_file, 'r') as f:
                    error_output = f.read()
                raise ServiceStartError(
                    config.name,
                    f"Process exited immediately: {error_output}"
                )
            
            # Save PID
            with open(config.pid_file, 'w') as f:
                f.write(str(process.pid))
            
            # Register service
            self.services[key] = config
            self._save_registry()
            
            self.logger.info(f"Service {config.name} started successfully", pid=process.pid)
            
        except Exception as e:
            raise ServiceStartError(config.name, str(e), cause=e)
    
    def stop_service(self, namespace: str, name: str, port: int, protocol: str = None) -> None:
        """Stop a running service."""
        # Try to find service with protocol first, fall back to old format for compatibility
        key = None
        if protocol:
            key = self._get_service_key(namespace, name, port, protocol)
        
        # If not found with protocol or no protocol specified, try old format
        if not key or key not in self.services:
            key = self._get_service_key(namespace, name, port)
        
        if key not in self.services:
            self.logger.warning(f"Service {name} not found in registry")
            return
            
        config = self.services[key]
        
        # Try to read PID
        if os.path.exists(config.pid_file):
            try:
                with open(config.pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                # Try graceful termination first
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(0.5)
                except ProcessLookupError:
                    pass  # Already dead
                
                # Force kill if still running
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                    
                self.logger.info(f"Service {name} stopped", pid=pid)
                
            except (ValueError, OSError) as e:
                self.logger.warning(f"Failed to stop service via PID", error=str(e))
        
        # Cleanup files
        cleanup_files = [config.pid_file, config.log_file]
        
        for file_path in cleanup_files:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
        
        # Remove from registry
        del self.services[key]
        self._save_registry()
    
    def restart_service(self, config: ServiceConfig) -> None:
        """Restart a service."""
        key = self._get_service_key(config.namespace, config.name, config.port, config.protocol.value)
        
        # Stop if running
        if key in self.services:
            self.stop_service(config.namespace, config.name, config.port, config.protocol.value)
            time.sleep(0.5)  # Brief pause
        
        # Start again
        self.start_service(config)
    
    def is_service_running(self, config: ServiceConfig) -> bool:
        """Check if service is running."""
        if not os.path.exists(config.pid_file):
            return False
            
        try:
            with open(config.pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            # Check if process exists
            os.kill(pid, 0)
            return True
            
        except (ValueError, OSError, ProcessLookupError):
            return False
    
    def get_service_status(self, namespace: str, name: str, port: int, protocol: str = None) -> ServiceStatus:
        """Get service status."""
        # Try to find service with protocol first, fall back to old format for compatibility
        key = None
        if protocol:
            key = self._get_service_key(namespace, name, port, protocol)
        
        # If not found with protocol or no protocol specified, try old format
        if not key or key not in self.services:
            key = self._get_service_key(namespace, name, port)
        
        if key not in self.services:
            return ServiceStatus.UNKNOWN
            
        config = self.services[key]
        
        if self.is_service_running(config):
            return ServiceStatus.RUNNING
        else:
            return ServiceStatus.STOPPED
    
    def list_services(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all services or services in a namespace."""
        services = []
        
        # Get active routers from bridge registry
        known_routers = set()
        try:
            registry_file = Path("/tmp/traceroute_bridges_registry.json")
            if registry_file.exists():
                with open(registry_file, 'r') as f:
                    bridge_registry = json.load(f)
                
                for bridge_name, bridge_info in bridge_registry.items():
                    router_data = bridge_info.get('routers', {})
                    for router_name in router_data.keys():
                        known_routers.add(router_name)
        except (json.JSONDecodeError, IOError):
            pass
        
        # Get active hosts from host registry
        hosts = {}
        try:
            host_registry_file = Path("/tmp/traceroute_hosts_registry.json")
            if host_registry_file.exists():
                with open(host_registry_file, 'r') as f:
                    hosts = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
        
        for key, config in self.services.items():
            if namespace and config.namespace != namespace:
                continue
                
            # Skip services on system namespaces (not known routers or hosts)
            if config.namespace not in known_routers and config.namespace not in hosts:
                continue
                
            status = self.get_service_status(config.namespace, config.name, config.port, config.protocol.value)
            
            # Determine if this is a host or router
            is_host = config.namespace in hosts
            
            services.append({
                "namespace": config.namespace,
                "name": config.name,
                "port": config.port,
                "protocol": config.protocol.value,
                "status": status.value,
                "bind_address": config.bind_address,
                "is_host": is_host
            })
        
        return services
    
    def cleanup_all_services(self) -> None:
        """Stop and cleanup all registered services."""
        self.logger.info("Cleaning up all services")
        
        # Copy keys to avoid modification during iteration
        service_keys = list(self.services.keys())
        
        for key in service_keys:
            parts = key.split(':')
            if len(parts) == 3:
                namespace, name, port = parts
                try:
                    self.stop_service(namespace, name, int(port))
                except Exception as e:
                    self.logger.warning(f"Failed to stop service {key}", error=str(e))
        
        # Remove registry file
        if self.registry_file.exists():
            self.registry_file.unlink()


class ServiceClient:
    """Client for testing services in namespaces."""
    
    def __init__(self, verbose_level: int = 0):
        """Initialize service client."""
        self.verbose_level = verbose_level
        self.logger = get_logger(__name__, verbose_level)
    
    def test_service(
        self,
        source_namespace: str,
        dest_ip: str,
        port: int,
        protocol: ServiceProtocol,
        message: str = "Hello",
        timeout: int = 5
    ) -> Tuple[bool, str]:
        """
        Test a service by sending a message and checking response.
        
        Args:
            source_namespace: Namespace to run test from
            dest_ip: Destination IP address
            port: Destination port
            protocol: TCP or UDP
            message: Message to send
            timeout: Connection timeout
            
        Returns:
            Tuple of (success, response_or_error)
        """
        self.logger.info(
            f"Testing {protocol.value} service",
            source=source_namespace,
            dest=f"{dest_ip}:{port}",
            test_message=message
        )
        
        if protocol == ServiceProtocol.TCP:
            return self._test_tcp_service(source_namespace, dest_ip, port, message, timeout)
        else:
            return self._test_udp_service(source_namespace, dest_ip, port, message, timeout)
    
    def _test_tcp_service(
        self,
        namespace: str,
        dest_ip: str,
        port: int,
        message: str,
        timeout: int
    ) -> Tuple[bool, str]:
        """Test TCP service using socat."""
        cmd = [
            "ip", "netns", "exec", namespace,
            "sh", "-c",
            f'echo "{message}" | timeout {timeout} socat - TCP:{dest_ip}:{port}'
        ]
        
        try:
            self.logger.debug(f"Executing TCP test", command=" ".join(cmd))
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 1
            )
            
            if result.returncode == 124:  # timeout command exit code
                raise ServiceConnectionError(
                    dest_ip, port, "TCP",
                    "Connection timeout - no response from server"
                )
            elif result.returncode != 0:
                # Check for specific error patterns
                stderr = result.stderr.lower()
                if "connection refused" in stderr:
                    raise ServiceConnectionError(
                        dest_ip, port, "TCP",
                        "Connection refused"
                    )
                elif "no route to host" in stderr:
                    raise ServiceConnectionError(
                        dest_ip, port, "TCP",
                        "No route to host"
                    )
                else:
                    raise ServiceConnectionError(
                        dest_ip, port, "TCP",
                        f"Connection failed: {result.stderr}"
                    )
            
            # Check response - socat just echoes back the message
            response = result.stdout.strip()
            
            if response != message:
                raise ServiceResponseError(message, response)
            
            self.logger.info("TCP service test successful", response=response)
            return True, response
            
        except subprocess.TimeoutExpired:
            raise ServiceConnectionError(
                dest_ip, port, "TCP",
                "Command execution timeout"
            )
        except Exception as e:
            if isinstance(e, ServiceError):
                raise
            raise ServiceConnectionError(
                dest_ip, port, "TCP",
                str(e),
                cause=e
            )
    
    def _test_udp_service(
        self,
        namespace: str,
        dest_ip: str,
        port: int,
        message: str,
        timeout: int
    ) -> Tuple[bool, str]:
        """Test UDP service using socat."""
        cmd = [
            "ip", "netns", "exec", namespace,
            "sh", "-c",
            f'echo "{message}" | timeout {timeout} socat - UDP:{dest_ip}:{port}'
        ]
        
        try:
            self.logger.debug(f"Executing UDP test", command=" ".join(cmd))
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 1
            )
            
            # UDP doesn't give connection errors, just timeouts
            if result.returncode == 124:  # timeout
                raise ServiceConnectionError(
                    dest_ip, port, "UDP",
                    "No response from UDP service (timeout)"
                )
            
            # Check response - socat just echoes back the message
            response = result.stdout.strip()
            
            if not response:
                raise ServiceConnectionError(
                    dest_ip, port, "UDP",
                    "No response from UDP service"
                )
            
            if response != message:
                raise ServiceResponseError(message, response)
            
            self.logger.info("UDP service test successful", response=response)
            return True, response
            
        except subprocess.TimeoutExpired:
            raise ServiceConnectionError(
                dest_ip, port, "UDP",
                "Command execution timeout"
            )
        except Exception as e:
            if isinstance(e, ServiceError):
                raise
            raise ServiceConnectionError(
                dest_ip, port, "UDP",
                str(e),
                cause=e
            )


@ErrorHandler.wrap_main
def main():
    """Command-line interface for service management."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Service Manager for Network Namespace Simulation'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Start command
    start_parser = subparsers.add_parser('start', help='Start a service')
    start_parser.add_argument('--namespace', required=True, help='Namespace name')
    start_parser.add_argument('--name', required=True, help='Service name')
    start_parser.add_argument('--port', type=int, required=True, help='Port number')
    start_parser.add_argument('--protocol', choices=['tcp', 'udp'], default='tcp', help='Protocol')
    start_parser.add_argument('--bind', default='0.0.0.0', help='Bind address')
    
    # Stop command
    stop_parser = subparsers.add_parser('stop', help='Stop a service')
    stop_parser.add_argument('--namespace', required=True, help='Namespace name')
    stop_parser.add_argument('--name', required=True, help='Service name')
    stop_parser.add_argument('--port', type=int, required=True, help='Port number')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Check service status')
    status_parser.add_argument('--namespace', help='Filter by namespace')
    status_parser.add_argument('-j', '--json', action='store_true', help='Output in JSON format')
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Test a service')
    test_parser.add_argument('--source', required=True, help='Source namespace')
    test_parser.add_argument('--dest', required=True, help='Destination IP')
    test_parser.add_argument('--port', type=int, required=True, help='Port number')
    test_parser.add_argument('--protocol', choices=['tcp', 'udp'], default='tcp', help='Protocol')
    test_parser.add_argument('--message', default='Hello', help='Test message')
    test_parser.add_argument('--timeout', type=int, default=5, help='Timeout in seconds')
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Stop all services')
    
    # Common arguments
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity (-v, -vv, -vvv)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Create manager
    manager = ServiceManager(args.verbose)
    
    if args.command == 'start':
        config = ServiceConfig(
            name=args.name,
            port=args.port,
            protocol=ServiceProtocol(args.protocol),
            namespace=args.namespace,
            bind_address=args.bind
        )
        manager.start_service(config)
        if args.verbose >= 1 and not args.json:
            print(f"Service {args.name} started on {args.namespace}:{args.port}/{args.protocol}")
        
    elif args.command == 'stop':
        manager.stop_service(args.namespace, args.name, args.port)
        if args.verbose >= 1 and not args.json:
            print(f"Service {args.name} stopped")
        
    elif args.command == 'status':
        services = manager.list_services(args.namespace)
        
        if args.json:
            # JSON output - add entity_type field
            for svc in services:
                svc['entity_type'] = 'host' if svc['is_host'] else 'router'
            print(json.dumps(services, indent=2))
        else:
            # Table output - separate routers and hosts
            if not services:
                print("No services found")
            else:
                # Separate services by type
                router_services = [s for s in services if not s['is_host']]
                host_services = [s for s in services if s['is_host']]
                
                # Print router services
                if router_services:
                    print("=== Services on Routers ===")
                    print(f"{'Router':<15} {'Listen IP':<20} {'Port':<8} {'Protocol':<8} {'Status':<10}")
                    print("-" * 70)
                    for svc in router_services:
                        print(f"{svc['namespace']:<15} {svc['bind_address']:<20} "
                              f"{svc['port']:<8} {svc['protocol']:<8} {svc['status']:<10}")
                    
                # Print host services
                if host_services:
                    if router_services:
                        print()  # Blank line between tables
                    print("=== Services on Hosts ===")
                    print(f"{'Host':<15} {'Listen IP':<20} {'Port':<8} {'Protocol':<8} {'Status':<10}")
                    print("-" * 70)
                    for svc in host_services:
                        print(f"{svc['namespace']:<15} {svc['bind_address']:<20} "
                              f"{svc['port']:<8} {svc['protocol']:<8} {svc['status']:<10}")
                      
    elif args.command == 'test':
        client = ServiceClient(args.verbose)
        success, response = client.test_service(
            args.source,
            args.dest,
            args.port,
            ServiceProtocol(args.protocol),
            args.message,
            args.timeout
        )
        print(f"Test {'succeeded' if success else 'failed'}: {response}")
        
    elif args.command == 'cleanup':
        manager.cleanup_all_services()
        if args.verbose >= 1 and not args.json:
            print("All services cleaned up")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())