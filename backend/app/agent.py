"""KarSaathi agent: capture -> read -> validate -> compute -> check -> confidence gate.

The agent works only through allow-listed tools. Three actions are *gated*: they refuse to run
without a human approval object (filing, IMS accept/reject, e-way bill generation)."""
from __future__ import annotations

import re
import uuid
from datetime import date

from sqlalchemy import select

from . import audit, clock, engine, ewaybill, i18n, llm, reader, rules, summary
from .db import BILL_STORE, Client, Document, EwayBill, Message, Party
from .validators import expected_tax, money


class GateError(PermissionError):
    pass


SAFE_TOOLS = {"read_bill", "parse_text", "parse_sms", "apply_rules", "find_duplicate", "supplier_risk",
              "ewb_preflight", "draft_nudge", "draft_return", "explain_notice", "query"}
GATED_TOOLS = {"file_return", "ims_action", "generate_ewb"}


def gate(s, tool: str, client_id: int | None, approval: dict | None = None, raise_: bool = True):
    """Every agent tool call passes through here. Unknown tools and unapproved gated tools are refused and logged.
    With raise_=False a refusal returns False so the caller can commit the audit entry before answering 403."""
    if tool in SAFE_TOOLS:
        return True
    if tool in GATED_TOOLS:
        if approval and approval.get("by") and approval.get("human") is True:
            audit.log(s, approval["by"], f"approved:{tool}", {"approval": approval}, client_id)
            return True
        audit.log(s, "agent", f"blocked:{tool}", {"reason": "no signed human approval"}, client_id)
        if not raise_:
            return False
        raise GateError(f"'{tool}' needs a human approval")
    audit.log(s, "agent", f"blocked:{tool}", {"reason": "not on allow-list"}, client_id)
    raise GateError(f"'{tool}' is not an allowed tool")


# ---------------------------------------------------------------------- helpers

def _next_sale_no(s, client: Client) -> str:
    t = clock.today()
    fy = f"{t.year % 100 if t.month >= 4 else t.year % 100 - 1}-{(t.year % 100 + 1) if t.month >= 4 else t.year % 100}"
    prefix = "".join(w[0] for w in client.name.split()[:2]).upper()
    nums = [int(m.group(1)) for (no,) in s.execute(select(Document.inv_no).where(Document.client_id == client.id, Document.kind == "sale"))
            if (m := re.search(r"/(\d+)$", no or ""))]
    return f"{prefix}/{fy}/{max(nums, default=0) + 1:04d}"


def _parties(s, client_id):
    return s.execute(select(Party).where(Party.client_id == client_id)).scalars().all()


def _gate_confidence(doc: Document, threshold: float) -> tuple[bool, str | None]:
    critical = ["inv_no", "inv_date", "taxable", "party_name"] + (["supplier_gstin"] if doc.kind == "purchase" and not doc.rcm else [])
    low = [(k, v) for k, v in (doc.field_conf or {}).items() if k in critical and v.get("conf", 1) < threshold]
    missing = [k for k in critical if k in ("inv_no", "inv_date") and not getattr(doc, k)]
    high_issue = next((i for i in doc.issues if i["severity"] == "high"), None)
    doc.confidence = round(min([v.get("conf", 1) for v in (doc.field_conf or {}).values()] or [1.0]), 2)
    if missing:
        return False, f"Please send the {' and '.join(m.replace('inv_', 'invoice ') for m in missing)} for this bill."
    if low:
        k, _ = low[0]
        return False, f"I am not sure about the {k.replace('_', ' ')} on this bill. Please confirm it."
    if high_issue:
        return False, f"Problem on this bill: {high_issue['msg']}. Shall I keep it aside for the accountant?"
    return True, None


def _confirm_line(doc: Document) -> str:
    tax = doc.cgst + doc.sgst + doc.igst
    who = "to" if doc.kind == "sale" else "from"
    line = f"Booked {doc.kind} {doc.inv_no} {who} {doc.party_name}: {summary.inr(doc.total)} (GST {summary.inr(tax)}, {doc.rate:g}% HSN {doc.hsn})."
    if doc.kind == "purchase" and not doc.itc_eligible:
        line += f" No credit: {doc.itc_note}."
    if doc.rcm:
        line += " Reverse charge: you pay this GST."
    return line + f" [rules v{doc.rule_version}]"


# ---------------------------------------------------------------------- main entry

