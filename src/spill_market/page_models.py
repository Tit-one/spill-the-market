"""Versioned page-audit contracts, independent of the sales engine."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PageContract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


Viewport = Literal["desktop", "mobile"]


class ScreenshotInput(PageContract):
    name: str = Field(default="screenshot", min_length=1, max_length=150)
    data_base64: str = Field(min_length=1, max_length=8_000_000)
    viewport: Viewport = "desktop"
    scroll_y: int = Field(default=0, ge=0, le=200_000)


class PageVariantInput(PageContract):
    id: Literal["A", "B"] = "A"
    label: str = Field(default="Page A", min_length=1, max_length=150)
    source: Literal["demo", "url", "html", "screenshots"] = "demo"
    url: str | None = Field(default=None, max_length=2048)
    html: str | None = Field(default=None, max_length=500_000)
    screenshots: list[ScreenshotInput] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def source_present(self):
        if self.source == "url" and not self.url:
            raise ValueError("A public URL is required")
        if self.source == "html" and not self.html:
            raise ValueError("HTML content is required")
        if self.source == "screenshots" and not self.screenshots:
            raise ValueError("At least one screenshot is required")
        if self.source != "url" and self.url is not None:
            raise ValueError("URL is only valid for a URL source")
        if self.source != "html" and self.html is not None:
            raise ValueError("HTML is only valid for an HTML source")
        if self.source != "screenshots" and self.screenshots:
            raise ValueError("Screenshots are only valid for an image source")
        return self


class PageAuditSpec(PageContract):
    schema_version: str = "1.0"
    variants: list[PageVariantInput] = Field(default_factory=lambda: [PageVariantInput()], min_length=1, max_length=2)
    viewports: list[Viewport] = Field(default_factory=lambda: ["desktop", "mobile"], min_length=1, max_length=2)
    max_sections: int = Field(default=3, ge=1, le=6)
    persona_count: int = Field(default=8, ge=1, le=24)
    direct_vision_count: int = Field(default=2, ge=0, le=4)
    advertisement_context: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def identities(self):
        if len({v.id for v in self.variants}) != len(self.variants) or self.variants[0].id != "A":
            raise ValueError("Variants must be A, optionally followed by B")
        if len(set(self.viewports)) != len(self.viewports):
            raise ValueError("Viewports must be unique")
        if self.direct_vision_count > self.persona_count:
            raise ValueError("Direct controls cannot exceed the persona sample")
        total = sum(len(s.data_base64) for v in self.variants for s in v.screenshots)
        if total > 24_000_000:
            raise ValueError("Combined image payload exceeds 24 MB encoded")
        return self


class AnalyzePageRequest(PageContract):
    provider_id: Literal["demo", "configured", "local"] = "demo"
    allow_remote: bool = False


class Box(PageContract):
    x: float = Field(ge=0, le=20_000)
    y: float = Field(ge=0, le=20_000)
    width: float = Field(gt=0, le=20_000)
    height: float = Field(gt=0, le=20_000)


class VisibleElement(PageContract):
    id: str
    tag: str
    text: str
    box: Box


class PageSnapshot(PageContract):
    id: str
    variant_id: str
    section_index: int
    viewport: Viewport
    width: int = Field(gt=0, le=4000)
    height: int = Field(gt=0, le=12_000)
    scroll_y: int = Field(ge=0)
    page_height: int = Field(gt=0)
    content_hash: str
    captured_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    image_url: str = ""
    dom: list[VisibleElement] = Field(default_factory=list)
    provenance: Literal["demo", "public_url", "html_render", "screenshot_import"]
    warnings: list[str] = Field(default_factory=list)


class VisualRegion(PageContract):
    id: str
    box: Box
    kind: Literal["heading", "text", "price", "button", "image", "navigation", "other"]
    literal_text: str
    description: str
    uncertainty: str


class GroundedObservation(PageContract):
    snapshot_id: str
    summary: str
    regions: list[VisualRegion]
    unknowns: list[str]
    interpretations: list[str]
    mode: Literal["vision", "demo"]


class PersonaPageReview(PageContract):
    persona_id: str
    age: int = Field(ge=18, le=100)
    variant_id: str
    snapshot_id: str
    viewport: Viewport
    step: int = Field(ge=0)
    mode: Literal["observation", "direct_vision", "demo"]
    visible_information_ids: list[str]
    understanding: str
    questions: list[str]
    positives: list[str]
    frictions: list[str]
    confidence: float = Field(ge=0, le=1)
    trust: float = Field(ge=0, le=1)
    intention_before: float = Field(ge=0, le=1)
    intention_after: float = Field(ge=0, le=1)
    intended_action: Literal["scroll", "seek_information", "consider_purchase", "leave"]
    evidence_ids: list[str]


class PageAuditReport(PageContract):
    schema_version: str = "1.0"
    audit_id: str
    study_id: str
    mode: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    observations: list[GroundedObservation]
    reviews: list[PersonaPageReview]
    findings: list[dict]
    comparisons: list[dict]
    direct_vision_controls: list[dict]
    audience_coverage: dict
    cost: dict
    limitations: list[str]
