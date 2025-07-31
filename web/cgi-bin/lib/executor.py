#!/usr/bin/env -S python3 -B -u
"""Command execution wrapper for web service"""
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
            os.path.join(self.simulator_path, "web/scripts/network_reachability_test_wrapper.py"),
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