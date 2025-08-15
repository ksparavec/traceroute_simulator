# SSSD Authentication Integration

This document describes the SSSD (System Security Services Daemon) authentication integration for the Traceroute Simulator web interface.

## Implementation Summary

The SSSD authentication has been successfully implemented as a secondary fallback mechanism for the web application. This implementation allows the system to authenticate users against external identity providers while maintaining support for local users.

### Key Changes Made

1. **Modified AuthManager** (`web/cgi-bin/lib/auth.py`):
   - Added SSSD/PAM authentication support as fallback
   - Returns tuple (success, auth_source) to identify authentication method
   - Comprehensive error handling and logging
   - Maintains backward compatibility

2. **Updated login.py** (`web/cgi-bin/login.py`):
   - Handles dual authentication sources
   - Logs authentication source (local vs sssd)
   - Maintains backward compatibility with legacy AuthManager

3. **Created PAM Configurations**:
   - `web/config/pam/traceroute-web`: Main PAM service using pam_sss.so
   - `web/config/pam/sssd-proxy-target`: PAM service for SSSD proxy backend

4. **Added Makefile Target** (`make pam-config`):
   - Copies PAM configuration to /etc/pam.d/traceroute-web
   - Sets proper permissions (644)

5. **Python PAM Module**:
   - Required for web authentication only (not part of tsimsh dependencies)
   - Must be installed manually from pip before using SSSD authentication
   - Uses `python-pam` package from PyPI (pip version 2.0.2+)
   - **Important**: Do NOT use system package (python3-pam) as it has incompatible API

6. **Created Documentation** (`docs/SSSD_AUTHENTICATION.md`):
   - Complete setup instructions
   - Architecture overview  
   - Troubleshooting guide
   - Security considerations

7. **Added Password Visibility Toggle**:
   - Login forms now include eye icon button to show/hide password
   - Implemented in both `web/htdocs/login.html` and `web/cgi-bin/login.py`
   - Uses SVG icons for better cross-browser compatibility

### Authentication Flow
1. User credentials are first checked against local JSON database
2. If local authentication fails, SSSD authentication is attempted
3. All authentication events are logged with their source
4. Original error messages to users remain generic for security

### Quick Deployment

#### For Existing SSSD Environments (Production)
```bash
# Install python-pam module
sudo pip3 install --break-system-packages python-pam

# Copy PAM configuration
sudo make pam-config
# OR manually:
sudo cp web/config/pam/traceroute-web /etc/pam.d/traceroute-web
sudo chmod 644 /etc/pam.d/traceroute-web

# That's all! Users can now authenticate via existing SSSD
```

#### For New Installations or Testing
```bash
# Install python-pam module
sudo pip3 install --break-system-packages python-pam

# Copy PAM configuration  
sudo make pam-config

# If testing with local users, configure SSSD proxy (see documentation)
sudo vim /etc/sssd/sssd.conf
sudo systemctl restart sssd
```

The implementation is production-ready with proper error handling, logging, and maintains full backward compatibility with existing local users.

## Overview

The web application now supports dual authentication mechanisms:
1. **Primary**: Local JSON-based user database (existing functionality)
2. **Secondary**: SSSD authentication via PAM (fallback when local authentication fails)

This allows the application to authenticate against external identity providers (Active Directory, LDAP, FreeIPA, etc.) while maintaining local user support.

## Architecture

```
User Login
    ↓
AuthManager.verify_user()
    ↓
Try Local Authentication (_verify_local_user)
    ↓
If Failed → Try SSSD Authentication (_verify_sssd_user)
    ↓
Return (success: bool, auth_source: 'local'|'sssd'|None)
```

## Installation

### Prerequisites

1. SSSD installed and configured on the system
2. Python PAM module (installed from pip via `make pam-config`)
3. Proper PAM service configuration

### Setup Steps

1. **Install Python PAM Module**
   The python-pam module is required for web authentication only (not part of tsimsh dependencies).
   Install it manually using pip:
   ```bash
   sudo pip3 install python-pam
   # or if you get a warning about system packages:
   sudo pip3 install --break-system-packages python-pam
   ```
   
   **Important**: Do NOT use the Debian/Ubuntu system package (python3-pam) as it has a different, incompatible API.

