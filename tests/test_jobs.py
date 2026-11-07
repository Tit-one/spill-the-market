def test_process_reconciliation_cannot_overwrite_a_concurrent_completion(tmp_path, monkeypatch):
    from spill_market import jobs
    from spill_market.storage import Store
    store = Store(tmp_path)
    study = store.create_study({}, [], [], None)
    run = store.create_run(study["id"], {}, [])
    store.update_run(run["id"], status="running", worker_pid=1234, worker_created=1000.0)

    def exits_after_committing_report(snapshot):
        store.update_run(snapshot["id"], status="completed", progress={"percent": 100})
        return False

    monkeypatch.setattr(jobs, "worker_is_alive", exits_after_committing_report)
    jobs.reconcile_workers(store)
    assert store.get_run(run["id"])["status"] == "completed"


def test_stale_reconciliation_cannot_mark_a_replacement_worker_interrupted(tmp_path, monkeypatch):
    from spill_market import jobs
    from spill_market.storage import Store
    store = Store(tmp_path)
    study = store.create_study({}, [], [], None)
    run = store.create_run(study["id"], {}, [])
    store.update_run(run["id"], status="running", worker_pid=1234, worker_created=1000.0)

    def resumes_before_old_process_check_finishes(snapshot):
        store.update_run(snapshot["id"], status="running", worker_pid=5678, worker_created=2000.0)
        return False

    monkeypatch.setattr(jobs, "worker_is_alive", resumes_before_old_process_check_finishes)
    jobs.reconcile_workers(store)
    assert store.get_run(run["id"])["status"] == "running"


def test_same_missing_worker_is_still_marked_interrupted(tmp_path, monkeypatch):
    from spill_market import jobs
    from spill_market.storage import Store
    store = Store(tmp_path)
    study = store.create_study({}, [], [], None)
    run = store.create_run(study["id"], {}, [])
    store.update_run(run["id"], status="running", worker_pid=1234, worker_created=1000.0)
    monkeypatch.setattr(jobs, "worker_is_alive", lambda snapshot: False)
    jobs.reconcile_workers(store)
    assert store.get_run(run["id"])["status"] == "interrupted"
