"""Owned subprocess lifecycle for capture and page-inference work."""
import os
import subprocess
import sys

import psutil

from .page_store import PageAuditStore


def page_worker_is_alive(audit: dict) -> bool:
    pid, created = audit.get("worker_pid"), audit.get("worker_created")
    if not pid or created is None:
        return False
    try:
        process = psutil.Process(pid)
        if abs(process.create_time() - created) > .01 or not process.is_running():
            return False
        command = process.cmdline()
        return "spill_market.page_worker" in command and audit["id"] in command
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def reconcile_page_workers(pages: PageAuditStore, *, include_unstarted=False):
    for snapshot in pages.active():
        if snapshot.get("worker_pid") is None and not include_unstarted:
            continue
        if not page_worker_is_alive(snapshot):
            pages.interrupt_if_owned(snapshot)


def spawn_page_worker(pages: PageAuditStore, identifier: str):
    directory = pages.assets_dir(identifier).parent
    directory.mkdir(parents=True, exist_ok=True)
    nonce = pages.get(identifier, internal=True)["worker_nonce"]
    command = [sys.executable, "-m", "spill_market.page_worker", str(pages.root), identifier, nonce]
    with (directory / "worker.log").open("ab") as log:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        pages.set_worker(identifier, process.pid, psutil.Process(process.pid).create_time(), nonce)
    except psutil.NoSuchProcess:
        pass

