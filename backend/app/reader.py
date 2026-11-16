"""Reader: QR first, then OCR, then LLM. Each field carries its confidence and method.

1. Signed e-invoice QR (IRP JWT): GSTINs, number, date, value, main HSN. Highest trust.
2. OCR (Tesseract, if installed) + regex for the fields QR does not carry.
3. Claude vision only for what the first two could not settle.
Plus parsers for WhatsApp text / voice transcripts and UPI / bank SMS.
"""
from __future__ import annotations

import io
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path

import jwt

from . import llm, rules
from .db import DATA_DIR

log = logging.getLogger("karsaathi.reader")
IRP_PUBLIC = DATA_DIR / "mock_irp_public.pem"
IRP_PRIVATE = DATA_DIR / "mock_irp_private.pem"
GSTIN_ANY = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")


# ---------------------------------------------------------------- QR

def ensure_irp_keys():
    """The demo signs synthetic e-invoices with a mock IRP key; production would load the NIC IRP public key."""
    if IRP_PUBLIC.exists():
        return
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    IRP_PRIVATE.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    IRP_PUBLIC.write_bytes(k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))


def sign_einvoice(data: dict) -> str:
    ensure_irp_keys()
    return jwt.encode({"data": json.dumps(data), "iss": "NIC (mock)"}, IRP_PRIVATE.read_bytes(), algorithm="RS256")


def decode_qr_image(img_bytes: bytes) -> str | None:
    try:
        import cv2
        import numpy as np
        arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        det = cv2.QRCodeDetector()
        val, _, _ = det.detectAndDecode(img)
        if not val:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            val, _, _ = det.detectAndDecode(cv2.resize(gray, None, fx=2, fy=2))
        return val or None
    except Exception as e:  # noqa: BLE001
        log.info("QR decode unavailable: %s", e)
        return None


def read_signed_qr(token: str) -> dict | None:
    ensure_irp_keys()
    try:
        claims = jwt.decode(token, IRP_PUBLIC.read_bytes(), algorithms=["RS256"])
        signed = True
    except jwt.InvalidSignatureError:
        claims = jwt.decode(token, options={"verify_signature": False})
        signed = False
    except Exception:  # noqa: BLE001
        return None
    d = json.loads(claims["data"]) if isinstance(claims.get("data"), str) else claims.get("data", {})
    return {"signed": signed, "supplier_gstin": d.get("SellerGstin"), "buyer_gstin": d.get("BuyerGstin"),
            "inv_no": d.get("DocNo"), "inv_date": datetime.strptime(d["DocDt"], "%d/%m/%Y").date() if d.get("DocDt") else None,
            "total": float(d.get("TotInvVal") or 0), "hsn": d.get("MainHsnCode"), "irn": d.get("Irn"),
            "supplier_name": d.get("SellerName")}


# ---------------------------------------------------------------- OCR

def ocr_text(img_bytes: bytes) -> str | None:
    try:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(io.BytesIO(img_bytes)))
    except Exception as e:  # noqa: BLE001
        log.info("OCR unavailable: %s", e)
        return None


AMT = r"(?:Rs\.?|₹|INR)?\s*([0-9][0-9,]*\.?[0-9]{0,2})"


def regex_fields(text: str) -> dict:
    out = {}
    g = GSTIN_ANY.findall(text.upper())
    if g:
        out["supplier_gstin"] = g[0]
        if len(g) > 1:
            out["buyer_gstin"] = g[1]
    m = re.search(r"inv(?:oice)?\s*(?:no|number|#)?\.?\s*[:\-]?\s*([A-Z0-9/\-]{2,20})", text, re.I)
    if m:
        out["inv_no"] = m.group(1)
    m = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b", text)
    if m:
        dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            out["inv_date"] = date(yy + 2000 if yy < 100 else yy, mm, dd)
        except ValueError:
            pass
    for key, pat in (("taxable", r"taxable\s*(?:value|amt|amount)?"), ("cgst", r"cgst"), ("sgst", r"sgst"),
                     ("igst", r"igst"), ("total", r"(?:grand\s*)?total")):
        m = re.search(pat + r"[^0-9\n]{0,20}" + AMT, text, re.I)
        if m:
            out[key] = float(m.group(1).replace(",", ""))
    m = re.search(r"\bHSN\s*(?:/SAC)?\s*[:\-]?\s*(\d{4,8})", text, re.I)
    if m:
        out["hsn"] = m.group(1)
    return out


