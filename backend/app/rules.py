"""Rules-as-data. Every rate, threshold and due date comes from a versioned YAML file.

Rule changes ship as new files (v<date>.yaml), never as model or code updates.
Each lookup returns the value *and* a citation: rule id + rule-set version.
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

RULES_DIR = Path(os.environ.get("KARSAATHI_RULES_DIR", Path(__file__).parent / "rulesets"))
ACTIVE_FILE = RULES_DIR / "ACTIVE"


@dataclass
class Cite:
    rule_id: str
    version: str
    source: str | None = None

    def as_dict(self):
        return {"rule_id": self.rule_id, "version": self.version, "source": self.source}

    def __str__(self):
        return f"{self.rule_id} @ rule set v{self.version}"


def _d(s):
    if s is None or isinstance(s, date):
        return s
    return date.fromisoformat(str(s))


class RuleSet:
    def __init__(self, data: dict):
        self.data = data
        self.version = data["version"]

    # ---------- generic ----------
    def section(self, name: str) -> dict:
        return self.data[name]

    def cite(self, section: str) -> Cite:
        s = self.data[section]
        return Cite(s["id"], self.version, s.get("source"))

    # ---------- HSN / rates ----------
    def rate_entry(self, hsn: str, on: date):
        hsn = (hsn or "").strip()
        best = None
        for r in self.data["hsn_rates"]:
            if not hsn.startswith(r["hsn"]):
                continue
            f, t = _d(r["effective_from"]), _d(r.get("effective_to"))
            if f and on < f:
                continue
            if t and on > t:
                continue
            if best is None or len(r["hsn"]) > len(best["hsn"]):
                best = r
        return best

    def rate(self, hsn: str, on: date):
        e = self.rate_entry(hsn, on)
        if not e:
            return None, None
        return e["rate"], Cite(e["id"], self.version, e.get("source"))

    def hsn_from_text(self, text: str):
        t = (text or "").lower()
        for r in self.data["hsn_rates"]:
            if any(k in t for k in r.get("keywords", [])):
                return r
        return None

    def known_hsn(self, hsn: str) -> bool:
        return any((hsn or "").startswith(r["hsn"]) for r in self.data["hsn_rates"])

    def blocked(self, hsn: str):
        for b in self.data.get("blocked_credit", []):
            if (hsn or "").startswith(b["hsn_prefix"]):
                return b["reason"], Cite(b["id"], self.version, b.get("source"))
        return None, None

    def is_rcm(self, hsn: str, on: date) -> bool:
        e = self.rate_entry(hsn, on)
        return bool(e and e.get("rcm"))

    def state_name(self, code: str) -> str:
        return self.data.get("states", {}).get(code, f"State {code}")


_cache: dict[str, RuleSet] = {}


def list_versions() -> list[str]:
    return sorted(p.stem[1:] for p in RULES_DIR.glob("v*.yaml"))


def load(version: str) -> RuleSet:
    if version not in _cache:
        with open(RULES_DIR / f"v{version}.yaml", encoding="utf-8") as f:
            _cache[version] = RuleSet(yaml.safe_load(f))
    return _cache[version]


def active_version() -> str:
    if ACTIVE_FILE.exists():
        v = ACTIVE_FILE.read_text().strip()
        if (RULES_DIR / f"v{v}.yaml").exists():
            return v
    return list_versions()[-1]


def active() -> RuleSet:
    return load(active_version())


def set_active(version: str):
    ACTIVE_FILE.write_text(version)


def write_version(data: dict) -> str:
    v = data["version"]
    with open(RULES_DIR / f"v{v}.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    _cache.pop(v, None)
    return v


def clone_active() -> dict:
    return copy.deepcopy(active().data)


def reset_to(version: str):
    """Demo helper: drop every version newer than `version` and activate it."""
    for v in list_versions():
        if v > version:
            (RULES_DIR / f"v{v}.yaml").unlink()
            _cache.pop(v, None)
    set_active(version)
