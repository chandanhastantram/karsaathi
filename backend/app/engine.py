"""Deterministic GST engine. Every figure here is computed by code from the rule set.
The LLM never produces a tax number."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from . import clock, portal, rules
from .db import Client, Document, ImsAction, Party, ReturnDraft
from .validators import check_arithmetic, expected_tax, gstin_valid, money, norm_inv


# ======================================================================
# Per-document: classify, compute, validate
# ======================================================================

def supply_states(doc: Document, client: Client) -> tuple[str, str]:
    """(supplier state, place of supply)"""
    own = client.gstin[:2]
    party = (doc.party_gstin or "")[:2] or None
    if doc.kind == "sale":
        return own, (doc.pos or party or own)
    return (party or own), (doc.pos or own)


def apply_rules(doc: Document, client: Client, rs: rules.RuleSet | None = None) -> Document:
    """Fill rate / heads / ITC eligibility from the rule set and record issues + citations.
    Keeps the amounts as read from the bill; differences become issues, never silent fixes."""
    rs = rs or rules.active()
    on = doc.inv_date or clock.today()
    issues = [i for i in (doc.issues or []) if i.get("code") in ("LOWCONF", "DUPLICATE", "NEEDS_INFO")]
    cites = []

    # GSTIN of counterparty
    if doc.party_gstin:
        ok, msg = gstin_valid(doc.party_gstin)
        if not ok:
            issues.append({"code": "GSTIN", "severity": "high", "msg": msg})
    elif doc.kind == "purchase" and not doc.rcm:
        issues.append({"code": "GSTIN", "severity": "medium", "msg": "Supplier GSTIN missing: no input credit without it"})

    # HSN -> rate
    if not doc.hsn:
        guess = rs.hsn_from_text(doc.description)
        if guess:
            doc.hsn = guess["hsn"]
    rate, cite = rs.rate(doc.hsn, on)
    if rate is None:
        issues.append({"code": "HSN", "severity": "medium", "msg": f"HSN '{doc.hsn or '?'}' not in rule table; rate unknown"})
    else:
        cites.append(cite.as_dict())
        if doc.rate is None:
            doc.rate = rate
        elif abs((doc.rate or 0) - rate) > 0.01:
            issues.append({"code": "RATE", "severity": "high",
                           "msg": f"Bill says {doc.rate:g}% but {cite.rule_id} says {rate:g}% for HSN {doc.hsn} on {on:%d %b %Y}"})

    # Reverse charge (e.g. GTA)
    doc.rcm = bool(doc.kind == "purchase" and rs.is_rcm(doc.hsn, on) and not doc.party_gstin)

    # Place of supply -> heads
    s_state, pos = supply_states(doc, client)
    doc.pos = pos
    intra = s_state == pos
    cites.append(rs.cite("place_of_supply").as_dict())
    if doc.rcm:
        # supplier charges no tax; recipient pays under reverse charge
        exp = expected_tax(doc.taxable, rate or 0, intra)
        doc.cgst, doc.sgst, doc.igst = exp["cgst"], exp["sgst"], exp["igst"]
        doc.total = money(doc.taxable)
    else:
        if not (doc.cgst or doc.sgst or doc.igst) and rate is not None and doc.method in ("text", "manual"):
            exp = expected_tax(doc.taxable, rate, intra)
            doc.cgst, doc.sgst, doc.igst = exp["cgst"], exp["sgst"], exp["igst"]
        if not doc.total:
            doc.total = money(doc.taxable + doc.cgst + doc.sgst + doc.igst)
        issues += check_arithmetic(
            {"taxable": doc.taxable, "cgst": doc.cgst, "sgst": doc.sgst, "igst": doc.igst, "total": doc.total},
            None if any(i["code"] == "RATE" for i in issues) else rate, intra)

    # ITC eligibility (purchases)
    doc.itc_eligible, doc.itc_note = True, ""
    if doc.kind == "purchase":
        reason, bcite = rs.blocked(doc.hsn)
        if reason:
            doc.itc_eligible, doc.itc_note = False, reason
            cites.append(bcite.as_dict())

    # Document age for e-way bills
    if doc.kind == "sale" and doc.total >= rs.section("eway_bill")["threshold_value"]:
        cites.append(rs.cite("eway_bill").as_dict())

    doc.issues = issues
    doc.cites = cites
    doc.rule_version = rs.version
    return doc


def find_duplicate(s, doc: Document) -> Document | None:
    q = select(Document).where(Document.client_id == doc.client_id, Document.kind == doc.kind,
                               Document.status != "rejected")
    if doc.id:
        q = q.where(Document.id != doc.id)
    for d in s.execute(q).scalars():
        same_party = (d.party_gstin or d.party_name.lower()) == (doc.party_gstin or doc.party_name.lower())
        if same_party and norm_inv(d.inv_no) == norm_inv(doc.inv_no) and doc.inv_no:
            return d
    return None


def itc_of(d: Document) -> float:
    return money(d.cgst + d.sgst + d.igst)


# ======================================================================
# Supplier risk model
# ======================================================================

def supplier_risk(party: Party, period_filed: bool | None = None) -> dict:
    """Logistic score on the supplier's last 6 months of GSTR-1 behaviour.
    Weights calibrated on the synthetic supplier-history set (see data/README)."""
    hist = (party.filing_history or [])[-6:]
    n = max(len(hist), 1)
    missed = sum(1 for h in hist if h is None) / n
    late = sum(1 for h in hist if h is not None and h > 0) / n
    delays = [h for h in hist if h is not None]
    avg_delay = sum(delays) / len(delays) if delays else 0
    t = clock.today()
    overdue_now = 1.0 if (period_filed is False and t.day > 11) else 0.0
    z = -2.4 + 4.2 * missed + 2.0 * late + 0.06 * avg_delay + 1.4 * overdue_now
    p = 1 / (1 + math.exp(-z))
    level = "High" if p >= 0.6 else "Medium" if p >= 0.3 else "Low"
    return {"p_miss": round(p, 2), "level": level,
            "features": {"missed_share": round(missed, 2), "late_share": round(late, 2),
                         "avg_delay_days": round(avg_delay, 1), "overdue_this_month": bool(overdue_now)}}


# ======================================================================
# Reconciliation: books vs IMS / GSTR-2B
# ======================================================================

def ims_actions(s, client_id: int) -> dict:
    out = {}
    for a in s.execute(select(ImsAction).where(ImsAction.client_id == client_id).order_by(ImsAction.id)).scalars():
        out[(a.supplier_gstin, norm_inv(a.inv_no))] = a.action
    return out


def reconcile(s, client: Client, period: str) -> dict:
    start, end = clock.period_bounds(period)
    books = s.execute(select(Document).where(
        Document.client_id == client.id, Document.kind == "purchase", Document.status == "booked",
        Document.rcm == False, Document.inv_date >= start, Document.inv_date <= end)).scalars().all()  # noqa: E712
    filings = portal.filings_for(client.gstin)
    actions = ims_actions(s, client.id)
    parties = {p.gstin: p for p in s.execute(select(Party).where(Party.client_id == client.id)).scalars() if p.gstin}
    fidx = {(f["supplier_gstin"], norm_inv(f["inv_no"])): f for f in filings}
    generated = portal.gstr2b_generated(period)

    rows, used = [], set()
    for d in books:
        key = (d.party_gstin, norm_inv(d.inv_no))
        f = fidx.get(key)
        party = parties.get(d.party_gstin)
        row = {"doc_id": d.id, "supplier": d.party_name, "supplier_gstin": d.party_gstin, "party_id": party.id if party else None,
               "inv_no": d.inv_no, "inv_date": d.inv_date, "book_taxable": d.taxable, "book_itc": itc_of(d),
               "itc_eligible": d.itc_eligible, "itc_note": d.itc_note}
        if f:
            used.add(key)
            p_itc = money(f["cgst"] + f["sgst"] + f["igst"])
            diff = abs(f["taxable"] - d.taxable) > 1 or abs(p_itc - itc_of(d)) > 1
            row.update({"portal_taxable": f["taxable"], "portal_itc": p_itc, "filed_on": f["filed_on"],
                        "gstr2b_period": f["gstr2b_period"]})
            if diff:
                row.update(status="mismatch", recommend="pending",
                           why=f"Supplier reported Rs {f['taxable']:,.0f} taxable, your bill says Rs {d.taxable:,.0f}. Keep pending and ask for GSTR-1A amendment.")
            elif f["gstr2b_period"] != period:
                row.update(status="late", recommend="accept",
                           why=f"Supplier filed after the cut-off; credit moves to the {clock.period_label(f['gstr2b_period'])} GSTR-2B.")
            else:
                row.update(status="matched", recommend="accept", why="Invoice, GSTIN and amounts match.")
        else:
            row.update(status="missing", recommend=None, portal_itc=0,
                       why="Supplier has not reported this invoice yet.")
        row["ims_action"] = actions.get(key)
        row["at_risk"] = row["book_itc"] if (row["status"] in ("missing", "mismatch") and d.itc_eligible) else 0
        if party:
            row["risk"] = supplier_risk(party, period_filed=row["status"] != "missing")
        rows.append(row)

    # On the portal but not in the books
    start_p = start
    for key, f in fidx.items():
        if key in used or not (start_p <= date.fromisoformat(f["inv_date"]) <= end):
            continue
        rows.append({"doc_id": None, "supplier": f.get("supplier_name", f["supplier_gstin"]), "supplier_gstin": f["supplier_gstin"],
                     "inv_no": f["inv_no"], "inv_date": f["inv_date"], "book_taxable": 0, "book_itc": 0,
                     "portal_taxable": f["taxable"], "portal_itc": money(f["cgst"] + f["sgst"] + f["igst"]),
                     "filed_on": f["filed_on"], "gstr2b_period": f["gstr2b_period"], "status": "not_in_books",
                     "recommend": "pending", "why": "Supplier reported an invoice you have no bill for. Ask for a copy before accepting; reject if it is not yours.",
                     "ims_action": actions.get(key), "at_risk": 0, "itc_eligible": True})

    by_supplier = defaultdict(lambda: {"at_risk": 0.0, "invoices": 0})
    for r in rows:
        if r["at_risk"]:
            b = by_supplier[r["supplier"]]
            b["at_risk"] += r["at_risk"]
            b["invoices"] += 1
            b["party_id"] = r.get("party_id")
            b["risk"] = r.get("risk", {"level": "Medium", "p_miss": 0.5})
    suppliers = sorted(({"supplier": k, **v} for k, v in by_supplier.items()), key=lambda x: -x["at_risk"])
    counts = defaultdict(int)
    for r in rows:
        counts[r["status"]] += 1
    return {"period": period, "gstr2b_generated": generated, "rows": rows, "counts": dict(counts),
            "at_risk_total": money(sum(r["at_risk"] for r in rows)), "suppliers": suppliers,
            "cite": rules.active().cite("ims").as_dict()}


# ======================================================================
# Rule 37: 180-day payment ageing
# ======================================================================

def ageing(s, client: Client) -> list[dict]:
    rs = rules.active()
    cfg = rs.section("itc_payment_condition")
    t = clock.today()
    out = []
    for d in s.execute(select(Document).where(Document.client_id == client.id, Document.kind == "purchase",
                                              Document.status == "booked", Document.paid_on == None)).scalars():  # noqa: E711
        if not d.inv_date:
            continue
        age = (t - d.inv_date).days
        if age >= cfg["warn_days"]:
            out.append({"doc_id": d.id, "supplier": d.party_name, "inv_no": d.inv_no, "age_days": age,
                        "itc": itc_of(d), "reversal_on": d.inv_date + timedelta(days=cfg["days"]),
                        "reversed": age >= cfg["days"], "cite": rs.cite("itc_payment_condition").as_dict()})
    return sorted(out, key=lambda x: -x["age_days"])


# ======================================================================
# Due dates, late fee, interest
# ======================================================================

def due_dates(client: Client, period: str) -> list[dict]:
    rs = rules.active()
    dd = rs.section("due_dates")
    m, y = int(period[:2]), int(period[2:])
    nm, ny = (1, y + 1) if m == 12 else (m + 1, y)
    cite = rs.cite("due_dates").as_dict()
    out = []
    if client.scheme == "QRMP":
        q_end = m in (6, 9, 12, 3)
        if q_end:
            out.append({"form": "GSTR-1", "due": date(ny, nm, dd["gstr1_qrmp_day"]), "pays_tax": False})
            day = dd["gstr3b_qrmp_day_cat_a"] if client.gstin[:2] in dd["qrmp_cat_a_states"] else dd["gstr3b_qrmp_day_cat_b"]
            out.append({"form": "GSTR-3B", "due": date(ny, nm, day), "pays_tax": True})
        else:
            out.append({"form": "PMT-06", "due": date(ny, nm, dd["pmt06_day"]), "pays_tax": True})
    else:
        out.append({"form": "GSTR-1", "due": date(ny, nm, dd["gstr1_monthly_day"]), "pays_tax": False})
        out.append({"form": "GSTR-3B", "due": date(ny, nm, dd["gstr3b_monthly_day"]), "pays_tax": True})
    out.append({"form": "TDS deposit", "due": date(ny, nm, dd["tds_deposit_day"]), "pays_tax": True})
    for o in out:
        o["period"] = period
        o["cite"] = cite
    return out


def late_cost(client: Client, due: date, cash: float, nil: bool = False, on: date | None = None) -> dict:
    rs = rules.active()
    lf = rs.section("late_fee")
    on = on or clock.today()
    days = max((on - due).days, 0)
    cap = lf["cap_upto_1_5cr"] if client.aato_cr <= 1.5 else lf["cap_upto_5cr"] if client.aato_cr <= 5 else lf["cap_above_5cr"]
    fee = min(days * (lf["per_day_nil"] if nil else lf["per_day"]), cap)
    interest = money(cash * lf["interest_rate_pct"] / 100 * days / 365)
    return {"days_late": days, "late_fee": fee, "interest": interest, "cap": cap, "cite": rs.cite("late_fee").as_dict()}


# ======================================================================
# GSTR-3B / PMT-06 computation with Rule 88A set-off
# ======================================================================

def _heads(docs) -> dict:
    return {"txval": money(sum(d.taxable for d in docs)), "iamt": money(sum(d.igst for d in docs)),
            "camt": money(sum(d.cgst for d in docs)), "samt": money(sum(d.sgst for d in docs)), "csamt": 0.0,
            "doc_ids": [d.id for d in docs]}


def set_off(liab: dict, cred: dict) -> dict:
    """Rule 88A: IGST credit first (IGST, then CGST/SGST); CGST credit never against SGST and vice versa."""
    L = dict(liab)
    C = dict(cred)
    used = defaultdict(float)

    def use(src, dst, amt):
        amt = money(max(0.0, min(amt, C[src], L[dst])))
        C[src] -= amt
        L[dst] -= amt
        used[f"{src}->{dst}"] += amt

    use("igst", "igst", L["igst"])
    # IGST credit to the heads that their own credit cannot cover
    use("igst", "cgst", max(0, L["cgst"] - C["cgst"]))
    use("igst", "sgst", max(0, L["sgst"] - C["sgst"]))
    use("igst", "cgst", L["cgst"])
    use("igst", "sgst", L["sgst"])
    use("cgst", "cgst", L["cgst"])
    use("sgst", "sgst", L["sgst"])
    use("cgst", "igst", L["igst"])
    use("sgst", "igst", L["igst"])
    return {"cash": {k: money(v) for k, v in L.items()}, "carry_forward": {k: money(v) for k, v in C.items()},
            "utilised": {k: money(v) for k, v in used.items() if v}}


def compute_3b(s, client: Client, period: str) -> dict:
    rs = rules.active()
    start, end = clock.period_bounds(period)
    in_period = lambda q: q.where(Document.client_id == client.id, Document.status == "booked",  # noqa: E731
                                  Document.inv_date >= start, Document.inv_date <= end)
    sales = s.execute(in_period(select(Document).where(Document.kind == "sale"))).scalars().all()
    purchases = s.execute(in_period(select(Document).where(Document.kind == "purchase"))).scalars().all()
    rcm = [d for d in purchases if d.rcm]

    # ITC per IMS / GSTR-2B: only invoices the supplier reported (Sec 16(2)(aa)), not rejected/pending
    rec = reconcile(s, client, period)
    actions = ims_actions(s, client.id)
    docs_by_id = {d.id: d for d in purchases}
    # also pick up earlier-period invoices whose credit landed in this period's 2B
    all_booked = {(d.party_gstin, norm_inv(d.inv_no)): d for d in s.execute(select(Document).where(
        Document.client_id == client.id, Document.kind == "purchase", Document.status == "booked")).scalars()}
    claim, blocked, held = [], [], []
    for f in portal.filings_for(client.gstin):
        if f["gstr2b_period"] != period:
            continue
        key = (f["supplier_gstin"], norm_inv(f["inv_no"]))
        act = actions.get(key)
        d = all_booked.get(key)
        if act in ("reject", "pending") or d is None:
            continue
        p_itc = money(f["cgst"] + f["sgst"] + f["igst"])
        if abs(f["taxable"] - d.taxable) > 1 or abs(p_itc - itc_of(d)) > 1:
            continue  # mismatch: held until amended / accepted explicitly
        (claim if d.itc_eligible else blocked).append(d)
    for r in rec["rows"]:
        if r["status"] in ("missing", "mismatch") and r["doc_id"] in docs_by_id and docs_by_id[r["doc_id"]].itc_eligible:
            held.append(docs_by_id[r["doc_id"]])

    # Rule 37 reversals: claimed earlier, now unpaid for 180+ days, reversal date falls in this period
    age = [a for a in ageing(s, client) if a["reversed"] and start <= a["reversal_on"] <= end]
    r37 = [docs_by_id.get(a["doc_id"]) or s.get(Document, a["doc_id"]) for a in age]

    out_t = _heads(sales)
    rcm_t = _heads(rcm)
    itc_all = _heads(claim + blocked)
    itc_rcm = _heads(rcm)
    rev_blocked = _heads(blocked)
    rev_r37 = _heads(r37)
    net = {k: money(itc_all[k] + itc_rcm[k] - rev_blocked[k] - rev_r37[k]) for k in ("iamt", "camt", "samt")}

    so = set_off({"igst": out_t["iamt"], "cgst": out_t["camt"], "sgst": out_t["samt"]},
                 {"igst": net["iamt"], "cgst": net["camt"], "sgst": net["samt"]})
    rcm_cash = {"igst": rcm_t["iamt"], "cgst": rcm_t["camt"], "sgst": rcm_t["samt"]}
    cash_total = money(sum(so["cash"].values()) + sum(rcm_cash.values()))

    form = next(d["form"] for d in due_dates(client, period) if d["pays_tax"] and d["form"] != "TDS deposit")
    due = next(d["due"] for d in due_dates(client, period) if d["form"] == form)
    late = late_cost(client, due, cash_total, nil=not sales and not purchases)

    held_itc = money(sum(itc_of(d) for d in held))
    big = max(sales, key=lambda d: d.cgst + d.sgst + d.igst, default=None)

    return {
        "client": client.name, "gstin": client.gstin, "period": period, "period_label": clock.period_label(period),
        "form": form, "due": due, "rule_version": rs.version,
        "table_3_1": {"a_outward_taxable": out_t, "d_inward_rcm": rcm_t},
        "table_4": {"A3_rcm": itc_rcm, "A5_all_other": itc_all, "B1_blocked_17_5": rev_blocked,
                    "B2_rule37": rev_r37, "C_net": net},
        "set_off": so, "rcm_cash": rcm_cash, "cash_payable": cash_total, "late": late,
        "summary": {
            "output_tax": money(out_t["iamt"] + out_t["camt"] + out_t["samt"]),
            "itc_claimed": money(net["iamt"] + net["camt"] + net["samt"]),
            "itc_held": held_itc, "held_suppliers": sorted({d.party_name for d in held}),
            "blocked": money(sum(itc_of(d) for d in blocked)), "rule37": money(sum(itc_of(d) for d in r37 if d)),
            "rcm": money(sum(rcm_cash.values())), "cash_payable": cash_total,
            "sales_count": len(sales), "purchase_count": len(purchases),
            "biggest_sale": {"doc_id": big.id, "inv_no": big.inv_no, "party": big.party_name,
                             "tax": money(big.cgst + big.sgst + big.igst), "inter_state": big.igst > 0} if big else None,
        },
        "cites": [rs.cite("ims").as_dict(), rs.cite("due_dates").as_dict(), rs.cite("late_fee").as_dict(),
                  rs.cite("itc_payment_condition").as_dict()],
    }


def gstr3b_json(c: dict) -> dict:
    """Portal-style GSTR-3B JSON (subset of the offline-tool schema)."""
    h = lambda x: {k: x[k] for k in ("txval", "iamt", "camt", "samt", "csamt") if k in x}  # noqa: E731
    t4 = c["table_4"]
    return {
        "gstin": c["gstin"], "ret_period": c["period"],
        "sup_details": {"osup_det": h(c["table_3_1"]["a_outward_taxable"]), "isup_rev": h(c["table_3_1"]["d_inward_rcm"])},
        "itc_elg": {
            "itc_avl": [{"ty": "ISRC", **{k: t4["A3_rcm"][k] for k in ("iamt", "camt", "samt", "csamt")}},
                        {"ty": "OTH", **{k: t4["A5_all_other"][k] for k in ("iamt", "camt", "samt", "csamt")}}],
            "itc_rev": [{"ty": "RUL", **{k: t4["B1_blocked_17_5"][k] for k in ("iamt", "camt", "samt", "csamt")}},
                        {"ty": "OTH", **{k: t4["B2_rule37"][k] for k in ("iamt", "camt", "samt", "csamt")}}],
            "itc_net": {**t4["C_net"], "csamt": 0},
        },
        "intr_ltfee": {"intr_details": {"iamt": c["late"]["interest"]}, "ltfee_details": {"camt": c["late"]["late_fee"] / 2, "samt": c["late"]["late_fee"] / 2}},
    }


def gstr1_json(s, client: Client, period: str) -> dict:
    start, end = clock.period_bounds(period)
    sales = s.execute(select(Document).where(Document.client_id == client.id, Document.kind == "sale",
                                             Document.status == "booked", Document.inv_date >= start,
                                             Document.inv_date <= end)).scalars().all()
    b2b = defaultdict(list)
    b2cs = defaultdict(lambda: {"txval": 0.0, "iamt": 0.0, "camt": 0.0, "samt": 0.0})
    hsn = defaultdict(lambda: {"qty": 0.0, "txval": 0.0, "iamt": 0.0, "camt": 0.0, "samt": 0.0})
    for d in sales:
        itm = {"num": 1, "itm_det": {"txval": d.taxable, "rt": d.rate, "iamt": d.igst, "camt": d.cgst, "samt": d.sgst, "csamt": 0}}
        if d.party_gstin:
            b2b[d.party_gstin].append({"inum": d.inv_no, "idt": d.inv_date.strftime("%d-%m-%Y"), "val": d.total,
                                       "pos": d.pos, "rchrg": "N", "inv_typ": "R", "itms": [itm]})
        else:
            k = (d.pos, d.rate)
            for f, v in (("txval", d.taxable), ("iamt", d.igst), ("camt", d.cgst), ("samt", d.sgst)):
                b2cs[k][f] += v
        hh = hsn[(d.hsn, d.rate)]
        for f, v in (("qty", d.qty), ("txval", d.taxable), ("iamt", d.igst), ("camt", d.cgst), ("samt", d.sgst)):
            hh[f] += v
    return {
        "gstin": client.gstin, "fp": period,
        "b2b": [{"ctin": k, "inv": v} for k, v in b2b.items()],
        "b2cs": [{"sply_ty": "INTRA" if pos == client.gstin[:2] else "INTER", "pos": pos, "rt": rt, "typ": "OE",
                  **{k: money(v) for k, v in vals.items()}} for (pos, rt), vals in b2cs.items()],
        "hsn": {"data": [{"num": i + 1, "hsn_sc": h, "rt": rt, **{k: money(v) for k, v in vals.items()}}
                         for i, ((h, rt), vals) in enumerate(hsn.items())]},
    }


# ======================================================================
# Cash forecast
# ======================================================================

def cash_forecast(s, client: Client) -> dict:
    fp = clock.filing_period()
    periods = [clock.prev_period(clock.prev_period(fp)), clock.prev_period(fp), fp, clock.next_period(fp)]
    bars = []
    t = clock.today()
    for p in periods:
        c = compute_3b(s, client, p)
        projected = p == clock.period_of(t)
        amt = c["cash_payable"]
        if projected:
            start, end = clock.period_bounds(p)
            elapsed = max((t - start).days + 1, 1)
            amt = money(amt * (end - start).days / elapsed) if elapsed < (end - start).days else amt
        filed = s.execute(select(ReturnDraft).where(ReturnDraft.client_id == client.id, ReturnDraft.period == p,
                                                    ReturnDraft.status == "filed")).scalar_one_or_none()
        bars.append({"period": p, "label": clock.period_label(p), "amount": amt, "due": c["due"], "form": c["form"],
                     "state": "projected" if projected else ("paid" if filed or c["due"] < t else "due")})
    cur = bars[2]
    return {"bars": bars, "keep_aside": cur["amount"], "by": cur["due"], "form": cur["form"],
            "delta_vs_last": money(cur["amount"] - bars[1]["amount"])}
