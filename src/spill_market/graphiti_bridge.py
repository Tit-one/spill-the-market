"""Optional read-only bridge to Graphiti-shaped Neo4j entity/edge storage.

This is a direct, scoped snapshot reader, not the Graphiti SDK or its LLM
extractor. It issues only the two fixed MATCH/RETURN queries below and never
modifies the remote graph. Imported statements are unverified synthetic local
beliefs, not externally validated facts. The optional Neo4j driver is imported
only when the user explicitly configures a real connection.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from itertools import islice
from urllib.parse import urlsplit

from .memory import LocalMemory
from .models import utc_now

_ENTITIES = """
MATCH (n:Entity)
WHERE n.group_id = $group_id
RETURN n.uuid AS uuid, n.group_id AS group_id,
       substring(coalesce(n.name, ''), 0, 300) AS name,
       substring(coalesce(n.summary, ''), 0, 4000) AS summary,
       n.created_at AS created_at
ORDER BY n.uuid
LIMIT $limit
"""

_FACTS = """
MATCH (source:Entity)-[r:RELATES_TO]->(target:Entity)
WHERE r.group_id = $group_id
  AND source.group_id = $group_id
  AND target.group_id = $group_id
  AND r.invalid_at IS NULL
  AND r.expired_at IS NULL
RETURN r.uuid AS uuid, r.group_id AS group_id,
       source.uuid AS source_uuid, target.uuid AS target_uuid,
       source.group_id AS source_group_id, target.group_id AS target_group_id,
       substring(coalesce(r.name, ''), 0, 200) AS name,
       substring(coalesce(r.fact, ''), 0, 4000) AS fact,
       r.episodes[..20] AS episodes,
       r.created_at AS created_at, r.valid_at AS valid_at,
       r.invalid_at AS invalid_at, r.expired_at AS expired_at
