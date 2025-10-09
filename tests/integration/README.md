# TSIM Parallel Job Integration Tests

Comprehensive integration test suite for testing parallel job execution with router-level conflict detection.

## Overview

This test suite validates:
- Parallel execution of quick jobs (DSCP isolated)
- Serial execution of detailed jobs (router-level conflicts)
- Router-level conflict detection between quick and detailed jobs
- Scheduler's ability to maximize parallelism
- Correctness of results across all scenarios

## Test Scenarios

1. **01_single_detailed** - Single detailed job baseline
2. **02_multiple_detailed_disjoint** - Multiple detailed jobs on disjoint routers (parallel)
3. **03_multiple_detailed_overlapping** - Multiple detailed jobs with router overlap (queued)
4. **04_single_quick** - Single quick job baseline
5. **05_multiple_quick** - Multiple quick jobs (all parallel, DSCP isolated)
6. **06_detailed_quick_disjoint** - Detailed + quick on disjoint routers (parallel)
7. **07_detailed_quick_overlapping** - Detailed + quick with router overlap (queued)
8. **08_detailed_multiple_quick_disjoint** - Detailed + multiple quick, disjoint (parallel)
9. **09_detailed_multiple_quick_overlapping** - Detailed + multiple quick, overlapping (partial)
10. **10_multiple_detailed_multiple_quick_disjoint** - Multiple detailed + quick, disjoint (parallel)
11. **11_crown_test_overlapping** - **CROWN TEST**: Complex scenario with all conflict types

## Directory Structure

 * [test_parallel_jobs.py](./test_parallel_jobs.py)
 * [configs](./configs)
   * [01_single_detailed.conf](./configs/01_single_detailed.conf)
   * [02_multiple_detailed_disjoint.conf](./configs/02_multiple_detailed_disjoint.conf)
   * [03_multiple_detailed_overlapping.conf](./configs/03_multiple_detailed_overlapping.conf)
   * [04_single_quick.conf](./configs/04_single_quick.conf)
   * [05_multiple_quick.conf](./configs/05_multiple_quick.conf)
   * [06_detailed_quick_disjoint.conf](./configs/06_detailed_quick_disjoint.conf)
   * [07_detailed_quick_overlapping.conf](./configs/07_detailed_quick_overlapping.conf)
   * [08_detailed_multiple_quick_disjoint.conf](./configs/08_detailed_multiple_quick_disjoint.conf)
   * [09_detailed_multiple_quick_overlapping.conf](./configs/09_detailed_multiple_quick_overlapping.conf)
   * [10_multiple_detailed_multiple_quick_disjoint.conf](./configs/10_multiple_detailed_multiple_quick_disjoint.conf)
   * [11_crown_test_overlapping.conf](./configs/11_crown_test_overlapping.conf)
 * [run_all_scenarios.sh](./run_all_scenarios.sh)
 * [analyze_results.py](./analyze_results.py)
 * [QUICKSTART.md](./QUICKSTART.md)
 * [README.md](./README.md)

## Configuration File Format

Jobs are defined in config files using semicolon-separated format:

```
# Comment line
trace_file_path ; analysis_mode ; dest_ports

# Example:
/path/to/trace.json ; detailed ; 80,443,22
/path/to/trace2.json ; quick ; 80,443
```

**Fields:**
- `trace_file_path`: Path to trace JSON file
- `analysis_mode`: Either `quick` or `detailed`
- `dest_ports`: Comma-separated list of destination ports

**Whitespace:** Amount of whitespace around separators doesn't matter.

## Usage

### Running Individual Scenarios

```bash
./test_parallel_jobs.py \
  --config configs/01_single_detailed.conf \
  --scenario 01_single_detailed \
  --username admin \
  --password <password> \
  --source-ip 10.0.1.1 \
  --dest-ip 10.0.2.1
```

### Running All Scenarios

```bash
./run_all_scenarios.sh \
  --username admin \
  --password <password> \
  --source-ip 10.0.1.1 \
  --dest-ip 10.0.2.1
```

### Environment Variables

```bash
export TSIM_BASE_URL="http://localhost/tsim"
export TSIM_USERNAME="admin"
export TSIM_PASSWORD="secret"
export TSIM_SOURCE_IP="10.0.1.1"
export TSIM_DEST_IP="10.0.2.1"
export TSIM_TIMEOUT="600"

./run_all_scenarios.sh
```

### Check Mode (Regression Testing)

```bash
# First run: establish baseline
./run_all_scenarios.sh --username admin --password secret \
  --source-ip 10.0.1.1 --dest-ip 10.0.2.1

# Results saved to: results/20250309_143022/

# Later run: compare against baseline
./run_all_scenarios.sh --username admin --password secret \
  --source-ip 10.0.1.1 --dest-ip 10.0.2.1 \
  --check results/20250309_143022/
```

Check mode compares:
- Job counts
- Status codes
- Analysis modes
- Destination ports
- JSON result structure (excluding volatile fields like run_id, timestamps)

### Sequential Mode

By default, jobs are submitted in parallel. Use `--sequential` to submit one at a time:

```bash
./run_all_scenarios.sh --sequential \
  --username admin --password secret \
  --source-ip 10.0.1.1 --dest-ip 10.0.2.1
```

## Command Line Options

### test_parallel_jobs.py

| Option | Description |
|--------|-------------|
| `--config PATH` | Job configuration file (required) |
| `--scenario NAME` | Scenario name (required) |
| `--output-dir DIR` | Output directory (default: ./test_results) |
| `--base-url URL` | Base URL for TSIM API |
| `--username USER` | Authentication username (required) |
| `--password PASS` | Authentication password (required) |
| `--source-ip IP` | Source IP address (required) |
| `--dest-ip IP` | Destination IP address (required) |
| `--sequential` | Submit jobs sequentially |
| `--timeout SECONDS` | Timeout per job (default: 600) |
| `--check DIR` | Check mode: compare with expected results |

