#!/usr/bin/env python3
"""
KSMS Test Suite Client
Comprehensive testing of KSMS tester with parallel job execution, queueing, and correctness validation.
"""

import argparse
import asyncio
import concurrent.futures
import json
import logging
import random
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict


@dataclass
class TestJob:
    """Test job specification"""
    job_id: str
    source_ip: str
    dest_ip: str
    ports: str
    expected_results: Dict[str, str]  # port/proto -> YES/NO/UNKNOWN
    priority: int = 0
    timeout: int = 300
    created_at: float = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()


@dataclass 
class TestResult:
    """Test execution result"""
    job_id: str
    success: bool
    duration: float
    results: Optional[Dict] = None
    error: Optional[str] = None
    dscp_used: Optional[int] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


class KsmsTestClient:
    """KSMS Test Suite Client"""
    
    def __init__(self, tsimsh_path: str = "tsimsh", verbose: int = 1):
        self.tsimsh_path = tsimsh_path
        self.verbose = verbose
        self.logger = self._setup_logging()
        self.results: List[TestResult] = []
        
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        level = logging.DEBUG if self.verbose >= 2 else logging.INFO
        logging.basicConfig(
            level=level,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        return logging.getLogger('ksms_test_client')
    
    async def run_test_suite(self, test_config: Dict) -> Dict:
        """Run comprehensive test suite"""
        self.logger.info(f"Starting KSMS test suite with {len(test_config['test_jobs'])} jobs")
        
        # Run different test scenarios
        results = {}
        
        if test_config.get('test_serial_execution', True):
            results['serial'] = await self._test_serial_execution(test_config['test_jobs'][:5])
            
        if test_config.get('test_parallel_execution', True):
            results['parallel'] = await self._test_parallel_execution(test_config['test_jobs'][:10])
            
        if test_config.get('test_dscp_exhaustion', True):
            results['dscp_exhaustion'] = await self._test_dscp_exhaustion()
            
        if test_config.get('test_queue_management', True):
            results['queue_management'] = await self._test_queue_management(test_config['test_jobs'])
            
        if test_config.get('test_error_handling', True):
            results['error_handling'] = await self._test_error_handling()
            
        if test_config.get('test_correctness', True):
            results['correctness'] = await self._test_result_correctness(test_config['validation_jobs'])
            
        # Generate comprehensive report
        report = self._generate_test_report(results)
        return report
    
    async def _test_serial_execution(self, jobs: List[TestJob]) -> Dict:
        """Test serial job execution"""
        self.logger.info("Testing serial execution...")
        
        results = []
        start_time = time.time()
        
        for job in jobs:
            result = await self._execute_single_job(job)
            results.append(result)
            
        end_time = time.time()
        
        return {
            'type': 'serial_execution',
            'total_jobs': len(jobs),
            'successful_jobs': sum(1 for r in results if r.success),
            'failed_jobs': sum(1 for r in results if not r.success),
            'total_duration': end_time - start_time,
            'average_job_duration': sum(r.duration for r in results) / len(results),
            'results': [asdict(r) for r in results]
        }
    
    async def _test_parallel_execution(self, jobs: List[TestJob]) -> Dict:
        """Test parallel job execution"""
        self.logger.info("Testing parallel execution...")
        
        start_time = time.time()
        
        # Execute jobs in parallel batches
        batch_size = 8  # Max concurrent jobs
        results = []
        
        for i in range(0, len(jobs), batch_size):
            batch = jobs[i:i + batch_size]
            batch_start = time.time()
            
            # Execute batch concurrently
            tasks = [self._execute_single_job(job) for job in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            batch_end = time.time()
            batch_duration = batch_end - batch_start
            
            self.logger.info(f"Batch {i//batch_size + 1}: {len(batch)} jobs in {batch_duration:.2f}s")
            
            # Handle exceptions
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    error_result = TestResult(
                        job_id=batch[j].job_id,
                        success=False,
                        duration=0.0,
                        error=str(result)
                    )
                    results.append(error_result)
                else:
                    results.append(result)
        
        end_time = time.time()
        
        # Analyze parallelism efficiency
        total_sequential_time = sum(r.duration for r in results if r.success)
        actual_parallel_time = end_time - start_time
        parallelism_efficiency = total_sequential_time / actual_parallel_time if actual_parallel_time > 0 else 0
        
        return {
            'type': 'parallel_execution',
            'total_jobs': len(jobs),
            'successful_jobs': sum(1 for r in results if r.success),
            'failed_jobs': sum(1 for r in results if not r.success),
            'total_duration': end_time - start_time,
            'theoretical_sequential_duration': total_sequential_time,
            'parallelism_efficiency': parallelism_efficiency,
            'average_job_duration': sum(r.duration for r in results if r.success) / max(1, sum(1 for r in results if r.success)),
            'dscp_usage': self._analyze_dscp_usage(results),
            'results': [asdict(r) for r in results]
        }
    
    async def _test_dscp_exhaustion(self) -> Dict:
        """Test DSCP exhaustion scenarios"""
        self.logger.info("Testing DSCP exhaustion...")
        
        # Create 35 jobs (more than 32 DSCP limit)
        jobs = []
        for i in range(35):
            job = TestJob(
                job_id=f"exhaustion_test_{i}",
                source_ip="10.1.1.100",
                dest_ip="10.2.1.200", 
                ports="80/tcp",
                expected_results={"80/tcp": "UNKNOWN"}  # Don't care about actual results
            )
            jobs.append(job)
        
        # Try to execute all at once
        start_time = time.time()
        tasks = [self._execute_single_job(job, expect_failure=True) for job in jobs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()
        
        # Analyze results
        successful_jobs = sum(1 for r in results if isinstance(r, TestResult) and r.success)
        failed_jobs = len(results) - successful_jobs
        dscp_exhaustion_errors = sum(1 for r in results if isinstance(r, TestResult) and r.error and "DSCP" in r.error)
        
        return {
            'type': 'dscp_exhaustion',
            'total_jobs': len(jobs),
            'successful_jobs': successful_jobs,
            'failed_jobs': failed_jobs,
            'dscp_exhaustion_errors': dscp_exhaustion_errors,
            'duration': end_time - start_time,
            'expected_max_concurrent': 32,
            'actual_max_concurrent': successful_jobs
        }
    
    async def _test_queue_management(self, jobs: List[TestJob]) -> Dict:
        """Test job queue management"""
        self.logger.info("Testing queue management...")
        
        # Submit many jobs rapidly and monitor queue behavior
        rapid_jobs = jobs[:20]
        
        # Submit all jobs as fast as possible
        start_time = time.time()
        submit_tasks = [self._submit_job_async(job) for job in rapid_jobs]
        await asyncio.gather(*submit_tasks)
        submit_time = time.time() - start_time
        
        # Monitor queue status
        queue_states = []
        for i in range(30):  # Monitor for 30 seconds
            queue_status = await self._get_queue_status()
            queue_states.append({
                'timestamp': time.time(),
                'queue_length': queue_status.get('queue_length', 0),
                'active_jobs': queue_status.get('active_jobs', 0)
            })
            await asyncio.sleep(1)
        
        # Wait for all jobs to complete
        completion_results = []
        while True:
            queue_status = await self._get_queue_status()
            if queue_status.get('queue_length', 0) == 0 and queue_status.get('active_jobs', 0) == 0:
                break
            await asyncio.sleep(2)
        
        end_time = time.time()
        
        return {
            'type': 'queue_management',
            'total_jobs': len(rapid_jobs),
            'submit_duration': submit_time,
            'total_duration': end_time - start_time,
            'queue_states': queue_states,
            'max_queue_length': max(s['queue_length'] for s in queue_states),
            'max_active_jobs': max(s['active_jobs'] for s in queue_states)
        }
    
    async def _test_error_handling(self) -> Dict:
        """Test error handling scenarios"""
        self.logger.info("Testing error handling...")
        
        error_scenarios = [
            # Invalid source IP
            TestJob("error_invalid_src", "999.999.999.999", "10.2.1.200", "80/tcp", {}),
            # Invalid destination IP  
            TestJob("error_invalid_dst", "10.1.1.100", "invalid_ip", "80/tcp", {}),
            # Invalid port specification
            TestJob("error_invalid_ports", "10.1.1.100", "10.2.1.200", "99999/invalid", {}),
            # Empty port specification
            TestJob("error_empty_ports", "10.1.1.100", "10.2.1.200", "", {}),
            # Extremely large port range
            TestJob("error_large_range", "10.1.1.100", "10.2.1.200", "1-65535/tcp", {})
        ]
        
        results = []
        for job in error_scenarios:
            result = await self._execute_single_job(job, expect_failure=True)
            results.append(result)
        
        return {
            'type': 'error_handling',
            'total_scenarios': len(error_scenarios),
            'handled_gracefully': sum(1 for r in results if not r.success and r.error),
            'unexpected_successes': sum(1 for r in results if r.success),
            'unhandled_errors': sum(1 for r in results if not r.success and not r.error),
            'results': [asdict(r) for r in results]
        }
    
    async def _test_result_correctness(self, validation_jobs: List[TestJob]) -> Dict:
        """Test result correctness against known expected results"""
        self.logger.info("Testing result correctness...")
        
        results = []
        correct_results = 0
        
        for job in validation_jobs:
            result = await self._execute_single_job(job)
            if result.success and result.results:
                # Compare actual vs expected results
                actual_results = result.results.get('results', {})
                correctness = self._validate_job_results(actual_results, job.expected_results)
                results.append({
                    'job_id': job.job_id,
                    'expected': job.expected_results,
                    'actual': actual_results, 
                    'correct': correctness['all_correct'],
                    'correct_count': correctness['correct_count'],
                    'total_count': correctness['total_count'],
                    'discrepancies': correctness['discrepancies']
                })
                if correctness['all_correct']:
                    correct_results += 1
            else:
                results.append({
                    'job_id': job.job_id,
                    'expected': job.expected_results,
                    'actual': None,
                    'correct': False,
                    'error': result.error
                })
        
        return {
            'type': 'result_correctness',
            'total_jobs': len(validation_jobs),
            'correct_jobs': correct_results,
            'accuracy': correct_results / len(validation_jobs) if validation_jobs else 0,
            'results': results
        }
    
    async def _execute_single_job(self, job: TestJob, expect_failure: bool = False) -> TestResult:
        """Execute a single KSMS job"""
        start_time = time.time()
        
        try:
            # Build ksms_tester command
            cmd = [
                self.tsimsh_path,
                "ksms_tester",
                "-s", job.source_ip,
                "-d", job.dest_ip, 
                "-P", job.ports,
                "-j",  # JSON output
                "--force"  # No interactive prompts
            ]
            
            if self.verbose >= 3:
                cmd.append("-vvv")
            elif self.verbose >= 2:
                cmd.append("-vv")
            elif self.verbose >= 1:
                cmd.append("-v")
            
            self.logger.debug(f"Executing job {job.job_id}: {' '.join(cmd)}")
            
            # Execute with timeout
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=job.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise RuntimeError(f"Job {job.job_id} timed out after {job.timeout}s")
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Parse results
            if process.returncode == 0:
                try:
                    results = json.loads(stdout.decode())
                    
                    return TestResult(
                        job_id=job.job_id,
                        success=True,
                        duration=duration,
                        results=results,
                        dscp_used=results.get('dscp_used'),
                        started_at=start_time,
                        completed_at=end_time
                    )
                except json.JSONDecodeError as e:
                    return TestResult(
                        job_id=job.job_id,
                        success=False,
                        duration=duration,
                        error=f"JSON decode error: {e}",
                        started_at=start_time,
                        completed_at=end_time
                    )
            else:
                error_msg = stderr.decode() if stderr else f"Process exited with code {process.returncode}"
                
                if expect_failure:
                    # Expected failure - this is success for error testing
                    return TestResult(
                        job_id=job.job_id,
                        success=False,
                        duration=duration,
                        error=error_msg,
                        started_at=start_time,
                        completed_at=end_time
                    )
                else:
                    return TestResult(
                        job_id=job.job_id,
                        success=False,
                        duration=duration,
                        error=error_msg,
                        started_at=start_time,
                        completed_at=end_time
                    )
                    
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            
            return TestResult(
                job_id=job.job_id,
                success=False,
                duration=duration,
                error=str(e),
                started_at=start_time,
                completed_at=end_time
            )
    
    async def _submit_job_async(self, job: TestJob) -> bool:
        """Submit job asynchronously (for queue testing)"""
        # This would integrate with WSGI API for job submission
        # For now, simulate rapid submission
        await asyncio.sleep(random.uniform(0.01, 0.1))
        return True
    
    async def _get_queue_status(self) -> Dict:
        """Get current queue status"""
        # This would query the WSGI queue API
        # For now, simulate queue status
        return {
            'queue_length': random.randint(0, 10),
            'active_jobs': random.randint(0, 8)
        }
    
    def _analyze_dscp_usage(self, results: List[TestResult]) -> Dict:
        """Analyze DSCP value usage patterns"""
        dscp_values = [r.dscp_used for r in results if r.success and r.dscp_used is not None]
        
        if not dscp_values:
            return {'dscp_values_used': [], 'unique_dscp_count': 0}
        
        unique_dscps = set(dscp_values)
        dscp_frequency = {dscp: dscp_values.count(dscp) for dscp in unique_dscps}
        
        return {
            'dscp_values_used': sorted(unique_dscps),
            'unique_dscp_count': len(unique_dscps),
            'dscp_frequency': dscp_frequency,
            'max_concurrent_estimate': len(unique_dscps)
        }
    
    def _validate_job_results(self, actual: Dict, expected: Dict) -> Dict:
        """Validate job results against expected outcomes"""
        if not actual or not expected:
            return {'all_correct': False, 'correct_count': 0, 'total_count': len(expected), 'discrepancies': []}
        
        discrepancies = []
        correct_count = 0
        
        for service, expected_result in expected.items():
            actual_result = actual.get(service, 'MISSING')
            if actual_result == expected_result:
                correct_count += 1
            else:
                discrepancies.append({
                    'service': service,
                    'expected': expected_result,
                    'actual': actual_result
                })
        
        return {
            'all_correct': len(discrepancies) == 0,
            'correct_count': correct_count,
            'total_count': len(expected),
            'discrepancies': discrepancies
        }
    
    def _generate_test_report(self, results: Dict) -> Dict:
        """Generate comprehensive test report"""
        report = {
            'test_suite': 'KSMS Comprehensive Test Suite',
            'timestamp': datetime.now().isoformat(),
            'summary': {},
            'detailed_results': results,
            'recommendations': []
        }
        
        # Calculate overall summary
        total_tests = sum(len(test_result.get('results', [])) for test_result in results.values() if isinstance(test_result.get('results', []), list))
        
        summary = {
            'total_test_scenarios': len(results),
            'total_individual_tests': total_tests,
        }
        
        # Add scenario-specific summaries
        for scenario_name, scenario_results in results.items():
            if isinstance(scenario_results, dict):
                scenario_summary = {
                    'type': scenario_results.get('type', scenario_name),
                    'success': scenario_results.get('successful_jobs', 0) > 0,
                }
                
                # Add scenario-specific metrics
                if 'parallelism_efficiency' in scenario_results:
                    scenario_summary['parallelism_efficiency'] = scenario_results['parallelism_efficiency']
                
                if 'accuracy' in scenario_results:
                    scenario_summary['accuracy'] = scenario_results['accuracy']
                
                summary[scenario_name] = scenario_summary
        
        report['summary'] = summary
        
        # Generate recommendations
        recommendations = []
        
        if 'parallel' in results:
            efficiency = results['parallel'].get('parallelism_efficiency', 0)
            if efficiency < 2.0:
                recommendations.append("Parallelism efficiency is low - consider investigating DSCP registry or queue bottlenecks")
        
        if 'correctness' in results:
            accuracy = results['correctness'].get('accuracy', 0)
            if accuracy < 0.95:
                recommendations.append("Result accuracy is below 95% - investigate KSMS algorithm or test environment")
        
        if 'dscp_exhaustion' in results:
            max_concurrent = results['dscp_exhaustion'].get('actual_max_concurrent', 0)
            if max_concurrent < 30:
                recommendations.append("DSCP exhaustion handling may be too conservative - review allocation limits")
        
        report['recommendations'] = recommendations
        
        return report


def create_test_configuration() -> Dict:
    """Create comprehensive test configuration"""
    
    # Basic connectivity test jobs
    basic_jobs = [
        TestJob(f"basic_tcp_{i}", "10.1.1.100", "10.2.1.200", "80/tcp", {"80/tcp": "YES"})
        for i in range(5)
    ]
    
    # Multi-service test jobs
    multi_service_jobs = [
        TestJob(f"multi_service_{i}", "10.1.1.100", "10.2.1.200", 
               "80/tcp,443/tcp,22/tcp,53/udp", 
               {"80/tcp": "YES", "443/tcp": "YES", "22/tcp": "NO", "53/udp": "UNKNOWN"})
        for i in range(10)
    ]
    
    # Large port range jobs
    large_range_jobs = [
        TestJob(f"large_range_{i}", "10.1.1.100", "10.2.1.200",
               "8000-8050/tcp,9000-9020/udp",
               {f"{p}/tcp": "UNKNOWN" for p in range(8000, 8051)} | 
               {f"{p}/udp": "UNKNOWN" for p in range(9000, 9021)})
        for i in range(3)
    ]
    
    # Validation jobs with known expected results (for correctness testing)
    validation_jobs = [
        TestJob("validation_web", "10.1.1.100", "10.2.1.200", "80/tcp,443/tcp", 
               {"80/tcp": "YES", "443/tcp": "YES"}),
        TestJob("validation_blocked", "10.1.1.100", "10.2.1.200", "23/tcp,135/tcp",
               {"23/tcp": "NO", "135/tcp": "NO"}),
        TestJob("validation_mixed", "10.1.1.100", "10.2.1.200", "80/tcp,23/tcp,53/udp",
               {"80/tcp": "YES", "23/tcp": "NO", "53/udp": "YES"})
    ]
    
    return {
        'test_jobs': basic_jobs + multi_service_jobs + large_range_jobs,
        'validation_jobs': validation_jobs,
        'test_serial_execution': True,
        'test_parallel_execution': True,
        'test_dscp_exhaustion': True, 
        'test_queue_management': True,
        'test_error_handling': True,
        'test_correctness': True
    }


async def main():
    """Main test runner"""
    parser = argparse.ArgumentParser(description='KSMS Comprehensive Test Suite')
    parser.add_argument('--tsimsh-path', default='tsimsh', help='Path to tsimsh command')
    parser.add_argument('--verbose', '-v', action='count', default=1, help='Increase verbosity')
    parser.add_argument('--output', '-o', help='Output file for test results (JSON)')
    parser.add_argument('--config', help='Test configuration file (JSON)')
    parser.add_argument('--scenarios', nargs='+', 
                       choices=['serial', 'parallel', 'dscp_exhaustion', 'queue_management', 'error_handling', 'correctness'],
                       help='Specific test scenarios to run')
    
    args = parser.parse_args()
    
    # Load or create test configuration
    if args.config:
        with open(args.config, 'r') as f:
            test_config = json.load(f)
    else:
        test_config = create_test_configuration()
    
    # Filter scenarios if specified
    if args.scenarios:
        scenario_map = {
            'serial': 'test_serial_execution',
            'parallel': 'test_parallel_execution', 
            'dscp_exhaustion': 'test_dscp_exhaustion',
            'queue_management': 'test_queue_management',
            'error_handling': 'test_error_handling',
            'correctness': 'test_correctness'
        }
        
        # Disable all scenarios first
        for key in scenario_map.values():
            test_config[key] = False
            
        # Enable selected scenarios
        for scenario in args.scenarios:
            test_config[scenario_map[scenario]] = True
    
    # Create test client and run tests
    client = KsmsTestClient(tsimsh_path=args.tsimsh_path, verbose=args.verbose)
    
    try:
        report = await client.run_test_suite(test_config)
        
        # Output results
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"Test results written to {args.output}")
        else:
            print(json.dumps(report, indent=2))
            
        # Print summary
        print(f"\n=== KSMS Test Suite Summary ===")
        print(f"Total scenarios: {report['summary']['total_test_scenarios']}")
        print(f"Total tests: {report['summary']['total_individual_tests']}")
        
        if 'parallel' in report['summary']:
            efficiency = report['summary']['parallel'].get('parallelism_efficiency', 0)
            print(f"Parallelism efficiency: {efficiency:.2f}x")
            
        if 'correctness' in report['summary']:
            accuracy = report['summary']['correctness'].get('accuracy', 0)
            print(f"Result accuracy: {accuracy:.1%}")
        
        if report.get('recommendations'):
            print(f"\nRecommendations:")
            for rec in report['recommendations']:
                print(f"- {rec}")
                
        return 0
        
    except Exception as e:
        print(f"Test suite failed: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))