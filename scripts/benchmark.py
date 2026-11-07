"""Measure complete experiments, not a single representative-agent microbenchmark."""
from __future__ import annotations

import argparse
import json
import platform
import threading
import time
from pathlib import Path
from uuid import uuid4

import psutil

from spill_market.examples import examples
from spill_market.media import propose_plans
from spill_market.models import StudySpec
from spill_market.simulation import ENGINE_VERSION, compare_strategies


def measure(population: int, days: int, repetitions: int, work_dir: Path) -> dict:
    spec = StudySpec.model_validate(examples()[0]["spec"])
    spec.audience.population = population
    spec.rounds = days
    spec.exploration_repetitions = spec.validation_repetitions = repetitions
    plans = propose_plans(spec.product, spec.audience, spec.media_budget_cents)
    process = psutil.Process()
    peak = [process.memory_info().rss]
    stop = threading.Event()

    def monitor():
        while not stop.wait(.05):
            peak[0] = max(peak[0], process.memory_info().rss)

    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    start = time.perf_counter()
    # Every measurement gets an empty path. Re-running this command must never
    # report a cached comparison as hundreds of millions of computed agent-days.
    output_dir = work_dir / f"{population}-cold-{uuid4().hex[:12]}"
    if output_dir.exists():
        raise RuntimeError("Cold benchmark destination unexpectedly exists")
    try:
        report = compare_strategies(spec, plans, checkpoint_dir=output_dir)
    finally:
        stop.set()
        watcher.join()
    elapsed = time.perf_counter() - start
    result = {
        "population": population, "days": days, "candidate_strategies": len(plans),
        "price_matched_baselines": len({plan.price_cents for plan in plans}),
        "exploration_repetitions": repetitions, "validation_repetitions": repetitions,
        "scenario_replicates": len(report["scenarios"]) * repetitions * 2,
        "agent_days": population * days * len(report["scenarios"]) * repetitions * 2,
        "elapsed_seconds": round(elapsed, 3), "peak_process_rss_mib": round(peak[0] / 2**20, 2),
        "checkpoint_and_cache_bytes": sum(p.stat().st_size for p in output_dir.rglob("*") if p.is_file()),
        "external_api_calls": 0, "engine_version": ENGINE_VERSION,
        "numpy_numeric_individuals": True, "daily_checkpoints_enabled": True,
        "cold_run": True, "preexisting_replica_results": 0,
        "committed_replica_results": len(list(output_dir.rglob("*.json"))),
        "measurement_directory": output_dir.name,
    }
    (work_dir / f"result-{population}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="1000,10000,100000")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--work-dir", type=Path, default=Path(".work/benchmarks"))
    parser.add_argument("--output", type=Path, default=Path(".work/benchmark-results.json"))
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for size in map(int, args.sizes.split(",")):
        print(f"Starting complete {size:,}-person experiment...", flush=True)
        result = measure(size, args.days, args.repetitions, args.work_dir)
        results.append(result)
        print(json.dumps(result), flush=True)
        payload = {"hardware": {"platform": platform.platform(), "python": platform.python_version(),
                                "logical_cpus": psutil.cpu_count(),
                                "ram_gib": round(psutil.virtual_memory().total / 2**30, 1)}, "results": results}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
