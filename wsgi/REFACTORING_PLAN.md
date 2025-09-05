# WSGI Performance Refactoring Plan - Hybrid Approach (HIGH-RISK/HIGH-GAIN)

## Executive Summary

**Complete rewrite** of WSGI implementation to eliminate all subprocess spawning and implement a hybrid execution model using direct execution, thread pools for I/O-bound tasks, and process pools for CPU-bound operations. **All existing WSGI code will be removed immediately** - no backwards compatibility, no gradual rollout.

## Current Architecture Problems

### 1. Unnecessary Subprocess Layers
```
WSGI Handler → Background Executor → subprocess.Popen → Python Script → Imports → Execution
     ↓              ↓                      ↓                ↓            ↓          ↓
  (Persistent)  (Creates script)    (NEW PROCESS)    (Overhead)   (Overhead)  (Finally!)
```

### 2. Unnecessary Shell/Wrapper Scripts
- CGI needs shell wrappers for virtualenv activation
- WSGI doesn't need this - it's already in the correct Python environment
- Current WSGI still creates intermediate scripts unnecessarily

## Refactoring Goals

1. **DELETE all existing WSGI subprocess code immediately**
2. **Remove ALL script generation** - execute Python code directly
3. **Implement hybrid execution model from scratch:**
   - Direct execution for lightweight operations
   - Thread pool for I/O-bound operations (tsimsh commands)
   - Process pool for CPU-bound operations (PDF generation, packet analysis)
4. **Target: 40-60% performance improvement or complete failure**

## Feasibility Assessment for 100% Feature Parity

### Current WSGI Feature Inventory

After analyzing the current WSGI implementation:

**11 Handlers:** Each must be fully functional
1. **tsim_login_handler** - Authentication (KEEP AS IS - works fine)
2. **tsim_logout_handler** - Session cleanup (KEEP AS IS - works fine)  
3. **tsim_main_handler** - Core test execution (COMPLETE REWRITE - 500+ lines)
4. **tsim_progress_handler** - Progress status JSON (MINOR CHANGES)
5. **tsim_progress_stream_handler** - SSE streaming (MAJOR REWRITE)
6. **tsim_pdf_handler** - PDF serving (KEEP AS IS - already fixed)
7. **tsim_cleanup_handler** - Resource cleanup (ADAPT to new model)
8. **tsim_test_config_handler** - Test configuration (KEEP AS IS)
9. **tsim_services_config_handler** - Services configuration (KEEP AS IS)
10. **tsim_base_handler** - Base class (KEEP AS IS - 350+ lines)
11. **Static file handlers** - CSS/JS serving (UNCHANGED)

**13 Services:** Core functionality
1. **tsim_auth_service** - PAM authentication (KEEP AS IS)
2. **tsim_background_executor** - 650 lines (DELETE ENTIRELY)
3. **tsim_config_service** - Configuration loading (KEEP AS IS)
4. **tsim_executor** - 500 lines (90% DELETE, REWRITE)
5. **tsim_lock_manager_service** - Resource locking (KEEP AS IS)
6. **tsim_logger_service** - Logging infrastructure (KEEP AS IS)
7. **tsim_performance_middleware** - Request timing (KEEP AS IS)
8. **tsim_port_parser_service** - Port parsing (KEEP AS IS)
9. **tsim_progress_tracker** - Progress tracking (COMPLETE REWRITE)
10. **tsim_session_manager** - Session handling (KEEP AS IS)
11. **tsim_timing_service** - Performance metrics (KEEP AS IS)
12. **tsim_validator_service** - Input validation (KEEP AS IS)
13. **NEW: tsim_hybrid_executor** - Core execution engine (NEW 400+ lines)

### Critical Features That MUST Work

1. **Authentication/Authorization** ✓ (No changes needed)
   - PAM login
   - Session management
   - Cookie handling

2. **Core Test Execution** ⚠️ (Complete rewrite needed)
   - Trace execution via tsimsh
   - Multi-service reachability testing
   - Port/protocol configuration
   - Result collection

3. **Progress Tracking** ⚠️ (Major rewrite needed)
   - Real-time SSE streaming
   - Progress phase updates
   - Error reporting
   - Completion detection

