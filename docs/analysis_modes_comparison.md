# Network Analysis Modes: Quick vs. Detailed Analysis

## Overview

The Network Service Reachability Analyzer provides two distinct analysis modes, each optimized for different use cases. This document provides comprehensive technical details about both modes to help users and administrators make informed decisions.

## Analysis Modes

### Quick Analysis Mode

**Purpose**: Rapid service reachability testing across multiple services and routers simultaneously.

**Technology**: KSMS (Kernel-Space Multi-Service) tester with DSCP-based traffic tagging for parallel execution.

**Use Cases**:
- Initial network reconnaissance
- Bulk service discovery (10-1000+ services)
- Quick health checks
- Pre-change validation baseline
- Compliance checks requiring simple YES/NO answers

### Detailed Analysis Mode

**Purpose**: Comprehensive firewall rule analysis with precise iptables counter tracking and packet-level diagnostics.

**Technology**: MultiServiceTester with sequential service testing, iptables counter analysis, and packet tracing.

**Use Cases**:
- Troubleshooting blocked connections
- Firewall rule verification
- Identifying specific blocking rules
- Security audits requiring detailed evidence
- Post-incident analysis

## Technical Architecture

### Quick Analysis Architecture

**Quick Analysis Flow:**

| Step | Phase | Description | Details |
| ---- | ----- | ----------- | ------- |
| 1 | Parse Arguments & Create Run Directory | Initialize test environment | Allocate unique DSCP value (32-63 range) |
| 2 | Setup Source Hosts | Create minimal source hosts on routers | Source hosts created from trace file |
| 3 | Execute KSMS Bulk Scan | Test all services simultaneously | All services tested in parallel; DSCP tagging prevents cross-job interference; Kernel-space packet processing (high performance); Returns: YES/NO/UNKNOWN per router per service |
| 4 | Cleanup Source Hosts | Remove created network namespaces | Remove all created source hosts |
| 5 | Generate Summary PDF | Create report | Single-page reachability matrix |
| 6 | Release DSCP & Complete | Finalize | Release DSCP value for next job |

**Key Components**:
- **KSMS Tester**: Kernel-space network testing tool using raw sockets
- **DSCP Registry**: Manages differentiated services code points (32-63) for traffic isolation
- **DSCP Tagging**: Each job gets unique DSCP value to prevent packet collision
- **Parallel Execution**: Up to 32 concurrent quick analysis jobs
- **Router-Based Output**: Results organized by router with nested services

### Detailed Analysis Architecture

**Detailed Analysis Flow:**

| Step | Phase | Description | Details |
| ---- | ----- | ----------- | ------- |
| 1 | Parse Arguments & Create Run Directory | Initialize test environment | Create run directory structure |
| 2 | Setup Source & Destination Hosts | Create full network topology | Create hosts on ALL routers (full topology) |
| 3a | Start Service on Destination | Launch service listener | Launch actual TCP/UDP listener |
| 3b | Get iptables Counters BEFORE | Snapshot firewall state | Snapshot all router firewall counters |
| 3c | Execute Traceroute Test | Test network connectivity | Test connectivity from each source host |
| 3d | Execute Service Test | Test actual service | Actual connection attempts to service |
| 3e | Get iptables Counters AFTER | Snapshot firewall state | Snapshot firewall counters again |
| 3f | Analyze Packet Counts | Identify firewall rules | Compare BEFORE vs AFTER counters; Identify allowing rules (counter increase); Identify blocking rules (counter increase); Generate per-service detailed analysis |
| 3g | Stop Service | Cleanup service | Stop service listener |
| 3h | Save Service Results | Store results | Individual JSON file per service |
| 3 | (Repeat steps 3a-3h) | Sequential Service Testing Loop | Repeat for each service (port/protocol) |
| 4 | Cleanup All Hosts & Services | Remove all test components | Remove all created network namespaces and services |
| 5 | Generate Comprehensive PDF | Create detailed report | Summary page with all services; Per-service detailed pages; Network topology diagrams; Firewall rule analysis; Packet counter evidence |

**Key Components**:
- **MultiServiceTester**: Python-based orchestrator for sequential testing
- **Network Status Tool**: Captures iptables rules and counters as JSON
- **Packet Tracer**: Analyzes which rules processed packets (counter deltas)
- **Service Commands**: Actual TCP/UDP listeners for authoritative testing
- **iptables Log Processor**: Analyzes firewall rules and packet counters
- **Service-Based Output**: Results organized by service with nested router info

## DSCP Registry and Parallel Execution

### DSCP Allocation (Quick Analysis Only)

The DSCP registry enables parallel execution of quick analysis jobs by assigning unique DSCP values:

```python
# DSCP range: 32-63 (32 values available)
- Job 1: DSCP 32
- Job 2: DSCP 33
- Job 3: DSCP 34
...
- Job 32: DSCP 63
```

