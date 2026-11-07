import concurrent.futures
import json

import httpx
import pytest
from pydantic import BaseModel

from spill_market.gateway import BudgetExceeded, BudgetLedger, SemanticClient


def test_durable_reservations_uncertainty_and_immutable_limits(tmp_path):
    path = tmp_path / "budget.db"
    ledger = BudgetLedger(path, 1, max_calls=3)
    first = ledger.reserve("search", 0.7)
    ledger.mark_uncertain(first)
    reopened = BudgetLedger(path, 1, max_calls=3)
    with pytest.raises(BudgetExceeded):
        reopened.reserve("retry", 0.4)
    summary = reopened.summary()
    assert summary["uncertain_usd"] == 0.7
    assert summary["reserved_usd"] == 0.7
    with pytest.raises(ValueError, match="immutable"):
        BudgetLedger(path, 2, max_calls=3)
    reopened.settle(first, 0.5, {"credits": 1})
    assert reopened.summary()["confirmed_usd"] == 0.5
    reopened.settle(first, 0.5)
    with pytest.raises(ValueError):
        reopened.settle(first, 0.1)


def test_concurrent_clients_cannot_overspend_or_exceed_call_count(tmp_path):
    path = tmp_path / "budget.db"
    BudgetLedger(path, 1, max_calls=2)
    def reserve(_):
        try:
            return BudgetLedger(path, 1, max_calls=2).reserve("parallel", 0.4)
        except BudgetExceeded:
            return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(value is not None for value in pool.map(reserve, range(12))) == 2
    summary = BudgetLedger(path, 1, max_calls=2).summary()
    assert summary["calls"] == 2
    assert summary["reserved_usd"] == 0.8


def test_settlement_cannot_hide_provider_overrun(tmp_path):
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    reservation = ledger.reserve("provider", 0.5)
    ledger.settle(reservation, 1.2)
    assert ledger.summary()["confirmed_usd"] == 1.2
    assert ledger.summary()["over_budget"] is True
    with pytest.raises(BudgetExceeded):
        ledger.reserve("again", 0.01)


@pytest.mark.parametrize("amount", [-1, float("nan"), float("inf")])
def test_reject_invalid_costs(tmp_path, amount):
    with pytest.raises(ValueError):
        BudgetLedger(tmp_path / "b.db", amount)


async def test_semantic_json_is_validated_and_usage_settles_actual_cost(tmp_path):
    class Answer(BaseModel):
        text: str
    calls = []
    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"text":"evidence"}'}}],
                                         "usage": {"prompt_tokens": 20, "completion_tokens": 10}})
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        semantic = SemanticClient(ledger, base_url="https://llm.example/v1", api_key="test-only",
                                  model="test", input_usd_per_million=1,
                                  output_usd_per_million=2, max_output_tokens=100, client=client)
        answer = await semantic.summarize("extract evidence", "untrusted document", Answer)
    assert answer.text == "evidence"
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert "tools" not in calls[0]
    assert ledger.summary()["confirmed_usd"] == 0.00004


async def test_semantic_timeout_retains_reservation_and_no_automatic_retry(tmp_path):
    class Answer(BaseModel):
        text: str
    def respond(request):
        raise httpx.ReadTimeout("simulated", request=request)
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        semantic = SemanticClient(ledger, base_url="https://llm.example/v1", api_key="test-only",
                                  model="test", input_usd_per_million=1,
                                  output_usd_per_million=2, max_output_tokens=100, client=client)
        with pytest.raises(httpx.ReadTimeout):
            await semantic.summarize("extract", "text", Answer)
    assert ledger.summary()["calls"] == 1
    assert ledger.summary()["uncertain_usd"] > 0


async def test_semantic_configurable_reasoning_and_token_parameter(tmp_path):
    class Answer(BaseModel):
        text: str
    captured = []
    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"text":"ok"}'}}]})
    ledger = BudgetLedger(tmp_path / "b.db", 1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        semantic = SemanticClient(ledger, base_url="https://example.com/v1", api_key="test-only", model="test",
                                  input_usd_per_million=1, output_usd_per_million=1, max_output_tokens=100,
                                  reasoning_effort="none", token_parameter="max_tokens", client=client)
        await semantic.summarize("extract", "text", Answer)
    assert captured[0]["reasoning_effort"] == "none"
    assert captured[0]["max_tokens"] == 100
    assert "max_completion_tokens" not in captured[0]
    assert ledger.summary()["uncertain_usd"] > 0