### run_all_scenarios.sh

| Option | Description |
|--------|-------------|
| `--username USER` | Authentication username |
| `--password PASS` | Authentication password (required) |
| `--source-ip IP` | Source IP address |
| `--dest-ip IP` | Destination IP address |
| `--base-url URL` | Base URL for TSIM API |
| `--sequential` | Submit jobs sequentially |
| `--timeout SECONDS` | Timeout per job |
| `--check DIR` | Check mode: compare with expected results |
| `--help` | Show help message |

## Output Files

### Meta JSON (meta.json)

```json
{
  "scenario_name": "01_single_detailed",
  "timestamp": "2025-03-09T14:30:22",
  "total_duration_seconds": 45.67,
  "statistics": {
    "total_jobs": 1,
    "success": 1,
    "failed": 0,
    "timeout": 0
  },
  "jobs": [
    {
      "job_id": 0,
      "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "trace_file": "/path/to/trace.json",
      "analysis_mode": "detailed",
      "dest_ports": [80, 443, 22],
      "timings": {
        "submit_time": 1709994622.123,
        "complete_time": 1709994667.890,
        "duration_seconds": 45.67
      },
      "status": "SUCCESS",
      "curl_exit_code": 0,
      "outputs": {
        "pdf_path": "/path/to/output.pdf",
        "json_path": "/path/to/runs/run_id"
      },
      "error_message": null
    }
  ]
}
```

### Summary JSON (summary.json)

```json
{
  "test_run": {
    "timestamp": "20250309_143022",
    "start_time": 1709994622,
    "end_time": 1709995222,
    "duration_seconds": 600,
    "output_directory": "/path/to/results/20250309_143022"
  },
  "configuration": {
    "base_url": "http://localhost/tsim",
    "username": "admin",
    "source_ip": "10.0.1.1",
    "dest_ip": "10.0.2.1",
    "timeout": 600,
    "sequential": false,
    "check_mode": null
  },
  "results": {
    "total_scenarios": 11,
    "passed": 11,
    "failed": 0,
    "failed_scenarios": []
  }
}
```

## Expected Behavior

### Scenario 1: Single Detailed
- 1 job completes successfully
- Duration: ~30-60s

### Scenario 2: Multiple Detailed Disjoint
- All 3 detailed jobs run in parallel
- Duration: ~30-60s (same as single job)

### Scenario 3: Multiple Detailed Overlapping
- Jobs run sequentially due to router overlap
- Duration: ~90-180s (3x single job)

### Scenario 4: Single Quick
- 1 quick job completes
- Duration: ~5-15s

### Scenario 5: Multiple Quick
- All 5 quick jobs run in parallel (DSCP isolated)
- Duration: ~5-15s (same as single quick job)

### Scenario 6: Detailed + Quick Disjoint
- Both jobs run in parallel
- Duration: ~30-60s (detailed job duration)

### Scenario 7: Detailed + Quick Overlapping
- Quick job queued until detailed completes
- Duration: ~40-75s (detailed + quick sequential)

### Scenario 8: Detailed + Multiple Quick Disjoint
- All jobs run in parallel
- Duration: ~30-60s (detailed job duration)

### Scenario 9: Detailed + Multiple Quick Overlapping
- Quick jobs with no overlap run immediately
- Quick jobs with overlap are queued
- Duration: ~40-75s (detailed + overlapping quick sequential)

### Scenario 10: Multiple Detailed + Multiple Quick Disjoint
- All jobs run in parallel
- Duration: ~30-60s (detailed job duration)

### Scenario 11: Crown Test (Most Complex)
- Scheduler makes intelligent decisions
- Jobs run as parallel as possible given router constraints
- Duration: depends on conflict resolution
- **This is the ultimate test of scheduler correctness**

## Performance Metrics

Key metrics to monitor:

1. **Parallelism Efficiency**:
   - Compare parallel vs sequential run times
   - Should see near-linear speedup for disjoint scenarios

2. **Queue Wait Time**:
   - Monitor time between submit and actual execution
   - Should be minimal for non-conflicting jobs

3. **Individual Job Duration**:
   - Quick jobs: 5-15 seconds
   - Detailed jobs: 30-60 seconds
   - Should be consistent regardless of parallelism

4. **Total Scenario Duration**:
   - Disjoint scenarios: ~single job time
   - Overlapping scenarios: ~sum of job times

## Troubleshooting

### Jobs Timing Out

- Increase timeout: `--timeout 1200`
- Check system resources (CPU, memory)
- Check for deadlocks in scheduler

### PDF Files Not Found

- Verify `/dev/shm/tsim/results` directory exists
- Check file permissions
- Increase wait time in `collect_results()` method

### JSON Files Missing

- Verify `/dev/shm/tsim/runs` directory exists
- Check that jobs completed successfully
- Verify run_id in meta.json

### Check Mode Failures

- Normal for volatile fields (timestamps, run_ids)
- Verify actual differences using `diff` on JSON files
- Update baseline if behavior changed intentionally

## Contributing

When adding new test scenarios:

1. Create config file in `configs/`
2. Add scenario to `SCENARIOS` array in `run_all_scenarios.sh`
3. Document expected behavior in this README
4. Test with both parallel and sequential modes

## See Also

- `docs/race_condition_elimination_plan.md` - Architecture documentation
- `docs/queue_scheduler_integration_plan.md` - Scheduler design
- `docs/analysis_modes_comparison.md` - Quick vs Detailed analysis
