import asyncio


def test_explicit_ai_context_is_frozen_and_reported_without_direct_sales(tmp_path, monkeypatch):
    from spill_market import representatives
    from spill_market.examples import examples
    from spill_market.models import StudySpec
    from spill_market.services import prepare_study
    from spill_market.storage import Store
    from spill_market.worker import execute_run

    async def enrich(spec, personas, research, plans, *, ledger, cache_dir, cancel_check=None):
        return {"reactions": [{"persona_id": personas[0].id, "channel": "tiktok", "comment": "Show gameplay"}],
                "response_multipliers": {"tiktok": 1.1}, "model": "test-provider", "assumption": "Unvalidated"}
    monkeypatch.setattr(representatives, "enrich_representatives", enrich)
    spec = StudySpec.model_validate(examples()[0]["spec"])
    spec.rounds = 2
    spec.audience.population = 60
    spec.use_representative_llm = True
    spec.api_budget_usd = 1
    spec.exploration_repetitions = spec.validation_repetitions = 1
    store = Store(tmp_path)
    study = asyncio.run(prepare_study(store, spec))
    run = store.create_run(study["id"], spec.model_dump(), study["plans"])
    result = execute_run(tmp_path, run["id"])
    assert result["metadata"]["semantic_reactions"][0]["comment"] == "Show gameplay"
    assert result["metadata"]["response_multipliers"] == {"tiktok": 1.1}
    assert result["metadata"]["real_api_cost"]["scope"] == "study_cumulative"
    assert result["metadata"]["real_api_cost"]["calls"] == 0
