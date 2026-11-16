"""Rule-engine tests: dated cases with known answers. Run: pytest -q"""
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("KARSAATHI_LLM", "off")

import pytest  # noqa: E402

from app import approvals, ewaybill, rules  # noqa: E402
from app.db import ReturnDraft  # noqa: E402
from app.engine import set_off  # noqa: E402
from app.reader import parse_sms  # noqa: E402
from app.summary import inr  # noqa: E402
from app.validators import check_arithmetic, gstin_check_char, gstin_valid, make_gstin, vehicle_valid  # noqa: E402


def test_gstin_check_digit_known():
    # Published sample GSTIN with a valid check digit
    assert gstin_check_char("27AAPFU0939F1Z") == "V"
    assert gstin_valid("27AAPFU0939F1ZV")[0]
    assert not gstin_valid("27AAPFU0939F1ZX")[0]


def test_make_gstin_roundtrip():
    g = make_gstin("29", "AAKFR4821M")
    assert gstin_valid(g)[0]


def test_arithmetic_and_place_of_supply():
    assert check_arithmetic({"taxable": 1000, "cgst": 90, "sgst": 90, "igst": 0, "total": 1180}, 18, intra=True) == []
    codes = {i["code"] for i in check_arithmetic({"taxable": 1000, "cgst": 0, "sgst": 0, "igst": 180, "total": 1180}, 18, intra=True)}
    assert "POS_HEAD" in codes
    codes = {i["code"] for i in check_arithmetic({"taxable": 1000, "cgst": 60, "sgst": 60, "igst": 0, "total": 1120}, 18, intra=True)}
    assert "RATE" in codes


def test_set_off_rule_88a_order():
    # IGST credit must be used first, and CGST credit never against SGST
    r = set_off({"igst": 100, "cgst": 50, "sgst": 50}, {"igst": 120, "cgst": 0, "sgst": 40})
    assert r["utilised"]["igst->igst"] == 100
    assert r["utilised"]["igst->cgst"] == 20
    assert r["cash"] == {"igst": 0, "cgst": 30, "sgst": 10}
    r = set_off({"igst": 0, "cgst": 10, "sgst": 50}, {"igst": 0, "cgst": 60, "sgst": 0})
    assert r["cash"]["sgst"] == 50          # CGST credit cannot pay SGST
    assert r["carry_forward"]["cgst"] == 50


def test_dated_rate_lookup():
    rs = rules.load("2026.10.01")
    rate, cite = rs.rate("2523", date(2026, 10, 10))
    assert rate == 18 and cite.rule_id == "R-HSN-2523" and cite.version == "2026.10.01"
    assert rs.rate("2523", date(2025, 1, 1))[0] is None   # before effective_from
    assert rs.blocked("996331")[0]                          # food: Section 17(5)


def test_ewb_validity_midnight_rule():
    assert ewaybill.validity_days(150) == 1
    assert ewaybill.validity_days(380) == 2
    assert ewaybill.validity_days(201) == 2
    start = datetime(2026, 11, 16, 15, 0)
    assert ewaybill.valid_until(start, 1) == datetime(2026, 11, 17, 23, 59, 59)


def test_vehicle_numbers():
    pat = rules.load("2026.10.01").section("eway_bill")["vehicle_regex"]
    assert vehicle_valid("KA01AB4521", pat)
    assert vehicle_valid("ka 01 ab 4521", pat)
    assert vehicle_valid("22BH1234AB", pat)
    assert not vehicle_valid("KA5AB123", pat)


def test_maker_checker():
    r = ReturnDraft(client_id=1, period="102026", form="GSTR-3B", status="draft")
    approvals.prepare(r, {"x": 1}, "owner")
    with pytest.raises(approvals.ApprovalError):
        approvals.check(r, "owner")
    approvals.check(r, "ca")
    assert approvals.verify(r)
    r.payload = {"x": 2}                    # tampering after signing
    assert not approvals.verify(r)


def test_sms_parser():
    p = parse_sms("Rs.71,980.00 debited from A/c XX4821 to SAI CABLES on 16-11-26 UPI Ref 6231908812")
    assert p["amount"] == 71980 and p["direction"] == "out" and p["date"] == date(2026, 11, 16)


def test_inr_grouping():
    assert inr(1234567) == "₹12,34,567"
    assert inr(999) == "₹999"
