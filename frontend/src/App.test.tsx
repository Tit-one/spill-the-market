// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import App from "./App";
import { api } from "./api";
import { initialSpec } from "./utils";
import type { Bootstrap, Study, Run, MediaPlan } from "./types";

vi.mock("./api", () => ({ api: vi.fn(), setToken: vi.fn() }));
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
const plan = (id: string): MediaPlan => ({
  id,
  name: `Plan ${id}`,
  description: "A launch candidate",
  price_cents: 1490,
  media_budget_cents: 100000,
  placements: [],
  adaptive: true,
  intensity: "balanced",
  rationale: [],
});
function study(id: string, name = "Orbit Orchard"): Study {
  return {
    id,
    spec: {
      ...structuredClone(initialSpec),
      product: { ...initialSpec.product, name },
    },
    plans: ["a", "b", "c"].map(plan),
    personas: [],
    research: {
      schema_version: "1",
      topic: "Evidence",
      mode: "demo",
      created_at: "2026-11-07T12:00:00Z",
      language: "en",
      region: "global",
      sources: [],
      trends: [],
      pain_points: [],
      jargon: [],
      segments: [],
      coverage: {},
      limitations: [],
      recommended_age_range: null,
    },
    created_at: "2026-11-07T12:00:00Z",
    runs: [],
  };
}
const a = study("study-a"),
  b = study("study-b", "FrameBridge");
const bootstrap: Bootstrap = {
  version: "0.1",
  session_token: "local-test-token",
  capabilities: {},
  channels: [],
  provider_status: {
    tavily: false,
    firecrawl: false,
    llm: false,
    llm_model: null,
    configuration: "environment",
  },
  examples: [
    { id: "game", name: a.spec.product.name, spec: a.spec },
    { id: "software", name: b.spec.product.name, spec: b.spec },
  ],
};
let handler: (path: string, method: string, body?: unknown) => Promise<unknown>;
beforeEach(() => {
  localStorage.clear();
  window.scrollTo = vi.fn();
  vi.mocked(api).mockReset();
  handler = async (path, method) => {
    if (path === "/bootstrap") return bootstrap;
    if (path === "/studies" && method === "GET") return { studies: [a, b] };
    if (path === "/studies/study-a") return structuredClone(a);
    if (path === "/studies/study-b") return structuredClone(b);
    throw new Error(`Unexpected request ${method} ${path}`);
  };
  vi.mocked(api).mockImplementation(
    async (path, method = "GET", body) =>
      (await handler(path, method, body)) as never,
  );
});
afterEach(cleanup);
async function openA() {
  render(<App />);
  await screen.findByRole("combobox", { name: "Saved experiments" });
  fireEvent.change(
    screen.getByRole("combobox", { name: "Saved experiments" }),
    { target: { value: a.id } },
  );
  await screen.findByRole("textbox", { name: "Strategy name" });
}
const nav = (label: string) =>
  screen.getByRole("button", { name: new RegExp(`^${label}`) });