2. **Configure PAM Services**
   ```bash
   # Run the automated configuration (requires sudo)
   sudo make pam-config
   ```

   This will:
   - Copy PAM configuration to `/etc/pam.d/traceroute-web`
   - Set proper permissions (644)

3. **Manual PAM Configuration** (if automated setup fails)
   ```bash
   # Copy PAM configuration
   sudo cp web/config/pam/traceroute-web /etc/pam.d/traceroute-web
   sudo chmod 644 /etc/pam.d/traceroute-web
   
   # If testing with SSSD proxy provider, also copy:
   sudo cp web/config/pam/sssd-proxy-target /etc/pam.d/sssd-proxy-target
   sudo chmod 644 /etc/pam.d/sssd-proxy-target
   
   # Add web user to shadow group (if needed for your setup)
   sudo usermod -a -G shadow www-data  # or apache on RHEL-based systems
   ```

4. **Configure SSSD** (only if not already configured)
   
   **For existing SSSD installations**: Skip this step - your SSSD is already configured!
   
   **For new installations or testing**:
   ```bash
   # Edit SSSD configuration
   sudo vim /etc/sssd/sssd.conf
   
   # Use Option 2 configuration for testing with local users
   # Or configure for your identity provider (LDAP, AD, IPA, etc.)
   
   # Restart SSSD
   sudo systemctl restart sssd
   ```

## Configuration

### AuthManager Configuration

The `AuthManager` class in `/web/cgi-bin/lib/auth.py` accepts these parameters:

```python
AuthManager(
    users_dir="/var/www/traceroute-web/data/users",  # Local user database
    enable_sssd=True,                                 # Enable SSSD fallback
    pam_service='traceroute-web',                    # PAM service name
    log_dir="/var/www/traceroute-web/logs"          # Authentication logs
)
```

### PAM Service Configuration

Two PAM configuration files are required:

1. **Main service** (`/etc/pam.d/traceroute-web`):
```
#%PAM-1.0
auth       required     pam_sss.so nodelay
account    required     pam_sss.so
session    required     pam_sss.so
password   required     pam_sss.so
```

2. **SSSD proxy target** (`/etc/pam.d/sssd-proxy-target`):
```
#%PAM-1.0
auth       required     pam_unix.so nullok nodelay
account    required     pam_unix.so
session    required     pam_permit.so
password   required     pam_permit.so
```

### SSSD Configuration

#### Option 1: Production Environment with Existing SSSD

**If SSSD is already configured and running in production (with IPA, AD, LDAP, etc.), no SSSD configuration changes are needed!**

Simply create the PAM service file:
```bash
sudo cp web/config/pam/traceroute-web /etc/pam.d/traceroute-web
```

That's it! No SSSD restart required. The web application will immediately authenticate users through your existing SSSD configuration.

#### Option 2: Testing with Local Unix Users

For testing without external identity providers, configure SSSD proxy in `/etc/sssd/sssd.conf`:

```ini
[sssd]
services = nss, pam
domains = LOCAL

[domain/LOCAL]
id_provider = files
auth_provider = proxy
proxy_pam_target = sssd-proxy-target
proxy_fast_alias = true

[pam]
offline_credentials_expiration = 7

[nss]
filter_users = root
filter_groups = root
```

This requires the additional `sssd-proxy-target` PAM file (see PAM Service Configuration above).

#### Option 3: FreeIPA Integration

For new FreeIPA deployments, the domain section would look like:

```ini
[domain/IPA.EXAMPLE.COM]
id_provider = ipa
auth_provider = ipa
ipa_server = ipa.example.com
ipa_domain = ipa.example.com
cache_credentials = true
```

Or simply use `ipa-client-install` which configures SSSD automatically

## Authentication Flow

1. User submits credentials via web form
2. `AuthManager.verify_user()` is called
3. First attempts local database authentication
4. If local fails and SSSD is enabled, attempts PAM authentication
5. Returns tuple: `(success: bool, auth_source: str)`
6. Login page logs the authentication source

## Logging

Authentication events are logged to `/var/www/traceroute-web/logs/auth.log`:

- Successful local authentication
- Successful SSSD authentication
- Failed authentication attempts
- PAM errors and debug information

