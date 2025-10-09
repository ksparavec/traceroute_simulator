# Comprehensive Race Condition Elimination Plan

## Executive Summary

Implement host reference counting and per-router locking to eliminate race conditions between concurrent quick analysis jobs and between quick/detailed analysis jobs. This involves enhancing the existing Host Registry with reference counting capabilities, modifying iptables rule management, and adding conflict detection mechanisms.

## Design Principles

### No Hardcoded Paths
- All runtime paths come from `config_loader.get_registry_paths()` or `config.get()`
- Never hardcode `/dev/shm/`, `/var/opt/`, or absolute system paths
- File paths in documentation are relative to repository root

### No Environment Variables for IPC
- **Job-specific values** (DSCP, run_id): Command-line arguments
- **Global configuration** (registry paths, lock directories): Read from config in each process
- Environment variables eliminated for inter-process communication
- Makes data flow explicit and testable

### Configuration-Driven
- All coordination mechanisms configurable via `wsgi/config.json`
- Can disable registry coordination for single-threaded deployments
- Lock timeouts, retry attempts, and DSCP ranges all configurable

### Scheduler-Based Job Coordination
- **Scheduler manages all concurrency** via enhanced `TsimSchedulerService`
- Scheduler pops compatible jobs from queue:
  - **Quick jobs**: Up to 32 in parallel (DSCP-isolated)
  - **Detailed jobs**: One at a time (exclusive)
- **No global lock** - parallel execution enabled
- Jobs execute immediately when popped (no waiting/blocking in job code)
- DSCP allocation/deallocation handled by scheduler
- Existing queue/scheduler infrastructure leveraged

---

## Current Problem Analysis

### Race Condition #1: Concurrent Quick Jobs on Shared Router

**Scenario**: Two quick analysis jobs run simultaneously and share a common router.

**Timeline of Failure**:
```
Time | Job 1 (DSCP 32, testing 80/tcp) | Job 2 (DSCP 33, testing 443/tcp)
-----+----------------------------------+----------------------------------
T0   | iptables-save (reads state A)   |
T1   |                                  | iptables-save (reads state A)
T2   | Remove ALL TSIM_KSMS rules       |
T3   | Add Job 1 rules (DSCP 32)        |
T4   | iptables-restore (installs)      |
T5   |                                  | Remove ALL TSIM_KSMS rules <--- REMOVES JOB 1!
T6   |                                  | Add Job 2 rules (DSCP 33)
T7   |                                  | iptables-restore (overwrites!)
```

**Problem Code** (ksms_tester.py:274):
```python
if 'TSIM_KSMS=' in ln:
    continue  # Skip ANY line containing TSIM_KSMS (ALL jobs)
```

**Result**: Job 1's iptables rules are removed by Job 2, causing Job 1 to report UNKNOWN for all services.

### Race Condition #2: Host Creation/Deletion Conflicts

**Scenario**: Quick job A is using a source host while Quick job B or Detailed job tries to delete it.

**Problem Code** (tsim_ksms_service.py:783):
```python
# Blindly removes host without checking if other jobs are using it
tsimsh_exec(f"host remove --name {src_host_name} --force")
```

**Result**: Active job loses its network namespace mid-execution, causing connection failures.

### Race Condition #3: Quick/Detailed Job Conflicts

**Scenario**: Detailed analysis starts while quick jobs are running on same routers.

**Problem**: No conflict detection mechanism exists. Detailed analysis uses `host clean --force` which removes ALL hosts regardless of active usage.

---

## Phase 1: Enhance Host Registry with Reference Counting

### 1.1 Enhance `host_namespace_setup.py`

**Location**: `src/simulators/host_namespace_setup.py`

**Purpose**: Add reference counting and job tracking to existing host registry infrastructure.

**Current Implementation**:
- Registry path obtained from `config_loader.get_registry_paths()['hosts']`
- Managed by `HostNamespaceSetup` class
- Uses `_atomic_json_operation()` for thread-safe file locking (fcntl)
- Current structure tracks host creation metadata

**Enhancements Needed**:
- Add per-host reference counting
- Add job tracking (which jobs are using each host)
- Add conflict detection between job types
- Add stale job cleanup (check if process alive)
- Add acquire/release methods for job lifecycle

**Enhanced Data Structure** (adds to existing fields):
```json
{
  "destination-2": {
    "primary_ip": "10.128.47.21/24",
    "secondary_ips": [],
    "connected_to": "befw-00190-045.lvnbb.de",
    "router_interface": "ens2f0",
    "gateway_ip": "10.128.47.247",
    "router_ip_added": false,
    "dummy_interfaces": [],
    "created_at": "Thu Oct  9 04:09:39 PM CEST 2025",
    "connection_type": "sim_mesh_direct",
    "mesh_bridge": "br0010",
    "host_veth": "h34ba20",
    "mesh_veth": "m34ba20",
    "sim_namespace": "netsim",

    "ref_count": 2,
    "jobs": {
      "job-abc123": {
        "pid": 12345,
        "type": "quick",
        "dscp": 32,
        "allocated_at": 1234567890.123
      },
      "job-def456": {
        "pid": 12346,
        "type": "quick",
        "dscp": 33,
        "allocated_at": 1234567891.234
      }
    }
  }
}
```

**New Methods to Add to `HostNamespaceSetup` class**:

```python
def acquire_host_ref(self, job_id: str, host_name: str,
                     job_type: str, dscp: int = None) -> Dict[str, Any]:
    """Acquire reference to host, increment ref count

    Called AFTER host is physically created. Updates registry atomically.

    Args:
        job_id: Unique job identifier
        host_name: Host namespace name
        job_type: 'quick' or 'detailed'
        dscp: DSCP value (for quick jobs only)

    Returns:
        {
            'action': 'acquired' | 'initialized',
            'ref_count': int,
            'conflicts': List[str]  # Conflicting job IDs (if any)
        }
    """

def release_host_ref(self, job_id: str, host_name: str) -> Dict[str, Any]:
    """Release host reference, decrement ref count

    Called BEFORE host is physically removed.

    Returns:
        {
            'ref_count': int,  # Remaining ref count
            'should_remove_host': bool  # True if ref_count reached 0
        }
    """

def check_host_conflicts(self, host_name: str, job_type: str) -> Dict[str, Any]:
    """Check for conflicts (OPTIONAL - for monitoring/debugging only)

    NOTE: Conflict detection now handled by scheduler (Phase 2).
    This method is optional and primarily useful for:
    - Debugging and monitoring
    - Unit tests
    - Standalone mode (when not using scheduler)

    Uses existing load_host_registry() method.

    Returns:
        {
            'has_conflict': bool,
            'conflict_type': 'quick_vs_detailed' | 'detailed_vs_quick' | None,
            'active_jobs': List[Dict]  # Conflicting job info
        }
    """

def get_host_ref_count(self, host_name: str) -> int:
    """Get current reference count for host

    Returns 0 if host not found or has no ref_count field."""

def cleanup_stale_job_refs(self) -> int:
    """Remove references for dead processes across all hosts

    Checks if PIDs are alive using os.kill(pid, 0).
    Returns count of stale jobs cleaned."""

def get_active_jobs_for_host(self, host_name: str) -> List[Dict]:
    """Get all active jobs using specific host"""
```

**Host Registry Usage**:
- **Primary purpose**: Reference counting for shared host reuse
- **NOT used for**: Job conflict detection (handled by scheduler)
- Jobs acquire/release host references via `acquire_host_ref()` and `release_host_ref()`
- Registry tracks which jobs are using each host to prevent premature deletion
- Stale job references cleaned up automatically via PID checking

**Job Conflict Detection** (router-level, handled by scheduler):

Router locks enable fine-grained parallelism:

1. **Quick vs Quick**: ALLOWED (DSCP isolated, any routers)
   - Up to 32 concurrent, no router overlap checking needed

2. **Quick vs Detailed**: ALLOWED if router sets are disjoint
   - Example: Quick uses routers {A,B}, Detailed uses {X,Y} -> parallel OK
   - Example: Quick uses routers {A,B}, Detailed uses {B,C} -> BLOCKED (router B overlap)

3. **Detailed vs Quick**: ALLOWED if router sets are disjoint
   - Same logic as (2)

4. **Detailed vs Detailed**: ALLOWED if router sets are disjoint
   - Example: Detailed1 uses {A,B,C}, Detailed2 uses {X,Y,Z} -> parallel OK
   - Example: Detailed1 uses {A,B,C}, Detailed2 uses {C,D,E} -> BLOCKED (router C overlap)

**Router Overlap Rules**:
- Quick jobs: Don't need router locks, but scheduler tracks their routers
- Detailed jobs: Need exclusive router access (via locks)
- Conflict = ANY router used by both jobs

**Implementation**:
- **Phase 2 (Scheduler/Queue)**: Scheduler tracks router usage per job, checks for overlaps
- **Phase 3 (Router Locks)**: Detailed jobs acquire locks per router (enforcement)
- **Phase 5 (ksms_tester.py)**: NO conflict checking - executes when called
- **Phase 6 (network_reachability_test_multi.py)**: Acquires router locks before each router measurement
- Scheduler ensures no router conflicts before starting jobs

### 1.2 Enhance `_batch_register_host()` Method

**Location**: `host_namespace_setup.py:644`

**Current Behavior**: Atomically adds host to registry with physical metadata only

**Enhancement**: Initialize ref_count and jobs fields when creating new host

**Modification** (line 695):
```python
def add_host_op(registry):
    # ... existing collision checks (lines 654-693) ...

    # All checks passed, safe to add
    registry[host_name] = host_config

    # NEW: Initialize reference counting fields
    registry[host_name]['ref_count'] = 0
    registry[host_name]['jobs'] = {}

    return True, registry
```

**Backward Compatibility**: Existing hosts without these fields will be handled gracefully in `acquire_host_ref()` by initializing them on first access.

---

## Phase 2: Enhance Scheduler for Parallel Execution

### 2.1 Enhance `TsimQueueService`

**Location**: `wsgi/services/tsim_queue_service.py` (existing file)

**Purpose**: Add intelligent job selection for parallel execution

**Current Behavior**: Simple FIFO queue with `pop_next()` returning single job

**Enhancements**:

**Add `analysis_mode` and `routers` to queued job metadata:**

```python
def enqueue(self, run_id: str, username: str, params: Dict[str, Any]) -> int:
    """Enqueue a new job and return its 1-based position."""
    with self._lock():
        q = self._load_queue()
        jobs: List[Dict[str, Any]] = q.get('jobs', [])

        # Avoid duplicating existing run_id
        for idx, j in enumerate(jobs):
            if j.get('run_id') == run_id:
                return idx + 1

        jobs.append({
            'run_id': run_id,
            'username': username,
            'created_at': time.time(),
            'status': 'QUEUED',
            'params': params,
            'analysis_mode': params.get('analysis_mode', 'detailed'),  # NEW
            'routers': params.get('routers', [])  # NEW - from trace analysis
        })
        q['jobs'] = jobs
        q['updated_at'] = time.time()
        self._save_queue(q)
        return len(jobs)
```

