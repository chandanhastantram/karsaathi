"""Plain-language explanations. Numbers come from the engine; words come from fixed
templates, so the summary can never state a figure the engine did not compute."""
from __future__ import annotations

from datetime import date

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
    "kn": ["ಜನವರಿ", "ಫೆಬ್ರವರಿ", "ಮಾರ್ಚ್", "ಏಪ್ರಿಲ್", "ಮೇ", "ಜೂನ್", "ಜುಲೈ", "ಆಗಸ್ಟ್", "ಸೆಪ್ಟೆಂಬರ್", "ಅಕ್ಟೋಬರ್", "ನವೆಂಬರ್", "ಡಿಸೆಂಬರ್"],
}


def inr(x: float) -> str:
    """Indian digit grouping: 12,34,567."""
    neg = x < 0
    n = int(round(abs(x)))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "₹" + s


def _date(d: date, lang: str) -> str:
    return f"{d.day} {MONTHS[lang][d.month - 1]}"


T = {
    "en": {
        "core": "In {month} you collected {out} GST on sales and got {itc} of credit on purchases.",
        "held": "{held} of credit is held back because {n} supplier{s} ({names}) {have} not reported your bills yet.",
        "blocked": "{amt} is not claimable as credit (food, cabs: Section 17(5)).",
        "r37": "{amt} of credit is reversed because a supplier was not paid within 180 days.",
        "rcm": "{amt} is reverse-charge tax on transport: you pay it in cash and take it back as credit.",
        "pay": "You need to pay {cash} by {due} ({form}).",
        "nothing": "No cash payment is due for {month}; credit covers your tax.",
        "delta_up": "That is {d} more than last month, mostly from invoice {inv} to {party}{inter}.",
        "delta_down": "That is {d} less than last month.",
        "inter": " (inter-state)",
        "late": "If you pay late: {fee} per day late fee (up to {cap}) plus 18% yearly interest.",
        "late_now": "This is already {days} days late: {fee} late fee and {intr} interest so far.",
    },
    "hi": {
        "core": "{month} में आपने बिक्री पर {out} GST वसूला और खरीद पर {itc} का क्रेडिट मिला।",
        "held": "{held} का क्रेडिट रुका है, क्योंकि {n} सप्लायर ({names}) ने अभी तक आपके बिल दर्ज नहीं किए।",
        "blocked": "{amt} का क्रेडिट नहीं मिलेगा (खाना, कैब: धारा 17(5))।",
        "r37": "{amt} का क्रेडिट वापस हुआ, क्योंकि सप्लायर को 180 दिन में भुगतान नहीं हुआ।",
        "rcm": "{amt} ट्रांसपोर्ट पर रिवर्स चार्ज टैक्स है: नकद में भरें, फिर क्रेडिट वापस मिलता है।",
        "pay": "आपको {due} तक {cash} जमा करना है ({form})।",
        "nothing": "{month} के लिए कोई नकद भुगतान नहीं है; क्रेडिट से टैक्स पूरा हो गया।",
        "delta_up": "यह पिछले महीने से {d} ज़्यादा है, ज़्यादातर {party} को बिल {inv}{inter} की वजह से।",
        "delta_down": "यह पिछले महीने से {d} कम है।",
        "inter": " (दूसरे राज्य)",
        "late": "देर से भरने पर: रोज़ {fee} लेट फीस ({cap} तक) और 18% सालाना ब्याज।",
        "late_now": "यह पहले ही {days} दिन लेट है: अब तक {fee} लेट फीस और {intr} ब्याज।",
    },
    "kn": {
        "core": "{month} ನಲ್ಲಿ ನೀವು ಮಾರಾಟದ ಮೇಲೆ {out} GST ಸಂಗ್ರಹಿಸಿದ್ದೀರಿ ಮತ್ತು ಖರೀದಿಯ ಮೇಲೆ {itc} ಕ್ರೆಡಿಟ್ ಸಿಕ್ಕಿದೆ.",
        "held": "{n} ಪೂರೈಕೆದಾರರು ({names}) ಇನ್ನೂ ನಿಮ್ಮ ಬಿಲ್‌ಗಳನ್ನು ದಾಖಲಿಸದ ಕಾರಣ {held} ಕ್ರೆಡಿಟ್ ತಡೆಹಿಡಿಯಲಾಗಿದೆ.",
        "blocked": "{amt} ಕ್ರೆಡಿಟ್ ಸಿಗುವುದಿಲ್ಲ (ಊಟ, ಕ್ಯಾಬ್: ಸೆಕ್ಷನ್ 17(5)).",
        "r37": "180 ದಿನಗಳಲ್ಲಿ ಪೂರೈಕೆದಾರರಿಗೆ ಹಣ ಪಾವತಿಸದ ಕಾರಣ {amt} ಕ್ರೆಡಿಟ್ ಹಿಂತಿರುಗಿಸಲಾಗಿದೆ.",
        "rcm": "{amt} ಸಾರಿಗೆಯ ಮೇಲಿನ ರಿವರ್ಸ್ ಚಾರ್ಜ್ ತೆರಿಗೆ: ನಗದಾಗಿ ಕಟ್ಟಿ, ನಂತರ ಕ್ರೆಡಿಟ್ ಆಗಿ ಹಿಂಪಡೆಯಬಹುದು.",
        "pay": "ನೀವು {due} ಒಳಗೆ {cash} ಪಾವತಿಸಬೇಕು ({form}).",
        "nothing": "{month} ಗೆ ನಗದು ಪಾವತಿ ಇಲ್ಲ; ಕ್ರೆಡಿಟ್‌ನಿಂದ ತೆರಿಗೆ ಪೂರ್ಣಗೊಂಡಿದೆ.",
        "delta_up": "ಇದು ಕಳೆದ ತಿಂಗಳಿಗಿಂತ {d} ಹೆಚ್ಚು, ಮುಖ್ಯವಾಗಿ {party} ಗೆ ನೀಡಿದ ಬಿಲ್ {inv}{inter} ಕಾರಣ.",
        "delta_down": "ಇದು ಕಳೆದ ತಿಂಗಳಿಗಿಂತ {d} ಕಡಿಮೆ.",
        "inter": " (ಅಂತರರಾಜ್ಯ)",
        "late": "ತಡವಾಗಿ ಕಟ್ಟಿದರೆ: ದಿನಕ್ಕೆ {fee} ವಿಳಂಬ ಶುಲ್ಕ ({cap} ವರೆಗೆ) ಮತ್ತು ವಾರ್ಷಿಕ 18% ಬಡ್ಡಿ.",
        "late_now": "ಇದು ಈಗಾಗಲೇ {days} ದಿನ ತಡವಾಗಿದೆ: ಇಲ್ಲಿಯವರೆಗೆ {fee} ವಿಳಂಬ ಶುಲ್ಕ ಮತ್ತು {intr} ಬಡ್ಡಿ.",
    },
}


