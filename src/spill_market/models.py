"""Versioned contracts shared by the CLI, HTTP service and simulation workers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ProductSpec(Contract):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=8, max_length=12000)
    category: Literal["game", "software", "physical", "service", "other"] = "software"
    unit_price_cents: int = Field(gt=0, le=100_000_000)
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    variable_cost_cents: int = Field(default=0, ge=0, le=100_000_000)
    stock: int | None = Field(default=None, ge=0)
    prerequisites: list[str] = Field(default_factory=list, max_length=20)
    keywords: list[str] = Field(default_factory=list, max_length=30)


class AudienceSpec(Contract):
    population: int = Field(default=1000, ge=30, le=100_000)
    age_min: int = Field(default=18, ge=18, le=100)
    age_max: int = Field(default=65, ge=18, le=100)
    auto_age: bool = False
    age_behavior_weight: float = Field(default=0.15, ge=0, le=0.5)
    representatives: int = Field(default=50, ge=1, le=200)
    languages: list[str] = Field(default_factory=lambda: ["fr", "en"], min_length=1, max_length=10)
    region: str = Field(default="global", max_length=100)
    timezone: str = "Europe/Paris"

    @model_validator(mode="after")
    def check_ages(self):
        if self.age_min > self.age_max:
            raise ValueError("age_min must be <= age_max")
        if self.representatives > self.population:
            raise ValueError("representatives must not exceed population")
        return self


class ImportedDocument(Contract):
    name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=200_000)


class ResearchRequest(Contract):
    mode: Literal["demo", "offline", "urls", "live"] = "demo"
    topic: str = Field(default="", max_length=500)
    language: str = "en"
    region: str = "global"
    days: int = Field(default=90, ge=1, le=730)
    urls: list[str] = Field(default_factory=list, max_length=20)
    documents: list[ImportedDocument] = Field(default_factory=list, max_length=20)
    max_sources: int = Field(default=12, ge=1, le=30)
    use_llm: bool = False
    use_firecrawl: bool = False


class EvidenceSource(Contract):
    id: str
    title: str
    url: str | None = None
    content: str
    kind: Literal["demo", "import", "web", "rss"]
    retrieved_at: str = Field(default_factory=utc_now)
    published_at: str | None = None
    content_hash: str = ""
    url_reference_hash: str = Field(default="", pattern=r"^(?:[0-9a-f]{64})?$")


class Finding(Contract):
    text: str
    source_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.3, ge=0, le=1)
    status: Literal["observed", "inferred", "assumption"] = "assumption"


class TrendReport(Contract):
    schema_version: str = "1.0"
    topic: str
    mode: str
    created_at: str = Field(default_factory=utc_now)
    language: str = "en"
    region: str = "global"
    sources: list[EvidenceSource] = Field(default_factory=list)
    trends: list[Finding] = Field(default_factory=list)
    pain_points: list[Finding] = Field(default_factory=list)
    jargon: list[Finding] = Field(default_factory=list)
    segments: list[Finding] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    recommended_age_range: list[int] | None = None


class Persona(Contract):
    id: str
    name: str
    age: int = Field(ge=18, le=100)
    language: str
    profession: str
    budget_cents: int = Field(ge=0)
    need_fit: float = Field(ge=0, le=1)
    trust: float = Field(ge=0, le=1)
    skepticism: float = Field(default=0.5, ge=0, le=1)
    price_sensitivity: float = Field(ge=0, le=1)
    social_sensitivity: float = Field(ge=0, le=1)
    fatigue_tolerance: float = Field(ge=0, le=1)
    channels: dict[str, float] = Field(default_factory=dict)
    beliefs: list[dict[str, Any]] = Field(default_factory=list)
    segment: str = "general"
    timezone: str = "Europe/Paris"


Channel = Literal[
    "tiktok", "instagram", "facebook", "youtube", "twitch", "in_game", "search",
    "display", "podcast", "newsletter", "affiliate", "creators", "communities", "x", "reddit",
]


class Placement(Contract):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    channel: Channel
    format: str = "feed"
    distribution: Literal["paid", "organic", "partnership"] = "paid"
    weight: float = Field(default=1, ge=0, le=100)
    daily_frequency: float = Field(default=1.5, ge=0, le=12)
    charge_basis: Literal["CPM", "CPC", "CPA", "FIXED", "ORGANIC"] = "CPM"
    cpm_cents: int = Field(default=800, gt=0, le=1_000_000)
    cpc_cents: int = Field(default=50, gt=0, le=1_000_000)
    cpa_cents: int = Field(default=300, gt=0, le=100_000_000)
    fee_cents: int = Field(default=1000, ge=0, le=100_000_000)
    locked: bool = False
    creative: str = Field(default="See the product in action.", max_length=2000)
    dayparts: list[int] = Field(default_factory=lambda: [12, 18], min_length=1, max_length=24)
    assumption: str = "Illustrative response and cost parameters; not observed ad-platform prices."

    @model_validator(mode="after")
    def check_hours(self):
        if any(not 0 <= hour <= 23 for hour in self.dayparts):
            raise ValueError("dayparts must be between 0 and 23")
        return self


class MediaPlan(Contract):
    id: str
    name: str
    description: str = ""
    price_cents: int = Field(gt=0, le=100_000_000)
    media_budget_cents: int = Field(ge=0, le=10_000_000_000)
    placements: list[Placement] = Field(default_factory=list, max_length=30)
    adaptive: bool = True
    intensity: Literal["selective", "balanced", "intensive"] = "balanced"
    rationale: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_placement_identity(self):
        ids = [placement.id for placement in self.placements]
        if len(ids) != len(set(ids)):
            raise ValueError("Placement ids must be unique within a plan")
        return self


class MarketAssumptions(Contract):
    incumbent_share: float = Field(default=0.6, ge=0, le=1, allow_inf_nan=False)
    switching_friction: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    addressable_population: int | None = Field(default=None, ge=1, le=1_000_000_000_000)
    product_url: str = Field(default="", max_length=4096)
    competitor_urls: list[Annotated[str, Field(max_length=4096)]] = Field(default_factory=list, max_length=10)


class StudySpec(Contract):
    product: ProductSpec
    objective: Literal["campaign", "market_discovery"] = "campaign"
    market: MarketAssumptions = Field(default_factory=MarketAssumptions)
    audience: AudienceSpec = Field(default_factory=AudienceSpec)
    research: ResearchRequest = Field(default_factory=ResearchRequest)
    rounds: int = Field(default=30, ge=1, le=90)
    media_budget_cents: int = Field(default=100_000, ge=0, le=10_000_000_000)
    api_budget_usd: float = Field(default=0, ge=0, le=10_000)
    api_max_calls: int = Field(default=300, ge=1, le=10000)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    exploration_repetitions: int = Field(default=10, ge=1, le=50)
    validation_repetitions: int = Field(default=10, ge=1, le=50)
    fatigue_multiplier: float = Field(default=1, ge=0, le=3)
    price_elasticity: float = Field(default=1, ge=0.1, le=3)
    use_representative_llm: bool = False
    response_multipliers: dict[Channel, Annotated[float, Field(ge=0.8, le=1.2)]] = Field(default_factory=dict)
    locale: Literal["fr", "en"] = "en"


class CreateStudyRequest(Contract):
    spec: StudySpec


class StartRunRequest(Contract):
    plans: list[MediaPlan] | None = None


from .page_models import PageAuditSpec as PageAuditSpec  # noqa: E402
