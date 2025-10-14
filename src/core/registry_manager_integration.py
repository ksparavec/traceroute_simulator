#!/usr/bin/env -S python3 -B -u
"""
Integration helper for TsimRegistryManager.

This module provides helper functions and examples for integrating
TsimRegistryManager with existing services.

Usage Examples:
    # Initialize from config
    registry_mgr = init_registry_manager_from_config(config_path, logger)

    # Use in host creation workflow
    if registry_mgr.check_and_register_host(name, ip, router, mac):
        # Physical host creation here
        create_physical_host(name, ip, router)

        # Acquire lease after physical creation
        ref_count = registry_mgr.acquire_source_host_lease(
            run_id=job_id,
            host_name=name,
            job_type='quick',
            router_name=router,
            dscp=32
        )
    else:
        # Host already exists - just acquire lease
        ref_count = registry_mgr.acquire_source_host_lease(...)

    # Release lease and delete if needed
    ref_count, should_delete = registry_mgr.release_source_host_lease(
        run_id=job_id,
        host_name=name
    )
    if should_delete:
        delete_physical_host(name)
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from tsim.core.registry_manager import TsimRegistryManager
from tsim.core.config_loader import load_traceroute_config


def init_registry_manager_from_config(
    config_path: Optional[str] = None,
    logger: Optional[logging.Logger] = None
) -> TsimRegistryManager:
    """Initialize TsimRegistryManager from configuration file.

    Args:
        config_path: Path to config.json (optional, uses default if not provided)
        logger: Optional logger instance

    Returns:
        Initialized TsimRegistryManager instance

    Raises:
        FileNotFoundError: If config file not found
        ValueError: If configuration is invalid
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    # Load configuration
    if config_path:
        with open(config_path, 'r') as f:
            config = json.load(f)
    else:
        # Use default config from WSGI
        default_config_path = Path(__file__).parent.parent.parent / 'wsgi' / 'config.json'
        if default_config_path.exists():
            with open(default_config_path, 'r') as f:
                config = json.load(f)
        else:
            # Fallback to minimal config
            config = {
                'data_dir': '/dev/shm/tsim',
                'lock_dir': '/dev/shm/tsim/locks'
            }

    # Initialize registry manager
    registry_mgr = TsimRegistryManager(config, logger)
    logger.info("TsimRegistryManager initialized successfully")

    return registry_mgr


def get_registry_manager_singleton(
    config: Optional[Dict[str, Any]] = None,
    logger: Optional[logging.Logger] = None
) -> TsimRegistryManager:
    """Get singleton instance of TsimRegistryManager.

    This ensures only one instance is created per process.

    Args:
        config: Configuration dict (only used on first call)
        logger: Logger instance (only used on first call)

    Returns:
        TsimRegistryManager singleton instance
    """
    if not hasattr(get_registry_manager_singleton, '_instance'):
        if config is None:
            # Load default config
            config = {'data_dir': '/dev/shm/tsim', 'lock_dir': '/dev/shm/tsim/locks'}
        if logger is None:
            logger = logging.getLogger(__name__)

        get_registry_manager_singleton._instance = TsimRegistryManager(config, logger)

    return get_registry_manager_singleton._instance


