# KSMS Test Suite

Comprehensive test suite for validating KSMS tester functionality including job queueing, parallel execution, DSCP registry management, and result correctness.

## Overview

The KSMS test suite provides automated testing capabilities for:

- **Serial Execution**: Sequential job processing validation
- **Parallel Execution**: Concurrent job execution with DSCP isolation testing
- **DSCP Exhaustion**: Registry limit and resource management validation  
- **Queue Management**: Job queueing and processing order testing
- **Error Handling**: Graceful handling of invalid inputs and edge cases
- **Result Correctness**: Validation against known expected outcomes

## Files

### `ksms_test_client.py`
Main test client with comprehensive test scenarios and reporting capabilities.

### `test_config_examples.json` 
Example test configurations for different testing scenarios:
- `basic_test_config`: Standard functionality testing
- `stress_test_config`: High-load and resource exhaustion testing  
- `parallel_performance_config`: Parallel execution performance validation

## Usage

### Basic Test Run
```bash
# Run all test scenarios with default configuration
python3 tests/ksms_test_client.py

# Run with increased verbosity
python3 tests/ksms_test_client.py -vv

# Save results to file
python3 tests/ksms_test_client.py --output /tmp/ksms_test_results.json
```

### Specific Test Scenarios
```bash
# Test only parallel execution capabilities
python3 tests/ksms_test_client.py --scenarios parallel

# Test DSCP exhaustion and queue management
python3 tests/ksms_test_client.py --scenarios dscp_exhaustion queue_management

# Test result correctness with custom tsimsh path
python3 tests/ksms_test_client.py --scenarios correctness --tsimsh-path /usr/local/bin/tsimsh
```

### Custom Test Configuration
```bash
# Use custom test configuration file
python3 tests/ksms_test_client.py --config tests/test_config_examples.json

# Extract specific configuration and run
jq '.basic_test_config' tests/test_config_examples.json > /tmp/my_test.json
python3 tests/ksms_test_client.py --config /tmp/my_test.json
```

## Test Scenarios

### 1. Serial Execution Test
Validates basic KSMS functionality with sequential job processing:
- Executes 5 basic jobs sequentially
- Measures total duration and per-job timing
- Validates success/failure rates

### 2. Parallel Execution Test  
Tests concurrent job execution capabilities:
- Runs jobs in batches of 8 concurrent executions
- Measures parallelism efficiency vs sequential execution
- Analyzes DSCP usage patterns and isolation
- Validates that jobs don't interfere with each other

### 3. DSCP Exhaustion Test
Tests system behavior when DSCP registry reaches capacity:
- Attempts to run 35 jobs simultaneously (exceeds 32 DSCP limit)
- Validates graceful handling of resource exhaustion
- Measures actual vs expected maximum concurrent jobs

### 4. Queue Management Test
Validates job queue processing:
- Rapidly submits 20 jobs 
- Monitors queue length and active job count over time
- Measures submission rate vs processing rate
- Validates FIFO job processing order

### 5. Error Handling Test
Tests graceful handling of invalid inputs:
- Invalid IP addresses (source and destination)
- Invalid port specifications and formats
- Empty or malformed port ranges
- Extremely large port ranges

### 6. Result Correctness Test
Validates accuracy of KSMS results against known expected outcomes:
- Compares actual vs expected results per service
- Calculates accuracy percentage
- Identifies discrepancies for debugging

## Test Results and Reporting

### JSON Output Format
```json
{
  "test_suite": "KSMS Comprehensive Test Suite",
  "timestamp": "2024-01-15T10:30:00",
  "summary": {
    "total_test_scenarios": 6,
    "total_individual_tests": 45,
    "parallel": {
      "type": "parallel_execution", 
      "parallelism_efficiency": 3.2,
      "success": true
    },
    "correctness": {
      "accuracy": 0.95,
      "success": true
    }
  },
  "detailed_results": {
    "serial": { /* detailed serial execution results */ },
    "parallel": { /* detailed parallel execution results */ },
    "dscp_exhaustion": { /* DSCP exhaustion test results */ },
    "queue_management": { /* queue management results */ },
    "error_handling": { /* error handling results */ },
    "correctness": { /* correctness validation results */ }
  },
  "recommendations": [
    "Parallelism efficiency is excellent at 3.2x speedup",
    "Result accuracy at 95% meets quality standards"
  ]
}
```