4. **PDF Generation** ⚠️ (Needs integration)
   - Summary page generation
   - Individual service PDFs
   - PDF merging
   - PDF serving

5. **Resource Management** ✓ (Minor changes)
   - Cleanup of old runs
   - Memory management
   - Process pool lifecycle

### Complexity Assessment

**KEEP AS IS (60% of code):**
- 7 handlers × ~100 lines = 700 lines
- 8 services × ~150 lines = 1,200 lines
- **Total: ~1,900 lines unchanged**

**COMPLETE REWRITE (40% of code):**
- tsim_main_handler: 500 lines → 200 lines
- tsim_executor: 500 lines → 50 lines  
- tsim_background_executor: 650 lines → DELETE
- tsim_progress_tracker: 200 lines → 100 lines
- tsim_progress_stream_handler: 200 lines → 150 lines
- NEW tsim_hybrid_executor: 0 → 400 lines
- **Total: 2,050 lines → 900 lines**

### Time Requirements for 100% Features

**Day 1: Deletion & Setup (8 hours)**
- Delete subprocess code (2 hours)
- Create hybrid executor skeleton (3 hours)
- Set up thread/process pools (3 hours)

**Day 2-3: Core Execution (16 hours)**
- Trace execution direct call (4 hours)
- Reachability test integration (6 hours)
- Error handling & logging (3 hours)
- Testing & debugging (3 hours)

**Day 4: Progress Tracking (8 hours)**
- In-memory progress store (2 hours)
- SSE streaming rewrite (3 hours)
- Progress callback integration (3 hours)

**Day 5: PDF Generation (8 hours)**
- Process pool PDF execution (3 hours)
- Summary page integration (2 hours)
- PDF merging in pool (2 hours)
- Testing all services (1 hour)

**Day 6-7: Integration & Testing (16 hours)**
- End-to-end testing (4 hours)
- Performance benchmarking (2 hours)
- Bug fixes (6 hours)
- Documentation (2 hours)
- Final testing (2 hours)

**Total: 56 hours of focused development**

### Required Functionality (100% Feature Parity Checklist)

**MUST WORK from Day 1 of deployment:**

1. **User Authentication**
   - Login with PAM credentials
   - Session persistence across requests
   - Logout functionality
   - Session timeout handling

2. **Test Configuration**
   - Source/destination IP input
   - Port and protocol selection
   - Service configuration (22/tcp, 443/tcp, etc.)
   - User-provided trace file upload

3. **Test Execution Pipeline**
   - Trace discovery (tsimsh trace command)
   - Host creation in namespaces
   - Service startup (netcat listeners)
   - Reachability testing per service
   - Packet count analysis
   - Result aggregation

4. **Progress Tracking**
   - Real-time progress updates via SSE
   - Phase completion notifications
   - Error reporting during execution
   - Progress persistence for page refresh

5. **PDF Generation**
   - Summary page with test parameters
   - Individual service test results
   - Network diagrams and paths
   - Packet analysis visualization
   - Merged final report

6. **Result Management**
   - PDF viewing in browser
   - PDF download capability
   - Test history per session
   - Cleanup of old test data

7. **Error Handling**
   - Timeout management (2-minute limit)
   - Resource cleanup on failure
   - User-friendly error messages
   - Logging for debugging

8. **Performance Requirements**
   - Handle multiple concurrent users
   - Complete single service test < 30s
   - No memory leaks
   - Clean process termination

### FEASIBILITY VERDICT: CHALLENGING BUT POSSIBLE

**Can deliver 100% features in 1 week? YES, with caveats:**

1. **Must work 8-10 hours/day** on implementation
2. **No exploratory coding** - must know exactly what to build
3. **Copy CGI logic verbatim** where possible
4. **No optimization in week 1** - just make it work
5. **Test continuously** - no big bang integration

**Risk factors:**
- Progress tracking SSE rewrite (most complex)
- Process pool management (memory/zombie processes)
- Thread safety for shared resources
- Integration with existing handlers

**Success factors:**
- 60% of code stays unchanged
- CGI code provides working reference
- Clear interfaces between components
- Can test incrementally

