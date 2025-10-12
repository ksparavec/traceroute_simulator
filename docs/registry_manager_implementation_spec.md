# RegistryManager Implementation Specification

## Document Purpose

This document provides complete implementation details for `src/core/registry_manager.py`. Developers can use this specification to implement the centralized registry manager that eliminates scattered lock management and TOCTOU vulnerabilities.

## File Location

`src/core/registry_manager.py`

## Dependencies

```python
import json
import os
import time
import logging
import posix_ipc
import select
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
from contextlib import contextmanager
from dataclasses import dataclass
```

## Configuration Structure

The RegistryManager expects this configuration structure:

```python
{
    "registry_manager": {
        "enabled": true,
        "registry_dir": "/dev/shm/tsim",
        "lock_dir": "/dev/shm/tsim/locks",
        "lock_timeouts": {
            "host_registry": 5.0,
            "host_leases": 3.0,
            "router_lock": 30.0,
            "router_lock_atomic": 60.0,
            "neighbor_leases": 3.0
        },
        "retry_attempts": 3,
        "retry_delay": 0.1,
        "enable_transaction_log": true,
        "transaction_log_path": "/var/log/tsim/registry_transactions.log"
    }
}
```

## Exception Classes

```python
class RegistryError(Exception):
    """Base exception for registry operations."""
    pass


class RegistryLockTimeout(RegistryError):
    """Lock acquisition timeout."""
    pass


class RegistryCollision(RegistryError):
    """Resource collision detected (IP, name, MAC, etc.)."""
    pass


class RegistryCorruption(RegistryError):
    """Registry file corrupted or invalid."""
    pass


class RegistryNotFound(RegistryError):
    """Registry file or entry not found."""
    pass
```

## Lock Names and Ordering

To prevent deadlocks, locks MUST be acquired in this order:

```python
LOCK_ORDER = {
    'host_registry': 1,      # /tsim-hosts-registry
    'host_leases': 2,        # /tsim-host-leases
    'router_locks': 3,       # /tsim-router-{name} (multiple, sorted by name)
    'neighbor_leases': 4     # /tsim-neighbor-leases
}

# Lock names format:
# - Host registry: "tsim-hosts-registry"
# - Host leases: "tsim-host-leases"
# - Router lock: "tsim-router-{router_name}"
# - Neighbor leases: "tsim-neighbor-leases"
```

## Internal Classes

### _LockManager (Internal)

```python
class _LockManager:
    """Internal lock manager using posix_ipc semaphores.

    This class is NOT exposed to external callers.
    """

    def __init__(self, lock_dir: Path, logger: logging.Logger):
        """Initialize lock manager.

        Args:
            lock_dir: Directory for lock files
            logger: Logger instance
        """
        self.lock_dir = Path(lock_dir)
        self.logger = logger
        self.semaphores: Dict[str, posix_ipc.Semaphore] = {}
        self.lock_dir.mkdir(parents=True, exist_ok=True)

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
                try:
                    # Try to create with initial value 1
                    sem = posix_ipc.Semaphore(sem_name, flags=posix_ipc.O_CREAT,
                                             mode=0o600, initial_value=1)
                except posix_ipc.ExistentialError:
                    # Already exists, open it
                    sem = posix_ipc.Semaphore(sem_name)
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
            raise RegistryError(f"Lock acquisition failed: {e}")

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
```

### _RegistryIO (Internal)

```python
class _RegistryIO:
    """Internal registry I/O handler with atomic operations.

    This class is NOT exposed to external callers.
    """

    def __init__(self, registry_dir: Path, logger: logging.Logger,
                 retry_attempts: int = 3, retry_delay: float = 0.1):
        """Initialize registry I/O handler.

        Args:
            registry_dir: Directory containing registry files
            logger: Logger instance
            retry_attempts: Number of retry attempts on I/O errors
            retry_delay: Delay between retries in seconds
        """
        self.registry_dir = Path(registry_dir)
        self.logger = logger
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.registry_dir.mkdir(parents=True, exist_ok=True)

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
                    raise RegistryCorruption(f"Corrupted registry: {file_name}")
                time.sleep(self.retry_delay)

            except Exception as e:
                self.logger.error(f"Error reading {file_name}: {e}")
                if attempt == self.retry_attempts - 1:
                    raise RegistryError(f"Failed to read registry: {e}")
                time.sleep(self.retry_delay)

        return {}

    def atomic_write(self, file_name: str, data: Dict[str, Any]) -> None:
        """Write registry file atomically with fsync.

        Process:
        1. Write to temporary file
        2. fsync temporary file
        3. Atomic rename to target

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
                return

            except Exception as e:
                self.logger.error(f"Error writing {file_name}: {e}")
                if attempt == self.retry_attempts - 1:
                    raise RegistryError(f"Failed to write registry: {e}")
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
```

### _Transaction (Internal)

