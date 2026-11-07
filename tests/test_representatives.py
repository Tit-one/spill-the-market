import json
import asyncio

import httpx
import pytest

from spill_market.gateway import BudgetExceeded, BudgetLedger, SemanticClient
from spill_market.models import MediaPlan, Persona, Placement, ProductSpec, StudySpec
from spill_market.representatives import RepresentativeUncertain, enrich_representatives


def inputs(enabled=True, count=12):
    product = ProductSpec(name="RenderDesk", description="A creative GPU rendering tool.", unit_price_cents=2000)
    spec = StudySpec(product=product).model_copy(update={"use_representative_llm": enabled})
    personas = [Persona(id=f"p{i}", name=f"Person {i}", age=20 + i % 50, language="en", profession="Creator",
                        budget_cents=5000, need_fit=0.7, trust=0.5, price_sensitivity=0.5,
                        social_sensitivity=0.5, fatigue_tolerance=0.5, channels={"search": 0.8}) for i in range(count)]
    plans = [MediaPlan(id="one", name="Search demo", price_cents=2000, media_budget_cents=2000,
                       placements=[Placement(channel="search", creative="Try GPU rendering")])]
    return spec, personas, plans


def response(request, *, invalid=False):
    body = json.loads(request.content)
    evidence = json.loads(json.loads(body["messages"][1]["content"])["untrusted_evidence"])
    reactions = [{"persona_id": person["id"] if not invalid else "invented-id", "channel": "search",
                  "understanding": "A rendering workflow", "objection": "Need to see a trial",
                  "comment": "I would try it before buying.", "response_multiplier": 1.1}
                 for person in evidence["personas"]]
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"reactions": reactions})}}],
                                     "usage": {"prompt_tokens": 100, "completion_tokens": 200}})


def factory(monkeypatch, client):
    from spill_market import representatives
    monkeypatch.setattr(representatives.SemanticClient, "from_env", classmethod(lambda cls, ledger:
        SemanticClient(ledger, base_url="https://llm.example/v1", api_key="test-only", model="test-model",
                       input_usd_per_million=1, output_usd_per_million=1, max_output_tokens=2000, client=client)))


async def test_optional_reps_are_budgeted_batched_validated_and_cached(monkeypatch, tmp_path):
    calls = []
    def respond(request):
        calls.append(request)
        return response(request)
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    spec, personas, plans = inputs()
    before = [p.model_dump() for p in personas]
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        factory(monkeypatch, client)
        first = await enrich_representatives(spec, personas, None, plans, ledger=ledger, cache_dir=tmp_path / "cache")
        second = await enrich_representatives(spec, personas, None, plans, ledger=ledger, cache_dir=tmp_path / "cache")
    assert len(calls) == 2 and ledger.summary()["calls"] == 2
    assert len(first["reactions"]) == 12 and first == second
    assert first["response_multipliers"]["search"] == pytest.approx(1.1)
    assert "unvalidated" in first["assumption"].lower()
    assert [p.model_dump() for p in personas] == before
    markers = list((tmp_path / "cache").glob("*.dispatched.json"))
    assert len(markers) == 2
    assert all(json.loads(marker.read_text())["status"] == "committed" for marker in markers)


async def test_disabled_reps_do_not_read_configuration_or_touch_network(monkeypatch, tmp_path):
    from spill_market import representatives
    monkeypatch.setattr(representatives.SemanticClient, "from_env", classmethod(lambda *args: (_ for _ in ()).throw(AssertionError("configuration read"))))
    spec, personas, plans = inputs(enabled=False)
    result = await enrich_representatives(spec, personas, None, plans, ledger=None, cache_dir=tmp_path / "cache")
    assert result["reactions"] == [] and result["response_multipliers"] == {}
    assert not (tmp_path / "cache").exists()


async def test_invalid_persona_id_is_rejected_and_not_retried(monkeypatch, tmp_path):
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    spec, personas, plans = inputs(count=2)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response(request, invalid=True))) as client:
        factory(monkeypatch, client)
        with pytest.raises(ValueError, match="persona"):
            await enrich_representatives(spec, personas, None, plans, ledger=ledger, cache_dir=tmp_path / "cache")
        with pytest.raises(RepresentativeUncertain):
            await enrich_representatives(spec, personas, None, plans, ledger=ledger, cache_dir=tmp_path / "cache")
    assert ledger.summary()["calls"] == 1


