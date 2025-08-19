# CSV Output Format Documentation

## Overview

The wrapper script converts both `traceroute` and `mtr` output to a canonical CSV format that can be easily processed by the reverse path tracer, regardless of which tool was used on the remote host.

## CSV Format Specification

### Structure
```
# <header comment with trace info>
<hop_number>,<ip_address>,<response_time>,<loss>
```

### Fields

1. **hop_number**: Integer (1-based) indicating the hop position
2. **ip_address**: IPv4 address of the responding hop (empty if no response)
3. **response_time**: Average response time in milliseconds (empty if no response)
4. **loss**: Binary indicator (0 = responded, 1 = no response)

### Header Comment

The first line is a comment (prefixed with `#`) containing trace information:
- For traceroute: `# traceroute to <target> (<target>), <max_hops> hops max, <packet_size> byte packets`
- For mtr: `# mtr to <target>, <max_hops> hops max, <packet_size> byte packets`

## Examples

### Successful Trace (traceroute)

**Original traceroute output:**
```
traceroute to 10.10.0.2 (10.10.0.2), 30 hops max, 60 byte packets
 1  192.168.122.1  0.727 ms  0.680 ms  0.660 ms
 2  192.168.50.1  3.631 ms  3.584 ms  3.561 ms
 3  10.10.0.2  4.028 ms  4.342 ms  4.441 ms
```

**CSV output:**
```
# traceroute to 10.10.0.2 (10.10.0.2), 30 hops max, 60 byte packets
1,192.168.122.1,0.680,0
2,192.168.50.1,3.584,0
3,10.10.0.2,4.342,0
```

### Trace with Non-Responding Hop

**Original traceroute output:**
```
traceroute to 10.10.0.5 (10.10.0.5), 30 hops max, 60 byte packets
 1  192.168.122.1  0.727 ms  0.680 ms  0.660 ms
 2  * * *
 3  10.10.0.5  5.123 ms  5.234 ms  5.345 ms
```

**CSV output:**
```
# traceroute to 10.10.0.5 (10.10.0.5), 30 hops max, 60 byte packets
1,192.168.122.1,0.680,0
2,,,1
3,10.10.0.5,5.234,0
```

### MTR Output Conversion

**Original mtr output:**
```
HOST: router1                     Loss%   Snt   Last   Avg  Best  Wrst StDev
  1.|-- 192.168.122.1             0.0%     1    0.7   0.7   0.7   0.7   0.0
  2.|-- ???                      100.0     1    0.0   0.0   0.0   0.0   0.0
  3.|-- 10.10.0.2                 0.0%     1    4.3   4.3   4.3   4.3   0.0
```

**CSV output:**
```
# mtr to 10.10.0.2, 20 hops max, 60 byte packets
1,192.168.122.1,0.7,0
2,,,1
3,10.10.0.2,4.3,0
```

## Response Time Selection

### Traceroute
- When 3 response times are available (default), the **middle value** (2nd) is used
- This provides a median-like value, avoiding outliers
- Example: `0.727 ms  0.680 ms  0.660 ms` → Uses `0.680`

### MTR
- Uses the **average** value directly from MTR's output
- With `-c 1` (single ping), this is the single response time
- Example: `Avg: 0.7` → Uses `0.7`

## Loss Indication

### Value Meanings
- **0**: Hop responded successfully
- **1**: No response received (timeout)

### Detection Methods

#### Traceroute
- Loss detected when output shows `* * *`
- All three probes must fail for loss = 1

#### MTR
- Loss detected when:
  - Output shows `???` for hostname
  - Loss percentage is 100%

## Empty Fields

When a hop doesn't respond:
- **ip_address**: Empty (no value between commas)
- **response_time**: Empty (no value between commas)
- **loss**: Set to 1

Example: `2,,,1` indicates hop 2 didn't respond

## Parser Implementation Details

### Traceroute Parser
1. Preserves header line as comment
2. Extracts hop number from leading digits
3. Checks for `* * *` pattern for non-responding hops
4. Extracts IP address using regex
5. Selects middle response time from three values
6. Outputs CSV line

### MTR Parser
1. Converts HOST line to header comment
2. Identifies data lines by `hop.|--` pattern
3. Checks for `???` or 100% loss
4. Extracts IP, loss percentage, and average time
5. Converts loss percentage to binary (100% → 1, else → 0)
6. Outputs CSV line

## Error Handling

### Invalid Target
If target validation fails (not a 10.x.x.x IPv4 address), a comment line is returned:
```
# input invalid: <input provided> - must be valid 10.x.x.x IPv4 address
```

Examples:
```
# input invalid: 8.8.8.8 - must be valid 10.x.x.x IPv4 address
# input invalid: google.com - must be valid 10.x.x.x IPv4 address
# input invalid: 192.168.1.1 - must be valid 10.x.x.x IPv4 address
```

### Tool Not Available
If neither traceroute nor mtr is available:
```
Error: Neither traceroute nor mtr is available on this system
```

### No Target Specified
If no target is provided:
```
Error: No target specified. Usage: ssh traceroute-user@host <10.x.x.x>
```

## Integration with Reverse Path Tracer

The reverse path tracer can parse the CSV output by:
1. Skipping comment lines (starting with `#`)
2. Splitting each line by commas
3. Processing the four fields
4. Handling empty fields for non-responding hops

### Sample Parser (Python)
```python
def parse_trace_output(output):
    hops = []
    for line in output.strip().split('\n'):
        if line.startswith('#'):
            continue  # Skip header
        parts = line.split(',')
        if len(parts) == 4:
            hop = {
                'hop_num': int(parts[0]),
                'ip': parts[1] if parts[1] else None,
                'rtt': float(parts[2]) if parts[2] else None,
                'loss': int(parts[3])
            }
            hops.append(hop)
    return hops
```

## Benefits of CSV Format

1. **Tool Agnostic**: Same format regardless of traceroute or mtr
2. **Simple Parsing**: No complex regex needed for consumption
3. **Consistent**: Predictable field positions
4. **Compact**: Minimal data transfer
5. **Human Readable**: Easy to debug and verify
6. **Machine Friendly**: Direct import to data analysis tools