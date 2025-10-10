# Review: Race Condition Elimination Plan vs. Current WSGI/KSMS Code

## Executive Summary

The plan correctly identifies key races (iptables rules clobbering and host lifecycle conflicts), but several pitfalls remain:
- Current WSGI scheduler uses a single global lock. This is appropriate for detailed analysis to ensure no routers are touched during a run, but it blocks quick job parallelism unless made conditional.
- ksms_tester still removes all TSIM_KSMS= rules per router, which will clobber other jobs without per router locks.
- The plan's no env vars for IPC conflicts with how DSCP is currently passed to the KSMS subprocess.
- Host reference counting is not implemented in the code; the plan needs precise atomic update semantics and rollback.

This review highlights mismatches between the plan and the present code, details additional concurrency and robustness issues, and recommends concrete changes.

---

## Plan Pitfalls and Gaps

### 1) DSCP Isolation Is Not Enough Without Router Locks
- Confirmed behavior: in src/simulators/ksms_tester.py the prepare_router step removes ALL lines containing the literal substring TSIM_KSMS= (any run_id and any DSCP) before inserting current rules. It does not use a run_id or DSCP specific match here.
- It then rebuilds payloads with iptables-save and iptables-restore.
- Without a per router exclusive lock for the critical section, concurrent quick jobs touching the same router will clobber each other, even if DSCP differs.

### 2) Scheduler-Plan Alignment (Router Locks Only; No Global Lock)
- Replace the global system lock with router locks.
- Detailed analysis (network_reachability_test_multi.py) reads, sets, and deletes router locks as it processes routers. It may hold multiple router locks at once if working on multiple routers in flight, but it should release each router's lock as soon as processing of that router completes.
- Quick jobs do not set router locks. They only read router locks: if a router lock is present, the quick job waits for that router to be unlocked, but it can proceed on other routers in parallel. When no router lock is present, multiple quick jobs may operate on the same router concurrently.
- Scheduler changes:
  - Remove use of the global network_test lock. The scheduler should not serialize jobs globally.
  - The scheduler can remain ignorant of routers; router level coordination happens in the job code (detailed acquires per router locks; quick jobs wait via a router waiter and proceed when a router becomes free).

### 3) Environment Variable Policy Conflict
- The plan states that DSCP will be passed as a CLI argument to ksms_tester. That is clear and is the right approach.
- Code changes needed:
  - Update ksms_tester to accept `--dscp <int>` in argparse and remove reliance on KSMS_JOB_DSCP.
  - Update wsgi/services/tsim_ksms_service.py to append `--dscp {job_dscp}` to the ksms command and stop setting env for DSCP.
  - Keep TsimDscpRegistry allocation and release as is.

### 4) Host Ref Counting Needs Precise Atomicity and Rollback
- Plan proposes ref_count and job tracking for hosts via HostNamespaceSetup. That approach is sound; suggestions to refine it:
  - Maintain a separate leases registry file (hosts_leases.json) distinct from the physical hosts registry. Each lease entry records host_name, run_id, pid, job_type, dscp, allocated_at.
  - Implement atomic acquire or release by updating the leases registry under a POSIX semaphore (existing pattern) and returning the current ref_count for the host (count of active leases).
  - Physical creation happens before acquire; physical removal only when release returns ref_count == 0. If physical removal fails, leave no lease (so another job can recreate) and log for reconciler.
  - Reconciler: periodically scan leases, drop stale ones (pid dead or age beyond timeout), and if a host has zero leases but still exists physically, optionally remove it.
  - This separation keeps the long lived physical registry stable and makes the frequently changing reference data isolated and simpler to reconcile.

### 5) Router Lock Scope for Quick vs Detailed
- Quick analysis (ksms_tester): do not acquire router locks. Quick jobs operate only on their own rules using incremental iptables-restore --noflush payloads (or -A/-D), and must not perform table wide restore. If a router is locked by a detailed job, the quick job blocks via a router_waiter until the router becomes free, then proceeds.
- Detailed analysis (network_reachability_test_multi.py): acquire an exclusive (write) lock for each router that is being processed; release as soon as that router's operations are complete. The job may hold several exclusive locks at once if it processes multiple routers in flight, but each lock is independent and short lived.

### 6) Quick vs Detailed Overlap Detection Details
- Routers are not known in advance because trace execution is out of band or provided by the user. Therefore, pre scheduling router set computation is not applicable.
- With the router lock policy above, quick jobs run in parallel and only wait on a router while a detailed job holds that router's lock. Otherwise, quick jobs can operate concurrently on the same router.
- Detailed analysis uses per router locks to ensure exclusive access to the router it is actively processing, without blocking other routers.

