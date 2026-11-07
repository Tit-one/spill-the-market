"""Spawn-owned workers: no CPU-bound simulation inside an HTTP request."""
import os
import subprocess
import sys

import psutil

from .storage import Store


def worker_is_alive(run: dict) -> bool:
    pid = run.get("worker_pid")
    created = run.get("worker_created")
    if not pid or created is None:
        return False
    try:
        process = psutil.Process(pid)
        if abs(process.create_time() - created) > 0.01 or not process.is_running():
            return False
        command = process.cmdline()
        worker = "spill_market.worker" in command and run["id"] in command
        cli = any("spill-market" in part or "spill_market.cli" in part for part in command)
        return worker or cli
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def reconcile_workers(store: Store, *, include_unstarted=False):
    """Only a missing/mismatched actual process makes a run interrupted; no heartbeat timeout."""
    for run in store.active_runs():
        if run.get("worker_pid") is None and not include_unstarted:
            continue
        if not worker_is_alive(run):
            store.update_run(run["id"], status="interrupted", error="Worker process is no longer present; checkpoints retained.")


def spawn_worker(store: Store, run_id: str):
    directory = store.run_directory(run_id)
    command = [sys.executable, "-m", "spill_market.worker", "--data-dir", str(store.root), "--run-id", run_id]
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    try:
        with (directory / "worker.log").open("ab") as output:
            process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                       env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}, **options)
        try:
            created = psutil.Process(process.pid).create_time()
        except psutil.NoSuchProcess:
            return
        store.update_run(run_id, worker_pid=process.pid, worker_created=created)
    except Exception as exc:
        store.update_run(run_id, status="failed", error=f"Could not start worker: {type(exc).__name__}")
        raise
