#!/usr/bin/env -S python3 -B -u
"""
TSIM Hybrid Executor - Core execution engine
Direct execution, thread pools for I/O, process pools for CPU-bound tasks
"""

import os
import sys
import json
import time
import logging
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Callable
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, Future
import multiprocessing
import queue

from .tsim_timing_service import TsimTimingService
from .tsim_ksms_service import TsimKsmsService


def _tsim_init_worker():
    """Initializer for ProcessPool workers: disable bytecode and set cache dir."""
    try:
        import sys as _sys, os as _os
        _sys.dont_write_bytecode = True
        _os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
        _os.environ.setdefault('PYTHONPYCACHEPREFIX', '/dev/shm/tsim/pycache')
    except Exception:
        pass


class TsimHybridExecutor:
    """
    Hybrid executor using:
    - Direct execution for lightweight tasks
    - ThreadPoolExecutor for I/O-bound tasks (tsimsh commands)
    - ProcessPoolExecutor for CPU-bound tasks (PDF generation)
    """
    
    def __init__(self, config_service, progress_tracker=None, timing_service=None):
        """Initialize hybrid executor
        
        Args:
            config_service: TsimConfigService instance
            progress_tracker: Optional progress tracker instance
            timing_service: Optional timing service instance
        """
        self.config = config_service
        # Ensure child processes/execs don't write bytecode to install dirs
        try:
            os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
            os.environ.setdefault('PYTHONPYCACHEPREFIX', '/dev/shm/tsim/pycache')
            Path(os.environ['PYTHONPYCACHEPREFIX']).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.progress_tracker = progress_tracker
        # Ensure a timing service is available
        self.timing_service = timing_service or TsimTimingService()
        self.logger = logging.getLogger('tsim.hybrid_executor')
        
        # Paths
        self.tsimsh_path = config_service.tsimsh_path
        self.run_dir = Path('/dev/shm/tsim/runs')
        self.run_dir.mkdir(parents=True, exist_ok=True)
        
        # Thread pool for I/O-bound operations (tsimsh commands)
        self.thread_pool = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix='tsim-io'
        )
        
        # Process pool for CPU-bound operations (PDF generation)
        # Use initializer to disable bytecode in worker processes, and set env
        # Use 'spawn' context to be compatible with max_tasks_per_child on Python 3.11+
        # Fallback to default context without max_tasks_per_child if spawn unavailable
        try:
            mp_ctx = multiprocessing.get_context('spawn')
            self.process_pool = ProcessPoolExecutor(
                max_workers=2,
                max_tasks_per_child=10,  # Restart workers after 10 tasks to prevent memory leaks
                initializer=_tsim_init_worker,
                mp_context=mp_ctx
            )
        except Exception:
            # Fallback: omit max_tasks_per_child (not supported on 'fork')
            self.process_pool = ProcessPoolExecutor(
                max_workers=2,
                initializer=_tsim_init_worker
            )
        
        # Progress callback storage
        self.progress_callbacks = {}
        self.callback_lock = threading.Lock()
        
        self.logger.info("TsimHybridExecutor initialized with thread and process pools")

    # -----------------------------
    # Timing helpers
    # -----------------------------
    def _timer_id(self, run_id: str) -> str:
        return f"run_{run_id}"

    def _start_timing(self, run_id: str):
        try:
            self.timing_service.start_timer(self._timer_id(run_id))
        except Exception:
            pass

    def _checkpoint(self, run_id: str, name: str, details: str = None):
        try:
            self.timing_service.checkpoint(self._timer_id(run_id), name, details)
        except Exception:
            pass

    def _end_timing(self, run_id: str, run_dir: Path, extra: dict = None) -> dict:
        try:
            timing = self.timing_service.end_timer(self._timer_id(run_id))
        except Exception:
            timing = {}

        # Write per-run timing.json for later analysis
        try:
            timing_out = dict(timing) if isinstance(timing, dict) else {}
            if extra:
                timing_out['extra'] = extra
            out_path = Path(run_dir) / 'timing.json'
            with open(out_path, 'w') as f:
                json.dump(timing_out, f, indent=2)
        except Exception:
            pass

        # Log concise summary
        try:
            total = timing.get('total_elapsed') if isinstance(timing, dict) else None
            if total is not None:
                checkpoints = timing.get('checkpoints', [])
                summary = ', '.join([f"{c['name']}:{c.get('delta', 0):.3f}s" for c in checkpoints])
                self.logger.info(f"Timing {run_id}: total={total:.3f}s, {summary}")
        except Exception:
            pass

        return timing if isinstance(timing, dict) else {}
    
    def __del__(self):
        """Cleanup pools on deletion"""
        try:
            self.thread_pool.shutdown(wait=False)
            self.process_pool.shutdown(wait=False)
        except:
            pass
    
    def execute_full_test(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute complete test pipeline without subprocesses
        
        Args:
            params: Test parameters including:
                - run_id: Unique run identifier
                - source_ip: Source IP
                - dest_ip: Destination IP
                - port_protocol_list: List of (port, protocol) tuples
                - user_trace_data: Optional user trace data
                - analysis_mode: 'quick' or 'detailed' (optional)
                
        Returns:
            Dictionary with test results
        """
        # Continue with normal analysis (both test and production modes)
        # Quick/Detailed analysis mode will be handled within the normal flow
        run_id = params['run_id']
        run_dir = Path(params['run_dir'])
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize progress tracking
        self._update_progress(run_id, 'START', 'Starting test execution')
        self._start_timing(run_id)
        
        try:
            # Step 1: Execute trace (I/O bound - use thread)
            self._checkpoint(run_id, 'TRACE_START', f"{params['source_ip']}->{params['dest_ip']}")
            self._update_progress(run_id, 'MULTI_REACHABILITY_PHASE1_start', f"Path discovery from {params['source_ip']} to {params['dest_ip']}")
            trace_result = self._execute_trace(params, run_dir)
            # After obtaining the trace, compute exact expected step count based on analysis mode
            try:
                router_count = 0
                if trace_result.get('trace_file'):
                    with open(trace_result['trace_file'], 'r') as f:
                        td = json.load(f)
                        router_count = len([h for h in td.get('path', []) if h.get('is_router')])
                service_count = len(params.get('port_protocol_list', []))
                
                # Different step calculations for different analysis modes
                analysis_mode = params.get('analysis_mode', 'detailed')
                if analysis_mode == 'quick':
                    # Quick analysis steps: 
                    # 5 initial phases + router_count host creation steps + 4 KSMS phases + 3 completion phases
                    expected_steps = 5 + router_count + 4 + 3
                else:
                    # Detailed analysis steps (original formula)
                    expected_steps = 25 + (12 * service_count) + (2 * router_count)
                
                if self.progress_tracker:
                    try:
                        self.progress_tracker.set_expected_steps(params['run_id'], expected_steps)
                    except Exception:
                        pass
            except Exception:
                pass
            self._checkpoint(run_id, 'TRACE_DONE')
            if trace_result.get('trace_file'):
                # Count routers in trace
                try:
                    with open(trace_result['trace_file'], 'r') as f:
                        trace_data = json.load(f)
                        routers = [h for h in trace_data.get('path', []) if h.get('is_router')]
                        router_names = ', '.join([r.get('name', 'unknown') for r in routers])
                        self._update_progress(run_id, 'MULTI_REACHABILITY_PHASE1_complete', f"Found {len(routers)} routers: {router_names}")
                except:
                    self._update_progress(run_id, 'MULTI_REACHABILITY_PHASE1_complete', 'Path discovery completed')
            
            # Step 2: Execute reachability tests (I/O bound - use thread)
            self._checkpoint(run_id, 'REACHABILITY_START')
            self._update_progress(run_id, 'MULTI_REACHABILITY_PHASE2_start', 'Setting up simulation environment')
            params['trace_file'] = trace_result['trace_file']
            reach_result = self._execute_reachability(params, run_dir)
            self._checkpoint(run_id, 'REACHABILITY_DONE', f"services={len(params.get('port_protocol_list', []))}")
            self._update_progress(run_id, 'MULTI_REACHABILITY_PHASE4_complete', 'All service tests completed')
            
            # Step 3: Generate PDFs (CPU bound - use process pool)
            # Skip PDF generation for KSMS as it handles its own PDF generation
            analysis_mode = reach_result.get('analysis_mode', 'detailed')
            if analysis_mode == 'quick':
                # KSMS already generated PDF - extract the PDF path from results
                pdf_result = reach_result.get('results', {}).get('pdf_result', {})
                if pdf_result.get('success'):
                    final_pdf_path = pdf_result.get('pdf_path')
                    pdf_result = {'success': True, 'final_pdf': final_pdf_path}
                else:
                    pdf_result = {'success': False, 'error': 'KSMS PDF generation failed'}
            else:
                # Standard detailed analysis PDF generation
                self._checkpoint(run_id, 'PDF_START')
                self._update_progress(run_id, 'PDF_GENERATION', 'Generating PDF reports')
                params['result_files'] = reach_result.get('result_files', [])
                params['analysis_mode'] = analysis_mode
                pdf_result = self._execute_pdf_generation(params, run_dir)
                self._checkpoint(run_id, 'PDF_DONE')
                self._update_progress(run_id, 'PDF_COMPLETE', 'PDF generation completed')
            
            # Mark completion with PDF file and total timing
            final_pdf = pdf_result.get('final_pdf')
            if self.progress_tracker:
                self.progress_tracker.mark_complete(run_id, True, final_pdf)
            else:
                self._update_progress(run_id, 'COMPLETE', 'All tests completed successfully')
            
            self.logger.info(f"Test completed for {run_id} with PDF: {final_pdf}")
            
            timing = self._end_timing(run_id, run_dir, {'service_count': len(params.get('port_protocol_list', []))})
            return {
                'success': True,
                'run_id': run_id,
                'trace': trace_result,
                'reachability': reach_result,
                'pdf': pdf_result,
                'final_pdf': final_pdf,
                'timestamp': datetime.now().isoformat(),
                'timing': timing
            }
            
        except Exception as e:
            self.logger.error(f"Test execution failed for {run_id}: {e}")
            self._update_progress(run_id, 'ERROR', f'Test failed: {str(e)}')
            # Finalize timing even on error
            self._end_timing(run_id, run_dir, {'error': str(e)})
            raise
    
    def _execute_trace(self, params: Dict[str, Any], run_dir: Path) -> Dict[str, Any]:
        """Execute trace command directly
        
        Args:
            params: Test parameters
            run_dir: Run directory
            
        Returns:
            Trace results
        """
        run_id = params['run_id']
        
        # Check for user-provided trace data first
        if params.get('user_trace_data'):
            trace_file = run_dir / f"{run_id}.trace"
            trace_file.write_text(params['user_trace_data'])
            self.logger.info(f"Using user-provided trace data for {run_id}")
            return {'trace_file': str(trace_file)}
        
        # Execute tsimsh trace command with JSON output only
        source_ip = params['source_ip']
        dest_ip = params['dest_ip']
        # Use -j for JSON output, which should suppress warnings
        trace_command = f"trace -s {source_ip} -d {dest_ip} -j\n"
        
        self.logger.info(f"Executing trace for {run_id}: {source_ip} -> {dest_ip}")
        self.logger.info(f"Trace command: {trace_command.strip()}")
        
        # Run in thread pool for I/O operation
        future = self.thread_pool.submit(self._run_tsimsh_command, trace_command, run_id, str(run_dir))
        output = future.result(timeout=120)  # 2 minute timeout
        
        # Write complete trace output to debug file
        debug_file = run_dir / f"{run_id}_trace_debug.txt"
        try:
            with open(debug_file, 'w') as f:
                f.write(f"=== TRACE DEBUG OUTPUT FOR {run_id} ===\n")
                f.write(f"Command: {trace_command.strip()}\n")
                f.write(f"Output length: {len(output)} characters\n")
                f.write(f"Raw output:\n{output}\n")
                f.write("=== END RAW OUTPUT ===\n")
        except Exception as e:
            self.logger.error(f"Failed to write debug file: {e}")
        
        # Debug logging: log basic info only
        self.logger.info(f"Trace output length: {len(output)} characters - see {debug_file}")
        
        # Try to parse the JSON output for detailed logging
        try:
            import json
            trace_data = json.loads(output)
            self.logger.info(f"Trace JSON success field: {trace_data.get('success')}")
            path = trace_data.get('path', [])
            router_count = sum(1 for hop in path if hop.get('is_router', False))
            self.logger.info(f"Total routers found in trace: {router_count}")
            
            # Write parsed data to debug file
            with open(debug_file, 'a') as f:
                f.write(f"\n=== PARSED JSON DATA ===\n")
                f.write(f"Success: {trace_data.get('success')}\n")
                f.write(f"Source: {trace_data.get('source')}\n")
                f.write(f"Destination: {trace_data.get('destination')}\n")
                f.write(f"Path length: {len(path)}\n")
                f.write(f"Router count: {router_count}\n")
                for i, hop in enumerate(path):
                    f.write(f"Hop {i}: {hop}\n")
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse trace JSON output for {run_id}: {e}")
            try:
                with open(debug_file, 'a') as f:
                    f.write(f"\n=== JSON PARSE ERROR ===\n")
                    f.write(f"Error: {e}\n")
                    f.write(f"Output that failed to parse:\n{output}\n")
            except:
                pass
        except Exception as e:
            self.logger.error(f"Error analyzing trace output for {run_id}: {e}")
        
        # Save trace output
        trace_file = run_dir / f"{run_id}.trace"
        trace_file.write_text(output)
        
        return {'trace_file': str(trace_file), 'output': output}
    
    def _execute_reachability(self, params: Dict[str, Any], run_dir: Path) -> Dict[str, Any]:
        """Execute reachability tests based on analysis mode
        
        Args:
            params: Test parameters including analysis_mode
            run_dir: Run directory
            
        Returns:
            Reachability test results
        """
        # Create results directory
        results_dir = run_dir / 'results'
        results_dir.mkdir(exist_ok=True)
        
        # Get analysis mode (default to detailed for backward compatibility)  
        analysis_mode = params.get('analysis_mode', 'detailed')
        
        if analysis_mode == 'quick':
            # Use KSMS for quick analysis
            self.logger.info(f"Starting KSMS quick analysis for {params['run_id']}")
            return self._execute_ksms_analysis(params, results_dir)
        else:
            # Use MultiServiceTester for detailed analysis
            self.logger.info(f"Starting detailed analysis for {params['run_id']}")
            return self._execute_detailed_analysis(params, results_dir)
    
    def _execute_ksms_analysis(self, params: Dict[str, Any], results_dir: Path) -> Dict[str, Any]:
        """Execute KSMS quick analysis
        
        Args:
            params: Test parameters
            results_dir: Results directory
            
        Returns:
            KSMS analysis results
        """
        # Initialize KSMS service
        ksms_service = TsimKsmsService(self.config)
        
        # Set up progress callback
        def ksms_progress_callback(phase: str, message: str = ""):
            self._update_progress(params['run_id'], f'KSMS_{phase}', message)
        
        # Execute KSMS fast scan with progress callback
        # Set progress callback - add MULTI_REACHABILITY_ prefix to match detailed analysis
        progress_callback = lambda phase, msg: self._update_progress(
            params['run_id'], f'MULTI_REACHABILITY_{phase}', msg
        )
        
        try:
            # Execute KSMS in thread pool (I/O bound)
            future = self.thread_pool.submit(
                ksms_service.execute_quick_analysis,
                params,
                progress_callback
            )
            results = future.result(timeout=300)  # 5 minute timeout
            
            # KSMS service handles its own completion progress message
            
            # Save results to JSON file
            result_file = results_dir / f"{params['run_id']}_ksms_results.json"
            result_file.write_text(json.dumps(results, indent=2))
            
            return {
                'results': results,
                'result_files': [str(result_file)],
                'results_dir': str(results_dir),
                'analysis_mode': 'quick'
            }
            
        except Exception as e:
            self.logger.error(f"KSMS execution failed for {params['run_id']}: {e}")
            self._update_progress(params['run_id'], 'KSMS_ERROR', f'KSMS failed: {str(e)}')
            raise
    
    def _execute_detailed_analysis(self, params: Dict[str, Any], results_dir: Path) -> Dict[str, Any]:
        """Execute detailed analysis using MultiServiceTester
        
        Args:
            params: Test parameters
            results_dir: Results directory
            
        Returns:
            Detailed analysis results
        """
        # Import the network reachability test module
        from scripts.network_reachability_test_multi import MultiServiceTester
        
        # Initialize tester
        tester = MultiServiceTester(
            source_ip=params['source_ip'],
            source_port=params.get('source_port'),
            dest_ip=params['dest_ip'],
            services=params['port_protocol_list'],  # MultiServiceTester expects 'services'
            output_dir=str(results_dir),
            trace_file=params['trace_file'],
            verbose=1
        )
        
        # Set progress callback - add MULTI_REACHABILITY_ prefix to match CGI
        tester.progress_callback = lambda phase, msg: self._update_progress(
            params['run_id'], f'MULTI_REACHABILITY_{phase}', msg
        )
        
        # Execute tests in thread pool (I/O bound)
        self.logger.info(f"Starting detailed reachability tests for {params['run_id']}")
        future = self.thread_pool.submit(tester.run)
        results = future.result(timeout=300)  # 5 minute timeout
        
        # Collect result files - MultiServiceTester saves as {port}_{protocol}_results.json
        result_files = []
        for port, protocol in params['port_protocol_list']:
            # Try both naming patterns
            result_file1 = results_dir / f"{params['run_id']}_{port}_{protocol}_results.json"
            result_file2 = results_dir / f"{port}_{protocol}_results.json"
            
            if result_file1.exists():
                result_files.append(str(result_file1))
            elif result_file2.exists():
                result_files.append(str(result_file2))
        
        return {
            'results': results,
            'result_files': result_files,
            'results_dir': str(results_dir),
            'analysis_mode': 'detailed'
        }
    
    def _execute_pdf_generation(self, params: Dict[str, Any], run_dir: Path) -> Dict[str, Any]:
        """Execute PDF generation in process pool
        
        Args:
            params: Test parameters
            run_dir: Run directory
            
        Returns:
            PDF generation results
        """
        try:
            # This will be executed in process pool for CPU-bound operation
            self.logger.info(f"Starting PDF generation for {params['run_id']}")
            future = self.process_pool.submit(
                self._generate_pdfs_worker,
                params,
                str(run_dir)
            )
            
            result = future.result(timeout=120)  # 2 minute timeout
            self.logger.info(f"PDF generation completed for {params['run_id']}: {result}")
            return result
        except Exception as e:
            self.logger.error(f"PDF generation failed for {params['run_id']}: {e}")
            # Return empty result on failure
            return {
                'success': False,
                'error': str(e),
                'pdf_files': []
            }
    
    @staticmethod
    def _generate_pdfs_worker(params: Dict[str, Any], run_dir_str: str) -> Dict[str, Any]:
        """Worker function for PDF generation (runs in process pool)
        
        Args:
            params: Test parameters
            run_dir_str: Run directory path as string
            
        Returns:
            PDF generation results
        """
        import sys
        from pathlib import Path
        
        run_dir = Path(run_dir_str)
        run_id = params['run_id']
        pdf_files = []
        
        # Step 1: Generate summary page if we have summary data
        if params.get('summary'):
            try:
                # Create form data and results list files
                form_data_file = run_dir / f"{run_id}_form.json"
                with open(form_data_file, 'w') as f:
                    json.dump({
                        'source_ip': params['source_ip'],
                        'dest_ip': params['dest_ip'],
                        'timestamp': params['summary']['timestamp'],
                        'run_id': run_id,
                        'session_id': run_id
                    }, f)
                
                results_list_file = run_dir / f"{run_id}_results_list.json"
                results_list = []
                for result_file in params.get('result_files', []):
                    parts = Path(result_file).stem.split('_')
                    if len(parts) >= 3:
                        results_list.append({
                            'port': parts[-3],
                            'protocol': parts[-2],
                            'file': result_file
                        })
                with open(results_list_file, 'w') as f:
                    json.dump(results_list, f)
                
                # Generate summary PDF
                summary_pdf = run_dir / f"{run_id}_summary.pdf"
                from scripts.generate_summary_page_reportlab import create_summary_page
                create_summary_page(str(summary_pdf), 
                                  json.loads(form_data_file.read_text()),
                                  [(r['port'], r['protocol'], r['file']) for r in results_list])
                
                if summary_pdf.exists():
                    pdf_files.append(str(summary_pdf))
            except Exception as e:
                print(f"Failed to generate summary: {e}", file=sys.stderr)
        
        # Step 2: Generate individual service PDFs (direct call, no subprocess)
        try:
            from scripts.visualize_reachability import create_networkx_visualization, load_json_file
        except Exception as e:
            print(f"Visualizer import failed: {e}", file=sys.stderr)
            create_networkx_visualization = None
            load_json_file = None

        trace_data = None
        if create_networkx_visualization and load_json_file:
            try:
                trace_data = load_json_file(params['trace_file']) if params.get('trace_file') else None
            except Exception as e:
                print(f"Failed to load trace file: {e}", file=sys.stderr)
                trace_data = None

        for result_file in params.get('result_files', []):
            try:
                result_path = Path(result_file)
                stem = result_path.stem
                if '_results' not in stem:
                    continue
                parts = stem.replace('_results', '').split('_')
                if len(parts) < 2:
                    continue
                port = parts[-2]
                protocol = parts[-1]
                service_pdf = run_dir / f"{run_id}_{port}_{protocol}.pdf"

                if create_networkx_visualization and load_json_file and trace_data:
                    try:
                        results_data = load_json_file(result_file)
                        results_data.setdefault('service_tested', f"{port}/{protocol}")
                        create_networkx_visualization(trace_data, results_data, str(service_pdf))
                        if service_pdf.exists():
                            pdf_files.append(str(service_pdf))
                        continue
                    except Exception as e:
                        print(f"Direct PDF render failed, skipping: {e}", file=sys.stderr)
                        continue
            except Exception as e:
                print(f"Failed to generate PDF for {result_file}: {e}", file=sys.stderr)
        
        # Step 3: Merge PDFs
        final_pdf = None
        if len(pdf_files) > 0:
            try:
                final_pdf = run_dir / f"{run_id}_report.pdf"
                
                if len(pdf_files) == 1:
                    # Just copy the single PDF
                    import shutil
                    shutil.copy2(pdf_files[0], str(final_pdf))
                else:
                    # Merge multiple PDFs
                    merge_list_file = run_dir / f"{run_id}_merge_list.json"
                    with open(merge_list_file, 'w') as f:
                        json.dump(pdf_files, f)
                    
                    from scripts.merge_pdfs import merge_pdfs
                    if merge_pdfs(pdf_files, str(final_pdf)):
                        merge_list_file.unlink()
                
                if final_pdf.exists():
                    return {
                        'success': True,
                        'final_pdf': str(final_pdf),
                        'pdf_files': pdf_files
                    }
            except Exception as e:
                print(f"Failed to merge PDFs: {e}", file=sys.stderr)
        
        return {
            'success': False,
            'error': 'PDF generation failed',
            'pdf_files': pdf_files
        }
    
    def _run_tsimsh_command(self, command: str, run_id: str, run_dir: str = None) -> str:
        """Run tsimsh command directly (no bash wrapper)
        
        Args:
            command: Command to execute
            run_id: Run identifier for logging
            
        Returns:
            Command output
        """
        try:
            # Set environment to point to config file and suppress bytecode
            env = os.environ.copy()
            env['TRACEROUTE_SIMULATOR_CONF'] = self.config.get('traceroute_simulator_conf', 
                                                              '/opt/tsim/wsgi/conf/traceroute_simulator.yaml')
            env.setdefault('PYTHONDONTWRITEBYTECODE', '1')
            env.setdefault('PYTHONPYCACHEPREFIX', '/dev/shm/tsim/pycache')
            
            # Debug logging: log the execution details
            self.logger.info(f"Running tsimsh command for {run_id}")
            self.logger.info(f"tsimsh path: {self.tsimsh_path}")
            self.logger.info(f"Command input: {repr(command)}")
            self.logger.info(f"Environment TRACEROUTE_SIMULATOR_CONF: {env.get('TRACEROUTE_SIMULATOR_CONF')}")
            self.logger.info(f"Environment TRACEROUTE_SIMULATOR_RAW_FACTS: {env.get('TRACEROUTE_SIMULATOR_RAW_FACTS')}")
            
            # Direct execution - capture stdout only, let stderr go to logs
            result = subprocess.run(
                [self.tsimsh_path],
                input=command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,  # Capture but don't mix with stdout
                text=True,
                timeout=120,
                env=env
            )
            
            # Write complete stderr to debug file if available
            if run_dir:
                stderr_file = Path(run_dir) / f"{run_id}_tsimsh_stderr.txt"
                try:
                    with open(stderr_file, 'w') as f:
                        f.write(f"=== TSIMSH STDERR FOR {run_id} ===\n")
                        f.write(f"Return code: {result.returncode}\n")
                        f.write(f"Stderr length: {len(result.stderr)} characters\n")
                        f.write(f"Stderr content:\n{result.stderr}\n")
                except Exception:
                    pass
            
            # Debug logging: log the execution results
            self.logger.info(f"tsimsh return code for {run_id}: {result.returncode}")
            self.logger.info(f"tsimsh stdout length for {run_id}: {len(result.stdout)} characters")
            self.logger.info(f"tsimsh stderr length for {run_id}: {len(result.stderr)} characters")
            
            if result.returncode != 0:
                self.logger.error(f"tsimsh command failed for {run_id}: {result.stderr}")
                raise RuntimeError(f"tsimsh failed: {result.stderr}")
            
            # Log stderr warnings separately if present
            if result.stderr:
                self.logger.warning(f"tsimsh warnings for {run_id}: {result.stderr}")
            
            return result.stdout
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"tsimsh command timed out for {run_id}")
            raise RuntimeError("tsimsh command timed out")
        except Exception as e:
            self.logger.error(f"tsimsh command error for {run_id}: {e}")
            raise
    
    def _update_progress(self, run_id: str, phase: str, message: str = ""):
        """Update progress tracking
        
        Args:
            run_id: Run identifier
            phase: Progress phase
            message: Progress message
        """
        if self.progress_tracker:
            self.progress_tracker.log_phase(run_id, phase, message)
        
        # Also log for debugging
        self.logger.debug(f"Progress [{run_id}]: {phase} - {message}")
    
    def cleanup(self):
        """Clean up resources"""
        self.logger.info("Shutting down executor pools")
        self.thread_pool.shutdown(wait=True, cancel_futures=True)
        self.process_pool.shutdown(wait=True, cancel_futures=True)