### 7) Cleanup Ordering and Failure Modes (Details and Suggested Implementation)
- Below are concrete details using the same code snippet style as the original plan.

**Quick job router access policy (waiter based blocking, then batch add exact rules):**

```python
def prepare_router_quick(rname: str):
    # wait until router is free (no detailed exclusive lock held)
    router_waiter.wait_until_free(rname)  # blocks without polling
    # batch-add rules for this run_id only using iptables-restore --noflush
    lines = ["*mangle"]
    for rule in computed_rules:  # each 'rule' is a list like ['-A','PREROUTING', ... '--comment', f'TSIM_KSMS={run_id}:...']
        lines.append(" ".join(rule))
    lines.append("COMMIT")
    payload = "\n".join(lines) + "\n"
    run(['ip','netns','exec', rname, 'iptables-restore', '--noflush', '-n'], input_data=payload)
    return True
```

**Cleanup with best effort and idempotence (quick jobs, batch delete):**

```python
def cleanup_router_quick(rname: str):
    try:
        router_waiter.wait_until_free(rname)
        # batch-delete exact rules for this run_id using iptables-restore --noflush
        lines = ["*mangle"]
        for rule in computed_rules_for_run:  # convert to -D lines
            dline = [rule[0].replace('-A','-D')] + rule[1:]
            lines.append(" ".join(dline))
        lines.append("COMMIT")
        payload = "\n".join(lines) + "\n"
        run(['ip','netns','exec', rname, 'iptables-restore', '--noflush', '-n'], input_data=payload)
        neighbor_ref_release(rname, iface, nexthop)
    except Exception as e:
        _dbg(f"[{rname}] cleanup warning: {e}", 1)
```

**Neighbor reference counting sketch:**

```python
# leases file: /dev/shm/tsim/neighbor_leases.json
def neighbor_ref_acquire(router: str, iface: str, ip: str):
    with neighbor_lease_lock():
        leases = load_neighbor_leases()
        key = f"{router}|{iface}|{ip}"
        cnt = leases.get(key, 0)
        if cnt == 0:
            run(['ip','netns','exec', router, 'ip','neigh','replace', ip, 'dev', iface])
        leases[key] = cnt + 1
        save_neighbor_leases(leases)

def neighbor_ref_release(router: str, iface: str, ip: str):
    with neighbor_lease_lock():
        leases = load_neighbor_leases()
        key = f"{router}|{iface}|{ip}"
        cnt = leases.get(key, 0)
        if cnt <= 1:
            leases.pop(key, None)
            # best effort delete
            run(['ip','netns','exec', router, 'ip','neigh','del', ip, 'dev', iface])
        else:
            leases[key] = cnt - 1
        save_neighbor_leases(leases)
```

**Host lifecycle and leases reconciler (outline):**

```python
def reconcile_leases():
    # drop stale host leases where pid is dead or age exceeded
    # if a host has zero leases but exists physically, remove it
    # drop stale neighbor leases where no active jobs are present
    pass
```

These changes keep cleanup safe and localized to the current run while avoiding global purges.

**RouterWaiter using inotify (no polling):**

```python
class RouterWaiter:
    def __init__(self, lock_manager, lock_dir="/dev/shm/tsim/locks"):
        self.lock_manager = lock_manager
        self.lock_dir = lock_dir

    def wait_until_free(self, router: str, timeout: float = None) -> bool:
        """Block until router lock is released (no polling).

        Fast path returns immediately when not locked.
        Uses inotify on the locks directory and reacts to lock delete or notify touch.
        """
        import os
        import time
        import ctypes
        import select
        import struct

        lock_name = f"router:{router}"
        lock_file = f"{lock_name}.lock"
        notify_file = f"router.{router}.notify"

        # Fast path: not locked
        if not self.lock_manager or not self.lock_manager.is_locked(lock_name):
            return True

        # inotify constants
        IN_DELETE = 0x00000200
        IN_MOVED_FROM = 0x00000040
        IN_ATTRIB = 0x00000004
        IN_CLOSE_WRITE = 0x00000008
        IN_ONLYDIR = 0x01000000

        # Setup inotify
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        inotify_init1 = getattr(libc, "inotify_init1", None)
        if inotify_init1 is None:
            # Fallback: coarse wait without busy polling
            while self.lock_manager.is_locked(lock_name):
                time.sleep(0.5)
            return True

        fd = inotify_init1(0)
        if fd < 0:
            while self.lock_manager.is_locked(lock_name):
                time.sleep(0.5)
            return True

        libc.inotify_add_watch(fd, self.lock_dir.encode(),
                               IN_DELETE | IN_MOVED_FROM | IN_ATTRIB | IN_CLOSE_WRITE | IN_ONLYDIR)

        poller = select.poll()
        poller.register(fd, select.POLLIN)
        start = time.time()

        try:
            while True:
                if timeout is not None and time.time() - start > timeout:
                    return False
                events = poller.poll(1000)
                if not events:
                    continue
                buf = os.read(fd, 4096)
                i = 0
                # Parse inotify_event entries
                while i + 16 <= len(buf):
                    wd, mask, cookie, name_len = struct.unpack_from("iIII", buf, i)
                    i += 16
                    name = buf[i:i+name_len].split(b"\x00", 1)[0].decode()
                    i += name_len
                    if name in (lock_file, notify_file):
                        # Recheck lock state
                        if not self.lock_manager.is_locked(lock_name):
                            return True
        finally:
            try:
                os.close(fd)
            except Exception:
                pass
```

