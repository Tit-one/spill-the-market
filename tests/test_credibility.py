import copy
import json

import pytest

from spill_market.credibility import assess_product_credibility
from spill_market.models import EvidenceSource, Finding, ProductSpec, TrendReport


def product(description, category="physical", **kwargs):
    return ProductSpec(name="My life", description=description, category=category, unit_price_cents=150000, **kwargs)


def test_french_miracle_immortality_claim_has_strong_unsubstantiated_risk_despite_stale_game_keywords():
    subject = product("Un produit miracle qui promet l'immortalité", keywords=["co-op", "cozy"])
    result = assess_product_credibility(subject)
    assert result["status"] == "extraordinary_unsubstantiated"
    assert 0 < result["score"] <= 0.1
    assert 0.85 <= result["scam_suspicion"] < 1
    assert result["claims"][0]["kind"] == "immortality"
    assert result["claims"][0]["evidence_status"] == "unsubstantiated"
    assert "immortalité" in result["claims"][0]["text"]
    assert result["required_evidence"] and result["assumptions"]
    assert result["source"] == "rule_based" and result["version"]
    assert set(result) == {"status", "score", "scam_suspicion", "claims", "reasons", "assumptions", "required_evidence", "source", "version"}
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("description,category", [
    ("A game about immortality and a fictional hero's adventures.", "game"),
    ("Become immortal in this fantasy adventure game.", "game"),
    ("Un jeu de plateau où le personnage devient immortel.", "physical"),
    ("This software tracks immortal characters in a game.", "software"),
    ("Un roman sur la quête de l'immortalité dans un univers imaginaire.", "physical"),
    ("Ce produit ne promet PAS l'immortalité et ne guérit pas toutes les maladies.", "physical"),
    ("This product does not promise immortality or cure every disease.", "physical"),
    ("This is not an immortality treatment; it is an ordinary moisturizing cream.", "physical"),
    ("Critique des publicités qui promettent l'immortalité : ce sont de fausses promesses.", "service"),
    ('We debunk the advertisement "this pill grants immortality" and explain why the claim is unsupported.', "service"),
    ("A prototype battery aiming to improve cycle life by 20%, under laboratory evaluation.", "physical"),
    ("We research whether immortality might be possible; no efficacy is claimed.", "service"),
    ("A durable backpack with a lifetime warranty and a 30-day money-back guarantee.", "physical"),
    ("A cooperative cozy game with unlimited respawns for the player character.", "game"),
    ("Un produit cosmétique à l'immortelle pour hydrater la peau.", "physical"),
    ("Un produit parfumé appelé Immortalité qui dure quelques heures.", "physical"),
    ("Ce produit ne rend personne immortel.", "physical"),
    ("No product can make humans immortal.", "service"),
    ("Our book examines the claim that a pill grants immortality.", "physical"),
    ("Notre service rend vos souvenirs immortels grâce à des copies de photos.", "service"),
    ("Our service makes your artwork immortal with durable printed copies.", "service"),
])
def test_mentions_fiction_negation_counterclaims_and_ordinary_guarantees_are_not_extraordinary_promises(description, category):
    result = assess_product_credibility(product(description, category))
    assert result["status"] == "ordinary"
    assert result["claims"] == []
    assert result["scam_suspicion"] <= 0.15


@pytest.mark.parametrize("description,kind", [
    ("Our miracle pill grants immortality and makes your body live forever.", "immortality"),
    ("Ce remède miracle guérit toutes les maladies, sans exception.", "cure_all"),
    ("This supplement cures every disease with guaranteed results.", "cure_all"),
    ("Guaranteed investment returns of 30% every month with absolutely no risk.", "guaranteed_returns"),
    ("Un rendement garanti de 30 % par mois, sans aucun risque de perte.", "guaranteed_returns"),
    ("A perpetual motion machine produces unlimited energy without any fuel or input.", "unbounded_physical_performance"),
])
def test_explicit_unbounded_real_world_claims_have_auditable_risk(description, kind):
    result = assess_product_credibility(product(description))
    assert result["status"] == "extraordinary_unsubstantiated"
    assert any(claim["kind"] == kind for claim in result["claims"])
    assert result["score"] <= 0.2 and result["scam_suspicion"] >= 0.7
    assert all(claim["text"] and claim["reason"] for claim in result["claims"])


def test_game_category_cannot_hide_an_explicit_real_life_efficacy_promise():
    result = assess_product_credibility(product("This game promises to make your real-life body immortal.", category="game"))
    assert result["status"] == "extraordinary_unsubstantiated"


def test_negated_promise_does_not_hide_a_later_affirmative_promise():
    result = assess_product_credibility(product("Nous ne promettons pas une peau parfaite, mais notre pilule vous rend immortel."))
    assert result["status"] == "extraordinary_unsubstantiated"


def test_criticizing_other_promises_does_not_hide_the_products_own_later_promise():
    result = assess_product_credibility(product("We debunk misleading advertisements, and our pill grants immortality."))
    assert result["status"] == "extraordinary_unsubstantiated"


