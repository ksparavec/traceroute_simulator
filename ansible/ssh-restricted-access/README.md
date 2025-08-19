# SSH Restricted Access Ansible Playbook

## Overview

This Ansible playbook automates the deployment and management of SSH restricted access for executing traceroute commands on remote routers. It uses a custom shell (`tracersh`) that serves both as a login shell and command wrapper, implementing OpenSSH's `restrict` option combined with `command=` in authorized_keys for maximum security.

## Features

- **Custom Shell (`tracersh`)**: Combined login shell and command wrapper in one script
- **Secure Implementation**: Uses OpenSSH 7.2+ `restrict` option for maximum security
- **Dual Tool Support**: Supports both `traceroute` and `mtr` with automatic fallback
- **Canonical CSV Output**: Converts both tools' output to unified CSV format
- **Input Validation**: Returns `# input invalid: <input> - must be valid 10.x.x.x IPv4 address` for invalid inputs
- **10.x.x.x Only**: Restricts targets to internal network (10.0.0.0/8)
- **Centralized User Support**: Works with FreeIPA/LDAP managed users
- **Fully Configurable**: All parameters configurable via YAML
- **Idempotent Operations**: Safe to run multiple times
- **Clean Removal**: Ability to completely remove the restricted user setup
- **Comprehensive Testing**: Built-in test suite for connectivity, commands, and security

## Requirements

### Control Node (Ansible Host)
- Ansible 2.9 or higher
- Python 3.6+
- SSH access to target hosts with sudo privileges

### Target Nodes (Remote Routers)
- OpenSSH 7.2 or higher (RHEL/CentOS 7+, Ubuntu 16.04+, Debian 9+)
- sudo configured for administrative account
- Python installed (for Ansible modules)
- bc calculator (for MTR output parsing) - usually pre-installed
- traceroute and/or mtr installed

## Quick Start

### Prerequisites

1. **Create configuration file:**
```bash
cp config/default.yml.example config/default.yml
```

2. **Edit `config/default.yml` and set your SSH public key:**
```yaml
ssh_config:
  public_key: "YOUR_SSH_PUBLIC_KEY_HERE"  # REQUIRED!
```

3. **Create or update inventory (`inventory/hosts.yml`):**
```yaml
all:
  hosts:
    192.168.122.230:
      ansible_user: your_admin_user  # User with sudo access
```

### Deployment

```bash
# Deploy to all hosts
ansible-playbook deploy.yml

# Deploy to specific host
ansible-playbook deploy.yml -l 192.168.122.230

# Test the deployment
ansible-playbook test.yml
```

## Directory Structure

```
ansible/ssh-restricted-access/
├── README.md                   # This documentation
├── deploy.yml                  # Main deployment playbook  
├── remove.yml                  # Removal playbook
├── test.yml                    # Test playbook
├── inventory/
│   └── hosts.yml              # Inventory file
├── roles/
│   └── ssh_restricted_access/
│       ├── defaults/
│       │   └── main.yml       # Default variables
│       ├── tasks/
│       │   ├── main.yml       # Main tasks
│       │   ├── deploy.yml     # Deployment tasks
│       │   ├── remove.yml     # Removal tasks
│       │   └── validate.yml   # Validation tasks
│       ├── templates/
│       │   ├── authorized_keys.j2
│       │   └── tracersh.j2    # Combined shell/wrapper script
│       └── handlers/
│           └── main.yml       # Handlers
├── config/
│   └── default.yml.example    # Example configuration (COPY THIS!)
└── tests/
    ├── test_connectivity.yml  # Connectivity tests
    ├── test_restrictions.yml  # Security restriction tests
    └── test_commands.yml      # Command execution tests
```

## Configuration

### Configuration File (config/default.yml.example)