Note: emitting a notify touch on router lock release (e.g., updating `router.<name>.notify`) can improve wakeup latency and resilience.

### 8) Single Host Assumption
- Accepted: the system is designed for single host operation. Horizontal scaling can be achieved by running multiple identical systems behind a load balancer with sticky sessions.
- No change required to internal locking or registries for this deployment model.

---

## Current Code Review: Concurrency and Robustness Issues

### A) KSMS iptables Rule Handling (required changes)
- File: src/simulators/ksms_tester.py
- Problem: prepare_router removes ALL TSIM_KSMS= rules and rebuilds from snapshots with iptables-restore. This risks clobbering other jobs and creates lost-update hazards.
- Required action:
  - Remove any global TSIM_KSMS= purge in prepare phase.
  - Do not rebuild from iptables-save snapshots in quick jobs.
  - Use iptables-restore --noflush -n with payload containing only this run's exact -A lines for add, and -D lines for delete.
  - Call RouterWaiter.wait_until_free(router) before touching a router to avoid overlapping with a detailed job holding the router lock.

### B) Detailed Router Locking (exclusive locks)
- File: network_reachability_test_multi.py (detailed path)
- Problem: Detailed workflow touches router state in multi-step sequences; requires isolation from quick jobs and other detailed jobs.
- Required action:
  - Acquire an exclusive per-router lock via TsimLockManagerService before each router operation block; release immediately after that router is complete.
  - It is acceptable to hold several router locks concurrently if multiple routers are in flight; release each as soon as its work completes.

### C) Scheduler Behavior (no global lock)
- File: wsgi/services/tsim_scheduler_service.py
- Problem: Current scheduler uses a global lock and serializes everything.
- Required action:
  - Remove use of the global network_test lock entirely.
  - Keep scheduler router-agnostic; job code coordinates at router level (detailed acquires exclusive locks; quick waits via RouterWaiter).

### D) Lock Manager Notify (inotify wakeups)
- File: wsgi/services/tsim_lock_manager_service.py
- Problem: No notification on router lock release for waiters; quick jobs would need polling.
- Required action:
  - On release_lock("router:<name>") touch/update a notify file (e.g., router.<name>.notify) in the lock dir.
  - Provide is_locked(name) fast check; no changes to file-locking semantics otherwise.

### E) ARP Neighbor Setup and Cleanup (refcount)
- File: src/simulators/ksms_tester.py (and shared helper)
- Problem: Multiple jobs may add the same neighbor; one job deleting can impact another.
- Required action:
  - Implement neighbor_ref_acquire/release using a small leases registry and only delete when refcount reaches zero.

### F) Progress and Run Files
- File: wsgi/services/tsim_progress_tracker.py
- Observation: Single-writer per run today; acceptable. If multi-process writes appear, add simple file locks.

### G) Cancel Semantics
- Files: wsgi/services/tsim_queue_service.py, wsgi/services/tsim_scheduler_service.py
- Problem: Cancel only checked before start.
- Optional improvement: Executors may check a cancel flag between major phases and abort cleanly.
- File: wsgi/services/tsim_dscp_registry.py
- Allocations include PID and are cleaned when PID dies or when too old. Works if the same process owns the job; could be wrong if a separate worker process is used.
- Recommendation: If execution moves out of process, include a stable job owner identity (for example, run_id heartbeat file) rather than PID.