**Benefits**:
- Prevents packet collision between concurrent jobs
- Enables up to 32 simultaneous quick analyses
- Automatic cleanup on job completion or failure
- Thread-safe allocation and release

**Note**: Detailed analysis does NOT use DSCP tagging and requires global network lock (serial execution).

## Data Structures and Output Formats

### Quick Analysis Output (Router-Based Structure)

```json
{
  "source": "10.1.1.100",
  "destination": "10.2.1.200",
  "routers": [
    {
      "name": "hq-gw",
      "iface": "eth0",
      "services": [
        {"port": 22, "protocol": "tcp", "result": "YES"},
        {"port": 80, "protocol": "tcp", "result": "NO"},
        {"port": 443, "protocol": "tcp", "result": "YES"}
      ]
    },
    {
      "name": "br-gw",
      "iface": "eth1",
      "services": [
        {"port": 22, "protocol": "tcp", "result": "UNKNOWN"},
        {"port": 80, "protocol": "tcp", "result": "NO"},
        {"port": 443, "protocol": "tcp", "result": "YES"}
      ]
    }
  ]
}
```

**Result Values**:
- `YES`: Service is reachable through this router
- `NO`: Service is blocked/unreachable through this router
- `UNKNOWN`: Unable to determine (network/routing issues)

### Detailed Analysis Output (Service-Based Structure)

```json
{
  "timestamp": "2025-10-09 14:23:45",
  "version": "2.0.0",
  "summary": {
    "source_ip": "10.1.1.100",
    "source_port": "52500",
    "destination_ip": "10.2.1.200",
    "destination_port": "443",
    "protocol": "tcp"
  },
  "reachability_tests": {
    "traceroute": {
      "result": {
        "summary": {
          "total_tests": 2,
          "passed": 2,
          "failed": 0,
          "pass_rate": 100.0
        },
        "tests": [
          {
            "source": {"namespace": "source-1", "ip": "10.1.1.100"},
            "destination": {"namespace": "destination-1", "ip": "10.2.1.200"},
            "router": "hq-gw",
            "success": true
          }
        ]
      }
    },
    "service": {
      "result": {
        "summary": {
          "total_tests": 2,
          "successful": 1,
          "failed": 1,
          "overall_status": "PARTIAL"
        },
        "tests": [
          {
            "source_host": "source-1",
            "source_ip": "10.1.1.100",
            "source_port": 52500,
            "destination_host": "destination-1",
            "destination_ip": "10.2.1.200",
            "destination_port": 443,
            "via_router": "hq-gw",
            "incoming_interface": "eth0",
            "outgoing_interface": "wg0",
            "status": "OK",
            "message": "Connection successful",
            "allowing_rules": [
              {
                "chain": "FORWARD",
                "rule": "-A FORWARD -i eth0 -o wg0 -j ACCEPT",
                "packets_before": 15234,
                "packets_after": 15236,
                "packet_increase": 2
              }
            ],
            "blocking_rules": []
          },
          {
            "source_host": "source-2",
            "source_ip": "10.1.1.100",
            "destination_ip": "10.2.1.200",
            "destination_port": 443,
            "via_router": "br-gw",
            "status": "FAIL",
            "message": "Connection blocked by firewall",
            "allowing_rules": [],
            "blocking_rules": [
              {
                "chain": "FORWARD",
                "rule": "-A FORWARD -i eth1 -p tcp --dport 443 -j DROP",
                "packets_before": 8921,
                "packets_after": 8923,
                "packet_increase": 2
              }
            ]
          }
        ]
      }
    }
  },
  "iptables_analysis": {
    "routers_analyzed": 2,
    "rules_allowing": 15,
    "rules_blocking": 3,
    "rules_no_match": 127
  }
}
```

## iptables Counter Analysis (Detailed Mode Only)

### How Counter Analysis Works

1. **Snapshot BEFORE Test**:
   ```bash
   network status --json --limit hq-gw iptables
   ```
   Captures all iptables rules with current packet counters.

2. **Execute Service Test**:
   - Actual TCP/UDP connection attempts
   - Packets traverse firewall rules
   - Matching rules increment counters

3. **Snapshot AFTER Test**:
   ```bash
   network status --json --limit hq-gw iptables
   ```
   Captures updated packet counters.

4. **Analyze Deltas**:
   ```
   For each rule:
     delta = packets_after - packets_before
     if delta > 0:
       This rule processed packets from our test
   ```

### Example Counter Analysis

**BEFORE Test**:
```
Chain FORWARD (policy DROP 0 packets)
pkts  target     prot opt source      destination
15234 ACCEPT     all  --  0.0.0.0/0   0.0.0.0/0
8921  DROP       tcp  --  0.0.0.0/0   0.0.0.0/0   tcp dpt:443
```

**AFTER Test**:
```
Chain FORWARD (policy DROP 0 packets)
pkts  target     prot opt source      destination
15236 ACCEPT     all  --  0.0.0.0/0   0.0.0.0/0      <-- +2 packets
8923  DROP       tcp  --  0.0.0.0/0   0.0.0.0/0   tcp dpt:443  <-- +2 packets
```

