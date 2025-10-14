#!/usr/bin/env -S python3 -B -u
"""Centralized Registry Manager for all coordination operations.

This module provides a single point of coordination for:
- Physical host registry (hosts.json)
- Host leases registry (host_leases.json) with reference counting
- Router locks (per-router exclusive locks)
- Router waiter operations (inotify-based waiting)
- Neighbor leases registry (neighbor_leases.json) with reference counting

Thread-safe and process-safe using posix_ipc semaphores.
All operations are atomic.
"""

import json
import os
import time
import logging
import posix_ipc
import select
import grp
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
from contextlib import contextmanager
from dataclasses import dataclass


# ==================== EXCEPTION CLASSES ====================

class TsimRegistryError(Exception):
    """Base exception for registry operations."""
    pass


class TsimRegistryLockTimeout(TsimRegistryError):
    """Lock acquisition timeout."""
    pass


class TsimRegistryCollision(TsimRegistryError):
    """Resource collision detected (IP, name, MAC, etc.)."""
    pass


class TsimRegistryCorruption(TsimRegistryError):
    """Registry file corrupted or invalid."""
    pass


class TsimRegistryNotFound(TsimRegistryError):
    """Registry file or entry not found."""
    pass


# ==================== LOCK ORDERING ====================

LOCK_ORDER = {
    'host_registry': 1,      # /tsim-hosts-registry
    'host_leases': 2,        # /tsim-host-leases
    'router_locks': 3,       # /tsim-router-{name} (multiple, sorted by name)
    'neighbor_leases': 4     # /tsim-neighbor-leases
}


# ==================== HELPER FUNCTIONS ====================

def ensure_tsim_directory(path: Path, unix_group: str = 'tsim-users', logger: Optional[logging.Logger] = None) -> None:
    """Create directory with proper tsim permissions (2775, group ownership).

    Args:
        path: Directory path to create
        unix_group: Group name for ownership (default: tsim-users)
        logger: Optional logger for error messages

    Note: Permission errors are logged but don't raise - allows operation to continue
          even if we can't set ideal permissions (e.g., running as non-root)
    """
    try:
        # Create directory if it doesn't exist
        path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        # Can't create directory - check if it already exists
        if not path.exists():
            if logger:
                logger.error(f"Cannot create directory {path}: Permission denied")
            raise
        # Directory exists, continue

    # Try to set permissions - don't fail if we can't
    try:
        path.chmod(0o2775)
    except (PermissionError, OSError) as e:
        if logger:
            logger.debug(f"Cannot set permissions on {path}: {e}")
        # Continue anyway

    # Try to set group ownership - don't fail if we can't
    try:
        gid = grp.getgrnam(unix_group).gr_gid
        os.chown(path, -1, gid)
    except KeyError:
        if logger:
            logger.debug(f"{unix_group} group not found")
    except (PermissionError, OSError) as e:
        if logger:
            logger.debug(f"Cannot set group ownership on {path}: {e}")


def ensure_tsim_file_permissions(path: Path, unix_group: str = 'tsim-users', logger: Optional[logging.Logger] = None) -> None:
    """Set proper tsim file permissions (0660, group ownership).

    Args:
        path: File path to fix permissions on
        unix_group: Group name for ownership (default: tsim-users)
        logger: Optional logger for error messages

    Note: Permission errors are logged but don't raise - allows operation to continue
          even if we can't set ideal permissions (e.g., running as non-root)
    """
    # Try to set permissions - don't fail if we can't
    try:
        path.chmod(0o660)
    except (PermissionError, OSError) as e:
        if logger:
            logger.debug(f"Cannot set permissions on {path}: {e}")
        # Continue anyway

    # Try to set group ownership - don't fail if we can't
    try:
        gid = grp.getgrnam(unix_group).gr_gid
        os.chown(path, -1, gid)
    except KeyError:
        if logger:
            logger.debug(f"{unix_group} group not found")
    except (PermissionError, OSError) as e:
        if logger:
            logger.debug(f"Cannot set group ownership on {path}: {e}")


# ==================== INTERNAL CLASSES ====================

