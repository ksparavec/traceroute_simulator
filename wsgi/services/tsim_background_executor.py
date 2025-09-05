#!/usr/bin/env -S python3 -B -u
"""
TSIM Background Executor Service
Handles background task execution with process isolation
"""

import os
import sys
import json
import uuid
import tempfile
import subprocess
import threading
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime


class TsimBackgroundExecutor:
    """Service for executing background tasks with process isolation"""
    
    def __init__(self, config_service, lock_manager, timing_service):
        """Initialize background executor
        
        Args:
            config_service: TsimConfigService instance
            lock_manager: TsimLockManagerService instance
            timing_service: TsimTimingService instance
        """
        self.config = config_service
        self.lock_manager = lock_manager
        self.timing = timing_service
        self.logger = logging.getLogger('tsim.background_executor')
        
        # Directories - all temp files in /dev/shm/tsim
        self.run_dir = Path(config_service.get('run_dir', '/dev/shm/tsim/runs'))
        self.scripts_dir = Path(config_service.get('scripts_dir', '/dev/shm/tsim/scripts'))
        # Use the raw_facts_dir from config service (already resolved from environment or config)
        self.raw_facts_dir = config_service.raw_facts_dir
        
        # Ensure directories exist
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
    
    def create_worker_script(self, run_id: str, task_type: str, 
                           task_params: Dict[str, Any]) -> Path:
        """Create isolated worker script for task execution
        
        Args:
            run_id: Run identifier
            task_type: Type of task (trace, reachability, pdf)
            task_params: Task parameters
            
        Returns:
            Path to created script
        """
        script_path = self.scripts_dir / f"{run_id}_{task_type}.py"
        
        # Generate script content based on task type
        if task_type == 'trace':
            script_content = self._generate_trace_script(run_id, task_params)
        elif task_type == 'reachability':
            script_content = self._generate_reachability_script(run_id, task_params)
        elif task_type == 'pdf':
            script_content = self._generate_pdf_script(run_id, task_params)
        elif task_type == 'full_test':
            script_content = self._generate_full_test_script(run_id, task_params)
        else:
            raise ValueError(f"Unknown task type: {task_type}")
        
        # Write script
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        script_path.chmod(0o755)
        self.logger.info(f"Created worker script: {script_path}")
        
        return script_path
    
    def _generate_trace_script(self, run_id: str, params: Dict[str, Any]) -> str:
        """Generate trace execution script
        
        Args:
            run_id: Run identifier
            params: Trace parameters
            
        Returns:
            Script content
        """
        source_ip = params['source_ip']
        dest_ip = params['dest_ip']
        user_trace = params.get('user_trace_data', '')
        run_dir = self.run_dir / run_id
        
        script = f'''#!/usr/bin/env -S python3 -B -u
import os
import sys
import json
import subprocess
from pathlib import Path

# Task parameters
RUN_ID = "{run_id}"
SOURCE_IP = "{source_ip}"
DEST_IP = "{dest_ip}"
USER_TRACE = """{user_trace}"""
RUN_DIR = Path("{run_dir}")
RAW_FACTS_DIR = Path("{self.raw_facts_dir}")

# Create run directory
RUN_DIR.mkdir(parents=True, exist_ok=True)

# Progress logging
def log_progress(phase, message="", details=""):
    with open(RUN_DIR / "progress.json", "a") as f:
        json.dump({{
            "timestamp": datetime.now().isoformat(),
            "phase": phase,
            "message": message,
            "details": details
        }}, f)
        f.write("\\n")

try:
    log_progress("trace_start", f"Starting trace from {{SOURCE_IP}} to {{DEST_IP}}")
    
    if USER_TRACE:
        # Use provided trace data
        trace_file = RUN_DIR / "trace.json"
        with open(trace_file, "w") as f:
            f.write(USER_TRACE)
        log_progress("trace_user_data", "Using provided trace data")
    else:
        # Execute actual trace
        os.environ["TRACEROUTE_SIMULATOR_RAW_FACTS"] = str(RAW_FACTS_DIR)
        
        # Import and use tsimsh trace functionality
        import sys
        # Path already set in parent environment
        from scripts.tsim_reachability_tester import TsimReachabilityTester
        
        tester = TsimReachabilityTester(
            raw_facts_dir=str(RAW_FACTS_DIR),
            run_dir=str(RUN_DIR)
        )
        
        trace_file = tester.execute_trace(SOURCE_IP, DEST_IP)
        log_progress("trace_execute", f"Executed trace, output: {{trace_file}}")
    
    log_progress("trace_complete", f"Trace completed: {{trace_file}}")
    
    # Write completion marker
    with open(RUN_DIR / "trace_complete", "w") as f:
        f.write(str(trace_file))
    
except Exception as e:
    log_progress("trace_error", f"Trace failed: {{str(e)}}")
    raise
'''
        return script
    
    def _generate_reachability_script(self, run_id: str, params: Dict[str, Any]) -> str:
        """Generate reachability test script
        
        Args:
            run_id: Run identifier
            params: Test parameters
            
        Returns:
            Script content
        """
        run_dir = self.run_dir / run_id
        
        script = f'''#!/usr/bin/env -S python3 -B -u
import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Task parameters
RUN_ID = "{run_id}"
RUN_DIR = Path("{run_dir}")
RAW_FACTS_DIR = Path("{self.raw_facts_dir}")
PARAMS = {repr(params)}

# Progress logging
def log_progress(phase, message="", details=""):
    with open(RUN_DIR / "progress.json", "a") as f:
        json.dump({{
            "timestamp": datetime.now().isoformat(),
            "phase": phase,
            "message": message,
            "details": details
        }}, f)
        f.write("\\n")

try:
    log_progress("reachability_start", "Starting reachability tests")
    
    # Set environment
    os.environ["TRACEROUTE_SIMULATOR_RAW_FACTS"] = str(RAW_FACTS_DIR)
    os.environ["RUN_ID"] = RUN_ID
    
    # Import the actual business logic script from src/scripts
    sys.path.insert(0, '/home/sparavec/git/traceroute-simulator/src/scripts')
    from network_reachability_test_multi import MultiServiceTester
    
    # Create services list from params
    services = [(s['port'], s['protocol']) for s in PARAMS['services']]
    
    # Initialize tester with same parameters as CGI
    tester = MultiServiceTester(
        source_ip=PARAMS['source_ip'],
        source_port=PARAMS.get('source_port'),
        dest_ip=PARAMS['dest_ip'],
        services=services,
        output_dir=str(RUN_DIR),
        trace_file=PARAMS.get('trace_file'),
        verbose=1
    )
    
    # Run the tests
    try:
        tester.run()
        log_progress("reachability_complete", f"Tests completed successfully")
    finally:
        # Always cleanup
        tester.cleanup()
    
    # Write completion marker
    with open(RUN_DIR / "reachability_complete", "w") as f:
        f.write("success")
    
except Exception as e:
    log_progress("reachability_error", f"Tests failed: {{str(e)}}")
    with open(RUN_DIR / "reachability_error", "w") as f:
        f.write(str(e))
    raise
'''
        return script
    
    def _generate_pdf_section(self, params: Dict[str, Any]) -> str:
        """Generate the PDF generation section - using CGI code verbatim
        
        Args:
            params: Parameters including result_files, trace_file, summary data
            
        Returns:
            Python code string for PDF generation
        """
        return '''
    # PDF Generation Section - CGI code verbatim with minimal WSGI adjustments
    log_progress("PDF_GENERATION", "Generating PDF reports")
    
    import os
    import sys
    import json
    import subprocess
    import shutil
    
    # Set matplotlib backend and config 
    os.environ['MPLBACKEND'] = 'Agg'
    os.environ['DISPLAY'] = ''
    os.environ['MPLCONFIGDIR'] = '/dev/shm/tsim/matplotlib_cache'
    os.makedirs('/dev/shm/tsim/matplotlib_cache', exist_ok=True, mode=0o775)
    
    pdf_files = []
    
    # Step 1: Generate summary page using CGI script verbatim
    summary_pdf = RUN_DIR / f"{RUN_ID}_summary.pdf"
    try:
        # Prepare form data for summary page
        form_data_file = RUN_DIR / f"{RUN_ID}_form.json"
        form_data = {
            'source_ip': PARAMS.get('source_ip', 'N/A'),
            'dest_ip': PARAMS.get('dest_ip', 'N/A'),
            'timestamp': PARAMS.get('summary', {}).get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            'run_id': RUN_ID,
            'session_id': RUN_ID
        }
        with open(form_data_file, 'w') as f:
            json.dump(form_data, f)
        
        # Prepare results list for summary page
        results_list_file = RUN_DIR / f"{RUN_ID}_results_list.json"
        result_files = PARAMS.get('result_files', [])
        if not result_files and 'results' in locals():
            result_files = results.get('result_files', [])
        
        results_list = []
        for result_file in result_files:
            # Extract port and protocol from filename
            parts = Path(result_file).stem.split('_')
            if len(parts) >= 3:
                port = parts[-3]
                protocol = parts[-2]
            else:
                port = "unknown"
                protocol = "unknown"
            results_list.append({
                'port': port,
                'protocol': protocol,
                'file': str(result_file)
            })
        with open(results_list_file, 'w') as f:
            json.dump(results_list, f)
        
        # Run summary page generator with CGI script
        from scripts.generate_summary_page_reportlab import main as generate_summary
        sys.argv = ['generate_summary_page_reportlab.py',
                   '--form-data', str(form_data_file),
                   '--results', str(results_list_file),
                   '--output', str(summary_pdf)]
        generate_summary()
        
        if summary_pdf.exists():
            pdf_files.append(str(summary_pdf))
            log_progress("PDF_summary", "Generated summary page")
        else:
            log_progress("PDF_summary_error", "Failed to generate summary page")
            
    except Exception as e:
        log_progress("PDF_summary_error", f"Failed to generate summary: {e}")
    
    # Step 2: Generate individual PDFs for each service using CGI visualize_reachability.py
    for result_file in result_files:
        try:
            # Extract service name from filename
            result_path = Path(result_file)
            parts = result_path.stem.split('_')
            if len(parts) >= 3:
                port = parts[-3]
                protocol = parts[-2]
                service_info = f"{port}/{protocol}"
            else:
                service_info = result_path.stem
            
            # Generate PDF for this service
            service_pdf = RUN_DIR / f"{RUN_ID}_{port}_{protocol}.pdf"
            
            # Get trace file
            trace_file = PARAMS.get('trace_file', str(RUN_DIR / "trace.json"))
            if 'trace_file' in locals():
                trace_file = str(trace_file)
            
            # Run visualize_reachability.py using CGI script verbatim
            # Scripts are already in PYTHONPATH from app.wsgi
            cmd = [sys.executable, "-B", "-u", "-m", "scripts.visualize_reachability",
                   "--trace", str(trace_file),
                   "--results", str(result_file),
                   "--output", str(service_pdf),
                   "--service", service_info]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and service_pdf.exists() and service_pdf.stat().st_size > 0:
                pdf_files.append(str(service_pdf))
                log_progress(f"PDF_{port}_{protocol}", f"Generated PDF for {service_info}")
            else:
                log_progress(f"PDF_ERROR", f"Failed to generate PDF for {service_info}: {result.stderr}")
                
        except Exception as e:
            log_progress(f"PDF_ERROR", f"Failed to generate PDF for {result_file}: {e}")
    
    # Step 3: Merge all PDFs using CGI merge_pdfs.py script
    final_pdf = None
    if len(pdf_files) > 0:
        try:
            final_pdf = RUN_DIR / f"{RUN_ID}_report.pdf"
            
            # Create merge list file
            merge_list_file = RUN_DIR / f"{RUN_ID}_merge_list.json"
            with open(merge_list_file, 'w') as f:
                json.dump(pdf_files, f)
            
            # Run merge script using CGI merge_pdfs.py
            from scripts.merge_pdfs import main as merge_pdfs
            sys.argv = ['merge_pdfs.py',
                       '--input-list', str(merge_list_file),
                       '--output', str(final_pdf),
                       '--cleanup']
            merge_pdfs()
            
            if final_pdf.exists():
                log_progress("PDF_merge_complete", f"Merged PDF: {final_pdf}")
                
                # Clean up merge list file
                try:
                    merge_list_file.unlink()
                except:
                    pass
            else:
                # If merge failed, just use first PDF
                if pdf_files:
                    shutil.copy(pdf_files[0], str(final_pdf))
                    
        except Exception as e:
            log_progress("PDF_merge_error", f"Failed to merge PDFs: {e}")
            # Fall back to first PDF
            if pdf_files:
                shutil.copy(pdf_files[0], str(final_pdf))
    
    # PDF is served directly from run directory - no copying needed to save RAM
    if final_pdf and final_pdf.exists():
        log_progress("PDF_COMPLETE", f"PDF generation completed: {final_pdf}")
    else:
        log_progress("PDF_ERROR", "PDF generation failed - no final PDF created")
'''

    def _generate_pdf_script(self, run_id: str, params: Dict[str, Any]) -> str:
        """Generate standalone PDF generation script
        
        Args:
            run_id: Run identifier  
            params: PDF parameters including result_files, trace_file, summary
            
        Returns:
            Script content
        """
        run_dir = self.run_dir / run_id
        
        script = f'''#!/usr/bin/env -S python3 -B -u
import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Task parameters
RUN_ID = "{run_id}"
RUN_DIR = Path("{run_dir}")
PARAMS = {repr(params)}

# Progress logging
def log_progress(phase, message="", details=""):
    with open(RUN_DIR / "progress.json", "a") as f:
        json.dump({{
            "timestamp": datetime.now().isoformat(),
            "phase": phase,
            "message": message,
            "details": details
        }}, f)
        f.write("\\n")

try:
    log_progress("START", "Starting PDF generation")
    
{self._generate_pdf_section(params)}
    
    # Write completion marker
    with open(RUN_DIR / "pdf_complete", "w") as f:
        f.write(str(final_pdf) if final_pdf else "")
    
except Exception as e:
    log_progress("ERROR", f"PDF generation failed: {{str(e)}}")
    raise
'''
        return script
    
    def _generate_full_test_script(self, run_id: str, params: Dict[str, Any]) -> str:
        """Generate complete test execution script (trace + reachability + PDF)
        
        Args:
            run_id: Run identifier
            params: Test parameters
            
        Returns:
            Script content
        """
        run_dir = self.run_dir / run_id
        
        script = f'''#!/usr/bin/env -S python3 -B -u
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

# Task parameters
RUN_ID = "{run_id}"
RUN_DIR = Path("{run_dir}")
PARAMS = {repr(params)}

# Ensure run directory exists
RUN_DIR.mkdir(parents=True, exist_ok=True)

# Progress logging
def log_progress(phase, message="", details=""):
    progress_file = RUN_DIR / "progress.json"
    with open(progress_file, "a") as f:
        json.dump({{
            "timestamp": datetime.now().isoformat(),
            "phase": phase,
            "message": message,
            "details": details
        }}, f)
        f.write("\\n")
    print(f"[{{phase}}] {{message}}", file=sys.stderr)

# WSGI path should already be in sys.path from parent process
# All environment variables are inherited from parent

try:
    # PHASE 1: Execute trace
    log_progress("PHASE1_START", "Starting path discovery")
    
    if PARAMS.get('user_trace_data'):
        # Use provided trace data
        trace_file = RUN_DIR / f"{{RUN_ID}}.trace"
        with open(trace_file, 'w') as f:
            f.write(PARAMS['user_trace_data'])
        log_progress("PHASE1_COMPLETE", "Using provided trace data")
    else:
        # Execute trace command
        log_progress("PHASE1_TRACE", "Executing trace command")
        # Import tsimsh execution function
        from scripts.tsim_multi_service_tester import tsimsh_exec
        
        trace_command = f"trace -s {{PARAMS['source_ip']}} -d {{PARAMS['dest_ip']}} -j -vv"
        trace_output = tsimsh_exec(trace_command, capture_output=True)
        
        if trace_output:
            trace_file = RUN_DIR / f"{{RUN_ID}}.trace"
            with open(trace_file, 'w') as f:
                f.write(trace_output)
            log_progress("PHASE1_COMPLETE", "Trace completed successfully")
        else:
            raise RuntimeError("Failed to execute trace")
    
    # PHASE 2-4: Execute reachability tests
    log_progress("PHASE2_START", "Starting host setup")
    
    # Import reachability tester
    from scripts.tsim_reachability_tester import TsimReachabilityTester
    
    # Create tester instance
    tester = TsimReachabilityTester(
        source_ip=PARAMS['source_ip'],
        dest_ip=PARAMS['dest_ip'],
        source_port=PARAMS.get('source_port'),
        port_protocol_list=PARAMS['port_protocol_list'],
        trace_file=str(trace_file),
        results_dir=str(RUN_DIR / 'results'),
        run_id=RUN_ID,
        verbose=1,
        cleanup=True
    )
    
    # Run tests
    log_progress("PHASE3_START", "Creating services")
    log_progress("PHASE4_START", "Testing services")
    
    results = tester.run()
    
    log_progress("PHASE5_START", "Cleanup")
    log_progress("PHASE5_COMPLETE", "Cleanup completed")
    
    # PHASE 6: Generate PDFs using unified approach
{self._generate_pdf_section(params)}
    
    # Write completion marker
    log_progress("COMPLETE", "All tests completed successfully")
    
    with open(RUN_DIR / "test_complete", "w") as f:
        json.dump({{
            'success': True,
            'trace_file': str(trace_file),
            'result_files': results.get('result_files', []),
            'pdf_files': pdf_files,
            'final_pdf': str(final_pdf) if final_pdf else None,
            'timestamp': datetime.now().isoformat()
        }}, f)
    
except Exception as e:
    log_progress("ERROR", f"Test failed: {{str(e)}}")
    with open(RUN_DIR / "test_error", "w") as f:
        json.dump({{
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }}, f)
    raise
'''
        return script
    
    def execute_background_task(self, run_id: str, task_type: str,
                               task_params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute task in background with process isolation
        
        Args:
            run_id: Run identifier
            task_type: Type of task
            task_params: Task parameters
            
        Returns:
            Task execution info
        """
        # Create worker script
        script_path = self.create_worker_script(run_id, task_type, task_params)
        
        # Create run directory
        run_dir = self.run_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize progress file
        progress_file = run_dir / "progress.json"
        with open(progress_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "phase": "START",
                "message": f"Starting {task_type} task"
            }, f)
            f.write("\n")
        
        # Execute script in background
        try:
            process = subprocess.Popen(
                [sys.executable, str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(run_dir),
                env={**os.environ, 'PYTHONUNBUFFERED': '1'}
            )
            
            self.logger.info(f"Started background task {task_type} for run {run_id}, PID: {process.pid}")
            
            # Start thread to monitor process
            monitor_thread = threading.Thread(
                target=self._monitor_process,
                args=(process, run_id, task_type, script_path)
            )
            monitor_thread.daemon = True
            monitor_thread.start()
            
            return {
                'run_id': run_id,
                'task_type': task_type,
                'pid': process.pid,
                'script': str(script_path),
                'run_dir': str(run_dir),
                'progress_file': str(progress_file)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to start background task: {e}")
            # Clean up script
            if script_path.exists():
                script_path.unlink()
            raise
    
    def _monitor_process(self, process, run_id: str, task_type: str, script_path: Path):
        """Monitor background process and clean up when done
        
        Args:
            process: Subprocess instance
            run_id: Run identifier
            task_type: Task type
            script_path: Path to script
        """
        try:
            # Wait for process to complete
            stdout, stderr = process.communicate()
            
            # Log completion
            self.logger.info(f"Background task {task_type} for run {run_id} completed with code {process.returncode}")
            
            if process.returncode != 0:
                self.logger.error(f"Task stderr: {stderr.decode('utf-8', errors='ignore')}")
            
            # Update progress file
            run_dir = self.run_dir / run_id
            progress_file = run_dir / "progress.json"
            with open(progress_file, 'a') as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "phase": "COMPLETE" if process.returncode == 0 else "ERROR",
                    "message": f"Task {task_type} completed",
                    "return_code": process.returncode
                }, f)
                f.write("\n")
            
        finally:
            # Clean up script file
            try:
                if script_path.exists():
                    script_path.unlink()
            except Exception as e:
                self.logger.warning(f"Failed to clean up script {script_path}: {e}")
    
    def get_task_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get status of background task
        
        Args:
            run_id: Run identifier
            
        Returns:
            Task status or None if not found
        """
        run_dir = self.run_dir / run_id
        if not run_dir.exists():
            return None
        
        progress_file = run_dir / "progress.json"
        if not progress_file.exists():
            return None
        
        # Read all progress entries
        progress_entries = []
        with open(progress_file, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        progress_entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        
        if not progress_entries:
            return None
        
        # Get latest status
        latest = progress_entries[-1]
        
        # Check for completion markers
        is_complete = False
        if (run_dir / "pdf_complete").exists():
            is_complete = True
        elif (run_dir / "reachability_complete").exists() and latest['phase'] != 'pdf_start':
            is_complete = True
        elif (run_dir / "trace_complete").exists() and latest['phase'] not in ['reachability_start', 'pdf_start']:
            is_complete = True
        
        return {
            'run_id': run_id,
            'phase': latest['phase'],
            'message': latest.get('message', ''),
            'complete': is_complete or latest['phase'] in ['COMPLETE', 'ERROR'],
            'error': latest['phase'] == 'ERROR',
            'all_phases': progress_entries
        }