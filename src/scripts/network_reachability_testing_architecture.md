# Network Reachability Testing Architecture

## Overview

This document outlines the architecture for testing network service reachability within the traceroute simulator environment using exclusively tsimsh commands. The solution determines whether a service running on a destination IP/port is reachable from a source IP (and optionally port), identifies the path packets would take through Linux routers, and pinpoints any blocking rules using iptables packet counts.

## Requirements

### Input Parameters
- **Source IP** (mandatory): The originating IP address
- **Source Port** (optional): The originating port number
- **Destination IP** (mandatory): The target IP address  
- **Destination Port** (mandatory): The target port number

### Output Requirements
1. Reachability status (reachable/unreachable)
2. Complete packet path through Linux routers
3. Analyze packet counts before/after test and report results (see below)
4. Step-by-step execution trace with intermediate results and step duration in seconds

## Solution Architecture

### Phase 1: Path Discovery (Real Network)

1. **Trace the network path**:
   ```bash
   echo "trace --source <SOURCE_IP> --destination <DESTINATION_IP> --json" | tsimsh -q
   TRACE_RESULT=$TSIM_RESULT
   ```
   - This is the ONLY operation performed on the real network
   - Provides bidirectional path information
   - JSON output contains router sequence
   - Store result in `$TRACE_RESULT` for parsing
   - Identifies all Linux routers that packets will traverse

### Phase 2: Simulation Environment Setup

1. **Add source host** to the network simulation:
   ```bash
   echo "host add --name src_host --primary-ip <SOURCE_IP>/24 --connect-to <ROUTER>" | tsimsh -q
   ```
   - Router selection based on source IP subnet matching

2. **Add destination host** to the network simulation:
   ```bash
   echo "host add --name dst_host --primary-ip <DESTINATION_IP>/24 --connect-to <ROUTER>" | tsimsh -q
   ```
   - Router selection based on destination IP subnet matching

3. **Start destination service**:
   ```bash
   echo "service start --ip <DESTINATION_IP> --port <DESTINATION_PORT> [--protocol tcp|udp]" | tsimsh -q
   ```

### Phase 3: Initial Reachability Test

1. **Test ICMP connectivity (ping)**:
   ```bash
   echo "ping --source <SOURCE_IP> --destination <DESTINATION_IP> --json" | tsimsh -q
   PING_RESULT=$TSIM_RESULT
   PING_RETURN=$TSIM_RETURN_VALUE
   ```
   - Basic layer 3 connectivity test
   - JSON output for parsing
   - Store result in `$PING_RESULT`
   - Check `$PING_RETURN` (0 = success, non-zero = failure)

2. **Test path with MTR**:
   ```bash
   echo "mtr --source <SOURCE_IP> --destination <DESTINATION_IP> --json" | tsimsh -q
   MTR_RESULT=$TSIM_RESULT
   MTR_RETURN=$TSIM_RETURN_VALUE
   ```
   - Detailed hop-by-hop connectivity analysis
   - JSON output with latency and packet loss per hop
   - Store result in `$MTR_RESULT`
   - Check `$MTR_RETURN` for success/failure

3. **Test service connectivity**:
   ```bash
   echo "service test --source <SOURCE_IP> --destination <DESTINATION_IP>:<DESTINATION_PORT> [--protocol tcp|udp] --json" | tsimsh -q
   SERVICE_RESULT=$TSIM_RESULT
   SERVICE_RETURN=$TSIM_RETURN_VALUE
   ```
   - Application layer connectivity test
   - JSON output for parsing
   - Store result in `$SERVICE_RESULT`
   - Check `$SERVICE_RETURN` (0 = success, non-zero = failure)

### Phase 4: Packet Count Analysis (**implemented**)

N.B. Packet analysis is fully implemented in ./analyze_packet_counts.py. Script usage example: ./test_packet_counting.sh
Use this script only - do not create any new code.
Following documentation is only to be seen as reference:

If the service test fails, analyze iptables rules on each router in the path:

1. **Capture initial packet counts** for each router:
   ```bash
   echo "network status --limit <ROUTER> iptables --json" | tsimsh -q
   IPTABLES_BEFORE_<ROUTER>=$TSIM_RESULT
   ```
   - Store baseline packet counts for all chains
   - Save each router's data in separate variable

2. **Attempt connection again**:
   ```bash
   echo "service test --source <SOURCE_IP> --destination <DESTINATION_IP>:<DESTINATION_PORT> [--protocol tcp|udp] --json" | tsimsh -q
   ```

