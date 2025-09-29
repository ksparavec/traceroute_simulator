#!/usr/bin/env -S python3 -B -u
"""
High-level manager for network status operations.

Orchestrates data collection, caching, and formatting to provide
a unified interface for network namespace status queries.
"""

import fnmatch
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

from tsim.simulators.network_status.cache import CacheManager
from tsim.simulators.network_status.collector import DataCollector
from tsim.simulators.network_status.config import NetworkStatusConfig
from tsim.simulators.network_status.formatter import DataFormatter
from tsim.simulators.network_status.exceptions import ConfigurationError, NamespaceNotFoundError


logger = logging.getLogger(__name__)


class NetworkStatusManager:
    """
    Main orchestrator for network status operations.
    
    Coordinates between cache, collector, and formatter components
    to provide high-performance namespace status queries.
    """
    
    def __init__(self, config_path: Optional[str] = None,
                 verbose: int = 0):
        """
        Initialize network status manager.
        
        Args:
            config_path: Optional path to configuration file
            verbose: Verbosity level (0=silent, 1=errors, 2=info, 3=debug)
        """
        # Set up logging based on verbosity
        self._setup_logging(verbose)
        
        # Load configuration
        self.config = NetworkStatusConfig(config_path)
        
        # Initialize components
        self.cache = CacheManager(self.config.cache_config)
        
        self.collector = DataCollector(
            config=self.config.parallel_config
        )
        
        self.formatter = DataFormatter(
            config=self.config.formatting_config
        )
        
        # Track known entities
        self.known_routers: Set[str] = set()
        self.known_hosts: Set[str] = set()
        self._load_known_entities()
        
        # Statistics
        self.stats = {
            'queries': 0,
            'total_time': 0.0
        }
        
        logger.info(f"NetworkStatusManager initialized: "
                   f"cache={self.config.cache_enabled}, "
                   f"parallel={self.config.parallel_enabled}")
    
    def _setup_logging(self, verbose: int):
        """Configure logging based on verbosity level."""
        # NEVER call logging.basicConfig() as it interferes with cmd2/readline
        # Just set the logger level for this module
        if verbose == 0:
            level = logging.CRITICAL
        elif verbose == 1:
            level = logging.ERROR
        elif verbose == 2:
            level = logging.INFO
        else:  # verbose >= 3
            level = logging.DEBUG
        
        # Only set the level for our module loggers, don't configure root logger
        logger.setLevel(level)
        # Also set for all submodule loggers
        logging.getLogger('tsim.simulators.network_status').setLevel(level)
    
    def _load_known_entities(self):
        """Load list of known routers and hosts from registries."""
        # Load routers from router registry
        router_registry_file = Path('/dev/shm/tsim/router_registry.json')
        if router_registry_file.exists():
            try:
                import json
                with open(router_registry_file, 'r') as f:
                    router_registry = json.load(f)
                    self.known_routers.update(router_registry.keys())
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load router registry: {e}")
        
        # Load hosts from host registry
        try:
            from tsim.core.config_loader import get_registry_paths
            registry_paths = get_registry_paths()
            host_registry_file = Path(registry_paths['hosts'])
        except ImportError:
            # Fallback to default path
            host_registry_file = Path('/dev/shm/tsim/host_registry.json')
        
        if host_registry_file.exists():
            try:
                import json
                with open(host_registry_file, 'r') as f:
                    host_registry = json.load(f)
                    self.known_hosts.update(host_registry.keys())
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load host registry: {e}")
        
        logger.debug(f"Loaded {len(self.known_routers)} routers, {len(self.known_hosts)} hosts")
    
    def get_status(self, function: str = 'summary',
                  namespaces: Optional[List[str]] = None,
                  limit_pattern: Optional[str] = None,
                  use_cache: bool = True,
                  output_format: str = 'text') -> str:
        """
        Get network namespace status.
        
        Args:
            function: Status function (summary, interfaces, routes, rules, 
                     iptables, ipsets, all)
            namespaces: Optional list of specific namespaces
            limit_pattern: Optional glob pattern to filter namespaces
            use_cache: Whether to use cache
            output_format: Output format (text or json)
            
        Returns:
            Formatted status output
        """
        start_time = time.time()
        self.stats['queries'] += 1
        
        # Determine target namespaces
        target_namespaces = self._get_target_namespaces(namespaces, limit_pattern)
        
        if not target_namespaces:
            return self._format_no_namespaces(output_format)
        
        # Determine required data types
        data_types = self._get_required_data_types(function)
        
        # Collect data (with caching)
        data = self._collect_data(target_namespaces, data_types, use_cache)
        
        # Format output
        if output_format == 'json':
            result = self.formatter.format_json(data, function)
        elif output_format == 'table':
            result = self.formatter.format_table(data, function)
        else:
            result = self.formatter.format_text(data, function)
        
        elapsed = time.time() - start_time
        self.stats['total_time'] += elapsed
        
        logger.info(f"Status query completed in {elapsed:.3f}s for {len(target_namespaces)} namespaces")
        
        return result
    
    def _get_target_namespaces(self, namespaces: Optional[List[str]], 
                               limit_pattern: Optional[str]) -> List[str]:
        """Determine target namespaces based on arguments."""
        # Discover available namespaces
        available = set(self.collector.discover_namespaces())
        
        if namespaces:
            # Use specified namespaces
            target = [ns for ns in namespaces if ns in available]
        else:
            # Use all available
            target = list(available)
        
        # Apply pattern filter if specified
        if limit_pattern:
            filtered = []
            for ns in target:
                if fnmatch.fnmatch(ns, limit_pattern):
                    filtered.append(ns)
            target = filtered
        
        # Filter out system namespaces
        try:
            from tsim.core.config_loader import get_network_setup_config
            network_config = get_network_setup_config()
            hidden_ns = network_config.get('hidden_namespace', 'tsim-hidden')
        except ImportError:
            # Fallback to default
            hidden_ns = 'tsim-hidden'
        
        target = [ns for ns in target if ns not in ['default', hidden_ns]]
        
        return sorted(target)
    
    def _get_required_data_types(self, function: str) -> List[str]:
        """Determine required data types for function."""
        if function == 'interfaces':
            return ['interfaces']
        elif function == 'routes':
            return ['routes']
        elif function == 'rules':
            return ['rules']
        elif function == 'iptables':
            return ['iptables']
        elif function == 'ipsets':
            return ['ipsets']
        elif function in ['all', 'summary']:
            # Get all configured data types
            types = []
            for dtype, enabled in self.config.collection_config.items():
                if enabled:
                    types.append(dtype)
            return types
        else:
            return ['interfaces', 'routes', 'rules']  # Default
    
    def _collect_data(self, namespaces: List[str], 
                     data_types: List[str],
                     use_cache: bool) -> Dict[str, Dict]:
        """Collect data with caching support."""
        result = {}
        
        # Build fine-grained cache/fetch plan per data type
        if use_cache and self.config.cache_enabled:
            ns_fetch_plan = {}  # namespace -> [data_types_to_fetch]
            
            for ns in namespaces:
                ns_data = {}
                missing_types = []
                
                # Check each data type individually
                for dtype in data_types:
                    cached_data = self.cache.get_namespace_data(ns, dtype)
                    if cached_data is not None:  # Accept empty dict {} as valid cached data
                        ns_data[dtype] = cached_data
                    else:
                        missing_types.append(dtype)
                
                # Store what we have from cache
                if ns_data:
                    result[ns] = ns_data
                
                # Plan to fetch only missing data types
                if missing_types:
                    ns_fetch_plan[ns] = missing_types
            
            logger.debug(f"Cache status: {len([ns for ns in namespaces if ns not in ns_fetch_plan])} fully cached, "
                        f"{len(ns_fetch_plan)} need partial fetch")
        else:
            # No cache - fetch everything
            ns_fetch_plan = {ns: data_types for ns in namespaces}
        
        # Collect missing data using fine-grained plan
        if ns_fetch_plan:
            # Collect only the missing data types for each namespace
            for ns, missing_types in ns_fetch_plan.items():
                if missing_types:
                    fresh_data = self.collector.collect_all_data([ns], missing_types)
                    
                    # Cache the fresh data
                    if use_cache and self.config.cache_enabled:
                        for ns_key, ns_data in fresh_data.items():
                            for dtype, data in ns_data.items():
                                if not isinstance(data, dict) or 'error' not in data:
                                    self.cache.set_namespace_data(ns_key, dtype, data)
                    
                    # Merge fresh data with existing cached data
                    if ns in result:
                        result[ns].update(fresh_data.get(ns, {}))
                    else:
                        result.update(fresh_data)
        
        return result
    
    def _format_no_namespaces(self, output_format: str) -> str:
        """Format output when no namespaces found."""
        if output_format == 'json':
            return '{}'
        else:
            return "No namespaces found matching criteria"
    
    def invalidate_cache(self, namespace: Optional[str] = None):
        """
        Invalidate cache entries.
        
        Args:
            namespace: Optional specific namespace to invalidate
                      (None = invalidate all)
        """
        if not self.config.cache_enabled:
            return
        
        if namespace:
            self.cache.invalidate_namespace(namespace)
            logger.info(f"Cache invalidated for namespace: {namespace}")
        else:
            self.cache.invalidate_all()
            logger.info("All cache invalidated")
    
    def warm_cache(self, namespaces: Optional[List[str]] = None,
                  pattern: Optional[str] = None):
        """
        Pre-populate cache for specified namespaces.
        
        Args:
            namespaces: Optional list of namespaces
            pattern: Optional pattern to match namespaces
        """
        if not self.config.cache_enabled:
            return
        
        target = self._get_target_namespaces(namespaces, pattern)
        if not target:
            return
        
        logger.info(f"Warming cache for {len(target)} namespaces")
        
        # Get all configured data types
        data_types = [dtype for dtype, enabled in self.config.collection_config.items() 
                     if enabled]
        
        # Collect and cache data
        data = self.collector.collect_all_data(target, data_types)
        
        for ns, ns_data in data.items():
            for dtype, type_data in ns_data.items():
                if not isinstance(type_data, dict) or 'error' not in type_data:
                    self.cache.set_namespace_data(ns, dtype, type_data)
        
        logger.info(f"Cache warmed for {len(data)} namespaces")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics."""
        stats = self.stats.copy()
        
        # Add component stats
        if self.config.cache_enabled:
            stats['cache'] = self.cache.get_stats()
        
        stats['collector'] = self.collector.get_stats()
        
        return stats
    
    def is_host(self, namespace: str) -> bool:
        """Check if namespace is a known host."""
        return namespace in self.known_hosts
    
    def is_router(self, namespace: str) -> bool:
        """Check if namespace is a known router."""
        return namespace in self.known_routers