# SSH Restricted Access Ansible Playbook

## Overview

This Ansible playbook automates the deployment and management of SSH restricted access for executing traceroute commands on remote routers. It uses a custom shell (`tracersh`) that serves both as a login shell and command wrapper, implementing OpenSSH's `restrict` option combined with `command=` in authorized_keys for maximum security.

## Features

- **Custom Shell (`tracersh`)**: Combined login shell and command executor in one script
- **Secure Implementation**: Uses OpenSSH 7.2+ `restrict` option for maximum security
- **Dual Tool Support**: Supports both `traceroute` and `mtr` with automatic fallback
- **Canonical CSV Output**: Converts both tools' output to unified CSV format
- **Input Validation**: Returns `# input invalid: <input> - must be valid 10.x.x.x IPv4 address` for invalid inputs
- **10.x.x.x Only**: Restricts targets to internal network (10.0.0.0/8)
- **Centralized User Support**: Works with FreeIPA/LDAP managed users
- **Fully Configurable**: All parameters configurable via YAML or environment variables
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

## Rights and Permissions Requirements

| Task | Ansible Playbook Execution | Traceroute Execution on Target |
|------|----------------------------|----------------------------------|
| **User Requirements** | Admin user with sudo access | Restricted user (traceuser) |
| **Privileges Needed** | Full sudo (root) privileges | NO admin rights required |
| **SSH Access** | Password or key-based SSH | Key-based only (forced command) |
| **File Access** | Write to /usr/local/bin, /home | Read-only via group membership |
| **Network Access** | Any source IP | Restricted by from= in authorized_keys |
| **Command Execution** | Full shell access | Only tracersh (no shell) |
| **Purpose** | Deploy/configure the solution | Execute traceroute/mtr only |

## Quick Start

### Using Default Configuration

The playbook can be used without modifying `config/default.yml` by using environment variables:

```bash
# Set environment variables for configuration
export TRACEROUTE_SIMULATOR_TRACEUSER_PKEY_FILE="/path/to/your/id_traceuser.pub"
export TRACEROUTE_SIMULATOR_FROM_HOSTS="10.0.0.0/8,192.168.0.0/16"

# Generate SSH key pair if needed
ssh-keygen -t ed25519 -f /tmp/id_traceuser -C "tracersh@example.com"
export TRACEROUTE_SIMULATOR_TRACEUSER_PKEY_FILE="/tmp/id_traceuser.pub"

# Deploy with inline inventory (no inventory file needed)
ansible-playbook -i "192.168.122.230," deploy.yml -u admin_user

# Deploy to multiple hosts
ansible-playbook -i "router1.example.com,router2.example.com," deploy.yml

# With custom SSH port
ansible-playbook -i "192.168.122.230:2222," deploy.yml
```

### Alternative: Modifying Configuration File

If you prefer to modify the configuration file instead of using environment variables:

```bash
# Edit config/default.yml directly
vim config/default.yml
# Set pkey_file: "/path/to/your/id_traceuser.pub"
# Set from_hosts as needed

# Deploy
ansible-playbook -i "192.168.122.230," deploy.yml
```

## Directory Structure

```
ansible/ssh-restricted-access/
├── README.md                   # This documentation
├── deploy.yml                  # Main deployment playbook  
├── remove.yml                  # Removal playbook
├── test.yml                    # Test playbook
├── config/
│   └── default.yml            # Production configuration
├── docs/                      # Documentation
│   ├── CHANGES.md             # Change log
│   ├── CSV-OUTPUT-FORMAT.md   # Output format specification
│   ├── SECURITY-ANALYSIS.md   # Security analysis
│   ├── TOOL-CONFIGURATION.md  # Tool configuration guide
│   └── presentation-de.*      # German presentation files
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
│       │   ├── authorized_keys.j2  # SSH authorized_keys template
│       │   └── tracersh.j2    # Combined shell/wrapper script
│       └── handlers/
│           └── main.yml       # Handlers
└── tests/
    ├── test_connectivity.yml  # Connectivity tests
    ├── test_restrictions.yml  # Security restriction tests
    └── test_commands.yml      # Command execution tests
```

## Configuration

### Configuration File (config/default.yml)

