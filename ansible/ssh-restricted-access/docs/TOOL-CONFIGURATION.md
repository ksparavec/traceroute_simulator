# Traceroute and MTR Tool Configuration Guide

## Overview

The SSH restricted access wrapper supports both `traceroute` and `mtr` tools with automatic detection and fallback. All tool options are configured via Ansible YAML and cannot be changed at runtime via SSH for security.

## Key Configuration Changes

### Security-Focused Defaults
- **DNS Resolution**: Always disabled (`no_dns: true`) for security and performance
- **Max Hops**: Reduced to 20 (from 30) to limit scope
- **ICMP Mode**: Always uses ICMP ECHO probes instead of UDP
- **Target Validation**: Only accepts `10.x.x.x` IPv4 addresses
- **No Runtime Options**: SSH users cannot modify tool behavior

### Tool Selection

#### Global Configuration (config/default.yml or production.yml)
```yaml
tracersh:
  preferred_tool: "traceroute"  # or "mtr"
```

#### Per-Host Override (inventory/hosts.yml)
```yaml
hosts:
  router1:
    wrapper_preferred_tool: traceroute
  router2:
    wrapper_preferred_tool: mtr
```

#### Automatic Fallback
- If preferred tool is not available, wrapper automatically uses the alternative
- If neither tool is available, deployment fails with clear error

## Traceroute Configuration

### Options (tracersh.traceroute_options)
```yaml
traceroute_options:
  max_hops: 20        # -m: Maximum TTL (hops)
  wait_time: 3        # -w: Wait time per probe (seconds)
  queries: 3          # -q: Number of queries per hop
  packet_size: 60     # Packet size in bytes
  no_dns: true        # -n: No DNS resolution (always true)
  use_icmp: true      # -I: Use ICMP ECHO (always true)
```

### Generated Command Example
```bash
traceroute -I -n -m 20 -w 3 -q 3 10.0.0.1 60
```

### Key Points
- **ICMP Mode (`-I`)**: Requires root privileges or setuid bit on traceroute binary
- **No DNS (`-n`)**: Faster execution, no external DNS queries
- **Removed Options**: `interface` and `source_address` are auto-detected by the system

## MTR Configuration

### Options (tracersh.mtr_options)
```yaml
mtr_options:
  max_hops: 20        # -m: Maximum TTL
  report_cycles: 1    # -c: Number of pings per hop (1 for fast results)
  interval: 1         # -i: Interval between pings (seconds)
  packet_size: 60     # -s: Packet size in bytes
  no_dns: true        # -n: No DNS resolution (always true)
  report_mode: true   # -r: Report mode (non-interactive)
  show_ips: false     # -b: Show IPs (disabled when no_dns is true)
  mpls: false         # --mpls: MPLS information
```

### Generated Command Example
```bash
mtr -r -n -m 20 -c 1 -i 1 -s 60 10.0.0.1
```

### Key Points
- **Report Mode (`-r`)**: Non-interactive output, suitable for SSH
- **Single Ping (`-c 1`)**: Fast results with minimal network impact
- **ICMP by Default**: MTR uses ICMP by default (no flag needed)
- **Consistent Output**: Report mode provides consistent, parseable output

## Wrapper Script Behavior

### Tool Detection Logic
1. Check if preferred tool exists and is executable
2. If not available, check alternative tool
3. If neither available, exit with error
4. Log tool selection (if logging enabled)

### Execution Flow
```
SSH Command → Wrapper Script → Tool Detection → Validation → Execute Tool
     ↓              ↓                ↓              ↓            ↓
"10.0.0.1"    Extract IP      Check tools    Verify 10.x.x.x   Run with
              (ignore rest)    traceroute/mtr    pattern       fixed options
```

### Security Features
- **Single Parameter**: Only first positional parameter (IP) is used
- **No Options**: All SSH command options/flags are ignored
- **Strict Validation**: Regex pattern ensures only 10.x.x.x addresses
- **Fixed Configuration**: Options cannot be modified at runtime

## Permissions Required

### For Traceroute ICMP Mode
```bash
# Option 1: setuid bit (common)
sudo chmod u+s /usr/bin/traceroute

# Option 2: Capabilities (modern)
sudo setcap cap_net_raw+ep /usr/bin/traceroute

# Option 3: Run as root (not recommended)
```

### For MTR
```bash
# Usually has setuid by default
ls -l /usr/bin/mtr
-rwsr-xr-x 1 root root ... /usr/bin/mtr
```

## Testing Tool Availability

### Manual Check
```bash
# Check traceroute
which traceroute && traceroute -I -n 10.0.0.1

# Check mtr
which mtr && mtr -r -n -c 1 10.0.0.1
```

### Ansible Playbook Check
The deployment playbook automatically:
1. Checks both tool paths
2. Verifies at least one is executable
3. Reports available tools in summary
4. Configures wrapper accordingly

## Troubleshooting

### Common Issues

1. **"Neither traceroute nor mtr is available"**
   - Install required package: `apt-get install traceroute mtr` or `yum install traceroute mtr`

2. **"Operation not permitted" (traceroute)**
   - ICMP mode requires elevated privileges
   - Apply setuid bit or capabilities (see above)

3. **No output from traceroute**
   - Check if ICMP is blocked by firewall
   - Verify target is reachable
   - Check wrapper script logs (if enabled)

4. **MTR shows "???" for all hops**
   - ICMP may be filtered
   - Try increasing report_cycles
   - Check network connectivity

### Debug Mode
Enable wrapper logging for troubleshooting:
```yaml
tracersh:
  logging:
    enabled: yes
    path: "log/tracersh.log"
```

Then check logs:
```bash
tail -f /home/traceroute-user/log/tracersh.log
```

## Example Configurations

### Fast Response Setup (MTR with single ping)
```yaml
tracersh:
  preferred_tool: "mtr"
  mtr_options:
    report_cycles: 1    # Single ping for fastest results
    interval: 1         # Standard interval
```

### More Accurate Setup (MTR with multiple pings)
```yaml
tracersh:
  preferred_tool: "mtr"
  mtr_options:
    report_cycles: 5    # Multiple pings for better statistics
    interval: 1         # Standard interval
```

### Conservative Setup (Traceroute)
```yaml
tracersh:
  preferred_tool: "traceroute"
  traceroute_options:
    wait_time: 5        # Longer timeout for slow networks
    queries: 5          # More queries for accuracy
```

### Minimal Logging Setup
```yaml
tracersh:
  logging:
    enabled: no         # Default - no performance impact
```

## Security Considerations

1. **No User Control**: Users cannot modify tool behavior
2. **Fixed Target Range**: Only 10.0.0.0/8 addresses accepted
3. **No DNS Queries**: Prevents DNS-based attacks/leaks
4. **ICMP Only**: More reliable and secure than UDP
5. **Logged Attempts**: All executions can be logged for audit