from spill_market.examples import examples
from spill_market.models import StudySpec
from spill_market.page_models import PageAuditSpec, PageSnapshot
from spill_market.page_store import PageAuditStore
from spill_market.page_worker import execute_page_audit
from spill_market.services import prepare_study
from spill_market.storage import Store


async def test_cancelled_capture_preserves_committed_snapshot_manifest(tmp_path, monkeypatch):
    from spill_market.page_capture import PageCaptureCancelled
    store = Store(tmp_path)
    spec = StudySpec.model_validate(examples()[0]['spec'])
    spec.audience.population = 60
    spec.audience.representatives = 8
    study = await prepare_study(store, spec)
    pages = PageAuditStore(store)
    audit = pages.create(study['id'], PageAuditSpec())
    snapshot = PageSnapshot(id='s1',variant_id='A',section_index=0,viewport='desktop',width=390,height=844,
                            scroll_y=0,page_height=844,content_hash='test',provenance='demo')

    async def capture(spec, output_dir, *, on_progress, cancel_check):
        on_progress({'percent':50,'snapshot':snapshot.model_dump(),'message':'committed'})
        raise PageCaptureCancelled('cancelled after snapshot')

    monkeypatch.setattr('spill_market.page_capture.capture_pages',capture)
    await execute_page_audit(tmp_path,audit['id'])
    finished = pages.get(audit['id'])
    assert finished['status']=='cancelled'
    assert finished['snapshots'][0]['id']=='s1'
    assert finished['snapshots'][0]['image_url'].endswith('/images/s1')


async def test_rejected_provider_is_actionable_without_echoing_provider_secrets(tmp_path, monkeypatch):
    import httpx
    from spill_market.page_models import AnalyzePageRequest
    store = Store(tmp_path)
    spec = StudySpec.model_validate(examples()[0]['spec'])
    spec.audience.population = 60
    spec.audience.representatives = 8
    study = await prepare_study(store,spec)
    pages = PageAuditStore(store)
    audit = pages.create(study['id'],PageAuditSpec())
    pages.update(audit['id'],status='captured',snapshots=[{'id':'s1'}])
    pages.start_analysis(audit['id'],AnalyzePageRequest(provider_id='configured',allow_remote=True))

    async def rejected(*args,**kwargs):
        request = httpx.Request('POST','https://provider.example/v1/chat/completions')
        response = httpx.Response(401,request=request,text='never-echo-this-credential')
        raise httpx.HTTPStatusError('never-echo-this-credential',request=request,response=response)

    monkeypatch.setattr('spill_market.page_analysis.analyze_page_audit',rejected)
    await execute_page_audit(tmp_path,audit['id'])
    result = pages.get(audit['id'])
    assert result['status']=='failed' and result['error_code']=='uncertain_provider_dispatch'
    assert 'HTTP 401' in result['error'] and 'credential' in result['error']
    assert 'never-echo-this' not in result['error']
