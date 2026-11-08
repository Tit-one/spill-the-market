// @vitest-environment jsdom
import { it, expect, afterEach, vi } from "vitest";
import { render, screen, within, cleanup } from "@testing-library/react";
import ResultOverview from "./ResultOverview";
import { RunMonitor } from "./App";
import { initialSpec } from "./utils";
import type { Report, Scenario, Run } from "./types";
afterEach(cleanup);
const scenario = (
  id: string,
  revenue: number,
  units: number,
  baseline = false,
): Scenario => ({
  plan_id: id,
  name: `Stratégie ${id}`,
  is_baseline: baseline,
  price_cents: 10000,
  mean_revenue_cents: revenue,
  median_revenue_cents: revenue,
  revenue_interval_cents: [revenue, revenue],
  mean_units: units,
  mean_spend_cents: 10000,
  mean_cac_cents: units ? 10000 / units : null,
  mean_paid_cac_cents: units ? 10000 / units : null,
  daily: [],
  channels: [],
  traces: [],
  adjustments: [],
  replicate_totals: [],
});
const report: Report = {
  schema_version: "1",
  engine_version: "test",
  product: initialSpec.product,
  population: 100,
  rounds: 30,
  seed: 42,
  winner_id: null,
  winner_reason: "Technical conditional test detail.",
  assumptions: [],
  personas: [],
  scenarios: [
    scenario("A", 20000, 2),
    scenario("B", 40000, 4),
    scenario("C", 30000, 3),
    scenario("baseline", 990000, 99, true),
  ],
  comparisons: [],
  metadata: {},
};
it("names the leading campaign, makes indecision explicit, and shows one scenario totals rather than adding alternatives", () => {
  render(<ResultOverview report={report} lang="fr" />);
  expect(
    screen.getByRole("heading", {
      name: /Aucune stratégie ne se détache avec certitude/,
    }),
  ).toBeTruthy();
  expect(
    screen.getByText(/Stratégie B.*CA virtuel le plus élevé/),
  ).toBeTruthy();
  const kpi = screen.getByRole("region", { name: "Résultats de Stratégie B" });
  expect(within(kpi).getByText("4", { exact: true })).toBeTruthy();
  expect(within(kpi).getByText(/400,00/)).toBeTruthy();
  expect(within(kpi).getByText(/100,00/)).toBeTruthy();
  expect(within(kpi).getByText(/25,00/)).toBeTruthy();
  expect(within(kpi).queryByText(/990/)).toBeNull();
});
it("states credibility is unevaluated for older reports", () => {
  render(<ResultOverview report={report} lang="fr" />);
  expect(
    screen.getByText("Crédibilité non évaluée — ancien modèle"),
  ).toBeTruthy();
});
it("presents extraordinary claims as unsubstantiated, never as verified efficacy or proven fraud", () => {
  render(
    <ResultOverview
      report={{
        ...report,
        metadata: {
          product_credibility: {
            status: "extraordinary_unsubstantiated",
            score: 0.01,
            scam_suspicion: 0.95,
            claims: ["Immortality"],
            reasons: ["No reliable evidence supplied"],
            required_evidence: ["Independent evidence"],
            source: "rule_based",
            version: "1",
          },
        },
      }}
      lang="fr"
    />,
  );
  expect(screen.getByText("Promesse extraordinaire non étayée")).toBeTruthy();
  expect(screen.getByText("No reliable evidence supplied")).toBeTruthy();
  expect(screen.queryByText("Fraude prouvée")).toBeNull();
});
it("shows an undefined acquisition cost as not calculable rather than a free acquisition", () => {
  render(
    <ResultOverview
      report={{ ...report, scenarios: [scenario("A", 0, 0)], winner_id: null }}
      lang="fr"
    />,
  );
  expect(screen.getByText("Non calculable")).toBeTruthy();
});
it("does not recommend a launch winner when every candidate has zero sales, even if a historical report names one", () => {
  render(
    <ResultOverview
      report={{
        ...report,
        scenarios: [
          scenario("A", 0, 0),
          scenario("B", 0, 0),
          scenario("C", 0, 0),
        ],
        winner_id: "B",
      }}
      lang="fr"
    />,
  );
  expect(
    screen.getByRole("heading", {
      name: "Aucune vente virtuelle dans ces scénarios.",
    }),
  ).toBeTruthy();
  expect(screen.queryByText("Stratégie retenue")).toBeNull();
  expect(screen.queryByText(/cette stratégie est le choix retenu/)).toBeNull();
});
it("offers an explicit resume action for a failed run", () => {
  const run: Run = {
    id: "failed",
    study_id: "study",
    status: "failed",
    progress: { percent: 40, message: "Stopped" },
    error: "Report serialization failed",
  };
  render(
    <RunMonitor
      run={run}
      busy={false}
      onCancel={vi.fn()}
      onResume={vi.fn()}
      onRefresh={vi.fn()}
    />,
  );
  expect(
    screen.getByRole("button", { name: /Resume checkpoint/ }),
  ).toBeTruthy();
});