```yaml
# User account configuration
restricted_user:
  name: traceuser
  comment: "Restricted user for traceroute execution"
  shell: /usr/local/bin/tracersh  # Custom shell that handles both login and command execution
  home: /home/traceuser
  state: present  # Set to 'absent' to remove

# SSH configuration
ssh_config:
  # authorized_keys options
  restrict: yes
  from_hosts:
    - "192.168.1.0/24"
    - "10.0.0.0/8"
  command: "/usr/local/bin/tracersh"
  
  # SSH key (required)
  public_key: ""  # Must be provided
  key_type: "ssh-ed25519"  # or ssh-rsa
  key_comment: "traceroute-restricted@example.com"

# Tracersh (wrapper script) configuration
tracersh:
  enabled: yes
  path: "/usr/local/bin/tracersh"
  traceroute_path: "/usr/bin/traceroute"
  mtr_path: "/usr/bin/mtr"
  preferred_tool: "traceroute"
  validation:
    enabled: yes
    # Regex pattern for 10.x.x.x IPv4 addresses only
    pattern: "^10\\.([0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])\\.([0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])\\.([0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])$"
  logging:
    enabled: no
    path: "log/tracersh.log"

# Security settings
security:
  ssh_dir_owner: "root"
  ssh_dir_group: "root"
  ssh_dir_mode: "0700"
  authorized_keys_owner: "root"
  authorized_keys_group: "root"
  authorized_keys_mode: "0644"
  tracersh_owner: "root"
  tracersh_group: "root"
  tracersh_mode: "0755"

# Testing configuration
testing:
  test_targets:
    - "10.0.0.1"
    - "10.8.8.8"
    - "10.1.1.1"
  forbidden_commands:
    - "ls"
    - "cat /etc/passwd"
    - "bash"
```

### Host-Specific Configuration (inventory/host_vars/router1.yml)

```yaml
# Override default settings for specific host
restricted_user:
  name: traceroute-router1

ssh_config:
  from_hosts:
    - "192.168.100.0/24"
  public_key: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... user@admin"
```

## Usage

### 1. Initial Setup

```bash
# Clone or create the directory structure
mkdir -p ansible/ssh-restricted-access
cd ansible/ssh-restricted-access

# Copy your configuration
cp config/default.yml.example config/production.yml
# Edit config/production.yml with your settings

# Set up inventory
vim inventory/hosts.yml
```

### 2. Deploy Restricted Access

```bash
# Deploy to all hosts (uses inventory/hosts.yml by default)
ansible-playbook deploy.yml

# Deploy to specific host
ansible-playbook deploy.yml -l 192.168.122.230

# Dry run (check mode)
ansible-playbook deploy.yml --check
```

### 3. Test the Setup

```bash
# Run all tests
ansible-playbook test.yml

# Test SSH access manually (should return error for invalid IPs)
ssh traceuser@192.168.122.230 8.8.8.8
# Output: # input invalid: 8.8.8.8 - must be valid 10.x.x.x IPv4 address

# Test with valid IP
ssh traceuser@192.168.122.230 10.0.0.1
# Output: CSV format traceroute results
```

### 4. Remove Restricted Access

```bash
# Remove from all hosts
ansible-playbook remove.yml

# Remove from specific host
ansible-playbook remove.yml -l 192.168.122.230
```

## Playbook Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `ssh_config.public_key` | SSH public key for authentication | `ssh-ed25519 AAAAC3...` |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `restricted_user.name` | `traceuser` | Username for restricted account |
| `restricted_user.shell` | `/usr/local/bin/tracersh` | Custom shell that handles SSH commands |
| `restricted_user.home` | `/home/traceuser` | Home directory path |
| `restricted_user.centrally_managed` | `false` | Skip user creation for FreeIPA/LDAP users |
| `ssh_config.from_hosts` | `[]` | List of allowed source IPs/networks |
| `ssh_config.command` | `bin/traceroute-wrapper` | Command to execute (relative to home) |
| `wrapper_script.enabled` | `yes` | Whether to install wrapper script |
| `wrapper_script.preferred_tool` | `traceroute` | Preferred tool (`traceroute` or `mtr`) |
| `wrapper_script.traceroute_options.max_hops` | `20` | Maximum TTL for traceroute |
| `wrapper_script.traceroute_options.no_dns` | `true` | Disable DNS resolution |
| `wrapper_script.traceroute_options.use_icmp` | `true` | Use ICMP instead of UDP |
| `wrapper_script.mtr_options.report_cycles` | `1` | Number of pings for mtr (1 for fast results) |

## Security Features

### 1. OpenSSH Restrictions
- Uses `restrict` option (OpenSSH 7.2+) which disables:
  - Port forwarding
  - Agent forwarding
  - X11 forwarding
  - PTY allocation
  - Execution of ~/.ssh/rc

### 2. Network Restrictions
- `from=` option limits connections to specific IP addresses/networks
- Configurable per host or globally