**Analysis**:
- ACCEPT rule: +2 packets = Allowed outbound traffic
- DROP rule: +2 packets = Blocked return traffic
- Result: Partial connectivity (outbound OK, return blocked)

## Performance Characteristics

### Quick Analysis Performance

**Fixed Steps** (independent of service count):
1. Create source hosts
2. KSMS bulk scan (all services simultaneously)
3. Cleanup hosts
4. Generate PDF

**Total Time**: Constant time regardless of service count

**Parallelization**:
- Up to 32 concurrent jobs (DSCP limit)
- No global network lock required
- Can run alongside detailed analysis

**Resource Usage**:
- Minimal CPU (kernel-space processing)
- Low memory footprint
- No service listeners needed
- Temporary namespaces only

### Detailed Analysis Performance

**Per-Service Steps**:
1. Start service
2. Get iptables BEFORE
3. Run traceroute
4. Run service test
5. Get iptables AFTER
6. Analyze counters
7. Stop service
8. Save results

**Total Time Per Service**: Multiple steps per service

**Total Time for N Services**: Linear time scaling with service count (O(N))

**Parallelization**:
- Serial execution only (one detailed job at a time)
- Requires global network lock
- Services tested sequentially within job

**Resource Usage**:
- Higher CPU (user-space Python processing)
- Moderate memory (JSON snapshots per router)
- Service listeners for each test
- Full network topology (source + destination hosts)

## PDF Report Differences

### Quick Analysis PDF

**Structure**:
- Single summary page
- Reachability matrix (routers x services)
- Color-coded results ([YES], [NO], [UNKNOWN])
- Test parameters and metadata
- Quick statistics summary

**Content**:

Example Quick Analysis PDF contains:

**Test Parameters:**
- Source IP: 10.1.1.100
- Destination IP: 10.2.1.200
- Analysis Mode: Quick
- Services Tested: 10

**Test Summary:**
- Total Tests: 20 (2 routers x 10 svc)
- Successful: 14
- Failed: 4
- Unknown: 2
- Overall Status: PARTIAL

**Service Test Results:**

| Port | Protocol | hq-gw | br-gw |
| ---- | -------- | ----- | ----- |
| 22 | tcp | YES | NO |
| 80 | tcp | NO | NO |
| 443 | tcp | YES | YES |

Note: For detailed iptables rule analysis, run Detailed Analysis mode.

### Detailed Analysis PDF

**Structure**:
- Summary page (like quick analysis)
- Per-service detailed pages
- Network topology diagrams
- Firewall rule analysis
- Packet counter evidence
- Router-by-router breakdown

**Content**:

**Page 1:** Summary (same as quick mode)

**Page 2:** Service 22/tcp Analysis
- Test parameters
- Source/destination details
- Router: hq-gw
  - Status: BLOCKED
  - Blocking Rule: `-A FORWARD -p tcp --dport 22 -j DROP`
  - Packet count delta: +2
- Router: br-gw
  - Status: ALLOWED
  - Allowing Rule: `-A FORWARD -i eth0 -j ACCEPT`
  - Packet count delta: +2

**Page 3:** Service 80/tcp Analysis
- (similar detailed breakdown)

**Page N:** Network Topology Diagram
- GraphViz visualization
- Router connections
- Interface labels

## Execution Modes and Concurrency

### Quick Analysis Execution

**Lock Requirements**: None (parallel execution enabled)

**Concurrency Model**:

DSCP Registry (32-63):

| Job | DSCP Value | Status | User |
| --- | ---------- | ------ | ---- |
| Job A | DSCP 32 | Running | User1 |
| Job B | DSCP 33 | Running | User2 |
| Job C | DSCP 34 | Running | User1 |
| Job D | DSCP 35 | Running | User3 |
| ... | ... | ... | ... |
| (Available) | DSCP 36-63 | Available | - |

**Queue Behavior**:
- Check DSCP registry for available values
- If available: allocate DSCP and run immediately (parallel)
- If exhausted: queue job until DSCP released
- On completion: release DSCP for next job

### Detailed Analysis Execution

**Lock Requirements**: Global `network_test` lock (serial execution)

**Concurrency Model**:

Global Network Test Lock:

| Job | Lock Status | Status | User |
| --- | ----------- | ------ | ---- |
| Job X | LOCKED | Running | User4 |
| Job Y | QUEUED | Waiting | User5 |
| Job Z | QUEUED | Waiting | User6 |

**Queue Behavior**:
- Acquire global `network_test` lock
- Only one detailed job runs at a time
- Subsequent jobs queue until lock released
- Lock timeout: 3600 seconds (1 hour)

### Mixed-Mode Execution