## Detailed Refactoring Steps

### Phase 1: Complete Code Removal (DESTRUCTIVE)

#### Step 1.1: Delete All Subprocess-Based Code FIRST

**Files to DELETE entirely:**
- `wsgi/services/tsim_background_executor.py` - 600+ lines of subprocess spawning
- `wsgi/scripts/tsim_reachability_tester.py` - wrapper around multi-service tester
- `wsgi/scripts/tsim_multi_service_tester.py` - duplicate of CGI functionality

**Sections to REMOVE from existing files:**
- `wsgi/services/tsim_executor.py`:
  - Remove `tsim_execute_async()` method
  - Remove `background_executor` initialization
  - Remove all subprocess.Popen references
  
- `wsgi/handlers/tsim_main_handler.py`:
  - Remove all async task creation
  - Remove background executor calls
  - Remove progress file monitoring

**This will break EVERYTHING - that's intentional**

#### Step 1.2: Create New Executor Architecture
**File:** `wsgi/services/tsim_hybrid_executor.py` (NEW)

```python
class TsimHybridExecutor:
    """
    Hybrid executor using:
    - Direct execution for lightweight tasks
    - ThreadPoolExecutor for I/O-bound tasks (tsimsh commands)
    - ProcessPoolExecutor for CPU-bound tasks (PDF generation)
    """
    
    def __init__(self):
        self.thread_pool = ThreadPoolExecutor(max_workers=4)
        self.process_pool = ProcessPoolExecutor(max_workers=2)
        # Pre-import heavy modules to avoid reimport costs
        self._preload_modules()
    
    def execute_trace(self, params) -> Future:
        """Execute trace - I/O bound, use thread pool"""
        return self.thread_pool.submit(self._run_trace_direct, params)
    
    def execute_reachability(self, params) -> Future:
        """Execute reachability test - I/O bound, use thread pool"""
        return self.thread_pool.submit(self._run_reachability_direct, params)
    
    def execute_pdf_generation(self, params) -> Future:
        """Generate PDF - CPU bound, use process pool"""
        return self.process_pool.submit(self._run_pdf_direct, params)
```

#### Step 1.2: Create Direct Execution Methods
**Location:** Within `tsim_hybrid_executor.py`

These methods will run directly without creating scripts or spawning processes:

```python
def _run_trace_direct(self, params):
    """Direct trace execution without subprocess"""
    # Import here stays in memory for thread pool reuse
    from scripts.tsim_multi_service_tester import tsimsh_exec
    
    # Execute tsimsh directly - no subprocess wrapper
    trace_command = f"trace -s {params['source_ip']} -d {params['dest_ip']} -j -vv"
    return tsimsh_exec(trace_command, capture_output=True)

def _run_reachability_direct(self, params):
    """Direct reachability test without subprocess"""
    from scripts.tsim_reachability_tester import TsimReachabilityTester
    
    # Create tester and run directly
    tester = TsimReachabilityTester(**params)
    return tester.run()

def _run_pdf_direct(self, params):
    """Direct PDF generation without subprocess"""
    # This runs in a process pool worker
    # Heavy imports like matplotlib stay loaded in worker
    from scripts.visualize_reachability import main as generate_pdf
    return generate_pdf(params)
```

### Phase 2: Build New Implementation from Scratch

#### Step 2.1: Rewrite Main Handler Completely
**File:** `wsgi/handlers/tsim_main_handler.py`

**DELETE everything and rewrite:**

```python
class TsimMainHandler:
    def __init__(self):
        # Single hybrid executor for all operations
        self.executor = TsimHybridExecutor()
    
    def handle(self, environ, start_response):
        # Parse parameters (keep this part)
        params = self.parse_params(environ)
        
        # Execute DIRECTLY - no async, no background tasks
        result = self.executor.execute_full_test(params)
        
        # Return immediately with results or future reference
        return self.json_response(start_response, result)
```

#### Step 2.2: New Executor Service
**File:** `wsgi/services/tsim_executor.py`