def process_inbound(s, client: Client, text: str | None = None, media: bytes | None = None,
                    mime: str | None = None, filename: str | None = None, channel: str = "whatsapp_text",
                    sender: str = "owner") -> dict:
    trace = []
    rs = rules.active()
    th = rs.section("confidence")["auto_book_threshold"]

    def step(name, ok, msg, **extra):
        trace.append({"step": name, "ok": ok, "msg": msg, **extra})

    # 1. Capture
    path = None
    if media:
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf", "image/webp": ".webp"}.get(mime or "", ".bin")
        path = BILL_STORE / f"{client.id}_{uuid.uuid4().hex[:10]}{ext}"
        path.write_bytes(media)
    msg_in = Message(client_id=client.id, direction="in", text=text or "", media=path.name if path else None)
    s.add(msg_in)
    s.flush()
    step("Capture", True, f"Received {'file ' + (filename or path.name) if media else 'message'} from {sender} on WhatsApp")
    audit.log(s, sender, "inbound", {"channel": channel, "text": (text or "")[:200], "file": path.name if path else None}, client.id)

    doc = None
    reply = None

    # 2. Read
    if media:
        gate(s, "read_bill", client.id)
        r = reader.read_bill(media, mime or "image/jpeg", client.gstin)
        for st in r["steps"]:
            step("Read · " + st["step"], st["ok"], st["msg"])
        f = r["fields"]
        doc = Document(client_id=client.id, kind=r["kind"], channel=channel, method=r["method"],
                       inv_no=str(f.get("inv_no") or ""), inv_date=f.get("inv_date"),
                       party_name=(f.get("buyer_name") if r["kind"] == "sale" else f.get("supplier_name")) or "",
                       party_gstin=f.get("buyer_gstin") if r["kind"] == "sale" else f.get("supplier_gstin"),
                       hsn=str(f.get("hsn") or "")[:8], description=f.get("description") or "", qty=float(f.get("qty") or 0),
                       taxable=float(f.get("taxable") or 0), cgst=float(f.get("cgst") or 0), sgst=float(f.get("sgst") or 0),
                       igst=float(f.get("igst") or 0), total=float(f.get("total") or 0), irn=f.get("irn"),
                       file_path=path.name if path else None, raw_text=r["raw_text"], field_conf=r["conf"], issues=[])
        if r["kind"] == "purchase" and doc.party_gstin and not doc.party_name:
            p = next((p for p in _parties(s, client.id) if p.gstin == doc.party_gstin), None)
            doc.party_name = p.name if p else doc.party_gstin
            doc.field_conf["party_name"] = {"conf": 0.99 if p else 0.7, "method": "master" if p else "qr"}
        elif "party_name" not in doc.field_conf:
            doc.field_conf["party_name"] = doc.field_conf.get("supplier_name") or doc.field_conf.get("buyer_name") or {"conf": 0.5, "method": "?"}
        # QR carries only the total: split it with the rule rate (code, not model)
        if r["method"] == "qr" and not doc.taxable and doc.total:
            rate, _ = rs.rate(doc.hsn, doc.inv_date or clock.today())
            if rate is not None:
                doc.taxable = money(doc.total / (1 + rate / 100))
                s_state, pos = engine.supply_states(doc, client)
                exp = expected_tax(doc.taxable, rate, s_state == pos)
                doc.cgst, doc.sgst, doc.igst = exp["cgst"], exp["sgst"], exp["igst"]
                doc.total = money(doc.taxable + doc.cgst + doc.sgst + doc.igst)
                doc.field_conf["taxable"] = {"conf": 0.97, "method": "qr+rule"}
                step("Read · split", True, f"Split signed total into taxable {summary.inr(doc.taxable)} + tax at {rate:g}% (rule table)")
        if r["unclear"]:
            u = r["unclear"][0]
            doc.question = f"Is the {u['field'].replace('_', ' ')} {' or '.join(u['options'])}?"
    elif text:
        sms = reader.parse_sms(text) if re.search(r"(credited|debited)\b.*(a/c|upi|ref)", text, re.I) else None
        vno = re.sub(r"[\s-]", "", text.strip().upper())
        if sms:
            gate(s, "parse_sms", client.id)
            return _handle_payment(s, client, sms, msg_in, trace, step)
        if re.fullmatch(r"[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{4}|\d{2}BH\d{4}[A-Z]{1,2}", vno):
            return _handle_vehicle(s, client, vno, msg_in, trace, step)
        gate(s, "parse_text", client.id)
        p = reader.parse_text(text, _parties(s, client.id))
        if not p:
            ans = ask(s, client, text)
            step("Ask", True, "Question answered from tools" + (" (Claude, read-only tools)" if llm.available() else " (rule-based)"))
            return _reply(s, client, msg_in, ans, trace)
        step("Read · text", True, f"Parsed a {p['kind']} from the {'voice note' if channel == 'voice' else 'message'}")
        rate, _ = rs.rate(p.get("hsn", ""), clock.today())
        amount = p.get("amount", 0)
        taxable = money(amount / (1 + (rate or 0) / 100)) if p.get("inclusive") and rate else amount
        doc = Document(client_id=client.id, kind=p["kind"], channel=channel, method="text",
                       inv_no=_next_sale_no(s, client) if p["kind"] == "sale" else "", inv_date=clock.today(),
                       party_name=p.get("party_name", ""), party_gstin=p.get("party_gstin"), hsn=p.get("hsn", ""),
                       description=p.get("description", ""), qty=p.get("qty", 0), taxable=taxable,
                       distance_km=p.get("distance_km"), raw_text=text, field_conf=p["conf"], issues=[])
        doc.field_conf.update({"inv_no": {"conf": 1.0 if doc.inv_no else 0, "method": "series"},
                               "inv_date": {"conf": 1.0, "method": "today"}})
        if p.get("vehicle_no"):
            doc._vehicle = p["vehicle_no"]
        if not p.get("party_gstin") and p["kind"] == "sale" and p.get("party_name"):
            doc.question = f"Is {p['party_name']} GST-registered? Send their GSTIN, or reply 'no' for a B2C sale."
    else:
        return _reply(s, client, msg_in, "Send a bill photo, PDF, voice note or UPI SMS.", trace)

    # 3. Validate
    gate(s, "find_duplicate", client.id)
    dup = engine.find_duplicate(s, doc)
    if dup:
        doc.issues = [{"code": "DUPLICATE", "severity": "high", "msg": f"Same invoice {dup.inv_no} from {dup.party_name} already booked (#{dup.id})"}]
        step("Validate", False, f"Duplicate of document #{dup.id}")

    # 4. Compute
    gate(s, "apply_rules", client.id)
    engine.apply_rules(doc, client, rs)
    step("Validate", not any(i["severity"] == "high" for i in doc.issues),
         "; ".join(i["msg"] for i in doc.issues) or "GSTIN check digit, HSN, tax arithmetic and place of supply OK")
    step("Compute", True, f"{doc.rate:g}% on {summary.inr(doc.taxable)} → CGST {summary.inr(doc.cgst)} SGST {summary.inr(doc.sgst)} IGST {summary.inr(doc.igst)}"
         if doc.rate is not None else "Rate unknown", cites=doc.cites)

    # 6. Confidence gate (before checks so the checks know the status)
    ok, q = _gate_confidence(doc, th)
    doc.question = doc.question or q
    doc.status = "booked" if ok and not doc.question else "review"
    if not ok and doc.question is None:
        doc.question = q
    if doc.kind == "purchase" and not doc.inv_no:
        doc.status = "review"
    s.add(doc)
    s.flush()
    msg_in.document_id = doc.id

    # 5. Checks
    lines = []
    if doc.kind == "purchase" and doc.party_gstin:
        gate(s, "supplier_risk", client.id)
        party = next((p for p in _parties(s, client.id) if p.gstin == doc.party_gstin), None)
        if party:
            risk = engine.supplier_risk(party, period_filed=False)
            step("Check · supplier", True, f"{party.name}: {risk['level']} risk of not reporting (p={risk['p_miss']})")
            if risk["level"] != "Low" and doc.itc_eligible:
                lines.append(f"{party.name} often files late; {summary.inr(engine.itc_of(doc))} credit at risk. I will remind them before the 11th.")
    if ewaybill.needs_ewb(doc) and doc.status != "rejected":
        gate(s, "ewb_preflight", client.id)
        ewb = EwayBill(client_id=client.id, document_id=doc.id, distance_km=doc.distance_km or 0,
                       vehicle_no=getattr(doc, "_vehicle", None), transporter_phone="")
        s.add(ewb)
        s.flush()
        pf = ewaybill.preflight(doc, client, ewb)
        step("Check · e-way bill", pf["ready"], f"E-way bill needed (value {summary.inr(doc.total)}); Part A pre-filled. " +
             ("Ready for approval." if pf["ready"] else "Waiting: " + "; ".join(c["msg"] for c in pf["checks"] if not c["ok"])))
        if not ewb.vehicle_no:
            lines.append(f"E-way bill Part A is ready for {doc.inv_no}. I've asked the transporter for the vehicle number.")
            s.add(Message(client_id=client.id, direction="out",
                          text=f"[to transporter] Namaste, please send the vehicle number for {client.name} invoice {doc.inv_no} ({doc.party_name}, {doc.distance_km or '?'} km)."))
        else:
            lines.append(f"E-way bill pre-flight done for {doc.inv_no}. Open the app to approve and generate.")

    step("Confidence gate", doc.status == "booked",
         f"Confidence {doc.confidence:.2f} (threshold {th}) → " + ("booked" if doc.status == "booked" else "review queue"))
    audit.log(s, "agent", "document:" + doc.status, {"doc_id": doc.id, "inv_no": doc.inv_no, "method": doc.method,
                                                    "confidence": doc.confidence, "rule_version": doc.rule_version,
                                                    "issues": doc.issues}, client.id)

    if doc.status == "booked":
        reply = _confirm_line(doc)
    else:
        reply = f"Got it ({doc.kind}{' ' + doc.inv_no if doc.inv_no else ''}{' from ' + doc.party_name if doc.party_name and doc.kind == 'purchase' else ''}). {doc.question}"
    if lines:
        reply += "\n" + "\n".join(lines)
    return _reply(s, client, msg_in, reply, trace, doc)


