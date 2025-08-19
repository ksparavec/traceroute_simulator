# SSH Restricted Access Solutions for Remote Command Execution

## Executive Summary

This document presents comprehensive research on existing solutions for creating restricted SSH access that allows execution of only specific preconfigured commands (such as `/usr/bin/traceroute`) on remote hosts. The analysis covers security implications, implementation complexity, and maintenance requirements of various approaches.

## Requirements

- Local user must be able to execute traceroute command on remote router via SSH
- Public key authentication to avoid password prompts
- Remote user can execute only preconfigured commands with full paths
- One command per connection (immediate exit after execution)
- Configuration must be owned by root and immutable by the restricted user
- Public keys must be managed securely

## Solutions Analysis

### 1. OpenSSH Built-in Restrictions

#### 1.1 authorized_keys command= Option

**Implementation:**
```bash
command="/usr/bin/traceroute" ssh-rsa AAAAB3NzaC1yc2E...
```

**Features:**
- Forces execution of specified command regardless of what client requests
- Provides `$SSH_ORIGINAL_COMMAND` environment variable for wrapper scripts
- Can combine with other restrictions (no-port-forwarding, no-X11-forwarding, etc.)

**Security Considerations:**
- Command injection risks when using `$SSH_ORIGINAL_COMMAND` without proper validation
- Path traversal vulnerabilities if not carefully implemented
- Requires one key per command for multiple commands

#### 1.2 OpenSSH restrict Option (v7.2+)

**Implementation:**
```bash
restrict,command="/usr/bin/traceroute" ssh-rsa AAAAB3NzaC1yc2E...
```

**Features:**
- Applies all security restrictions by default
- Disables: port forwarding, agent forwarding, X11 forwarding, PTY allocation, ~/.ssh/rc execution
- Future-proof: includes any restrictions added in future OpenSSH versions
- Can selectively re-enable features as needed

**Best Practice Example:**
```bash
restrict,from="192.168.1.0/24",command="/usr/bin/traceroute $SSH_ORIGINAL_COMMAND" ssh-rsa AAAAB3...
```

#### 1.3 ForceCommand in sshd_config

**Implementation:**
```bash
Match User traceroute-user
    ForceCommand /usr/bin/traceroute
    AllowTcpForwarding no
    X11Forwarding no
```

**Features:**
- Server-wide enforcement
- Cannot be overridden by authorized_keys
- Works with Match blocks for granular control

**Limitations:**
- Less flexible than per-key restrictions
- All connections for matched users get same command

### 2. Restricted Shells

#### 2.1 rbash (Restricted Bash)

**Security Issues:**
- **Easily bypassed** through multiple vectors:
  - Vi/Vim: `:set shell=/bin/bash` then `:shell`
  - Python: `python -c 'import os; os.system("/bin/bash")'`
  - SSH: `ssh user@localhost -t "/bin/bash"`
  - AWK: `awk 'BEGIN {system("/bin/sh")}'`
- Not designed as a security feature
- Limited configurability

**Verdict:** Not suitable for security-critical applications

#### 2.2 rssh

**Critical Issues:**
- **No longer maintained** (abandoned by author)
- Multiple CVEs including command injection vulnerabilities
- CVE-2019-1000018: Command execution bypass
- CVE-2019-3463/3464: Validation vulnerabilities

**Verdict:** Do not use - deprecated and vulnerable

#### 2.3 scponly

**Vulnerabilities:**
- Command execution via dangerous subcommands (CVE affecting v4.6 and earlier)
- PATH manipulation attacks
- LD_PRELOAD privilege escalation
- Argument injection vulnerabilities

**Verdict:** Multiple security issues, not recommended

#### 2.4 lshell (Python-based)

**Known Issues:**
- Remote Code Execution in v0.9.15
- Shell escape through command chaining (`echo && bash`)
- Python interpreter escapes
- File creation in allowed directories can lead to escapes

**Mitigation:**
- Add `&&`, `||`, `;` to forbidden list
- Restrict interpreter access
- Regular updates required

**Verdict:** Requires careful configuration and constant vigilance

#### 2.5 git-shell

**Purpose-Built Limitations:**
- Designed only for Git operations
- CVE-2022-39260: Heap overflow leading to RCE
- CVE-2017-8386: Less pager bypass vulnerability

