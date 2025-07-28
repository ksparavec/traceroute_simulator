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
3. If blocked: identify blocking router and specific iptables rule
4. Step-by-step execution trace with intermediate results

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

### Phase 4: Packet Count Analysis (for unreachable services)

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

2. **Create final report structure**:
   ```json
   {
     "summary": {
       "service_reachable": false,
       "test_performed": "TCP service on 10.3.20.100:80 from 10.1.1.100",
       "overall_result": "Service is BLOCKED by firewall rules"
     },
     "connectivity_tests": {
       "layer3_ping": {
         "status": "success",
         "description": "Basic network connectivity works"
       },
       "path_mtr": {
         "status": "success", 
         "description": "All routers along the path are responding"
       },
       "service_test": {
         "status": "failed",
         "description": "TCP connection to port 80 was blocked"
       }
     },
     "network_path": {
       "routers": ["hq-gw", "hq-core", "dc-core", "dc-srv"],
       "description": "Packets travel through 4 routers from source to destination"
     },
     "blocking_analysis": {
       "blocked": true,
       "blocking_points": [
         {
           "router": "dc-core",
           "explanation": "This router blocked the connection",
           "rule_description": "Firewall rule blocks all web traffic (port 80) from HQ network (10.1.0.0/16) to datacenter servers (10.3.20.0/24)",
           "technical_details": {
             "chain": "FORWARD",
             "rule_number": 7,
             "action": "DROP"
           }
         }
       ]
     },
     "recommendations": [
       "Contact network administrator to allow web traffic from HQ to datacenter servers",
       "Specify source IP 10.1.1.100 and destination 10.3.20.100:80 in the request"
     ]
   }
   ```

3. **Human-readable format** (for interactive mode):
   - Use clear headings and explanations
   - Avoid technical jargon where possible
   - Provide actionable recommendations

## Bash Script Usage

When using tsimsh commands in bash scripts, you must echo the commands to tsimsh with the `-q` (quiet) flag:

### Basic Command Structure
```bash
echo "<tsimsh_command>" | tsimsh -q
```

The `-q` flag runs tsimsh in quiet mode, suppressing the interactive prompt and making it suitable for scripting.

### Capturing Output
After each command, the results are available in special variables:
- `$TSIM_RESULT` - Contains the command output (JSON for commands with --json flag)
- `$TSIM_RETURN_VALUE` - Contains the command return code (0 for success, non-zero for failure)

### Example Script
```bash
#!/bin/bash

# Set source and destination IPs
SRC_IP="10.1.1.100"
DST_IP="10.3.20.100"
DST_PORT="80"

# Trace the network path
echo "trace --source $SRC_IP --destination $DST_IP --json" | tsimsh -q
if [ $? -ne 0 ]; then
    echo "Failed to trace network path"
    exit 1
fi
TRACE_RESULT=$TSIM_RESULT

# Add source host to simulation
echo "host add --name src_host --primary-ip ${SRC_IP}/24 --connect-to hq-gw" | tsimsh -q

# Add destination host to simulation
echo "host add --name dst_host --primary-ip ${DST_IP}/24 --connect-to dc-srv" | tsimsh -q

# Start destination service
echo "service start --ip $DST_IP --port $DST_PORT --protocol tcp" | tsimsh -q

# Test connectivity with ping
echo "ping --source $SRC_IP --destination $DST_IP --json" | tsimsh -q
PING_RESULT=$TSIM_RESULT
PING_RETURN=$TSIM_RETURN_VALUE

# Test service connectivity
echo "service test --source $SRC_IP --destination ${DST_IP}:${DST_PORT} --protocol tcp --json" | tsimsh -q
SERVICE_RESULT=$TSIM_RESULT
SERVICE_RETURN=$TSIM_RETURN_VALUE

# Cleanup
echo "service stop --ip ${DST_IP}:${DST_PORT}" | tsimsh -q
echo "host remove --name src_host" | tsimsh -q
echo "host remove --name dst_host" | tsimsh -q

# Check results
if [ "$SERVICE_RETURN" -eq 0 ]; then
    echo "Service is reachable"
else
    echo "Service is blocked"
fi
```

### Working with JSON Results in Bash

When using JSON output in bash scripts, you need to access the data through tsimsh variable operations:

```bash
# Get JSON result
echo "ping --source $SRC_IP --destination $DST_IP --json" | tsimsh -q
PING_RESULT=$TSIM_RESULT

# Access JSON fields through tsimsh
echo "ALL_PASSED=\$PING_RESULT.summary.all_passed" | tsimsh -q
echo "PACKET_LOSS=\$PING_RESULT.tests[0].ping_stats.packet_loss_percent" | tsimsh -q

# Use the extracted values in bash
if [ "$ALL_PASSED" = "true" ]; then
    echo "All tests passed"
fi
```

