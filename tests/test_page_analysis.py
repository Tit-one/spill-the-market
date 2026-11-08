import hashlib
import io
import json

import httpx
import pytest
from PIL import Image

from spill_market.gateway import BudgetLedger
from spill_market.models import AudienceSpec, Persona, ProductSpec, StudySpec
from spill_market.page_models import Box, PageAuditSpec, PageSnapshot, PageVariantInput, VisibleElement
from spill_market.page_analysis import PageAnalysisCancelled, PageStageUncertain, analyze_page_audit


def fixture_audit(tmp_path, provenance="demo"):
    output = io.BytesIO()
    Image.new("RGB", (160, 100), "white").save(output, "JPEG")
    data = output.getvalue()
    personas = [Persona(id=f"p{i}", name=f"Person {i}", age=age, language="en", profession="Creator", budget_cents=5000,
                        need_fit=0.6, trust=0.5, price_sensitivity=0.4, social_sensitivity=0.4, fatigue_tolerance=0.5)
                for i, age in enumerate([20, 35, 55, 70])]
    study = StudySpec(product=ProductSpec(name="SECRET_PRODUCT_NAME", description="SECRET DESCRIPTION NEVER REVEALED", unit_price_cents=98765432),
                      audience=AudienceSpec(population=30, age_min=18, age_max=75, representatives=4))
    spec = PageAuditSpec(variants=[PageVariantInput(id="A"), PageVariantInput(id="B")],
                         viewports=["desktop"], max_sections=2, persona_count=3, direct_vision_count=1)
    snapshots = []
    for variant in ["A", "B"]:
        for section in range(2):
            identifier = f"shot_{variant}_{section}"
            (tmp_path / f"{identifier}.jpg").write_bytes(data)
            snapshot = PageSnapshot(id=identifier, variant_id=variant, section_index=section, viewport="desktop",
                                    width=160, height=100, scroll_y=section * 100, page_height=200,
                                    content_hash=hashlib.sha256(data).hexdigest(), provenance=provenance,
                                    dom=[VisibleElement(id="d0", tag="h1", text="Visible title" if section == 0 else "29 € Buy",
                                                        box=Box(x=0, y=0, width=100, height=20))])
            snapshots.append(snapshot.model_dump())
    return {"id": "audit-one", "study_id": "study-one", "spec": spec.model_dump(),
            "study_snapshot": {"spec": study.model_dump(), "personas": [p.model_dump() for p in personas]},
            "snapshots": snapshots}


async def test_demo_is_network_free_stratified_progressive_paired_and_honest(monkeypatch, tmp_path):
    from spill_market import page_analysis
    monkeypatch.setattr(page_analysis.VisionClient, "from_env", classmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("provider read"))))
    audit = fixture_audit(tmp_path)
    ledger = BudgetLedger(tmp_path / "budget.db", 0)
    result = await analyze_page_audit(audit, assets_dir=tmp_path, ledger=ledger, journal_path=tmp_path / "j.db",
                                     provider_id="demo", allow_remote=False)
    assert result.mode == "demo" and len(result.observations) == 4
    assert result.audience_coverage["selected"] == 3
    assert min(result.audience_coverage["ages"]) == 20 and max(result.audience_coverage["ages"]) == 70
    assert result.comparisons and result.comparisons[0]["paired_count"] == 3
    first_steps = [review for review in result.reviews if review.step == 0]
    assert all(review.intention_before == 0 for review in first_steps)
    assert all("29" not in review.understanding for review in first_steps)
    assert all("shot_A_1" not in " ".join(review.visible_information_ids) for review in first_steps if review.variant_id == "A")
    assert ledger.summary()["calls"] == 0
    assert any("fictional" in text.lower() for text in result.limitations)


async def test_demo_cannot_fabricate_analysis_for_real_images(tmp_path):
    audit = fixture_audit(tmp_path, provenance="screenshot_import")
    with pytest.raises(ValueError, match="demo"):
        await analyze_page_audit(audit, assets_dir=tmp_path, ledger=BudgetLedger(tmp_path / "b.db", 0),
                                 journal_path=tmp_path / "j.db", provider_id="demo", allow_remote=False)


