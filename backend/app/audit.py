"""Hash-chained audit trail. Each entry's hash covers the previous hash,
so editing or deleting any past row breaks verification from that row on."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

from sqlalchemy import select

from .db import AuditLog

GENESIS = "0" * 64
SECRET = os.environ.get("KARSAATHI_SECRET", "karsaathi-demo-secret-change-me")


def _digest(prev: str, at: str, actor: str, action: str, client_id, detail: dict) -> str:
    body = json.dumps({"prev": prev, "at": at, "actor": actor, "action": action,
                       "client_id": client_id, "detail": detail},
                      sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()


def log(s, actor: str, action: str, detail: dict | None = None, client_id: int | None = None) -> AuditLog:
    detail = json.loads(json.dumps(detail or {}, default=str))
    last = s.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).scalar_one_or_none()
    prev = last.hash if last else GENESIS
    at = datetime.now().isoformat(timespec="seconds")
    h = _digest(prev, at, actor, action, client_id, detail)
    row = AuditLog(at=at, actor=actor, action=action, client_id=client_id, detail=detail, prev_hash=prev, hash=h)
    s.add(row)
    s.flush()
    return row


def verify(s) -> dict:
    prev = GENESIS
    rows = s.execute(select(AuditLog).order_by(AuditLog.id)).scalars().all()
    for r in rows:
        if r.prev_hash != prev or _digest(prev, r.at, r.actor, r.action, r.client_id, r.detail) != r.hash:
            return {"ok": False, "entries": len(rows), "broken_at": r.id}
        prev = r.hash
    return {"ok": True, "entries": len(rows), "head": prev}


def sha256_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()
