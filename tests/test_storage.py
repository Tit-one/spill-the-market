import pytest


def test_study_and_run_survive_new_store(tmp_path):
    from spill_market.storage import Store
    store = Store(tmp_path)
    study = store.create_study({"product": {"name": "Example"}}, [], [], None)
    run = store.create_run(study["id"], {"product": {"name": "Example"}}, [])
    other = Store(tmp_path)
    assert other.get_study(study["id"])["spec"]["product"]["name"] == "Example"
    assert other.get_run(run["id"])["status"] == "queued"


def test_cannot_spawn_duplicate_active_runs(tmp_path):
    from spill_market.storage import Store, ActiveRunError
    store = Store(tmp_path)
    study = store.create_study({}, [], [], None)
    store.create_run(study["id"], {}, [])
    with pytest.raises(ActiveRunError):
        store.create_run(study["id"], {}, [])


def test_run_cancellation_and_resume_keep_snapshot(tmp_path):
    from spill_market.storage import Store
    store = Store(tmp_path)
    study = store.create_study({}, [], [], None)
    run = store.create_run(study["id"], {"seed": 42}, [{"id": "original"}])
    store.request_cancel(run["id"])
    assert store.is_cancel_requested(run["id"])
    store.update_run(run["id"], status="cancelled")
    store.prepare_resume(run["id"])
    resumed = store.get_run(run["id"], internal=True)
    assert resumed["status"] == "queued"
    assert resumed["spec_snapshot"] == {"seed": 42}
    assert resumed["plans_snapshot"] == [{"id": "original"}]
    assert not resumed["cancel_requested"]


def test_starting_run_atomically_saves_the_exact_submitted_plans(tmp_path):
    from spill_market.storage import Store
    store = Store(tmp_path)
    study = store.create_study({}, [{"id": "old"}], [], None)
    run = store.create_run(study["id"], {}, [{"id": "edited"}])
    assert store.get_study(study["id"])["plans"] == [{"id": "edited"}]
    assert store.get_run(run["id"], internal=True)["plans_snapshot"] == [{"id": "edited"}]