def provider_response(request, captured, invalid_box=False, invalid_age=False):
    body = json.loads(request.content)
    context = json.loads(body["messages"][1]["content"][0]["text"])
    captured.append((context, body))
    if context["task"] == "observe":
        snapshot = context["snapshot"]
        result = {"snapshot_id": snapshot["id"], "summary": "Visible page text", "regions": [
            {"id": "r0", "box": {"x": 0, "y": 0, "width": 1000 if invalid_box else 100, "height": 20},
             "kind": "text", "literal_text": f"OBSERVER_TEXT_{snapshot['id']}", "description": "Visible block", "uncertainty": ""}],
                  "unknowns": ["Button function untested"], "interpretations": []}
    else:
        result = {"reviews": []}
        for person in context["personas"]:
            result["reviews"].append({"persona_id": person["id"], "age": 99 if invalid_age else person["age"],
                "understanding": "I read only the revealed section", "questions": ["Where is the price?"],
                "positives": ["The text is clear"], "frictions": ["I need pricing information"],
                "confidence": 0.6, "trust": 0.55, "intention_before": person["intention_before"],
                "intention_after": min(1, person["intention_before"] + 0.1), "intended_action": "scroll",
                "evidence_ids": context["available_information_ids"][-1:]})
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result)}}],
                                     "usage": {"prompt_tokens": 100, "completion_tokens": 100}})


def configured(monkeypatch):
    for name, value in {"SPILL_VISION_ENABLED": "true", "SPILL_LLM_BASE_URL": "https://api.example/v1",
                        "SPILL_LLM_MODEL": "explicit-vision-model", "SPILL_LLM_API_KEY": "test-only",
                        "SPILL_LLM_INPUT_USD_PER_MILLION": "0.1", "SPILL_LLM_OUTPUT_USD_PER_MILLION": "0.5",
                        "SPILL_VISION_MAX_IMAGE_INPUT_TOKENS": "16000"}.items():
        monkeypatch.setenv(name, value)


async def test_vision_uses_images_without_product_or_future_leaks_and_blind_controls(monkeypatch, tmp_path):
    from spill_market import page_analysis
    from spill_market.page_vision import VisionClient
    configured(monkeypatch)
    captured = []
    audit = fixture_audit(tmp_path, provenance="screenshot_import")
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    original_factory = VisionClient.from_env
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: provider_response(r, captured))) as transport:
        monkeypatch.setattr(page_analysis.VisionClient, "from_env", classmethod(lambda cls, provider_id, **kwargs:
            original_factory(provider_id, **kwargs, client=transport)))
        first = await analyze_page_audit(audit, assets_dir=tmp_path, ledger=ledger, journal_path=tmp_path / "j.db",
                                        provider_id="configured", allow_remote=True)
        before = len(captured)
        second = await analyze_page_audit(audit, assets_dir=tmp_path, ledger=ledger, journal_path=tmp_path / "j.db",
                                         provider_id="configured", allow_remote=True)
    assert len(captured) == before and first.observations == second.observations
    assert first.mode == "vision_remote" and first.direct_vision_controls
    assert first.cost["model"] == "explicit-vision-model"
    for context, payload in captured:
        serialized = json.dumps(payload)
        assert "SECRET_PRODUCT_NAME" not in serialized and "SECRET DESCRIPTION" not in serialized and "98765432" not in serialized
        if context["task"] == "observe" or context.get("review_mode") == "direct_vision":
            assert any(part["type"] == "image_url" for part in payload["messages"][1]["content"])
        if context.get("review_mode") == "direct_vision":
            assert "OBSERVER_TEXT" not in serialized and "current_observation" not in context
        if context["task"] == "review" and context["snapshot"]["section_index"] == 0:
            assert all(person["history"] == [] for person in context["personas"])
            assert "OBSERVER_TEXT_shot_A_1" not in serialized and "OBSERVER_TEXT_shot_B_1" not in serialized
        if context["task"] == "review":
            assert len(context["personas"]) == 1, "Each model context must contain only its own persona's history"
    valid_ids = {s["id"] for s in audit["snapshots"]} | {region.id for obs in first.observations for region in obs.regions}
    assert all(set(finding["evidence_ids"]) <= valid_ids for finding in first.findings)


