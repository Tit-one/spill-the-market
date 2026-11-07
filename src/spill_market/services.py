"""Application operations shared by CLI and HTTP clients."""
import re

from .models import ProductSpec, ResearchRequest, StudySpec, TrendReport
from .storage import Store


def age_recommendation(product: ProductSpec, report: TrendReport) -> dict:
    """Propose, never claim an optimal age or infer demographics from slang."""
    for source in report.sources:
        if source.kind == "demo":
            continue
        match = re.search(r"(?:ages?|âg[ée]s? de)\s*(\d{2})\s*(?:-|–|to|à)\s*(\d{2})", source.content, re.I)
        if match:
            low, high = map(int, match.groups())
            if 18 <= low <= high <= 100:
                return {"range": [low, high], "status": "inferred", "source_ids": [source.id],
                        "reason": "An explicit age range occurs in a supplied source; relevance still needs user confirmation."}
    default = {"game": [18, 35], "software": [25, 55], "physical": [18, 65],
               "service": [25, 65], "other": [18, 65]}[product.category]
    return {"range": default, "status": "assumption", "source_ids": [],
            "reason": "Illustrative product-category hypothesis, not measured demographics or an optimal target."}


def persist_beliefs(memory, study_id, personas):
    for persona in personas:
        for belief in persona.beliefs[:6]:
            if belief.get("text"):
                memory.add_belief(study_id, persona.id, str(belief["text"]), belief.get("source_ids", []))


async def prepare_study(store: Store, spec: StudySpec) -> dict:
    from .media import propose_plans
    from .memory import LocalMemory
    from .personas import generate_personas
    from .research import run_research

    # Saving an experiment must never implicitly purchase research or inference.
    request = spec.research if spec.research.mode in {"demo", "offline"} else ResearchRequest(
        mode="offline", topic=spec.research.topic, language=spec.research.language, region=spec.research.region,
    )
    report = await run_research(request, spec.product)
    suggestion = age_recommendation(spec.product, report)
    report.coverage["age_recommendation"] = suggestion
    if spec.audience.auto_age:
        report.recommended_age_range = suggestion["range"]
        report.limitations.append("Proposed target ages require explicit confirmation; the submitted strict age range is unchanged.")
    personas = generate_personas(spec.product, spec.audience, report, seed=spec.seed,
                                 limit=spec.audience.representatives)
    plans = propose_plans(spec.product, spec.audience, spec.media_budget_cents, report)
    study = store.create_study(spec.model_dump(), [p.model_dump() for p in plans],
                               [p.model_dump() for p in personas], report.model_dump())
    memory = LocalMemory(store.root / "memory.sqlite")
    memory.ingest_report(study["id"], report)
    persist_beliefs(memory, study["id"], personas)
    return study


async def research_study(store: Store, study_id: str, payload: ResearchRequest | None = None) -> dict:
    from .gateway import BudgetLedger
    from .media import propose_plans
    from .memory import LocalMemory
    from .models import MediaPlan
    from .personas import generate_personas
    from .research import run_research
    study = store.get_study(study_id)
    spec = StudySpec.model_validate(study["spec"])
    request = payload or spec.research
    paid = request.mode == "live" or (request.mode == "urls" and request.use_firecrawl)
    if paid and spec.api_budget_usd <= 0:
        raise ValueError("Set a positive real API budget when creating the study before enabling paid services")
    (store.root / "budgets").mkdir(exist_ok=True)
    ledger = BudgetLedger(store.root / "budgets" / f"{study_id}.sqlite", spec.api_budget_usd, spec.api_max_calls)
    report = await run_research(request, spec.product, ledger=ledger)
    suggestion = age_recommendation(spec.product, report)
    report.coverage["age_recommendation"] = suggestion
    if spec.audience.auto_age:
        report.recommended_age_range = suggestion["range"]
        report.limitations.append("Proposed target ages require explicit confirmation; the submitted strict age range is unchanged.")
    personas = generate_personas(spec.product, spec.audience, report, seed=spec.seed,
                                 limit=spec.audience.representatives)
    proposed = propose_plans(spec.product, spec.audience, spec.media_budget_cents, report)
    old_plans = {plan["id"]: MediaPlan.model_validate(plan) for plan in study["plans"]}
    for plan in proposed:
        previous = old_plans.get(plan.id)
        if previous:
            plan.price_cents = previous.price_cents
            locked = [p for p in previous.placements if p.locked]
            locked_channels = {p.channel for p in locked}
            locked_ids = {p.id for p in locked}
            plan.placements = [p for p in plan.placements if p.channel not in locked_channels and p.id not in locked_ids] + locked
    spec.research = request
    store.update_study(study_id, spec=spec.model_dump(), research=report.model_dump(),
                       personas=[p.model_dump() for p in personas], plans=[p.model_dump() for p in proposed])
    memory = LocalMemory(store.root / "memory.sqlite")
    memory.ingest_report(study_id, report)
    persist_beliefs(memory, study_id, personas)
    return {"report": report.model_dump(), "cost": ledger.summary(), "plans": [p.model_dump() for p in proposed]}
