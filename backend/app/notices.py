"""Notice reader. Claude explains when configured; otherwise a fixed table of common GST forms."""
from __future__ import annotations

import re
from datetime import date, timedelta

from . import i18n, llm

FORMS = {
    "GSTR-3A": {"title": "Notice for not filing a return", "days": 15, "risk": "high",
                "en": "The department says a return was not filed. File it with late fee within 15 days, or they can assess your tax on their own (best judgement).",
                "hi": "विभाग कह रहा है कि एक रिटर्न नहीं भरा गया। 15 दिन में लेट फीस के साथ भरें, नहीं तो विभाग खुद टैक्स तय कर सकता है।",
                "kn": "ಒಂದು ರಿಟರ್ನ್ ಸಲ್ಲಿಸಿಲ್ಲ ಎಂದು ಇಲಾಖೆ ಹೇಳುತ್ತಿದೆ. 15 ದಿನಗಳಲ್ಲಿ ವಿಳಂಬ ಶುಲ್ಕದೊಂದಿಗೆ ಸಲ್ಲಿಸಿ, ಇಲ್ಲದಿದ್ದರೆ ಇಲಾಖೆಯೇ ತೆರಿಗೆ ನಿರ್ಧರಿಸಬಹುದು.",
                "docs": ["Pending return", "Challan for tax and late fee"]},
    "ASMT-10": {"title": "Scrutiny: differences found in your returns", "days": 30, "risk": "medium",
                "en": "An officer compared your returns and found differences (often GSTR-3B credit vs GSTR-2B). Explain each difference within 30 days, or pay the shortfall with interest.",
                "hi": "अधिकारी ने आपके रिटर्न में अंतर पाया है (अक्सर GSTR-3B क्रेडिट और GSTR-2B में)। 30 दिन में हर अंतर का कारण बताएं, या कमी ब्याज सहित भरें।",
                "kn": "ಅಧಿಕಾರಿ ನಿಮ್ಮ ರಿಟರ್ನ್‌ಗಳಲ್ಲಿ ವ್ಯತ್ಯಾಸ ಕಂಡಿದ್ದಾರೆ (ಹೆಚ್ಚಾಗಿ GSTR-3B ಕ್ರೆಡಿಟ್ ಮತ್ತು GSTR-2B ನಡುವೆ). 30 ದಿನಗಳಲ್ಲಿ ಪ್ರತಿ ವ್ಯತ್ಯಾಸಕ್ಕೆ ವಿವರಣೆ ನೀಡಿ ಅಥವಾ ಕೊರತೆಯನ್ನು ಬಡ್ಡಿಯೊಂದಿಗೆ ಪಾವತಿಸಿ.",
                "docs": ["Purchase register", "GSTR-2B for the period", "Reconciliation statement", "Supplier invoices"]},
    "DRC-01A": {"title": "Intimation before a show-cause notice", "days": 30, "risk": "medium",
                "en": "The officer has worked out tax they think you owe. You can pay now (lower penalty) or reply that you disagree, with reasons.",
                "hi": "अधिकारी ने टैक्स बकाया का हिसाब लगाया है। अभी भरें (कम पेनल्टी) या असहमति कारण सहित लिखें।",
                "kn": "ನೀವು ಬಾಕಿ ಇರುವ ತೆರಿಗೆಯನ್ನು ಅಧಿಕಾರಿ ಲೆಕ್ಕ ಹಾಕಿದ್ದಾರೆ. ಈಗಲೇ ಪಾವತಿಸಿ (ಕಡಿಮೆ ದಂಡ) ಅಥವಾ ಕಾರಣಗಳೊಂದಿಗೆ ಒಪ್ಪಿಗೆ ಇಲ್ಲ ಎಂದು ಉತ್ತರಿಸಿ.",
                "docs": ["Working of the amount", "Returns for the period", "Payment proofs"]},
    "DRC-01": {"title": "Show-cause notice (demand)", "days": 30, "risk": "high",
               "en": "A formal demand: the department asks why tax, interest and penalty should not be collected. A written reply and a hearing are needed. Involve your accountant now.",
               "hi": "औपचारिक मांग: विभाग पूछ रहा है कि टैक्स, ब्याज और पेनल्टी क्यों न वसूली जाए। लिखित जवाब और सुनवाई ज़रूरी है। अभी अपने अकाउंटेंट को शामिल करें।",
               "kn": "ಔಪಚಾರಿಕ ಬೇಡಿಕೆ: ತೆರಿಗೆ, ಬಡ್ಡಿ ಮತ್ತು ದಂಡ ಏಕೆ ವಸೂಲಿ ಮಾಡಬಾರದು ಎಂದು ಇಲಾಖೆ ಕೇಳುತ್ತಿದೆ. ಲಿಖಿತ ಉತ್ತರ ಮತ್ತು ವಿಚಾರಣೆ ಅಗತ್ಯ. ಈಗಲೇ ನಿಮ್ಮ ಲೆಕ್ಕಿಗರನ್ನು ಸೇರಿಸಿ.",
               "docs": ["All returns for the period", "Books of account", "Reconciliation", "Earlier replies"]},
    "REG-17": {"title": "Show-cause notice for cancelling registration", "days": 7, "risk": "high",
               "en": "The department may cancel your GST registration (often for not filing returns or missing bank details). Reply within 7 working days and fix the cause.",
               "hi": "विभाग आपका GST रजिस्ट्रेशन रद्द कर सकता है (अक्सर रिटर्न न भरने या बैंक विवरण न देने पर)। 7 कार्य-दिवस में जवाब दें और कारण ठीक करें।",
               "kn": "ಇಲಾಖೆ ನಿಮ್ಮ GST ನೋಂದಣಿಯನ್ನು ರದ್ದುಪಡಿಸಬಹುದು (ಹೆಚ್ಚಾಗಿ ರಿಟರ್ನ್ ಸಲ್ಲಿಸದಿರುವುದು ಅಥವಾ ಬ್ಯಾಂಕ್ ವಿವರ ನೀಡದಿರುವುದಕ್ಕೆ). 7 ಕೆಲಸದ ದಿನಗಳಲ್ಲಿ ಉತ್ತರಿಸಿ ಮತ್ತು ಕಾರಣ ಸರಿಪಡಿಸಿ.",
               "docs": ["Pending returns filed", "Bank account proof", "Business address proof"]},
    "REG-03": {"title": "Clarification needed on your registration", "days": 7, "risk": "low",
               "en": "The officer needs more information or documents for your registration or amendment. Reply in REG-04 within 7 working days.",
               "hi": "रजिस्ट्रेशन के लिए अधिकारी को और जानकारी चाहिए। 7 कार्य-दिवस में REG-04 में जवाब दें।",
               "kn": "ನೋಂದಣಿಗಾಗಿ ಅಧಿಕಾರಿಗೆ ಹೆಚ್ಚಿನ ಮಾಹಿತಿ ಬೇಕು. 7 ಕೆಲಸದ ದಿನಗಳಲ್ಲಿ REG-04 ನಲ್ಲಿ ಉತ್ತರಿಸಿ.",
               "docs": ["Documents listed in the notice"]},
}


