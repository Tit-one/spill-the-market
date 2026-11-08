import pytest

from spill_market.examples import examples
from spill_market.models import StudySpec
from spill_market.page_models import AnalyzePageRequest, PageAuditSpec, PageVariantInput
from spill_market.page_store import PageAuditStore
from spill_market.services import prepare_study
from spill_market.storage import ActiveRunError, Store


@pytest.fixture
async def setup(tmp_path):
    store = Store(tmp_path)
    spec = StudySpec.model_validate(examples()[0]["spec"])
    spec.audience.population = 60
    study = await prepare_study(store, spec)
    return PageAuditStore(store), study


async def test_capture_is_immutable_local_and_does_not_expose_html(setup):
    pages, study = setup
    audit = pages.create(study["id"], PageAuditSpec(variants=[PageVariantInput(source="html", html="<p>local</p>")]))
    assert audit["status"] == "queued" and audit["provider_id"] is None
    assert audit["spec"]["variants"][0]["html"] is None
    internal = pages.get(audit["id"], internal=True)
    assert internal["spec"]["variants"][0]["html"] == "<p>local</p>"
    assert internal["study_snapshot"]["spec"] == study["spec"]
    assert "study_snapshot" not in audit
    with pytest.raises(ActiveRunError):
        pages.create(study["id"], PageAuditSpec())


async def test_analysis_claim_is_single_flight_and_capture_required(setup):
    pages, study = setup
    audit = pages.create(study["id"], PageAuditSpec())
    with pytest.raises(ActiveRunError):
        pages.start_analysis(audit["id"], AnalyzePageRequest())
    pages.update(audit["id"], status="captured", snapshots=[{"id": "snapshot"}])
    claimed = pages.start_analysis(audit["id"], AnalyzePageRequest())
    assert claimed["status"] == "queued" and claimed["provider_id"] == "demo"
    with pytest.raises(ActiveRunError):
        pages.start_analysis(audit["id"], AnalyzePageRequest())


async def test_stale_reconciliation_cannot_overwrite_finished_or_replaced_worker(setup):
    pages, study = setup
    audit = pages.create(study["id"], PageAuditSpec())
    stale = pages.get(audit["id"], internal=True)
    pages.update(audit["id"], status="captured")
    assert not pages.interrupt_if_owned(stale)
    assert pages.get(audit["id"])["status"] == "captured"
    pages.update(audit["id"], status="capturing", worker_pid=123, worker_created=9.0)
    assert not pages.interrupt_if_owned(stale)
    current = pages.get(audit["id"], internal=True)
    assert pages.interrupt_if_owned(current)
    assert pages.get(audit["id"])["status"] == "interrupted"


async def test_resume_keeps_identity_assets_and_blocks_uncertain_paid_replay(setup):
    pages, study = setup
    audit = pages.create(study["id"], PageAuditSpec())
    pages.update(audit["id"], status="cancelled", snapshots=[{"id": "retained"}])
    resumed = pages.prepare_resume(audit["id"])
    assert resumed["id"] == audit["id"] and resumed["snapshots"] == [{"id": "retained"}]
    pages.update(audit["id"], status="failed", error_code="uncertain_provider_dispatch")
    with pytest.raises(ValueError, match="reconcil"):
        pages.prepare_resume(audit["id"])


async def test_invalid_asset_identifier_cannot_escape_local_store(setup):
    pages, _ = setup
    with pytest.raises(ValueError):
        pages.assets_dir("../private")
    with pytest.raises(KeyError):
        pages.get("0" * 32)


async def test_worker_lease_accepts_windows_launcher_child_and_rejects_old_attempt(setup):
    pages, study = setup
    audit = pages.create(study["id"], PageAuditSpec())
    nonce = pages.get(audit["id"], internal=True)["worker_nonce"]
    pages.set_worker(audit["id"], 100, 1.0, nonce)
    assert pages.claim_worker(audit["id"], 200, 2.0, nonce)
    assert pages.get(audit["id"], internal=True)["worker_pid"] == 200
    pages.update(audit["id"], status="interrupted")
    pages.prepare_resume(audit["id"])
    assert not pages.claim_worker(audit["id"], 200, 2.0, nonce)
    new_nonce = pages.get(audit["id"], internal=True)["worker_nonce"]
    assert new_nonce != nonce
    assert pages.claim_worker(audit["id"], 300, 3.0, new_nonce)
