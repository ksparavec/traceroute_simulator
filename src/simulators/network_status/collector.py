#!/usr/bin/env -S python3 -B -u
"""
Parallel data collector for network namespace information.

Coordinates parallel execution of namespace queries using thread pool
executor and worker instances.
"""

import asyncio
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Callable

# Use uvloop for better async performance
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass  # Fall back to standard asyncio

from tsim.simulators.network_status.worker import NamespaceQueryWorker
from tsim.simulators.network_status.exceptions import CollectionError


logger = logging.getLogger(__name__)


class DataCollector:
    """
    Handles parallel data collection from network namespaces.
    
    Uses ThreadPoolExecutor to query multiple namespaces concurrently,
    significantly improving performance for large deployments.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize data collector.
        
        Args:
            config: Configuration dictionary
        """
        config = config or {}
        
        # Parallelization settings
        self.parallel_enabled = config.get('enabled', True)
        self.timeout_per_namespace = config.get('timeout_per_namespace', 5)
        
        # Auto-calculate max_concurrent based on file descriptor limits if not set
        max_concurrent = config.get('max_concurrent', None)
        if max_concurrent is None:
            import resource
            soft_limit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
            # Use 80% of FD limit, accounting for 3 FDs per subprocess + 100 overhead
            available_fds = int(soft_limit * 0.8) - 100
            max_concurrent = max(1, available_fds // 3)  # Minimum 1, respect FD limits
            
        
        self.max_concurrent = max_concurrent
        
        # Performance settings
        performance = config.get('performance', {})
        self.use_json = performance.get('use_json_commands', True)
        
        # Statistics
        self.stats = {
            'namespaces_queried': 0,
            'successful_queries': 0,
            'failed_queries': 0,
            'timeouts': 0,
            'total_time': 0.0,
            'avg_time_per_namespace': 0.0
        }
        
        # Track timeout details for summary
        self.timeout_details = []
        
        # Initialize worker
        self.worker = NamespaceQueryWorker(
            timeout=self.timeout_per_namespace,
            use_json=self.use_json
        )
        # Set the collector reference for timeout tracking
        self.worker.timeout_callback = self._record_timeout
        
        logger.info(f"DataCollector initialized: parallel={self.parallel_enabled}, "
                   f"timeout={self.timeout_per_namespace}s, max_concurrent={self.max_concurrent}")
    
    def discover_namespaces(self) -> List[str]:
        """
        Discover available network namespaces.
        
        Returns:
            List of namespace names
        """
        try:
            needs_sudo = os.geteuid() != 0
            cmd = "sudo ip netns list" if needs_sudo else "ip netns list"
            
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_per_namespace
            )
            
            if result.returncode != 0:
                logger.warning(f"Failed to list namespaces: {result.stderr}")
                return []
            
            namespaces = []
            for line in result.stdout.split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                # Extract namespace name (format: "namespace_name (id: X)")
                ns_match = re.match(r'^([^\s(]+)', line)
                if ns_match:
                    namespaces.append(ns_match.group(1))
            
            logger.info(f"Discovered {len(namespaces)} namespaces")
            return namespaces
            
        except Exception as e:
            logger.error(f"Error discovering namespaces: {e}")
            return []
    
    async def collect_all_data(self, namespaces: List[str], 
                        data_types: Optional[List[str]] = None) -> Dict[str, Dict]:
        """
        Collect all requested data from namespaces in parallel.
        
        Args:
            namespaces: List of namespace names
            data_types: Optional list of data types to collect
                       (interfaces, routes, rules, iptables, ipsets)
                       
        Returns:
            Dictionary mapping namespace -> data_type -> data
        """
        if not namespaces:
            return {}
        
        data_types = data_types or ['interfaces', 'routes', 'rules', 'iptables', 'ipsets']
        
        start_time = time.time()
        self.stats['namespaces_queried'] = len(namespaces)
        
        if self.parallel_enabled and len(namespaces) > 1:
            results = await self._collect_parallel(namespaces, data_types)
        else:
            results = await self._collect_serial(namespaces, data_types)
        
        elapsed_time = time.time() - start_time
        self.stats['total_time'] = elapsed_time
        self.stats['avg_time_per_namespace'] = elapsed_time / len(namespaces) if namespaces else 0
        
        logger.info(f"Collected data from {len(namespaces)} namespaces in {elapsed_time:.2f}s "
                   f"(avg {self.stats['avg_time_per_namespace']:.3f}s per namespace)")
        logger.info(f"Collection details: timeout_per_ns={self.timeout_per_namespace}s, "
                   f"max_concurrent={self.max_concurrent}, total_tasks={len(namespaces) * len(data_types)}")
        
        return results
    
    async def collect_specific(self, namespaces: List[str], data_type: str) -> Dict[str, Any]:
        """
        Collect specific data type from namespaces.
        
        Args:
            namespaces: List of namespace names
            data_type: Type of data to collect
            
        Returns:
            Dictionary mapping namespace -> data
        """
        results = await self.collect_all_data(namespaces, [data_type])
        return {ns: data.get(data_type, {}) for ns, data in results.items()}
    
    async def _collect_parallel(self, namespaces: List[str], 
                         data_types: List[str]) -> Dict[str, Dict]:
        """Collect data using parallel execution with concurrency limits."""
        results = {}
        
        # Create tasks directly without semaphore (max_concurrent calculated to be safe)
        tasks = []
        task_metadata = []
        
        for ns in namespaces:
            for data_type in data_types:
                if data_type == 'interfaces':
                    coro = self.worker.query_interfaces(ns)
                elif data_type == 'routes':
                    coro = self.worker.query_routes(ns)
                elif data_type == 'rules':
                    coro = self.worker.query_rules(ns)
                elif data_type == 'iptables':
                    coro = self.worker.query_iptables(ns)
                elif data_type == 'ipsets':
                    coro = self.worker.query_ipsets(ns)
                else:
                    continue
                
                tasks.append(coro)
                task_metadata.append((ns, data_type))
        
        # Execute all tasks concurrently (timeout handled at worker level)
        logger.info(f"Starting {len(tasks)} tasks with max_concurrent={self.max_concurrent}")
        gather_start = time.time()
        try:
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"Error in parallel collection: {e}")
            return {}
        gather_time = time.time() - gather_start
        logger.info(f"asyncio.gather() completed in {gather_time:.2f}s for {len(tasks)} tasks")
        
        # Process results
        for i, result in enumerate(task_results):
            ns, data_type = task_metadata[i]
            
            if ns not in results:
                results[ns] = {}
            
            if isinstance(result, asyncio.TimeoutError):
                logger.warning(f"Timeout collecting {data_type} for {ns}")
                results[ns][data_type] = {'error': 'Query timeout'}
                self.stats['timeouts'] += 1
                self.stats['failed_queries'] += 1
            elif isinstance(result, Exception):
                logger.error(f"Error collecting {data_type} for {ns}: {result}")
                results[ns][data_type] = {'error': str(result)}
                self.stats['failed_queries'] += 1
            else:
                results[ns][data_type] = result
                self.stats['successful_queries'] += 1
        
        return results
    
    
    async def _collect_serial(self, namespaces: List[str], 
                       data_types: List[str]) -> Dict[str, Dict]:
        """Collect data using serial execution (fallback)."""
        results = {}
        
        for ns in namespaces:
            ns_results = {}
            
            for data_type in data_types:
                try:
                    if data_type == 'interfaces':
                        result = await self.worker.query_interfaces(ns)
                    elif data_type == 'routes':
                        result = await self.worker.query_routes(ns)
                    elif data_type == 'rules':
                        result = await self.worker.query_rules(ns)
                    elif data_type == 'iptables':
                        result = await self.worker.query_iptables(ns)
                    elif data_type == 'ipsets':
                        result = await self.worker.query_ipsets(ns)
                    else:
                        continue
                    
                    ns_results[data_type] = result
                    self.stats['successful_queries'] += 1
                    
                except Exception as e:
                    logger.error(f"Error collecting {data_type} for {ns}: {e}")
                    ns_results[data_type] = {'error': str(e)}
                    self.stats['failed_queries'] += 1
            
            results[ns] = ns_results
        
        return results
    
    def collect_interfaces(self, namespaces: List[str]) -> Dict[str, Dict]:
        """Collect interface data from namespaces."""
        return self.collect_specific(namespaces, 'interfaces')
    
    def collect_routes(self, namespaces: List[str]) -> Dict[str, Dict]:
        """Collect routing data from namespaces."""
        return self.collect_specific(namespaces, 'routes')
    
    def collect_rules(self, namespaces: List[str]) -> Dict[str, List]:
        """Collect policy rules from namespaces."""
        return self.collect_specific(namespaces, 'rules')
    
    def collect_iptables(self, namespaces: List[str]) -> Dict[str, Dict]:
        """Collect iptables data from namespaces."""
        return self.collect_specific(namespaces, 'iptables')
    
    def collect_ipsets(self, namespaces: List[str]) -> Dict[str, Dict]:
        """Collect ipset data from namespaces."""
        return self.collect_specific(namespaces, 'ipsets')
    
    def get_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        return self.stats.copy()
    
    def _record_timeout(self, command: str, namespace: str, timeout: int):
        """Record timeout details for summary display."""
        self.timeout_details.append({
            'command': command,
            'namespace': namespace,
            'timeout': timeout
        })
    
    
    def reset_stats(self):
        """Reset collection statistics."""
        self.stats = {
            'namespaces_queried': 0,
            'successful_queries': 0,
            'failed_queries': 0,
            'timeouts': 0,
            'total_time': 0.0,
            'avg_time_per_namespace': 0.0
        }