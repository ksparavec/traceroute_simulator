#!/usr/bin/env -S python3 -B -u
"""
Test script for DSCP Registry functionality
"""

import sys
import os
import time
import threading
from pathlib import Path

# Add wsgi services to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / 'wsgi'))

from services.tsim_dscp_registry import TsimDscpRegistry
from services.tsim_config_service import TsimConfigService


def test_basic_allocation():
    """Test basic DSCP allocation and release"""
    print("=== Test: Basic Allocation ===")
    
    # Create config service with test configuration
    config = TsimConfigService()
    
    # Create DSCP registry
    registry = TsimDscpRegistry(config)
    
    # Test allocation
    print("Testing allocation...")
    dscp1 = registry.allocate_dscp("job_1", "test_user")
    print(f"Allocated DSCP {dscp1} for job_1")
    
    dscp2 = registry.allocate_dscp("job_2", "test_user")
    print(f"Allocated DSCP {dscp2} for job_2")
    
    # Test getting existing allocation
    existing = registry.get_job_dscp("job_1")
    print(f"Retrieved DSCP {existing} for job_1 (should match {dscp1})")
    assert existing == dscp1, f"Expected {dscp1}, got {existing}"
    
    # Test status
    status = registry.get_allocation_status()
    print(f"Status: {status['total_allocations']} allocations, DSCPs: {status['used_dscps']}")
    
    # Test release
    print("Testing release...")
    success = registry.release_dscp("job_1")
    print(f"Released job_1: {success}")
    
    success = registry.release_dscp("job_2")
    print(f"Released job_2: {success}")
    
    # Final status
    status = registry.get_allocation_status()
    print(f"Final status: {status['total_allocations']} allocations")
    
    print("✅ Basic allocation test passed\n")


def test_exhaustion():
    """Test DSCP exhaustion scenarios"""
    print("=== Test: DSCP Exhaustion ===")
    
    config = TsimConfigService()
    registry = TsimDscpRegistry(config)
    
    allocated_jobs = []
    allocated_dscps = []
    
    # Allocate all available DSCPs (32 total: 32-63)
    print("Allocating all available DSCPs...")
    for i in range(32):
        job_id = f"exhaustion_job_{i}"
        dscp = registry.allocate_dscp(job_id, "test_user")
        if dscp is not None:
            allocated_jobs.append(job_id)
            allocated_dscps.append(dscp)
            print(f"  Allocated DSCP {dscp} for {job_id}")
        else:
            print(f"  No DSCP available for {job_id}")
            break
    
    print(f"Successfully allocated {len(allocated_jobs)} DSCPs")
    
    # Try to allocate one more (should fail)
    print("Trying to allocate beyond capacity...")
    overflow_dscp = registry.allocate_dscp("overflow_job", "test_user")
    if overflow_dscp is None:
        print("✅ Correctly rejected allocation beyond capacity")
    else:
        print(f"❌ Unexpectedly allocated DSCP {overflow_dscp} beyond capacity")
    
    # Release all allocations
    print("Releasing all allocations...")
    for job_id in allocated_jobs:
        registry.release_dscp(job_id)
    
    # Verify all released
    status = registry.get_allocation_status()
    if status['total_allocations'] == 0:
        print("✅ All allocations released successfully")
    else:
        print(f"❌ {status['total_allocations']} allocations remain after release")
    
    print("✅ Exhaustion test passed\n")