def explain_return(c: dict, lang: str = "en", delta: float | None = None) -> list[dict]:
    """Returns sentences, each tagged with the figure keys it uses (for click-through)."""
    lang = lang if lang in T else "en"
    t = T[lang]
    s = c["summary"]
    m = int(c["period"][:2])
    month = MONTHS[lang][m - 1]
    out = [{"text": t["core"].format(month=month, out=inr(s["output_tax"]), itc=inr(s["itc_claimed"])),
            "refs": ["table_3_1.a_outward_taxable", "table_4.C_net"]}]
    if s["itc_held"] > 0:
        n = len(s["held_suppliers"])
        out.append({"text": t["held"].format(held=inr(s["itc_held"]), n=n, s="s" if n != 1 else "",
                                             names=", ".join(s["held_suppliers"][:3]), have="have" if n != 1 else "has"),
                    "refs": ["held"]})
    if s["blocked"] > 0:
        out.append({"text": t["blocked"].format(amt=inr(s["blocked"])), "refs": ["table_4.B1_blocked_17_5"]})
    if s["rule37"] > 0:
        out.append({"text": t["r37"].format(amt=inr(s["rule37"])), "refs": ["table_4.B2_rule37"]})
    if s["rcm"] > 0:
        out.append({"text": t["rcm"].format(amt=inr(s["rcm"])), "refs": ["table_3_1.d_inward_rcm"]})
    if c["cash_payable"] > 0:
        out.append({"text": t["pay"].format(cash=inr(c["cash_payable"]), due=_date(c["due"], lang), form=c["form"]),
                    "refs": ["set_off"]})
    else:
        out.append({"text": t["nothing"].format(month=month), "refs": ["set_off"]})
    if delta is not None and abs(delta) >= 1000:
        b = s.get("biggest_sale")
        if delta > 0 and b:
            out.append({"text": t["delta_up"].format(d=inr(delta), inv=b["inv_no"], party=b["party"],
                                                     inter=t["inter"] if b["inter_state"] else ""),
                        "refs": [f"doc:{b['doc_id']}"]})
        else:
            out.append({"text": t["delta_down"].format(d=inr(abs(delta))), "refs": []})
    late = c["late"]
    if late["days_late"] > 0:
        out.append({"text": t["late_now"].format(days=late["days_late"], fee=inr(late["late_fee"]), intr=inr(late["interest"])),
                    "refs": ["late"]})
    else:
        out.append({"text": t["late"].format(fee=inr(50), cap=inr(late["cap"])), "refs": ["late"]})
    return out