def _find_date(text: str):
    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def explain(text: str, lang: str, business: str, today: date) -> dict:
    lang = i18n.supported(lang)
    if llm.available():
        try:
            r = llm.explain_notice(text, lang, business)
            r["engine"] = "claude"
            return r
        except Exception as e:  # noqa: BLE001
            err = str(e)
    else:
        err = None
    form = next((f for f in FORMS if re.search(f.replace("-", r"[\s-]?"), text, re.I)), None)
    amt = re.search(r"(?:Rs\.?|₹|INR)\s*([0-9][0-9,]*)", text)
    issued = _find_date(text) or today
    if not form:
        return {"engine": "rules", "form": "Unknown", "plain_summary": "I could not recognise this notice form. Your accountant should read it.",
                "what_is_asked": [], "reply_by": None, "amount_mentioned": float(amt.group(1).replace(",", "")) if amt else None,
                "risk": "medium", "documents_needed": [], "reply_draft": "", "note": err}
    f = FORMS[form]
    reply_by = issued + timedelta(days=f["days"])
    return {
        "engine": "rules", "form": form, "title": f["title"], "plain_summary": f[lang] if lang in f else f["en"],
        "what_is_asked": [f["title"]], "reply_by": reply_by.isoformat(),
        "amount_mentioned": float(amt.group(1).replace(",", "")) if amt else None, "risk": f["risk"],
        "documents_needed": f["docs"],
        "reply_draft": (f"To the Proper Officer,\n\nSub: Reply to {form} dated {issued:%d-%m-%Y} — {business}\n\n"
                        "We acknowledge receipt of the above notice. Our point-wise reply is as follows:\n"
                        "1. [explain each difference with reference to the attached reconciliation]\n"
                        "2. [attach GSTR-2B / IMS extract and supplier invoices]\n\n"
                        "We request that the proceedings be dropped. We are available for a personal hearing if required.\n\n"
                        f"For {business}\n[Authorised signatory]"),
        "note": err,
    }
