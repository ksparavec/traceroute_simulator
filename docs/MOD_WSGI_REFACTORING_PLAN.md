# TSIM mod_wsgi Refactoring Plan for Web Interface

## Important: Folder Structure

**ALL WSGI code will be placed in a NEW top-level `wsgi/` folder**, separate from existing code:
```
traceroute-simulator/
├── web/              # EXISTING CGI code - DO NOT MODIFY
│   ├── cgi-bin/     # Keep as-is during development
│   └── htdocs/      # Keep as-is
├── src/             # EXISTING core code - DO NOT MODIFY
│   └── scripts/     # Keep as-is during development
└── wsgi/            # NEW WSGI implementation
    ├── app.wsgi     # Main WSGI entry point
    ├── tsim_app.py  # Core application
    ├── handlers/    # Request handlers
    ├── services/    # Shared services
    └── scripts/     # Refactored scripts from src/scripts/
```

**This separation allows:**
- Side-by-side development without breaking existing CGI
- Easy rollback if needed
- Clean migration path
- No risk to production during development

## Big-Bang Migration Strategy

**Since this is a small, non-production application**, we'll replace CGI with WSGI completely in one go:
- **Day 1**: Implement all WSGI handlers and update frontend
- **Day 2**: Deploy and test
- **No gradual migration needed** - just replace everything at once

## Critical Performance Strategy: Complete Module Preloading

**MANDATORY REQUIREMENT**: To achieve maximum performance, ALL Python modules MUST be preloaded at startup in `app.wsgi`. This is non-negotiable for performance-critical applications.

### Preloading Strategy
1. **Load EVERYTHING at startup** - no exceptions
2. **NO dynamic imports** after application starts
3. **Memory usage is NOT a concern** - performance is critical
4. **Pre-compile all regex patterns** at module level
5. **Pre-compile all .py files to .pyc** for faster loading

### Benefits of Complete Preloading
- **Zero import overhead**: No filesystem I/O during request handling
- **Hot cache**: All code remains in CPU cache
- **Predictable performance**: Every request has same performance profile
- **Shared memory**: Copy-on-write sharing across worker processes
- **No first-request penalty**: Everything ready from first request

### What Gets Preloaded
- All standard library modules (json, time, uuid, etc.)
- All third-party libraries (numpy, pandas, matplotlib, ujson)
- All handler classes
- All service classes
- All script classes
- All utility functions
- All compiled regex patterns

## Why mod_wsgi Instead of CGI?

### Current CGI Limitations
- **Process overhead**: New Python process for each request
- **No connection pooling**: Database/session connections recreated
- **No shared state**: Configuration loaded repeatedly
- **Slow startup**: Virtual environment initialized per request

### mod_wsgi Benefits
- **Persistent Python**: Interpreter stays loaded
- **Shared resources**: Configuration, connections cached
- **Better performance**: 5-10x faster than CGI
- **Modern architecture**: Industry standard for Python web apps

## Architecture Overview

```
Apache with mod_wsgi
    ↓
WSGI Application (persistent)
    ├── Router/Dispatcher
    ├── Session Manager (cached)
    ├── Config (loaded once)
    └── Request Handlers
        ├── LoginHandler
        ├── MainHandler
        ├── ProgressHandler
        └── PDFHandler
            ↓
    Direct Python Imports (no subprocess)
        ├── MultiServiceReachabilityTester
        ├── ReachabilityVisualizer
        └── PDFGenerator
```

## Implementation Plan

### Complete Name Mapping (Old → New)

To maintain clarity during refactoring, here's the complete mapping of ALL files being migrated:

#### CGI Scripts → WSGI Handlers
| Current Location | New Location | New Module | Handler Class |
|-----------------|--------------|------------|---------------|
| `web/cgi-bin/login.py` | `wsgi/handlers/tsim_login_handler.py` | `tsim_login_handler` | `TsimLoginHandler` |
| `web/cgi-bin/logout.py` | `wsgi/handlers/tsim_logout_handler.py` | `tsim_logout_handler` | `TsimLogoutHandler` |
| `web/cgi-bin/main.py` | `wsgi/handlers/tsim_main_handler.py` | `tsim_main_handler` | `TsimMainHandler` |
| `web/cgi-bin/pdf_viewer.py` | `wsgi/handlers/tsim_pdf_handler.py` | `tsim_pdf_handler` | `TsimPDFHandler` |
| `web/cgi-bin/get_progress.py` | `wsgi/handlers/tsim_progress_handler.py` | `tsim_progress_handler` | `TsimProgressHandler` |
| `web/cgi-bin/progress_stream.py` | `wsgi/handlers/tsim_progress_stream_handler.py` | `tsim_progress_stream_handler` | `TsimProgressStreamHandler` |
| `web/cgi-bin/get_services_config.py` | `wsgi/handlers/tsim_services_config_handler.py` | `tsim_services_config_handler` | `TsimServicesConfigHandler` |
| `web/cgi-bin/get_test_config.py` | `wsgi/handlers/tsim_test_config_handler.py` | `tsim_test_config_handler` | `TsimTestConfigHandler` |
| `web/cgi-bin/cleanup.py` | `wsgi/handlers/tsim_cleanup_handler.py` | `tsim_cleanup_handler` | `TsimCleanupHandler` |

#### CGI Libraries → WSGI Services
| Current Location | New Location | New Module | New Class |
|-----------------|--------------|------------|----------|
| `web/cgi-bin/lib/auth.py` | `wsgi/services/tsim_auth_service.py` | `tsim_auth_service` | `TsimAuthService` |
| `web/cgi-bin/lib/config.py` | `wsgi/services/tsim_config_service.py` | `tsim_config_service` | `TsimConfigService` |
| `web/cgi-bin/lib/executor.py` | `wsgi/services/tsim_executor.py` | `tsim_executor` | `TsimExecutor` |
| `web/cgi-bin/lib/session.py` | `wsgi/services/tsim_session_manager.py` | `tsim_session_manager` | `TsimSessionManager` |
| `web/cgi-bin/lib/validator.py` | `wsgi/services/tsim_validator_service.py` | `tsim_validator_service` | `TsimValidatorService` |
| `web/cgi-bin/lib/port_parser.py` | `wsgi/services/tsim_port_parser_service.py` | `tsim_port_parser_service` | `TsimPortParserService` |
| `web/cgi-bin/lib/logger.py` | `wsgi/services/tsim_logger_service.py` | `tsim_logger_service` | `TsimLoggerService` |
| `web/cgi-bin/lib/timing.py` | `wsgi/services/tsim_timing_service.py` | `tsim_timing_service` | `TsimTimingService` |
| `web/cgi-bin/lib/lock_manager.py` | `wsgi/services/tsim_lock_manager_service.py` | `tsim_lock_manager_service` | `TsimLockManagerService` |

#### Shell Scripts → Python Modules
| Current Location | New Location | New Module | New Class |
|-----------------|--------------|------------|----------|
| `web/cgi-bin/generate_pdf.sh` | `wsgi/services/tsim_pdf_generator.py` | `tsim_pdf_generator` | `TsimPDFGenerator` |

#### Core Scripts → WSGI Scripts
| Current Location | New Location | New Module | New Class | CLI Compatibility |
|-----------------|--------------|------------|-----------|-------------------|
| `src/scripts/network_reachability_test_multi.py` | `wsgi/scripts/tsim_reachability_tester.py` | `tsim_reachability_tester` | `TsimReachabilityTester` | ✓ Preserved |
| `src/scripts/visualize_reachability.py` | `wsgi/scripts/tsim_reachability_visualizer.py` | `tsim_reachability_visualizer` | `TsimReachabilityVisualizer` | ✓ Preserved |
| `src/scripts/analyze_packet_counts.py` | `wsgi/scripts/tsim_packet_analyzer.py` | `tsim_packet_analyzer` | `TsimPacketAnalyzer` | ✓ Preserved |