ORDER BY r.uuid
LIMIT $limit
"""


def _namespace(group_id):
    if (not isinstance(group_id, str) or not group_id.strip() or len(group_id) > 200
            or "*" in group_id or re.search(r"[\x00-\x1f\x7f]", group_id)):
        raise ValueError("An explicit bounded Graphiti group_id namespace is required; wildcards are forbidden")
    return group_id


def _limit(limit):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("Graphiti snapshot limit must be an integer between 1 and 500")
    return limit


def _text(value, bound=4000):
    return value[:bound] if isinstance(value, str) else ""


def _date(value):
    if value is None:
        return None
    if hasattr(value, "iso_format"):
        return str(value.iso_format())[:100]
    if hasattr(value, "isoformat"):
        return str(value.isoformat())[:100]
    return str(value)[:100]


def _id(value):
    if not isinstance(value, str) or not value or len(value) > 200:
        raise ValueError("Graphiti record has an absent or invalid source UUID")
    return value


def _read_snapshot(transaction, group_id, limit):
    # One managed read transaction provides a coherent bounded view. All query
    # structure is constant; external namespaces are always query parameters.
    entity_limit = max(1, limit // 2)
    entities = [dict(row) for row in islice(transaction.run(_ENTITIES, group_id=group_id, limit=entity_limit), entity_limit)]
    remaining = limit - len(entities)
    facts = ([dict(row) for row in islice(transaction.run(_FACTS, group_id=group_id, limit=remaining), remaining)]
             if remaining else [])
    return entities, facts


# Neo4j's documented unit_of_work decorator attaches these callback settings.
# Keep the exact same metadata without importing the optional driver eagerly.
_read_snapshot.timeout = 15.0
_read_snapshot.metadata = {"application": "spill-the-market", "purpose": "read-only-graphiti-snapshot"}


class GraphitiReadConnector:
    def __init__(self, uri: str | None = None, user: str | None = None, password: str | None = None,
                 database: str = "neo4j", *, driver=None):
        if not isinstance(database, str) or not database.strip() or len(database) > 100:
            raise ValueError("A bounded Neo4j database name is required")
        self.database = database
        self._owns_driver = driver is None
        if driver is None:
            try:
                parsed = urlsplit(uri or "")
            except ValueError as exc:
                raise ValueError("Configure a valid SPILL_NEO4J_URI") from exc
            if (parsed.scheme not in {"neo4j", "neo4j+s", "neo4j+ssc", "bolt", "bolt+s", "bolt+ssc"}
                    or not parsed.hostname or parsed.username or parsed.password or parsed.fragment
                    or not user or not password):
                raise ValueError("Configure SPILL_NEO4J_URI, SPILL_NEO4J_USER and SPILL_NEO4J_PASSWORD explicitly")
            try:
                from neo4j import GraphDatabase
            except ImportError as exc:
                raise RuntimeError("Install the optional Neo4j driver extra to read a Graphiti snapshot") from exc
            driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=5,
                                          connection_acquisition_timeout=10, max_transaction_retry_time=0,
                                          max_connection_pool_size=2)
        self._driver = driver

    @classmethod
    def from_env(cls):
        """Read only the explicitly configured bridge settings, without env-file discovery."""
        return cls(uri=os.environ.get("SPILL_NEO4J_URI"), user=os.environ.get("SPILL_NEO4J_USER"),
                   password=os.environ.get("SPILL_NEO4J_PASSWORD"),
                   database=os.environ.get("SPILL_NEO4J_DATABASE", "neo4j"))

    def snapshot(self, group_id: str, limit: int = 200) -> dict:
        group = _namespace(group_id)
        limit = _limit(limit)
        with self._driver.session(database=self.database, default_access_mode="READ", fetch_size=min(limit, 100)) as session:
            raw_entities, raw_facts = session.execute_read(_read_snapshot, group, limit)
        entities, facts = [], []
        for row in raw_entities:
            if row.get("group_id") != group:
                raise ValueError("Graphiti entity escaped the requested namespace")
            entities.append({"uuid": _id(row.get("uuid")), "group_id": group,
                             "name": _text(row.get("name"), 300), "summary": _text(row.get("summary")),
                             "created_at": _date(row.get("created_at"))})
        for row in raw_facts:
            if any(row.get(field) != group for field in ("group_id", "source_group_id", "target_group_id")):
                raise ValueError("Graphiti relationship or endpoint escaped the requested namespace")
            # Defense in depth: ignore invalidated facts even if a proxy or
            # injected driver returned rows that violate the fixed predicates.
            if row.get("invalid_at") is not None or row.get("expired_at") is not None:
                continue
            episodes = row.get("episodes") if isinstance(row.get("episodes"), list) else []
            facts.append({"uuid": _id(row.get("uuid")), "group_id": group,
                "source_uuid": _id(row.get("source_uuid")), "target_uuid": _id(row.get("target_uuid")),
                "source_group_id": group, "target_group_id": group, "name": _text(row.get("name"), 200),
                "fact": _text(row.get("fact")), "episodes": [_text(item, 200) for item in episodes[:20]
                                                               if isinstance(item, str)],
                "created_at": _date(row.get("created_at")), "valid_at": _date(row.get("valid_at")),
                "invalid_at": None, "expired_at": None})
        return {"group_id": group, "entities": entities, "facts": facts, "read_only": True,
                "unverified": True, "limit": limit, "retrieved_at": utc_now(),
                "scope": "Graphiti-shaped Neo4j entity/edge snapshot; no Graphiti SDK or LLM extraction"}

    def import_into(self, memory: LocalMemory, study_id: str, group_id: str, limit: int = 200) -> dict:
        if not isinstance(study_id, str) or not study_id.strip() or len(study_id) > 200:
            raise ValueError("An explicit local study namespace is required")
        snapshot = self.snapshot(group_id, limit=limit)
        # LocalMemory's public belief API preserves isolation and explicitly
        # marks these as synthetic, unverified simulation memory. Source UUIDs,
        # original namespace and temporal fields survive inside each text.
        owner = "graphiti:" + hashlib.sha256(group_id.encode("utf-8")).hexdigest()[:24]
        imported = 0
        for kind, records in (("entity", snapshot["entities"]), ("fact", snapshot["facts"])):
            for record in records:
                text = "UNVERIFIED SYNTHETIC Graphiti source memory: " + json.dumps({
                    "origin": "graphiti_read_snapshot", "source_uuid": record["uuid"], "group_id": group_id,
                    "record_kind": kind, "verified": False, "synthetic": True, "record": record},
                    ensure_ascii=False, sort_keys=True, allow_nan=False)
                memory.add_belief(study_id, owner, text, [])
                imported += 1
        return {"imported": imported, "entities": len(snapshot["entities"]), "facts": len(snapshot["facts"]),
                "study_id": study_id, "source_group_id": group_id, "verified": False,
                "synthetic": True, "remote_read_only": True}

    def close(self):
        if self._owns_driver:
            self._driver.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
