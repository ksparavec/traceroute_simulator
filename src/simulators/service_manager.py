#!/usr/bin/env -S python3 -B -u
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
import posix_ipc
import hashlib

# Use absolute imports for installed package
from tsim.core.exceptions import (
    ExecutionError, NetworkError, ValidationError,
    PortValidationError, ConfigurationError, ErrorHandler
)
from tsim.core.models import IptablesRule
from tsim.core.structured_logging import get_logger, setup_logging
from tsim.core.config_loader import get_registry_paths, load_traceroute_config
from tsim.core.creator_tag import CreatorTagManager


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
    created_by: Optional[str] = None  # Track creator: "wsgi", "cli", "api", etc.
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        # Validate port
        if not 1 <= self.port <= 65535:
            raise PortValidationError(str(self.port))

        # Set default paths if not provided - use /dev/shm/tsim for all files
        if not self.pid_file:
            self.pid_file = f"/dev/shm/tsim/service_{self.namespace}_{self.name}_{self.port}.pid"
        if not self.log_file:
            self.log_file = f"/dev/shm/tsim/service_{self.namespace}_{self.name}_{self.port}.log"

        # Auto-detect creator if not set
        if self.created_by is None:
            self.created_by = CreatorTagManager.get_creator_tag()
    
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
        
        # Load configuration for unix_group
        config = load_traceroute_config()
        self.unix_group = config.get('system', {}).get('unix_group', 'tsim-users')
        
        # Load registry paths from configuration
        registry_paths = get_registry_paths()
        
        # Service registry
        self.registry_file = Path(registry_paths['services'])
        
        # Initialize semaphore for atomic operations
        self._init_semaphore()
        
        # Load registry with atomic operations
        self.services: Dict[str, ServiceConfig] = self._load_registry()
        
    def _init_semaphore(self):
        """Initialize POSIX semaphore for service registry."""
        self.sem_name = "/tsim_services_reg"
        try:
            # Try to open existing semaphore first
            self.semaphore = posix_ipc.Semaphore(self.sem_name)
        except posix_ipc.ExistentialError:
            # Create new semaphore if it doesn't exist
            try:
                old_umask = os.umask(0)
                try:
                    self.semaphore = posix_ipc.Semaphore(self.sem_name, posix_ipc.O_CREAT | posix_ipc.O_EXCL, initial_value=1, mode=0o660)
                finally:
                    os.umask(old_umask)
                    
                # Set group ownership to unix_group from config
                sem_path = f"/dev/shm/sem.{self.sem_name[1:]}"  # Remove leading slash
                try:
                    import grp
                    tsim_gid = grp.getgrnam(self.unix_group).gr_gid
                    os.chown(sem_path, -1, tsim_gid)
                    os.chmod(sem_path, 0o660)  # Ensure proper permissions
                except (KeyError, OSError) as e:
                    self.logger.warning(f"Could not set {self.unix_group} group for {sem_path}: {e}")
                    
            except posix_ipc.ExistentialError:
                # Another process created it between our check and create
                self.semaphore = posix_ipc.Semaphore(self.sem_name)
        except posix_ipc.PermissionsError as e:
            self.logger.warning(f"Permission denied for semaphore, attempting to recreate", error=str(e))
            try:
                # Try to unlink and recreate with proper permissions
                posix_ipc.unlink_semaphore(self.sem_name)
                old_umask = os.umask(0)
                try:
                    self.semaphore = posix_ipc.Semaphore(self.sem_name, posix_ipc.O_CREAT | posix_ipc.O_EXCL, initial_value=1, mode=0o660)
                finally:
                    os.umask(old_umask)
                    
                # Set group ownership to unix_group from config
                sem_path = f"/dev/shm/sem.{self.sem_name[1:]}"
                try:
                    import grp
                    tsim_gid = grp.getgrnam(self.unix_group).gr_gid
                    os.chown(sem_path, -1, tsim_gid)
                    os.chmod(sem_path, 0o660)  # Ensure proper permissions
                except (KeyError, OSError) as e:
                    self.logger.warning(f"Could not set {self.unix_group} group for {sem_path}: {e}")
            except Exception as e2:
                # Fallback to unique name
                self.logger.warning(f"Failed to recreate semaphore, using fallback", error=str(e2))
                unique_suffix = hashlib.md5(str(os.getpid()).encode()).hexdigest()[:8]
                self.sem_name = f"/tsim_services_reg_{unique_suffix}"
                old_umask = os.umask(0)
                try:
                    self.semaphore = posix_ipc.Semaphore(self.sem_name, posix_ipc.O_CREAT, initial_value=1, mode=0o660)
                finally:
                    os.umask(old_umask)
                    
                # Set group ownership to unix_group from config
                sem_path = f"/dev/shm/sem.{self.sem_name[1:]}"
                try:
                    import grp
                    tsim_gid = grp.getgrnam(self.unix_group).gr_gid
                    os.chown(sem_path, -1, tsim_gid)
                    os.chmod(sem_path, 0o660)  # Ensure proper permissions
                except (KeyError, OSError):
                    pass
        
    def _load_registry(self) -> Dict[str, ServiceConfig]:
        """Load service registry from disk with atomic operations."""
        if not self.registry_file.exists():
            return {}
            
        try:
            self.semaphore.acquire()
            try:
                with open(self.registry_file, 'r') as f:
                    data = json.load(f)
                
                services = {}
                for key, config in data.items():
                    services[key] = ServiceConfig.from_dict(config)
                return services
            finally:
                self.semaphore.release()
                
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"Failed to load service registry", error=str(e))
            return {}
    
    def _save_registry(self) -> None:
        """Save service registry to disk with atomic operations."""
        data = {}
        for key, config in self.services.items():
            data[key] = config.to_dict()
            
        self.semaphore.acquire()
        try:
            # Save current umask and set new one for group write
            old_umask = os.umask(0o002)  # Allow group write
            try:
                with open(self.registry_file, 'w') as f:
                    json.dump(data, f, indent=2)
                
                # Ensure the file has correct permissions
                os.chmod(self.registry_file, 0o664)  # rw-rw-r--
            finally:
                # Restore original umask
                os.umask(old_umask)
        finally:
            self.semaphore.release()
    
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
    
    def _run_command(self, cmd: list, check: bool = True) -> subprocess.CompletedProcess:
        """Run command with sudo if needed."""
        # Check if command needs sudo
        cmd_str = ' '.join(cmd)
        needs_sudo = False
        
        # Commands that need sudo
        if not os.geteuid() == 0:  # Not already root
            if cmd[0] == "ip" and len(cmd) > 2 and cmd[1] == "netns" and cmd[2] == "exec":
                needs_sudo = True
            elif cmd[0] in ["kill", "pkill"]:
                needs_sudo = True
        
        if needs_sudo:
            cmd = ["sudo"] + cmd
        
        return subprocess.run(cmd, check=check, capture_output=True, text=True)
    
    def _check_namespace_exists(self, namespace: str) -> None:
        """Check if namespace exists."""
        try:
            self._run_command(
                ["ip", "netns", "exec", namespace, "true"],
                check=True
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
        
        # Show command with -vv
        if self.verbose_level >= 2:
            import shlex
            print(f"[CMD] {' '.join(shlex.quote(arg) for arg in cmd)}")
        
        try:
            result = self._run_command(cmd, check=False)
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
        
        # Add sudo if needed
        if not os.geteuid() == 0:
            cmd = ["sudo"] + cmd
        
        # Show command with -vv
        if self.verbose_level >= 2:
            import shlex
            print(f"[CMD] {' '.join(shlex.quote(arg) for arg in cmd)}")
        else:
            self.logger.debug(f"Starting socat service", command=" ".join(cmd))
        
        # Start service
        try:
            # Open log file
            with open(config.log_file, 'w') as log_file:
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,  # Detach stdin to prevent TTY issues
                    stdout=log_file,
                    stderr=log_file
                    # Keep in same process group for proper cleanup
                )
            
            # Set proper permissions on log file
            os.chmod(config.log_file, 0o664)
            
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
            
            # Save PID of the sudo process
            # When we kill the sudo process, it will also kill its children (socat)
            self.logger.debug(f"Saving PID {process.pid} to {config.pid_file}")
            with open(config.pid_file, 'w') as f:
                f.write(str(process.pid))
            
            # Set proper permissions on pid file
            os.chmod(config.pid_file, 0o664)
            
            # Register service
            self.services[key] = config
            self._save_registry()
            
            self.logger.info(f"Service {config.name} started successfully", pid=process.pid)
            
        except Exception as e:
            raise ServiceStartError(config.name, str(e), cause=e)
    
    def stop_service(self, namespace: str, name: str, port: int, protocol: str = None) -> None:
        """Stop a running service by finding and killing the process listening on the port."""
        # Try to find service with protocol first, fall back to old format for compatibility
        key = None
        if protocol:
            key = self._get_service_key(namespace, name, port, protocol)
        
        # If not found with protocol or no protocol specified, try old format
        if not key or key not in self.services:
            key = self._get_service_key(namespace, name, port)
        
        if key not in self.services:
            self.logger.warning(f"Service {name} not found in registry")
            print(f"[STOP] Service {name} not found in registry (key: {key})", file=sys.stderr)
            print(f"[STOP] Available services: {list(self.services.keys())}", file=sys.stderr)
            return
            
        config = self.services[key]
        
        # Use lsof to find the process listening on the specific port in this namespace
        try:
            # Determine protocol string for lsof (tcp or udp)
            lsof_protocol = protocol.lower() if protocol else 'tcp'
            
            # Use lsof to find PID listening on the port
            # sudo ip netns exec <namespace> lsof -ti <protocol>:<port>
            lsof_cmd = ["sudo", "ip", "netns", "exec", namespace, "lsof", "-ti", f"{lsof_protocol}:{port}"]
            
            if self.verbose_level >= 2:
                print(f"[SERVICE] Finding process: {' '.join(lsof_cmd)}")
            
            result = subprocess.run(lsof_cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout.strip():
                # lsof returns the PID(s) of processes listening on the port
                pids = result.stdout.strip().split('\n')
                
                for pid_str in pids:
                    if pid_str.strip():
                        # Kill the process with SIGTERM
                        self.logger.info(f"Found process {pid_str} listening on {namespace}:{port}/{lsof_protocol}")
                        if self.verbose_level >= 1:
                            print(f"[SERVICE] Killing process {pid_str} in namespace {namespace}")
                        
                        # Kill within the namespace context to ensure we get the right process
                        kill_cmd = ["sudo", "ip", "netns", "exec", namespace, "kill", "-TERM", pid_str.strip()]
                        kill_result = subprocess.run(kill_cmd, capture_output=True)
                        
                        if kill_result.returncode == 0:
                            self.logger.info(f"Successfully killed process {pid_str}")
                            if self.verbose_level >= 1:
                                print(f"[SERVICE] Successfully terminated process {pid_str}")
                        else:
                            # Process might have already exited, try regular kill
                            fallback_kill = ["sudo", "kill", "-TERM", pid_str.strip()] 
                            fallback_result = subprocess.run(fallback_kill, capture_output=True)
                            if fallback_result.returncode == 0:
                                self.logger.info(f"Successfully killed process {pid_str} (fallback)")
                            else:
                                self.logger.warning(f"Failed to kill process {pid_str}: {kill_result.stderr}")
                        
                        # Give the parent process time to collect exit status
                        time.sleep(0.2)
            else:
                # No process found listening on the port
                self.logger.info(f"No process found listening on {namespace}:{port}/{lsof_protocol}")
                if self.verbose_level >= 1:
                    print(f"[SERVICE] No process found listening on {namespace}:{port}/{lsof_protocol}")
                
        except Exception as e:
            self.logger.error(f"Error finding/killing process: {e}")
        
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
            if os.geteuid() == 0:
                os.kill(pid, 0)
            else:
                # Use kill -0 with sudo to check
                result = subprocess.run(["sudo", "kill", "-0", str(pid)], check=False, capture_output=True)
                if result.returncode != 0:
                    return False
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
            # Load registry paths from configuration
            registry_paths = get_registry_paths()
            registry_file = Path(registry_paths['bridges'])
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
            host_registry_file = Path(registry_paths['hosts'])
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
                # Old format: namespace:name:port
                namespace, name, port = parts
                try:
                    self.stop_service(namespace, name, int(port))
                except Exception as e:
                    self.logger.warning(f"Failed to stop service {key}", error=str(e))
            elif len(parts) == 4:
                # New format: namespace:name:port:protocol
                namespace, name, port, protocol = parts
                try:
                    self.stop_service(namespace, name, int(port), protocol)
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
        if self.verbose_level >= 3:
            print(f"[DEBUG] ServiceClient.test_service called: ns={source_namespace}, dest_ip={dest_ip}, port={port}, proto={protocol.value}, msg='{message}'")
        
        if protocol == ServiceProtocol.TCP:
            return self._test_tcp_service(source_namespace, dest_ip, port, message, timeout)
        else:
            return self._test_udp_service(source_namespace, dest_ip, port, message, timeout)
    
    def _create_python_test_script(self, protocol: str, dest_ip: str, port: int, message: str, timeout: int) -> str:
        """Create Python script for testing services (TCP or UDP)."""
        # Escape message for safe inclusion in Python string
        escaped_message = message.replace('\\', '\\\\').replace("'", "\\'")
        
        if protocol.upper() == "TCP":
            socket_type = "socket.SOCK_STREAM"
            connect_code = f"sock.connect(('{dest_ip}', {port}))"
            send_recv_code = f"""
    # Send message
    sock.send('{escaped_message}'.encode() + b'\\n')
    
    # Receive response
    response = sock.recv(1024).decode()"""
        else:  # UDP
            socket_type = "socket.SOCK_DGRAM"
            connect_code = ""  # UDP doesn't connect
            send_recv_code = f"""
    # Send message
    sock.sendto('{escaped_message}'.encode() + b'\\n', ('{dest_ip}', {port}))
    
    # Receive response (with timeout)
    response, addr = sock.recvfrom(1024)
    response = response.decode()"""
        
        return f'''
import socket
import sys

try:
    # Create socket
    sock = socket.socket(socket.AF_INET, {socket_type})
    sock.settimeout({timeout})
    {connect_code}
    {send_recv_code}
    # Determine local (ephemeral) port actually used
    try:
        local_port = sock.getsockname()[1]
    except Exception:
        local_port = None
    
    # Close connection
    sock.close()
    
    # Print response to stdout
    if local_port is not None:
        # Print response plus marker with local port on a new line
        print(str(response), end='')
        print("\\nLOCAL_PORT:" + str(local_port), end='')
    else:
        print(str(response), end='')
    sys.exit(0)
    
except socket.timeout:
    print("Connection timeout", file=sys.stderr)
    sys.exit(1)
except ConnectionRefusedError:
    print("Connection refused", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Error: {{e}}", file=sys.stderr)
    sys.exit(1)
'''

    def _test_service_common(
        self,
        namespace: str,
        dest_ip: str,
        port: int,
        protocol: str,
        message: str,
        timeout: int
    ) -> Tuple[bool, str]:
        """Common method for testing both TCP and UDP services."""
        if self.verbose_level >= 3:
            print(f"[DEBUG] _test_{protocol.lower()}_service: ns={namespace}, dest={dest_ip}:{port}")
        
        # Create Python script
        python_script = self._create_python_test_script(protocol, dest_ip, port, message, timeout)
        
        # Run Python script in namespace
        cmd = [
            "ip", "netns", "exec", namespace,
            "python3", "-c", python_script
        ]
        
        # Show command with -vv
        if self.verbose_level >= 2:
            print(f"[CMD] Running Python {protocol} client in namespace {namespace}")
        
        try:
            if self.verbose_level >= 3:
                print(f"[DEBUG] Running Python {protocol} client...")
            
            # Add sudo if needed
            if not os.geteuid() == 0:
                cmd = ["sudo"] + cmd
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 1
            )
            
            # Get the response
            response = result.stdout
            
            # Debug output with -vvv
            if self.verbose_level >= 3:
                print(f"[DEBUG] Python client exit code: {result.returncode}")
                print(f"[DEBUG] stdout: '{response}'")
                print(f"[DEBUG] stderr: '{result.stderr}'")
            
            # Check for errors
            if result.returncode != 0:
                stderr_lower = result.stderr.lower()
                if "connection refused" in stderr_lower:
                    raise ServiceConnectionError(dest_ip, port, protocol, "Connection refused")
                elif "connection timeout" in stderr_lower:
                    raise ServiceConnectionError(dest_ip, port, protocol, "Connection timeout")
                else:
                    raise ServiceConnectionError(dest_ip, port, protocol, result.stderr.strip())
            
            # Success: check indicators
            # 1) Expected message contained
            # 2) Our LOCAL_PORT marker present (means connection and send/recv worked)
            if message in response or ('LOCAL_PORT:' in response):
                return True, response.strip()
            
            # If we got here, we connected but didn't get expected response
            if self.verbose_level >= 3:
                print(f"[DEBUG] Looking for '{message}' in response")
                print(f"[DEBUG] Response bytes: {repr(response)}")
            
            # Even with empty response, if exit code is 0, connection worked
            if not response:
                return True, "Connected successfully"
            
            # Otherwise it's a response error
            raise ServiceResponseError(message, response.strip())
            
        except subprocess.TimeoutExpired:
            raise ServiceConnectionError(dest_ip, port, protocol, "Command execution timeout")
        except Exception as e:
            if self.verbose_level >= 3:
                print(f"[DEBUG] Exception in _test_{protocol.lower()}_service: {type(e).__name__}: {e}")
            if isinstance(e, ServiceError):
                raise
            raise ServiceConnectionError(dest_ip, port, protocol, str(e), cause=e)

    def _test_tcp_service(
        self,
        namespace: str,
        dest_ip: str,
        port: int,
        message: str,
        timeout: int
    ) -> Tuple[bool, str]:
        """Test TCP service by connecting to the actual running service."""
        return self._test_service_common(namespace, dest_ip, port, "TCP", message, timeout)
    
    def _test_udp_service(
        self,
        namespace: str,
        dest_ip: str,
        port: int,
        message: str,
        timeout: int
    ) -> Tuple[bool, str]:
        """Test UDP service by sending a message and checking response."""
        return self._test_service_common(namespace, dest_ip, port, "UDP", message, timeout)


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
