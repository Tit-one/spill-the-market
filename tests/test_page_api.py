import base64
import hashlib
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from spill_market.api import create_app
from spill_market.page_models import PageAuditSpec
from spill_market.page_store import PageAuditStore


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, launch_workers=False)
    with TestClient(app) as client:
        b = client.get('/api/v1/bootstrap').json()
        spec = b['examples'][0]['spec']
        spec['audience'].update(population=60, representatives=8)
        headers = {'X-Spill-Token': b['session_token']}
        study = client.post('/api/v1/studies', json={'spec': spec}, headers=headers).json()
        client.study, client.write_headers, client.pages = study, headers, PageAuditStore(app.state.store)
        yield client


def test_local_capture_route_and_provider_inventory(client):
    providers = client.get('/api/v1/page-audit/providers')
    assert providers.status_code == 200
    assert 'capture' in providers.json() and 'providers' in providers.json()
    path = f"/api/v1/studies/{client.study['id']}/page-audits"
    assert client.post(path, json={}).status_code == 403
    response = client.post(path, json={}, headers=client.write_headers)
    assert response.status_code == 202, response.text
    audit = response.json()
    assert audit['status'] == 'queued' and audit['provider_id'] is None
    assert client.get(path).json()['audits'][0]['id'] == audit['id']
    assert client.post(f"/api/v1/page-audits/{audit['id']}/analyze", json={},
                       headers=client.write_headers).status_code == 409


def test_image_asset_and_export_are_scoped_to_persisted_snapshot(client):
    audit = client.pages.create(client.study['id'], PageAuditSpec())
    directory = client.pages.assets_dir(audit['id'])
    directory.mkdir(parents=True)
    output = io.BytesIO()
    Image.new('RGB', (390, 844), 'white').save(output, 'JPEG')
    image = output.getvalue()
    (directory / 's1.jpg').write_bytes(image)
    client.pages.update(audit['id'], status='captured', snapshots=[{'id': 's1', 'content_hash': hashlib.sha256(image).hexdigest()}])
    path = f"/api/v1/page-audits/{audit['id']}"
    assert client.get(path+'/images/s1').content == image
    assert client.get(path+'/images/not-in-manifest').status_code == 404
    assert client.get(path+'/export').status_code == 409


def test_untrusted_page_source_is_never_inlined_into_app_or_sent_for_demo(client):
    path = f"/api/v1/studies/{client.study['id']}/page-audits"
    image = io.BytesIO()
    Image.new('RGB', (10, 10)).save(image, 'PNG')
    payload = {'variants': [{'source': 'screenshots', 'screenshots': [{'data_base64': base64.b64encode(image.getvalue()).decode()}]}]}
    audit = client.post(path, json=payload, headers=client.write_headers).json()
    assert audit['spec']['variants'][0]['screenshots'] == []
    client.pages.update(audit['id'], status='captured', snapshots=[{'id': 's', 'provenance': 'screenshot_import'}])
    response = client.post(f"/api/v1/page-audits/{audit['id']}/analyze", json={'provider_id':'demo'}, headers=client.write_headers)
    assert response.status_code == 400
    assert client.pages.get(audit['id'])['status'] == 'captured'


def test_remote_consent_and_budget_are_checked_before_job_claim(client, monkeypatch):
    monkeypatch.setattr('spill_market.page_vision.vision_provider_status', lambda: [
        {'id':'configured','scope':'remote','available':True,'reason':'ready'},
    ])
    audit = client.pages.create(client.study['id'], PageAuditSpec())
    client.pages.update(audit['id'], status='captured', snapshots=[{'id':'s', 'provenance':'screenshot_import'}])
    path = f"/api/v1/page-audits/{audit['id']}/analyze"
    response = client.post(path, json={'provider_id':'configured'}, headers=client.write_headers)
    assert response.status_code == 400 and 'permission' in response.json()['detail']
    response = client.post(path, json={'provider_id':'configured','allow_remote':True}, headers=client.write_headers)
    assert response.status_code == 400 and 'budget' in response.json()['detail']
    assert client.pages.get(audit['id'])['status']=='captured'
    assert not (client.pages.root/'budgets'/f"{client.study['id']}.sqlite").exists()
