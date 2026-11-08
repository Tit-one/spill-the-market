"""Reconciled financial summaries and conditional simulation uncertainty."""
from __future__ import annotations

import numpy as np


def interval(values: list[float]) -> list[float]:
    return [float(v) for v in np.quantile(values, [.05, .95])]


def mean_interval(values: list[float]) -> list[float] | None:
    if len(values) < 2:
        return None
    mean = float(np.mean(values))
    half = 1.96 * float(np.std(values, ddof=1)) / len(values) ** .5
    return [mean - half, mean + half]


def _optional_interval(values):
    available = [value for value in values if value is not None]
    return interval(available) if available else None


def _summarize_age_segments(replicas):
    summaries = []
    for index, first in enumerate(replicas[0]["age_segments"]):
        rows = [replica["age_segments"][index] for replica in replicas]
        summary = {key: first[key] for key in ("age_min", "age_max", "label")}
        for key in ("population", "units", "organic_units", "revenue_cents"):
            values = [row[key] for row in rows]
            summary[key] = float(np.mean(values))
            summary["revenue_interval_cents" if key == "revenue_cents" else key + "_interval"] = interval(values)
        summary["conversion_rate"] = summary["units"] / summary["population"] if summary["population"] else None
        summary["conversion_rate_interval"] = _optional_interval([row["conversion_rate"] for row in rows])
        population = sum(row["population"] for row in rows)
        summary["mean_intention"] = (sum(row["mean_intention"] * row["population"] for row in rows if row["population"])
                                     / population if population else None)
        summary["mean_intention_interval"] = _optional_interval([row["mean_intention"] for row in rows])
        channels = []
        for channel_index, first_channel in enumerate(first["channels"]):
            channel_rows = [row["channels"][channel_index] for row in rows]
            channel = {"channel": first_channel["channel"]}
            for key in ("unique_reach", "units"):
                values = [row[key] for row in channel_rows]
                channel[key] = float(np.mean(values))
                channel[key + "_interval"] = interval(values)
            channel["conversion_rate"] = channel["units"] / channel["unique_reach"] if channel["unique_reach"] else None
            channel["conversion_rate_interval"] = _optional_interval([row["conversion_rate"] for row in channel_rows])
            channels.append(channel)
        summary["channels"] = channels
        summaries.append(summary)
    return summaries


def _summarize_market_switching(replicas):
    rows = [replica["market_switching"] for replica in replicas]
    summary = {key: rows[0][key] for key in ("enabled", "status", "incumbent_share", "switching_friction", "assumptions")}
    for key in ("population", "buyers", "incumbent_users", "non_incumbent_users", "switchers",
                "new_to_category_buyers", "retained_incumbents", "new_to_category_nonbuyers", "mean_switching_acceptance"):
        values = [row[key] for row in rows]
        summary[key] = float(np.mean(values)) if values[0] is not None else None
        summary[key + "_interval"] = _optional_interval(values)
    return summary