#### File Name Patterns
| Current Name (Pattern) | New Name (Pattern) | Rationale |
|-------------|----------|-----------|
| `network_reachability_test_multi.py` | `tsim_reachability_tester.py` | Verb→Subject, added tsim prefix |
| `visualize_reachability.py` | `tsim_reachability_visualizer.py` | Verb→Subject, added tsim prefix |
| `analyze_packet_counts.py` | `tsim_packet_analyzer.py` | Verb→Subject, simplified, added tsim prefix |
| `executor.py` | `tsim_executor.py` | Added tsim prefix |
| `pdf_generator.py` | `tsim_pdf_generator.py` | Added tsim prefix |
| `generate_pdf.sh` | (removed) | Replaced by Python module |
| `traceroute_app.py` | `tsim_app.py` | Added tsim prefix |

#### Class Names
| Current Name (Pattern) | New Name (Pattern) | Rationale |
|-------------|----------|-----------|
| `MultiServiceReachabilityTester` | `TsimReachabilityTester` | Added Tsim prefix, simplified |
| `ReachabilityVisualizer` | `TsimReachabilityVisualizer` | Added Tsim prefix |
| `PacketAnalyzer` | `TsimPacketAnalyzer` | Added Tsim prefix |
| `PDFGenerator` | `TsimPDFGenerator` | Added Tsim prefix |
| `CommandExecutor`/`TraceExecutor` | `TsimExecutor` | Added Tsim prefix, unified naming |
| `TracerouteWSGIApp` | `TsimWSGIApp` | Changed to Tsim prefix |
| `BaseHandler` | `TsimBaseHandler` | Added Tsim prefix |
| `LoginHandler` | `TsimLoginHandler` | Added Tsim prefix |
| `LogoutHandler` | `TsimLogoutHandler` | Added Tsim prefix |
| `MainHandler` | `TsimMainHandler` | Added Tsim prefix |
| `PDFHandler` | `TsimPDFHandler` | Added Tsim prefix |
| `ProgressHandler` | `TsimProgressHandler` | Added Tsim prefix |
| `ProgressStreamHandler` | `TsimProgressStreamHandler` | Added Tsim prefix |
| `ServicesConfigHandler` | `TsimServicesConfigHandler` | Added Tsim prefix |
| `TestConfigHandler` | `TsimTestConfigHandler` | Added Tsim prefix |
| `CleanupHandler` | `TsimCleanupHandler` | Added Tsim prefix |
| `AuthService`/`auth` module | `TsimAuthService` | Added Tsim prefix |
| `Config`/`config` module | `TsimConfigService` | Added Tsim prefix |
| `SessionManager`/`session` module | `TsimSessionManager` | Added Tsim prefix |
| `InputValidator`/`validator` module | `TsimValidatorService` | Added Tsim prefix |
| `PortParser`/`port_parser` module | `TsimPortParserService` | Added Tsim prefix |
| `Logger`/`logger` module | `TsimLoggerService` | Added Tsim prefix |
| `Timing`/`timing` module | `TsimTimingService` | Added Tsim prefix |
| `LockManager`/`lock_manager` module | `TsimLockManagerService` | Added Tsim prefix |
| `PerformanceMiddleware` | `TsimPerformanceMiddleware` | Added Tsim prefix |

#### Method Names
| Current Name | New Name | Context |
|-------------|----------|---------|
| `execute()` | `tsim_execute()` | TsimExecutor class |
| `execute_trace()` | `tsim_execute_trace()` | TsimExecutor class |
| `execute_reachability_multi()` | `tsim_execute_reachability_multi()` | TsimExecutor class |
| `generate_multi_page_pdf()` | `tsim_generate_multi_page_pdf()` | TsimExecutor class |
| `generate_service_pdf()` | `tsim_generate_service_pdf()` | TsimPDFGenerator class |
| `merge_pdfs()` | `tsim_merge_pdfs()` | TsimPDFGenerator class |
| `generate_multi_service_report()` | `tsim_generate_multi_service_report()` | TsimPDFGenerator class |

#### Configuration & Environment
| Current Name | New Name | Context |
|-------------|----------|---------|
| `traceroute_simulator_raw_facts` | `tsim_raw_facts` | config.json key |
| `traceroute.example.com` | `tsim.example.com` | Apache ServerName |
| `traceroute-wsgi.conf` | `tsim-wsgi.conf` | Apache config file |
| `traceroute` process | `tsim` process | WSGIDaemonProcess name |
| `traceroute-error.log` | `tsim-error.log` | Apache log file |
| `traceroute-access.log` | `tsim-access.log` | Apache log file |

### Configuration Architecture

**Apache Configuration**: Defines `TSIM_WEB_ROOT` environment variable pointing to the deployed `wsgi/` folder:
```apache
Define TSIM_WEB_ROOT /opt/tsim/wsgi  # Points to deployed wsgi/ folder
```

**Directory Structure after deployment**:
```
/opt/tsim/
├── venv/           # Virtual environment
├── raw_facts/      # Raw facts directory
├── data/           # Runtime data
├── logs/           # Application logs
└── wsgi/           # DEPLOYED WSGI code (from repo's wsgi/ folder)
    ├── app.wsgi
    ├── tsim_app.py
    ├── config.json
    ├── handlers/
    ├── services/
    └── scripts/    # Refactored scripts from src/scripts/
```

**All paths are relative to deployment root**:
- Configuration: `${TSIM_WEB_ROOT}/config.json`
- Scripts: `${TSIM_WEB_ROOT}/scripts/`
- Handlers: `${TSIM_WEB_ROOT}/handlers/`
- Services: `${TSIM_WEB_ROOT}/services/`
- Data: `/opt/tsim/data/` (defined in config.json)
- Virtual environment: `/opt/tsim/venv/` (defined in config.json)
- Raw facts: `/opt/tsim/raw_facts/` (defined in config.json)

**Sample `config.json`**:
```json
{
    "venv_path": "/opt/tsim/venv",
    "tsimsh_path": "/usr/local/bin/tsimsh",
    "tsim_raw_facts": "/opt/tsim/raw_facts",
    "data_dir": "/var/www/tsim/data",
    "log_dir": "/var/www/tsim/logs",
    "secret_key": "generated-secret-key"
}
```

### Phase 1: WSGI Application Structure

#### 1.1 Main WSGI Application

**New file:** `wsgi/app.wsgi` (top-level, NOT under web/)

**CRITICAL PERFORMANCE REQUIREMENT**: ALL Python modules MUST be preloaded here at startup. NO dynamic imports are allowed later. Memory usage is not a concern - performance is critical.

