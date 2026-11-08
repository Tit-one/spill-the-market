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
                              "page_snapshots": 4, "page_reviews": 12, "page_controls": 4,
                              "page_worker_status": finished["status"]}))


if __name__ == "__main__":
    main()