**Quick + Detailed Can Run Together**:
```
Timeline:
----------------------------------------------------->
+-- Quick Job A (DSCP 32) -----------+
+-- Quick Job B (DSCP 33) ----------------+
+-- Detailed Job X (Network Lock) --------------------------+
+-- Quick Job C (DSCP 34) --------+
+-- Quick Job D (DSCP 35) -----------+
```

**Why This Works**:
- Quick jobs use DSCP tagging (no interference)
- Detailed jobs use different namespaces
- No shared resources between modes

## Progress Tracking

### Quick Analysis Progress

**Phase Names**:
1. `parse_args` - Parsing arguments
2. `PHASE2_ksms_start` - Starting KSMS quick analysis
3. `PHASE2_host_setup` - Creating source hosts
4. `PHASE2_host_{N}` - Creating source host N on router
5. `PHASE3_ksms_scan` - Executing KSMS bulk scan
6. `PHASE3_cleanup` - Removing created hosts
7. `PHASE4_format` - Converting results for PDF
8. `PHASE4_pdf` - Generating summary PDF
9. `PHASE4_complete` - Analysis complete

**Expected Steps**: ~4 fixed steps (independent of service count)

**Progress Calculation**:
```python
base_steps = 4  # host_setup, ksms_scan, cleanup, pdf
percentage = (completed_steps / base_steps) * 100
```

### Detailed Analysis Progress

**Phase Names**:
1. `parse_args` - Parsing arguments
2. `MULTI_REACHABILITY_PHASE1_START` - Setup phase start
3. `MULTI_REACHABILITY_setup_hosts` - Creating all hosts
4. `MULTI_REACHABILITY_PHASE2_START` - Service testing start
5. `MULTI_REACHABILITY_service_{port}_{proto}_start` - Starting service test
6. `iptables_before_{port}_{proto}` - Getting iptables snapshot
7. `MULTI_REACHABILITY_traceroute_{port}_{proto}` - Running traceroute
8. `MULTI_REACHABILITY_service_test_{port}_{proto}` - Running service test
9. `iptables_after_{port}_{proto}` - Getting iptables snapshot
10. `MULTI_REACHABILITY_service_{port}_{proto}_complete` - Service complete
11. `MULTI_REACHABILITY_cleanup` - Cleanup all hosts
12. `MULTI_REACHABILITY_pdf` - Generating comprehensive PDF
13. `MULTI_REACHABILITY_COMPLETE` - Analysis complete

**Expected Steps**:
```python
base_steps = 21  # static phases
per_service_steps = 9  # per-service phases
total_steps = base_steps + (per_service_steps * num_services)
```

**Progress Calculation**:
```python
percentage = (completed_steps / total_steps) * 100
```

## Use Case Decision Matrix

| Requirement | Quick Analysis | Detailed Analysis |
| ----------- | -------------- | ----------------- |
| Need results in <1 minute | [YES] | [NO] |
| Testing 10+ services | [YES] Ideal | [WARN] Slow |
| Need firewall rule identification | [NO] | [YES] |
| Need packet counter evidence | [NO] | [YES] |
| Troubleshooting blocked connection | [WARN] Identifies block | [YES] Finds exact rule |
| Compliance documentation | [WARN] Basic | [YES] Comprehensive |
| Pre-change baseline | [YES] Fast baseline | [WARN] Too slow |
| Security audit | [NO] Insufficient | [YES] Full evidence |
| Initial reconnaissance | [YES] Perfect | [NO] Overkill |
| Root cause analysis | [NO] Limited | [YES] Complete |

**Legend**:
- [YES] = Recommended / Ideal
- [WARN] = Possible but not optimal
- [NO] = Not suitable / Not supported

## Configuration Requirements

### Quick Analysis Configuration

```json
{
  "ksms_enabled": true,
  "ksms_timeout": 300,
  "ksms_mode_default": "quick",
  "max_services": 10,
  "dscp_range_start": 32,
  "dscp_range_end": 63
}
```

### Detailed Analysis Configuration

```json
{
  "max_services": 10,
  "network_test_timeout": 3600,
  "iptables_snapshot_timeout": 60,
  "service_test_timeout": 30
}
```

## Limitations and Constraints

### Quick Analysis Limitations

| Limitation | Impact | Workaround |
| ---------- | ------ | ---------- |
| No rule identification | Cannot determine which specific rule blocked traffic | Use detailed analysis for blocked services |
| No packet counter evidence | Cannot prove which rules processed packets | Use detailed analysis for audits |
| No actual service testing | May miss application-level issues | Follow up with detailed analysis if needed |
| DSCP exhaustion | Max 32 concurrent jobs | Jobs queue automatically |
| Limited debugging info | Hard to troubleshoot false negatives | Check KSMS logs, retry with detailed |

### Detailed Analysis Limitations

| Limitation | Impact | Workaround |
| ---------- | ------ | ---------- |
| Sequential testing only | Slow for many services | Use quick analysis first to filter interesting services |
| Global network lock | Only one job at a time | Queue system handles this automatically |
| Memory intensive | Large iptables snapshots consume RAM | Monitor /dev/shm usage |
| Time-consuming | ~20 sec/service | Split into multiple jobs if possible |
| Service conflicts | Can't test same port twice simultaneously | Built-in: services tested sequentially |

