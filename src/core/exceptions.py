"""
Structured Exception Hierarchy for Traceroute Simulator

This module provides a comprehensive exception hierarchy with application-aware
error messages and user-friendly suggestions for error resolution.

Key Features:
- Structured exceptions for different error categories
- User-friendly error messages without technical details
- Suggested actions for error resolution
- Debug information available only in verbose mode
- Consistent error reporting across all modules
"""

import sys
import traceback
from typing import Optional, Dict, Any, List
from enum import IntEnum


class ErrorCode(IntEnum):
    """Standard exit codes for the application."""
    SUCCESS = 0
    NO_PATH = 1
    NOT_FOUND = 2
    NO_LINUX_ROUTERS = 4
    INVALID_INPUT = 10
    CONFIGURATION_ERROR = 11
    NETWORK_ERROR = 12
    PERMISSION_ERROR = 13
    RESOURCE_ERROR = 14
    INTERNAL_ERROR = 15


class TracerouteError(Exception):
    """
    Base exception class for all traceroute simulator errors.
    
    Provides structured error information with user-friendly messages
    and suggested actions for resolution.
    """
    
    def __init__(
        self,
        message: str,
        suggestion: Optional[str] = None,
        error_code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        """
        Initialize traceroute error with structured information.
        
        Args:
            message: User-friendly error message
            suggestion: Suggested action to resolve the error
            error_code: Exit code for the error
            details: Additional error details (shown only in verbose mode)
            cause: Original exception that caused this error
        """
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion
        self.error_code = error_code
        self.details = details or {}
        self.cause = cause
        
    def format_error(self, verbose_level: int = 0) -> str:
        """
        Format error message based on verbosity level.
        
        Args:
            verbose_level: 0=basic, 1=verbose, 2=debug, 3=full details
            
        Returns:
            Formatted error message
        """
        lines = [f"Error: {self.message}"]
        
        if self.suggestion:
            lines.append(f"Suggestion: {self.suggestion}")
            
        if verbose_level >= 1 and self.details:
            lines.append("\nDetails:")
            for key, value in self.details.items():
                lines.append(f"  {key}: {value}")
                
        if verbose_level >= 2 and self.cause:
            lines.append(f"\nCaused by: {type(self.cause).__name__}: {str(self.cause)}")
            
        if verbose_level >= 3:
            lines.append("\nStack trace:")
            # Get the actual traceback if available
            tb = traceback.format_exc()
            if tb and tb != 'NoneType: None\n':
                lines.append(tb)
            else:
                # Try to get the stored traceback from the exception
                import sys
                if sys.exc_info()[2]:
                    lines.append(''.join(traceback.format_tb(sys.exc_info()[2])))
                else:
                    lines.append("(No active exception - stack trace not available)")
            
        return "\n".join(lines)


# Configuration and Setup Errors

class ConfigurationError(TracerouteError):
    """Raised when there are configuration-related issues."""
    
    def __init__(self, message: str, config_file: Optional[str] = None, **kwargs):
        suggestion = "Check your configuration file format and values."
        if config_file:
            suggestion += f" Configuration file: {config_file}"
            kwargs['details'] = kwargs.get('details', {})
            kwargs['details']['config_file'] = config_file
        super().__init__(
            message=message,
            suggestion=suggestion,
            error_code=ErrorCode.CONFIGURATION_ERROR,
            **kwargs
        )


class FactsDirectoryError(ConfigurationError):
    """Raised when facts directory is missing or invalid."""
    
    def __init__(self, directory: str, **kwargs):
        details = kwargs.get('details', {})
        details['directory'] = directory
        kwargs['details'] = details
        super().__init__(
            message=f"Facts directory not found or inaccessible: {directory}",
            **kwargs
        )
        # Override suggestion after parent init
        self.suggestion = (
            "Ensure the facts directory exists and contains router JSON files. "
            "You can:\n"
            "  1. Set environment variable: export TRACEROUTE_SIMULATOR_FACTS=/path/to/facts\n"
            "  2. Collect new data: make fetch-routing-data"
        )


class NoRouterDataError(ConfigurationError):
    """Raised when no router data files are found."""
    
    def __init__(self, directory: str, **kwargs):
        details = kwargs.get('details', {})
        details.update({
            "directory": directory,
            "expected_pattern": "*.json"
        })
        kwargs['details'] = details
        super().__init__(
            message=f"No router data files found in {directory}",
            **kwargs
        )
        # Override suggestion after parent init
        self.suggestion = (
            "The facts directory exists but contains no router JSON files. "
            "Please:\n"
            "  1. Run data collection: make fetch-routing-data\n"
            "  2. Check file permissions in the directory\n"
            "  3. Verify JSON files have .json extension"
        )


# Network and Routing Errors

class NetworkError(TracerouteError):
    """Base class for network-related errors."""
    
    def __init__(self, message: str, **kwargs):
        if 'error_code' not in kwargs:
            kwargs['error_code'] = ErrorCode.NETWORK_ERROR
        super().__init__(
            message=message,
            **kwargs
        )


class IPNotFoundError(NetworkError):
    """Raised when an IP address is not found in any router."""
    
    def __init__(self, ip_address: str, ip_type: str = "IP", available_networks: Optional[List[str]] = None, **kwargs):
        networks_hint = ""
        if available_networks and len(available_networks) <= 5:
            networks_hint = f"\nAvailable networks: {', '.join(available_networks[:5])}"
        elif available_networks:
            networks_hint = f"\nFound {len(available_networks)} networks. Use -v to see all."
        
        details = kwargs.get('details', {})
        details.update({
            "ip_address": ip_address,
            "ip_type": ip_type,
            "available_networks": available_networks
        })
        kwargs['details'] = details
        kwargs.pop('error_code', None)  # Remove if passed
        
        super().__init__(
            message=f"{ip_type} address {ip_address} is not configured on any router",
            **kwargs
        )
        
        # Set after init
        self.error_code = ErrorCode.NOT_FOUND
        self.suggestion = (
            f"Please verify the {ip_type.lower()} IP address is correct. "
            f"The IP must be:\n"
            f"  1. Configured on a router interface, OR\n"
            f"  2. Within a directly connected network{networks_hint}"
        )


class NoRouteError(NetworkError):
    """Raised when no route exists between source and destination."""
    
    def __init__(self, source: str, destination: str, last_hop: Optional[str] = None, **kwargs):
        details = kwargs.get('details', {})
        details.update({
            "source": source,
            "destination": destination
        })
        if last_hop:
            details["last_successful_hop"] = last_hop
        kwargs['details'] = details
        kwargs.pop('error_code', None)
            
        super().__init__(
            message=f"No route found from {source} to {destination}",
            **kwargs
        )
        
        self.error_code = ErrorCode.NO_PATH
        self.suggestion = (
            "The source and destination exist but no routing path connects them. "
            "This could mean:\n"
            "  1. Missing routes in the routing table\n"
            "  2. Firewall blocking the path\n"
            "  3. Network isolation between segments\n"
            "Try: Check routing tables on intermediate routers"
        )


class InvalidIPError(NetworkError):
    """Raised when an IP address format is invalid."""
    
    def __init__(self, ip_address: str, **kwargs):
        details = kwargs.get('details', {})
        details['provided_value'] = ip_address
        kwargs['details'] = details
        kwargs['error_code'] = ErrorCode.INVALID_INPUT
        super().__init__(
            message=f"Invalid IP address format: '{ip_address}'",
            **kwargs
        )
        # Override suggestion
        self.suggestion = (
            "Please provide a valid IPv4 or IPv6 address. Examples:\n"
            "  IPv4: 192.168.1.1, 10.0.0.1\n"
            "  IPv6: 2001:db8::1, fe80::1"
        )


# Router and Data Errors

class RouterError(TracerouteError):
    """Base class for router-related errors."""
    pass


class RouterNotFoundError(RouterError):
    """Raised when a specified router cannot be found."""
    
    def __init__(self, router_name: str, available_routers: Optional[List[str]] = None, **kwargs):
        routers_hint = ""
        if available_routers and len(available_routers) <= 10:
            routers_hint = f"\nAvailable routers: {', '.join(sorted(available_routers))}"
        elif available_routers:
            routers_hint = f"\nFound {len(available_routers)} routers. Use -v to see all."
        
        facts_dir = kwargs.get('facts_dir', 'tsim_facts')
        details = kwargs.get('details', {})
        details.update({
            "router_name": router_name,
            "available_routers": available_routers
        })
        kwargs['details'] = details
        kwargs.pop('error_code', None)
        kwargs.pop('facts_dir', None)  # Remove from kwargs
            
        super().__init__(
            message=f"Router '{router_name}' not found",
            error_code=ErrorCode.NOT_FOUND,
            **kwargs
        )
        
        self.suggestion = (
            f"Please check the router name spelling.{routers_hint}\n"
            f"You can list all routers with: ls {facts_dir}/*.json"
        )


class RouterDataError(RouterError):
    """Raised when router data is corrupted or invalid."""
    
    def __init__(self, router_name: str, file_path: str, parse_error: str, **kwargs):
        details = kwargs.get('details', {})
        details.update({
            "router": router_name,
            "file": file_path,
            "parse_error": parse_error
        })
        kwargs['details'] = details
        kwargs.pop('error_code', None)
        
        super().__init__(
            message=f"Failed to load data for router '{router_name}'",
            error_code=ErrorCode.CONFIGURATION_ERROR,
            **kwargs
        )
        
        self.suggestion = (
            "The router data file appears to be corrupted or invalid. Try:\n"
            "  1. Re-collect data: make fetch-routing-data\n"
            f"  2. Validate JSON: python3 -m json.tool {file_path}\n"
            "  3. Check file permissions"
        )


class NoLinuxRoutersError(RouterError):
    """Raised when no Linux routers are found for MTR execution."""
    
    def __init__(self, path: List[str], **kwargs):
        super().__init__(
            message="No Linux routers found in the network path",
            suggestion=(
                "MTR execution requires at least one Linux router in the path. "
                "Options:\n"
                "  1. Use simulation-only mode: add --no-mtr flag\n"
                "  2. Ensure router metadata files mark Linux routers correctly\n"
                "  3. Check router facts include metadata section"
            ),
            error_code=ErrorCode.NO_LINUX_ROUTERS,
            details={"path": path},
            **kwargs
        )


# Execution and System Errors

class ExecutionError(TracerouteError):
    """Base class for execution-related errors."""
    pass


class SSHConnectionError(ExecutionError):
    """Raised when SSH connection fails."""
    
    def __init__(self, host: str, error: str, **kwargs):
        super().__init__(
            message=f"Failed to connect to {host} via SSH",
            suggestion=(
                "SSH connection failed. Please check:\n"
                "  1. SSH service is running on the target\n"
                "  2. Your SSH key is authorized\n"
                "  3. Network connectivity to the host\n"
                "  4. Firewall rules allow SSH (port 22)"
            ),
            error_code=ErrorCode.NETWORK_ERROR,
            details={"host": host, "ssh_error": error},
            **kwargs
        )


class CommandExecutionError(ExecutionError):
    """Raised when a command execution fails."""
    
    def __init__(self, command: str, exit_code: int, error_output: str = "", **kwargs):
        super().__init__(
            message=f"Command execution failed with exit code {exit_code}",
            suggestion=(
                "The command failed to execute properly. Check:\n"
                "  1. Required tools are installed (mtr, ip, iptables)\n"
                "  2. Sufficient permissions to run the command\n"
                "  3. Command syntax is correct"
            ),
            error_code=ErrorCode.INTERNAL_ERROR,
            details={
                "command": command,
                "exit_code": exit_code,
                "error_output": error_output
            },
            **kwargs
        )


class PermissionError(ExecutionError):
    """Raised when there are permission-related issues."""
    
    def __init__(self, operation: str, resource: str, **kwargs):
        super().__init__(
            message=f"Permission denied for {operation}",
            suggestion=(
                f"This operation requires elevated privileges. Try:\n"
                f"  1. Run with sudo: sudo {' '.join(sys.argv)}\n"
                f"  2. Check file/directory permissions\n"
                f"  3. Ensure your user has necessary capabilities"
            ),
            error_code=ErrorCode.PERMISSION_ERROR,
            details={"operation": operation, "resource": resource},
            **kwargs
        )


class ResourceError(ExecutionError):
    """Raised when system resources are exhausted."""
    
    def __init__(self, resource_type: str, **kwargs):
        super().__init__(
            message=f"Insufficient {resource_type} resources",
            suggestion=(
                f"System resources are limited. Try:\n"
                f"  1. Close other applications\n"
                f"  2. Clean up temporary files: make clean\n"
                f"  3. Check system resource usage"
            ),
            error_code=ErrorCode.RESOURCE_ERROR,
            details={"resource_type": resource_type},
            **kwargs
        )


# Validation Errors

class ValidationError(TracerouteError):
    """Base class for input validation errors."""
    
    def __init__(self, field: str, value: Any, requirement: str, **kwargs):
        super().__init__(
            message=f"Invalid {field}: {value}",
            suggestion=f"The {field} must {requirement}",
            error_code=ErrorCode.INVALID_INPUT,
            details={"field": field, "value": value, "requirement": requirement},
            **kwargs
        )


class PortValidationError(ValidationError):
    """Raised when port number is invalid."""
    
    def __init__(self, port: str, **kwargs):
        super().__init__(
            field="port",
            value=port,
            requirement="be a number between 1 and 65535, or a valid range (e.g., 80,443 or 8000:8080)",
            **kwargs
        )


class ProtocolValidationError(ValidationError):
    """Raised when protocol is invalid."""
    
    def __init__(self, protocol: str, **kwargs):
        super().__init__(
            field="protocol",
            value=protocol,
            requirement="be one of: tcp, udp, icmp, all",
            **kwargs
        )


# Error Handler Utility

class ErrorHandler:
    """Utility class for consistent error handling across the application."""
    
    @staticmethod
    def handle_error(error: Exception, verbose_level: int = 0) -> int:
        """
        Handle an error and return appropriate exit code.
        
        Args:
            error: The exception to handle
            verbose_level: Verbosity level (0-3)
            
        Returns:
            Exit code for the application
        """
        if isinstance(error, TracerouteError):
            print(error.format_error(verbose_level), file=sys.stderr)
            return error.error_code
        else:
            # Handle unexpected errors
            print(f"Error: An unexpected error occurred", file=sys.stderr)
            print(f"Suggestion: This might be a bug. Please report it with the full error output.", file=sys.stderr)
            
            if verbose_level >= 1:
                print(f"\nError type: {type(error).__name__}", file=sys.stderr)
                print(f"Error message: {str(error)}", file=sys.stderr)
                
            if verbose_level >= 3:
                print("\nStack trace:", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                
            return ErrorCode.INTERNAL_ERROR
    
    @staticmethod
    def wrap_main(main_func):
        """
        Decorator to wrap main functions with error handling.
        
        Usage:
            @ErrorHandler.wrap_main
            def main():
                # Your main function code
                pass
        """
        def wrapper(*args, **kwargs):
            try:
                return main_func(*args, **kwargs)
            except KeyboardInterrupt:
                print("\nOperation cancelled by user", file=sys.stderr)
                return ErrorCode.INTERNAL_ERROR
            except Exception as e:
                # Get verbose level from args if available
                verbose_level = 0
                if hasattr(args[0], 'verbose_level'):
                    verbose_level = args[0].verbose_level
                elif 'verbose_level' in kwargs:
                    verbose_level = kwargs['verbose_level']
                    
                return ErrorHandler.handle_error(e, verbose_level)
                
        return wrapper