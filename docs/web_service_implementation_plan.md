# Network Reachability Web Service Implementation Plan

## Overview

This document provides a comprehensive implementation plan for a web-based network reachability testing service using Apache CGI, Python, and the traceroute simulator. The service includes authentication, session management, concurrent execution protection, and PDF report generation.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Browser   │────▶│ Apache HTTPS │────▶│   CGI Scripts   │
└─────────────┘     └──────────────┘     └─────────────────┘
                                                    │
                                          ┌─────────┴─────────┐
                                          │                   │
                                    ┌─────▼─────┐      ┌─────▼─────┐
                                    │  tsimsh   │      │   Scripts  │
                                    └───────────┘      └────────────┘
                                                              │
                                                       ┌──────▼──────┐
                                                       │ POSIX Lock  │
                                                       └─────────────┘
```

## Key Features

1. **Custom Session-Based Authentication**: Secure login system with session cookies
2. **Concurrent Execution Protection**: POSIX semaphore locking to prevent race conditions
3. **Virtual Environment Support**: Automatic activation of Python virtual environment
4. **Comprehensive Logging**: Detailed audit trails for debugging
5. **Data Retention**: Configurable retention period (default: 1 year)
6. **PDF Generation**: Inline browser display with shareable links
7. **Form State Persistence**: Browser localStorage for user convenience

## Directory Structure

```
/var/www/traceroute-web/
├── cgi-bin/
│   ├── login.py                 # Login handler
│   ├── logout.py                # Logout handler
│   ├── main.py                  # Main form processor
│   ├── pdf_viewer.py            # PDF display handler
│   ├── cleanup.py               # Maintenance script
│   └── lib/
│       ├── __init__.py
│       ├── session.py           # Session management
│       ├── auth.py              # Authentication
│       ├── validator.py         # Input validation
│       ├── executor.py          # Command execution wrapper
│       ├── logger.py            # Detailed logging
│       ├── config.py            # Configuration management
│       └── lock_manager.py      # POSIX locking
├── htdocs/
│   ├── index.html               # Redirect to login
│   ├── login.html               # Login page
│   ├── form.html                # Input form (protected)
│   ├── css/
│   │   └── style.css           # Styling
│   └── js/
│       └── form.js             # Form state management
├── data/
│   ├── traces/                  # JSON trace files
│   ├── results/                 # Reachability results
│   ├── pdfs/                    # Generated PDFs
│   ├── sessions/                # Session data
│   └── users/                   # User credentials
├── logs/
│   ├── access.log              # User access logs
│   ├── error.log               # Error logs
│   └── audit.log               # Command execution logs
└── conf/
    └── config.json             # Configuration file
```

## Implementation Components

### 1. Configuration Management (lib/config.py)

```python
#!/usr/bin/env python3
import json
import os

class Config:
    DEFAULT_CONFIG = {
        "data_retention_days": 365,
        "session_timeout": 3600,
        "venv_path": "/home/sparavec/tsim-venv",
        "tsimsh_path": "tsimsh",
        "traceroute_simulator_path": "/home/sparavec/git/traceroute_simulator",
        "log_level": "DEBUG",
        "secret_key": None  # Generated on first run
    }
    
    def __init__(self, config_file="/var/www/traceroute-web/conf/config.json"):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                config = json.load(f)
        else:
            config = self.DEFAULT_CONFIG.copy()
            # Generate secret key
            import secrets
            config['secret_key'] = secrets.token_hex(32)
            self.save_config(config)
        return config
    
    def save_config(self, config):
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
```

### 2. Detailed Logger (lib/logger.py)

```python
#!/usr/bin/env python3
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
            "timestamp": datetime.utcnow().isoformat(),
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
            "timestamp": datetime.utcnow().isoformat(),
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
            "timestamp": datetime.utcnow().isoformat(),
            "type": "info",
            "message": message
        }))
    
    def log_warning(self, message):
        """Log warning message"""
        self.audit_logger.warning(json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            "type": "warning",
            "message": message
        }))
```

### 3. Authentication System (lib/auth.py)

```python
#!/usr/bin/env python3
import hashlib
import json
import os
import secrets
from datetime import datetime

class AuthManager:
    def __init__(self, users_dir="/var/www/traceroute-web/data/users"):
        self.users_dir = users_dir
        os.makedirs(users_dir, exist_ok=True)
    
    def hash_password(self, password, salt=None):
        if salt is None:
            salt = secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac('sha256', 
                                       password.encode('utf-8'), 
                                       salt.encode('utf-8'), 
                                       100000)
        return salt, pwd_hash.hex()
    
    def create_user(self, username, password):
        user_file = os.path.join(self.users_dir, f"{username}.json")
        if os.path.exists(user_file):
            return False
        
        salt, pwd_hash = self.hash_password(password)
        user_data = {
            "username": username,
            "salt": salt,
            "password_hash": pwd_hash,
            "created": datetime.utcnow().isoformat()
        }
        
        with open(user_file, 'w') as f:
            json.dump(user_data, f)
        return True
    
    def verify_user(self, username, password):
        user_file = os.path.join(self.users_dir, f"{username}.json")
        if not os.path.exists(user_file):
            return False
        
        with open(user_file, 'r') as f:
            user_data = json.load(f)
        
        _, pwd_hash = self.hash_password(password, user_data['salt'])
        return pwd_hash == user_data['password_hash']
```

### 4. Session Management (lib/session.py)

```python
#!/usr/bin/env python3
import os
import time
import json
import secrets
from http import cookies
from datetime import datetime, timedelta

