import importlib.util
import json

import numpy as np
import pytest

from spill_market.models import AudienceSpec, MediaPlan, Placement, ProductSpec, StudySpec


def engine():
    assert importlib.util.find_spec("spill_market.simulation"), "native simulation subsystem is missing"
    from spill_market import simulation
    return simulation


def product(**kwargs):
    return ProductSpec(name="Creative tool", description="A creative editing tool for independent makers", **kwargs)


def plan(**kwargs):
    defaults = dict(id="test", name="Test", price_cents=1000, media_budget_cents=30000,
                    placements=[Placement(id="search", channel="search", daily_frequency=4)])
    defaults.update(kwargs)
    return MediaPlan(**defaults)


def test_distinct_population_and_bounded_adult_personas():
    engine()
    from spill_market.personas import generate_personas, initialize_population
    p = product(unit_price_cents=1000)
    a = AudienceSpec(population=100_000, age_min=39, age_max=41, representatives=12)
    states = initialize_population(p, a, seed=31)
    assert len(np.unique(states["id"])) == 100_000
    assert len(np.unique(states["need_fit"])) > 99_000
    assert states["age"].min() >= 39 and states["age"].max() <= 41
    personas = generate_personas(p, a, seed=31, limit=8)
    assert len(personas) == 8
    assert all(39 <= item.age <= 41 for item in personas)
    assert all(item.beliefs[0]["status"] == "synthetic" for item in personas)


def test_three_product_aware_plans_and_fifteen_executable_channels():
    engine()
    from spill_market.media import channel_catalog, propose_plans
    a = AudienceSpec()
    games = propose_plans(product(unit_price_cents=2000, category="game"), a, 15000)
    software = propose_plans(product(unit_price_cents=2000), a, 15000)
    assert len(games) == len(software) == 3
    assert len({p.price_cents for p in games}) == 3
    assert all(p.media_budget_cents == 15000 for p in games + software)
    assert [p.model_dump() for p in games] != [p.model_dump() for p in software]
    catalog = channel_catalog()
    assert len(catalog) == 15
    assert {c["mechanism"] for c in catalog} >= {"short_video", "closed_group", "in_game"}
    result = engine().simulate_scenario(product(unit_price_cents=1000), AudienceSpec(population=1000),
        plan(placements=[Placement(id=c["channel"], channel=c["channel"], charge_basis="ORGANIC")
                         for c in catalog]), 3, 42)
    assert len(result["channels"]) == 15
    assert all(c["impressions"] > 0 for c in result["channels"])


def test_simulation_reproducible_finances_and_first_purchase_deduplication():
    sim = engine()
    p = product(unit_price_cents=1000, stock=75, variable_cost_cents=100)
    a = AudienceSpec(population=1000)
    r = sim.simulate_scenario(p, a, plan(), 10, 42)
    assert r == sim.simulate_scenario(p, a, plan(), 10, 42)
    assert r["units"] <= 75
    assert r["revenue_cents"] == r["units"] * 1000
    assert r["spend_cents"] <= 30000
    assert sum(d["units"] for d in r["daily"]) == r["units"]
    assert sum(c["units"] for c in r["channels"]) + r["organic_units"] == r["units"]
    assert sum(c["spend_cents"] for c in r["channels"]) == r["spend_cents"]
    assert r["unique_buyers"] == r["units"]
    assert len(r["traces"]) <= 2000
    assert r["daily"][-1]["mean_intention"] != r["daily"][-1]["units"] / a.population
    state = {"purchased": np.zeros(3, dtype=bool), "budget_cents": np.array([1000, 999, 5000])}
    assert sim.buy_product(state, np.array([0, 1, 2]), 1000, stock_remaining=1).tolist() == [0]
    assert sim.buy_product(state, np.array([0]), 1000, stock_remaining=2).size == 0


def test_no_campaign_and_zero_budget_still_have_organic_sales():
    sim = engine()
    p = product(unit_price_cents=100)
    a = AudienceSpec(population=5000)
    empty = sim.simulate_scenario(p, a, plan(price_cents=100, placements=[], media_budget_cents=0), 15, 99)
    zero = sim.simulate_scenario(p, a, plan(price_cents=100, media_budget_cents=0), 15, 99)
    assert empty["units"] > 0
    assert empty["units"] == zero["units"]
    assert empty["spend_cents"] == zero["spend_cents"] == 0


