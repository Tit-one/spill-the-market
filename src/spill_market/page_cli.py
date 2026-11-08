"""Page-audit commands using the same persistence/preflight as the web app."""
import base64
import json
from pathlib import Path
from typing import Annotated

import typer


def install_page_cli(app):
    page = typer.Typer(help="Capture product pages and compare synthetic persona reactions.")
    app.add_typer(page, name="page")

    def setup(data_dir, env_file=None):
        from .settings import load_env_file, load_provider_profile
        from .page_store import PageAuditStore
        from .storage import Store
        if env_file:
            load_env_file(env_file)
        load_provider_profile(data_dir, include_env_file=env_file is None)
        return PageAuditStore(Store(data_dir))

    def emit(value):
        typer.echo(json.dumps(value, ensure_ascii=False, indent=2))

    @page.command("capture")
    def capture(
        study_id: str,
        data_dir: Annotated[Path | None, typer.Option()] = None,
        spec_file: Annotated[Path | None, typer.Option("--spec", exists=True, dir_okay=False)] = None,
        url: str | None = None,
        html_file: Annotated[Path | None, typer.Option("--html", exists=True, dir_okay=False)] = None,
        image: Annotated[list[Path] | None, typer.Option(exists=True, dir_okay=False)] = None,
    ):
        from .page_jobs import spawn_page_worker
        from .page_models import PageAuditSpec, PageVariantInput, ScreenshotInput
        if sum(bool(x) for x in (spec_file, url, html_file, image)) > 1:
            raise typer.BadParameter("Choose one of --spec, --url, --html or --image")
        if spec_file:
            spec = PageAuditSpec.model_validate_json(spec_file.read_text(encoding="utf-8"))
        elif url:
            spec = PageAuditSpec(variants=[PageVariantInput(source="url", url=url)])
        elif html_file:
            spec = PageAuditSpec(variants=[PageVariantInput(source="html", html=html_file.read_text(encoding="utf-8"))])
        elif image:
            if len(image) > 12 or any(path.stat().st_size > 6_000_000 for path in image):
                raise typer.BadParameter("At most twelve images, each no larger than 6 MB")
            shots = [ScreenshotInput(name=p.name, data_base64=base64.b64encode(p.read_bytes()).decode()) for p in image]
            spec = PageAuditSpec(variants=[PageVariantInput(source="screenshots", screenshots=shots)])
        else:
            spec = PageAuditSpec()
        pages = setup(data_dir)
        audit = pages.create(study_id, spec)
        spawn_page_worker(pages, audit["id"])
        emit(pages.get(audit["id"]))

    @page.command("analyze")
    def analyze(
        audit_id: str, provider: str = "configured", allow_remote: bool = False,
        data_dir: Annotated[Path | None, typer.Option()] = None,
        env_file: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    ):
        from .page_api import validate_page_analysis
        from .page_jobs import spawn_page_worker
        from .page_models import AnalyzePageRequest
        pages = setup(data_dir, env_file)
        request = AnalyzePageRequest(provider_id=provider, allow_remote=allow_remote)
        validate_page_analysis(pages, audit_id, request)
        pages.start_analysis(audit_id, request)
        spawn_page_worker(pages, audit_id)
        emit(pages.get(audit_id))

    @page.command("status")
    def status(audit_id: str, data_dir: Annotated[Path | None, typer.Option()] = None):
        from .page_jobs import reconcile_page_workers
        pages = setup(data_dir)
        reconcile_page_workers(pages)
        emit(pages.get(audit_id))

    @page.command("cancel")
    def cancel(audit_id: str, data_dir: Annotated[Path | None, typer.Option()] = None):
        pages = setup(data_dir)
        pages.request_cancel(audit_id)
        emit(pages.get(audit_id))

    @page.command("resume")
    def resume(audit_id: str, data_dir: Annotated[Path | None, typer.Option()] = None):
        from .page_jobs import reconcile_page_workers, spawn_page_worker
        pages = setup(data_dir)
        reconcile_page_workers(pages)
        pages.prepare_resume(audit_id)
        spawn_page_worker(pages, audit_id)
        emit(pages.get(audit_id))

    @page.command("export")
    def export(audit_id: str, output: Path, format: str = "json",
               data_dir: Annotated[Path | None, typer.Option()] = None):
        from .page_exports import export_page_audit
        pages = setup(data_dir)
        audit = pages.get(audit_id)
        if audit["status"] != "completed" or not audit["report"]:
            raise typer.BadParameter("Complete page analysis before exporting")
        content, _, _ = export_page_audit(audit, pages.assets_dir(audit_id), format)
        output.write_text(content, encoding="utf-8")
        emit({"path": str(output.resolve()), "format": format})