class SessionManager:
    def __init__(self, session_dir="/var/www/traceroute-web/data/sessions", 
                 timeout=3600):
        self.session_dir = session_dir
        self.timeout = timeout
        os.makedirs(session_dir, exist_ok=True)
    
    def create_session(self, username):
        session_id = secrets.token_urlsafe(32)
        session_file = os.path.join(self.session_dir, f"{session_id}.json")
        
        session_data = {
            'session_id': session_id,
            'username': username,
            'created': time.time(),
            'last_access': time.time(),
            'form_data': {},
            'ip_address': os.environ.get('REMOTE_ADDR', '')
        }
        
        with open(session_file, 'w') as f:
            json.dump(session_data, f)
        
        # Create cookie
        cookie = cookies.SimpleCookie()
        cookie['session_id'] = session_id
        cookie['session_id']['httponly'] = True
        cookie['session_id']['secure'] = True
        cookie['session_id']['samesite'] = 'Strict'
        cookie['session_id']['max-age'] = self.timeout
        
        return session_id, cookie
    
    def get_session(self, session_id):
        if not session_id:
            return None
            
        session_file = os.path.join(self.session_dir, f"{session_id}.json")
        if not os.path.exists(session_file):
            return None
        
        with open(session_file, 'r') as f:
            session_data = json.load(f)
        
        # Check timeout
        if time.time() - session_data['last_access'] > self.timeout:
            os.remove(session_file)
            return None
        
        # Update last access
        session_data['last_access'] = time.time()
        with open(session_file, 'w') as f:
            json.dump(session_data, f)
        
        return session_data
    
    def update_form_data(self, session_id, form_data):
        session_file = os.path.join(self.session_dir, f"{session_id}.json")
        if os.path.exists(session_file):
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            
            session_data['form_data'] = form_data
            session_data['last_access'] = time.time()
            
            with open(session_file, 'w') as f:
                json.dump(session_data, f)
    
    def destroy_session(self, session_id):
        session_file = os.path.join(self.session_dir, f"{session_id}.json")
        if os.path.exists(session_file):
            os.remove(session_file)
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions"""
        current_time = time.time()
        for filename in os.listdir(self.session_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.session_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        session_data = json.load(f)
                    if current_time - session_data['last_access'] > self.timeout:
                        os.remove(filepath)
                except:
                    pass
```

### 5. Input Validator (lib/validator.py)

```python
#!/usr/bin/env python3
import re
import ipaddress

class InputValidator:
    @staticmethod
    def validate_ip(ip_str):
        try:
            ipaddress.ip_address(ip_str)
            return True
        except:
            return False
    
    @staticmethod
    def validate_port(port_str):
        try:
            port = int(port_str)
            return 1 <= port <= 65535
        except:
            return False
    
    @staticmethod
    def validate_protocol(protocol):
        return protocol in ['tcp', 'udp']
    
    @staticmethod
    def sanitize_input(value):
        # Remove any shell metacharacters
        return re.sub(r'[;&|`$()<>\\\'"{}[\]*?~]', '', value)
```

### 6. Lock Manager (lib/lock_manager.py)

```python
#!/usr/bin/env python3
import posix_ipc
import time
import os
import signal
import sys

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
```

### 7. Command Executor (lib/executor.py)

```python
#!/usr/bin/env python3
import subprocess
import os
import sys
import uuid
import json
import time
import shutil
from datetime import datetime, timedelta

class CommandExecutor:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.data_dir = "/var/www/traceroute-web/data"
        self.venv_path = config.config['venv_path']
        self.tsimsh_path = config.config['tsimsh_path']
        self.simulator_path = config.config['traceroute_simulator_path']
        
    def _activate_venv_and_run(self, cmd, timeout=60, capture_output=True):
        """Run command with virtual environment activated"""
        # Prepare environment
        env = os.environ.copy()
        env['PATH'] = f"{self.venv_path}/bin:{env['PATH']}"
        env['VIRTUAL_ENV'] = self.venv_path
        
        # Add Python path for imports
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] = f"{self.simulator_path}:{env['PYTHONPATH']}"
        else:
            env['PYTHONPATH'] = self.simulator_path
        
        # Execute command
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                env=env,
                cwd=self.simulator_path,
                capture_output=capture_output,
                text=True,
                timeout=timeout
            )
            end_time = time.time()
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'error': result.stderr,
                'return_code': result.returncode,
                'duration': end_time - start_time
            }
        except subprocess.TimeoutExpired:
            end_time = time.time()
            return {
                'success': False,
                'output': '',
                'error': 'Command timed out',
                'return_code': -1,
                'duration': end_time - start_time
            }
        except Exception as e:
            end_time = time.time()
            return {
                'success': False,
                'output': '',
                'error': str(e),
                'return_code': -1,
                'duration': end_time - start_time
            }
    
    def execute_trace(self, session_id, username, source_ip, dest_ip):
        """Execute tsimsh trace command"""
        run_id = str(uuid.uuid4())
        trace_file = os.path.join(self.data_dir, "traces", f"{run_id}_trace.json")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(trace_file), exist_ok=True)
        
        # Build command
        cmd = [
            self.tsimsh_path, "-q",
            "-c", f"trace --source {source_ip} --destination {dest_ip} --json"
        ]
        
        # Execute command
        start_time = time.time()
        result = self._activate_venv_and_run(cmd, timeout=30)
        end_time = time.time()
        
        # Log execution
        self.logger.log_command_execution(
            session_id=session_id,
            username=username,
            command="tsimsh trace",
            args={'source': source_ip, 'dest': dest_ip},
            start_time=start_time,
            end_time=end_time,
            return_code=result['return_code'],
            output=result['output'],
            error=result['error']
        )
        
        if result['success'] and result['output']:
            # Save trace output
            with open(trace_file, 'w') as f:
                f.write(result['output'])
            return run_id, trace_file
        else:
            raise Exception(f"Trace execution failed: {result['error']}")
    
    def execute_reachability_test(self, session_id, username, run_id, trace_file,
                                  source_ip, source_port, dest_ip, dest_port, protocol):
        """Execute network_reachability_test.sh with locking"""
        results_file = os.path.join(self.data_dir, "results", f"{run_id}_results.json")
        os.makedirs(os.path.dirname(results_file), exist_ok=True)
        
        # Use the Python wrapper that handles locking
        cmd = [
            os.path.join(self.venv_path, "bin", "python"),
            os.path.join(self.simulator_path, "src/scripts/network_reachability_test_wrapper.py"),
            "--source", source_ip,
            "--destination", dest_ip,
            "--port", str(dest_port),
            "--protocol", protocol,
            "--trace-file", trace_file,
            "--output", results_file,
            "--json"
        ]
        
        if source_port:
            cmd.extend(["--source-port", str(source_port)])
        
        # Log that we're attempting to acquire lock
        self.logger.log_info(
            f"Session {session_id}: Requesting network test lock for "
            f"{source_ip} -> {dest_ip}:{dest_port}/{protocol}"
        )
        
        # Execute command (will wait for lock if needed)
        start_time = time.time()
        result = self._activate_venv_and_run(cmd, timeout=420)  # 7 minutes (5 min lock + 2 min execution)
        end_time = time.time()
        
        # Log execution
        self.logger.log_command_execution(
            session_id=session_id,
            username=username,
            command="network_reachability_test.sh (with lock)",
            args={
                'source': source_ip,
                'source_port': source_port,
                'dest': dest_ip,
                'dest_port': dest_port,
                'protocol': protocol,
                'trace_file': trace_file,
                'lock_wait_time': 'check audit log'
            },
            start_time=start_time,
            end_time=end_time,
            return_code=result['return_code'],
            output=result['output'],
            error=result['error']
        )
        
        if result['success'] and os.path.exists(results_file):
            return results_file
        else:
            raise Exception(f"Reachability test failed: {result['error']}")
    
    def generate_pdf(self, session_id, username, run_id, trace_file, results_file):
        """Execute visualize_reachability.py to generate PDF"""
        pdf_file = os.path.join(self.data_dir, "pdfs", f"{run_id}_report.pdf")
        os.makedirs(os.path.dirname(pdf_file), exist_ok=True)
        
        # Build command
        cmd = [
            os.path.join(self.venv_path, "bin", "python"),
            os.path.join(self.simulator_path, "src/scripts/visualize_reachability.py"),
            "--trace", trace_file,
            "--results", results_file,
            "--output", pdf_file
        ]
        
        # Execute command
        start_time = time.time()
        result = self._activate_venv_and_run(cmd, timeout=60)
        end_time = time.time()
        
        # Log execution
        self.logger.log_command_execution(
            session_id=session_id,
            username=username,
            command="visualize_reachability.py",
            args={
                'trace': trace_file,
                'results': results_file,
                'output': pdf_file
            },
            start_time=start_time,
            end_time=end_time,
            return_code=result['return_code'],
            output=result['output'],
            error=result['error']
        )
        
        if result['success'] and os.path.exists(pdf_file):
            return pdf_file
        else:
            raise Exception(f"PDF generation failed: {result['error']}")
    
    def cleanup_old_data(self):
        """Remove data older than retention period"""
        retention_days = self.config.config['data_retention_days']
        cutoff_time = datetime.now() - timedelta(days=retention_days)
        
        for subdir in ['traces', 'results', 'pdfs']:
            dir_path = os.path.join(self.data_dir, subdir)
            if os.path.exists(dir_path):
                for filename in os.listdir(dir_path):
                    filepath = os.path.join(dir_path, filename)
                    if os.path.getmtime(filepath) < cutoff_time.timestamp():
                        try:
                            os.remove(filepath)
                        except:
                            pass
```

### 8. Network Reachability Test Wrapper (src/scripts/network_reachability_test_wrapper.py)

```python
#!/usr/bin/env python3
"""
Python wrapper for network_reachability_test.sh that handles locking
"""
import sys
import os
import subprocess
import signal

# Add lib directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../cgi-bin/lib'))

from lock_manager import NetworkLockManager
from logger import AuditLogger

def signal_handler(signum, frame):
    """Handle signals to ensure lock cleanup"""
    print("Received signal, cleaning up...", file=sys.stderr)
    sys.exit(1)

def main():
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Initialize logger
    logger = AuditLogger()
    
    # Get the actual script path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    actual_script = os.path.join(script_dir, "network_reachability_test.sh")
    
    try:
        # Acquire lock before running the script
        with NetworkLockManager(logger) as lock:
            # Pass all arguments to the shell script
            cmd = [actual_script] + sys.argv[1:]
            
            # Execute the script
            result = subprocess.run(cmd)
            
            # Exit with same code as the script
            sys.exit(result.returncode)
            
    except TimeoutError as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        logger.log_error("Network test lock timeout", str(e))
        sys.exit(1)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        logger.log_error("Network test wrapper error", str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
```

## CGI Scripts

### Login Handler (cgi-bin/login.py)

```python
#!/usr/bin/env python3
import cgi
import cgitb
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from auth import AuthManager
from session import SessionManager
from logger import AuditLogger

# Enable error logging but not display
cgitb.enable(display=0, logdir="/var/www/traceroute-web/logs")

def show_login_form(error=None):
    print("Content-Type: text/html\n")
    print(f"""<!DOCTYPE html>
