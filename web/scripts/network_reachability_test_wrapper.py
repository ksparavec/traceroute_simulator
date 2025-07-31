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
    actual_script = os.path.join(script_dir, "../../src/scripts/network_reachability_test.sh")
    
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