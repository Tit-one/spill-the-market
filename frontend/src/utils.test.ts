import { describe, it, expect } from "vitest";
import { money, percent, safeURL, validateSpec, initialSpec } from "./utils";
describe("report values retain their meaning", () => {
  it("distinguishes undefined CAC from zero CAC", () => {
    expect(money(null)).toBe("—");
    expect(money(0)).toContain("0.00");
    expect(percent(undefined)).toBe("—");
    expect(percent(0)).toBe("0%");
  });
  it("converts integer cents to money without multiplying totals", () => {
    expect(money(1490, "EUR", "en")).toContain("14.90");
    expect(money(1490, "EUR", "fr")).toContain("14,90");
  });
  it("never emits executable or non-web source links", () => {
    expect(safeURL("javascript:alert(1)")).toBe(null);
    expect(safeURL("file:///etc/passwd")).toBe(null);
    expect(safeURL("https://example.org/evidence")).toBe(
      "https://example.org/evidence",
    );
  });
});
describe("experiment bounds", () => {
  it("accepts the fictional study and rejects inverted age bands", () => {
    expect(validateSpec(initialSpec, "en")).toEqual([]);
    const s = structuredClone(initialSpec);
    s.audience.age_min = 65;
    s.audience.age_max = 18;
    expect(validateSpec(s, "en").join()).toContain("age");
  });
  it("rejects a representative sample larger than the numerical population", () => {
    const s = structuredClone(initialSpec);
    s.audience.population = 30;
    s.audience.representatives = 40;
    expect(validateSpec(s, "en").join()).toContain("Representative");
  });
});