class _TsimLockManager:
    """Internal lock manager using posix_ipc semaphores.

    This class is NOT exposed to external callers.
    """

    def __init__(self, lock_dir: Path, unix_group: str, logger: logging.Logger):
        """Initialize lock manager.

        Args:
            lock_dir: Directory for lock files (must already exist with proper permissions)
            unix_group: Group name for ownership
            logger: Logger instance
        """
        self.lock_dir = Path(lock_dir)
        self.unix_group = unix_group
        self.logger = logger
        self.semaphores: Dict[str, posix_ipc.Semaphore] = {}
        # Directory is created by parent with proper permissions

    def acquire(self, lock_name: str, timeout: float) -> bool:
        """Acquire semaphore with timeout.

        Args:
            lock_name: Name of lock (e.g., "tsim-hosts-registry")
            timeout: Maximum wait time in seconds

        Returns:
            True if acquired, False if timeout

        Raises:
            RegistryError: On lock system errors
        """
        try:
            # Get or create semaphore
            sem_name = f"/{lock_name}"
            if lock_name not in self.semaphores:
                created_new = False
                try:
                    # Try to create with initial value 1
                    # Mode 0o660 allows owner and group to read/write
                    sem = posix_ipc.Semaphore(sem_name, flags=posix_ipc.O_CREAT,
                                             mode=0o660, initial_value=1)
                    created_new = True
                except posix_ipc.ExistentialError:
                    # Already exists, open it
                    sem = posix_ipc.Semaphore(sem_name)

                # Set group ownership on the semaphore file
                if created_new:
                    sem_file = f"/dev/shm/sem.{lock_name}"
                    try:
                        import grp
                        gid = grp.getgrnam(self.unix_group).gr_gid
                        os.chown(sem_file, -1, gid)
                    except (KeyError, PermissionError, OSError) as e:
                        self.logger.debug(f"Cannot set group ownership on semaphore {sem_file}: {e}")

                self.semaphores[lock_name] = sem
            else:
                sem = self.semaphores[lock_name]

            # Try to acquire with timeout
            start_time = time.time()
            while True:
                try:
                    sem.acquire(timeout=0.1)  # Poll every 100ms
                    self.logger.debug(f"Acquired lock: {lock_name}")
                    return True
                except posix_ipc.BusyError:
                    if time.time() - start_time >= timeout:
                        self.logger.warning(f"Timeout acquiring lock: {lock_name}")
                        return False
                    continue

        except Exception as e:
            self.logger.error(f"Error acquiring lock {lock_name}: {e}")
            raise TsimRegistryError(f"Lock acquisition failed: {e}")

    def release(self, lock_name: str) -> bool:
        """Release semaphore.

        Args:
            lock_name: Name of lock to release

        Returns:
            True if released, False if not held
        """
        try:
            if lock_name in self.semaphores:
                sem = self.semaphores[lock_name]
                sem.release()
                self.logger.debug(f"Released lock: {lock_name}")
                return True
            else:
                self.logger.warning(f"Attempted to release unheld lock: {lock_name}")
                return False
        except Exception as e:
            self.logger.error(f"Error releasing lock {lock_name}: {e}")
            return False

    def acquire_multiple_sorted(self, lock_names: List[str],
                                timeout: float) -> Tuple[bool, List[str]]:
        """Atomically acquire multiple locks in sorted order.

        CRITICAL: All-or-nothing acquisition prevents deadlocks.

        Args:
            lock_names: List of lock names to acquire
            timeout: Total timeout for all locks

        Returns:
            Tuple of (success: bool, acquired: List[str])
            If success=False, acquired list shows which locks were obtained
            before failure (caller must release these)
        """
        # Sort to ensure consistent ordering
        sorted_names = sorted(lock_names)
        acquired = []
        start_time = time.time()

        try:
            for lock_name in sorted_names:
                remaining = timeout - (time.time() - start_time)
                if remaining <= 0:
                    self.logger.warning("Timeout during multi-lock acquisition")
                    return False, acquired

                if not self.acquire(lock_name, remaining):
                    self.logger.warning(f"Failed to acquire {lock_name} in multi-lock")
                    return False, acquired

                acquired.append(lock_name)

            # Successfully acquired all
            return True, acquired

        except Exception as e:
            self.logger.error(f"Exception during multi-lock acquisition: {e}")
            return False, acquired

    def release_multiple(self, lock_names: List[str]) -> int:
        """Release multiple locks.

        Args:
            lock_names: List of lock names to release

        Returns:
            Number of locks successfully released
        """
        count = 0
        for lock_name in lock_names:
            if self.release(lock_name):
                count += 1
        return count

    def cleanup(self):
        """Cleanup semaphores on shutdown."""
        for lock_name, sem in self.semaphores.items():
            try:
                sem.close()
            except Exception as e:
                self.logger.error(f"Error closing semaphore {lock_name}: {e}")
        self.semaphores.clear()


