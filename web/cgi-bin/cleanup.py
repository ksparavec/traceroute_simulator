#!/usr/bin/env -S python3 -B -u
"""
Maintenance script for cleaning old data and expired sessions
Run via cron daily
"""
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from config import Config
from session import SessionManager
from executor import CommandExecutor
from logger import AuditLogger
from lock_manager import NetworkLockManager

def main():
    config = Config()
    logger = AuditLogger()
    
    try:
        # Clean up expired sessions
        session_mgr = SessionManager()
        session_mgr.cleanup_expired_sessions()
        logger.log_info("Cleaned up expired sessions")
        
        # Clean up old data files
        executor = CommandExecutor(config, logger)
        executor.cleanup_old_data()
        logger.log_info("Cleaned up old data files")
        
        # Check and clean up stale locks
        lock_mgr = NetworkLockManager(logger)
        # Try to acquire lock with short timeout
        try:
            lock_mgr.acquire(timeout=5)
            lock_mgr.release()
        except TimeoutError:
            logger.log_warning("Network test lock may be stale")
            
    except Exception as e:
        logger.log_error("Cleanup script error", str(e))

if __name__ == "__main__":
    main()