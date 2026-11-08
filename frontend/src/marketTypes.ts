export interface AgeSegment {
  age_min: number;
  age_max: number;
  label?: string;
  population?: number;
  units?: number;
  organic_units?: number;
  conversion_rate?: number;
  revenue_cents?: number;
  mean_intention?: number;
  channels?: ChannelResult[];
  [key: string]: unknown;
}
export interface ChannelResult {
  channel?: string;
  unique_reach?: number;
  units?: number;
  conversion_rate?: number;
  attributed_conversion_rate?: number;
  [key: string]: unknown;
}
export interface MarketSource {
  id: string;
  title?: string;
  url?: string | null;
  retrieved_at?: string | null;
  published_at?: string | null;
  kind?: string;
}
export interface MarketAnalysis {
  schema_version?: string;
  objective?: string;
  status?: "hypotheses_only" | "evidence_informed_simulation" | "demo";
  coverage?: {
    real_source_count?: number;
    demo_source_count?: number;
    competitor_reference_count?: number;
    market_size_status?: string;
  };
  competitors?: {
    name?: string;
    url?: string | null;
    source_ids?: string[];
    excerpts?: string[];
    evidence_status?: string;
  }[];
  barriers?: {
    kind?: string;
    title?: string;
    detail?: string;
    status?: string;
    source_ids?: string[];
    severity?: string;
  }[];
  segment_recommendation?: {
    status?: "hypothesis" | "inconclusive";
    age_min?: number | null;
    age_max?: number | null;
    reason?: string;
    based_on_plan?: string;
    segments?: AgeSegment[];
  };
  channel_recommendation?: {
    status?: string;
    channel?: string | null;
    reason?: string;
    based_on_plan?: string;
    channels?: ChannelResult[];
  };
  switching?: {
    enabled?: boolean;
    status?: string;
    population?: number;
    buyers?: number;
    incumbent_users?: number;
    non_incumbent_users?: number;
    switchers?: number;
    new_to_category_buyers?: number;
    retained_incumbents?: number;
    new_to_category_nonbuyers?: number;
    mean_switching_acceptance?: number;
    incumbent_share?: number;
    switching_friction?: number;
    assumptions?: string[];
    market_projection?: null | {
      addressable_population?: number;
      estimated_switchers?: number;
      status?: "unvalidated_extrapolation";
    };
  };
  next_actions?: {
    kind?: string;
    title?: string;
    detail?: string;
    source_ids?: string[];
  }[];
  sources?: MarketSource[];
  limitations?: string[];
}
