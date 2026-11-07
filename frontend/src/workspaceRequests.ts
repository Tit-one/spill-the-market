/** Synchronous operation lock plus generation guard for selected-notebook requests. */
export interface OperationTicket {
  current(): boolean;
  finish(): boolean;
}
export class WorkspaceRequests {
  private generation = 0;
  private active: number | null = null;
  get pending() {
    return this.active !== null;
  }
  begin(): OperationTicket | null {
    if (this.pending) return null;
    const generation = ++this.generation;
    this.active = generation;
    const current = () =>
      this.active === generation && this.generation === generation;
    return {
      current,
      finish: () => {
        if (!current()) return false;
        this.active = null;
        return true;
      },
    };
  }
  invalidate() {
    this.generation++;
    this.active = null;
  }
}