### Important Notes
- Always use the `-q` flag when piping to tsimsh in scripts
- Variable assignments inside tsimsh need escaped dollar signs (`\$`)
- Check return codes with `$?` after each command
- JSON data must be accessed through tsimsh variable operations
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

## Key tsimsh Commands Used

1. **trace**: Discover the packet path through routers (REAL NETWORK)
2. **host add**: Create source/destination hosts in simulation
3. **service start**: Start the destination service
4. **ping**: Test ICMP connectivity (supports JSON output)
5. **mtr**: Test path connectivity with hop-by-hop analysis (supports JSON output)
6. **service test**: Test TCP/UDP service connectivity
7. **network status**: Retrieve iptables rules with packet counts
8. **Variable operations**: Store and manipulate command outputs

## Error Handling

- Validate all input parameters before proceeding
- Check command return values via `$TSIM_RETURN_VALUE`
- Handle cases where hosts cannot be added (subnet mismatch)
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

#### Key JSON Fields

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

### Accessing JSON Data

#### Working with Ping/MTR JSON Results
```bash
# Run ping test and capture JSON
echo "ping --source $SRC_IP --destination $DST_IP --json" | tsimsh -q
PING_RESULT=$TSIM_RESULT

# Check if all tests passed
echo "ALL_PASSED=\$PING_RESULT.summary.all_passed" | tsimsh -q
if [ "$ALL_PASSED" = "true" ]; then
    echo "All ping tests passed"
fi

# Get packet loss percentage from first test
echo "PACKET_LOSS=\$PING_RESULT.tests[0].ping_stats.packet_loss_percent" | tsimsh -q

# Get average RTT
echo "AVG_RTT=\$PING_RESULT.tests[0].ping_rtt.avg" | tsimsh -q

# Get source namespace information
echo "SOURCE_NS=\$PING_RESULT.tests[0].source.namespace" | tsimsh -q
echo "SOURCE_TYPE=\$PING_RESULT.tests[0].source.namespace_type" | tsimsh -q

# Run MTR and get hop count
echo "mtr --source $SRC_IP --destination $DST_IP --json" | tsimsh -q
MTR_RESULT=$TSIM_RESULT
echo "HOP_COUNT=\$MTR_RESULT.tests[0].mtr_hops.length()" | tsimsh -q

# List all routers in MTR path
for i in $(seq 0 $(($HOP_COUNT - 1))); do
    echo "HOP_NS=\$MTR_RESULT.tests[0].mtr_hops[$i].namespace" | tsimsh -q
    echo "HOP_IP=\$MTR_RESULT.tests[0].mtr_hops[$i].ip" | tsimsh -q
    echo "Hop $i: $HOP_NS ($HOP_IP)"
done
```

#### Working with Trace Results
```bash
# Extract router list from trace result
echo "trace --source $SRC_IP --destination $DST_IP --json" | tsimsh -q
TRACE_RESULT=$TSIM_RESULT
echo "ROUTERS=\$TRACE_RESULT.traceroute_path" | tsimsh -q

# Access nested values
echo "ROUTER_NAME=\$TRACE_RESULT.traceroute_path[0].name" | tsimsh -q

# Get array length
echo "ROUTER_COUNT=\$TRACE_RESULT.traceroute_path.length()" | tsimsh -q
```

### Comparing Packet Counts
```bash
# Store iptables data before and after
echo "network status --limit $ROUTER iptables --json" | tsimsh -q
IPTABLES_BEFORE=$TSIM_RESULT
echo "network status --limit $ROUTER iptables --json" | tsimsh -q
IPTABLES_AFTER=$TSIM_RESULT

# Access specific chain and rule
CHAIN="FORWARD"
RULE_INDEX=7

# Get packet counts
echo "BEFORE_COUNT=\$IPTABLES_BEFORE.iptables.filter[$CHAIN][$RULE_INDEX].packets" | tsimsh -q
echo "AFTER_COUNT=\$IPTABLES_AFTER.iptables.filter[$CHAIN][$RULE_INDEX].packets" | tsimsh -q

# Compare values
if [ "$AFTER_COUNT" -gt "$BEFORE_COUNT" ]; then
    PACKETS_BLOCKED=$(($AFTER_COUNT - $BEFORE_COUNT))
    echo "RULE_TEXT=\$IPTABLES_AFTER.iptables.filter[$CHAIN][$RULE_INDEX].rule" | tsimsh -q
fi
```

### Building Result JSON
```bash
# Initialize result structure
echo "BLOCKING_ROUTERS='[]'" | tsimsh -q
echo "NON_BLOCKING_ROUTERS='[]'" | tsimsh -q

# Add to arrays dynamically
# Note: Full JSON construction would be done through variable manipulation

# Access methods
echo "KEYS=\$IPTABLES_RESULT.iptables.filter.keys()" | tsimsh -q  # Get chain names
echo "VALUES=\$IPTABLES_RESULT.iptables.filter.values()" | tsimsh -q  # Get chain data
```

