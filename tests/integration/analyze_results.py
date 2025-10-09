#!/usr/bin/env python3
"""
Test result analyzer - generates detailed performance and correctness reports.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime


def load_meta_files(results_dir: Path) -> Dict[str, Any]:
    """Load all meta.json files from a test run"""

    scenarios = {}

    for scenario_dir in results_dir.iterdir():
        if not scenario_dir.is_dir():
            continue

        meta_file = scenario_dir / 'meta.json'
        if not meta_file.exists():
            continue

        with open(meta_file) as f:
            scenarios[scenario_dir.name] = json.load(f)

    return scenarios


def analyze_parallelism(scenarios: Dict[str, Any]):
    """Analyze parallelism efficiency"""

    print("\n" + "="*70)
    print("PARALLELISM ANALYSIS")
    print("="*70)

    for scenario_name, data in sorted(scenarios.items()):
        print(f"\n{scenario_name}:")

        total_jobs = data['statistics']['total_jobs']
        total_duration = data['total_duration_seconds']

        # Calculate individual job durations
        job_durations = [
            job['timings']['duration_seconds']
            for job in data['jobs']
            if job['status'] == 'SUCCESS'
        ]

        if not job_durations:
            print("  No successful jobs")
            continue

        avg_job_duration = sum(job_durations) / len(job_durations)
        max_job_duration = max(job_durations)
        min_job_duration = min(job_durations)

        # Calculate theoretical times
        theoretical_parallel = max_job_duration  # All jobs in parallel
        theoretical_sequential = sum(job_durations)  # All jobs sequential

        # Calculate parallelism factor
        if theoretical_sequential > 0:
            parallelism_factor = theoretical_sequential / total_duration
            efficiency = (parallelism_factor / total_jobs) * 100
        else:
            parallelism_factor = 0
            efficiency = 0

        print(f"  Jobs:                    {total_jobs}")
        print(f"  Total Duration:          {total_duration:.2f}s")
        print(f"  Avg Job Duration:        {avg_job_duration:.2f}s")
        print(f"  Min/Max Job Duration:    {min_job_duration:.2f}s / {max_job_duration:.2f}s")
        print(f"  Theoretical Parallel:    {theoretical_parallel:.2f}s")
        print(f"  Theoretical Sequential:  {theoretical_sequential:.2f}s")
        print(f"  Parallelism Factor:      {parallelism_factor:.2f}x")
        print(f"  Efficiency:              {efficiency:.1f}%")

        # Assess performance
        if total_duration <= theoretical_parallel * 1.1:  # Within 10% overhead
            print(f"  Assessment:              ✓ Excellent (near-optimal parallelism)")
        elif total_duration <= theoretical_sequential * 0.5:  # Better than half sequential
            print(f"  Assessment:              ✓ Good (significant parallelism)")
        elif total_duration < theoretical_sequential:
            print(f"  Assessment:              ~ Fair (some parallelism)")
        else:
            print(f"  Assessment:              ✗ Poor (no parallelism benefit)")


def analyze_correctness(scenarios: Dict[str, Any]):
    """Analyze test correctness"""

    print("\n" + "="*70)
    print("CORRECTNESS ANALYSIS")
    print("="*70)

    total_jobs = 0
    total_success = 0
    total_failed = 0
    total_timeout = 0

    for scenario_name, data in sorted(scenarios.items()):
        stats = data['statistics']
        total_jobs += stats['total_jobs']
        total_success += stats['success']
        total_failed += stats['failed']
        total_timeout += stats['timeout']

        status = "✓" if stats['failed'] == 0 and stats['timeout'] == 0 else "✗"

        print(f"\n{status} {scenario_name}:")
        print(f"  Total:    {stats['total_jobs']}")
        print(f"  Success:  {stats['success']}")
        print(f"  Failed:   {stats['failed']}")
        print(f"  Timeout:  {stats['timeout']}")

        # List failed jobs
        if stats['failed'] > 0 or stats['timeout'] > 0:
            for job in data['jobs']:
                if job['status'] != 'SUCCESS':
                    print(f"    Job {job['job_id']}: {job['status']}")
                    if job['error_message']:
                        print(f"      Error: {job['error_message']}")

    # Overall statistics
    print(f"\n{'='*70}")
    print(f"OVERALL:")
    print(f"  Total Jobs:      {total_jobs}")
    print(f"  Success:         {total_success} ({total_success/total_jobs*100:.1f}%)")
    print(f"  Failed:          {total_failed} ({total_failed/total_jobs*100:.1f}%)")
    print(f"  Timeout:         {total_timeout} ({total_timeout/total_jobs*100:.1f}%)")


def analyze_timing_breakdown(scenarios: Dict[str, Any]):
    """Analyze timing breakdown by job type"""

    print("\n" + "="*70)
    print("TIMING BREAKDOWN")
    print("="*70)

    quick_durations = []
    detailed_durations = []

    for scenario_name, data in scenarios.items():
        for job in data['jobs']:
            if job['status'] != 'SUCCESS':
                continue

            duration = job['timings']['duration_seconds']
            mode = job['analysis_mode']

            if mode == 'quick':
                quick_durations.append(duration)
            elif mode == 'detailed':
                detailed_durations.append(duration)

    def print_stats(name, durations):
        if not durations:
            print(f"\n{name}: No data")
            return

        avg = sum(durations) / len(durations)
        min_d = min(durations)
        max_d = max(durations)
        median = sorted(durations)[len(durations)//2]

        print(f"\n{name} Jobs ({len(durations)} total):")
        print(f"  Average:  {avg:.2f}s")
        print(f"  Median:   {median:.2f}s")
        print(f"  Min:      {min_d:.2f}s")
        print(f"  Max:      {max_d:.2f}s")
        print(f"  Std Dev:  {(sum((d-avg)**2 for d in durations)/len(durations))**0.5:.2f}s")

    print_stats("Quick", quick_durations)
    print_stats("Detailed", detailed_durations)


def generate_summary_table(scenarios: Dict[str, Any]):
    """Generate summary table"""

    print("\n" + "="*70)
    print("SCENARIO SUMMARY TABLE")
    print("="*70)

    print("\n{:<45} {:>6} {:>8} {:>8}".format(
        "Scenario", "Jobs", "Duration", "Status"
    ))
    print("-" * 70)

    for scenario_name, data in sorted(scenarios.items()):
        stats = data['statistics']
        duration = data['total_duration_seconds']
        status = "PASS" if stats['failed'] == 0 and stats['timeout'] == 0 else "FAIL"

        print("{:<45} {:>6} {:>7.1f}s {:>8}".format(
            scenario_name,
            stats['total_jobs'],
            duration,
            status
        ))


def compare_runs(baseline_dir: Path, current_dir: Path):
    """Compare two test runs"""

    print("\n" + "="*70)
    print(f"COMPARISON: {baseline_dir.name} vs {current_dir.name}")
    print("="*70)

    baseline = load_meta_files(baseline_dir)
    current = load_meta_files(current_dir)

    # Compare each scenario
    for scenario_name in sorted(set(baseline.keys()) | set(current.keys())):
        if scenario_name not in baseline:
            print(f"\n{scenario_name}: NEW (not in baseline)")
            continue

        if scenario_name not in current:
            print(f"\n{scenario_name}: REMOVED (not in current)")
            continue

        base_data = baseline[scenario_name]
        curr_data = current[scenario_name]

        base_duration = base_data['total_duration_seconds']
        curr_duration = curr_data['total_duration_seconds']
        delta = curr_duration - base_duration
        percent = (delta / base_duration * 100) if base_duration > 0 else 0

        base_success = base_data['statistics']['success']
        curr_success = curr_data['statistics']['success']

        status = "✓" if curr_success == base_success else "✗"

        print(f"\n{status} {scenario_name}:")
        print(f"  Success:  {base_success} → {curr_success}")
        print(f"  Duration: {base_duration:.1f}s → {curr_duration:.1f}s "
              f"({delta:+.1f}s, {percent:+.1f}%)")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze TSIM integration test results'
    )

    parser.add_argument(
        'results_dir',
        type=Path,
        help='Directory containing test results (e.g., results/20250309_143022)'
    )

    parser.add_argument(
        '--compare',
        type=Path,
        help='Compare with another test run directory'
    )

    parser.add_argument(
        '--format',
        choices=['text', 'json'],
        default='text',
        help='Output format (default: text)'
    )

    args = parser.parse_args()

    if not args.results_dir.exists():
        print(f"ERROR: Results directory not found: {args.results_dir}")
        return 1

    # Load scenarios
    scenarios = load_meta_files(args.results_dir)

    if not scenarios:
        print(f"ERROR: No scenario results found in {args.results_dir}")
        return 1

    print("\n" + "="*70)
    print(f"TEST RESULTS ANALYSIS: {args.results_dir.name}")
    print("="*70)
    print(f"Scenarios analyzed: {len(scenarios)}")

    # Load summary if available
    summary_file = args.results_dir / 'summary.json'
    if summary_file.exists():
        with open(summary_file) as f:
            summary = json.load(f)

        timestamp = summary['test_run']['timestamp']
        duration = summary['test_run']['duration_seconds']

        print(f"Test run:           {timestamp}")
        print(f"Total duration:     {duration}s ({duration/60:.1f}m)")
        print(f"Configuration:      {summary['configuration']['base_url']}")

    # Generate analyses
    generate_summary_table(scenarios)
    analyze_correctness(scenarios)
    analyze_parallelism(scenarios)
    analyze_timing_breakdown(scenarios)

    # Compare runs if requested
    if args.compare:
        if not args.compare.exists():
            print(f"\nWARNING: Comparison directory not found: {args.compare}")
        else:
            compare_runs(args.compare, args.results_dir)

    return 0


if __name__ == '__main__':
    sys.exit(main())
