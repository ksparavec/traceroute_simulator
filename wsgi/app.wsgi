#!/usr/bin/env python3
"""
TSIM WSGI Application Entry Point
PERFORMANCE CRITICAL: ALL modules are preloaded at startup for maximum performance
Memory usage is not a concern - we want everything in memory for speed
"""

import sys
import os
import logging

# Prevent Python from writing .pyc files (avoid __pycache__ in install dirs)
try:
    sys.dont_write_bytecode = True
except Exception:
    pass

# Load configuration first to get all paths
import json
from pathlib import Path

# Resolve configuration path strictly from environment or default install path
config_path = Path(os.environ.get('TSIM_CONFIG_FILE', '/opt/tsim/wsgi/conf/config.json'))
if config_path.exists():
    with open(config_path, 'r') as f:
        config = json.load(f)
    # Use configured web_root or default to standard install path
    web_root = config.get('web_root', '/opt/tsim/wsgi')
    venv_path = config.get('venv_path', '/opt/tsim/venv')
    
    # Set environment variables from config
    os.environ['PYTHONPYCACHEPREFIX'] = config.get('cache_dir', '/dev/shm/tsim/pycache')
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['MPLCONFIGDIR'] = config.get('matplotlib_cache_dir', '/dev/shm/tsim/matplotlib')
    os.environ['TSIM_WEB_ROOT'] = web_root
    os.environ['TRACEROUTE_SIMULATOR_RAW_FACTS'] = config.get('traceroute_simulator_raw_facts', '/opt/tsim/raw_facts')
    os.environ['TRACEROUTE_SIMULATOR_FACTS'] = config.get('traceroute_simulator_facts', '/opt/tsim/facts')
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    
    # Add web_root to PYTHONPATH so all child processes can import from it
    current_pythonpath = os.environ.get('PYTHONPATH', '')
    if current_pythonpath:
        os.environ['PYTHONPATH'] = f"{web_root}:{current_pythonpath}"
    else:
        os.environ['PYTHONPATH'] = web_root
    
    # Add venv bin directory to PATH so tsimsh can be found
    venv_bin = os.path.join(venv_path, 'bin')
    current_path = os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin')
    os.environ['PATH'] = f"{venv_bin}:{current_path}"
else:
    # Fallback if config doesn't exist
    print(f"Warning: Config file not found at {config_path}, using defaults", file=sys.stderr)
    # Try to infer local dev path relative to this file
    try:
        web_root = str(Path(__file__).resolve().parent)
    except Exception:
        web_root = '/opt/tsim/wsgi'
    venv_path = '/opt/tsim/venv'
    os.environ['PYTHONPYCACHEPREFIX'] = '/dev/shm/tsim/pycache'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['MPLCONFIGDIR'] = '/dev/shm/tsim/matplotlib'
    os.environ['TSIM_WEB_ROOT'] = web_root
    os.environ['TRACEROUTE_SIMULATOR_RAW_FACTS'] = '/opt/tsim/raw_facts'
    os.environ['TRACEROUTE_SIMULATOR_FACTS'] = '/opt/tsim/facts'
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    
    # Add web_root to PYTHONPATH so all child processes can import from it
    current_pythonpath = os.environ.get('PYTHONPATH', '')
    if current_pythonpath:
        os.environ['PYTHONPATH'] = f"{web_root}:{current_pythonpath}"
    else:
        os.environ['PYTHONPATH'] = web_root
    
    # Add venv bin directory to PATH
    venv_bin = os.path.join(venv_path, 'bin')
    current_path = os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin')
    os.environ['PATH'] = f"{venv_bin}:{current_path}"

# Print diagnostics only in debug mode
_debug_enabled = False
try:
    _debug_enabled = (str(config.get('log_level', '')).upper() == 'DEBUG') or bool(config.get('debug', False))
except Exception:
    _debug_enabled = False

