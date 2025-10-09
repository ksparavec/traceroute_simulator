# Queue/Scheduler Integration Plan

## Current Architecture Analysis

### Job Flow
```
User -> Main Handler -> Queue Service (enqueue) -> Scheduler (background thread)
                                                           |
                                            acquires GLOBAL 'network_test' lock
                                                           |
                                              Executor -> Hybrid Executor
                                                           |
                                    +----------------------+----------------------+
                                    |                                             |
                              'quick' mode                                 'detailed' mode
                                    |                                             |
                      TsimKsmsService (ksms_tester.py)              MultiServiceTester
```

### Existing Components

**TsimQueueService** (`wsgi/services/tsim_queue_service.py`)
- FIFO queue for user job submissions
- File-backed JSON at `<data_dir>/queue/queue.json`
- Methods: `enqueue()`, `pop_next()`, `get_current()`, `list_jobs()`
- Currently stores: `run_id`, `username`, `status`, `params`, `created_at`

**TsimSchedulerService** (`wsgi/services/tsim_scheduler_service.py`)
- Background thread with leader election
- Pops jobs with `queue.pop_next()`
- **PROBLEM**: Acquires global `network_test` lock - prevents ALL concurrency
- Calls `executor.execute(params)` with `analysis_mode` parameter

**TsimDscpRegistry** (`wsgi/services/tsim_dscp_registry.py`)
- Already exists for DSCP allocation (32-63)
- Methods: `allocate_dscp(run_id)`, `release_dscp(run_id)`

**Admin Queue Viewer** (`wsgi/handlers/tsim_queue_admin_handler.py`, `tsim_admin_queue_stream_handler.py`)
- Shows single `running` job + queued jobs + history
- SSE streaming for real-time updates
- Displays: `run_id`, `username`, `status`, `phase`, `percent`, locks

## Integration Requirements

### Goal
Replace global serialization with intelligent parallel scheduling:
- **Quick jobs**: Run up to 32 concurrently (DSCP-isolated)
- **Detailed jobs**: Run one at a time (exclusive)
- **Conflict rules**:
  - Quick + Quick: Allowed (parallel, different DSCP)
  - Quick + Detailed: Queue detailed until all quick complete
  - Detailed + Quick: Queue quick until detailed completes
  - Detailed + Detailed: Queue (one at a time)

### Changes Needed

1. **Enhance Queue Service**
   - Add `analysis_mode` to queued job metadata
   - Change `pop_next()` → `pop_compatible_jobs()`
     - Returns list of compatible jobs based on current running jobs
     - Up to 32 quick jobs if no detailed running
     - 1 detailed job if no jobs running
     - Empty list if conflicts exist

2. **Enhance Scheduler Service**
   - Remove global `network_test` lock
   - Track `running_jobs` dict: `{run_id: {'type': str, 'dscp': int, 'started_at': float}}`
   - Pop multiple compatible jobs
   - Execute in parallel using ThreadPoolExecutor
   - Clean up running_jobs on completion

3. **Update Admin Viewer**
   - Change `running` (single) → `running_jobs` (list)
   - Show DSCP values for quick jobs
   - Show job type (quick/detailed)
   - Update frontend HTML/JS to display multiple running jobs

4. **Integration with Race Condition Plan**
   - Keep Phase 1: Host Registry (reference counting)
   - Keep Phase 3: Router Locks (per-router iptables locking)
   - Keep Phase 4: DSCP filtering in ksms_tester.py
   - **Remove Phase 2**: Job Queue Manager Service (redundant with enhanced scheduler)
   - Update Phase 5: network_reachability_test_multi.py (no queue manager needed)

## Detailed Design

### 1. Enhanced TsimQueueService

**Add to job metadata when enqueuing:**
```python
def enqueue(self, run_id: str, username: str, params: Dict[str, Any]) -> int:
    jobs.append({
        'run_id': run_id,
        'username': username,
        'created_at': time.time(),
        'status': 'QUEUED',
        'params': params,
        'analysis_mode': params.get('analysis_mode', 'detailed')  # NEW
    })
```