def _reply(s, client, msg_in, text, trace, doc=None):
    msg_in.trace = trace
    s.add(Message(client_id=client.id, direction="out", text=text, document_id=doc.id if doc else None))
    s.flush()
    return {"reply": text, "trace": trace, "document_id": doc.id if doc else None}


def _handle_payment(s, client, sms, msg_in, trace, step):
    step("Read · SMS", True, f"UPI/bank SMS: {summary.inr(sms['amount'])} {'paid to' if sms['direction'] == 'out' else 'received from'} {sms['party'] or '?'}")
    kind = "purchase" if sms["direction"] == "out" else "sale"
    cands = s.execute(select(Document).where(Document.client_id == client.id, Document.kind == kind,
                                             Document.status == "booked", Document.paid_on == None)).scalars().all()  # noqa: E711
    name = (sms["party"] or "").lower()
    match = None
    for d in sorted(cands, key=lambda d: d.inv_date or date.min):
        if abs(d.total - sms["amount"]) <= 1 and (not name or name.split()[0] in d.party_name.lower()):
            match = d
            break
    if match:
        match.paid_on = sms["date"] or clock.today()
        step("Match", True, f"Matched to {match.inv_no} ({match.party_name}); marked paid on {match.paid_on:%d %b}")
        extra = ""
        if kind == "purchase":
            age = (match.paid_on - match.inv_date).days if match.inv_date else 0
            extra = f" Paid within {age} days, so the 180-day credit rule is satisfied." if age <= 180 else \
                f" Paid after {age} days: credit reversed earlier can now be re-claimed."
        reply = f"Payment of {summary.inr(sms['amount'])} recorded against {match.inv_no} ({match.party_name}).{extra}"
        audit.log(s, "agent", "payment:matched", {"doc_id": match.id, "amount": sms["amount"], "ref": sms["ref"]}, client.id)
    else:
        step("Match", False, "No open invoice with this amount; kept for the accountant")
        reply = f"Noted a payment of {summary.inr(sms['amount'])}. I couldn't match it to a bill; the accountant will check."
        audit.log(s, "agent", "payment:unmatched", sms, client.id)
    return _reply(s, client, msg_in, reply, trace, match)


