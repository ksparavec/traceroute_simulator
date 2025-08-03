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
        
        # Create a clean environment with all necessary variables
        env = {
            # Basic environment
            'PATH': f"{self.venv_path}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            'VIRTUAL_ENV': self.venv_path,
            'PYTHONPATH': self.simulator_path,
            'HOME': '/tmp',  # Safe home directory for www-data
            'USER': 'www-data',
            'SHELL': '/bin/bash',
            'LANG': 'C.UTF-8',
            'LC_ALL': 'C.UTF-8',
            
            # Traceroute simulator specific
            'TRACEROUTE_SIMULATOR_RAW_FACTS': self.raw_facts_path if self.raw_facts_path else '',
            'TRACEROUTE_SIMULATOR_FACTS': self.facts_path if self.facts_path else '',
        }
        
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
        
        # Create a clean environment with all necessary variables
        env = {
            # Basic environment
            'PATH': f"{self.venv_path}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            'VIRTUAL_ENV': self.venv_path,
            'PYTHONPATH': self.simulator_path,
            'HOME': '/tmp',  # Safe home directory for www-data
            'USER': 'www-data',
            'SHELL': '/bin/bash',
            'LANG': 'C.UTF-8',
            'LC_ALL': 'C.UTF-8',
            
            # Traceroute simulator specific
            'TRACEROUTE_SIMULATOR_RAW_FACTS': self.raw_facts_path if self.raw_facts_path else '',
            'TRACEROUTE_SIMULATOR_FACTS': self.facts_path if self.facts_path else '',
        }
        
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
    
    def execute_trace(self, session_id, username, source_ip, dest_ip):
        """Execute tsimsh trace command or use test trace file"""
        run_id = str(uuid.uuid4())
        trace_file = os.path.join(self.data_dir, "traces", f"{run_id}_trace.json")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(trace_file), exist_ok=True)
        
        # Check if we're in test mode
        if self.mode == 'test' and self.test_trace_file:
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
        trace_command = f"trace -s {source_ip} -d {dest_ip} -j"
        
        # Use tsimsh directly - environment is set by _activate_venv_and_run_with_input
        cmd = [os.path.join(self.venv_path, "bin", "tsimsh"), "-q"]
        
        # Log the command being executed
        self.logger.log_info(f"Executing tsimsh trace: cmd={cmd}, trace_command={trace_command}")
        
        # Execute command with input
        start_time = time.time()
        result = self._activate_venv_and_run_with_input(cmd, trace_command + "\n", timeout=120)
        end_time = time.time()
        
        # Log the raw result
        self.logger.log_info(f"Tsimsh trace result: success={result['success']}, return_code={result['return_code']}, output_len={len(result['output'])}, error={result['error'][:100] if result['error'] else 'None'}")
        
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
        """Execute visualize_reachability.py to generate PDF"""
        pdf_file = os.path.join(self.data_dir, "pdfs", f"{run_id}_report.pdf")
        os.makedirs(os.path.dirname(pdf_file), exist_ok=True)
        
        # Build command
        cmd = [
            os.path.join(self.venv_path, "bin", "python"),
            "-B", "-u",
            os.path.join(self.simulator_path, "visualize_reachability.py"),
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