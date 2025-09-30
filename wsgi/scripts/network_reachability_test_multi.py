#!/usr/bin/env -S python3 -B -u
"""
Multi-Service Network Reachability Testing Script
Tests multiple network services efficiently with proper sequential testing for accurate firewall counters.

This script follows the exact logic of the shell script network_reachability_test.sh but supports
testing multiple services in one run.

Key features:
- Sets up hosts on ALL routers (1-based indexing like shell script)
- Starts ALL services at once in parallel on destination
- Tests services SEQUENTIALLY to avoid firewall counter conflicts
- Checks firewall counters before/after each individual service test
- Generates individual JSON output files for each service (for PDF generation)
- Cleans up all resources at the end
"""

import os
import sys
import json
import time
import argparse
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

# Constants
VERSION = "2.0.0"
SCRIPT_START_TIME = time.time()
LAST_CHECKPOINT_TIME = SCRIPT_START_TIME

def log_timing(checkpoint: str, details: str = "") -> None:
    """Log timing information for performance tracking."""
    global LAST_CHECKPOINT_TIME
    
    current_time = time.time()
    duration = current_time - LAST_CHECKPOINT_TIME
    LAST_CHECKPOINT_TIME = current_time
    
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    session_id = os.environ.get('RUN_ID', str(uuid.uuid4()))
    
    # Log to timings.log - use TSIM_LOG_DIR environment variable
    log_dir = Path(os.environ.get('TSIM_LOG_DIR', '/var/log/tsim'))
    if log_dir.exists():
        timings_file = log_dir / "timings.log"
        audit_file = log_dir / "audit.log"
        
        timing_entry = f"[{timestamp}] [{session_id}] {duration:7.2f}s | MULTI_REACHABILITY_{checkpoint}"
        if details:
            timing_entry += f" | {details}"
        
        try:
            with open(timings_file, 'a') as f:
                f.write(timing_entry + "\n")
        except:
            pass
        
        # Also log to audit.log for progress tracking
        audit_entry = {
            "timestamp": timestamp,
            "run_id": session_id,
            "phase": checkpoint,
            "message": details
        }
        try:
            with open(audit_file, 'a') as f:
                f.write(json.dumps(audit_entry) + "\n")
        except:
            pass