### Variable Features Used
- **Nested access**: `$VAR.key1.key2[index]`
- **Array indexing**: `$VAR[0]`, `$VAR[-1]`
- **Method calls**: `.length()`, `.keys()`, `.values()`
- **Dynamic key access**: `$VAR[$KEY_VARIABLE]`
- **Arithmetic**: `$(($VAR1 - $VAR2))`
- **Conditionals**: Numeric and string comparisons

## Example Output Formats

### Interactive Mode (Human-Readable)

```
=== Network Service Reachability Test ===

Testing: Can 10.1.1.100 reach web service on 10.3.20.100:80?

[Step 1/5] Discovering network path...
✓ Path found: Your connection goes through 4 routers

[Step 2/5] Setting up test environment...
✓ Test environment ready

[Step 3/5] Running connectivity tests...
✓ Basic network connectivity (ping): SUCCESS
  - The destination computer is reachable on the network
✓ Path connectivity (mtr): SUCCESS  
  - All routers along the path are working properly
✗ Service connectivity: FAILED
  - Cannot connect to web service on port 80

[Step 4/5] Analyzing why the connection failed...
✓ Found the blocking point

[Step 5/5] Cleaning up...
✓ Cleanup complete

=== RESULTS ===

Status: SERVICE BLOCKED

What happened:
- Your computer CAN reach the destination on the network
- But a firewall is blocking access to the web service

Where it's blocked:
- Router: dc-core (datacenter core router)
- Reason: Security rule blocks web traffic from HQ network to datacenter servers

What to do:
1. Contact your network administrator
2. Request access from source IP 10.1.1.100 to 10.3.20.100 port 80
3. Reference blocking rule: "HQ to DC web traffic restriction"

Technical details (for administrator):
- Blocking router: dc-core
- Firewall chain: FORWARD
- Rule #7: -s 10.1.0.0/16 -d 10.3.20.0/24 -p tcp --dport 80 -j DROP
```

### Batch Mode (JSON)

```json
{
  "summary": {
    "service_reachable": false,
    "source": "10.1.1.100",
    "destination": "10.3.20.100:80",
    "protocol": "tcp",
    "overall_result": "Service blocked by firewall",
    "test_timestamp": "2024-01-15T14:32:10Z"
  },
  "connectivity_tests": {
    "ping": {
      "success": true,
      "description": "Basic network connectivity works",
      "return_code": 0
    },
    "mtr": {
      "success": true,
      "description": "All routers responding along path",
      "return_code": 0,
      "hop_count": 4
    },
    "service": {
      "success": false,
      "description": "TCP connection blocked",
      "return_code": 1
    }
  },
  "network_path": {
    "routers": [
      {
        "name": "hq-gw",
        "incoming_interface": "eth0",
        "incoming_ip": "10.1.1.1",
        "outgoing_interface": "eth1",
        "outgoing_ip": "10.1.0.1"
      },
      {
        "name": "hq-core",
        "incoming_interface": "eth0",
        "incoming_ip": "10.1.0.2",
        "outgoing_interface": "eth2",
        "outgoing_ip": "172.16.0.1"
      },
      {
        "name": "dc-core",
        "incoming_interface": "eth0",
        "incoming_ip": "172.16.0.2",
        "outgoing_interface": "eth2",
        "outgoing_ip": "10.3.20.1"
      },
      {
        "name": "dc-srv",
        "incoming_interface": "eth0",
        "incoming_ip": "10.3.20.2",
        "outgoing_interface": null,
        "outgoing_ip": null
      }
    ],
    "source_host": {
      "ip": "10.1.1.100",
      "connected_to": "hq-gw"
    },
    "destination_host": {
      "ip": "10.3.20.100",
      "connected_to": "dc-srv",
      "service_port": 80,
      "service_protocol": "tcp"
    }
  },
  "blocking_analysis": {
    "service_blocked": true,
    "blocking_routers": [
      {
        "router": "dc-core",
        "rule_description": "Blocks web traffic from HQ to datacenter",
        "source_match": "10.1.0.0/16",
        "destination_match": "10.3.20.0/24",
        "port_match": "80",
        "action": "DROP",
        "chain": "FORWARD",
        "rule_number": 7,
        "packets_blocked": 1,
        "rule_text": "-s 10.1.0.0/16 -d 10.3.20.0/24 -p tcp --dport 80 -j DROP"
      }
    ],
    "non_blocking_routers": ["hq-gw", "hq-core", "dc-srv"],
    "analysis_method": "packet_count_comparison"
  },
  "recommendations": [
    "Request firewall exception for 10.1.1.100 to 10.3.20.100:80",
    "Reference blocking rule on router dc-core, FORWARD chain, rule #7"
  ],
  "debug_info": {
    "trace_command": "trace --source 10.1.1.100 --destination 10.3.20.100 --json",
    "simulation_hosts_created": ["src_host", "dst_host"],
    "services_started": ["10.3.20.100:80/tcp"],
    "cleanup_performed": true
  }
}
```