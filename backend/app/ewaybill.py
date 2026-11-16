"""E-way bill pre-flight, (simulated) generation behind an approval gate, and expiry watch."""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from . import clock, rules
from .db import Client, Document, EwayBill
from .validators import gstin_valid, vehicle_valid


def validity_days(distance_km: int, odc: bool = False) -> int:
    cfg = rules.active().section("eway_bill")
    per = cfg["odc_km_per_day"] if odc else cfg["km_per_day"]
    return max(1, math.ceil(distance_km / per))


def valid_until(start: datetime, days: int) -> datetime:
    """Rule 138(10): a 'day' ends at midnight following the date of generation."""
    return clock.eod((start + timedelta(days=days)).date())


def needs_ewb(doc: Document) -> bool:
    cfg = rules.active().section("eway_bill")
    return doc.kind == "sale" and doc.status != "rejected" and doc.total >= cfg["threshold_value"]


def preflight(doc: Document, client: Client, ewb: EwayBill | None) -> dict:
    rs = rules.active()
    cfg = rs.section("eway_bill")
    cite = rs.cite("eway_bill").as_dict()
    checks = []

    def add(ok, msg, level=None):
        checks.append({"ok": ok, "msg": msg, "level": level or ("ok" if ok else "error")})

    if doc.party_gstin:
        ok, msg = gstin_valid(doc.party_gstin)
        add(ok, f"Recipient {msg}" if ok else f"Recipient {msg[0].lower() + msg[1:]}")
    else:
        add(True, "Recipient unregistered: enter URP in Part A", "warn")
    need = doc.total >= cfg["threshold_value"]
    side, verdict = ("above", "needed") if need else ("below", "not needed")
    add(True, f"Value ₹{doc.total:,.0f} is {side} ₹{cfg['threshold_value']:,}: e-way bill {verdict}", "ok" if need else "warn")
    age = (clock.today() - doc.inv_date).days if doc.inv_date else 0
    add(age <= cfg["max_document_age_days"],
        ("Invoice dated today" if age == 0 else f"Invoice is {age} day{'s' if age != 1 else ''} old") +("" if age <= cfg["max_document_age_days"] else f": portal blocks e-way bills on documents older than {cfg['max_document_age_days']} days"))
    if not doc.hsn:
        add(False, "HSN code missing in Part A")
    vno = ewb.vehicle_no if ewb else None
    if not vno:
        add(False, "Vehicle number not received yet: transporter asked on WhatsApp", "warn")
    elif vehicle_valid(vno, cfg["vehicle_regex"]):
        add(True, f"Vehicle number {vno} format valid")
    else:
        add(False, f"Vehicle number '{vno}' format invalid: fix before dispatch")
    dist = (ewb.distance_km if ewb else None) or doc.distance_km or 0
    if dist:
        d = validity_days(dist)
        add(True, f"Validity: {d} day{'s' if d > 1 else ''} (distance {dist} km, {cfg['km_per_day']} km per day)")
    else:
        add(False, "Distance missing: needed to compute validity", "warn")
    ready = all(c["ok"] for c in checks if c["level"] == "error") and bool(vno) and vehicle_valid(vno, cfg["vehicle_regex"]) and dist > 0
    return {"checks": checks, "ready": ready, "cite": cite,
            "part_a": {"supply_type": "Outward", "sub_type": "Supply", "doc_type": "Tax Invoice", "doc_no": doc.inv_no,
                       "doc_date": doc.inv_date, "from_gstin": client.gstin, "to_gstin": doc.party_gstin or "URP",
                       "to_name": doc.party_name, "pos": doc.pos, "hsn": doc.hsn, "description": doc.description,
                       "taxable": doc.taxable, "cgst": doc.cgst, "sgst": doc.sgst, "igst": doc.igst, "total": doc.total,
                       "distance_km": dist},
            "part_b": {"mode": "Road", "vehicle_no": vno}}


def generate(ewb: EwayBill, approver: str) -> EwayBill:
    """Simulated generation. Only reachable through the approval endpoint."""
    now = clock.now()
    ewb.ewb_no = "".join(random.choices("0123456789", k=12))
    ewb.generated_at = now
    ewb.valid_until = valid_until(now, validity_days(ewb.distance_km))
    ewb.km_remaining = ewb.distance_km
    ewb.status = "generated"
    ewb.approved_by = approver
    return ewb


def watch(ewb: EwayBill) -> dict | None:
    """Expiry alert: compare time left with distance left (assume 35 km/h average for a loaded truck)."""
    if ewb.status not in ("generated", "extended") or not ewb.valid_until:
        return None
    now = clock.now()
    hours_left = (ewb.valid_until - now).total_seconds() / 3600
    need_h = (ewb.km_remaining or 0) / 35
    cfg = rules.active().section("eway_bill")
    can_extend = -cfg["extension_window_hours"] <= hours_left <= cfg["extension_window_hours"]
    if hours_left < 0:
        level, msg = "error", f"EWB {ewb.ewb_no} expired {abs(hours_left):.0f} h ago" + (" — extend now (inside 8 h window)" if can_extend else "")
    elif need_h > hours_left:
        level, msg = "warn", f"EWB {ewb.ewb_no} expires in {hours_left:.0f} h, truck still {ewb.km_remaining} km away. Extend?"
    else:
        level, msg = "ok", f"EWB {ewb.ewb_no} valid for {hours_left:.0f} h; {ewb.km_remaining} km to go"
    return {"level": level, "msg": msg, "hours_left": round(hours_left, 1), "can_extend": can_extend}


def extend(ewb: EwayBill, km_remaining: int) -> EwayBill:
    now = clock.now()
    ewb.km_remaining = km_remaining
    ewb.valid_until = valid_until(now, validity_days(km_remaining))
    ewb.status = "extended"
    return ewb
