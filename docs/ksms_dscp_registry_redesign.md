# KSMS DSCP Registry Redesign Plan

## Overview
Replace DSCP cycling with a **global DSCP registry** that assigns unique DSCP values per job, enabling parallel test execution while maintaining packet isolation.

## Core Design Changes

### 1. DSCP Registry Service (`/wsgi/services/tsim_dscp_registry.py`)

```python
class TsimDscpRegistry:
    """Thread-safe DSCP allocation registry for parallel KSMS jobs"""
    
    def __init__(self, config_service):
        self.config = config_service
        self.registry_file = Path(config_service.get('data_dir')) / 'dscp_registry.json'
        self.lock_file = Path(config_service.get('lock_dir')) / 'dscp_registry.lock'
        self.semaphore = threading.Semaphore(1)
        
        # DSCP allocation range: 32-63 (0x20-0x3F) = 32 concurrent jobs max
        self.dscp_min = 32
        self.dscp_max = 63
        
    def allocate_dscp(self, job_id: str, username: str = None) -> Optional[int]:
        """Allocate unique DSCP value for job. Returns None if no DSCP available."""
        with self.semaphore:
            registry = self._load_registry()
            
            # Clean up stale allocations first
            self._cleanup_stale_allocations(registry)
            
            # Find available DSCP
            used_dscps = {entry['dscp'] for entry in registry['allocations'].values()}
            for dscp in range(self.dscp_min, self.dscp_max + 1):
                if dscp not in used_dscps:
                    # Allocate this DSCP
                    registry['allocations'][job_id] = {
                        'dscp': dscp,
                        'job_id': job_id,
                        'username': username,
                        'allocated_at': time.time(),
                        'pid': os.getpid(),
                        'status': 'active'
                    }
                    self._save_registry(registry)
                    return dscp
            
            return None  # No DSCP available
    
    def release_dscp(self, job_id: str) -> bool:
        """Release DSCP allocation for completed job"""
        with self.semaphore:
            registry = self._load_registry()
            if job_id in registry['allocations']:
                del registry['allocations'][job_id]
                self._save_registry(registry)
                return True
            return False
    
    def get_job_dscp(self, job_id: str) -> Optional[int]:
        """Get allocated DSCP for job"""
        registry = self._load_registry()
        allocation = registry['allocations'].get(job_id)
        return allocation['dscp'] if allocation else None
    
    def _cleanup_stale_allocations(self, registry: Dict):
        """Remove allocations for dead processes or old jobs"""
        stale_jobs = []
        current_time = time.time()
        max_age = 3600  # 1 hour timeout
        
        for job_id, alloc in registry['allocations'].items():
            # Check if process still exists
            try:
                os.kill(alloc['pid'], 0)  # Signal 0 checks if process exists
                process_alive = True
            except (OSError, ProcessLookupError):
                process_alive = False
            
            # Mark as stale if process dead or allocation too old
            if not process_alive or (current_time - alloc['allocated_at']) > max_age:
                stale_jobs.append(job_id)
        
        for job_id in stale_jobs:
            del registry['allocations'][job_id]
```

### 2. Updated KSMS Service Integration

```python
class TsimKsmsService:
    def __init__(self, config_service, dscp_registry):
        self.dscp_registry = dscp_registry
        # ... other init
    
    def execute_fast_scan(self, job_id: str, source_ip: str, dest_ip: str, 
                         port_protocol_list: List[Tuple[int, str]]) -> Dict[str, Any]:
        """Execute KSMS scan with job-specific DSCP"""
        
        # Allocate unique DSCP for this job
        job_dscp = self.dscp_registry.allocate_dscp(job_id)
        if job_dscp is None:
            raise RuntimeError("No DSCP values available - too many concurrent jobs")
        
        try:
            # Execute KSMS with single DSCP for all services
            result = self._execute_ksms_with_dscp(job_id, job_dscp, source_ip, dest_ip, port_protocol_list)
            return result
        finally:
            # Always release DSCP when done
            self.dscp_registry.release_dscp(job_id)
```

### 3. Simplified KSMS Tester Changes

**Remove DSCP Cycling Logic:**
```python
# OLD (lines 585-594): Complex cycling through 32 values
for idx, (port, proto) in enumerate(services):
    dscp = 0x20 + (idx % 32)  # REMOVE THIS
    svc_tokens[(port, proto)] = {'dscp': dscp, 'tos': dscp << 2}

# NEW: Single DSCP per job
def assign_service_tokens(services: List[Tuple[int, str]], job_dscp: int) -> Dict:
    """Assign single DSCP value to all services in job"""
    svc_tokens = {}
    for port, proto in services:
        svc_tokens[(port, proto)] = {
            'dscp': job_dscp, 
            'tos': job_dscp << 2
        }
    return svc_tokens
```

