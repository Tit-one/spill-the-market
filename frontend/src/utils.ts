import type { Lang, StudySpec, Channel, Placement } from "./types";
export function planName(
  plan: { id?: string; plan_id?: string; name: string },
  lang: Lang,
): string {
  const defaults: Record<string, [string, string]> = {
    value: ["Accessible discovery", "Découverte accessible"],
    balanced: ["Demonstrate the benefit", "Démontrer le bénéfice"],
    premium: ["Focused premium launch", "Lancement premium ciblé"],
  };
  const pair = defaults[plan.plan_id ?? plan.id ?? ""];
  return lang === "fr" && pair && plan.name === pair[0] ? pair[1] : plan.name;
}
export const channels: Channel[] = [
  "tiktok",
  "instagram",
  "facebook",
  "youtube",
  "twitch",
  "x",
  "reddit",
  "communities",
  "creators",
  "in_game",
  "search",
  "display",
  "podcast",
  "newsletter",
  "affiliate",
];
export const channelNames: Record<string, string> = {
  tiktok: "TikTok",
  instagram: "Instagram",
  facebook: "Facebook",
  youtube: "YouTube",
  twitch: "Twitch",
  x: "X",
  reddit: "Reddit",
  communities: "Communities",
  creators: "Creators",
  in_game: "In-game",
  search: "Search",
  display: "Display",
  podcast: "Podcast",
  newsletter: "Newsletter",
  affiliate: "Affiliate",
};
export function money(
  cents: number | null | undefined,
  currency = "EUR",
  lang: Lang = "en",
  compact = false,
) {
  if (cents == null || !Number.isFinite(cents)) return "—";
  return new Intl.NumberFormat(lang === "fr" ? "fr-FR" : "en-GB", {
    style: "currency",
    currency,
    maximumFractionDigits: compact ? 0 : 2,
  }).format(cents / 100);
}
export function number(
  value: number | undefined,
  lang: Lang = "en",
  digits = 0,
) {
  return value == null || !Number.isFinite(value)
    ? "—"
    : new Intl.NumberFormat(lang === "fr" ? "fr-FR" : "en-GB", {
        maximumFractionDigits: digits,
      }).format(value);
}
export function percent(value: number | undefined, lang: Lang = "en") {
  return value == null || !Number.isFinite(value)
    ? "—"
    : new Intl.NumberFormat(lang === "fr" ? "fr-FR" : "en-GB", {
        style: "percent",
        maximumFractionDigits: 1,
      }).format(value);
}
export function plain(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}
export function safeURL(url: string | null) {
  if (!url) return null;
  try {
    const u = new URL(url);
    return ["https:", "http:"].includes(u.protocol) ? u.href : null;
  } catch {
    return null;
  }
}
export function validateSpec(s: StudySpec, lang: Lang): string[] {
  const fr = lang === "fr";
  const e: string[] = [];
  if (s.product.name.trim().length < 2)
    e.push(fr ? "Indiquez un nom de produit." : "Enter a product name.");
  if (s.product.description.trim().length < 8)
    e.push(
      fr
        ? "Décrivez le produit en au moins 8 caractères."
        : "Describe the product in at least 8 characters.",
    );
  if (
    !Number.isInteger(s.audience.population) ||
    s.audience.population < 30 ||
    s.audience.population > 100000
  )
    e.push(
      fr
        ? "La population doit comprendre de 30 à 100 000 adultes."
        : "Population must contain 30–100,000 adults.",
    );
  if (
    s.audience.age_min < 18 ||
    s.audience.age_max > 100 ||
    s.audience.age_min > s.audience.age_max
  )
    e.push(
      fr
        ? "Vérifiez la tranche d’âge (18–100 ans, minimum ≤ maximum)."
        : "Check the age range (18–100, minimum ≤ maximum).",
    );
  if (s.audience.representatives > s.audience.population)
    e.push(
      fr
        ? "Les profils représentatifs ne peuvent dépasser la population."
        : "Representative profiles cannot exceed the population.",
    );
  if (s.product.unit_price_cents <= 0)
    e.push(fr ? "Le prix doit être positif." : "Price must be positive.");
  if (
    [s.market?.product_url, ...(s.market?.competitor_urls ?? [])].some(
      (url) => url?.trim() && !safeURL(url.trim()),
    )
  )
    e.push(
      fr
        ? "Les sources doivent être des URL publiques commençant par https:// ou http://."
        : "Source URLs must start with https:// or http://.",
    );
  if ((s.market?.competitor_urls.filter((url) => url.trim()).length ?? 0) > 10)
    e.push(
      fr
        ? "Ajoutez au plus 10 URL concurrentes."
        : "Add at most 10 competitor URLs.",
    );
  return e;
}
export function newPlacement(channel: Channel = "instagram"): Placement {
  return {
    id: crypto.randomUUID().slice(0, 12),
    channel,
    format: "feed",
    distribution: "paid",
    weight: 1,
    daily_frequency: 1.5,
    charge_basis: "CPM",
    cpm_cents: 800,
    cpc_cents: 50,
    cpa_cents: 300,
    fee_cents: 1000,
    locked: false,
    creative: "See the product in action.",
    dayparts: [12, 18],
    assumption:
      "Illustrative response and cost parameters; not observed ad-platform prices.",
  };
}
export const initialSpec: StudySpec = {
  product: {
    name: "Orbit Orchard",
    description:
      "A fictional cosy puzzle game about growing a tiny orchard in space. Short sessions, single-player challenges, and a one-time purchase.",
    category: "game",
    unit_price_cents: 1490,
    currency: "EUR",
    variable_cost_cents: 150,
    stock: null,
    prerequisites: [],
    keywords: ["cosy", "puzzle", "indie game"],
  },
  audience: {
    population: 1000,
    age_min: 18,
    age_max: 65,
    auto_age: false,
    representatives: 40,
    languages: ["fr", "en"],
    region: "France",
    timezone: "Europe/Paris",
  },
  research: {
    mode: "demo",
    topic: "cosy puzzle games",
    language: "en",
    region: "France",
    days: 90,
    urls: [],
    documents: [],
    max_sources: 12,
    use_llm: false,
    use_firecrawl: false,
  },
  rounds: 30,
  media_budget_cents: 100000,
  api_budget_usd: 0,
  api_max_calls: 300,
  seed: 42,
  exploration_repetitions: 5,
  validation_repetitions: 5,
  fatigue_multiplier: 1,
  price_elasticity: 1,
  locale: "en",
};

/** New experiments have no inherited fictional product, keywords or research. */
export const blankStudySpec: StudySpec = {
  ...initialSpec,
  objective: "campaign",
  market: {
    incumbent_share: 0.6,
    switching_friction: 0.5,
    addressable_population: null,
    product_url: "",
    competitor_urls: [],
  },
  audience: { ...initialSpec.audience, languages: ["fr"] },
  product: {
    ...initialSpec.product,
    name: "",
    description: "",
    category: "other",
    unit_price_cents: 0,
    variable_cost_cents: 0,
    keywords: [],
    prerequisites: [],
    stock: null,
  },
  research: {
    ...initialSpec.research,
    mode: "offline",
    language: "fr",
    topic: "",
    documents: [],
    urls: [],
  },
};
