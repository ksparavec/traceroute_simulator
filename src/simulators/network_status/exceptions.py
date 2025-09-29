#!/usr/bin/env -S python3 -B -u
"""
Custom exceptions for network status module.
"""


class NetworkStatusError(Exception):
    """Base exception for network status operations."""
    pass


class CacheError(NetworkStatusError):
    """Exception raised for cache-related errors."""
    pass


class CollectionError(NetworkStatusError):
    """Exception raised during data collection."""
    pass


class NamespaceNotFoundError(NetworkStatusError):
    """Exception raised when a namespace is not found."""
    pass


class ConfigurationError(NetworkStatusError):
    """Exception raised for configuration issues."""
    pass


class TimeoutError(NetworkStatusError):
    """Exception raised when operation times out."""
    pass