**Add router-aware job popping:**

```python
def pop_compatible_jobs(self, running_jobs: Dict[str, Dict]) -> List[Dict[str, Any]]:
    """Pop compatible jobs based on router overlap with running jobs.

    Args:
        running_jobs: Dict of {run_id: {'type': 'quick'|'detailed',
                                        'dscp': int, 'routers': List[str]}}

    Returns:
        List of job dicts to execute (no router conflicts)
    """
    with self._lock():
        q = self._load_queue()
        jobs = q.get('jobs', [])
        if not jobs:
            return []

        # Collect all routers currently in use
        used_routers = set()
        for job_info in running_jobs.values():
            used_routers.update(job_info.get('routers', []))

        # Count running quick jobs for DSCP limit
        quick_count = sum(1 for j in running_jobs.values() if j['type'] == 'quick')

        to_pop = []
        for job in jobs:
            job_routers = set(job.get('routers', []))
            job_type = job.get('analysis_mode', 'detailed')

            # Check router overlap
            has_router_conflict = bool(job_routers & used_routers)

            if has_router_conflict:
                # Router conflict - cannot start this job
                continue

            # No router conflict - check type-specific limits
            if job_type == 'quick':
                if quick_count >= 32:
                    # Hit DSCP limit
                    continue
                # Can start this quick job
                to_pop.append(job)
                quick_count += 1
                used_routers.update(job_routers)

            else:  # detailed
                # Can start this detailed job (no router conflicts)
                to_pop.append(job)
                used_routers.update(job_routers)

            # Limit how many jobs we pop at once
            if len(to_pop) >= 32:
                break

        # Remove popped jobs from queue
        if to_pop:
            remaining = [j for j in jobs if j not in to_pop]
            q['jobs'] = remaining
            q['updated_at'] = time.time()
            self._save_queue(q)

        return to_pop
```

**Key Logic**:
- Iterate through queued jobs (FIFO order preserved)
- For each job, check if its routers overlap with any running job's routers
- If no overlap: allow job to start (add to `to_pop`)
- If overlap: skip job (stays in queue)
- Respect DSCP limit (32 max quick jobs)
- Can pop multiple detailed jobs if they use different routers!

**Add running jobs tracking (replaces single `current` job):**

```python
def set_running(self, jobs: List[Dict[str, Any]]):
    """Set multiple jobs as running (replaces set_current)"""
    with self._lock():
        tmp = self.current_file.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            json.dump({
                'version': 1,
                'updated_at': time.time(),
                'jobs': jobs
            }, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self.current_file)

def get_running(self) -> List[Dict[str, Any]]:
    """Get all running jobs (replaces get_current)"""
    with self._lock():
        if not self.current_file.exists():
            return []
        try:
            with open(self.current_file, 'r') as f:
                data = json.load(f)
                return data.get('jobs', [])
        except Exception:
            return []

def remove_running(self, run_id: str):
    """Remove a job from running list"""
    with self._lock():
        if not self.current_file.exists():
            return
        try:
            with open(self.current_file, 'r') as f:
                data = json.load(f)
            jobs = data.get('jobs', [])
            jobs = [j for j in jobs if j.get('run_id') != run_id]
            data['jobs'] = jobs
            data['updated_at'] = time.time()

            tmp = self.current_file.with_suffix('.tmp')
            with open(tmp, 'w') as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(self.current_file)
        except Exception:
            pass
```

### 2.2 Enhance `TsimSchedulerService`

**Location**: `wsgi/services/tsim_scheduler_service.py` (existing file)

**Current Problem**: Uses global `network_test` lock that prevents ALL concurrency

**Current Code (line 83)**:
```python
with self.lock_manager.lock('network_test', timeout=3600):
    # Only ONE job runs at a time - blocks all parallelism!
    tester = MultiServiceTester(...)
    results = tester.run()
```

**Enhancements**:

**Track running jobs:**

```python
class TsimSchedulerService:
    def __init__(self, config_service, queue_service, progress_tracker, executor, lock_manager):
        # ... existing init ...

        # NEW: Track multiple running jobs
        self.running_jobs = {}  # {run_id: {'type': str, 'dscp': int, 'future': Future, 'started_at': float, 'job': dict}}
        self.running_lock = threading.Lock()

        # NEW: Thread pool for parallel job execution
        self.executor_pool = ThreadPoolExecutor(max_workers=33, thread_name_prefix='job-executor')
```

**Replace leader loop to remove global lock:**

```python
def _leader_loop(self):
    """While leader, manage parallel job execution with router-level conflict detection"""
    while not self._stop_event.is_set():
        # Clean up completed jobs
        self._cleanup_completed_jobs()

        # Pop compatible jobs based on router overlap
        with self.running_lock:
            running_jobs_info = {
                run_id: {
                    'type': info['type'],
                    'dscp': info.get('dscp'),
                    'routers': info.get('routers', [])  # NEW - for router conflict detection
                }
                for run_id, info in self.running_jobs.items()
            }

        jobs_to_start = self.queue.pop_compatible_jobs(running_jobs_info)

        if not jobs_to_start:
            time.sleep(0.5)
            continue

        # Start all compatible jobs in parallel (no router conflicts!)
        for job in jobs_to_start:
            self._start_job(job)

        time.sleep(0.25)

def _start_job(self, job: Dict[str, Any]):
    """Start a single job in thread pool"""
    run_id = job.get('run_id')
    analysis_mode = job.get('analysis_mode', 'detailed')
    routers = job.get('routers', [])  # NEW - track routers for conflict detection

    # Allocate DSCP for quick jobs
    dscp = None
    if analysis_mode == 'quick':
        from services.tsim_dscp_registry import TsimDscpRegistry
        dscp_registry = TsimDscpRegistry(self.config)
        dscp = dscp_registry.allocate_dscp(run_id)
        if dscp is None:
            self.logger.error(f"No DSCP available for quick job {run_id}")
            return

    # Add to running jobs tracking
    with self.running_lock:
        self.running_jobs[run_id] = {
            'type': analysis_mode,
            'dscp': dscp,
            'routers': routers,  # NEW - track routers
            'started_at': time.time(),
            'job': job
        }

    # Update queue service with running jobs list
    self._update_queue_running()

    # Submit to thread pool for parallel execution
    future = self.executor_pool.submit(self._execute_job_wrapper, job, dscp)

    with self.running_lock:
        self.running_jobs[run_id]['future'] = future

def _execute_job_wrapper(self, job: Dict[str, Any], dscp: Optional[int]) -> Dict[str, Any]:
    """Wrapper for job execution with error handling and cleanup"""
    run_id = job.get('run_id')
    try:
        # Inject DSCP into params for quick jobs
        params = job.get('params', {})
        if dscp is not None:
            params['job_dscp'] = dscp

        # Execute job (without global lock - parallelism enabled!)
        result = self.executor.execute(
            run_id,
            params.get('source_ip'),
            params.get('dest_ip'),
            params.get('source_port'),
            params.get('port_protocol_list', []),
            params.get('user_trace_data'),
            params.get('analysis_mode', 'detailed')
        )
        return {'success': True, 'result': result}

    except Exception as e:
        self.logger.error(f"Job {run_id} failed: {e}")
        try:
            self.progress.log_phase(run_id, 'ERROR', f'Execution error: {e}')
        except Exception:
            pass
        return {'success': False, 'error': str(e)}

    finally:
        # Release DSCP for quick jobs
        if dscp is not None:
            from services.tsim_dscp_registry import TsimDscpRegistry
            dscp_registry = TsimDscpRegistry(self.config)
            dscp_registry.release_dscp(run_id)

def _cleanup_completed_jobs(self):
    """Remove completed jobs from running_jobs"""
    with self.running_lock:
        completed = []
        for run_id, info in self.running_jobs.items():
            future = info.get('future')
            if future and future.done():
                completed.append(run_id)

        for run_id in completed:
            del self.running_jobs[run_id]

    # Update queue service
    if completed:
        self._update_queue_running()

def _update_queue_running(self):
    """Update queue service with current running jobs list"""
    running_list = []
    with self.running_lock:
        for run_id, info in self.running_jobs.items():
            running_list.append({
                'run_id': run_id,
                'username': info['job'].get('username'),
                'status': 'RUNNING',
                'type': info['type'],
                'dscp': info.get('dscp'),
                'started_at': info['started_at'],
                'params': info['job'].get('params', {})
            })
    self.queue.set_running(running_list)
```

**Key Changes**:
- Removed global `network_test` lock
- Added `running_jobs` dict for tracking multiple jobs (with routers)
- Added `executor_pool` ThreadPoolExecutor for parallel execution
- Scheduler now pops multiple compatible jobs based on router overlap
- Router-level conflict detection enables maximum parallelism
- DSCP allocation/deallocation handled by scheduler

### 2.3 Two-Phase Job Execution

**Critical Design Point**: Tracing step has NO conflicts and runs immediately in parallel.

**Phase A: Trace Execution** (always parallel, no queueing)
- Job submitted → trace executed immediately (or provided by user)
- Multiple trace executions can run in parallel without any synchronization
- No router conflicts during tracing (only reading topology, not testing)
- Applies to both quick and detailed analysis modes

**Phase B: Router List Extraction and Queueing** (after trace available)
- Once trace completes: extract router list
- Update queue entry with router list
- Scheduler makes conflict decisions based on router lists

**Implementation**:

**Location**: `wsgi/handlers/tsim_main_handler.py`

```python
def _handle_post(self, environ, start_response, session):
    # ... existing validation ...

    # Generate run ID
    run_id = str(uuid.uuid4())

    # Phase A: Execute trace IMMEDIATELY (no queueing, always parallel)
    routers = []
    if user_trace_data:
        # Testing mode: user provides trace
        try:
            trace_json = json.loads(user_trace_data)
            path = trace_json.get('path', [])
            routers = [hop.get('name') for hop in path if hop.get('is_router')]
        except Exception as e:
            self.logger.warning(f"Could not extract routers from trace: {e}")
    else:
        # Production mode: execute trace immediately (fully parallel, no conflicts)
        try:
            trace_result = self._execute_trace_immediately(
                source_ip, dest_ip, run_id
            )
            # Extract routers from completed trace
            path = trace_result.get('path', [])
            routers = [hop.get('name') for hop in path if hop.get('is_router')]
        except Exception as e:
            self.logger.error(f"Trace execution failed: {e}")
            # Could enqueue with empty routers (scheduler will be conservative)
            # or return error to user

    # Phase B: Enqueue job with router list
    # Now scheduler can make intelligent decisions about conflicts
    params = {
        'run_id': run_id,
        'source_ip': source_ip,
        'dest_ip': dest_ip,
        'source_port': source_port,
        'port_protocol_list': port_protocol_list,
        'user_trace_data': user_trace_data or trace_result,  # Save trace result
        'analysis_mode': analysis_mode,
        'routers': routers  # Always populated after Phase A
    }

    # Enqueue job - scheduler will pop based on router conflicts
    position = self.queue_service.enqueue(run_id, username, params)

def _execute_trace_immediately(self, source_ip: str, dest_ip: str, run_id: str) -> Dict:
    """Execute trace immediately without queueing

    Traces have no conflicts and can run in parallel without any synchronization.
    This is called BEFORE enqueueing the job.

    Args:
        source_ip: Source IP address
        dest_ip: Destination IP address
        run_id: Run identifier

    Returns:
        Trace result dict with 'path' containing router list
    """
    # Execute trace using existing trace logic
    # (details depend on current trace implementation)
    trace_result = self.executor.execute_trace_only(source_ip, dest_ip, run_id)
    return trace_result
```

