"""Maker-checker approval. The owner (maker) prepares, the accountant (checker) checks,
and the signature binds both names to the exact payload hash. The filing tool refuses
anything without a valid signature or with a payload changed after signing."""
from __future__ import annotations

import hashlib
import hmac

from . import clock
from .audit import SECRET, sha256_json
from .db import ReturnDraft


class ApprovalError(Exception):
    pass


def sign(payload_hash: str, maker: str, checker: str) -> str:
    msg = f"{payload_hash}|{maker}|{checker}".encode()
    return hmac.new(SECRET.encode(), msg, hashlib.sha256).hexdigest()


def prepare(r: ReturnDraft, payload: dict, maker: str):
    if r.status in ("approved", "filed"):
        raise ApprovalError(f"Return already {r.status}")
    r.payload = payload
    r.payload_hash = sha256_json(payload)
    r.maker, r.maker_at = maker, clock.now()
    r.checker = r.checker_at = r.signature = None
    r.status = "prepared"


def check(r: ReturnDraft, checker: str):
    if r.status != "prepared":
        raise ApprovalError("Only a prepared return can be checked")
    if checker == r.maker:
        raise ApprovalError("Maker and checker must be different people")
    if sha256_json(r.payload) != r.payload_hash:
        raise ApprovalError("Payload changed after it was prepared")
    r.checker, r.checker_at = checker, clock.now()
    r.signature = sign(r.payload_hash, r.maker, checker)
    r.status = "approved"


def verify(r: ReturnDraft) -> bool:
    if not (r.signature and r.maker and r.checker):
        return False
    if sha256_json(r.payload) != r.payload_hash:
        return False
    return hmac.compare_digest(r.signature, sign(r.payload_hash, r.maker, r.checker))
