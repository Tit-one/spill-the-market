import json

import pytest

from spill_market.models import EvidenceSource, Finding, StudySpec, TrendReport


def spec(**market):
    return StudySpec.model_validate({
        "product": {"name": "Fieldnote", "description": "An offline note organizer for creative teams.",
                    "category": "software", "unit_price_cents": 2900},
        "objective": "market_discovery", "market": market, "locale": "fr",
    })


def report(units=12):
    return {"metadata": {"exploration_selected_id": "balanced"}, "scenarios": [{
        "plan_id": "balanced", "is_baseline": False, "mean_units": units, "mean_revenue_cents": units * 2900,
        "age_segments": [
            {"age_min": 18, "age_max": 24, "label": "18–24", "population": 100, "units": units / 2,
             "conversion_rate": units / 200, "revenue_cents": units * 1450, "channels": []},
            {"age_min": 25, "age_max": 34, "label": "25–34", "population": 900, "units": units / 2,
             "conversion_rate": units / 1800, "revenue_cents": units * 1450, "channels": []}],
        "channels": [{"channel": "search", "unique_reach": 100, "units": units, "spend_cents": 2000,
                      "attributed_conversion_rate": units / 100}],
        "market_switching": {"enabled": True, "status": "unvalidated_assumption", "population": 1000,
            "buyers": units, "incumbent_users": 600, "non_incumbent_users": 400,
            "switchers": units / 2, "new_to_category_buyers": units / 2, "retained_incumbents": 600 - units / 2,
            "new_to_category_nonbuyers": 400 - units / 2, "mean_switching_acceptance": .7,
            "incumbent_share": .6, "switching_friction": .5, "assumptions": []},
    }]}


def test_no_sources_cannot_invent_competitors_or_market_size():
    from spill_market.market_analysis import build_market_analysis
    result = build_market_analysis(spec(), None, report())
    assert result["status"] == "hypotheses_only"
    assert result["competitors"] == []
    assert result["coverage"]["market_size_status"] == "unknown"
    assert result["switching"]["market_projection"] is None
    assert any(row["kind"] == "research_gap" for row in result["barriers"])
    assert result["segment_recommendation"]["age_min"] == 18  # rate, not raw population/units
    assert result["segment_recommendation"]["status"] == "hypothesis"
    json.dumps(result, allow_nan=False)


def test_competitors_and_pain_points_keep_actual_source_provenance():
    from spill_market.market_analysis import build_market_analysis
    text = "Alternative to Fieldnote: Existing Notes. Export is expensive and migration is difficult."
    evidence = TrendReport(topic="notes", mode="urls", sources=[
        EvidenceSource(id="real", title="Existing Notes — Pricing", content=text,
                       kind="web", url="https://notes.example/pricing")],
        pain_points=[Finding(text="Export is expensive and migration is difficult.", source_ids=["real"], status="observed"),
                     Finding(text="invented unsupported pain", source_ids=["missing"], status="observed")],
        coverage={"competitor_mentions": [{"text": text, "source_ids": ["real"]}]})
    result = build_market_analysis(spec(competitor_urls=["https://notes.example/pricing", "https://unknown.example"]), evidence, report())
    assert result["status"] == "evidence_informed_simulation"
    assert result["coverage"]["real_source_count"] == 1
    first, unknown = result["competitors"]
    assert first["source_ids"] == ["real"] and first["evidence_status"] == "source_statement"
    assert first["excerpts"] and all(excerpt in text for excerpt in first["excerpts"])
    assert unknown["evidence_status"] == "unread_reference" and unknown["source_ids"] == []
    assert "invented unsupported pain" not in json.dumps(result)
    assert all(row["source_ids"] == ["real"] for row in result["barriers"] if row["status"] == "source_statement")


def test_demo_is_never_mistaken_for_observed_competition():
    from spill_market.market_analysis import build_market_analysis
    evidence = TrendReport(topic="demo", mode="demo", sources=[EvidenceSource(
        id="fiction", title="Fictional alternative", content="Competitor X has one million users.",
        kind="demo", url="https://fiction.example")])
    result = build_market_analysis(spec(competitor_urls=["https://fiction.example"]), evidence, report())
    assert result["status"] == "demo"
    assert result["coverage"]["real_source_count"] == 0
    assert result["competitors"][0]["evidence_status"] == "fictional"
    assert result["switching"]["market_projection"] is None


@pytest.mark.parametrize("units", [0, .2])
def test_no_confident_target_or_channel_with_no_or_very_few_buyers(units):
    from spill_market.market_analysis import build_market_analysis
    result = build_market_analysis(spec(), None, report(units))
    assert result["segment_recommendation"]["status"] == "inconclusive"
    assert result["channel_recommendation"]["status"] == "inconclusive"
    assert result["segment_recommendation"]["age_min"] is None
    assert result["channel_recommendation"]["channel"] is None


def test_market_projection_is_only_explicit_linear_assumption_not_extra_sales():
    from spill_market.market_analysis import build_market_analysis
    result = build_market_analysis(spec(addressable_population=100_000), None, report())
    switching = result["switching"]
    assert switching["switchers"] + switching["new_to_category_buyers"] == switching["buyers"] == 12
    assert switching["market_projection"] == {"addressable_population": 100_000,
        "estimated_switchers": 600, "status": "unvalidated_extrapolation"}
    assert result["coverage"]["market_size_status"] == "user_assumption"