**Key Points**:
- **Testing mode** (user trace): Routers extracted from user data, job enqueued with router list
- **Production mode** (no user trace): Trace executes immediately in handler BEFORE enqueueing
- **All traces parallel**: Multiple trace executions can run concurrently without any conflicts
- **Scheduler decisions**: Only made after job is enqueued with complete router list
- **No queue updates needed**: Job always enqueued with final router list

---

## Phase 3: Per-Router Locking (MANDATORY for Detailed Jobs)

### 3.1 Router Lock Design

**Lock Requirements by Job Type**:

| Job Type | Needs Router Lock? | Why? |
|----------|-------------------|------|
| **Quick** | **NO** | Each has unique DSCP, rules don't conflict, fully parallel |
| **Detailed** | **YES - MANDATORY** | Reads ALL FORWARD chain counters - any other traffic pollutes measurements |

**Critical Understanding**:
- **Quick jobs**: Use DSCP marking in PREROUTING/POSTROUTING chains
  - Each job's rules are isolated by unique DSCP value
  - Can run fully in parallel (up to 32)
  - **No router locks needed**

- **Detailed jobs**: Use FORWARD chain counters and policy
  - Read counters for ALL traffic through router (not DSCP-specific)
  - Measure: baseline counters → send traffic → final counters → calculate delta
  - ANY other traffic on that router corrupts measurements!
  - **MUST have exclusive access to router** during measurement
  - **Router locks are MANDATORY**

**Race Condition Example** (without router lock):
```
Time | Detailed Job (Router A)        | Quick Job (Router A)
-----+--------------------------------+---------------------------
T0   | Read baseline FORWARD counters |
T1   |                                | Sends traffic (pollutes!)
T2   | Read final FORWARD counters    |
T3   | Calculate delta (WRONG!)       |
```
Result: Detailed job's measurements include quick job's traffic → incorrect results!

### 3.2 Implementation (MANDATORY)

**Location**: `wsgi/services/tsim_lock_manager_service.py` (existing)

**Add router lock methods**:

```python
def acquire_router_lock(self, router_name: str, job_id: str,
                        timeout: float = 30.0) -> bool:
    """Acquire exclusive lock for router operations

    MANDATORY for detailed jobs - prevents measurement corruption!
    NOT used by quick jobs - they're DSCP-isolated.

    Args:
        router_name: Router namespace name
        job_id: Job ID requesting lock
        timeout: Maximum wait time (default: 30s for detailed jobs)

    Returns:
        True if acquired, False if timeout
    """
    lock_name = f"router_{router_name}_forward"
    return self.acquire_lock(lock_name, timeout)

def release_router_lock(self, router_name: str, job_id: str) -> bool:
    """Release router lock"""
    lock_name = f"router_{router_name}_forward"
    return self.release_lock(lock_name)

@contextmanager
def router_lock(self, router_name: str, job_id: str, timeout: float = 30.0):
    """Context manager for router-exclusive operations

    Usage (detailed jobs ONLY):
        with lock_manager.router_lock('router-hq', 'job-123'):
            # Read baseline FORWARD counters
            # Send test traffic
            # Read final FORWARD counters
            # No other job can pollute measurements!
    """
    if not self.acquire_router_lock(router_name, job_id, timeout):
        raise TimeoutError(f"Could not acquire router lock: {router_name}")
    try:
        yield
    finally:
        self.release_router_lock(router_name, job_id)
```

**Lock File Naming**: `{lock_dir}/router_{router_name}_forward.lock`

### 3.3 When Router Locks Are Acquired

**Quick jobs**: Never acquire router locks
- Operate directly on PREROUTING/POSTROUTING chains
- DSCP isolation prevents conflicts
- Fully parallel

**Detailed jobs**: MUST acquire router lock for each router
- **Before** reading baseline FORWARD counters
- **Hold** during entire measurement (baseline → test → final)
- **Release** after calculating delta
- **One router at a time per detailed job**

**Scheduler ensures**: Only one detailed job runs globally
**Router locks ensure**: Within that detailed job, each router is measured atomically

### 3.4 Configuration

```json
{
  "router_locks": {
    "enabled": true,
    "lock_dir": "<runtime_directory>/locks/routers",
    "default_timeout": 30.0,
    "max_wait": 60.0
  }
}
```

**Note**: Longer timeouts for detailed jobs (30-60s) vs quick jobs (5s) because detailed jobs need to:
1. Read baseline counters
2. Send test traffic
3. Wait for responses
4. Read final counters

---

## Phase 4: Modify `ksms_tester.py` for Batched iptables-restore

### 4.1 Architecture Change: Batched Installation

**Key Insight**: DSCP enables full parallelism - use batched iptables-restore for all services!

**OLD approach** (serialized, slow):
```
1. iptables-save (read all rules)
2. Filter/modify in memory
3. iptables-restore (write all rules)
Problem: Must be serialized per router, wastes time
```

**NEW approach** (parallel, fast):
```
1. Delete stale rules with our DSCP (if any) - batched iptables-restore
2. Add all our rules in one batched iptables-restore call
3. Read counters for our DSCP
4. Delete our rules using batched iptables-restore
Benefit: Fully parallel, no serialization needed, all operations batched!
```

### 4.2 Pre-flight: Clean Stale Rules

**Add at beginning of `prepare_router()` function**:

```python
def prepare_router(rname: str):
    """Prepare router for testing - cleanup stale rules if any"""
    if VERBOSE >= 2:
        print(f"  [{rname}] Preparing router...", file=sys.stderr)

    # PRE-FLIGHT: Remove any stale rules with our DSCP from crashed previous run
    # Uses batched iptables-restore for deletion - fully parallel!
    cleanup_stale_rules(rname, job_dscp, run_id)

def cleanup_stale_rules(rname: str, dscp: int, job_id: str):
    """Remove stale rules with our DSCP (from crashed previous runs)

    Uses batched iptables-restore for deletion - fully parallel.
    """

    # Check if any rules exist with our DSCP in PREROUTING
    result = run(['ip', 'netns', 'exec', rname, 'iptables', '-t', 'mangle', '-S', 'PREROUTING'],
                capture_output=True, text=True)

    stale_prerouting = []
    for line in result.stdout.splitlines():
        if f'TSIM_KSMS=' in line and f'--set-dscp 0x{dscp:02x}' in line:
            # Convert -A to -D for deletion
            stale_prerouting.append(line.replace('-A PREROUTING', '-D PREROUTING', 1))

    # Check POSTROUTING
    result = run(['ip', 'netns', 'exec', rname, 'iptables', '-t', 'mangle', '-S', 'POSTROUTING'],
                capture_output=True, text=True)

    stale_postrouting = []
    for line in result.stdout.splitlines():
        if f'TSIM_KSMS=' in line and f'--set-dscp 0x{dscp:02x}' in line:
            # Convert -A to -D for deletion
            stale_postrouting.append(line.replace('-A POSTROUTING', '-D POSTROUTING', 1))

    if stale_prerouting or stale_postrouting:
        if VERBOSE >= 2:
            total = len(stale_prerouting) + len(stale_postrouting)
            print(f"  [{rname}] Found {total} stale rules with DSCP {dscp}",
                  file=sys.stderr)

        # Batch delete all stale rules using iptables-restore
        lines = ['*mangle']
        lines.extend(stale_prerouting)
        lines.extend(stale_postrouting)
        lines.append('COMMIT')
        payload = '\n'.join(lines) + '\n'

        result = run(['ip', 'netns', 'exec', rname, 'iptables-restore', '-n'],
                    input=payload, text=True, capture_output=True)

        if result.returncode != 0:
            if VERBOSE >= 2:
                print(f"  [{rname}] Warning: Cleanup failed: {result.stderr}", file=sys.stderr)
        elif VERBOSE >= 2:
            print(f"  [{rname}] Cleaned {len(stale_prerouting) + len(stale_postrouting)} stale rules (batched)",
                  file=sys.stderr)
```

### 4.3 Rule Addition: Batched iptables-restore

**Use batched installation for all services on a router**:

```python
def install_all_tap_rules_batched(rname: str, dscp: int, run_id: str,
                                  services: List[Tuple[str, str, int, str]]):
    """Install all rules in one iptables-restore call for performance

    No iptables-save/restore needed - each job has unique DSCP.
    Fully parallel - multiple jobs can install rules simultaneously.

    Args:
        rname: Router namespace name
        dscp: DSCP value for this job (32-63)
        run_id: Job identifier
        services: List of (src_ip, dest_ip, port, protocol) tuples
    """

    # Build iptables-restore input
    lines = ['*mangle']

    for src_ip, dest_ip, port, protocol in services:
        # PREROUTING rule: Mark outgoing packets (source -> destination)
        lines.append(
            f'-A PREROUTING -s {src_ip} -d {dest_ip} -p {protocol} '
            f'--dport {port} -j DSCP --set-dscp 0x{dscp:02x} '
            f'-m comment --comment "TSIM_KSMS={run_id}"'
        )

        # POSTROUTING rule: Mark return packets (destination -> source)
        lines.append(
            f'-A POSTROUTING -s {dest_ip} -d {src_ip} -p {protocol} '
            f'--sport {port} -j DSCP --set-dscp 0x{dscp:02x} '
            f'-m comment --comment "TSIM_KSMS={run_id}"'
        )

    lines.append('COMMIT')
    payload = '\n'.join(lines) + '\n'

    # Apply all rules at once using iptables-restore -n (no flush)
    result = run(['ip', 'netns', 'exec', rname, 'iptables-restore', '-n'],
                input=payload, text=True, capture_output=True)

    if result.returncode != 0:
        raise RuntimeError(f"Batch install failed: {result.stderr}")

    if VERBOSE >= 2:
        print(f"  [{rname}] Installed {len(services)*2} rules (batched)",
              file=sys.stderr)
```

**Key Benefits**:
- **Single atomic operation**: All rules installed in one iptables-restore call
- **Better performance**: Eliminates per-rule overhead
- **Fully parallel**: Multiple jobs can call this simultaneously (different DSCP values)
- **No conflicts**: Each job's rules are DSCP-isolated

### 4.4 Counter Reading: Query Specific Rules

**Replace counter reading logic**:

