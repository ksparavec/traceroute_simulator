# Quick Start Guide

Get started with integration tests in 5 minutes.

## Prerequisites

1. TSIM system running and accessible
2. Valid credentials (username/password)
3. Python 3.6+ installed
4. Trace files prepared (see below)

## Step 1: Prepare Trace Files

Create trace files for your test topology. You need traces with different router sets:

```bash
# Example: Create trace files directory
mkdir -p ~/tsim_traces

# Copy or create your trace JSON files
# Example trace structure:
{
  "path": [
    {"name": "routerA", "is_router": true},
    {"name": "routerB", "is_router": true},
    {"name": "host-dest", "is_router": false}
  ]
}
```

## Step 2: Update Configuration Files

Edit config files in `configs/` to point to your trace files:

```bash
cd tests/integration/configs

# Edit 01_single_detailed.conf
nano 01_single_detailed.conf
```

Replace `/path/to/traces/` with your actual trace file paths:

```
# Before:
/path/to/traces/trace_routerA_routerB.json ; detailed ; 80,443,22

# After:
/home/user/tsim_traces/trace_routerA_routerB.json ; detailed ; 80,443,22
```

## Step 3: Set Environment Variables

```bash
export TSIM_BASE_URL="http://your-tsim-server/tsim"
export TSIM_USERNAME="admin"
export TSIM_PASSWORD="your-password"
export TSIM_SOURCE_IP="10.0.1.1"
export TSIM_DEST_IP="10.0.2.1"
```

## Step 4: Run Tests

### Run Single Scenario

```bash
./test_parallel_jobs.py \
  --config configs/01_single_detailed.conf \
  --scenario 01_single_detailed \
  --username $TSIM_USERNAME \
  --password $TSIM_PASSWORD \
  --source-ip $TSIM_SOURCE_IP \
  --dest-ip $TSIM_DEST_IP
```

### Run All Scenarios

```bash
./run_all_scenarios.sh
```

## Step 5: Analyze Results

```bash
# Find latest results
LATEST=$(ls -t results/ | head -1)

# Analyze
./analyze_results.py results/$LATEST
```

## Example Output

```
======================================================================
  TSIM Parallel Job Integration Test Suite
======================================================================
  Timestamp:    20250309_143022
  Output:       results/20250309_143022
  Base URL:     http://localhost/tsim
  Username:     admin
  Source IP:    10.0.1.1
  Dest IP:      10.0.2.1
======================================================================

Running scenario: 01_single_detailed
Job 0 (detailed): SUCCESS (run_id: abc123, duration: 42.34s)

Scenario '01_single_detailed' completed:
  Total duration: 43.12s
  Success: 1/1
  Failed: 0/1
  Timeout: 0/1

...

======================================================================
  TEST SUITE SUMMARY
======================================================================
  Total Time:        312s (00:05:12)
  Total Scenarios:   11
  Passed:            11
  Failed:            0

  Results saved to: results/20250309_143022
======================================================================
```

## Troubleshooting

### Common Issues

**Authentication Failed:**
```bash
# Verify credentials
curl -u admin:password http://localhost/tsim/api/status
```

**Trace File Not Found:**
```bash
# Check file exists
ls -l /path/to/trace.json

# Verify file is valid JSON
python3 -m json.tool < /path/to/trace.json
```

**Jobs Timing Out:**
```bash
# Increase timeout
./run_all_scenarios.sh --timeout 1200
```

**Permission Denied on Scripts:**
```bash
# Make scripts executable
chmod +x test_parallel_jobs.py run_all_scenarios.sh analyze_results.py
```

### Viewing Results

```bash
# List all test runs
ls -lh results/

# View scenario results
cat results/20250309_143022/01_single_detailed/meta.json | python3 -m json.tool

# View PDFs
ls results/20250309_143022/*/*.pdf
```

## Next Steps

1. **Customize Scenarios**: Edit config files for your topology
2. **Add Scenarios**: Create new config files for additional test cases
3. **Regression Testing**: Use `--check` to compare runs
4. **Performance Analysis**: Use `analyze_results.py --compare` to track changes

## Quick Reference

### Environment Variables
```bash
TSIM_BASE_URL      # Base URL for TSIM API
TSIM_USERNAME      # Username for authentication
TSIM_PASSWORD      # Password for authentication
TSIM_SOURCE_IP     # Source IP address for tests
TSIM_DEST_IP       # Destination IP address for tests
TSIM_TIMEOUT       # Timeout per job (seconds)
```

### Key Commands
```bash
# Run single scenario
./test_parallel_jobs.py --config <conf> --scenario <name> [options]

# Run all scenarios
./run_all_scenarios.sh [options]

# Analyze results
./analyze_results.py results/<timestamp>

# Compare runs
./analyze_results.py results/<new> --compare results/<baseline>

# Check mode (regression)
./run_all_scenarios.sh --check results/<baseline>
```

### Config File Format
```
trace_file ; analysis_mode ; dest_ports
```

Example:
```
/path/to/trace.json ; detailed ; 80,443,22
/path/to/trace.json ; quick ; 80,443
```

## Support

For issues or questions:
1. Check the main README.md
2. Review docs/race_condition_elimination_plan.md
3. Examine test logs in results directory
4. Check TSIM server logs

## See Also

- [README.md](README.md) - Full documentation
- [Configuration Examples](configs/) - Sample configurations
- [Race Condition Plan](../../docs/race_condition_elimination_plan.md) - Architecture details
