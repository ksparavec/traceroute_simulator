#!/usr/bin/env -S python3 -B -u
"""
Multi-Service Network Reachability Test Wrapper with Locking

This wrapper ensures only one network test runs at a time to prevent interference
between concurrent tests. It calls the multi-service test script which efficiently
tests multiple services with proper sequential testing for accurate firewall counters.
"""

import os
import sys
import json
import time
import argparse
import subprocess
import fcntl
import signal
from pathlib import Path
from typing import Optional, List, Tuple

# Constants
LOCK_FILE = '/dev/shm/tsim/network_test.lock'
LOCK_TIMEOUT = 300  # 5 minutes max wait for lock
LOCK_ACQUISITION_TIMEOUT = 5  # Max time to wait for each lock attempt
MAX_RETRIES = 60  # Number of times to retry getting the lock

def ensure_lock_dir():
    """Ensure the lock directory exists."""
    lock_dir = Path(LOCK_FILE).parent
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o775)
    
    # Try to set proper group
    try:
        import grp
        tsim_gid = grp.getgrnam('tsim-users').gr_gid
        os.chown(lock_dir, -1, tsim_gid)
    except:
        pass


def acquire_lock(timeout: int = LOCK_TIMEOUT) -> Optional[int]:
    """
    Acquire the network test lock with timeout.
    Returns the file descriptor if successful, None if timeout.
    """
    ensure_lock_dir()
    
    start_time = time.time()
    attempt = 0
    
    # Log to audit log that we're waiting for lock
    audit_log = Path("/var/www/traceroute-web/logs/audit.log")
    if audit_log.parent.exists():
        try:
            with open(audit_log, 'a') as f:
                entry = {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "run_id": os.environ.get('RUN_ID', 'unknown'),
                    "phase": "LOCK_WAIT",
                    "message": "Waiting to acquire network test lock for multi-service test"
                }
                f.write(json.dumps(entry) + "\n")
        except:
            pass
    
    while time.time() - start_time < timeout:
        attempt += 1
        
        try:
            # Try to open and lock the file
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_WRONLY, 0o664)
            
            # Try to acquire exclusive lock (non-blocking)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # Write our PID to the lock file
            os.write(fd, f"{os.getpid()}\n".encode())
            os.fsync(fd)
            
            # Log successful lock acquisition
            if audit_log.parent.exists():
                try:
                    with open(audit_log, 'a') as f:
                        entry = {
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "run_id": os.environ.get('RUN_ID', 'unknown'),
                            "phase": "LOCK_ACQUIRED",
                            "message": f"Network test lock acquired after {attempt} attempts"
                        }
                        f.write(json.dumps(entry) + "\n")
                except:
                    pass
            
            return fd
            
        except BlockingIOError:
            # Lock is held by another process
            if fd:
                os.close(fd)
            
            # Log waiting status periodically
            if attempt % 10 == 0:
                elapsed = time.time() - start_time
                print(f"Waiting for lock... ({elapsed:.1f}s elapsed, attempt {attempt})", file=sys.stderr)
            
            # Wait before retry
            time.sleep(LOCK_ACQUISITION_TIMEOUT)
            
        except Exception as e:
            print(f"Error acquiring lock: {e}", file=sys.stderr)
            if 'fd' in locals():
                try:
                    os.close(fd)
                except:
                    pass
            time.sleep(LOCK_ACQUISITION_TIMEOUT)
    
    # Timeout reached
    print(f"Failed to acquire lock after {timeout} seconds", file=sys.stderr)
    return None


def release_lock(fd: int):
    """Release the network test lock."""
    try:
        # Release the lock
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        
        # Try to remove the lock file
        try:
            os.unlink(LOCK_FILE)
        except:
            pass
        
        # Log lock release
        audit_log = Path("/var/www/traceroute-web/logs/audit.log")
        if audit_log.parent.exists():
            try:
                with open(audit_log, 'a') as f:
                    entry = {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "run_id": os.environ.get('RUN_ID', 'unknown'),
                        "phase": "LOCK_RELEASED",
                        "message": "Network test lock released"
                    }
                    f.write(json.dumps(entry) + "\n")
            except:
                pass
                
    except Exception as e:
        print(f"Error releasing lock: {e}", file=sys.stderr)