```python
#!/usr/bin/env python3
"""
Main WSGI application entry point
PERFORMANCE CRITICAL: ALL modules are preloaded at startup
"""

import sys
import os

# Get web root from environment
web_root = os.environ.get('TSIM_WEB_ROOT', '/opt/tsim/wsgi')

# Add paths
sys.path.insert(0, web_root)
sys.path.insert(0, os.path.join(web_root, 'scripts'))

# ============================================================================
# PRELOAD ALL MODULES FOR MAXIMUM PERFORMANCE
# Memory usage is not a concern - we want everything in memory
# ============================================================================

# Preload standard library modules that will be used
import json
import time
import uuid
import hashlib
import secrets
import traceback
import subprocess
import threading
import queue
import re
import cgi
import io
import fcntl
import tempfile
import shutil
import gzip
import base64
import urllib.parse
import http.cookies
from pathlib import Path
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from functools import lru_cache, wraps
from collections import defaultdict, OrderedDict

# Preload heavy third-party modules
try:
    import numpy
    import pandas
    import matplotlib
    import matplotlib.pyplot as plt
    import ujson  # Ultra-fast JSON
except ImportError:
    pass  # Some may not be installed

# Preload ALL handlers (import but don't instantiate yet)
from handlers.tsim_base_handler import TsimBaseHandler
from handlers.tsim_login_handler import TsimLoginHandler
from handlers.tsim_logout_handler import TsimLogoutHandler
from handlers.tsim_main_handler import TsimMainHandler
from handlers.tsim_pdf_handler import TsimPDFHandler
from handlers.tsim_progress_handler import TsimProgressHandler
from handlers.tsim_progress_stream_handler import TsimProgressStreamHandler
from handlers.tsim_services_config_handler import TsimServicesConfigHandler
from handlers.tsim_test_config_handler import TsimTestConfigHandler
from handlers.tsim_cleanup_handler import TsimCleanupHandler

# Preload ALL services
from services.tsim_auth_service import TsimAuthService
from services.tsim_config_service import TsimConfigService
from services.tsim_session_manager import TsimSessionManager
from services.tsim_validator_service import TsimValidatorService
from services.tsim_port_parser_service import TsimPortParserService
from services.tsim_logger_service import TsimLoggerService
from services.tsim_timing_service import TsimTimingService
from services.tsim_lock_manager_service import TsimLockManagerService
from services.tsim_executor import TsimExecutor
from services.tsim_pdf_generator import TsimPDFGenerator

# Preload ALL refactored scripts
from scripts.tsim_reachability_tester import TsimReachabilityTester
from scripts.tsim_reachability_visualizer import TsimReachabilityVisualizer
from scripts.tsim_packet_analyzer import TsimPacketAnalyzer

# Pre-compile all regex patterns that will be used
import re
IP_PATTERN = re.compile(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$')
PORT_PATTERN = re.compile(r'^([0-9]+)(?:/([a-z]+))?$')
SESSION_ID_PATTERN = re.compile(r'^[a-f0-9]{32}$')

# Pre-compile Python files for faster execution
import py_compile
import compileall
compileall.compile_dir(web_root, force=True, quiet=True)

# Import the main application AFTER all modules are loaded
from tsim_app import application

# Wrap with performance monitoring
from services.tsim_performance_middleware import TsimPerformanceMiddleware
application = TsimPerformanceMiddleware(application)

# This is what mod_wsgi will call
application = application
```

#### 1.2 Core WSGI Application

**New file:** `wsgi/tsim_app.py` (top-level, NOT under web/)

```python
"""
TSIM WSGI Application
NOTE: All imports should already be preloaded by app.wsgi
"""

# These imports are redundant (already loaded in app.wsgi) but kept for clarity
# They will NOT cause re-loading - Python will use cached modules
import json
import os
import sys
import traceback
from urllib.parse import parse_qs
from http.cookies import SimpleCookie

# All handlers are already preloaded in app.wsgi
from handlers.tsim_login_handler import TsimLoginHandler
from handlers.tsim_logout_handler import TsimLogoutHandler
from handlers.tsim_main_handler import TsimMainHandler
from handlers.tsim_pdf_handler import TsimPDFHandler
from handlers.tsim_progress_handler import TsimProgressHandler
from handlers.tsim_progress_stream_handler import TsimProgressStreamHandler
from handlers.tsim_services_config_handler import TsimServicesConfigHandler
from handlers.tsim_test_config_handler import TsimTestConfigHandler
from handlers.tsim_cleanup_handler import TsimCleanupHandler

# All services are already preloaded in app.wsgi
from services.tsim_session_manager import TsimSessionManager
from services.tsim_config_service import TsimConfigService
from services.tsim_logger_service import TsimLoggerService

class TsimWSGIApp:
    """Main WSGI Application"""
    
    def __init__(self):
        """Initialize shared services once at startup
        
        PERFORMANCE NOTE: All service classes are already loaded in memory
        from app.wsgi preloading. This just instantiates them.
        """
        self.config = TsimConfigService()
        self.session_manager = TsimSessionManager()
        self.logger = TsimLoggerService()
        
        # Initialize ALL handlers with shared services
        self.handlers = {
            '/api/login': TsimLoginHandler(self.session_manager, self.logger),
            '/api/logout': TsimLogoutHandler(self.session_manager, self.logger),
            '/api/main': TsimMainHandler(self.config, self.session_manager, self.logger),
            '/api/pdf': TsimPDFHandler(self.config, self.session_manager, self.logger),
            '/api/progress': TsimProgressHandler(self.session_manager, self.logger),
            '/api/progress-stream': TsimProgressStreamHandler(self.session_manager, self.logger),
            '/api/services-config': TsimServicesConfigHandler(self.config),
            '/api/test-config': TsimTestConfigHandler(self.config, self.session_manager),
            '/api/cleanup': TsimCleanupHandler(self.config, self.session_manager, self.logger),
        }
        
        self.logger.log_info("WSGI Application initialized")
    
    def __call__(self, environ, start_response):
        """WSGI application callable"""
        
        path = environ.get('PATH_INFO', '/')
        method = environ.get('REQUEST_METHOD', 'GET')
        
        try:
            # Route to appropriate handler
            if path in self.handlers:
                return self.handlers[path].handle(environ, start_response)
            else:
                # 404 Not Found
                start_response('404 Not Found', [('Content-Type', 'text/plain')])
                return [b'Not Found']
                
        except Exception as e:
            # Log error
            self.logger.log_error(f"WSGI Error: {str(e)}", traceback=traceback.format_exc())
            
            # Return 500 error
            start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
            return [b'Internal Server Error']

# Create single application instance (persistent across requests)
application = TsimWSGIApp()
```

#### 1.3 Base Handler Class

**New file:** `wsgi/handlers/tsim_base_handler.py` (top-level wsgi/, NOT under web/)

```python
"""
Base handler class for all request handlers
"""

from abc import ABC, abstractmethod
from urllib.parse import parse_qs
from http.cookies import SimpleCookie
import json
import cgi
import io

class TsimBaseHandler(ABC):
    """Base class for all handlers"""
    
    def __init__(self, session_manager=None, logger=None):
        self.session_manager = session_manager
        self.logger = logger
    
    def parse_post_data(self, environ):
        """Parse POST data from environ"""
        try:
            content_length = int(environ.get('CONTENT_LENGTH', 0))
        except ValueError:
            content_length = 0
        
        if content_length > 0:
            body = environ['wsgi.input'].read(content_length)
            
            if environ.get('CONTENT_TYPE', '').startswith('application/x-www-form-urlencoded'):
                return parse_qs(body.decode('utf-8'))
            elif environ.get('CONTENT_TYPE', '').startswith('multipart/form-data'):
                # Handle multipart form data
                fp = io.BytesIO(body)
                form = cgi.FieldStorage(fp=fp, environ=environ, keep_blank_values=True)
                return form
            elif environ.get('CONTENT_TYPE', '').startswith('application/json'):
                return json.loads(body.decode('utf-8'))
        
        return {}
    
    def parse_cookies(self, environ):
        """Parse cookies from environ"""
        cookie_str = environ.get('HTTP_COOKIE', '')
        cookies = SimpleCookie(cookie_str)
        return cookies
    
    def get_session_id(self, environ):
        """Extract session ID from cookies"""
        cookies = self.parse_cookies(environ)
        if 'session_id' in cookies:
            return cookies['session_id'].value
        return None
    
    def json_response(self, start_response, data, status='200 OK'):
        """Send JSON response"""
        response_body = json.dumps(data).encode('utf-8')
        response_headers = [
            ('Content-Type', 'application/json'),
            ('Content-Length', str(len(response_body)))
        ]
        start_response(status, response_headers)
        return [response_body]
    
    def redirect_response(self, start_response, location, cookie=None):
        """Send redirect response"""
        headers = [
            ('Location', location),
            ('Content-Type', 'text/html')
        ]
        if cookie:
            headers.append(('Set-Cookie', cookie))
        
        start_response('302 Found', headers)
        return [b'Redirecting...']
    
    @abstractmethod
    def handle(self, environ, start_response):
        """Handle the request"""
        pass
```