@pytest.mark.parametrize("basis", ["CPM", "CPC", "CPA", "FIXED", "ORGANIC"])
def test_cost_bases_respect_budget_and_reconcile(basis):
    sim = engine()
    placement = Placement(id="ad", channel="search", charge_basis=basis, daily_frequency=8,
                          cpm_cents=1000, cpc_cents=7, cpa_cents=13, fee_cents=50)
    r = sim.simulate_scenario(product(unit_price_cents=100), AudienceSpec(population=3000),
                              plan(price_cents=100, media_budget_cents=1000, placements=[placement]), 12, 40)
    c = r["channels"][0]
    assert c["impressions"] > 0
    assert 0 <= r["spend_cents"] <= 1000
    if basis == "CPC":
        assert c["spend_cents"] == c["clicks"] * 7
    if basis == "CPA":
        assert c["spend_cents"] == c["units"] * 13
    if basis == "ORGANIC":
        assert c["spend_cents"] == 0
        assert c["paid_clicks"] == 0
    if basis == "FIXED":
        assert c["spend_cents"] % 50 == 0


def test_checkpoint_cancel_resume_is_identical_and_rejects_different_spec(tmp_path):
    sim = engine()
    p, a, media = product(unit_price_cents=1000), AudienceSpec(population=1000), plan()
    check = tmp_path / "scenario.npz"
    seen = []
    with pytest.raises(sim.SimulationCancelled):
        sim.simulate_scenario(p, a, media, 8, 42, checkpoint_path=check,
            on_day=lambda row: seen.append(row["day"]), cancel_check=lambda: len(seen) >= 3)
    assert seen == [1, 2, 3]
    resumed_days = []
    resumed = sim.simulate_scenario(p, a, media, 8, 42, checkpoint_path=check,
                                   on_day=lambda row: resumed_days.append(row["day"]))
    assert resumed_days == [4, 5, 6, 7, 8]
    assert resumed == sim.simulate_scenario(p, a, media, 8, 42)
    with pytest.raises(ValueError, match="checkpoint"):
        sim.simulate_scenario(p, a, media.model_copy(update={"price_cents": 999}), 8, 42, checkpoint_path=check)


def test_frequency_locks_dayparts_formats_costs_weights_and_fatigue_are_executed():
    sim = engine()
    p, a = product(unit_price_cents=500), AudienceSpec(population=3000)
    base = Placement(id="ad", channel="in_game", format="rewarded_video", daily_frequency=9,
                     charge_basis="ORGANIC", locked=True, dayparts=[18])
    r = sim.simulate_scenario(p, a, plan(placements=[base]), 8, 42)
    assert not r["adjustments"]
    adaptive = sim.simulate_scenario(p, a, plan(placements=[base.model_copy(update={"locked": False})]), 8, 42)
    assert adaptive["adjustments"]
    for change in ({"dayparts": [3]}, {"format": "banner"}, {"daily_frequency": .2}, {"weight": 0}):
        changed = sim.simulate_scenario(p, a, plan(placements=[base.model_copy(update=change)]), 8, 42)
        assert changed["channels"][0]["impressions"] != r["channels"][0]["impressions"]
    no_fatigue = sim.simulate_scenario(p, a, plan(placements=[base]), 8, 42, fatigue_multiplier=0)
    assert no_fatigue["daily"][-1]["mean_fatigue"] == 0
    assert r["daily"][-1]["mean_fatigue"] > 0


