#!/usr/bin/env -S python3 -B -u
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

# Set umask for proper file and directory permissions
# umask 0007: files=0660, dirs=0770 (with setgid parent → 2770)
# Note: We fix dir permissions to 2775 in startup code below
# This ensures all files created by WSGI have proper group permissions (0660)
os.umask(0o0007)

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
    
    # Set environment variables that tsimsh needs
    os.environ['TRACEROUTE_SIMULATOR_FACTS'] = config.get('traceroute_simulator_facts', '/opt/tsim/tsim_facts')
    os.environ['TRACEROUTE_SIMULATOR_RAW_FACTS'] = config.get('traceroute_simulator_raw_facts', '/opt/tsim/raw_facts')
    
    # Validate facts directories (critical for system operation)
    facts_dir = Path(os.environ['TRACEROUTE_SIMULATOR_FACTS'])
    raw_facts_dir = Path(os.environ['TRACEROUTE_SIMULATOR_RAW_FACTS'])
    facts_valid = True
    facts_errors = []
    
    # Check JSON facts directory
    if not facts_dir.exists():
        facts_errors.append(f"Facts directory does not exist: {facts_dir}")
        facts_valid = False
    elif not facts_dir.is_dir():
        facts_errors.append(f"Facts path is not a directory: {facts_dir}")
        facts_valid = False
    elif not any(facts_dir.glob('*.json')):
        facts_errors.append(f"No JSON fact files found in: {facts_dir}")
        facts_valid = False
    
    # Check raw facts directory
    if not raw_facts_dir.exists():
        facts_errors.append(f"Raw facts directory does not exist: {raw_facts_dir}")
        facts_valid = False
    elif not raw_facts_dir.is_dir():
        facts_errors.append(f"Raw facts path is not a directory: {raw_facts_dir}")
        facts_valid = False
    elif not any(raw_facts_dir.iterdir()):
        facts_errors.append(f"No files found in raw facts directory: {raw_facts_dir}")
        facts_valid = False
    
    if not facts_valid:
        # Log all errors
        for error in facts_errors:
            print(f"CRITICAL: {error}", file=sys.stderr)
        print("CRITICAL: FACTS VALIDATION FAILED - System cannot perform network analysis", file=sys.stderr)
        # Set a flag that services can check
        os.environ['TSIM_FACTS_INVALID'] = '1'
    
    # Set only system environment variables (not config values)
    os.environ['PYTHONPYCACHEPREFIX'] = config.get('cache_dir', '/dev/shm/tsim/pycache')
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['MPLCONFIGDIR'] = config.get('matplotlib_cache_dir', '/dev/shm/tsim/matplotlib')
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
    # Set environment variables that tsimsh needs
    os.environ['TRACEROUTE_SIMULATOR_FACTS'] = '/opt/tsim/tsim_facts'
    os.environ['TRACEROUTE_SIMULATOR_RAW_FACTS'] = '/opt/tsim/raw_facts'
    
    # Validate facts directories (same as above)
    facts_dir = Path(os.environ['TRACEROUTE_SIMULATOR_FACTS'])
    raw_facts_dir = Path(os.environ['TRACEROUTE_SIMULATOR_RAW_FACTS'])
    facts_valid = True
    facts_errors = []
    
    if not facts_dir.exists():
        facts_errors.append(f"Facts directory does not exist: {facts_dir}")
        facts_valid = False
    elif not facts_dir.is_dir():
        facts_errors.append(f"Facts path is not a directory: {facts_dir}")
        facts_valid = False
    elif not any(facts_dir.glob('*.json')):
        facts_errors.append(f"No JSON fact files found in: {facts_dir}")
        facts_valid = False
    
    if not raw_facts_dir.exists():
        facts_errors.append(f"Raw facts directory does not exist: {raw_facts_dir}")
        facts_valid = False
    elif not raw_facts_dir.is_dir():
        facts_errors.append(f"Raw facts path is not a directory: {raw_facts_dir}")
        facts_valid = False
    elif not any(raw_facts_dir.iterdir()):
        facts_errors.append(f"No files found in raw facts directory: {raw_facts_dir}")
        facts_valid = False
    
    if not facts_valid:
        for error in facts_errors:
            print(f"CRITICAL: {error}", file=sys.stderr)
        print("CRITICAL: FACTS VALIDATION FAILED - System cannot perform network analysis", file=sys.stderr)
        os.environ['TSIM_FACTS_INVALID'] = '1'
    
    os.environ['PYTHONPYCACHEPREFIX'] = '/dev/shm/tsim/pycache'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['MPLCONFIGDIR'] = '/dev/shm/tsim/matplotlib'
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