## Best Practices

### When to Use Quick Analysis

1. **Initial Assessment**
   - Run quick analysis first to get overview
   - Identify which services are blocked vs allowed
   - Test many services quickly

2. **Bulk Testing**
   - Testing large service lists (email, web, database, etc.)
   - Compliance checks across many protocols
   - Pre/post-change validation

3. **Parallel Operations**
   - Multiple users need results simultaneously
   - Can run 32 jobs in parallel
   - No waiting for network lock

4. **Quick Decisions**
   - Emergency troubleshooting requiring fast answers
   - Time-sensitive testing windows
   - Customer waiting on call

### When to Use Detailed Analysis

1. **Root Cause Analysis**
   - Service is blocked but need to know WHY
   - Which specific firewall rule is responsible
   - Need packet counter evidence

2. **Security Audits**
   - Compliance requirements for documented evidence
   - Need to prove rules are working as configured
   - Chain of custody for security findings

3. **Change Validation**
   - Verify new firewall rules are correct
   - Prove old rules were removed
   - Document before/after rule changes

4. **Complex Troubleshooting**
   - Intermittent connectivity issues
   - Asymmetric routing problems
   - Need complete diagnostic data

### Hybrid Workflow (Recommended)

| Step | Phase | Action | Results |
| ---- | ----- | ------ | ------- |
| 1 | Run Quick Analysis | Test all services | 50 YES, 30 NO, 20 UNKNOWN |
| 2 | Analyze Quick Results | Review results | Focus on blocked services (30 NO); Investigate unknowns (20 UNKNOWN) |
| 3 | Run Detailed Analysis | Test filtered services only | Only test the 50 interesting services; Get firewall rule details for failures |

**Performance Comparison:**

| Metric | Hybrid Workflow | All Detailed |
| ------ | --------------- | ------------ |
| Approach | Quick first, then detailed on filtered set | Detailed on all services |
| Services Tested | Selective (filtered subset) | All services |
| Efficiency Gain | Significantly faster | Baseline |

## Troubleshooting

### Quick Analysis Issues

**Problem**: All services show UNKNOWN
- **Cause**: Network connectivity issue, DSCP routing problem
- **Solution**: Check routing tables, verify DSCP not filtered
- **Diagnosis**: Run detailed analysis for one service to confirm

**Problem**: Results differ from detailed analysis
- **Cause**: KSMS uses different code path than service test
- **Solution**: Service test result is authoritative, use for final decision
- **Note**: Discrepancies logged to audit.log for investigation

**Problem**: Quick analysis takes too long or times out
- **Cause**: Too many services, KSMS script error, network issues
- **Solution**: Reduce service count, check KSMS logs in /var/log/tsim
- **Workaround**: Split into multiple smaller jobs

### Detailed Analysis Issues

**Problem**: Detailed analysis takes a long time
- **Cause**: Many services being tested sequentially
- **Solution**: Use quick analysis first to filter services
- **Optimization**: Test only failed services from quick analysis

**Problem**: iptables counter deltas are zero
- **Cause**: Wrong rule being checked, packets took different path
- **Solution**: Check all chains (INPUT, FORWARD, OUTPUT)
- **Debug**: Review iptables snapshots in run directory

**Problem**: Service test fails but should work
- **Cause**: Service startup issue, port already in use
- **Solution**: Check for conflicting services, review error logs
- **Retry**: Detailed analysis retries failed services automatically

## Technical Specifications Summary

### Quick Analysis Specifications

| Specification | Value |
| ------------- | ----- |
| Technology | KSMS (Kernel-Space Multi-Service) |
| Execution Model | Parallel (DSCP-based isolation) |
| Max Concurrent Jobs | 32 (DSCP range 32-63) |
| Time per Job | Constant (fixed) |
| Services per Job | Limited by config (typically 10 web, unlimited CLI) |
| Memory Usage | Low (~100MB per job) |
| CPU Usage | Low (kernel-space processing) |
| Network Impact | Minimal (no actual services) |
| Lock Required | None |
| Result Granularity | YES/NO/UNKNOWN per router |
| Evidence Level | Reachability only |
| PDF Pages | 1 (summary only) |

### Detailed Analysis Specifications

| Specification | Value |
| ------------- | ----- |
| Technology | MultiServiceTester (Python) |
| Execution Model | Serial (sequential services) |
| Max Concurrent Jobs | 1 (global network lock) |
| Time per Service | Per-service sequential |
| Services per Job | Limited by config (typically 10) |
| Memory Usage | Moderate (~500MB per job) |
| CPU Usage | Moderate (Python processing) |
| Network Impact | Moderate (actual service listeners) |
| Lock Required | Global network_test lock |
| Result Granularity | Per-rule packet counters |
| Evidence Level | Complete (rules + counters) |
| PDF Pages | 1 + N (N = number of services) |

