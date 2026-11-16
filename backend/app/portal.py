"""Mock GST portal. A separate store and API so the simulated boundary is obvious.

- Suppliers' GSTR-1 filings (seeded) feed each recipient's IMS and GSTR-2B.
- File endpoint accepts a return only with a valid maker-checker signature and returns a fake ARN.
No call ever leaves this machine.
"""
from __future__ import annotations

import json
import random
import string
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import clock
from .db import DATA_DIR

STORE = DATA_DIR / "mock_portal.json"
_lock = threading.Lock()
router = APIRouter(prefix="/portal", tags=["mock-gst-portal"])


def _load() -> dict:
    if not STORE.exists():
        return {"filings": [], "returns": []}
    return json.loads(STORE.read_text(encoding="utf-8"))


def _save(d: dict):
    STORE.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")


def reset(filings: list[dict]):
    with _lock:
        _save({"filings": filings, "returns": []})


def gstr2b_period(filed_on: date) -> str:
    """GSTR-1 filed by the 11th lands in the previous month's 2B; later, in this month's."""
    if filed_on.day <= 11:
        return clock.prev_period(clock.period_of(filed_on))
    return clock.period_of(filed_on)


def filings_for(recipient_gstin: str, upto: date | None = None) -> list[dict]:
    upto = upto or clock.today()
    out = []
    for f in _load()["filings"]:
        if f["recipient_gstin"] != recipient_gstin:
            continue
        fo = date.fromisoformat(f["filed_on"])
        if fo > upto:
            continue  # supplier has not filed yet as of today
        out.append({**f, "gstr2b_period": gstr2b_period(fo)})
    return out


def gstr2b_generated(period: str) -> bool:
    start, end = clock.period_bounds(period)
    return clock.today() >= end + timedelta(days=14)


def file_return(gstin: str, form: str, period: str, payload: dict, signature: str) -> dict:
    with _lock:
        d = _load()
        arn = "AA" + gstin[:2] + period[:2] + period[4:] + "".join(random.choices(string.digits + string.ascii_uppercase, k=7))
        rec = {"arn": arn, "gstin": gstin, "form": form, "period": period, "signature": signature,
               "received_at": datetime.now().isoformat(timespec="seconds"), "simulated": True}
        d["returns"].append({**rec, "payload": payload})
        _save(d)
        return rec


# ---------------- HTTP surface (what a real integration would call) ----------------

@router.get("/gstr2b/{gstin}/{period}")
def api_gstr2b(gstin: str, period: str):
    if not gstr2b_generated(period):
        raise HTTPException(409, f"GSTR-2B for {period} is generated on the 14th of the next month")
    items = [f for f in filings_for(gstin) if f["gstr2b_period"] == period]
    return {"gstin": gstin, "rtnprd": period, "simulated": True, "docdata": {"b2b": items}}


@router.get("/ims/{gstin}")
def api_ims(gstin: str):
    return {"gstin": gstin, "simulated": True, "invoices": filings_for(gstin)}


class FileReq(BaseModel):
    gstin: str
    form: str
    period: str
    payload: dict
    signature: str


@router.get("/returns/{gstin}")
def api_returns(gstin: str):
    return [{k: v for k, v in r.items() if k != "payload"} for r in _load()["returns"] if r["gstin"] == gstin]
