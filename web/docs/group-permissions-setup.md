# Group Permissions Setup for Traceroute Simulator Web Interface

This document describes how to set up group permissions to allow multiple users (e.g., `sparavec` and `www-data`) to access the traceroute simulator registry files and semaphores.

## Problem

The traceroute simulator uses several registry files and POSIX semaphores for coordination:
- `/tmp/traceroute_hosts_registry.json`
- `/tmp/traceroute_routers_registry.json`
- `/tmp/traceroute_interfaces_registry.json`
- `/tmp/traceroute_bridges_registry.json`
- `/tmp/traceroute_services_registry.json`
- POSIX semaphores: `/tsim_hosts_reg`, `/tsim_routers_reg`, `/tsim_interfaces_reg`, `/tsim_bridges_reg`, `/tsim_services_reg`

When different users (e.g., development user and web server user) need to access these resources, permission issues arise.

## Solution

Create a shared group and configure the simulator to use group permissions.

### 1. Create the Shared Group

```bash
# Create the tsim-users group
sudo groupadd tsim-users

# Add users to the group
sudo usermod -a -G tsim-users sparavec
sudo usermod -a -G tsim-users www-data

# Verify group membership
groups sparavec
groups www-data
```

### 2. Configure Sudoers (Already Done)

The sudoers file has already been configured via:
```bash
sudo cp web/config/tsimsh-sudoers /etc/sudoers.d/tsimsh-web
sudo chmod 0440 /etc/sudoers.d/tsimsh-web
```

### 3. Clean Up Existing Resources

Before the first run with the new group permissions, clean up any existing registry files and semaphores:

```bash
# Remove existing registry files
sudo rm -f /tmp/traceroute_*_registry.json

# Remove existing semaphores (requires manual cleanup)
# List semaphores
ls -la /dev/shm/sem.tsim*

# Remove each semaphore file
sudo rm -f /dev/shm/sem.tsim_hosts_reg
sudo rm -f /dev/shm/sem.tsim_routers_reg
sudo rm -f /dev/shm/sem.tsim_interfaces_reg
sudo rm -f /dev/shm/sem.tsim_bridges_reg
sudo rm -f /dev/shm/sem.tsim_services_reg
```

### 4. Code Changes (Already Implemented)

The following changes have been made to the codebase:

1. **Semaphore Creation with Group Permissions** (mode=0o660):
   - `src/simulators/host_namespace_setup.py`
   - `src/simulators/service_manager.py`

2. **File Creation with Group Permissions**:
   - Set umask to 0o002 before creating files
   - Set file permissions to 0o664 (rw-rw-r--)
   - Implemented in all registry save methods

3. **Updated Files**:
   - `src/simulators/host_namespace_setup.py`
   - `src/simulators/service_manager.py`
   - `src/simulators/network_namespace_setup.py`

## Usage

After setting up the group:

1. **Logout and login** again for group changes to take effect:
   ```bash
   # Or use newgrp for immediate effect
   newgrp tsim-users
   ```

2. **Run network setup** (creates initial registries):
   ```bash
   sudo make netsetup
   ```

3. **Web interface** should now work without permission errors:
   - The web server (www-data) can read/write registry files
   - Both users can access shared semaphores

## Troubleshooting

### Permission Denied Errors

If you still see permission errors:

1. **Check group membership**:
   ```bash
   id sparavec
   id www-data
   ```

2. **Check registry file permissions**:
   ```bash
   ls -la /tmp/traceroute_*_registry.json
   ```
   Should show group as `tsim-users` with permissions `-rw-rw-r--`

3. **Check semaphore permissions**:
   ```bash
   ls -la /dev/shm/sem.tsim*
   ```
   Should show group permissions (rw-rw----)

### Bridge Registry Not Found

If you see "ERROR: Bridge registry not found. Run netsetup first":

1. Run the network setup:
   ```bash
   sudo make netsetup
   ```

2. Verify registries were created:
   ```bash
   ls -la /tmp/traceroute_*_registry.json
   ```

## Security Considerations

- The `tsim-users` group has read/write access to all registry files
- Members can create and modify network namespaces via tsimsh
- Ensure only trusted users are added to this group
- The sudoers configuration allows www-data to run Python scripts without password

## Alternative Registry Locations

You can configure alternative locations for registry files by creating `~/traceroute_simulator.yaml`:

```yaml
registry_files:
  hosts: /var/lib/traceroute_simulator/hosts_registry.json
  routers: /var/lib/traceroute_simulator/routers_registry.json
  interfaces: /var/lib/traceroute_simulator/interfaces_registry.json
  bridges: /var/lib/traceroute_simulator/bridges_registry.json
  services: /var/lib/traceroute_simulator/services_registry.json
```

Ensure the directory exists and has proper group permissions:
```bash
sudo mkdir -p /var/lib/traceroute_simulator
sudo chgrp tsim-users /var/lib/traceroute_simulator
sudo chmod 2775 /var/lib/traceroute_simulator  # setgid bit ensures new files inherit group
```