---

## Comparison Summary Table

| Feature | Quick Analysis | Detailed Analysis |
| ------- | -------------- | ----------------- |
| **Speed** | Constant time (all services) | Linear time per service |
| **Concurrency** | Up to 32 parallel jobs | 1 job at a time (serial) |
| **Technology** | KSMS (kernel-space) | MultiServiceTester (user-space) |
| **Testing Method** | Parallel bulk scan | Sequential per-service |
| **Service Listeners** | Not required | Required for each test |
| **iptables Analysis** | [NO] | [YES] (BEFORE/AFTER counters) |
| **Rule Identification** | [NO] | [YES] (exact rules with counters) |
| **Packet Tracing** | [NO] | [YES] (traceroute included) |
| **Result Detail** | YES/NO/UNKNOWN | OK/FAIL with rule details |
| **Evidence Quality** | Basic reachability | Complete packet counter evidence |
| **PDF Report** | Single summary page | Multi-page detailed report |
| **Memory Usage** | Low (~100MB) | Moderate (~500MB) |
| **Best For** | Bulk testing, reconnaissance | Troubleshooting, audits |
| **Typical Use Case** | "Are these 100 services reachable?" | "Why is SSH blocked on router X?" |
| **Output Structure** | Router-based (routers[].services[]) | Service-based (tests[] with router info) |
| **DSCP Tagging** | [YES] (32-63 range) | [NO] |
| **Network Lock** | [NO] Not required | [YES] Required (global) |
| **Firewall Counter Snapshots** | [NO] | [YES] (before + after) |
| **Network Topology** | Minimal (source hosts only) | Complete (source + destination) |
| **Cleanup** | Quick | Thorough |
| **Real Service Testing** | [NO] (probe-based) | [YES] (actual connections) |
| **Max Services (Web)** | Limited by config (typically 10) | Limited by config (typically 10) |
| **Max Services (CLI)** | Unlimited (CLI bypasses limits) | Limited by time constraints |
| **Time Scaling** | O(1) - constant time | O(N) - linear with service count |
| **Recommended For** | First-pass analysis | Deep-dive investigation |

## Conclusion

Both analysis modes serve complementary purposes in network security testing:

- **Quick Analysis** excels at rapid bulk testing and initial reconnaissance, providing YES/NO answers across many services in under a minute.
- **Detailed Analysis** provides comprehensive firewall rule analysis with packet counter evidence, essential for troubleshooting and compliance.

**Recommended Workflow**: Use quick analysis to identify interesting services (blocked, unknown, or critical), then run detailed analysis on the filtered subset for complete diagnostic information.

This hybrid approach provides optimal speed while maintaining forensic-level detail where needed.

---

## Appendix A: Quick Analysis Technical Details

### Overview

Quick Analysis mode uses the KSMS (Kernel-Space Multi-Service) tester to provide rapid YES/NO/UNKNOWN reachability results for multiple services simultaneously. This appendix provides detailed technical analysis of the iptables rule construction mechanism and DSCP-based packet tagging implementation.

### DSCP-Based Packet Tagging

**DSCP Allocation**:
Each KSMS job receives a unique DSCP (Differentiated Services Code Point) value:
- DSCP range: 32-63 (32 available values, 0x20-0x3F in hexadecimal)
- DSCP value obtained from environment variable `KSMS_JOB_DSCP` or defaults to 32
- All services within a single job share the same DSCP value
- DSCP validation ensures value is within reserved range (32-63)

**TOS Field Calculation**:
The DSCP value is converted to the TOS (Type of Service) field value for socket options:
```python
tos = dscp << 2  # Left shift by 2 bits
```

Example conversions:
- DSCP 32 (0x20) => TOS 128 (0x80)
- DSCP 33 (0x21) => TOS 132 (0x84)
- DSCP 63 (0x3F) => TOS 252 (0xFC)

The left shift by 2 bits positions the DSCP value in the correct bits of the TOS field (bits 2-7), leaving bits 0-1 for ECN (Explicit Congestion Notification).

### iptables Rule Construction in PREROUTING and POSTROUTING

**Rule Format**:
The ksms_tester.py script constructs iptables rules in the mangle table using three matching criteria:
1. DSCP value (unique per job)
2. Protocol (tcp or udp)
3. Destination port number

**PREROUTING Chain Rules**:
```
-A PREROUTING -p {proto} -m dscp --dscp 0x{dscp:02x} -m {proto} --dport {port} -m comment --comment "TSIM_KSMS={run_id}:PREROUTING:{port}/{proto}" -j TSIM_TAP_FW
```

Example for port 80/tcp with DSCP 32:
```
-A PREROUTING -p tcp -m dscp --dscp 0x20 -m tcp --dport 80 -m comment --comment "TSIM_KSMS=KSMS12345_67890:PREROUTING:80/tcp" -j TSIM_TAP_FW
```

