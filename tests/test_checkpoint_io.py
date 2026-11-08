import ctypes
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from spill_market import simulation
from spill_market.models import AudienceSpec, MediaPlan, ProductSpec


def denied():
    error = PermissionError(13, "Temporary Windows sharing denial")
    error.winerror = 5
    return error


def test_atomic_json_retries_temporary_windows_replace_denial(tmp_path, monkeypatch):
    target = tmp_path / "result.json"
    target.write_text('{"committed":1}', encoding="utf-8")
    original, attempts = os.replace, []
    def transient(source, destination):
        attempts.append(str(source))
        if len(attempts) < 3:
            raise denied()
        return original(source, destination)
    monkeypatch.setattr(os, "replace", transient)
    simulation._atomic_json(target, {"committed": 2})
    assert json.loads(target.read_text()) == {"committed": 2}
    assert len(attempts) == 3


def test_atomic_json_concurrent_writers_have_distinct_complete_staged_files(tmp_path, monkeypatch):
    target = tmp_path / "result.json"
    original, barrier, sources = os.replace, threading.Barrier(2), []
    def together(source, destination):
        sources.append(str(source))
        json.loads(source.read_text(encoding="utf-8"))
        if len(sources) <= 2:
            barrier.wait(timeout=5)
        return original(source, destination)
    monkeypatch.setattr(os, "replace", together)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(simulation._atomic_json, target, {"writer": i, "data": "x" * 1000}) for i in range(2)]
        for job in jobs:
            job.result(timeout=8)
    assert len(set(sources)) == 2
    assert json.loads(target.read_text())["writer"] in {0, 1}


def test_permanent_replace_denial_is_actionable_bounded_and_retains_commit(tmp_path, monkeypatch):
    target = tmp_path / "result.json"
    target.write_text('{"committed":1}', encoding="utf-8")
    def permanent(*args):
        raise denied()
    monkeypatch.setattr(os, "replace", permanent)
    started = time.monotonic()
    with pytest.raises(OSError, match="retained|preserved") as failure:
        simulation._atomic_json(target, {"committed": 2})
    assert time.monotonic() - started < 2
    assert "resume" in str(failure.value).lower()
    assert json.loads(target.read_text()) == {"committed": 1}


def test_atomic_write_retry_can_cancel_without_losing_committed_checkpoint(tmp_path, monkeypatch):
    target = tmp_path / "result.json"
    target.write_text('{"committed":1}', encoding="utf-8")
    attempts = []
    def locked(*args):
        attempts.append(1)
        raise denied()
    monkeypatch.setattr(os, "replace", locked)
    with pytest.raises(simulation.SimulationCancelled):
        simulation._atomic_json(target, {"committed": 2}, cancel_check=lambda: bool(attempts))
    assert len(attempts) == 1
    assert json.loads(target.read_text()) == {"committed": 1}


def test_checkpoint_rejects_incompatible_fingerprint_without_overwriting(tmp_path):
    target = tmp_path / "scenario.npz"
    state = {key: np.zeros(1) for key in simulation.MUTABLE_FIELDS}
    simulation._save_checkpoint(target, "original-fingerprint", state, np.zeros((15, 1)), {"day": 1})
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="checkpoint|fingerprint"):
        simulation._save_checkpoint(target, "different-fingerprint", state, np.zeros((15, 1)), {"day": 2})
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows deny-delete sharing semantics")
def test_windows_held_open_destination_recovers_when_handle_is_released(tmp_path):
    from ctypes import wintypes
    target = tmp_path / "held.json"
    target.write_text('{"committed":1}', encoding="utf-8")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(target), 0x80000000, 0x1 | 0x2, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    released = threading.Event()
    def release():
        kernel.CloseHandle(handle)
        released.set()
    timer = threading.Timer(.15, release)
    timer.start()
    try:
        simulation._atomic_json(target, {"committed": 2})
    finally:
        timer.join(timeout=1)
        if not released.is_set():
            release()
    assert released.is_set()
    assert json.loads(target.read_text()) == {"committed": 2}


def test_checkpoint_resume_closes_npz_files_and_matches_continuous_run(tmp_path, monkeypatch):
    product = ProductSpec(name="IO fixture", description="A small checkpoint fixture", unit_price_cents=100)
    audience = AudienceSpec(population=60, representatives=10)
    plan = MediaPlan(id="io", name="IO", price_cents=100, media_budget_cents=0)
    target, seen = tmp_path / "scenario.npz", []
    with pytest.raises(simulation.SimulationCancelled):
        simulation.simulate_scenario(product, audience, plan, 4, 42, checkpoint_path=target,
            on_day=seen.append, cancel_check=lambda: len(seen) >= 2)
    opened, original_load = [], np.load
    def tracked(*args, **kwargs):
        value = original_load(*args, **kwargs)
        opened.append(value)
        return value
    monkeypatch.setattr(np, "load", tracked)
    resumed = simulation.simulate_scenario(product, audience, plan, 4, 42, checkpoint_path=target)
    assert resumed == simulation.simulate_scenario(product, audience, plan, 4, 42)
    assert opened and all(value.fid is None for value in opened)
