"""Durable simulation entry point, compatible with Windows process spawning."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import psutil

from .models import MediaPlan, StudySpec, TrendReport, utc_now
from .storage import Store
from .atomic_io import AtomicWriteCancelled, atomic_write


def commit_run_report(path: Path, report: dict, *, cancel_check=None):
    encoded = json.dumps(report, ensure_ascii=False, allow_nan=False).encode("utf-8")
    atomic_write(path, lambda stream: stream.write(encoded), description="simulation report", cancel_check=cancel_check)


def execute_run(data_dir: str | Path, run_id: str) -> dict:
    from .simulation import SimulationCancelled, compare_strategies

    store = Store(data_dir)
    run = store.get_run(run_id, internal=True)
    if run["status"] == "completed":
        return run["report"]
    spec = StudySpec.model_validate(run["spec_snapshot"])
    plans = [MediaPlan.model_validate(p) for p in run["plans_snapshot"]]
    research = TrendReport.model_validate(run["research_snapshot"]) if run["research_snapshot"] else None
    directory = store.run_directory(run_id)
    store.update_run(run_id, status="running", error=None, worker_pid=os.getpid(),
                     worker_created=psutil.Process().create_time())

    def progress(value: dict):
        store.update_run(run_id, progress=value)

    try:
        semantic = None
        budget_path = store.root / "budgets" / f"{run['study_id']}.sqlite"
        if spec.use_representative_llm:
            from .gateway import BudgetLedger
            from .personas import generate_personas
            from .representatives import enrich_representatives
            if spec.api_budget_usd <= 0:
                raise ValueError("A positive real API budget is required for representative inference")
            ledger = BudgetLedger(budget_path, spec.api_budget_usd, spec.api_max_calls)
            progress({"percent": 0, "message": "Preparing bounded, cached AI representative reactions"})
            personas = generate_personas(spec.product, spec.audience, research, seed=spec.seed,
                                         limit=spec.audience.representatives)
            semantic = asyncio.run(enrich_representatives(
                spec, personas, research, plans, ledger=ledger, cache_dir=directory / "representatives",
                cancel_check=lambda: store.is_cancel_requested(run_id),
            ))
            spec = StudySpec.model_validate({**spec.model_dump(), "response_multipliers": semantic["response_multipliers"]})
        report = compare_strategies(
            spec, plans, research=research, on_progress=progress,
            checkpoint_dir=directory / "checkpoints", cancel_check=lambda: store.is_cancel_requested(run_id),
        )
        if store.is_cancel_requested(run_id):
            raise SimulationCancelled("Cancelled before report commit")
        report.update(run_id=run_id, study_id=run["study_id"], created_at=utc_now())
        report.setdefault("metadata", {})["api_calls_during_numeric_simulation"] = 0
        report["metadata"]["response_multipliers"] = spec.response_multipliers
        if semantic:
            report["metadata"]["semantic_reactions"] = semantic["reactions"]
            report["metadata"]["semantic_model"] = semantic["model"]
            report["metadata"]["semantic_assumption"] = semantic["assumption"]
        if budget_path.is_file():
            from .gateway import BudgetLedger
            cost = BudgetLedger(budget_path, spec.api_budget_usd, spec.api_max_calls).summary()
        else:
            cost = {"currency": "USD", "limit_usd": spec.api_budget_usd, "calls": 0,
                    "confirmed_usd": 0, "reserved_usd": 0, "uncertain_usd": 0, "committed_usd": 0}
        report["metadata"]["real_api_cost"] = {**cost, "scope": "study_cumulative"}
        commit_run_report(directory / "report.json", report, cancel_check=lambda: store.is_cancel_requested(run_id))
        store.update_run(run_id, status="completed", report_path=str(directory / "report.json"),
                         progress={"percent": 100, "message": "Experiment completed", "day": spec.rounds})
        return report
    except (SimulationCancelled, AtomicWriteCancelled):
        store.update_run(run_id, status="cancelled", error=None)
        return {}
    except Exception as exc:
        store.update_run(run_id, status="failed", error=f"{type(exc).__name__}: {str(exc)[:600]}")
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    execute_run(args.data_dir, args.run_id)


if __name__ == "__main__":
    main()
