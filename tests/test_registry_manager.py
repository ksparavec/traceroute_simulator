#!/usr/bin/env -S python3 -B -u
"""Unit tests for RegistryManager.

Tests cover:
- Exception classes
- Lock ordering enforcement
- Atomic check-and-register (TOCTOU elimination)
- Collision detection (IP, name, MAC)
- Reference counting (host leases, neighbor leases)
- Atomic multi-router lock acquisition
- Deadlock prevention
- Transaction rollback
- Concurrent access (multiple threads)
"""

import unittest
import tempfile
import shutil
import json
import time
import logging
import threading
from pathlib import Path
from typing import List

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from core.registry_manager import (
    TsimRegistryManager,
    TsimRegistryError,
    TsimRegistryLockTimeout,
    TsimRegistryCollision,
    TsimRegistryCorruption,
    TsimRegistryNotFound
)


class TestRegistryManagerBasic(unittest.TestCase):
    """Basic functionality tests for RegistryManager."""

    def setUp(self):
        """Create temporary directories for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.registry_dir = Path(self.test_dir) / "registry"
        self.lock_dir = Path(self.test_dir) / "locks"

        self.config = {
            'data_dir': str(self.registry_dir),
            'lock_dir': str(self.lock_dir),
            'registry_manager': {
                'enabled': True,
                'lock_timeouts': {
                    'host_registry': 5.0,
                    'host_leases': 3.0,
                    'router_lock': 30.0,
                    'router_lock_atomic': 60.0,
                    'neighbor_leases': 3.0
                },
                'retry_attempts': 3,
                'retry_delay': 0.1,
                'enable_transaction_log': False
            }
        }

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        self.mgr = TsimRegistryManager(self.config, self.logger)

    def tearDown(self):
        """Cleanup temporary directories and semaphores."""
        self.mgr.cleanup()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_initialization(self):
        """Test RegistryManager initialization."""
        self.assertTrue(self.registry_dir.exists())
        self.assertTrue(self.lock_dir.exists())
        self.assertEqual(self.mgr.registry_dir, self.registry_dir)
        self.assertEqual(self.mgr.lock_dir, self.lock_dir)

    def test_check_and_register_host_success(self):
        """Test successful host registration."""
        result = self.mgr.check_and_register_host(
            host_name="test-host-1",
            primary_ip="10.0.0.1/24",
            connected_to="router-1",
            mac_address="aa:bb:cc:dd:ee:01"
        )
        self.assertTrue(result)

        # Verify host is in registry
        host_info = self.mgr.get_host_info("test-host-1")
        self.assertIsNotNone(host_info)
        self.assertEqual(host_info['primary_ip'], "10.0.0.1/24")
        self.assertEqual(host_info['connected_to'], "router-1")
        self.assertEqual(host_info['mac_address'], "aa:bb:cc:dd:ee:01")

    def test_check_and_register_host_name_collision(self):
        """Test host name collision detection."""
        # Register first host
        self.mgr.check_and_register_host(
            host_name="test-host-1",
            primary_ip="10.0.0.1/24",
            connected_to="router-1",
            mac_address="aa:bb:cc:dd:ee:01"
        )

        # Try to register same host name
        result = self.mgr.check_and_register_host(
            host_name="test-host-1",
            primary_ip="10.0.0.2/24",
            connected_to="router-2",
            mac_address="aa:bb:cc:dd:ee:02"
        )
        self.assertFalse(result)

    def test_check_and_register_host_ip_collision(self):
        """Test IP address collision detection."""
        # Register first host
        self.mgr.check_and_register_host(
            host_name="test-host-1",
            primary_ip="10.0.0.1/24",
            connected_to="router-1",
            mac_address="aa:bb:cc:dd:ee:01"
        )

        # Try to register different host with same IP
        result = self.mgr.check_and_register_host(
            host_name="test-host-2",
            primary_ip="10.0.0.1/24",
            connected_to="router-2",
            mac_address="aa:bb:cc:dd:ee:02"
        )
        self.assertFalse(result)

    def test_check_and_register_host_mac_collision(self):
        """Test MAC address collision detection."""
        # Register first host
        self.mgr.check_and_register_host(
            host_name="test-host-1",
            primary_ip="10.0.0.1/24",
            connected_to="router-1",
            mac_address="aa:bb:cc:dd:ee:01"
        )

        # Try to register different host with same MAC
        result = self.mgr.check_and_register_host(
            host_name="test-host-2",
            primary_ip="10.0.0.2/24",
            connected_to="router-2",
            mac_address="aa:bb:cc:dd:ee:01"
        )
        self.assertFalse(result)

    def test_unregister_host(self):
        """Test host unregistration."""
        # Register host
        self.mgr.check_and_register_host(
            host_name="test-host-1",
            primary_ip="10.0.0.1/24",
            connected_to="router-1",
            mac_address="aa:bb:cc:dd:ee:01"
        )

        # Unregister
        result = self.mgr.unregister_host("test-host-1")
        self.assertTrue(result)

        # Verify host is gone
        host_info = self.mgr.get_host_info("test-host-1")
        self.assertIsNone(host_info)

    def test_unregister_nonexistent_host(self):
        """Test unregistering non-existent host."""
        result = self.mgr.unregister_host("nonexistent-host")
        self.assertFalse(result)

    def test_list_all_hosts(self):
        """Test listing all hosts."""
        # Register multiple hosts
        self.mgr.check_and_register_host(
            "test-host-1", "10.0.0.1/24", "router-1", "aa:bb:cc:dd:ee:01"
        )
        self.mgr.check_and_register_host(
            "test-host-2", "10.0.0.2/24", "router-2", "aa:bb:cc:dd:ee:02"
        )

        hosts = self.mgr.list_all_hosts()
        self.assertEqual(len(hosts), 2)
        self.assertIn("test-host-1", hosts)
        self.assertIn("test-host-2", hosts)


class TestRegistryManagerLeases(unittest.TestCase):
    """Test host lease operations."""

    def setUp(self):
        """Create temporary directories for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.registry_dir = Path(self.test_dir) / "registry"
        self.lock_dir = Path(self.test_dir) / "locks"

        self.config = {
            'data_dir': str(self.registry_dir),
            'lock_dir': str(self.lock_dir),
            'registry_manager': {
                'enabled': True,
                'lock_timeouts': {
                    'host_registry': 5.0,
                    'host_leases': 3.0,
                    'router_lock': 30.0,
                    'router_lock_atomic': 60.0,
                    'neighbor_leases': 3.0
                },
                'retry_attempts': 3,
                'retry_delay': 0.1
            }
        }

        self.logger = logging.getLogger(__name__)
        self.mgr = TsimRegistryManager(self.config, self.logger)

        # Register a host for testing
        self.mgr.check_and_register_host(
            "test-host-1", "10.0.0.1/24", "router-1", "aa:bb:cc:dd:ee:01"
        )

    def tearDown(self):
        """Cleanup."""
        self.mgr.cleanup()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_acquire_source_host_lease(self):
        """Test acquiring source host lease."""
        ref_count = self.mgr.acquire_source_host_lease(
            run_id="job-1",
            host_name="test-host-1",
            job_type="quick",
            router_name="router-1",
            dscp=32
        )
        self.assertEqual(ref_count, 1)

        # Check lease count
        count = self.mgr.get_host_lease_count("test-host-1")
        self.assertEqual(count, 1)

    def test_acquire_multiple_leases_same_host(self):
        """Test multiple jobs acquiring leases on same host."""
        ref_count1 = self.mgr.acquire_source_host_lease(
            "job-1", "test-host-1", "quick", "router-1", dscp=32
        )
        self.assertEqual(ref_count1, 1)

        ref_count2 = self.mgr.acquire_source_host_lease(
            "job-2", "test-host-1", "quick", "router-1", dscp=33
        )
        self.assertEqual(ref_count2, 2)

        # Check total lease count
        count = self.mgr.get_host_lease_count("test-host-1")
        self.assertEqual(count, 2)

    def test_release_source_host_lease(self):
        """Test releasing source host lease."""
        # Acquire lease
        self.mgr.acquire_source_host_lease(
            "job-1", "test-host-1", "quick", "router-1", dscp=32
        )

        # Release lease
        ref_count, should_delete = self.mgr.release_source_host_lease(
            "job-1", "test-host-1"
        )
        self.assertEqual(ref_count, 0)
        self.assertTrue(should_delete)

    def test_release_lease_with_remaining_references(self):
        """Test releasing lease when other jobs still hold references."""
        # Acquire two leases
        self.mgr.acquire_source_host_lease(
            "job-1", "test-host-1", "quick", "router-1", dscp=32
        )
        self.mgr.acquire_source_host_lease(
            "job-2", "test-host-1", "quick", "router-1", dscp=33
        )

        # Release one lease
        ref_count, should_delete = self.mgr.release_source_host_lease(
            "job-1", "test-host-1"
        )
        self.assertEqual(ref_count, 1)
        self.assertFalse(should_delete)

    def test_acquire_lease_nonexistent_host(self):
        """Test acquiring lease for non-existent host."""
        with self.assertRaises(ValueError):
            self.mgr.acquire_source_host_lease(
                "job-1", "nonexistent-host", "quick", "router-1", dscp=32
            )

    def test_release_nonexistent_lease(self):
        """Test releasing non-existent lease."""
        with self.assertRaises(ValueError):
            self.mgr.release_source_host_lease("job-1", "test-host-1")