#### 1.4 Main Request Handler

**New file:** `wsgi/handlers/tsim_main_handler.py` (top-level wsgi/, NOT under web/)

```python
"""
Main test execution handler
"""

import sys
import uuid
import json
from .tsim_base_handler import TsimBaseHandler

# Direct imports - no subprocess needed!
# Scripts must be installed in <web-root>/scripts/
from tsim_reachability_tester import TsimReachabilityTester
from tsim_reachability_visualizer import TsimReachabilityVisualizer

from services.tsim_validator_service import TsimValidatorService
from services.tsim_port_parser_service import TsimPortParserService
from services.tsim_executor import TsimExecutor
from services.tsim_pdf_generator import TsimPDFGenerator

class TsimMainHandler(TsimBaseHandler):
    """Handle main test execution requests"""
    
    def __init__(self, config, session_manager, logger):
        super().__init__(session_manager, logger)
        self.config = config
        self.validator = TsimValidatorService()
        self.port_parser = TsimPortParserService()
        self.trace_executor = TsimExecutor(config)  # Still uses subprocess for tsimsh
        self.pdf_generator = TsimPDFGenerator()
    
    def handle(self, environ, start_response):
        """Handle test execution request"""
        
        # Check session
        session_id = self.get_session_id(environ)
        session = self.session_manager.get_session(session_id)
        
        if not session:
            return self.redirect_response(start_response, '/login.html')
        
        # Parse POST data
        data = self.parse_post_data(environ)
        
        # Extract parameters
        source_ip = data.get('source_ip', [''])[0]
        source_port = data.get('source_port', [''])[0]
        dest_ip = data.get('dest_ip', [''])[0]
        port_mode = data.get('port_mode', ['quick'])[0]
        
        # Validate inputs
        if not self.validator.validate_ip(source_ip):
            return self.json_response(start_response, {'error': 'Invalid source IP'}, '400 Bad Request')
        
        if not self.validator.validate_ip(dest_ip):
            return self.json_response(start_response, {'error': 'Invalid destination IP'}, '400 Bad Request')
        
        # Parse ports
        if port_mode == 'quick':
            quick_ports = data.get('quick_ports', [])
            dest_port_spec = ','.join(quick_ports)
        else:
            dest_port_spec = data.get('dest_ports', [''])[0]
        
        default_protocol = data.get('default_protocol', ['tcp'])[0]
        user_trace_data = data.get('user_trace_data', [''])[0]
        
        # Parse port specifications
        try:
            port_protocol_list = self.port_parser.parse_port_spec(
                dest_port_spec, default_protocol, max_services=10
            )
        except ValueError as e:
            return self.json_response(start_response, {'error': str(e)}, '400 Bad Request')
        
        # Generate run ID
        run_id = str(uuid.uuid4())
        
        # Execute test synchronously (no background worker needed with mod_wsgi)
        try:
            # 1. Execute trace (still uses subprocess for tsimsh)
            trace_file = self.trace_executor.tsim_execute(
                run_id, source_ip, dest_ip, user_trace_data
            )
            
            # 2. Execute reachability tests (DIRECT PYTHON CALL)
            tester = TsimReachabilityTester(
                trace_file=trace_file,
                source_ip=source_ip,
                dest_ip=dest_ip,
                source_port=source_port,
                port_protocol_list=port_protocol_list
            )
            results = tester.run()
            
            # 3. Generate PDF (DIRECT PYTHON CALL)
            pdf_file = self.pdf_generator.tsim_generate_multi_service_report(
                run_id, trace_file, results['result_files']
            )
            
            # Save to session for retrieval
            self.session_manager.save_test_result(session_id, run_id, {
                'pdf_file': pdf_file,
                'trace_file': trace_file,
                'results': results
            })
            
            # Return success response
            return self.json_response(start_response, {
                'success': True,
                'run_id': run_id,
                'redirect': f'/pdf_viewer_final.html?id={run_id}'
            })
            
        except Exception as e:
            self.logger.log_error(f"Test execution failed: {str(e)}")
            return self.json_response(start_response, {
                'error': 'Test execution failed'
            }, '500 Internal Server Error')
```

#### 1.5 Additional Handler Examples

**Progress Stream Handler** (`wsgi/handlers/tsim_progress_stream_handler.py`):
```python
"""
Server-sent events for real-time progress updates
"""
import json
import time
from pathlib import Path
from .tsim_base_handler import TsimBaseHandler

class TsimProgressStreamHandler(TsimBaseHandler):
    """Handle SSE progress stream requests"""
    
    def handle(self, environ, start_response):
        """Stream progress updates via Server-Sent Events"""
        
        run_id = self.get_query_param(environ, 'run_id')
        session_id = self.get_query_param(environ, 'session')
        
        # Validate session
        session = self.session_manager.get_session(session_id)
        if not session:
            return self.error_response(start_response, 'Invalid session', '401 Unauthorized')
        
        # Set SSE headers
        headers = [
            ('Content-Type', 'text/event-stream'),
            ('Cache-Control', 'no-cache'),
            ('Connection', 'keep-alive'),
            ('Access-Control-Allow-Origin', '*')
        ]
        start_response('200 OK', headers)
        
        # Stream progress updates
        progress_file = Path(f'/opt/tsim/data/progress/{run_id}.json')
        last_position = 0
        
        def generate():
            nonlocal last_position
            while True:
                if progress_file.exists():
                    with open(progress_file, 'r') as f:
                        f.seek(last_position)
                        new_data = f.read()
                        if new_data:
                            last_position = f.tell()
                            yield f"data: {new_data}\n\n".encode('utf-8')
                        
                        # Check if complete
                        f.seek(0)
                        all_data = json.load(f)
                        if all_data.get('complete'):
                            yield f"data: {json.dumps({'complete': True})}\n\n".encode('utf-8')
                            break
                
                time.sleep(0.5)  # Poll every 500ms
        
        return generate()
```

**Test Config Handler** (`wsgi/handlers/tsim_test_config_handler.py`):
```python
"""
Handle test configuration requests
"""
from .tsim_base_handler import TsimBaseHandler

class TsimTestConfigHandler(TsimBaseHandler):
    """Return test configuration options"""
    
    def __init__(self, config, session_manager):
        super().__init__(session_manager)
        self.config = config
    
    def handle(self, environ, start_response):
        """Return available test configurations"""
        
        # Check session
        session_id = self.get_session_id(environ)
        session = self.session_manager.get_session(session_id)
        
        if not session:
            return self.redirect_response(start_response, '/login.html')
        
        # Return test configurations
        test_config = {
            'available_ports': {
                'quick': ['22/tcp', '80/tcp', '443/tcp', '3306/tcp', '5432/tcp'],
                'common': ['21/tcp', '22/tcp', '23/tcp', '25/tcp', '53/udp', 
                          '80/tcp', '110/tcp', '143/tcp', '443/tcp', '445/tcp',
                          '3306/tcp', '3389/tcp', '5432/tcp', '8080/tcp', '8443/tcp'],
                'all': 'Use custom port specification'
            },
            'protocols': ['tcp', 'udp'],
            'max_services': 10,
            'timeout': 60,
            'trace_options': {
                'max_hops': 30,
                'packet_size': 60,
                'protocol': 'ICMP'
            }
        }
        
        return self.json_response(start_response, test_config)
```