if _debug_enabled:
    print(f"=== TSIM WSGI Python Environment ===", file=sys.stderr)
    print(f"Python Version: {sys.version}", file=sys.stderr)
    print(f"Python Executable: {sys.executable}", file=sys.stderr)
    print(f"Python Prefix: {sys.prefix}", file=sys.stderr)
    print(f"Python Path: {':'.join(sys.path)}", file=sys.stderr)
    print(f"Working Directory: {os.getcwd()}", file=sys.stderr)
    print(f"Process UID: {os.getuid()}, GID: {os.getgid()}", file=sys.stderr)
    print(f"Config File: {config_path}", file=sys.stderr)
    print(f"Web Root: {web_root}", file=sys.stderr)
    print(f"Environment Variables (from config):", file=sys.stderr)
    print(f"  PYTHONPYCACHEPREFIX: {os.environ.get('PYTHONPYCACHEPREFIX')}", file=sys.stderr)
    print(f"  MPLCONFIGDIR: {os.environ.get('MPLCONFIGDIR')}", file=sys.stderr)
    print(f"  TRACEROUTE_SIMULATOR_RAW_FACTS: {os.environ.get('TRACEROUTE_SIMULATOR_RAW_FACTS')}", file=sys.stderr)
    print(f"  PATH: {os.environ.get('PATH', 'NOT SET')}", file=sys.stderr)
    print(f"=====================================", file=sys.stderr)

# Ensure cache directories exist
Path(os.environ['MPLCONFIGDIR']).mkdir(parents=True, exist_ok=True)
Path(os.environ['PYTHONPYCACHEPREFIX']).mkdir(parents=True, exist_ok=True)

# Remove /tmp from path if present (security risk)
while '/tmp' in sys.path:
    sys.path.remove('/tmp')

# Add WSGI paths needed for imports
sys.path.insert(0, os.path.join(web_root, 'scripts'))
sys.path.insert(0, web_root)

if _debug_enabled:
    print(f"Adjusted Python Path: {':'.join(sys.path)}", file=sys.stderr)

# Configure logging early
# Note: mod_wsgi logs all stderr output as wsgi:error regardless of actual log level
# This is normal behavior and cannot be changed without modifying Apache LogLevel
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('tsim.startup')
logger.info(f"Starting TSIM WSGI application from {web_root}")

# ============================================================================
# PRELOAD ALL MODULES FOR MAXIMUM PERFORMANCE
# Memory usage is not a concern - we want everything in memory
# This ensures zero import overhead during request handling
# ============================================================================

logger.info("Beginning module preloading...")

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
from typing import Dict, List, Optional, Tuple, Any

logger.info("Standard library modules loaded")

# Preload heavy third-party modules
try:
    import matplotlib
    import matplotlib.pyplot as plt
    # Set non-interactive backend
    matplotlib.use('Agg')
    os.environ['MPLBACKEND'] = 'Agg'
    logger.info("matplotlib loaded with Agg backend")
except ImportError:
    logger.warning("matplotlib not available")

try:
    import ujson  # Ultra-fast JSON
    logger.info("ujson loaded")
except ImportError:
    logger.warning("ujson not available - using standard json")
    ujson = json  # Fallback to standard json

try:
    import psutil
    logger.info("psutil loaded")
except ImportError:
    logger.warning("psutil not available")

try:
    import networkx
    logger.info("networkx loaded")
except ImportError:
    logger.warning("networkx not available")

try:
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    logger.info("reportlab loaded")
except ImportError:
    logger.warning("reportlab not available")

try:
    import PyPDF2
    logger.info("PyPDF2 loaded")
except ImportError:
    logger.warning("PyPDF2 not available")

try:
    import pam
    logger.info("pam loaded")
except ImportError:
    logger.warning("pam not available - PAM authentication disabled")