```python
def read_counters(rname: str, dscp: int) -> Dict[str, int]:
    """Read packet counters for our DSCP rules

    Uses iptables -L with -v (verbose) to get counters.
    Fully parallel - each job reads its own DSCP counters.
    """

    counters = {'packets': 0, 'bytes': 0}

    # Read PREROUTING counters
    result = run(['ip', 'netns', 'exec', rname, 'iptables', '-t', 'mangle',
                  '-L', 'PREROUTING', '-v', '-n', '-x'],
                capture_output=True, text=True)

    # Parse output for our DSCP
    dscp_hex = f'0x{dscp:02x}'
    for line in result.stdout.splitlines():
        if dscp_hex in line and 'DSCP' in line:
            # Extract packet/byte counts from verbose output
            parts = line.split()
            if len(parts) >= 2:
                counters['packets'] += int(parts[0])
                counters['bytes'] += int(parts[1])

    # Read POSTROUTING counters
    result = run(['ip', 'netns', 'exec', rname, 'iptables', '-t', 'mangle',
                  '-L', 'POSTROUTING', '-v', '-n', '-x'],
                capture_output=True, text=True)

    for line in result.stdout.splitlines():
        if dscp_hex in line and 'DSCP' in line:
            parts = line.split()
            if len(parts) >= 2:
                counters['packets'] += int(parts[0])
                counters['bytes'] += int(parts[1])

    return counters
```

### 4.5 Rule Deletion: Batched iptables-restore

**Replace cleanup logic**:

```python
def cleanup_router(rname: str, dscp: int, run_id: str):
    """Remove our rules using batched iptables-restore - fully parallel!

    No save/restore needed - batch delete our DSCP rules
    """

    # List all rules in PREROUTING
    result = run(['ip', 'netns', 'exec', rname, 'iptables', '-t', 'mangle', '-S', 'PREROUTING'],
                capture_output=True, text=True)

    our_prerouting = []
    for line in result.stdout.splitlines():
        if f'TSIM_KSMS={run_id}' in line and f'--set-dscp 0x{dscp:02x}' in line:
            # Convert -A to -D for deletion
            our_prerouting.append(line.replace('-A PREROUTING', '-D PREROUTING', 1))

    # List all rules in POSTROUTING
    result = run(['ip', 'netns', 'exec', rname, 'iptables', '-t', 'mangle', '-S', 'POSTROUTING'],
                capture_output=True, text=True)

    our_postrouting = []
    for line in result.stdout.splitlines():
        if f'TSIM_KSMS={run_id}' in line and f'--set-dscp 0x{dscp:02x}' in line:
            # Convert -A to -D for deletion
            our_postrouting.append(line.replace('-A POSTROUTING', '-D POSTROUTING', 1))

    if our_prerouting or our_postrouting:
        # Batch delete all our rules using iptables-restore
        lines = ['*mangle']
        lines.extend(our_prerouting)
        lines.extend(our_postrouting)
        lines.append('COMMIT')
        payload = '\n'.join(lines) + '\n'

        result = run(['ip', 'netns', 'exec', rname, 'iptables-restore', '-n'],
                    input=payload, text=True, capture_output=True)

        if result.returncode != 0:
            if VERBOSE >= 2:
                print(f"  [{rname}] Warning: Rule removal failed: {result.stderr}", file=sys.stderr)
        elif VERBOSE >= 2:
            total = len(our_prerouting) + len(our_postrouting)
            print(f"  [{rname}] Removed {total} rules for DSCP {dscp} (batched)",
                  file=sys.stderr)
```

---

## Phase 5: Modify `ksms_tester.py` for Host Registry Integration

**Design Note - No Environment Variables**:

All inter-process communication now uses explicit mechanisms:
- **Job-specific values** (DSCP, run_id): Passed as command-line arguments from scheduler
- **Global config** (registry paths, lock dirs): Read from config in each process
- **No environment variables** used for IPC between service and subprocess

**Conflict handling**: Scheduler handles all job conflicts - ksms_tester.py just executes when called.

### 5.1 Add DSCP CLI Argument

**Add to argument parser**:

```python
ap.add_argument('--dscp', type=int, required=True, metavar='VALUE',
                help='DSCP value for this job (32-63, allocated by scheduler)')
```

**Note**: DSCP is allocated by `TsimSchedulerService` and passed as CLI argument.

### 5.2 Add Host Registry Support

**At top of file, add registry loading**:

```python
# Host registry integration (uses existing HostNamespaceSetup)
host_setup = None
try:
    # Get registry path directly from config
    from traceroute_simulator.core.config_loader import get_registry_paths
    registry_path = get_registry_paths().get('hosts')

    if registry_path and os.path.exists(registry_path):
        from traceroute_simulator.simulators.host_namespace_setup import HostNamespaceSetup
        host_setup = HostNamespaceSetup(verbose=VERBOSE >= 3)
        _dbg(f"[INFO] Using shared host registry: {registry_path}", 1)
except ImportError as e:
    _dbg(f"[WARN] Host registry not available - running without coordination: {e}", 1)
    host_setup = None
```

### 5.3 Modify Main Function Structure

**Simplified main - no queue coordination needed**:

```python
def main():
    global VERBOSE, job_dscp, run_id

    # ... argument parsing ...

    # Get DSCP value from command-line argument (allocated by scheduler)
    job_dscp = args.dscp

    # Generate run ID
    run_id = f"KSMS{os.getpid()}_{int(time.time() * 1000) % 100000}"

    if VERBOSE >= 1:
        print(f"[INFO] Starting quick analysis with DSCP {job_dscp}", file=sys.stderr)

    # Track acquired resources for cleanup
    acquired_hosts = []

    try:
        # Phase 1: Router preparation (with per-router locking)
        # Phase 2: Create/acquire source hosts (with registry coordination)
        acquired_hosts = create_source_hosts(routers, args.source, run_id)

        # Phase 3: Emit probes
        # Phase 4: Collect results
        # Phase 5: Output results

        sys.exit(0)

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    finally:
        # ALWAYS cleanup acquired resources
        if VERBOSE >= 1:
            print(f"[CLEANUP] Starting resource cleanup...", file=sys.stderr)

        # Cleanup hosts (with registry coordination)
        if acquired_hosts:
            cleanup_source_hosts(acquired_hosts, run_id)

        # Cleanup iptables rules on all routers (with DSCP filtering)
        for rname in routers:
            cleanup_router(rname)

        if VERBOSE >= 1:
            print(f"[CLEANUP] Resource cleanup completed", file=sys.stderr)
```

**Key Points**:
- No queue manager integration - scheduler handles conflicts
- DSCP passed as CLI argument from scheduler
- Job just executes when called - no waiting/blocking logic needed

### 5.4 Modify Host Creation with Registry

**Replace host creation logic (around line 750)**:

```python
def create_source_hosts(routers: List[str], source_ip: str, run_id: str) -> List[Tuple[str, str]]:
    """Create or acquire source hosts with registry coordination

    Returns:
        List of (host_name, router) tuples that were acquired
    """
    acquired_hosts = []

    for i, router in enumerate(routers, 1):
        src_host_name = f"source-{i}"
        host_key = f"{src_host_name}:{router}"

        # Check if host already exists
        host_list_output = tsimsh_exec("host list --json", capture_output=True)
        existing_hosts = {}
        if host_list_output:
            try:
                data = json.loads(host_list_output)
                existing_hosts = data.get('hosts', {})
            except:
                pass

        # Check if this specific host exists with correct IP and router
        host_exists = False
        for hname, hinfo in existing_hosts.items():
            if hname == src_host_name:
                connected = hinfo.get('connected_to', '')
                primary_ip = hinfo.get('primary_ip', '')
                if '/' in primary_ip:
                    ip_only = primary_ip.split('/')[0]
                    if ip_only == source_ip and connected == router:
                        host_exists = True
                        break

        # Create host if needed (physical creation first)
        should_create = not host_exists
        if should_create:
            if VERBOSE >= 2:
                print(f"  [{router}] Creating source host {src_host_name}", file=sys.stderr)

            result = tsimsh_exec(
                f"host add --name {src_host_name} --primary-ip {source_ip}/24 "
                f"--connect-to {router} --no-delay",
                verbose=VERBOSE
            )

            if result is not None:  # Error
                _dbg(f"  [{router}] Failed to create {src_host_name}: {result}", 1)
                continue

        # Acquire reference AFTER physical creation
        if host_setup:
            try:
                result = host_setup.acquire_host_ref(
                    job_id=run_id,
                    host_name=src_host_name,
                    job_type='quick',
                    dscp=job_dscp
                )

                ref_count = result['ref_count']
                conflicts = result.get('conflicts', [])

                if conflicts:
                    _dbg(f"  [{router}] WARNING: Host {src_host_name} has conflicts: {conflicts}", 1)

                if VERBOSE >= 2:
                    print(f"  [{router}] Host {src_host_name} acquired "
                          f"(ref_count={ref_count})", file=sys.stderr)

            except Exception as e:
                _dbg(f"  [{router}] WARNING: Host registry acquisition failed: {e}", 1)
                # Continue anyway - host is already created
        else:
            if VERBOSE >= 2:
                print(f"  [{router}] Reusing existing source host {src_host_name}", file=sys.stderr)

        # Track acquired host
        acquired_hosts.append((src_host_name, router))

    return acquired_hosts
```

### 5.4 Modify Host Cleanup with Registry

**Replace cleanup logic (around line 778)**:

```python
def cleanup_source_hosts(acquired_hosts: List[Tuple[str, str]], run_id: str):
    """Cleanup source hosts using registry coordination

    Args:
        acquired_hosts: List of (host_name, router) tuples to release
        run_id: Job run ID
    """
    for host_name, router in acquired_hosts:
        should_remove = False
        if host_setup:
            try:
                result = host_setup.release_host_ref(job_id=run_id, host_name=host_name)
                should_remove = result['should_remove_host']
                ref_count = result['ref_count']

                if VERBOSE >= 2:
                    print(f"  [{router}] Released host {host_name} "
                          f"(ref_count={ref_count}, remove={should_remove})", file=sys.stderr)

            except Exception as e:
                _dbg(f"  [{router}] WARNING: Host registry release failed: {e}", 1)
                should_remove = True  # Fallback to always removing
        else:
            # No registry - always attempt removal
            should_remove = True

        # Remove host if reference count reached zero
        if should_remove:
            if VERBOSE >= 2:
                print(f"  [{router}] Removing source host {host_name}", file=sys.stderr)

            result = tsimsh_exec(
                f"host remove --name {host_name} --force",
                verbose=VERBOSE
            )

            if result is not None:
                _dbg(f"  [{router}] WARNING: Failed to remove host {host_name}", 1)
        else:
            if VERBOSE >= 2:
                print(f"  [{router}] Keeping host {host_name} (in use by other jobs)", file=sys.stderr)
```

### 5.5 Cleanup Logic Already in 5.2

**Note**: Cleanup logic including `job_queue.release()` is already shown in section 5.2 above in the `finally` block.

**Wrap main execution in try/finally**:

