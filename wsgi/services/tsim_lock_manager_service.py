#!/usr/bin/env -S python3 -B -u
"""
TSIM Lock Manager Service
Manages locks for concurrent operations
"""

import os
import fcntl
import time
import threading
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import contextmanager


class TsimLockManagerService:
    """Lock management service for preventing concurrent test execution"""
    
    def __init__(self, config_service):
        """Initialize lock manager
        
        Args:
            config_service: TsimConfigService instance
        """
        self.config = config_service
        self.logger = logging.getLogger('tsim.locks')
        
        # Lock directory
        self.lock_dir = Path(config_service.get('lock_dir', '/dev/shm/tsim/locks'))
        
        # Ensure lock directory exists
        try:
            self.lock_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
            self.logger.debug(f"Using lock directory: {self.lock_dir}")
        except Exception as e:
            self.logger.error(f"Failed to create lock directory: {e}")
            # Use config-based fallback
            fallback_dir = config_service.get('lock_dir', '/dev/shm/tsim/locks')
            self.lock_dir = Path(fallback_dir)
            self.lock_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
        
        # In-memory locks for thread synchronization
        self.thread_locks = {}
        self.thread_lock_mutex = threading.Lock()
        
        # File-based locks for process synchronization
        self.file_locks = {}
        # Optional legacy lock FDs (for network_test compatibility)
        self.legacy_file_locks = {}
    
    def acquire_lock(self, lock_name: str, timeout: float = 60.0, 
                    retry_interval: float = 0.5) -> bool:
        """Acquire a named lock
        
        Args:
            lock_name: Name of the lock
            timeout: Maximum time to wait for lock (seconds)
            retry_interval: Time between retry attempts (seconds)
            
        Returns:
            True if lock acquired, False if timeout
        """
        # Thread-level locking first
        with self.thread_lock_mutex:
            if lock_name not in self.thread_locks:
                self.thread_locks[lock_name] = threading.Lock()
            thread_lock = self.thread_locks[lock_name]
        
        # Try to acquire thread lock
        if not thread_lock.acquire(timeout=timeout):
            self.logger.warning(f"Failed to acquire thread lock: {lock_name}")
            return False
        
        # Now try file-based lock for inter-process synchronization
        lock_file = self.lock_dir / f"{lock_name}.lock"
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Open or create lock file
                fd = os.open(str(lock_file), os.O_CREAT | os.O_WRONLY, 0o644)
                
                # Try to acquire exclusive lock (non-blocking)
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                
                # Write PID and timestamp
                lock_info = f"{os.getpid()}\n{time.time()}\n"
                os.write(fd, lock_info.encode())
                os.fsync(fd)
                
                # Store file descriptor
                self.file_locks[lock_name] = fd

                # Also acquire legacy global lock for network_test to ensure cross-tool serialization
                if lock_name == 'network_test':
                    legacy_path = '/dev/shm/tsim/network_test.lock'
                    try:
                        lfd = os.open(legacy_path, os.O_CREAT | os.O_WRONLY, 0o664)
                        fcntl.flock(lfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        os.write(lfd, f"{os.getpid()}\n".encode())
                        os.fsync(lfd)
                        self.legacy_file_locks[lock_name] = lfd
                    except BlockingIOError:
                        # Release primary lock and retry after interval to avoid split-brain
                        try:
                            fcntl.flock(fd, fcntl.LOCK_UN)
                            os.close(fd)
                            del self.file_locks[lock_name]
                        except Exception:
                            pass
                        time.sleep(retry_interval)
                        continue
                    except Exception as _e:
                        # If legacy lock fails for other reasons, log and proceed with primary
                        self.logger.debug(f"Legacy lock acquisition issue: {_e}")

                self.logger.debug(f"Acquired lock: {lock_name}")
                return True

            except BlockingIOError:
                # Lock is held by another process
                os.close(fd)
                time.sleep(retry_interval)
                
            except Exception as e:
                self.logger.error(f"Error acquiring lock {lock_name}: {e}")
                # Release thread lock on error
                thread_lock.release()
                return False
        
        # Timeout reached
        thread_lock.release()
        if lock_name == 'scheduler_leader':
            self.logger.debug(f"Timeout acquiring lock: {lock_name}")
        else:
            self.logger.warning(f"Timeout acquiring lock: {lock_name}")
        return False
    
    def release_lock(self, lock_name: str) -> bool:
        """Release a named lock
        
        Args:
            lock_name: Name of the lock
            
        Returns:
            True if released successfully
        """
        success = True
        
        # Release file lock first
        if lock_name in self.file_locks:
            fd = self.file_locks[lock_name]
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                del self.file_locks[lock_name]
                
                # Optionally remove lock file
                lock_file = self.lock_dir / f"{lock_name}.lock"
                try:
                    lock_file.unlink()
                except:
                    pass  # Non-critical
                
                self.logger.debug(f"Released lock: {lock_name}")
            except Exception as e:
                self.logger.error(f"Error releasing file lock {lock_name}: {e}")
                success = False

        # Release legacy lock if held
        if lock_name in self.legacy_file_locks:
            lfd = self.legacy_file_locks[lock_name]
            try:
                fcntl.flock(lfd, fcntl.LOCK_UN)
                os.close(lfd)
                del self.legacy_file_locks[lock_name]
            except Exception as e:
                self.logger.warning(f"Error releasing legacy lock {lock_name}: {e}")
        
        # Release thread lock
        with self.thread_lock_mutex:
            if lock_name in self.thread_locks:
                try:
                    self.thread_locks[lock_name].release()
                except RuntimeError:
                    # Lock was not acquired
                    pass
        
        return success
    
    @contextmanager
    def lock(self, lock_name: str, timeout: float = 60.0):
        """Context manager for locks
        
        Usage:
            with lock_manager.lock('test_execution'):
                # Critical section
                pass
        
        Args:
            lock_name: Name of the lock
            timeout: Maximum time to wait for lock
            
        Yields:
            None if lock acquired
            
        Raises:
            TimeoutError: If lock cannot be acquired
        """
        if not self.acquire_lock(lock_name, timeout):
            raise TimeoutError(f"Could not acquire lock: {lock_name}")
        
        try:
            yield
        finally:
            self.release_lock(lock_name)
    
    def is_locked(self, lock_name: str) -> bool:
        """Check if a lock is currently held
        
        Args:
            lock_name: Name of the lock
            
        Returns:
            True if locked, False otherwise
        """
        lock_file = self.lock_dir / f"{lock_name}.lock"
        
        if not lock_file.exists():
            return False
        
        try:
            # Try to acquire lock non-blocking
            fd = os.open(str(lock_file), os.O_WRONLY)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # If we got here, lock was not held
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            return False
        except BlockingIOError:
            # Lock is held
            return True
        except Exception:
            # Assume not locked on error
            return False
    
    def get_lock_info(self, lock_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a lock
        
        Args:
            lock_name: Name of the lock
            
        Returns:
            Lock information or None if not locked
        """
        lock_file = self.lock_dir / f"{lock_name}.lock"
        
        if not lock_file.exists():
            return None
        
        try:
            with open(lock_file, 'r') as f:
                lines = f.readlines()
            
            if len(lines) >= 2:
                pid = int(lines[0].strip())
                timestamp = float(lines[1].strip())
                
                return {
                    'lock_name': lock_name,
                    'pid': pid,
                    'timestamp': timestamp,
                    'age': time.time() - timestamp,
                    'locked': self.is_locked(lock_name)
                }
        except Exception as e:
            self.logger.error(f"Error reading lock info for {lock_name}: {e}")
        
        return None
    
    def cleanup_stale_locks(self, max_age: Optional[float] = None) -> int:
        """Clean up stale lock files
        
        Args:
            max_age: Maximum age in seconds before considering lock stale, defaults to session_timeout
            
        Returns:
            Number of locks cleaned up
        """
        if max_age is None:
            max_age = self.config.get('session_timeout', 3600)
        cleaned = 0
        current_time = time.time()
        
        try:
            for lock_file in self.lock_dir.glob("*.lock"):
                try:
                    # Check if lock is stale
                    with open(lock_file, 'r') as f:
                        lines = f.readlines()
                    
                    if len(lines) >= 2:
                        timestamp = float(lines[1].strip())
                        age = current_time - timestamp
                        
                        if age > max_age:
                            # Check if still locked
                            if not self.is_locked(lock_file.stem):
                                lock_file.unlink()
                                cleaned += 1
                                self.logger.info(f"Cleaned stale lock: {lock_file.name}")
                except Exception as e:
                    self.logger.warning(f"Error checking lock file {lock_file}: {e}")
        except Exception as e:
            self.logger.error(f"Error during lock cleanup: {e}")
        
        if cleaned > 0:
            self.logger.info(f"Cleaned {cleaned} stale locks")
        
        return cleaned
    
    def release_all_locks(self):
        """Release all locks held by this process"""
        # Release all file locks
        for lock_name in list(self.file_locks.keys()):
            self.release_lock(lock_name)
        
        self.logger.info("Released all locks")
    
    def __del__(self):
        """Cleanup on deletion"""
        try:
            self.release_all_locks()
        except:
            pass