def test_tentative_ambition_is_needs_evidence_not_a_scientific_fraud_verdict():
    result = assess_product_credibility(product("Our experimental prototype may eventually allow humans to live forever; this remains an untested hypothesis."))
    assert result["status"] == "needs_evidence"
    assert result["score"] >= 0.4 and result["scam_suspicion"] <= 0.4


def test_marketing_sources_never_become_independent_verified_evidence():
    subject = product("A miracle pill promising immortality.")
    research = TrendReport(topic="marketing", mode="live", sources=[
        EvidenceSource(id="promo", title="Our clinical proof", url="https://example.com/marketing", kind="web",
                       content="Our product is scientifically proven to grant immortality.")],
        trends=[Finding(text="Our product is scientifically proven to grant immortality.", source_ids=["promo"], status="observed", confidence=1)])
    before = assess_product_credibility(subject)
    after = assess_product_credibility(subject, research)
    assert after["status"] == before["status"] and after["score"] == before["score"]
    assert all(claim["evidence_status"] != "verified" for claim in after["claims"])


def test_assessment_is_deterministic_does_not_mutate_inputs_and_has_no_age_argument():
    subject = product("A miracle product promises immortality.")
    original = copy.deepcopy(subject.model_dump())
    assert assess_product_credibility(subject) == assess_product_credibility(subject.model_dump())
    assert subject.model_dump() == original


def test_numeric_overrides_are_explicit_hypotheses_and_cannot_forge_verified_evidence():
    result = assess_product_credibility(product("A miracle pill promises immortality."), overrides={
        "score": 0.6, "scam_suspicion": 0.2, "status": "needs_evidence", "reason": "Owner's sensitivity scenario"})
    assert result["score"] == 0.6 and result["status"] == "needs_evidence"
    assert any("override" in assumption.lower() for assumption in result["assumptions"])
    assert result["claims"][0]["evidence_status"] == "unsubstantiated"
    with pytest.raises(ValueError):
        assess_product_credibility(product("A miracle pill promises immortality."), overrides={"evidence_status": "verified"})


@pytest.mark.parametrize("overrides", [{"score": -0.1}, {"score": float("nan")}, {"scam_suspicion": 1.1}, {"status": "proven_scam"}, []])
def test_invalid_overrides_are_rejected(overrides):
    with pytest.raises(ValueError):
        assess_product_credibility(product("An ordinary handmade bag with a durable strap."), overrides=overrides)


@pytest.mark.parametrize("description", [
    "This supplement does not help you live forever; it is an ordinary moisturizing cream.",
    "Ce produit ne procure pas l’immortalité; il hydrate la peau.",
])
def test_negation_governs_the_matched_claim_without_a_fixed_verb_list(description):
    result = assess_product_credibility(product(description))
    assert result["status"] == "ordinary" and result["claims"] == []


@pytest.mark.parametrize("description", [
    "A fantasy game is included and our bracelet grants immortality.",
    "A game-inspired bracelet grants immortality to its wearer.",
    "We debunk ordinary skin myths while our pill guarantees immortality.",
])
def test_unrelated_fiction_or_counterclaim_context_cannot_exempt_a_real_promise(description):
    result = assess_product_credibility(product(description))
    assert result["status"] == "extraordinary_unsubstantiated"
    assert any(claim["kind"] == "immortality" for claim in result["claims"])


@pytest.mark.parametrize("description", [
    "Our pill grants immortality to humans just like fictional characters.",
    "Notre pilule rend les humains immortels comme des personnages fictifs.",
])
def test_fictional_comparison_does_not_exempt_a_real_human_promise(description):
    result = assess_product_credibility(product(description))
    assert result["status"] == "extraordinary_unsubstantiated"
    assert any(claim["kind"] == "immortality" for claim in result["claims"])


@pytest.mark.parametrize("description", [
    "A physical board game where your character becomes immortal.",
    "A game item: this bracelet grants immortality to the player character.",
    "Our fictional character becomes immortal.",
    "This potion grants immortality to a fictional character.",
    "Cette potion rend le personnage immortel.",
    "In this fantasy game, the potion grants immortality.",
    "We debunk the claim that our pill guarantees immortality.",
    "This supplement does not confer immortality or cure every disease.",
    "Ce produit n'apporte pas l'immortalité et aide seulement à hydrater la peau.",
])
def test_governing_narrative_counterclaim_and_generic_negation_remain_nonclaims(description):
    assert assess_product_credibility(product(description))["status"] == "ordinary"


@pytest.mark.parametrize("description", [
    "Our cream does not cost much while it grants immortality.",
    "Ce produit ne coûte pas cher mais procure l'immortalité.",
])
def test_negation_of_an_unrelated_predicate_does_not_negate_a_later_claim(description):
    assert assess_product_credibility(product(description))["status"] == "extraordinary_unsubstantiated"


@pytest.mark.parametrize("description", [
    "A game-inspired immortality accessory.",
    "Our pill is not incapable of granting immortality.",
])
def test_ambiguous_scope_requires_evidence_instead_of_a_fiction_or_negation_exemption(description):
    assert assess_product_credibility(product(description))["status"] == "needs_evidence"