**Cleanup Handler** (`wsgi/handlers/tsim_cleanup_handler.py`):
```python
"""
Handle cleanup of old test data
"""
import os
import time
from pathlib import Path
from .tsim_base_handler import TsimBaseHandler

class TsimCleanupHandler(TsimBaseHandler):
    """Clean up old test data and sessions"""
    
    def __init__(self, config, session_manager, logger):
        super().__init__(session_manager, logger)
        self.config = config
        self.data_dir = Path('/opt/tsim/data')
        self.max_age = 86400  # 24 hours
    
    def handle(self, environ, start_response):
        """Perform cleanup of old data"""
        
        # Admin authentication required
        session_id = self.get_session_id(environ)
        session = self.session_manager.get_session(session_id)
        
        if not session or session.get('role') != 'admin':
            return self.error_response(start_response, 'Admin access required', '403 Forbidden')
        
        cleanup_stats = {
            'sessions_removed': 0,
            'test_files_removed': 0,
            'pdf_files_removed': 0,
            'total_space_freed': 0
        }
        
        current_time = time.time()
        
        # Clean old sessions from /dev/shm/tsim
        session_dir = Path('/dev/shm/tsim')
        if session_dir.exists():
            for session_file in session_dir.glob('*.json'):
                if current_time - session_file.stat().st_mtime > self.max_age:
                    cleanup_stats['total_space_freed'] += session_file.stat().st_size
                    session_file.unlink()
                    cleanup_stats['sessions_removed'] += 1
        
        # Clean old test data
        for test_dir in ['traces', 'results', 'progress']:
            dir_path = self.data_dir / test_dir
            if dir_path.exists():
                for test_file in dir_path.glob('*'):
                    if current_time - test_file.stat().st_mtime > self.max_age:
                        cleanup_stats['total_space_freed'] += test_file.stat().st_size
                        test_file.unlink()
                        cleanup_stats['test_files_removed'] += 1
        
        # Clean old PDFs
        pdf_dir = self.data_dir / 'pdfs'
        if pdf_dir.exists():
            for pdf_file in pdf_dir.glob('*.pdf'):
                if current_time - pdf_file.stat().st_mtime > self.max_age:
                    cleanup_stats['total_space_freed'] += pdf_file.stat().st_size
                    pdf_file.unlink()
                    cleanup_stats['pdf_files_removed'] += 1
        
        # Log cleanup
        self.logger.log_info(f"Cleanup completed: {cleanup_stats}")
        
        return self.json_response(start_response, {
            'success': True,
            'stats': cleanup_stats
        })
```

### Phase 2: Apache Configuration

#### 2.0 Apache Environment Setup

The Apache configuration uses environment variables and the `Define` directive to avoid hardcoded paths:

```apache
# In main Apache config or virtual host
Define TSIM_WEB_ROOT /var/www/tsim

# This can be overridden per deployment:
# - Production: /var/www/tsim
# - Staging: /var/www/tsim-staging  
# - Development: /home/developer/tsim-web
```

All other Apache directives use `${TSIM_WEB_ROOT}` to reference paths, making the configuration portable.

#### 2.1 How mod_wsgi Ensures Venv Python is Used

**Key Concept**: mod_wsgi is compiled for a specific Python version. The `python-home` parameter tells it where to find the virtual environment.

**Critical Points**:
1. **mod_wsgi must be compiled against the same Python version as your venv**
2. **The `python-home` directive points to the venv root**
3. **mod_wsgi automatically uses venv's site-packages**

#### 2.2 Install mod_wsgi in Virtual Environment

**We use Option B: Install mod_wsgi in Venv** for maximum compatibility and performance:

```bash
# Step 1: Install mod_wsgi in virtual environment
/opt/tsim/venv/bin/pip install mod-wsgi

# Step 2: Generate Apache configuration snippet
/opt/tsim/venv/bin/mod_wsgi-express module-config > /tmp/mod_wsgi_config.txt

# Step 3: Add to Apache configuration (usually in /etc/apache2/mods-available/wsgi_tsim.load)
# Content will be similar to:
LoadModule wsgi_module /opt/tsim/venv/lib/python3.9/site-packages/mod_wsgi/server/mod_wsgi-py39.cpython-39-x86_64-linux-gnu.so

# Step 4: Enable the module
sudo a2enmod wsgi_tsim
sudo systemctl restart apache2
```

**Benefits of Venv Installation**:
- Compiled specifically for your Python version
- No system Python dependency
- Faster execution (optimized for your environment)
- Can update independently of system packages

#### 2.3 Apache Virtual Host Configuration

**File:** `/etc/apache2/sites-available/tsim-wsgi.conf`

```apache
<VirtualHost *:443>
    ServerName tsim.example.com
    
    # All parameters as Define directives for easy management
    Define TSIM_WEB_ROOT /opt/tsim/wsgi  # Points to deployed wsgi/ folder
    Define TSIM_VENV_PATH /opt/tsim/venv
    Define TSIM_SESSION_DIR /dev/shm/tsim
    Define TSIM_PROCESSES 4
    Define TSIM_THREADS 15
    Define TSIM_MAX_REQUESTS 10000
    Define TSIM_INACTIVITY_TIMEOUT 300
    Define TSIM_REQUEST_TIMEOUT 60
    
    # Static files still served from original web/htdocs during transition
    DocumentRoot /var/www/tsim/htdocs  # Original htdocs, will be moved later
    
    # SSL Configuration (with performance optimizations)
    SSLEngine on
    SSLCertificateFile /path/to/cert.pem
    SSLCertificateKeyFile /path/to/key.pem
    SSLProtocol -all +TLSv1.2 +TLSv1.3
    SSLCipherSuite HIGH:!aNULL:!MD5
    SSLSessionCache shmcb:/run/httpd/sslcache(512000)
    SSLSessionCacheTimeout 300
    
    # Static files with caching headers (from original location during transition)
    Alias /css /var/www/tsim/htdocs/css
    Alias /js /var/www/tsim/htdocs/js
    Alias /images /var/www/tsim/htdocs/images
    
    <Directory /var/www/tsim/htdocs>
        Options -Indexes +FollowSymLinks
        AllowOverride None
        Require all granted
        
        # Enable compression for static files
        <IfModule mod_deflate.c>
            AddOutputFilterByType DEFLATE text/css text/javascript application/javascript
        </IfModule>
        
        # Cache static files
        <IfModule mod_expires.c>
            ExpiresActive On
            ExpiresByType text/css "access plus 1 week"
            ExpiresByType application/javascript "access plus 1 week"
            ExpiresByType image/png "access plus 1 month"
        </IfModule>
    </Directory>
    
    # WSGI Configuration with Performance Optimizations
    WSGIDaemonProcess tsim \
        python-home=${TSIM_VENV_PATH} \
        python-path=${TSIM_WEB_ROOT}/wsgi:${TSIM_WEB_ROOT}/scripts \
        processes=${TSIM_PROCESSES} \
        threads=${TSIM_THREADS} \
        maximum-requests=${TSIM_MAX_REQUESTS} \
        inactivity-timeout=${TSIM_INACTIVITY_TIMEOUT} \
        request-timeout=${TSIM_REQUEST_TIMEOUT} \
        socket-timeout=60 \
        cpu-time-limit=300 \
        display-name=tsim-wsgi \
        user=www-data \
        group=www-data \
        lang=C.UTF-8 \
        locale=C.UTF-8
    
    # Performance notes:
    # - processes=4: Good for quad-core server
    # - threads=15: Optimal for I/O-bound operations
    # - maximum-requests=10000: Recycle processes to prevent memory leaks
    # - inactivity-timeout=300: Kill idle processes after 5 minutes
    # - request-timeout=60: Prevent hung requests
    
    WSGIProcessGroup tsim
    WSGIApplicationGroup %{GLOBAL}
    
    # Mount WSGI application from new wsgi/ folder
    WSGIScriptAlias /api ${TSIM_WEB_ROOT}/app.wsgi
    
    <Directory ${TSIM_WEB_ROOT}>
        Require all granted
    </Directory>
    
    # Environment variables
    SetEnv TSIM_WEB_ROOT ${TSIM_WEB_ROOT}
    # Other paths will be read from config.json
    
    # Logging
    ErrorLog ${APACHE_LOG_DIR}/tsim-error.log
    CustomLog ${APACHE_LOG_DIR}/tsim-access.log combined
</VirtualHost>
```

