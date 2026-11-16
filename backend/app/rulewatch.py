"""Rule-watch: an advisory arrives -> proposed rule change -> human approves -> new
rule-set version -> past invoices re-run and affected ones flagged. No model retraining."""
from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import select

from . import audit, engine, llm, rules
from .db import Client, Document, RuleProposal

SIMULATED_ADVISORY = """SIMULATED ADVISORY (demo only, not a real notification)
GST Council recommendation implemented: the rate on ceramic floor and wall tiles (HSN 6907)
is reduced from 18% to 5% with effect from 01-11-2026. Taxpayers should issue invoices at the
revised rate for supplies on or after this date."""


def _parse_without_llm(text: str) -> dict:
    changes = []
    for m in re.finditer(r"HSN\s*(\d{4,8}).*?from\s*(\d+)%\s*to\s*(\d+)%.*?(\d{2})-(\d{2})-(\d{4})", text, re.I | re.S):
        changes.append({"hsn": m.group(1), "new_rate": float(m.group(3)),
                        "effective_from": f"{m.group(6)}-{m.group(5)}-{m.group(4)}", "description": f"HSN {m.group(1)} rate change"})
    return {"summary": text.strip().splitlines()[0], "changes": changes}


def propose(s, advisory: str, actor: str = "rule-watch") -> RuleProposal:
    parsed = None
    if llm.available():
        try:
            parsed = llm.read_advisory(advisory)
        except Exception:  # noqa: BLE001
            parsed = None
    parsed = parsed or _parse_without_llm(advisory)
    base = rules.active()
    diffs = []
    for c in parsed["changes"]:
        cur = base.rate_entry(c["hsn"], date.fromisoformat(c["effective_from"]))
        diffs.append({**c, "old_rate": cur["rate"] if cur else None, "rule_id": cur["id"] if cur else None,
                      "description": cur["description"] if cur else c["description"]})
    eff = min((c["effective_from"] for c in diffs), default=str(date.today()))
    new_v = eff.replace("-", ".")
    if new_v <= base.version:
        new_v = base.version + ".1"
    p = RuleProposal(advisory=advisory, base_version=base.version, new_version=new_v, changes=diffs,
                     impact=preview_impact(s, diffs))
    s.add(p)
    s.flush()
    audit.log(s, actor, "rules:proposed", {"proposal": p.id, "changes": diffs, "new_version": new_v})
    return p


def preview_impact(s, diffs: list[dict]) -> list[dict]:
    out = []
    for c in diffs:
        eff = date.fromisoformat(c["effective_from"])
        for d in s.execute(select(Document).where(Document.hsn.like(c["hsn"] + "%"), Document.inv_date >= eff,
                                                  Document.status != "rejected")).scalars():
            client = s.get(Client, d.client_id)
            out.append({"doc_id": d.id, "client": client.name, "client_id": client.id, "kind": d.kind, "inv_no": d.inv_no,
                        "inv_date": d.inv_date, "party": d.party_name, "taxable": d.taxable, "charged_rate": d.rate,
                        "new_rate": c["new_rate"],
                        "tax_difference": round(d.taxable * ((d.rate or 0) - c["new_rate"]) / 100, 2)})
    return out


def approve(s, p: RuleProposal, approver: str) -> dict:
    if p.status != "proposed":
        raise ValueError("Proposal already decided")
    data = rules.clone_active()
    data["version"] = p.new_version
    data["published_on"] = str(date.today())
    data["approved_by"] = approver
    data["notes"] = f"Derived from v{p.base_version}. Advisory: {p.advisory.strip().splitlines()[0]}"
    for c in p.changes:
        eff = date.fromisoformat(c["effective_from"])
        rows = data["hsn_rates"]
        for r in rows:
            if r["hsn"] == c["hsn"] and r.get("effective_to") is None:
                r["effective_to"] = str(eff - timedelta(days=1))
                new = {**r, "id": f"{r['id']}-{eff:%Y%m%d}", "rate": c["new_rate"], "effective_from": str(eff),
                       "effective_to": None, "source": "SIMULATED advisory (demo)"}
                rows.append(new)
                break
    rules.write_version(data)
    rules.set_active(p.new_version)
    p.status, p.approved_by = "approved", approver

    # Re-run every document dated on/after the effective date with the new rule set
    rs = rules.active()
    flagged = []
    for c in p.changes:
        eff = date.fromisoformat(c["effective_from"])
        for d in s.execute(select(Document).where(Document.hsn.like(c["hsn"] + "%"), Document.inv_date >= eff,
                                                  Document.status != "rejected")).scalars():
            engine.apply_rules(d, s.get(Client, d.client_id), rs)
            if any(i["code"] == "RATE" for i in d.issues):
                d.status = "review"
                d.question = (f"Rule change v{rs.version}: HSN {d.hsn} is now {c['new_rate']:g}% from {eff:%d %b %Y}. "
                              f"{'Issue a credit note to ' + d.party_name if d.kind == 'sale' else 'Ask ' + d.party_name + ' for a corrected invoice'}.")
                flagged.append(d.id)
    p.impact = preview_impact(s, p.changes)
    audit.log(s, approver, "rules:approved", {"proposal": p.id, "version": p.new_version, "flagged_docs": flagged})
    return {"version": p.new_version, "flagged": flagged}
