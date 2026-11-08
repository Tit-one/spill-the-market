import json

import numpy as np
import pytest

from spill_market import simulation
from spill_market.models import AudienceSpec, MarketAssumptions, MediaPlan, Placement, ProductSpec, StudySpec
from spill_market.personas import initialize_population
from spill_market.reports import summarize_scenario


def product():
    return ProductSpec(name="Ordinary editor", description="An ordinary offline editor for creative work.",
                       unit_price_cents=100)


def plan(channel="search", **changes):
    values = dict(id="market", name="Market", price_cents=100, media_budget_cents=0, adaptive=False,
                  placements=[] if channel is None else [Placement(id="ad", channel=channel,
                    format="short_video" if channel == "tiktok" else "closed_group" if channel == "communities" else "search",
                    charge_basis="ORGANIC", daily_frequency=8, dayparts=[18], locked=True)])
    values.update(changes)
    return MediaPlan(**values)


def without_market(value):
    return {key: item for key, item in value.items() if key not in {"age_segments", "market_switching"}}


def test_legacy_study_defaults_and_market_contract_bounds():
    spec = StudySpec(product=product())
    assert spec.objective == "campaign"
    assert spec.market == MarketAssumptions(incumbent_share=.6, switching_friction=.5)
    assert MarketAssumptions(addressable_population=10**12).addressable_population == 10**12
    assert len(MarketAssumptions(competitor_urls=["https://example.com"] * 10).competitor_urls) == 10
    for changes in ({"incumbent_share": -.1}, {"incumbent_share": 1.1}, {"switching_friction": float("nan")},
                    {"switching_friction": 1.1}, {"addressable_population": 0}, {"addressable_population": 10**12 + 1},
                    {"product_url": "x" * 4097}, {"competitor_urls": ["x" * 4097]},
                    {"competitor_urls": ["https://example.com"] * 11}):
        with pytest.raises(ValueError):
            MarketAssumptions(**changes)
    with pytest.raises(ValueError):
        StudySpec(product=product(), objective="unsupported")


@pytest.mark.parametrize("age", [18, 24, 25, 64, 65, 100])
def test_single_age_segments_clip_exact_bounds_including_100(age):
    result = simulation.simulate_scenario(product(), AudienceSpec(population=30, representatives=10,
        age_min=age, age_max=age), plan(), 2, 42)
    assert len(result["age_segments"]) == 1
    row = result["age_segments"][0]
    assert (row["age_min"], row["age_max"], row["population"]) == (age, age, 30)
    assert row["units"] == result["units"] and row["revenue_cents"] == result["revenue_cents"]


def test_segments_cover_every_numerical_person_and_remember_actual_attribution(monkeypatch):
    audience, media = AudienceSpec(population=500, representatives=10, age_min=22, age_max=68), plan()
    original = simulation._stream
    def early_only(seed, ids, day, mechanism):
        if mechanism.endswith(":exposure"):
            return np.full(len(ids), 0 if day == 1 else 1)
        if mechanism == "purchase":
            return np.full(len(ids), 0 if day == 1 else 1)
        return original(seed, ids, day, mechanism)
    monkeypatch.setattr(simulation, "_stream", early_only)
    result = simulation.simulate_scenario(product(), audience, media, 12, 42)
    segments = result["age_segments"]
    ages = initialize_population(product(), audience, 42)["age"]
    assert [(r["age_min"], r["age_max"]) for r in segments] == [(22, 24), (25, 34), (35, 44), (45, 54), (55, 64), (65, 68)]
    assert sum(r["population"] for r in segments) == 500
    assert sum(r["units"] for r in segments) == result["units"]
    assert sum(r["organic_units"] for r in segments) == result["organic_units"]
    assert sum(r["revenue_cents"] for r in segments) == result["revenue_cents"]
    for row in segments:
        assert row["population"] == int(np.count_nonzero((ages >= row["age_min"]) & (ages <= row["age_max"])))
        assert row["units"] == sum(c["units"] for c in row["channels"]) + row["organic_units"]
        assert row["conversion_rate"] == row["units"] / row["population"]
    channel = result["channels"][0]
    assert sum(r["channels"][0]["units"] for r in segments) == channel["units"] > 0
    assert sum(r["channels"][0]["unique_reach"] for r in segments) == channel["unique_reach"]


def test_zero_reach_channels_and_natural_purchases_have_reconciled_segments():
    audience = AudienceSpec(population=1000, representatives=10)
    media = plan(placements=[Placement(id="off", channel="search", charge_basis="ORGANIC", weight=0)])
    result = simulation.simulate_scenario(product(), audience, media, 20, 99)
    assert result["units"] > 0 and result["organic_units"] == result["units"]
    assert result["channels"][0]["cac_cents"] is None
    for row in result["age_segments"]:
        assert row["organic_units"] == row["units"]
        assert row["channels"][0] == {"channel": "search", "unique_reach": 0, "units": 0, "conversion_rate": None}