3. **Capture final packet counts** for each router:
   ```bash
   echo "network status --limit <ROUTER> iptables --json" | tsimsh -q
   IPTABLES_AFTER_<ROUTER>=$TSIM_RESULT
   ```

4. **Compare packet counts**:
   - Parse JSON from `$IPTABLES_BEFORE_<ROUTER>` and `$IPTABLES_AFTER_<ROUTER>`
   - Identify rules where packet count increased
   - Rules with increased DROP/REJECT counts are blocking rules
   - Store all findings in a JSON object:
   ```
   PACKET_COUNT_ANALYSIS='{
     "routers_analyzed": ["hq-gw", "hq-core", "dc-core", "dc-srv"],
     "blocking_routers": [
       {
         "router": "dc-core",
         "chain": "FORWARD",
         "rule_number": 7,
         "rule_text": "-s 10.1.0.0/16 -d 10.3.20.0/24 -p tcp --dport 80 -j DROP",
         "action": "DROP",
         "packet_count_before": 152,
         "packet_count_after": 153,
         "packets_blocked": 1
       }
     ],
     "non_blocking_routers": ["hq-gw", "hq-core", "dc-srv"]
   }'
   ```

### Phase 5: Result Compilation

Generate comprehensive output in appropriate format:

1. **Determine output format**:
   - Check if running in batch mode (non-interactive)
   - If batch mode: output JSON
   - If interactive: output human-readable text

2. **Create final report**:
   - final report has to contain detailed results from each step (copy result JSON objects from previous steps verbatim)
   - final report has to contain summary section with most important findings


## Bash Script Usage

When using tsimsh commands in bash scripts, you must echo the commands to tsimsh with the `-q` (quiet) flag:

### Basic Command Structure
```bash
source /home/sparavec/tsim-venv/bin/activate && echo "<tsimsh_command>" | tsimsh -q
```

The `-q` flag runs tsimsh in quiet mode, suppressing the interactive prompt and making it suitable for scripting.

### Example Script
```bash
#!/bin/bash

# Set source and destination IPs
SRC_IP="10.1.1.100"
DST_IP="10.3.20.100"
DST_PORT="80"

# Trace the network path
TRACE_RESULT=`echo "trace --source $SRC_IP --destination $DST_IP --json" | tsimsh -q`

# Add source host to simulation
echo "host add --name src_host --primary-ip ${SRC_IP}/24 --connect-to hq-gw" | tsimsh -q

# Add destination host to simulation
echo "host add --name dst_host --primary-ip ${DST_IP}/24 --connect-to dc-srv" | tsimsh -q

# Start destination service
echo "service start --ip $DST_IP --port $DST_PORT --protocol tcp" | tsimsh -q

# Test connectivity with ping
PING_RESULT=`echo "ping --source $SRC_IP --destination $DST_IP --json" | tsimsh -q`

# Test service connectivity
SERVICE_RESULT=`echo "service test --source $SRC_IP --destination ${DST_IP}:${DST_PORT} --protocol tcp --json" | tsimsh -q`

# Cleanup
echo "service stop --ip ${DST_IP} --port ${DST_PORT}" --protocol tcp | tsimsh -q
echo "host remove --name src_host" | tsimsh -q
echo "host remove --name dst_host" | tsimsh -q
```

### Important Notes
- Always use the `-q` flag when piping to tsimsh in scripts
- When testing, always source venv first (see above for example)
- Check return codes with `$?` after each command
- Clean up resources (hosts, services) even if errors occur

## Implementation Algorithm

```
1. Parse input parameters (src_ip, src_port, dst_ip, dst_port)
2. Run trace command to discover router path (REAL NETWORK OPERATION)
3. Extract router list from trace results
4. Determine appropriate routers for host connections based on subnets
5. Add source and destination hosts to simulation
6. Start service on destination
7. Perform reachability tests:
   a. Run ping test and report result
   b. Run MTR test and report result
   c. Run service test and report result
8. If all tests succeed:
   - Report "Service is fully reachable"
   - Show packet path from trace results
9. If any test fails (especially service test):
   - For each router in path (from trace results):
     a. Get initial iptables packet counts
     b. Attempt connection
     c. Get final iptables packet counts
     d. Compare counts to find triggered rules
   - Identify blocking router and rule
   - Report findings
10. Cleanup:
    a. Stop service first
    b. Remove hosts (source and destination)
    c. Leave network setup unchanged
```

## Important Notes
1. Output has to be in single JSON object format only - no human readable messages printed whatsoever
2. Script should return result on its stdout, even if errors occur during execution
3. Return value: 0 if successful, 1 otherwise