**New method for intelligent popping:**
```python
def pop_compatible_jobs(self, running_jobs: Dict[str, Dict]) -> List[Dict[str, Any]]:
    """Pop compatible jobs based on current running jobs.

    Args:
        running_jobs: Dict of {run_id: {'type': 'quick'|'detailed', 'dscp': int}}

    Returns:
        List of job dicts to execute
    """
    with self._lock():
        q = self._load_queue()
        jobs = q.get('jobs', [])
        if not jobs:
            return []

        # Determine what's currently running
        has_detailed = any(j['type'] == 'detailed' for j in running_jobs.values())
        quick_count = sum(1 for j in running_jobs.values() if j['type'] == 'quick')

        # If detailed job running, nothing can start
        if has_detailed:
            return []

        # If quick jobs running, only more quick jobs can start
        if quick_count > 0:
            max_quick = 32
            slots_available = max_quick - quick_count
            if slots_available <= 0:
                return []

            # Pop up to slots_available quick jobs
            quick_jobs = [j for j in jobs if j.get('analysis_mode') == 'quick']
            to_pop = quick_jobs[:slots_available]

            # Remove from queue
            remaining = [j for j in jobs if j not in to_pop]
            q['jobs'] = remaining
            q['updated_at'] = time.time()
            self._save_queue(q)
            return to_pop

        # Nothing running - check first job
        first_job = jobs[0]
        if first_job.get('analysis_mode') == 'quick':
            # Pop multiple quick jobs
            quick_jobs = [j for j in jobs if j.get('analysis_mode') == 'quick']
            to_pop = quick_jobs[:32]

            remaining = [j for j in jobs if j not in to_pop]
            q['jobs'] = remaining
            q['updated_at'] = time.time()
            self._save_queue(q)
            return to_pop
        else:
            # Pop one detailed job
            jobs.pop(0)
            q['jobs'] = jobs
            q['updated_at'] = time.time()
            self._save_queue(q)
            return [first_job]
```

**New tracking for multiple running jobs:**
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

### 2. Enhanced TsimSchedulerService

**Track running jobs:**
```python
class TsimSchedulerService:
    def __init__(self, config_service, queue_service, progress_tracker, executor, lock_manager):
        # ... existing init ...
        self.running_jobs = {}  # {run_id: {'type': str, 'dscp': int, 'future': Future, 'started_at': float}}
        self.running_lock = threading.Lock()
        self.executor_pool = ThreadPoolExecutor(max_workers=33, thread_name_prefix='job-executor')
```

