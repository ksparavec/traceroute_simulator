#!/usr/bin/env -S python3 -B -u
"""
Shared Memory Manager for TSIM

Manages batch files in /dev/shm/tsim/ directory.
"""

import os
from pathlib import Path

class TsimBatchMemory:
    """
    Manages a batch file in /dev/shm/tsim/
    """
    
    def __init__(self, batch_name: str):
        """
        Initialize batch memory segment.
        
        Args:
            batch_name: Name for the batch file (without prefix)
        """
        self.batch_name = batch_name
        self.shm_dir = Path('/dev/shm/tsim')
        self.file_path = self.shm_dir / f"batch_{batch_name}"
        
        # Create directory if it doesn't exist
        self._ensure_directory()
        
    def _ensure_directory(self):
        """Ensure /dev/shm/tsim/ directory exists with proper permissions."""
        if not self.shm_dir.exists():
            self.shm_dir.mkdir(mode=0o2775, parents=True, exist_ok=True)
            # Try to set group to tsim-users if we have permissions
            try:
                import grp
                import pwd
                gid = grp.getgrnam('tsim-users').gr_gid
                uid = pwd.getpwuid(os.getuid()).pw_uid
                os.chown(self.shm_dir, uid, gid)
            except:
                # Ignore if we can't set group
                pass
                
    def write(self, content: str):
        """
        Write content to the batch file.
        
        Args:
            content: Content to write
        """
        with open(self.file_path, 'w') as f:
            f.write(content)
        # Set permissions
        os.chmod(self.file_path, 0o664)
        
    def read(self) -> str:
        """
        Read content from the batch file.
        
        Returns:
            File content
        """
        with open(self.file_path, 'r') as f:
            return f.read()
            
    def get_path(self) -> str:
        """
        Get the full path to the batch file.
        
        Returns:
            Full path as string
        """
        return str(self.file_path)
        
    def exists(self) -> bool:
        """
        Check if the batch file exists.
        
        Returns:
            True if file exists
        """
        return self.file_path.exists()
        
    def delete(self):
        """Delete the batch file if it exists."""
        if self.file_path.exists():
            self.file_path.unlink()