<html>
<head>
    <title>Login - Network Reachability Test</title>
    <link rel="stylesheet" href="/css/style.css">
</head>
<body>
    <div class="login-container">
        <h1>Network Reachability Test</h1>
        <h2>Login</h2>
        {f'<div class="error">{error}</div>' if error else ''}
        <form method="POST" action="/cgi-bin/login.py">
            <label>Username: <input type="text" name="username" required></label>
            <label>Password: <input type="password" name="password" required></label>
            <button type="submit">Login</button>
        </form>
    </div>
</body>
</html>""")

def main():
    form = cgi.FieldStorage()
    auth_mgr = AuthManager()
    session_mgr = SessionManager()
    logger = AuditLogger()
    
    # Get form data
    username = form.getvalue('username', '').strip()
    password = form.getvalue('password', '')
    
    if not username or not password:
        show_login_form()
        return
    
    # Verify credentials
    if auth_mgr.verify_user(username, password):
        # Create session
        session_id, cookie = session_mgr.create_session(username)
        
        # Log successful login
        logger.log_access(
            username=username,
            action="login_success",
            ip_address=os.environ.get('REMOTE_ADDR', ''),
            user_agent=os.environ.get('HTTP_USER_AGENT', '')
        )
        
        # Redirect to form with session cookie
        print(f"{cookie}")
        print("Status: 302 Found")
        print("Location: /form.html")
        print()
    else:
        # Log failed login
        logger.log_access(
            username=username,
            action="login_failed",
            ip_address=os.environ.get('REMOTE_ADDR', ''),
            user_agent=os.environ.get('HTTP_USER_AGENT', '')
        )
        show_login_form("Invalid username or password")

if __name__ == "__main__":
    main()
```

### Main Form Processor (cgi-bin/main.py)

```python
#!/usr/bin/env python3
import cgi
import cgitb
import os
import sys
import json
import hashlib
from http import cookies

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from session import SessionManager
from validator import InputValidator
from executor import CommandExecutor
from logger import AuditLogger
from config import Config

# Enable error logging but not display
cgitb.enable(display=0, logdir="/var/www/traceroute-web/logs")

def get_session_id():
    """Extract session ID from cookie"""
    cookie_str = os.environ.get('HTTP_COOKIE', '')
    cookie = cookies.SimpleCookie(cookie_str)
    if 'session_id' in cookie:
        return cookie['session_id'].value
    return None

def show_error(message="An error occurred. Please try again."):
    """Show generic error message to user"""
    print("Content-Type: text/html\n")
    print(f"""<!DOCTYPE html>