class RegistryManagerIntegrationExample:
    """
    Example class showing how to integrate TsimRegistryManager
    with existing host namespace management code.
    """

    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        """Initialize with configuration."""
        self.config = config
        self.logger = logger

        # Initialize registry manager
        self.registry_mgr = TsimRegistryManager(config, logger)

        # Initialize other components (HostNamespaceManager, etc.)
        # ...

    def create_source_host_with_lease(
        self,
        run_id: str,
        host_name: str,
        primary_ip: str,
        router_name: str,
        mac_address: str,
        job_type: str,
        dscp: Optional[int] = None
    ) -> tuple:
        """
        Create source host with proper coordination.

        This is the recommended pattern for creating source hosts.

        Returns:
            Tuple of (success: bool, ref_count: int, created_physical: bool)
        """
        created_physical = False

        try:
            # Step 1: Atomic check-and-register
            # This eliminates TOCTOU vulnerability
            registered = self.registry_mgr.check_and_register_host(
                host_name=host_name,
                primary_ip=primary_ip,
                connected_to=router_name,
                mac_address=mac_address
            )

            if registered:
                # Host was newly registered - create physical host
                self.logger.info(f"Creating physical host: {host_name}")
                self._create_physical_host(host_name, primary_ip, router_name, mac_address)
                created_physical = True
            else:
                # Host already exists physically - just acquire lease
                self.logger.info(f"Host {host_name} already exists, acquiring lease")

            # Step 2: Acquire lease (always done, whether new or existing host)
            ref_count = self.registry_mgr.acquire_source_host_lease(
                run_id=run_id,
                host_name=host_name,
                job_type=job_type,
                router_name=router_name,
                dscp=dscp
            )

            self.logger.info(
                f"Host {host_name} lease acquired: ref_count={ref_count}, "
                f"created_physical={created_physical}"
            )

            return True, ref_count, created_physical

        except Exception as e:
            self.logger.error(f"Failed to create host {host_name}: {e}")

            # Rollback if we created physical host
            if created_physical:
                try:
                    self._delete_physical_host(host_name)
                    self.registry_mgr.unregister_host(host_name)
                except Exception as cleanup_err:
                    self.logger.error(f"Cleanup failed: {cleanup_err}")

            return False, 0, False

    def release_source_host_with_cleanup(
        self,
        run_id: str,
        host_name: str
    ) -> tuple:
        """
        Release source host lease and cleanup if needed.

        Returns:
            Tuple of (success: bool, deleted_physical: bool)
        """
        try:
            # Release lease
            ref_count, should_delete = self.registry_mgr.release_source_host_lease(
                run_id=run_id,
                host_name=host_name
            )

            self.logger.info(
                f"Released lease for {host_name}: ref_count={ref_count}, "
                f"should_delete={should_delete}"
            )

            deleted_physical = False
            if should_delete:
                # No more leases - safe to delete physical host
                self.logger.info(f"Deleting physical host: {host_name}")
                self._delete_physical_host(host_name)
                self.registry_mgr.unregister_host(host_name)
                deleted_physical = True

            return True, deleted_physical

        except Exception as e:
            self.logger.error(f"Failed to release host {host_name}: {e}")
            return False, False

    def _create_physical_host(self, host_name: str, primary_ip: str,
                             router_name: str, mac_address: str):
        """Create physical host namespace (placeholder)."""
        # This would call actual HostNamespaceManager methods
        pass

    def _delete_physical_host(self, host_name: str):
        """Delete physical host namespace (placeholder)."""
        # This would call actual HostNamespaceManager methods
        pass


class QuickJobIntegrationExample:
    """
    Example showing how quick jobs should use TsimRegistryManager.
    """

    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.registry_mgr = TsimRegistryManager(config, logger)

    def run_quick_job(self, run_id: str, router_name: str, dscp: int):
        """
        Example quick job using registry manager.
        """
        source_hosts = []

        try:
            # Step 1: Wait for router to be free (if locked by detailed job)
            if not self.registry_mgr.wait_for_router(router_name, timeout=30.0):
                raise TimeoutError(f"Router {router_name} locked by detailed job")

            # Step 2: Create/acquire source hosts
            for i in range(2):
                host_name = f"qtest-{run_id}-{i}"
                ip = f"10.100.{i}.1/24"
                mac = f"aa:bb:cc:dd:ee:{i:02x}"

                # Check and register + acquire lease
                if self.registry_mgr.check_and_register_host(
                    host_name, ip, router_name, mac
                ):
                    # Create physical host
                    self._create_host(host_name, ip, router_name)

                # Acquire lease
                ref_count = self.registry_mgr.acquire_source_host_lease(
                    run_id=run_id,
                    host_name=host_name,
                    job_type='quick',
                    router_name=router_name,
                    dscp=dscp
                )
                source_hosts.append(host_name)

            # Step 3: Run tests (DSCP-isolated)
            self._run_tests(source_hosts, dscp)

        finally:
            # Step 4: Cleanup - release leases
            for host_name in source_hosts:
                try:
                    ref_count, should_delete = \
                        self.registry_mgr.release_source_host_lease(run_id, host_name)

                    if should_delete:
                        self._delete_host(host_name)
                        self.registry_mgr.unregister_host(host_name)

                except Exception as e:
                    self.logger.error(f"Cleanup failed for {host_name}: {e}")

    def _create_host(self, host_name, ip, router):
        """Placeholder for physical host creation."""
        pass

    def _delete_host(self, host_name):
        """Placeholder for physical host deletion."""
        pass

    def _run_tests(self, hosts, dscp):
        """Placeholder for running tests."""
        pass


