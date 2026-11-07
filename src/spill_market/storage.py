"""Short transactional writes and immutable run snapshots in a local SQLite database."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from platformdirs import user_data_dir

from .models import utc_now


class ActiveRunError(ValueError):
    pass


def data_directory(path: str | Path | None = None) -> Path:
    root = Path(path or os.environ.get("SPILL_MARKET_DATA_DIR") or user_data_dir("SpillTheMarket", appauthor=False))
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


class Store:
    def __init__(self, root: str | Path | None = None):
        self.root = data_directory(root)
        self.path = self.root / "studies.sqlite"
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS studies (
                    id TEXT PRIMARY KEY, spec TEXT NOT NULL, plans TEXT NOT NULL,
                    personas TEXT NOT NULL, research TEXT, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES studies(id),
                    status TEXT NOT NULL, progress TEXT NOT NULL, error TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    spec_snapshot TEXT NOT NULL, plans_snapshot TEXT NOT NULL,
                    research_snapshot TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
                    worker_pid INTEGER, worker_created REAL, report_path TEXT);
                CREATE INDEX IF NOT EXISTS runs_study ON runs(study_id, created_at);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA foreign_keys=ON")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def create_study(self, spec: dict, plans: list, personas: list, research: dict | None) -> dict:
        identifier, now = uuid4().hex, utc_now()
        with self.connection() as db:
            db.execute("INSERT INTO studies VALUES (?,?,?,?,?,?,?)", (
                identifier, json.dumps(spec), json.dumps(plans), json.dumps(personas),
                json.dumps(research) if research is not None else None, now, now,
            ))
        return self.get_study(identifier)

    def get_study(self, identifier: str) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM studies WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError(identifier)
        result = dict(row)
        for key in ("spec", "plans", "personas", "research"):
            result[key] = json.loads(result[key]) if result[key] is not None else None
        result["runs"] = self.list_runs(identifier)
        return result

    def list_studies(self) -> list[dict]:
        with self.connection() as db:
            rows = db.execute("SELECT id FROM studies ORDER BY created_at DESC").fetchall()
        return [self.get_study(row["id"]) for row in rows]

    def update_study(self, identifier: str, **changes):
        allowed = {"spec", "plans", "personas", "research"}
        if not changes or not set(changes) <= allowed:
            raise ValueError("Unsupported study fields")
        with self.connection() as db:
            fields = ",".join(f"{key}=?" for key in changes)
            values = [json.dumps(value) for value in changes.values()]
            cursor = db.execute(f"UPDATE studies SET {fields},updated_at=? WHERE id=?", (*values, utc_now(), identifier))
            if cursor.rowcount != 1:
                raise KeyError(identifier)
        return self.get_study(identifier)

    def create_run(self, study_id: str, spec: dict, plans: list) -> dict:
        study = self.get_study(study_id)
        identifier, now = uuid4().hex, utc_now()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("SELECT id FROM runs WHERE status IN ('queued','running') LIMIT 1").fetchone()
            if active:
                raise ActiveRunError("A simulation is already active. Cancel or finish it before starting another.")
            db.execute("""INSERT INTO runs
                (id,study_id,status,progress,created_at,updated_at,spec_snapshot,plans_snapshot,research_snapshot)
                VALUES (?,?,?,?,?,?,?,?,?)""", (
                identifier, study_id, "queued", json.dumps({"percent": 0, "message": "Queued"}), now, now,
                json.dumps(spec), json.dumps(plans), json.dumps(study["research"]),
            ))
            # Saving the exact user-submitted plans and queueing their immutable
            # snapshot are one transaction; a reload must not restore old edits.
            db.execute("UPDATE studies SET plans=?,updated_at=? WHERE id=?", (json.dumps(plans), now, study_id))
        self.run_directory(identifier)
        return self.get_run(identifier)

    def run_directory(self, identifier: str) -> Path:
        if len(identifier) != 32 or not all(c in "0123456789abcdef" for c in identifier):
            raise ValueError("Invalid run identifier")
        path = self.root / "runs" / identifier
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_run(self, identifier: str, *, internal=False, include_report=True) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError(identifier)
        result = dict(row)
        result["progress"] = json.loads(result["progress"])
        result["cancel_requested"] = bool(result["cancel_requested"])
        if internal:
            for key in ("spec_snapshot", "plans_snapshot", "research_snapshot"):
                result[key] = json.loads(result[key]) if result[key] else None
        else:
            for key in ("spec_snapshot", "plans_snapshot", "research_snapshot", "worker_pid", "worker_created"):
                result.pop(key, None)
        report_path = result.pop("report_path", None)
        if result["status"] == "completed" and include_report and report_path:
            safe_path = self.run_directory(identifier) / "report.json"
            if safe_path.is_file():
                result["report"] = json.loads(safe_path.read_text(encoding="utf-8"))
        return result

    def list_runs(self, study_id: str) -> list[dict]:
        with self.connection() as db:
            rows = db.execute("SELECT id FROM runs WHERE study_id=? ORDER BY created_at DESC", (study_id,)).fetchall()
        return [self.get_run(row["id"], include_report=False) for row in rows]

    def update_run(self, identifier: str, **changes):
        allowed = {"status", "progress", "error", "worker_pid", "worker_created", "report_path", "cancel_requested"}
        if not changes or not set(changes) <= allowed:
            raise ValueError("Unsupported run fields")
        values = [json.dumps(v) if key == "progress" else v for key, v in changes.items()]
        with self.connection() as db:
            fields = ",".join(f"{key}=?" for key in changes)
            cursor = db.execute(f"UPDATE runs SET {fields},updated_at=? WHERE id=?", (*values, utc_now(), identifier))
            if cursor.rowcount != 1:
                raise KeyError(identifier)

    def request_cancel(self, identifier: str):
        run = self.get_run(identifier, include_report=False)
        if run["status"] in ("queued", "running"):
            self.update_run(identifier, cancel_requested=1)

    def is_cancel_requested(self, identifier: str) -> bool:
        with self.connection() as db:
            row = db.execute("SELECT cancel_requested FROM runs WHERE id=?", (identifier,)).fetchone()
        return bool(row and row[0])

    def prepare_resume(self, identifier: str):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM runs WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise KeyError(identifier)
            if row[0] not in ("cancelled", "failed", "interrupted"):
                raise ValueError("Only a cancelled, failed or interrupted run can resume")
            if db.execute("SELECT id FROM runs WHERE status IN ('queued','running') LIMIT 1").fetchone():
                raise ActiveRunError("Another simulation is active")
            db.execute("""UPDATE runs SET status='queued',cancel_requested=0,error=NULL,
                worker_pid=NULL,worker_created=NULL,updated_at=? WHERE id=?""", (utc_now(), identifier))

    def active_runs(self) -> list[dict]:
        with self.connection() as db:
            rows = db.execute("SELECT id FROM runs WHERE status IN ('queued','running')").fetchall()
        return [self.get_run(row[0], internal=True, include_report=False) for row in rows]