async def test_ambiguous_batch_blocks_automatic_retry_after_restart(monkeypatch, tmp_path):
    def timeout(request):
        raise httpx.ReadTimeout("ambiguous charge", request=request)
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    spec, personas, plans = inputs(count=2)
    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        factory(monkeypatch, client)
        with pytest.raises(httpx.ReadTimeout):
            await enrich_representatives(spec, personas, None, plans, ledger=ledger, cache_dir=tmp_path / "cache")
        restarted = BudgetLedger(tmp_path / "b.db", 1)
        with pytest.raises(RepresentativeUncertain):
            await enrich_representatives(spec, personas, None, plans, ledger=restarted, cache_dir=tmp_path / "cache")
    assert restarted.summary()["calls"] == 1 and restarted.summary()["uncertain_usd"] > 0


async def test_zero_budget_cannot_send_representative_inference(monkeypatch, tmp_path):
    def no_network(request):
        raise AssertionError("zero-budget network call")
    ledger = BudgetLedger(tmp_path / "b.db", 0)
    spec, personas, plans = inputs(count=2)
    async with httpx.AsyncClient(transport=httpx.MockTransport(no_network)) as client:
        factory(monkeypatch, client)
        with pytest.raises(BudgetExceeded):
            await enrich_representatives(spec, personas, None, plans, ledger=ledger, cache_dir=tmp_path / "cache")
    assert ledger.summary()["calls"] == 0


async def test_cancellation_between_batches_preserves_completed_cache(monkeypatch, tmp_path):
    from spill_market.simulation import SimulationCancelled
    calls = []
    def respond(request):
        calls.append(request)
        return response(request)
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    spec, personas, plans = inputs(count=12)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        factory(monkeypatch, client)
        with pytest.raises(SimulationCancelled):
            await enrich_representatives(spec, personas, None, plans, ledger=ledger,
                                         cache_dir=tmp_path / "cache", cancel_check=lambda: len(calls) == 1)
        result = await enrich_representatives(spec, personas, None, plans, ledger=ledger, cache_dir=tmp_path / "cache")
    assert len(calls) == 2 and len(result["reactions"]) == 12


@pytest.mark.parametrize("change", ["age", "unknown_channel", "unplanned_channel", "nan", "outside_range"])
async def test_untrusted_reactions_cannot_change_age_channel_or_multiplier_bounds(monkeypatch, tmp_path, change):
    def respond(request):
        result = response(request)
        body = result.json()
        generated = json.loads(body["choices"][0]["message"]["content"])
        row = generated["reactions"][0]
        if change == "age":
            row["age"] = 99
        elif change == "unknown_channel":
            row["channel"] = "invented"
        elif change == "unplanned_channel":
            row["channel"] = "tiktok"
        else:
            row["response_multiplier"] = float("nan") if change == "nan" else 1.21
        body["choices"][0]["message"]["content"] = json.dumps(generated)
        return httpx.Response(200, json=body)
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    spec, personas, plans = inputs(count=2)
    before = [person.age for person in personas]
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        factory(monkeypatch, client)
        with pytest.raises(ValueError):
            await enrich_representatives(spec, personas, None, plans, ledger=ledger, cache_dir=tmp_path / "cache")
    assert [person.age for person in personas] == before


async def test_concurrent_representative_dispatch_does_not_repeat_batch(monkeypatch, tmp_path):
    started, finish = asyncio.Event(), asyncio.Event()
    calls = []
    async def respond(request):
        calls.append(request)
        started.set()
        await finish.wait()
        return response(request)
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    spec, personas, plans = inputs(count=2)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        factory(monkeypatch, client)
        running = asyncio.create_task(enrich_representatives(spec, personas, None, plans, ledger=ledger,
                                                             cache_dir=tmp_path / "cache"))
        await started.wait()
        try:
            with pytest.raises(RepresentativeUncertain):
                await enrich_representatives(spec, personas, None, plans, ledger=ledger, cache_dir=tmp_path / "cache")
        finally:
            finish.set()
        await running
    assert len(calls) == 1