def test_compare_has_price_baselines_paired_validation_and_serializable_report(tmp_path):
    sim = engine()
    from spill_market.media import propose_plans
    spec = StudySpec(product=product(unit_price_cents=1000), audience=AudienceSpec(population=100),
                     rounds=3, exploration_repetitions=2, validation_repetitions=2)
    candidates = propose_plans(spec.product, spec.audience, spec.media_budget_cents)
    progress = []
    report = sim.compare_strategies(spec, candidates, checkpoint_dir=tmp_path,
                                   on_progress=progress.append)
    json.dumps(report, allow_nan=False)
    assert report["schema_version"] and report["assumptions"] and report["personas"]
    assert len(report["scenarios"]) == 6
    assert len(report["comparisons"]) == 3
    assert len(report["metadata"]["exploration_seeds"]) == 2
    assert len(report["metadata"]["validation_seeds"]) == 2
    assert set(report["metadata"]["exploration_seeds"]).isdisjoint(report["metadata"]["validation_seeds"])
    for scenario in report["scenarios"]:
        assert len(scenario["replicate_totals"]) == 2
        assert scenario["channels"] is not None and scenario["traces"] is not None
        assert [r["seed"] for r in scenario["replicate_totals"]] == report["metadata"]["validation_seeds"]
    assert progress[-1]["percent"] == 100
    assert report == sim.compare_strategies(spec, candidates, checkpoint_dir=tmp_path)


def test_numeric_100k_individuals_smoke():
    sim = engine()
    r = sim.simulate_scenario(product(unit_price_cents=1000), AudienceSpec(population=100_000),
                              plan(), 2, 123)
    assert r["population"] == 100_000
    assert r["state_count"] == 100_000
    assert r["unique_buyers"] <= 100_000


def test_weak_age_priors_preserve_financial_fairness_and_within_age_diversity():
    engine()
    from spill_market.personas import initialize_population
    p = product(unit_price_cents=1000)
    young = initialize_population(p, AudienceSpec(population=1000, age_min=18, age_max=22), 42)
    older = initialize_population(p, AudienceSpec(population=1000, age_min=70, age_max=75), 42)
    for key in ["need_fit", "trust", "budget_cents", "price_sensitivity"]:
        assert np.array_equal(young[key], older[key]), key
    for key in ["channel_affinity", "social_sensitivity"]:
        assert not np.array_equal(young[key], older[key]), key
        assert np.max(np.abs(young[key] - older[key])) < .1
        assert young[key].std() > .1 and older[key].std() > .1
    neutral_young = initialize_population(p, AudienceSpec(population=1000, age_min=18, age_max=22,
                                                         age_behavior_weight=0), 42)
    neutral_older = initialize_population(p, AudienceSpec(population=1000, age_min=70, age_max=75,
                                                         age_behavior_weight=0), 42)
    for key in ["channel_affinity", "social_sensitivity"]:
        assert np.array_equal(neutral_young[key], neutral_older[key])


def test_exposed_purchase_rate_measures_all_exposed_buyers_not_only_attributed():
    sim = engine()
    p = product(unit_price_cents=100)
    a = AudienceSpec(population=5000)
    placements = [Placement(id="banner", channel="display", format="banner", charge_basis="ORGANIC",
                            daily_frequency=9, locked=True),
                  Placement(id="search", channel="search", charge_basis="ORGANIC",
                            daily_frequency=9, locked=True)]
    result = sim.simulate_scenario(p, a, plan(price_cents=100, placements=placements), 20, 23)
    assert all("exposed_purchase_units" in c for c in result["channels"])
    assert any(c["exposed_purchase_units"] > c["units"] for c in result["channels"])
    assert all(c["exposed_purchase_rate"] == c["exposed_purchase_units"] / c["unique_reach"]
               for c in result["channels"])


def test_stateless_random_mechanisms_and_global_attention_are_bounded():
    sim = engine()
    ids = np.arange(5000)
    draws = sim._stream(42, ids, 4, "purchase")
    assert np.array_equal(draws[100:200], sim._stream(42, ids[100:200], 4, "purchase"))
    assert not np.array_equal(draws, sim._stream(42, ids, 4, "click"))
    from spill_market.media import channel_catalog
    result = sim.simulate_scenario(product(unit_price_cents=500), AudienceSpec(population=500),
        plan(placements=[Placement(id=c["channel"], channel=c["channel"], daily_frequency=12,
                                  charge_basis="ORGANIC", weight=20) for c in channel_catalog()]), 3, 42)
    assert all(0 <= t["exposures"] <= 6 for t in result["traces"])
    assert all(1 <= t["exposures"] + t["attention_remaining"] <= 6 for t in result["traces"])


