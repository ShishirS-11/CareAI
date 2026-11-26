from __future__ import annotations

import re
from typing import Any

SYMPTOM_TERMS = {
    "fever": ("fever", "high temperature"),
    "swelling": ("swelling", "swollen", "effusion"),
    "vomiting": ("vomiting", "vomit", "throwing up"),
    "nausea": ("nausea", "nauseous"),
    "diarrhoea": ("diarrhoea", "diarrhea", "loose stools"),
    "constipation": ("constipation",),
    "redness": ("redness", "red"),
    "warmth": ("warmth", "warm", "hot to touch"),
    "shortness of breath": ("shortness of breath", "difficulty breathing", "breathlessness"),
    "chest pain": ("chest pain", "chest pressure"),
    "numbness": ("numbness",),
    "tingling": ("tingling",),
    "locking": ("locking", "locks", "locked"),
    "instability": ("giving way", "give way", "unstable", "instability"),
}
NEGATION = re.compile(
    r"\b(no|not|never|without|denies|denied|don't|doesn't|didn't|haven't|hasn't|has not|have not|none)\b",
    re.I,
)


def reconcile_associated_symptoms(existing: Any, transcript: str) -> tuple[list[str], list[str]]:
    """Reconcile positive/negative symptom mentions; the latest mention wins."""
    positive = [str(x).strip() for x in existing] if isinstance(existing, list) else []
    text = str(transcript or "")
    latest: dict[str, tuple[int, bool]] = {}

    for canonical, variants in SYMPTOM_TERMS.items():
        for variant in variants:
            pattern = r"(?<![a-z])" + re.escape(variant) + r"(?![a-z])"
            for match in re.finditer(pattern, text, re.I):
                start = max(text.rfind(mark, 0, match.start()) for mark in (".", "!", "?", ";", "\n")) + 1
                prefix = text[start:match.start()]
                is_negative = bool(NEGATION.search(prefix[-100:]))
                previous = latest.get(canonical)
                if previous is None or match.start() >= previous[0]:
                    latest[canonical] = (match.start(), is_negative)

    denied = [symptom for symptom, (_, is_negative) in latest.items() if is_negative]
    for symptom, (_, is_negative) in latest.items():
        if not is_negative and symptom not in positive:
            positive.append(symptom)
    denied_set = set(denied)
    positive = [item for item in positive if item.lower() not in denied_set]
    return positive, denied
