"""Local page-audit snapshots, assets and atomic worker transitions."""
from __future__ import annotations

import json
import re
from uuid import uuid4

from .models import utc_now
from .page_models import AnalyzePageRequest, PageAuditSpec
from .storage import ActiveRunError, Store

ACTIVE = {"queued", "capturing", "analyzing"}


class PageAuditStore:
    def __init__(self, store: Store):
        self.store = store
        self.root = store.root
        with store.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS page_audits (
                id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES studies(id),
                spec TEXT NOT NULL, study_snapshot TEXT NOT NULL, status TEXT NOT NULL,
                operation TEXT NOT NULL, progress TEXT NOT NULL, snapshots TEXT NOT NULL,
                report TEXT, error TEXT, error_code TEXT, provider_id TEXT,
                allow_remote INTEGER NOT NULL DEFAULT 0, cancel_requested INTEGER NOT NULL DEFAULT 0,
                worker_pid INTEGER, worker_created REAL, worker_nonce TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(page_audits)")}
            if "worker_nonce" not in columns:
                db.execute("ALTER TABLE page_audits ADD COLUMN worker_nonce TEXT")

    def assets_dir(self, identifier: str):
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise ValueError("Invalid audit identifier")
        return self.root / "page_audits" / identifier / "images"

    def create(self, study_id: str, spec: PageAuditSpec) -> dict:
        study = self.store.get_study(study_id)
        now, identifier = utc_now(), uuid4().hex
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM page_audits WHERE study_id=? AND status IN ('queued','capturing','analyzing')",
                          (study_id,)).fetchone():
                raise ActiveRunError("An active page audit already exists for this study")
            db.execute("""INSERT INTO page_audits
                (id,study_id,spec,study_snapshot,status,operation,progress,snapshots,worker_nonce,created_at,updated_at)
                VALUES(?,?,?,?,'queued','capture',?,'[]',?,?,?)""", (
                    identifier, study_id, spec.model_dump_json(), json.dumps(study),
                    json.dumps({"phase": "capture", "message": "Capture queued", "percent": 0}), uuid4().hex, now, now,
                ))
        return self.get(identifier)

    def get(self, identifier: str, *, internal=False) -> dict:
        self.assets_dir(identifier)
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM page_audits WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError(identifier)
        result = dict(row)
        for key in ("spec", "study_snapshot", "progress", "snapshots", "report"):
            result[key] = json.loads(result[key]) if result[key] is not None else None
        for key in ("allow_remote", "cancel_requested"):
            result[key] = bool(result[key])
        result["cost"] = result["report"].get("cost", {}) if result["report"] else {}
        if not internal:
            result.pop("study_snapshot")
            result.pop("worker_pid")
            result.pop("worker_created")
            result.pop("worker_nonce")
            for variant in result["spec"]["variants"]:
                variant["html"] = None
                variant["screenshots"] = []
        return result

    def list(self, study_id: str) -> list[dict]:
        self.store.get_study(study_id)
        with self.store.connection() as db:
            rows = db.execute("SELECT id FROM page_audits WHERE study_id=? ORDER BY created_at DESC",
                              (study_id,)).fetchall()
        return [self.get(row[0]) for row in rows]

    def update(self, identifier: str, **changes):
        permitted = {"status", "operation", "progress", "snapshots", "report", "error", "error_code",
                     "provider_id", "allow_remote", "cancel_requested", "worker_pid", "worker_created"}
        if not changes or not set(changes) <= permitted:
            raise ValueError("Invalid page-audit update")
        encoded = {key: json.dumps(value, allow_nan=False) if key in {"progress", "snapshots", "report"}
                   and value is not None else value for key, value in changes.items()}
        encoded["updated_at"] = utc_now()
        with self.store.connection() as db:
            cursor = db.execute("UPDATE page_audits SET " + ",".join(f"{key}=?" for key in encoded) + " WHERE id=?",
                                (*encoded.values(), identifier))
            if not cursor.rowcount:
                raise KeyError(identifier)

    def start_analysis(self, identifier: str, request: AnalyzePageRequest) -> dict:
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status,snapshots FROM page_audits WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise KeyError(identifier)
            if row["status"] != "captured" or not json.loads(row["snapshots"]):
                raise ActiveRunError("Capture must finish before analysis; an existing analysis cannot be started twice")
            db.execute("""UPDATE page_audits SET status='queued',operation='analysis',provider_id=?,allow_remote=?,
                cancel_requested=0,worker_pid=NULL,worker_created=NULL,worker_nonce=?,error=NULL,error_code=NULL,progress=?,updated_at=?
                WHERE id=?""", (request.provider_id, request.allow_remote,
                                uuid4().hex,
                                json.dumps({"phase": "analysis", "message": "Analysis queued", "percent": 0}),
                                utc_now(), identifier))
        return self.get(identifier)

    def request_cancel(self, identifier: str):
        with self.store.connection() as db:
            cursor = db.execute("UPDATE page_audits SET cancel_requested=1,updated_at=? "
                                "WHERE id=? AND status IN ('queued','capturing','analyzing')", (utc_now(), identifier))
            if not cursor.rowcount:
                raise ActiveRunError("Only active audits can be cancelled")

    def prepare_resume(self, identifier: str) -> dict:
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM page_audits WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise KeyError(identifier)
            if row["error_code"] == "uncertain_provider_dispatch":
                raise ValueError("An uncertain provider dispatch requires reconciliation before any resume")
            if row["status"] not in {"cancelled", "interrupted", "failed"}:
                raise ActiveRunError("Only stopped audits can be resumed")
            db.execute("""UPDATE page_audits SET status='queued',cancel_requested=0,worker_pid=NULL,
                worker_created=NULL,worker_nonce=?,error=NULL,error_code=NULL,updated_at=? WHERE id=?""",
                       (uuid4().hex, utc_now(), identifier))
        return self.get(identifier)

    def active(self) -> list[dict]:
        with self.store.connection() as db:
            rows = db.execute("SELECT id FROM page_audits WHERE status IN ('queued','capturing','analyzing')").fetchall()
        return [self.get(row[0], internal=True) for row in rows]

    def set_worker(self, identifier: str, pid: int, created: float, nonce: str):
        with self.store.connection() as db:
            db.execute("UPDATE page_audits SET worker_pid=?,worker_created=?,updated_at=? "
                       "WHERE id=? AND status='queued' AND worker_nonce=?", (pid, created, utc_now(), identifier, nonce))

    def claim_worker(self, identifier: str, pid: int, created: float, nonce: str) -> bool:
        with self.store.connection() as db:
            cursor = db.execute("""UPDATE page_audits SET status=CASE operation WHEN 'capture' THEN 'capturing'
                ELSE 'analyzing' END,worker_pid=?,worker_created=?,updated_at=?
                WHERE id=? AND status='queued' AND worker_nonce=?""",
                                (pid, created, utc_now(), identifier, nonce))
        return cursor.rowcount == 1

    def interrupt_if_owned(self, snapshot: dict) -> bool:
        with self.store.connection() as db:
            cursor = db.execute("""UPDATE page_audits SET status='interrupted',error=?,updated_at=?
                WHERE id=? AND status IN ('queued','capturing','analyzing') AND worker_pid IS ?
                AND worker_created IS ? AND updated_at=?""", (
                    "Worker no longer present; committed page stages retained", utc_now(), snapshot["id"],
                    snapshot.get("worker_pid"), snapshot.get("worker_created"), snapshot["updated_at"],
                ))
        return cursor.rowcount == 1