**New leader loop without global lock:**
```python
def _leader_loop(self):
    """While leader, manage parallel job execution"""
    while not self._stop_event.is_set():
        # Check for completed jobs
        self._cleanup_completed_jobs()

        # Pop compatible jobs
        with self.running_lock:
            running_jobs_info = {
                run_id: {'type': info['type'], 'dscp': info.get('dscp')}
                for run_id, info in self.running_jobs.items()
            }

        jobs_to_start = self.queue.pop_compatible_jobs(running_jobs_info)

        if not jobs_to_start:
            time.sleep(0.5)
            continue

        # Start all compatible jobs
        for job in jobs_to_start:
            self._start_job(job)

        time.sleep(0.25)

def _start_job(self, job: Dict[str, Any]):
    """Start a single job in thread pool"""
    run_id = job.get('run_id')
    analysis_mode = job.get('analysis_mode', 'detailed')

    # Allocate DSCP for quick jobs
    dscp = None
    if analysis_mode == 'quick':
        from services.tsim_dscp_registry import TsimDscpRegistry
        dscp_registry = TsimDscpRegistry(self.config)
        dscp = dscp_registry.allocate_dscp(run_id)
        if dscp is None:
            self.logger.error(f"No DSCP available for quick job {run_id}")
            return

    # Add to running jobs
    with self.running_lock:
        self.running_jobs[run_id] = {
            'type': analysis_mode,
            'dscp': dscp,
            'started_at': time.time(),
            'job': job
        }

    # Update queue tracking
    running_list = []
    with self.running_lock:
        for rid, info in self.running_jobs.items():
            running_list.append({
                'run_id': rid,
                'username': info['job'].get('username'),
                'status': 'RUNNING',
                'type': info['type'],
                'dscp': info.get('dscp'),
                'started_at': info['started_at'],
                'params': info['job'].get('params', {})
            })
    self.queue.set_running(running_list)

    # Submit to thread pool
    future = self.executor_pool.submit(self._execute_job_wrapper, job, dscp)

    with self.running_lock:
        self.running_jobs[run_id]['future'] = future

def _execute_job_wrapper(self, job: Dict[str, Any], dscp: Optional[int]) -> Dict[str, Any]:
    """Wrapper for job execution with error handling"""
    run_id = job.get('run_id')
    try:
        # Inject DSCP into params for quick jobs
        params = job.get('params', {})
        if dscp is not None:
            params['job_dscp'] = dscp

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
        # Cleanup
        analysis_mode = job.get('analysis_mode', 'detailed')
        if analysis_mode == 'quick' and dscp is not None:
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
            self.queue.remove_running(run_id)
```

### 3. Update Admin Viewer

**Backend changes in `tsim_queue_admin_handler.py`:**
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
            # Remove 'network_test' lock (no longer used)
        }
    }
    return self.json_response(start_response, response)
```

**Frontend changes needed:**
- Modify `admin_queue.html` to display multiple running jobs in a list/table
- Show job type (Quick/Detailed), DSCP value (for quick), progress %
- Update SSE handler similarly

### 4. Integration with Race Condition Plan

**Modified Phase Structure:**

- **Phase 1**: Host Registry Enhancement (keep as-is)
  - Reference counting for host reuse
  - Methods: `acquire_host_ref()`, `release_host_ref()`, `check_host_conflicts()`

- **Phase 2**: Per-Router Iptables Locking (renumber from Phase 3)
  - Lock dir from config
  - Per-router file locks

- **Phase 3**: DSCP Rule Filtering in ksms_tester.py (renumber from Phase 4)
  - Filter by DSCP value
  - Pre-flight cleanup
  - **Pass DSCP via `--dscp` CLI argument** (not environment variable)

- **Phase 4**: Host Registry Integration - ksms_tester.py (keep from old Phase 4)
  - Acquire/release host references
  - Use HostNamespaceSetup

- **Phase 5**: Host Registry Integration - network_reachability_test_multi.py (keep from old Phase 5)
  - Acquire/release host references
  - **No queue manager needed** - scheduler handles conflicts upstream

- **Phase 6**: Scheduler/Queue Integration (NEW)
  - Implement enhanced scheduler with parallel execution
  - Remove global lock
  - DSCP allocation in scheduler

- **Phase 7**: WSGI Service Updates
  - Update tsim_ksms_service to accept DSCP as parameter
  - No environment variables

- **Phase 8**: Admin Viewer Updates
  - Multiple running jobs display
  - Job type and DSCP display

## Summary of Key Changes

1. **Remove**: Standalone job queue manager service (Phase 2 from original plan)
2. **Enhance**: Existing TsimQueueService with intelligent job selection
3. **Enhance**: Existing TsimSchedulerService with parallel execution
4. **Keep**: Host registry, router locks, DSCP filtering
5. **Update**: Admin viewer for multiple running jobs
6. **Simplify**: No separate queue manager - scheduler handles everything

## Benefits

1. **Simpler architecture** - uses existing queue/scheduler infrastructure
2. **Better visibility** - admin can see all running jobs
3. **Proven code** - leverages existing DSCP registry and queue service
4. **Cleaner integration** - scheduler controls execution, not individual jobs