<html>
<head>
    <title>Error - Network Reachability Test</title>
    <link rel="stylesheet" href="/css/style.css">
</head>
<body>
    <div class="error-container">
        <h1>Error</h1>
        <p>{message}</p>
        <a href="/form.html">Back to form</a>
    </div>
</body>
</html>""")

def generate_shareable_link(run_id, config):
    """Generate secure shareable link"""
    secret = config.config['secret_key']
    token = hashlib.hmac(
        key=secret.encode(),
        msg=run_id.encode(),
        digestmod=hashlib.sha256
    ).hexdigest()
    
    base_url = os.environ.get('HTTP_HOST', 'localhost')
    return f"https://{base_url}/cgi-bin/pdf_viewer.py?id={run_id}&token={token}"

def main():
    try:
        # Initialize components
        config = Config()
        session_mgr = SessionManager()
        logger = AuditLogger()
        validator = InputValidator()
        
        # Check session
        session_id = get_session_id()
        session = session_mgr.get_session(session_id)
        
        if not session:
            print("Status: 302 Found")
            print("Location: /login.html")
            print()
            return
        
        # Get form data
        form = cgi.FieldStorage()
        source_ip = form.getvalue('source_ip', '').strip()
        source_port = form.getvalue('source_port', '').strip()
        dest_ip = form.getvalue('dest_ip', '').strip()
        dest_port = form.getvalue('dest_port', '').strip()
        protocol = form.getvalue('protocol', 'tcp').lower()
        
        # Validate inputs
        if not validator.validate_ip(source_ip):
            raise ValueError("Invalid source IP")
        if not validator.validate_ip(dest_ip):
            raise ValueError("Invalid destination IP")
        if not validator.validate_port(dest_port):
            raise ValueError("Invalid destination port")
        if source_port and not validator.validate_port(source_port):
            raise ValueError("Invalid source port")
        if not validator.validate_protocol(protocol):
            raise ValueError("Invalid protocol")
        
        # Sanitize inputs
        source_ip = validator.sanitize_input(source_ip)
        dest_ip = validator.sanitize_input(dest_ip)
        dest_port = validator.sanitize_input(dest_port)
        source_port = validator.sanitize_input(source_port) if source_port else None
        
        # Save form data to session
        form_data = {
            'source_ip': source_ip,
            'source_port': source_port,
            'dest_ip': dest_ip,
            'dest_port': dest_port,
            'protocol': protocol
        }
        session_mgr.update_form_data(session_id, form_data)
        
        # Execute commands
        executor = CommandExecutor(config, logger)
        
        # 1. Execute trace
        run_id, trace_file = executor.execute_trace(
            session_id, session['username'], source_ip, dest_ip
        )
        
        # 2. Execute reachability test
        results_file = executor.execute_reachability_test(
            session_id, session['username'], run_id, trace_file,
            source_ip, source_port, dest_ip, dest_port, protocol
        )
        
        # 3. Generate PDF
        pdf_file = executor.generate_pdf(
            session_id, session['username'], run_id, trace_file, results_file
        )
        
        # Generate shareable link
        share_link = generate_shareable_link(run_id, config)
        
        # Redirect to PDF viewer
        print("Status: 302 Found")
        print(f"Location: /cgi-bin/pdf_viewer.py?id={run_id}&session={session_id}")
        print()
        
    except Exception as e:
        # Log detailed error
        logger.log_error(
            error_type=type(e).__name__,
            error_msg=str(e),
            session_id=session_id if 'session_id' in locals() else None,
            traceback=True
        )
        # Show generic error to user
        show_error()

if __name__ == "__main__":
    main()
```

### PDF Viewer (cgi-bin/pdf_viewer.py)

```python
#!/usr/bin/env python3
import cgi
import cgitb
import os
import sys
import hashlib

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from session import SessionManager
from config import Config
from logger import AuditLogger

# Enable error logging but not display
cgitb.enable(display=0, logdir="/var/www/traceroute-web/logs")

def verify_token(run_id, token, config):
    """Verify shareable link token"""
    secret = config.config['secret_key']
    expected_token = hashlib.hmac(
        key=secret.encode(),
        msg=run_id.encode(),
        digestmod=hashlib.sha256
    ).hexdigest()
    return token == expected_token

def serve_pdf(pdf_path):
    """Serve PDF file for inline display"""
    if not os.path.exists(pdf_path):
        print("Status: 404 Not Found")
        print("Content-Type: text/plain")
        print()
        print("PDF not found")
        return
    
    # Get file size
    file_size = os.path.getsize(pdf_path)
    
    # Send PDF headers for inline display
    print("Content-Type: application/pdf")
    print(f"Content-Length: {file_size}")
    print("Content-Disposition: inline")
    print("Cache-Control: no-cache")
    print()
    
    # Send PDF content
    sys.stdout.flush()
    with open(pdf_path, 'rb') as f:
        sys.stdout.buffer.write(f.read())

def main():
    try:
        form = cgi.FieldStorage()
        config = Config()
        logger = AuditLogger()
        
        # Get parameters
        run_id = form.getvalue('id', '').strip()
        token = form.getvalue('token', '').strip()
        session_param = form.getvalue('session', '').strip()
        
        if not run_id:
            print("Status: 400 Bad Request")
            print("Content-Type: text/plain")
            print()
            print("Missing ID parameter")
            return
        
        # Check if accessing via session or shareable link
        authenticated = False
        username = "anonymous"
        
        if session_param:
            # Session-based access
            session_mgr = SessionManager()
            session = session_mgr.get_session(session_param)
            if session:
                authenticated = True
                username = session['username']
        elif token:
            # Token-based access (shareable link)
            if verify_token(run_id, token, config):
                authenticated = True
                username = "shared_link"
        
        if not authenticated:
            print("Status: 403 Forbidden")
            print("Content-Type: text/plain")
            print()
            print("Access denied")
            return
        
        # Log access
        logger.log_access(
            username=username,
            action=f"pdf_view_{run_id}",
            ip_address=os.environ.get('REMOTE_ADDR', ''),
            user_agent=os.environ.get('HTTP_USER_AGENT', '')
        )
        
        # Construct PDF path
        pdf_path = os.path.join("/var/www/traceroute-web/data/pdfs", 
                               f"{run_id}_report.pdf")
        
        # Serve PDF
        serve_pdf(pdf_path)
        
    except Exception as e:
        logger.log_error(
            error_type=type(e).__name__,
            error_msg=str(e),
            session_id=None,
            traceback=True
        )
        print("Status: 500 Internal Server Error")
        print("Content-Type: text/plain")
        print()
        print("An error occurred")

if __name__ == "__main__":
    main()
```

### Logout Handler (cgi-bin/logout.py)

```python
#!/usr/bin/env python3
import os
import sys
from http import cookies

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from session import SessionManager
from logger import AuditLogger

def get_session_id():
    """Extract session ID from cookie"""
    cookie_str = os.environ.get('HTTP_COOKIE', '')
    cookie = cookies.SimpleCookie(cookie_str)
    if 'session_id' in cookie:
        return cookie['session_id'].value
    return None

def main():
    session_mgr = SessionManager()
    logger = AuditLogger()
    
    # Get session ID
    session_id = get_session_id()
    
    if session_id:
        # Get session info for logging
        session = session_mgr.get_session(session_id)
        if session:
            logger.log_access(
                username=session['username'],
                action="logout",
                ip_address=os.environ.get('REMOTE_ADDR', ''),
                user_agent=os.environ.get('HTTP_USER_AGENT', '')
            )
        
        # Destroy session
        session_mgr.destroy_session(session_id)
    
    # Clear cookie and redirect to login
    cookie = cookies.SimpleCookie()
    cookie['session_id'] = ''
    cookie['session_id']['expires'] = 'Thu, 01 Jan 1970 00:00:00 GMT'
    cookie['session_id']['httponly'] = True
    cookie['session_id']['secure'] = True
    
    print(f"{cookie}")
    print("Status: 302 Found")
    print("Location: /login.html")
    print()

if __name__ == "__main__":
    main()
```

## Frontend Files

### Form HTML (htdocs/form.html)

```html
<!DOCTYPE html>
<html>
<head>
    <title>Network Reachability Test</title>
    <link rel="stylesheet" href="/css/style.css">
    <script src="/js/form.js"></script>
</head>
<body>
    <div class="container">
        <header>
            <h1>Network Reachability Test</h1>
            <a href="/cgi-bin/logout.py" class="logout">Logout</a>
        </header>
        
        <form id="reachability-form" action="/cgi-bin/main.py" method="POST">
            <div class="form-group">
                <label for="source_ip">Source IP Address *</label>
                <input type="text" id="source_ip" name="source_ip" 
                       pattern="^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$" 
                       required placeholder="e.g., 10.1.1.1">
            </div>
            
            <div class="form-group">
                <label for="source_port">Source Port (optional)</label>
                <input type="number" id="source_port" name="source_port" 
                       min="1" max="65535" placeholder="e.g., 12345">
            </div>
            
            <div class="form-group">
                <label for="dest_ip">Destination IP Address *</label>
                <input type="text" id="dest_ip" name="dest_ip" 
                       pattern="^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$" 
                       required placeholder="e.g., 10.2.1.1">
            </div>
            
            <div class="form-group">
                <label for="dest_port">Destination Port *</label>
                <input type="number" id="dest_port" name="dest_port" 
                       min="1" max="65535" required placeholder="e.g., 80">
            </div>
            
            <div class="form-group">
                <label for="protocol">Protocol *</label>
                <select id="protocol" name="protocol" required>
                    <option value="tcp">TCP</option>
                    <option value="udp">UDP</option>
                </select>
            </div>
            
            <div class="form-actions">
                <button type="submit">Run Test</button>
                <button type="button" onclick="clearForm()">Clear</button>
            </div>
        </form>
        
        <div class="info">
            <p>This tool will generate a comprehensive network reachability report including:</p>
            <ul>
                <li>Network path trace</li>
                <li>Connectivity tests (ping, MTR, service)</li>
                <li>Firewall rule analysis</li>
                <li>Visual network diagram</li>
            </ul>
        </div>
    </div>
</body>
</html>
```

### JavaScript (htdocs/js/form.js)

```javascript
// Restore form data from localStorage
window.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('reachability-form');
    const savedData = localStorage.getItem('reachability_form_data');
    
    if (savedData) {
        const data = JSON.parse(savedData);
        for (const [key, value] of Object.entries(data)) {
            const field = form.elements[key];
            if (field) {
                field.value = value;
            }
        }
    }
});

// Save form data before submission
document.getElementById('reachability-form').addEventListener('submit', function(e) {
    const formData = new FormData(this);
    const data = {};
    
    for (const [key, value] of formData.entries()) {
        data[key] = value;
    }
    
    localStorage.setItem('reachability_form_data', JSON.stringify(data));
});

// Clear form and localStorage
function clearForm() {
    document.getElementById('reachability-form').reset();
    localStorage.removeItem('reachability_form_data');
}

// Validate IP address format
function validateIP(input) {
    const ipPattern = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
    if (!ipPattern.test(input.value)) {
        input.setCustomValidity('Please enter a valid IP address');
    } else {
        input.setCustomValidity('');
    }
}

// Add IP validation to fields
document.getElementById('source_ip').addEventListener('input', function() {
    validateIP(this);
});

document.getElementById('dest_ip').addEventListener('input', function() {
    validateIP(this);
});
```

### CSS Styles (htdocs/css/style.css)

```css
/* Global Styles */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    background-color: #f5f5f5;
    color: #333;
    line-height: 1.6;
}

.container {
    max-width: 800px;
    margin: 0 auto;
    padding: 20px;
}

/* Header */
header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 30px;
    padding-bottom: 20px;
    border-bottom: 2px solid #e0e0e0;
}

h1 {
    color: #2c3e50;
    font-size: 28px;
}

.logout {
    color: #e74c3c;
    text-decoration: none;
    padding: 8px 16px;
    border: 1px solid #e74c3c;
    border-radius: 4px;
    transition: all 0.3s;
}

.logout:hover {
    background-color: #e74c3c;
    color: white;
}

/* Form Styles */
form {
    background: white;
    padding: 30px;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    margin-bottom: 30px;
}

.form-group {
    margin-bottom: 20px;
}

label {
    display: block;
    margin-bottom: 5px;
    font-weight: 600;
    color: #555;
}

input[type="text"],
input[type="number"],
input[type="password"],
select {
    width: 100%;
    padding: 10px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 16px;
    transition: border-color 0.3s;
}

input[type="text"]:focus,
input[type="number"]:focus,
input[type="password"]:focus,
select:focus {
    outline: none;
    border-color: #3498db;
}

input:invalid {
    border-color: #e74c3c;
}

/* Buttons */
.form-actions {
    display: flex;
    gap: 10px;
    margin-top: 25px;
}

button {
    padding: 10px 20px;
    border: none;
    border-radius: 4px;
    font-size: 16px;
    cursor: pointer;
    transition: background-color 0.3s;
}

button[type="submit"] {
    background-color: #3498db;
    color: white;
    flex: 1;
}

button[type="submit"]:hover {
    background-color: #2980b9;
}

button[type="button"] {
    background-color: #95a5a6;
    color: white;
}

button[type="button"]:hover {
    background-color: #7f8c8d;
}

/* Info Section */
.info {
    background: white;
    padding: 25px;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

.info h2 {
    color: #2c3e50;
    margin-bottom: 15px;
}

.info ul {
    list-style: none;
    padding-left: 0;
}

.info li {
    padding: 8px 0;
    padding-left: 25px;
    position: relative;
}

.info li:before {
    content: "✓";
    position: absolute;
    left: 0;
    color: #27ae60;
    font-weight: bold;
}

/* Login Page */
.login-container {
    max-width: 400px;
    margin: 100px auto;
    background: white;
    padding: 40px;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

.login-container h1 {
    text-align: center;
    margin-bottom: 10px;
}

.login-container h2 {
    text-align: center;
    color: #7f8c8d;
    font-weight: normal;
    margin-bottom: 30px;
}

/* Error Messages */
.error {
    background-color: #fee;
    color: #c33;
    padding: 10px;
    border-radius: 4px;
    margin-bottom: 20px;
    border: 1px solid #fcc;
}

.error-container {
    max-width: 500px;
    margin: 100px auto;
    background: white;
    padding: 40px;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    text-align: center;
}

.error-container h1 {
    color: #e74c3c;
    margin-bottom: 20px;
}

.error-container a {
    display: inline-block;
    margin-top: 20px;
    color: #3498db;
    text-decoration: none;
    padding: 10px 20px;
    border: 1px solid #3498db;
    border-radius: 4px;
    transition: all 0.3s;
}

.error-container a:hover {
    background-color: #3498db;
    color: white;
}

/* Responsive Design */
@media (max-width: 600px) {
    .container {
        padding: 10px;
    }
    
    form {
        padding: 20px;
    }
    
    .form-actions {
        flex-direction: column;
    }
    
    button {
        width: 100%;
    }
}
```

## Apache Configuration

```apache
<VirtualHost *:443>
    ServerName traceroute.example.com
    DocumentRoot /var/www/traceroute-web/htdocs
    
    SSLEngine on
    SSLCertificateFile /etc/ssl/certs/traceroute.crt
    SSLCertificateKeyFile /etc/ssl/private/traceroute.key
    
    # Increase timeout for long-running tests
    Timeout 600
    
    # CGI configuration
    ScriptAlias /cgi-bin/ /var/www/traceroute-web/cgi-bin/
    
    <Directory "/var/www/traceroute-web/cgi-bin">
        Options +ExecCGI
        AddHandler cgi-script .py
        Require all granted
        
        # Increase CGI timeout
        CGIScriptTimeout 600
    </Directory>
    
    # Redirect root to login
    RedirectMatch ^/$ /login.html
    
    # Protected form page (session check in CGI)
    <Location "/form.html">
        Require all granted
    </Location>
    
    # Public login page
    <Location "/login.html">
        Require all granted
    </Location>
    
    # Static resources
    <Directory "/var/www/traceroute-web/htdocs">
        Options -Indexes
        Require all granted
    </Directory>
    
    # Security headers
    Header always set X-Content-Type-Options "nosniff"
    Header always set X-Frame-Options "DENY"
    Header always set X-XSS-Protection "1; mode=block"
    Header always set Strict-Transport-Security "max-age=31536000"
    Header always set Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    
    # Logging
    ErrorLog /var/www/traceroute-web/logs/apache_error.log
    CustomLog /var/www/traceroute-web/logs/apache_access.log combined
</VirtualHost>

# Redirect HTTP to HTTPS
<VirtualHost *:80>
    ServerName traceroute.example.com
    Redirect permanent / https://traceroute.example.com/
</VirtualHost>
```

## Installation and Setup

### 1. System Requirements

```bash
# Install required packages
sudo apt-get update
sudo apt-get install -y apache2 libapache2-mod-ssl python3-pip python3-venv

# Enable Apache modules
sudo a2enmod cgi ssl headers rewrite
sudo systemctl restart apache2
```

### 2. Python Environment Setup

```bash
# Install Python packages in virtual environment
source /home/sparavec/tsim-venv/bin/activate
pip install posix-ipc

# Or install globally for CGI
sudo pip3 install posix-ipc
```

### 3. Directory Setup

```bash
# Create directory structure
sudo mkdir -p /var/www/traceroute-web/{cgi-bin/lib,htdocs/{css,js},data/{traces,results,pdfs,sessions,users},logs,conf}

# Set permissions
sudo chown -R www-data:www-data /var/www/traceroute-web
sudo chmod -R 750 /var/www/traceroute-web
sudo chmod -R 755 /var/www/traceroute-web/htdocs
```

### 4. SSL Certificate

```bash
# Generate self-signed certificate for testing
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/ssl/private/traceroute.key \
    -out /etc/ssl/certs/traceroute.crt \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=traceroute.example.com"

# Or use Let's Encrypt for production
sudo certbot --apache -d traceroute.example.com
```

### 5. Create Initial User

```bash
cd /var/www/traceroute-web/cgi-bin
sudo -u www-data python3 -c "
import sys
sys.path.append('lib')
from auth import AuthManager

auth = AuthManager()
auth.create_user('admin', 'changeme')
print('User admin created')
"
```

### 6. Crontab Setup

```bash
# Edit crontab for www-data user
sudo -u www-data crontab -e

# Add entries:
# Daily cleanup at 2 AM
0 2 * * * /usr/bin/python3 /var/www/traceroute-web/cgi-bin/cleanup.py >> /var/www/traceroute-web/logs/cleanup.log 2>&1

# Session cleanup every hour
0 * * * * /usr/bin/python3 -c "import sys; sys.path.append('/var/www/traceroute-web/cgi-bin/lib'); from session import SessionManager; SessionManager().cleanup_expired_sessions()"
```

## Maintenance Scripts

### Cleanup Script (cgi-bin/cleanup.py)

```python
#!/usr/bin/env python3
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
```

### User Management Script (create_user.sh)

```bash
#!/bin/bash
# create_user.sh - Create a new user for the web interface

cd /var/www/traceroute-web/cgi-bin

sudo -u www-data python3 -c "
import sys
sys.path.append('lib')
from auth import AuthManager

username = input('Username: ')
password = input('Password: ')

auth = AuthManager()
if auth.create_user(username, password):
    print(f'User {username} created successfully')
else:
    print(f'User {username} already exists')
"
```

## Security Considerations

1. **Input Validation**: All user inputs are validated and sanitized to prevent injection attacks
2. **Command Injection Prevention**: Shell metacharacters are stripped from inputs
3. **Path Traversal Prevention**: UUID-based filenames prevent directory traversal
4. **Session Security**: Cookies are HTTPOnly, Secure, and SameSite
5. **HTTPS Only**: All traffic is encrypted with SSL/TLS
6. **Error Handling**: Technical details logged, generic messages shown to users
7. **File Permissions**: Strict permissions on all directories and files
8. **Lock Timeout**: Prevents indefinite blocking of resources
9. **Signal Handling**: Ensures proper cleanup on interruption
10. **Least Privilege**: CGI scripts run as www-data user

## Monitoring and Troubleshooting

### Log Files

- **Access Log**: `/var/www/traceroute-web/logs/access.log` - User access and actions
- **Error Log**: `/var/www/traceroute-web/logs/error.log` - Technical errors
- **Audit Log**: `/var/www/traceroute-web/logs/audit.log` - Command execution details
- **Apache Error Log**: `/var/www/traceroute-web/logs/apache_error.log` - Web server errors

### Common Issues

1. **Lock Timeout**
   ```bash
   # Check if lock is held
   ls -la /dev/shm/sem.traceroute_network_test_lock
   
   # Remove stale lock if needed
   sudo python3 -c "import posix_ipc; posix_ipc.Semaphore('/traceroute_network_test_lock').unlink()"
   ```

2. **Session Problems**
   ```bash
   # Check active sessions
   ls -la /var/www/traceroute-web/data/sessions/
   
   # Clear all sessions if needed
   sudo rm -f /var/www/traceroute-web/data/sessions/*.json
   ```

3. **Permission Issues**
   ```bash
   # Fix ownership
   sudo chown -R www-data:www-data /var/www/traceroute-web/data
   
   # Fix permissions
   sudo chmod -R 750 /var/www/traceroute-web/data
   ```

4. **Virtual Environment Issues**
   ```bash
   # Test virtual environment activation
   sudo -u www-data /home/sparavec/tsim-venv/bin/python -c "import sys; print(sys.path)"
   ```

### Performance Monitoring

```bash
# Monitor active locks
watch -n 1 'ls -la /dev/shm/sem.* 2>/dev/null'

# Monitor CGI processes
ps aux | grep -E "(python|network_reachability)"

# Check disk usage
df -h /var/www/traceroute-web/data

# Monitor log growth
du -sh /var/www/traceroute-web/logs/*
```

## Testing Procedures

### 1. Lock Testing

```bash
# Terminal 1: Start long-running test
cd /home/sparavec/git/traceroute_simulator
./src/scripts/network_reachability_test_wrapper.py \
    --source 10.1.1.1 --destination 10.2.1.1 \
    --port 80 --protocol tcp --trace-file test1.json

# Terminal 2: Try concurrent execution (should wait)
./src/scripts/network_reachability_test_wrapper.py \
    --source 10.1.1.2 --destination 10.2.1.2 \
    --port 443 --protocol tcp --trace-file test2.json
```

### 2. Web Interface Testing

```bash
# Test login
curl -k -X POST https://traceroute.example.com/cgi-bin/login.py \
    -d "username=admin&password=changeme" \
    -c cookies.txt

# Test form submission
curl -k -X POST https://traceroute.example.com/cgi-bin/main.py \
    -b cookies.txt \
    -d "source_ip=10.1.1.1&dest_ip=10.2.1.1&dest_port=80&protocol=tcp"

# Test PDF access with token
curl -k "https://traceroute.example.com/cgi-bin/pdf_viewer.py?id=UUID&token=TOKEN"
```

### 3. Load Testing

```bash
# Simulate multiple concurrent users
for i in {1..5}; do
    (
        # Login
        curl -k -X POST https://traceroute.example.com/cgi-bin/login.py \
            -d "username=user$i&password=pass$i" \
            -c cookies$i.txt
        
        # Submit form
        curl -k -X POST https://traceroute.example.com/cgi-bin/main.py \
            -b cookies$i.txt \
            -d "source_ip=10.1.1.$i&dest_ip=10.2.1.$i&dest_port=80&protocol=tcp"
    ) &
done

# Monitor lock contention
tail -f /var/www/traceroute-web/logs/audit.log | grep "lock"
```

## Future Enhancements

1. **Database Backend**: Replace file-based storage with PostgreSQL/MySQL
2. **Job Queue**: Implement Celery/RQ for background processing
3. **WebSocket Support**: Real-time progress updates
4. **REST API**: RESTful interface for programmatic access
5. **Multi-tenancy**: Organization-based access control
6. **Caching**: Redis cache for repeated queries
7. **Metrics**: Prometheus/Grafana integration
8. **Container Support**: Docker/Kubernetes deployment
9. **High Availability**: Multi-server setup with shared storage
10. **Audit Compliance**: Enhanced logging for regulatory requirements