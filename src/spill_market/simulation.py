"""Local vectorized, unweighted, individual-based launch experiments.

Every response coefficient is an explicit modelling assumption. No inference,
network, real ad delivery or external purchase is performed by this module.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Callable

import numpy as np

from .media import channel_catalog
from .models import AudienceSpec, MediaPlan, ProductSpec, StudySpec, TrendReport
from .personas import AGE_CHANNEL_PRIORS, CHANNELS, generate_personas, initialize_population
from .reports import paired_comparison, paired_revenue_comparison, summarize_scenario

ENGINE_VERSION = "0.1.0-numeric-9"
MAX_TRACE_PERSONS = 20
MAX_CACHE_REPLICAS = 600
MUTABLE_FIELDS = ("budget_cents", "purchased", "intention", "awareness", "fatigue", "last_channel",
                  "last_exposure_day", "last_click_hour", "last_view_channel", "last_view_hour",
                  "earned_pending", "trend_adopted", "cpa_reserved_until")

ASSUMPTIONS = [
    "All people, purchasing power, needs, platform availability, costs and response coefficients are synthetic hypotheses, not observed demographics or platform estimates.",
    "One numerical individual can make at most one purchase of one unit per scenario. Purchasing power is price-independent; stock is shared across individuals.",
    "Age is sampled strictly within the submitted adult range. A configurable weak, unvalidated age prior shifts channel preferences and social sensitivity while preserving broad individual diversity; weight zero is neutral. Budget, need, trust and price sensitivity remain age-independent. Suggested ages require separate user confirmation.",
    "Grounded research findings enrich fictional persona beliefs and proposed creative themes with source ids and evidence status. A synthetic persona reaction is never an observed psychological fact; research does not silently calibrate numeric response rates or claim market performance.",
    "Optional declared channel multipliers (0.8–1.2) are shared across all strategies and change persuasion only. Any LLM inferred response hypothesis remains unvalidated; an LLM never directly creates a sale or replaces the numeric purchase gate. Empty multipliers preserve default numeric behavior.",
    "Local dayparts share the audience timezone; individual activity peaks are synthetic. Events execute by earliest configured hour and placement id.",
    "Attention is shared across placements; recency, repeated exposure and fatigue affect intention. Closed groups require synthetic membership; short-video continuation and in-game formats use distinct execution rules.",
    "CPM is rounded up to whole cents per placement/day. CPC charges delivered clicks; CPA charges attributed first purchases; FIXED charges one daily fee when delivered; ORGANIC has zero cash charge.",
    "CPA uses a conservative inventory assumption: reserve one potential fee per qualified individual before any CPA view, including earned views. A view hold lasts 24h and extends to seven days when clicked; overridden, expired and purchased holds are released or settled. Spend plus pending liability never exceeds the campaign cap. Customer purchasing decisions depend only on demand, means, prerequisites and stock, never on remaining media cash.",
    "Weight controls placement delivery and daily budget allocation. Unspent daily allowances carry forward. Distribution changes response; charge_basis determines cash cost.",
    "Attribution prioritizes the last clicked placement within seven days, then falls back to the last viewed placement within 24 hours. Configured latest placement hour timestamps exposure; purchases are decided at 23h. Attributed conversions are not causal incremental sales. Unattributed need-driven purchases are reported separately.",
    "Attributed conversion rate is attributed unique buyers divided by unique exposed people, per channel. Exposed purchase rate includes all buyers in that reached cohort regardless of attribution.",
    "Short-video spectators can complete, skip, comment, share and adopt a trend; a synthetic 12% creator subset can post. Shares and posts deliver at most two earned impressions per recipient/placement on the next day through sparse hashed contacts. These consume shared attention and affect intention without creating weighted buyers. Closed-group contacts stay inside one of 32 synthetic member communities. This is an unvalidated coarse social-network model, not a replica of any platform.",
    "Exposed purchase rate counts all eventual buyers previously reached by a channel, regardless of attribution; exposed buyers overlap across channels and must not be summed.",
    "CAC is spend divided by all buyers; paid CAC is spend divided by buyers attributed to non-ORGANIC placements. Undefined ratios are null. Affiliate CPA charges are included in spend and separately identified as commissions.",
    "Contribution equals virtual revenue minus variable product cost minus media spend. No tax, refunds, repeat purchases, fulfilment timing or real cash flow is modelled.",
    "Unsettled CPA inventory at the scenario horizon is a disclosed potential liability, not a completed expense. Contribution excludes that hold; committed contribution additionally subtracts pending liability as a conservative diagnostic.",
    "Exploration tunes only unlocked starting placement frequencies. Learned starting parameters, locked lines and the deterministic adaptive policy are frozen before disjoint validation seeds; the same daily controller remains active if requested. Validation never tunes the policy after observing results. All candidates share paired seeds and price-matched no-campaign controls.",
    "The primary objective is maximum total virtual revenue (CA), selected on exploration means across the three strategies. Contribution and price-matched no-campaign increments are separate diagnostics. A winner needs paired validation revenue superiority beyond a 1% practical margin against both alternatives; unavailable or overlapping intervals are indecisive.",
    "Intervals describe stochastic variability conditional on the submitted model, not real-world confidence or individual predictions.",
    "Displayed trajectories are validation means; bounded traces show the first validation replica and cannot represent every buyer. Numerical acquisition and attribution totals reconcile exactly within each replica.",
]


class SimulationCancelled(Exception):
    """Cancellation is checked between committed days and between replicas."""


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _stream(seed: int, ids: np.ndarray, day: int, mechanism: str) -> np.ndarray:
    """Counter randoms keyed by agent/day/mechanism; consumption order cannot shift streams."""
    salt = int.from_bytes(hashlib.blake2b(mechanism.encode(), digest_size=8).digest(), "little")
    with np.errstate(over="ignore"):
        x = ids.astype(np.uint64) + np.uint64(seed) * np.uint64(0x9E3779B97F4A7C15)
        x = x ^ np.uint64((day * 0xD1B54A32D192ED03 + salt) & ((1 << 64) - 1))
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        x = x ^ (x >> np.uint64(31))
    return (x >> np.uint64(11)).astype(np.float64) * (1.0 / (1 << 53))


def buy_product(state: dict, candidates: np.ndarray, price_cents: int,
                stock_remaining: int | None = None) -> np.ndarray:
    """The sole purchase gate: deduplicate, enforce means/stock, debit one unit."""
    candidates = np.asarray(candidates, dtype=np.int64)
    if not len(candidates) or stock_remaining == 0:
        return np.empty(0, dtype=np.int64)
    # Keep incoming (deterministically randomized) priority while removing duplicates.
    _, first = np.unique(candidates, return_index=True)
    eligible = candidates[np.sort(first)]
    eligible = eligible[(~state["purchased"][eligible]) & (state["budget_cents"][eligible] >= price_cents)]
    if "prerequisite_fit" in state:
        eligible = eligible[state["prerequisite_fit"][eligible]]
    if stock_remaining is not None:
        eligible = eligible[:max(0, stock_remaining)]
    state["purchased"][eligible] = True
    state["budget_cents"][eligible] -= price_cents
    return eligible


def _limit_counts(counts: np.ndarray, limit: int, priority: np.ndarray) -> np.ndarray:
    if int(counts.sum()) <= limit:
        return counts
    order = np.argsort(priority, kind="stable")
    ordered = counts[order]
    before = np.cumsum(ordered) - ordered
    result = np.zeros_like(counts)
    result[order] = np.minimum(ordered, np.maximum(0, limit - before))
    return result


def _queue_social(state: dict, placement_index: int, senders: np.ndarray, *, seed: int,
                  day: int, key: str, members: np.ndarray | None = None, contacts: int = 1) -> list[dict]:
    """Sparse deterministic contacts, with no dense adjacency matrix or weighted users."""
    if not len(senders):
        return []
    n = len(state["id"])
    targets, edges = [], []
    for contact in range(contacts):
        draws = _stream(seed, senders, day, f"{key}:contact:{contact}")
        if members is None:
            recipients = np.floor(draws * n).astype(np.int64)
            allowed = recipients != senders
        else:
            community = senders % 32
            size = (n - 1 - community) // 32 + 1
            recipients = community + np.floor(draws * size).astype(np.int64) * 32
            allowed = (recipients != senders) & members[recipients] & members[senders]
        targets.extend(recipients[allowed].tolist())
        for sender, recipient in zip(senders[allowed][:8], recipients[allowed][:8], strict=True):
            edges.append({"source": int(sender), "target": int(recipient), "day": day,
                          "delivery_day": day + 1, "community": int(sender % 32) if members is not None else None,
                          "status": "synthetic_hashed_contact"})
    additions = np.bincount(targets, minlength=n)
    state["earned_pending"][placement_index] = np.minimum(2, state["earned_pending"][placement_index] + additions)
    return edges


def _atomic_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def _save_checkpoint(path: Path, fingerprint: str, state: dict, reached: np.ndarray, metadata: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, **{key: state[key] for key in MUTABLE_FIELDS}, _reached=reached,
                            _metadata=np.array(json.dumps({"fingerprint": fingerprint, **metadata})))
    os.replace(temporary, path)


def _response(placement, catalog: dict, state: dict, price_acceptance: np.ndarray):
    availability, click, persuasion = catalog["availability"], catalog["click_rate"], catalog["persuasion"]
    mechanism = catalog["mechanism"]
    fmt = placement.format.lower()
    if mechanism == "short_video" or fmt in {"short", "short_video", "reel", "story"}:
        # Continuation/skip is separately drawn below; repeat short videos saturate quickly.
        availability *= 1.15
        persuasion *= .8
    if mechanism == "closed_group" or fmt in {"closed_group", "group"}:
        availability *= .7
        persuasion = persuasion * (1.1 + state["social_sensitivity"] * .6)
    if mechanism == "in_game":
        if fmt == "rewarded_video":
            availability *= .8
            click *= 1.3
            persuasion *= 1.25
        elif fmt == "interstitial":
            availability *= 1.1
            click *= .7
            persuasion *= .6
        else:  # banners / unknown formats have less attention and persuasion
            availability *= 1.35
            click *= .35
            persuasion *= .25
    if mechanism == "intent_search":
        availability = availability * (.2 + state["need_fit"])
        click = click * (.5 + price_acceptance)
    if mechanism in {"permission_email", "audio", "live_stream"}:
        persuasion *= 1.12
    if fmt not in catalog["formats"]:
        persuasion *= .85
    if placement.distribution == "organic":
        persuasion *= 1.1
        availability *= .7
    elif placement.distribution == "partnership":
        persuasion *= 1.18
    return availability, click, persuasion


def simulate_scenario(product: ProductSpec, audience: AudienceSpec, plan: MediaPlan, days: int, seed: int, *,
                      research: TrendReport | None = None, fatigue_multiplier: float = 1.0,
                      price_elasticity: float = 1.0, on_day: Callable | None = None,
                      checkpoint_path=None, cancel_check: Callable | None = None,
                      response_multipliers: dict | None = None, social_sharing_enabled: bool = True) -> dict:
    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")
    if fatigue_multiplier < 0 or price_elasticity <= 0:
        raise ValueError("Invalid fatigue or price elasticity")
    multipliers = dict(response_multipliers or {})
    if any(channel not in CHANNELS or not isinstance(value, (int, float)) or
           not math.isfinite(value) or not .8 <= value <= 1.2 for channel, value in multipliers.items()):
        raise ValueError("response_multipliers require known channels and finite values from 0.8 to 1.2")
    fingerprint = _digest({"engine": ENGINE_VERSION, "product": product.model_dump(),
                           "audience": audience.model_dump(), "plan": plan.model_dump(), "days": days,
                           "seed": seed, "fatigue": fatigue_multiplier, "elasticity": price_elasticity,
                           "response_multipliers": multipliers, "social_sharing_enabled": social_sharing_enabled})
    checkpoint = Path(checkpoint_path) if checkpoint_path is not None else None
    placements = sorted(plan.placements, key=lambda p: (min(p.dayparts), p.id))
    if len({p.id for p in placements}) != len(placements):
        raise ValueError("Placement ids must be unique within a plan")
    catalog = {c["channel"]: c for c in channel_catalog()}
    n = audience.population
    state = initialize_population(product, audience, seed)
    state["earned_pending"] = np.zeros((len(placements), n), dtype=np.uint8)
    state["trend_adopted"] = np.zeros((len(CHANNELS), n), dtype=bool)
    state["cpa_reserved_until"] = np.full((len(placements), n), -1000, dtype=np.int16)
    cpa_indices = [j for j, p in enumerate(placements) if p.charge_basis == "CPA"]
    reached = np.zeros((len(CHANNELS), n), dtype=bool)
    frequencies = [p.daily_frequency for p in placements]
    channel_totals = {c: {"channel": c, "impressions": 0, "clicks": 0, "paid_clicks": 0, "units": 0,
                          "revenue_cents": 0, "spend_cents": 0, "view_attributed_units": 0,
                          "click_attributed_units": 0, "views": 0, "completions": 0, "skips": 0,
                          "comments": 0, "shares": 0, "trend_adoptions": 0, "creator_posts": 0,
                          "earned_impressions": 0, "nonmember_deliveries": 0,
                          "cross_community_deliveries": 0, "social_edges": [],
                          "reserved_liability_cents": 0, "released_liability_cents": 0,
                          "settled_liability_cents": 0}
                      for c in dict.fromkeys(p.channel for p in placements)}
    history, traces, adjustments = [], [], []
    totals = {"units": 0, "revenue_cents": 0, "spend_cents": 0, "organic_units": 0,
              "paid_units": 0, "commission_cents": 0, "pending_liability_cents": 0,
              "reserved_liability_cents": 0, "released_liability_cents": 0, "settled_liability_cents": 0}
    first_day = 1
    if checkpoint and checkpoint.exists():
        with np.load(checkpoint, allow_pickle=False) as data:
            saved = json.loads(str(data["_metadata"]))
            if saved["fingerprint"] != fingerprint:
                raise ValueError("The checkpoint belongs to a different scenario or engine version")
            state.update({key: data[key].copy() for key in MUTABLE_FIELDS})
            reached = data["_reached"].copy()
        history, traces, adjustments = saved["history"], saved["traces"], saved["adjustments"]
        totals, frequencies, channel_totals = saved["totals"], saved["frequencies"], saved["channel_totals"]
        first_day = saved["day"] + 1
    ids = state["id"]
    # Original means are not depleted for price aversion; affordability is gated at purchase.
    initial_budget = state["budget_cents"] + state["purchased"].astype(np.int64) * plan.price_cents
    price_acceptance = np.exp(-price_elasticity * state["price_sensitivity"] *
                              plan.price_cents / np.maximum(initial_budget, 1))
    trace_ids = np.linspace(0, n - 1, min(MAX_TRACE_PERSONS, n), dtype=int)
    product_tokens = set((product.name + " " + product.description + " " + " ".join(product.keywords)).lower().split())

    def release_holds(j, mask):
        amount = int(np.count_nonzero(mask)) * placements[j].cpa_cents
        if amount:
            state["cpa_reserved_until"][j, mask] = -1000
            totals["pending_liability_cents"] -= amount
            totals["released_liability_cents"] += amount
            channel_totals[placements[j].channel]["released_liability_cents"] += amount

    def free_media_cash():
        return plan.media_budget_cents - totals["spend_cents"] - totals["pending_liability_cents"]

    for day in range(first_day, days + 1):
        if cancel_check and cancel_check():
            raise SimulationCancelled("Simulation cancelled after the last committed day")
        before_units, before_spend = totals["units"], totals["spend_cents"]
        before_liabilities = {key: totals[key] for key in
                              ("reserved_liability_cents", "released_liability_cents", "settled_liability_cents")}
        for j in cpa_indices:
            holds = state["cpa_reserved_until"][j]
            release_holds(j, (holds >= 0) & (holds < (day - 1) * 24))
        state["fatigue"] *= .68
        state["intention"] *= .86
        state["awareness"] *= .96
        attention = (1 + np.floor(_stream(seed, ids, day, "global-attention") * 6)).astype(np.int16)
        observed = np.zeros(n, dtype=np.int16)
        clicked_today = np.zeros(n, dtype=bool)
        questions = np.zeros(n, dtype=bool)
        commented_today = np.zeros(n, dtype=bool)
        shared_today = np.zeros(n, dtype=bool)
        pending_today = state["earned_pending"].copy()
        state["earned_pending"].fill(0)
        social_daily = {"earned_impressions": 0, "comments": 0, "shares": 0, "creator_posts": 0,
                        "trend_adoptions": 0}
        spend_by_placement = [0] * len(placements)
        impressions_by_placement = [0] * len(placements)
        day_budget = free_media_cash() // (days - day + 1)
        active_weight = sum(p.weight for p in placements if p.weight > 0 and p.charge_basis != "ORGANIC")
        placement_caps = [math.floor(day_budget * p.weight / active_weight) if active_weight and p.charge_basis != "ORGANIC"
                          else 0 for p in placements]
        for j, placement in enumerate(placements):
            if placement.weight <= 0 or frequencies[j] <= 0:
                continue
            basis = placement.charge_basis
            event_hour = (day - 1) * 24 + max(placement.dayparts)
            if basis == "CPA":
                holds = state["cpa_reserved_until"][j]
                release_holds(j, (holds >= 0) & (holds < event_hour))
            cap = min(placement_caps[j], free_media_cash())
            paid_delivery_allowed = not (basis != "ORGANIC" and (cap <= 0 or
               (basis == "FIXED" and placement.fee_cents > cap) or
               (basis == "CPC" and placement.cpc_cents > cap))) or basis == "CPA"
            cidx = CHANNELS.index(placement.channel)
            model = catalog[placement.channel]
            key = f"{placement.channel}:{placement.format}"
            availability, click_rate, persuasion = _response(placement, model, state, price_acceptance)
            persuasion = persuasion * multipliers.get(placement.channel, 1.0)
            # Product relevance is category-specific, never inferred from a person's age.
            relevant = ((product.category == "game" and placement.channel in {"twitch", "in_game", "tiktok"}) or
                        (product.category == "software" and placement.channel in {"search", "youtube", "reddit"}))
            relevance = 1.15 if relevant else 1.0
            hour_distance = np.min(np.abs(((state["peak_hour"][:, None] - np.array(placement.dayparts) + 12) % 24) - 12), axis=1)
            time_fit = .10 + .90 * np.exp(-hour_distance ** 2 / 18)
            affinity = state["channel_affinity"][:, cidx]
            probability = np.minimum(.95, availability * affinity * time_fit * relevance)
            mechanism = model["mechanism"]
            is_group = mechanism == "closed_group" or placement.format in {"group", "closed_group"}
            is_short = mechanism == "short_video" or placement.format in {"short", "short_video", "reel", "story"}
            members = _stream(seed, ids, 0, key + ":membership") < .65 if is_group else None
            if is_group:
                probability *= members
            desired = np.minimum(12, frequencies[j] * placement.weight * probability)
            paid_counts = np.floor(desired).astype(np.int16)
            paid_counts += (_stream(seed, ids, day, key + ":exposure") < desired - paid_counts).astype(np.int16)
            if not paid_delivery_allowed:
                paid_counts.fill(0)
            earned_counts = np.minimum(pending_today[j], attention).astype(np.int16)
            earned_counts[state["purchased"]] = 0
            if is_group:
                earned_counts[~members] = 0
            paid_counts = np.minimum(paid_counts, attention - earned_counts)
            paid_counts[state["purchased"]] = 0
            if basis == "CPM":
                paid_counts = _limit_counts(paid_counts, cap * 1000 // placement.cpm_cents,
                                       _stream(seed, ids, day, key + ":delivery-priority"))
            counts = paid_counts + earned_counts
            if basis == "CPA":
                qualified = ((~state["purchased"]) & state["prerequisite_fit"] &
                             (state["budget_cents"] >= plan.price_cents))
                holds = state["cpa_reserved_until"][j]
                funded = (holds >= event_hour) & qualified
                new_people = np.flatnonzero((counts > 0) & qualified & ~funded)
                capacity = max(0, min(cap, free_media_cash()) // placement.cpa_cents)
                priority = _stream(seed, new_people, day, key + ":CPA-inventory-priority")
                reserved = new_people[np.argsort(priority, kind="stable")[:capacity]]
                amount = len(reserved) * placement.cpa_cents
                if amount:
                    funded[reserved] = True
                    totals["pending_liability_cents"] += amount
                    totals["reserved_liability_cents"] += amount
                    channel_totals[placement.channel]["reserved_liability_cents"] += amount
                paid_counts[~funded] = 0
                earned_counts[~funded] = 0
                counts = paid_counts + earned_counts
                exposed = counts > 0
                holds[exposed] = np.maximum(holds[exposed], event_hour + 24)
            count = int(counts.sum())
            if not count:
                continue
            eligible = counts > 0
            attention -= counts
            observed += counts
            reached[cidx] |= eligible
            effective = counts.astype(float)
            completions = np.zeros(n, dtype=np.int16)
            if is_short:
                # Skipping still consumes an impression and shared attention.
                expected = counts * (.25 + .55 * state["need_fit"])
                completions = np.minimum(counts, np.floor(expected).astype(np.int16) +
                    (_stream(seed, ids, day, key + ":continuation") < expected % 1).astype(np.int16))
                effective = completions + .15 * (counts - completions)
            if placement.channel == "in_game" and placement.format == "interstitial":
                state["fatigue"] += counts * .09 * fatigue_multiplier
            fatigue_penalty = np.exp(-state["fatigue"] * (1.3 - state["fatigue_tolerance"]))
            creative_tokens = set(placement.creative.lower().split())
            message_fit = .75 + .25 * min(1, len(product_tokens & creative_tokens) / max(1, min(8, len(product_tokens))))
            interest = effective * persuasion * message_fit * (.25 + .75 * state["need_fit"]) * fatigue_penalty
            state["awareness"] = np.minimum(1, state["awareness"] + effective * .08)
            state["intention"] = np.clip(state["intention"] + interest * state["trust"] * price_acceptance, 0, 1)
            clicks = eligible & (_stream(seed, ids, day, key + ":click") < np.minimum(.95, click_rate * effective * (.4 + state["need_fit"])))
            paid_clicks = clicks & (_stream(seed, ids, day, key + ":paid-click") <
                                   paid_counts / np.maximum(counts, 1))
            if basis == "ORGANIC":
                paid_clicks.fill(False)
            if basis == "CPC":
                accepted_paid_clicks = _limit_counts(paid_clicks.astype(np.int16), cap // placement.cpc_cents,
                                       _stream(seed, ids, day, key + ":click-priority")).astype(bool)
                clicks &= ~paid_clicks | accepted_paid_clicks
                paid_clicks = accepted_paid_clicks
            clicked_today |= clicks
            questions |= eligible & (_stream(seed, ids, day, key + ":question") < .08 + state["need_fit"] * .15)
            latest_click = clicks & (event_hour >= state["last_click_hour"])
            latest_view = eligible & (event_hour >= state["last_view_hour"])
            state["last_channel"][latest_click] = j
            state["last_exposure_day"][latest_click] = day
            state["last_click_hour"][latest_click] = event_hour
            state["last_view_channel"][latest_view] = j
            state["last_view_hour"][latest_view] = event_hour
            if basis == "CPA":
                holds = state["cpa_reserved_until"][j]
                holds[clicks] = np.maximum(holds[clicks], event_hour + 7 * 24)
            state["fatigue"] += counts * .07 * (1.25 - state["fatigue_tolerance"]) * fatigue_multiplier
            spend = (math.ceil(int(paid_counts.sum()) * placement.cpm_cents / 1000) if basis == "CPM" else
                     int(paid_clicks.sum()) * placement.cpc_cents if basis == "CPC" else
                     placement.fee_cents if basis == "FIXED" and np.any(paid_counts) else 0)
            totals["spend_cents"] += spend
            spend_by_placement[j] += spend
            impressions_by_placement[j] = count
            row = channel_totals[placement.channel]
            row["impressions"] += count
            row["clicks"] += int(clicks.sum())
            row["paid_clicks"] += int(paid_clicks.sum())
            row["spend_cents"] += spend
            row["views"] += count
            row["completions"] += int(completions.sum())
            row["skips"] += count - int(completions.sum()) if is_short else 0
            earned = int(earned_counts.sum())
            row["earned_impressions"] += earned
            social_daily["earned_impressions"] += earned
            if is_group:
                row["nonmember_deliveries"] += int(counts[~members].sum())
            if is_short or is_group:
                engaged = completions > 0 if is_short else eligible
                social = state["social_sensitivity"]
                comments = engaged & (_stream(seed, ids, day, key + ":comment") < (.12 + .20 * state["need_fit"]) * social)
                shares = engaged & (_stream(seed, ids, day, key + ":share") < (.05 + .12 * state["need_fit"]) * social)
                posts = (engaged & state["creator_role"] &
                         (_stream(seed, ids, day, key + ":creator-post") < .15 + .25 * state["need_fit"])) if is_short else np.zeros(n, dtype=bool)
                adopted = (engaged & ~state["trend_adopted"][cidx] &
                           (_stream(seed, ids, day, key + ":trend") < (.03 + .08 * state["need_fit"]) * social)) if is_short else np.zeros(n, dtype=bool)
                state["trend_adopted"][cidx] |= adopted
                commented_today |= comments
                shared_today |= shares
                state["intention"] = np.minimum(1, state["intention"] +
                                                (.015 * comments + .025 * adopted) * price_acceptance)
                for metric, values in (("comments", comments), ("shares", shares), ("creator_posts", posts),
                                       ("trend_adoptions", adopted)):
                    amount = int(values.sum())
                    row[metric] += amount
                    social_daily[metric] += amount
                if social_sharing_enabled:
                    edges = _queue_social(state, j, np.flatnonzero(shares), seed=seed, day=day, key=key + ":share",
                                          members=members)
                    edges += _queue_social(state, j, np.flatnonzero(posts), seed=seed, day=day, key=key + ":post",
                                           members=members, contacts=2)
                    row["social_edges"].extend(edges[:max(0, 64 - len(row["social_edges"]))])
        # Need-driven discovery exists without any campaign and is paired across scenarios.
        organic_interest = .014 * state["need_fit"] * state["trust"] * price_acceptance
        state["intention"] = np.minimum(1, state["intention"] + organic_interest)
        purchase_probability = (.0015 * state["need_fit"] * state["trust"] * price_acceptance +
                                .12 * state["intention"] ** 1.7 * state["need_fit"] * price_acceptance)
        purchase_probability *= np.exp(-state["fatigue"] * .45)
        candidates = np.flatnonzero((~state["purchased"]) & (_stream(seed, ids, day, "purchase") < purchase_probability))
        priority = _stream(seed, candidates, day, "purchase-priority")
        candidates = candidates[np.argsort(priority, kind="stable")]
        decision_hour = (day - 1) * 24 + 23
        recent_click = (state["last_channel"] >= 0) & (decision_hour - state["last_click_hour"] <= 7 * 24)
        recent_view = (state["last_view_channel"] >= 0) & (decision_hour - state["last_view_hour"] <= 24)
        attribution = np.where(recent_click, state["last_channel"], np.where(recent_view, state["last_view_channel"], -1))
        # Retain every still-valid potential click/view touch: a view can become
        # the fallback after an older competing click expires tomorrow.
        for j in cpa_indices:
            holds = state["cpa_reserved_until"][j]
            potential_click = recent_click & (state["last_channel"] == j)
            potential_view = recent_view & (state["last_view_channel"] == j)
            potential = (potential_click | potential_view) & ~state["purchased"]
            release_holds(j, (holds >= 0) & ((holds < decision_hour) | ~potential))
            active = (attribution == j) & ~state["purchased"]
            if np.any(active & (holds < decision_hour)):
                raise AssertionError("CPA attribution has no funded inventory reservation")
            holds[potential] = np.maximum(
                np.where(potential_click[potential], state["last_click_hour"][potential] + 7 * 24, -1000),
                np.where(potential_view[potential], state["last_view_hour"][potential] + 24, -1000))
        stock_remaining = None if product.stock is None else product.stock - totals["units"]
        buyers = buy_product(state, candidates, plan.price_cents, stock_remaining)
        for j in cpa_indices:
            holds = state["cpa_reserved_until"][j]
            release_holds(j, (holds >= 0) & state["purchased"] & (attribution != j))
        for j, placement in enumerate(placements):
            bought = int(np.count_nonzero(attribution[buyers] == j))
            if not bought:
                continue
            row = channel_totals[placement.channel]
            row["units"] += bought
            row["click_attributed_units"] += int(np.count_nonzero((attribution[buyers] == j) & recent_click[buyers]))
            row["view_attributed_units"] += int(np.count_nonzero((attribution[buyers] == j) & ~recent_click[buyers]))
            row["revenue_cents"] += bought * plan.price_cents
            if placement.charge_basis != "ORGANIC":
                totals["paid_units"] += bought
            if placement.charge_basis == "CPA":
                spend = bought * placement.cpa_cents
                matched_buyers = buyers[attribution[buyers] == j]
                state["cpa_reserved_until"][j, matched_buyers] = -1000
                totals["pending_liability_cents"] -= spend
                totals["settled_liability_cents"] += spend
                row["settled_liability_cents"] += spend
                totals["spend_cents"] += spend
                spend_by_placement[j] += spend
                row["spend_cents"] += spend
                if placement.channel == "affiliate":
                    totals["commission_cents"] += spend
        totals["organic_units"] += int(np.count_nonzero(attribution[buyers] < 0))
        totals["units"] += len(buyers)
        totals["revenue_cents"] += len(buyers) * plan.price_cents
        daily = {"day": day, "units": totals["units"] - before_units,
                 "revenue_cents": (totals["units"] - before_units) * plan.price_cents,
                 "spend_cents": totals["spend_cents"] - before_spend,
                 "cumulative_units": totals["units"], "cumulative_revenue_cents": totals["revenue_cents"],
                 "cumulative_spend_cents": totals["spend_cents"],
                 "mean_intention": float(state["intention"].mean()), "mean_fatigue": float(state["fatigue"].mean()),
                 "pending_liability_cents": totals["pending_liability_cents"],
                 "available_media_cents": free_media_cash(),
                 **{key: totals[key] - before_liabilities[key] for key in before_liabilities},
                 **social_daily}
        history.append(daily)
        bought_set = set(buyers.tolist())
        for i in trace_ids:
            j = int(attribution[i])
            traces.append({"persona_id": f"persona-{i:06d}", "day": day, "exposures": int(observed[i]),
                           "attention_remaining": int(attention[i]), "aware": bool(state["awareness"][i] > 0),
                           "interest": float(state["awareness"][i] * state["need_fit"][i]),
                           "question": bool(questions[i]), "clicked": bool(clicked_today[i]),
                           "intention": float(state["intention"][i]), "fatigue": float(state["fatigue"][i]),
                           "purchased_today": int(i) in bought_set, "has_purchased": bool(state["purchased"][i]),
                           "budget_remaining_cents": int(state["budget_cents"][i]),
                           "attributed_channel": placements[j].channel if j >= 0 else None,
                           "attribution_rule": "last_click_7d" if recent_click[i] else "last_view_24h" if recent_view[i] else "organic",
                           "shared": bool(shared_today[i]),
                           "creator_role": bool(state["creator_role"][i]),
                           "synthetic_comment": f"Synthetic comment: how does {product.name} fit my needs?" if commented_today[i] else None,
                           "status": "simulated"})
        if plan.adaptive and day < days:
            for j, placement in enumerate(placements):
                if placement.locked or placement.weight <= 0 or not frequencies[j]:
                    continue
                # Synthetic aggregate feedback changes delivery, never any submitted locked parameter.
                exposed = reached[CHANNELS.index(placement.channel)] & ~state["purchased"]
                fatigue = float(state["fatigue"][exposed].mean()) if np.any(exposed) else 0
                factor = .86 if fatigue > .22 else 1.035 if impressions_by_placement[j] else 1
                changed = min(12, max(.05, frequencies[j] * factor))
                if abs(changed - frequencies[j]) > 1e-12:
                    adjustments.append({"day": day, "placement_id": placement.id,
                                        "parameter": "daily_frequency", "before": frequencies[j], "after": changed,
                                        "reason": "reduce repeated-exposure fatigue" if factor < 1 else "bounded attention feedback"})
                    frequencies[j] = changed
        if checkpoint:
            _save_checkpoint(checkpoint, fingerprint, state, reached,
                             {"day": day, "history": history, "traces": traces, "adjustments": adjustments,
                              "totals": totals, "frequencies": frequencies, "channel_totals": channel_totals})
        if on_day:
            on_day(daily.copy())
    rows = []
    for channel, row in channel_totals.items():
        reach = int(reached[CHANNELS.index(channel)].sum())
        exposed_buyers = int(np.count_nonzero(reached[CHANNELS.index(channel)] & state["purchased"]))
        pending_channel = sum(int(np.count_nonzero(state["cpa_reserved_until"][j] >= 0)) * placements[j].cpa_cents
                              for j in cpa_indices if placements[j].channel == channel)
        rows.append({**row, "unique_reach": reach, "exposed_purchase_units": exposed_buyers,
                     "pending_liability_cents": pending_channel,
                     "attributed_conversion_rate": row["units"] / reach if reach else None,
                     "exposed_purchase_rate": exposed_buyers / reach if reach else None,
                     "cac_cents": row["spend_cents"] / row["units"] if row["units"] else None})
    assert totals["spend_cents"] + totals["pending_liability_cents"] <= plan.media_budget_cents
    assert totals["reserved_liability_cents"] - totals["released_liability_cents"] - totals["settled_liability_cents"] == totals["pending_liability_cents"]
    assert totals["units"] == sum(r["units"] for r in rows) + totals["organic_units"]
    return {"engine_version": ENGINE_VERSION, "plan_id": plan.id, "seed": seed,
            "price_cents": plan.price_cents, "population": n, "state_count": n, **totals,
            "unique_buyers": totals["units"],
            "contribution_cents": totals["revenue_cents"] - product.variable_cost_cents * totals["units"] - totals["spend_cents"],
            "committed_contribution_cents": totals["revenue_cents"] - product.variable_cost_cents * totals["units"] - totals["spend_cents"] - totals["pending_liability_cents"],
            "daily": history, "channels": rows, "traces": traces, "adjustments": adjustments,
            "final_frequencies": {p.id: frequencies[j] for j, p in enumerate(placements)},
            "social_sharing_enabled": social_sharing_enabled,
            "trace_scope": "First 20 evenly sampled numerical individuals; at most 1800 person-days."}


def compare_strategies(spec: StudySpec, plans: list[MediaPlan], *, research: TrendReport | None = None,
                       on_progress: Callable | None = None, checkpoint_dir=None,
                       cancel_check: Callable | None = None) -> dict:
    if len(plans) != 3 or len({p.id for p in plans}) != 3:
        raise ValueError("Exactly three plans with unique ids are required")
    if any(p.media_budget_cents != spec.media_budget_cents for p in plans):
        raise ValueError("All candidates must use the study's common media budget")
    base_ids = {f"baseline-{p.price_cents}" for p in plans}
    if any(p.id in base_ids for p in plans):
        raise ValueError("Candidate ids must not collide with price baseline ids")
    baselines = [MediaPlan(id=f"baseline-{price}", name=f"No campaign / {price / 100:.2f}",
                          price_cents=price, media_budget_cents=0, placements=[], adaptive=False)
                 for price in sorted({p.price_cents for p in plans})]
    rng = np.random.default_rng(np.random.SeedSequence([spec.seed, 48721]))
    seed_count = spec.exploration_repetitions + spec.validation_repetitions
    seeds = rng.choice(np.iinfo(np.int32).max, size=seed_count, replace=False).tolist()
    exploration_seeds = seeds[:spec.exploration_repetitions]
    validation_seeds = seeds[spec.exploration_repetitions:]
    total = len(plans + baselines) * seed_count
    completed = 0
    checkpoint_root = Path(checkpoint_dir) if checkpoint_dir is not None else None
    # Cache keys include every numerical input and engine version. No stale cross-study reuse.
    study_key = _digest({"engine": ENGINE_VERSION, "spec": spec.model_dump(), "plans": [p.model_dump() for p in plans]})
    cache = checkpoint_root / study_key if checkpoint_root else None

    def emit(message, day=0, scenario="", percent=None):
        if on_progress:
            on_progress({"percent": round(100 * completed / total, 3) if percent is None else percent,
                         "message": message, "day": day, "scenario": scenario})

    def run(plan, seed, phase):
        nonlocal completed
        if cancel_check and cancel_check():
            raise SimulationCancelled("Comparison cancelled after the last committed replica")
        key = _digest({"plan": plan.model_dump(), "seed": seed, "phase": phase})
        result_file = cache / f"{key}.json" if cache else None
        checkpoint = cache / f"{key}.npz" if cache else None
        if result_file and result_file.exists():
            result = json.loads(result_file.read_text(encoding="utf-8"))
        else:
            def on_day(row):
                emit(f"{phase}: {plan.name}, day {row['day']}/{spec.rounds}", row["day"], plan.id,
                     round(100 * (completed + row["day"] / spec.rounds) / total, 3))
            result = simulate_scenario(spec.product, spec.audience, plan, spec.rounds, seed,
                research=research, fatigue_multiplier=spec.fatigue_multiplier, price_elasticity=spec.price_elasticity,
                on_day=on_day, checkpoint_path=checkpoint, cancel_check=cancel_check,
                response_multipliers=spec.response_multipliers)
            if result_file:
                _atomic_json(result_file, result)
                checkpoint.unlink(missing_ok=True)
        completed += 1
        emit(f"Committed {phase} replica", spec.rounds, plan.id)
        return result

    exploration = {}
    exploration_summaries = []
    frozen = []
    for plan in plans + baselines:
        replicas = [run(plan, seed, "exploration") for seed in exploration_seeds]
        summary = summarize_scenario(plan, replicas, is_baseline=plan.id in base_ids)
        exploration_summaries.append(summary)
        exploration[plan.id] = summary
        if plan in plans:
            edited = plan.model_copy(deep=True)
            for placement in edited.placements:
                if not placement.locked:
                    placement.daily_frequency = float(np.mean([r["final_frequencies"][placement.id] for r in replicas]))
            frozen.append(edited)
    exploration_comparisons = [paired_comparison(exploration[p.id], exploration[f"baseline-{p.price_cents}"]) for p in plans]
    selected_id = max(plans, key=lambda p: exploration[p.id]["mean_revenue_cents"]).id
    validation = []
    for plan in frozen + baselines:
        validation.append(summarize_scenario(plan, [run(plan, seed, "validation") for seed in validation_seeds],
                                             is_baseline=plan.id in base_ids))
    by_id = {r["plan_id"]: r for r in validation}
    comparisons = [paired_comparison(by_id[p.id], by_id[f"baseline-{p.price_cents}"]) for p in plans]
    revenue_validation = [paired_revenue_comparison(by_id[selected_id], by_id[p.id])
                          for p in plans if p.id != selected_id]
    winner_id = selected_id if all(c["supported_practical_superiority"] for c in revenue_validation) else None
    reason = ("The maximum-revenue exploration candidate exceeds both alternatives by more than the 1% practical revenue threshold in paired validation mean intervals. Conditional model evidence only."
              if winner_id else "Indecisive: the maximum-revenue exploration candidate does not exceed both alternatives by the 1% practical revenue threshold in paired validation, or uncertainty is unavailable.")
    report = {"schema_version": "1.0", "engine_version": ENGINE_VERSION,
              "product": spec.product.model_dump(), "population": spec.audience.population,
              "rounds": spec.rounds, "seed": spec.seed, "winner_id": winner_id, "winner_reason": reason,
              "assumptions": ASSUMPTIONS.copy(),
              "personas": [p.model_dump() for p in generate_personas(spec.product, spec.audience, research, spec.seed)],
              "scenarios": validation, "comparisons": comparisons,
              "metadata": {"exploration_seeds": exploration_seeds, "validation_seeds": validation_seeds,
                           "objective": "maximum_total_revenue", "practical_threshold_fraction": .01,
                           "selected_revenue_validation": revenue_validation,
                           "exploration_selected_id": selected_id,
                           "original_plans": [p.model_dump() for p in plans],
                           "frozen_validation_plans": [p.model_dump() for p in frozen],
                           "exploration_comparisons": exploration_comparisons,
                           "exploration_scenarios": exploration_summaries,
                           "research_source_ids": [s.id for s in research.sources] if research else [],
                           "response_hypotheses": {"multipliers": spec.response_multipliers,
                                                   "status": "unvalidated_assumption",
                                                   "description": "LLM inferred response hypothesis when supplied by the optional reaction library; shared numeric persuasion input, not direct LLM sales."},
                           "age_behavior": {"weight": spec.audience.age_behavior_weight,
                                            "status": "unvalidated_assumption",
                                            "mechanism": "Weak age-centered log-odds shift, broad within-age variability; zero disables.",
                                            "channel_slopes": dict(zip(CHANNELS, AGE_CHANNEL_PRIORS, strict=True)),
                                            "social_sensitivity_slope": -.3},
                           "numeric_states": spec.audience.population, "weighted_sales": False,
                           "social_model": {"status": "unvalidated_assumption", "creator_fraction": .12,
                                            "communities": 32, "max_pending_per_recipient_placement": 2,
                                            "network": "sparse hashed contacts; next-day earned exposure consumes shared attention",
                                            "comments": "synthetic templates in bounded traces"},
                           "cache_replica_limit": MAX_CACHE_REPLICAS,
                           "cache_retention": "All completed replica results retained through cancellation and completion; no active-run eviction. Input limits bound a comparison to600replicas. Cleanup must be explicit after terminal completion.",
                           "random_streams": "Seed + numerical agent id + day + mechanism; no mutable draw cursor.",
                           "uncertainty": "5th–95th replica quantiles and approximate normal 95% paired mean intervals; conditional assumptions only."}}
    emit("Comparison complete", spec.rounds, "", 100)
    return report
