// @vitest-environment jsdom
import { it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import PageOverview from "./PageOverview";
import type { PageAuditReport, PersonaPageReview } from "./pageAnalysisTypes";
afterEach(cleanup);
const review = (id: string, age: number, step: number): PersonaPageReview => ({
  persona_id: id,
  age,
  step,
  variant_id: "A",
  snapshot_id: "image",
  viewport: "desktop",
  mode: "observation",
  visible_information_ids: [],
  understanding: "The product is a creative workspace.",
  questions: ["Is there a trial?"],
  positives: [],
  frictions: ["The conditions are unclear."],
  confidence: 0.5,
  trust: 0.5,
  intention_before: 0.2,
  intention_after: 0.3,
  intended_action: "seek_information",
  evidence_ids: [],
});
const report: PageAuditReport = {
  schema_version: "1",
  audit_id: "audit",
  study_id: "study",
  mode: "vision",
  created_at: "2026-11-08",
  observations: [],
  reviews: [
    review("young", 30, 0),
    review("young", 30, 1),
    review("older", 60, 0),
  ],
  findings: [
    {
      id: "issue",
      severity: "high",
      text: "The price conditions need clarification.",
      snapshot_id: "image",
    },
  ],
  comparisons: [],
  direct_vision_controls: [],
  audience_coverage: {},
  cost: {},
  limitations: [],
};
it("leads with concrete findings and age-group questions, counting each persona once", () => {
  render(<PageOverview report={report} lang="fr" onInspect={vi.fn()} />);
  expect(
    screen.getByRole("heading", { name: "Ce qui ressort de la lecture" }),
  ).toBeTruthy();
  expect(
    screen.getByText("The price conditions need clarification."),
  ).toBeTruthy();
  expect(
    screen.getByRole("columnheader", { name: "Questions exprimées" }),
  ).toBeTruthy();
  expect(screen.getByText("55–74 ans")).toBeTruthy();
  expect(screen.getByText("2", { exact: true })).toBeTruthy();
  expect(screen.queryByText("3 personnes")).toBeNull();
});
it("labels demonstration reading as fictional at the report overview", () => {
  render(
    <PageOverview
      report={{ ...report, mode: "demo" }}
      lang="fr"
      onInspect={vi.fn()}
    />,
  );
  expect(
    screen.getByText("Démonstration fictive — aucune lecture par IA visuelle"),
  ).toBeTruthy();
});
