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
import type { Bootstrap, Study, Run, MediaPlan, StudySpec } from "./types";

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
  async function fillQuickProduct() {
    await screen.findByRole("combobox", { name: "Saved experiments" });
    fireEvent.change(screen.getByRole("textbox", { name: "Product name" }), {
      target: { value: "A real product" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /What does it do/ }), {
      target: {
        value:
          "An everyday product with a clear benefit and stated requirements.",
      },
    });
    fireEvent.change(
      screen.getByRole("spinbutton", {
        name: "Selling price (EUR)",
      }),
      { target: { value: "49" } },
    );
  }
  const queued: Run = {
    id: "quick-run",
    study_id: "quick-study",
    status: "queued",
    progress: { percent: 0, message: "Queued direct launch" },
  };
  it("launches a known-audience campaign once and adopts its run and history without a manual preparation step", async () => {
    const pending = deferred<{ study: Study; run: Run }>();
    const base = handler;
    handler = async (path, method, body) =>
      path === "/studies/launch" && method === "POST"
        ? pending.promise
        : base(path, method, body);
    render(<App />);
    await fillQuickProduct();
    fireEvent.change(screen.getByRole("spinbutton", { name: "Minimum age" }), {
      target: { value: "25" },
    });
    fireEvent.change(screen.getByRole("spinbutton", { name: "Maximum age" }), {
      target: { value: "45" },
    });
    fireEvent.click(screen.getByRole("radio", { name: /Find my market/ }));
    fireEvent.click(screen.getByRole("radio", { name: /I know my audience/ }));
    const button = screen.getByRole("button", {
      name: "Launch my campaign",
    });
    fireEvent.click(button);
    fireEvent.submit(button.closest("form")!);
    expect(
      vi.mocked(api).mock.calls.filter(([path]) => path === "/studies/launch"),
    ).toHaveLength(1);
    expect(
      screen
        .getByRole("textbox", { name: "Product name" })
        .matches(":disabled"),
    ).toBe(true);
    const body = vi
      .mocked(api)
      .mock.calls.find(([path]) => path === "/studies/launch")![2] as {
      spec: StudySpec;
    };
    expect(body.spec.objective).toBe("campaign");
    expect(body.spec.use_representative_llm).toBe(false);
    expect([body.spec.audience.age_min, body.spec.audience.age_max]).toEqual([
      25, 45,
    ]);
    const launched = {
      ...study("quick-study", "A real product"),
      spec: body.spec,
      runs: [queued],
    };
    pending.resolve({ study: launched, run: queued });
    await screen.findByText(/Queued direct launch/);
    expect(screen.getByRole("heading", { name: "Saved runs" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /quick-ru/ })).toBeTruthy();
  });
  it("explores broad adult ages with optional controlled URLs and no inherited paid research settings", async () => {
    let sent: StudySpec | undefined;
    const base = handler;
    handler = async (path, method, body) => {
      if (path === "/studies/launch" && method === "POST") {
        sent = (body as { spec: StudySpec }).spec;
        return {
          study: { ...study("quick-study"), spec: sent, runs: [queued] },
          run: queued,
        };
      }
      return base(path, method, body);
    };
    render(<App />);
    await fillQuickProduct();
    fireEvent.click(screen.getByRole("radio", { name: /Find my market/ }));
    expect(
      screen.queryByRole("spinbutton", { name: "Minimum age" }),
    ).toBeNull();
    expect(screen.getByText(/^Exploration across ages 18–75/)).toBeTruthy();
    fireEvent.click(screen.getByText("Enrich with sources", { exact: true }));
    fireEvent.change(
      screen.getByRole("textbox", {
        name: "Product page URL (optional)",
      }),
      { target: { value: "https://example.org/product" } },
    );
    fireEvent.change(
      screen.getByRole("textbox", {
        name: "Competitor URLs (one per line)",
      }),
      { target: { value: "https://example.org/competitor" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Explore my market" }));
    await screen.findByText(/Queued direct launch/);
    expect(sent?.objective).toBe("market_discovery");
    expect([sent?.audience.age_min, sent?.audience.age_max]).toEqual([18, 75]);
    expect(sent?.audience.region).toBe("France");
    expect(sent?.research.language).toBe("fr");
    expect(sent?.research.use_llm).toBe(false);
    expect(sent?.research.use_firecrawl).toBe(false);
    expect(sent?.market?.competitor_urls).toEqual([
      "https://example.org/competitor",
    ]);
    expect(sent?.market?.product_url).toBe("https://example.org/product");
  });
  it("keeps a successfully launched run when optional source collection returns a warning", async () => {
    const base = handler;
    handler = async (path, method, body) =>
      path === "/studies/launch" && method === "POST"
        ? {
            study: { ...study("quick-study"), runs: [queued] },
            run: queued,
            research_error: "The supplied source could not be read.",
          }
        : base(path, method, body);
    render(<App />);
    await fillQuickProduct();
    fireEvent.click(screen.getByRole("button", { name: "Launch my campaign" }));
    await screen.findByText(/Queued direct launch/);
    expect(
      screen.getByText(/The supplied source could not be read/),
    ).toBeTruthy();
    expect(
      vi.mocked(api).mock.calls.filter(([path]) => path === "/studies/launch"),
    ).toHaveLength(1);
  });
  it("opens an older saved study as a campaign without changing its ages or launching again", async () => {
    await openA();
    fireEvent.click(nav("The brief"));
    expect(
      (
        screen.getByRole("radio", {
          name: /I know my audience/,
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);
    expect(
      (
        screen.getByRole("spinbutton", {
          name: "Minimum age",
        }) as HTMLInputElement
      ).value,
    ).toBe("18");
    expect(
      (
        screen.getByRole("spinbutton", {
          name: "Maximum age",
        }) as HTMLInputElement
      ).value,
    ).toBe("65");
    expect(
      vi.mocked(api).mock.calls.some(([path]) => path === "/studies/launch"),
    ).toBe(false);
  });
  it("preserves explicit imported research when a saved demo-mode study switches to market discovery", async () => {
    const imported = study("imported-study", "My saved product");
    imported.spec.research = {
      ...imported.spec.research,
      mode: "demo",
      topic: "User supplied accessibility research",
      documents: [
        {
          name: "Customer interviews",
          text: "Customers described migration effort and accessibility requirements.",
        },
      ],
      urls: ["https://example.org/user-supplied-evidence"],
    };
    let submitted: StudySpec | undefined;
    const base = handler;
    handler = async (path, method, body) => {
      if (path === "/studies" && method === "GET")
        return { studies: [imported] };
      if (path === "/studies/imported-study") return structuredClone(imported);
      if (path === "/studies/launch" && method === "POST") {
        submitted = (body as { spec: StudySpec }).spec;
        return {
          study: {
            ...imported,
            id: queued.study_id,
            spec: submitted,
            runs: [queued],
          },
          run: queued,
        };
      }
      return base(path, method, body);
    };
    render(<App />);
    await screen.findByRole("combobox", { name: "Saved experiments" });
    fireEvent.change(
      screen.getByRole("combobox", { name: "Saved experiments" }),
      { target: { value: imported.id } },
    );
    await screen.findByRole("textbox", { name: "Strategy name" });
    fireEvent.click(nav("The brief"));
    fireEvent.click(screen.getByRole("radio", { name: /Find my market/ }));
    fireEvent.click(screen.getByRole("button", { name: "Explore my market" }));
    await screen.findByText(/Queued direct launch/);
    expect(submitted?.research.mode).toBe("offline");
    expect(submitted?.research.topic).toBe(imported.spec.research.topic);
    expect(submitted?.research.documents).toEqual(
      imported.spec.research.documents,
    );
    expect(submitted?.research.urls).toEqual(imported.spec.research.urls);
    expect(submitted?.research.use_llm).toBe(false);
    expect(submitted?.research.use_firecrawl).toBe(false);
  });
  it("starts with a neutral product and loads a fictional example only after choosing it", async () => {
    render(<App />);
    await screen.findByRole("combobox", { name: "Saved experiments" });
    expect(
      (
        screen.getByRole("textbox", {
          name: "Product name",
        }) as HTMLInputElement
      ).value,
    ).toBe("");
    expect(
      (
        screen.getByRole("textbox", {
          name: /What does it do/,
        }) as HTMLTextAreaElement
      ).value,
    ).toBe("");
    fireEvent.click(screen.getByRole("button", { name: /Orbit Orchard/ }));
    expect(
      (
        screen.getByRole("textbox", {
          name: "Product name",
        }) as HTMLInputElement
      ).value,
    ).toBe("Orbit Orchard");
  });
  it("detaches inherited game keywords when an example becomes another product", async () => {
    render(<App />);
    await screen.findByRole("combobox", { name: "Saved experiments" });
    fireEvent.click(screen.getByRole("button", { name: /Orbit Orchard/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Product name" }), {
      target: { value: "My own physical product" },
    });
    fireEvent.click(
      screen.getByRole("button", {
        name: "Product assumptions and advanced settings",
      }),
    );
    expect(
      (
        screen.getByRole("textbox", {
          name: /Keywords used for the audience/,
        }) as HTMLInputElement
      ).value,
    ).toBe("");
  });
  it("preserves explicitly edited keywords when an example becomes another product", async () => {
    render(<App />);
    await screen.findByRole("combobox", { name: "Saved experiments" });
    fireEvent.click(screen.getByRole("button", { name: /Orbit Orchard/ }));
    fireEvent.click(
      screen.getByRole("button", {
        name: "Product assumptions and advanced settings",
      }),
    );
    const keywords = screen.getByRole("textbox", {
      name: /Keywords used for the audience/,
    });
    fireEvent.change(keywords, { target: { value: "handmade, local" } });
    fireEvent.blur(keywords);
    fireEvent.change(screen.getByRole("textbox", { name: "Product name" }), {
      target: { value: "My own physical product" },
    });
    expect(
      (
        screen.getByRole("textbox", {
          name: /Keywords used for the audience/,
        }) as HTMLInputElement
      ).value,
    ).toBe("handmade, local");
  });
  it("renders the French page-analysis heading with intact accents", async () => {
    await openA();
    fireEvent.click(screen.getByRole("button", { name: "Switch to French" }));
    fireEvent.click(screen.getByRole("button", { name: /^La page/ }));
    expect(
      screen.getByRole("heading", {
        name: "Que se passe-t-il après le clic ?",
      }),
    ).toBeTruthy();
  });
  it("holds example switching and draft edits while preparation is pending", async () => {
    const pending = deferred<Study>();
    const base = handler;
    handler = async (path, method, body) =>
      path === "/studies" && method === "POST"
        ? pending.promise
        : base(path, method, body);
    render(<App />);
    await screen.findByRole("combobox", { name: "Saved experiments" });
    fireEvent.click(
      screen.getByRole("button", {
        name: "Product assumptions and advanced settings",
      }),
    );
    const prepare = await screen.findByRole("button", {
      name: "Prepare experiment",
    });
    await waitFor(() => expect(prepare.matches(":disabled")).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: /Orbit Orchard/ }));
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
          screen.getByRole("button", {
            name: "Product assumptions and advanced settings",
          }),
        );
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