**POSTROUTING Chain Rules**:
```
-A POSTROUTING -p {proto} -m dscp --dscp 0x{dscp:02x} -m {proto} --dport {port} -m comment --comment "TSIM_KSMS={run_id}:POSTROUTING:{port}/{proto}" -j TSIM_TAP_FW
```

Example for port 80/tcp with DSCP 32:
```
-A POSTROUTING -p tcp -m dscp --dscp 0x20 -m tcp --dport 80 -m comment --comment "TSIM_KSMS=KSMS12345_67890:POSTROUTING:80/tcp" -j TSIM_TAP_FW
```

### Rule Components Explained

**DSCP Matching (`-m dscp --dscp 0x{dscp:02x}`)**:
- Uses hexadecimal notation for DSCP value
- DSCP 32 = 0x20, DSCP 33 = 0x21, etc.
- Matches packets where DSCP field equals specified value
- Critical for job isolation: only packets from this job match

**Protocol Matching (`-p {proto} -m {proto}`)**:
- `-p {proto}`: Matches protocol (tcp or udp)
- `-m {proto}`: Loads protocol-specific module (tcp or udp module)
- Required for `--dport` matching

**Port Matching (`--dport {port}`)**:
- Matches destination port number
- Only works with tcp or udp protocols
- Combined with DSCP creates unique signature per service

**Comment Field**:
- Format: `TSIM_KSMS={run_id}:PREROUTING:{port}/{proto}`
- Run ID: Unique identifier (e.g., KSMS12345_67890)
- Chain identifier: PREROUTING or POSTROUTING
- Service identifier: port/protocol pair
- Used for counter extraction and cleanup

