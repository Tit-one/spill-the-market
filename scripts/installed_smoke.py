"""Cross-platform installed-wheel qualification with Node absent from PATH."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

# Only the installed Python directory remains executable by name. Numeric
# workers use their absolute interpreter path and must need neither Node nor uv.
os.environ["PATH"] = str(Path(sys.executable).parent)
os.environ.pop("PYTHONPATH", None)
assert shutil.which("node") is None, "Node must be absent during runtime qualification"

import psutil  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import spill_market  # noqa: E402
from spill_market.api import create_app  # noqa: E402
from spill_market.models import MarketAssumptions, ResearchRequest  # noqa: E402
from spill_market.storage import Store  # noqa: E402


def main():
    package = Path(spill_market.__file__).resolve().parent
    assert "site-packages" in package.parts, "Run this with an installed, non-editable wheel"
    assert (package / "web" / "third-party-notices.txt").is_file()
    with tempfile.TemporaryDirectory(prefix="spill-installed-", ignore_cleanup_errors=True) as temporary:
        app = create_app(temporary, launch_workers=True)
        with TestClient(app, base_url="http://127.0.0.1") as client:
            bootstrap = client.get("/api/v1/bootstrap").json()
            assert client.get("/").status_code == 200
            for asset in (package / "web" / "assets").iterdir():
                assert client.get("/assets/" + asset.name).status_code == 200
            spec = bootstrap["examples"][0]["spec"]
            spec.update(rounds=2, exploration_repetitions=1, validation_repetitions=1)
            spec["audience"].update(population=60, representatives=10)
            headers = {"X-Spill-Token": bootstrap["session_token"]}
            study_response = client.post("/api/v1/studies", json={"spec": spec}, headers=headers)
            assert study_response.status_code == 201, study_response.text
            study = study_response.json()
            response = client.post(f"/api/v1/studies/{study['id']}/runs", json={}, headers=headers)
            assert response.status_code == 202, response.text
            identifier = response.json()["id"]
            deadline = time.monotonic() + 90
            while True:
                run = client.get(f"/api/v1/runs/{identifier}").json()
                if run["status"] in {"completed", "failed", "interrupted", "cancelled"}:
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("Installed worker did not terminate within 90 seconds")
                time.sleep(.1)
            assert run["status"] == "completed", run
            report = run["report"]
            assert report["population"] == 60 and len(report["scenarios"]) == 6
            assert report["metadata"]["real_api_cost"]["calls"] == 0
            for format in ("json", "csv", "html", "md"):
                assert client.get(f"/api/v1/runs/{identifier}/export?format={format}").status_code == 200
            internal = Store(temporary).get_run(identifier, internal=True, include_report=False)
            try:
                process = psutil.Process(internal["worker_pid"])
                if abs(process.create_time() - internal["worker_created"]) < .01:
                    process.wait(timeout=10)
            except psutil.NoSuchProcess:
                pass

            # Exercise the guided market entry point through an actual installed
            # worker. This payload cannot authorize research/inference or URLs.
            market_spec = json.loads(json.dumps(spec))
            market_spec.update(objective="market_discovery", market=MarketAssumptions().model_dump(),
                               research=ResearchRequest(mode="offline").model_dump(),
                               rounds=2, exploration_repetitions=1, validation_repetitions=1,
                               api_budget_usd=0, use_representative_llm=False)
            market_spec["audience"].update(population=60, representatives=10)
            launched = client.post("/api/v1/studies/launch", json={"spec": market_spec}, headers=headers)
            assert launched.status_code == 202, launched.text
            launch = launched.json()
            assert launch["research_error"] is None
            assert launch["study"]["research"]["sources"] == []
            market_id = launch["run"]["id"]
            deadline = time.monotonic() + 90
            while True:
                market_run = client.get(f"/api/v1/runs/{market_id}").json()
                if market_run["status"] in {"completed", "failed", "interrupted", "cancelled"}:
                    break
                assert time.monotonic() < deadline, "Installed guided-market worker exceeded 90 seconds"
                time.sleep(.1)
            assert market_run["status"] == "completed", market_run
            market_report = market_run["report"]
            assert market_report["metadata"]["study_objective"] == "market_discovery"
            assert market_report["metadata"]["real_api_cost"]["calls"] == 0
            assert market_report["metadata"]["real_api_cost"]["committed_usd"] == 0
            assert market_report["market_analysis"]["status"] == "hypotheses_only"
            assert market_report["market_analysis"]["competitors"] == []
            assert market_report["population"] == 60 and len(market_report["scenarios"]) == 6
            for scenario in market_report["scenarios"]:
                segments = scenario["age_segments"]
                assert abs(sum(s["population"] for s in segments) - 60) < 1e-9
                assert abs(sum(s["units"] for s in segments) - scenario["mean_units"]) < 1e-9
                assert abs(sum(s["revenue_cents"] for s in segments) - scenario["mean_revenue_cents"]) < 1e-9
                for segment in segments:
                    assert abs(segment["organic_units"] + sum(c["units"] for c in segment["channels"])
                               - segment["units"]) < 1e-9
                switching = scenario["market_switching"]
                assert switching["enabled"] is True
                assert switching["status"] == "unvalidated_assumption"
                assert 0 <= switching["switchers"] <= switching["incumbent_users"] <= 60
                assert abs(switching["switchers"] + switching["new_to_category_buyers"]
                           - scenario["mean_units"]) < 1e-9
                assert abs(switching["retained_incumbents"] + switching["switchers"]
                           - switching["incumbent_users"]) < 1e-9
                assert abs(switching["incumbent_users"] + switching["non_incumbent_users"] - 60) < 1e-9
                assert abs(switching["retained_incumbents"] + switching["new_to_category_nonbuyers"]
                           + scenario["mean_units"] - 60) < 1e-9
            for format in ("json", "csv", "html", "md"):
                exported = client.get(f"/api/v1/runs/{market_id}/export?format={format}")
                assert exported.status_code == 200, exported.text
                assert "hypotheses_only" in exported.text
            internal_market = Store(temporary).get_run(market_id, internal=True, include_report=False)
            try:
                process = psutil.Process(internal_market["worker_pid"])
                if abs(process.create_time() - internal_market["worker_created"]) < .01:
                    process.wait(timeout=10)
            except psutil.NoSuchProcess:
                pass
            market_candidate = next(s for s in market_report["scenarios"] if not s["is_baseline"])

            # The page pipeline must also work from the wheel, with the bundled
            # Playwright driver and no separate developer Node installation.
            providers = client.get("/api/v1/page-audit/providers").json()
            assert providers["capture"]["available"], providers["capture"]
            capture = client.post(f"/api/v1/studies/{study['id']}/page-audits", headers=headers, json={
                "variants": [{"id": "A", "source": "demo"}, {"id": "B", "source": "demo"}],
                "viewports": ["desktop", "mobile"], "max_sections": 1,
                "persona_count": 2, "direct_vision_count": 1,
            })
            assert capture.status_code == 202, capture.text
            audit_id = capture.json()["id"]

            def wait_audit(expected):
                deadline = time.monotonic() + 90
                while True:
                    value = client.get(f"/api/v1/page-audits/{audit_id}").json()
                    if value["status"] == expected:
                        return value
                    assert value["status"] not in {"failed", "interrupted", "cancelled"}, value
                    assert time.monotonic() < deadline, "Installed page worker did not finish"
                    time.sleep(.1)

            captured = wait_audit("captured")
            assert len(captured["snapshots"]) == 4
            for snapshot in captured["snapshots"]:
                assert client.get(snapshot["image_url"]).status_code == 200
            analyzed = client.post(f"/api/v1/page-audits/{audit_id}/analyze", headers=headers,
                                   json={"provider_id": "demo"})
            assert analyzed.status_code == 202, analyzed.text
            finished = wait_audit("completed")
            page_report = finished["report"]
            assert len(page_report["observations"]) == 4 and len(page_report["reviews"]) == 12
            assert len(page_report["comparisons"]) == 2 and len(page_report["direct_vision_controls"]) == 4
            assert finished["cost"]["calls"] == 0
            for format in ("json", "csv", "html", "md"):
                assert client.get(f"/api/v1/page-audits/{audit_id}/export?format={format}").status_code == 200
            from spill_market.page_store import PageAuditStore
            internal_page = PageAuditStore(Store(temporary)).get(audit_id, internal=True)
            try:
                process = psutil.Process(internal_page["worker_pid"])
                if abs(process.create_time() - internal_page["worker_created"]) < .01:
                    process.wait(timeout=10)
            except psutil.NoSuchProcess:
                pass
            print(json.dumps({"installed_package": str(package), "node_on_path": False,
                              "real_worker_status": run["status"], "population": 60,
                              "scenarios": 6, "provider_calls": 0, "exports": ["json", "csv", "html", "md"],
                              "guided_market_status": market_run["status"],
                              "market_age_segments": len(market_candidate["age_segments"]),
                              "market_switchers": market_candidate["market_switching"]["switchers"],
                              "page_snapshots": 4, "page_reviews": 12, "page_controls": 4,
                              "page_worker_status": finished["status"]}))


if __name__ == "__main__":
    main()