describe("notebook lifecycle regressions", () => {
  it("holds example switching and draft edits while preparation is pending", async () => {
    const pending = deferred<Study>();
    const base = handler;
    handler = async (path, method, body) =>
      path === "/studies" && method === "POST"
        ? pending.promise
        : base(path, method, body);
    render(<App />);
    const prepare = await screen.findByRole("button", {
      name: "Prepare experiment",
    });
    await waitFor(() => expect(prepare.matches(":disabled")).toBe(false));
    fireEvent.click(prepare);
    const example = screen.getByRole("button", { name: /FrameBridge/ });
    expect(example.matches(":disabled")).toBe(true);
    expect(
      screen
        .getByRole("textbox", { name: "Product name" })
        .matches(":disabled"),
    ).toBe(true);
    fireEvent.click(example);
    expect(
      (
        screen.getByRole("textbox", {
          name: "Product name",
        }) as HTMLInputElement
      ).value,
    ).toBe("Orbit Orchard");
    pending.resolve(structuredClone(a));
    await screen.findByRole("textbox", { name: "Strategy name" });
  });
  it("holds media edits until a save response is applied", async () => {
    const pending = deferred<Study>();
    const base = handler;
    let submitted: MediaPlan[] = [];
    handler = async (path, method, body) => {
      if (path.endsWith("/plans") && method === "PUT") {
        submitted = (body as { plans: MediaPlan[] }).plans;
        return pending.promise;
      }
      return base(path, method, body);
    };
    await openA();
    const name = screen.getByRole("textbox", { name: "Strategy name" });
    fireEvent.change(name, { target: { value: "Saved edit" } });
    fireEvent.click(screen.getByRole("button", { name: "Save plans" }));
    expect(name.matches(":disabled")).toBe(true);
    expect(nav("The brief").matches(":disabled")).toBe(true);
    fireEvent.change(name, { target: { value: "Late edit" } });
    pending.resolve({ ...structuredClone(a), plans: submitted });
    await waitFor(() => expect(name.matches(":disabled")).toBe(false));
    expect((name as HTMLInputElement).value).toBe("Saved edit");
  });
  it.each(["example", "open", "prepare"] as const)(
    "does not display study A costs after a %s boundary",
    async (boundary) => {
      const base = handler;
      handler = async (path, method, body) => {
        if (path.endsWith("/research"))
          return { report: a.research, cost: { marker: "LEDGER_FOR_A" } };
        if (path === "/studies" && method === "POST") return study("new-study");
        return base(path, method, body);
      };
      await openA();
      fireEvent.click(nav("Evidence"));
      fireEvent.click(
        screen.getByRole("button", { name: "Analyse selected evidence" }),
      );
      await screen.findByText("Research cost ledger");
      fireEvent.click(nav("The brief"));
      if (boundary === "example")
        fireEvent.click(screen.getByRole("button", { name: /FrameBridge/ }));
      if (boundary === "open") {
        fireEvent.change(
          screen.getByRole("combobox", { name: "Saved experiments" }),
          { target: { value: b.id } },
        );
        await waitFor(() =>
          expect(
            screen.getByRole("heading", { name: "Three ways to show up." }),
          ).toBeTruthy(),
        );
      }
      if (boundary === "prepare") {
        fireEvent.click(
          screen.getByRole("button", { name: "Prepare experiment" }),
        );
        await screen.findByRole("textbox", { name: "Strategy name" });
      }
      fireEvent.click(nav("Evidence"));
      expect(screen.queryByText("Research cost ledger")).toBeNull();
      expect(screen.queryByText(/LEDGER_FOR_A/)).toBeNull();
    },
  );
  it("keeps edited plans marked unsaved if canonical refresh after run creation fails", async () => {
    const base = handler;
    let started = false;
    const created: Run = {
      id: "run-one",
      study_id: a.id,
      status: "completed",
      progress: { percent: 100, message: "Complete" },
    };
    handler = async (path, method, body) => {
      if (path.endsWith("/runs") && method === "POST") {
        started = true;
        return created;
      }
      if (path === `/studies/${a.id}` && started)
        throw new Error("Canonical refresh failed");
      return base(path, method, body);
    };
    await openA();
    fireEvent.change(screen.getByRole("textbox", { name: "Strategy name" }), {
      target: { value: "Unconfirmed saved edit" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run experiment" }));
    await screen.findByText("Canonical refresh failed");
    fireEvent.click(nav("Media plans"));
    expect(
      screen.getByRole("button", { name: "Save plans" }).matches(":disabled"),
    ).toBe(false);
    expect(
      (
        screen.getByRole("textbox", {
          name: "Strategy name",
        }) as HTMLInputElement
      ).value,
    ).toBe("Unconfirmed saved edit");
  });
  it("synchronizes canonical plans and run history at creation and terminal polling without reopening", async () => {
    const base = handler;
    let runs: Run[] = [];
    let savedPlans = structuredClone(a.plans);
    let count = 0;
    handler = async (path, method, body) => {
      if (path === `/studies/${a.id}`)
        return { ...structuredClone(a), plans: savedPlans, runs };
      if (path.endsWith("/runs") && method === "POST") {
        savedPlans = (body as { plans: MediaPlan[] }).plans;
        const created: Run = {
          id: `run-${++count}`,
          study_id: a.id,
          status: "queued",
          progress: { percent: 0, message: "Queued" },
        };
        runs = [created, ...runs];
        return created;
      }
      if (path.startsWith("/runs/run-")) {
        const id = path.split("/").at(-1)!;
        const completed = {
          ...runs.find((r) => r.id === id)!,
          status: "completed",
          progress: { percent: 100, message: "Complete" },
        };
        runs = runs.map((r) => (r.id === id ? completed : r));
        return completed;
      }
      return base(path, method, body);
    };
    await openA();
    fireEvent.change(
      screen.getByRole("spinbutton", { name: "Candidate price (EUR)" }),
      { target: { value: "23" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Run experiment" }));
    await screen.findByRole(
      "button",
      { name: "run-1 · Completed" },
      { timeout: 4000 },
    );
    expect(savedPlans[0].price_cents).toBe(2300);
    fireEvent.click(nav("Media plans"));
    expect(
      (
        screen.getByRole("spinbutton", {
          name: "Candidate price (EUR)",
        }) as HTMLInputElement
      ).value,
    ).toBe("23");
    expect(
      screen.getByRole("button", { name: "Save plans" }).matches(":disabled"),
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Run experiment" }));
    await screen.findByRole(
      "button",
      { name: "run-2 · Completed" },
      { timeout: 4000 },
    );
    expect(
      screen.getByRole("button", { name: "run-1 · Completed" }),
    ).toBeTruthy();
  });
});