def summarize_scenario(plan, replicas: list[dict], *, is_baseline: bool = False) -> dict:
    revenue = [r["revenue_cents"] for r in replicas]
    daily = []
    for i, day in enumerate(replicas[0]["daily"]):
        daily.append({key: day[key] if key == "day" else float(np.mean([r["daily"][i][key] for r in replicas]))
                      for key in day})
    channel_rows = []
    for i, row in enumerate(replicas[0]["channels"]):
        values = {key: float(np.mean([r["channels"][i][key] for r in replicas]))
                  for key in ["impressions", "unique_reach", "clicks", "units", "revenue_cents", "spend_cents",
                              "exposed_purchase_units", "view_attributed_units", "click_attributed_units",
                              "paid_clicks", "views", "completions", "skips", "comments", "shares",
                              "trend_adoptions", "creator_posts", "earned_impressions",
                              "nonmember_deliveries", "cross_community_deliveries", "skeptical_comments", "positive_comments"]}
        for key in ("pending_liability_cents", "reserved_liability_cents", "released_liability_cents", "settled_liability_cents"):
            values[key] = float(np.mean([r["channels"][i][key] for r in replicas]))
        values.update(channel=row["channel"],
                      attributed_conversion_rate=values["units"] / values["unique_reach"] if values["unique_reach"] else None,
                      conversion_rate_interval=_optional_interval([
                          r["channels"][i]["units"] / r["channels"][i]["unique_reach"]
                          if r["channels"][i]["unique_reach"] else None for r in replicas]),
                      exposed_purchase_rate=values["exposed_purchase_units"] / values["unique_reach"] if values["unique_reach"] else None,
                      cac_cents=values["spend_cents"] / values["units"] if values["units"] else None)
        channel_rows.append(values)
        values["social_edges"] = row["social_edges"]
    mean_spend = float(np.mean([r["spend_cents"] for r in replicas]))
    mean_units = float(np.mean([r["units"] for r in replicas]))
    paid_units = float(np.mean([r["paid_units"] for r in replicas]))
    return {
        "plan_id": plan.id, "name": plan.name, "is_baseline": is_baseline,
        "price_cents": plan.price_cents, "mean_revenue_cents": float(np.mean(revenue)),
        "median_revenue_cents": float(np.median(revenue)), "revenue_interval_cents": interval(revenue),
        "mean_units": mean_units, "mean_unique_buyers": mean_units, "mean_spend_cents": mean_spend,
        "product_credibility": replicas[0]["product_credibility"],
        "mean_scam_suspicion": float(np.mean([r["mean_scam_suspicion"] for r in replicas])),
        "mean_credibility_acceptance": float(np.mean([r["mean_credibility_acceptance"] for r in replicas])),
        "skeptical_comments": float(np.mean([r["skeptical_comments"] for r in replicas])),
        "positive_comments": float(np.mean([r["positive_comments"] for r in replicas])),
        "age_segments": _summarize_age_segments(replicas),
        "market_switching": _summarize_market_switching(replicas),
        "mean_cac_cents": mean_spend / mean_units if mean_units else None,
        "mean_paid_cac_cents": mean_spend / paid_units if paid_units else None,
        "mean_paid_units": paid_units,
        "mean_organic_units": float(np.mean([r["organic_units"] for r in replicas])),
        "mean_commission_cents": float(np.mean([r["commission_cents"] for r in replicas])),
        "mean_pending_liability_cents": float(np.mean([r["pending_liability_cents"] for r in replicas])),
        "mean_contribution_cents": float(np.mean([r["contribution_cents"] for r in replicas])),
        "mean_committed_contribution_cents": float(np.mean([r["contribution_cents"] - r["pending_liability_cents"]
                                                          for r in replicas])),
        "daily": daily, "channels": channel_rows, "traces": replicas[0]["traces"],
        "adjustments": replicas[0]["adjustments"],
        "trace_seed": replicas[0]["seed"], "trace_scope": "Bounded sample from the first validation replica; not all buyers.",
        "replicate_totals": [{k: r[k] for k in ["seed", "units", "unique_buyers", "revenue_cents",
                              "spend_cents", "commission_cents", "paid_units", "organic_units", "contribution_cents",
                              "pending_liability_cents", "reserved_liability_cents", "released_liability_cents", "settled_liability_cents"]}
                             for r in replicas],
    }


def paired_comparison(candidate: dict, baseline: dict) -> dict:
    pairs = list(zip(candidate["replicate_totals"], baseline["replicate_totals"], strict=True))
    if any(a["seed"] != b["seed"] for a, b in pairs):
        raise ValueError("Comparisons require paired random seeds")
    profits = [a["contribution_cents"] - b["contribution_cents"] for a, b in pairs]
    units = [a["units"] - b["units"] for a, b in pairs]
    return {
        "plan_id": candidate["plan_id"], "baseline_id": baseline["plan_id"],
        "price_cents": candidate["price_cents"], "paired_seeds": [a["seed"] for a, _ in pairs],
        "mean_incremental_units": float(np.mean(units)),
        "mean_incremental_contribution_cents": float(np.mean(profits)),
        "incremental_contribution_interval_cents": interval(profits),
        "incremental_mean_95pct_interval_cents": mean_interval(profits),
        "incremental_cac_cents": candidate["mean_spend_cents"] / float(np.mean(units)) if np.mean(units) > 0 else None,
        "uncertainty": "Conditional simulation variability, not a real-world forecast or causal measurement; normal mean interval is approximate.",
    }


def paired_revenue_comparison(candidate: dict, alternative: dict, practical_fraction: float = .01) -> dict:
    """Primary maximum-CA objective, with paired variation and a 1% practical margin."""
    pairs = list(zip(candidate["replicate_totals"], alternative["replicate_totals"], strict=True))
    if any(a["seed"] != b["seed"] for a, b in pairs):
        raise ValueError("Revenue comparisons require paired random seeds")
    deltas = [a["revenue_cents"] - b["revenue_cents"] for a, b in pairs]
    ci = mean_interval(deltas)
    threshold = practical_fraction * alternative["mean_revenue_cents"]
    return {"plan_id": candidate["plan_id"], "alternative_id": alternative["plan_id"],
            "paired_seeds": [a["seed"] for a, _ in pairs],
            "mean_revenue_difference_cents": float(np.mean(deltas)),
            "revenue_difference_interval_cents": interval(deltas),
            "revenue_difference_mean_95pct_interval_cents": ci,
            "practical_threshold_fraction": practical_fraction,
            "practical_threshold_cents": threshold,
            "supported_practical_superiority": ci is not None and ci[0] > threshold,
            "uncertainty": "Paired conditional simulation uncertainty; approximate mean interval, no real-market validation."}
