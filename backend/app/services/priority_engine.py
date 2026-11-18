"""
AutoDesk - Priority Engine
==========================

Deterministic, explainable priority assignment for IT tickets.

IMPORTANT (see SRS section 12)
-------------------------------
Priority is NOT produced by the DistilBERT category classifier. DistilBERT
predicts the *category* only. Priority is decided by this independent,
rule-based (keyword + score) engine so that the decision can be justified in a
viva and audited per ticket.

The whole rule set is declared once, at the top of this file, in
``DEFAULT_KEYWORD_TIERS`` / ``DEFAULT_THRESHOLDS`` / ``DEFAULT_MODIFIERS``.
Nothing is duplicated in other modules, and every tier can be overridden from
the environment (``PRIORITY_RULES_FILE``) without touching business logic.

Scoring model
-------------
    final_score = SUM(weight of every keyword tier matched)
                + SUM(delta of every context modifier matched)

    final_score >= 100  ->  Critical
    final_score >=  60  ->  High
    final_score >=  25  ->  Medium
    otherwise           ->  Low

Because each tier's weight equals (or exceeds) its own threshold, a single
critical phrase is enough to escalate a ticket to ``Critical``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Priorities supported by the system (must match database CHECK constraint)
# ---------------------------------------------------------------------------
PRIORITIES: Tuple[str, ...] = ("Low", "Medium", "High", "Critical")
PRIORITY_SET = frozenset(PRIORITIES)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
#: Keyword tiers. Each tier owns a numeric weight and a list of phrases.
#: Phrases are matched case-insensitively on word boundaries.
DEFAULT_KEYWORD_TIERS: Dict[str, Dict[str, Any]] = {
    # ---------------- Critical: full business stoppage -------------------
    "critical": {
        "weight": 100,
        "description": "Complete outage / total loss of a core IT service",
        "phrases": [
            "server down",
            "servers are down",
            "server is down",
            "entire system down",
            "whole system down",
            "entire network down",
            "production down",
            "production server down",
            "complete outage",
            "total outage",
            "full outage",
            "critical failure",
            "everything is down",
            "all services down",
            "company wide outage",
            "all servers offline",
            "data centre down",
            "datacenter down",
            "disaster recovery",
            "ransomware attack",
            "major security breach",
            "security breach",
            "data loss",
            "lost all my data",
            "cannot access anything",
            "nobody can login",
            "no one can login",
            "everyone is locked out",
        ],
    },
    # ---------------- High: severe impact on work -------------------
    "high": {
        "weight": 60,
        "description": "Severe impact, an urgent blocker for the requester",
        "phrases": [
            "urgent",
            "urgently",
            "asap",
            "immediately",
            "cannot work",
            "can not work",
            "can't work",
            "unable to work",
            "blocked",
            "business blocked",
            "blocking my work",
            "block my work",
            "stopped me from working",
            "major issue",
            "major problem",
            "severe issue",
            "severe problem",
            "department unavailable",
            "team unavailable",
            "not able to work",
            "work has stopped",
            "work stopped",
            "cannot complete my work",
            "cannot attend",
            "missing important meeting",
            "deadline",
            "cannot submit",
            "unable to submit",
            "payment failed",
            "cannot reach the office network",
        ],
    },
    # ---------------- Medium: a real but non-blocking fault -------------------
    "medium": {
        "weight": 30,
        "description": "Annoying fault that degrades normal working",
        "phrases": [
            "not working",
            "stopped working",
            "isn't working",
            "is not working",
            "not responding",
            "not responding",
            "does not work",
            "doesn't work",
            "will not open",
            "cannot open",
            "can't open",
            "unable to open",
            "error",
            "errors",
            "error message",
            "crash",
            "crashes",
            "crashing",
            "freezes",
            "freezing",
            "very slow",
            "too slow",
            "unable",
            "cannot",
            "can't",
            "issue",
            "problem",
            "trouble",
            "fails",
            "failed",
            "broken",
        ],
    },
    # ---------------- Low: request / question / routine install -------------------
    "low": {
        "weight": 8,
        "description": "Information request, routine request or minor nuisance",
        "phrases": [
            "request",
            "requests",
            "requesting",
            "install",
            "installation",
            "installing",
            "setup",
            "set up",
            "configure",
            "configuration",
            "information",
            "info",
            "details",
            "how do i",
            "how to",
            "where can i",
            "question",
            "query",
            "minor",
            "small issue",
            "assistance",
            "help",
            "guidance",
            "advice",
            "suggestion",
            "recommendation",
            "when will",
            "documentation",
            "guide",
            "manual",
        ],
    },
}

#: Score -> priority cut-offs, evaluated from the highest threshold downwards.
DEFAULT_THRESHOLDS: Dict[str, int] = {
    "Critical": 100,
    "High": 60,
    "Medium": 25,
}

#: Additional additive deltas applied on top of the keyword score.
#: Positive values escalate, negative values de-escalate.
DEFAULT_MODIFIERS: Dict[str, Dict[str, Any]] = {
    # ---- escalation modifiers ----
    "many_affected": {
        "delta": 25,
        "description": "Reported as affecting several people, not just the requester",
        "phrases": [
            "many users",
            "several people",
            "a few of us",
            "my colleagues",
            "my teammates",
            "other employees",
            "half the office",
            "several of us",
            "everyone in my",
            "whole team",
            "entire team",
            "the whole floor",
            "multiple users",
        ],
    },
    "hard_deadline": {
        "delta": 20,
        "description": "Explicit time pressure attached to the request",
        "phrases": [
            "before end of day",
            "end of day",
            "eod",
            "by tonight",
            "this afternoon",
            "within the hour",
            "in the next hour",
            "client meeting",
            "customer meeting",
            "presentation today",
            "exam",
            "payroll",
            "payroll deadline",
        ],
    },
    "security_sensitive": {
        "delta": 25,
        "description": "Possible security / compliance exposure",
        "phrases": [
            "suspicious email",
            "phishing",
            "stolen laptop",
            "lost laptop",
            "left my laptop",
            "account hacked",
            "someone accessed my account",
            "unauthorised access",
            "unauthorized access",
            "wrong password reset",
            "password reset by someone",
            "confidential file",
        ],
    },
    # ---- de-escalation modifiers ----
    "informational": {
        "delta": -25,
        "description": "Purely a question / how-to request with no fault",
        "phrases": [
            "just a question",
            "just wondering",
            "curious",
            "out of curiosity",
            "no urgency",
            "whenever you get a chance",
            "not urgent",
            "no rush",
            "whenever free",
            "for my records",
            "wanted to know",
            "please advise",
        ],
    },
    "workaround_present": {
        "delta": -10,
        "description": "Requester already has a usable workaround",
        "phrases": [
            "i can still work",
            "i can work around it",
            "i have a workaround",
            "it is inconvenient but",
            "not stopping my work",
            "i managed to finish",
            "it works sometimes",
        ],
    },
}

#: Keywords that suppress the default Medium floor for pure information
#: requests, e.g. "how do i install x" contains the Medium word "unable"
#: far less often, but "cannot" in "cannot find the install guide" should be Low.
DEFAULT_NEGATIVE_PATTERN = re.compile(
    r"\b(?:how (?:do|can|would) i|where (?:do|can) i|is it possible to know)\b"
)


@dataclass(frozen=True)
class PriorityRules:
    """Immutable rule-set used by the priority engine."""

    keyword_tiers: Dict[str, Dict[str, Any]] = field(
        default_factory=lambda: json.loads(json.dumps(DEFAULT_KEYWORD_TIERS))
    )
    thresholds: Dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_THRESHOLDS)
    )
    modifiers: Dict[str, Dict[str, Any]] = field(
        default_factory=lambda: json.loads(json.dumps(DEFAULT_MODIFIERS))
    )
    base_score: int = 0

    def score_to_priority(self, score: int) -> str:
        for priority in ("Critical", "High", "Medium"):
            threshold = self.thresholds.get(priority)
            if threshold is not None and score >= threshold:
                return priority
        return "Low"


# ---------------------------------------------------------------------------
# Rule loading (file / env override)
# ---------------------------------------------------------------------------
_DEFAULT_RULES: Optional[PriorityRules] = None


def _coerce_rules(raw: Dict[str, Any]) -> PriorityRules:
    """Validate an arbitrary mapping and coerce it into a ``PriorityRules``."""
    tiers: Dict[str, Dict[str, Any]] = {}
    for name, spec in (raw.get("keyword_tiers") or DEFAULT_KEYWORD_TIERS).items():
        if not isinstance(spec, dict):
            raise ValueError(f"keyword tier '{name}' must be an object")
        phrases = spec.get("phrases") or []
        if not isinstance(phrases, list):
            raise ValueError(f"keyword tier '{name}' -> 'phrases' must be a list")
        tiers[name] = {
            "weight": int(spec.get("weight", 0)),
            "description": spec.get("description", ""),
            "phrases": [str(p).lower() for p in phrases],
        }

    modifiers: Dict[str, Dict[str, Any]] = {}
    for name, spec in (raw.get("modifiers") or DEFAULT_MODIFIERS).items():
        if not isinstance(spec, dict):
            raise ValueError(f"modifier '{name}' must be an object")
        phrases = spec.get("phrases") or []
        modifiers[name] = {
            "delta": int(spec.get("delta", 0)),
            "description": spec.get("description", ""),
            "phrases": [str(p).lower() for p in phrases],
        }

    thresholds = {str(k): int(v) for k, v in (raw.get("thresholds") or DEFAULT_THRESHOLDS).items()}
    for key in thresholds:
        if key not in PRIORITY_SET:
            raise ValueError(f"threshold key '{key}' is not a valid priority")

    return PriorityRules(
        keyword_tiers=tiers,
        thresholds=thresholds,
        modifiers=modifiers,
        base_score=int(raw.get("base_score", 0)),
    )


def load_rules(path: Optional[str] = None) -> PriorityRules:
    """
    Return the active rule-set.

    A JSON file pointed at by ``PRIORITY_RULES_FILE`` (or *path*) overrides the
    built-in defaults. Invalid overrides are logged and ignored so that a typo
    can never take the helpdesk offline.
    """
    global _DEFAULT_RULES
    path = path or os.getenv("PRIORITY_RULES_FILE")
    if not path:
        if _DEFAULT_RULES is None:
            _DEFAULT_RULES = _coerce_rules({})
        return _DEFAULT_RULES

    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        rules = _coerce_rules(raw)
        logger.info("Priority rules loaded from %s", path)
        return rules
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Could not load priority rules from %s (%s); using defaults", path, exc)
        if _DEFAULT_RULES is None:
            _DEFAULT_RULES = _coerce_rules({})
        return _DEFAULT_RULES


# ---------------------------------------------------------------------------
# Text handling
# ---------------------------------------------------------------------------
_WHITESPACE = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^a-z0-9\s]+")
_MULTI_SPACE = re.compile(r"\s{2,}")


def normalize_text(*parts: Optional[str]) -> str:
    """Lower-case, strip punctuation noise and collapse whitespace."""
    joined = " ".join(p for p in parts if p)
    joined = _WHITESPACE.sub(" ", joined).strip().lower()
    joined = _NON_WORD.sub(" ", joined)
    return _MULTI_SPACE.sub(" ", joined).strip()


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    escaped = re.escape(phrase.strip())
    return re.compile(rf"(?<!\w){escaped}(?!\w)")


def _match_phrases(text: str, phrases: Iterable[str]) -> List[str]:
    hits: List[str] = []
    for phrase in phrases:
        phrase = phrase.strip().lower()
        if not phrase:
            continue
        if _phrase_pattern(phrase).search(text):
            hits.append(phrase)
    return hits


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def predict_priority(
    text: str = "",
    title: str = "",
    description: str = "",
    rules: Optional[PriorityRules] = None,
) -> Dict[str, Any]:
    """
    Assign a priority to a ticket.

    Parameters
    ----------
    text:
        Optional convenience argument - if supplied and *title*/*description*
        are empty it is treated as the description.
    title, description:
        Raw ticket text. Both are analysed, because employees often put the
        severity only in the title ("URGENT - cannot work").
    rules:
        Rule-set override. Defaults to the cached rules loaded from
        ``PRIORITY_RULES_PATH``; passing an explicit set is what lets the test
        suite exercise the engine against a known configuration.

    Returns
    -------
    dict
        ``{"priority": "High", ...}`` plus the audit trail (``score``,
        ``matched_keywords``, ``matched_modifiers``) so the UI and the viva
        can show exactly *why* a priority was chosen.

    The dict shape is deliberately a superset of the SRS contract
    ``{"priority": "High"}``.
    """
    rules = rules or load_rules()
    raw_text = " ".join(p for p in (text, title, description) if p)
    normalized = normalize_text(raw_text)

    if not normalized:
        return {
            "priority": "Low",
            "score": rules.base_score,
            "base_score": rules.base_score,
            "matched_keywords": [],
            "matched_modifiers": [],
            "explanation": "No text supplied; defaulted to Low priority.",
        }

    matched_keywords: List[str] = []
    keyword_score = 0
    for tier_name in ("critical", "high", "medium", "low"):
        tier = rules.keyword_tiers.get(tier_name)
        if not tier:
            continue
        hits = _match_phrases(normalized, tier.get("phrases", []))
        if hits:
            keyword_score += int(tier["weight"])
            matched_keywords.extend(hits)

    matched_modifiers: List[str] = []
    modifier_score = 0
    for mod_name, spec in rules.modifiers.items():
        hits = _match_phrases(normalized, spec.get("phrases", []))
        if hits:
            modifier_score += int(spec["delta"])
            matched_modifiers.extend(hits)

    score = rules.base_score + keyword_score + modifier_score

    # Pure how-to / information requests are informational even when they
    # contain words such as "cannot" or "error".
    if DEFAULT_NEGATIVE_PATTERN.search(normalized):
        score = min(score, rules.thresholds.get("Medium", 25) - 1)

    priority = rules.score_to_priority(score)

    explanation = _build_explanation(priority, score, matched_keywords, matched_modifiers)
    return {
        "priority": priority,
        "score": score,
        "base_score": rules.base_score,
        "keyword_score": keyword_score,
        "modifier_score": modifier_score,
        "matched_keywords": matched_keywords,
        "matched_modifiers": matched_modifiers,
        "explanation": explanation,
    }


def _build_explanation(
    priority: str,
    score: int,
    keywords: List[str],
    modifiers: List[str],
) -> str:
    """Human readable one-liner describing the decision."""
    if not keywords and not modifiers:
        return f"No priority keywords detected, defaulted to {priority}."

    seen: List[str] = []
    for term in keywords + modifiers:
        if term not in seen:
            seen.append(term)
    shown = ", ".join(f"'{term}'" for term in seen[:6])
    if len(seen) > 6:
        shown += f" (+{len(seen) - 6} more)"
    return f"Scored {score} from: {shown} -> {priority}."


def priority_is_valid(priority: str) -> bool:
    """Validate a priority string against the allowed database values."""
    return isinstance(priority, str) and priority in PRIORITY_SET