```python
@dataclass
class _ActionRecord:
    """Record of an action for potential rollback."""
    rollback_fn: Callable
    args: Tuple
    description: str


class _Transaction:
    """Internal transaction manager for rollback on failure.

    This class is NOT exposed to external callers.
    """

    def __init__(self, registry_mgr: 'RegistryManager'):
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
```

## Main RegistryManager Class

```python
class RegistryManager:
    """Centralized registry and lock manager for all coordination operations.

    Thread-safe and process-safe. All operations are atomic.

    Usage:
        registry_mgr = RegistryManager(config, logger)

        # Check and register host atomically
        if registry_mgr.check_and_register_host(name, ip, router, mac):
            create_physical_host(name)

        # Acquire router lock
        with registry_mgr.router_lock(router_name, job_id):
            perform_operations()
    """

    # Registry file names
    HOSTS_REGISTRY = "hosts.json"
    HOST_LEASES_REGISTRY = "host_leases.json"
    NEIGHBOR_LEASES_REGISTRY = "neighbor_leases.json"

    # Lock names
    LOCK_HOSTS = "tsim-hosts-registry"
    LOCK_HOST_LEASES = "tsim-host-leases"
    LOCK_NEIGHBOR_LEASES = "tsim-neighbor-leases"

    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """Initialize registry manager with configuration.

        Args:
            config: Configuration dict containing registry_manager section
            logger: Optional logger instance
        """
        self.config = config.get('registry_manager', {})
        self.logger = logger or logging.getLogger(__name__)

        # Extract configuration
        self.registry_dir = Path(self.config.get('registry_dir', '/dev/shm/tsim'))
        self.lock_dir = Path(self.config.get('lock_dir', '/dev/shm/tsim/locks'))
        self.lock_timeouts = self.config.get('lock_timeouts', {})
        self.retry_attempts = self.config.get('retry_attempts', 3)
        self.retry_delay = self.config.get('retry_delay', 0.1)

        # Create directories
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.lock_dir.mkdir(parents=True, exist_ok=True)

        # Initialize internal managers
        self._lock_mgr = _LockManager(self.lock_dir, self.logger)
        self._io = _RegistryIO(self.registry_dir, self.logger,
                               self.retry_attempts, self.retry_delay)

        # Transaction log
        self.enable_transaction_log = self.config.get('enable_transaction_log', False)
        self.transaction_log_path = self.config.get('transaction_log_path')

        self.logger.info(f"RegistryManager initialized: registry_dir={self.registry_dir}, "
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
            raise RegistryLockTimeout(f"Timeout acquiring host registry lock")

        try:
            def update_fn(hosts: Dict) -> Dict:
                # Extract IP without CIDR mask for comparison
                ip_only = primary_ip.split('/')[0] if '/' in primary_ip else primary_ip

                # Check for collisions
                for existing_name, existing_info in hosts.items():
                    # Name collision
                    if existing_name == host_name:
                        raise RegistryCollision(f"Host name already exists: {host_name}")

                    # IP collision
                    existing_ip = existing_info.get('primary_ip', '')
                    existing_ip_only = existing_ip.split('/')[0] if '/' in existing_ip else existing_ip
                    if existing_ip_only == ip_only:
                        raise RegistryCollision(
                            f"IP {ip_only} already in use by {existing_name}"
                        )

                    # MAC collision
                    if existing_info.get('mac_address') == mac_address:
                        raise RegistryCollision(
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
                self._io.atomic_update(self.HOSTS_REGISTRY, update_fn)
                self._log_transaction('register_host', {
                    'host_name': host_name,
                    'ip': primary_ip,
                    'router': connected_to
                })
                return True

            except RegistryCollision:
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
            raise RegistryLockTimeout(f"Timeout acquiring host registry lock")

        try:
            def update_fn(hosts: Dict) -> Dict:
                if host_name in hosts:
                    del hosts[host_name]
                return hosts

            hosts_before = self._io.atomic_read(self.HOSTS_REGISTRY)
            self._io.atomic_update(self.HOSTS_REGISTRY, update_fn)

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
        hosts = self._io.atomic_read(self.HOSTS_REGISTRY)
        return hosts.get(host_name)

    def list_all_hosts(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered hosts (no lock needed - read-only)."""
        return self._io.atomic_read(self.HOSTS_REGISTRY)

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
            raise RegistryLockTimeout(f"Timeout acquiring host leases lock")

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

            new_leases = self._io.atomic_update(self.HOST_LEASES_REGISTRY, update_fn)
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
            raise RegistryLockTimeout(f"Timeout acquiring host leases lock")

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

            self._io.atomic_update(self.HOST_LEASES_REGISTRY, update_fn)

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
        leases = self._io.atomic_read(self.HOST_LEASES_REGISTRY)
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
        leases = self._io.atomic_read(self.HOST_LEASES_REGISTRY)
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
        """Notify RouterWaiter instances that router is free (touch notify file)."""
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
            raise RegistryLockTimeout(
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
            raise RegistryLockTimeout(
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
            raise RegistryLockTimeout(f"Timeout acquiring neighbor leases lock")

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

            new_leases = self._io.atomic_update(self.NEIGHBOR_LEASES_REGISTRY, update_fn)
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
            raise RegistryLockTimeout(f"Timeout acquiring neighbor leases lock")

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

            self._io.atomic_update(self.NEIGHBOR_LEASES_REGISTRY, update_fn)

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
        self.logger.info("RegistryManager shutting down...")
        self._lock_mgr.cleanup()
        self.logger.info("RegistryManager shutdown complete")
```

