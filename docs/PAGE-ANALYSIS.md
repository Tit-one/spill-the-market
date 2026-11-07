# Module 5 — visual product-page comprehension (planned)

Approved future module; not enabled or claimed implemented in v0.1. Core contracts keep this extension independent from acquisition simulation.

## Data flow

`PageAuditSpec -> PageSnapshot -> GroundedObservation -> PersonaPageReview -> PageAuditReport -> funnel hypotheses`

1. Accept a public URL, uploaded HTML or user-selected screenshots. Snapshot stores content hash, capture time, viewport, scroll offset and navigation history. Capture mobile and desktop; retain above-the-fold separately. Local HTML is untrusted and never executes in the application origin.
2. Multimodal observer records visible text, elements, coordinates, section IDs, prices, buttons and absent/unknown information. DOM/accessibility text is evidence alongside images, never a substitute for seeing the image. Separate exact observations, uncertain OCR and interpretations.
3. An exposure scheduler reveals only the current viewport/section to each persona. Hidden prices, full-page summaries and auditor recommendations must not leak into a first impression. Preserve the advertisement that led to the visit.
4. Personas produce current understanding, questions, confidence, sought information, proposed next action, friction and conditional buying intention. Age is one configurable hypothesis alongside ability, familiarity, need and means.
5. A stratified control sample sees the actual images directly, compared with personas using structured observations. This measures information lost or added by the shared observer; it does not establish real-user validity.
6. Report each issue against the exact screenshot/section and persona context. Pair A/B page variants with the same initial personas, advertisements and random streams. Proposed friction coefficients remain hypotheses until calibrated with observed user behavior.

## Integration contracts

- `PageSnapshot`: id/hash, source, viewport, scroll position, image reference, visible DOM, capture metadata.
- `GroundedObservation`: regions with bounding boxes, literal observations, evidence references, uncertainty; no global judgment embedded in neutral descriptions.
- `PersonaPageReview`: persona_id, snapshot_id, visible_information_ids, understanding, questions, reaction, intended_action, intention_before/after, provenance.
- `PageAuditReport`: paired versions, audience coverage, findings by section/persona, direct-vision control results, recommended experiments, limitations and real inference receipts.
- The acquisition engine receives versioned, editable friction/trust hypotheses. Page audit does not directly invent sales.

## Cost and execution boundaries

All vision calls use the same real-services ledger, token/image limits and uncertain-charge rules. Raw images/HTML stay local until the user explicitly selects a remote provider. Local vision providers remain an option. Reuse factual observations across personas while retaining representative direct-image checks.

A later browser-agent extension verifies navigation and interactive behavior for a bounded subset. Visual reading alone cannot prove a working checkout, accessibility flow, valid purchase, actual conversion rate or real-person comprehension.
