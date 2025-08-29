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
from pathlib import Path

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
        
        # Convert cmd list to string - handle if elements are already quoted
        import shlex
        cmd_str = ' '.join([str(c) for c in cmd])
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
    
    def execute_trace(self, session_id, username, run_id, source_ip, dest_ip, user_trace_data=None):
        """Execute tsimsh trace command or use test trace file or user-provided trace data"""
        trace_file = os.path.join(self.data_dir, "traces", f"{run_id}_trace.json")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(trace_file), exist_ok=True, mode=0o775)
        
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
    
    def execute_reachability_multi(self, session_id, username, run_id, trace_file,
                                   source_ip, source_port, dest_ip, port_protocol_list):
        """Execute optimized multi-service reachability test"""
        # Store IPs for summary page generation
        self.last_source_ip = source_ip
        self.last_dest_ip = dest_ip
        
        # Create output directory for results
        output_dir = os.path.join(self.data_dir, "results", run_id)
        os.makedirs(output_dir, exist_ok=True, mode=0o775)
        
        # Use the multi-service wrapper with locking
        wrapper_path = os.path.join(self.simulator_path, "network_reachability_test_wrapper_multi.py")
        
        # Log the wrapper path for debugging
        self.logger.log_info(f"Looking for multi-service wrapper at: {wrapper_path}")
        
        if not os.path.exists(wrapper_path):
            self.logger.log_error("Wrapper not found", f"network_reachability_test_wrapper_multi.py not found at {wrapper_path}")
            raise Exception(f"Multi-service wrapper script not found at {wrapper_path}")
        
        # Write services to a JSON file instead of passing via command line
        services_file = os.path.join(output_dir, "services.json")
        with open(services_file, 'w') as f:
            json.dump(port_protocol_list, f)
        
        cmd = [
            os.path.join(self.venv_path, "bin", "python"),
            "-B", "-u",
            wrapper_path,
            "-s", source_ip,
            "-d", dest_ip,
            "-p", services_file,  # Now passing the file path instead of JSON string
            "-o", output_dir,
            "-f", trace_file
        ]
        
        if source_port:
            cmd.extend(["-S", str(source_port)])
        
        # Add verbose flags if configured
        verbose_level = self.config.config.get('tsimsh_verbose_level', 0)
        for _ in range(verbose_level):
            cmd.append("-v")
        
        # Log that we're starting the multi-service test
        self.logger.log_info(
            f"Session {session_id}: Starting multi-service test for "
            f"{len(port_protocol_list)} services from {source_ip} to {dest_ip}"
        )
        
        # Execute command (will wait for lock if needed)
        start_time = time.time()
        result = self._activate_venv_and_run(cmd, timeout=420)  # 7 minutes (5 min lock + execution)
        end_time = time.time()
        
        # Log execution
        self.logger.log_command_execution(
            session_id=session_id,
            username=username,
            command="network_reachability_test_wrapper_multi.py",
            args={
                'source_ip': source_ip,
                'source_port': source_port,
                'dest_ip': dest_ip,
                'services': port_protocol_list,
                'trace_file': trace_file,
                'output_dir': output_dir
            },
            start_time=start_time,
            end_time=end_time,
            return_code=result['return_code'],
            output=result['output'][:1000] if result['output'] else "",
            error=result['error'][:1000] if result['error'] else ""
        )
        
        if not result['success']:
            self.logger.log_error("Multi-service test failed", result['error'])
            raise Exception(f"Multi-service reachability test failed: {result['error']}")
        
        # Parse the output to get status
        try:
            output_data = json.loads(result['output'])
            self.logger.log_info(
                f"Multi-service test completed: {output_data.get('services_reachable', 0)}/"
                f"{output_data.get('services_tested', 0)} services reachable"
            )
        except:
            pass
        
        # Collect result files that were generated
        result_files = []
        for port, protocol in port_protocol_list:
            result_file = os.path.join(output_dir, f"{port}_{protocol}_results.json")
            if os.path.exists(result_file):
                result_files.append((port, protocol, result_file))
            else:
                self.logger.log_warning(f"Result file not found for {port}/{protocol}")
        
        if not result_files:
            raise Exception("No service result files were generated")
        
        self.logger.log_info(f"Collected {len(result_files)} result files for PDF generation")
        
        return result_files
    
    def execute_reachability_test(self, session_id, username, run_id, trace_file,
                                  source_ip, source_port, dest_ip, dest_port, protocol):
        """Execute network_reachability_test.sh with locking"""
        # Make filename unique for each port/protocol combination
        results_file = os.path.join(self.data_dir, "results", f"{run_id}_{dest_port}_{protocol}_results.json")
        os.makedirs(os.path.dirname(results_file), exist_ok=True, mode=0o775)
        
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
        import ssl
        
        pdf_file = os.path.join(self.data_dir, "pdfs", f"{run_id}_report.pdf")
        os.makedirs(os.path.dirname(pdf_file), exist_ok=True, mode=0o775)
    
    def generate_multi_page_pdf(self, session_id, username, run_id, trace_file, results_files):
        """Generate multi-page PDF with results for each port/protocol combination"""
        import urllib.parse
        import urllib.request
        import ssl
        import tempfile
        from PyPDF2 import PdfMerger
        
        pdf_file = os.path.join(self.data_dir, "pdfs", f"{run_id}_report.pdf")
        os.makedirs(os.path.dirname(pdf_file), exist_ok=True, mode=0o775)
        
        # Get base URL from config (required)
        base_url = self.config.config.get('base_url')
        if not base_url:
            raise Exception("base_url not configured in config.json")
        
        # Step 1: Generate summary page
        summary_pdf = os.path.join(self.data_dir, "pdfs", f"{run_id}_summary.pdf")
        try:
            self.logger.log_info("Generating summary page")
            
            # Prepare form data for summary page
            sessions_dir = os.path.join(self.data_dir, "sessions", session_id)
            os.makedirs(sessions_dir, exist_ok=True, mode=0o775)  # Ensure directory exists
            form_data_file = os.path.join(sessions_dir, f"{run_id}_form.json")
            form_data = {
                'source_ip': self.last_source_ip if hasattr(self, 'last_source_ip') else 'N/A',
                'dest_ip': self.last_dest_ip if hasattr(self, 'last_dest_ip') else 'N/A',
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'run_id': run_id,  # Add the run_id/session_id
                'session_id': run_id  # Same as run_id for tracking
            }
            with open(form_data_file, 'w') as f:
                json.dump(form_data, f)
            
            # Prepare results list for summary page
            results_list_file = os.path.join(self.data_dir, "sessions", session_id, f"{run_id}_results_list.json")
            results_list = []
            for port, protocol, result_file in results_files:
                results_list.append({
                    'port': port,
                    'protocol': protocol,
                    'file': result_file
                })
            with open(results_list_file, 'w') as f:
                json.dump(results_list, f)
            
            # Run summary page generator with virtual environment
            summary_script = "/var/www/traceroute-web/scripts/generate_summary_page_reportlab.py"
            cmd = [
                os.path.join(self.venv_path, "bin", "python"),
                "-B", "-u", summary_script,
                "--form-data", form_data_file,
                "--results", results_list_file,
                "--output", summary_pdf
            ]
            
            # Use the same venv activation method as other scripts
            result = self._activate_venv_and_run(cmd, timeout=30)
            if result['success'] and os.path.exists(summary_pdf):
                self.logger.log_info(f"Summary page generated: {summary_pdf}")
            else:
                self.logger.log_warning(f"Summary page generation failed: {result.get('error', result.get('output', ''))}")
                summary_pdf = None
                
        except Exception as e:
            self.logger.log_warning(f"Failed to generate summary page: {str(e)}")
            summary_pdf = None
        
        # Step 2: Generate individual PDFs for each service using existing single-page generator
        individual_pdfs = []
        
        # Add summary page as first PDF if it was generated
        if summary_pdf and os.path.exists(summary_pdf):
            individual_pdfs.append(summary_pdf)
        
        for port, protocol, result_file in results_files:
            try:
                # Generate PDF for this service
                service_pdf = os.path.join(self.data_dir, "pdfs", f"{run_id}_{port}_{protocol}.pdf")
                
                # Build URL with parameters
                params = {
                    'trace': trace_file,
                    'results': result_file,
                    'output': service_pdf,
                    'service': f"{port}/{protocol}"  # Add service identifier
                }
                query_string = urllib.parse.urlencode(params)
                url = f"{base_url}/cgi-bin/generate_pdf.sh?{query_string}"
                
                self.logger.log_info(f"Generating PDF for {port}/{protocol}: {url}")
                
                # Create SSL context that doesn't verify certificates
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                
                # Make the request with SSL context
                with urllib.request.urlopen(url, timeout=30, context=ctx) as response:
                    # Check content type and read response
                    content_type = response.headers.get('content-type', '')
                    pdf_data = response.read()
                    
                    # Log what we received
                    self.logger.log_info(f"Response for {port}/{protocol}: content-type={content_type}, size={len(pdf_data)} bytes")
                    
                    if 'application/pdf' in content_type and len(pdf_data) > 0:
                        # Save the PDF
                        with open(service_pdf, 'wb') as f:
                            f.write(pdf_data)
                        individual_pdfs.append(service_pdf)
                        self.logger.log_info(f"PDF for {port}/{protocol} saved successfully")
                    elif len(pdf_data) == 0:
                        self.logger.log_error(f"PDF generation for {port}/{protocol}", "Received empty response")
                        # Try to diagnose the issue
                        self.logger.log_info(f"Response headers: {dict(response.headers)}")
                    else:
                        # Response was not PDF - treat as error
                        try:
                            error_msg = pdf_data.decode('utf-8')[:500]  # First 500 chars of error
                        except:
                            error_msg = f"Non-PDF response with content-type: {content_type}"
                        self.logger.log_error(f"PDF generation failed for {port}/{protocol}", error_msg)
                        # Continue with other services
                        
            except Exception as e:
                self.logger.log_error(f"Error generating PDF for {port}/{protocol}", str(e))
                # Continue with other services
        
        # Merge all PDFs into one
        if individual_pdfs:
            try:
                merger = PdfMerger()
                
                # Add each PDF to the merger
                for pdf in individual_pdfs:
                    merger.append(pdf)
                
                # Write the merged PDF
                merger.write(pdf_file)
                merger.close()
                
                self.logger.log_info(f"Merged {len(individual_pdfs)} PDFs into {pdf_file}")
                
                # Clean up individual PDFs
                for pdf in individual_pdfs:
                    try:
                        os.remove(pdf)
                    except:
                        pass
                
                return pdf_file
                
            except Exception as e:
                self.logger.log_error("Failed to merge PDFs", str(e))
                # Fall back to returning the first PDF if merge fails
                if individual_pdfs:
                    shutil.copy(individual_pdfs[0], pdf_file)
                    return pdf_file
                raise Exception(f"PDF merge failed: {str(e)}")
        else:
            raise Exception("No PDFs were generated successfully")
    
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
