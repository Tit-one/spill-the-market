// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import MarketOverview from "./MarketOverview";
import type { MarketAnalysis } from "./marketTypes";

afterEach(cleanup);
const report: MarketAnalysis = {
  schema_version: "1",
  objective: "market_discovery",
  status: "hypotheses_only",
  coverage: {
    real_source_count: 0,
    demo_source_count: 0,
    competitor_reference_count: 1,
    market_size_status: "unknown",
  },
  segment_recommendation: {
    status: "hypothesis",
    age_min: 25,
    age_max: 44,
    reason: "A conditional simulation signal.",
    segments: [
      {
        age_min: 25,
        age_max: 44,
        population: 50,
        units: 3.5,
        conversion_rate: 0.07,
        revenue_cents: 3500,
      },
    ],
  },
  channel_recommendation: {
    status: "hypothesis",
    channel: "search",
    reason: "A virtual channel signal.",
    channels: [
      {
        channel: "search",
        unique_reach: 40,
        units: 2.5,
        attributed_conversion_rate: 0.0625,
      },
    ],
  },
  competitors: [],
  barriers: [],
  next_actions: [],
  sources: [],
  limitations: [],
};
it("labels an unsourced exploration as hypotheses and never invents a market size", () => {
  render(<MarketOverview report={report} lang="fr" currency="EUR" />);
  expect(
    screen.getByText(
      "Hypothèses de simulation — aucune source réelle collectée.",
    ),
  ).toBeTruthy();
  expect(screen.getByText("Taille du marché : inconnue")).toBeTruthy();
  expect(
    screen.getByRole("heading", { name: "25–44 ans à tester" }),
  ).toBeTruthy();
  expect(screen.getByText(/pas une demande réelle mesurée/)).toBeTruthy();
});
it("does not recommend ages or a channel when every simulated segment and channel has zero purchases", () => {
  render(
    <MarketOverview
      report={{
        ...report,
        segment_recommendation: {
          ...report.segment_recommendation,
          segments: [{ age_min: 25, age_max: 44, population: 50, units: 0 }],
        },
        channel_recommendation: {
          ...report.channel_recommendation,
          channels: [{ channel: "search", units: 0 }],
        },
      }}
      lang="fr"
      currency="EUR"
    />,
  );
  expect(
    screen.getByRole("heading", { name: "Aucun âge ne se détache" }),
  ).toBeTruthy();
  expect(
    screen.getByRole("heading", { name: "Aucun canal ne se détache" }),
  ).toBeTruthy();
  expect(screen.queryByText("25–44 ans à tester")).toBeNull();
});
it("distinguishes source-backed references, unread URLs and fictional competitors without claiming verified competitors", () => {
  render(
    <MarketOverview
      report={{
        ...report,
        status: "evidence_informed_simulation",
        coverage: { ...report.coverage, real_source_count: 1 },
        competitors: [
          {
            name: "Read reference",
            url: "https://example.org/read",
            evidence_status: "source_statement",
            source_ids: ["s1"],
          },
          {
            name: "Unread reference",
            url: "https://example.org/unread",
            evidence_status: "unread_reference",
            source_ids: [],
          },
          {
            name: "Fictional reference",
            evidence_status: "fictional",
            source_ids: ["demo1"],
          },
        ],
        sources: [
          {
            id: "s1",
            title: "Supplied source",
            url: "https://example.org/read",
            kind: "web",
          },
        ],
      }}
      lang="fr"
      currency="EUR"
    />,
  );
  expect(screen.getByText("Référence documentée")).toBeTruthy();
  expect(screen.getByText("URL fournie — contenu non lu")).toBeTruthy();
  expect(screen.getByText("Référence fictive")).toBeTruthy();
  expect(screen.getByText(/demande réelle non mesurée/)).toBeTruthy();
  expect(screen.queryByText("Concurrent vérifié")).toBeNull();
});
it("keeps fractional switching means and makes the simulated population distinct from an unknown market", () => {
  render(
    <MarketOverview
      report={{
        ...report,
        switching: {
          enabled: true,
          status: "hypothesis",
          population: 100,
          buyers: 2.5,
          incumbent_users: 40,
          switchers: 0.75,
          new_to_category_buyers: 1.75,
          retained_incumbents: 39.25,
          assumptions: ["Unvalidated switching friction."],
          market_projection: null,
        },
      }}
      lang="fr"
      currency="EUR"
    />,
  );
  const switching = screen.getByRole("region", {
    name: "Changement de solution simulé",
  });
  expect(within(switching).getByText("0,75", { exact: true })).toBeTruthy();
  expect(within(switching).getByText("1,75", { exact: true })).toBeTruthy();
  expect(within(switching).getByText(/Moyennes de simulation/)).toBeTruthy();
  expect(
    within(switching).getByText(/aucune extrapolation au marché réel/),
  ).toBeTruthy();
});
it("handles incomplete older data and refuses executable source links", () => {
  render(
    <MarketOverview
      report={{
        sources: [
          { id: "unsafe", title: "Unsafe source", url: "javascript:alert(1)" },
        ],
      }}
      lang="fr"
      currency="EUR"
    />,
  );
  expect(
    screen.getByText(
      "Aucune conclusion de marché disponible pour cet ancien rapport.",
    ),
  ).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Unsafe source" })).toBeNull();
  expect(screen.getByText("Taille du marché : inconnue")).toBeTruthy();
});
it("labels any supplied addressable-market extrapolation as unvalidated", () => {
  render(
    <MarketOverview
      report={{
        ...report,
        switching: {
          enabled: true,
          market_projection: {
            addressable_population: 10000,
            estimated_switchers: 75.5,
            status: "unvalidated_extrapolation",
          },
        },
      }}
      lang="en"
      currency="EUR"
    />,
  );
  expect(
    screen.getByText("Unvalidated extrapolation — not a market forecast"),
  ).toBeTruthy();
  expect(screen.getByText(/75.5/)).toBeTruthy();
});
