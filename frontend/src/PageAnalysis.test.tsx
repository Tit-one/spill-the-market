// @vitest-environment jsdom
import { beforeEach, afterEach, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import PageAnalysis from "./PageAnalysis";
import { validatePageSpec } from "./PageAnalysis";
import { api } from "./api";
import { initialSpec } from "./utils";
import type { Study } from "./types";
import type {
  PageAudit,
  PageProviders,
  PageSnapshot,
} from "./pageAnalysisTypes";
vi.mock("./api", () => ({ api: vi.fn() }));
const study: Study = {
  id: "study-A",
  spec: { ...initialSpec, api_budget_usd: 1 },
  plans: [],
  personas: [],
  research: {} as Study["research"],
  created_at: "2026-11-08T12:00:00Z",
  runs: [],
};
const snapshot: PageSnapshot = {
  id: "snapshot-A",
  variant_id: "A",
  section_index: 0,
  viewport: "desktop",
  width: 1200,
  height: 800,
  scroll_y: 0,
  page_height: 1600,
  content_hash: "hash",
  captured_at: "2026-11-08T12:00:00Z",
  image_url: "/api/v1/page-audits/images/snapshot-A",
  dom: [],
  provenance: "demo",
  warnings: [],
};
const audit: PageAudit = {
  id: "audit-A",
  study_id: study.id,
  status: "captured",
  progress: { phase: "capture", percent: 100, message: "Captured locally" },
  spec: {
    schema_version: "1.0",
    variants: [
      {
        id: "A",
        label: "Page A",
        source: "demo",
        url: null,
        html: null,
        screenshots: [],
      },
    ],
    viewports: ["desktop", "mobile"],
    max_sections: 3,
    persona_count: 8,
    direct_vision_count: 2,
    advertisement_context: "",
  },
  snapshots: [snapshot],
  report: null,
  error: null,
  cost: {},
  provider_id: null,
  created_at: "2026-11-08T12:00:00Z",
  updated_at: "2026-11-08T12:00:00Z",
};
const providers: PageProviders = {
  providers: [
    {
      id: "demo",
      name: "Fictional demonstration",
      model: "synthetic",
      scope: "local",
      available: true,
      reason: "",
      vision: false,
      pricing: {},
    },
    {
      id: "configured",
      name: "Configured vision",
      model: "my-vision-model",
      scope: "remote",
      available: true,
      reason: "",
      vision: true,
      pricing: { input_usd_per_million: 1 },
    },
  ],
  capture: { available: true, reason: "" },
};
let handler: (path: string, method: string, body?: unknown) => Promise<unknown>;
beforeEach(() => {
  vi.mocked(api).mockReset();
  handler = async (path, method) => {
    if (path === "/page-audit/providers") return providers;
    if (path.endsWith("/page-audits") && method === "GET")
      return { audits: [] };
    if (path.endsWith("/page-audits") && method === "POST")
      return structuredClone(audit);
    if (path.endsWith("/analyze")) return { ...audit, status: "completed" };
    throw new Error(path);
  };
  vi.mocked(api).mockImplementation(
    async (path, method = "GET", body) =>
      (await handler(path, method, body)) as never,
  );
});
afterEach(cleanup);
const show = (s = study) =>
  render(<PageAnalysis study={s} lang="en" onOpenBrief={vi.fn()} />);
async function capture() {
  await screen.findByRole("button", { name: "Capture locally" });
  fireEvent.click(screen.getByRole("button", { name: "Capture locally" }));
  await screen.findByRole("heading", { name: "Captured evidence" });
}
it("captures locally without dispatching any analysis", async () => {
  show();
  await capture();
  expect(
    vi.mocked(api).mock.calls.filter(([path]) => path.endsWith("/analyze")),
  ).toHaveLength(0);
  expect(screen.getByRole("img", { name: /Page A/ })).toBeTruthy();
});
it("requires named remote consent and sends only the selected provider after a separate action", async () => {
  show();
  await capture();
  fireEvent.change(
    screen.getByRole("combobox", { name: "Analysis provider / model" }),
    { target: { value: "configured" } },
  );
  const button = screen.getByRole("button", { name: "Analyse captured page" });
  expect(button.matches(":disabled")).toBe(true);
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: /Send the selected screenshots.*my-vision-model/,
    }),
  );
  expect(button.matches(":disabled")).toBe(false);
  fireEvent.click(button);
  await waitFor(() =>
    expect(
      vi
        .mocked(api)
        .mock.calls.some(
          ([path, , body]) =>
            path.endsWith("/analyze") &&
            JSON.stringify(body) ===
              '{"provider_id":"configured","allow_remote":true}',
        ),
    ).toBe(true),
  );
});
it("does not offer synthetic analysis for real captured evidence", async () => {
  const real = {
    ...structuredClone(audit),
    snapshots: [{ ...snapshot, provenance: "public_url" as const }],
  };
  const base = handler;
  handler = async (path, method, body) =>
    path.endsWith("/page-audits") && method === "POST"
      ? real
      : base(path, method, body);
  show();
  await capture();
  expect(
    screen
      .getByRole("button", { name: "Analyse captured page" })
      .matches(":disabled"),
  ).toBe(true);
  expect(
    screen.getByText(/Demo analysis only accepts fictional captures/),
  ).toBeTruthy();
});
it("locks duplicate capture and draft edits while pending", async () => {
  let resolve!: (a: PageAudit) => void;
  const pending = new Promise<PageAudit>((yes) => (resolve = yes));
  const base = handler;
  handler = async (path, method, body) =>
    path.endsWith("/page-audits") && method === "POST"
      ? pending
      : base(path, method, body);
  show();
  await screen.findByRole("button", { name: "Capture locally" });
  fireEvent.click(screen.getByRole("button", { name: "Capture locally" }));
  fireEvent.click(screen.getByRole("button", { name: "Capture locally" }));
  expect(
    screen
      .getByRole("textbox", { name: "Variant A label" })
      .matches(":disabled"),
  ).toBe(true);
  expect(
    vi
      .mocked(api)
      .mock.calls.filter(
        ([path, method]) => path.endsWith("/page-audits") && method === "POST",
      ),
  ).toHaveLength(1);
  resolve(audit);
  await screen.findByRole("heading", { name: "Captured evidence" });
});
it("discards late audit responses after selecting another study", async () => {
  let resolve!: (a: PageAudit) => void;
  const pending = new Promise<PageAudit>((yes) => (resolve = yes));
  const base = handler;
  handler = async (path, method, body) =>
    path.endsWith("/page-audits") && method === "POST"
      ? pending
      : base(path, method, body);
  const rendered = show();
  await screen.findByRole("button", { name: "Capture locally" });
  fireEvent.click(screen.getByRole("button", { name: "Capture locally" }));
  rendered.rerender(
    <PageAnalysis
      study={{ ...study, id: "study-B" }}
      lang="en"
      onOpenBrief={vi.fn()}
    />,
  );
  resolve({ ...audit, cost: { marker: "COST_A" } });
  await waitFor(() =>
    expect(
      vi
        .mocked(api)
        .mock.calls.some(([path]) => path === "/studies/study-B/page-audits"),
    ).toBe(true),
  );
  expect(
    screen.queryByRole("heading", { name: "Captured evidence" }),
  ).toBeNull();
  expect(screen.queryByText(/COST_A/)).toBeNull();
});