## Key tsimsh Commands Used

1. **trace**: Discover the packet path through routers (REAL NETWORK)
2. **host add**: Create source/destination hosts in simulation
3. **service start**: Start the destination service
4. **ping**: Test ICMP connectivity (supports JSON output)
5. **mtr**: Test path connectivity with hop-by-hop analysis (supports JSON output)
6. **service test**: Test TCP/UDP service connectivity
7. **network status**: Retrieve iptables rules with packet counts

## Error Handling

- Validate all input parameters before proceeding
- Clean up resources even if errors occur:
  - Always stop services before removing hosts
  - Never modify the base network setup
  - Ensure cleanup runs even on script failure

## Advantages of This Approach

1. **Uses existing tsimsh commands** - no new functionality needed
2. **Non-invasive** - analyzes packet counts without modifying rules
3. **Accurate** - identifies exact blocking rule by observing counter changes
4. **Comprehensive** - provides full path and blocking details
5. **Automated** - entire process can be scripted in tsimsh

## JSON Processing Capabilities

The tsimsh shell provides comprehensive JSON handling capabilities that enable all required operations:

### Automatic JSON Parsing
- Command outputs with `-j` or `--json` flag are automatically parsed into objects
- Variables storing JSON strings are automatically converted to dictionaries/lists

### Ping and MTR JSON Output Formats

The ping and mtr commands support JSON output with the `-j` or `--json` flag. The JSON output includes:
- Complete namespace information (source and destination)
- Full command output (same as `-v` mode)
- Parsed statistics for easier programmatic access
- Router information for understanding the network path

**Important**: When there are multiple Linux routers on the path between source and destination, the ping and mtr commands will generate **one test per router**. For example:
- If trace shows 3 Linux routers on the path, there will be 3 tests in the tests array
- Each test represents connectivity testing through a specific router
- Each test will have two hosts (source and destination) with one router in between

#### Ping JSON Output

Example with 3 Linux routers on the path:
```json
{
  "summary": {
    "total_tests": 3,
    "passed": 3,
    "failed": 0,
    "pass_rate": 100.0,
    "all_passed": true
  },
  "tests": [
    {
      "source": {
        "namespace": "host1",
        "namespace_type": "host",
        "ip": "10.1.1.100"
      },
      "destination": {
        "namespace": "host2",
        "namespace_type": "host",
        "ip": "10.2.1.200"
      },
      "router": "hq-gw",
      "test_type": "PING",
      "success": true,
      "summary": "PING successful",
      "output": "PING 10.2.1.200 (10.2.1.200) from 10.1.1.100 : 56(84) bytes of data.\n64 bytes from 10.2.1.200: icmp_seq=1 ttl=63 time=2.36 ms\n64 bytes from 10.2.1.200: icmp_seq=2 ttl=63 time=2.27 ms\n64 bytes from 10.2.1.200: icmp_seq=3 ttl=63 time=2.36 ms\n\n--- 10.2.1.200 ping statistics ---\n3 packets transmitted, 3 received, 0% packet loss, time 2003ms\nrtt min/avg/max/mdev = 2.269/2.327/2.359/0.041 ms",
      "ping_stats": {
        "packets_transmitted": 3,
        "packets_received": 3,
        "packet_loss_percent": 0.0
      },
      "ping_rtt": {
        "min": 2.269,
        "avg": 2.327,
        "max": 2.359,
        "mdev": 0.041
      }
    },
    {
      "source": {
        "namespace": "host1",
        "namespace_type": "host",
        "ip": "10.1.1.100"
      },
      "destination": {
        "namespace": "host2",
        "namespace_type": "host",
        "ip": "10.2.1.200"
      },
      "router": "hq-core",
      "test_type": "PING",
      "success": true,
      "summary": "PING successful",
      "output": "[ping output through hq-core]",
      "ping_stats": {
        "packets_transmitted": 3,
        "packets_received": 3,
        "packet_loss_percent": 0.0
      },
      "ping_rtt": {
        "min": 2.456,
        "avg": 2.512,
        "max": 2.587,
        "mdev": 0.055
      }
    },
    {
      "source": {
        "namespace": "host1",
        "namespace_type": "host",
        "ip": "10.1.1.100"
      },
      "destination": {
        "namespace": "host2",
        "namespace_type": "host",
        "ip": "10.2.1.200"
      },
      "router": "br-gw",
      "test_type": "PING",
      "success": true,
      "summary": "PING successful",
      "output": "[ping output through br-gw]",
      "ping_stats": {
        "packets_transmitted": 3,
        "packets_received": 3,
        "packet_loss_percent": 0.0
      },
      "ping_rtt": {
        "min": 2.789,
        "avg": 2.845,
        "max": 2.923,
        "mdev": 0.058
      }
    }
  ]
}
```