### H) Environment Mutations in app.wsgi
- File: wsgi/app.wsgi
- Mutates os.environ at import and in the WSGI wrapper (first request). Two concurrent first requests could race in setting TSIM_ENV_SET. Practically benign, but avoid duplicated setup.
- Recommendation: Do all env setup at module import time with a process local guard (for example, a module level boolean or lock) and keep the request wrapper idempotent.

### I) Heavy Module Preloading Costs
- File: wsgi/app.wsgi
- Preloads heavy modules (matplotlib, reportlab, PyPDF2, networkx) in every worker. Increases memory footprint and startup time.
- Recommendation: Consider lazy loading heavy, non critical libs (for example, only load PDF stack on demand) if worker count is high.

### J) Hardcoded or Fallback Paths and /dev/shm Assumptions
- Files: wsgi/app.wsgi, wsgi/services/tsim_config_service.py
- Some hardcoded defaults remain and /dev/shm is assumed available and writeable.
- Recommendation: Ensure all paths are configurable and validated; document /dev/shm dependency or allow alternate tmpfs or data dirs via config.

---

## Recommendations and Next Steps

### 1) Remove global scheduler lock
- Update wsgi/services/tsim_scheduler_service.py to stop acquiring the global network_test lock and run jobs without global serialization.

### 2) Detailed per-router exclusive locks
- In the detailed path (network_reachability_test_multi.py), wrap router mutation blocks with TsimLockManagerService exclusive locks on router:<name>, releasing each as soon as its work completes.

### 3) Quick job batching and waiter
- In ksms_tester:
  - Eliminate any global TSIM_KSMS= purge and any snapshot-based restore in quick jobs.
  - Before touching a router, call RouterWaiter.wait_until_free(router).
  - Batch add/delete rules for this run only using iptables-restore --noflush -n with exact -A/-D lines; do not flush or rebuild.

### 4) Lock manager notify support
- In wsgi/services/tsim_lock_manager_service.py, on release_lock("router:<name>") touch or update router.<name>.notify in the lock dir so RouterWaiter can wake without polling.

### 5) DSCP via CLI
- Change ksms_tester to accept --dscp <int> and update wsgi/services/tsim_ksms_service.py to pass it; remove env-based DSCP.

### 6) Neighbor refcount leases
- Add a small neighbor leases registry and implement neighbor_ref_acquire/release; only delete neighbor entries when refcount reaches zero.

### 7) Host leases (optional but recommended)
- Implement host leases (ref_count and jobs) in a separate leases registry with atomic acquire/release and a reconciler to drop stale leases.

### 8) Cancellation (optional)
- Add mid-phase cancel checks in executors to improve responsiveness to cancel requests.

---

## Positive Findings / What Is Already Good
- TsimDscpRegistry provides a reasonable DSCP allocation scheme with stale cleanup and atomic file updates.
- host_namespace_setup.py already uses POSIX semaphores for atomic JSON registry updates and includes collision checks for IPs on the same router.
- The scheduler, queue, and reconciler are cleanly separated; refactoring to per router scheduling is feasible.
- KSMS code already marks cleanup ours vs others at the end of runs when removing rules by run_id.

---

## Concrete Code Touchpoints
- Per router locking and KSMS rule handling:
  - src/simulators/ksms_tester.py (prepare, insert, cleanup paths)
- Scheduler policy changes:
  - wsgi/services/tsim_scheduler_service.py (remove global lock; implement router overlap logic)
  - wsgi/services/tsim_lock_manager_service.py (ensure router lock naming)
- DSCP passing policy:
  - wsgi/services/tsim_ksms_service.py (change env passing to CLI or config or document exception)
- Host ref counting:
  - src/simulators/host_namespace_setup.py (new fields and methods; atomic updates)
- ARP neighbor coordination:
  - src/simulators/ksms_tester.py (neighbor setup or cleanup with ref counting or idempotence)
- Optional: progress or cancel robustness and reconciler enhancements.

---

## Summary
Implement the following single course of action to eliminate races and enable safe concurrency:
- Remove the global scheduler lock; keep the scheduler router-agnostic.
- Use exclusive per-router locks only in detailed analysis; release each lock as soon as that router is done.
- Make quick jobs wait (no polling) until a router is free, then batch -A/-D their own rules via iptables-restore --noflush -n; never rebuild from snapshots or purge globally.
- Add lock-release notifications in the lock manager for inotify-based waiters.
- Pass DSCP via CLI; add neighbor and (optionally) host leases for safe cleanup.
This plan clearly separates responsibilities and uses OS primitives to block, not poll, ensuring correctness and performance.