it("serves images through the audit-scoped local route", async () => {
  show();
  await capture();
  expect(screen.getByRole("img", { name: /Page A/ }).getAttribute("src")).toBe(
    "/api/v1/page-audits/audit-A/images/snapshot-A",
  );
});

it("renders French comparison labels without encoding replacement characters", async () => {
  const completed = {
    ...audit,
    status: "completed",
    report: {
      schema_version: "1",
      audit_id: audit.id,
      study_id: study.id,
      mode: "demo",
      created_at: audit.created_at,
      observations: [],
      reviews: [],
      findings: [],
      comparisons: [
        {
          variant_a: "A",
          variant_b: "B",
          viewport: "desktop",
          persona_count: 8,
          paired_count: 8,
        },
      ],
      direct_vision_controls: [],
      audience_coverage: {},
      cost: {},
      limitations: [],
    },
  };
  const base = handler;
  handler = async (path, method, body) =>
    path.endsWith("/page-audits") && method === "GET"
      ? { audits: [completed] }
      : base(path, method, body);
  render(<PageAnalysis study={study} lang="fr" onOpenBrief={vi.fn()} />);
  expect(
    await screen.findByRole("columnheader", { name: "Personas appariés" }),
  ).toBeTruthy();
});
it("rejects out-of-bound section and sample values before capture dispatch", () => {
  expect(validatePageSpec({ ...audit.spec, max_sections: 0 })).not.toBeNull();
  expect(validatePageSpec({ ...audit.spec, persona_count: 25 })).not.toBeNull();
  expect(
    validatePageSpec({ ...audit.spec, direct_vision_count: 5 }),
  ).not.toBeNull();
});
it("shows paired and direct-control tables while keeping later-section reactions out of the first view", async () => {
  const future = {
    ...snapshot,
    id: "snapshot-next",
    section_index: 1,
    scroll_y: 800,
  };
  const review = {
    persona_id: "person-one",
    age: 61,
    variant_id: "A",
    snapshot_id: snapshot.id,
    viewport: "desktop" as const,
    step: 0,
    mode: "observation" as const,
    visible_information_ids: ["heading"],
    understanding: "First screen understanding",
    questions: ["First screen question"],
    positives: [],
    frictions: [],
    confidence: 0.5,
    trust: 0.6,
    intention_before: 0.2,
    intention_after: 0.3,
    intended_action: "scroll" as const,
    evidence_ids: ["heading"],
  };
  const completed = {
    ...audit,
    status: "completed" as const,
    snapshots: [snapshot, future],
    report: {
      schema_version: "1",
      audit_id: audit.id,
      study_id: study.id,
      mode: "demo",
      created_at: audit.created_at,
      observations: [],
      reviews: [
        review,
        {
          ...review,
          snapshot_id: future.id,
          step: 1,
          understanding: "Later secret understanding",
          questions: ["Later secret question"],
        },
      ],
      findings: [],
      comparisons: [
        {
          variant_a: "A",
          variant_b: "B",
          viewport: "desktop",
          persona_count: 8,
          paired_count: 8,
          mean_intention_a: 0.3,
          mean_intention_b: 0.4,
          mean_intention_delta: 0.1,
          mean_trust_delta: 0.05,
          status: "conditional",
          limitations: [],
        },
      ],
      direct_vision_controls: [
        {
          persona_id: "person-one",
          age: 61,
          variant_id: "A",
          viewport: "desktop",
          snapshot_id: snapshot.id,
          step: 0,
          intention_delta: 0.1,
          trust_delta: 0,
          understanding_differs: true,
          status: "paired",
        },
      ],
      audience_coverage: {},
      cost: {},
      limitations: [],
    },
  };
  const base = handler;
  handler = async (path, method, body) =>
    path.endsWith("/page-audits") && method === "GET"
      ? { audits: [completed] }
      : base(path, method, body);
  show();
  await screen.findByText("First screen question");
  expect(screen.queryByText("Later secret question")).toBeNull();
  expect(
    screen.getByRole("columnheader", { name: "Paired personas" }),
  ).toBeTruthy();
  expect(
    screen.getByRole("columnheader", { name: "Understanding differs" }),
  ).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "A · Desktop · Section 2" }),
  );
  expect(screen.getByText("Later secret question")).toBeTruthy();
});