def run_multi_test(args: argparse.Namespace) -> int:
    """Run the multi-service network reachability test."""
    # Build command for the multi-service test script
    script_path = Path(__file__).parent / "network_reachability_test_multi.py"
    
    if not script_path.exists():
        print(f"Error: Multi-service test script not found at {script_path}", file=sys.stderr)
        return 1
    
    # Write services to a temporary file for the multi script
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(args.services, f)
        services_file = f.name
    
    try:
        cmd = [
            sys.executable, "-B", "-u",
            str(script_path),
            "-s", args.source_ip,
            "-d", args.dest_ip,
            "-p", services_file,  # Pass the file path
            "-o", args.output_dir
        ]
        
        if args.source_port:
            cmd.extend(["-S", str(args.source_port)])
        
        if args.trace_file:
            cmd.extend(["-f", args.trace_file])
        
        # Add verbose flags
        for _ in range(args.verbose):
            cmd.append("-v")
        
        # Set RUN_ID environment variable for logging
        env = os.environ.copy()
        if 'RUN_ID' not in env:
            import uuid
            env['RUN_ID'] = str(uuid.uuid4())
        
        # Execute the test
        try:
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            # Print output
            if result.stdout:
                print(result.stdout, end='')
            if result.stderr:
                print(result.stderr, file=sys.stderr, end='')
            
            return result.returncode
            
        except subprocess.TimeoutExpired:
            print("Error: Test execution timed out", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"Error running test: {e}", file=sys.stderr)
            return 1
    finally:
        # Clean up temporary services file
        try:
            os.unlink(services_file)
        except:
            pass


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Multi-Service Network Reachability Test Wrapper with Locking"
    )
    
    parser.add_argument('-s', '--source-ip', required=True,
                        help='Source IP address')
    parser.add_argument('-S', '--source-port', type=int,
                        help='Source port (optional)')
    parser.add_argument('-d', '--dest-ip', required=True,
                        help='Destination IP address')
    parser.add_argument('-p', '--services', required=True,
                        help='Path to JSON file containing array of [port, protocol] pairs')
    parser.add_argument('-o', '--output-dir', required=True,
                        help='Output directory for result files')
    parser.add_argument('-f', '--trace-file',
                        help='Use existing trace file')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help='Increase verbosity')
    parser.add_argument('--no-lock', action='store_true',
                        help='Skip locking (for testing only)')
    
    args = parser.parse_args()
    
    # Read services from JSON file
    try:
        with open(args.services, 'r') as f:
            services = json.load(f)
    except FileNotFoundError:
        print(f"Error: Services file not found: {args.services}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in services file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Validate services format
    if not isinstance(services, list):
        print("Error: Services must be a JSON array", file=sys.stderr)
        sys.exit(1)
    
    for item in services:
        if not isinstance(item, list) or len(item) != 2:
            print(f"Error: Invalid service format: {item}", file=sys.stderr)
            print("Expected format: [[port1, 'protocol1'], [port2, 'protocol2'], ...]", file=sys.stderr)
            sys.exit(1)
    
    # Replace args.services with the loaded data for the rest of the script
    args.services = services
    
    # Handle signals for cleanup
    lock_fd = None
    
    def signal_handler(signum, frame):
        if lock_fd is not None:
            release_lock(lock_fd)
        sys.exit(1)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Acquire lock unless --no-lock specified
    if not args.no_lock:
        lock_fd = acquire_lock()
        if lock_fd is None:
            print("Error: Failed to acquire network test lock", file=sys.stderr)
            sys.exit(1)
    
    try:
        # Run the test
        return_code = run_multi_test(args)
        
    finally:
        # Release lock
        if lock_fd is not None:
            release_lock(lock_fd)
    
    return return_code


if __name__ == "__main__":
    sys.exit(main())