def test_compare_cancel_resume_replays_no_completed_days(tmp_path):
    sim = engine()
    from spill_market.media import propose_plans
    spec = StudySpec(product=product(unit_price_cents=1000), audience=AudienceSpec(population=100),
                     rounds=3, exploration_repetitions=1, validation_repetitions=1)
    candidates = propose_plans(spec.product, spec.audience, spec.media_budget_cents)
    seen = []
    with pytest.raises(sim.SimulationCancelled):
        sim.compare_strategies(spec, candidates, checkpoint_dir=tmp_path,
            on_progress=seen.append, cancel_check=lambda: len([p for p in seen if p["day"] == 2]) >= 1)
    resumed = sim.compare_strategies(spec, candidates, checkpoint_dir=tmp_path)
    continuous = sim.compare_strategies(spec, candidates)
    assert resumed == continuous


def test_multi_placement_commissions_and_deduplication_share_budget_and_stock():
    sim = engine()
    placements = [Placement(id=f"affiliate-{i}", channel="affiliate", charge_basis="CPA",
                            daily_frequency=12, weight=5, cpa_cents=17) for i in range(3)]
    result = sim.simulate_scenario(product(unit_price_cents=100, stock=200), AudienceSpec(population=10_000),
        plan(price_cents=100, media_budget_cents=500, placements=placements), 30, 23)
    assert 0 < result["paid_units"] <= result["units"] <= 200
    assert result["commission_cents"] == result["spend_cents"] == result["paid_units"] * 17 <= 500


def test_100k_checkpoints_remain_small_enough_for_daily_commits(tmp_path):
    sim = engine()
    path = tmp_path / "large.npz"
    sim.simulate_scenario(product(unit_price_cents=1000), AudienceSpec(population=100_000),
                          plan(), 2, 123, checkpoint_path=path)
    assert path.stat().st_size < 4_000_000


def test_exploration_optimizes_total_revenue_when_margin_prefers_another_price():
    sim = engine()
    spec = StudySpec(product=product(unit_price_cents=1000, variable_cost_cents=5000),
                     audience=AudienceSpec(population=1000, age_behavior_weight=0),
                     rounds=15, media_budget_cents=0, exploration_repetitions=3, validation_repetitions=3)
    candidates = [plan(id=str(price), name=str(price), price_cents=price, media_budget_cents=0,
        placements=[Placement(id="ad", channel="search", charge_basis="ORGANIC", daily_frequency=6)])
        for price in [1000, 3000, 30000]]
    report = sim.compare_strategies(spec, candidates)
    explored = [s for s in report["metadata"]["exploration_scenarios"] if not s["is_baseline"]]
    revenue_best = max(explored, key=lambda s: s["mean_revenue_cents"])["plan_id"]
    margin_best = max(explored, key=lambda s: s["mean_contribution_cents"])["plan_id"]
    assert revenue_best != margin_best
    assert report["metadata"]["exploration_selected_id"] == revenue_best
    assert report["metadata"]["objective"] == "maximum_total_revenue"
    assert len(report["metadata"]["selected_revenue_validation"]) == 2
    assert all(c["practical_threshold_fraction"] == .01
               for c in report["metadata"]["selected_revenue_validation"])


def test_validation_freezes_adaptive_policy_and_starting_parameters_not_daily_actions():
    sim = engine()
    spec = StudySpec(product=product(unit_price_cents=500), audience=AudienceSpec(population=200),
                     rounds=6, exploration_repetitions=2, validation_repetitions=2)
    from spill_market.media import propose_plans
    candidates = propose_plans(spec.product, spec.audience, spec.media_budget_cents)
    for candidate in candidates:
        candidate.placements[0].locked = True
    report = sim.compare_strategies(spec, candidates)
    validation_plans = report["metadata"]["frozen_validation_plans"]
    assert all(p["adaptive"] for p in validation_plans)
    assert all(s["adjustments"] for s in report["scenarios"] if not s["is_baseline"])
    for original, frozen in zip(candidates, validation_plans, strict=True):
        assert frozen["placements"][0] == original.placements[0].model_dump()
        scenario = next(s for s in report["scenarios"] if s["plan_id"] == original.id)
        assert all(a["placement_id"] != original.placements[0].id for a in scenario["adjustments"])