# Pre-compile all regex patterns that will be used
logger.info("Pre-compiling regex patterns...")
IP_PATTERN = re.compile(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$')
PORT_PATTERN = re.compile(r'^([0-9]+)(?:/([a-z]+))?$')
SESSION_ID_PATTERN = re.compile(r'^[a-f0-9]{32,}$')
UUID_PATTERN = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')

# Preload ALL services (import but don't instantiate yet)
logger.info("Loading service modules...")
from services.tsim_auth_service import TsimAuthService
from services.tsim_config_service import TsimConfigService
from services.tsim_session_manager import TsimSessionManager
from services.tsim_validator_service import TsimValidatorService
from services.tsim_port_parser_service import TsimPortParserService
from services.tsim_logger_service import TsimLoggerService
from services.tsim_timing_service import TsimTimingService
from services.tsim_lock_manager_service import TsimLockManagerService
from services.tsim_executor import TsimExecutor
from services.tsim_progress_tracker import TsimProgressTracker
try:
    from services.tsim_hybrid_executor import TsimHybridExecutor
    logger.info("Hybrid executor loaded")
except ImportError as e:
    logger.warning(f"Hybrid executor not available: {e}")
logger.info("All service modules loaded")

# Preload ALL handlers (import but don't instantiate yet)
logger.info("Loading handler modules...")
from handlers.tsim_base_handler import TsimBaseHandler
from handlers.tsim_login_handler import TsimLoginHandler
from handlers.tsim_logout_handler import TsimLogoutHandler
from handlers.tsim_main_handler import TsimMainHandler
from handlers.tsim_pdf_handler import TsimPDFHandler
from handlers.tsim_progress_handler import TsimProgressHandler
from handlers.tsim_progress_stream_handler import TsimProgressStreamHandler
from handlers.tsim_services_config_handler import TsimServicesConfigHandler
from handlers.tsim_cleanup_handler import TsimCleanupHandler
logger.info("All handler modules loaded")

# Script modules are loaded on-demand, not preloaded
logger.info("Script modules will be loaded on demand")

# Import the main application AFTER all modules are loaded
logger.info("Loading main WSGI application...")
from tsim_app import TsimWSGIApp

# Create the application instance
application = TsimWSGIApp()

# Wrap with performance monitoring if available
try:
    from services.tsim_performance_middleware import TsimPerformanceMiddleware
    application = TsimPerformanceMiddleware(application)
    logger.info("Performance middleware enabled")
except ImportError:
    logger.info("Performance middleware not available")

# Log detailed startup information
try:
    import psutil
    process = psutil.Process(os.getpid())
    memory_mb = process.memory_info().rss / 1024 / 1024
    logger.info(f"Application startup complete - Memory usage: {memory_mb:.1f} MB")
    
    # Log loaded modules summary
    loaded_modules = [name for name in sys.modules.keys() if not name.startswith('_')]
    logger.info(f"Total modules loaded: {len(sys.modules)}")
    logger.info(f"TSIM modules: {len([m for m in loaded_modules if 'tsim' in m.lower()])}")
    logger.info(f"Key libraries present: matplotlib={('matplotlib' in sys.modules)}, " +
                f"reportlab={('reportlab' in sys.modules)}, " +
                f"PyPDF2={('PyPDF2' in sys.modules)}, " +
                f"networkx={('networkx' in sys.modules)}")
except:
    logger.info("Application startup complete")

# Create wrapper to handle environment variables from Apache SetEnv
_application = application

def application(environ, start_response):
    """WSGI application wrapper that transfers Apache SetEnv variables to os.environ"""
    # Transfer config file location from Apache SetEnv to os.environ (one-time only)
    if 'TSIM_CONFIG_FILE' in environ and 'TSIM_CONFIG_FILE_SET' not in os.environ:
        os.environ['TSIM_CONFIG_FILE'] = environ['TSIM_CONFIG_FILE']
        os.environ['TSIM_CONFIG_FILE_SET'] = '1'  # Flag to prevent repeated setting
        logger.info(f"Config file path set from Apache: {os.environ['TSIM_CONFIG_FILE']}")
    
    # Call the actual application
    return _application(environ, start_response)