**Verdict:** Only suitable for Git operations, not general commands

### 3. Advanced Solutions

#### 3.1 sshdo

**Features:**
- Training mode to learn required commands
- Automatic configuration generation
- Unlearn feature for maintaining least privilege
- Written in Python
- Flexible multi-command support

**Implementation:**
```bash
# Install sshdo
# Configure as forced command in authorized_keys
command="/usr/local/bin/sshdo" ssh-rsa AAAAB3...
```

**Pros:**
- Well-designed security model
- Active maintenance
- Gradual restriction capabilities

**Cons:**
- Additional software dependency
- Requires Python
- More complex than built-in solutions

#### 3.2 Chroot Jails

**Implementation Complexity:**
- Must copy all required binaries and libraries
- Requires proper directory structure
- Need to maintain updates in jail

**Security Considerations:**
- **Not a security feature by design**
- Classic double chroot escape if user has root
- Writable root directory vulnerabilities
- Process table manipulation escapes
- File descriptor exploitation

**Best Practices:**
- Always drop privileges after chrooting
- Mount with nosuid option
- Remove all SUID binaries
- Regular security audits

**Verdict:** High maintenance, complex setup, not foolproof

#### 3.3 Custom C Wrapper

**Example Implementation Approach:**
```c
// Pseudo-code structure
int main(int argc, char *argv[]) {
    // Read configuration from /etc/traceroute-wrapper.conf
    // Validate arguments against whitelist
    // Execute only /usr/bin/traceroute with validated args
    // Exit immediately
}
```

**Advantages:**
- Complete control over execution
- No shell interpretation
- Fast and efficient
- Can implement specific validation

**Disadvantages:**
- Requires development expertise
- Potential for security bugs
- Must handle all edge cases
- Ongoing maintenance burden

### 4. Sudo-based Approach

While not directly an SSH restriction mechanism, sudo can be combined with SSH forced commands:

**Implementation:**
```bash
# In authorized_keys
command="sudo -n /usr/bin/traceroute" ssh-rsa...

# In /etc/sudoers.d/traceroute
traceroute-user ALL=(ALL) NOPASSWD: /usr/bin/traceroute *
```

**Security Features:**
- Digest verification for binaries
- Environment sanitization
- Comprehensive logging
- Well-tested codebase

## Comparison Matrix

| Solution | Security Level | Maintenance | Complexity | Recommendation |
|----------|---------------|-------------|------------|----------------|
| OpenSSH restrict + command= | Very High | Low | Low | **Recommended** |
| ForceCommand | High | Low | Low | Good alternative |
| rbash | Very Low | Low | Low | Not recommended |
| rssh | Very Low | N/A | Medium | Deprecated - Do not use |
| scponly | Low | Medium | Medium | Not recommended |
| lshell | Low-Medium | Medium | Medium | Use with caution |
| git-shell | Medium (Git only) | Low | Low | Git operations only |
| sshdo | High | Medium | Medium | Good for complex needs |
| Chroot Jail | Medium | High | High | Overkill for simple commands |
| Custom C Wrapper | Variable | High | High | For specific requirements |
| Sudo + SSH | Very High | Medium | Medium | Good for existing sudo setups |

## Recommended Implementation

### Primary Solution: OpenSSH Native Restrictions

For the specific use case of allowing only traceroute execution:

```bash
# 1. Create dedicated user
sudo useradd -r -s /bin/false -d /var/empty/traceroute-user traceroute-user

# 2. Create .ssh directory structure
sudo mkdir -p /var/empty/traceroute-user/.ssh
sudo chmod 700 /var/empty/traceroute-user/.ssh

# 3. Configure authorized_keys with maximum restrictions
sudo tee /var/empty/traceroute-user/.ssh/authorized_keys << 'EOF'
restrict,from="192.168.1.0/24",command="/usr/local/bin/traceroute-wrapper" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI...
EOF

# 4. Set proper ownership and permissions
sudo chown -R root:root /var/empty/traceroute-user/.ssh
sudo chmod 644 /var/empty/traceroute-user/.ssh/authorized_keys

# 5. Create wrapper script (optional, for parameter validation)
sudo tee /usr/local/bin/traceroute-wrapper << 'EOF'
#!/bin/bash
set -euo pipefail

# Validate SSH_ORIGINAL_COMMAND
if [[ -z "${SSH_ORIGINAL_COMMAND:-}" ]]; then
    echo "Error: No target specified" >&2
    exit 1
fi

# Extract and validate target
TARGET="${SSH_ORIGINAL_COMMAND}"

# Basic validation (adjust as needed)
if ! [[ "$TARGET" =~ ^[a-zA-Z0-9.-]+$ ]]; then
    echo "Error: Invalid target format" >&2
    exit 1
fi

# Execute traceroute with validated target
exec /usr/bin/traceroute "$TARGET"
EOF

sudo chmod 755 /usr/local/bin/traceroute-wrapper
sudo chown root:root /usr/local/bin/traceroute-wrapper
```