def _handle_vehicle(s, client, vno, msg_in, trace, step):
    ewb = s.execute(select(EwayBill).where(EwayBill.client_id == client.id, EwayBill.status == "draft")
                    .order_by(EwayBill.id.desc())).scalars().first()
    if not ewb:
        return _reply(s, client, msg_in, f"Vehicle {vno} noted, but there is no pending e-way bill.", trace)
    ewb.vehicle_no = vno
    doc = s.get(Document, ewb.document_id)
    pf = ewaybill.preflight(doc, client, ewb)
    step("E-way bill", pf["ready"], f"Vehicle {vno} attached to {doc.inv_no}; " + ("pre-flight passed" if pf["ready"] else "pre-flight still failing"))
    audit.log(s, "transporter", "ewb:vehicle", {"ewb_id": ewb.id, "vehicle_no": vno}, client.id)
    bad = [c["msg"] for c in pf["checks"] if not c["ok"]]
    reply = (f"Vehicle {vno} added to e-way bill for {doc.inv_no}. Pre-flight passed; owner approval needed to generate."
             if pf["ready"] else f"Vehicle {vno} added, but: {'; '.join(bad)}")
    return _reply(s, client, msg_in, reply, trace, doc)


# ---------------------------------------------------------------------- read-only Q&A

