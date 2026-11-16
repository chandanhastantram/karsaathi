"""KarSaathi API. LLMs read. Rules decide. Humans approve."""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select

from . import (agent, approvals, audit, clock, engine, ewaybill, i18n, llm, notices, portal, rules, rulewatch,
               summary)
from .db import (BILL_STORE, DATA_DIR, Client, Document, EwayBill, ImsAction, Message, Notice, Nudge, Party,
                 ReturnDraft, RuleProposal, SessionLocal, init_db)

app = FastAPI(title="KarSaathi", version="0.1.0", description="Agentic GST co-pilot for micro enterprises (filing simulated)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(portal.router)


@app.exception_handler(agent.GateError)
def _gate_error(_req, exc):
    return JSONResponse({"detail": str(exc)}, status_code=403)


@app.on_event("startup")
def _startup():
    init_db()
    s = SessionLocal()
    try:
        if not s.execute(select(Client)).first():
            from . import seed
            s.close()
            seed.run()
    finally:
        s.close()


def db():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_client(s, cid: int) -> Client:
    c = s.get(Client, cid)
    if not c:
        raise HTTPException(404, "client not found")
    return c


def doc_dict(d: Document) -> dict:
    return {k: getattr(d, k) for k in (
        "id", "client_id", "kind", "channel", "method", "status", "confidence", "inv_no", "inv_date", "party_name",
        "party_gstin", "pos", "hsn", "description", "qty", "taxable", "rate", "cgst", "sgst", "igst", "total", "rcm",
        "itc_eligible", "itc_note", "paid_on", "distance_km", "irn", "file_path", "raw_text", "field_conf", "issues",
        "question", "rule_version", "cites", "created_at")}


class By(BaseModel):
    by: str


# ======================================================================= meta

@app.get("/api/meta")
def meta(s=Depends(db)):
    clients = s.execute(select(Client).order_by(Client.id)).scalars().all()
    return {"today": clock.today(), "filing_period": clock.filing_period(), "filing_period_label": clock.period_label(clock.filing_period()),
            "rule_version": rules.active_version(), "llm": llm.available(), "model": llm.MODEL if llm.available() else None,
            "languages": i18n.LANGUAGES, "speech": i18n.SPEECH_LOCALE,
            "clients": [{"id": c.id, "name": c.name, "gstin": c.gstin, "city": c.city, "scheme": c.scheme, "language": c.language}
                        for c in clients]}


# ======================================================================= owner overview

@app.get("/api/clients/{cid}/overview")
def overview(cid: int, s=Depends(db)):
    c = get_client(s, cid)
    fp = clock.filing_period()
    comp = engine.compute_3b(s, c, fp)
    rec = engine.reconcile(s, c, fp)
    fc = engine.cash_forecast(s, c)
    total_docs = s.execute(select(func.count()).select_from(Document).where(Document.client_id == cid)).scalar()
    review = s.execute(select(func.count()).select_from(Document).where(Document.client_id == cid, Document.status == "review")).scalar()
    upcoming = sorted([d for p in (fp, clock.period_of(clock.today())) for d in engine.due_dates(c, p) if d["due"] >= clock.today()],
                      key=lambda d: d["due"])
    ewbs = []
    for e in s.execute(select(EwayBill).where(EwayBill.client_id == cid).order_by(EwayBill.id.desc())).scalars():
        d = s.get(Document, e.document_id)
        ewbs.append({"id": e.id, "status": e.status, "inv_no": d.inv_no, "party": d.party_name, "total": d.total,
                     "preflight": ewaybill.preflight(d, c, e) if e.status == "draft" else None, "watch": ewaybill.watch(e)})
    ret = s.execute(select(ReturnDraft).where(ReturnDraft.client_id == cid, ReturnDraft.period == fp)).scalars().first()
    health = []
    if not c.bank_verified:
        rc = rules.active().cite("registration")
        health.append({"level": "error", "msg": "Bank account not furnished in GST profile: registration can be suspended (Rule 10A), which blocks returns and e-way bills.",
                       "cite": rc.as_dict()})
    ageing = engine.ageing(s, c)
    return {
        "client": {"id": c.id, "name": c.name, "gstin": c.gstin, "scheme": c.scheme, "city": c.city, "language": c.language},
        "period": fp, "period_label": clock.period_label(fp),
        "kpis": {"payment_due": comp["cash_payable"], "payment_form": comp["form"], "payment_due_on": comp["due"],
                 "credit_at_risk": rec["at_risk_total"], "review": review, "documents": total_docs,
                 "next_due": upcoming[0] if upcoming else None},
        "credit_at_risk": rec["suppliers"], "ageing": ageing, "forecast": fc, "eway_bills": ewbs,
        "return": {"status": ret.status if ret else "draft", "arn": ret.arn if ret else None, "form": comp["form"],
                   "cash": comp["cash_payable"], "delta": fc["delta_vs_last"],
                   "explain": summary.explain_return(comp, i18n.supported(c.language), fc["delta_vs_last"])[:3]},
        "health": health, "upcoming": upcoming[:4], "rule_version": comp["rule_version"],
    }


# ======================================================================= documents

@app.get("/api/clients/{cid}/documents")
def documents(cid: int, status: str | None = None, kind: str | None = None, ids: str | None = None, s=Depends(db)):
    q = select(Document).where(Document.client_id == cid)
    if status:
        q = q.where(Document.status == status)
    if kind:
        q = q.where(Document.kind == kind)
    if ids:
        q = q.where(Document.id.in_([int(x) for x in ids.split(",") if x]))
    return [doc_dict(d) for d in s.execute(q.order_by(Document.inv_date.desc().nullslast(), Document.id.desc())).scalars()]


@app.get("/api/documents/{did}")
def document(did: int, s=Depends(db)):
    d = s.get(Document, did)
    if not d:
        raise HTTPException(404)
    return doc_dict(d)


class DocPatch(BaseModel):
    by: str
    fields: dict


EDITABLE = {"kind", "inv_no", "inv_date", "party_name", "party_gstin", "hsn", "description", "qty", "taxable", "rate",
            "cgst", "sgst", "igst", "total", "distance_km"}


@app.patch("/api/documents/{did}")
def review_document(did: int, body: DocPatch, s=Depends(db)):
    """Human review: correct fields, re-run the rules, book if clean."""
    d = s.get(Document, did)
    c = get_client(s, d.client_id)
    before = doc_dict(d)
    for k, v in body.fields.items():
        if k not in EDITABLE:
            continue
        if k == "inv_date" and v:
            v = date.fromisoformat(v)
        if k in ("qty", "taxable", "rate", "cgst", "sgst", "igst", "total") and v not in (None, ""):
            v = float(v)
        setattr(d, k, v)
        d.field_conf = {**(d.field_conf or {}), k: {"conf": 1.0, "method": "human"}}
    d.issues = [i for i in (d.issues or []) if i["code"] not in ("LOWCONF", "NEEDS_INFO", "DUPLICATE")]
    engine.apply_rules(d, c)
    high = [i for i in d.issues if i["severity"] == "high"]
    d.status = "review" if high else "booked"
    d.question = high[0]["msg"] if high else None
    d.confidence = 1.0 if not high else d.confidence
    audit.log(s, body.by, "document:reviewed", {"doc_id": d.id, "changed": {k: [str(before.get(k)), str(v)] for k, v in body.fields.items()},
                                                "status": d.status}, c.id)
    return doc_dict(d)


@app.post("/api/documents/{did}/reject")
def reject_document(did: int, body: By, s=Depends(db)):
    d = s.get(Document, did)
    d.status = "rejected"
    audit.log(s, body.by, "document:rejected", {"doc_id": did}, d.client_id)
    return doc_dict(d)


@app.get("/api/files/{name}")
def bill_file(name: str):
    p = (BILL_STORE / name).resolve()
    if not str(p).startswith(str(BILL_STORE.resolve())) or not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


@app.get("/api/samples")
def samples():
    d = DATA_DIR / "samples"
    return sorted(p.name for p in d.glob("*")) if d.exists() else []


@app.get("/api/samples/{name}")
def sample_file(name: str):
    p = (DATA_DIR / "samples" / name).resolve()
    if not str(p).startswith(str((DATA_DIR / "samples").resolve())) or not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


# ======================================================================= WhatsApp (in-app simulator + Twilio)

@app.post("/api/clients/{cid}/inbound")
async def inbound(cid: int, text: str = Form(""), channel: str = Form("whatsapp_text"), sender: str = Form("owner"),
                  file: UploadFile | None = File(None), s=Depends(db)):
    c = get_client(s, cid)
    media = await file.read() if file else None
    mime = file.content_type if file else None
    if file and not channel.startswith("whatsapp_"):
        channel = "whatsapp_photo"
    if file and mime == "application/pdf":
        channel = "whatsapp_pdf"
    return agent.process_inbound(s, c, text=text or None, media=media, mime=mime, filename=file.filename if file else None,
                                 channel=channel, sender=sender)


@app.get("/api/clients/{cid}/messages")
def messages(cid: int, s=Depends(db)):
    return [{"id": m.id, "direction": m.direction, "text": m.text, "media": m.media, "trace": m.trace,
             "document_id": m.document_id, "at": m.at}
            for m in s.execute(select(Message).where(Message.client_id == cid).order_by(Message.id)).scalars()]


@app.post("/webhook/whatsapp")
async def twilio_webhook(request: Request, s=Depends(db)):
    """Twilio WhatsApp sandbox webhook (form-encoded). Set TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN to fetch media."""
    form = await request.form()
    frm = (form.get("From") or "").replace("whatsapp:", "")
    c = next((c for c in s.execute(select(Client)).scalars() if c.owner_phone.replace(" ", "") == frm), None) or s.get(Client, 1)
    media = mime = None
    if int(form.get("NumMedia") or 0) > 0:
        import httpx
        auth = (os.environ.get("TWILIO_ACCOUNT_SID", ""), os.environ.get("TWILIO_AUTH_TOKEN", ""))
        r = httpx.get(form["MediaUrl0"], auth=auth, follow_redirects=True, timeout=30)
        media, mime = r.content, form.get("MediaContentType0")
    out = agent.process_inbound(s, c, text=form.get("Body") or None, media=media, mime=mime,
                                channel="whatsapp_photo" if media else "whatsapp_text", sender=frm or "owner")
    return Response(f"<Response><Message>{escape(out['reply'])}</Message></Response>", media_type="application/xml")


# ======================================================================= suppliers, IMS, nudges

@app.get("/api/clients/{cid}/reconcile")
def reconcile(cid: int, period: str | None = None, s=Depends(db)):
    c = get_client(s, cid)
    return engine.reconcile(s, c, period or clock.filing_period())


@app.get("/api/clients/{cid}/suppliers")
def suppliers(cid: int, s=Depends(db)):
    out = []
    for p in s.execute(select(Party).where(Party.client_id == cid, Party.role == "supplier")).scalars():
        out.append({"id": p.id, "name": p.name, "gstin": p.gstin, "phone": p.phone, "history": p.filing_history,
                    "risk": engine.supplier_risk(p) if p.gstin else None})
    return out


class ImsReq(BaseModel):
    by: str
    items: list[dict]  # {supplier_gstin, inv_no, action}


@app.post("/api/clients/{cid}/ims")
def ims(cid: int, body: ImsReq, s=Depends(db)):
    agent.gate(s, "ims_action", cid, {"by": body.by, "human": True, "count": len(body.items)})
    for it in body.items:
        if it["action"] not in ("accept", "reject", "pending"):
            raise HTTPException(400, "bad action")
        s.add(ImsAction(client_id=cid, supplier_gstin=it["supplier_gstin"], inv_no=it["inv_no"], action=it["action"], by=body.by))
    audit.log(s, body.by, "ims:actions", {"items": body.items}, cid)
    return {"ok": True}


class NudgeReq(BaseModel):
    supplier: str
    lang: str = "en"


@app.post("/api/clients/{cid}/nudges")
def draft_nudge(cid: int, body: NudgeReq, s=Depends(db)):
    c = get_client(s, cid)
    agent.gate(s, "draft_nudge", cid)
    rec = engine.reconcile(s, c, clock.filing_period())
    nxt = engine.reconcile(s, c, clock.period_of(clock.today()))
    rows = [r for r in rec["rows"] + nxt["rows"] if r["supplier"] == body.supplier and r["status"] in ("missing", "mismatch")]
    if not rows:
        raise HTTPException(404, "nothing to nudge")
    party = s.get(Party, rows[0]["party_id"]) if rows[0].get("party_id") else None
    n = Nudge(client_id=cid, party_id=party.id if party else 0, message=summary.nudge_text(body.supplier, rows, c.name, body.lang))
    s.add(n)
    s.flush()
    audit.log(s, "agent", "nudge:drafted", {"nudge": n.id, "supplier": body.supplier}, cid)
    return {"id": n.id, "message": n.message, "phone": party.phone if party else "", "status": n.status}


@app.post("/api/nudges/{nid}/send")
def send_nudge(nid: int, body: By, s=Depends(db)):
    n = s.get(Nudge, nid)
    n.status = "sent"
    s.add(Message(client_id=n.client_id, direction="out", text=f"[to supplier] {n.message}"))
    audit.log(s, body.by, "nudge:sent", {"nudge": nid}, n.client_id)
    return {"ok": True, "status": "sent", "simulated": True}


@app.get("/api/clients/{cid}/ageing")
def ageing(cid: int, s=Depends(db)):
    return engine.ageing(s, get_client(s, cid))


# ======================================================================= e-way bills

def ewb_dict(s, e: EwayBill, c: Client):
    d = s.get(Document, e.document_id)
    return {"id": e.id, "status": e.status, "vehicle_no": e.vehicle_no, "distance_km": e.distance_km, "ewb_no": e.ewb_no,
            "generated_at": e.generated_at, "valid_until": e.valid_until, "km_remaining": e.km_remaining,
            "approved_by": e.approved_by, "doc": doc_dict(d), "preflight": ewaybill.preflight(d, c, e), "watch": ewaybill.watch(e)}


@app.get("/api/clients/{cid}/ewaybills")
def ewaybills(cid: int, s=Depends(db)):
    c = get_client(s, cid)
    return [ewb_dict(s, e, c) for e in s.execute(select(EwayBill).where(EwayBill.client_id == cid).order_by(EwayBill.id.desc())).scalars()]


class EwbPatch(BaseModel):
    by: str
    vehicle_no: str | None = None
    distance_km: int | None = None


@app.patch("/api/ewaybills/{eid}")
def ewb_update(eid: int, body: EwbPatch, s=Depends(db)):
    e = s.get(EwayBill, eid)
    if body.vehicle_no is not None:
        e.vehicle_no = body.vehicle_no.upper().replace(" ", "").replace("-", "")
    if body.distance_km is not None:
        e.distance_km = body.distance_km
    audit.log(s, body.by, "ewb:updated", {"ewb": eid, "vehicle_no": e.vehicle_no, "distance_km": e.distance_km}, e.client_id)
    return ewb_dict(s, e, s.get(Client, e.client_id))


@app.post("/api/ewaybills/{eid}/generate")
def ewb_generate(eid: int, body: By, s=Depends(db)):
    e = s.get(EwayBill, eid)
    c = s.get(Client, e.client_id)
    d = s.get(Document, e.document_id)
    pf = ewaybill.preflight(d, c, e)
    if not pf["ready"]:
        raise HTTPException(409, "Pre-flight not passed: " + "; ".join(x["msg"] for x in pf["checks"] if not x["ok"]))
    if not c.bank_verified:
        raise HTTPException(409, "GSTIN at risk of suspension (bank details missing); fix before generating e-way bills")
    agent.gate(s, "generate_ewb", c.id, {"by": body.by, "human": True, "ewb": eid})
    ewaybill.generate(e, body.by)
    audit.log(s, body.by, "ewb:generated (simulated)", {"ewb": eid, "ewb_no": e.ewb_no, "valid_until": e.valid_until}, c.id)
    return ewb_dict(s, e, c)


class ExtendReq(BaseModel):
    by: str
    km_remaining: int


@app.post("/api/ewaybills/{eid}/extend")
def ewb_extend(eid: int, body: ExtendReq, s=Depends(db)):
    e = s.get(EwayBill, eid)
    w = ewaybill.watch(e)
    if not w or not w["can_extend"]:
        raise HTTPException(409, "Extension is allowed only from 8 hours before to 8 hours after expiry")
    agent.gate(s, "generate_ewb", e.client_id, {"by": body.by, "human": True, "ewb": eid, "op": "extend"})
    ewaybill.extend(e, body.km_remaining)
    audit.log(s, body.by, "ewb:extended (simulated)", {"ewb": eid, "valid_until": e.valid_until}, e.client_id)
    return ewb_dict(s, e, s.get(Client, e.client_id))


@app.get("/api/kit/{eid}")
def checkpoint_kit(eid: int, s=Depends(db)):
    """No-login checkpoint kit for the driver: what an officer will ask for."""
    e = s.get(EwayBill, eid)
    if not e or not e.ewb_no:
        raise HTTPException(404)
    c = s.get(Client, e.client_id)
    d = s.get(Document, e.document_id)
    return {"ewb_no": e.ewb_no, "valid_until": e.valid_until, "vehicle_no": e.vehicle_no, "from": f"{c.name} ({c.gstin})",
            "to": f"{d.party_name} ({d.party_gstin or 'URP'})", "invoice": d.inv_no, "invoice_date": d.inv_date,
            "value": d.total, "hsn": d.hsn, "description": d.description, "simulated": True}


# ======================================================================= returns

def _return_payload(s, c: Client, period: str):
    comp = engine.compute_3b(s, c, period)
    return comp, {"form": comp["form"], "gstr3b": engine.gstr3b_json(comp), "cash_payable": comp["cash_payable"],
                  "rule_version": comp["rule_version"]}


@app.get("/api/clients/{cid}/return")
def get_return(cid: int, period: str | None = None, lang: str | None = None, s=Depends(db)):
    c = get_client(s, cid)
    period = period or clock.filing_period()
    comp, payload = _return_payload(s, c, period)
    fc = engine.cash_forecast(s, c)
    r = s.execute(select(ReturnDraft).where(ReturnDraft.client_id == cid, ReturnDraft.period == period)).scalars().first()
    stale = bool(r and r.status in ("prepared", "approved") and audit.sha256_json(payload) != r.payload_hash)
    return {"computation": comp, "payload": payload, "gstr1": engine.gstr1_json(s, c, period),
            "explain": summary.explain_return(comp, i18n.supported(lang or c.language), fc["delta_vs_last"] if period == clock.filing_period() else None),
            "record": {"status": r.status if r else "draft", "maker": r.maker if r else None, "maker_at": r.maker_at if r else None,
                       "checker": r.checker if r else None, "checker_at": r.checker_at if r else None,
                       "signature": r.signature if r else None, "arn": r.arn if r else None, "filed_at": r.filed_at if r else None,
                       "payload_hash": r.payload_hash if r else audit.sha256_json(payload), "stale": stale},
            "review_pending": s.execute(select(func.count()).select_from(Document).where(Document.client_id == cid, Document.status == "review")).scalar()}


def _record(s, cid, period, form):
    r = s.execute(select(ReturnDraft).where(ReturnDraft.client_id == cid, ReturnDraft.period == period)).scalars().first()
    if not r:
        r = ReturnDraft(client_id=cid, period=period, form=form)
        s.add(r)
        s.flush()
    if form and r.status != "filed":
        r.form = form
    return r


class ReturnAct(BaseModel):
    by: str
    period: str | None = None


@app.post("/api/clients/{cid}/return/prepare")
def prepare_return(cid: int, body: ReturnAct, s=Depends(db)):
    c = get_client(s, cid)
    period = body.period or clock.filing_period()
    comp, payload = _return_payload(s, c, period)
    agent.gate(s, "draft_return", cid)
    r = _record(s, cid, period, comp["form"])
    try:
        approvals.prepare(r, payload, body.by)
    except approvals.ApprovalError as e:
        raise HTTPException(409, str(e))
    audit.log(s, body.by, "return:prepared (maker)", {"period": period, "form": r.form, "hash": r.payload_hash}, cid)
    return {"status": r.status, "hash": r.payload_hash}


@app.post("/api/clients/{cid}/return/check")
def check_return(cid: int, body: ReturnAct, s=Depends(db)):
    c = get_client(s, cid)
    period = body.period or clock.filing_period()
    r = _record(s, cid, period, "")
    _, payload = _return_payload(s, c, period)
    if audit.sha256_json(payload) != r.payload_hash:
        raise HTTPException(409, "Books changed after the owner prepared this return. Ask the owner to prepare it again.")
    try:
        approvals.check(r, body.by)
    except approvals.ApprovalError as e:
        raise HTTPException(409, str(e))
    audit.log(s, body.by, "return:approved (checker)", {"period": period, "signature": r.signature}, cid)
    return {"status": r.status, "signature": r.signature}


@app.post("/api/clients/{cid}/return/file")
def file_return(cid: int, body: ReturnAct, s=Depends(db)):
    c = get_client(s, cid)
    period = body.period or clock.filing_period()
    r = _record(s, cid, period, "")
    if r.status != "approved" or not approvals.verify(r):
        agent.gate(s, "file_return", cid, None, raise_=False)  # logs the blocked attempt (committed)
        return JSONResponse({"detail": "Blocked: filing needs the owner's preparation and the accountant's signed approval."}, status_code=403)
    agent.gate(s, "file_return", cid, {"by": body.by, "human": True, "signature": r.signature})
    ack = portal.file_return(c.gstin, r.form, period, r.payload, r.signature)
    r.arn, r.filed_at, r.status = ack["arn"], clock.now(), "filed"
    audit.log(s, body.by, "return:filed (simulated)", {"period": period, "arn": r.arn}, cid)
    return {"status": r.status, "arn": r.arn, "ack": ack}


@app.get("/api/clients/{cid}/calendar")
def calendar(cid: int, s=Depends(db)):
    c = get_client(s, cid)
    fp = clock.filing_period()
    out = []
    for p in (clock.prev_period(fp), fp, clock.period_of(clock.today())):
        comp = engine.compute_3b(s, c, p)
        for d in engine.due_dates(c, p):
            filed = s.execute(select(ReturnDraft).where(ReturnDraft.client_id == cid, ReturnDraft.period == p,
                                                        ReturnDraft.status == "filed")).scalar_one_or_none()
            cost = engine.late_cost(c, d["due"], comp["cash_payable"] if d["pays_tax"] else 0, on=d["due"] + timedelta(days=10))
            out.append({**d, "period_label": clock.period_label(p), "done": bool(filed) or d["due"] < clock.today(),
                        "late_10_days": round(cost["late_fee"] + cost["interest"])})
    return sorted(out, key=lambda x: x["due"])


# ======================================================================= notices

class NoticeReq(BaseModel):
    text: str
    lang: str = "en"


@app.post("/api/clients/{cid}/notices")
def read_notice(cid: int, body: NoticeReq, s=Depends(db)):
    c = get_client(s, cid)
    agent.gate(s, "explain_notice", cid)
    res = notices.explain(body.text, body.lang, c.name, clock.today())
    n = Notice(client_id=cid, text=body.text, result=res)
    s.add(n)
    s.flush()
    audit.log(s, "agent", "notice:explained", {"notice": n.id, "form": res.get("form"), "engine": res.get("engine")}, cid)
    return {"id": n.id, **res}


# ======================================================================= rules

@app.get("/api/rules")
def rules_view():
    rs = rules.active()
    return {"active": rs.version, "versions": rules.list_versions(), "data": rs.data,
            "simulated_advisory": rulewatch.SIMULATED_ADVISORY}


@app.get("/api/rules/{version}")
def rules_version(version: str):
    if version not in rules.list_versions():
        raise HTTPException(404)
    return rules.load(version).data


class Advisory(BaseModel):
    text: str | None = None


def prop_dict(p: RuleProposal):
    return {"id": p.id, "advisory": p.advisory, "base_version": p.base_version, "new_version": p.new_version,
            "changes": p.changes, "status": p.status, "approved_by": p.approved_by, "impact": p.impact, "created_at": p.created_at}


@app.post("/api/rules/advisory")
def advisory(body: Advisory, s=Depends(db)):
    return prop_dict(rulewatch.propose(s, body.text or rulewatch.SIMULATED_ADVISORY))


@app.get("/api/rules/proposals/all")
def proposals(s=Depends(db)):
    return [prop_dict(p) for p in s.execute(select(RuleProposal).order_by(RuleProposal.id.desc())).scalars()]


@app.post("/api/rules/proposals/{pid}/approve")
def approve_proposal(pid: int, body: By, s=Depends(db)):
    p = s.get(RuleProposal, pid)
    try:
        out = rulewatch.approve(s, p, body.by)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {**prop_dict(p), **out}


@app.post("/api/rules/proposals/{pid}/reject")
def reject_proposal(pid: int, body: By, s=Depends(db)):
    p = s.get(RuleProposal, pid)
    p.status, p.approved_by = "rejected", body.by
    audit.log(s, body.by, "rules:rejected", {"proposal": pid})
    return prop_dict(p)


# ======================================================================= accountant console

@app.get("/api/console")
def console(s=Depends(db)):
    fp = clock.filing_period()
    out = []
    for c in s.execute(select(Client).order_by(Client.id)).scalars():
        docs = s.execute(select(func.count()).select_from(Document).where(Document.client_id == c.id)).scalar()
        review = s.execute(select(Document).where(Document.client_id == c.id, Document.status == "review")).scalars().all()
        rec = engine.reconcile(s, c, fp)
        comp = engine.compute_3b(s, c, fp)
        r = s.execute(select(ReturnDraft).where(ReturnDraft.client_id == c.id, ReturnDraft.period == fp)).scalars().first()
        out.append({"id": c.id, "name": c.name, "gstin": c.gstin, "city": c.city, "scheme": c.scheme, "documents": docs,
                    "to_review": len(review), "credit_at_risk": rec["at_risk_total"], "cash_payable": comp["cash_payable"],
                    "form": comp["form"], "due": comp["due"], "return_status": r.status if r else "draft",
                    "bank_verified": c.bank_verified,
                    "queue": [{"id": d.id, "kind": d.kind, "party": d.party_name, "inv_no": d.inv_no, "question": d.question,
                               "confidence": d.confidence} for d in review[:6]]})
    return {"period": fp, "period_label": clock.period_label(fp), "clients": out,
            "totals": {"documents": sum(x["documents"] for x in out), "to_review": sum(x["to_review"] for x in out)}}


# ======================================================================= audit + admin

@app.get("/api/audit")
def audit_log(client_id: int | None = None, limit: int = 200, s=Depends(db)):
    from .db import AuditLog
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if client_id:
        q = q.where((AuditLog.client_id == client_id) | (AuditLog.client_id == None))  # noqa: E711
    return [{"id": a.id, "at": a.at, "actor": a.actor, "action": a.action, "client_id": a.client_id, "detail": a.detail,
             "prev_hash": a.prev_hash, "hash": a.hash} for a in s.execute(q).scalars()]


@app.get("/api/audit/verify")
def audit_verify(s=Depends(db)):
    return audit.verify(s)


@app.post("/api/admin/reseed")
def reseed():
    from . import seed
    seed.run()
    return {"ok": True}


# ======================================================================= frontend (built)

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="ui")