## Testing Requirements

### Unit Tests

Create `tests/test_registry_manager.py` with:

1. **Test lock ordering enforcement**
2. **Test atomic check-and-register** (no TOCTOU)
3. **Test collision detection** (IP, name, MAC)
4. **Test reference counting** (host leases, neighbor leases)
5. **Test atomic multi-router lock acquisition**
6. **Test deadlock prevention**
7. **Test transaction rollback**
8. **Test concurrent access** (multiple threads)

### Integration Tests

Create `tests/integration/test_registry_manager_concurrent.py` with:

1. **Multiple processes competing for locks**
2. **Quick jobs waiting for detailed jobs**
3. **Detailed jobs acquiring multiple router locks**
4. **Reference counting with concurrent acquire/release**
5. **Lock timeout scenarios**

### Performance Tests

Create `tests/performance/test_registry_manager_perf.py` with:

1. **100+ concurrent jobs**
2. **Rapid lock acquire/release cycles**
3. **Large registry files (1000+ hosts)**
4. **Lock contention measurement**

## Usage Examples

### Example 1: Register Host

```python
registry_mgr = RegistryManager(config, logger)

# Atomic check and register (eliminates TOCTOU)
if registry_mgr.check_and_register_host(
    host_name="host-1",
    primary_ip="10.0.0.10/24",
    connected_to="router-1",
    mac_address="aa:bb:cc:dd:ee:ff"
):
    # Registration succeeded - create physical host
    create_physical_host("host-1")
else:
    # Collision detected - host/IP/MAC already exists
    logger.warning("Host registration failed - collision")
```

### Example 2: Quick Job with Router Wait

```python
registry_mgr = RegistryManager(config, logger)

# Wait for router to be free
for router in routers:
    if not registry_mgr.wait_for_router(router, timeout=30.0):
        raise TimeoutError(f"Router {router} locked, timeout")

# Router is free - acquire source host lease
ref_count = registry_mgr.acquire_source_host_lease(
    run_id=run_id,
    host_name="source-1",
    job_type="quick",
    router_name="router-1",
    dscp=32
)

try:
    # Perform quick analysis
    perform_quick_analysis()
finally:
    # Release lease
    ref_count, should_delete = registry_mgr.release_source_host_lease(
        run_id, "source-1"
    )
    if should_delete:
        delete_physical_host("source-1")
```

### Example 3: Detailed Job with Atomic Locking

```python
registry_mgr = RegistryManager(config, logger)

# Atomically acquire ALL router locks (deadlock prevention)
with registry_mgr.all_router_locks(routers, job_id, timeout=60.0):
    # Have exclusive access to ALL routers and ALL hosts

    # Acquire source host leases
    for host_name, router_name in hosts:
        registry_mgr.acquire_source_host_lease(
            run_id, host_name, "detailed", router_name
        )

    # Perform measurements
    perform_detailed_analysis()

    # Release leases
    for host_name, _ in hosts:
        ref_count, should_delete = registry_mgr.release_source_host_lease(
            run_id, host_name
        )
        if should_delete:
            delete_physical_host(host_name)

# ALL locks released automatically
```

## Migration Checklist

- [ ] Implement `RegistryManager` class in `src/core/registry_manager.py`
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Update `host_namespace_setup.py` to use RegistryManager
- [ ] Update `ksms_tester.py` to use RegistryManager
- [ ] Update `network_reachability_test_multi.py` to use RegistryManager
- [ ] Update `TsimSchedulerService` to use RegistryManager
- [ ] Deprecate `TsimLockManagerService`
- [ ] Deprecate standalone `RouterWaiter`
- [ ] Update configuration files
- [ ] Update documentation
- [ ] Run performance benchmarks
- [ ] Deploy to test environment
- [ ] Monitor for issues
- [ ] Deploy to production

## Notes

- All internal classes (`_LockManager`, `_RegistryIO`, `_Transaction`) are prefixed with underscore to indicate they are NOT part of the public API
- Services should ONLY use the public methods of `RegistryManager`
- Lock ordering is CRITICAL - never acquire locks out of order
- Always use context managers (`with` statements) for lock operations when possible
- Transaction log is optional but recommended for debugging