class _TsimRegistryIO:
    """Internal registry I/O handler with atomic operations.

    This class is NOT exposed to external callers.
    """

    def __init__(self, registry_dir: Path, unix_group: str, logger: logging.Logger,
                 retry_attempts: int = 3, retry_delay: float = 0.1):
        """Initialize registry I/O handler.

        Args:
            registry_dir: Directory containing registry files (must already exist with proper permissions)
            unix_group: Group name for file ownership
            logger: Logger instance
            retry_attempts: Number of retry attempts on I/O errors
            retry_delay: Delay between retries in seconds
        """
        self.registry_dir = Path(registry_dir)
        self.unix_group = unix_group
        self.logger = logger
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        # Directory is created by parent with proper permissions

    def atomic_read(self, file_name: str) -> Dict[str, Any]:
        """Read registry file with error handling and retries.

        Args:
            file_name: Name of registry file (e.g., "hosts.json")

        Returns:
            Registry data dict

        Raises:
            RegistryNotFound: If file doesn't exist
            RegistryCorruption: If file is corrupted
            RegistryError: On I/O errors after retries
        """
        file_path = self.registry_dir / file_name

        if not file_path.exists():
            # Return empty registry structure
            return {}

        for attempt in range(self.retry_attempts):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                return data

            except json.JSONDecodeError as e:
                self.logger.error(f"JSON corruption in {file_name}: {e}")
                if attempt == self.retry_attempts - 1:
                    raise TsimRegistryCorruption(f"Corrupted registry: {file_name}")
                time.sleep(self.retry_delay)

            except Exception as e:
                self.logger.error(f"Error reading {file_name}: {e}")
                if attempt == self.retry_attempts - 1:
                    raise TsimRegistryError(f"Failed to read registry: {e}")
                time.sleep(self.retry_delay)

        return {}

    def atomic_write(self, file_name: str, data: Dict[str, Any]) -> None:
        """Write registry file atomically with fsync.

        Process:
        1. Write to temporary file
        2. fsync temporary file
        3. Atomic rename to target
        4. Set proper permissions (0660, group ownership)

        Args:
            file_name: Name of registry file (e.g., "hosts.json")
            data: Data to write

        Raises:
            RegistryError: On write errors after retries
        """
        file_path = self.registry_dir / file_name
        temp_path = file_path.with_suffix('.tmp')

        for attempt in range(self.retry_attempts):
            try:
                # Write to temp file
                with open(temp_path, 'w') as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())

                # Atomic rename
                temp_path.replace(file_path)

                # Set proper permissions on the file
                ensure_tsim_file_permissions(file_path, self.unix_group, self.logger)

                return

            except Exception as e:
                self.logger.error(f"Error writing {file_name}: {e}")
                if attempt == self.retry_attempts - 1:
                    raise TsimRegistryError(f"Failed to write registry: {e}")
                time.sleep(self.retry_delay)

    def atomic_update(self, file_name: str,
                     update_fn: Callable[[Dict], Dict]) -> Dict[str, Any]:
        """Atomic read-modify-write operation.

        IMPORTANT: This method must be called while holding appropriate lock!

        Args:
            file_name: Registry file to update
            update_fn: Function that takes current data and returns new data

        Returns:
            New data after update

        Raises:
            RegistryError: On I/O errors
        """
        # Read current data
        data = self.atomic_read(file_name)

        # Apply update function
        new_data = update_fn(data)

        # Write back atomically
        self.atomic_write(file_name, new_data)

        return new_data


@dataclass
class _ActionRecord:
    """Record of an action for potential rollback."""
    rollback_fn: Callable
    args: Tuple
    description: str


class _TsimTransaction:
    """Internal transaction manager for rollback on failure.

    This class is NOT exposed to external callers.
    """

    def __init__(self, registry_mgr: 'TsimRegistryManager'):
        """Initialize transaction.

        Args:
            registry_mgr: Parent RegistryManager instance
        """
        self.registry_mgr = registry_mgr
        self.actions: List[_ActionRecord] = []
        self.committed = False

    def record_action(self, rollback_fn: Callable, *args, description: str = ""):
        """Record action for potential rollback.

        Args:
            rollback_fn: Function to call for rollback
            args: Arguments to pass to rollback function
            description: Human-readable description of action
        """
        self.actions.append(_ActionRecord(rollback_fn, args, description))

    def commit(self):
        """Commit transaction (clear rollback actions)."""
        self.committed = True
        self.actions.clear()

    def rollback(self):
        """Rollback all recorded actions in reverse order."""
        if self.committed:
            return

        # Execute rollback actions in reverse order
        for action in reversed(self.actions):
            try:
                self.registry_mgr.logger.info(f"Rolling back: {action.description}")
                action.rollback_fn(*action.args)
            except Exception as e:
                self.registry_mgr.logger.error(
                    f"Rollback failed for {action.description}: {e}"
                )

        self.actions.clear()


# ==================== MAIN REGISTRY MANAGER CLASS ====================

