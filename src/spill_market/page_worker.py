"""Two-phase local page-audit worker; never dispatch inference during capture."""
import asyncio
import os
from pathlib import Path
import sys
import traceback

import httpx
import psutil

from .gateway import BudgetLedger
from .page_models import PageAuditSpec
from .page_store import PageAuditStore
from .storage import Store


async def execute_page_audit(root: str | Path, identifier: str, nonce: str | None = None):
    pages = PageAuditStore(Store(root))
    nonce = nonce or pages.get(identifier, internal=True)["worker_nonce"]
    if not pages.claim_worker(identifier, os.getpid(), psutil.Process().create_time(), nonce):
        return
    audit = pages.get(identifier, internal=True)

    def cancelled():
        return pages.get(identifier, internal=True)["cancel_requested"]

    def progress(event):
        event = dict(event)
        snapshot = event.pop("snapshot", None)
        changes = {"progress": {"phase": audit["operation"], **event}}
        if snapshot is not None:
            snapshot["image_url"] = f"/api/v1/page-audits/{identifier}/images/{snapshot['id']}"
            current = pages.get(identifier)["snapshots"]
            def key(s):
                return s["variant_id"], s["viewport"], s["section_index"]
            current = [s for s in current if key(s) != key(snapshot)]
            changes["snapshots"] = [*current, snapshot]
        pages.update(identifier, **changes)

    try:
        from .page_capture import PageCaptureCancelled, capture_pages
        from .page_analysis import PageAnalysisCancelled, PageStageUncertain, analyze_page_audit
        if cancelled():
            pages.update(identifier, status="cancelled")
            return
        if audit["operation"] == "capture":
            snapshots = await capture_pages(PageAuditSpec.model_validate(audit["spec"]), pages.assets_dir(identifier),
                                            on_progress=progress, cancel_check=cancelled)
            values = []
            for snapshot in snapshots:
                value = snapshot.model_dump()
                value["image_url"] = f"/api/v1/page-audits/{identifier}/images/{snapshot.id}"
                values.append(value)
            pages.update(identifier, status="captured", snapshots=values,
                         progress={"phase": "capture", "percent": 100, "message": "Captures retained locally; choose analysis"})
        else:
            spec = audit["study_snapshot"]["spec"]
            ledger = BudgetLedger(pages.root / "budgets" / f"{audit['study_id']}.sqlite",
                                  spec["api_budget_usd"], spec["api_max_calls"])
            report = await analyze_page_audit(
                audit, assets_dir=pages.assets_dir(identifier), ledger=ledger,
                journal_path=pages.assets_dir(identifier).parent / "stages.sqlite",
                provider_id=audit["provider_id"], allow_remote=audit["allow_remote"],
                on_progress=progress, cancel_check=cancelled,
            )
            pages.update(identifier, status="completed", report=report.model_dump(),
                         progress={"phase": "analysis", "percent": 100, "message": "Page analysis completed"})
    except (PageCaptureCancelled, PageAnalysisCancelled):
        pages.update(identifier, status="cancelled", error="Cancelled; committed stages retained")
    except PageStageUncertain:
        pages.update(identifier, status="failed", error_code="uncertain_provider_dispatch",
                     error="Provider dispatch is uncertain. Reserved costs retained; reconcile before resuming.")
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        reason = "Authentication was refused; check the selected credential configuration." if status == 401 else \
                 "Check model access, request compatibility and provider availability."
        pages.update(identifier, status="failed", error_code="uncertain_provider_dispatch",
                     error=f"Visual provider returned HTTP {status}. {reason} "
                           "Unconfirmed charges remain reserved; no automatic retry was sent.")
    except Exception as exc:
        traceback.print_exc()
        message = str(exc)[:1000] if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__
        pages.update(identifier, status="failed", error=message)


if __name__ == "__main__":
    asyncio.run(execute_page_audit(sys.argv[1], sys.argv[2], sys.argv[3]))
