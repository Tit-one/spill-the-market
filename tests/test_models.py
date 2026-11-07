import pytest


def test_age_range_is_strict_and_inclusive():
    from spill_market.models import AudienceSpec
    assert AudienceSpec(age_min=18, age_max=25).age_max == 25
    with pytest.raises(ValueError):
        AudienceSpec(age_min=40, age_max=25)
    with pytest.raises(ValueError):
        AudienceSpec(age_min=17)


def test_product_and_placement_reject_invalid_money():
    from spill_market.models import ProductSpec, Placement
    with pytest.raises(ValueError):
        ProductSpec(name="Demo", description="A fictional game", unit_price_cents=-1)
    with pytest.raises(ValueError):
        Placement(channel="in_game", daily_frequency=99)


def test_study_can_run_offline_without_api_budget():
    from spill_market.models import StudySpec, ProductSpec
    spec = StudySpec(product=ProductSpec(name="Demo", description="A fictional product", unit_price_cents=2000))
    assert spec.research.mode == "demo"
    assert spec.api_budget_usd == 0


def test_optional_ai_response_hypotheses_are_bounded():
    from spill_market.models import StudySpec, ProductSpec
    product = ProductSpec(name="Demo", description="Fictional game", unit_price_cents=2000)
    spec = StudySpec(product=product, use_representative_llm=True, response_multipliers={"tiktok": 1.1})
    assert spec.response_multipliers["tiktok"] == 1.1
    with pytest.raises(ValueError):
        StudySpec(product=product, response_multipliers={"tiktok": 9})


def test_duplicate_placement_ids_are_rejected_before_saving():
    from spill_market.models import MediaPlan, Placement
    with pytest.raises(ValueError):
        MediaPlan(id="test", name="Test", price_cents=1000, media_budget_cents=1000,
                  placements=[Placement(id="same", channel="youtube"), Placement(id="same", channel="search")])
