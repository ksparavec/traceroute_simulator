#!/usr/bin/env -S python3 -B -u
"""
TSIM DSCP Registry Service
Thread-safe DSCP allocation registry for parallel KSMS jobs
"""

import os
import json
import time
import fcntl
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List


class TsimDscpRegistry:
    """Thread-safe DSCP allocation registry for parallel KSMS jobs"""
    
    def __init__(self, config_service):
        """Initialize DSCP registry
        
        Args:
            config_service: TsimConfigService instance
        """
        self.config = config_service
        self.logger = logging.getLogger('tsim.dscp_registry')
        
        # Registry files - same pattern as other registries (directly in data_dir)
        base_dir = Path(config_service.get('data_dir', '/dev/shm/tsim'))
        self.registry_file = base_dir / 'dscp_registry.json'
        self.lock_file = base_dir / 'dscp_registry.lock'
        
        # Thread safety
        self.semaphore = threading.Semaphore(1)
        
        # DSCP allocation configuration
        dscp_config = config_service.get('dscp_registry', {})
        self.dscp_min = dscp_config.get('dscp_range_min', 32)
        self.dscp_max = dscp_config.get('dscp_range_max', 63)
        self.max_age = dscp_config.get('allocation_timeout', 3600)  # 1 hour
        self.enabled = dscp_config.get('enabled', True)
        
        # Validate DSCP range
        if self.dscp_min < 0 or self.dscp_max > 63 or self.dscp_min > self.dscp_max:
            raise ValueError(f"Invalid DSCP range: {self.dscp_min}-{self.dscp_max} (must be 0-63)")
        
        # Ensure base directory exists (should already exist)
        try:
            base_dir.mkdir(parents=True, exist_ok=True, mode=0o2775)  # Set group sticky bit
        except Exception as e:
            self.logger.warning(f"Failed to ensure base directory exists: {e}")
        
        # Initialize registry if missing
        if not self.registry_file.exists():
            self._save_registry({
                'version': 1,
                'created_at': time.time(),
                'updated_at': time.time(),
                'allocations': {}
            })

        # Clean up stale allocations from previous Apache processes on startup
        if self.enabled:
            try:
                cleaned = self.cleanup_stale_allocations()
                if cleaned > 0:
                    self.logger.info(f"Cleaned up {cleaned} stale DSCP allocations on startup")
            except Exception as e:
                self.logger.warning(f"Failed to cleanup stale allocations on startup: {e}")

        self.logger.info(f"DSCP Registry initialized: range {self.dscp_min}-{self.dscp_max} "
                        f"({'enabled' if self.enabled else 'disabled'})")
    
    def allocate_dscp(self, job_id: str, username: str = None) -> Optional[int]:
        """Allocate unique DSCP value for job
        
        Args:
            job_id: Unique job identifier
            username: Optional username for tracking
            
        Returns:
            DSCP value (32-63) or None if no DSCP available
            
        Raises:
            RuntimeError: If registry operations fail
        """
        if not self.enabled:
            self.logger.debug("DSCP registry disabled - using default DSCP 32")
            return 32
        
        with self.semaphore:
            try:
                # Use file lock for cross-process synchronization
                with self._file_lock():
                    registry = self._load_registry()
                    
                    # Clean up stale allocations first
                    cleaned = self._cleanup_stale_allocations(registry)
                    if cleaned > 0:
                        self.logger.debug(f"Cleaned up {cleaned} stale DSCP allocations")
                    
                    # Check if job already has allocation
                    if job_id in registry['allocations']:
                        existing = registry['allocations'][job_id]
                        self.logger.debug(f"Job {job_id} already has DSCP {existing['dscp']}")
                        return existing['dscp']
                    
                    # Find available DSCP
                    used_dscps = {entry['dscp'] for entry in registry['allocations'].values()}
                    available_dscps = set(range(self.dscp_min, self.dscp_max + 1)) - used_dscps
                    
                    if not available_dscps:
                        self.logger.warning(f"No DSCP values available for job {job_id} "
                                          f"({len(used_dscps)} allocated)")
                        return None
                    
                    # Allocate lowest available DSCP
                    dscp = min(available_dscps)
                    
                    # Create allocation record
                    allocation = {
                        'dscp': dscp,
                        'job_id': job_id,
                        'username': username or 'unknown',
                        'allocated_at': time.time(),
                        'pid': os.getpid(),
                        'status': 'active'
                    }
                    
                    registry['allocations'][job_id] = allocation
                    registry['updated_at'] = time.time()
                    
                    # Save updated registry
                    self._save_registry(registry)
                    
                    self.logger.info(f"Allocated DSCP {dscp} to job {job_id} "
                                   f"({len(registry['allocations'])}/{self.dscp_max - self.dscp_min + 1} used)")
                    
                    return dscp
                    
            except Exception as e:
                self.logger.error(f"Failed to allocate DSCP for job {job_id}: {e}")
                raise RuntimeError(f"DSCP allocation failed: {e}")
    
    def release_dscp(self, job_id: str) -> bool:
        """Release DSCP allocation for job
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if DSCP was released, False if not found
        """
        if not self.enabled:
            return True  # No allocation to release when disabled
        
        with self.semaphore:
            try:
                with self._file_lock():
                    registry = self._load_registry()
                    
                    if job_id not in registry['allocations']:
                        self.logger.debug(f"No DSCP allocation found for job {job_id}")
                        return False
                    
                    # Get allocation details for logging
                    allocation = registry['allocations'][job_id]
                    dscp = allocation['dscp']
                    
                    # Remove allocation
                    del registry['allocations'][job_id]
                    registry['updated_at'] = time.time()
                    
                    # Save updated registry
                    self._save_registry(registry)
                    
                    self.logger.info(f"Released DSCP {dscp} from job {job_id} "
                                   f"({len(registry['allocations'])}/{self.dscp_max - self.dscp_min + 1} used)")
                    
                    return True
                    
            except Exception as e:
                self.logger.error(f"Failed to release DSCP for job {job_id}: {e}")
                return False
    
    def get_job_dscp(self, job_id: str) -> Optional[int]:
        """Get allocated DSCP for job
        
        Args:
            job_id: Job identifier
            
        Returns:
            DSCP value or None if not allocated
        """
        if not self.enabled:
            return 32
        
        try:
            registry = self._load_registry()
            allocation = registry['allocations'].get(job_id)
            return allocation['dscp'] if allocation else None
        except Exception as e:
            self.logger.warning(f"Failed to get DSCP for job {job_id}: {e}")
            return None
    
    def get_allocation_status(self) -> Dict[str, Any]:
        """Get current allocation status
        
        Returns:
            Dictionary with allocation statistics
        """
        if not self.enabled:
            return {
                'enabled': False,
                'total_allocations': 0,
                'available_dscps': self.dscp_max - self.dscp_min + 1,
                'used_dscps': []
            }
        
        try:
            registry = self._load_registry()
            allocations = registry['allocations']
            used_dscps = sorted([alloc['dscp'] for alloc in allocations.values()])
            
            return {
                'enabled': True,
                'dscp_range': f"{self.dscp_min}-{self.dscp_max}",
                'total_capacity': self.dscp_max - self.dscp_min + 1,
                'total_allocations': len(allocations),
                'available_slots': (self.dscp_max - self.dscp_min + 1) - len(allocations),
                'used_dscps': used_dscps,
                'allocations': {
                    job_id: {
                        'dscp': alloc['dscp'],
                        'username': alloc['username'],
                        'allocated_at': alloc['allocated_at'],
                        'age_seconds': time.time() - alloc['allocated_at']
                    }
                    for job_id, alloc in allocations.items()
                }
            }
        except Exception as e:
            self.logger.error(f"Failed to get allocation status: {e}")
            return {'error': str(e)}
    
    def get_dscp_for_job(self, job_id: str) -> Optional[int]:
        """Get DSCP value for a specific job
        
        Args:
            job_id: Job identifier
            
        Returns:
            DSCP value or None if not found/not allocated
        """
        if not self.enabled:
            return None
        
        try:
            registry = self._load_registry()
            allocations = registry['allocations']
            
            if job_id in allocations:
                return allocations[job_id]['dscp']
            
            return None
        except Exception as e:
            self.logger.error(f"Failed to get DSCP for job {job_id}: {e}")
            return None
    
    def cleanup_stale_allocations(self) -> int:
        """Clean up stale allocations (public method)
        
        Returns:
            Number of allocations cleaned up
        """
        if not self.enabled:
            return 0
        
        with self.semaphore:
            try:
                with self._file_lock():
                    registry = self._load_registry()
                    cleaned = self._cleanup_stale_allocations(registry)
                    if cleaned > 0:
                        self._save_registry(registry)
                        self.logger.info(f"Cleaned up {cleaned} stale DSCP allocations")
                    return cleaned
            except Exception as e:
                self.logger.error(f"Failed to cleanup stale allocations: {e}")
                return 0
    
    def _file_lock(self):
        """Context manager for file-based locking"""
        class FileLock:
            def __init__(self, lock_file: Path):
                self.lock_file = lock_file
                self.fd = None
                
            def __enter__(self):
                try:
                    self.fd = os.open(str(self.lock_file), os.O_CREAT | os.O_RDWR, 0o664)
                    fcntl.flock(self.fd, fcntl.LOCK_EX)
                    return self
                except Exception:
                    if self.fd is not None:
                        os.close(self.fd)
                    raise
                    
            def __exit__(self, exc_type, exc_val, exc_tb):
                try:
                    if self.fd is not None:
                        fcntl.flock(self.fd, fcntl.LOCK_UN)
                        os.close(self.fd)
                except Exception:
                    pass
        
        return FileLock(self.lock_file)
    
    def _load_registry(self) -> Dict[str, Any]:
        """Load registry from file
        
        Returns:
            Registry data dictionary
        """
        if not self.registry_file.exists():
            return {
                'version': 1,
                'created_at': time.time(),
                'updated_at': time.time(),
                'allocations': {}
            }
        
        try:
            with open(self.registry_file, 'r') as f:
                registry = json.load(f)
                
            # Validate registry structure
            if not isinstance(registry.get('allocations'), dict):
                self.logger.warning("Invalid registry structure - reinitializing")
                return {
                    'version': 1,
                    'created_at': time.time(),
                    'updated_at': time.time(),
                    'allocations': {}
                }
                
            return registry
            
        except Exception as e:
            self.logger.error(f"Failed to load registry: {e} - reinitializing")
            return {
                'version': 1,
                'created_at': time.time(),
                'updated_at': time.time(),
                'allocations': {}
            }
    
    def _save_registry(self, registry: Dict[str, Any]):
        """Save registry to file atomically
        
        Args:
            registry: Registry data to save
        """
        # Use temporary file for atomic write
        tmp_file = self.registry_file.with_suffix('.tmp')
        
        try:
            with open(tmp_file, 'w') as f:
                json.dump(registry, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            
            # Set proper permissions (group writable like other registries)
            os.chmod(tmp_file, 0o664)  # rw-rw-r--
            
            # Atomic rename
            tmp_file.replace(self.registry_file)
            
        except Exception as e:
            # Clean up temporary file on error
            try:
                tmp_file.unlink()
            except Exception:
                pass
            raise RuntimeError(f"Failed to save registry: {e}")
    
    def _cleanup_stale_allocations(self, registry: Dict[str, Any]) -> int:
        """Remove stale allocations from registry
        
        Args:
            registry: Registry data to clean
            
        Returns:
            Number of allocations removed
        """
        stale_jobs = []
        current_time = time.time()
        
        for job_id, allocation in registry['allocations'].items():
            # Check if process still exists
            pid = allocation.get('pid', 0)
            process_alive = self._is_process_alive(pid)
            
            # Check allocation age
            allocated_at = allocation.get('allocated_at', 0)
            age = current_time - allocated_at
            too_old = age > self.max_age
            
            # Mark as stale if process dead or too old
            if not process_alive:
                stale_jobs.append((job_id, f"process {pid} not found"))
            elif too_old:
                stale_jobs.append((job_id, f"allocation expired ({age:.0f}s > {self.max_age}s)"))
        
        # Remove stale allocations
        for job_id, reason in stale_jobs:
            dscp = registry['allocations'][job_id]['dscp']
            del registry['allocations'][job_id]
            self.logger.debug(f"Cleaned up stale allocation: job={job_id}, dscp={dscp}, reason={reason}")
        
        if stale_jobs:
            registry['updated_at'] = current_time
        
        return len(stale_jobs)
    
    def _is_process_alive(self, pid: int) -> bool:
        """Check if process is still alive
        
        Args:
            pid: Process ID
            
        Returns:
            True if process exists, False otherwise
        """
        if pid <= 0:
            return False
        
        try:
            # Signal 0 checks process existence without sending signal
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False
    
    def __repr__(self) -> str:
        """String representation"""
        return f"TsimDscpRegistry(range={self.dscp_min}-{self.dscp_max}, enabled={self.enabled})"