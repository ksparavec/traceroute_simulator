#!/usr/bin/env -S python3 -B -u
"""Detailed logging system for web service"""
import logging
import json
import time
import os
from datetime import datetime

class AuditLogger:
    def __init__(self, log_dir="/var/www/traceroute-web/logs"):
        self.log_dir = log_dir
        
        # Configure error logger
        self.error_logger = logging.getLogger('error')
        error_handler = logging.FileHandler(os.path.join(log_dir, 'error.log'))
        error_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        self.error_logger.addHandler(error_handler)
        self.error_logger.setLevel(logging.DEBUG)
        
        # Configure audit logger for command execution
        self.audit_logger = logging.getLogger('audit')
        audit_handler = logging.FileHandler(os.path.join(log_dir, 'audit.log'))
        audit_handler.setFormatter(logging.Formatter('%(message)s'))
        self.audit_logger.addHandler(audit_handler)
        self.audit_logger.setLevel(logging.INFO)
    
    def log_command_execution(self, session_id, username, command, args, 
                            start_time, end_time, return_code, output, error):
        """Log detailed command execution for debugging"""
        audit_entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "username": username,
            "command": command,
            "args": args,
            "duration": end_time - start_time,
            "return_code": return_code,
            "output_size": len(output) if output else 0,
            "error": error,
            "output_preview": output[:500] if output else None
        }
        self.audit_logger.info(json.dumps(audit_entry))
    
    def log_error(self, error_type, error_msg, session_id=None, traceback=None):
        """Log technical error details"""
        self.error_logger.error(f"Type: {error_type}, Session: {session_id}, "
                               f"Message: {error_msg}", exc_info=traceback)
    
    def log_access(self, username, action, ip_address, user_agent):
        """Log user access"""
        access_entry = {
            "timestamp": datetime.now().isoformat(),
            "username": username,
            "action": action,
            "ip_address": ip_address,
            "user_agent": user_agent
        }
        with open(os.path.join(self.log_dir, 'access.log'), 'a') as f:
            f.write(json.dumps(access_entry) + '\n')
    
    def log_info(self, message):
        """Log informational message"""
        self.audit_logger.info(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "type": "info",
            "message": message
        }))
    
    def log_warning(self, message):
        """Log warning message"""
        self.audit_logger.warning(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "type": "warning",
            "message": message
        }))