**DELETE everything and replace with:**
```python
class TsimExecutor:
    def __init__(self, config):
        self.hybrid = TsimHybridExecutor(config)
    
    def execute(self, run_id, source_ip, dest_ip, port_protocol_list):
        # Direct execution, no subprocess
        return self.hybrid.execute_full_test({
            'run_id': run_id,
            'source_ip': source_ip,
            'dest_ip': dest_ip,
            'port_protocol_list': port_protocol_list
        })
```

### Phase 3: Reimplement Core Functionality

#### Step 3.1: Progress Tracking - Complete Rewrite
**File:** `wsgi/services/tsim_progress_tracker.py`

**DELETE file-based progress tracking, replace with:**
```python
class TsimProgressTracker:
    def __init__(self):
        # In-memory progress tracking
        self.progress = {}
        self.lock = threading.Lock()
    
    def update(self, run_id, phase, message):
        with self.lock:
            if run_id not in self.progress:
                self.progress[run_id] = []
            self.progress[run_id].append({
                'phase': phase,
                'message': message,
                'timestamp': time.time()
            })
    
    def get_progress(self, run_id):
        with self.lock:
            return self.progress.get(run_id, [])
```

**No more file writes, no more JSON parsing overhead**

#### Step 3.2: Implement Full Test Pipeline
**Location:** `tsim_hybrid_executor.py`

```python
def execute_full_test(self, params):
    """Execute complete test pipeline without subprocesses"""
    run_id = params['run_id']
    
    # Step 1: Execute trace (I/O bound - thread)
    trace_future = self.thread_pool.submit(self._run_trace_direct, params)
    trace_result = trace_future.result(timeout=120)
    
    # Step 2: Setup hosts and run reachability tests (I/O bound - thread)
    params['trace_file'] = trace_result['output_file']
    reach_future = self.thread_pool.submit(self._run_reachability_direct, params)
    reach_result = reach_future.result(timeout=300)
    
    # Step 3: Generate PDFs (CPU bound - process pool)
    params['results'] = reach_result
    pdf_future = self.process_pool.submit(self._run_pdf_direct, params)
    pdf_result = pdf_future.result(timeout=60)
    
    return {
        'trace': trace_result,
        'reachability': reach_result,
        'pdf': pdf_result
    }
```

### Phase 4: Aggressive Optimization

#### Step 4.1: Eliminate Virtualenv Activation
**Remove from all WSGI code:**
```python
# CGI needs this:
bash_cmd = f'source {venv_activate} && {cmd_str}'
subprocess.run(['bash', '-c', bash_cmd])

# WSGI doesn't - it's already in the right environment
```

#### Step 4.2: Remove Shell Script Wrappers
**Files to modify:**
- Remove bash command building
- Remove shell=True from any subprocess calls
- Call Python functions directly instead of via CLI

#### Step 4.3: Simplify tsimsh Execution
**Current (with wrapper):**
```python
# CGI style with subprocess
cmd = ['bash', '-c', f'echo "{command}" | tsimsh']
result = subprocess.run(cmd)
```

**New (direct):**
```python
# Direct execution for WSGI
import subprocess
# tsimsh still needs subprocess but no bash wrapper
result = subprocess.run(['tsimsh'], input=command, text=True)
```

### Phase 5: Optimize Module Loading

#### Step 5.1: Pre-import Heavy Modules
**Location:** `wsgi/app.wsgi` startup

```python
# Pre-import heavy modules at WSGI startup
def application(environ, start_response):
    # These imports happen once at startup
    import matplotlib
    matplotlib.use('Agg')  # Set backend before importing pyplot
    import matplotlib.pyplot  # Heavy import - do once
    import numpy  # If used
    import networkx  # If used
    
    # Store in application context for reuse
    app.matplotlib = matplotlib
    app.pyplot = matplotlib.pyplot
```

#### Step 5.2: Cache Class Instances
**Location:** `tsim_hybrid_executor.py`

```python
class TsimHybridExecutor:
    def __init__(self):
        # Cache reusable instances
        self._tester_cache = {}
        
    def _get_tester(self, key, **params):
        """Get cached tester instance or create new"""
        if key not in self._tester_cache:
            from scripts.tsim_reachability_tester import TsimReachabilityTester
            self._tester_cache[key] = TsimReachabilityTester(**params)
        return self._tester_cache[key]
```

