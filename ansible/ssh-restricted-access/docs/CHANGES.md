# Change Log - SSH Restricted Access Ansible Playbook

## Major Updates

### User Management
- **Centrally Managed Users Support**: Playbook now detects and respects users managed by FreeIPA, LDAP, or SSSD
  - Automatic detection via `sss_cache` and getent checks
  - Manual override with `centrally_managed: true` configuration option
  - Skips user creation/modification for centrally managed accounts
  - Uses existing user home directory from central management

### Directory Structure Changes
- **Home Directory**: Changed from `/var/empty/traceroute-user` to `/home/traceroute-user`
  - More standard location for service accounts
  - Directory will contain `.ssh/authorized_keys` and other files
- **Wrapper Script Location**: Moved from `/usr/local/bin` to `$HOME/bin`
  - All restricted user files now in one contained location
  - Easier management and cleanup
- **Log Location**: Changed to `$HOME/log` when logging is enabled
  - Keeps all user-related files together

### File Management
- **"Managed by Ansible" Detection**: 
  - Both `authorized_keys` and wrapper script check for "ansible_managed" marker
  - Files without this marker are not modified (preserved for manual management)
  - Files are only created/updated if they don't exist or contain the marker

### Security Enhancements
- **IP Validation**: Wrapper script now ONLY accepts `10.x.x.x` IPv4 addresses
  - Strict regex validation: `^10\.([0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])\.(...)`
  - First positional parameter only - all other SSH command arguments ignored
  - Prevents command injection and parameter manipulation
- **Configurable Traceroute Options**: 
  - All traceroute options now configured in YAML, not via SSH
  - Options include: max_hops, wait_time, queries, packet_size, no_dns, interface, source_address
  - Users cannot override these options via SSH commands

### Logging Changes
- **Default Disabled**: Logging now disabled by default for performance
  - Set `tracersh.logging.enabled: yes` to enable
- **Location**: Logs written to `$HOME/log/tracersh.log`

### Permission Structure
```
/home/traceroute-user/          # Owner: user, Group: user, Mode: 0750
├── .ssh/                       # Owner: root, Group: root, Mode: 0700
│   └── authorized_keys         # Owner: root, Group: root, Mode: 0644
├── bin/                        # Owner: root, Group: user, Mode: 0750
│   └── tracersh      # Owner: root, Group: user, Mode: 0750
└── log/                        # Owner: user, Group: user, Mode: 0750 (if logging enabled)
    └── tracersh.log  # Owner: user, Group: user, Mode: 0640
```

## Configuration Changes

### New Options
- `restricted_user.centrally_managed`: Skip user creation for FreeIPA/LDAP users
- `tracersh.traceroute_options`: Full control over traceroute parameters
- Security permissions for all directories (home, bin, log)

### Changed Defaults
- Home directory: `/home/traceroute-user` (was `/var/empty/traceroute-user`)
- Wrapper path: `bin/tracersh` (was `/usr/local/bin/tracersh`)
- Logging: Disabled by default (was enabled)
- Validation pattern: Only accepts `10.x.x.x` addresses

## Usage Impact

### SSH Command Changes
```bash
# Old usage (any target accepted):
ssh traceroute-user@router google.com -n -m 10

# New usage (only 10.x.x.x IP, no options):
ssh traceroute-user@router 10.0.0.1
```

### Testing Updates
- All test targets updated to use `10.x.x.x` addresses
- Invalid target tests include non-10.x.x.x addresses
- Options are configured in YAML, not tested via SSH

## Migration Notes

For existing deployments:
1. Backup current configuration
2. Update configuration files with new paths
3. Set `centrally_managed: true` if using FreeIPA/LDAP
4. Configure desired traceroute options in YAML
5. Run playbook - it will migrate files to new locations

## Security Benefits

1. **Reduced Attack Surface**: Only `10.x.x.x` addresses accepted
2. **No Parameter Injection**: SSH command options completely ignored
3. **Centralized Control**: All options configured via Ansible, not runtime
4. **Preserved Manual Config**: Won't overwrite manually managed files
5. **FreeIPA/LDAP Compatible**: Works with enterprise identity management