"""Application operations shared by CLI and HTTP clients."""
import re

from .models import ProductSpec, ResearchRequest, StudySpec, TrendReport
from .storage import Store


def study_with_credibility(study: dict) -> dict:
    from .credibility import assess_product_credibility
    return {**study, "product_credibility": assess_product_credibility(study["spec"]["product"])}


def screen_product_claims(report: TrendReport, product: ProductSpec):
    from .credibility import assess_product_credibility
    assessment = assess_product_credibility(product, report)
    report.coverage["product_credibility"] = assessment
    if assessment["status"] != "ordinary":
        report.limitations.append("Product promises are unsubstantiated; skepticism coefficients are declared hypotheses, not scientific verification or measured fraud rates.")


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
    screen_product_claims(report, spec.product)
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
    return study_with_credibility(study)


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
    if spec.objective == "market_discovery" and request.mode == "live":
        suffix = (" alternatives concurrents prix avis migration" if spec.locale == "fr"
                  else " alternatives competitors pricing reviews migration")
        if not request.topic.endswith(suffix):
            request = request.model_copy(update={"topic": (request.topic or spec.product.name)[:330] + suffix})
    paid = request.mode == "live" or (request.mode == "urls" and request.use_firecrawl)
    if paid and spec.api_budget_usd <= 0:
        raise ValueError("Set a positive real API budget when creating the study before enabling paid services")
    (store.root / "budgets").mkdir(exist_ok=True)
    ledger = BudgetLedger(store.root / "budgets" / f"{study_id}.sqlite", spec.api_budget_usd, spec.api_max_calls)
    report = await run_research(request, spec.product, ledger=ledger)
    screen_product_claims(report, spec.product)
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


async def guided_launch(store: Store, spec: StudySpec, *, launch_workers: bool) -> dict:
    """Explicit one-click free/offline launch; paid research keeps its own action."""
    from .jobs import spawn_worker
    if spec.research.mode == "live" or spec.research.use_llm or spec.research.use_firecrawl or spec.use_representative_llm:
        raise ValueError("Guided launch uses free/offline research. Start paid research or representative inference through its explicit action.")
    study = await prepare_study(store, spec)
    warning = None
    supplied = ([spec.market.product_url] if spec.market.product_url else []) + spec.market.competitor_urls
    urls = list(dict.fromkeys(supplied + spec.research.urls))
    if urls:
        # The click authorizes fetching supplied pages, never discovery or inference.
        request = spec.research.model_copy(update={"mode": "urls", "urls": urls[:20],
            "region": spec.audience.region})
        try:
            result = await research_study(store, study["id"], request)
            if result["report"]["coverage"].get("failures") or len(urls) > min(20, request.max_sources):
                warning = ("Certaines sources n'ont pas pu être lues ou dépassent la limite de collecte. L'étude est conservée ; les conclusions restent conditionnelles."
                           if spec.locale == "fr" else "Some sources could not be read or exceeded the collection limit. The study is retained; conclusions remain conditional.")
        except (ValueError, OSError) as exc:
            # Preserve the editable saved study if acquisition is unavailable.
            warning = (f"Sources indisponibles ({type(exc).__name__}). Simulation lancée sur les données conservées."
                       if spec.locale == "fr" else f"Sources unavailable ({type(exc).__name__}). Simulation uses the retained inputs.")
    study = study_with_credibility(store.get_study(study["id"]))
    run = store.create_run(study["id"], study["spec"], study["plans"])
    if launch_workers:
        spawn_worker(store, run["id"])
    return {"study": study, "run": store.get_run(run["id"], include_report=False), "research_error": warning}
