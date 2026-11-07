export type Lang = "en" | "fr";
export type Category = "game" | "software" | "physical" | "service" | "other";
export type Channel =
  | "tiktok"
  | "instagram"
  | "facebook"
  | "youtube"
  | "twitch"
  | "in_game"
  | "search"
  | "display"
  | "podcast"
  | "newsletter"
  | "affiliate"
  | "creators"
  | "communities"
  | "x"
  | "reddit";
export interface Product {
  name: string;
  description: string;
  category: Category;
  unit_price_cents: number;
  currency: string;
  variable_cost_cents: number;
  stock: number | null;
  prerequisites: string[];
  keywords: string[];
}
export interface Audience {
  population: number;
  age_min: number;
  age_max: number;
  auto_age: boolean;
  age_behavior_weight?: number;
  representatives: number;
  languages: string[];
  region: string;
  timezone: string;
}
export interface ResearchRequest {
  mode: "demo" | "offline" | "urls" | "live";
  topic: string;
  language: string;
  region: string;
  days: number;
  urls: string[];
  documents: { name: string; text: string }[];
  max_sources: number;
  use_llm: boolean;
  use_firecrawl: boolean;
}
export interface StudySpec {
  product: Product;
  audience: Audience;
  research: ResearchRequest;
  rounds: number;
  media_budget_cents: number;
  api_budget_usd: number;
  api_max_calls: number;
  seed: number;
  exploration_repetitions: number;
  validation_repetitions: number;
  fatigue_multiplier: number;
  price_elasticity: number;
  locale: Lang;
  use_representative_llm?: boolean;
  response_multipliers?: Record<string, number>;
}
export interface Placement {
  id: string;
  channel: Channel;
  format: string;
  distribution: "paid" | "organic" | "partnership";
  weight: number;
  daily_frequency: number;
  charge_basis: "CPM" | "CPC" | "CPA" | "FIXED" | "ORGANIC";
  cpm_cents: number;
  cpc_cents: number;
  cpa_cents: number;
  fee_cents: number;
  locked: boolean;
  creative: string;
  dayparts: number[];
  assumption: string;
}
export interface MediaPlan {
  id: string;
  name: string;
  description: string;
  price_cents: number;
  media_budget_cents: number;
  placements: Placement[];
  adaptive: boolean;
  intensity: "selective" | "balanced" | "intensive";
  rationale: string[];
}
export interface Finding {
  text: string;
  source_ids: string[];
  confidence: number;
  status: "observed" | "inferred" | "assumption";
}
export interface EvidenceSource {
  id: string;
  title: string;
  url: string | null;
  content: string;
  kind: "demo" | "import" | "web" | "rss";
  retrieved_at: string;
  published_at: string | null;
  content_hash: string;
}
export interface TrendReport {
  schema_version: string;
  topic: string;
  mode: string;
  created_at: string;
  language: string;
  region: string;
  sources: EvidenceSource[];
  trends: Finding[];
  pain_points: Finding[];
  jargon: Finding[];
  segments: Finding[];
  coverage: Record<string, unknown>;
  limitations: string[];
  recommended_age_range: number[] | null;
}
export interface Persona {
  id: string;
  name: string;
  age: number;
  language: string;
  profession: string;
  budget_cents: number;
  need_fit: number;
  trust: number;
  price_sensitivity: number;
  social_sensitivity: number;
  fatigue_tolerance: number;
  channels: Record<string, number>;
  beliefs: Record<string, unknown>[];
  segment: string;
  timezone: string;
}
export interface Daily {
  day: number;
  units: number;
  revenue_cents: number;
  spend_cents: number;
  cumulative_units: number;
  cumulative_revenue_cents: number;
  cumulative_spend_cents: number;
  mean_intention: number;
  mean_fatigue: number;
}
export interface ChannelResult {
  channel: string;
  impressions: number;
  unique_reach: number;
  clicks: number;
  units: number;
  revenue_cents: number;
  spend_cents: number;
  attributed_conversion_rate: number;
  exposed_purchase_rate: number;
  cac_cents: number | null;
  views?: number;
  completions?: number;
  skips?: number;
  comments?: number;
  shares?: number;
  trend_adoptions?: number;
  creator_posts?: number;
  earned_impressions?: number;
  view_attributed_units?: number;
  click_attributed_units?: number;
}
export interface Scenario {
  plan_id: string;
  name: string;
  is_baseline: boolean;
  price_cents: number;
  mean_revenue_cents: number;
  median_revenue_cents: number;
  revenue_interval_cents: number[];
  mean_units: number;
  mean_unique_buyers?: number;
  mean_paid_units?: number;
  mean_organic_units?: number;
  mean_commission_cents?: number;
  mean_contribution_cents?: number;
  mean_spend_cents: number;
  mean_cac_cents: number | null;
  mean_paid_cac_cents: number | null;
  daily: Daily[];
  channels: ChannelResult[];
  traces: Record<string, unknown>[];
  adjustments: Record<string, unknown>[];
  replicate_totals: Record<string, unknown>[];
  [key: string]: unknown;
}
export interface Report {
  schema_version: string;
  engine_version: string;
  product: Product;
  population: number;
  rounds: number;
  seed: number;
  winner_id: string | null;
  winner_reason: string;
  assumptions: string[];
  personas: Persona[];
  scenarios: Scenario[];
  comparisons: Record<string, unknown>[];
  metadata: Record<string, unknown>;
}
export interface Progress {
  percent: number;
  message: string;
  day?: number;
  scenario?: string;
}
export interface Run {
  id: string;
  study_id: string;
  status: string;
  progress: Progress;
  error?: string | null;
  report?: Report;
  created_at?: string;
}
export interface Study {
  id: string;
  spec: StudySpec;
  plans: MediaPlan[];
  research: TrendReport;
  personas: Persona[];
  created_at: string;
  runs: Run[];
}
export interface Bootstrap {
  version: string;
  session_token: string;
  capabilities: Record<string, unknown>;
  channels: Record<string, unknown>[];
  examples: { id: string; name: string; spec: StudySpec }[];
  provider_status: {
    tavily: boolean;
    firecrawl: boolean;
    llm: boolean;
    llm_model: string | null;
    configuration: string;
  };
}
