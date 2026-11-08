import asyncio
import json

from typer.testing import CliRunner

from spill_market.cli import app
from spill_market.examples import examples
from spill_market.models import StudySpec
from spill_market.services import prepare_study
from spill_market.storage import Store


def test_cli_capture_queues_only_local_work_and_status_retains_job(tmp_path, monkeypatch):
    store = Store(tmp_path)
    spec = StudySpec.model_validate(examples()[0]['spec'])
    spec.audience.population = 60
    spec.audience.representatives = 8
    study = asyncio.run(prepare_study(store, spec))
    monkeypatch.setattr('spill_market.page_jobs.spawn_page_worker', lambda *args: None)
    monkeypatch.setattr('spill_market.page_jobs.reconcile_page_workers', lambda *args: None)
    runner = CliRunner()
    result = runner.invoke(app, ['page','capture',study['id'],'--data-dir',str(tmp_path)])
    assert result.exit_code == 0, result.output
    audit = json.loads(result.stdout)
    assert audit['status']=='queued' and audit['provider_id'] is None
    result = runner.invoke(app, ['page','status',audit['id'],'--data-dir',str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)['id']==audit['id']
