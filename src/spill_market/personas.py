"""Synthetic individual attributes with optional weak, unvalidated age priors.

Representatives are bounded, fictional examples of the same numerical population;
they are never expanded into weighted sales or treated as demographic evidence.
"""
from __future__ import annotations

import numpy as np

from .models import AudienceSpec, Persona, ProductSpec, TrendReport


CHANNELS = (
    "tiktok", "instagram", "facebook", "youtube", "twitch", "in_game", "search",
    "display", "podcast", "newsletter", "affiliate", "creators", "communities", "x", "reddit",
)

# Illustrative log-odds slopes, not demographic measurements. Even at the maximum
# permitted weight, these soft shifts preserve the full (0, 1) support and broad
# within-age variation. Purchasing power, need and price response are unaffected.
AGE_CHANNEL_PRIORS = (-.8, -.4, .4, -.1, -.6, -.5, .1, 0, .2, .3, 0, -.2, 0, -.1, .1)


def grounded_findings(research: TrendReport | None, limit: int = 8) -> list[dict]:
    """Return bounded themes with intact provenance; orphan findings are excluded."""
    if research is None:
        return []
    sources = {s.id: s for s in research.sources}
    result, seen = [], set()
    for kind in ("pain_points", "trends", "jargon", "segments"):
        for finding in getattr(research, kind):
            if not finding.source_ids or any(source_id not in sources for source_id in finding.source_ids):
                continue
            if finding.text in seen:
                continue
            seen.add(finding.text)
            result.append({"text": finding.text[:320], "source_ids": finding.source_ids[:10],
                           "evidence_status": finding.status, "confidence": finding.confidence,
                           "source_kinds": sorted({sources[s].kind for s in finding.source_ids}),
                           "theme_kind": kind})
            if len(result) >= limit:
                return result
    return result


def initialize_population(product: ProductSpec, audience: AudienceSpec, seed: int = 42) -> dict:
    """Allocate one unweighted numerical state per individual (including 100,000)."""
    rng = np.random.default_rng(np.random.SeedSequence([int(seed), 19371]))
    age_rng = np.random.default_rng(np.random.SeedSequence([int(seed), 19372]))
    n = audience.population
    # Price-independent purchasing power is essential for a fair price comparison.
    states = {
        "id": np.arange(n, dtype=np.int64),
        "age": age_rng.integers(audience.age_min, audience.age_max + 1, n, dtype=np.int16),
        "budget_cents": np.clip(rng.lognormal(8.4, 1.15, n), 50, 10_000_000).astype(np.int64),
        "need_fit": rng.beta(2.1, 2.4, n),
        "trust": rng.beta(2.7, 2.3, n),
        "price_sensitivity": rng.beta(2.2, 2.2, n),
        "social_sensitivity": rng.beta(2.1, 2.1, n),
        "fatigue_tolerance": rng.beta(2.3, 2.3, n),
        "prerequisite_fit": rng.random(n) >= min(.7, .07 * len(product.prerequisites)),
        "peak_hour": (rng.normal(18, 4, n) % 24),
        "language_index": rng.integers(0, len(audience.languages), n),
        "profession_index": rng.integers(0, 8, n),
        "channel_affinity": rng.beta(1.8, 2.8, (n, len(CHANNELS))),
        "purchased": np.zeros(n, dtype=bool),
        "intention": np.zeros(n, dtype=np.float64),
        "awareness": np.zeros(n, dtype=np.float64),
        "fatigue": np.zeros(n, dtype=np.float64),
        "last_channel": np.full(n, -1, dtype=np.int16),
        "last_exposure_day": np.full(n, -100, dtype=np.int16),
        "last_click_hour": np.full(n, -1000, dtype=np.int16),
        "last_view_channel": np.full(n, -1, dtype=np.int16),
        "last_view_hour": np.full(n, -1000, dtype=np.int16),
        "creator_role": rng.random(n) < .12,
    }
    if audience.age_behavior_weight:
        centered_age = np.clip((states["age"].astype(float) - 44) / 36, -1, 1)
        weight = audience.age_behavior_weight
        def soft_shift(values, shift):
            return 1 / (1 + np.exp(-(np.log(values / (1 - values)) + shift)))
        states["channel_affinity"] = soft_shift(states["channel_affinity"],
            weight * centered_age[:, None] * np.array(AGE_CHANNEL_PRIORS))
        states["social_sensitivity"] = soft_shift(states["social_sensitivity"], -.3 * weight * centered_age)
    return states


def generate_personas(product: ProductSpec, audience: AudienceSpec, research: TrendReport | None = None,
                      seed: int = 42, limit: int = 200) -> list[Persona]:
    states = initialize_population(product, audience, seed)
    count = min(max(0, limit), audience.representatives, 200, audience.population)
    indices = np.linspace(0, audience.population - 1, count, dtype=int)
    professions = ["Designer", "Developer", "Teacher", "Technician", "Retail worker",
                   "Independent maker", "Office worker", "Researcher"]
    result = []
    themes = grounded_findings(research)
    for i in indices:
        beliefs = [{"text": f"A fictional need for a product in the {product.category} category.",
                    "status": "synthetic", "source_ids": []}]
        if themes:
            for offset in range(min(2, len(themes))):
                theme = themes[(int(i) + offset) % len(themes)]
                beliefs.append({**theme, "finding_text": theme["text"],
                                "text": f"Synthetic reaction: I may care about this research theme: {theme['text']}",
                                "status": "synthetic"})
        beliefs.append({"text": "Channel preferences and social sensitivity include a weak, unvalidated age prior with broad individual variation.",
                        "status": "synthetic", "source_ids": [],
                        "age_behavior_weight": audience.age_behavior_weight})
        result.append(Persona(
            id=f"persona-{i:06d}", name=f"Synthetic person {i + 1}", age=int(states["age"][i]),
            language=audience.languages[int(states["language_index"][i])],
            profession=professions[int(states["profession_index"][i])],
            budget_cents=int(states["budget_cents"][i]), need_fit=float(states["need_fit"][i]),
            trust=float(states["trust"][i]), price_sensitivity=float(states["price_sensitivity"][i]),
            social_sensitivity=float(states["social_sensitivity"][i]),
            fatigue_tolerance=float(states["fatigue_tolerance"][i]),
            channels={c: float(states["channel_affinity"][i, j]) for j, c in enumerate(CHANNELS)},
            beliefs=beliefs,
            segment="high_need" if states["need_fit"][i] > .6 else "exploring", timezone=audience.timezone,
        ))
    return result
