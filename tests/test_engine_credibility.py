import hashlib
import json
from pathlib import Path

import pytest

from spill_market import simulation
from spill_market.models import AudienceSpec, MediaPlan, Placement, ProductSpec, StudySpec


def claim():
    return ProductSpec(name="MyLife physical supplement", category="physical", unit_price_cents=1000,
        description="Our physical pill guarantees immortality and allows humans to live forever.")


def campaign(channel=None):
    return MediaPlan(id="claim", name="Claim test", price_cents=1000, media_budget_cents=500_000,
        adaptive=False, placements=[] if channel is None else [Placement(id="ad", channel=channel,
            format="short_video" if channel == "tiktok" else "closed_group" if channel == "communities" else "search",
            charge_basis="CPM" if channel == "search" else "ORGANIC", daily_frequency=12,
            weight=20, locked=True, dayparts=[12, 18, 21], creative="Discover the product.")])


@pytest.mark.parametrize("channel", [None, "search", "tiktok", "communities"])
def test_unsupported_promise_reduces_all_purchase_routes_under_extreme_frequency(channel):
    product, audience, plan = claim(), AudienceSpec(population=6000, representatives=20), campaign(channel)
    assessed = simulation.simulate_scenario(product, audience, plan, 20, 123, fatigue_multiplier=0)
    neutral = simulation.simulate_scenario(product, audience, plan, 20, 123, fatigue_multiplier=0,
        credibility_overrides={"status": "ordinary", "score": 1.0, "scam_suspicion": 0.0,
                               "reason": "Explicit neutral response sensitivity control"})
    assert neutral["units"] > 0
    assert assessed["units"] <= neutral["units"] * .25
    assert assessed["mean_credibility_acceptance"] < .15
    assert assessed["mean_scam_suspicion"] > .25
    assert all(d["mean_intention"] <= d["mean_credibility_acceptance"] + 1e-12 for d in assessed["daily"])
    assert all(0 < t["credibility_acceptance"] <= 1 and 0 <= t["scam_suspicion"] <= 1 for t in assessed["traces"])
    assert len({round(t["credibility_acceptance"], 5) for t in assessed["traces"]}) > 10
    assert assessed["unique_buyers"] == assessed["units"]
    assert assessed["revenue_cents"] == assessed["units"] * plan.price_cents
    if channel in {"tiktok", "communities"}:
        row = assessed["channels"][0]
        assert row["skeptical_comments"] > 0
        assert row["positive_comments"] + row["skeptical_comments"] == row["comments"]


def test_skeptical_comments_are_not_counted_as_positive_recommendations(monkeypatch):
    original = simulation._stream
    def comments(enabled):
        def stream(seed, ids, day, mechanism):
            if mechanism.endswith(":comment"):
                import numpy as np
                return np.full(len(ids), 0.0 if enabled else 1.0)
            if mechanism.endswith(":comment-skepticism"):
                import numpy as np
                return np.zeros(len(ids))
            return original(seed, ids, day, mechanism)
        return stream
    product, audience, plan = claim(), AudienceSpec(population=2000), campaign("tiktok")
    monkeypatch.setattr(simulation, "_stream", comments(True))
    critical = simulation.simulate_scenario(product, audience, plan, 10, 42, fatigue_multiplier=0,
                                            social_sharing_enabled=False)
    monkeypatch.setattr(simulation, "_stream", comments(False))
    silent = simulation.simulate_scenario(product, audience, plan, 10, 42, fatigue_multiplier=0,
                                          social_sharing_enabled=False)
    assert critical["skeptical_comments"] > 0 and critical["positive_comments"] == 0
    assert critical["channels"][0]["shares"] == 0
    assert critical["channels"][0]["creator_posts"] == 0
    assert critical["daily"][-1]["mean_intention"] <= silent["daily"][-1]["mean_intention"]
    assert critical["units"] <= silent["units"]


