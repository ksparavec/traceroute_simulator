# SSSD Configuration for FreeIPA Provider

## Example FreeIPA Domain Configuration

Replace the `[domain/LOCAL]` section in `/etc/sssd/sssd.conf` with:

```ini
[sssd]
services = nss, pam, sudo, ssh
domains = IPA.EXAMPLE.COM

[domain/IPA.EXAMPLE.COM]
# IPA provider automatically configures everything
id_provider = ipa
auth_provider = ipa
access_provider = ipa
chpass_provider = ipa

# IPA server settings
ipa_server = ipa.example.com
# Or for multiple servers with failover:
# ipa_server = ipa1.example.com, ipa2.example.com

# IPA domain and hostname
ipa_domain = ipa.example.com
ipa_hostname = client.ipa.example.com

# Optional: Cache credentials for offline authentication
cache_credentials = true
krb5_store_password_if_offline = true

# Optional: Performance tuning
ldap_id_use_start_tls = true
ldap_tls_cacert = /etc/ipa/ca.crt

# Optional: Override homedir if needed
# override_homedir = /home/%u

# Optional: Restrict access to specific groups
# access_provider = simple
# simple_allow_groups = webusers, admins

[pam]
offline_credentials_expiration = 7

[nss]
filter_users = root
filter_groups = root
```

## Automatic Configuration with ipa-client-install

The easiest way to configure SSSD for FreeIPA is using the IPA client installer:

```bash
# Install IPA client packages
sudo apt-get install freeipa-client  # Debian/Ubuntu
# or
sudo dnf install ipa-client  # RHEL/Fedora

# Join the IPA domain (will configure SSSD automatically)
sudo ipa-client-install \
  --server=ipa.example.com \
  --domain=ipa.example.com \
  --realm=IPA.EXAMPLE.COM \
  --principal=admin \
  --password=adminpassword \
  --mkhomedir \
  --enable-dns-updates

# This automatically:
# - Configures /etc/sssd/sssd.conf
# - Sets up Kerberos (/etc/krb5.conf)
# - Configures NSS and PAM
# - Retrieves IPA CA certificate
# - Creates host principal in IPA
```

## Key Differences from Proxy Provider

1. **No proxy_pam_target needed** - IPA provider handles authentication directly
2. **Automatic discovery** - Can auto-discover IPA servers via DNS SRV records
3. **Kerberos integration** - Supports SSO with Kerberos tickets
4. **HBAC support** - Host-based access control from IPA
5. **Sudo rules** - Centralized sudo rules from IPA
6. **SSH keys** - SSH public key management from IPA

## Features Available with IPA Provider

### 1. Host-Based Access Control (HBAC)
```ini
# In the domain section:
access_provider = ipa
# HBAC rules are fetched from IPA server
```

### 2. Automatic Home Directory Creation
```ini
[pam]
pam_mkhomedir = True
```

### 3. Kerberos Authentication
Users can authenticate with Kerberos tickets instead of passwords:
```bash
kinit user@IPA.EXAMPLE.COM
# Now can access web app without password
```

### 4. Group-Based Access
Control access via IPA groups:
```ini
# Option 1: Using simple access provider
access_provider = simple
simple_allow_groups = webusers, developers

# Option 2: Using HBAC rules in IPA
access_provider = ipa
# Configure HBAC rules on IPA server
```

## Testing IPA Authentication

1. **Verify IPA connectivity**:
   ```bash
   # Check if client can reach IPA server
   ipa ping
   
   # List IPA users
   ipa user-find
   
   # Check SSSD can see IPA users
   getent passwd username@ipa.example.com
   ```

2. **Test authentication**:
   ```bash
   # Test with IPA user
   su - ipauser@ipa.example.com
   
   # Test PAM authentication
   pamtester traceroute-web ipauser authenticate
   ```

3. **Check web authentication**:
   - IPA users should be able to log in to the web interface
   - Authentication source will show as "sssd"
   - No need to create local users for IPA users

## Troubleshooting IPA Provider

1. **Check IPA enrollment**:
   ```bash
   sudo ipa-client-install --uninstall  # If needed to re-enroll
   klist -k /etc/krb5.keytab  # Check host keytab
   ```

2. **Debug SSSD with IPA**:
   ```ini
   [domain/IPA.EXAMPLE.COM]
   debug_level = 9
   ```

3. **Common issues**:
   - DNS must be properly configured for IPA discovery
   - Time sync is critical (use NTP/chrony)
   - Firewall must allow LDAP (389/636) and Kerberos (88/464)

## Advantages of IPA Provider

1. **Centralized management** - All user/group/policy management in IPA
2. **No local user management** - Users are created/managed in IPA only
3. **Advanced features** - HBAC, sudo rules, SSH keys, certificates
4. **Scalability** - Supports thousands of users with caching
5. **Security** - Kerberos authentication, encrypted LDAP, central audit