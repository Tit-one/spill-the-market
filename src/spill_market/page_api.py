"""Product-page capture and explicit-analysis HTTP endpoints."""
import re

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

from .gateway import BudgetLedger
from .page_jobs import reconcile_page_workers, spawn_page_worker
from .page_models import AnalyzePageRequest, PageAuditSpec
from .page_store import PageAuditStore


def validate_page_analysis(pages, identifier, payload):
    from .page_vision import vision_provider_status
    from .storage import ActiveRunError
    audit = pages.get(identifier, internal=True)
    if audit["status"] != "captured":
        raise ActiveRunError("Capture must finish before analysis")
    provider = next(p for p in vision_provider_status() if p["id"] == payload.provider_id)
    if not provider["available"]:
        raise ValueError(provider["reason"])
    if payload.provider_id == "demo" and any(s["provenance"] != "demo" for s in audit["snapshots"]):
        raise ValueError("Demo analysis is only available for fictional demo captures; select a visual model")
    if provider["scope"] == "remote":
        if not payload.allow_remote:
            raise ValueError("Explicit permission is required to send screenshots and persona context to this provider")
        if audit["study_snapshot"]["spec"]["api_budget_usd"] <= 0:
            raise ValueError("Create a study with a positive real API budget before remote visual analysis")


def install_page_routes(app, store, *, launch_workers: bool):
    pages = PageAuditStore(store)
    app.state.page_store = pages

    def reconcile():
        if launch_workers:
            reconcile_page_workers(pages)

    def public(identifier):
        audit = pages.get(identifier)
        study_spec = store.get_study(audit["study_id"])["spec"]
        budget = store.root / "budgets" / f"{audit['study_id']}.sqlite"
        if budget.is_file():
            audit["cost"] = BudgetLedger(budget, study_spec["api_budget_usd"], study_spec["api_max_calls"]).summary()
        return audit

    @app.get("/api/v1/page-audit/providers")
    def providers():
        from .page_capture import capture_available
        from .page_vision import vision_provider_status
        return {"providers": vision_provider_status(), "capture": capture_available()}

    @app.get("/api/v1/studies/{study_id}/page-audits")
    def list_audits(study_id: str):
        reconcile()
        return {"audits": pages.list(study_id)}

    @app.post("/api/v1/studies/{study_id}/page-audits", status_code=202)
    def capture(study_id: str, payload: PageAuditSpec):
        reconcile()
        if launch_workers and len(pages.active()) >= 2:
            raise HTTPException(409, "Two page workers are already active; wait for one to finish")
        audit = pages.create(study_id, payload)
        if launch_workers:
            spawn_page_worker(pages, audit["id"])
        return public(audit["id"])

    @app.get("/api/v1/page-audits/{identifier}")
    def get_audit(identifier: str):
        reconcile()
        return public(identifier)

    @app.post("/api/v1/page-audits/{identifier}/analyze", status_code=202)
    def analyze(identifier: str, payload: AnalyzePageRequest):
        reconcile()
        validate_page_analysis(pages, identifier, payload)
        pages.start_analysis(identifier, payload)
        if launch_workers:
            spawn_page_worker(pages, identifier)
        return public(identifier)

    @app.post("/api/v1/page-audits/{identifier}/cancel")
    def cancel(identifier: str):
        pages.request_cancel(identifier)
        return public(identifier)

    @app.post("/api/v1/page-audits/{identifier}/resume", status_code=202)
    def resume(identifier: str):
        reconcile()
        pages.prepare_resume(identifier)
        if launch_workers:
            spawn_page_worker(pages, identifier)
        return public(identifier)

    @app.get("/api/v1/page-audits/{identifier}/images/{snapshot_id}")
    def image(identifier: str, snapshot_id: str):
        audit = pages.get(identifier)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", snapshot_id) or not any(s["id"] == snapshot_id for s in audit["snapshots"]):
            raise HTTPException(404, "Snapshot not found in this audit")
        path = pages.assets_dir(identifier) / f"{snapshot_id}.jpg"
        if not path.is_file():
            raise HTTPException(404, "Snapshot image missing")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})

    @app.get("/api/v1/page-audits/{identifier}/export")
    def export(identifier: str, format: str = "json"):
        from .page_exports import export_page_audit
        audit = public(identifier)
        if audit["status"] != "completed" or not audit["report"]:
            raise HTTPException(409, "Complete the analysis before exporting")
        content, media_type, name = export_page_audit(audit, pages.assets_dir(identifier), format)
        return Response(content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{name}"'})