def test_grounded_research_enriches_synthetic_beliefs_and_proposed_messages():
    engine()
    from spill_market.models import EvidenceSource, Finding, TrendReport
    from spill_market.personas import generate_personas
    from spill_market.media import propose_plans
    research = TrendReport(topic="Editing", mode="offline", sources=[EvidenceSource(
        id="interview", title="Interview", content="Rendering exports takes too long.", kind="import")],
        pain_points=[Finding(text="Rendering exports takes too long.", source_ids=["interview"], status="observed")],
        jargon=[Finding(text="Export queue", source_ids=["missing"], status="inferred")])
    p, a = product(unit_price_cents=1000), AudienceSpec(population=100)
    people = generate_personas(p, a, research)
    grounded = [b for person in people for b in person.beliefs if b.get("source_ids")]
    assert grounded
    assert all(b["status"] == "synthetic" and b["evidence_status"] == "observed" for b in grounded)
    assert all(b["source_ids"] == ["interview"] for b in grounded)
    assert any("Rendering exports takes too long" in b["text"] for b in grounded)
    candidates = propose_plans(p, a, 10000, research)
    assert all(any("Rendering exports takes too long" in line.creative for line in c.placements)
               for c in candidates)
    assert all(any("interview" in reason for reason in c.rationale) for c in candidates)
    assert not any("Export queue" in line.creative for c in candidates for line in c.placements)


def test_declared_response_hypotheses_are_bounded_shared_numeric_inputs(tmp_path):
    sim = engine()
    p, a = product(unit_price_cents=1000), AudienceSpec(population=1000)
    media = plan(placements=[Placement(id="ad", channel="search", charge_basis="ORGANIC",
                                       daily_frequency=6)])
    default = sim.simulate_scenario(p, a, media, 6, 42)
    assert default == sim.simulate_scenario(p, a, media, 6, 42, response_multipliers={})
    lower = sim.simulate_scenario(p, a, media, 6, 42, response_multipliers={"search": .8})
    higher = sim.simulate_scenario(p, a, media, 6, 42, response_multipliers={"search": 1.2})
    assert higher["daily"][-1]["mean_intention"] > lower["daily"][-1]["mean_intention"]
    path = tmp_path / "hypotheses.npz"
    sim.simulate_scenario(p, a, media, 6, 42, checkpoint_path=path, response_multipliers={"search": .8})
    with pytest.raises(ValueError, match="checkpoint"):
        sim.simulate_scenario(p, a, media, 6, 42, checkpoint_path=path, response_multipliers={"search": 1.2})
    for invalid in [{"search": 1.3}, {"search": float("nan")}, {"invalid": 1.0}]:
        with pytest.raises(ValueError, match="response_multipliers"):
            sim.simulate_scenario(p, a, media, 6, 42, response_multipliers=invalid)


def test_compare_passes_shared_response_hypothesis_and_discloses_it():
    sim = engine()
    spec = StudySpec(product=product(unit_price_cents=1000), audience=AudienceSpec(population=100),
                     rounds=3, exploration_repetitions=1, validation_repetitions=1,
                     response_multipliers={"search": 1.2})
    candidates = [plan(id=str(i), name=str(i), price_cents=1000, media_budget_cents=spec.media_budget_cents,
                      adaptive=False) for i in range(3)]
    report = sim.compare_strategies(spec, candidates)
    seed = report["metadata"]["validation_seeds"][0]
    direct = sim.simulate_scenario(spec.product, spec.audience, candidates[0], spec.rounds, seed,
                                   response_multipliers=spec.response_multipliers)
    assert report["scenarios"][0]["daily"] == direct["daily"]
    assert report["metadata"]["response_hypotheses"]["multipliers"] == {"search": 1.2}
    assert report["winner_id"] is None  # Identical plans cannot exceed the 1% threshold.
    assert "Indecisive" in report["winner_reason"]


