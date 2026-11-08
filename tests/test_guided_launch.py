from fastapi.testclient import TestClient

from spill_market.api import create_app


def entry(client):
    bootstrap = client.get('/api/v1/bootstrap').json()
    spec = bootstrap['examples'][0]['spec']
    spec.update(rounds=2, exploration_repetitions=1, validation_repetitions=1, objective='market_discovery')
    spec['audience'].update(population=60, representatives=10, age_min=18, age_max=75)
    spec['research'].update(mode='offline', use_llm=False, use_firecrawl=False, documents=[], urls=[])
    return spec, {'X-Spill-Token': bootstrap['session_token']}


def test_guided_launch_creates_one_saved_study_and_queues_one_real_run(tmp_path):
    app = create_app(tmp_path, launch_workers=False)
    with TestClient(app) as client:
        spec, headers = entry(client)
        response = client.post('/api/v1/studies/launch', json={'spec': spec}, headers=headers)
        assert response.status_code == 202, response.text
        result = response.json()
        assert result['study']['spec']['objective'] == 'market_discovery'
        assert len(result['study']['plans']) == 3
        assert result['run']['study_id'] == result['study']['id']
        assert result['run']['status'] == 'queued'
        assert len(client.get('/api/v1/studies').json()['studies']) == 1


def test_guided_launch_collects_user_urls_without_paid_providers(tmp_path, monkeypatch):
    from spill_market import research
    urls = []
    async def fetch(self, url):
        urls.append(url)
        return url, '<html><title>Existing notes</title><p>Migration is difficult.</p></html>', 'text/html'
    monkeypatch.setattr(research.SafeFetcher, 'fetch', fetch)
    with TestClient(create_app(tmp_path, launch_workers=False)) as client:
        spec, headers = entry(client)
        spec['locale'] = 'fr'
        spec['research']['language'] = 'en'
        spec['market'] = {'product_url': 'https://product.example', 'competitor_urls': ['https://notes.example']}
        response = client.post('/api/v1/studies/launch', json={'spec': spec}, headers=headers)
        assert response.status_code == 202, response.text
        assert urls == ['https://product.example', 'https://notes.example']
        assert response.json()['study']['research']['coverage']['collected'] == 2
        assert response.json()['study']['spec']['research']['language'] == 'en'
        assert response.json()['run']['status'] == 'queued'


def test_guided_redirects_keep_requested_product_and_competitor_association(tmp_path, monkeypatch):
    from spill_market import research
    from spill_market.market_analysis import build_market_analysis
    from spill_market.models import StudySpec, TrendReport
    async def redirect(self, url):
        ours = 'product.example' in url
        text = '<title>Our product</title><p>Alternative to Existing Notes: our product.</p>' if ours else '<title>Existing Notes</title><p>Migration is difficult.</p>'
        return 'https://catalog.example/item?code=' + ('ours' if ours else 'theirs'), text, 'text/html'
    monkeypatch.setattr(research.SafeFetcher, 'fetch', redirect)
    with TestClient(create_app(tmp_path, launch_workers=False)) as client:
        spec, headers = entry(client)
        spec['market'] = {'product_url': 'https://product.example', 'competitor_urls': ['https://notes.example']}
        response = client.post('/api/v1/studies/launch', json={'spec': spec}, headers=headers)
        assert response.status_code == 202, response.text
        saved = response.json()['study']
        analysis = build_market_analysis(StudySpec.model_validate(saved['spec']), TrendReport.model_validate(saved['research']), {})
        assert len(analysis['competitors']) == 1
        assert analysis['competitors'][0]['name'] == 'Existing Notes'
        assert analysis['competitors'][0]['evidence_status'] == 'source_statement'


def test_guided_launch_keeps_study_and_explains_unavailable_sources(tmp_path, monkeypatch):
    from spill_market import research
    async def fail(self, url):
        raise OSError('fixture unavailable')
    monkeypatch.setattr(research.SafeFetcher, 'fetch', fail)
    with TestClient(create_app(tmp_path, launch_workers=False)) as client:
        spec, headers = entry(client)
        spec['market'] = {'product_url': 'https://unavailable.example'}
        response = client.post('/api/v1/studies/launch', json={'spec': spec}, headers=headers)
        assert response.status_code == 202, response.text
        assert response.json()['research_error']
        assert response.json()['study']['research']['coverage']['failures']
        assert response.json()['run']['status'] == 'queued'


def test_guided_launch_cannot_implicitly_purchase_research(tmp_path):
    with TestClient(create_app(tmp_path, launch_workers=False)) as client:
        spec, headers = entry(client)
        spec['research']['mode'] = 'live'
        spec['api_budget_usd'] = 10
        response = client.post('/api/v1/studies/launch', json={'spec': spec}, headers=headers)
        assert response.status_code == 400
        assert client.get('/api/v1/studies').json()['studies'] == []


async def test_market_research_retry_keeps_identical_query_and_budget_identity(tmp_path, monkeypatch):
    from spill_market import research, services
    from spill_market.models import ResearchRequest, StudySpec, TrendReport
    from spill_market.storage import Store
    store = Store(tmp_path)
    spec = StudySpec.model_validate({'product': {'name': 'Notes tool', 'description': 'A simple offline note organizer.',
        'unit_price_cents': 2900}, 'objective': 'market_discovery', 'api_budget_usd': .05,
        'research': {'mode': 'offline', 'topic': 'note-taking'}})
    study = await services.prepare_study(store, spec)
    queries = []
    async def collect(request, product, *, ledger):
        queries.append(request.model_dump())
        return TrendReport(topic=request.topic, mode=request.mode)
    monkeypatch.setattr(research, 'run_research', collect)
    await services.research_study(store, study['id'], ResearchRequest(mode='live', topic='note-taking'))
    await services.research_study(store, study['id'])
    assert queries[0] == queries[1]
    assert 'competitors' in queries[0]['topic']