Log format:
```
[2024-01-15T10:30:45] [INFO] Local authentication successful for user: jsmith
[2024-01-15T10:31:02] [INFO] SSSD authentication successful for user: aduser
[2024-01-15T10:31:15] [WARNING] All authentication methods failed for user: unknown
```

## Security Considerations

1. **Shadow Group Access**: Web user needs to be in the `shadow` group for PAM authentication
2. **File Permissions**: Ensure proper permissions on:
   - `/var/www/traceroute-web/data/users/` (750)
   - `/var/www/traceroute-web/logs/` (750)
3. **PAM Service**: Uses dedicated service name to isolate from system authentication
4. **Password Handling**: Passwords are never logged or stored (except hashed in local DB)

## Troubleshooting

### Common Issues and Solutions

1. **Authentication Hangs with Wrong Password**
   - **Cause**: SSSD proxy provider can hang on failed authentication
   - **Solution**: Ensure `sssd-proxy-target` PAM service is configured with `nodelay` option
   - **Verify**: Both PAM services should have `nodelay` in their auth lines

2. **SSSD Service Not Running**
   ```bash
   sudo systemctl status sssd
   sudo systemctl restart sssd
   sudo systemctl enable sssd
   ```

3. **Python PAM Module Issues**
   - **Wrong module**: Ensure you're using pip's `python-pam`, NOT Debian's `python3-pam`
   - **Check installation**:
     ```bash
     python3 -c "import pam; print(pam.__file__)"
     # Should show: /usr/local/lib/python3.*/dist-packages/pam/__init__.py
     ```
   - **Reinstall if needed**:
     ```bash
     sudo apt-get remove python3-pam  # Remove system package if installed
     sudo pip3 install --break-system-packages python-pam
     ```

4. **Check SSSD Logs**
   ```bash
   # Enable debug logging in /etc/sssd/sssd.conf:
   # debug_level = 9
   
   # View logs
   sudo journalctl -u sssd -f
   
   # Application logs
   tail -f /var/www/traceroute-web/logs/auth.log
   
   # System auth logs
   sudo tail -f /var/log/auth.log  # Debian/Ubuntu
   ```


## Testing

### Test Setup with SSSD Proxy

For testing SSSD integration without external identity providers:

1. **Create a test user**:
   ```bash
   sudo useradd -m testsssd
   sudo passwd testsssd  # Set a known password
   ```

2. **Configure SSSD with proxy provider** (see configuration section above)

3. **Copy PAM configurations**:
   ```bash
   sudo cp web/config/pam/traceroute-web /etc/pam.d/traceroute-web
   sudo cp web/config/pam/sssd-proxy-target /etc/pam.d/sssd-proxy-target
   ```

4. **Restart SSSD**:
   ```bash
   sudo systemctl restart sssd
   ```

5. **Test authentication**:
   ```bash
   # Create a simple test script
   cat > test_auth.py << 'EOF'
   import sys
   sys.path.insert(0, '/path/to/web/cgi-bin/lib')
   from auth import AuthManager
   
   auth = AuthManager(enable_sssd=True)
   success, source = auth.verify_user_extended('testsssd', 'password')
   print(f"Success: {success}, Source: {source}")
   EOF
   
   sudo -u www-data python3 test_auth.py
   ```

### Verify Authentication Flow

1. **Check logs** to confirm SSSD is being used:
   ```bash
   tail -f /var/www/traceroute-web/logs/auth.log
   # Should show: "SSSD authentication successful for user: testsssd"
   ```

2. **Test both success and failure**:
   - Correct password should return immediately with success
   - Wrong password should return immediately with failure

### Test Fallback Behavior
1. Create a local web user in `/var/www/traceroute-web/data/users/`
2. Local authentication takes precedence over SSSD
3. If local user doesn't exist, SSSD authentication is attempted

## Backward Compatibility

The implementation maintains full backward compatibility:
- Existing local users continue to work unchanged
- Applications using old `verify_user()` return format work via compatibility check
- No changes required to existing user management tools

## Performance Considerations

- Local authentication is attempted first (fast)
- SSSD authentication only on local failure
- SSSD caches credentials for offline scenarios
- PAM operations may add 100-500ms latency

## Future Enhancements

Potential improvements:
1. Configuration option to change authentication order
2. Support for multiple PAM services
3. Group-based authorization from SSSD
4. Two-factor authentication support
5. Session management improvements for SSSD users