#!/usr/bin/env -S python3 -B -u
"""
Python wrapper for network_reachability_test.sh that handles locking
"""
import sys
import os
import subprocess
import signal

# Add lib directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../cgi-bin/lib'))

from lock_manager import NetworkLockManager
from logger import AuditLogger
from config import Config

def signal_handler(signum, frame):
    """Handle signals to ensure lock cleanup"""
    print("Received signal, cleaning up...", file=sys.stderr)
    sys.exit(1)

def main():
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Initialize logger and config
    logger = AuditLogger()
    config = Config()
    
    # Get the actual script path - check if we're running from installed location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Try installed location first
    actual_script = os.path.join(script_dir, "network_reachability_test.sh")
    if not os.path.exists(actual_script):
        # Fall back to development location
        actual_script = os.path.join(script_dir, "../../src/scripts/network_reachability_test.sh")
    
    # Log script path for debugging
    logger.log_info(f"Network reachability test wrapper: script_dir={script_dir}, actual_script={actual_script}, exists={os.path.exists(actual_script)}")
    
    if not os.path.exists(actual_script):
        print(f"Error: Script not found at {actual_script}", file=sys.stderr)
        logger.log_error("Script not found", f"network_reachability_test.sh not found at {actual_script}")
        sys.exit(1)
    
    try:
        # Acquire lock before running the script
        with NetworkLockManager(logger) as lock:
            # Get venv path from config
            venv_path = config.config.get('venv_path')
            if not venv_path:
                print("Error: Virtual environment path not configured", file=sys.stderr)
                logger.log_error("Configuration error", "venv_path not configured in config.json")
                sys.exit(1)
                
            venv_activate = os.path.join(venv_path, 'bin', 'activate')
            if not os.path.exists(venv_activate):
                print("Error: Virtual environment not found", file=sys.stderr)
                logger.log_error("Configuration error", f"venv activate script not found at {venv_activate}")
                sys.exit(1)
            
            # Get verbose level from config
            verbose_level = config.config.get('tsimsh_verbose_level', 0)
            verbose_flags = ' '.join(['-V'] * verbose_level) if verbose_level > 0 else ''
            
            # Build command to source venv and run script
            script_args = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
            
            # Log the arguments for debugging
            logger.log_info(f"Wrapper passing arguments to script: {script_args}")
            
            cmd = ['bash', '-c', f'source {venv_activate} && {actual_script} {verbose_flags} {script_args}']
            
            # Set up environment with TRACEROUTE_* variables
            env = os.environ.copy()
            # Ensure key environment variables are set
            traceroute_vars = {
                'TRACEROUTE_SIMULATOR_FACTS': os.environ.get('TRACEROUTE_SIMULATOR_FACTS', ''),
                'TRACEROUTE_SIMULATOR_RAW_FACTS': os.environ.get('TRACEROUTE_SIMULATOR_RAW_FACTS', ''),
                'TRACEROUTE_SIMULATOR_CONF': os.environ.get('TRACEROUTE_SIMULATOR_CONF', '')
            }
            
            # Only add non-empty values
            for key, value in traceroute_vars.items():
                if value:
                    env[key] = value
            
            # Execute the script with environment
            result = subprocess.run(cmd, env=env)
            
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