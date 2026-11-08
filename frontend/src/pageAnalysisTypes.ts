export type Viewport = "desktop" | "mobile";
export type PageSource = "demo" | "url" | "html" | "screenshots";
export type ProviderId = "demo" | "configured" | "local";
export interface ScreenshotInput {
  name: string;
  data_base64: string;
  viewport: Viewport;
  scroll_y: number;
}
export interface PageVariantInput {
  id: "A" | "B";
  label: string;
  source: PageSource;
  url: string | null;
  html: string | null;
  screenshots: ScreenshotInput[];
}
export interface PageAuditSpec {
  schema_version: string;
  variants: PageVariantInput[];
  viewports: Viewport[];
  max_sections: number;
  persona_count: number;
  direct_vision_count: number;
  advertisement_context: string;
}
export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}
export interface PageSnapshot {
  id: string;
  variant_id: string;
  section_index: number;
  viewport: Viewport;
  width: number;
  height: number;
  scroll_y: number;
  page_height: number;
  content_hash: string;
  captured_at: string;
  image_url: string;
  dom: { id: string; tag: string; text: string; box: Box }[];
  provenance: "demo" | "public_url" | "html_render" | "screenshot_import";
  warnings: string[];
}
export interface VisualRegion {
  id: string;
  box: Box;
  kind:
    "heading" | "text" | "price" | "button" | "image" | "navigation" | "other";
  literal_text: string;
  description: string;
  uncertainty: string;
}
export interface GroundedObservation {
  snapshot_id: string;
  summary: string;
  regions: VisualRegion[];
  unknowns: string[];
  interpretations: string[];
  mode: "vision" | "demo";
}
export interface PersonaPageReview {
  persona_id: string;
  age: number;
  variant_id: string;
  snapshot_id: string;
  viewport: Viewport;
  step: number;
  mode: "observation" | "direct_vision" | "demo";
  visible_information_ids: string[];
  understanding: string;
  questions: string[];
  positives: string[];
  frictions: string[];
  confidence: number;
  trust: number;
  intention_before: number;
  intention_after: number;
  intended_action:
    "scroll" | "seek_information" | "consider_purchase" | "leave";
  evidence_ids: string[];
}
export interface PageAuditReport {
  schema_version: string;
  audit_id: string;
  study_id: string;
  mode: string;
  created_at: string;
  observations: GroundedObservation[];
  reviews: PersonaPageReview[];
  findings: Record<string, unknown>[];
  comparisons: Record<string, unknown>[];
  direct_vision_controls: Record<string, unknown>[];
  audience_coverage: Record<string, unknown>;
  cost: Record<string, unknown>;
  limitations: string[];
}
export interface PageAudit {
  id: string;
  study_id: string;
  status:
    | "queued"
    | "capturing"
    | "captured"
    | "analyzing"
    | "completed"
    | "cancelled"
    | "failed"
    | "interrupted";
  progress: { phase: string; message: string; percent: number };
  spec: PageAuditSpec;
  snapshots: PageSnapshot[];
  report: PageAuditReport | null;
  error: string | null;
  error_code?: string | null;
  operation?: "capture" | "analysis";
  cost: Record<string, unknown>;
  provider_id: ProviderId | null;
  created_at: string;
  updated_at: string;
}
export interface PageProvider {
  id: ProviderId;
  name: string;
  model: string;
  scope: "local" | "remote";
  available: boolean;
  reason: string;
  vision: boolean;
  pricing: Record<string, unknown>;
}
export interface PageProviders {
  providers: PageProvider[];
  capture: { available: boolean; reason: string };
}