@pytest.mark.parametrize("invalid", ["box", "age"])
async def test_invalid_grounding_or_identity_is_rejected_and_never_paid_twice(monkeypatch, tmp_path, invalid):
    from spill_market import page_analysis
    from spill_market.page_vision import VisionClient
    configured(monkeypatch)
    captured = []
    audit = fixture_audit(tmp_path, provenance="screenshot_import")
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    original_factory = VisionClient.from_env
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: provider_response(r, captured, invalid_box=invalid == "box", invalid_age=invalid == "age"))) as transport:
        monkeypatch.setattr(page_analysis.VisionClient, "from_env", classmethod(lambda cls, provider_id, **kwargs:
            original_factory(provider_id, **kwargs, client=transport)))
        with pytest.raises(ValueError):
            await analyze_page_audit(audit, assets_dir=tmp_path, ledger=ledger, journal_path=tmp_path / "j.db",
                                     provider_id="configured", allow_remote=True)
        before = len(captured)
        with pytest.raises(PageStageUncertain):
            await analyze_page_audit(audit, assets_dir=tmp_path, ledger=ledger, journal_path=tmp_path / "j.db",
                                     provider_id="configured", allow_remote=True)
    assert len(captured) == before


async def test_cancelled_analysis_reuses_committed_observations(monkeypatch, tmp_path):
    audit = fixture_audit(tmp_path)
    ledger = BudgetLedger(tmp_path / "b.db", 0)
    progress = []
    with pytest.raises(PageAnalysisCancelled):
        await analyze_page_audit(audit, assets_dir=tmp_path, ledger=ledger, journal_path=tmp_path / "j.db",
                                 provider_id="demo", allow_remote=False, on_progress=progress.append,
                                 cancel_check=lambda: bool(progress))
    result = await analyze_page_audit(audit, assets_dir=tmp_path, ledger=ledger, journal_path=tmp_path / "j.db",
                                     provider_id="demo", allow_remote=False)
    assert result.cost["journal"]["cached_stages_this_attempt"] >= 1


async def test_french_demo_narrative_preserves_literal_page_text_and_strict_ages(tmp_path):
    audit = fixture_audit(tmp_path)
    audit["study_snapshot"]["spec"]["locale"] = "fr"
    audit["study_snapshot"]["spec"]["audience"]["age_min"] = 30
    audit["study_snapshot"]["spec"]["audience"]["age_max"] = 60
    audit["study_snapshot"]["spec"]["audience"]["representatives"] = 2
    for person in audit["study_snapshot"]["personas"]:
        person["language"] = "fr"
    report = await analyze_page_audit(audit, assets_dir=tmp_path, ledger=BudgetLedger(tmp_path / "b.db", 0),
                                     journal_path=tmp_path / "j.db", provider_id="demo", allow_remote=False)
    assert report.audience_coverage["ages"] == [35, 55]
    assert all(30 <= review.age <= 60 for review in report.reviews)
    assert "Visible title" in report.observations[0].regions[0].literal_text
    assert all(review.understanding.startswith("Je découvre") for review in report.reviews)
    assert any("fictifs" in text for text in report.limitations)


async def test_unequal_sections_compare_only_common_exposure_horizon(tmp_path):
    audit = fixture_audit(tmp_path)
    audit["snapshots"] = [snapshot for snapshot in audit["snapshots"]
                          if not (snapshot["variant_id"] == "A" and snapshot["section_index"] == 1)]
    report = await analyze_page_audit(audit, assets_dir=tmp_path, ledger=BudgetLedger(tmp_path / "b.db", 0),
                                     journal_path=tmp_path / "j.db", provider_id="demo", allow_remote=False)
    comparison = report.comparisons[0]
    assert comparison["matched_step"] == 0
    assert comparison["final_step_a"] == 0 and comparison["final_step_b"] == 1
    assert comparison["count_a"] == 1 and comparison["count_b"] == 2
    assert comparison["mean_intention_delta"] == 0
    assert comparison["status"] == "descriptive_unequal_coverage"
    assert any("unequal" in text.lower() for text in comparison["limitations"])
