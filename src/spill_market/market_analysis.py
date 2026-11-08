"""Evidence-aware market interpretation; no inferred market sizes or factual competitors.

Numerical outcomes remain conditional on assumptions. External statements are
quoted as data with provenance and never treated as executable instructions.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from .credibility import assess_product_credibility
from .evidence_urls import public_evidence_url, url_reference_hash
from .models import StudySpec, TrendReport


def _url(value: str | None) -> str | None:
    return public_evidence_url(value)


def _recommend(rows, *, metric, population_key, identity, t):
    eligible = [r for r in rows if r.get(population_key, 0) >= 30 and r.get("units", 0) >= 1
                and r.get(metric) is not None]
    ordered = sorted(eligible, key=lambda row: row[metric], reverse=True)
    chosen = ordered[0] if ordered else None
    if len(ordered) > 1:
        top, runner = ordered[:2]
        if abs(top[metric] - runner[metric]) <= 1e-12:
            chosen = None
        bounds = top.get("conversion_rate_interval")
        for other in ordered[1:]:
            other_bounds = other.get("conversion_rate_interval")
            if bounds and other_bounds and bounds[0] <= other_bounds[1]:
                chosen = None
    return {"status": "hypothesis" if chosen else "inconclusive",
            **{key: chosen.get(key) if chosen else None for key in identity},
            "reason": (t("Une piste issue des taux simulés, à confirmer sur le terrain.",
                         "A lead from simulated rates, requiring real-world validation.") if chosen else
                       t("Aucun classement suffisamment distinct : trop peu de réponses, égalité ou dispersion qui se recoupe.",
                         "No sufficiently distinct ranking: sparse responses, ties or overlapping simulation dispersion."))}


def build_market_analysis(spec: StudySpec, research: TrendReport | None, report: dict) -> dict:
    """Combine grounded excerpts and full-population validation aggregates.

    A supplied competitor URL is a reference, not proof of competitive relevance.
    Switching is a subset of simulated buyers; optional projection is explicitly
    a user-population extrapolation, never additional simulated revenue.
    """
    def t(fr, en):
        return fr if spec.locale == "fr" else en
    sources = research.sources if research else []
    by_id = {source.id: source for source in sources}
    real = [source for source in sources if source.kind != "demo"]
    demo = [source for source in sources if source.kind == "demo"]
    competitors, represented = [], set()
    product_url = _url(spec.market.product_url)
    product_reference = url_reference_hash(spec.market.product_url)

    def reference(source):
        return source.url_reference_hash or url_reference_hash(source.url)

    for supplied in spec.market.competitor_urls:
        url = _url(supplied)
        identity = url_reference_hash(supplied)
        if not url or identity == product_reference or identity in represented:
            continue
        represented.add(identity)
        matches = [s for s in sources if reference(s) == identity]
        actual = [s for s in matches if s.kind != "demo"]
        chosen = actual or matches
        competitors.append({"name": chosen[0].title if chosen else urlsplit(url).hostname,
            "url": url, "source_ids": [s.id for s in chosen],
            "excerpts": [s.content[:700] for s in chosen[:2]],
            "evidence_status": "source_statement" if actual else "fictional" if chosen else "unread_reference"})
    mentions = research.coverage.get("competitor_mentions", []) if research else []
    for mention in mentions[:20]:
        text = mention.get("text", "")
        ids = mention.get("source_ids", [])
        if not text or not ids or any(i not in by_id or text not in by_id[i].content for i in ids):
            continue
        source = by_id[ids[0]]
        url = _url(source.url)
        identity = reference(source)
        if identity and (identity == product_reference or identity in represented):
            continue
        if not source.url_reference_hash and url and url == product_url:
            continue
        if identity:
            represented.add(identity)
        competitors.append({"name": source.title, "url": url, "source_ids": ids,
            "excerpts": [text], "evidence_status": "fictional" if any(by_id[i].kind == "demo" for i in ids)
            else "source_statement"})
    candidates = [row for row in report.get("scenarios", []) if not row.get("is_baseline")]
    selected_id = report.get("metadata", {}).get("exploration_selected_id")
    scenario = next((row for row in candidates if row.get("plan_id") == selected_id), None)
    scenario = scenario or (max(candidates, key=lambda row: row.get("mean_revenue_cents", 0)) if candidates else {})
    segments = scenario.get("age_segments", [])
    channels = scenario.get("channels", [])
    segment_rec = _recommend(segments, metric="conversion_rate", population_key="population",
                             identity=("age_min", "age_max"), t=t)
    channel_rec = _recommend(channels, metric="attributed_conversion_rate", population_key="unique_reach",
                             identity=("channel",), t=t)
    segment_rec.update(based_on_plan=scenario.get("plan_id"), segments=segments)
    channel_rec.update(based_on_plan=scenario.get("plan_id"), channels=channels)
    switching = dict(scenario.get("market_switching", {"enabled": False, "status": "not_available"}))
    switching["market_projection"] = None
    if switching.get("enabled") and spec.market.addressable_population is not None:
        switching["market_projection"] = {"addressable_population": spec.market.addressable_population,
            "estimated_switchers": switching.get("switchers", 0) / spec.audience.population * spec.market.addressable_population,
            "status": "unvalidated_extrapolation"}
    barriers = []

    def barrier(kind, title, detail, *, status="assumption", severity="medium", source_ids=None):
        barriers.append({"kind": kind, "title": title, "detail": detail, "status": status,
                         "severity": severity, "source_ids": source_ids or []})

    assessment = assess_product_credibility(spec.product, research=research)
    if assessment["status"] != "ordinary":
        barrier("credibility", t("La promesse peut susciter de la méfiance", "The promise may create distrust"),
            t("La promesse demande des preuves. Le modèle applique une réserve hypothétique, sans établir une fraude.",
              "The claim needs evidence. The model applies hypothetical skepticism, without establishing fraud."), severity="high")
    if switching.get("enabled") and spec.market.switching_friction > 0:
        barrier("switching", t("Changer de solution demande un effort", "Changing solutions takes effort"),
            t("Apprentissage, migration des données, habitudes et engagements peuvent retenir les utilisateurs. Leur intensité est une hypothèse modifiable.",
              "Learning, data migration, habits and commitments can retain users. Their strength is an editable assumption."), status="simulated")
    barrier("price", t("Vérifier l'acceptabilité du prix", "Check price acceptability"),
        t("La sensibilité au prix et les budgets des personas sont synthétiques. Comparer des offres et tester le prix auprès de prospects réels.",
          "Persona budgets and price sensitivity are synthetic. Compare alternatives and test price with real prospects."))
    if research:
        for finding in research.pain_points[:8]:
            ids = finding.source_ids
            if ids and all(i in by_id and by_id[i].kind != "demo" and finding.text in by_id[i].content for i in ids):
                barrier("source_pain", t("Difficulté mentionnée dans une source", "Difficulty reported in a source"),
                        finding.text, status="source_statement", source_ids=ids)
    if not real:
        barrier("research_gap", t("Les besoins restent à vérifier", "Needs remain unverified"),
            t("Aucune source réelle lisible. Ajouter des pages concurrentes, avis, entretiens ou données de marché avant de généraliser.",
              "No readable real sources. Add competitor pages, reviews, interviews or market data before generalizing."), severity="high")
    next_actions = [
        {"kind": "competition", "title": t("Comparer les alternatives", "Compare alternatives"),
         "detail": t("Recueillir prix, limites, preuves, avis et conditions de migration. Une référence n'est pas un concurrent vérifié.",
                     "Collect prices, limits, evidence, reviews and migration conditions. A reference is not a verified competitor."), "source_ids": []},
        {"kind": "page", "title": t("Tester la compréhension de la page", "Test page comprehension"),
         "detail": t("Ouvrir l'analyse de page pour examiner les questions, la confiance et les freins par persona, avec captures.",
                     "Open page analysis to examine persona questions, trust and friction using screenshots."), "source_ids": []},
        {"kind": "validation", "title": t("Confronter les pistes à de vrais prospects", "Validate leads with real prospects"),
         "detail": t("Tester le besoin, le prix et le changement d'offre avec des entretiens puis un petit test de campagne mesuré.",
                     "Test need, price and switching in interviews, then a small measured campaign."), "source_ids": []},
    ]
    limitations = [
        t("Tranches et canaux : résultats conditionnels à des profils et préférences synthétiques, pas une démographie mesurée.",
          "Ages and channels: conditional synthetic profiles and preferences, not measured demographics."),
        t("Les taux par canal décrivent des expositions et budgets différents ; ce n'est pas un test causal isolant chaque canal.",
          "Channel rates describe different exposures and budgets; this is not a controlled causal channel test."),
        t("Les personnes qui changent d'offre sont incluses dans les acheteurs, jamais ajoutées aux ventes. Parts d'utilisateurs et freins sont des hypothèses.",
          "Switchers are included in buyers, never added to sales. Incumbent shares and friction are assumptions."),
        t("Sans population de marché fournie et documentée, aucun volume réel de clients accessibles n'est estimé.",
          "Without a supplied, documented market population, no real addressable customer volume is estimated."),
    ]
    return {"schema_version": "1.0", "objective": spec.objective,
        "status": "evidence_informed_simulation" if real else "demo" if demo else "hypotheses_only",
        "coverage": {"real_source_count": len(real), "demo_source_count": len(demo),
            "competitor_reference_count": len(competitors),
            "market_size_status": "user_assumption" if spec.market.addressable_population is not None else "unknown"},
        "competitors": competitors[:20], "barriers": barriers, "segment_recommendation": segment_rec,
        "channel_recommendation": channel_rec, "switching": switching, "next_actions": next_actions,
        "sources": [{"id": s.id, "title": s.title, "url": _url(s.url), "retrieved_at": s.retrieved_at,
                     "published_at": s.published_at, "kind": s.kind} for s in sources], "limitations": limitations}
