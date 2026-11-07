# Model definitions and limitations

## Evidence versus assumptions

Research stores source excerpts and their URLs/IDs, publication date when available, retrieval time, extraction status and coverage. Retrieved text is not independently verified. A search sample is not a population survey. A single collection cannot estimate trend velocity, market size or the optimal age of a buyer.

Demo sources and people are explicitly fictional. Persona beliefs can reference source findings while remaining simulated beliefs. Category-based age suggestions and weak age-related behavior priors are declared hypotheses. Manual age bounds are authoritative until the user explicitly changes them.

Default channel prices/response coefficients are illustrative and editable. None reproduces proprietary TikTok/Meta recommendations or observed ad inventory. Different formats execute different mechanics; that distinction is not empirical calibration.

## Population, exposure and purchase

One NumPy row is one adult synthetic individual, not a weighted block of consumers. A bounded displayed sample and optional language-model reactions supply qualitative context. Shared response hypotheses, when enabled, are explicitly unvalidated and apply equally to every strategy.

Daily exposure depends on channel affinity, format, eligible group membership, individual active hours, placements, budgets and a shared attention allowance. Short-video events include skips/completions, creator activity, short comments, sharing and first trend adoption. Sparse next-day earned contacts consume the same attention allowance; group contacts stay inside their synthetic community.

Intention combines need, trust, social influence, accumulated communication, price relative to means, friction and fatigue. The first-purchase gate enforces available means, prerequisites, stock and seeded stochastic choice. Each person buys at most one unit of the product per scenario. An unresolved requirement or conditional intention is not a sale.

Price-independent initial purchasing power and shared initial random traits make price comparisons interpretable. Weak age behavior priors preserve within-age diversity; setting their weight to zero gives neutral age behavior. No age alone determines a person's response.

## Experiments and primary objective

Three candidate price/media plans share the same submitted media envelope. Each distinct price also gets a no-campaign baseline. Default: 30 days, 10 exploration seeds and 10 disjoint validation seeds. All candidates use paired mechanism-specific random streams so path divergence does not simply consume a different random draw cursor.

Exploration selects the candidate with maximum mean **total revenue** and learns unlocked starting frequencies. The validation plans/policy/inputs are frozen, while the same declared daily adaptive controller remains active for unlocked lines. Validation does not retune the candidates after inspecting their outcomes.

The exploration-selected plan is a supported winner only when both paired validation revenue comparisons exceed a 1% practical threshold and the approximate mean-difference interval supports superiority. Otherwise report no supported winner. Contribution is visible but never silently substitutes for the requested revenue objective.

Quantile bands and approximate mean intervals describe simulation variability conditional on the model. They do not establish a real-world forecast interval or validate the assumptions. Replicates with a single seed cannot support a mean uncertainty claim.

## Money and attribution

- Revenue: units × actual scenario unit price; integer cents within a replicate.
- Contribution: revenue − product variable costs − acquisition spending. Taxes, refunds, repeat purchases, lifetime value and inventory replenishment are outside v0.1.
- Costs: CPM, CPC, CPA, daily fixed fee, or organic. Affiliate commissions are included in acquisition spending and also disclosed separately, never subtracted twice.
- CPA inventory conservatively reserves possible fees before eligible exposure. A hold remains while either its click or view can still become the qualifying touch, then expires/releases or settles on purchase. Media cash never blocks an otherwise-qualified customer's purchase. Cash contribution and conservative contribution after pending liability are distinguished; end-of-horizon pending amounts remain visible.
- Blended CAC: total acquisition spend / all new buyers. Paid CAC uses paid-attributed buyers. No buyers means `null`, not infinity or an invented zero.
- Attribution: last qualifying click within seven days; otherwise last qualifying view within 24 hours; otherwise organic/unknown. Every attributed buyer must have a recorded qualifying touch. One sale has one attribution.
- Attributed conversion: attributed unique buyers / unique people exposed on that channel. Exposed-cohort purchase rate separately counts all buyers in the reached cohort, even if attributed elsewhere. Cohort counts may overlap across channels and cannot be added.

No sales after the configured horizon are counted. End-of-window conversions are therefore right-censored. Attribution is a reading rule; the price-matched control supplies a separate simulated campaign contrast, not proof of real-world causality.

Summary values are means across validation replicas and may be fractional. Individual transactions and each replica's ledger remain integer/unweighted. Sampled persona/social traces are bounded examples, not an exhaustive transaction log.

## Real service costs

Provider prices are supplied in USD. Integer nanodollars avoid floating-point budget drift. Reserve a known request maximum before dispatch; settle with usage if available. Missing/ambiguous usage retains a conservative reservation. Confirmed usage-based estimates are not a bank invoice.

Search/extraction/semantic stages and representative batches retain committed results; an unresolved dispatched operation blocks an automatic repeat. The same research request reuses its original retrieval time. New live research can be intentionally started in a new study/request; no automatic action may raise the user's cost cap.
