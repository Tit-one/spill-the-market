import json

from spill_market.worker import commit_run_report


def test_final_report_commit_recovers_transient_windows_replace_denial(tmp_path, monkeypatch):
    import spill_market.atomic_io as atomic
    original = atomic.os.replace
    attempts = []

    def briefly_locked(source, destination):
        attempts.append((source, destination))
        if len(attempts) < 3:
            error = PermissionError('temporary report sharing lock')
            error.winerror = 32
            raise error
        return original(source, destination)

    monkeypatch.setattr(atomic.os,'replace',briefly_locked)
    report = {'revenue_cents':1250,'label':'rapport préservé'}
    path = tmp_path/'report.json'
    commit_run_report(path,report)
    assert json.loads(path.read_text(encoding='utf-8')) == report
    assert len(attempts)==3 and len({str(a[0]) for a in attempts})==1
    assert not list(tmp_path.glob('*.tmp'))
