import json
import sqlite3

import pytest

from spill_market.memory import LocalMemory
from spill_market.models import EvidenceSource, Finding, TrendReport


def report():
    return TrendReport(topic="creative", mode="offline", sources=[
        EvidenceSource(id="s1", title="Notes", content="Offline rendering is slow", kind="import")],
        pain_points=[Finding(text="rendering is slow", source_ids=["s1"], status="observed")])


def test_fts_graph_and_beliefs_stay_in_study_namespace(tmp_path):
    memory = LocalMemory(tmp_path / "memory.db")
    memory.ingest_report("one", report())
    memory.ingest_report("one", report())
    assert memory.search("one", "rendering")
    assert memory.search("two", "rendering") == []
    memory.add_belief("one", "p1", "I expect rendering to help", ["s1"])
    graph = memory.graph("one")
    assert any(node["kind"] == "belief" and node["synthetic"] for node in graph["nodes"])
    assert any(node["kind"] == "fact" and not node["synthetic"] for node in graph["nodes"])
    assert graph["edges"]
    assert memory.graph("two") == {"nodes": [], "edges": []}
    with pytest.raises(ValueError, match="source"):
        memory.add_belief("two", "p1", "cross study", ["s1"])
    assert memory.search("one", '" OR * ; DROP TABLE nodes;') == []


def test_demo_sources_do_not_become_real_facts(tmp_path):
    memory = LocalMemory(tmp_path / "memory.db")
    r = report()
    r.mode = "demo"
    r.sources[0].kind = "demo"
    memory.ingest_report("one", r)
    assert all(node["synthetic"] for node in memory.graph("one")["nodes"])


def test_source_identity_cannot_silently_change_under_existing_facts(tmp_path):
    memory = LocalMemory(tmp_path / "memory.db")
    memory.ingest_report("one", report())
    changed = report()
    changed.sources[0].content = "A different unsupported statement"
    with pytest.raises(ValueError, match="identity"):
        memory.ingest_report("one", changed)
    assert any("slow" in node["text"] for node in memory.graph("one")["nodes"])


def test_mirofish_cannot_import_memory_database_into_itself(tmp_path):
    path = tmp_path / "memory.sqlite"
    memory = LocalMemory(path)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="itself"):
        memory.import_mirofish("study", path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("extension", ["json", "csv", "sqlite"])
def test_read_only_mirofish_import_preserves_unverified_provenance(tmp_path, extension):
    source = tmp_path / f"export.{extension}"
    if extension == "json":
        source.write_text(json.dumps({"nodes": [{"id": "x", "text": "rendering preference", "type": "belief"}]}))
    elif extension == "csv":
        source.write_text("id,text,type\nx,rendering preference,belief\n")
    else:
        connection = sqlite3.connect(source)
        connection.execute("CREATE TABLE memories(id TEXT,text TEXT,type TEXT)")
        connection.execute("INSERT INTO memories VALUES('x','rendering preference','belief')")
        connection.commit()
        connection.close()
    before = source.read_bytes()
    memory = LocalMemory(tmp_path / "local.db")
    result = memory.import_mirofish("study", source)
    assert result["imported"] == 1
    assert source.read_bytes() == before
    node = memory.search("study", "rendering")[0]
    assert node["synthetic"] is True
    assert node["provenance"]["format"] == extension
    assert node["provenance"]["verified"] is False