```python
def main():
    global VERBOSE, job_dscp, run_id

    # ... argument parsing ...

    # Generate run ID
    run_id = f"KSMS{os.getpid()}_{int(time.time() * 1000) % 100000}"

    # Get DSCP value from command-line argument
    job_dscp = args.dscp

    # Track acquired resources for cleanup
    acquired_hosts = []
    dscp_allocated = False

    try:
        # ... load registries, parse services, etc. ...

        # Phase 1: Router preparation
        # ... prepare routers in parallel ...

        # Phase 2: Create/acquire source hosts
        acquired_hosts = create_source_hosts(routers, args.source, run_id)

        # Phase 3: Emit probes
        # ... emit probes from acquired hosts ...

        # Phase 4: Collect results
        # ... finalize routers and extract counters ...

        # Phase 5: Output results
        if args.json:
            print(json.dumps({'source': args.source, 'destination': args.destination,
                            'routers': results}, indent=2))
        else:
            # ... formatted output ...

        sys.exit(0)

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    finally:
        # ALWAYS cleanup acquired resources
        if VERBOSE >= 1:
            print(f"[CLEANUP] Starting resource cleanup...", file=sys.stderr)

        # Cleanup hosts (with registry coordination)
        if acquired_hosts:
            cleanup_source_hosts(acquired_hosts, run_id)

        # Cleanup iptables rules on all routers
        for rname in routers:
            cleanup_router(rname)

        # Release DSCP (happens in calling service, not here)

        if VERBOSE >= 1:
            print(f"[CLEANUP] Resource cleanup completed", file=sys.stderr)
```

---

## Phase 6: Modify `network_reachability_test_multi.py` for Host Registry

**Design Note**: `run_id` is now a required constructor parameter instead of being read from environment variable. This makes dependencies explicit and simplifies testing.

**Conflict handling**: Scheduler handles all job conflicts - detailed jobs only execute when no conflicts exist.

### 6.1 Add Host Registry Integration

**At top of MultiServiceTester class (around line 110)**:

```python
class MultiServiceTester:
    """Main class for multi-service testing."""

    def __init__(self, source_ip: str, source_port: Optional[int], dest_ip: str,
                 services: List[Tuple[int, str]], output_dir: str,
                 trace_file: Optional[str] = None, verbose: int = 0,
                 run_id: Optional[str] = None):
        self.source_ip = source_ip
        self.source_port = source_port
        self.dest_ip = dest_ip
        self.services = services
        self.output_dir = Path(output_dir)
        self.trace_file = trace_file
        self.verbose = verbose

        # ... existing initialization ...

        # Track acquired hosts (not just created hosts!)
        self.acquired_hosts = []  # List of (host_name, router) tuples

        # Initialize host setup (uses existing HostNamespaceSetup)
        try:
            from traceroute_simulator.simulators.host_namespace_setup import HostNamespaceSetup
            self.host_setup = HostNamespaceSetup(verbose=verbose >= 3)
        except ImportError:
            self.host_setup = None
            if verbose > 0:
                print("[WARN] Host registry not available", file=sys.stderr)

        # Set run ID from parameter or generate new one
        self.run_id = run_id or str(uuid.uuid4())
```

### 6.2 Simplified Run Method

**No queue coordination needed - scheduler handles conflicts**:

```python
def run(self) -> Dict[str, Any]:
    """Execute the multi-service testing workflow.

    Note: Conflict detection handled by scheduler - this method
    executes only when safe (no conflicting jobs running).
    """

    try:
        # Continue with existing workflow
        self._log_progress("start", f"Starting multi-service test for {self.dest_ip}")

        # Phase 1: Trace Analysis
        routers = self.phase1_trace_analysis()

        # Phase 2: Setup Environment (creates/acquires hosts)
        self.phase2_setup_environment(routers)

        # Phase 3: Test Services
        results = self.phase3_test_services(routers)

        # Phase 4: Generate Output
        self.phase4_generate_output(results)

        self._log_progress("complete", "Multi-service test completed successfully")
        return results

    except Exception as e:
        self._log_progress("error", f"Test failed: {e}")
        raise

    finally:
        # ALWAYS cleanup, even on error
        self.cleanup()
```

**Key Points**:
- No queue manager integration - scheduler handles conflicts
- Job executes when called - no waiting/blocking logic needed
- Conflicts prevented upstream by scheduler

### 6.3 Simplify phase2_setup_environment() Method

**No conflict checking needed - scheduler handles conflicts**:

```python
def phase2_setup_environment(self, routers: List[str]) -> None:
    """Phase 2: Setup Environment with host registry coordination.

    Note: Conflict detection handled by scheduler - this method can proceed
    safely knowing no conflicting jobs are active.
    """
    self._log_progress("PHASE2_start", "Setting up simulation environment")

    # Query existing hosts
    self._log_progress("PHASE2_host_list", "Query existing hosts")
    host_list_output = tsimsh_exec("host list --json", capture_output=True)

    existing_hosts = {}
    if host_list_output:
        try:
            data = json.loads(host_list_output)
            existing_hosts = data.get('hosts', {})
        except:
            pass

    # Add hosts to ALL routers with registry coordination
    num_routers = len(routers)
    self._log_progress("PHASE2_host_setup_start", f"Adding hosts to {num_routers} routers")

    hosts_added = 0
    router_index = 1

    for router in routers:
        # SOURCE HOST
        src_host_name = f"source-{router_index}"

        # Check if host exists
        source_exists = False
        for hname, hinfo in existing_hosts.items():
            if hname == src_host_name:
                connected = hinfo.get('connected_to', '')
                primary_ip = hinfo.get('primary_ip', '')
                if '/' in primary_ip:
                    ip_only = primary_ip.split('/')[0]
                    if ip_only == self.source_ip and connected == router:
                        source_exists = True
                        break

        # Create host if needed (no conflict check - scheduler already coordinated)
        should_create = not source_exists
        if should_create:
            self._log_progress(f"host_add_source_{router_index}",
                             f"Adding source host {src_host_name} to router {router}")
            result = tsimsh_exec(
                f"host add --name {src_host_name} --primary-ip {self.source_ip}/24 "
                f"--connect-to {router} --no-delay",
                verbose=self.verbose
            )

            if result is None:  # Success
                hosts_added += 1
                if self.verbose > 0:
                    print(f"[DEBUG] Added {src_host_name} to {router}", file=sys.stderr)
            else:
                if self.verbose > 0:
                    print(f"[DEBUG] Failed to add {src_host_name} to {router}: {result}",
                          file=sys.stderr)
                continue
        else:
            if self.verbose > 0:
                print(f"[DEBUG] Reusing existing {src_host_name} on {router}", file=sys.stderr)

        # Acquire reference AFTER physical creation
        if self.host_setup:
            try:
                result = self.host_setup.acquire_host_ref(
                    job_id=self.run_id,
                    host_name=src_host_name,
                    job_type='detailed',
                    dscp=None
                )
                if self.verbose > 0:
                    print(f"[DEBUG] Acquired {src_host_name} (ref_count={result['ref_count']})",
                          file=sys.stderr)
            except Exception as e:
                error_msg = f"Failed to acquire host reference for {src_host_name}: {e}"
                self._log_progress("PHASE2_error", error_msg)
                raise RuntimeError(error_msg)

        # Track acquired host
        self.acquired_hosts.append((src_host_name, router))

        # DESTINATION HOST (similar logic)
        dst_host_name = f"destination-{router_index}"

        # ... repeat same pattern for destination host ...

        router_index += 1

    self._log_progress("PHASE2_hosts_complete", f"Host setup completed: {hosts_added} hosts added")

    # ... continue with service startup ...
```

### 5.3 Modify Cleanup Method

**Replace cleanup() method (lines 142-160)**:

```python
def cleanup(self) -> None:
    """Clean up all created resources with registry coordination."""
    self._log_progress("cleanup_start", "Starting cleanup")

    # STOP using 'host clean --force' and 'service clean --force'!
    # These commands don't respect reference counting

    # Stop services individually
    for ip, port, protocol in self.started_services:
        try:
            tsimsh_exec(f"service stop --ip {ip} --port {port} --protocol {protocol}",
                       verbose=self.verbose)
        except Exception:
            pass

    # Release hosts via registry
    for host_name, router in self.acquired_hosts:
        if self.host_setup:
            try:
                result = self.host_setup.release_host_ref(job_id=self.run_id, host_name=host_name)
                should_remove = result['should_remove_host']

                if should_remove:
                    # Reference count reached zero - physically remove host
                    tsimsh_exec(f"host remove --name {host_name} --force",
                               verbose=self.verbose)
                else:
                    if self.verbose > 0:
                        print(f"[DEBUG] Keeping {host_name} (ref_count={result['ref_count']})",
                              file=sys.stderr)
            except Exception as e:
                if self.verbose > 0:
                    print(f"[ERROR] Failed to release host {host_name}: {e}", file=sys.stderr)
        else:
            # No registry - always attempt removal
            try:
                tsimsh_exec(f"host remove --name {host_name} --force", verbose=self.verbose)
            except Exception:
                pass

    # Clear tracking lists
    self.started_services = []
    self.acquired_hosts = []

    self._log_progress("cleanup_complete", "Cleanup completed")
```

### 5.4 Scheduler Coordination

**Note**: Job coordination is handled by the scheduler (Phase 2) before jobs are started. The scheduler's `pop_compatible_jobs()` method checks for router-level conflicts and only starts jobs that won't conflict with currently running jobs. Jobs remain in the queue until they can run safely.

**Calling code** (in executor/scheduler):

```python
# Scheduler calls executor.execute() only for compatible jobs
# No conflict checking needed in individual test scripts
result = executor.execute(
    run_id, source_ip, dest_ip, source_port,
    port_protocol_list, user_trace_data, analysis_mode
)
```


---

## Phase 7: Modify `tsim_ksms_service.py` Integration

### 7.1 Update KSMS Service to Pass DSCP

**Note**: No imports or constructor changes needed. The host registry is managed by `ksms_tester.py` which uses `HostNamespaceSetup` directly.

**Modify _execute_ksms_scan() method**:

```python
def _execute_ksms_scan(self, source_ip: str, dest_ip: str, services: List,
                       job_dscp: int, run_id: str) -> Dict[str, Any]:
    """Execute KSMS bulk scan with registry coordination"""

    # Build ksms_tester command
    script_path = self._get_ksms_tester_path()

    # Build command arguments (all config passed via args, not env vars)
    cmd_args = [
        sys.executable, script_path,
        '--source', source_ip,
        '--destination', dest_ip,
        '--ports', self._build_port_spec(services),
        '--dscp', str(job_dscp),
        '--json',
        '-v' if self.config.get('verbose', False) else ''
    ]

    # Execute with timeout
    try:
        result = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            timeout=self.timeout
        )

        if result.returncode != 0:
            raise RuntimeError(f"KSMS scan failed: {result.stderr}")

        # Parse JSON output
        ksms_results = json.loads(result.stdout)
        return ksms_results

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"KSMS scan timed out after {self.timeout} seconds")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse KSMS output: {e}")
```