# ---------------------------------------------------------------- pipeline for bill images / PDFs

def read_bill(data: bytes, mime: str, own_gstin: str) -> dict:
    """Returns {fields, conf, method, steps, unclear, raw_text}."""
    rs = rules.active()
    cfg = rs.section("confidence")
    fields, conf, steps, unclear = {}, {}, [], []
    method = None

    if mime.startswith("image/"):
        token = decode_qr_image(data)
        q = read_signed_qr(token) if token else None
        if q:
            method = "qr"
            c = cfg["qr_signed"] if q["signed"] else 0.6
            for k in ("supplier_gstin", "buyer_gstin", "inv_no", "inv_date", "total", "hsn", "irn", "supplier_name"):
                if q.get(k):
                    fields[k] = q[k]
                    conf[k] = {"conf": c, "method": "qr"}
            steps.append({"step": "QR", "ok": True,
                          "msg": f"Signed e-invoice QR read ({'signature verified' if q['signed'] else 'SIGNATURE NOT VERIFIED'}), IRN {str(q.get('irn'))[:12]}…"})
        else:
            steps.append({"step": "QR", "ok": False, "msg": "No e-invoice QR found"})

    raw = None
    need = {"taxable", "cgst", "sgst", "igst", "inv_no", "inv_date", "supplier_gstin", "hsn"} - set(fields)
    if mime.startswith("image/") and need:
        raw = ocr_text(data)
        if raw:
            rf = regex_fields(raw)
            got = []
            for k, v in rf.items():
                if k not in fields:
                    fields[k] = v
                    conf[k] = {"conf": cfg["ocr_regex"], "method": "ocr"}
                    got.append(k)
            method = method or "ocr"
            steps.append({"step": "OCR", "ok": bool(got), "msg": f"OCR read {len(got)} field(s): {', '.join(got) or 'none'}"})
        else:
            steps.append({"step": "OCR", "ok": False, "msg": "Local OCR not installed; skipped"})

    # A signed QR carries the total; the taxable split is derived later from the rule rate.
    wanted = ("inv_no", "inv_date", "supplier_gstin", "total", "hsn") if method == "qr" else \
        ("inv_no", "inv_date", "supplier_gstin", "taxable", "total", "hsn")
    weak = [k for k in wanted if k not in fields or conf.get(k, {}).get("conf", 0) < cfg["auto_book_threshold"]]
    if weak and llm.available():
        try:
            r = llm.extract_invoice(data, mime)
            used = []
            for k in llm.FIELDS:
                v = r.get(k)
                if v in (None, ""):
                    continue
                c = min(float(r["confidence"].get(k, 0)), cfg["llm_cap"])
                if k not in fields or conf.get(k, {}).get("conf", 0) < c:
                    if k == "inv_date":
                        try:
                            v = date.fromisoformat(v)
                        except ValueError:
                            continue
                    fields[k] = v
                    conf[k] = {"conf": round(c, 2), "method": "llm"}
                    used.append(k)
            unclear = r.get("unclear", [])
            method = method or "llm"
            steps.append({"step": "LLM", "ok": True, "msg": f"Claude read {len(used)} remaining field(s)"})
        except Exception as e:  # noqa: BLE001
            steps.append({"step": "LLM", "ok": False, "msg": f"LLM read failed: {e}"})
    elif weak:
        steps.append({"step": "LLM", "ok": False, "msg": "LLM not configured; low-confidence fields go to review"})
    else:
        steps.append({"step": "LLM", "ok": True, "msg": "Not needed: signed QR settled every key field"})

    # sale or purchase?
    kind = "purchase"
    if fields.get("supplier_gstin") == own_gstin:
        kind = "sale"
    return {"fields": fields, "conf": conf, "method": method or "manual", "steps": steps, "unclear": unclear,
            "raw_text": raw, "kind": kind}


# ---------------------------------------------------------------- WhatsApp text / voice transcript

SALE_WORDS = r"(sold|sale|sell|becha|बेचा|bikri|ಮಾರಾಟ|ಮಾರಿದೆ)"
BUY_WORDS = r"(bought|purchased|purchase|buy|kharida|खरीदा|ಖರೀದಿ)"