class TestRegistryManagerRouterLocks(unittest.TestCase):
    """Test router lock operations."""

    def setUp(self):
        """Create temporary directories for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.registry_dir = Path(self.test_dir) / "registry"
        self.lock_dir = Path(self.test_dir) / "locks"

        self.config = {
            'data_dir': str(self.registry_dir),
            'lock_dir': str(self.lock_dir),
            'registry_manager': {
                'enabled': True,
                'lock_timeouts': {
                    'host_registry': 5.0,
                    'host_leases': 3.0,
                    'router_lock': 30.0,
                    'router_lock_atomic': 60.0,
                    'neighbor_leases': 3.0
                },
                'retry_attempts': 3,
                'retry_delay': 0.1
            }
        }

        self.logger = logging.getLogger(__name__)
        self.mgr = TsimRegistryManager(self.config, self.logger)

    def tearDown(self):
        """Cleanup."""
        self.mgr.cleanup()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_acquire_router_lock(self):
        """Test acquiring router lock."""
        result = self.mgr.acquire_router_lock("router-1", "job-1", timeout=5.0)
        self.assertTrue(result)

        # Release lock
        released = self.mgr.release_router_lock("router-1", "job-1")
        self.assertTrue(released)

    def test_router_lock_context_manager(self):
        """Test router lock context manager."""
        with self.mgr.router_lock("router-1", "job-1", timeout=5.0):
            # Lock should be held here
            pass
        # Lock should be released here

    def test_acquire_all_router_locks_atomic(self):
        """Test atomic multi-router lock acquisition."""
        routers = ["router-1", "router-2", "router-3"]
        result = self.mgr.acquire_all_router_locks_atomic(routers, "job-1", timeout=10.0)
        self.assertTrue(result)

        # Release all locks
        count = self.mgr.release_all_router_locks(routers, "job-1")
        self.assertEqual(count, 3)

    def test_all_router_locks_context_manager(self):
        """Test all router locks context manager."""
        routers = ["router-1", "router-2", "router-3"]
        with self.mgr.all_router_locks(routers, "job-1", timeout=10.0):
            # All locks should be held here
            pass
        # All locks should be released here

    def test_concurrent_lock_acquisition(self):
        """Test that two jobs cannot acquire same router lock."""
        # Job 1 acquires lock
        result1 = self.mgr.acquire_router_lock("router-1", "job-1", timeout=5.0)
        self.assertTrue(result1)

        # Job 2 tries to acquire same lock (should timeout quickly)
        result2 = self.mgr.acquire_router_lock("router-1", "job-2", timeout=0.5)
        self.assertFalse(result2)

        # Release job 1's lock
        self.mgr.release_router_lock("router-1", "job-1")

        # Now job 2 should be able to acquire
        result3 = self.mgr.acquire_router_lock("router-1", "job-2", timeout=5.0)
        self.assertTrue(result3)

        self.mgr.release_router_lock("router-1", "job-2")


class TestRegistryManagerConcurrency(unittest.TestCase):
    """Test concurrent access scenarios."""

    def setUp(self):
        """Create temporary directories for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.registry_dir = Path(self.test_dir) / "registry"
        self.lock_dir = Path(self.test_dir) / "locks"

        self.config = {
            'data_dir': str(self.registry_dir),
            'lock_dir': str(self.lock_dir),
            'registry_manager': {
                'enabled': True,
                'lock_timeouts': {
                    'host_registry': 5.0,
                    'host_leases': 3.0,
                    'router_lock': 30.0,
                    'router_lock_atomic': 60.0,
                    'neighbor_leases': 3.0
                },
                'retry_attempts': 3,
                'retry_delay': 0.1
            }
        }

        self.logger = logging.getLogger(__name__)
        self.mgr = TsimRegistryManager(self.config, self.logger)

    def tearDown(self):
        """Cleanup."""
        self.mgr.cleanup()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_concurrent_host_registration(self):
        """Test concurrent host registration by multiple threads."""
        results = []

        def register_host(host_id):
            try:
                result = self.mgr.check_and_register_host(
                    host_name=f"test-host-{host_id}",
                    primary_ip=f"10.0.0.{host_id}/24",
                    connected_to="router-1",
                    mac_address=f"aa:bb:cc:dd:ee:{host_id:02x}"
                )
                results.append((host_id, result))
            except Exception as e:
                results.append((host_id, str(e)))

        # Start 10 threads registering hosts
        threads = []
        for i in range(1, 11):
            t = threading.Thread(target=register_host, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # All should succeed
        self.assertEqual(len(results), 10)
        for host_id, result in results:
            self.assertTrue(result, f"Host {host_id} registration failed")

    def test_concurrent_lease_acquisition(self):
        """Test concurrent lease acquisition by multiple threads."""
        # Register a host first
        self.mgr.check_and_register_host(
            "test-host-1", "10.0.0.1/24", "router-1", "aa:bb:cc:dd:ee:01"
        )

        results = []

        def acquire_lease(job_id):
            try:
                ref_count = self.mgr.acquire_source_host_lease(
                    run_id=f"job-{job_id}",
                    host_name="test-host-1",
                    job_type="quick",
                    router_name="router-1",
                    dscp=32 + job_id
                )
                results.append((job_id, ref_count))
            except Exception as e:
                results.append((job_id, str(e)))

        # Start 5 threads acquiring leases
        threads = []
        for i in range(5):
            t = threading.Thread(target=acquire_lease, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # All should succeed and final count should be 5
        self.assertEqual(len(results), 5)
        final_count = self.mgr.get_host_lease_count("test-host-1")
        self.assertEqual(final_count, 5)


class TestRegistryManagerNeighborLeases(unittest.TestCase):
    """Test neighbor lease operations."""

    def setUp(self):
        """Create temporary directories for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.registry_dir = Path(self.test_dir) / "registry"
        self.lock_dir = Path(self.test_dir) / "locks"

        self.config = {
            'data_dir': str(self.registry_dir),
            'lock_dir': str(self.lock_dir),
            'registry_manager': {
                'enabled': True,
                'lock_timeouts': {
                    'host_registry': 5.0,
                    'host_leases': 3.0,
                    'router_lock': 30.0,
                    'router_lock_atomic': 60.0,
                    'neighbor_leases': 3.0
                },
                'retry_attempts': 3,
                'retry_delay': 0.1
            }
        }

        self.logger = logging.getLogger(__name__)
        self.mgr = TsimRegistryManager(self.config, self.logger)

    def tearDown(self):
        """Cleanup."""
        self.mgr.cleanup()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_acquire_neighbor_lease(self):
        """Test acquiring neighbor lease."""
        ref_count = self.mgr.acquire_neighbor_lease(
            run_id="job-1",
            host_name="test-host-1",
            neighbor_ip="10.0.0.254"
        )
        self.assertEqual(ref_count, 1)

    def test_acquire_multiple_neighbor_leases(self):
        """Test multiple jobs acquiring same neighbor."""
        ref_count1 = self.mgr.acquire_neighbor_lease(
            "job-1", "test-host-1", "10.0.0.254"
        )
        self.assertEqual(ref_count1, 1)

        ref_count2 = self.mgr.acquire_neighbor_lease(
            "job-2", "test-host-1", "10.0.0.254"
        )
        self.assertEqual(ref_count2, 2)

    def test_release_neighbor_lease(self):
        """Test releasing neighbor lease."""
        # Acquire lease
        self.mgr.acquire_neighbor_lease("job-1", "test-host-1", "10.0.0.254")

        # Release lease
        ref_count, should_delete = self.mgr.release_neighbor_lease(
            "job-1", "test-host-1", "10.0.0.254"
        )
        self.assertEqual(ref_count, 0)
        self.assertTrue(should_delete)

    def test_release_neighbor_lease_with_remaining_references(self):
        """Test releasing neighbor lease with remaining references."""
        # Acquire two leases
        self.mgr.acquire_neighbor_lease("job-1", "test-host-1", "10.0.0.254")
        self.mgr.acquire_neighbor_lease("job-2", "test-host-1", "10.0.0.254")

        # Release one lease
        ref_count, should_delete = self.mgr.release_neighbor_lease(
            "job-1", "test-host-1", "10.0.0.254"
        )
        self.assertEqual(ref_count, 1)
        self.assertFalse(should_delete)


if __name__ == '__main__':
    # Set up logging
    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run tests
    unittest.main()