@pytest.mark.parametrize("market", [MarketAssumptions(incumbent_share=1, switching_friction=0),
                                  MarketAssumptions(incumbent_share=0, switching_friction=1)])
def test_zero_friction_or_zero_incumbents_preserve_all_campaign_equations(market):
    audience, media = AudienceSpec(population=300, representatives=10), plan("tiktok")
    campaign = simulation.simulate_scenario(product(), audience, media, 8, 42)
    discovery = simulation.simulate_scenario(product(), audience, media, 8, 42,
        objective="market_discovery", market=market)
    assert without_market(discovery) == without_market(campaign)
    assert discovery["age_segments"] == campaign["age_segments"]
    assert campaign["market_switching"]["enabled"] is False
    assert discovery["market_switching"]["enabled"] is True


@pytest.mark.parametrize("channel", [None, "search", "tiktok", "communities"])
def test_switching_friction_reduces_all_routes_and_counts_only_subsets_of_sales(channel):
    audience, media = AudienceSpec(population=1000, representatives=10), plan(channel)
    if channel == "search":
        media = plan(channel, media_budget_cents=50_000, placements=[Placement(id="ad", channel="search",
            format="search", charge_basis="CPM", daily_frequency=8, dayparts=[18], locked=True)])
    neutral = simulation.simulate_scenario(product(), audience, media, 15, 123, fatigue_multiplier=0)
    result = simulation.simulate_scenario(product(), audience, media, 15, 123, fatigue_multiplier=0,
        objective="market_discovery", market=MarketAssumptions(incumbent_share=1, switching_friction=1))
    switch = result["market_switching"]
    assert neutral["units"] > 0 and result["units"] < neutral["units"]
    assert switch["incumbent_users"] == 1000 and switch["non_incumbent_users"] == 0
    assert switch["switchers"] == switch["buyers"] == result["units"]
    assert switch["retained_incumbents"] + switch["switchers"] == 1000
    assert switch["new_to_category_buyers"] == switch["new_to_category_nonbuyers"] == 0
    assert 0 <= switch["mean_switching_acceptance"] < 1
    assert result["revenue_cents"] == result["units"] * media.price_cents
    if channel == "search":
        assert 0 < result["spend_cents"] <= media.media_budget_cents


def test_mixed_incumbent_counts_are_paired_across_strategies_and_age_bounds():
    market, audience = MarketAssumptions(incumbent_share=.6, switching_friction=.8), AudienceSpec(population=600)
    results = [simulation.simulate_scenario(product(), audience, plan(channel), 10, 42,
        objective="market_discovery", market=market) for channel in (None, "tiktok")]
    assert results[0]["market_switching"]["incumbent_users"] == results[1]["market_switching"]["incumbent_users"]
    older = simulation.simulate_scenario(product(), AudienceSpec(population=600, age_min=100, age_max=100),
        plan(), 1, 42, objective="market_discovery", market=market)
    assert older["market_switching"]["incumbent_users"] == results[0]["market_switching"]["incumbent_users"]
    for result in results:
        switch = result["market_switching"]
        assert 0 < switch["incumbent_users"] < 600
        assert switch["incumbent_users"] + switch["non_incumbent_users"] == 600
        assert switch["switchers"] + switch["new_to_category_buyers"] == result["units"]
        assert switch["retained_incumbents"] + switch["new_to_category_nonbuyers"] == 600 - result["units"]
        assert 0 <= switch["switchers"] <= switch["incumbent_users"]
        assert switch["assumptions"]


def test_market_state_and_purchase_attribution_resume_exactly_and_fingerprint_changes(tmp_path):
    audience, media, market = AudienceSpec(population=100, representatives=10), plan("tiktok"), MarketAssumptions()
    path, seen = tmp_path / "market.npz", []
    with pytest.raises(simulation.SimulationCancelled):
        simulation.simulate_scenario(product(), audience, media, 7, 42, checkpoint_path=path,
            objective="market_discovery", market=market, on_day=seen.append, cancel_check=lambda: len(seen) >= 3)
    resumed = simulation.simulate_scenario(product(), audience, media, 7, 42, checkpoint_path=path,
        objective="market_discovery", market=market)
    assert resumed == simulation.simulate_scenario(product(), audience, media, 7, 42,
        objective="market_discovery", market=market)
    with pytest.raises(ValueError, match="checkpoint"):
        simulation.simulate_scenario(product(), audience, media, 7, 42, checkpoint_path=path,
            objective="market_discovery", market=MarketAssumptions(switching_friction=.9))