def test_paired_revenue_superiority_requires_uncertainty_and_practical_difference():
    from spill_market.reports import paired_revenue_comparison
    def scenario(identifier, revenues):
        return {"plan_id": identifier, "mean_revenue_cents": float(np.mean(revenues)),
                "replicate_totals": [{"seed": i, "revenue_cents": value} for i, value in enumerate(revenues)]}
    alternative = scenario("alternative", [10000, 10000])
    tiny = paired_revenue_comparison(scenario("tiny", [10050, 10050]), alternative)
    assert not tiny["supported_practical_superiority"]
    clear = paired_revenue_comparison(scenario("clear", [10200, 10200]), alternative)
    assert clear["supported_practical_superiority"]
    noisy = paired_revenue_comparison(scenario("noisy", [8000, 14000]), alternative)
    assert not noisy["supported_practical_superiority"]
    single = paired_revenue_comparison(scenario("single", [50000]), scenario("one", [10000]))
    assert single["revenue_difference_mean_95pct_interval_cents"] is None
    assert not single["supported_practical_superiority"]


def test_attributed_conversion_uses_unique_exposed_denominator_and_view_fallback():
    sim = engine()
    p, a = product(unit_price_cents=100), AudienceSpec(population=3000)
    media = plan(price_cents=100, placements=[Placement(id="banner", channel="display", format="banner",
                       charge_basis="ORGANIC", daily_frequency=10, dayparts=[18])])
    result = sim.simulate_scenario(p, a, media, 20, 42)
    row = result["channels"][0]
    assert row["unique_reach"] != row["clicks"] and row["units"] > 0
    assert row["attributed_conversion_rate"] == row["units"] / row["unique_reach"]
    assert row["view_attributed_units"] > 0
    assert row["click_attributed_units"] + row["view_attributed_units"] == row["units"]
    assert any(t["attribution_rule"] == "last_view_24h" for t in result["traces"])
    from spill_market.reports import summarize_scenario
    summary = summarize_scenario(media, [result])
    channel = summary["channels"][0]
    assert channel["attributed_conversion_rate"] == channel["units"] / channel["unique_reach"]


def test_short_video_social_events_create_bounded_next_day_earned_exposures(tmp_path):
    sim = engine()
    p, a = product(unit_price_cents=1000, category="game"), AudienceSpec(population=5000)
    media = plan(placements=[Placement(id="short", channel="tiktok", format="short_video",
                   charge_basis="ORGANIC", daily_frequency=6, dayparts=[18], locked=True)])
    result = sim.simulate_scenario(p, a, media, 8, 42)
    channel = result["channels"][0]
    for metric in ["views", "completions", "skips", "comments", "shares", "trend_adoptions", "creator_posts"]:
        assert channel[metric] > 0, metric
    assert channel["completions"] + channel["skips"] == channel["views"]
    assert result["daily"][0]["earned_impressions"] == 0
    assert sum(d["earned_impressions"] for d in result["daily"][1:]) > 0
    assert all(d["earned_impressions"] <= 2 * a.population for d in result["daily"])
    disabled = sim.simulate_scenario(p, a, media, 8, 42, social_sharing_enabled=False)
    assert sum(d["earned_impressions"] for d in disabled["daily"]) == 0
    assert result["daily"][-1]["mean_intention"] != disabled["daily"][-1]["mean_intention"]
    path, seen = tmp_path / "social.npz", []
    with pytest.raises(sim.SimulationCancelled):
        sim.simulate_scenario(p, a, media, 8, 42, checkpoint_path=path,
                             on_day=seen.append, cancel_check=lambda: len(seen) >= 3)
    assert result == sim.simulate_scenario(p, a, media, 8, 42, checkpoint_path=path)


