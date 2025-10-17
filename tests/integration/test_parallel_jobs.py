#!/usr/bin/env python3
"""
Integration test script for parallel job execution.

Tests various scenarios of quick/detailed jobs with router conflicts.
Supports run and check modes for regression testing.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


@dataclass
class JobConfig:
    """Configuration for a single job"""
    trace_file: str
    analysis_mode: str  # 'quick' or 'detailed'
    dest_ports: List[str]  # Support both "80" and "80/tcp" or "1000/udp" format

    @classmethod
    def from_line(cls, line: str) -> 'JobConfig':
        """Parse job config from semicolon-separated line"""
        parts = [p.strip() for p in line.split(';')]
        if len(parts) != 3:
            raise ValueError(f"Invalid config line: {line}")

        trace_file = parts[0]
        analysis_mode = parts[1]
        # Keep port specs as strings to support "port" or "port/protocol" format
        dest_ports = [p.strip() for p in parts[2].split(',')]

        return cls(trace_file, analysis_mode, dest_ports)


@dataclass
class JobResult:
    """Result of a single job execution"""
    job_id: int
    run_id: str
    trace_file: str
    analysis_mode: str
    dest_ports: List[str]  # Support both "80" and "80/tcp" or "1000/udp" format
    submit_time: float
    complete_time: Optional[float]
    duration: Optional[float]  # HTTP request duration
    server_duration: Optional[float] = None  # Actual job execution time on server
    curl_exit_code: int = 0
    curl_output: str = ''
    pdf_path: Optional[str] = None
    json_path: Optional[str] = None
    status: str = 'SUCCESS'  # 'SUCCESS', 'FAILED', 'TIMEOUT'
    error_message: Optional[str] = None
    results_valid: Optional[bool] = None  # True if all results are valid YES/NO
    results_pattern: Optional[str] = None  # Actual pattern found (e.g., "NO/YES")


@dataclass
class ScenarioResult:
    """Result of entire scenario execution"""
    scenario_name: str
    jobs: List[JobResult]
    start_time: float
    end_time: float
    total_duration: float
    success_count: int
    failed_count: int
    timeout_count: int


class IntegrationTester:
    """Integration test executor for parallel jobs"""

    def __init__(self, base_url: str, username: str, password: str,
                 output_dir: Path, timeout: int = 600, insecure: bool = False):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.output_dir = output_dir
        self.timeout = timeout
        self.insecure = insecure
        self.cookie_file = self.output_dir / '.session_cookie'

        # Create output directory structure
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Login to get session cookie
        self._login()

    def _login(self):
        """Login to get session cookie"""
        # Build curl command for login
        curl_cmd = ['curl', '-s', '-w', '\\n%{http_code}', '-c', str(self.cookie_file)]

        if self.insecure:
            curl_cmd.append('-k')

        curl_cmd.extend([
            '-L',  # Follow redirects
            '-X', 'POST',
            '-F', f'username={self.username}',
            '-F', f'password={self.password}',
            f'{self.base_url}/login'
        ])

        try:
            result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise RuntimeError(f"Login failed: curl exit code {result.returncode}")

            # Check if login succeeded
            lines = result.stdout.strip().split('\n')
            http_code = lines[-1] if lines else '000'

            # Check cookie file exists and has session cookie
            if not self.cookie_file.exists():
                raise RuntimeError("Login failed: no cookie file created")

            cookie_content = self.cookie_file.read_text()
            if not cookie_content.strip():
                raise RuntimeError("Login failed: empty cookie file")

            print(f"Login successful (HTTP {http_code})", file=sys.stderr)
        except Exception as e:
            raise RuntimeError(f"Login failed: {e}")

    def submit_job(self, job_id: int, config: JobConfig) -> JobResult:
        """Submit a single job via curl"""

        # Read trace file
        with open(config.trace_file, 'r') as f:
            trace_data = f.read()

        # Extract source_ip and dest_ip from trace file
        try:
            trace_json = json.loads(trace_data)
            source_ip = trace_json.get('source', '')
            dest_ip = trace_json.get('destination', '')

            if not source_ip or not dest_ip:
                raise ValueError("source or destination not found in trace file")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"ERROR: Failed to extract IPs from trace file: {e}", file=sys.stderr)
            return JobResult(
                job_id=job_id,
                run_id='ERROR',
                trace_file=config.trace_file,
                analysis_mode=config.analysis_mode,
                dest_ports=config.dest_ports,
                submit_time=time.time(),
                complete_time=time.time(),
                duration=0,
                curl_exit_code=1,
                curl_output='',
                pdf_path=None,
                json_path=None,
                status='FAILED',
                error_message=f"Failed to extract IPs from trace: {e}"
            )

        # Prepare form data
        # Always use port_mode=manual for CLI scripts (quick mode is for web browser only)
        # Port format supports:
        # - Just port number (e.g., "80") -> add default_protocol ("/tcp")
        # - Port/protocol (e.g., "80/udp") -> use as-is
        default_protocol = 'tcp'
        port_specs = []
        for p in config.dest_ports:
            p_str = str(p)
            # If port already has /protocol, use as-is
            if '/' in p_str:
                port_specs.append(p_str)
            else:
                # Just a port number, add default protocol
                port_specs.append(f"{p_str}/{default_protocol}")

        form_data = {
            'source_ip': source_ip,
            'dest_ip': dest_ip,
            'source_port': '',
            'port_mode': 'manual',
            'dest_ports': ','.join(port_specs),
            'default_protocol': default_protocol,
            'analysis_mode': config.analysis_mode,
            'user_trace_data': trace_data
        }

        # Build curl command with session cookie
        # Use -D to dump headers so we can extract Location header
        headers_file = self.output_dir / f'.headers_{job_id}'
        curl_cmd = [
            'curl', '-s', '-D', str(headers_file), '-w', '\\n%{http_code}',
            '-b', str(self.cookie_file),
            '-X', 'POST'
        ]

        # Add insecure flag if needed (skip SSL verification)
        if self.insecure:
            curl_cmd.append('-k')

        # Add form fields
        for key, value in form_data.items():
            curl_cmd.extend(['-F', f'{key}={value}'])

        curl_cmd.append(f'{self.base_url}/main')

        # Execute curl
        submit_time = time.time()
        try:
            result = subprocess.run(
                curl_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            exit_code = result.returncode
            output = result.stdout

            # Parse response - curl -w adds \n%{http_code} to output
            # For empty responses (like 302 redirects), we only get the http code
            lines = output.strip().split('\n')
            if len(lines) >= 1 and lines[-1].isdigit():
                http_code = lines[-1]
                response_body = '\n'.join(lines[:-1]) if len(lines) > 1 else ''
            else:
                http_code = '000'
                response_body = output

            # Parse headers to get Location (for redirect with run_id)
            run_id = 'UNKNOWN'
            status = 'FAILED'
            error_msg = None

            if headers_file.exists():
                headers = headers_file.read_text()

                # Check for redirect with Location header
                if http_code == '302':
                    # Extract run_id from Location header
                    # Format: Location: /progress.html?id=<run_id>
                    for line in headers.split('\n'):
                        if line.lower().startswith('location:'):
                            location = line.split(':', 1)[1].strip()
                            # Extract id parameter
                            if '?id=' in location:
                                run_id = location.split('?id=')[1].split('&')[0]
                                status = 'SUCCESS'
                                break

                # Clean up headers file
                headers_file.unlink()

            # If we got a JSON response instead of redirect
            if status == 'FAILED' and response_body and http_code != '302':
                try:
                    response_json = json.loads(response_body)
                    if isinstance(response_json, dict):
                        run_id = response_json.get('run_id', 'UNKNOWN')
                        if http_code == '200':
                            status = 'SUCCESS'
                        error_msg = response_json.get('error')
                except (json.JSONDecodeError, ValueError):
                    error_msg = f"HTTP {http_code}: {response_body[:200]}"

            # Debug output
            if status == 'SUCCESS':
                print(f"Job {job_id} submitted: run_id={run_id}", file=sys.stderr)
            else:
                print(f"Job {job_id} failed: HTTP {http_code}, {error_msg or 'Unknown error'}", file=sys.stderr)

            return JobResult(
                job_id=job_id,
                run_id=run_id,
                trace_file=config.trace_file,
                analysis_mode=config.analysis_mode,
                dest_ports=config.dest_ports,
                submit_time=submit_time,
                complete_time=time.time(),
                duration=time.time() - submit_time,
                curl_exit_code=exit_code,
                curl_output=output,
                pdf_path=None,  # Will be filled later
                json_path=None,  # Will be filled later
                status=status,
                error_message=error_msg
            )

        except subprocess.TimeoutExpired:
            return JobResult(
                job_id=job_id,
                run_id='TIMEOUT',
                trace_file=config.trace_file,
                analysis_mode=config.analysis_mode,
                dest_ports=config.dest_ports,
                submit_time=submit_time,
                complete_time=time.time(),
                duration=self.timeout,
                curl_exit_code=-1,
                curl_output='',
                pdf_path=None,
                json_path=None,
                status='TIMEOUT',
                error_message=f'Job exceeded timeout of {self.timeout}s'
            )
        except Exception as e:
            import traceback
            error_details = f"{str(e)}\n{traceback.format_exc()}"
            print(f"ERROR in submit_job: {error_details}", file=sys.stderr)
            return JobResult(
                job_id=job_id,
                run_id='ERROR',
                trace_file=config.trace_file,
                analysis_mode=config.analysis_mode,
                dest_ports=config.dest_ports,
                submit_time=submit_time,
                complete_time=time.time(),
                duration=time.time() - submit_time,
                curl_exit_code=-1,
                curl_output='',
                pdf_path=None,
                json_path=None,
                status='FAILED',
                error_message=str(e)
            )

    def _wait_for_jobs_completion(self, results: List[JobResult], poll_interval: float = 1.0, max_wait: float = 600.0):
        """Wait for all jobs to complete on the server by polling progress.json"""

        pending_jobs = [r for r in results if r.status == 'SUCCESS' and r.run_id != 'UNKNOWN']

        if not pending_jobs:
            return

        start_wait = time.time()
        completed_count = 0

        while pending_jobs and (time.time() - start_wait) < max_wait:
            for job in list(pending_jobs):
                progress_file = Path(f'/dev/shm/tsim/runs/{job.run_id}/progress.json')

                if not progress_file.exists():
                    time.sleep(0.1)
                    continue

                try:
                    with open(progress_file, 'r') as f:
                        progress_data = json.load(f)

                    if progress_data.get('complete'):
                        completed_count += 1
                        pending_jobs.remove(job)
                        print(f"  Job {job.job_id} completed ({completed_count}/{len(results)})")
                except Exception:
                    pass  # File might be being written, try again next iteration

            if pending_jobs:
                time.sleep(poll_interval)

        if pending_jobs:
            print(f"  Warning: {len(pending_jobs)} jobs did not complete within {max_wait}s")

    def collect_results(self, result: JobResult, scenario_dir: Path) -> JobResult:
        """Collect PDF and JSON files for completed job"""

        if result.status != 'SUCCESS' or result.run_id == 'UNKNOWN':
            return result

        # Read server-side execution time from progress.json
        json_dir = Path('/dev/shm/tsim/runs') / result.run_id
        progress_file = json_dir / 'progress.json'
        if progress_file.exists():
            try:
                with open(progress_file, 'r') as f:
                    progress_data = json.load(f)
                phases = progress_data.get('phases', [])
                if phases:
                    first_timestamp = phases[0]['timestamp']
                    last_timestamp = phases[-1]['timestamp']
                    total_duration = last_timestamp - first_timestamp

                    # For KSMS quick analysis, exclude thread pool queue wait time
                    # Queue wait is the gap between PHASE2_start and PHASE2_ksms_start
                    thread_pool_wait = 0
                    phase2_start = None
                    phase2_ksms_start = None

                    for phase in phases:
                        if phase['phase'] == 'MULTI_REACHABILITY_PHASE2_start':
                            phase2_start = phase['timestamp']
                        elif phase['phase'] == 'MULTI_REACHABILITY_PHASE2_ksms_start':
                            phase2_ksms_start = phase['timestamp']
                            break

                    if phase2_start and phase2_ksms_start:
                        thread_pool_wait = phase2_ksms_start - phase2_start

                    # Actual execution time = total time - queue wait
                    result.server_duration = total_duration - thread_pool_wait
            except Exception as e:
                pass  # Keep server_duration as None if we can't read it

        # Look for PDF file
        pdf_pattern = f"*{result.run_id}*.pdf"
        pdf_files = list(Path('/dev/shm/tsim/results').glob(pdf_pattern))

        if pdf_files:
            # Copy PDF to scenario directory
            pdf_src = pdf_files[0]
            pdf_dst = scenario_dir / pdf_src.name
            try:
                shutil.copy2(pdf_src, pdf_dst)
                result.pdf_path = str(pdf_dst)
            except Exception as e:
                result.error_message = f"Failed to copy PDF: {e}"

        # Look for JSON results and copy them
        if json_dir.exists():
            json_dst_dir = scenario_dir / 'runs' / result.run_id
            json_dst_dir.mkdir(parents=True, exist_ok=True)

            try:
                # Copy all JSON files
                for json_file in json_dir.glob('*.json'):
                    shutil.copy2(json_file, json_dst_dir / json_file.name)

                result.json_path = str(json_dst_dir)

                # Validate results pattern
                self._validate_results(result, json_dst_dir)

            except Exception as e:
                result.error_message = f"Failed to copy JSON: {e}"

        return result

    def _validate_results(self, result: JobResult, json_dir: Path):
        """Validate that all results are either YES or NO"""

        # Find results JSON file
        results_files = list(json_dir.glob('*_results.json'))
        if not results_files:
            result.results_valid = None
            result.results_pattern = "NO_FILE"
            return

        results_file = results_files[0]

        try:
            with open(results_file, 'r') as f:
                results_data = json.load(f)

            # Check for error
            if 'error' in results_data:
                result.results_valid = False
                result.results_pattern = f"ERROR: {results_data['error']}"
                return

            # Extract KSMS results in order
            tests = results_data.get('tests', [])
            if not tests:
                result.results_valid = False
                result.results_pattern = "NO_TESTS"
                return

            # Build actual pattern from KSMS original results (YES/NO)
            pattern_parts = []
            for test in tests:
                ksms_result = test.get('ksms_original_result', 'UNKNOWN')
                # Validate each result is YES or NO
                if ksms_result not in ('YES', 'NO'):
                    result.results_valid = False
                    result.results_pattern = f"INVALID: {ksms_result}"
                    return
                pattern_parts.append(ksms_result)

            actual_pattern = "/".join(pattern_parts)
            result.results_pattern = actual_pattern

            # All results are valid if we got here (all YES or NO)
            result.results_valid = True

        except Exception as e:
            result.results_valid = False
            result.results_pattern = f"PARSE_ERROR: {str(e)}"

    def run_scenario(self, scenario_name: str, jobs: List[JobConfig],
                     parallel: bool = True) -> ScenarioResult:
        """Run a complete test scenario"""

        print(f"\n{'='*60}")
        print(f"Running scenario: {scenario_name}")
        print(f"Jobs: {len(jobs)}")
        print(f"Parallel: {parallel}")
        print(f"{'='*60}\n")

        # Create scenario directory
        scenario_dir = self.output_dir / scenario_name
        scenario_dir.mkdir(parents=True, exist_ok=True)

        start_time = time.time()
        results = []

        if parallel:
            # Submit jobs with 1 second delay between each to preserve queue order
            # This prevents the scheduler from reordering jobs that arrive at the same time
            with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
                futures = {}
                for i, job in enumerate(jobs):
                    # Add 1 second delay before submitting next job
                    if i > 0:
                        time.sleep(1)
                    future = executor.submit(self.submit_job, i, job)
                    futures[future] = i

                for future in as_completed(futures):
                    job_id = futures[future]
                    try:
                        result = future.result()
                        ports_str = ','.join(result.dest_ports)
                        print(f"Job {job_id} ({result.analysis_mode}, {ports_str}): {result.status} "
                              f"(run_id: {result.run_id}, duration: {result.duration:.2f}s)")
                        results.append(result)
                    except Exception as e:
                        print(f"Job {job_id} failed with exception: {e}")
        else:
            # Submit jobs sequentially
            for i, job in enumerate(jobs):
                result = self.submit_job(i, job)
                ports_str = ','.join(result.dest_ports)
                print(f"Job {i} ({result.analysis_mode}, {ports_str}): {result.status} "
                      f"(run_id: {result.run_id}, duration: {result.duration:.2f}s)")
                results.append(result)

        # Wait for all jobs to complete on server
        print("\nWaiting for jobs to complete on server...")
        self._wait_for_jobs_completion(results)

        # Collect results
        print("\nCollecting results...")
        for i, result in enumerate(results):
            results[i] = self.collect_results(result, scenario_dir)

        end_time = time.time()

        # Calculate statistics
        success_count = sum(1 for r in results if r.status == 'SUCCESS')
        failed_count = sum(1 for r in results if r.status == 'FAILED')
        timeout_count = sum(1 for r in results if r.status == 'TIMEOUT')

        scenario_result = ScenarioResult(
            scenario_name=scenario_name,
            jobs=results,
            start_time=start_time,
            end_time=end_time,
            total_duration=end_time - start_time,
            success_count=success_count,
            failed_count=failed_count,
            timeout_count=timeout_count
        )

        # Save meta JSON
        self.save_meta_json(scenario_result, scenario_dir)

        # Print summary
        print(f"\nScenario '{scenario_name}' completed:")
        print(f"  Total duration: {scenario_result.total_duration:.2f}s")
        print(f"  Success: {success_count}/{len(jobs)}")
        print(f"  Failed: {failed_count}/{len(jobs)}")
        print(f"  Timeout: {timeout_count}/{len(jobs)}")

        # Print timing statistics
        self._print_timing_statistics(scenario_result)

        # Print validation summary
        self._print_validation_summary(scenario_result)

        return scenario_result

    def _print_timing_statistics(self, result: ScenarioResult):
        """Print detailed timing statistics"""

        # Collect server-side execution times (actual job execution on server)
        server_durations = [job.server_duration for job in result.jobs if job.server_duration is not None]

        if not server_durations:
            return

        # Calculate statistics
        server_durations_sorted = sorted(server_durations)
        min_time = min(server_durations)
        max_time = max(server_durations)
        avg_time = sum(server_durations) / len(server_durations)
        median_time = server_durations_sorted[len(server_durations_sorted) // 2]

        print(f"\n  Job Execution Times (server-side):")
        print(f"    Min:     {min_time:.2f}s")
        print(f"    Max:     {max_time:.2f}s")
        print(f"    Average: {avg_time:.2f}s")
        print(f"    Median:  {median_time:.2f}s")

        # Calculate wall-clock time: earliest job start to latest job end
        # Read actual server-side timestamps from progress.json files
        job_times = []
        run_dir = Path('/dev/shm/tsim/runs')
        for job in result.jobs:
            progress_file = run_dir / job.run_id / 'progress.json'
            if progress_file.exists():
                try:
                    with open(progress_file, 'r') as f:
                        progress_data = json.load(f)
                    phases = progress_data.get('phases', [])
                    if phases:
                        start = phases[0]['timestamp']
                        end = phases[-1]['timestamp']
                        job_times.append((start, end))
                except Exception:
                    pass

        if job_times:
            first_start = min(t[0] for t in job_times)
            last_end = max(t[1] for t in job_times)
            wall_clock = last_end - first_start

            print(f"\n  Wall-clock Time (first job start → last job end):")
            print(f"    {wall_clock:.2f}s")

            # Calculate parallelism factor
            total_sequential_time = sum(server_durations)
            if wall_clock > 0:
                parallelism = total_sequential_time / wall_clock
                efficiency = (parallelism / len(server_durations)) * 100
                print(f"\n  Parallelism:")
                print(f"    Speedup:    {parallelism:.1f}x")
                print(f"    Sequential: {total_sequential_time:.2f}s")
                print(f"    Parallel:   {wall_clock:.2f}s")
                print(f"    Efficiency: {efficiency:.0f}%")

    def _print_validation_summary(self, result: ScenarioResult):
        """Print validation summary for job results"""

        # Collect validation results
        valid_jobs = []
        invalid_jobs = []
        unvalidated_jobs = []

        for job in result.jobs:
            if job.results_valid is None:
                unvalidated_jobs.append(job)
            elif job.results_valid:
                valid_jobs.append(job)
            else:
                invalid_jobs.append(job)

        # Print summary
        print(f"\n  Results Validation:")
        print(f"    Valid:       {len(valid_jobs)}/{len(result.jobs)}")
        print(f"    Invalid:     {len(invalid_jobs)}/{len(result.jobs)}")
        print(f"    Unvalidated: {len(unvalidated_jobs)}/{len(result.jobs)}")

        # Print details for invalid results
        if invalid_jobs:
            print(f"\n  Invalid Results:")
            for job in invalid_jobs:
                actual = job.results_pattern
                print(f"    Job {job.job_id}: {actual}")

    def save_meta_json(self, result: ScenarioResult, scenario_dir: Path):
        """Save scenario metadata to JSON"""

        meta = {
            'scenario_name': result.scenario_name,
            'timestamp': datetime.fromtimestamp(result.start_time).isoformat(),
            'total_duration_seconds': result.total_duration,
            'statistics': {
                'total_jobs': len(result.jobs),
                'success': result.success_count,
                'failed': result.failed_count,
                'timeout': result.timeout_count
            },
            'jobs': [
                {
                    'job_id': job.job_id,
                    'run_id': job.run_id,
                    'trace_file': job.trace_file,
                    'analysis_mode': job.analysis_mode,
                    'dest_ports': job.dest_ports,
                    'timings': {
                        'submit_time': job.submit_time,
                        'complete_time': job.complete_time,
                        'duration_seconds': job.duration,
                        'server_duration_seconds': job.server_duration
                    },
                    'status': job.status,
                    'curl_exit_code': job.curl_exit_code,
                    'outputs': {
                        'pdf_path': job.pdf_path,
                        'json_path': job.json_path
                    },
                    'error_message': job.error_message
                }
                for job in result.jobs
            ]
        }

        meta_file = scenario_dir / 'meta.json'
        with open(meta_file, 'w') as f:
            json.dump(meta, f, indent=2)

        print(f"\nMeta JSON saved: {meta_file}")

    def check_mode(self, scenario_name: str, expected_dir: Path) -> bool:
        """Check mode: compare results with expected output"""

        print(f"\n{'='*60}")
        print(f"Check mode: {scenario_name}")
        print(f"Expected results: {expected_dir}")
        print(f"{'='*60}\n")

        actual_dir = self.output_dir / scenario_name

        if not actual_dir.exists():
            print(f"ERROR: Actual results not found: {actual_dir}")
            return False

        # Load meta JSONs
        expected_meta = expected_dir / 'meta.json'
        actual_meta = actual_dir / 'meta.json'

        if not expected_meta.exists():
            print(f"ERROR: Expected meta.json not found: {expected_meta}")
            return False

        if not actual_meta.exists():
            print(f"ERROR: Actual meta.json not found: {actual_meta}")
            return False

        with open(expected_meta) as f:
            expected_data = json.load(f)

        with open(actual_meta) as f:
            actual_data = json.load(f)

        # Compare job counts
        expected_jobs = len(expected_data['jobs'])
        actual_jobs = len(actual_data['jobs'])

        if expected_jobs != actual_jobs:
            print(f"ERROR: Job count mismatch: expected {expected_jobs}, got {actual_jobs}")
            return False

        # Compare each job (excluding volatile fields)
        all_match = True
        volatile_fields = {'run_id', 'submit_time', 'complete_time', 'duration_seconds',
                          'timestamp', 'total_duration_seconds', 'pdf_path', 'json_path'}

        for i, (exp_job, act_job) in enumerate(zip(expected_data['jobs'], actual_data['jobs'])):
            # Compare status
            if exp_job['status'] != act_job['status']:
                print(f"Job {i}: Status mismatch - expected {exp_job['status']}, "
                      f"got {act_job['status']}")
                all_match = False

            # Compare trace file
            if exp_job['trace_file'] != act_job['trace_file']:
                print(f"Job {i}: Trace file mismatch")
                all_match = False

            # Compare analysis mode
            if exp_job['analysis_mode'] != act_job['analysis_mode']:
                print(f"Job {i}: Analysis mode mismatch")
                all_match = False

            # Compare dest ports
            if exp_job['dest_ports'] != act_job['dest_ports']:
                print(f"Job {i}: Dest ports mismatch")
                all_match = False

            # Compare JSON results if available
            if exp_job['status'] == 'SUCCESS' and act_job['status'] == 'SUCCESS':
                # Compare progress.json
                exp_progress = Path(exp_job['outputs']['json_path']) / 'progress.json'
                act_progress = Path(act_job['outputs']['json_path']) / 'progress.json'

                if exp_progress.exists() and act_progress.exists():
                    if not self.compare_json_files(exp_progress, act_progress, volatile_fields):
                        print(f"Job {i}: Progress JSON mismatch")
                        all_match = False

        if all_match:
            print("\n✓ All checks passed - results match expected output")
        else:
            print("\n✗ Some checks failed - results differ from expected output")

        return all_match

    def compare_json_files(self, expected: Path, actual: Path,
                          volatile_fields: set) -> bool:
        """Compare two JSON files, ignoring volatile fields"""

        with open(expected) as f:
            exp_data = json.load(f)

        with open(actual) as f:
            act_data = json.load(f)

        return self.compare_dicts(exp_data, act_data, volatile_fields)

    def compare_dicts(self, d1: Any, d2: Any, volatile_fields: set, path: str = '') -> bool:
        """Recursively compare two dictionaries, ignoring volatile fields"""

        if type(d1) != type(d2):
            return False

        if isinstance(d1, dict):
            if set(d1.keys()) != set(d2.keys()):
                return False

            for key in d1:
                if key in volatile_fields:
                    continue

                new_path = f"{path}.{key}" if path else key
                if not self.compare_dicts(d1[key], d2[key], volatile_fields, new_path):
                    return False

        elif isinstance(d1, list):
            if len(d1) != len(d2):
                return False

            for i, (v1, v2) in enumerate(zip(d1, d2)):
                new_path = f"{path}[{i}]"
                if not self.compare_dicts(v1, v2, volatile_fields, new_path):
                    return False

        else:
            if d1 != d2:
                return False

        return True


def load_config_file(config_file: Path) -> List[JobConfig]:
    """Load job configurations from file"""

    jobs = []
    with open(config_file) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            try:
                job = JobConfig.from_line(line)
                jobs.append(job)
            except Exception as e:
                print(f"Warning: Skipping invalid line {line_num}: {e}")

    return jobs


def main():
    parser = argparse.ArgumentParser(
        description='Integration test script for parallel job execution'
    )

    parser.add_argument(
        '--config', '-c',
        type=Path,
        required=True,
        help='Job configuration file (semicolon-separated: trace_file;mode;ports)'
    )

    parser.add_argument(
        '--scenario', '-s',
        required=True,
        help='Scenario name (e.g., "01_single_detailed")'
    )

    parser.add_argument(
        '--output-dir', '-o',
        type=Path,
        default=Path('./test_results'),
        help='Output directory for test results (default: ./test_results)'
    )

    parser.add_argument(
        '--base-url',
        default='http://localhost/tsim',
        help='Base URL for TSIM API (default: http://localhost/tsim)'
    )

    parser.add_argument(
        '--username', '-u',
        required=True,
        help='Authentication username'
    )

    parser.add_argument(
        '--password', '-p',
        required=True,
        help='Authentication password'
    )

    parser.add_argument(
        '--sequential',
        action='store_true',
        help='Submit jobs sequentially instead of parallel'
    )

    parser.add_argument(
        '--timeout',
        type=int,
        default=600,
        help='Timeout per job in seconds (default: 600)'
    )

    parser.add_argument(
        '--check',
        type=Path,
        help='Check mode: compare with expected results in this directory'
    )

    parser.add_argument(
        '--insecure', '-k',
        action='store_true',
        help='Allow insecure SSL connections (skip certificate verification)'
    )

    args = parser.parse_args()

    # Load job configurations
    if not args.config.exists():
        print(f"ERROR: Config file not found: {args.config}")
        return 1

    jobs = load_config_file(args.config)

    if not jobs:
        print("ERROR: No valid jobs found in config file")
        return 1

    print(f"Loaded {len(jobs)} jobs from {args.config}")

    # Create tester
    tester = IntegrationTester(
        base_url=args.base_url,
        username=args.username,
        password=args.password,
        output_dir=args.output_dir,
        timeout=args.timeout,
        insecure=args.insecure
    )

    # Run scenario
    result = tester.run_scenario(
        scenario_name=args.scenario,
        jobs=jobs,
        parallel=not args.sequential
    )

    # Check mode if requested
    if args.check:
        if not tester.check_mode(args.scenario, args.check):
            return 1

    # Return exit code based on results
    if result.failed_count > 0 or result.timeout_count > 0:
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
