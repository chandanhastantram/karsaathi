"""Deterministic checks. No model involved."""
from __future__ import annotations

import re
from datetime import date

CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def gstin_check_char(first14: str) -> str:
    """GSTIN check digit (mod-36, alternating factor 1/2 from the left)."""
    total = 0
    for i, ch in enumerate(first14.upper()):
        v = CHARS.index(ch) * (2 if i % 2 else 1)
        total += v // 36 + v % 36
    return CHARS[(36 - total % 36) % 36]


def make_gstin(state: str, pan: str, entity: str = "1") -> str:
    base = f"{state}{pan}{entity}Z"
    return base + gstin_check_char(base)


def gstin_valid(g: str | None) -> tuple[bool, str]:
    if not g:
        return False, "GSTIN missing"
    g = g.strip().upper()
    if not GSTIN_RE.match(g):
        return False, "GSTIN format is wrong (15 characters: state, PAN, entity, Z, check)"
    exp = gstin_check_char(g[:14])
    if g[14] != exp:
        return False, f"GSTIN check digit is wrong (expected {exp}, found {g[14]})"
    return True, "GSTIN check digit valid"


def money(x) -> float:
    return round(float(x or 0) + 1e-9, 2)


def expected_tax(taxable: float, rate: float, intra: bool) -> dict:
    t = money(taxable * rate / 100)
    if intra:
        half = money(t / 2)
        return {"cgst": half, "sgst": half, "igst": 0.0}
    return {"cgst": 0.0, "sgst": 0.0, "igst": t}


def check_arithmetic(doc: dict, rate: float | None, intra: bool) -> list[dict]:
    """Returns a list of issues. Tolerance Rs 1 for rounding."""
    issues = []
    taxable = money(doc.get("taxable"))
    cg, sg, ig = money(doc.get("cgst")), money(doc.get("sgst")), money(doc.get("igst"))
    if intra and ig > 0:
        issues.append({"code": "POS_HEAD", "severity": "high",
                       "msg": "Same-state supply but IGST charged; should be CGST + SGST"})
    if not intra and (cg > 0 or sg > 0):
        issues.append({"code": "POS_HEAD", "severity": "high",
                       "msg": "Inter-state supply but CGST/SGST charged; should be IGST"})
    if rate is not None:
        exp = expected_tax(taxable, rate, intra)
        charged = cg + sg + ig
        should = exp["cgst"] + exp["sgst"] + exp["igst"]
        if abs(charged - should) > 1.0:
            eff = round(charged * 100 / taxable, 2) if taxable else 0
            issues.append({"code": "RATE", "severity": "high",
                           "msg": f"Tax charged Rs {charged:,.2f} ({eff}%) but rule rate {rate}% gives Rs {should:,.2f}"})
    total = doc.get("total")
    if total is not None and abs(money(total) - (taxable + cg + sg + ig)) > 1.0:
        issues.append({"code": "TOTAL", "severity": "medium",
                       "msg": f"Invoice total Rs {money(total):,.2f} does not equal taxable + tax Rs {taxable + cg + sg + ig:,.2f}"})
    return issues


def norm_inv(n: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (n or "").upper()).lstrip("0")


def fy_of(d: date) -> str:
    y = d.year if d.month >= 4 else d.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def vehicle_valid(v: str | None, pattern: str) -> bool:
    if not v:
        return False
    return bool(re.match(pattern, re.sub(r"[\s-]", "", v.upper())))
