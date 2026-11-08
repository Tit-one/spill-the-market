import hashlib
import io
import json

import httpx
import pytest
from PIL import Image
from pydantic import BaseModel

from spill_market.gateway import BudgetLedger
from spill_market.page_models import PageSnapshot
from spill_market.page_vision import PageDispatchJournal, PageStageUncertain, VisionClient, load_snapshot_image, vision_provider_status


def configured(monkeypatch):
    for name, value in {"SPILL_VISION_ENABLED": "true", "SPILL_LLM_BASE_URL": "https://api.example/v1",
                        "SPILL_LLM_MODEL": "explicit-vision-model", "SPILL_LLM_API_KEY": "test-secret-never-cache",
                        "SPILL_LLM_INPUT_USD_PER_MILLION": "0.1", "SPILL_LLM_OUTPUT_USD_PER_MILLION": "0.5",
                        "SPILL_VISION_MAX_IMAGE_INPUT_TOKENS": "16000"}.items():
        monkeypatch.setenv(name, value)


def picture(tmp_path, name="shot", provenance="screenshot_import"):
    output = io.BytesIO()
    Image.new("RGB", (160, 100), "white").save(output, "JPEG")
    data = output.getvalue()
    (tmp_path / f"{name}.jpg").write_bytes(data)
    snapshot = PageSnapshot(id=name, variant_id="A", section_index=0, viewport="desktop", width=160, height=100,
                            scroll_y=0, page_height=200, content_hash=hashlib.sha256(data).hexdigest(), provenance=provenance)
    return snapshot


class Answer(BaseModel):
    text: str


def test_provider_status_reads_no_credentials_or_network(monkeypatch):
    configured(monkeypatch)
    from spill_market import page_vision
    class PublicOnly(dict):
        def get(self, key, default=None):
            if "API_KEY" in key:
                raise AssertionError("credential value loaded during metadata request")
            return super().get(key, default)
    monkeypatch.setattr(page_vision.os, "environ", PublicOnly({
        "SPILL_VISION_ENABLED": "true", "SPILL_LLM_BASE_URL": "https://api.example/v1",
        "SPILL_LLM_MODEL": "explicit-vision-model", "SPILL_LLM_API_KEY": "dummy-unread-value",
        "SPILL_LLM_INPUT_USD_PER_MILLION": "0.1", "SPILL_LLM_OUTPUT_USD_PER_MILLION": "0.5",
        "SPILL_VISION_MAX_IMAGE_INPUT_TOKENS": "16000"}))
    monkeypatch.setattr(page_vision.httpx, "AsyncClient", lambda **kw: (_ for _ in ()).throw(AssertionError("network")))
    providers = vision_provider_status()
    provider = next(item for item in providers if item["id"] == "configured")
    assert provider["available"] is True and provider["scope"] == "remote"
    assert provider["pricing"]["max_image_input_tokens"] == 16000
    assert "test-secret" not in json.dumps(providers)


def test_remote_requires_explicit_consent_and_image_liability_before_dispatch(monkeypatch, tmp_path):
    configured(monkeypatch)
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    with pytest.raises(PermissionError):
        VisionClient.from_env("configured", ledger=ledger, allow_remote=False)
    monkeypatch.delenv("SPILL_VISION_MAX_IMAGE_INPUT_TOKENS")
    with pytest.raises(ValueError, match="IMAGE"):
        VisionClient.from_env("configured", ledger=ledger, allow_remote=True)
    assert ledger.summary()["calls"] == 0


