import sys
import time
from pathlib import Path
import tempfile


def test_fifo_and_single_run_execution():
    # Make wsgi services importable
    sys.path.insert(0, str(Path('wsgi').resolve()))

    from services.tsim_config_service import TsimConfigService
    from services.tsim_lock_manager_service import TsimLockManagerService
    from services.tsim_queue_service import TsimQueueService
    from services.tsim_progress_tracker import TsimProgressTracker
    from services.tsim_scheduler_service import TsimSchedulerService

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        data_dir = base / 'data'
        run_dir = base / 'runs'
        lock_dir = base / 'locks'
        session_dir = base / 'sessions'
        for p in (data_dir, run_dir, lock_dir, session_dir):
            p.mkdir(parents=True, exist_ok=True)

        cfg = TsimConfigService()
        cfg.set('data_dir', str(data_dir))
        cfg.set('run_dir', str(run_dir))
        cfg.set('lock_dir', str(lock_dir))
        cfg.set('session_dir', str(session_dir))
        cfg.set('session_timeout', 5)

        locks = TsimLockManagerService(cfg)
        queue = TsimQueueService(cfg)
        progress = TsimProgressTracker(cfg)

        # Fake executor that records order and simulates work
        exec_order = []
        timings = {}

        class FakeExecutor:
            def execute(self, run_id, source_ip, dest_ip, source_port, port_protocol_list, user_trace_data=None):
                start = time.time()
                timings.setdefault(run_id, {})['start'] = start
                exec_order.append(run_id)
                # Simulate execution time
                time.sleep(0.3)
                timings[run_id]['end'] = time.time()
                # Mark complete in progress tracker to mimic real behavior
                progress.mark_complete(run_id, True)
                return {'success': True, 'run_id': run_id}

        scheduler1 = TsimSchedulerService(cfg, queue, progress, FakeExecutor(), locks)
        scheduler2 = TsimSchedulerService(cfg, queue, progress, FakeExecutor(), locks)

        scheduler1.start()
        scheduler2.start()

        # Enqueue two jobs (A then B)
        A = 'run-A'
        B = 'run-B'
        progress.create_run_directory(A)
        progress.create_run_directory(B)

        queue.enqueue(A, 'user1', {'run_id': A, 'source_ip': '1.1.1.1', 'dest_ip': '2.2.2.2', 'port_protocol_list': []})
        queue.enqueue(B, 'user2', {'run_id': B, 'source_ip': '1.1.1.1', 'dest_ip': '2.2.2.2', 'port_protocol_list': []})

        # Wait until both executed or timeout
        t0 = time.time()
        while len(exec_order) < 2 and time.time() - t0 < 5:
            time.sleep(0.05)

        # Stop schedulers
        scheduler1.stop()
        scheduler2.stop()

        # Assertions: FIFO order and no overlap
        assert exec_order[:2] == [A, B], f"Expected FIFO [A,B], got {exec_order}"
    assert timings[A]['end'] <= timings[B]['start'], "Executions overlapped; expected single-run at a time"


def test_same_user_multiple_jobs_queue_and_run_serially():
    import time
    from pathlib import Path
    import tempfile
    sys.path.insert(0, str(Path('wsgi').resolve()))
    from services.tsim_config_service import TsimConfigService
    from services.tsim_lock_manager_service import TsimLockManagerService
    from services.tsim_queue_service import TsimQueueService
    from services.tsim_progress_tracker import TsimProgressTracker
    from services.tsim_scheduler_service import TsimSchedulerService

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        data_dir = base / 'data'
        run_dir = base / 'runs'
        lock_dir = base / 'locks'
        session_dir = base / 'sessions'
        for p in (data_dir, run_dir, lock_dir, session_dir):
            p.mkdir(parents=True, exist_ok=True)

        cfg = TsimConfigService()
        cfg.set('data_dir', str(data_dir))
        cfg.set('run_dir', str(run_dir))
        cfg.set('lock_dir', str(lock_dir))
        cfg.set('session_dir', str(session_dir))
        cfg.set('session_timeout', 5)

        locks = TsimLockManagerService(cfg)
        queue = TsimQueueService(cfg)
        progress = TsimProgressTracker(cfg)

        exec_order = []
        timings = {}

        class FakeExecutor:
            def execute(self, run_id, source_ip, dest_ip, source_port, port_protocol_list, user_trace_data=None):
                start = time.time()
                timings.setdefault(run_id, {})['start'] = start
                exec_order.append(run_id)
                time.sleep(0.2)
                timings[run_id]['end'] = time.time()
                progress.mark_complete(run_id, True)
                return {'success': True, 'run_id': run_id}

        scheduler = TsimSchedulerService(cfg, queue, progress, FakeExecutor(), locks)
        scheduler.start()

        # Enqueue two jobs for the same user
        R1 = 'same-user-1'
        R2 = 'same-user-2'
        progress.create_run_directory(R1)
        progress.create_run_directory(R2)
        queue.enqueue(R1, 'userX', {'run_id': R1, 'source_ip': '1.1.1.1', 'dest_ip': '2.2.2.2', 'port_protocol_list': []})
        queue.enqueue(R2, 'userX', {'run_id': R2, 'source_ip': '1.1.1.1', 'dest_ip': '2.2.2.2', 'port_protocol_list': []})

        t0 = time.time()
        while len(exec_order) < 2 and time.time() - t0 < 5:
            time.sleep(0.05)

        scheduler.stop()

        # Both jobs should run in FIFO order without overlap
        assert exec_order[:2] == [R1, R2]
        assert timings[R1]['end'] <= timings[R2]['start']


def test_active_run_clears_on_completion_cross_process():
    sys.path.insert(0, str(Path('wsgi').resolve()))
    from services.tsim_config_service import TsimConfigService
    from services.tsim_progress_tracker import TsimProgressTracker

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        run_dir = base / 'runs'
        run_dir.mkdir(parents=True, exist_ok=True)

        cfg = TsimConfigService()
        cfg.set('run_dir', str(run_dir))

        # Simulate Process A: sets active run and writes file progress (COMPLETE)
        tracker_A = TsimProgressTracker(cfg)
        run_id = 'run-X'
        tracker_A.create_run_directory(run_id)
        tracker_A.set_active_run_for_user('user1', run_id)
        tracker_A.log_phase(run_id, 'COMPLETE', 'done')

        # Simulate Process B: same config, independent tracker; it still has active run mapping if set,
        # but should detect completion via file and clear it
        tracker_B = TsimProgressTracker(cfg)
        # Mimic stale mapping in process B (e.g., from prior state)
        tracker_B.set_active_run_for_user('user1', run_id)
        # Now B should consult file and clear it
        assert tracker_B.get_active_run_for_user('user1') is None