**Simplified iptables Rules:**
```python
# OLD: Each service gets different DSCP
-A PREROUTING -p tcp -m dscp --dscp 0x20 --dport 80 -j TSIM_TAP_FW    # Service 1
-A PREROUTING -p tcp -m dscp --dscp 0x21 --dport 443 -j TSIM_TAP_FW   # Service 2
-A PREROUTING -p tcp -m dscp --dscp 0x22 --dport 3306 -j TSIM_TAP_FW  # Service 3

# NEW: All services in job share same DSCP
-A PREROUTING -p tcp -m dscp --dscp 0x20 --dport 80 -j TSIM_TAP_FW    # Job A
-A PREROUTING -p tcp -m dscp --dscp 0x20 --dport 443 -j TSIM_TAP_FW   # Job A  
-A PREROUTING -p tcp -m dscp --dscp 0x20 --dport 3306 -j TSIM_TAP_FW  # Job A

# Different job uses different DSCP
-A PREROUTING -p tcp -m dscp --dscp 0x21 --dport 22 -j TSIM_TAP_FW    # Job B
-A PREROUTING -p tcp -m dscp --dscp 0x21 --dport 80 -j TSIM_TAP_FW    # Job B
```

### 4. Queue System Integration

**Enhanced Job Parameters:**
```python
# In TsimSchedulerService
def _leader_loop(self):
    while not self._stop_event.is_set():
        job = self.queue.pop_next()
        if not job:
            time.sleep(0.5)
            return

        run_id = job.get('run_id')
        
        # Allocate DSCP before starting job
        job_dscp = self.dscp_registry.allocate_dscp(run_id)
        if job_dscp is None:
            # Queue job back and wait for DSCP availability
            self.queue.enqueue_front(job)  # New method needed
            time.sleep(5)  # Wait before retry
            continue
        
        try:
            # Execute with allocated DSCP
            params = job['params']
            params['job_dscp'] = job_dscp
            self.executor.execute(run_id, params)
        finally:
            self.dscp_registry.release_dscp(run_id)
```

### 5. Parallel Execution Capability

**Remove Global Network Lock for KSMS Jobs:**
```python
# Current: Single global lock prevents all parallel execution
with self.lock_manager.lock('network_test', timeout=3600):
    # Only one job at a time

# NEW: DSCP-based parallel execution  
if job_type == 'ksms_fast':
    # No global lock needed - DSCP provides isolation
    self.executor.execute_ksms_fast(params)
else:
    # Detailed analysis still needs global lock
    with self.lock_manager.lock('network_test', timeout=3600):
        self.executor.execute_detailed(params)
```

## Configuration Changes

### Updated `config.json`
```json
{
  "dscp_registry": {
    "enabled": true,
    "dscp_range_min": 32,
    "dscp_range_max": 63, 
    "max_concurrent_jobs": 32,
    "allocation_timeout": 3600,
    "cleanup_interval": 300
  },
  "ksms_parallel_execution": true,
  "max_parallel_fast_jobs": 8
}
```

## Benefits of This Design

### 1. **True Parallel Execution**
- Up to 32 KSMS fast jobs can run simultaneously  
- Each job gets isolated packet counting via unique DSCP
- No false positives from cross-job traffic contamination

### 2. **Simplified Service Logic**
- Eliminates complex DSCP cycling calculations
- All services in a job share the same DSCP value
- Easier debugging and troubleshooting

### 3. **Resource Efficiency**
- Better utilization of available CPU cores
- Reduced queue wait times for fast analysis
- Maintains detailed analysis serialization when needed

### 4. **Robust Resource Management**
- Process death cleanup prevents DSCP leaks
- Timeout-based stale allocation cleanup  
- Semaphore protection against race conditions

## Implementation Timeline

### Phase 1: Registry Infrastructure (Week 1)
1. Create `TsimDscpRegistry` service with semaphore protection
2. Add registry file management and cleanup logic
3. Unit tests for allocation/release/cleanup scenarios

### Phase 2: KSMS Integration (Week 2) 
1. Modify KSMS tester to accept job-specific DSCP
2. Remove cycling logic, implement single DSCP assignment
3. Update iptables rule generation 

### Phase 3: Queue System Enhancement (Week 3)
1. Update scheduler to use DSCP registry
2. Implement parallel execution for KSMS fast jobs
3. Add queue management for DSCP exhaustion scenarios

### Phase 4: Testing and Optimization (Week 4)
1. Test parallel job execution with packet isolation
2. Performance benchmarking with multiple concurrent fast jobs
3. Error handling and edge case validation

## Risk Mitigation

### DSCP Exhaustion Handling
- Queue jobs when no DSCP available rather than failing
- Monitor DSCP utilization and alert on high usage
- Graceful degradation to serial execution if needed

### Registry Corruption Protection
- Atomic file updates with temp files and renames
- Registry validation on load with auto-repair
- Backup/restore mechanisms for critical failures  

### Process Death Recovery
- PID-based stale allocation detection
- Timeout-based cleanup for hung processes
- Health check integration with registry cleanup

This design enables true parallel KSMS execution while maintaining packet isolation and simplifying the service differentiation logic significantly.