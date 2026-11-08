"""Loopback-only application API. All writes require a local-session token."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .examples import examples
from .exports import export_report
from .gateway import BudgetExceeded
from .jobs import reconcile_workers, spawn_worker
from .models import CreateStudyRequest, MediaPlan, ResearchRequest, StartRunRequest, StudySpec
from .research import ResearchUncertain
from .storage import ActiveRunError, Store


def provider_status() -> dict:
    return {
        "tavily": bool(os.environ.get("TAVILY_API_KEY")),
        "firecrawl": bool(os.environ.get("FIRECRAWL_API_KEY")),
        "llm": bool(os.environ.get("SPILL_LLM_API_KEY")),
        "llm_model": os.environ.get("SPILL_LLM_MODEL") or None,
        "configuration": "environment",
    }


def validate_plans(spec: StudySpec, plans: list[MediaPlan]):
    if len(plans) != 3 or len({p.id for p in plans}) != 3:
        raise ValueError("Exactly three strategies with unique IDs are required")
    if any(p.media_budget_cents != spec.media_budget_cents for p in plans):
        raise ValueError("All strategies must use the study's same virtual media budget")


def create_app(data_dir: str | Path | None = None, *, launch_workers=True) -> FastAPI:
    store = Store(data_dir)
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        if launch_workers:
            reconcile_workers(store, include_unstarted=True)
            from .page_jobs import reconcile_page_workers
            from .page_store import PageAuditStore
            reconcile_page_workers(PageAuditStore(store), include_unstarted=True)
        yield

    app = FastAPI(title="Spill the Market", version=__version__, lifespan=lifespan)
    app.state.store = store
    app.state.session_token = token

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        host = request.url.hostname
        permitted_hosts = {"127.0.0.1", "localhost", "::1"}
        if not launch_workers:
            permitted_hosts.add("testserver")
        if host not in permitted_hosts:
            return JSONResponse({"detail": "Local host required"}, status_code=403)
        origin = request.headers.get("origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.hostname not in permitted_hosts or parsed.scheme not in {"http", "https"}:
                return JSONResponse({"detail": "Local origin required"}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            supplied = request.headers.get("X-Spill-Token", "")
            if not secrets.compare_digest(supplied, token):
                return JSONResponse({"detail": "Reload the app to obtain a local session token"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        return response

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"detail": "Study or run not found"}, status_code=404)

    @app.exception_handler(ActiveRunError)
    async def active(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(BudgetExceeded)
    async def budget_refused(request, exc):
        return JSONResponse({"detail": str(exc), "code": "budget_exhausted"}, status_code=409)

    @app.exception_handler(ResearchUncertain)
    async def uncertain_research(request, exc):
        return JSONResponse({"detail": str(exc), "code": "uncertain_provider_dispatch"}, status_code=409)

    @app.get("/api/v1/bootstrap")
    def bootstrap():
        from .media import channel_catalog
        return {
            "version": __version__, "session_token": token, "channels": channel_catalog(),
            "examples": examples(), "provider_status": provider_status(),
            "capabilities": ["local-memory", "offline-research", "public-url-research", "bounded-live-research",
                             "adaptive-media", "individual-numeric-population", "cancel-resume", "report-export",
                             "visual-page-analysis"],
        }

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/studies")
    def studies():
        if launch_workers:
            reconcile_workers(store)
        return {"studies": store.list_studies()}

    @app.post("/api/v1/studies", status_code=201)
    async def create_study(payload: CreateStudyRequest):
        from .services import prepare_study
        return await prepare_study(store, payload.spec)

    @app.post("/api/v1/studies/launch", status_code=202)
    async def guided_launch(payload: CreateStudyRequest):
        from .services import guided_launch as operation
        return await operation(store, payload.spec, launch_workers=launch_workers)

    @app.get("/api/v1/studies/{study_id}")
    def get_study(study_id: str):
        from .services import study_with_credibility
        return study_with_credibility(store.get_study(study_id))

    @app.put("/api/v1/studies/{study_id}/plans")
    def update_plans(study_id: str, payload: StartRunRequest):
        study = store.get_study(study_id)
        plans = payload.plans or []
        validate_plans(StudySpec.model_validate(study["spec"]), plans)
        return store.update_study(study_id, plans=[p.model_dump() for p in plans])

    @app.post("/api/v1/studies/{study_id}/research")
    async def research_study(study_id: str, payload: ResearchRequest | None = None):
        from .services import research_study as operation
        return await operation(store, study_id, payload)

    @app.get("/api/v1/studies/{study_id}/memory")
    def memory(study_id: str, q: str = ""):
        from .memory import LocalMemory
        store.get_study(study_id)
        mem = LocalMemory(store.root / "memory.sqlite")
        return {"results": mem.search(study_id, q) if q else [], "graph": mem.graph(study_id)}

    @app.post("/api/v1/studies/{study_id}/runs", status_code=202)
    def start_run(study_id: str, payload: StartRunRequest | None = None):
        if launch_workers:
            reconcile_workers(store)
        study = store.get_study(study_id)
        spec = StudySpec.model_validate(study["spec"])
        if spec.use_representative_llm and (spec.api_budget_usd <= 0 or not provider_status()["llm"]):
            raise ValueError("Representative AI requires an explicitly configured model and positive real API budget")
        plans = payload.plans if payload and payload.plans is not None else [MediaPlan.model_validate(p) for p in study["plans"]]
        validate_plans(spec, plans)
        run = store.create_run(study_id, spec.model_dump(), [p.model_dump() for p in plans])
        if launch_workers:
            spawn_worker(store, run["id"])
        return store.get_run(run["id"], include_report=False)

    @app.get("/api/v1/runs/{run_id}")
    def get_run(run_id: str):
        if launch_workers:
            reconcile_workers(store)
        return store.get_run(run_id)

    @app.post("/api/v1/runs/{run_id}/cancel")
    def cancel(run_id: str):
        store.request_cancel(run_id)
        return store.get_run(run_id, include_report=False)

    @app.post("/api/v1/runs/{run_id}/resume", status_code=202)
    def resume(run_id: str):
        if launch_workers:
            reconcile_workers(store)
        store.prepare_resume(run_id)
        if launch_workers:
            spawn_worker(store, run_id)
        return store.get_run(run_id, include_report=False)

    @app.get("/api/v1/runs/{run_id}/events")
    async def events(run_id: str, request: Request):
        store.get_run(run_id, include_report=False)
        async def stream():
            previous = None
            while not await request.is_disconnected():
                run = store.get_run(run_id, include_report=False)
                encoded = json.dumps(run)
                if encoded != previous:
                    yield f"data: {encoded}\n\n"
                    previous = encoded
                if run["status"] in {"completed", "cancelled", "failed", "interrupted"}:
                    break
                await asyncio.sleep(0.75)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.get("/api/v1/runs/{run_id}/export")
    def export(run_id: str, format: str = "json"):
        run = store.get_run(run_id)
        if run["status"] != "completed" or "report" not in run:
            raise HTTPException(409, "The experiment must complete before exporting")
        content, media_type, name = export_report(run["report"], format)
        return Response(content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/api/v1/roadmap")
    def roadmap():
        return {"module": 5, "status": "available", "name": "Visual product-page comprehension",
                "steps": ["Capture desktop and mobile", "Grounded multimodal observation", "Progressive persona reading",
                          "Questions and section-level friction", "Direct screenshot control sample", "Paired page comparison"],
                "future": ["Autonomous interactive browser navigation", "Real advertising", "Real purchases"]}

    from .page_api import install_page_routes
    install_page_routes(app, store, launch_workers=launch_workers)

    web = Path(__file__).parent / "web"
    if (web / "index.html").is_file():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    else:
        @app.get("/")
        def building():
            return {"name": "Spill the Market", "status": "Frontend not built; run npm ci && npm run build in frontend/"}
    return app
