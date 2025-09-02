#!/usr/bin/env -S python3 -B -u
"""POSIX locking mechanism for preventing concurrent executions"""
import posix_ipc
import time
import os
import signal
import sys
from config import Config

class NetworkLockManager:
    """
    Manages POSIX semaphore for network_reachability_test.sh
    to prevent concurrent executions that could cause race conditions
    """
    
    SEMAPHORE_NAME = "/traceroute_network_test_lock"
    LOCK_TIMEOUT = 300  # 5 minutes max wait
    
    def __init__(self, logger=None):
        self.logger = logger
        self.semaphore = None
        self.acquired = False
        
        # Load config to get unix_group
        config = Config()
        self.unix_group = config.config.get('unix_group', 'tsim-users')
        
    def __enter__(self):
        """Context manager entry - acquire lock"""
        self.acquire()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - release lock"""
        self.release()
        
    def acquire(self, timeout=LOCK_TIMEOUT):
        """
        Acquire the network test lock with timeout
        """
        start_time = time.time()
        
        try:
            # Create or get existing semaphore
            self.semaphore = posix_ipc.Semaphore(
                self.SEMAPHORE_NAME,
                flags=posix_ipc.O_CREAT,
                initial_value=1
            )
            
            # Fix group ownership of semaphore file
            try:
                import grp
                import subprocess
                sem_path = f"/dev/shm/sem.{self.SEMAPHORE_NAME[1:]}"  # Remove leading /
                tsim_gid = grp.getgrnam(self.unix_group).gr_gid
                
                # Check current ownership
                stat_info = os.stat(sem_path)
                if stat_info.st_gid != tsim_gid:
                    # Change group ownership
                    if os.geteuid() == 0:
                        os.chown(sem_path, -1, tsim_gid)  # -1 means don't change user
                    else:
                        # Use sudo if not root
                        subprocess.run(['sudo', 'chgrp', self.unix_group, sem_path], 
                                     check=False, capture_output=True)
                    
                    # Also set group read/write permissions
                    os.chmod(sem_path, 0o660)
            except Exception as e:
                # Log but don't fail - semaphore still works
                if self.logger:
                    self.logger.log_info(f"Could not change semaphore group: {e}")
            
            # Try to acquire with polling
            while True:
                try:
                    self.semaphore.acquire(timeout=0)  # Non-blocking
                    self.acquired = True
                    if self.logger:
                        self.logger.log_info(
                            f"Acquired network test lock after "
                            f"{time.time() - start_time:.2f} seconds"
                        )
                    break
                except posix_ipc.BusyError:
                    # Check timeout
                    if time.time() - start_time > timeout:
                        raise TimeoutError(
                            f"Failed to acquire lock after {timeout} seconds"
                        )
                    
                    if self.logger:
                        wait_time = time.time() - start_time
                        if int(wait_time) % 10 == 0:  # Log every 10 seconds
                            self.logger.log_info(
                                f"Waiting for network test lock... "
                                f"{wait_time:.0f}s elapsed"
                            )
                    
                    time.sleep(0.5)  # Wait 500ms before retry
                    
        except Exception as e:
            if self.logger:
                self.logger.log_error("Lock acquisition failed", str(e))
            raise
            
    def release(self):
        """Release the network test lock"""
        if self.semaphore and self.acquired:
            try:
                self.semaphore.release()
                self.acquired = False
                if self.logger:
                    self.logger.log_info("Released network test lock")
            except Exception as e:
                if self.logger:
                    self.logger.log_error("Lock release failed", str(e))
                    
    def cleanup(self):
        """Remove the semaphore (for maintenance)"""
        try:
            sem = posix_ipc.Semaphore(self.SEMAPHORE_NAME)
            sem.unlink()
            if self.logger:
                self.logger.log_info("Cleaned up network test semaphore")
        except posix_ipc.ExistentialError:
            pass  # Semaphore doesn't exist