from fastapi.testclient import TestClient


def test_bootstrap_is_local_and_secret_free(tmp_path):
    from spill_market.api import create_app
    with TestClient(create_app(tmp_path, launch_workers=False)) as client:
        response = client.get("/api/v1/bootstrap")
        assert response.status_code == 200
        data = response.json()
        assert data["session_token"]
        assert {x["id"] for x in data["examples"]} == {"game", "software"}
        assert client.get("/api/v1/bootstrap", headers={"Origin": "https://evil.example"}).status_code == 403
        assert client.post("/api/v1/studies", json={}).status_code == 403


def test_create_study_then_edit_plan_and_queue_run(tmp_path):
    from spill_market.api import create_app
    with TestClient(create_app(tmp_path, launch_workers=False)) as client:
        bootstrap = client.get("/api/v1/bootstrap").json()
        headers = {"X-Spill-Token": bootstrap["session_token"]}
        spec = bootstrap["examples"][0]["spec"]
        response = client.post("/api/v1/studies", json={"spec": spec}, headers=headers)
        assert response.status_code == 201, response.text
        study = response.json()
        assert len(study["plans"]) == 3
        assert study["research"]["mode"] == "demo"
        assert len(study["personas"]) <= spec["audience"]["representatives"]
        study["plans"][0]["placements"][0]["locked"] = True
        edited = client.put(f"/api/v1/studies/{study['id']}/plans", json={"plans": study["plans"]}, headers=headers)
        assert edited.status_code == 200
        assert edited.json()["plans"][0]["placements"][0]["locked"]
        run = client.post(f"/api/v1/studies/{study['id']}/runs", json={}, headers=headers)
        assert run.status_code == 202, run.text
        assert run.json()["status"] == "queued"


def test_demo_run_finishes_and_exports_safe_html(tmp_path):
    from spill_market.api import create_app
    from spill_market.worker import execute_run
    app = create_app(tmp_path, launch_workers=False)
    with TestClient(app) as client:
        bootstrap = client.get("/api/v1/bootstrap").json()
        headers = {"X-Spill-Token": bootstrap["session_token"]}
        spec = bootstrap["examples"][0]["spec"]
        spec.update(rounds=3, exploration_repetitions=1, validation_repetitions=1)
        spec["audience"].update(population=60, representatives=10)
        spec["product"]["name"] = "<script>alert(1)</script>"
        study = client.post("/api/v1/studies", json={"spec": spec}, headers=headers).json()
        run = client.post(f"/api/v1/studies/{study['id']}/runs", json={}, headers=headers).json()
        execute_run(tmp_path, run["id"])
        finished = client.get(f"/api/v1/runs/{run['id']}").json()
        assert finished["status"] == "completed", finished
        assert len(finished["report"]["scenarios"]) >= 4
        html = client.get(f"/api/v1/runs/{run['id']}/export?format=html")
        assert html.status_code == 200
        assert "<script>alert(1)</script>" not in html.text
        assert client.get(f"/api/v1/runs/{run['id']}/export?format=csv").status_code == 200