def test_credibility_state_resumes_exactly_and_rejects_different_assumptions(tmp_path):
    product, audience, plan = claim(), AudienceSpec(population=500), campaign("tiktok")
    path, seen = tmp_path / "credibility.npz", []
    with pytest.raises(simulation.SimulationCancelled):
        simulation.simulate_scenario(product, audience, plan, 8, 42, checkpoint_path=path,
            on_day=seen.append, cancel_check=lambda: len(seen) >= 3)
    resumed = simulation.simulate_scenario(product, audience, plan, 8, 42, checkpoint_path=path)
    assert resumed == simulation.simulate_scenario(product, audience, plan, 8, 42)
    assert resumed["daily"][-1]["mean_scam_suspicion"] > resumed["daily"][0]["mean_scam_suspicion"]
    with pytest.raises(ValueError, match="checkpoint"):
        simulation.simulate_scenario(product, audience, plan, 8, 42, checkpoint_path=path,
                                      credibility_overrides={"score": .5})


def test_report_discloses_unvalidated_product_credibility_and_bounds():
    product, audience = claim(), AudienceSpec(population=100)
    spec = StudySpec(product=product, audience=audience, rounds=2, exploration_repetitions=1,
                     validation_repetitions=1, media_budget_cents=500_000)
    plans = [campaign(channel).model_copy(update={"id": str(i)}) for i, channel in enumerate([None, "search", "tiktok"])]
    report = simulation.compare_strategies(spec, plans)
    json.dumps(report, allow_nan=False)
    assessment = report["metadata"]["product_credibility"]
    assert assessment["status"] == "extraordinary_unsubstantiated"
    assert assessment["numeric_policy"]["status"] == "unvalidated_assumption"
    assert assessment["numeric_policy"]["acceptance_bounds"] == [.0005, 1.0]
    assert report["engine_version"] == "0.2.0-numeric-11"
    assert all("mean_scam_suspicion" in s and "skeptical_comments" in s for s in report["scenarios"])


def test_ordinary_numeric9_outputs_are_preserved_except_explicit_new_metrics():
    product = ProductSpec(name="Ordinary creative editor", category="software", unit_price_cents=1000,
        description="An ordinary offline editing utility for organizing clips.")
    audience = AudienceSpec(population=400, representatives=10)
    plans = [MediaPlan(id="baseline", name="baseline", price_cents=1000, media_budget_cents=0),
        MediaPlan(id="mixed", name="mixed", price_cents=1000, media_budget_cents=3000, placements=[
            Placement(id="search", channel="search", daily_frequency=4),
            Placement(id="short", channel="tiktok", format="short_video", charge_basis="ORGANIC", daily_frequency=6)])]
    expected = {"baseline": "bf9781fe73f0c0217c4ca5f1b446f8af34f3b623c20ac305ed57f5a438056ca1",
                "mixed": "61c8b92dd8c54a3b9d87d039356b0210890cb4ef418458a80995cc93ac5a13ba"}
    new_keys = {"product_credibility", "mean_scam_suspicion", "mean_credibility_acceptance",
                "scam_suspicion", "credibility_acceptance", "comment_sentiment", "skeptical_comments", "positive_comments",
                "age_segments", "market_switching"}
    def legacy(value):
        if isinstance(value, dict):
            return {key: legacy(item) for key, item in value.items() if key not in new_keys}
        if isinstance(value, list):
            return [legacy(item) for item in value]
        return value

    def compare(actual, reference, path="result"):
        # NumPy's platform builds can differ by ULPs in continuous quantities.
        # Counts, monetary cents, strings, booleans and structure stay exact.
        assert type(actual) is type(reference), path
        if isinstance(reference, dict):
            assert actual.keys() == reference.keys(), path
            for key in reference:
                compare(actual[key], reference[key], f"{path}.{key}")
        elif isinstance(reference, list):
            assert len(actual) == len(reference), path
            for index, (item, expected_item) in enumerate(zip(actual, reference, strict=True)):
                compare(item, expected_item, f"{path}[{index}]")
        elif isinstance(reference, float):
            assert actual == pytest.approx(reference, rel=1e-12, abs=1e-12), path
        else:
            assert actual == reference, path

    for plan in plans:
        result = legacy(simulation.simulate_scenario(product, audience, plan, 7, 123))
        result["engine_version"] = "0.1.0-numeric-9"
        fixture = Path(__file__).parent / "fixtures" / "numeric9" / f"{plan.id}.json"
        reference = json.loads(fixture.read_text(encoding="utf-8"))
        digest = hashlib.sha256(json.dumps(reference, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        assert digest == expected[plan.id]
        compare(json.loads(json.dumps(result)), reference)