class DetailedJobIntegrationExample:
    """
    Example showing how detailed jobs should use TsimRegistryManager.
    """

    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.registry_mgr = TsimRegistryManager(config, logger)

    def run_detailed_job(self, run_id: str, router_names: list):
        """
        Example detailed job using registry manager.
        """
        source_hosts = []

        try:
            # Step 1: Acquire ALL router locks atomically (deadlock prevention)
            with self.registry_mgr.all_router_locks(router_names, run_id, timeout=60.0):
                self.logger.info(f"Acquired all router locks for {run_id}")

                # Step 2: Create/acquire source hosts on ALL routers
                for router in router_names:
                    host_name = f"dtest-{run_id}-{router}"
                    ip = f"10.200.{len(source_hosts)}.1/24"
                    mac = f"bb:cc:dd:ee:ff:{len(source_hosts):02x}"

                    if self.registry_mgr.check_and_register_host(
                        host_name, ip, router, mac
                    ):
                        self._create_host(host_name, ip, router)

                    ref_count = self.registry_mgr.acquire_source_host_lease(
                        run_id=run_id,
                        host_name=host_name,
                        job_type='detailed',
                        router_name=router,
                        dscp=None
                    )
                    source_hosts.append(host_name)

                # Step 3: Create ephemeral destination hosts (no leases)
                dest_hosts = self._create_destination_hosts(router_names)

                # Step 4: Run measurements (exclusive access to all routers)
                self._run_measurements(source_hosts, dest_hosts)

                # Step 5: Cleanup destination hosts
                self._cleanup_destination_hosts(dest_hosts)

        finally:
            # Step 6: Release source host leases
            # Locks automatically released by context manager
            for host_name in source_hosts:
                try:
                    ref_count, should_delete = \
                        self.registry_mgr.release_source_host_lease(run_id, host_name)

                    if should_delete:
                        self._delete_host(host_name)
                        self.registry_mgr.unregister_host(host_name)

                except Exception as e:
                    self.logger.error(f"Cleanup failed for {host_name}: {e}")

    def _create_host(self, host_name, ip, router):
        """Placeholder."""
        pass

    def _delete_host(self, host_name):
        """Placeholder."""
        pass

    def _create_destination_hosts(self, routers):
        """Placeholder."""
        return []

    def _cleanup_destination_hosts(self, hosts):
        """Placeholder."""
        pass

    def _run_measurements(self, src_hosts, dst_hosts):
        """Placeholder."""
        pass


if __name__ == '__main__':
    """
    Example usage of registry manager integration helpers.
    """
    import logging

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Example 1: Initialize from config
    try:
        registry_mgr = init_registry_manager_from_config(logger=logger)
        logger.info("Registry manager initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize: {e}")

    # Example 2: Use singleton pattern
    registry_mgr = get_registry_manager_singleton()

    # Example 3: Test basic operations
    test_config = {
        'data_dir': '/tmp/test_registry',
        'lock_dir': '/tmp/test_registry/locks'
    }

    example = RegistryManagerIntegrationExample(test_config, logger)

    # Simulate host creation
    success, ref_count, created = example.create_source_host_with_lease(
        run_id='test-job-1',
        host_name='test-host-1',
        primary_ip='10.0.0.1/24',
        router_name='router-1',
        mac_address='aa:bb:cc:dd:ee:01',
        job_type='quick',
        dscp=32
    )

    logger.info(f"Host creation result: success={success}, ref_count={ref_count}, created={created}")

    # Simulate host release
    success, deleted = example.release_source_host_with_cleanup(
        run_id='test-job-1',
        host_name='test-host-1'
    )

    logger.info(f"Host release result: success={success}, deleted={deleted}")
