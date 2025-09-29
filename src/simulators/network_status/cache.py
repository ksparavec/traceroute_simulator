#!/usr/bin/env -S python3 -B -u
"""
Cache implementation for network status data.

Provides abstract cache interface with pluggable backends.
Currently implements shared memory backend with future support
for Redis and SQLite.
"""

import json
import logging
import os
import time
import fcntl
import hashlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import glob as glob_module

from tsim.simulators.network_status.exceptions import CacheError


logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract interface for cache backends."""
    
    @abstractmethod
    def get(self, key: str) -> Optional[Dict]:
        """
        Get cached data if not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached data or None if not found/expired
        """
        pass
    
    @abstractmethod
    def set(self, key: str, data: Dict, ttl: Optional[int] = None):
        """
        Store data in cache with optional TTL.
        
        Args:
            key: Cache key
            data: Data to cache
            ttl: Time-to-live in seconds (None = use default)
        """
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        Delete a cache entry.
        
        Args:
            key: Cache key
            
        Returns:
            True if deleted, False if not found
        """
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists and not expired
        """
        pass
    
    @abstractmethod
    def scan(self, pattern: str) -> List[str]:
        """
        Find keys matching pattern.
        
        Args:
            pattern: Glob pattern (e.g., "namespace/*/interfaces")
            
        Returns:
            List of matching keys
        """
        pass
    
    @abstractmethod
    def clear(self):
        """Clear all cache entries."""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache stats
        """
        pass