def test_group_propagation_is_member_and_community_restricted():
    sim = engine()
    p, a = product(unit_price_cents=1000), AudienceSpec(population=3000)
    media = plan(placements=[Placement(id="group", channel="facebook", format="group",
                  charge_basis="ORGANIC", daily_frequency=8, dayparts=[18])])
    result = sim.simulate_scenario(p, a, media, 8, 42)
    channel = result["channels"][0]
    assert channel["comments"] > 0 and channel["shares"] > 0
    assert channel["earned_impressions"] > 0
    assert channel["cross_community_deliveries"] == 0
    assert channel["nonmember_deliveries"] == 0
    assert channel["social_edges"]
    assert all(e["source"] % 32 == e["target"] % 32 == e["community"] for e in channel["social_edges"])
    members = sim._stream(42, np.arange(a.population), 0, "facebook:group:membership") < .65
    assert all(members[e["source"]] and members[e["target"]] for e in channel["social_edges"])
    assert any(t["synthetic_comment"] for t in result["traces"])


def test_large_allowed_comparison_resume_never_reexecutes_committed_calendars(tmp_path, monkeypatch):
    sim = engine()
    spec = StudySpec(product=product(unit_price_cents=1000), audience=AudienceSpec(population=30,
                     representatives=10), rounds=1, exploration_repetitions=50, validation_repetitions=1)
    candidates = [plan(id=str(i), name=str(i), media_budget_cents=spec.media_budget_cents,
                       placements=[]) for i in range(3)]
    original = sim.simulate_scenario
    executed, committed = [], []
    def observe(*args, **kwargs):
        executed.append((args[2].id, args[4]))
        return original(*args, **kwargs)
    monkeypatch.setattr(sim, "simulate_scenario", observe)
    def progress(row):
        if row["message"].startswith("Committed"):
            committed.append(row)
    with pytest.raises(sim.SimulationCancelled):
        sim.compare_strategies(spec, candidates, checkpoint_dir=tmp_path, on_progress=progress,
                               cancel_check=lambda: len(committed) >= 150)
    assert len(list(tmp_path.rglob("*.json"))) == 150
    report = sim.compare_strategies(spec, candidates, checkpoint_dir=tmp_path)
    assert len(executed) == len(set(executed)) == 4 * 51
    assert len(report["scenarios"]) == 4


def test_cpa_cash_limit_reserves_before_delivery_and_never_blocks_natural_demand(monkeypatch, tmp_path):
    sim = engine()
    p, a = product(unit_price_cents=100), AudienceSpec(population=30, representatives=10)
    media = plan(price_cents=100, media_budget_cents=2,
                 placements=[Placement(id="affiliate", channel="affiliate", charge_basis="CPA",
                                       cpa_cents=1, daily_frequency=12, weight=100, dayparts=[18], locked=True)])
    original_population, original_stream = sim.initialize_population, sim._stream
    def qualified(*args, **kwargs):
        state = original_population(*args, **kwargs)
        for key in ["need_fit", "trust", "prerequisite_fit"]:
            state[key][:] = 1
        state["budget_cents"][:] = 10000
        return state
    def forced(seed, ids, day, mechanism):
        if mechanism == "purchase":
            return np.full(len(ids), 1.0 if day == 1 else 0.0)
        return original_stream(seed, ids, day, mechanism)
    monkeypatch.setattr(sim, "initialize_population", qualified)
    monkeypatch.setattr(sim, "_stream", forced)
    result = sim.simulate_scenario(p, a, media, 2, 42, checkpoint_path=tmp_path / "cpa.npz")
    assert result["daily"][0]["units"] == 0
    assert result["daily"][1]["units"] == 30
    assert result["units"] == 30
    assert result["spend_cents"] <= 2
    assert result["daily"][0]["pending_liability_cents"] > 0
    assert all(d["cumulative_spend_cents"] + d["pending_liability_cents"] <= 2 for d in result["daily"])
    assert result["pending_liability_cents"] == 0
    channel = result["channels"][0]
    assert channel["unique_reach"] <= 2
    assert channel["settled_liability_cents"] == result["spend_cents"]
    assert channel["reserved_liability_cents"] - channel["released_liability_cents"] - channel["settled_liability_cents"] == 0