def parse_text(text: str, parties: list) -> dict | None:
    t = text.strip()
    kind = "sale" if re.search(SALE_WORDS, t, re.I) else "purchase" if re.search(BUY_WORDS, t, re.I) else None
    if not kind:
        return None
    rs = rules.active()
    out, conf = {"kind": kind}, {}
    amt = re.findall(r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.\d+)?)\s*(k|lakh|l)?", t, re.I) or \
        re.findall(r"\b([0-9][0-9,]{3,}(?:\.\d+)?)\b", t)
    if amt:
        a = amt[-1]
        num, unit = (a if isinstance(a, tuple) else (a, ""))
        v = float(num.replace(",", ""))
        v *= {"k": 1e3, "lakh": 1e5, "l": 1e5}.get((unit or "").lower(), 1)
        incl = re.search(r"incl|including|with gst|inclusive", t, re.I)
        out["amount"], out["inclusive"] = v, bool(incl)
        conf["taxable"] = {"conf": 0.9, "method": "text"}
    m = re.search(r"(\d+(?:\.\d+)?)\s*(bags?|kg|kgs|tons?|nos|pcs|pieces|boxes|meters?|mtrs?|ltrs?|litres?|sqm)?\s+(?:of\s+)?([a-z][a-z ]{2,30}?)\s+(?:to|from)\b", t, re.I)
    if m:
        out["qty"] = float(m.group(1))
        out["description"] = (m.group(3) + (" " + m.group(2) if m.group(2) else "")).strip()
    hsn = rs.hsn_from_text(out.get("description", "") or t)
    if hsn:
        out["hsn"], out["description"] = hsn["hsn"], out.get("description") or hsn["description"]
        conf["hsn"] = {"conf": 0.88, "method": "text"}
    m = re.search(r"\b(?:to|from)\s+([A-Za-z][A-Za-z .&]+?)(?:\s+(?:for|at|@|₹|rs|inr|worth|of|,|\d)|$)", t, re.I)
    name = m.group(1).strip() if m else None
    party = None
    if name:
        for p in parties:
            if name.lower() in p.name.lower() or p.name.lower().startswith(name.lower().split()[0]):
                party = p
                break
    out["party_name"] = party.name if party else (name or "")
    out["party_gstin"] = party.gstin if party else None
    conf["party_name"] = {"conf": 0.95 if party else 0.6, "method": "text"}
    m = re.search(r"(\d{2,4})\s*km", t, re.I)
    if m:
        out["distance_km"] = int(m.group(1))
    m = re.search(r"\b([A-Z]{2}\s?\d{1,2}\s?[A-Z]{0,3}\s?\d{4})\b", t.upper())
    if m:
        out["vehicle_no"] = m.group(1).replace(" ", "")
    out["conf"] = conf
    return out


# ---------------------------------------------------------------- UPI / bank SMS

def parse_sms(text: str) -> dict | None:
    t = text.replace("\n", " ")
    if not re.search(r"credited|debited|paid|received|sent", t, re.I):
        return None
    m = re.search(r"(?:Rs\.?|INR|₹)\s*([0-9][0-9,]*(?:\.\d+)?)", t, re.I)
    if not m:
        return None
    amount = float(m.group(1).replace(",", ""))
    direction = "out" if re.search(r"debited|paid|sent", t, re.I) else "in"
    party = None
    m2 = re.search(r"(?:to|by|from)\s+(?:VPA\s+)?([A-Za-z][A-Za-z .&]{2,40}?)(?:\s+(?:on|ref|upi|via|a/c)|[.,]|$)", t, re.I)
    if m2:
        party = m2.group(1).strip()
    d = None
    m3 = re.search(r"(\d{1,2})[-/](\d{1,2}|[A-Za-z]{3})[-/](\d{2,4})", t)
    if m3:
        try:
            mon = int(m3.group(2)) if m3.group(2).isdigit() else datetime.strptime(m3.group(2)[:3].title(), "%b").month
            y = int(m3.group(3))
            d = date(y + 2000 if y < 100 else y, mon, int(m3.group(1)))
        except ValueError:
            d = None
    ref = re.search(r"ref(?:\s*no)?\.?\s*[:#]?\s*(\w+)", t, re.I)
    return {"amount": amount, "direction": direction, "party": party, "date": d, "ref": ref.group(1) if ref else None}