### Performance Optimizations for Maximum Speed

#### 0. Module Preloading (MOST CRITICAL)

**MANDATORY REQUIREMENT**: ALL Python modules MUST be preloaded in `app.wsgi` at startup:

```python
# NO dynamic imports allowed after startup!
# Everything must be loaded in app.wsgi:
# - All standard library modules
# - All third-party libraries
# - All handlers
# - All services
# - All scripts
# - All utilities

# This ensures:
# - Zero import overhead during requests
# - All code is hot in CPU cache
# - No filesystem I/O for module loading
# - Predictable sub-millisecond response times
```

### Additional Performance Optimizations

#### 1. Memory-Based Session Management (/dev/shm)

```python
# services/tsim_session_manager.py
import os
import json
import time
import fcntl
from pathlib import Path

class TsimSessionManager:
    """High-performance session management using /dev/shm (RAM disk)"""
    
    def __init__(self, session_dir="/dev/shm/tsim"):
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(mode=0o700, exist_ok=True)
        
    def create_session(self, username):
        """Create session in memory (100x faster than disk)"""
        session_id = self._generate_session_id()
        session_file = self.session_dir / f"{session_id}.json"
        
        session_data = {
            'username': username,
            'created': time.time(),
            'last_access': time.time()
        }
        
        # Atomic write with file locking
        with open(session_file, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            json.dump(session_data, f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        return session_id
    
    def get_session(self, session_id):
        """Read session from memory (microseconds)"""
        session_file = self.session_dir / f"{session_id}.json"
        
        if not session_file.exists():
            return None
            
        with open(session_file, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            data = json.load(f)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
        return data
```

**Benefits of /dev/shm**:
- **100x faster** than disk-based sessions
- **No disk I/O** - pure memory operations
- **Automatic cleanup** on reboot
- **No SSD wear** from session writes

#### 2. Python Code Optimizations

```python
# Optimization techniques for WSGI handlers

# 1. Pre-compile regex patterns
import re
IP_PATTERN = re.compile(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$')
PORT_PATTERN = re.compile(r'^([0-9]+)(?:/([a-z]+))?$')

# 2. Use __slots__ for memory efficiency
class TsimRequest:
    __slots__ = ['source_ip', 'dest_ip', 'ports', 'session_id']
    
    def __init__(self, source_ip, dest_ip, ports, session_id):
        self.source_ip = source_ip
        self.dest_ip = dest_ip
        self.ports = ports
        self.session_id = session_id

# 3. Cache expensive operations
from functools import lru_cache

@lru_cache(maxsize=128)
def validate_ip(ip_address):
    """Cached IP validation"""
    return IP_PATTERN.match(ip_address) is not None

# 4. Use generators for large datasets
def process_results(data):
    """Memory-efficient processing"""
    for item in data:
        yield process_item(item)  # Don't load all in memory

# 5. Optimize JSON operations
import ujson  # Ultra-fast JSON (install: pip install ujson)

def fast_json_response(data):
    return ujson.dumps(data)  # 2-3x faster than json.dumps
```

#### 3. Apache/mod_wsgi Optimizations

```apache
# Additional performance directives

# Enable HTTP/2 for better performance
Protocols h2 http/1.1

# Connection keep-alive settings
KeepAlive On
KeepAliveTimeout 5
MaxKeepAliveRequests 100

# Enable sendfile for static files
EnableSendfile On

# Optimize buffer sizes
SendBufferSize 65536
ReceiveBufferSize 65536

# WSGI specific optimizations
WSGIRestrictEmbedded On  # Don't load WSGI in Apache processes
WSGISocketPrefix /var/run/wsgi  # Faster socket communication
```

#### 4. Database/Cache Optimizations

```python
# Use Redis for shared cache (if needed)
import redis
import pickle

class TsimCache:
    def __init__(self):
        # Unix socket is faster than TCP
        self.redis = redis.Redis(unix_socket_path='/var/run/redis/redis.sock')
        
    def get(self, key):
        data = self.redis.get(key)
        return pickle.loads(data) if data else None
        
    def set(self, key, value, ttl=300):
        self.redis.setex(key, ttl, pickle.dumps(value))
```

#### 5. Startup Optimizations

**CRITICAL REQUIREMENT**: ALL modules MUST be preloaded in app.wsgi. See section 1.1 for the complete preloading implementation.

```python
# Key principles for maximum performance:
# 1. EVERYTHING is loaded at startup in app.wsgi
# 2. NO dynamic imports after startup
# 3. Memory usage is NOT a concern
# 4. All regex patterns pre-compiled
# 5. All Python files pre-compiled to .pyc
# 6. All heavy libraries loaded before fork

# Benefits of complete preloading:
# - Zero import overhead during request handling
# - All code is hot in memory
# - No filesystem access for imports
# - Predictable performance (no first-request penalty)
# - Shared memory across worker processes (copy-on-write)
```

#### 6. Monitoring & Profiling

**New file:** `wsgi/services/tsim_performance_middleware.py`

```python
# This file is PRELOADED in app.wsgi - no dynamic import overhead
import time
import logging
import os
import psutil  # If available, for memory monitoring

class TsimPerformanceMiddleware:
    """Performance monitoring middleware - loaded at startup"""
    
    def __init__(self, app):
        self.app = app
        self.logger = logging.getLogger('performance')
        self.request_count = 0
        self.total_time = 0
        
        # Log startup confirmation
        self.logger.info("All modules preloaded successfully")
        self.logger.info(f"Process memory: {self._get_memory_usage()}MB")
        
    def _get_memory_usage(self):
        """Get current memory usage in MB"""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except:
            return 0
            
    def __call__(self, environ, start_response):
        start_time = time.time()
        self.request_count += 1
        
        # Log if this is first request (should be fast due to preloading)
        if self.request_count == 1:
            self.logger.info("First request - all modules already loaded")
        
        def custom_start_response(status, headers):
            elapsed = time.time() - start_time
            self.total_time += elapsed
            
            # Add performance headers
            headers.append(('X-Response-Time', f'{elapsed:.3f}'))
            headers.append(('X-Request-Count', str(self.request_count)))
            headers.append(('X-Avg-Response-Time', f'{self.total_time/self.request_count:.3f}'))
            
            # Log slow requests
            if elapsed > 1.0:
                self.logger.warning(f"Slow request: {elapsed:.3f}s - {environ.get('PATH_INFO')}")
            
            return start_response(status, headers)
            
        return self.app(environ, custom_start_response)
```

Note: This middleware is instantiated in `app.wsgi` AFTER all modules are preloaded.

### How mod_wsgi Uses Virtual Environment

#### What Happens When Apache Starts