def test_cpa_reservation_expiration_and_resume_reconcile(tmp_path):
    sim = engine()
    p, a = product(unit_price_cents=1000), AudienceSpec(population=300)
    media = plan(media_budget_cents=1000, placements=[Placement(id="affiliate", channel="affiliate",
                 charge_basis="CPA", cpa_cents=30, daily_frequency=5)])
    path, seen = tmp_path / "reserved.npz", []
    with pytest.raises(sim.SimulationCancelled):
        sim.simulate_scenario(p, a, media, 12, 42, checkpoint_path=path,
            on_day=seen.append, cancel_check=lambda: len(seen) >= 4)
    resumed = sim.simulate_scenario(p, a, media, 12, 42, checkpoint_path=path)
    assert resumed == sim.simulate_scenario(p, a, media, 12, 42)
    pending = 0
    for day in resumed["daily"]:
        pending += day["reserved_liability_cents"] - day["released_liability_cents"] - day["settled_liability_cents"]
        assert pending == day["pending_liability_cents"]
        assert pending + day["cumulative_spend_cents"] <= 1000


def test_unclicked_cpa_view_inventory_releases_after_24_hours(monkeypatch):
    sim = engine()
    original = sim._stream
    def no_new_touch(seed, ids, day, mechanism):
        if mechanism.endswith(":exposure"):
            return np.full(len(ids), 0.0 if day == 1 else 1.0)
        if mechanism == "purchase" or mechanism.endswith(":click"):
            return np.ones(len(ids))
        return original(seed, ids, day, mechanism)
    monkeypatch.setattr(sim, "_stream", no_new_touch)
    media = plan(price_cents=100, media_budget_cents=600, adaptive=False,
        placements=[Placement(id="affiliate", channel="affiliate", charge_basis="CPA",
                              cpa_cents=30, daily_frequency=.2, dayparts=[18])])
    result = sim.simulate_scenario(product(unit_price_cents=100), AudienceSpec(population=30,
                                   representatives=10), media, 2, 42)
    assert result["daily"][0]["pending_liability_cents"] > 0
    assert result["daily"][1]["released_liability_cents"] == result["daily"][0]["pending_liability_cents"]
    assert result["pending_liability_cents"] == result["spend_cents"] == 0


def test_cpa_view_hold_survives_older_click_until_exact_24h_fallback(monkeypatch, tmp_path):
    sim = engine()
    original = sim._stream
    def scheduled(seed, ids, day, mechanism):
        if mechanism.endswith(":exposure"):
            delivered = (mechanism.startswith("search:") and day == 1 or
                         mechanism.startswith("affiliate:") and day == 7)
            return np.full(len(ids), 0.0 if delivered else 1.0)
        if mechanism.endswith(":click"):
            return np.full(len(ids), 0.0 if mechanism.startswith("search:") and day == 1 else 1.0)
        if mechanism == "purchase":
            return np.ones(len(ids))
        return original(seed, ids, day, mechanism)
    monkeypatch.setattr(sim, "_stream", scheduled)
    media = plan(price_cents=100, media_budget_cents=60, adaptive=False, placements=[
        Placement(id="search", channel="search", format="search", charge_basis="ORGANIC",
                  daily_frequency=.1, dayparts=[0]),
        Placement(id="affiliate", channel="affiliate", format="review", charge_basis="CPA",
                  cpa_cents=1, daily_frequency=.1, dayparts=[23]),
    ])
    p, a = product(unit_price_cents=100), AudienceSpec(population=30, representatives=10)
    path, seen = tmp_path / "fallback.npz", []
    with pytest.raises(sim.SimulationCancelled):
        sim.simulate_scenario(p, a, media, 8, 42, checkpoint_path=path,
                             on_day=seen.append, cancel_check=lambda: len(seen) >= 7)
    assert seen[-1]["pending_liability_cents"] > 0
    resumed = sim.simulate_scenario(p, a, media, 8, 42, checkpoint_path=path)
    assert resumed == sim.simulate_scenario(p, a, media, 8, 42)
    assert resumed["daily"][7]["pending_liability_cents"] > 0
    assert resumed["units"] == 0
    assert any(t["day"] == 8 and t["attribution_rule"] == "last_view_24h" and
               t["attributed_channel"] == "affiliate" for t in resumed["traces"])