def test_validation_segment_means_intervals_and_switching_counts_reconcile():
    audience, media = AudienceSpec(population=150, representatives=10), plan("tiktok")
    replicas = [simulation.simulate_scenario(product(), audience, media, 6, seed,
        objective="market_discovery", market=MarketAssumptions()) for seed in (11, 12, 13)]
    summary = summarize_scenario(media, replicas)
    assert sum(r["population"] for r in summary["age_segments"]) == pytest.approx(150)
    assert sum(r["units"] for r in summary["age_segments"]) == pytest.approx(summary["mean_units"])
    assert sum(r["revenue_cents"] for r in summary["age_segments"]) == pytest.approx(summary["mean_revenue_cents"])
    for row in summary["age_segments"]:
        assert len(row["units_interval"]) == len(row["revenue_interval_cents"]) == 2
        assert row["conversion_rate"] == pytest.approx(row["units"] / row["population"])
        for channel in row["channels"]:
            assert channel["conversion_rate"] == (channel["units"] / channel["unique_reach"] if channel["unique_reach"] else None)
    switch = summary["market_switching"]
    assert switch["switchers"] + switch["new_to_category_buyers"] == pytest.approx(summary["mean_units"])
    assert switch["retained_incumbents"] + switch["switchers"] == pytest.approx(switch["incumbent_users"])
    assert len(switch["switchers_interval"]) == 2
    weighted_intention = sum(row["population"] * row["mean_intention"]
                             for row in summary["age_segments"] if row["population"]) / 150
    assert weighted_intention == pytest.approx(summary["daily"][-1]["mean_intention"])
    json.dumps(summary, allow_nan=False)


def test_unpopulated_age_bins_have_null_rates_and_intention_not_nan(monkeypatch):
    original = simulation.initialize_population
    def one_cohort(*args):
        state = original(*args)
        state["age"].fill(18)
        return state
    monkeypatch.setattr(simulation, "initialize_population", one_cohort)
    audience, media = AudienceSpec(population=30, representatives=10, age_min=18, age_max=100), plan()
    replicas = [simulation.simulate_scenario(product(), audience, media, 2, seed) for seed in (11, 12)]
    summary = summarize_scenario(media, replicas)
    assert len(summary["age_segments"]) == 6
    assert summary["age_segments"][0]["population"] == 30
    for row in summary["age_segments"][1:]:
        assert row["population"] == row["units"] == row["revenue_cents"] == 0
        assert row["conversion_rate"] is row["mean_intention"] is None
        assert row["conversion_rate_interval"] is row["mean_intention_interval"] is None
        assert all(c["conversion_rate"] is None for c in row["channels"])
    json.dumps(summary, allow_nan=False)


def test_campaign_ignores_switching_assumptions_and_global_no_reach_band_is_null():
    audience, media = AudienceSpec(population=60, representatives=10), plan()
    original = simulation.simulate_scenario(product(), audience, media, 3, 42)
    altered = simulation.simulate_scenario(product(), audience, media, 3, 42,
        market=MarketAssumptions(incumbent_share=1, switching_friction=1))
    assert without_market(original) == without_market(altered)
    no_reach = plan(placements=[Placement(id="off", channel="search", weight=0)])
    replicas = [simulation.simulate_scenario(product(), audience, no_reach, 2, seed) for seed in (1, 2)]
    assert summarize_scenario(no_reach, replicas)["channels"][0]["conversion_rate_interval"] is None


def test_global_channel_intervals_use_actual_replica_purchase_to_reach_rates():
    audience, media = AudienceSpec(population=300, representatives=10), plan()
    replicas = [simulation.simulate_scenario(product(), audience, media, 12, seed) for seed in (1, 2, 3)]
    channel = summarize_scenario(media, replicas)["channels"][0]
    rates = [replica["channels"][0]["units"] / replica["channels"][0]["unique_reach"] for replica in replicas]
    assert channel["conversion_rate_interval"] == pytest.approx(np.quantile(rates, [.05, .95]).tolist())
    assert channel["attributed_conversion_rate"] == pytest.approx(
        sum(replica["channels"][0]["units"] for replica in replicas)
        / sum(replica["channels"][0]["unique_reach"] for replica in replicas))


def test_market_comparison_routes_switching_into_candidates_and_price_controls():
    spec = StudySpec(product=product(), audience=AudienceSpec(population=60, representatives=10),
        objective="market_discovery", market=MarketAssumptions(incumbent_share=1, switching_friction=.7),
        rounds=2, media_budget_cents=0, exploration_repetitions=2, validation_repetitions=2)
    candidates = [plan(channel).model_copy(update={"id": str(index)})
                  for index, channel in enumerate((None, "search", "tiktok"))]
    report = simulation.compare_strategies(spec, candidates)
    assert report["metadata"]["study_objective"] == "market_discovery"
    assert report["metadata"]["market_assumptions"] == spec.market.model_dump()
    assert report["market_analysis"]
    assert all(scenario["market_switching"]["incumbent_users"] == 60 for scenario in report["scenarios"])
    assert all(scenario["market_switching"]["switchers"] == scenario["mean_units"] for scenario in report["scenarios"])
    json.dumps(report, allow_nan=False)