1. **mod_wsgi loads**: Uses the Python version it was compiled against
2. **Reads python-home**: Points to venv root directory
3. **Sets up Python environment**:
   ```python
   # mod_wsgi internally does equivalent of:
   sys.prefix = '/opt/tsim/venv'
   sys.exec_prefix = '/opt/tsim/venv'
   sys.path.insert(0, '/opt/tsim/venv/lib/python3.9/site-packages')
   ```
4. **Imports work correctly**: All venv packages are available
5. **No activation needed**: Unlike CGI, no subprocess or activation script required

#### Verification

To verify correct Python is being used, add this to your WSGI app:

```python
import sys
import os

def application(environ, start_response):
    info = [
        f"sys.executable: {sys.executable}",
        f"sys.prefix: {sys.prefix}",
        f"sys.path: {sys.path[:3]}",  # First 3 paths
        f"Virtual env: {os.environ.get('VIRTUAL_ENV', 'Not set')}",
    ]
    
    response = '\n'.join(info).encode('utf-8')
    status = '200 OK'
    headers = [('Content-Type', 'text/plain')]
    start_response(status, headers)
    return [response]
```

Should show:
```
sys.executable: /opt/tsim/venv/bin/python
sys.prefix: /opt/tsim/venv
sys.path: ['/opt/tsim/venv/lib/python3.9/site-packages', ...]
```

### Phase 3: Frontend Updates

#### 3.1 URL Endpoint Mapping

All frontend JavaScript and HTML forms must be updated to use new API endpoints:

| Old CGI Endpoint | New WSGI Endpoint | Used In Files |
|-----------------|-------------------|---------------|
| `/cgi-bin/login.py` | `/api/login` | `login.html` |
| `/cgi-bin/logout.py` | `/api/logout` | All pages with logout |
| `/cgi-bin/main.py` | `/api/main` | `form.html` |
| `/cgi-bin/pdf_viewer.py` | `/api/pdf` | `pdf_viewer_final.html` |
| `/cgi-bin/get_progress.py` | `/api/progress` | `progress.html` |
| `/cgi-bin/progress_stream.py` | `/api/progress-stream` | `progress.html` |
| `/cgi-bin/get_services_config.py` | `/api/services-config` | `form.html` |
| `/cgi-bin/get_test_config.py` | `/api/test-config` | `form.html` |
| `/cgi-bin/cleanup.py` | `/api/cleanup` | Admin panel |

#### 3.2 Update HTML Forms to Use API Endpoints

**Updated:** `web/htdocs/form.html`

```html
<!-- Change form action from CGI to API endpoint -->
<form id="reachability-form" method="POST">
    <!-- Form fields remain the same -->
</form>

<script>
document.getElementById('reachability-form').onsubmit = async function(e) {
    e.preventDefault();
    
    const formData = new FormData(this);
    
    try {
        const response = await fetch('/api/main', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            window.location.href = result.redirect;
        } else {
            alert('Error: ' + result.error);
        }
    } catch (error) {
        alert('Request failed: ' + error);
    }
};
</script>
```

### Phase 4: Big-Bang Migration (Direct Replacement)

Since this is a small, non-production application, we'll do a **complete replacement** in one go:

#### Step 1: Implement All WSGI Handlers

Create all handlers at once in `wsgi/handlers/` (top-level wsgi folder):
- `tsim_base_handler.py`
- `tsim_login_handler.py`
- `tsim_main_handler.py` 
- `tsim_logout_handler.py`
- `tsim_progress_handler.py`
- `tsim_progress_stream_handler.py`
- `tsim_pdf_handler.py`
- `tsim_services_config_handler.py`
- `tsim_test_config_handler.py`
- `tsim_cleanup_handler.py`

#### Step 2: Replace Apache Configuration

**Remove old CGI configuration:**
```apache
# DELETE THIS from existing Apache config:
ScriptAlias /cgi-bin/ /var/www/tsim/cgi-bin/
<Directory "/var/www/tsim/cgi-bin">
    Options +ExecCGI
    AddHandler cgi-script .py
</Directory>
```

**Replace with WSGI configuration:**
```apache
# NEW CONFIGURATION - Complete replacement
<VirtualHost *:443>
    ServerName tsim.example.com
    
    Define TSIM_WEB_ROOT /opt/tsim/wsgi  # NEW wsgi folder
    DocumentRoot /var/www/tsim/htdocs  # Keep original for static files
    
    # Static files from original location
    Alias /css /var/www/tsim/htdocs/css
    Alias /js /var/www/tsim/htdocs/js
    
    # WSGI Configuration (replaces ALL CGI)
    WSGIDaemonProcess tsim \
        python-home=/opt/tsim/venv \
        python-path=${TSIM_WEB_ROOT}:${TSIM_WEB_ROOT}/scripts
    
    WSGIProcessGroup tsim
    WSGIScriptAlias / ${TSIM_WEB_ROOT}/app.wsgi
    
    # Map old URLs to new API endpoints
    RewriteEngine On
    RewriteRule ^/cgi-bin/login.py$ /api/login [R=301,L]
    RewriteRule ^/cgi-bin/main.py$ /api/main [R=301,L]
    RewriteRule ^/cgi-bin/logout.py$ /api/logout [R=301,L]
    RewriteRule ^/cgi-bin/pdf_viewer.py$ /api/pdf [R=301,L]
</VirtualHost>
```

#### Step 3: Update Frontend (All at Once)

Replace all CGI endpoints in JavaScript:
```javascript
// OLD
fetch('/cgi-bin/login.py', ...)
fetch('/cgi-bin/main.py', ...)

// NEW  
fetch('/api/login', ...)
fetch('/api/main', ...)
```

Or use a global constant:
```javascript
const API_BASE = '/api';  // No gradual migration needed
fetch(`${API_BASE}/login`, ...)
```

#### Step 4: Deploy and Test

1. **Stop Apache**: `sudo systemctl stop apache2`
2. **Deploy new code**: Copy all WSGI files
3. **Update Apache config**: Replace entire virtual host
4. **Start Apache**: `sudo systemctl start apache2`
5. **Test all endpoints**: Run full test suite

#### Timeline: 1-2 Days Total

| Day | Task | Duration |
|-----|------|----------|
| **Day 1 AM** | Write all WSGI handlers | 4 hours |
| **Day 1 PM** | Update frontend JavaScript | 2 hours |
| **Day 1 PM** | Test locally | 2 hours |
| **Day 2 AM** | Deploy to server | 1 hour |
| **Day 2 AM** | Run tests | 2 hours |
| **Day 2 PM** | Fix any issues | 2 hours |
| **Done!** | CGI completely replaced | - |

## Development and Deployment Structure

### During Development
```
traceroute-simulator/           # Git repository
├── web/                       # EXISTING CGI - DO NOT MODIFY
│   ├── cgi-bin/              # Current CGI scripts
│   └── htdocs/               # Current static files
├── src/                      # EXISTING core - DO NOT MODIFY
│   └── scripts/              # Current CLI scripts
└── wsgi/                     # NEW WSGI implementation
    ├── app.wsgi              # Entry point
    ├── tsim_app.py           # Main application
    ├── config.json           # Configuration
    ├── handlers/             # All request handlers
    │   ├── __init__.py
    │   ├── tsim_base_handler.py
    │   ├── tsim_login_handler.py
    │   ├── tsim_logout_handler.py
    │   ├── tsim_main_handler.py
    │   ├── tsim_pdf_handler.py
    │   ├── tsim_progress_handler.py
    │   ├── tsim_progress_stream_handler.py
    │   ├── tsim_services_config_handler.py
    │   ├── tsim_test_config_handler.py
    │   └── tsim_cleanup_handler.py
    ├── services/             # Shared services
    │   ├── __init__.py
    │   ├── tsim_auth_service.py
    │   ├── tsim_config_service.py
    │   ├── tsim_session_manager.py
    │   ├── tsim_validator_service.py
    │   ├── tsim_port_parser_service.py
    │   ├── tsim_logger_service.py
    │   ├── tsim_timing_service.py
    │   ├── tsim_lock_manager_service.py
    │   ├── tsim_executor.py
    │   └── tsim_pdf_generator.py
    └── scripts/              # Refactored from src/scripts
        ├── __init__.py
        ├── tsim_reachability_tester.py
        ├── tsim_reachability_visualizer.py
        └── tsim_packet_analyzer.py
```

