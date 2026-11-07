import { describe, it, expect } from "vitest";
import { WorkspaceRequests } from "./workspaceRequests";
describe("notebook request ownership", () => {
  it("locks immediately, before a React busy render can occur", () => {
    const gate = new WorkspaceRequests();
    const first = gate.begin()!;
    expect(gate.begin()).toBeNull();
    expect(first.finish()).toBe(true);
    expect(gate.begin()).not.toBeNull();
  });
  it("rejects late notebook responses and prevents stale cleanup unlocking a newer request", () => {
    const gate = new WorkspaceRequests();
    const notebookA = gate.begin()!;
    gate.invalidate();
    const notebookB = gate.begin()!;
    expect(notebookA.current()).toBe(false);
    expect(notebookA.finish()).toBe(false);
    expect(gate.pending).toBe(true);
    expect(notebookB.current()).toBe(true);
  });
});
