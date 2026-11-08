from spill_market.page_jobs import page_worker_is_alive


def test_page_liveness_requires_matching_creation_time_module_and_audit(monkeypatch):
    class Process:
        command = ['python','-m','spill_market.page_worker','data','audit-1']

        def create_time(self):
            return 123.25

        def is_running(self):
            return True

        def cmdline(self):
            return self.command

    process = Process()
    monkeypatch.setattr('spill_market.page_jobs.psutil.Process',lambda pid:process)
    snapshot = {'id':'audit-1','worker_pid':42,'worker_created':123.25}
    assert page_worker_is_alive(snapshot)
    process.command = ['python','-m','spill_market.worker','data','audit-1']
    assert not page_worker_is_alive(snapshot)
    process.command = ['python','-m','spill_market.page_worker','data','another-audit']
    assert not page_worker_is_alive(snapshot)
    process.command = ['python','-m','spill_market.page_worker','data','audit-1']
    snapshot['worker_created']=100
    assert not page_worker_is_alive(snapshot)
