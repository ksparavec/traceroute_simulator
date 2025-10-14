#!/usr/bin/env -S python3 -B -u
"""
TSIM Session Manager Service
High-performance session management using /dev/shm (RAM disk)
"""

import os
import json
import time
import fcntl
import secrets
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from http.cookies import SimpleCookie


class TsimSessionManager:
    """High-performance session management using RAM disk"""
    
    def __init__(self, config_service):
        """Initialize session manager
        
        Args:
            config_service: TsimConfigService instance
        """
        self.config = config_service
        self.logger = logging.getLogger('tsim.session')
        
        # Use /dev/shm for ultra-fast session storage
        self.session_dir = Path(config_service.get('session_dir', '/dev/shm/tsim'))
        self.timeout = config_service.get('session_timeout', 3600)
        
        # Ensure session directory exists with proper permissions
        try:
            self.session_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.logger.info(f"Using session directory: {self.session_dir}")
        except Exception as e:
            self.logger.error(f"Failed to create session directory: {e}")
            # Use config-based fallback
            fallback_dir = config_service.get('session_dir', '/dev/shm/tsim/sessions')
            self.session_dir = Path(fallback_dir)
            self.session_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.logger.warning(f"Using fallback session directory: {self.session_dir}")
    
    def create_session(self, username: str, ip_address: Optional[str] = None,
                      role: str = 'user', auth_method: str = 'local') -> tuple:
        """Create a new session

        Args:
            username: Username for the session
            ip_address: Client IP address
            role: User role (user/admin)
            auth_method: Authentication method (local/pam)

        Returns:
            Tuple of (session_id, cookie_header)
        """
        # Generate secure session ID
        session_id = secrets.token_urlsafe(32)
        session_file = self.session_dir / f"{session_id}.json"

        # Create session data
        session_data = {
            'session_id': session_id,
            'username': username,
            'role': role,
            'created': time.time(),
            'last_access': time.time(),
            'login_timestamp': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
            'auth_method': auth_method,
            'ip_address': ip_address or 'unknown',
            'form_data': {},
            'test_results': {},
            'active_tests': []
        }
        
        # Write session file with atomic operation
        try:
            # Write to temp file first
            temp_file = session_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(session_data, f)
                f.flush()
                os.fsync(f.fileno())
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            # Atomic rename
            temp_file.rename(session_file)
            
            self.logger.info(f"Created session {session_id} for user {username}")
        except Exception as e:
            self.logger.error(f"Failed to create session: {e}")
            raise
        
        # Create secure cookie
        cookie = SimpleCookie()
        cookie['session_id'] = session_id
        cookie['session_id']['httponly'] = True
        cookie['session_id']['secure'] = True  # Requires HTTPS
        cookie['session_id']['samesite'] = 'Strict'
        cookie['session_id']['max-age'] = self.timeout
        cookie['session_id']['path'] = '/'
        
        return session_id, cookie['session_id'].OutputString()
    
    def get_session(self, session_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Get session data
        
        Args:
            session_id: Session ID
            
        Returns:
            Session data dict or None if not found/expired
        """
        if not session_id:
            return None
        
        # Validate session ID format
        if not self._validate_session_id(session_id):
            self.logger.warning(f"Invalid session ID format: {session_id}")
            return None
        
        session_file = self.session_dir / f"{session_id}.json"
        
        if not session_file.exists():
            return None
        
        try:
            with open(session_file, 'r') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                data = json.load(f)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            # Check if session has expired
            if time.time() - data.get('last_access', 0) > self.timeout:
                self.logger.info(f"Session {session_id} has expired")
                self.destroy_session(session_id)
                return None
            
            # Update last access time
            self._update_last_access(session_id)
            
            return data
        except Exception as e:
            self.logger.error(f"Error reading session {session_id}: {e}")
            return None
    
    def update_session(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Update session data

        Args:
            session_id: Session ID
            data: Data to update

        Returns:
            True if successful, False otherwise
        """
        if not self._validate_session_id(session_id):
            return False

        session_file = self.session_dir / f"{session_id}.json"
        lock_file = self.session_dir / f"{session_id}.lock"

        if not session_file.exists():
            return False

        # Use separate lock file to coordinate read-modify-write across threads
        try:
            with open(lock_file, 'a') as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

                try:
                    # Read existing data (under lock)
                    with open(session_file, 'r') as f:
                        session_data = json.load(f)

                    # Update data (under lock)
                    session_data.update(data)
                    session_data['last_access'] = time.time()

                    # Write back (under lock)
                    temp_file = session_file.with_suffix('.tmp')
                    with open(temp_file, 'w') as f:
                        json.dump(session_data, f)
                        f.flush()
                        os.fsync(f.fileno())

                    # Atomic rename (under lock)
                    temp_file.rename(session_file)

                    return True
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            self.logger.error(f"Error updating session {session_id}: {e}")
            return False
    
    def save_test_result(self, session_id: str, run_id: str, 
                        result: Dict[str, Any]) -> bool:
        """Save test result to session
        
        Args:
            session_id: Session ID
            run_id: Test run ID
            result: Test result data
            
        Returns:
            True if successful, False otherwise
        """
        session = self.get_session(session_id)
        if not session:
            return False
        
        # Update test results
        test_results = session.get('test_results', {})
        test_results[run_id] = {
            'timestamp': time.time(),
            'data': result
        }
        
        # Keep only last 10 results
        if len(test_results) > 10:
            # Remove oldest entries
            sorted_results = sorted(test_results.items(), 
                                  key=lambda x: x[1]['timestamp'])
            for old_run_id, _ in sorted_results[:-10]:
                del test_results[old_run_id]
        
        return self.update_session(session_id, {'test_results': test_results})
    
    def get_test_result(self, session_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        """Get test result from session
        
        Args:
            session_id: Session ID
            run_id: Test run ID
            
        Returns:
            Test result data or None
        """
        session = self.get_session(session_id)
        if not session:
            return None
        
        test_results = session.get('test_results', {})
        if run_id in test_results:
            return test_results[run_id].get('data')
        
        return None
    
    def destroy_session(self, session_id: str) -> bool:
        """Destroy a session
        
        Args:
            session_id: Session ID
            
        Returns:
            True if successful, False otherwise
        """
        if not self._validate_session_id(session_id):
            return False
        
        session_file = self.session_dir / f"{session_id}.json"
        
        try:
            if session_file.exists():
                session_file.unlink()
                self.logger.info(f"Destroyed session {session_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error destroying session {session_id}: {e}")
            return False
    
    def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions
        
        Returns:
            Number of sessions cleaned up
        """
        cleaned = 0
        current_time = time.time()
        
        try:
            for session_file in self.session_dir.glob('*.json'):
                try:
                    # Check file age
                    if current_time - session_file.stat().st_mtime > self.timeout:
                        session_file.unlink()
                        cleaned += 1
                except Exception as e:
                    self.logger.warning(f"Error cleaning session file {session_file}: {e}")
        except Exception as e:
            self.logger.error(f"Error during session cleanup: {e}")
        
        if cleaned > 0:
            self.logger.info(f"Cleaned up {cleaned} expired sessions")
        
        return cleaned
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get list of active sessions
        
        Returns:
            List of active session summaries
        """
        sessions = []
        current_time = time.time()
        
        try:
            for session_file in self.session_dir.glob('*.json'):
                try:
                    with open(session_file, 'r') as f:
                        data = json.load(f)
                    
                    # Check if not expired
                    if current_time - data.get('last_access', 0) <= self.timeout:
                        sessions.append({
                            'session_id': data.get('session_id'),
                            'username': data.get('username'),
                            'created': data.get('created'),
                            'last_access': data.get('last_access'),
                            'ip_address': data.get('ip_address')
                        })
                except Exception:
                    continue
        except Exception as e:
            self.logger.error(f"Error getting active sessions: {e}")
        
        return sessions
    
    def _validate_session_id(self, session_id: str) -> bool:
        """Validate session ID format
        
        Args:
            session_id: Session ID to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Session ID should be alphanumeric with - and _
        if not session_id:
            return False
        
        # Check length (token_urlsafe(32) produces ~43 chars)
        if len(session_id) < 32 or len(session_id) > 64:
            return False
        
        # Check characters
        allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_')
        return all(c in allowed_chars for c in session_id)
    
    def _update_last_access(self, session_id: str):
        """Update last access time for a session
        
        Args:
            session_id: Session ID
        """
        session_file = self.session_dir / f"{session_id}.json"
        
        try:
            # Just update the file's modification time
            # This is faster than rewriting the whole file
            session_file.touch()
        except Exception:
            pass  # Non-critical error