# CRITICAL: Set parent data directory permissions BEFORE any subdirs are created
import grp
try:
    if 'config' in globals() and isinstance(config, dict):
        data_dir = Path(config.get('data_dir', '/dev/shm/tsim'))
        # Create parent if it doesn't exist
        data_dir.mkdir(parents=True, exist_ok=True)

        # Get unix_group from traceroute_simulator.yaml
        unix_group = 'tsim-users'  # default
        try:
            from tsim.core.config_loader import load_traceroute_config
            yaml_config = load_traceroute_config()
            unix_group = yaml_config.get('system', {}).get('unix_group', 'tsim-users')
        except Exception:
            pass

        try:
            gid = grp.getgrnam(unix_group).gr_gid
        except KeyError:
            gid = None  # Group doesn't exist

        # Set setgid bit (2775) and group ownership on parent
        data_dir.chmod(0o2775)
        if gid is not None:
            os.chown(data_dir, -1, gid)

        # Fix existing subdirectories and files that have wrong permissions
        # This is needed after reboot when dirs/files already exist
        for item in data_dir.iterdir():
            # Skip sessions directory - it has intentionally restrictive permissions
            if item.name == 'sessions':
                continue

            try:
                if item.is_dir():
                    # Always set proper permissions on subdirectory (2775)
                    # This is needed because umask 0007 creates dirs as 0770
                    item.chmod(0o2775)
                    # Set group ownership
                    if gid is not None:
                        os.chown(item, -1, gid)

                    # Fix files inside subdirectory
                    for subitem in item.iterdir():
                        try:
                            if subitem.is_file():
                                subitem_mode = subitem.stat().st_mode
                                if (subitem_mode & 0o7777) != 0o660:
                                    subitem.chmod(0o660)
                                if gid is not None:
                                    os.chown(subitem, -1, gid)
                        except Exception:
                            pass

                elif item.is_file():
                    # Fix file permissions in root data dir
                    current_mode = item.stat().st_mode
                    if (current_mode & 0o7777) != 0o660:
                        item.chmod(0o660)
                    if gid is not None:
                        os.chown(item, -1, gid)
            except Exception:
                pass  # Skip if we can't fix this one

except Exception as e:
    print(f"Warning: Could not set permissions on data directory: {e}", file=sys.stderr)

# Ensure cache directories exist (will inherit group from parent now)
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
# Respect log level from config.json if present
_level_map = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}
try:
    _cfg_level = None
    if 'config' in globals() and isinstance(config, dict):
        _cfg_level = str(config.get('log_level', 'INFO')).upper()
    _base_level = _level_map.get(_cfg_level, logging.INFO)
except Exception:
    _base_level = logging.INFO