### 3. Command Restrictions
- Forces execution of specific command only
- Wrapper script validates only `10.x.x.x` IPv4 addresses
- Uses ICMP for probing (more reliable than UDP)
- No DNS resolution (security and performance)
- No shell access (`/bin/false` shell)

### 4. File Permissions
- Root ownership of all configuration files
- Restrictive permissions (644 for authorized_keys)
- Immutable by restricted user

### 5. Input Validation
- Wrapper script validates command arguments
- Regex pattern matching for targets
- Length limitations

## Testing

### Automated Tests

The playbook includes comprehensive test cases:

1. **Connectivity Tests** (`tests/test_connectivity.yml`)
   - Verifies SSH key authentication works
   - Tests command execution
   - Validates output format

2. **Restriction Tests** (`tests/test_restrictions.yml`)
   - Ensures forbidden commands are blocked
   - Verifies no shell access
   - Tests escape attempt prevention

3. **Command Tests** (`tests/test_commands.yml`)
   - Tests valid traceroute targets
   - Verifies invalid targets are rejected
   - Checks error handling

### Manual Testing

```bash
# Test successful traceroute (returns CSV format)
ssh -i ~/.ssh/traceroute_key traceroute-user@router1 10.0.0.1

# Example output:
# # traceroute to 10.0.0.1 (10.0.0.1), 20 hops max, 60 byte packets
# 1,192.168.122.1,0.680,0
# 2,10.0.0.1,3.584,0

# Test invalid target (should fail)
ssh -i ~/.ssh/traceroute_key traceroute-user@router1 8.8.8.8

# Test command restriction (should fail)
ssh -i ~/.ssh/traceroute_key traceroute-user@router1 ls

# Test shell access (should fail)
ssh -i ~/.ssh/traceroute_key traceroute-user@router1
```

## Troubleshooting

### Common Issues

1. **"Permission denied (publickey)"**
   - Verify public key is correctly configured
   - Check file permissions (should be 644 for authorized_keys)
   - Ensure key format is correct

2. **"Command not found"**
   - Verify traceroute is installed on target system
   - Check wrapper script path is correct
   - Ensure wrapper script has execute permissions

3. **"This account is restricted"**
   - This is expected behavior when trying to get a shell
   - The account is working correctly

4. **No output from traceroute**
   - Check if traceroute requires sudo on the target system
   - Verify network connectivity
   - Check wrapper script logs if enabled

### Debug Mode

Enable verbose output for troubleshooting:

```bash
# Ansible verbose mode
ansible-playbook -i inventory/hosts.yml playbooks/deploy.yml -vvv

# SSH verbose mode
ssh -vvv -i ~/.ssh/traceroute_key traceroute-user@router1 8.8.8.8
```

### Log Files

If logging is enabled in wrapper script:
```bash
# On target router
sudo tail -f /var/log/traceroute-wrapper.log
```

## Maintenance

### Key Rotation

To rotate SSH keys:

1. Generate new key pair
2. Update `ssh_config.public_key` in configuration
3. Run deployment playbook
4. Test with new key
5. Remove old key from clients

### Updating Allowed Networks

1. Modify `ssh_config.from_hosts` in configuration
2. Run deployment playbook
3. Test from new networks

### Adding/Removing Commands

To allow additional commands:

1. Modify wrapper script template
2. Update validation patterns
3. Run deployment playbook
4. Test new commands

## Security Considerations

1. **Regular Updates**: Keep OpenSSH updated on all systems
2. **Key Management**: Store private keys securely, use key passphrases
3. **Network Security**: Combine with firewall rules for defense in depth
4. **Audit Logging**: Enable system audit logging for SSH connections
5. **Monitoring**: Monitor for failed authentication attempts
6. **Principle of Least Privilege**: Only grant access where necessary

## Support for Older Systems

For systems with OpenSSH < 7.2 (e.g., RHEL/CentOS 6):

1. Set `ssh_config.restrict: no` in configuration
2. The playbook will use traditional restrictions:
   - `no-port-forwarding`
   - `no-X11-forwarding`
   - `no-agent-forwarding`
   - `no-pty`

Note: This provides less security than the `restrict` option.

## License

This playbook is provided as-is for use in managing SSH restricted access.

## Contributing

To contribute improvements:

1. Test changes thoroughly
2. Update documentation
3. Ensure idempotency
4. Add test cases for new features