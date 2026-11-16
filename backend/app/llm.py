"""Claude: reads documents and writes explanations. Never computes tax.

Enabled when ANTHROPIC_API_KEY (or an `ant auth login` profile) is available and
KARSAATHI_LLM is not "off". Every caller has a deterministic fallback.
"""
from __future__ import annotations

import base64
import json
import logging
import os

log = logging.getLogger("karsaathi.llm")
MODEL = os.environ.get("KARSAATHI_MODEL", "claude-opus-5-5")
_client = None


def available() -> bool:
    if os.environ.get("KARSAATHI_LLM", "").lower() == "off":
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_PROFILE"))


def client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client


def _call(**kw):
    """Messages call with server-side refusal fallback. The installed SDK predates the
    `fallbacks` keyword, so it travels in extra_body with its beta header."""
    import anthropic
    try:
        resp = client().beta.messages.create(
            model=MODEL, betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"}, **kw)
    except anthropic.BadRequestError as e:
        log.warning("fallback params rejected (%s); retrying plain", e)
        resp = client().messages.create(model=MODEL, **kw)
    if resp.stop_reason == "refusal":
        raise RuntimeError("Model declined this document")
    return resp


def _json_text(resp) -> dict:
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def _nullable(t):
    return {"anyOf": [{"type": t}, {"type": "null"}]}


FIELDS = ["supplier_name", "supplier_gstin", "buyer_name", "buyer_gstin", "inv_no", "inv_date", "hsn",
          "description", "qty", "taxable", "rate", "cgst", "sgst", "igst", "total"]
NUM = {"qty", "taxable", "rate", "cgst", "sgst", "igst", "total"}

INVOICE_SCHEMA = {
    "type": "object",
    "properties": {
        **{f: _nullable("number" if f in NUM else "string") for f in FIELDS},
        "confidence": {"type": "object", "properties": {f: {"type": "number"} for f in FIELDS},
                       "required": FIELDS, "additionalProperties": False},
        "unclear": {"type": "array", "items": {"type": "object", "properties": {
            "field": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}}},
            "required": ["field", "options"], "additionalProperties": False}},
    },
    "required": FIELDS + ["confidence", "unclear"],
    "additionalProperties": False,
}

READ_PROMPT = """You are reading one Indian GST tax invoice for a bookkeeping system.
Copy what is printed; do not calculate, correct or infer tax. If a field is not printed or not legible, use null.
- inv_date as YYYY-MM-DD.
- GSTINs exactly as printed (15 characters).
- taxable = taxable value before tax; cgst/sgst/igst = tax amounts printed; total = invoice total.
- If there are several line items, use the main item's HSN and description, and the invoice totals for amounts.
- confidence: 0 to 1 per field, how sure you are the value is legible and correctly copied (use 0 for null).
- unclear: for any digit you cannot read for sure, list the field and the readings it could be (e.g. ["8400", "6400"])."""


def extract_invoice(data: bytes, mime: str) -> dict:
    b64 = base64.standard_b64encode(data).decode()
    block = ({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
             if mime == "application/pdf" else
             {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}})
    resp = _call(max_tokens=4000, output_config={"effort": "medium", "format": {"type": "json_schema", "schema": INVOICE_SCHEMA}},
                 messages=[{"role": "user", "content": [block, {"type": "text", "text": READ_PROMPT}]}])
    return _json_text(resp)


NOTICE_SCHEMA = {
    "type": "object",
    "properties": {
        "form": {"type": "string"},
        "plain_summary": {"type": "string"},
        "what_is_asked": {"type": "array", "items": {"type": "string"}},
        "reply_by": _nullable("string"),
        "amount_mentioned": _nullable("number"),
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "documents_needed": {"type": "array", "items": {"type": "string"}},
        "reply_draft": {"type": "string"},
    },
    "required": ["form", "plain_summary", "what_is_asked", "reply_by", "amount_mentioned", "risk", "documents_needed", "reply_draft"],
    "additionalProperties": False,
}

LANG = {"en": "simple English", "hi": "simple Hindi (Devanagari)", "kn": "simple Kannada (Kannada script)"}


def explain_notice(text: str, lang: str, business: str) -> dict:
    prompt = f"""A small business owner ({business}) received this GST notice. Explain it for someone who does not read tax language.
Write plain_summary, what_is_asked and documents_needed in {LANG.get(lang, 'simple English')}.
reply_by as YYYY-MM-DD if a date or period is stated (else null). amount_mentioned only if the notice prints one.
reply_draft: a short, polite English reply for the accountant to edit; it must not admit liability and must leave
placeholders like [attach reconciliation] where evidence is needed. Do not invent facts that are not in the notice.

<notice>
{text}
</notice>"""
    resp = _call(max_tokens=6000, output_config={"effort": "medium", "format": {"type": "json_schema", "schema": NOTICE_SCHEMA}},
                 messages=[{"role": "user", "content": prompt}])
    return _json_text(resp)


ADVISORY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "changes": {"type": "array", "items": {"type": "object", "properties": {
            "hsn": {"type": "string"}, "new_rate": {"type": "number"}, "effective_from": {"type": "string"},
            "description": {"type": "string"}},
            "required": ["hsn", "new_rate", "effective_from", "description"], "additionalProperties": False}},
    },
    "required": ["summary", "changes"],
    "additionalProperties": False,
}


def read_advisory(text: str) -> dict:
    resp = _call(max_tokens=3000, output_config={"effort": "medium", "format": {"type": "json_schema", "schema": ADVISORY_SCHEMA}},
                 messages=[{"role": "user", "content":
                            "Extract only the GST rate changes stated in this advisory (HSN, new rate in %, effective date YYYY-MM-DD). "
                            "Do not add changes that are not written in it.\n\n<advisory>\n" + text + "\n</advisory>"}])
    return _json_text(resp)


def run_agent(question: str, tools: list[dict], call_tool, lang: str, business: str, max_turns: int = 6) -> str:
    """Manual tool loop over an allow-list of read-only tools. No filing or approval tool is ever offered."""
    system = (f"You are KarSaathi, a GST helper on WhatsApp for {business}, a small Indian business. "
              f"Reply in {LANG.get(lang, 'simple English')}, in at most 4 short sentences, like a helpful munshi. "
              "Use the tools for every number; never compute or guess tax yourself. Quote amounts exactly as the tools return them, "
              "and mention the rule-set version when you state a rate, due date or fee. "
              "You cannot file returns, accept supplier invoices or generate e-way bills; if asked, say the owner or accountant must approve that in the app.")
    messages = [{"role": "user", "content": question}]
    for _ in range(max_turns):
        resp = _call(max_tokens=8000, system=system, tools=tools, output_config={"effort": "low"}, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        uses = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason != "tool_use" or not uses:
            return "".join(b.text for b in resp.content if b.type == "text").strip()
        results = []
        for u in uses:
            try:
                out = call_tool(u.name, u.input or {})
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": json.dumps(out, default=str)})
            except Exception as e:  # noqa: BLE001
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": str(e), "is_error": True})
        messages.append({"role": "user", "content": results})
    return "Sorry, I could not finish that. Please check the dashboard."