```yaml
# User account configuration
restricted_user:
  name: traceuser
  comment: "Production traceroute execution account"
  shell: /usr/local/bin/tracersh  # Custom shell
  home: /home/traceuser
  state: present
  centrally_managed: false  # Set to true for FreeIPA/LDAP users

# SSH configuration
ssh_config:
  restrict: yes  # Use OpenSSH 7.2+ restrict option
  
  # Network restrictions (can be overridden by env var)
  from_hosts:
    - "10.0.0.0/8"
    - "192.168.0.0/16"
    - "203.0.113.0/24"
  
  command: "/usr/local/bin/tracersh"
  
  # SSH public key file path (can be overridden by env var)
  pkey_file: "/tmp/id_traceuser.pub"

# Tracersh configuration
tracersh:
  enabled: yes
  path: "/usr/local/bin/tracersh"
  preferred_tool: "traceroute"  # or "mtr"
  
  # Tool paths
  traceroute_path: "/usr/bin/traceroute"
  mtr_path: "/usr/bin/mtr"
  
  # Validation
  validation:
    enabled: yes
    pattern: "^10\\.([0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])\\.([0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])\\.([0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])$"
  
  # Logging configuration
  logging:
    enabled: no
    path: "/var/log/tracersh.log"  # Full path to log file
    max_size: "100M"
    rotate: 30

# Security settings
security:
  home_dir_owner: "root"
  home_dir_group: "tracegroup"
  home_dir_mode: "0750"
  ssh_dir_owner: "root"
  ssh_dir_group: "tracegroup"
  ssh_dir_mode: "0750"
  authorized_keys_owner: "root"
  authorized_keys_group: "tracegroup"
  authorized_keys_mode: "0640"
  tracersh_owner: "root"
  tracersh_group: "tracegroup"
  tracersh_mode: "0750"
```

### Environment Variables

Override configuration without modifying files:

| Environment Variable | Description | Example |
|---------------------|-------------|---------|
| `TRACEROUTE_SIMULATOR_TRACEUSER_PKEY_FILE` | Path to SSH public key file | `/tmp/id_traceuser.pub` |
| `TRACEROUTE_SIMULATOR_FROM_HOSTS` | Comma-separated list of allowed networks | `10.0.0.0/8,192.168.0.0/16` |

## Usage

### 1. Deployment

```bash
# Deploy with inline inventory (recommended)
ansible-playbook -i "192.168.122.230," deploy.yml

# Deploy to multiple hosts
ansible-playbook -i "host1,host2,host3," deploy.yml

# With specific user
ansible-playbook -i "192.168.122.230," deploy.yml -u admin_user

# Dry run (check mode)
ansible-playbook -i "192.168.122.230," deploy.yml --check

# Deploy specific components
ansible-playbook -i "192.168.122.230," deploy.yml --tags ssh
ansible-playbook -i "192.168.122.230," deploy.yml --tags tracersh
```

### 2. Testing

The test playbook supports two modes:

#### Quick Test (connectivity only)
Tests basic SSH connectivity and authentication:
```bash
ansible-playbook -i "192.168.122.230," test.yml -e "run_quick_test=true"
```

#### Full Test Suite (default)
Runs comprehensive tests including:
1. **Connectivity tests**: SSH key authentication, basic command execution
2. **Command tests**: Valid/invalid traceroute targets, output format verification
3. **Security tests**: Forbidden commands, shell access prevention, escape attempts

```bash
# Run full test suite
ansible-playbook -i "192.168.122.230," test.yml

# Run specific test categories
ansible-playbook -i "192.168.122.230," test.yml --tags connectivity
ansible-playbook -i "192.168.122.230," test.yml --tags commands
ansible-playbook -i "192.168.122.230," test.yml --tags restrictions
```

Test results are saved to `/tmp/ssh-restricted-test-<hostname>-<timestamp>.txt`

### 3. Manual Testing

```bash
# Test with valid target (returns CSV)
ssh -i /tmp/id_traceuser traceuser@192.168.122.230 10.0.0.1

# Example output:
# # traceroute to 10.0.0.1 (10.0.0.1), 20 hops max, 60 byte packets
# 1,192.168.122.1,0.680,0
# 2,10.0.0.1,3.584,0

# Test with invalid target (returns error)
ssh -i /tmp/id_traceuser traceuser@192.168.122.230 8.8.8.8
# Output: # input invalid: 8.8.8.8 - must be valid 10.x.x.x IPv4 address

# Test shell access (should fail)
ssh -i /tmp/id_traceuser traceuser@192.168.122.230
# Output: This account is restricted to traceroute execution only.
```

### 4. Removal

```bash
# Remove from all specified hosts
ansible-playbook -i "192.168.122.230," remove.yml

# Remove from specific host
ansible-playbook -i "host1,host2," remove.yml --limit host1
```

## Logging Configuration

If logging is enabled in the configuration, the tracersh script will write to `/var/log/tracersh.log`. However, proper permissions must be set up for logging to work:

### Manual Log File Setup
```bash
# Create log file with correct permissions
sudo touch /var/log/tracersh.log
sudo chown root:tracegroup /var/log/tracersh.log
sudo chmod 660 /var/log/tracersh.log
```

### Automatic Setup with Logrotate
When logging is enabled, the playbook creates `/etc/logrotate.d/tracersh-traceuser` with:

```
/var/log/tracersh.log {
    weekly
    rotate 30
    maxsize 100M
    compress
    delaycompress
    missingok
    notifempty
    create 0660 root tracegroup  # Creates file with correct permissions
}
```

To initialize the log file immediately:
```bash
sudo logrotate -f /etc/logrotate.d/tracersh-traceuser
```

## Playbook Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `ssh_config.pkey_file` | Path to SSH public key file | `/tmp/id_traceuser.pub` |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `restricted_user.name` | `traceuser` | Username for restricted account |
| `restricted_user.shell` | `/usr/local/bin/tracersh` | Custom shell path |
| `restricted_user.home` | `/home/traceuser` | Home directory path |
| `restricted_user.centrally_managed` | `false` | Skip user creation for FreeIPA/LDAP users |
| `ssh_config.from_hosts` | `["10.0.0.0/8", "192.168.0.0/16", "203.0.113.0/24"]` | Allowed source networks |
| `ssh_config.command` | `/usr/local/bin/tracersh` | Forced command in authorized_keys |
| `tracersh.enabled` | `yes` | Whether to install tracersh script |
| `tracersh.preferred_tool` | `traceroute` | Preferred tool (`traceroute` or `mtr`) |
| `tracersh.logging.enabled` | `no` | Enable execution logging |
| `tracersh.logging.path` | `/var/log/tracersh.log` | Log file path |

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
- Configurable per deployment or via environment variables

### 3. Command Restrictions  
- Forces execution of `/usr/local/bin/tracersh` via `command=` in authorized_keys
- Tracersh serves as both login shell and command executor
- Validates only `10.x.x.x` IPv4 addresses (hardcoded regex pattern)
- Returns standardized error: `# input invalid: <input> - must be valid 10.x.x.x IPv4 address`
- Uses ICMP for probing (more reliable than UDP)
- No DNS resolution (security and performance)
- Blocks interactive SSH sessions and local logins

### 4. File Permissions
- Root ownership of critical files (authorized_keys, tracersh)
- Group-based access control via `tracegroup`
- Restrictive permissions:
  - Home directory: 750 (root:tracegroup)
  - .ssh directory: 750 (root:tracegroup)
  - authorized_keys: 640 (root:tracegroup)
  - tracersh script: 750 (root:tracegroup)
- Files immutable by restricted user

### 5. Input Validation & Hardening
- Bash script hardening block (must be first):
  - Environment sanitization (`LC_ALL=C`, `LANG=C`)
  - Secure IFS setting (`$'\n\t'`)
  - Fixed PATH (`/usr/sbin:/usr/bin:/sbin:/bin`)
  - Unset dangerous variables (`BASH_ENV`, `ENV`, `CDPATH`)
  - Remove all aliases
- Input validation:
  - Only first word of SSH_ORIGINAL_COMMAND processed
  - Regex pattern for 10.x.x.x addresses
  - Command injection prevention via parameter extraction
- Execution timeout (60s with 5s kill timeout)

## Troubleshooting

### Common Issues

1. **"Permission denied (publickey)"**
   - Verify public key file exists and is readable
   - Check file permissions on target system
   - Ensure key format is correct

2. **"Command not found"**
   - Verify traceroute or mtr is installed on target
   - Check tracersh script exists at `/usr/local/bin/tracersh`
   - Ensure script has execute permissions

3. **"This account is restricted"**
   - This is expected behavior when trying to get a shell
   - The account is working correctly

4. **No output from traceroute**
   - Check if traceroute requires sudo on the target system
   - Verify network connectivity
   - Check logs if logging is enabled

### Debug Mode

Enable verbose output for troubleshooting:

```bash
# Ansible verbose mode
ansible-playbook -i "192.168.122.230," deploy.yml -vvv

# SSH verbose mode
ssh -vvv -i /tmp/id_traceuser traceuser@192.168.122.230 10.0.0.1
```

### Log Files

If logging is enabled and properly configured:
```bash
# On target router
sudo tail -f /var/log/tracersh.log
```

## Maintenance

### Key Rotation

To rotate SSH keys:

1. Generate new key pair
2. Update `TRACEROUTE_SIMULATOR_TRACEUSER_PKEY_FILE` environment variable or `pkey_file` in config
3. Run deployment playbook
4. Test with new key
5. Remove old key from clients

### Updating Allowed Networks

1. Set `TRACEROUTE_SIMULATOR_FROM_HOSTS` environment variable or modify `ssh_config.from_hosts`
2. Run deployment playbook
3. Test from new networks

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

## Additional Documentation

- [Security Analysis](docs/SECURITY-ANALYSIS.md) - Comprehensive security assessment
- [CSV Output Format](docs/CSV-OUTPUT-FORMAT.md) - Output format specification
- [Tool Configuration](docs/TOOL-CONFIGURATION.md) - Detailed tool configuration guide
- [Changes](docs/CHANGES.md) - Version history and changes