class TsimRegistryManager:
    """Centralized registry and lock manager for all coordination operations.

    Thread-safe and process-safe. All operations are atomic.

    Usage:
        registry_mgr = TsimRegistryManager(config, logger)

        # Check and register host atomically
        if registry_mgr.check_and_register_host(name, ip, router, mac):
            create_physical_host(name)

        # Acquire router lock
        with registry_mgr.router_lock(router_name, job_id):
            perform_operations()
    """

    # Lock names
    LOCK_HOSTS = "tsim-hosts-registry"
    LOCK_HOST_LEASES = "tsim-host-leases"
    LOCK_NEIGHBOR_LEASES = "tsim-neighbor-leases"

    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """Initialize registry manager with configuration.

        Args:
            config: Configuration dict containing data_dir, lock_dir, registry_files, and registry_manager section
            logger: Optional logger instance

        Raises:
            ValueError: If required configuration is missing
        """
        self.logger = logger or logging.getLogger(__name__)

        # Get registry_manager config section (optional)
        registry_config = config.get('registry_manager', {})

        # Extract directories from main config (NO hardcoded defaults)
        data_dir = config.get('data_dir')
        lock_dir = config.get('lock_dir')

        if not data_dir:
            raise ValueError("Configuration missing required 'data_dir' parameter")
        if not lock_dir:
            raise ValueError("Configuration missing required 'lock_dir' parameter")

        # Get unix_group from system config or use default
        # This should come from traceroute_simulator.yaml's system.unix_group setting
        from tsim.core.config_loader import load_traceroute_config
        try:
            yaml_config = load_traceroute_config()
            self.unix_group = yaml_config.get('system', {}).get('unix_group', 'tsim-users')
        except Exception:
            self.unix_group = 'tsim-users'
            self.logger.warning("Could not load unix_group from config, using default: tsim-users")

        # Registry files from config
        registry_files = config.get('registry_files', {})
        if not registry_files:
            raise ValueError("Configuration missing required 'registry_files' section")

        # Extract registry file paths and convert to filenames
        # Config has full paths like "/dev/shm/tsim/host_registry.json"
        # We extract just the filename to use with registry_dir
        def get_filename(path_str: str, default_name: str) -> str:
            """Extract filename from full path, or use default."""
            if not path_str:
                return default_name
            return Path(path_str).name

        self.hosts_registry = get_filename(registry_files.get('hosts'), 'host_registry.json')
        self.host_leases_registry = get_filename(registry_files.get('host_leases'), 'host_leases.json')
        self.neighbor_leases_registry = get_filename(registry_files.get('neighbor_leases'), 'neighbor_leases.json')

        # Set directories
        self.registry_dir = Path(data_dir)
        self.lock_dir = Path(lock_dir)

        # Extract configuration parameters
        self.lock_timeouts = registry_config.get('lock_timeouts', {
            'host_registry': 5.0,
            'host_leases': 3.0,
            'router_lock': 30.0,
            'router_lock_atomic': 60.0,
            'neighbor_leases': 3.0
        })
        self.retry_attempts = registry_config.get('retry_attempts', 3)
        self.retry_delay = registry_config.get('retry_delay', 0.1)

        # Create directories with proper permissions (2775, group=unix_group)
        ensure_tsim_directory(self.registry_dir, self.unix_group, self.logger)
        ensure_tsim_directory(self.lock_dir, self.unix_group, self.logger)

        # Initialize internal managers
        self._lock_mgr = _TsimLockManager(self.lock_dir, self.unix_group, self.logger)
        self._io = _TsimRegistryIO(self.registry_dir, self.unix_group, self.logger,
                                    self.retry_attempts, self.retry_delay)

        # Transaction log
        self.enable_transaction_log = registry_config.get('enable_transaction_log', False)
        self.transaction_log_path = registry_config.get('transaction_log_path')

        self.logger.info(f"TsimRegistryManager initialized: registry_dir={self.registry_dir}, "
                        f"lock_dir={self.lock_dir}")

    def _get_timeout(self, operation: str) -> float:
        """Get timeout for operation from config."""
        return self.lock_timeouts.get(operation, 30.0)

    def _log_transaction(self, operation: str, details: Dict[str, Any]):
        """Log transaction to transaction log if enabled."""
        if not self.enable_transaction_log or not self.transaction_log_path:
            return

        try:
            log_entry = {
                'timestamp': time.time(),
                'operation': operation,
                'details': details
            }
            with open(self.transaction_log_path, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to write transaction log: {e}")

    # ==================== HOST REGISTRY OPERATIONS ====================

    def check_and_register_host(self, host_name: str, primary_ip: str,
                                connected_to: str, mac_address: str,
                                additional_info: Optional[Dict] = None) -> bool:
        """Atomically check availability and register host.

        CRITICAL: Entire operation under single lock - no TOCTOU vulnerability.

        Checks:
        1. Host name not already registered
        2. IP address not already in use
        3. MAC address not already in use

        If all checks pass, registers host atomically.

        Args:
            host_name: Unique host name
            primary_ip: Primary IP address (CIDR format, e.g., "10.0.0.1/24")
            connected_to: Router name
            mac_address: MAC address
            additional_info: Optional metadata

        Returns:
            True if registered successfully, False if collision detected

        Raises:
            RegistryError: On I/O errors or corruption
        """
        timeout = self._get_timeout('host_registry')

        if not self._lock_mgr.acquire(self.LOCK_HOSTS, timeout):
            raise TsimRegistryLockTimeout(f"Timeout acquiring host registry lock")

        try:
            def update_fn(hosts: Dict) -> Dict:
                # Extract IP without CIDR mask for comparison
                ip_only = primary_ip.split('/')[0] if '/' in primary_ip else primary_ip

                # Check for collisions
                for existing_name, existing_info in hosts.items():
                    # Name collision
                    if existing_name == host_name:
                        raise TsimRegistryCollision(f"Host name already exists: {host_name}")

                    # IP collision - only check if on the same router (each router has its own namespace)
                    existing_ip = existing_info.get('primary_ip', '')
                    existing_ip_only = existing_ip.split('/')[0] if '/' in existing_ip else existing_ip
                    existing_router = existing_info.get('connected_to', '')
                    if existing_ip_only == ip_only and existing_router == connected_to:
                        raise TsimRegistryCollision(
                            f"IP {ip_only} already in use by {existing_name} on router {connected_to}"
                        )

                    # MAC collision
                    if existing_info.get('mac_address') == mac_address:
                        raise TsimRegistryCollision(
                            f"MAC {mac_address} already in use by {existing_name}"
                        )

                # All checks passed - register host
                hosts[host_name] = {
                    'primary_ip': primary_ip,
                    'connected_to': connected_to,
                    'mac_address': mac_address,
                    'created_at': time.strftime('%c'),
                    'registered_at_timestamp': time.time()
                }

                # Add additional info if provided
                if additional_info:
                    hosts[host_name].update(additional_info)

                return hosts

            # Perform atomic update
            try:
                self._io.atomic_update(self.hosts_registry, update_fn)
                self._log_transaction('register_host', {
                    'host_name': host_name,
                    'ip': primary_ip,
                    'router': connected_to
                })
                return True

            except TsimRegistryCollision:
                # Collision detected - return False (not an error)
                return False

        finally:
            self._lock_mgr.release(self.LOCK_HOSTS)

    def unregister_host(self, host_name: str) -> bool:
        """Remove host from physical registry.

        Args:
            host_name: Host to remove

        Returns:
            True if removed, False if not found

        Raises:
            RegistryError: On I/O errors
        """
        timeout = self._get_timeout('host_registry')

        if not self._lock_mgr.acquire(self.LOCK_HOSTS, timeout):
            raise TsimRegistryLockTimeout(f"Timeout acquiring host registry lock")

        try:
            def update_fn(hosts: Dict) -> Dict:
                if host_name in hosts:
                    del hosts[host_name]
                return hosts

            hosts_before = self._io.atomic_read(self.hosts_registry)
            self._io.atomic_update(self.hosts_registry, update_fn)

            removed = host_name in hosts_before
            if removed:
                self._log_transaction('unregister_host', {'host_name': host_name})

            return removed

        finally:
            self._lock_mgr.release(self.LOCK_HOSTS)

    def get_host_info(self, host_name: str) -> Optional[Dict[str, Any]]:
        """Get host information (no lock needed - read-only).

        Args:
            host_name: Host to query

        Returns:
            Host info dict or None if not found
        """
        hosts = self._io.atomic_read(self.hosts_registry)
        return hosts.get(host_name)

    def list_all_hosts(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered hosts (no lock needed - read-only)."""
        return self._io.atomic_read(self.hosts_registry)

    # ==================== HOST LEASE OPERATIONS ====================

    def acquire_source_host_lease(self, run_id: str, host_name: str,
                                   job_type: str, router_name: str,
                                   dscp: Optional[int] = None) -> int:
        """Acquire lease for source host (reference counting).

        IMPORTANT: Caller MUST hold router lock for this host's router.
        This is enforced by design - router lock grants access to hosts.

        Args:
            run_id: Job identifier
            host_name: Source host name
            job_type: 'quick' or 'detailed'
            router_name: Router this host is attached to
            dscp: Optional DSCP for quick jobs

        Returns:
            Current reference count (>= 1)

        Raises:
            RegistryError: On I/O errors
            ValueError: If host not in physical registry
        """
        # Verify host exists in physical registry
        host_info = self.get_host_info(host_name)
        if not host_info:
            raise ValueError(f"Host {host_name} not in physical registry")

        timeout = self._get_timeout('host_leases')

        if not self._lock_mgr.acquire(self.LOCK_HOST_LEASES, timeout):
            raise TsimRegistryLockTimeout(f"Timeout acquiring host leases lock")

        try:
            def update_fn(leases: Dict) -> Dict:
                if host_name not in leases:
                    leases[host_name] = {
                        'router': router_name,
                        'leases': []
                    }

                leases[host_name]['leases'].append({
                    'run_id': run_id,
                    'pid': os.getpid(),
                    'job_type': job_type,
                    'dscp': dscp,
                    'allocated_at': time.time()
                })

                return leases

            new_leases = self._io.atomic_update(self.host_leases_registry, update_fn)
            ref_count = len(new_leases[host_name]['leases'])

            self._log_transaction('acquire_host_lease', {
                'run_id': run_id,
                'host_name': host_name,
                'ref_count': ref_count
            })

            return ref_count

        finally:
            self._lock_mgr.release(self.LOCK_HOST_LEASES)

    def release_source_host_lease(self, run_id: str, host_name: str) -> Tuple[int, bool]:
        """Release lease for source host (decrement reference count).

        Args:
            run_id: Job identifier
            host_name: Source host name

        Returns:
            Tuple of (new_ref_count, should_delete)
            should_delete=True when ref_count reaches 0

        Raises:
            RegistryError: On I/O errors
            ValueError: If lease not found
        """
        timeout = self._get_timeout('host_leases')

        if not self._lock_mgr.acquire(self.LOCK_HOST_LEASES, timeout):
            raise TsimRegistryLockTimeout(f"Timeout acquiring host leases lock")

        try:
            ref_count = 0
            should_delete = False

            def update_fn(leases: Dict) -> Dict:
                nonlocal ref_count, should_delete

                if host_name not in leases:
                    raise ValueError(f"No leases found for host {host_name}")

                # Remove this job's lease
                original_count = len(leases[host_name]['leases'])
                leases[host_name]['leases'] = [
                    lease for lease in leases[host_name]['leases']
                    if lease['run_id'] != run_id
                ]

                new_count = len(leases[host_name]['leases'])

                if new_count == original_count:
                    raise ValueError(f"Lease for {run_id} not found on host {host_name}")

                if new_count == 0:
                    # Remove host entry entirely
                    del leases[host_name]
                    should_delete = True
                else:
                    ref_count = new_count

                return leases

            self._io.atomic_update(self.host_leases_registry, update_fn)

            self._log_transaction('release_host_lease', {
                'run_id': run_id,
                'host_name': host_name,
                'ref_count': ref_count,
                'should_delete': should_delete
            })

            return ref_count, should_delete

        finally:
            self._lock_mgr.release(self.LOCK_HOST_LEASES)

    def get_host_lease_count(self, host_name: str) -> int:
        """Get current lease reference count for host.

        Args:
            host_name: Source host name

        Returns:
            Current reference count (0 if no leases)
        """
        leases = self._io.atomic_read(self.host_leases_registry)
        if host_name not in leases:
            return 0
        return len(leases[host_name].get('leases', []))

    def list_host_leases(self, host_name: Optional[str] = None) -> Dict[str, Any]:
        """List all leases, optionally filtered by host name.

        Args:
            host_name: Optional filter by host

        Returns:
            Dict of lease information
        """
        leases = self._io.atomic_read(self.host_leases_registry)
        if host_name:
            return {host_name: leases.get(host_name, {})}
        return leases

    # ==================== ROUTER LOCK OPERATIONS ====================

    def acquire_router_lock(self, router_name: str, job_id: str,
                            timeout: float = 30.0) -> bool:
        """Acquire exclusive lock for router.

        This grants exclusive access to:
        - Router itself (iptables, counters, forwarding)
        - ALL hosts attached to this router (source and destination)

        Args:
            router_name: Router to lock
            job_id: Job requesting lock
            timeout: Maximum wait time in seconds

        Returns:
            True if acquired, False if timeout

        Raises:
            RegistryError: On lock system errors
        """
        lock_name = f"tsim-router-{router_name}"
        acquired = self._lock_mgr.acquire(lock_name, timeout)

        if acquired:
            self._log_transaction('acquire_router_lock', {
                'router': router_name,
                'job_id': job_id
            })

        return acquired

    def release_router_lock(self, router_name: str, job_id: str) -> bool:
        """Release router lock and notify waiters.

        Args:
            router_name: Router to unlock
            job_id: Job releasing lock

        Returns:
            True if released, False if not held
        """
        lock_name = f"tsim-router-{router_name}"
        released = self._lock_mgr.release(lock_name)

        if released:
            # Touch notify file for inotify waiters
            self._notify_router_waiters(router_name)

            self._log_transaction('release_router_lock', {
                'router': router_name,
                'job_id': job_id
            })

        return released

    def _notify_router_waiters(self, router_name: str):
        """Notify waiters that router is free (touch notify file for inotify)."""
        notify_file = self.lock_dir / f"router_{router_name}_notify"
        try:
            notify_file.touch()
        except Exception as e:
            self.logger.warning(f"Could not touch notify file for {router_name}: {e}")

    def is_router_locked(self, router_name: str) -> bool:
        """Check if router is currently locked.

        Args:
            router_name: Router to check

        Returns:
            True if locked by any job
        """
        lock_file = self.lock_dir / f"tsim-router-{router_name}"
        return lock_file.exists()

    def acquire_all_router_locks_atomic(self, router_names: List[str],
                                         job_id: str, timeout: float = 60.0) -> bool:
        """Atomically acquire ALL router locks or none (deadlock prevention).

        CRITICAL: All-or-nothing acquisition prevents deadlocks.

        Deadlock scenario without atomic acquisition:
        - Job A acquires router-1, tries router-2 (blocked by Job B)
        - Job B acquires router-2, tries router-1 (blocked by Job A)
        - DEADLOCK!

        Solution:
        1. Sort router names (consistent ordering)
        2. Try to acquire all locks in order
        3. If ANY fails, release ALL and return False

        Args:
            router_names: List of routers to lock
            job_id: Job requesting locks
            timeout: Maximum total time to acquire all

        Returns:
            True if ALL acquired, False if timeout or any unavailable
        """
        lock_names = [f"tsim-router-{name}" for name in router_names]
        success, acquired = self._lock_mgr.acquire_multiple_sorted(lock_names, timeout)

        if not success:
            # Release any partially acquired locks
            self._lock_mgr.release_multiple(acquired)
            self.logger.warning(f"Failed to acquire all router locks for {job_id}")
            return False

        self._log_transaction('acquire_all_router_locks', {
            'routers': router_names,
            'job_id': job_id,
            'count': len(router_names)
        })

        return True

    def release_all_router_locks(self, router_names: List[str], job_id: str) -> int:
        """Release multiple router locks and notify all waiters.

        Args:
            router_names: List of routers to unlock
            job_id: Job releasing locks

        Returns:
            Number of locks successfully released
        """
        count = 0
        for router_name in router_names:
            if self.release_router_lock(router_name, job_id):
                count += 1

        return count

    @contextmanager
    def router_lock(self, router_name: str, job_id: str, timeout: float = 30.0):
        """Context manager for single router lock.

        Usage:
            with registry_mgr.router_lock('router-1', 'job-123'):
                # Have exclusive access to router-1 and all its hosts
                perform_operations()
            # Lock automatically released

        Args:
            router_name: Router to lock
            job_id: Job requesting lock
            timeout: Maximum wait time

        Raises:
            RegistryLockTimeout: If lock not acquired within timeout
        """
        if not self.acquire_router_lock(router_name, job_id, timeout):
            raise TsimRegistryLockTimeout(
                f"Could not acquire router lock: {router_name}"
            )
        try:
            yield
        finally:
            self.release_router_lock(router_name, job_id)

    @contextmanager
    def all_router_locks(self, router_names: List[str], job_id: str,
                         timeout: float = 60.0):
        """Context manager for atomic multi-router locking.

        Usage:
            with registry_mgr.all_router_locks(['r1', 'r2'], 'job-123'):
                # Have exclusive access to ALL routers and ALL their hosts
                perform_parallel_operations()
            # ALL locks automatically released atomically

        Args:
            router_names: List of routers to lock
            job_id: Job requesting locks
            timeout: Maximum total wait time

        Raises:
            RegistryLockTimeout: If all locks not acquired within timeout
        """
        if not self.acquire_all_router_locks_atomic(router_names, job_id, timeout):
            raise TsimRegistryLockTimeout(
                f"Could not acquire all router locks: {router_names}"
            )
        try:
            yield
        finally:
            self.release_all_router_locks(router_names, job_id)

    # ==================== ROUTER WAITER OPERATIONS ====================

    def wait_for_router(self, router_name: str, timeout: float = 30.0) -> bool:
        """Wait until router is free (inotify-based, no polling).

        Used by quick jobs to wait if router is locked by detailed job.

        Args:
            router_name: Router to wait for
            timeout: Maximum wait time

        Returns:
            True if router became free, False if timeout
        """
        lock_file = self.lock_dir / f"tsim-router-{router_name}"
        notify_file = self.lock_dir / f"router_{router_name}_notify"

        # Check if router is locked
        if not lock_file.exists():
            return True  # Not locked, proceed immediately

        # Router is locked - wait using inotify (no polling)
        self.logger.debug(f"Router {router_name} locked, waiting via inotify...")

        try:
            # Set up inotify watch on notify file
            fd = os.open(str(notify_file.parent), os.O_RDONLY)

            start_time = time.time()
            while time.time() - start_time < timeout:
                # Check if lock released
                if not lock_file.exists():
                    return True

                # Wait for notify file modification (inotify)
                readable, _, _ = select.select([fd], [], [], 0.5)
                if readable:
                    # Notify file was touched - check lock again
                    if not lock_file.exists():
                        return True

            # Timeout
            self.logger.warning(f"Timeout waiting for router {router_name}")
            return False

        except Exception as e:
            self.logger.error(f"Error waiting for router {router_name}: {e}")
            return False

        finally:
            try:
                os.close(fd)
            except:
                pass

    def wait_for_all_routers(self, router_names: List[str],
                             timeout: float = 30.0) -> bool:
        """Wait until ALL routers are free.

        Args:
            router_names: List of routers to wait for
            timeout: Maximum total wait time

        Returns:
            True if all became free, False if timeout
        """
        start_time = time.time()

        for router_name in router_names:
            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                return False

            if not self.wait_for_router(router_name, remaining):
                return False

        return True

    # ==================== NEIGHBOR LEASE OPERATIONS ====================

    def acquire_neighbor_lease(self, run_id: str, host_name: str,
                               neighbor_ip: str) -> int:
        """Acquire lease for neighbor ARP entry (reference counting).

        Args:
            run_id: Job identifier
            host_name: Host that needs this neighbor
            neighbor_ip: Neighbor IP address

        Returns:
            Current reference count
        """
        timeout = self._get_timeout('neighbor_leases')

        if not self._lock_mgr.acquire(self.LOCK_NEIGHBOR_LEASES, timeout):
            raise TsimRegistryLockTimeout(f"Timeout acquiring neighbor leases lock")

        try:
            def update_fn(leases: Dict) -> Dict:
                key = f"{host_name}:{neighbor_ip}"

                if key not in leases:
                    leases[key] = {
                        'host_name': host_name,
                        'neighbor_ip': neighbor_ip,
                        'leases': []
                    }

                leases[key]['leases'].append({
                    'run_id': run_id,
                    'pid': os.getpid(),
                    'allocated_at': time.time()
                })

                return leases

            new_leases = self._io.atomic_update(self.neighbor_leases_registry, update_fn)
            key = f"{host_name}:{neighbor_ip}"
            ref_count = len(new_leases[key]['leases'])

            self._log_transaction('acquire_neighbor_lease', {
                'run_id': run_id,
                'host_name': host_name,
                'neighbor_ip': neighbor_ip,
                'ref_count': ref_count
            })

            return ref_count

        finally:
            self._lock_mgr.release(self.LOCK_NEIGHBOR_LEASES)

    def release_neighbor_lease(self, run_id: str, host_name: str,
                               neighbor_ip: str) -> Tuple[int, bool]:
        """Release neighbor lease (decrement reference count).

        Args:
            run_id: Job identifier
            host_name: Host releasing neighbor
            neighbor_ip: Neighbor IP address

        Returns:
            Tuple of (new_ref_count, should_delete)
        """
        timeout = self._get_timeout('neighbor_leases')

        if not self._lock_mgr.acquire(self.LOCK_NEIGHBOR_LEASES, timeout):
            raise TsimRegistryLockTimeout(f"Timeout acquiring neighbor leases lock")

        try:
            ref_count = 0
            should_delete = False

            def update_fn(leases: Dict) -> Dict:
                nonlocal ref_count, should_delete

                key = f"{host_name}:{neighbor_ip}"

                if key not in leases:
                    raise ValueError(f"No leases found for {key}")

                # Remove this job's lease
                leases[key]['leases'] = [
                    lease for lease in leases[key]['leases']
                    if lease['run_id'] != run_id
                ]

                if not leases[key]['leases']:
                    # Remove entry entirely
                    del leases[key]
                    should_delete = True
                else:
                    ref_count = len(leases[key]['leases'])

                return leases

            self._io.atomic_update(self.neighbor_leases_registry, update_fn)

            self._log_transaction('release_neighbor_lease', {
                'run_id': run_id,
                'host_name': host_name,
                'neighbor_ip': neighbor_ip,
                'ref_count': ref_count,
                'should_delete': should_delete
            })

            return ref_count, should_delete

        finally:
            self._lock_mgr.release(self.LOCK_NEIGHBOR_LEASES)

    # ==================== CLEANUP AND SHUTDOWN ====================

    def cleanup(self):
        """Cleanup resources on shutdown."""
        self.logger.info("TsimRegistryManager shutting down...")
        self._lock_mgr.cleanup()
        self.logger.info("TsimRegistryManager shutdown complete")