### After Deployment
```
/opt/tsim/                    # Production deployment
├── venv/                     # Virtual environment
├── raw_facts/                # Raw facts data
├── data/                     # Runtime data
├── logs/                     # Application logs
└── wsgi/                     # Deployed from repo's wsgi/
    └── [same structure as above]

/var/www/tsim/                # Legacy location (temporary)
└── htdocs/                   # Static files (will move later)
```

## Comparison: CGI vs mod_wsgi

| Aspect | Current (CGI) | Proposed (mod_wsgi) | Improvement |
|--------|--------------|---------------------|-------------|
| **Startup Time** | ~500ms per request | ~5ms after first | 100x faster |
| **Memory Usage** | New process each time | Shared processes | 75% reduction |
| **Database Connections** | Created per request | Connection pool | 10x faster |
| **Configuration Load** | Every request | Once at startup | Eliminated |
| **Concurrent Requests** | Limited by processes | Thread pool | 5x capacity |
| **Error Recovery** | Process dies | Process recycled | More stable |
| **Debugging** | Simple (one process) | Need logging | Trade-off |
| **Deployment** | Simple file copy | Needs restart | Trade-off |

## Performance Benchmarks (Expected)

```bash
# CGI Performance
ab -n 1000 -c 10 https://server/cgi-bin/main.py
# Time per request: ~800ms
# Requests per second: ~12

# mod_wsgi Performance  
ab -n 1000 -c 10 https://server/api/main
# Time per request: ~150ms
# Requests per second: ~65
```

## Implementation Timeline (Big-Bang Approach)

### Day 1: Complete Implementation
**Morning (4 hours)**
- [ ] Install mod_wsgi in venv
- [ ] Create WSGI application structure in new `wsgi/` folder
- [ ] **CRITICAL**: Implement complete module preloading in `app.wsgi`
  - [ ] Import ALL standard library modules that will be used
  - [ ] Import ALL third-party libraries
  - [ ] Import ALL handlers, services, and scripts
  - [ ] Pre-compile all regex patterns
  - [ ] Pre-compile all Python files to .pyc
- [ ] Implement ALL handlers at once in `wsgi/handlers/`:
  - [ ] Base handler (`tsim_base_handler.py`)
  - [ ] Login handler (`tsim_login_handler.py`)
  - [ ] Logout handler (`tsim_logout_handler.py`)
  - [ ] Main execution handler (`tsim_main_handler.py`)
  - [ ] PDF handler (`tsim_pdf_handler.py`)
  - [ ] Progress handler (`tsim_progress_handler.py`)
  - [ ] Progress Stream handler (`tsim_progress_stream_handler.py`)
  - [ ] Services Config handler (`tsim_services_config_handler.py`)
  - [ ] Test Config handler (`tsim_test_config_handler.py`)
  - [ ] Cleanup handler (`tsim_cleanup_handler.py`)
- [ ] Migrate all CGI libraries to `wsgi/services/`:
  - [ ] Auth service (`tsim_auth_service.py`)
  - [ ] Config service (`tsim_config_service.py`)
  - [ ] Session Manager (`tsim_session_manager.py`)
  - [ ] Validator service (`tsim_validator_service.py`)
  - [ ] Port Parser service (`tsim_port_parser_service.py`)
  - [ ] Logger service (`tsim_logger_service.py`)
  - [ ] Timing service (`tsim_timing_service.py`)
  - [ ] Lock Manager service (`tsim_lock_manager_service.py`)
  - [ ] Executor service (`tsim_executor.py`)
  - [ ] PDF Generator (`tsim_pdf_generator.py`)
- [ ] Refactor scripts from `src/scripts/` to `wsgi/scripts/`:
  - [ ] TsimReachabilityTester (`tsim_reachability_tester.py`)
  - [ ] TsimReachabilityVisualizer (`tsim_reachability_visualizer.py`)
  - [ ] TsimPacketAnalyzer (`tsim_packet_analyzer.py`)

**Afternoon (4 hours)**
- [ ] Update ALL frontend JavaScript to use `/api/*` endpoints
- [ ] Remove all `/cgi-bin/*` references
- [ ] Local testing with development server

### Day 2: Deployment
**Morning (3 hours)**
- [ ] Deploy WSGI code to server
- [ ] Replace Apache configuration completely
- [ ] Remove CGI configuration
- [ ] Restart Apache

**Afternoon (3 hours)**
- [ ] Run full test suite
- [ ] Performance testing
- [ ] Fix any issues
- [ ] Documentation updates

### Total Time: 2 Days (vs 4 weeks for progressive migration)

### Success Checklist
- [ ] **ALL modules preloaded in app.wsgi** (verify with logging)
- [ ] **NO dynamic imports after startup** (audit all code)
- [ ] All endpoints respond at `/api/*`
- [ ] No CGI processes running
- [ ] 5-10x performance improvement verified
- [ ] Sub-millisecond response times for cached operations
- [ ] All tests passing
- [ ] Memory usage acceptable (should be 100-200MB per worker)
- [ ] CGI directory can be archived/removed

## Advantages of mod_wsgi Approach

1. **True Persistent Python**: Virtual environment loaded once
2. **Complete Module Preloading**: ALL modules loaded at startup - zero import overhead
3. **Shared Resources**: Config, connections, modules cached in memory
4. **Better Concurrency**: Thread/process pools with pre-warmed workers
5. **Modern Architecture**: RESTful API design
6. **Easier Testing**: Unit test handlers directly
7. **Better Monitoring**: Built-in stats and health checks
8. **Predictable Performance**: No first-request penalty, everything pre-compiled

## Challenges and Solutions

| Challenge | Solution |
|-----------|----------|
| Session management | Use Redis or memcached for shared sessions |
| File uploads | Stream directly, don't buffer |
| Long-running tasks | Use Celery or background workers |
| Debugging | Enhanced logging, development mode |
| Deployment | Blue-green deployment with Apache configs |

## Decision Factors

### Choose CGI (Simple Shebang) if:
- Quick implementation needed
- Low traffic volume
- Simplicity is priority
- Limited Apache configuration access

### Choose mod_wsgi with Complete Preloading if:
- **Performance is absolutely critical**
- **Sub-millisecond response times required**
- High concurrent users
- Memory usage is not a concern
- Want modern architecture
- Have full server control
- Need predictable, consistent performance

## Recommendation

**Go with mod_wsgi with COMPLETE MODULE PRELOADING** for these reasons:

1. **10-100x performance improvement** over CGI (with preloading)
2. **Sub-millisecond response times** for cached operations
3. **Zero import overhead** - everything loaded at startup
4. **Industry standard** for Python web applications
5. **Better resource utilization** with persistent processes
6. **Predictable performance** - no first-request penalties
7. **Cleaner architecture** with proper request handlers
8. **Future-proof** - easier to add features like WebSockets, async operations

**Critical Success Factor**: The complete preloading strategy in `app.wsgi` is MANDATORY for achieving maximum performance. Memory usage (100-200MB per worker) is a worthwhile trade-off for the massive performance gains.

The additional complexity is worth it for a production system, and the big-bang deployment strategy allows for clean migration.