### Phase 6: Progress Tracking Updates

#### Step 6.1: Update Progress Tracking
**Issue:** Current progress tracking expects subprocess with file-based communication

**Solution:** Use queue-based or callback-based progress

```python
class ProgressCallback:
    def __init__(self, run_id, progress_tracker):
        self.run_id = run_id
        self.tracker = progress_tracker
    
    def update(self, phase, message):
        # Direct call instead of file write
        self.tracker.log_phase(self.run_id, phase, message)

# Pass callback to execution methods
def _run_reachability_direct(self, params, progress_callback):
    tester = TsimReachabilityTester(**params)
    tester.set_progress_callback(progress_callback.update)
    return tester.run()
```

### Phase 7: Testing (After Complete Rewrite)

#### Step 7.1: Acceptance Criteria
**No gradual rollout - either it works or it doesn't:**
1. Single service test must complete in < 20s (down from 28s)
2. Three service test must complete in < 35s (down from 50s)
3. Memory usage must not exceed 500MB per request
4. All tests must pass or we revert to CGI

#### Step 7.2: Test Approach
1. **Delete old WSGI tests** - they're testing the wrong thing
2. Write new tests for direct execution
3. Benchmark against CGI, not old WSGI
4. **Binary decision:** Deploy new WSGI or stay on CGI

## Expected Code Removal

### Files to DELETE IMMEDIATELY (Day 1):
1. **wsgi/services/tsim_background_executor.py** - ENTIRE FILE (~650 lines)
2. **wsgi/scripts/tsim_reachability_tester.py** - ENTIRE FILE (~200 lines)
3. **wsgi/scripts/tsim_multi_service_tester.py** - ENTIRE FILE (~800 lines)
4. **wsgi/scripts/tsim_packet_count_analyzer.py** - ENTIRE FILE (if exists)

### Files to GUT and REWRITE:
1. **wsgi/services/tsim_executor.py** - Delete 90%, keep config (~50 lines kept of 500)
2. **wsgi/handlers/tsim_main_handler.py** - Delete 80%, rebuild (~100 lines kept of 500)
3. **wsgi/services/tsim_progress_tracker.py** - Complete rewrite (~100 lines)

### Total Code Impact:
- **~2,650 lines DELETED**
- **~400 lines of NEW code**
- **Net reduction: ~2,250 lines (85% less code)**
- **Complexity reduction: 90%**

## Performance Impact Estimation

### Current Execution Time Breakdown (28s total):
```
Process Creation:     0.3s  → 0.0s  (eliminated)
Script Generation:    0.1s  → 0.0s  (eliminated)
Module Import:        0.3s  → 0.0s  (cached)
Trace Execution:      8.0s  → 8.0s  (unchanged - tsimsh)
Host Setup:          12.0s  → 12.0s (unchanged - tsimsh)
Service Test:         5.0s  → 5.0s  (unchanged - tsimsh)
PDF Generation:       2.0s  → 1.2s  (process pool)
I/O Operations:       0.3s  → 0.3s  (already optimized)
```

### Expected New Time: 26.5s initially, potentially 18-20s with further optimization
- **Initial improvement: 5-10% (1.5-2.8s)**
- **After caching optimizations: 30-40% (8-11s)**

## Risk Assessment

### HIGH RISK - ACCEPTED:
- **Complete system rewrite** - no fallback within WSGI
- **All existing WSGI code deleted** - no rollback without Git
- **Binary outcome** - either 40% faster or complete failure
- **Production stays on CGI** until new WSGI proves itself

### Mitigation Strategy:
- **CGI remains untouched** - production fallback
- **WSGI development isolated** - no impact until deployed
- **Clear success criteria** - measurable performance targets
- **Fast fail approach** - know within 1 week if it works

### What Could Go Wrong:
1. **Memory leaks from pools** - Monitor and set limits
2. **Thread safety issues** - Use locks where needed
3. **Progress tracking breaks** - Rewrite from scratch
4. **PDF generation fails** - Test thoroughly

