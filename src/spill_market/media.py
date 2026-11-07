"""Editable campaign candidates and explicitly hypothetical execution constants."""
from __future__ import annotations

from .models import AudienceSpec, MediaPlan, Placement, ProductSpec, TrendReport
from .personas import grounded_findings


_CATALOG = [
    ("tiktok", "short_video", ["short_video", "feed"], .80, .055, .10, 700),
    ("instagram", "short_video", ["reel", "story", "feed"], .75, .05, .09, 800),
    ("facebook", "social_feed", ["feed", "group"], .65, .045, .08, 650),
    ("youtube", "long_video", ["video", "short", "preroll"], .62, .06, .13, 1000),
    ("twitch", "live_stream", ["stream", "sponsorship"], .45, .055, .12, 1200),
    ("in_game", "in_game", ["rewarded_video", "interstitial", "banner"], .60, .035, .07, 600),
    ("search", "intent_search", ["search", "text"], .40, .16, .20, 1500),
    ("display", "display", ["banner", "native"], .88, .012, .035, 400),
    ("podcast", "audio", ["host_read", "audio"], .30, .04, .15, 1800),
    ("newsletter", "permission_email", ["email", "sponsorship"], .35, .11, .17, 1200),
    ("affiliate", "affiliate", ["review", "referral"], .40, .10, .16, 900),
    ("creators", "creator", ["demo", "review", "short_video"], .48, .075, .16, 1400),
    ("communities", "closed_group", ["closed_group", "discussion"], .28, .09, .18, 700),
    ("x", "public_discussion", ["post", "thread"], .60, .04, .07, 600),
    ("reddit", "closed_group", ["community", "discussion"], .33, .075, .15, 750),
]


def channel_catalog() -> list[dict]:
    return [{"channel": c, "name": c.replace("_", " ").title(), "mechanism": mechanism,
             "formats": formats, "availability": availability, "click_rate": click,
             "persuasion": persuasion, "default_cpm_cents": cpm,
             "cost_bases": ["CPM", "CPC", "CPA", "FIXED", "ORGANIC"],
             "assumption": "Synthetic illustrative constants; no measured platform performance or prices."}
            for c, mechanism, formats, availability, click, persuasion, cpm in _CATALOG]


def propose_plans(product: ProductSpec, audience: AudienceSpec, budget_cents: int,
                  research: TrendReport | None = None) -> list[MediaPlan]:
    catalog = {c["channel"]: c for c in channel_catalog()}
    themes = grounded_findings(research)
    channels = {
        "game": [("twitch", "stream"), ("creators", "demo"), ("communities", "closed_group"),
                 ("tiktok", "short_video"), ("in_game", "rewarded_video")],
        "software": [("search", "search"), ("youtube", "video"), ("newsletter", "email"),
                     ("creators", "demo"), ("reddit", "community")],
        "physical": [("instagram", "reel"), ("creators", "review"), ("search", "search"),
                     ("facebook", "feed"), ("affiliate", "review")],
        "service": [("search", "search"), ("communities", "closed_group"), ("newsletter", "email"),
                    ("facebook", "feed"), ("podcast", "host_read")],
        "other": [("search", "search"), ("creators", "demo"), ("communities", "closed_group"),
                  ("instagram", "feed"), ("youtube", "video")],
    }[product.category]
    result = []
    configurations = [("value", "Accessible discovery", .85, "balanced", channels[:3], 1.5),
                      ("balanced", "Demonstrate the benefit", 1, "selective", channels[1:4], 1.1),
                      ("premium", "Focused premium launch", 1.2, "intensive", channels[2:] + channels[:1], 2.2)]
    for key, name, price_factor, intensity, selected, frequency in configurations:
        placements = []
        for i, (channel, format_name) in enumerate(selected):
            row = catalog[channel]
            basis = "CPA" if channel == "affiliate" else "CPM"
            theme = themes[i % len(themes)] if themes else None
            theme_message = (f" Research theme to address, not a verified product benefit: {theme['text']}"
                             if theme else "")
            placements.append(Placement(
                id=f"{key}-{channel}", channel=channel, format=format_name, charge_basis=basis,
                weight=1.6 if i == 0 else 1, daily_frequency=frequency,
                cpm_cents=row["default_cpm_cents"], cpc_cents=70,
                cpa_cents=max(1, round(product.unit_price_cents * .12)),
                dayparts=[12, 18, 21] if product.category == "game" else [9, 12, 18],
                creative=f"Discover {product.name}: {product.description[:220]}{theme_message}",
            ))
        result.append(MediaPlan(
            id=key, name=name, description=f"{product.category.title()} launch for {audience.region}.",
            price_cents=max(1, round(product.unit_price_cents * price_factor)),
            media_budget_cents=budget_cents, placements=placements, intensity=intensity,
            rationale=[f"Channel selection reflects the {product.category} product category.",
                       "All costs, response rates and price alternatives are editable hypotheses.",
                       "Age-informed preferences use a configurable weak, unvalidated prior with broad individual diversity."] +
                      [f"Research theme ({t['evidence_status']}; sources: {', '.join(t['source_ids'])}): {t['text']}"
                       for t in themes[:3]],
        ))
    return result
