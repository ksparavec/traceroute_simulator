# Web Interface User Guide

## Table of Contents
1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Login and Authentication](#login-and-authentication)
4. [Running Network Tests](#running-network-tests)
5. [Understanding Test Results](#understanding-test-results)
6. [PDF Reports](#pdf-reports)
7. [Common Use Cases](#common-use-cases)
8. [Troubleshooting](#troubleshooting)

## Introduction

The Traceroute Simulator Web Interface provides a user-friendly way to analyze firewall configurations and test network connectivity through your browser. This tool helps you understand how data packets travel through your network infrastructure and identify potential connectivity issues.

### Key Benefits
- **No command-line knowledge required** - Simple web forms for all operations
- **Visual network diagrams** - Understand network paths at a glance
- **Professional PDF reports** - Download and share comprehensive analysis
- **Secure access** - Authentication protects sensitive network information
- **Real-time testing** - See live results as tests execute

## Getting Started

### System Requirements
- Modern web browser (Chrome, Firefox, Edge, Safari)
- JavaScript enabled
- PDF viewer for reports
- Network connectivity to the simulator server

### First-Time Access
1. Open your web browser
2. Navigate to: `http://your-server/login.html`
3. Contact your system administrator for credentials
4. Bookmark the page for easy access

## Login and Authentication

### Accessing the Interface

1. **Navigate to Login Page**
   - URL: `http://your-server/login.html`
   - You may be redirected here automatically

2. **Enter Credentials**
   - Username: Your assigned username
   - Password: Your secure password
   - Click "Login" button

3. **Session Management**
   - Sessions remain active for 30 minutes of inactivity
   - Logout when finished to secure your session
   - Browser cookies must be enabled

### Password Changes
If you need to change your password, contact your system administrator. They will provide instructions for the password change process.

## Running Network Tests

### Test Form Overview

The main test form allows you to specify:

#### Source Information
- **Source IP Address**: The starting point of your network trace
  - Example: `10.1.1.1`
  - Must be a valid IP address in your network

#### Destination Information
- **Destination IP Address**: The target endpoint
  - Example: `10.2.1.1` or `8.8.8.8`
  - Can be internal or external IP

#### Service Testing (Optional)
- **Port Number**: TCP/UDP port to test
  - Example: `80` for HTTP, `443` for HTTPS
  - Range: 1-65535
- **Protocol**: Select TCP or UDP
  - TCP: Connection-oriented services
  - UDP: Connectionless services

### Running a Test

1. **Fill in the Form**
   ```
   Source IP: 10.1.1.1
   Destination IP: 10.2.1.1
   Port: 443
   Protocol: TCP
   ```

2. **Submit the Test**
   - Click "Run Test" button
   - Progress indicator will appear
   - Wait for results (typically 5-30 seconds)

3. **View Results**
   - Results appear below the form
   - Download PDF report if needed
   - Run additional tests as required

### Test Types

#### Basic Connectivity Test
- Tests if packets can reach from source to destination
- Shows the complete network path
- Identifies blocking points

#### Service Test
- Verifies if specific services are accessible
- Tests both connectivity and port availability
- Useful for troubleshooting application issues

## Understanding Test Results

### Result Components

#### 1. Path Summary
Shows the route packets take through your network:
```
Source: 10.1.1.1 (hq-gw)
  ↓
Router: hq-gw (10.1.1.1)
  Interface: eth1 → wg0
  ↓
Router: br-gw (10.100.1.2)
  Interface: wg0 → eth1
  ↓
Destination: 10.2.1.1 (br-gw)
```

#### 2. Connectivity Status

**✅ REACHABLE**
- Packets can successfully reach the destination
- All firewalls allow the traffic
- Routing is properly configured

**❌ BLOCKED**
- Traffic is blocked by firewall rules
- Shows which router blocks the traffic
- Indicates the specific rule causing the block

**⚠️ NO ROUTE**
- No network path exists to destination
- Routing configuration issue
- May need VPN or gateway configuration

#### 3. Firewall Analysis

For each router in the path:
- **Allowed Rules**: Rules that permit the traffic
- **Blocked Rules**: Rules that deny the traffic
- **Default Action**: What happens if no rules match

Example output:
```
Router: hq-gw
Status: FORWARDING ALLOWED
Matching Rule: -A FORWARD -i eth1 -o wg0 -j ACCEPT
Packet Count: 15,234
```

#### 4. Performance Metrics
- **Test Duration**: How long the analysis took
- **Hop Count**: Number of routers in the path
- **MTU**: Maximum packet size supported

### Interpreting Colors and Icons

- 🟢 **Green/Check**: Traffic allowed, test passed
- 🔴 **Red/X**: Traffic blocked, test failed
- 🟡 **Yellow/Warning**: Partial success or warnings
- 🔵 **Blue/Info**: Informational messages

## PDF Reports

### Report Contents

PDF reports provide comprehensive documentation including:

1. **Executive Summary**
   - Test parameters
   - Overall result
   - Key findings

2. **Network Visualization**
   - GraphViz diagram showing the path
   - Router connections
   - Interface labels

3. **Detailed Analysis**
   - Router-by-router breakdown
   - All applicable firewall rules
   - Packet statistics
   - Rule hit counts

4. **Technical Details**
   - Complete routing tables
   - Policy routing rules
   - Interface configurations
   - Timestamp and test ID

### Downloading Reports

1. Click "Download PDF Report" button
2. Report generates (may take 10-20 seconds)
3. Save to your computer or open directly
4. File naming: `traceroute_report_YYYYMMDD_HHMMSS.pdf`

### Sharing Reports

Reports can be:
- Emailed to colleagues
- Attached to tickets
- Archived for compliance
- Used in documentation

## Common Use Cases

### 1. Verifying New Firewall Rules

**Scenario**: You've added new firewall rules and need to verify they work correctly.

**Steps**:
1. Enter the source IP that should be allowed
2. Enter the destination IP/port you're protecting
3. Run the test
4. Verify status shows "REACHABLE" for allowed traffic
5. Test with an IP that should be blocked
6. Verify status shows "BLOCKED"

### 2. Troubleshooting Connection Issues

**Scenario**: Users report they cannot access a service.

**Steps**:
1. Enter user's source IP address
2. Enter service destination IP and port
3. Run the test
4. Check where traffic is blocked
5. Review the blocking firewall rule
6. Generate PDF report for the network team

### 3. Pre-Change Validation

**Scenario**: Planning network changes and need to document current state.

**Steps**:
1. Run tests for all critical paths
2. Generate PDF reports for each
3. Save reports as baseline
4. After changes, run same tests
5. Compare results to verify no unintended impacts

### 4. Compliance Documentation

**Scenario**: Need to prove certain traffic is blocked for compliance.

**Steps**:
1. Test connections that must be blocked
2. Verify "BLOCKED" status
3. Generate PDF reports
4. Reports show blocking rules and timestamps
5. Archive for audit purposes

## Troubleshooting

### Common Issues and Solutions

#### Cannot Login
- **Issue**: Login fails with correct credentials
- **Solutions**:
  - Clear browser cookies and cache
  - Try a different browser
  - Verify caps lock is off
  - Contact administrator to reset password

#### Test Hangs or Times Out
- **Issue**: Test doesn't complete after 60 seconds
- **Solutions**:
  - Refresh the page and try again
  - Check if destination IP is valid
  - Verify network connectivity
  - Try a simpler test first

#### PDF Won't Download
- **Issue**: PDF report fails to generate
- **Solutions**:
  - Check popup blocker settings
  - Try a different browser
  - Save instead of opening directly
  - Contact support if issue persists

#### Results Don't Match Expectations
- **Issue**: Test shows different results than expected
- **Solutions**:
  - Verify IP addresses are correct
  - Check if test data is up-to-date
  - Confirm port and protocol settings
  - Review timestamp of last data update

### Getting Help

If you encounter issues not covered here:

1. **Check with your team lead** - They may know about recent changes
2. **Contact system administrator** - For login or access issues
3. **Submit a support ticket** - Include:
   - Screenshot of the error
   - Test parameters used
   - Time of the test
   - Expected vs actual results

### Best Practices

1. **Regular Testing**
   - Test critical paths weekly
   - Document baseline behavior
   - Save reports for comparison

2. **Accurate Input**
   - Double-check IP addresses
   - Verify port numbers
   - Use correct protocol

3. **Security**
   - Always logout when finished
   - Don't share credentials
   - Report suspicious activity

4. **Documentation**
   - Save important reports
   - Name files descriptively
   - Maintain test history