def _tool_specs():
    empty = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    return [
        {"name": "get_return_summary", "description": "This filing period's GST position: output tax, credit claimed, credit held back, cash payable, due date, late fee rules.", "input_schema": empty, "strict": True},
        {"name": "get_credit_at_risk", "description": "Suppliers whose invoices are missing or mismatched in IMS/GSTR-2B, with credit at risk and risk level.", "input_schema": empty, "strict": True},
        {"name": "get_due_dates", "description": "Upcoming GST and TDS due dates with late fee per day.", "input_schema": empty, "strict": True},
        {"name": "get_eway_bills", "description": "E-way bills: drafts waiting for vehicle numbers, generated ones and expiry alerts.", "input_schema": empty, "strict": True},
        {"name": "get_review_queue", "description": "Documents waiting for a human because the agent was unsure.", "input_schema": empty, "strict": True},
    ]


def query_tool(s, client: Client, name: str) -> dict:
    gate(s, "query", client.id)
    fp = clock.filing_period()
    if name == "get_return_summary":
        c = engine.compute_3b(s, client, fp)
        return {"period": c["period_label"], "form": c["form"], "due": c["due"], **c["summary"], "rule_version": c["rule_version"],
                "late_fee_per_day": 50, "interest_pct": 18}
    if name == "get_credit_at_risk":
        r = engine.reconcile(s, client, fp)
        return {"period": clock.period_label(fp), "total_at_risk": r["at_risk_total"],
                "suppliers": [{"name": x["supplier"], "at_risk": x["at_risk"], "level": x["risk"]["level"]} for x in r["suppliers"]]}
    if name == "get_due_dates":
        out = []
        for p in (fp, clock.period_of(clock.today())):
            for d in engine.due_dates(client, p):
                if d["due"] >= clock.today():
                    out.append({"form": d["form"], "period": clock.period_label(p), "due": d["due"]})
        return {"rule_version": rules.active_version(), "due": sorted(out, key=lambda x: x["due"])[:5]}
    if name == "get_eway_bills":
        out = []
        for e in s.execute(select(EwayBill).where(EwayBill.client_id == client.id)).scalars():
            d = s.get(Document, e.document_id)
            w = ewaybill.watch(e)
            out.append({"invoice": d.inv_no, "status": e.status, "vehicle": e.vehicle_no, "alert": w["msg"] if w else None})
        return {"eway_bills": out}
    if name == "get_review_queue":
        docs = s.execute(select(Document).where(Document.client_id == client.id, Document.status == "review")).scalars().all()
        return {"count": len(docs), "items": [{"id": d.id, "kind": d.kind, "party": d.party_name, "question": d.question} for d in docs[:10]]}
    raise GateError(f"unknown tool {name}")


def ask(s, client: Client, question: str) -> str:
    lang = i18n.supported(client.language)
    if llm.available():
        try:
            return llm.run_agent(question, _tool_specs(), lambda n, _a: query_tool(s, client, n), lang, client.name)
        except Exception as e:  # noqa: BLE001
            audit.log(s, "agent", "llm:error", {"error": str(e)[:300]}, client.id)
    q = question.lower()
    fp = clock.filing_period()
    if re.search(r"due|date|deadline|last date|kab|ಯಾವಾಗ", q):
        d = query_tool(s, client, "get_due_dates")["due"]
        return "Due: " + "; ".join(f"{x['form']} ({x['period']}) by {x['due']:%d %b}" for x in d) + f" [rules v{rules.active_version()}]"
    if re.search(r"supplier|credit|itc|risk|2b|ims", q):
        r = query_tool(s, client, "get_credit_at_risk")
        if not r["suppliers"]:
            return "All supplier invoices for this period are in your GSTR-2B."
        return f"{summary.inr(r['total_at_risk'])} credit at risk: " + ", ".join(f"{x['name']} {summary.inr(x['at_risk'])} ({x['level']})" for x in r["suppliers"][:3])
    if re.search(r"eway|e-way|ewb|truck|vehicle|lorry", q):
        e = query_tool(s, client, "get_eway_bills")["eway_bills"]
        return "E-way bills: " + ("; ".join(f"{x['invoice']}: {x['alert'] or x['status']}" for x in e) or "none.")
    if re.search(r"review|pending|doubt", q):
        r = query_tool(s, client, "get_review_queue")
        return f"{r['count']} document(s) need a look." + (" First: " + (r["items"][0]["question"] or "") if r["items"] else "")
    c = engine.compute_3b(s, client, fp)
    delta = engine.cash_forecast(s, client)["delta_vs_last"]
    return " ".join(x["text"] for x in summary.explain_return(c, lang, delta)[:3]) + f" [rules v{c['rule_version']}]"
