import copy
import sys
import types
from datetime import datetime, timezone

import pytest

from spill_market.graphiti_bridge import GraphitiReadConnector
from spill_market.memory import LocalMemory


class ReadTransaction:
    def __init__(self, owner):
        self.owner = owner

    def run(self, query, **parameters):
        self.owner.queries.append((query, parameters))
        assert not any(word in query.upper().split() for word in ["CREATE", "MERGE", "DELETE", "SET", "REMOVE", "CALL"])
        rows = self.owner.facts if "RELATES_TO" in query else self.owner.entities
        return copy.deepcopy(rows[:parameters["limit"]])


class ReadSession:
    def __init__(self, owner):
        self.owner = owner

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.owner.closed_sessions += 1

    def execute_read(self, function, *args, **kwargs):
        self.owner.reads += 1
        return function(ReadTransaction(self.owner), *args, **kwargs)

    def execute_write(self, *args, **kwargs):
        raise AssertionError("Write transaction forbidden")


class ReadDriver:
    def __init__(self):
        self.queries, self.sessions, self.reads, self.closed_sessions = [], [], 0, 0
        self.entities = [{"uuid": "entity-1", "group_id": "source-a", "name": "Creator", "summary": "Uses GPU rendering", "created_at": None}]
        self.facts = [{"uuid": "fact-1", "group_id": "source-a", "source_uuid": "entity-1", "target_uuid": "entity-2",
                       "source_group_id": "source-a", "target_group_id": "source-a", "name": "PREFERS",
                       "fact": "Creator prefers a rendering trial.", "episodes": ["episode-1"],
                       "created_at": None, "valid_at": datetime(2026, 11, 1, tzinfo=timezone.utc),
                       "invalid_at": None, "expired_at": None}]

    def session(self, **kwargs):
        self.sessions.append(kwargs)
        return ReadSession(self)


def test_snapshot_uses_only_parameterized_read_transactions_and_scoped_endpoints():
    driver = ReadDriver()
    original = copy.deepcopy((driver.entities, driver.facts))
    snapshot = GraphitiReadConnector(driver=driver).snapshot("source-a", limit=10)
    assert snapshot["read_only"] is True and snapshot["unverified"] is True
    assert snapshot["facts"][0]["valid_at"].startswith("2026-11-01")
    assert snapshot["facts"][0]["episodes"] == ["episode-1"]
    assert driver.reads >= 1 and driver.closed_sessions == 1
    assert driver.sessions[0]["default_access_mode"] == "READ"
    assert driver.sessions[0]["database"] == "neo4j"
    assert all(parameters["group_id"] == "source-a" and "$group_id" in query for query, parameters in driver.queries)
    edge_query = next(query for query, _ in driver.queries if "RELATES_TO" in query)
    for predicate in ["r.group_id = $group_id", "source.group_id = $group_id", "target.group_id = $group_id",
                      "r.invalid_at IS NULL", "r.expired_at IS NULL"]:
        assert predicate in edge_query
    assert (driver.entities, driver.facts) == original


@pytest.mark.parametrize("group", ["", " ", "*", None, "bad\nnamespace"])
def test_explicit_namespace_required_before_driver_access(group):
    driver = ReadDriver()
    with pytest.raises(ValueError, match="group"):
        GraphitiReadConnector(driver=driver).snapshot(group)
    assert driver.sessions == []


@pytest.mark.parametrize("limit", [0, -1, 501, True])
def test_snapshot_bound_rejected_before_driver_access(limit):
    driver = ReadDriver()
    with pytest.raises(ValueError, match="limit"):
        GraphitiReadConnector(driver=driver).snapshot("source-a", limit=limit)
    assert driver.sessions == []


def test_snapshot_total_is_bounded_and_invalidated_facts_are_not_returned():
    driver = ReadDriver()
    driver.entities *= 20
    driver.facts *= 20
    result = GraphitiReadConnector(driver=driver).snapshot("source-a", limit=8)
    assert len(result["entities"]) + len(result["facts"]) <= 8
    driver.entities = []
    driver.facts[0]["invalid_at"] = "2026-11-02T00:00:00Z"
    driver.facts[1]["expired_at"] = "2026-11-03T00:00:00Z"
    result = GraphitiReadConnector(driver=driver).snapshot("source-a", limit=10)
    assert all(fact["invalid_at"] is None and fact["expired_at"] is None for fact in result["facts"])


@pytest.mark.parametrize("target", ["entity", "relationship", "source", "target"])
def test_misbehaving_driver_cannot_return_foreign_namespace(target):
    driver = ReadDriver()
    if target == "entity":
        driver.entities[0]["group_id"] = "foreign"
    else:
        field = {"relationship": "group_id", "source": "source_group_id", "target": "target_group_id"}[target]
        driver.facts[0][field] = "foreign"
    with pytest.raises(ValueError, match="namespace"):
        GraphitiReadConnector(driver=driver).snapshot("source-a")


def test_import_is_unverified_synthetic_and_study_local(tmp_path):
    driver = ReadDriver()
    original = copy.deepcopy((driver.entities, driver.facts))
    memory = LocalMemory(tmp_path / "memory.db")
    summary = GraphitiReadConnector(driver=driver).import_into(memory, "local-study", "source-a")
    beliefs = [node for node in memory.graph("local-study")["nodes"] if node["kind"] == "belief"]
    assert summary["imported"] == 2 and summary["verified"] is False
    assert all(node["synthetic"] and node["provenance"]["verified"] is False for node in beliefs)
    assert any("fact-1" in node["text"] and "source-a" in node["text"] for node in beliefs)
    assert memory.graph("foreign-study") == {"nodes": [], "edges": []}
    assert (driver.entities, driver.facts) == original


def test_from_env_is_explicit_lazy_optional_driver_configuration(monkeypatch):
    calls = []
    driver = ReadDriver()
    module = types.SimpleNamespace(GraphDatabase=types.SimpleNamespace(driver=lambda uri, **kwargs: calls.append((uri, kwargs)) or driver))
    monkeypatch.setitem(sys.modules, "neo4j", module)
    monkeypatch.setenv("SPILL_NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("SPILL_NEO4J_USER", "test-user")
    monkeypatch.setenv("SPILL_NEO4J_PASSWORD", "test-only")
    monkeypatch.setenv("SPILL_NEO4J_DATABASE", "source-db")
    connector = GraphitiReadConnector.from_env()
    assert calls[0][0] == "bolt://localhost:7687"
    assert calls[0][1]["auth"] == ("test-user", "test-only")
    assert driver.sessions == []
    connector.snapshot("source-a")
    assert driver.sessions[0]["database"] == "source-db"