async def test_actual_jpeg_payload_usage_and_durable_cache(monkeypatch, tmp_path):
    configured(monkeypatch)
    snapshot = picture(tmp_path)
    image = load_snapshot_image(snapshot, tmp_path)
    calls = []
    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"text":"visible text"}'}}],
                                         "usage": {"prompt_tokens": 100, "completion_tokens": 20}})
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    journal = PageDispatchJournal(tmp_path / "journal.db", "audit", {"image": image.sha256})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
        client = VisionClient.from_env("configured", ledger=ledger, allow_remote=True, client=transport)
        async def operation(dispatch):
            return await client.complete_json("Read visible content only", {"snapshot_id": snapshot.id}, Answer,
                                               images=[image], dispatch=dispatch)
        first = await journal.run("observe:shot", {"hash": image.sha256}, client.configuration,
                                  operation, lambda result: result.model_dump(), Answer.model_validate)
        second = await journal.run("observe:shot", {"hash": image.sha256}, client.configuration,
                                   operation, lambda result: result.model_dump(), Answer.model_validate)
    assert first == second and first.text == "visible text" and len(calls) == 1
    assert calls[0]["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert calls[0]["response_format"]["type"] == "json_schema" and "tools" not in calls[0]
    assert ledger.summary()["confirmed_usd"] == 0.00002
    assert journal.summary()["cached_stages_this_attempt"] == 1


async def test_unknown_remote_charge_and_restart_never_repeat(monkeypatch, tmp_path):
    configured(monkeypatch)
    def respond(request):
        raise httpx.ReadTimeout("ambiguous dispatch", request=request)
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
        client = VisionClient.from_env("configured", ledger=ledger, allow_remote=True, client=transport)
        async def operation(dispatch):
            return await client.complete_json("Read only", {"task": "review"}, Answer, dispatch=dispatch)
        journal = PageDispatchJournal(tmp_path / "j.db", "audit", {})
        with pytest.raises(httpx.ReadTimeout):
            await journal.run("review:one", {}, client.configuration, operation, lambda x: x.model_dump(), Answer.model_validate)
        reopened = PageDispatchJournal(tmp_path / "j.db", "audit", {})
        with pytest.raises(PageStageUncertain):
            await reopened.run("review:one", {}, client.configuration, operation, lambda x: x.model_dump(), Answer.model_validate)
    assert ledger.summary()["calls"] == 1 and ledger.summary()["uncertain_usd"] > 0


async def test_local_ollama_has_no_auth_or_real_cost(monkeypatch, tmp_path):
    monkeypatch.setenv("SPILL_VISION_LOCAL_MODEL", "vision-local")
    monkeypatch.setenv("SPILL_VISION_LOCAL_URL", "http://127.0.0.1:11434/v1")
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"text":"local"}'}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
        client = VisionClient.from_env("local", ledger=None, allow_remote=False, client=transport)
        journal = PageDispatchJournal(tmp_path / "j.db", "local-audit", {})
        async def operation(dispatch):
            return await client.complete_json("Read only", {}, Answer, dispatch=dispatch)
        result = await journal.run("one", {}, client.configuration, operation, lambda x: x.model_dump(), Answer.model_validate)
    assert result.text == "local" and "authorization" not in calls[0].headers
    assert client.scope == "local" and client.maximum_call_usd == 0
    monkeypatch.setenv("SPILL_VISION_LOCAL_URL", "http://example.com/v1")
    with pytest.raises(ValueError, match="loopback"):
        VisionClient.from_env("local", ledger=None, allow_remote=False)


def test_snapshot_images_use_only_validated_ids_hashes_and_actual_dimensions(tmp_path):
    snapshot = picture(tmp_path)
    snapshot.image_url = "file:///unrelated-private-file"
    assert load_snapshot_image(snapshot, tmp_path).width == 160
    snapshot.content_hash = "0" * 64
    with pytest.raises(ValueError, match="hash"):
        load_snapshot_image(snapshot, tmp_path)
    snapshot.id = "../outside"
    with pytest.raises(ValueError, match="ID"):
        load_snapshot_image(snapshot, tmp_path)


def test_truncated_jpeg_is_rejected_before_any_inference(tmp_path):
    snapshot = picture(tmp_path)
    path = tmp_path / (snapshot.id + ".jpg")
    data = path.read_bytes()[:-20]
    path.write_bytes(data)
    snapshot.content_hash = hashlib.sha256(data).hexdigest()
    with pytest.raises(ValueError, match="JPEG"):
        load_snapshot_image(snapshot, tmp_path)