class SharedMemoryBackend(CacheBackend):
    """
    Shared memory implementation of cache backend using /dev/shm.
    
    Stores cache entries as JSON files with metadata for expiration.
    Uses file locking for concurrent access safety.
    """
    
    def __init__(self, base_path: str = '/dev/shm/tsim/network_status_cache', 
                 default_ttl: int = 3600):
        """
        Initialize shared memory backend.
        
        Args:
            base_path: Base directory for cache files
            default_ttl: Default TTL in seconds
        """
        self.base_path = Path(base_path)
        self.default_ttl = default_ttl
        # Create cache directory first
        try:
            self.base_path.mkdir(parents=True, exist_ok=True, mode=0o775)
            # Set group permissions if tsim-users group exists
            try:
                import grp
                tsim_gid = grp.getgrnam('tsim-users').gr_gid
                os.chown(str(self.base_path), -1, tsim_gid)
            except (KeyError, OSError):
                pass  # Group doesn't exist or no permission
        except OSError as e:
            logger.error(f"Failed to create cache directory: {e}")
            raise CacheError(f"Cannot create cache directory: {e}")
        
        # Initialize stats - load from file if exists, otherwise create new
        self.stats_file = self.base_path / '.cache_stats.json'
        self.stats = self._load_stats()
    
    def _get_file_path(self, key: str) -> Path:
        """Convert cache key to file path."""
        # Sanitize key for filesystem
        safe_key = key.replace('/', '_')
        return self.base_path / f"{safe_key}.json"
    
    def _get_metadata_path(self, key: str) -> Path:
        """Get metadata file path for a cache entry."""
        safe_key = key.replace('/', '_')
        return self.base_path / f"{safe_key}.meta"
    
    def _read_with_lock(self, file_path: Path) -> Optional[Dict]:
        """Read file with shared lock."""
        if not file_path.exists():
            return None
            
        try:
            with open(file_path, 'r') as f:
                # Acquire shared lock for reading
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    data = json.load(f)
                    return data
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (IOError, json.JSONDecodeError) as e:
            logger.debug(f"Failed to read cache file {file_path}: {e}")
            return None
    
    def _write_with_lock(self, file_path: Path, data: Dict):
        """Write file with exclusive lock."""
        try:
            # Write to temp file first for atomicity
            temp_path = file_path.with_suffix('.tmp')
            with open(temp_path, 'w') as f:
                # Acquire exclusive lock for writing
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(data, f, indent=2, sort_keys=True)
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            # Atomic rename
            temp_path.replace(file_path)
            
            # Set permissions
            try:
                os.chmod(str(file_path), 0o664)
                # Set group if tsim-users exists
                import grp
                try:
                    tsim_gid = grp.getgrnam('tsim-users').gr_gid
                    os.chown(str(file_path), -1, tsim_gid)
                except (KeyError, OSError):
                    pass
            except OSError:
                pass
                
        except IOError as e:
            logger.error(f"Failed to write cache file {file_path}: {e}")
            raise CacheError(f"Cannot write cache file: {e}")
    
    def _load_stats(self) -> Dict[str, int]:
        """Load stats from file or create new stats."""
        try:
            if self.stats_file.exists():
                with open(self.stats_file, 'r') as f:
                    fcntl.flock(f, fcntl.LOCK_SH)
                    data = json.load(f)
                    return {
                        'hits': data.get('hits', 0),
                        'misses': data.get('misses', 0),
                        'sets': data.get('sets', 0),
                        'deletes': data.get('deletes', 0),
                        'errors': data.get('errors', 0)
                    }
        except Exception as e:
            logger.debug(f"Could not load stats file: {e}")
        
        # Return default stats
        return {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'errors': 0
        }
    
    def _save_stats(self):
        """Save stats to file."""
        try:
            with open(self.stats_file, 'w') as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                json.dump(self.stats, f)
        except Exception as e:
            logger.debug(f"Could not save stats file: {e}")
    
    def get(self, key: str) -> Optional[Dict]:
        """Get cached data if not expired."""
        try:
            # Read metadata
            meta_path = self._get_metadata_path(key)
            metadata = self._read_with_lock(meta_path)
            
            if not metadata:
                self.stats['misses'] += 1
                self._save_stats()
                return None
            
            # Check expiration
            expires_at = metadata.get('expires_at', 0)
            if expires_at > 0 and time.time() > expires_at:
                logger.debug(f"Cache expired for key: {key}")
                self.stats['misses'] += 1
                self._save_stats()
                # Clean up expired entry
                self.delete(key)
                return None
            
            # Read data
            data_path = self._get_file_path(key)
            data = self._read_with_lock(data_path)
            
            # If we have metadata, this is always a cache hit, even if data is empty
            self.stats['hits'] += 1
            self._save_stats()
            logger.debug(f"Cache hit for key: {key}")
            return data  # Return data as-is, even if None or empty
                
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            self.stats['errors'] += 1
            self._save_stats()
            return None
    
    def set(self, key: str, data: Dict, ttl: Optional[int] = None):
        """Store data in cache with optional TTL."""
        try:
            ttl = ttl if ttl is not None else self.default_ttl
            
            # Prepare metadata
            metadata = {
                'key': key,
                'created_at': time.time(),
                'expires_at': time.time() + ttl if ttl > 0 else 0,
                'ttl': ttl,
                'size': len(json.dumps(data))
            }
            
            # Write data
            data_path = self._get_file_path(key)
            self._write_with_lock(data_path, data)
            
            # Write metadata
            meta_path = self._get_metadata_path(key)
            self._write_with_lock(meta_path, metadata)
            
            self.stats['sets'] += 1
            self._save_stats()
            logger.debug(f"Cache set for key: {key} (TTL: {ttl}s)")
            
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            self.stats['errors'] += 1
            self._save_stats()
            raise CacheError(f"Failed to cache data: {e}")
    
    def delete(self, key: str) -> bool:
        """Delete a cache entry."""
        try:
            data_path = self._get_file_path(key)
            meta_path = self._get_metadata_path(key)
            
            deleted = False
            if data_path.exists():
                data_path.unlink()
                deleted = True
            if meta_path.exists():
                meta_path.unlink()
                deleted = True
                
            if deleted:
                self.stats['deletes'] += 1
                self._save_stats()
                logger.debug(f"Cache deleted for key: {key}")
                
            return deleted
            
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            self.stats['errors'] += 1
            self._save_stats()
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache and not expired."""
        meta_path = self._get_metadata_path(key)
        if not meta_path.exists():
            return False
            
        metadata = self._read_with_lock(meta_path)
        if not metadata:
            return False
            
        # Check expiration
        expires_at = metadata.get('expires_at', 0)
        if expires_at > 0 and time.time() > expires_at:
            return False
            
        return True
    
    def scan(self, pattern: str) -> List[str]:
        """Find keys matching pattern."""
        try:
            # Convert pattern to file pattern
            safe_pattern = pattern.replace('/', '_')
            file_pattern = str(self.base_path / f"{safe_pattern}.meta")
            
            matching_keys = []
            for meta_file in glob_module.glob(file_pattern):
                meta_path = Path(meta_file)
                metadata = self._read_with_lock(meta_path)
                
                if metadata:
                    # Check if not expired
                    expires_at = metadata.get('expires_at', 0)
                    if expires_at == 0 or time.time() <= expires_at:
                        matching_keys.append(metadata.get('key'))
                        
            return matching_keys
            
        except Exception as e:
            logger.error(f"Cache scan error for pattern {pattern}: {e}")
            self.stats['errors'] += 1
            self._save_stats()
            return []
    
    def clear(self):
        """Clear all cache entries."""
        try:
            for file_path in self.base_path.glob("*.json"):
                file_path.unlink()
            for file_path in self.base_path.glob("*.meta"):
                file_path.unlink()
                
            logger.info("Cache cleared")
            
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
            self.stats['errors'] += 1
            self._save_stats()
            raise CacheError(f"Failed to clear cache: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            # Count files and calculate size
            data_files = list(self.base_path.glob("*.json"))
            meta_files = list(self.base_path.glob("*.meta"))
            
            total_size = sum(f.stat().st_size for f in data_files + meta_files)
            
            # Count expired entries
            expired = 0
            for meta_file in meta_files:
                metadata = self._read_with_lock(meta_file)
                if metadata:
                    expires_at = metadata.get('expires_at', 0)
                    if expires_at > 0 and time.time() > expires_at:
                        expired += 1
            
            return {
                **self.stats,
                'entries': len(data_files),
                'expired': expired,
                'size_bytes': total_size,
                'size_mb': round(total_size / (1024 * 1024), 2),
                'path': str(self.base_path)
            }
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return self.stats


class CacheManager:
    """
    High-level cache manager with backend abstraction.
    
    Provides namespace-specific caching operations with
    support for different cache backends.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize cache manager.
        
        Args:
            config: Cache configuration dictionary
        """
        config = config or {}
        self.enabled = config.get('enabled', True)
        
        if not self.enabled:
            logger.info("Cache disabled by configuration")
            self.backend = None
            return
        
        # Select backend based on configuration
        backend_type = config.get('backend', 'shared_memory')
        
        if backend_type == 'shared_memory':
            self.backend = SharedMemoryBackend(
                base_path=config.get('base_path', '/dev/shm/tsim/network_status_cache'),
                default_ttl=config.get('expiration_seconds', 3600)
            )
        elif backend_type == 'redis':
            # Future: Import and initialize RedisBackend
            raise NotImplementedError("Redis backend not yet implemented")
        elif backend_type == 'sqlite':
            # Future: Import and initialize SQLiteBackend
            raise NotImplementedError("SQLite backend not yet implemented")
        else:
            raise CacheError(f"Unknown cache backend: {backend_type}")
        
        logger.info(f"Cache initialized with {backend_type} backend")
    
    def get_namespace_data(self, namespace: str, data_type: str) -> Optional[Dict]:
        """
        Get cached namespace data.
        
        Args:
            namespace: Namespace name
            data_type: Type of data (interfaces, routes, etc.)
            
        Returns:
            Cached data or None
        """
        if not self.enabled or not self.backend:
            return None
            
        key = f"namespace/{namespace}/{data_type}"
        return self.backend.get(key)
    
    def set_namespace_data(self, namespace: str, data_type: str, data: Dict, 
                          ttl: Optional[int] = None):
        """
        Cache namespace data.
        
        Args:
            namespace: Namespace name
            data_type: Type of data
            data: Data to cache
            ttl: Optional TTL override
        """
        if not self.enabled or not self.backend:
            return
            
        key = f"namespace/{namespace}/{data_type}"
        self.backend.set(key, data, ttl)
    
    def get_all_namespace_data(self, namespace: str) -> Dict[str, Dict]:
        """
        Get all cached data for a namespace.
        
        Args:
            namespace: Namespace name
            
        Returns:
            Dictionary of data_type -> data
        """
        if not self.enabled or not self.backend:
            return {}
            
        result = {}
        for data_type in ['interfaces', 'routes', 'rules', 'iptables', 'ipsets']:
            data = self.get_namespace_data(namespace, data_type)
            if data:
                result[data_type] = data
                
        return result
    
    def invalidate_namespace(self, namespace: str):
        """
        Invalidate all cache entries for a namespace.
        
        Args:
            namespace: Namespace name
        """
        if not self.enabled or not self.backend:
            return
            
        pattern = f"namespace/{namespace}/*"
        for key in self.backend.scan(pattern):
            self.backend.delete(key)
            
        logger.info(f"Cache invalidated for namespace: {namespace}")
    
    def invalidate_all(self):
        """Invalidate all cache entries."""
        if not self.enabled or not self.backend:
            return
            
        self.backend.clear()
        logger.info("All cache invalidated")
    
    def warm_cache(self, namespaces: List[str], data_collector=None):
        """
        Pre-populate cache for specified namespaces.
        
        Args:
            namespaces: List of namespace names
            data_collector: DataCollector instance for fetching data
        """
        if not self.enabled or not self.backend or not data_collector:
            return
            
        logger.info(f"Warming cache for {len(namespaces)} namespaces")
        # This will be implemented when DataCollector is available
        pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self.enabled or not self.backend:
            return {'enabled': False}
            
        stats = self.backend.get_stats()
        stats['enabled'] = True
        return stats