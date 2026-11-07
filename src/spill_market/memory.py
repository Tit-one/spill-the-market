"""Study-scoped SQLite FTS5 and graph memory, with no MiroFish runtime imports."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from .models import TrendReport, utc_now


def _clean(text: str) -> str:
    soup = BeautifulSoup(str(text)[:200_000], "html.parser")
    for element in soup(["script", "style", "iframe", "object", "embed", "form"]):
        element.decompose()
    return " ".join(soup.stripped_strings)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class LocalMemory:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS nodes (study_id TEXT NOT NULL,id TEXT NOT NULL,"
                               "kind TEXT NOT NULL,text TEXT NOT NULL,synthetic INTEGER NOT NULL,"
                               "payload TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(study_id,id))")
            connection.execute("CREATE TABLE IF NOT EXISTS edges (study_id TEXT NOT NULL,source TEXT NOT NULL,"
                               "target TEXT NOT NULL,relation TEXT NOT NULL,PRIMARY KEY(study_id,source,target,relation))")
            connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING "
                               "fts5(study_id UNINDEXED,node_id UNINDEXED,text,tokenize='unicode61')")

    @contextmanager
    def _transaction(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _study(study_id: str) -> str:
        if not isinstance(study_id, str) or not study_id.strip() or len(study_id) > 200:
            raise ValueError("A nonempty study namespace is required")
        return study_id

    @staticmethod
    def _put(connection, study_id, node_id, kind, text, synthetic, payload):
        connection.execute("INSERT INTO nodes VALUES(?,?,?,?,?,?,?) ON CONFLICT(study_id,id) DO UPDATE SET "
                           "kind=excluded.kind,text=excluded.text,synthetic=excluded.synthetic,payload=excluded.payload",
                           (study_id, node_id, kind, text, int(synthetic), json.dumps(payload, ensure_ascii=False), utc_now()))
        connection.execute("DELETE FROM memory_fts WHERE study_id=? AND node_id=?", (study_id, node_id))
        connection.execute("INSERT INTO memory_fts(study_id,node_id,text) VALUES(?,?,?)", (study_id, node_id, text))

    @staticmethod
    def _edge(connection, study, source, target, relation):
        connection.execute("INSERT OR IGNORE INTO edges VALUES(?,?,?,?)", (study, source, target, relation))

    def ingest_report(self, study_id: str, report: TrendReport):
        study = self._study(study_id)
        report = TrendReport.model_validate(report)
        sources = {source.id: source for source in report.sources}
        if len(sources) != len(report.sources):
            raise ValueError("Duplicate source identity in report")
        with self._transaction() as connection:
            for source in report.sources:
                existing = connection.execute("SELECT payload FROM nodes WHERE study_id=? AND id=?",
                                              (study, "source:" + source.id)).fetchone()
                if existing:
                    previous = json.loads(existing["payload"])
                    if (previous.get("content_hash") != _digest(source.content) or previous.get("kind") != source.kind
                            or previous.get("url") != source.url):
                        raise ValueError("Source identity cannot be reused for different evidence")
                payload = source.model_dump(mode="json")
                payload["provenance"] = {"origin": "research", "mode": report.mode, "verified": False,
                                         "note": "Collected text is evidence, not an independently verified truth."}
                payload["content_hash"] = _digest(source.content)
                self._put(connection, study, "source:" + source.id, "source", source.content,
                          source.kind == "demo", payload)
            for category in ("trends", "pain_points", "jargon", "segments"):
                for finding in getattr(report, category):
                    if any(source_id not in sources for source_id in finding.source_ids):
                        raise ValueError("Finding references an unknown report source")
                    synthetic = report.mode == "demo" or any(sources[s].kind == "demo" for s in finding.source_ids)
                    kind = "fact" if finding.status == "observed" and finding.source_ids else "hypothesis"
                    payload = finding.model_dump(mode="json") | {"category": category, "provenance": {
                        "origin": "research", "verified": False, "meaning": "Observed source statement"}}
                    node_id = "finding:" + _digest(json.dumps(payload, sort_keys=True))[:32]
                    self._put(connection, study, node_id, kind, finding.text, synthetic, payload)
                    for source_id in finding.source_ids:
                        self._edge(connection, study, "source:" + source_id, node_id, "supports")

    def search(self, study_id: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
        study = self._study(study_id)
        limit = max(1, min(int(limit), 100))
        tokens = re.findall(r"[^\W_]+", str(query), re.UNICODE)[:20]
        with self._transaction() as connection:
            if tokens:
                # User text never becomes raw FTS syntax or SQL.
                expression = " AND ".join('"' + token + '"' for token in tokens)
                rows = connection.execute("SELECT n.* FROM memory_fts f JOIN nodes n ON "
                                          "n.study_id=f.study_id AND n.id=f.node_id "
                                          "WHERE memory_fts MATCH ? AND n.study_id=? ORDER BY rank LIMIT ?",
                                          (expression, study, limit)).fetchall()
            elif query.strip():
                return []
            else:
                rows = connection.execute("SELECT * FROM nodes WHERE study_id=? ORDER BY created_at DESC LIMIT ?",
                                          (study, limit)).fetchall()
        return [self._node(row) for row in rows]

    @staticmethod
    def _node(row) -> dict:
        payload = json.loads(row["payload"])
        return payload | {"id": row["id"], "kind": row["kind"], "text": row["text"],
                          "synthetic": bool(row["synthetic"]), "created_at": row["created_at"]}

    def add_belief(self, study_id: str, persona_id: str, text: str, source_ids: list[str]):
        study = self._study(study_id)
        text = _clean(text)
        if not text or not persona_id or len(persona_id) > 200:
            raise ValueError("Beliefs require a persona and nonempty text")
        with self._transaction() as connection:
            for source_id in source_ids:
                if connection.execute("SELECT 1 FROM nodes WHERE study_id=? AND id=? AND kind='source'",
                                      (study, "source:" + source_id)).fetchone() is None:
                    raise ValueError("Belief source does not exist in this study")
            persona_node = "persona:" + persona_id
            self._put(connection, study, persona_node, "persona", persona_id, True, {"persona_id": persona_id})
            node_id = "belief:" + _digest(persona_id + "\0" + text)[:32]
            self._put(connection, study, node_id, "belief", text, True,
                      {"persona_id": persona_id, "source_ids": list(source_ids),
                       "provenance": {"origin": "simulation", "verified": False}})
            self._edge(connection, study, persona_node, node_id, "believes")
            for source_id in source_ids:
                self._edge(connection, study, node_id, "source:" + source_id, "informed_by")

    def graph(self, study_id: str) -> dict:
        study = self._study(study_id)
        with self._transaction() as connection:
            nodes = connection.execute("SELECT * FROM nodes WHERE study_id=? ORDER BY id", (study,)).fetchall()
            edges = connection.execute("SELECT source,target,relation FROM edges WHERE study_id=? "
                                       "ORDER BY source,target,relation", (study,)).fetchall()
        return {"nodes": [self._node(row) for row in nodes], "edges": [dict(row) for row in edges]}

    def import_mirofish(self, study_id: str, path: str | Path) -> dict:
        """Import export-shaped records only. The source file is opened read-only.

        Supported SQLite tables: memories, nodes, entities, beliefs, edges,
        relationships. JSON accepts these lists, a records list, or a top-level
        list. Unknown content is explicitly unverified, never promoted to facts.
        """
        study = self._study(study_id)
        source = Path(path).resolve(strict=True)
        if source == self.path:
            raise ValueError("Local memory cannot import itself as a read-only source")
        if not source.is_file() or source.stat().st_size > 20_000_000:
            raise ValueError("MiroFish export must be a regular file smaller than 20 MB")
        extension = source.suffix.lower().lstrip(".")
        records, relationships = [], []
        if extension == "json":
            data = json.loads(source.read_text(encoding="utf-8-sig"))
            if isinstance(data, list):
                records = data
            elif isinstance(data, dict):
                for key in ("nodes", "entities", "memories", "beliefs", "records"):
                    values = data.get(key, [])
                    if isinstance(values, list):
                        records.extend(values)
                for key in ("edges", "relationships"):
                    if isinstance(data.get(key), list):
                        relationships.extend(data[key])
            else:
                raise ValueError("MiroFish JSON requires records")
        elif extension == "csv":
            records = list(csv.DictReader(io.StringIO(source.read_text(encoding="utf-8-sig"))))
        elif extension in {"sqlite", "sqlite3", "db"}:
            wal = Path(str(source) + "-wal")
            if wal.exists() and wal.stat().st_size:
                raise ValueError("Import a checkpointed SQLite export; active WAL files are not supported")
            connection = sqlite3.connect(source.as_uri() + "?mode=ro&immutable=1", uri=True)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("PRAGMA query_only=ON")
                connection.execute("PRAGMA trusted_schema=OFF")
                tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in ("memories", "nodes", "entities", "beliefs", "edges", "relationships"):
                    if table in tables:
                        rows = [dict(row) for row in connection.execute(f'SELECT * FROM "{table}" LIMIT 10001')]
                        (relationships if table in {"edges", "relationships"} else records).extend(rows)
            finally:
                connection.close()
        else:
            raise ValueError("Supported MiroFish exports are JSON, CSV and SQLite")
        if len(records) + len(relationships) > 10_000:
            raise ValueError("MiroFish export exceeds 10,000-record import bound")
        imported, skipped, linked = 0, 0, 0
        file_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        mapping = {}
        with self._transaction() as connection:
            for index, record in enumerate(records):
                if not isinstance(record, dict):
                    skipped += 1
                    continue
                text = _clean(next((str(record[k]) for k in ("text", "content", "description", "summary", "name")
                                    if record.get(k)), ""))
                if not text:
                    skipped += 1
                    continue
                external_id = str(record.get("id", record.get("uuid", index)))
                node_id = "mirofish:" + _digest(file_hash + "\0" + external_id)[:32]
                incoming_kind = str(record.get("type", record.get("kind", ""))).lower()
                synthetic = incoming_kind in {"belief", "persona", "agent", "simulation", "event"}
                kind = "belief" if incoming_kind == "belief" else "import"
                provenance = {"origin": "mirofish_export", "format": extension, "file": source.name,
                              "file_hash": file_hash, "external_id": external_id, "verified": False,
                              "synthetic_status": "fictional" if synthetic else "unknown"}
                self._put(connection, study, node_id, kind, text, synthetic, {"provenance": provenance})
                mapping[external_id] = node_id
                imported += 1
            for record in relationships:
                if not isinstance(record, dict):
                    skipped += 1
                    continue
                start = str(record.get("source", record.get("source_node_uuid", "")))
                end = str(record.get("target", record.get("target_node_uuid", "")))
                if start in mapping and end in mapping:
                    relation = _clean(record.get("relation", record.get("name", "related_to")))[:100]
                    self._edge(connection, study, mapping[start], mapping[end], relation)
                    linked += 1
                else:
                    skipped += 1
        return {"imported": imported, "edges": linked, "skipped": skipped, "study_id": study,
                "source_hash": file_hash, "verified": False, "source_modified": False}