logging.basicConfig(
    level=_base_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('tsim.startup')
logger.info(f"Starting TSIM WSGI application from {web_root}")

# Log facts validation status
if os.environ.get('TSIM_FACTS_INVALID') == '1':
    logger.critical("FACTS VALIDATION FAILED - System cannot perform network analysis")
    logger.critical("Please contact your system administrator to ensure fact files are properly installed")
    logger.critical(f"Expected JSON facts in: {os.environ.get('TRACEROUTE_SIMULATOR_FACTS')}")
    logger.critical(f"Expected raw facts in: {os.environ.get('TRACEROUTE_SIMULATOR_RAW_FACTS')}")
else:
    logger.info(f"Facts validated: JSON={os.environ.get('TRACEROUTE_SIMULATOR_FACTS')}, RAW={os.environ.get('TRACEROUTE_SIMULATOR_RAW_FACTS')}")

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
from services.tsim_queue_service import TsimQueueService
from services.tsim_scheduler_service import TsimSchedulerService
from services.tsim_reconciler_service import TsimReconcilerService
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
from handlers.tsim_queue_admin_handler import TsimQueueAdminHandler
from handlers.tsim_job_details_handler import TsimJobDetailsHandler
from handlers.tsim_admin_queue_stream_handler import TsimAdminQueueStreamHandler
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

# Initialize DSCP registry to trigger stale allocation cleanup
try:
    from services.tsim_dscp_registry import TsimDscpRegistry
    from services.tsim_config_service import TsimConfigService
    _config_service = TsimConfigService()
    _dscp_registry = TsimDscpRegistry(_config_service)
    logger.info("DSCP registry initialized (stale allocations cleaned on startup)")
except Exception as e:
    logger.warning(f"Could not initialize DSCP registry for cleanup: {e}")

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

# Clean up stale WSGI-created resources from previous daemon processes
logger.info("Checking for stale WSGI-created resources...")
try:
    import subprocess
    from pathlib import Path

    def _cleanup_wsgi_resources():
        """Remove hosts and services created by previous WSGI processes"""
        removed_hosts = 0
        removed_services = 0
        hosts_to_unregister = []

        try:
            # Read host registry
            host_registry_file = Path(config.get('data_dir', '/dev/shm/tsim')) / 'host_registry.json'
            if host_registry_file.exists():
                with open(host_registry_file, 'r') as f:
                    hosts = json.load(f)

                # Find WSGI-created hosts
                for host_name, host_info in hosts.items():
                    created_by = host_info.get('created_by', '')
                    if created_by.startswith('wsgi:'):
                        # Remove physical host
                        try:
                            result = subprocess.run(
                                ['tsimsh', '-q'],
                                input=f'host remove --name {host_name} --force\n',
                                capture_output=True,
                                text=True,
                                timeout=10
                            )
                            if result.returncode == 0:
                                removed_hosts += 1
                                hosts_to_unregister.append(host_name)
                                logger.info(f"Removed stale WSGI host: {host_name} ({created_by})")
                        except Exception as e:
                            logger.warning(f"Failed to remove host {host_name}: {e}")

                # Unregister successfully removed hosts from registry
                if hosts_to_unregister:
                    try:
                        from tsim.core.registry_manager import TsimRegistryManager
                        registry_mgr = TsimRegistryManager(config)
                        for host_name in hosts_to_unregister:
                            try:
                                registry_mgr.unregister_host(host_name)
                                logger.debug(f"Unregistered {host_name} from registry")
                            except Exception as e:
                                logger.warning(f"Failed to unregister {host_name} from registry: {e}")
                    except Exception as e:
                        logger.warning(f"Could not initialize registry manager: {e}")

        except Exception as e:
            logger.warning(f"Error reading host registry: {e}")

        try:
            # Read service registry
            service_registry_file = Path(config.get('data_dir', '/dev/shm/tsim')) / 'services_registry.json'
            if service_registry_file.exists():
                with open(service_registry_file, 'r') as f:
                    services = json.load(f)

                # Find WSGI-created services
                for service_key, service_info in services.items():
                    created_by = service_info.get('created_by', '')
                    if created_by.startswith('wsgi:'):
                        namespace = service_info.get('namespace')
                        name = service_info.get('name')
                        if namespace and name:
                            # Remove this service
                            try:
                                result = subprocess.run(
                                    ['tsimsh', '-q'],
                                    input=f'service stop --namespace {namespace} --name {name}\n',
                                    capture_output=True,
                                    text=True,
                                    timeout=10
                                )
                                if result.returncode == 0:
                                    removed_services += 1
                                    logger.info(f"Removed stale WSGI service: {namespace}:{name} ({created_by})")
                            except Exception as e:
                                logger.warning(f"Failed to remove service {namespace}:{name}: {e}")

        except Exception as e:
            logger.warning(f"Error reading service registry: {e}")

        if removed_hosts > 0 or removed_services > 0:
            logger.info(f"Cleanup complete: removed {removed_hosts} hosts, {removed_services} services")
        else:
            logger.info("No stale WSGI resources found")

    _cleanup_wsgi_resources()

except Exception as e:
    logger.warning(f"Could not perform WSGI resource cleanup: {e}")

# Create wrapper to handle environment variables from Apache SetEnv
_application = application

def application(environ, start_response):
    """WSGI application wrapper that transfers Apache SetEnv variables to os.environ"""
    # Transfer environment variables from Apache SetEnv to os.environ (one-time only)
    if 'TSIM_ENV_SET' not in os.environ:
        for key in ['TSIM_CONFIG_FILE', 'TSIM_WEB_ROOT', 'TSIM_HTDOCS', 'TSIM_VENV',
                    'TSIM_DATA_DIR', 'TSIM_LOG_DIR']:
            if key in environ:
                os.environ[key] = environ[key]
                logger.debug(f"{key} set from Apache: {environ[key]}")
        os.environ['TSIM_ENV_SET'] = '1'  # Flag to prevent repeated setting

    # Set TSIM_WSGI_USERNAME for creator tag tracking
    # This allows host/service creation to tag resources with logged-in user
    if 'HTTP_COOKIE' in environ:
        try:
            from services.tsim_session_manager import TsimSessionManager
            from services.tsim_config_service import TsimConfigService

            cookies = environ['HTTP_COOKIE']
            session_id = None

            # Parse cookies to find session_id
            for cookie in cookies.split(';'):
                cookie = cookie.strip()
                if cookie.startswith('session_id='):
                    session_id = cookie.split('=', 1)[1]
                    break

            if session_id:
                _cfg_svc = TsimConfigService()
                _session_mgr = TsimSessionManager(_cfg_svc)
                session_data = _session_mgr.get_session(session_id)

                if session_data:
                    username = session_data.get('username')
                    if username:
                        os.environ['TSIM_WSGI_USERNAME'] = username
        except Exception:
            pass  # Silently fail - not critical

    # Call the actual application
    return _application(environ, start_response)