async def test_provider_overrun_is_recorded_and_halts_analysis(monkeypatch, tmp_path):
    configured(monkeypatch)
    ledger = BudgetLedger(tmp_path / "b.db", 0.05)
    def respond(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"text":"unexpected"}'}}],
                                         "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 20}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
        client = VisionClient.from_env("configured", ledger=ledger, allow_remote=True, client=transport)
        journal = PageDispatchJournal(tmp_path / "j.db", "audit", {})
        async def operation(dispatch):
            return await client.complete_json("Read only", {}, Answer, dispatch=dispatch)
        with pytest.raises(ValueError, match="bound"):
            await journal.run("one", {}, client.configuration, operation, lambda x: x.model_dump(), Answer.model_validate)
    assert ledger.summary()["confirmed_usd"] > 0.05 and ledger.summary()["over_budget"] is True


async def test_zero_budget_refusal_leaves_no_ambiguous_stage(monkeypatch, tmp_path):
    configured(monkeypatch)
    from spill_market.gateway import BudgetExceeded
    def forbidden(request):
        raise AssertionError("zero-budget provider send")
    ledger = BudgetLedger(tmp_path / "b.db", 0)
    journal = PageDispatchJournal(tmp_path / "j.db", "audit", {})
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as transport:
        client = VisionClient.from_env("configured", ledger=ledger, allow_remote=True, client=transport)
        async def operation(dispatch):
            return await client.complete_json("Read only", {}, Answer, dispatch=dispatch)
        for _ in range(2):
            with pytest.raises(BudgetExceeded):
                await journal.run("one", {}, client.configuration, operation, lambda x: x.model_dump(), Answer.model_validate)
    assert journal.summary()["uncertain_stages"] == 0 and ledger.summary()["calls"] == 0


async def test_missing_usage_retains_maximum_and_committed_result_is_reusable(monkeypatch, tmp_path):
    configured(monkeypatch)
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"text":"usable but unpriced"}'}}]})
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    journal = PageDispatchJournal(tmp_path / "j.db", "audit", {})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
        client = VisionClient.from_env("configured", ledger=ledger, allow_remote=True, client=transport)
        async def operation(dispatch):
            return await client.complete_json("Read only", {}, Answer, dispatch=dispatch)
        for _ in range(2):
            result = await journal.run("one", {}, client.configuration, operation, lambda x: x.model_dump(), Answer.model_validate)
    assert result.text == "usable but unpriced" and len(calls) == 1
    assert ledger.summary()["uncertain_usd"] == pytest.approx(client.maximum_call_usd)


async def test_journal_concurrent_claim_and_frozen_config_guard(tmp_path):
    import asyncio
    started, release = asyncio.Event(), asyncio.Event()
    one = PageDispatchJournal(tmp_path / "j.db", "audit", {})
    two = PageDispatchJournal(tmp_path / "j.db", "audit", {})
    async def operation(dispatch):
        started.set()
        await release.wait()
        return Answer(text="committed once")
    running = asyncio.create_task(one.run("one", {}, {"model": "fixed"}, operation,
                                         lambda x: x.model_dump(), Answer.model_validate))
    await started.wait()
    try:
        with pytest.raises(PageStageUncertain):
            await two.run("one", {}, {"model": "fixed"}, operation, lambda x: x.model_dump(), Answer.model_validate)
    finally:
        release.set()
    await running
    with pytest.raises(PageStageUncertain):
        await two.run("one", {}, {"model": "changed"}, operation, lambda x: x.model_dump(), Answer.model_validate)


def test_vision_opt_in_and_local_cloud_model_boundaries(monkeypatch):
    configured(monkeypatch)
    monkeypatch.setenv("SPILL_VISION_ENABLED", "false")
    assert next(p for p in vision_provider_status() if p["id"] == "configured")["available"] is False
    monkeypatch.setenv("SPILL_VISION_LOCAL_MODEL", "vision-model:cloud")
    with pytest.raises(ValueError, match="cloud"):
        VisionClient.from_env("local", ledger=None, allow_remote=False)