def tsimsh_exec(command: str, capture_output: bool = False, verbose: int = 0) -> Optional[str]:
    """Execute tsimsh command."""
    # Always use tsimsh from PATH (properly installed version)
    tsimsh_path = "tsimsh"
    
    cmd = [tsimsh_path, "-q"]
    
    try:
        result = subprocess.run(
            cmd,
            input=command,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Debug output for verbose mode
        if verbose > 0:
            print(f"[DEBUG] tsimsh command: {command}", file=sys.stderr)
            if verbose > 1:
                print(f"[DEBUG] tsimsh stdout: {result.stdout[:500]}", file=sys.stderr)
                print(f"[DEBUG] tsimsh stderr: {result.stderr[:200]}", file=sys.stderr)
            print(f"[DEBUG] tsimsh return code: {result.returncode}", file=sys.stderr)
        
        if capture_output:
            return result.stdout
        return None if result.returncode == 0 else result.stderr
    except Exception as e:
        print(f"Error executing tsimsh command: {e}", file=sys.stderr)
        return None




class MultiServiceTester:
    """Main class for multi-service testing."""
    
    def __init__(self, source_ip: str, source_port: Optional[int], dest_ip: str, 
                 services: List[Tuple[int, str]], output_dir: str, 
                 trace_file: Optional[str] = None, verbose: int = 0):
        self.source_ip = source_ip
        self.source_port = source_port
        self.dest_ip = dest_ip
        self.services = services  # List of (port, protocol) tuples
        self.output_dir = Path(output_dir)
        self.trace_file = trace_file
        self.verbose = verbose
        
        # Create output directory with proper permissions
        self.output_dir.mkdir(parents=True, exist_ok=True, mode=0o775)
        
        # Track created resources for cleanup
        self.created_hosts = []
        self.started_services = []  # List of (ip, port, protocol) tuples
        
        # Track result files for each service (for PDF generation)
        self.service_result_files = []
        
        # Progress callback for WSGI integration
        self.progress_callback = None
        
    def _log_progress(self, phase: str, message: str = ""):
        """Log progress to both file and callback"""
        log_timing(phase, message)
        if self.progress_callback:
            self.progress_callback(phase, message)
    
    def cleanup(self) -> None:
        """Clean up all created resources (matches shell script cleanup)."""
        self._log_progress("cleanup_start", "Starting cleanup")
        
        # Fast global cleanup: wipe all services, then all hosts
        try:
            tsimsh_exec("service clean --force", verbose=self.verbose)
        except Exception:
            pass
        try:
            tsimsh_exec("host clean --force", verbose=self.verbose)
        except Exception:
            pass
        
        # Clear internal tracking (not strictly necessary with global clean)
        self.started_services = []
        self.created_hosts = []
        
        self._log_progress("cleanup_complete", "Cleanup completed")
    
    def phase1_path_discovery(self) -> Dict[str, Any]:
        """Phase 1: Path Discovery - matches shell script phase1_path_discovery."""
        self._log_progress("PHASE1_start", f"Path discovery from {self.source_ip} to {self.dest_ip}")
        
        if self.trace_file and Path(self.trace_file).exists():
            # Use existing trace file (READ ONLY - NEVER modify it)
            with open(self.trace_file, 'r') as f:
                trace_data = json.load(f)
            self._log_progress("PHASE1_trace_load", f"Loaded trace from file: {self.trace_file}")
        else:
            # Run live trace
            trace_output = tsimsh_exec(
                f"trace --source {self.source_ip} --destination {self.dest_ip} --json",
                capture_output=True,
                verbose=self.verbose
            )
            
            if not trace_output:
                raise Exception("Failed to run trace")
            
            trace_data = json.loads(trace_output)
            self._log_progress("PHASE1_trace_complete", "Live trace completed")
        
        return trace_data
    
    def phase2_setup_environment(self, routers: List[str]) -> None:
        """Phase 2: Setup Environment - matches shell script phase2_setup_environment."""
        self._log_progress("PHASE2_start", "Setting up simulation environment")
        
        # Check existing hosts (like shell script does)
        self._log_progress("PHASE2_host_list", "Query existing hosts")
        host_list_output = tsimsh_exec("host list --json", capture_output=True)
        
        existing_hosts = {}
        if host_list_output:
            try:
                data = json.loads(host_list_output)
                existing_hosts = data.get('hosts', {})
            except:
                pass
        
        # Check which hosts already exist for each router
        existing_source_hosts = []
        existing_dest_hosts = []
        
        for host_name, host_info in existing_hosts.items():
            primary_ip = host_info.get('primary_ip', '')
            if '/' in primary_ip:
                ip_only = primary_ip.split('/')[0]
                connected_to = host_info.get('connected_to', '')
                
                if ip_only == self.source_ip:
                    existing_source_hosts.append(f"{host_name}:{connected_to}")
                elif ip_only == self.dest_ip:
                    existing_dest_hosts.append(f"{host_name}:{connected_to}")
        
        # Add hosts to ALL routers (using 1-based indexing like shell script)
        num_routers = len(routers)
        self._log_progress("PHASE2_host_setup_start", f"Adding hosts to {num_routers} routers")
        
        hosts_added = 0
        router_index = 1  # Start at 1 like shell script
        
        for router in routers:
            # Check if source host already exists for THIS router
            source_exists_for_router = any(
                existing.endswith(f":{router}") for existing in existing_source_hosts
            )
            
            # Add source host to this router if needed
            src_host_name = f"source-{router_index}"
            if not source_exists_for_router:
                self._log_progress(f"host_add_source_{router_index}", f"Adding source host {src_host_name} to router {router}")
                result = tsimsh_exec(
                    f"host add --name {src_host_name} --primary-ip {self.source_ip}/24 --connect-to {router} --no-delay",
                    verbose=self.verbose
                )
                if result is None:  # Success
                    self.created_hosts.append(src_host_name)
                    hosts_added += 1
                    if self.verbose > 0:
                        print(f"[DEBUG] Added {src_host_name} to {router}", file=sys.stderr)
                else:
                    if self.verbose > 0:
                        print(f"[DEBUG] Failed to add {src_host_name} to {router}: {result}", file=sys.stderr)
            
            # Check if destination host already exists for THIS router  
            dest_exists_for_router = any(
                existing.endswith(f":{router}") for existing in existing_dest_hosts
            )
            
            # Add destination host to this router if needed
            dst_host_name = f"destination-{router_index}"
            if not dest_exists_for_router:
                self._log_progress(f"host_add_dest_{router_index}", f"Adding destination host {dst_host_name} to router {router}")
                result = tsimsh_exec(
                    f"host add --name {dst_host_name} --primary-ip {self.dest_ip}/24 --connect-to {router} --no-delay",
                    verbose=self.verbose
                )
                if result is None:  # Success
                    self.created_hosts.append(dst_host_name)
                    hosts_added += 1
                    if self.verbose > 0:
                        print(f"[DEBUG] Added {dst_host_name} to {router}", file=sys.stderr)
                else:
                    if self.verbose > 0:
                        print(f"[DEBUG] Failed to add {dst_host_name} to {router}: {result}", file=sys.stderr)
            
            router_index += 1  # Increment for next router
        
        self._log_progress("PHASE2_hosts_complete", f"Host setup completed: {hosts_added} hosts added")
        
        # Check existing services
        self._log_progress("PHASE2_service_check", "Checking existing services")
        service_list_output = tsimsh_exec("service list --json", capture_output=True)
        existing_services = []
        
        if service_list_output:
            try:
                services = json.loads(service_list_output)
                for service in services:
                    if service.get('status') == 'running':
                        bind_addr = service.get('bind_address', '')
                        port = service.get('port')
                        proto = service.get('protocol', '').lower()
                        existing_services.append((bind_addr, port, proto))
            except:
                pass
        
        # Start ALL services in parallel (different from shell script which starts one)
        self._log_progress("PHASE2_services_start", f"Starting {len(self.services)} services on {self.dest_ip}")
        
        for port, protocol in self.services:
            # Check if this service already exists
            service_exists = any(
                s[0] == self.dest_ip and str(s[1]) == str(port) and s[2] == protocol.lower()
                for s in existing_services
            )
            
            if not service_exists:
                # Start service using IP:port like shell script
                cmd = f"service start --ip {self.dest_ip} --port {port} --protocol {protocol}"
                result = tsimsh_exec(cmd, verbose=self.verbose)
                
                if result is None:  # Success
                    self.started_services.append((self.dest_ip, port, protocol))
                    self._log_progress(f"service_{port}_{protocol}_started", f"Started {protocol.upper()} service on {self.dest_ip}:{port}")
                else:
                    print(f"Warning: Failed to start service on {self.dest_ip}:{port}/{protocol}: {result}", file=sys.stderr)
            else:
                self._log_progress(f"service_{port}_{protocol}_exists", f"Service already running on {self.dest_ip}:{port}/{protocol}")
        
        # Give services a moment to stabilize
        time.sleep(1)
        self._log_progress("PHASE2_complete", "Environment setup finished")
    
    def phase3_initial_tests(self) -> Dict[str, Any]:
        """Phase 3: Initial Reachability Tests - only traceroute (no ping as requested)."""
        self._log_progress("PHASE3_start", "Starting initial reachability tests")
        
        # Run traceroute test only (no ping as requested)
        traceroute_output = tsimsh_exec(
            f"traceroute --source {self.source_ip} --destination {self.dest_ip} --timeout 1 --max-hops 2 --json",
            capture_output=True,
            verbose=self.verbose
        )
        
        traceroute_result = {}
        if traceroute_output:
            try:
                traceroute_result = json.loads(traceroute_output)
            except:
                traceroute_result = {"error": "Failed to parse traceroute output"}
        else:
            traceroute_result = {"error": "Traceroute failed"}
        
        self._log_progress("PHASE3_complete", "Initial tests finished")
        return traceroute_result
    
    def test_service_with_packet_analysis(self, port: int, protocol: str, routers: List[str], 
                                          reuse_before_snapshot: Dict[str, str] = None) -> Dict[str, Any]:
        """Test a single service with packet counter analysis.
        
        For each service sequentially:
        1. Get iptables counters BEFORE test
        2. Run service test (EXACTLY like shell script)
        3. Get iptables counters AFTER test
        4. Analyze packet counts with correct mode per router
        """
        self._log_progress(f"test_{port}_{protocol}_start", f"Testing {protocol.upper()} port {port}")
        
        result = {
            "port": port,
            "protocol": protocol,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source_ip": self.source_ip,
            "source_port": self.source_port,
            "destination_ip": self.dest_ip,
            "destination_port": port
        }
        
        # Step 1: Get iptables counters BEFORE test for each router
        # Optimization: reuse previous "after" snapshot as "before" if available
        if reuse_before_snapshot:
            self._log_progress(f"iptables_before_{port}_{protocol}", "Reusing previous iptables snapshot")
            if self.verbose > 0:
                print(f"[DEBUG] OPTIMIZATION: Reusing previous iptables snapshot for {port}/{protocol}", file=sys.stderr)
            iptables_before = reuse_before_snapshot
        else:
            self._log_progress(f"iptables_before_{port}_{protocol}_start", "Starting to get iptables counters before test")
            if self.verbose > 0:
                print(f"[DEBUG] Getting fresh iptables snapshot before {port}/{protocol} test", file=sys.stderr)
            # Fetch per-router snapshots concurrently to reduce wall time
            iptables_before = {}
            from concurrent.futures import ThreadPoolExecutor, as_completed
            def _fetch_before(r):
                cmd = f"network status --json --limit {r} iptables --no-cache"
                return r, tsimsh_exec(cmd, capture_output=True, verbose=self.verbose)
            with ThreadPoolExecutor(max_workers=min(4, len(routers))) as pool:
                futures = [pool.submit(_fetch_before, r) for r in routers]
                for fut in as_completed(futures):
                    r, out = fut.result()
                    if out:
                        iptables_before[r] = out
            self._log_progress(f"iptables_before_{port}_{protocol}_complete", f"Got iptables from {len(routers)} routers")
        
        # Step 2: Run service test EXACTLY like shell script
        # Shell script command: service test --source ${SOURCE_IP} --destination ${DEST_IP}:${DEST_PORT} --protocol ${PROTOCOL} --timeout 1 --json
        test_cmd = f"service test --source {self.source_ip} --destination {self.dest_ip}:{port} --protocol {protocol} --timeout 1 --json"
        # Note: shell script does NOT add source-port to the service test command
        
        self._log_progress(f"service_test_{port}_{protocol}_start", f"Starting connectivity test to {self.dest_ip}:{port}/{protocol}")
        service_output = tsimsh_exec(test_cmd, capture_output=True, verbose=self.verbose)
        self._log_progress(f"service_test_{port}_{protocol}_complete", "Service test completed")
        
        if service_output:
            try:
                service_data = json.loads(service_output)
                result["connectivity_test"] = service_data
                # Try to derive actual source port from tests
                try:
                    tests = service_data.get("tests", [])
                    for t in tests:
                        sp = t.get("source_port")
                        if sp and sp != "ephemeral":
                            result["source_port"] = sp
                            break
                except Exception:
                    pass
                # If still missing here, will remain 'ephemeral' in summary
            except:
                result["connectivity_test"] = {"error": "Failed to parse service test output"}
        else:
            result["connectivity_test"] = {"error": "Service test failed"}
        
        # Step 3: Get iptables counters AFTER test for each router
        time.sleep(0.5)  # Let packets complete processing
        self._log_progress(f"iptables_after_{port}_{protocol}_start", "Starting to get iptables counters after test")
        
        iptables_after = {}
        from concurrent.futures import ThreadPoolExecutor, as_completed
        def _fetch_after(r):
            cmd = f"network status --json --limit {r} iptables --no-cache"
            return r, tsimsh_exec(cmd, capture_output=True, verbose=self.verbose)
        with ThreadPoolExecutor(max_workers=min(4, len(routers))) as pool:
            futures = [pool.submit(_fetch_after, r) for r in routers]
            for fut in as_completed(futures):
                r, out = fut.result()
                if out:
                    iptables_after[r] = out
        self._log_progress(f"iptables_after_{port}_{protocol}_complete", f"Got iptables from {len(routers)} routers")
        
        # Step 4: Parse service test results EXACTLY like shell script
        # Shell script logic from phase3_reachability_tests lines 694-706:
        # for test in data['tests']:
        #     if 'via_router' in test:
        #         router = test['via_router']
        #         status = test.get('status', '')
        #         if status == 'OK':
        #             results[router] = 'ALLOWED'
        #         elif status in ['FAIL', 'TIMEOUT', 'ERROR']:
        #             results[router] = 'BLOCKED'
        
        router_modes = {}
        service_tests = result.get("connectivity_test", {}).get("tests", [])
        
        for test in service_tests:
            if 'via_router' in test:
                router = test['via_router']
                status = test.get('status', '')
                
                if status == 'OK':
                    router_modes[router] = 'allowing'  # ALLOWED in shell -> allowing mode for analyzer
                elif status in ['FAIL', 'TIMEOUT', 'ERROR']:
                    router_modes[router] = 'blocking'  # BLOCKED in shell -> blocking mode for analyzer
                else:
                    print(f"ERROR: Unknown status {status} for router {router}", file=sys.stderr)
        
        # Shell script verifies all routers have results - we should too
        missing_routers = set(routers) - set(router_modes.keys())
        if missing_routers:
            print(f"WARNING: Missing service test results for routers: {list(missing_routers)}", file=sys.stderr)
            # Add missing routers as blocking (conservative approach)
            for router in missing_routers:
                router_modes[router] = 'blocking'
        
        if self.verbose > 0:
            print(f"[DEBUG] Router modes for {port}/{protocol}: {router_modes}", file=sys.stderr)
        
        # Step 5: Analyze packet counts for each router
        self._log_progress(f"packet_analysis_{port}_{protocol}_start", "Starting packet count analysis")
        packet_analysis = self.analyze_packet_counts(
            iptables_before,
            iptables_after,
            port,
            protocol,
            router_modes
        )
        self._log_progress(f"packet_analysis_{port}_{protocol}_complete", f"Analyzed packets for {len(routers)} routers")
        # Store with both names for compatibility
        result["packet_analysis"] = packet_analysis
        result["packet_count_analysis"] = packet_analysis  # Expected by visualize_reachability.py
        
        # Step 6: Determine overall reachability
        result["reachable"] = self.determine_reachability(result)
        
        # Step 7: Add router_service_results for use in formatting
        router_service_results = {}
        if "connectivity_test" in result:
            for test in result["connectivity_test"].get("tests", []):
                if "via_router" in test:
                    router = test["via_router"]
                    status = test.get("status", "")
                    if status == "OK":
                        router_service_results[router] = "ALLOWED"
                    elif status in ["FAIL", "TIMEOUT", "ERROR"]:
                        router_service_results[router] = "BLOCKED"
        result["router_service_results"] = router_service_results
        
        # Step 8: Store iptables_after for potential reuse in next test
        result["iptables_after"] = iptables_after
        
        self._log_progress(f"test_{port}_{protocol}_complete", f"Service test completed: {result['reachable']}")
        
        # Log summary of this service test timing
        self._log_progress(f"test_{port}_{protocol}_summary", 
                          f"Test summary - Reachable: {result['reachable']}, "
                          f"Routers: {len(routers)}")
        
        return result
    
    def analyze_packet_counts(self, iptables_before: Dict[str, Any], 
                              iptables_after: Dict[str, Any], 
                              port: int, protocol: str,
                              router_modes: Dict[str, str]) -> Dict[str, Any]:
        """Analyze packet counts using analyze_packet_counts.py script."""
        # Use analyze_packet_counts.py from the same directory as this script
        # When installed, both scripts should be in web-root/scripts/
        script_dir = Path(__file__).parent
        script_path = script_dir / "analyze_packet_counts.py"
        
        if not script_path.exists():
            error_msg = f"analyze_packet_counts.py not found at {script_path}"
            print(f"ERROR: {error_msg}", file=sys.stderr)
            raise Exception(error_msg)
        
        analysis_results = {}
        
        # Analyze each router concurrently to reduce wall time
        from concurrent.futures import ThreadPoolExecutor, as_completed
        def _analyze_router(router: str):
            if router not in iptables_after:
                return router, {"error": "missing after snapshot"}
            analysis_mode = router_modes.get(router, "blocking")
            before_path = after_path = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as before_file:
                    before_file.write(iptables_before[router])
                    before_path = before_file.name
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as after_file:
                    after_file.write(iptables_after[router])
                    after_path = after_file.name
                cmd = [
                    sys.executable, "-B", "-u",
                    str(script_path),
                    router,
                    before_path,
                    after_path,
                    "-m", analysis_mode
                ]
                if self.verbose > 1:
                    print(f"[DEBUG] Analyzing {router} in {analysis_mode} mode", file=sys.stderr)
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode != 0:
                    err = result.stderr or "Analysis script failed"
                    return router, {"error": err}
                if result.stdout:
                    try:
                        return router, json.loads(result.stdout)
                    except json.JSONDecodeError:
                        return router, {"raw_output": result.stdout}
                return router, {"error": "No output"}
            except subprocess.TimeoutExpired:
                return router, {"error": f"analyze_packet_counts.py timed out for router {router}"}
            except Exception as e:
                return router, {"error": str(e)}
            finally:
                try:
                    if before_path:
                        os.unlink(before_path)
                    if after_path:
                        os.unlink(after_path)
                except:
                    pass
        with ThreadPoolExecutor(max_workers=min(4, len(iptables_before))) as pool:
            futures = [pool.submit(_analyze_router, r) for r in iptables_before.keys()]
            for fut in as_completed(futures):
                r, data = fut.result()
                analysis_results[r] = data
        
        return {
            "port": port,
            "protocol": protocol,
            "router_modes": router_modes,
            "routers": analysis_results
        }
    
    def convert_packet_analysis_to_list(self, packet_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert packet_count_analysis from dict format to list format expected by visualizer."""
        if not packet_analysis or not isinstance(packet_analysis, dict):
            return []
        
        # If it already looks like a list, return it
        if isinstance(packet_analysis, list):
            return packet_analysis
        
        # Convert from {routers: {router1: {...}, router2: {...}}} to [{router: ..., ...}, {...}]
        result_list = []
        routers_data = packet_analysis.get("routers", {})
        
        if routers_data:
            for router_name, router_data in routers_data.items():
                # Each router_data should already have the right structure
                if isinstance(router_data, dict):
                    result_list.append(router_data)
        
        return result_list
    
    def determine_reachability(self, result: Dict[str, Any]) -> bool:
        """Determine if service is reachable based on test results."""
        # Check connectivity test result
        conn_test = result.get("connectivity_test", {})
        if isinstance(conn_test, dict):
            # Check summary first
            summary = conn_test.get("summary", {})
            if summary.get("successful", 0) > 0:
                return True
            
            # Check individual tests
            tests = conn_test.get("tests", [])
            for test in tests:
                if test.get("status") == "OK":
                    return True
        
        return False
    
    def run(self) -> None:
        """Main execution flow matching shell script phases."""
        try:
            self._log_progress("START", f"Multi-service test: {self.source_ip} -> {self.dest_ip} ({len(self.services)} services)")
            
            # Phase 1: Path Discovery
            trace_data = self.phase1_path_discovery()
            self.trace_data = trace_data  # Store for later use in formatting
            
            # Extract routers from trace
            routers = []
            for hop in trace_data.get('path', []):
                if hop.get('is_router', False):
                    router_name = hop.get('name', '')
                    if router_name:
                        routers.append(router_name)
            
            if not routers:
                raise Exception("No routers found in trace path")
            
            self._log_progress("PHASE1_complete", f"Found {len(routers)} routers: {', '.join(routers)}")
            
            # Phase 2: Environment Setup (hosts and services)
            self.phase2_setup_environment(routers)
            
            # Phase 3: Initial Tests (traceroute only, no ping)
            traceroute_result = self.phase3_initial_tests()
            self.traceroute_result = traceroute_result  # Store for use in formatting
            
            # Phase 4: Test each service SEQUENTIALLY with packet analysis
            self._log_progress("PHASE4_start", f"Testing {len(self.services)} services sequentially")
            
            all_results = []
            last_iptables_snapshot = None  # Track last snapshot for optimization
            
            for i, (port, protocol) in enumerate(self.services, 1):
                # Test this service with packet counter analysis
                # Reuse previous "after" snapshot as "before" for performance
                service_result = self.test_service_with_packet_analysis(
                    port, protocol, routers,
                    reuse_before_snapshot=last_iptables_snapshot
                )
                
                # Save "after" snapshot for next iteration
                last_iptables_snapshot = service_result.pop("iptables_after", None)
                
                all_results.append(service_result)
                
                # Brief pause between service tests to ensure clean separation
                if i < len(self.services):
                    time.sleep(1)
            
            self._log_progress("PHASE4_complete", "All service tests completed")
            
            # Phase 5: Generate individual result files in EXACT shell script format
            self.service_result_files = []
            used_source_ports = []
            
            for i, (service_result, (port, protocol)) in enumerate(zip(all_results, self.services)):
                # Build result in EXACT format that shell script produces via format_reachability_output.py
                formatted_result = {
                    "timestamp": service_result.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S")),
                    "version": "1.0.0",
                    "summary": {
                        "source_ip": self.source_ip,
                        "source_port": (lambda v: str(v) if v not in (None, "", "ephemeral") else (str(self.source_port) if self.source_port else "ephemeral"))(service_result.get("source_port")),
                        "destination_ip": self.dest_ip,
                        "destination_port": str(port),
                        "protocol": protocol
                    },
                    "setup_status": {
                        "source_host_added": True,
                        "destination_host_added": True,
                        "service_started": True
                    },
                    "reachability_tests": {
                        "ping": {
                            "result": None,  # Shell script has None when ping not run
                            "return_code": None
                        },
                        "traceroute": {
                            "result": traceroute_result,
                            "return_code": 0
                        },
                        "service": {
                            "result": service_result.get("connectivity_test", None),
                            "return_code": 0 if service_result.get("reachable", False) else 1
                        }
                    },
                    # Convert packet_count_analysis from dict format to list format expected by visualizer
                    "packet_count_analysis": self.convert_packet_analysis_to_list(
                        service_result.get("packet_count_analysis", service_result.get("packet_analysis", {}))
                    ),
                    "router_service_results": service_result.get("router_service_results", {})
                }
                
                # Add operational summary (required by visualizer)
                formatted_result["operational_summary"] = []
                formatted_result["total_duration_seconds"] = 0.0
                
                # Add reachability summary based on router service results
                router_results = formatted_result["router_service_results"]
                if router_results:
                    reachable_via = []
                    blocked_by = []
                    total_routers = len(router_results)
                    
                    for router, status in router_results.items():
                        if status == "ALLOWED" or status == "OK":
                            reachable_via.append(router)
                        else:
                            blocked_by.append(router)
                    
                    # Service is only reachable if ALL routers allow it
                    service_reachable = len(reachable_via) == total_routers and total_routers > 0
                    
                    formatted_result["reachability_summary"] = {
                        "service_reachable": service_reachable,
                        "reachable_via_routers": reachable_via,
                        "blocked_by_routers": blocked_by
                    }
                
                # Save individual result file in EXACT shell script format
                result_file = self.output_dir / f"{port}_{protocol}_results.json"
                with open(result_file, 'w') as f:
                    json.dump(formatted_result, f, indent=2)
                
                self.service_result_files.append(str(result_file))
                # Track used source port if available
                try:
                    sp_used = formatted_result.get('summary', {}).get('source_port')
                    if sp_used and sp_used != 'ephemeral' and sp_used not in used_source_ports:
                        used_source_ports.append(sp_used)
                except Exception:
                    pass
                self._log_progress(f"service_{i+1}_file_created", f"Created result file for {port}/{protocol}")
            
            # Save summary file for reference
            summary = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source_ip": self.source_ip,
                "destination_ip": self.dest_ip,
                "services_tested": len(self.services),
                "services_reachable": sum(1 for r in all_results if r.get("reachable", False)),
                "result_files": self.service_result_files,
                "source_ports": used_source_ports
            }
            
            summary_file = self.output_dir / "summary.json"
            with open(summary_file, 'w') as f:
                json.dump(summary, f, indent=2)
            
            total_duration = time.time() - SCRIPT_START_TIME
            self._log_progress("TOTAL", f"Total execution time: {total_duration:.2f}s")
            
            # Print summary to stdout
            print(json.dumps({
                "status": "success",
                "services_tested": len(self.services),
                "services_reachable": summary["services_reachable"],
                "duration": total_duration,
                "output_dir": str(self.output_dir),
                "result_files": self.service_result_files
            }))
            
        except Exception as e:
            self._log_progress("ERROR", str(e))
            print(json.dumps({
                "status": "error",
                "error": str(e)
            }))
            raise
        finally:
            self.cleanup()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Multi-Service Network Reachability Testing",
        formatter_class=argparse.RawDescriptionHelpFormatter
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
                        help='Use existing trace file instead of running new trace')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help='Increase verbosity')
    parser.add_argument('--version', action='version',
                        version=f'%(prog)s {VERSION}')
    
    args = parser.parse_args()
    
    # Read services from JSON file
    try:
        with open(args.services, 'r') as f:
            services = json.load(f)
        
        if not isinstance(services, list):
            raise ValueError("Services must be a JSON array")
        
        # Convert to list of tuples
        service_list = []
        for item in services:
            if isinstance(item, list) and len(item) == 2:
                port, protocol = item
                service_list.append((int(port), str(protocol).lower()))
            else:
                raise ValueError(f"Invalid service specification: {item}")
                
    except FileNotFoundError:
        print(f"Error: Services file not found: {args.services}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in services file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error parsing services: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Run the tester
    tester = MultiServiceTester(
        source_ip=args.source_ip,
        source_port=args.source_port,
        dest_ip=args.dest_ip,
        services=service_list,
        output_dir=args.output_dir,
        trace_file=args.trace_file,
        verbose=args.verbose
    )
    
    tester.run()


if __name__ == "__main__":
    main()
