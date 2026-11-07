from spill_market.models import EvidenceSource, ProductSpec, TrendReport


def test_age_suggestion_is_grounded_when_explicit_and_hypothetical_otherwise():
    from spill_market.services import age_recommendation
    product = ProductSpec(name="Demo game", description="A fictional cooperative game", category="game", unit_price_cents=2000)
    report = TrendReport(topic="Demo", mode="offline", sources=[EvidenceSource(
        id="source-a", title="Provided audience brief", kind="import", content="Audience: adults ages 40–50.",
    )])
    sourced = age_recommendation(product, report)
    assert sourced["range"] == [40, 50]
    assert sourced["source_ids"] == ["source-a"]
    assert sourced["status"] == "inferred"
    assumed = age_recommendation(product, TrendReport(topic="Demo", mode="demo"))
    assert assumed["status"] == "assumption"
    assert assumed["source_ids"] == []
    assert assumed["range"] == [18, 35]


def test_automatic_target_is_only_a_proposal_until_user_confirms(tmp_path):
    import asyncio
    from spill_market.models import AudienceSpec, ImportedDocument, ResearchRequest, StudySpec
    from spill_market.services import prepare_study, research_study
    from spill_market.storage import Store
    store = Store(tmp_path)
    spec = StudySpec(
        product=ProductSpec(name="Demo game", description="A fictional cooperative game", category="game", unit_price_cents=2000),
        audience=AudienceSpec(age_min=18, age_max=25, auto_age=True),
        research=ResearchRequest(mode="offline", documents=[ImportedDocument(name="Audience brief", text="Audience: adults ages 40–50.")]),
    )
    study = asyncio.run(prepare_study(store, spec))
    assert [study["spec"]["audience"]["age_min"], study["spec"]["audience"]["age_max"]] == [18, 25]
    assert study["research"]["recommended_age_range"] == [40, 50]
    assert all(18 <= p["age"] <= 25 for p in study["personas"])
    asyncio.run(research_study(store, study["id"], spec.research))
    updated = store.get_study(study["id"])
    assert [updated["spec"]["audience"]["age_min"], updated["spec"]["audience"]["age_max"]] == [18, 25]


def test_research_refresh_preserves_locked_ids_after_channel_edit(tmp_path):
    import asyncio
    from spill_market.examples import examples
    from spill_market.models import StudySpec
    from spill_market.services import prepare_study, research_study
    from spill_market.storage import Store
    store = Store(tmp_path)
    spec = StudySpec.model_validate(examples()[1]["spec"])
    study = asyncio.run(prepare_study(store, spec))
    edited = study["plans"]
    line = edited[1]["placements"][0]
    line.update(channel="search", format="search", locked=True)
    locked_id = line["id"]
    store.update_study(study["id"], plans=edited)
    asyncio.run(research_study(store, study["id"], spec.research))
    result = store.get_study(study["id"])["plans"][1]["placements"]
    assert len({p["id"] for p in result}) == len(result)
    locked = next(p for p in result if p["id"] == locked_id)
    assert locked["locked"] and locked["channel"] == "search"