#### MTR JSON Output

Example with 3 Linux routers on the path:
```json
{
  "summary": {
    "total_tests": 3,
    "passed": 3,
    "failed": 0,
    "pass_rate": 100.0,
    "all_passed": true
  },
  "tests": [
    {
      "source": {
        "namespace": "host1",
        "namespace_type": "host",
        "ip": "10.1.1.100"
      },
      "destination": {
        "namespace": "dc-srv",
        "namespace_type": "router",
        "ip": "10.3.20.2"
      },
      "router": "hq-gw",
      "test_type": "MTR",
      "success": true,
      "summary": "MTR successful",
      "output": "HOST: host1                       Loss%   Snt   Last   Avg  Best  Wrst StDev\n  1.|-- 10.1.1.1                   0.0%     1    0.5   0.5   0.5   0.5   0.0\n  2.|-- 10.1.0.1                   0.0%     1    1.2   1.2   1.2   1.2   0.0\n  3.|-- 172.16.0.2                 0.0%     1    2.1   2.1   2.1   2.1   0.0\n  4.|-- 10.3.20.2                  0.0%     1    2.8   2.8   2.8   2.8   0.0",
      "mtr_hops": [
        {
          "hop": "1",
          "ip": "10.1.1.1",
          "namespace": "hq-gw",
          "namespace_type": "router"
        },
        {
          "hop": "2",
          "ip": "10.1.0.1",
          "namespace": "hq-core",
          "namespace_type": "router"
        },
        {
          "hop": "3",
          "ip": "172.16.0.2",
          "namespace": "dc-core",
          "namespace_type": "router"
        },
        {
          "hop": "4",
          "ip": "10.3.20.2",
          "namespace": "dc-srv",
          "namespace_type": "router"
        }
      ]
    },
    {
      "source": {
        "namespace": "host1",
        "namespace_type": "host",
        "ip": "10.1.1.100"
      },
      "destination": {
        "namespace": "dc-srv",
        "namespace_type": "router",
        "ip": "10.3.20.2"
      },
      "router": "hq-core",
      "test_type": "MTR",
      "success": true,
      "summary": "MTR successful",
      "output": "[MTR output through hq-core]",
      "mtr_hops": [
        {
          "hop": "1",
          "ip": "10.1.0.1",
          "namespace": "hq-core",
          "namespace_type": "router"
        },
        {
          "hop": "2",
          "ip": "172.16.0.2",
          "namespace": "dc-core",
          "namespace_type": "router"
        },
        {
          "hop": "3",
          "ip": "10.3.20.2",
          "namespace": "dc-srv",
          "namespace_type": "router"
        }
      ]
    },
    {
      "source": {
        "namespace": "host1",
        "namespace_type": "host",
        "ip": "10.1.1.100"
      },
      "destination": {
        "namespace": "dc-srv",
        "namespace_type": "router",
        "ip": "10.3.20.2"
      },
      "router": "dc-core",
      "test_type": "MTR",
      "success": true,
      "summary": "MTR successful",
      "output": "[MTR output through dc-core]",
      "mtr_hops": [
        {
          "hop": "1",
          "ip": "10.3.20.1",
          "namespace": "dc-core",
          "namespace_type": "router"
        },
        {
          "hop": "2",
          "ip": "10.3.20.2",
          "namespace": "dc-srv",
          "namespace_type": "router"
        }
      ]
    }
  ]
}
```

#### Some Key JSON Fields

- **source/destination**: Contains namespace information
  - `namespace`: The actual namespace where the test originates/terminates
  - `namespace_type`: Either "host" or "router"
  - `ip`: The IP address used
  
- **router**: The router through which the test is performed (when source is a host)

- **tests array**: Contains one test entry per Linux router on the path
  - If trace shows 3 Linux routers, tests array will have 3 elements
  - Each test simulates connectivity through a specific router
  - All tests use the same source and destination hosts

- **output**: Complete command output, identical to what you see with `-v`

- **ping_stats**: Parsed ping statistics (packets transmitted/received, loss percentage)

- **ping_rtt**: Round-trip time statistics (min/avg/max/mdev in milliseconds)

- **mtr_hops**: For MTR tests, shows each hop in the path with namespace mapping
