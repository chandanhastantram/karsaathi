"""Synthetic data for the demo. Fictional businesses only; no real taxpayer data.

Run:  python -m app.seed
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from PIL import Image, ImageDraw, ImageFont

from . import audit, clock, engine, portal, reader, rules
from .db import (DATA_DIR, Client, Document, EwayBill, Message, Party, ReturnDraft, SessionLocal, reset_db)
from .validators import expected_tax, make_gstin, money

R = random.Random(42)
SAMPLES = DATA_DIR / "samples"


def pan(kind="F"):
    L = "ABCDEFGHJKLMNPRSTUVWXYZ"
    return "A" + R.choice(L) + R.choice(L) + kind + R.choice(L) + f"{R.randint(1000, 9999)}" + R.choice(L)


def months_back(n):
    t = clock.today()
    out = []
    y, m = t.year, t.month
    for _ in range(n):
        out.insert(0, (y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def mk_doc(client, kind, party, d, hsn, taxable, inv_no, rs, **kw):
    rate, _ = rs.rate(hsn, d)
    s_state = client.gstin[:2] if kind == "sale" else (party.gstin or client.gstin)[:2]
    pos = (party.gstin[:2] if party.gstin else client.gstin[:2]) if kind == "sale" else client.gstin[:2]
    exp = expected_tax(taxable, rate, s_state == pos)
    e = rs.rate_entry(hsn, d)
    doc = Document(client_id=client.id, kind=kind, channel=kw.pop("channel", "seed"), method=kw.pop("method", "seed"),
                   status="booked", confidence=1.0, inv_no=inv_no, inv_date=d, party_name=party.name,
                   party_gstin=party.gstin, pos=pos, hsn=hsn, description=e["description"], qty=kw.pop("qty", 0),
                   taxable=money(taxable), rate=rate, cgst=exp["cgst"], sgst=exp["sgst"], igst=exp["igst"],
                   total=money(taxable + sum(exp.values())), field_conf={}, issues=[], **kw)
    engine.apply_rules(doc, client, rs)
    return doc


def filing(doc, supplier_name, filed_on, **override):
    f = {"supplier_gstin": doc.party_gstin, "supplier_name": supplier_name, "recipient_gstin": None,
         "inv_no": doc.inv_no, "inv_date": doc.inv_date.isoformat(), "taxable": doc.taxable,
         "cgst": doc.cgst, "sgst": doc.sgst, "igst": doc.igst, "rate": doc.rate, "filed_on": filed_on.isoformat()}
    f.update(override)
    return f


def next_month_day(d: date, day: int) -> date:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, day)


def run():
    reset_db()
    rules.reset_to("2026.10.01")
    reader.ensure_irp_keys()
    rs = rules.active()
    s = SessionLocal()
    filings = []
    today = clock.today()
    audit.log(s, "system", "seed:start", {"today": today})

    # ------------------------------------------------------------ Ramesh Traders (hero client)
    rt = Client(name="Ramesh Traders", gstin=make_gstin("29", "AAKFR4821M"), city="Bengaluru", scheme="QRMP",
                aato_cr=1.2, bank_verified=True, owner_phone="+91 98450 00000", language="kn")
    s.add(rt)
    s.flush()

    def party(name, state, hist, role="supplier", phone="", gst=True):
        p = Party(client_id=rt.id, name=name, gstin=make_gstin(state, pan()) if gst else None, phone=phone,
                  role=role, filing_history=hist)
        s.add(p)
        s.flush()
        return p

    sai = party("Sai Cables", "29", [3, None, 8, 12, None, 5], phone="+919800000001")
    mehta = party("Mehta Traders", "27", [0, 4, 0, 9, None, 2], phone="+919800000002")
    shree = party("Shree Metals", "29", [0, 0, 0, 0, 0, 0], phone="+919800000003")
    bharath = party("Bharath Cement Agencies", "29", [0, 0, 1, 0, 0, 0], phone="+919800000004")
    vinayaka = party("Vinayaka Pipes", "33", [0, 0, 0, 2, 0, 0], phone="+919800000005")
    kaveri = party("Kaveri Tiles", "29", [0, 0, 0, 0, 0, 0], phone="+919800000006")
    hotel = party("Annapoorna Hotel", "29", [0, 0, 0, 0, 0, 0])
    lorry = party("Manju Lorry Service", "29", [], gst=False, phone="+919800000007")
    ganesh = party("Sri Ganesh Constructions", "29", [], role="customer")
    mysore = party("Mysore Builders", "29", [], role="customer")
    hosur = party("Hosur Infra Projects", "33", [], role="customer")
    lakshmi = party("Lakshmi Hardware", "29", [], role="customer")
    walkin = party("Walk-in customer", "29", [], role="customer", gst=False)

    sale_no = [100]

    def sale(d, cust, hsn, taxable, **kw):
        sale_no[0] += 1
        doc = mk_doc(rt, "sale", cust, d, hsn, taxable, f"RT/26-27/{sale_no[0]:04d}", rs, **kw)
        s.add(doc)
        return doc

    def purchase(d, sup, hsn, taxable, inv_no, filed_on=None, paid_days=20, **kw):
        doc = mk_doc(rt, "purchase", sup, d, hsn, taxable, inv_no, rs, **kw)
        doc.paid_on = d + timedelta(days=paid_days) if paid_days is not None and d + timedelta(days=paid_days) <= today else None
        s.add(doc)
        if sup.gstin and filed_on:
            filings.append(filing(doc, sup.name, filed_on, recipient_gstin=rt.gstin))
        return doc

    # earlier months: Jun..Sep, all filed on time
    for (y, m) in months_back(6)[:-2]:
        base = date(y, m, 1)
        on_time = next_month_day(base, 10)
        for i in range(11):
            d = base + timedelta(days=R.randint(0, 27))
            cust = R.choice([ganesh, mysore, lakshmi, walkin, ganesh])
            hsn = R.choice(["2523", "7214", "8544", "3917", "3208", "6907"])
            sale(d, cust, hsn, R.choice([42000, 58000, 76000, 95000, 120000, 136000, 188000]))
        for i, (sup, hsn) in enumerate([(shree, "7214"), (bharath, "2523"), (vinayaka, "3917"), (kaveri, "6907"),
                                        (sai, "8544"), (mehta, "3208")]):
            d = base + timedelta(days=R.randint(0, 27))
            purchase(d, sup, hsn, R.choice([60000, 85000, 110000, 140000]),
                     f"{sup.name[:2].upper()}-{R.randint(1000, 1999)}", filed_on=on_time)
    # Rule 37 cases: old unpaid bills
    purchase(date(2026, 4, 20), bharath, "2523", 50000, "BCA-311", filed_on=date(2026, 5, 10), paid_days=None)
    purchase(date(2026, 6, 4), sai, "8544", 61000, "SC-1042", filed_on=date(2026, 7, 9), paid_days=None)

    # October (filing period) with the deliberate gaps
    oct_ = date(2026, 10, 1)
    for d, cust, hsn, tv in [(3, ganesh, "2523", 145000), (6, mysore, "7214", 210000), (9, lakshmi, "8544", 68000),
                             (12, walkin, "3208", 32000), (15, ganesh, "3917", 96000), (18, mysore, "6907", 124000),
                             (21, lakshmi, "2523", 88000), (24, ganesh, "7214", 175000), (27, walkin, "2523", 26000)]:
        sale(oct_.replace(day=d), cust, hsn, tv)
    big = sale(date(2026, 10, 29), hosur, "8544", 180000, distance_km=380)   # the large inter-state order
    purchase(date(2026, 10, 4), shree, "7214", 160000, "SM-5402", filed_on=date(2026, 11, 9))
    purchase(date(2026, 10, 7), bharath, "2523", 118000, "BCA-388", filed_on=date(2026, 11, 10))
    purchase(date(2026, 10, 10), sai, "8544", 150000, "SC-1131", filed_on=None, paid_days=10)
    purchase(date(2026, 10, 22), sai, "8544", 88900, "SC-1158", filed_on=None, paid_days=None)
    m_doc = purchase(date(2026, 10, 14), mehta, "3208", 69450, "MT/2210", filed_on=None)
    filings.append(filing(m_doc, mehta.name, date(2026, 11, 8), recipient_gstin=rt.gstin, taxable=64450.0,
                          igst=money(64450 * 0.18)))
    purchase(date(2026, 10, 17), vinayaka, "3917", 72000, "VP-0917", filed_on=date(2026, 11, 13))  # late -> Nov 2B
    purchase(date(2026, 10, 19), kaveri, "6907", 98000, "KT-871", filed_on=date(2026, 11, 7))
    purchase(date(2026, 10, 25), hotel, "9963", 6400, "AH-2231", filed_on=date(2026, 11, 5))       # blocked credit
    purchase(date(2026, 10, 29), lorry, "9965", 18000, "ML-77", paid_days=0)                  # GTA under RCM
    # supplier reported an invoice that is not in our books
    filings.append({"supplier_gstin": kaveri.gstin, "supplier_name": kaveri.name, "recipient_gstin": rt.gstin,
                    "inv_no": "KT-889", "inv_date": "2026-10-28", "taxable": 22000.0, "cgst": 1980.0, "sgst": 1980.0,
                    "igst": 0.0, "rate": 18, "filed_on": "2026-11-07"})

    # November so far (current month; suppliers have not filed yet)
    for d, cust, hsn, tv in [(3, ganesh, "2523", 98000), (5, mysore, "6907", 86000), (8, lakshmi, "7214", 132000),
                             (12, ganesh, "6907", 54000), (14, walkin, "3208", 21000)]:
        if date(2026, 11, d) <= today:
            sale(date(2026, 11, d), cust, hsn, tv)
    if today >= date(2026, 11, 3):
        purchase(date(2026, 11, 3), kaveri, "6907", 75000, "KT-902", filed_on=None)
    if today >= date(2026, 11, 6):
        purchase(date(2026, 11, 6), sai, "8544", 54000, "SC-1190", filed_on=None, paid_days=None)
    s.flush()

    # E-way bills: one in transit near expiry, one waiting on a valid vehicle number
    order231 = None
    if today >= date(2026, 11, 15):
        order231 = mk_doc(rt, "sale", hosur, date(2026, 11, 15), "3917", 67797, "RT/26-27/0231", rs, distance_km=150)
        s.add(order231)
        s.flush()
        s.add(EwayBill(client_id=rt.id, document_id=order231.id, status="draft", vehicle_no="KA5AB123",
                       distance_km=150, transporter_phone=lorry.phone))
    now = clock.now()
    s.add(EwayBill(client_id=rt.id, document_id=big.id, status="generated", vehicle_no="KA01AB4521", distance_km=380,
                   ewb_no="291004417785", generated_at=now - timedelta(hours=30), valid_until=now + timedelta(hours=6),
                   km_remaining=240, transporter_phone=lorry.phone, approved_by="Ramesh (owner)"))

    # Two bills the agent was not sure about (the review queue)
    for sup, inv, tv, conf, q in [
            (kaveri, "KT-907", 6400, 0.62, "Is the taxable value ₹8,400 or ₹6,400?"),
            (mehta, "MT/2291", 41000, 0.71, "Invoice date is smudged: 12 Nov or 17 Nov?")]:
        rv = mk_doc(rt, "purchase", sup, date(2026, 11, 12), "6907" if sup is kaveri else "3208", tv, inv, rs,
                    channel="whatsapp_photo", method="llm")
        rv.status, rv.confidence, rv.question = "review", conf, q
        rv.field_conf = {"taxable": {"conf": conf, "method": "llm"}, "inv_no": {"conf": 0.93, "method": "llm"}}
        s.add(rv)

    # Filed history (Aug, Sep)
    for p in ("082026", "092026"):
        s.add(ReturnDraft(client_id=rt.id, period=p, form="PMT-06" if p == "082026" else "GSTR-3B", status="filed",
                          arn=f"AA29{p[:2]}26{R.randint(1000000, 9999999)}", maker="Ramesh (owner)", checker="CA Kavya",
                          filed_at=datetime(int(p[2:]), int(p[:2]) % 12 + 1, 20)))

    # A short WhatsApp history
    for direction, text in [("in", "Namaskara. October bills sent."), ("out", "11 bills booked for October. 2 need your eyes in the app.")]:
        s.add(Message(client_id=rt.id, direction=direction, text=text, at=datetime.combine(date(2026, 11, 2), datetime.min.time())))

    # ------------------------------------------------------------ other clients (for the accountant console)
    def other(name, state, city, scheme, aato, lang, bank=True, n_s=10, n_p=8, n_review=3, sector=("7214", "8544")):
        c = Client(name=name, gstin=make_gstin(state, pan()), city=city, scheme=scheme, aato_cr=aato, bank_verified=bank, language=lang)
        s.add(c)
        s.flush()
        sups = [Party(client_id=c.id, name=n, gstin=make_gstin(st, pan()), role="supplier", filing_history=h)
                for n, st, h in [("Jindal Steel Depot", state, [0] * 6), ("Om Electricals", state, [0, None, 4, 0, 7, 0]),
                                 ("Balaji Hardware", "27", [0, 0, 0, 0, 0, 1])]]
        custs = [Party(client_id=c.id, name=n, gstin=make_gstin(state, pan()), role="customer") for n in ("Prestige Infra", "Nandi Builders")]
        s.add_all(sups + custs)
        s.flush()
        k = 0
        for (y, m) in months_back(4):
            base = date(y, m, 1)
            for i in range(n_s):
                d = base + timedelta(days=R.randint(0, 27))
                if d > today:
                    continue
                k += 1
                s.add(mk_doc(c, "sale", R.choice(custs), d, R.choice(sector), R.choice([38000, 64000, 91000, 150000]), f"{name[:2].upper()}/{k:04d}", rs))
            for i in range(n_p):
                d = base + timedelta(days=R.randint(0, 27))
                if d > today:
                    continue
                sp = R.choice(sups)
                doc = mk_doc(c, "purchase", sp, d, R.choice(sector), R.choice([30000, 52000, 77000]), f"{sp.name[:2].upper()}-{R.randint(100, 999)}", rs)
                doc.paid_on = d + timedelta(days=15) if d + timedelta(days=15) <= today else None
                s.add(doc)
                if sp.filing_history[-1] is not None or R.random() < 0.6:
                    filings.append(filing(doc, sp.name, next_month_day(d.replace(day=1), 10), recipient_gstin=c.gstin))
        for i in range(n_review):
            sp = R.choice(sups)
            s.add(Document(client_id=c.id, kind="purchase", channel="whatsapp_photo", method="llm", status="review",
                           confidence=round(R.uniform(0.55, 0.8), 2), inv_no=f"{sp.name[:2].upper()}-{R.randint(100, 999)}",
                           inv_date=today - timedelta(days=R.randint(1, 12)), party_name=sp.name, party_gstin=sp.gstin,
                           hsn=sector[0], taxable=R.choice([18000, 26500, 41000]), rate=18, field_conf={"taxable": {"conf": 0.62, "method": "llm"}},
                           issues=[], question=R.choice(["Is the taxable value ₹8,400 or ₹6,400?", "Invoice date is smudged: 12 or 17 Nov?",
                                                         "Supplier GSTIN check digit failed; please confirm the GSTIN."]),
                           rule_version=rs.version))
        return c

    other("Gupta Fabrication", "29", "Mysuru", "MONTHLY", 2.4, "hi", n_review=4)
    other("Sharma Transport", "29", "Hubballi", "MONTHLY", 0.9, "hi", bank=False, n_s=6, n_p=6, n_review=9, sector=("9965", "9954"))
    other("Patel Plastics", "24", "Ahmedabad", "MONTHLY", 3.1, "en", n_review=0, sector=("3923", "3917"))

    portal.reset(filings)
    audit.log(s, "system", "seed:done", {"filings": len(filings)})
    s.commit()
    make_samples(rt, shree, kaveri)
    s.close()
    print(f"Seeded. Today={today}. Filing period={clock.filing_period()}. Portal filings={len(filings)}")


# ---------------------------------------------------------------- sample bills for the WhatsApp demo

def _font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_bill(path, seller, seller_gstin, buyer, buyer_gstin, inv_no, inv_date, hsn, desc, qty, taxable, rate, qr_token=None, blur=False):
    W, H = 1000, 1300
    img = Image.new("RGB", (W, H), (252, 250, 244))
    d = ImageDraw.Draw(img)
    f_big, f, f_s = _font(40), _font(26), _font(22)
    d.text((60, 50), seller, fill=(20, 20, 20), font=f_big)
    d.text((60, 105), f"GSTIN: {seller_gstin}", fill=(40, 40, 40), font=f)
    d.text((60, 140), "TAX INVOICE", fill=(40, 40, 40), font=f)
    d.line((60, 190, W - 60, 190), fill=(60, 60, 60), width=2)
    d.text((60, 210), f"Invoice No: {inv_no}", font=f, fill=(20, 20, 20))
    d.text((60, 250), f"Date: {inv_date:%d/%m/%Y}", font=f, fill=(20, 20, 20))
    d.text((60, 310), f"Bill to: {buyer}", font=f, fill=(20, 20, 20))
    d.text((60, 350), f"GSTIN: {buyer_gstin}", font=f, fill=(20, 20, 20))
    y = 430
    d.rectangle((60, y, W - 60, y + 50), outline=(60, 60, 60), width=2)
    for x, t in ((75, "Description"), (430, "HSN"), (560, "Qty"), (700, "Taxable (Rs)")):
        d.text((x, y + 12), t, font=f_s, fill=(20, 20, 20))
    y += 60
    d.text((75, y), desc, font=f_s, fill=(20, 20, 20))
    d.text((430, y), hsn, font=f_s, fill=(20, 20, 20))
    d.text((560, y), str(qty), font=f_s, fill=(20, 20, 20))
    d.text((700, y), f"{taxable:,.2f}", font=f_s, fill=(20, 20, 20))
    tax = expected_tax(taxable, rate, seller_gstin[:2] == buyer_gstin[:2])
    y += 120
    rows = [("Taxable value", taxable)]
    if tax["igst"]:
        rows.append((f"IGST @ {rate}%", tax["igst"]))
    else:
        rows += [(f"CGST @ {rate / 2:g}%", tax["cgst"]), (f"SGST @ {rate / 2:g}%", tax["sgst"])]
    total = taxable + sum(tax.values())
    rows.append(("Total", total))
    for label, v in rows:
        d.text((520, y), label, font=f, fill=(20, 20, 20))
        d.text((780, y), f"{v:,.2f}", font=f, fill=(20, 20, 20))
        y += 45
    if qr_token:
        import qrcode
        q = qrcode.make(qr_token, box_size=3, border=2).convert("RGB").resize((330, 330))
        img.paste(q, (60, H - 420))
        d.text((60, H - 80), "Signed e-invoice QR", font=f_s, fill=(60, 60, 60))
    d.text((W - 360, H - 80), "Authorised signatory", font=f_s, fill=(60, 60, 60))
    if blur:
        from PIL import ImageFilter
        img = img.rotate(2, fillcolor=(240, 238, 230)).filter(ImageFilter.GaussianBlur(1.4))
    img.save(path)
    return total


def make_samples(rt, shree, kaveri):
    SAMPLES.mkdir(exist_ok=True)
    t = clock.today()
    taxable = 50000.0
    total = taxable * 1.18
    token = reader.sign_einvoice({"SellerGstin": shree.gstin, "SellerName": shree.name, "BuyerGstin": rt.gstin,
                                  "DocNo": "SM-5521", "DocTyp": "INV", "DocDt": f"{t:%d/%m/%Y}", "TotInvVal": round(total, 2),
                                  "ItemCnt": 1, "MainHsnCode": "7214", "Irn": "9f1c" + "0" * 56 + "a1b2", "IrnDt": f"{t:%Y-%m-%d} 10:12:00"})
    draw_bill(SAMPLES / "1_einvoice_shree_metals.png", shree.name, shree.gstin, rt.name, rt.gstin, "SM-5521", t, "7214",
              "TMT bars 12mm", "1000 kg", taxable, 18, qr_token=token)
    draw_bill(SAMPLES / "2_photo_kaveri_tiles.png", kaveri.name, kaveri.gstin, rt.name, rt.gstin, "KT-915", t - timedelta(days=1),
              "6907", "Floor tiles 600x600", "120 box", 36400.0, 18, blur=True)
    (SAMPLES / "messages.txt").write_text(
        "VOICE / TEXT\nsold 20 bags cement to Lakshmi Hardware ₹62,000\n"
        "sold 60 pipes to Hosur Infra Projects ₹75,000 incl gst 320 km\n\n"
        "TRANSPORTER REPLY\nKA01AB4521\n\n"
        "UPI SMS\nRs.71,980.00 debited from A/c XX4821 to SAI CABLES on 16-11-26 UPI Ref 6231908812\n\n"
        "QUESTIONS\nhow much GST do I pay this month?\nwhich suppliers have not filed?\n", encoding="utf-8")
    (SAMPLES / "notice_asmt10.txt").write_text(
        "FORM GST ASMT-10 [See rule 99(1)]\nReference No: ZA290926118822K   Date: 04-11-2026\n"
        f"To: {rt.name}, GSTIN {rt.gstin}\nTax period: July 2026 to September 2026\n"
        "Notice for intimating discrepancies in the return after scrutiny.\n"
        "Input tax credit availed in GSTR-3B exceeds the credit available in GSTR-2B by Rs 38,400.\n"
        "You are hereby directed to explain the reasons for the aforesaid discrepancies within thirty days, "
        "failing which proceedings in accordance with law may be initiated against you.\nProper Officer, Bengaluru (South) Range", encoding="utf-8")


if __name__ == "__main__":
    run()