### 6.4 Enhance Error Handling

**Wrap execute_quick_analysis() with proper cleanup**:

```python
def execute_quick_analysis(self, params: Dict[str, Any], progress_callback=None) -> Dict[str, Any]:
    """Execute KSMS quick analysis with full error handling"""

    run_id = params['run_id']
    job_dscp = None

    try:
        # Allocate DSCP
        job_dscp = self.dscp_registry.allocate_dscp(run_id)
        if job_dscp is None:
            raise RuntimeError("No DSCP values available")

        self.logger.info(f"Allocated DSCP {job_dscp} for job {run_id}")

        # Execute KSMS scan (host registry handled by ksms_tester.py)
        ksms_results = self._execute_ksms_scan(
            params['source_ip'],
            params['dest_ip'],
            params['services'],
            job_dscp,
            run_id
        )

        # Process and return results
        service_format_results = self._convert_to_service_format(ksms_results, params)
        pdf_result = self._generate_summary_pdf(service_format_results, params, ksms_results)

        return {
            'status': 'completed',
            'results': service_format_results,
            'pdf_path': pdf_result.get('pdf_path')
        }

    except Exception as e:
        self.logger.error(f"Quick analysis failed for {run_id}: {e}")
        raise

    finally:
        # ALWAYS release DSCP allocation
        if job_dscp is not None:
            released = self.dscp_registry.release_dscp(run_id)
            if released:
                self.logger.info(f"Released DSCP {job_dscp} for job {run_id}")
            else:
                self.logger.warning(f"Failed to release DSCP for job {run_id}")

        # Host cleanup is handled by ksms_tester.py
```

---

## Phase 8: Update Admin Queue Viewer for Multiple Running Jobs

### 8.1 Modify Backend Handlers

**File**: `wsgi/handlers/tsim_queue_admin_handler.py`

**Current Behavior**: Returns single `running` job

**Change to**: Return list of `running_jobs`

```python
def handle(self, environ, start_response):
    # ... auth checks ...

    jobs = self.queue_service.list_jobs()

    # Get multiple running jobs (not just one)
    running_jobs = self.queue_service.get_running()  # Returns list

    # Enrich each running job with progress
    for job in running_jobs:
        try:
            from services.tsim_progress_tracker import TsimProgressTracker
            tracker = TsimProgressTracker(self.config)
            prog = tracker.get_progress(job.get('run_id', '')) or {}
            job['percent'] = int(prog.get('overall_progress', 0))
            phases = prog.get('phases', [])
            job['phase'] = phases[-1]['phase'] if phases else 'UNKNOWN'
        except Exception:
            pass

    response = {
        'success': True,
        'running_jobs': running_jobs,  # Changed from 'running'
        'queue': jobs,
        'history': self._get_history(),
        'locks': {
            'scheduler_leader': self.lock_manager.is_locked('scheduler_leader')
            # Removed 'network_test' lock (no longer used)
        }
    }
    return self.json_response(start_response, response)
```

**File**: `wsgi/handlers/tsim_admin_queue_stream_handler.py`

**Similar changes for SSE streaming**:

```python
def _build_payload(self) -> Dict[str, Any]:
    # Get multiple running jobs
    running_jobs = self.queue_service.get_running()

    # Enrich each with progress
    for job in running_jobs:
        # ... add progress, DSCP info ...

    return {
        'running_jobs': running_jobs,  # Changed from 'running'
        'queue': jobs,
        'history': self._history(),
        'locks': {
            'scheduler_leader': self.lock_manager.is_locked('scheduler_leader')
            # Removed 'network_test'
        }
    }
```

### 8.2 Update Frontend (admin_queue.html)

**Display multiple running jobs as table/list**:

```html
<div id="running-section">
    <h3>Running Jobs (<span id="running-count">0</span>)</h3>
    <table id="running-jobs-table">
        <thead>
            <tr>
                <th>Run ID</th>
                <th>User</th>
                <th>Type</th>
                <th>DSCP</th>
                <th>Progress</th>
                <th>Phase</th>
                <th>Started</th>
            </tr>
        </thead>
        <tbody id="running-jobs-body">
            <!-- Populated by JavaScript -->
        </tbody>
    </table>
</div>
```

**Update JavaScript to handle multiple jobs**:

```javascript
function updateRunningJobs(data) {
    const running_jobs = data.running_jobs || [];
    document.getElementById('running-count').textContent = running_jobs.length;

    const tbody = document.getElementById('running-jobs-body');
    tbody.innerHTML = '';

    running_jobs.forEach(job => {
        const row = tbody.insertRow();
        row.insertCell().textContent = job.run_id.substring(0, 8) + '...';
        row.insertCell().textContent = job.username || 'unknown';
        row.insertCell().textContent = job.type || 'unknown';

        // Show DSCP for quick jobs
        const dscpCell = row.insertCell();
        if (job.type === 'quick' && job.dscp) {
            dscpCell.textContent = job.dscp;
            dscpCell.classList.add('dscp-value');
        } else {
            dscpCell.textContent = 'N/A';
        }

        // Progress bar
        const progressCell = row.insertCell();
        const percent = job.percent || 0;
        progressCell.innerHTML = `<div class="progress-bar"><div class="progress-fill" style="width: ${percent}%">${percent}%</div></div>`;

        // Phase
        row.insertCell().textContent = job.phase || 'UNKNOWN';

        // Started time
        const started = new Date(job.started_at * 1000);
        row.insertCell().textContent = started.toLocaleTimeString();
    });
}
```

**Add CSS for styling**:

```css
.dscp-value {
    font-family: monospace;
    font-weight: bold;
    color: #0066cc;
}

#running-jobs-table {
    width: 100%;
    border-collapse: collapse;
}

#running-jobs-table th,
#running-jobs-table td {
    padding: 8px;
    text-align: left;
    border-bottom: 1px solid #ddd;
}

.progress-bar {
    width: 100%;
    height: 20px;
    background-color: #f0f0f0;
    border-radius: 10px;
    overflow: hidden;
}

.progress-fill {
    height: 100%;
    background-color: #4CAF50;
    text-align: center;
    line-height: 20px;
    color: white;
    font-size: 12px;
}
```

---

## Phase 9: Command Line Standalone Support

### 7.1 Add CLI Arguments

**Add to argument parser in ksms_tester.py**:

```python
ap.add_argument('--dscp', type=int, required=True, metavar='VALUE',
                help='DSCP value for this job (32-63, typically allocated by DSCP registry)')
ap.add_argument('--no-registry', action='store_true',
                help='Disable registry coordination (may cause conflicts)')
```

**Note**: Registry and lock paths are read from config, not passed as arguments. DSCP is allocated by parent and passed explicitly.

### 7.2 Conditional Registry Loading

**Replace registry initialization**:

```python
def load_registries(args):
    """Load registries from config (not environment variables)"""
    host_setup = None
    lock_manager = None

    if args.no_registry:
        _dbg("[INFO] Registry coordination disabled by user", 1)
        return None, None

    try:
        # Get registry path from config only
        from traceroute_simulator.core.config_loader import get_registry_paths
        registry_path = get_registry_paths().get('hosts')

        if not registry_path or not os.path.exists(registry_path):
            _dbg("[WARN] Registry path not configured or doesn't exist", 1)
            _dbg("[WARN] Concurrent execution may cause conflicts!", 1)
            return None, None

        # Use existing HostNamespaceSetup for host registry
        from traceroute_simulator.simulators.host_namespace_setup import HostNamespaceSetup
        host_setup = HostNamespaceSetup(verbose=VERBOSE >= 3)

        # Load lock manager service
        from wsgi.services.tsim_lock_manager_service import TsimLockManagerService
        from wsgi.services.tsim_config_service import TsimConfigService
        config = TsimConfigService()
        lock_manager = TsimLockManagerService(config)

        _dbg(f"[INFO] Using shared host registry and lock manager", 1)

    except ImportError as e:
        _dbg(f"[WARN] Registry services not available: {e}, using standalone mode", 1)
        host_setup = None
        lock_manager = None

    return host_setup, lock_manager
```

### 7.3 Fallback Mode Warnings

**Add warning messages for standalone mode**:

```python
if host_setup is None:
    print("""
WARNING: Running without host registry coordination!

This may cause conflicts if multiple KSMS jobs run concurrently.
Symptoms: Incorrect UNKNOWN results, missing iptables rules, host removal errors.

To enable coordination:
  1. Ensure config_loader.get_registry_paths()['hosts'] is configured
  2. Run via WSGI service (recommended)
  3. Use --no-registry flag to suppress this warning

Proceeding in standalone mode...
""", file=sys.stderr)
```

---

## Phase 10: Testing and Validation

### 8.1 Unit Tests

**Create test files**:

#### `tests/test_host_registry.py`
```python
import unittest
import tempfile
import json
from pathlib import Path
from traceroute_simulator.simulators.host_namespace_setup import HostNamespaceSetup

class TestHostRegistry(unittest.TestCase):
    def setUp(self):
        """Create temporary test registry file"""
        self.temp_dir = tempfile.mkdtemp()
        self.registry_path = Path(self.temp_dir) / 'test_host_registry.json'
        self.host_setup = HostNamespaceSetup(verbose=False)
        # Override registry path for testing
        self.host_setup.host_registry_file = self.registry_path

    def test_reference_counting(self):
        """Test basic reference counting"""
        host_name = 'source-1'

        # First acquisition
        result1 = self.host_setup.acquire_host_ref('job1', host_name, 'quick', dscp=32)
        self.assertEqual(result1['ref_count'], 1)
        self.assertEqual(result1['action'], 'initialized')

        # Second acquisition (same host, different job)
        result2 = self.host_setup.acquire_host_ref('job2', host_name, 'quick', dscp=33)
        self.assertEqual(result2['ref_count'], 2)
        self.assertEqual(result2['action'], 'acquired')

        # First release
        release1 = self.host_setup.release_host_ref('job1', host_name)
        self.assertFalse(release1['should_remove_host'])
        self.assertEqual(release1['ref_count'], 1)

        # Second release
        release2 = self.host_setup.release_host_ref('job2', host_name)
        self.assertTrue(release2['should_remove_host'])
        self.assertEqual(release2['ref_count'], 0)

    def test_conflict_detection(self):
        """Test quick vs detailed conflict detection"""
        host_name = 'source-1'

        # Acquire as quick job
        self.host_setup.acquire_host_ref('job1', host_name, 'quick', dscp=32)

        # Try to acquire as detailed job - should detect conflict
        conflict = self.host_setup.check_host_conflicts(host_name, 'detailed')
        self.assertTrue(conflict['has_conflict'])
        self.assertEqual(conflict['conflict_type'], 'detailed_vs_quick')

    def test_stale_cleanup(self):
        """Test cleanup of stale references"""
        # Test cleanup_stale_job_refs() method
        cleaned_count = self.host_setup.cleanup_stale_job_refs()
        self.assertGreaterEqual(cleaned_count, 0)
```