NUDGE = {
    "en": ("Namaste {supplier}. Our invoice{s} {invs} from you ({amt} GST) {is_are} not in our GSTR-2B/IMS yet. "
           "Please report {it_them} in your GSTR-1 (or amend through GSTR-1A) before the 11th so we can claim the credit. "
           "Thank you, {client}."),
    "hi": ("नमस्ते {supplier}। आपके बिल {invs} ({amt} GST) अभी तक हमारे GSTR-2B/IMS में नहीं दिख रहे। "
           "कृपया 11 तारीख से पहले अपने GSTR-1 में दर्ज करें (या GSTR-1A से सुधारें), ताकि हमें क्रेडिट मिल सके। धन्यवाद, {client}।"),
    "kn": ("ನಮಸ್ಕಾರ {supplier}. ನಿಮ್ಮ ಬಿಲ್ {invs} ({amt} GST) ಇನ್ನೂ ನಮ್ಮ GSTR-2B/IMS ನಲ್ಲಿ ಕಾಣುತ್ತಿಲ್ಲ. "
           "ದಯವಿಟ್ಟು 11 ನೇ ತಾರೀಖಿನ ಒಳಗೆ ನಿಮ್ಮ GSTR-1 ನಲ್ಲಿ ದಾಖಲಿಸಿ (ಅಥವಾ GSTR-1A ಮೂಲಕ ತಿದ್ದುಪಡಿ ಮಾಡಿ), ಇದರಿಂದ ನಮಗೆ ಕ್ರೆಡಿಟ್ ಸಿಗುತ್ತದೆ. ಧನ್ಯವಾದಗಳು, {client}."),
}


def nudge_text(supplier: str, rows: list[dict], client: str, lang: str = "en") -> str:
    lang = lang if lang in NUDGE else "en"
    invs = ", ".join(f"{r['inv_no']} ({r['inv_date'].strftime('%d %b') if hasattr(r['inv_date'], 'strftime') else r['inv_date']})" for r in rows)
    amt = inr(sum(r["book_itc"] for r in rows))
    many = len(rows) > 1
    return NUDGE[lang].format(supplier=supplier, invs=invs, amt=amt, client=client, s="s" if many else "",
                              is_are="are" if many else "is", it_them="them" if many else "it")
