#!/usr/bin/env -S python3 -B -u
"""
Network Status Module

Provides high-performance network namespace status querying with
caching and parallel execution capabilities.
"""

from tsim.simulators.network_status.manager import NetworkStatusManager
from tsim.simulators.network_status.cache import CacheManager, CacheBackend, SharedMemoryBackend
from tsim.simulators.network_status.collector import DataCollector
from tsim.simulators.network_status.formatter import DataFormatter
from tsim.simulators.network_status.exceptions import (
    CacheError,
    CollectionError,
    NamespaceNotFoundError,
    ConfigurationError
)

__all__ = [
    'NetworkStatusManager',
    'CacheManager',
    'CacheBackend',
    'SharedMemoryBackend',
    'DataCollector',
    'DataFormatter',
    'CacheError',
    'CollectionError',
    'NamespaceNotFoundError',
    'ConfigurationError'
]

__version__ = '2.0.0'