#### `tests/test_ksms_concurrent.py`
```python
import unittest
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

class TestKsmsConcurrent(unittest.TestCase):
    def test_two_quick_jobs_same_router(self):
        """Test two quick jobs running concurrently on shared router"""

        # Job 1: Test port 80/tcp with DSCP 32
        cmd1 = [
            'python3', 'src/simulators/ksms_tester.py',
            '-s', '10.1.1.100',
            '-d', '10.2.1.200',
            '-P', '80/tcp',
            '--dscp', '32',
            '--json'
        ]

        # Job 2: Test port 443/tcp with DSCP 33 (different service, same router)
        cmd2 = [
            'python3', 'src/simulators/ksms_tester.py',
            '-s', '10.1.1.100',
            '-d', '10.2.1.200',
            '-P', '443/tcp',
            '--dscp', '33',
            '--json'
        ]

        # Execute concurrently (no environment variables needed)
        with ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(subprocess.run, cmd1,
                                    capture_output=True, text=True)
            time.sleep(0.1)  # Slight stagger to trigger race window
            future2 = executor.submit(subprocess.run, cmd2,
                                    capture_output=True, text=True)

            result1 = future1.result()
            result2 = future2.result()

        # Both should succeed
        self.assertEqual(result1.returncode, 0)
        self.assertEqual(result2.returncode, 0)

        # Parse results
        json1 = json.loads(result1.stdout)
        json2 = json.loads(result2.stdout)

        # Verify no UNKNOWN results (would indicate missing rules)
        for router in json1['routers']:
            for service in router['services']:
                self.assertNotEqual(service['result'], 'UNKNOWN',
                    "Job 1 should not have UNKNOWN results due to race condition")

        for router in json2['routers']:
            for service in router['services']:
                self.assertNotEqual(service['result'], 'UNKNOWN',
                    "Job 2 should not have UNKNOWN results due to race condition")

    def test_quick_then_detailed(self):
        """Test detailed job waits for quick job to complete"""
        # Start quick job
        # Start detailed job (should wait or error)
        # Verify no conflicts
        pass
```

### 8.2 Integration Test Scenarios

**Test Matrix**:

| Test | Job 1 Type | Job 2 Type | Expected Result |
| ---- | ---------- | ---------- | --------------- |
| 1 | Quick (DSCP 32, port 80) | Quick (DSCP 33, port 443) | Both succeed |
| 2 | Quick (DSCP 32) | Quick (DSCP 33) on different router | Both succeed (parallel) |
| 3 | Quick (DSCP 32) | Detailed (starting) | Detailed waits or errors |
| 4 | Detailed (running) | Quick (starting) | Quick blocked with error |
| 5 | Quick (crashed mid-run) | Quick (starting, same DSCP) | Stale rules cleaned, succeeds |
| 6 | 32 Quick jobs (exhaust DSCP) | Quick job 33 | Job 33 queued |

### 8.3 Stress Test

**Create `tests/stress_test_concurrent.sh`**:

```bash
#!/bin/bash
# Stress test: Launch 10 concurrent quick analysis jobs

echo "Starting stress test: 10 concurrent quick analysis jobs"

# Launch 10 jobs in background with unique DSCP values
for i in {1..10}; do
    dscp=$((31 + i))  # DSCP 32-41
    echo "Starting job $i (DSCP $dscp)..."
    python3 src/simulators/ksms_tester.py \
        -s 10.1.1.100 \
        -d 10.2.1.200 \
        -P "80/tcp,443/tcp" \
        --dscp $dscp \
        --json > /tmp/ksms_job_${i}.json 2>&1 &

    pids[$i]=$!
    sleep 0.1  # Stagger starts slightly
done

echo "All jobs launched, waiting for completion..."

# Wait for all jobs
failed=0
for i in {1..10}; do
    wait ${pids[$i]}
    exitcode=$?
    if [ $exitcode -ne 0 ]; then
        echo "Job $i FAILED with exit code $exitcode"
        failed=$((failed + 1))
    else
        echo "Job $i completed successfully"

        # Check for UNKNOWN results
        unknown_count=$(jq '[.routers[].services[] | select(.result == "UNKNOWN")] | length' /tmp/ksms_job_${i}.json)
        if [ "$unknown_count" -gt 0 ]; then
            echo "WARNING: Job $i has $unknown_count UNKNOWN results (possible race condition)"
            failed=$((failed + 1))
        fi
    fi
done

# Check host registry state
echo ""
echo "Checking host registry state..."
# Get registry path from config (this should match your deployment config)
registry_file=$(python3 -c "from traceroute_simulator.core.config_loader import get_registry_paths; print(get_registry_paths().get('hosts', ''))")
if [ -f "$registry_file" ]; then
    ref_counts=$(jq '[.[] | .ref_count // 0] | add' "$registry_file")
    echo "Total ref_count: $ref_counts (should be 0)"
    if [ "$ref_counts" -ne 0 ]; then
        echo "ERROR: Registry not properly cleaned up!"
        failed=$((failed + 1))
    fi
else
    echo "No registry file found at: $registry_file (might be OK if disabled)"
fi

echo ""
if [ $failed -eq 0 ]; then
    echo "SUCCESS: All 10 jobs completed without errors"
    exit 0
else
    echo "FAILURE: $failed jobs had errors or issues"
    exit 1
fi
```

---

## Phase 11: Documentation Updates

### 9.1 Update `analysis_modes_comparison.md`

**Add new section after Appendix A**:

```markdown
## Appendix B: Concurrency and Race Condition Prevention

### Overview

The system implements multiple mechanisms to prevent race conditions when concurrent quick analysis jobs run, or when quick and detailed analysis jobs coexist.

### Host Reference Counting

**Problem**: Multiple jobs may need the same source/destination host simultaneously.

**Solution**: Host Registry Service with reference counting semaphore.

**Mechanism**:
1. Job A acquires host: ref_count = 1, host created
2. Job B acquires same host: ref_count = 2, host reused
3. Job A releases host: ref_count = 1, host kept
4. Job B releases host: ref_count = 0, host removed

**Implementation**: Host registry file path from `config_loader.get_registry_paths()['hosts']` with fcntl locking

### Per-Router iptables Locking

**Problem**: Concurrent iptables-save/restore operations cause rule corruption.

**Solution**: Per-router file locks for iptables critical sections.

**Mechanism**:
- Lock acquired before iptables-save
- Lock held during rule modification
- Lock released after iptables-restore
- Timeout: 5 seconds per router (configurable)

**Implementation**: `{lock_dir}/router_{name}_iptables.lock` where `lock_dir` comes from `config.get('router_locks.lock_dir')`

### DSCP-Based Rule Filtering

**Problem**: iptables-restore removes ALL TSIM_KSMS rules, including other jobs.

**Solution**: Filter rules by DSCP value, not just presence of TSIM_KSMS marker.

**Old Code**:
```python
if 'TSIM_KSMS=' in line:
    continue  # WRONG: Removes ALL jobs' rules
```

**New Code**:
```python
if 'TSIM_KSMS=' in line and f'--dscp 0x{dscp:02x}' in line:
    continue  # CORRECT: Only removes OUR rules
```

### Scheduler-Based Concurrency Management

**Quick vs Quick**: Allowed (isolated by DSCP + router locks)
**Quick vs Detailed**: **QUEUED** - Detailed waits in queue until all quick complete
**Detailed vs Quick**: **QUEUED** - Quick waits in queue until detailed completes
**Detailed vs Detailed**: **QUEUED** - One at a time (FIFO)

**Implementation**: Enhanced existing `TsimSchedulerService` + `TsimQueueService` (Phase 2).

**Mechanism**:
1. User submits job → `TsimQueueService.enqueue()` with `analysis_mode`
2. Scheduler polls queue with `pop_compatible_jobs(running_jobs)`
3. Queue intelligently selects compatible jobs:
   - If nothing running: Pop first job (quick: up to 32, detailed: 1)
   - If quick running: Pop more quick (up to 32 total)
   - If detailed running: Pop nothing (wait for detailed to finish)
4. Scheduler allocates DSCP for quick jobs
5. Scheduler executes jobs in parallel via ThreadPoolExecutor
6. On completion: Scheduler releases DSCP and updates running_jobs

**No job-level coordination** - scheduler handles all conflicts upstream. Jobs execute immediately when called.

### Recovery Mechanisms

**Stale Host Cleanup**:
- Registry checks if process (PID) still alive
- Stale entries removed automatically
- Timeout: 1 hour

**Stale DSCP Rules**:
- Pre-flight check removes rules with allocated DSCP
- Handles crashed jobs that didn't cleanup

**Lock Staleness**:
- Lock files have timestamps
- Locks older than session_timeout are cleaned
```

### 9.2 Add Code Documentation

**Add docstrings to key functions explaining race prevention**:

```python
def build_insert_payload_from_existing(existing_save: str, insert_lines: List[str],
                                       dscp: int, run_id: str, with_counters: bool = True) -> str:
    """Build iptables-restore payload preserving other jobs' rules.

    CRITICAL RACE CONDITION PREVENTION:
    This function filters rules by DSCP value, not just TSIM_KSMS presence.
    This ensures concurrent jobs don't remove each other's iptables rules.

    Previous implementation removed ALL TSIM_KSMS rules, causing Job A's rules
    to be deleted by Job B when they shared a router, resulting in UNKNOWN
    results for Job A.

    Args:
        existing_save: Current iptables-save output
        insert_lines: New rules to insert
        dscp: This job's DSCP value (used for filtering)
        run_id: This job's run ID (for comments)
        with_counters: Include packet counters in output

    Returns:
        Complete iptables-restore payload with counters
    """
```

---

## Phase 12: Configuration Changes

### 10.1 Update `config.json`

**Add new configuration sections**:

**Note**: All paths should be configured in deployment configuration. Never hardcode paths in code.

**Note**: Host registry path is already defined in `config_loader.get_registry_paths()['hosts']`. The following additional config sections are needed:

```json
{
  "router_locks": {
    "enabled": true,
    "lock_dir": "<runtime_directory>/locks/routers",
    "default_timeout": 5.0,
    "max_wait": 30.0
  },

  "dscp_registry": {
    "enabled": true,
    "dscp_range_min": 32,
    "dscp_range_max": 63,
    "allocation_timeout": 3600
  },

  "concurrency": {
    "max_quick_jobs": 32,
    "stale_cleanup_enabled": true,
    "scheduler_poll_interval": 0.5
  }
}
```

**Configuration Notes**:
- `lock_dir`: Should be in a tmpfs or fast storage. Typically set via deployment config.
- All registry paths come from `config_loader.get_registry_paths()` which reads from deployment configuration.
- Never hardcode system paths like `/dev/shm/` or `/var/opt/` in code - always use config.
- `max_quick_jobs`: Maximum concurrent quick analysis jobs (default: 32, matches DSCP range)
- `scheduler_poll_interval`: How often scheduler checks for new compatible jobs (seconds)