### Recovery Plan:
- If new WSGI fails → Stay on CGI
- If partially works → Fix or abandon
- If successful → Deploy and deprecate CGI
- **No middle ground, no technical debt**

## Implementation Timeline (AGGRESSIVE)

### Day 1: Scorched Earth
- **Morning:** Delete all subprocess code
- **Afternoon:** WSGI is completely broken
- **Status:** Nothing works

### Day 2-3: Core Rebuild
- Implement TsimHybridExecutor
- Basic trace and reachability working
- Direct execution, no subprocesses

### Day 4-5: Full Pipeline
- PDF generation via process pool
- Progress tracking rewrite
- End-to-end test working

### Day 6-7: Testing & Decision
- Performance benchmarks
- Compare with CGI baseline
- **GO/NO-GO Decision**

### Week 2 (if GO):
- Bug fixes and optimization
- Memory profiling
- Production deployment prep

### Week 2 (if NO-GO):
- Document lessons learned
- Stay on CGI
- Consider alternative approaches

## Success Criteria (HARD TARGETS)

1. **Performance:** 
   - Single service: < 20s (current: 28s) = **28% improvement minimum**
   - Three services: < 35s (current: 50s) = **30% improvement minimum**
   - **Fail if less than 25% improvement**

2. **Reliability:** 
   - 100% test completion rate
   - No subprocess zombies
   - Clean resource cleanup

3. **Memory:** 
   - < 500MB per request
   - No memory leaks after 100 requests
   - Process pools properly managed

4. **Code Quality:** 
   - 2,000+ lines removed
   - Zero subprocess.Popen calls
   - All execution direct or pooled

## Next Steps

1. **Backup current WSGI** (for archaeological purposes)
2. **Create branch: `wsgi-nuclear-refactor`**
3. **Day 1: DELETE everything listed in Phase 1**
4. **Day 2: Start building from scratch**
5. **Day 7: GO/NO-GO decision**

## Why This Is High-Risk

### Technical Risks

1. **SSE Streaming Complexity**
   - Current implementation uses file-based progress tracking
   - New implementation needs thread-safe in-memory tracking
   - Must maintain connection for 2+ minutes
   - Browser compatibility issues possible

2. **Process Pool Management**
   - Never tested in this codebase
   - Potential for zombie processes
   - Memory usage could spike
   - Cleanup complexity on failures

3. **Thread Safety**
   - CGI never had to worry about threads
   - Shared resources need locking
   - Race conditions possible
   - Deadlock risks with multiple locks

4. **Direct tsimsh Integration**
   - Currently wrapped in multiple layers
   - Direct subprocess.run() to tsimsh untested
   - Error handling will be different
   - Timeout management crucial

5. **No Incremental Testing**
   - Can't test main handler without executor
   - Can't test executor without pools
   - Can't test pools without progress tracking
   - Everything must work together

### Why It Could Still Succeed

1. **CGI provides working reference**
   - All logic is proven
   - Can copy algorithms verbatim
   - Test cases already exist

2. **60% of code unchanged**
   - Authentication works
   - Session management works
   - Configuration works
   - Only execution path changes

3. **Clear architecture**
   - Thread pool for I/O
   - Process pool for CPU
   - Direct execution for lightweight
   - No ambiguity in design

4. **Fast feedback**
   - Know within hours if approach works
   - Can test core execution immediately
   - Performance gains measurable quickly

## Final Notes

**This is a complete rewrite, not a refactor.** We're not improving the existing WSGI code - we're deleting it and starting over with the correct architecture. The existing WSGI implementation is fundamentally flawed and cannot be fixed incrementally.

**Production continues on CGI** until we prove the new WSGI works. There's no risk to production, only to development time.

**Success means:**
- 30-40% faster execution
- 85% less code
- Proper WSGI architecture

**Failure means:**
- Stay on CGI
- Learn from the attempt
- Consider other approaches (FastCGI, pure async, etc.)

---
*Plan Created: 2025-09-05*
*Target Completion: 1 week for GO/NO-GO*
*Risk Level: HIGH (accepted)*
*Expected ROI: HIGH (30-40% performance improvement) or TOTAL LOSS*
*Philosophy: "Move fast and break things, then fix them properly"*