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
        self.raw_facts_path = config.config.get('traceroute_simulator_raw_facts', '')
        self.facts_path = config.config.get('traceroute_simulator_facts', '')
        self.mode = config.config.get('traceroute_simulator_mode', 'live')
        self.test_trace_file = config.config.get('test_trace_file', '')
        
        
    def _activate_venv_and_run(self, cmd, timeout=60, capture_output=True):
        """Run command with virtual environment activated (same as test_me.py)"""
        # Build bash command to source venv and run the actual command
        venv_activate = os.path.join(self.venv_path, 'bin', 'activate')
        
        # Convert cmd list to string
        cmd_str = ' '.join(cmd)
        bash_cmd = f'source {venv_activate} && {cmd_str}'
        
        # Debug logging
        self.logger.log_info(f"Executing bash command: {bash_cmd}")
        
        # Start with current environment and update specific variables
        env = os.environ.copy()
        
        # Update/override specific environment variables
        env.update({
            # Basic environment
            'PATH': f"{self.venv_path}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            'VIRTUAL_ENV': self.venv_path,
            'PYTHONPATH': self.simulator_path,
            'HOME': '/var/www/traceroute-web',  # Persistent home directory for apache
            'USER': 'apache',
            'SHELL': '/bin/bash',
            'LANG': 'C.UTF-8',
            'LC_ALL': 'C.UTF-8',
            
            # Matplotlib backend for headless operation
            'MPLBACKEND': 'Agg',
            'DISPLAY': '',  # Explicitly unset DISPLAY to prevent X11 connection attempts
            
            # Traceroute simulator specific
            'TRACEROUTE_SIMULATOR_RAW_FACTS': self.raw_facts_path if self.raw_facts_path else '',
            'TRACEROUTE_SIMULATOR_FACTS': self.facts_path if self.facts_path else '',
        })
        
        # Set config file path
        config_file = self.config.config.get('traceroute_simulator_conf', '')
        if config_file and os.path.exists(config_file):
            env['TRACEROUTE_SIMULATOR_CONF'] = config_file
            self.logger.log_info(f"Using config file: {config_file}")
        else:
            self.logger.log_info(f"Config file not found or not set: {config_file}")
        
        # Execute command with bash
        start_time = time.time()
        try:
            # Add debug output to see what command is being run
            if "visualize_reachability" in bash_cmd:
                self.logger.log_info(f"About to execute visualization: {bash_cmd[:200]}")
            
            result = subprocess.run(
                ['bash', '-c', bash_cmd],
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
    
    def _activate_venv_and_run_with_input(self, cmd, input_data, timeout=60):
        """Run command with virtual environment activated and input via stdin (same as test_me.py)"""
        # Build bash command to source venv and run the actual command
        venv_activate = os.path.join(self.venv_path, 'bin', 'activate')
        
        # Convert cmd list to string
        cmd_str = ' '.join(cmd)
        bash_cmd = f'source {venv_activate} && {cmd_str}'
        
        # Debug logging
        self.logger.log_info(f"Executing bash command: {bash_cmd}")
        
        # Start with current environment and update specific variables
        env = os.environ.copy()
        
        # Update/override specific environment variables
        env.update({
            # Basic environment
            'PATH': f"{self.venv_path}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            'VIRTUAL_ENV': self.venv_path,
            'PYTHONPATH': self.simulator_path,
            'HOME': '/var/www/traceroute-web',  # Persistent home directory for apache
            'USER': 'apache',
            'SHELL': '/bin/bash',
            'LANG': 'C.UTF-8',
            'LC_ALL': 'C.UTF-8',
            
            # Matplotlib backend for headless operation
            'MPLBACKEND': 'Agg',
            'DISPLAY': '',  # Explicitly unset DISPLAY to prevent X11 connection attempts
            
            # Traceroute simulator specific
            'TRACEROUTE_SIMULATOR_RAW_FACTS': self.raw_facts_path if self.raw_facts_path else '',
            'TRACEROUTE_SIMULATOR_FACTS': self.facts_path if self.facts_path else '',
        })
        
        # Set config file path
        config_file = self.config.config.get('traceroute_simulator_conf', '')
        if config_file and os.path.exists(config_file):
            env['TRACEROUTE_SIMULATOR_CONF'] = config_file
            self.logger.log_info(f"Using config file: {config_file}")
        else:
            self.logger.log_info(f"Config file not found or not set: {config_file}")
        
        # Execute command with bash and input
        start_time = time.time()
        try:
            result = subprocess.run(
                ['bash', '-c', bash_cmd],
                env=env,
                cwd=self.simulator_path,
                input=input_data,
                capture_output=True,
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
    
    def execute_trace(self, session_id, username, source_ip, dest_ip, user_trace_data=None):
        """Execute tsimsh trace command or use test trace file or user-provided trace data"""
        run_id = str(uuid.uuid4())
        trace_file = os.path.join(self.data_dir, "traces", f"{run_id}_trace.json")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(trace_file), exist_ok=True)
        
        # Check if user provided trace data
        if user_trace_data:
            self.logger.log_info(f"Using user-provided trace data, length: {len(user_trace_data)}")
            
            # Save user trace data
            try:
                # Validate JSON format one more time
                user_json = json.loads(user_trace_data)
                self.logger.log_info(f"User trace data - destination IP: {user_json.get('destination', 'NOT FOUND')}")
                self.logger.log_info(f"User trace data first 200 chars: {user_trace_data[:200]}")
                
                # Log if file already exists (shouldn't happen with UUID)
                if os.path.exists(trace_file):
                    self.logger.log_info(f"Warning: trace file already exists: {trace_file}")
                
                with open(trace_file, 'w') as f:
                    f.write(user_trace_data)
                    f.flush()  # Force write to disk
                    os.fsync(f.fileno())  # Ensure it's written to disk
                
                # Log file creation time and content
                stat_info = os.stat(trace_file)
                self.logger.log_info(f"Trace file saved: {trace_file}, size: {stat_info.st_size}, mtime: {time.ctime(stat_info.st_mtime)}")
                
                # Immediately read back and verify what was written
                with open(trace_file, 'r') as f:
                    saved_content = f.read()
                    saved_json = json.loads(saved_content)
                    self.logger.log_info(f"Trace file verification - destination IP immediately after save: {saved_json.get('destination', 'NOT FOUND')}")
                    self.logger.log_info(f"First 200 chars of saved trace: {saved_content[:200]}")
                
                self.logger.log_command_execution(
                    session_id=session_id,
                    username=username,
                    command="tsimsh trace (user-provided)",
                    args={'source': source_ip, 'dest': dest_ip, 'user_provided': True},
                    start_time=time.time(),
                    end_time=time.time(),
                    return_code=0,
                    output="User-provided trace data used",
                    error=""
                )
                return run_id, trace_file
            except Exception as e:
                raise Exception(f"Failed to save user-provided trace data: {str(e)}")
        
        # Check if we're in test mode
        elif self.mode == 'test' and self.test_trace_file:
            self.logger.log_info(f"Test mode: Using test trace file {self.test_trace_file}")
            
            # Copy test trace file
            try:
                shutil.copy2(self.test_trace_file, trace_file)
                self.logger.log_command_execution(
                    session_id=session_id,
                    username=username,
                    command="tsimsh trace (test mode)",
                    args={'source': source_ip, 'dest': dest_ip, 'test_file': self.test_trace_file},
                    start_time=time.time(),
                    end_time=time.time(),
                    return_code=0,
                    output="Test trace file used",
                    error=""
                )
                return run_id, trace_file
            except Exception as e:
                raise Exception(f"Failed to copy test trace file: {str(e)}")
        
        # Live mode - execute real trace
        # Build command - tsimsh expects commands via stdin
        trace_command = f"trace -s {source_ip} -d {dest_ip} -j -vv"
        
        # Use tsimsh directly - environment is set by _activate_venv_and_run_with_input
        cmd = [self.tsimsh_path, "-q"]
        
        # Log the command being executed
        self.logger.log_info(f"Executing tsimsh trace: cmd={cmd}, trace_command={trace_command}")
        
        # Execute command with input
        start_time = time.time()
        result = self._activate_venv_and_run_with_input(cmd, trace_command + "\n", timeout=120)
        end_time = time.time()
        
        # Log the raw result with full output
        self.logger.log_info(f"Tsimsh trace result: success={result['success']}, return_code={result['return_code']}, output_len={len(result['output'])}")
        if result['output']:
            self.logger.log_info(f"Tsimsh trace stdout: {result['output']}")
        else:
            self.logger.log_info("Tsimsh trace stdout is empty")
        if result['error']:
            self.logger.log_info(f"Tsimsh trace stderr: {result['error']}")
        else:
            self.logger.log_info("Tsimsh trace stderr is empty")
        
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
        wrapper_path = os.path.join(self.simulator_path, "network_reachability_test_wrapper.py")
        
        # Log the wrapper path for debugging
        self.logger.log_info(f"Looking for wrapper at: {wrapper_path}")
        
        if not os.path.exists(wrapper_path):
            self.logger.log_error("Wrapper not found", f"network_reachability_test_wrapper.py not found at {wrapper_path}")
            raise Exception(f"Wrapper script not found at {wrapper_path}")
        
        cmd = [
            os.path.join(self.venv_path, "bin", "python"),
            "-B", "-u",
            wrapper_path,
            "-s", source_ip,
            "-d", dest_ip,
            "-P", str(dest_port),
            "-t", protocol,
            "-f", trace_file
        ]
        
        if source_port:
            cmd.extend(["-p", str(source_port)])
        
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
        
        # Log trace file details before reachability test
        self.logger.log_info(f"About to run reachability test with trace file: {trace_file}")
        try:
            trace_stat = os.stat(trace_file)
            self.logger.log_info(f"Trace file stats: size={trace_stat.st_size}, mtime={time.ctime(trace_stat.st_mtime)}")
            
            with open(trace_file, 'r') as f:
                trace_content = f.read()
                trace_json = json.loads(trace_content)
                self.logger.log_info(f"Trace file content - destination IP: {trace_json.get('destination', 'NOT FOUND')}")
                self.logger.log_info(f"Trace file first 200 chars before reachability test: {trace_content[:200]}")
        except Exception as e:
            self.logger.log_error("Failed to read trace file for debugging", str(e))
        
        if result['success'] and result['output']:
            
            # Save the JSON output to results file
            with open(results_file, 'w') as f:
                f.write(result['output'])
            return results_file
        else:
            # Log detailed error information
            self.logger.log_error(
                "Reachability test failed",
                f"Return code: {result['return_code']}, Error: {result['error']}, Output: {result['output'][:500]}"
            )
            error_msg = result['error'] if result['error'] else f"Script returned code {result['return_code']}"
            if result['output']:
                error_msg += f" Output: {result['output'][:200]}"
            raise Exception(f"Reachability test failed: {error_msg}")
    
    def generate_pdf(self, session_id, username, run_id, trace_file, results_file):
        """Generate PDF by calling generate_pdf.sh via curl"""
        import urllib.parse
        import urllib.request
        
        pdf_file = os.path.join(self.data_dir, "pdfs", f"{run_id}_report.pdf")
        os.makedirs(os.path.dirname(pdf_file), exist_ok=True)
        
        # Get base URL from config (required)
        base_url = self.config.config.get('base_url')
        if not base_url:
            raise Exception("base_url not configured in config.json")
        
        # Build URL with parameters
        params = {
            'trace': trace_file,
            'results': results_file,
            'output': pdf_file
        }
        query_string = urllib.parse.urlencode(params)
        url = f"{base_url}/cgi-bin/generate_pdf.sh?{query_string}"
        
        self.logger.log_info(f"Calling PDF generation via: {url}")
        
        try:
            # Make the request
            with urllib.request.urlopen(url, timeout=30) as response:
                if response.headers.get('content-type') == 'application/pdf':
                    # Save the PDF
                    pdf_data = response.read()
                    with open(pdf_file, 'wb') as f:
                        f.write(pdf_data)
                    self.logger.log_info(f"PDF generated successfully, size: {len(pdf_data)} bytes")
                    return pdf_file
                else:
                    # Read error message
                    error_msg = response.read().decode('utf-8')
                    self.logger.log_error("PDF generation failed", error_msg)
                    raise Exception(f"PDF generation failed: {error_msg}")
                    
        except urllib.error.URLError as e:
            self.logger.log_error("PDF generation failed", str(e))
            raise Exception(f"PDF generation failed: {str(e)}")
    
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