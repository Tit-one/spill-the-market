"""Clearly fictional examples; never imported from the user's private studies."""
from .models import AudienceSpec, ProductSpec, ResearchRequest, StudySpec


def examples() -> list[dict]:
    game = StudySpec(
        product=ProductSpec(
            name="Orbit Orchard", category="game", unit_price_cents=1990, variable_cost_cents=150,
            description="A fictional cooperative space-gardening game. Short sessions, expressive world-building, "
            "playable solo or with friends. Windows and macOS. A free demo and gameplay trailer are available.",
            keywords=["co-op", "cozy gaming", "short sessions", "demo"],
        ),
        audience=AudienceSpec(age_min=18, age_max=35),
        research=ResearchRequest(topic="Independent cooperative cozy games", mode="demo"),
    )
    software = StudySpec(
        product=ProductSpec(
            name="FrameBridge", category="software", unit_price_cents=7900, variable_cost_cents=500,
            description="A fictional creative-workflow tool for editors: transfer structured sequences between "
            "editing applications, preserve names and timing, and reduce repetitive rebuilding. "
            "One-time licence, compatibility matrix, short demonstration and trial available.",
            keywords=["compatibility", "workflow", "trial", "editing"],
        ),
        audience=AudienceSpec(age_min=25, age_max=55),
        research=ResearchRequest(topic="Creative editing workflow software", mode="demo"),
    )
    return [
        {"id": "game", "name": game.product.name, "spec": game.model_dump()},
        {"id": "software", "name": software.product.name, "spec": software.model_dump()},
    ]