**Scheduler Behavior**:
- Jobs enqueued via `TsimQueueService.enqueue()` with `analysis_mode` field
- Scheduler pops compatible jobs using `pop_compatible_jobs(running_jobs)`
- Quick jobs run in parallel (up to 32), detailed jobs run exclusively
- DSCP allocated by scheduler, passed to ksms_tester.py as CLI argument
- No job-level coordination needed - scheduler manages all conflicts

### 10.2 Configuration Validation

**Add validation in TsimConfigService**:

```python
def validate_concurrency_config(self):
    """Validate concurrency-related configuration"""

    # Validate DSCP range
    dscp_min = self.get('dscp_registry.dscp_range_min', 32)
    dscp_max = self.get('dscp_registry.dscp_range_max', 63)

    if not (0 <= dscp_min <= 63 and 0 <= dscp_max <= 63):
        raise ValueError(f"Invalid DSCP range: {dscp_min}-{dscp_max}")

    if dscp_max - dscp_min + 1 < 1:
        raise ValueError("DSCP range must have at least 1 value")

    # Validate max quick jobs
    max_quick = self.get('concurrency.max_quick_jobs', 32)
    if max_quick > (dscp_max - dscp_min + 1):
        logger.warning(f"max_quick_jobs ({max_quick}) exceeds available DSCP values "
                      f"({dscp_max - dscp_min + 1})")
```

---

## Implementation Order and Timeline

### Week 1: Foundation
- **Day 1-2**: Phase 1 (Host Registry Enhancement)
  - Enhance `host_namespace_setup.py` with reference counting
  - Add `acquire_host_ref()` and `release_host_ref()` methods
  - Update `_batch_register_host()` to initialize ref_count fields
  - Unit tests

- **Day 3-4**: Phase 2 (Scheduler/Queue Enhancement)
  - Enhance `tsim_queue_service.py` with `analysis_mode` and `routers` fields
  - Implement `pop_compatible_jobs()` with router-level conflict detection
  - Enhance `tsim_scheduler_service.py` with parallel execution and router tracking
  - Add router extraction in `tsim_main_handler.py`
  - Remove global `network_test` lock
  - Unit tests

- **Day 5**: Phase 3 (Router Locks - MANDATORY for Detailed)
  - Extend `TsimLockManagerService`
  - Add per-router locking methods (for detailed jobs only)
  - Unit tests

### Week 2: Core Modifications
- **Day 6-7**: Phase 4 (ksms_tester.py - Batched iptables-restore)
  - Replace iptables save/restore with batched iptables-restore
  - Add `cleanup_stale_rules()`, `install_all_tap_rules_batched()`, `read_counters()`, `cleanup_router()`
  - Use batched rule installation (all services at once per router)
  - Add DSCP filtering in all operations
  - Add pre-flight stale cleanup
  - Modify host creation/cleanup logic with HostNamespaceSetup
  - No queue manager integration (scheduler handles conflicts)
  - Manual and integration testing

- **Day 8-9**: Phase 5 (detailed analysis modifications)
  - Modify `network_reachability_test_multi.py`
  - Add MANDATORY router lock acquisition for each router
  - Update host acquisition/release logic with HostNamespaceSetup
  - No queue manager integration (scheduler handles conflicts)
  - Integration testing

### Week 3: Service Integration
- **Day 10**: Phase 6 (KSMS service integration)
  - Modify `tsim_ksms_service.py`
  - Remove environment variables
  - Pass DSCP as CLI argument
  - Error handling improvements

- **Day 11**: Phase 7 (standalone support)
  - Add CLI arguments (--dscp, --no-registry)
  - Fallback mode implementation
  - Warning messages

### Week 4: Testing and Documentation
- **Day 12-13**: Phase 8 (comprehensive testing)
  - Unit tests (host registry, scheduler, router locks)
  - Integration tests (concurrent jobs with router conflicts)
  - Stress testing (10+ concurrent jobs)

- **Day 14**: Phase 9 & 10 (documentation and configuration)
  - Update analysis_modes_comparison.md
  - Add code documentation
  - Configuration changes (job_queue section)
  - Code review

---

## Risk Mitigation Strategies

### Backward Compatibility
- **Host registry defaults to pass-through** if disabled in config
- Old behavior preserved for single-threaded execution
- Graceful degradation if registry unavailable
- Standalone mode works without WSGI services

### Deadlock Prevention
- **Lock acquisition order**: DSCP → Host Registry → Router Lock
- Always use timeouts on all locks (no infinite waits)
- Never hold multiple router locks simultaneously
- Release locks in finally blocks

### Recovery from Failures
- Registry cleanup runs on every allocation attempt
- Stale process detection via PID checking (`os.kill(pid, 0)`)
- Lock files have timestamps for staleness detection
- Scheduler handles conflicts with router-level checking (no job polling)
- Pre-flight checks remove stale iptables rules

### Performance Impact
- Host registry lookups: < 1ms (in-memory + file)
- Router lock acquisition: < 5ms (file lock)
- DSCP allocation: < 1ms
- Total overhead per job: < 100ms (negligible)

### Data Corruption Prevention
- Atomic file writes using temporary file + rename
- fcntl locks prevent concurrent registry modifications
- iptables-restore is atomic per router
- Validation checks on registry load

---

## Success Criteria

### Functional Requirements
- Multiple quick jobs run concurrently without interference
- Quick and detailed jobs coexist safely (router-level conflict detection)
- No UNKNOWN results due to race conditions
- All hosts properly reference counted
- Graceful error messages on conflicts
- Zero data corruption in registries

### Performance Requirements
- Performance impact < 5% per job
- Lock acquisition < 5 seconds per router
- Registry operations < 10ms per call
- No degradation with 32 concurrent jobs

### Reliability Requirements
- All existing tests pass
- New stress tests pass 100 iterations
- Recovery from crash within 1 hour
- Zero leaked resources after 1000 jobs

### Usability Requirements
- Clear error messages on conflicts
- Automatic queuing with scheduler-based coordination (no job polling)
- No configuration required for basic usage
- Standalone mode works without WSGI

---

## Rollback Plan

If critical issues arise:

1. **Immediate**: Set `host_registry.enabled = false` in config
2. **Within 1 hour**: Revert ksms_tester.py changes to ALL rule removal
3. **Within 4 hours**: Revert all code changes
4. **Restore from backup**: Registry JSON files from configured registry paths

**Rollback indicators**:
- More than 10% UNKNOWN results
- Host removal errors in >5% of jobs
- Lock timeouts in >1% of jobs
- Registry corruption detected

---

## Appendix: File Modification Summary

### New Files (4)
1. `tests/test_host_registry.py`
2. `tests/test_router_locks.py`
3. `tests/test_ksms_concurrent.py`
4. `tests/stress_test_concurrent.sh`

### Modified Files (10)
1. `src/simulators/host_namespace_setup.py`
   - Line 695: `_batch_register_host()` - Initialize ref_count and jobs fields
   - Add `acquire_host_ref()` method
   - Add `release_host_ref()` method
   - Add `check_host_conflicts()` method
   - Add `get_host_ref_count()` method
   - Add `cleanup_stale_job_refs()` method
   - Add `get_active_jobs_for_host()` method

2. `wsgi/handlers/tsim_main_handler.py` **ENHANCED**
   - Execute trace immediately in handler BEFORE enqueueing (production mode)
   - Extract router list from user trace (testing mode) or completed trace (production mode)
   - Enqueue job with complete router list for scheduler conflict detection
   - Add `_execute_trace_immediately()` method

3. `wsgi/services/tsim_queue_service.py` **ENHANCED**
   - Add `analysis_mode` field to queued jobs
   - Add `routers` field to queued jobs (for router-level conflict detection)
   - Add `pop_compatible_jobs(running_jobs)` method with router overlap checking
   - Add `set_running(jobs)` method (replaces `set_current`)
   - Add `get_running()` method (replaces `get_current`)
   - Add `remove_running(run_id)` method

4. `wsgi/services/tsim_scheduler_service.py` **ENHANCED**
   - Remove global `network_test` lock
   - Add `running_jobs` dict for tracking multiple jobs with router lists
   - Add `executor_pool` ThreadPoolExecutor for parallel execution
   - Replace `_leader_loop()` with router-aware parallel job management
   - Add `_start_job()`, `_execute_job_wrapper()`, `_cleanup_completed_jobs()`
   - DSCP allocation/deallocation integrated
   - Track routers per job for conflict detection

5. `src/simulators/ksms_tester.py`
   - Replace iptables save/restore with batched iptables-restore
   - Add pre-flight cleanup of stale rules
   - Add `cleanup_stale_rules()`, `install_all_tap_rules_batched()`, `read_counters()`, `cleanup_router()`
   - Use batched iptables-restore for rule installation (all services at once)
   - Add DSCP filtering in all iptables operations
   - Add `--dscp` CLI argument
   - Add registry integration via HostNamespaceSetup
   - No queue manager integration (scheduler handles conflicts)

6. `wsgi/services/tsim_lock_manager_service.py`
   - Add `acquire_router_lock()` method
   - Add `release_router_lock()` method
   - Add `router_lock()` context manager

7. `wsgi/services/tsim_executor.py` or `tsim_hybrid_executor.py`
   - Add `execute_trace_only()` method for immediate trace execution
   - Trace execution without queueing (called from handler)
   - Returns trace result with router path

8. `wsgi/scripts/network_reachability_test_multi.py`
   - Lines 109-140: Add HostNamespaceSetup initialization
   - Simplified `run()` method (no queue coordination)
   - Lines 187-299: `phase2_setup_environment()` - Simplified (no conflict checks)
   - Lines 142-160: `cleanup()` - Add registry coordination via HostNamespaceSetup

9. `wsgi/services/tsim_ksms_service.py`
   - Modify `_execute_ksms_scan()` - Pass DSCP as CLI argument (from scheduler)
   - Modify `execute_quick_analysis()` - Enhanced error handling

10. `wsgi/handlers/tsim_queue_admin_handler.py` **ENHANCED**
    - Change `running` → `running_jobs` (list)
    - Remove `network_test` lock check
    - Display router information for each running job

11. `wsgi/handlers/tsim_admin_queue_stream_handler.py` **ENHANCED**
    - Change `running` → `running_jobs` (list)
    - Add DSCP display for quick jobs
    - Add router list display for all jobs

12. `wsgi/config.json`
    - Add `router_locks` section
    - Add `concurrency` section (with scheduler_poll_interval)
    - DSCP registry already exists

### Frontend Files (1)
1. `wsgi/static/admin_queue.html` (or similar admin viewer)
   - Update to display multiple running jobs in table
   - Add DSCP column for quick jobs
   - Add router list column for all jobs
   - Update JavaScript to handle `running_jobs` array

### Documentation Files (2)
1. `docs/analysis_modes_comparison.md`
   - Add Appendix B: Concurrency and Race Condition Prevention

2. `docs/race_condition_elimination_plan.md`
   - This document

**Total**: 19 files (4 new tests, 12 modified backend, 1 modified frontend, 2 documentation)

---

## End of Plan