def test_ties_and_overlapping_replica_ranges_do_not_select_a_target():
    from spill_market.market_analysis import build_market_analysis
    payload = report()
    age_rows = payload["scenarios"][0]["age_segments"]
    age_rows[0]["conversion_rate_interval"] = [0, .1]
    age_rows[1]["conversion_rate_interval"] = [0, .08]
    result = build_market_analysis(spec(), None, payload)
    assert result["segment_recommendation"]["status"] == "inconclusive"
    age_rows[1]["conversion_rate"] = age_rows[0]["conversion_rate"]
    for row in age_rows:
        row.pop("conversion_rate_interval")
    result = build_market_analysis(spec(), None, payload)
    assert result["segment_recommendation"]["status"] == "inconclusive"


def test_product_comparison_is_not_itself_a_competitor_and_query_identity_is_preserved():
    from spill_market.market_analysis import build_market_analysis
    own = 'https://catalog.example/item?id=ours'
    theirs = 'https://catalog.example/item?id=theirs'
    sentence = 'Alternative to Existing Notes: Our product.'
    evidence = TrendReport(topic='notes', mode='urls', sources=[
        EvidenceSource(id='own', title='Our product', url=own, kind='web', content=sentence),
        EvidenceSource(id='theirs', title='Existing Notes', url=theirs, kind='web', content='Existing Notes pricing.')],
        coverage={'competitor_mentions': [{'text': sentence, 'source_ids': ['own']}]})
    result = build_market_analysis(spec(product_url=own, competitor_urls=[theirs]), evidence, report())
    assert len(result['competitors']) == 1
    assert result['competitors'][0]['source_ids'] == ['theirs']
    assert result['competitors'][0]['url'] == theirs


def test_nondefault_scheme_port_and_identity_query_survive_but_tokens_do_not():
    from spill_market.market_analysis import _url
    from spill_market.research import _provenance_url
    supplied = 'https://user:password@catalog.example:80/item?id=42&token=private&utm_source=ad#part'
    for normalize in (_url, _provenance_url):
        result = normalize(supplied)
        assert result == 'https://catalog.example:80/item?id=42'


def test_redacted_codes_keep_distinct_internal_reference_identity():
    from spill_market.market_analysis import build_market_analysis
    from spill_market.research import _source
    own = 'https://catalog.example/item?code=ours'
    theirs = 'https://catalog.example/item?code=theirs'
    own_source = _source('Our product', 'Alternative to Existing Notes: Our product.', 'web', url=own)
    other_source = _source('Existing Notes', 'A competing organizer.', 'web', url=theirs)
    evidence = TrendReport(topic='notes', mode='urls', sources=[own_source, other_source], coverage={
        'competitor_mentions': [{'text': own_source.content, 'source_ids': [own_source.id]}]})
    result = build_market_analysis(spec(product_url=own, competitor_urls=[theirs]), evidence, report())
    assert len(result['competitors']) == 1
    assert result['competitors'][0]['name'] == 'Existing Notes'
    assert result['competitors'][0]['source_ids'] == [other_source.id]


def test_common_query_secrets_are_not_exported_from_references():
    from spill_market.research import _source
    source = _source('Private query fixture', 'Public source text.', 'web',
        url='https://catalog.example/item?id=42&jwt=FAKEJWT&pwd=FAKEPWD&sid=FAKESID&token=FAKETOKEN')
    exported = source.model_dump_json()
    assert all(value not in exported for value in ('FAKEJWT', 'FAKEPWD', 'FAKESID', 'FAKETOKEN'))
    assert 'id=42' in source.url


def test_third_segment_with_wide_uncertainty_prevents_a_distinct_ranking():
    from spill_market.market_analysis import build_market_analysis
    payload = report()
    payload['scenarios'][0]['age_segments'] = [
        {'age_min': age, 'age_max': age + 6, 'population': 100, 'units': rate * 100,
         'conversion_rate': rate, 'conversion_rate_interval': bounds}
        for age, rate, bounds in [(18, .10, [.09, .11]), (25, .08, [.07, .085]), (35, .07, [0, .20])]]
    result = build_market_analysis(spec(), None, payload)
    assert result['segment_recommendation']['status'] == 'inconclusive'


def test_market_findings_export_in_all_formats_and_html_escapes_source_text():
    from spill_market.exports import export_report
    payload = report()
    payload["market_analysis"] = {"status": "hypotheses_only", "competitors": [],
        "barriers": [{"title": "<script>attack()</script>", "detail": "Needs evidence", "status": "assumption", "source_ids": ['ev_unique']}],
        "sources": [{'id': 'ev_unique', 'title': 'Unique reference source', 'url': 'https://reference.example',
                     'retrieved_at': '2026-11-08', 'published_at': None, 'kind': 'web'}]}
    for format in ("json", "csv", "md", "html"):
        output, _, _ = export_report(payload, format)
        assert "hypotheses_only" in output
        assert "Needs evidence" in output
        assert 'ev_unique' in output and 'Unique reference source' in output
        if format == "html":
            assert "<script>attack()</script>" not in output
            assert "&lt;script&gt;" in output