### Alternative: Simple C Wrapper

For environments requiring maximum security and minimal dependencies:

```c
// traceroute-wrapper.c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <regex.h>

#define TRACEROUTE_PATH "/usr/bin/traceroute"
#define MAX_TARGET_LEN 255

int validate_target(const char *target) {
    regex_t regex;
    int ret;
    
    // Simple hostname/IP validation regex
    const char *pattern = "^[a-zA-Z0-9.-]+$";
    
    ret = regcomp(&regex, pattern, REG_EXTENDED);
    if (ret) return 0;
    
    ret = regexec(&regex, target, 0, NULL, 0);
    regfree(&regex);
    
    return (ret == 0);
}

int main(int argc, char *argv[]) {
    const char *ssh_cmd = getenv("SSH_ORIGINAL_COMMAND");
    
    if (!ssh_cmd || strlen(ssh_cmd) == 0) {
        fprintf(stderr, "Error: No target specified\n");
        return 1;
    }
    
    if (strlen(ssh_cmd) > MAX_TARGET_LEN) {
        fprintf(stderr, "Error: Target too long\n");
        return 1;
    }
    
    if (!validate_target(ssh_cmd)) {
        fprintf(stderr, "Error: Invalid target format\n");
        return 1;
    }
    
    // Execute traceroute
    char *args[] = {TRACEROUTE_PATH, (char *)ssh_cmd, NULL};
    execv(TRACEROUTE_PATH, args);
    
    // If we get here, exec failed
    perror("Error executing traceroute");
    return 1;
}
```

Compile and install:
```bash
gcc -O2 -Wall -Wextra -o traceroute-wrapper traceroute-wrapper.c
sudo mv traceroute-wrapper /usr/local/bin/
sudo chown root:root /usr/local/bin/traceroute-wrapper
sudo chmod 755 /usr/local/bin/traceroute-wrapper
```

## Security Best Practices

1. **Defense in Depth**
   - Combine multiple security layers
   - Use network-level restrictions (firewall rules)
   - Implement comprehensive logging

2. **Principle of Least Privilege**
   - Grant minimum necessary permissions
   - Use dedicated users for specific tasks
   - Regularly audit and remove unused access

3. **Configuration Management**
   - Root ownership of all configuration files
   - Immutable permissions (chmod 644 or more restrictive)
   - Version control for configuration changes

4. **Monitoring and Auditing**
   - Log all SSH connections and commands
   - Regular security audits
   - Monitor for escape attempts

5. **Regular Updates**
   - Keep OpenSSH updated
   - Apply security patches promptly
   - Review CVE databases for vulnerabilities

## Conclusion

For restricting SSH access to execute only traceroute commands, the **OpenSSH native solution using the `restrict` option combined with `command=` in authorized_keys** provides the best balance of security, simplicity, and maintainability. This approach:

- Requires no additional software
- Provides maximum security restrictions by default
- Is well-tested and widely deployed
- Has minimal maintenance overhead
- Is future-proof against new attack vectors

Avoid using deprecated or unmaintained solutions (rssh, scponly) and be cautious with restricted shells (rbash, lshell) due to their numerous bypass techniques. For complex multi-command requirements, consider sshdo or a custom wrapper, but ensure proper security validation and regular audits.

## References

- OpenSSH 7.2 Release Notes: https://www.openssh.com/txt/release-7.2
- SSH Forced Commands Documentation: OpenSSH Manual Pages
- CVE Database: https://cve.mitre.org/
- sshdo Project: https://github.com/raforg/sshdo