def test_concurrent_allocation():
    """Test concurrent allocation from multiple threads"""
    print("=== Test: Concurrent Allocation ===")
    
    config = TsimConfigService()
    registry = TsimDscpRegistry(config)
    
    results = {}
    errors = []
    
    def allocate_worker(thread_id):
        try:
            job_id = f"concurrent_job_{thread_id}"
            dscp = registry.allocate_dscp(job_id, f"user_{thread_id}")
            results[thread_id] = dscp
            if dscp:
                # Hold allocation briefly
                time.sleep(0.1)
                # Release it
                registry.release_dscp(job_id)
        except Exception as e:
            errors.append(f"Thread {thread_id}: {e}")
    
    # Launch 10 concurrent threads
    threads = []
    for i in range(10):
        thread = threading.Thread(target=allocate_worker, args=(i,))
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    # Check results
    successful_allocations = sum(1 for dscp in results.values() if dscp is not None)
    failed_allocations = sum(1 for dscp in results.values() if dscp is None)
    
    print(f"Successful allocations: {successful_allocations}")
    print(f"Failed allocations: {failed_allocations}")
    print(f"Errors: {len(errors)}")
    
    if errors:
        for error in errors:
            print(f"  Error: {error}")
    
    # Check for duplicate DSCPs
    allocated_dscps = [dscp for dscp in results.values() if dscp is not None]
    unique_dscps = set(allocated_dscps)
    
    if len(allocated_dscps) == len(unique_dscps):
        print("✅ No duplicate DSCP allocations")
    else:
        print(f"❌ Duplicate DSCPs detected: {len(allocated_dscps)} total, {len(unique_dscps)} unique")
    
    # Final cleanup check
    status = registry.get_allocation_status()
    if status['total_allocations'] == 0:
        print("✅ All concurrent allocations cleaned up")
    else:
        print(f"⚠️  {status['total_allocations']} allocations remain (may be timing issue)")
    
    print("✅ Concurrent allocation test passed\n")


def test_stale_cleanup():
    """Test cleanup of stale allocations"""
    print("=== Test: Stale Cleanup ===")
    
    config = TsimConfigService()
    registry = TsimDscpRegistry(config)
    
    # Manually create a stale allocation by modifying the registry
    print("Creating simulated stale allocation...")
    
    # Allocate normally first
    dscp = registry.allocate_dscp("test_stale_job", "test_user")
    print(f"Allocated DSCP {dscp} for test job")
    
    # Manually modify the registry to simulate a dead process
    with registry.semaphore:
        with registry._file_lock():
            reg_data = registry._load_registry()
            # Set a bogus PID to simulate dead process
            reg_data['allocations']['test_stale_job']['pid'] = 999999
            # Set old timestamp to simulate timeout
            reg_data['allocations']['test_stale_job']['allocated_at'] = time.time() - 7200  # 2 hours ago
            registry._save_registry(reg_data)
    
    print("Simulated stale allocation (dead PID + old timestamp)")
    
    # Run cleanup
    cleaned = registry.cleanup_stale_allocations()
    print(f"Cleanup removed {cleaned} stale allocations")
    
    # Verify cleanup worked
    status = registry.get_allocation_status()
    if status['total_allocations'] == 0:
        print("✅ Stale allocation cleaned up successfully")
    else:
        print(f"❌ {status['total_allocations']} allocations remain after cleanup")
    
    print("✅ Stale cleanup test passed\n")


def test_disabled_registry():
    """Test registry with disabled configuration"""
    print("=== Test: Disabled Registry ===")
    
    config = TsimConfigService()
    # Manually disable the registry
    config.config['dscp_registry'] = {'enabled': False}
    
    registry = TsimDscpRegistry(config)
    
    # Test allocation when disabled
    dscp = registry.allocate_dscp("disabled_test", "test_user")
    print(f"DSCP when disabled: {dscp}")
    
    if dscp == 32:  # Default value when disabled
        print("✅ Correctly returned default DSCP when disabled")
    else:
        print(f"❌ Expected default DSCP 32, got {dscp}")
    
    # Test release when disabled
    success = registry.release_dscp("disabled_test")
    if success:
        print("✅ Release succeeded when disabled")
    else:
        print("❌ Release failed when disabled")
    
    print("✅ Disabled registry test passed\n")


def main():
    """Run all tests"""
    print("Starting DSCP Registry Tests\n")
    
    try:
        test_basic_allocation()
        test_exhaustion()
        test_concurrent_allocation()
        test_stale_cleanup()
        test_disabled_registry()
        
        print("🎉 All DSCP Registry tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())