### Key Metrics

#### Performance Metrics
- **Parallelism Efficiency**: Ratio of sequential time to parallel time
- **Average Job Duration**: Mean execution time per job
- **Queue Processing Rate**: Jobs processed per second
- **DSCP Utilization**: Number of unique DSCP values used concurrently

#### Quality Metrics  
- **Success Rate**: Percentage of jobs completed successfully
- **Result Accuracy**: Percentage of results matching expected outcomes
- **Error Handling Rate**: Percentage of invalid inputs handled gracefully

#### Resource Metrics
- **Maximum Concurrent Jobs**: Peak number of simultaneous executions
- **DSCP Registry Usage**: Current and peak DSCP allocations
- **Queue Statistics**: Maximum queue length and processing throughput

## Test Environment Requirements

### Network Setup
Tests require a functional tsimsh environment with:
- Source and destination IP addresses accessible
- Network namespace support for packet isolation  
- iptables functionality for packet counting
- Sufficient IP address ranges for parallel testing

### System Resources
- **Memory**: Sufficient RAM for concurrent job execution
- **CPU**: Multi-core system recommended for parallel testing
- **Storage**: /dev/shm space for temporary test data
- **Network**: Low-latency network for accurate timing measurements

### Prerequisites
```bash
# Ensure tsimsh is available
which tsimsh

# Verify Python dependencies
python3 -c "import asyncio, json, logging, subprocess"

# Check system capabilities  
ls /dev/shm
iptables --version
ip netns list
```

## Troubleshooting

### Common Issues

1. **TSIMSH Not Found**
   ```bash
   # Specify full path to tsimsh
   python3 tests/ksms_test_client.py --tsimsh-path /path/to/tsimsh
   ```

2. **Permission Errors**  
   ```bash
   # Ensure proper permissions for network operations
   sudo python3 tests/ksms_test_client.py
   ```

3. **Timeout Errors**
   ```bash
   # Increase timeout in test configuration
   # Edit test_config_examples.json and increase "timeout" values
   ```

4. **Network Connectivity Issues**
   ```bash
   # Verify network setup
   ping 10.1.1.100
   ping 10.2.1.200
   
   # Check namespace connectivity
   tsimsh "ping 10.2.1.200"
   ```

### Debug Mode
```bash  
# Run with maximum verbosity for debugging
python3 tests/ksms_test_client.py -vvv --scenarios error_handling

# Enable detailed logging 
PYTHONPATH=. python3 -c "
import logging
logging.basicConfig(level=logging.DEBUG)
import tests.ksms_test_client
"
```

## Integration with CI/CD

### GitHub Actions Example
```yaml
name: KSMS Test Suite
on: [push, pull_request]
jobs:
  ksms-tests:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Setup test environment
      run: |
        sudo apt-get update
        sudo apt-get install -y iptables iproute2
    - name: Run KSMS tests
      run: |
        python3 tests/ksms_test_client.py --output ksms_results.json
    - name: Upload results
      uses: actions/upload-artifact@v3
      with:
        name: ksms-test-results
        path: ksms_results.json
```

### Jenkins Pipeline Example  
```groovy
pipeline {
    agent any
    stages {
        stage('KSMS Tests') {
            steps {
                sh 'python3 tests/ksms_test_client.py --scenarios parallel correctness'
                archiveArtifacts 'ksms_*.json'
                publishTestResults testResultsPattern: 'ksms_*.json'
            }
        }
    }
}
```

## Contributing

### Adding New Test Scenarios
1. Create new test method in `KsmsTestClient` class
2. Add scenario configuration option  
3. Update command-line argument parsing
4. Add scenario to `run_test_suite()` method
5. Update documentation and examples

### Test Data Management
- Use realistic IP addresses from test networks
- Avoid hardcoded expected results - use configuration files
- Include both positive and negative test cases
- Test edge cases and boundary conditions

### Performance Considerations  
- Parallel tests should not exceed system capabilities
- Use appropriate timeouts for different test types
- Monitor system resources during testing
- Clean up test artifacts after completion