**Target (`-j TSIM_TAP_FW`)**:
- Jumps to custom chain TSIM_TAP_FW
- Chain contains single rule: `-A TSIM_TAP_FW -j RETURN`
- Acts as a packet counter tap (counts but doesn't modify)
- Returns to calling chain immediately

### Rule Installation Process

**Chain Creation**:
```
:TSIM_TAP_FW - [0:0]
-A TSIM_TAP_FW -j RETURN
```

Creates the TSIM_TAP_FW chain with:
- Default policy: none (indicated by `-`)
- Initial counters: 0 packets, 0 bytes
- Single rule: unconditional RETURN

**Payload Construction** (from `build_insert_payload_from_existing`):
1. Read existing mangle table with `iptables-save -c -t mangle`
2. Remove all old TSIM_KSMS rules (prevent accumulation)
3. Remove TSIM_TAP_FW chain if no other jobs using it
4. Insert new TSIM_TAP_FW chain declaration
5. Append new rules for each service
6. Maintain all non-KSMS existing rules

**Atomic Installation**:
```bash
ip netns exec {router} iptables-restore -c -n
```

- `-c`: Restore with counters
- `-n`: Don't flush existing tables
- Atomic operation: all rules applied or none
- Preserves existing firewall configuration

### Probe Packet Generation

**Socket Configuration**:
```python
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # TCP
s.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, tos)
```

or

```python
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP
s.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, tos)
```

**TOS Field Setting**:
- Uses `socket.IP_TOS` socket option
- Sets entire TOS byte in IP header
- Value: `tos = dscp << 2`
- Kernel automatically places value in TOS field

**TCP Probe**:
```python
s.settimeout(tcp_timeout)
s.connect_ex((dst_ip, port))
```

- Sends TCP SYN packet with TOS field set
- Non-blocking connect attempt
- Times out after tcp_timeout seconds

**UDP Probe**:
```python
s.sendto(b"x", (dst_ip, port))
```

- Sends single UDP datagram with TOS field set
- Single byte payload
- No response expected

### Packet Flow Through Router

**Inbound Path (PREROUTING)**:
1. Packet arrives at router interface
2. PREROUTING chain evaluated before routing decision
3. Rule matches: `-m dscp --dscp 0x20 -p tcp --dport 80`
4. Counter incremented: PREROUTING counter += 1
5. Jump to TSIM_TAP_FW, immediate RETURN
6. Continue to routing decision

**Routing Decision**:
- Kernel consults routing table
- Determines egress interface
- If route exists: forward packet
- If no route: drop packet (won't reach POSTROUTING)

**Outbound Path (POSTROUTING)**:
1. Packet forwarded (passed routing decision)
2. POSTROUTING chain evaluated after routing decision
3. Rule matches: `-m dscp --dscp 0x20 -p tcp --dport 80`
4. Counter incremented: POSTROUTING counter += 1
5. Jump to TSIM_TAP_FW, immediate RETURN
6. Packet transmitted on egress interface

### Counter Extraction and Analysis

**Counter Format in iptables-save**:
```
[pkts:bytes] -A PREROUTING -p tcp -m dscp --dscp 0x20 -m tcp --dport 80 -m comment --comment "TSIM_KSMS=..." -j TSIM_TAP_FW
```

Example:
```
[5:300] -A PREROUTING -p tcp -m dscp --dscp 0x20 -m tcp --dport 80 -m comment --comment "TSIM_KSMS=KSMS12345:PREROUTING:80/tcp" -j TSIM_TAP_FW
```

Indicates: 5 packets, 300 bytes matched this rule

**Extraction Algorithm** (from `extract_counter` function):
```python
def extract_counter(snapshot: str, comment: str) -> Tuple[int, int]:
    for line in snapshot.splitlines():
        if comment in line and '--comment' in line:
            # Extract counter from [X:Y] format
            m = re.search(r'^\[(\d+):(\d+)\]', line)
            if m:
                pkts = int(m.group(1))
                bytes_ = int(m.group(2))
                return pkts, bytes_
    return 0, 0
```

**Delta Calculation**:
```python
# Get counters before test
before_pkts, _ = extract_counter(before_snapshot, prerouting_comment)
before2_pkts, _ = extract_counter(before_snapshot, postrouting_comment)

# Emit probe packets...

# Get counters after test
after_pkts, _ = extract_counter(after_snapshot, prerouting_comment)
after2_pkts, _ = extract_counter(after_snapshot, postrouting_comment)

# Calculate deltas
pre_delta = after_pkts - before_pkts
post_delta = after2_pkts - before2_pkts
```

### Verdict Logic

**Decision Algorithm** (from main function, lines 905-910):
```python
if post_delta > 0:
    verdict = 'YES'       # Packet forwarded successfully
elif pre_delta > 0 and post_delta == 0:
    verdict = 'NO'        # Packet entered but not forwarded (blocked)
else:
    verdict = 'UNKNOWN'   # No packets seen (routing/network issue)
```

**Interpretation**:

| PREROUTING Counter | POSTROUTING Counter | Verdict | Meaning |
| ------------------ | ------------------- | ------- | ------- |
| Increased | Increased | YES | Packet received and forwarded |
| Increased | Unchanged | NO | Packet received but blocked (dropped in FORWARD chain) |
| Unchanged | Unchanged | UNKNOWN | Packet never reached router (routing or ARP issue) |
| Unchanged | Increased | IMPOSSIBLE | Should never occur (packet can't leave without entering) |

**Why This Works**:
- PREROUTING occurs before FORWARD chain evaluation
- POSTROUTING occurs after FORWARD chain evaluation
- If FORWARD chain DROPs packet, POSTROUTING never executes
- Counter deltas reveal exactly where packet was blocked

### Key Implementation Details from Code

**Service Token Structure** (lines 597-603):
```python
svc_tokens: Dict[Tuple[int,str], Dict] = {}
for port, proto in services:
    svc_tokens[(port, proto)] = {
        'dscp': job_dscp,        # Same DSCP for all services in job
        'tos': job_dscp << 2     # TOS value for socket option
    }
```

**Run ID Generation** (line 587):
```python
run_id = f"KSMS{os.getpid()}_{int(time.time() * 1000) % 100000}"
```

Format: KSMS{pid}_{timestamp_ms}
Example: KSMS12345_67890

**Cleanup Process** (lines 945-977):
1. Capture current mangle table
2. Filter out rules matching this run_id
3. If no other TSIM_KSMS rules remain, remove TSIM_TAP_FW chain
4. Apply cleaned configuration with iptables-restore
5. Remove static ARP entries configured during setup

### Why DSCP + Port Combination?

**Job Isolation**:
- Multiple concurrent jobs test different services
- Same port may be tested by different jobs simultaneously
- DSCP value uniquely identifies each job
- Rules match only packets from specific job: `dscp=32 AND port=80`

**Example Scenario**:
```
Job 1 (DSCP 32) testing: 80/tcp, 443/tcp
Job 2 (DSCP 33) testing: 80/tcp, 22/tcp

Router iptables rules:
-A PREROUTING -m dscp --dscp 0x20 -p tcp --dport 80 ...  # Job 1, port 80
-A PREROUTING -m dscp --dscp 0x21 -p tcp --dport 80 ...  # Job 2, port 80
-A PREROUTING -m dscp --dscp 0x20 -p tcp --dport 443 ... # Job 1, port 443
-A PREROUTING -m dscp --dscp 0x21 -p tcp --dport 22 ...  # Job 2, port 22
```

Each rule counts packets for specific job + service combination with zero interference.

### Static ARP Configuration

**Purpose** (lines 748-758):
```python
ip neigh replace {nexthop} lladdr 02:00:00:00:02:00 dev {iface} nud permanent
```

- Prevents ARP resolution delays
- Uses dummy MAC address (02:00:00:00:02:00)
- Ensures packets leave router interface
- Required for testing when destination is unreachable
- Allows counter increments even if destination doesn't exist

**Cleanup**:
```python
ip neigh del {nexthop} dev {iface}
```

Removes static ARP entry after test completes.
