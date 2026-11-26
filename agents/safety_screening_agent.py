from __future__ import annotations

import re
from typing import Any


EMERGENCY_PATTERNS = {
    "possible cardiac symptoms": (
        r"\bchest pain\b",
        r"\bpressure in (?:my )?chest\b",
        r"\bcrushing (?:pain in (?:my )?)?chest\b",
        r"\bchest tightness\b",
        r"\bpain in (?:my )?chest\b",
        r"\bchest discomfort\b",
    ),
    "possible breathing emergency": (
        r"\bcan(?:not|'t) breathe\b",
        r"\bunable to breathe\b",
        r"\bsevere shortness of breath\b",
        r"\bshort of breath\b",
        r"\bstruggling to breathe\b",
        r"\bdifficulty breathing\b",
        r"\bbreathing difficulty\b",
        r"\btrouble breathing\b",
        r"\bgasping(?: for air)?\b",
        r"\bnot getting enough air\b",
    ),
    "possible stroke symptoms": (
        r"\bface droop(?:ing)?\b",
        r"\bface is drooping\b",
        r"\bfacial droop(?:ing)?\b",
        r"\bfacial muscles drooping\b",
        r"\bone side.{0,40}\bweak(?:ness)?\b",
        r"\bsudden.{0,40}\b(?:weakness|numbness)\b",
        r"\bslurred speech\b",
        r"\bspeech is slurred\b",
        r"\bwords are slurred\b",
        r"\bsudden trouble speaking\b",
        r"\bsudden difficulty speaking\b",
        r"\bcannot speak properly\b",
        r"\bunable to speak properly\b",
    ),
    "loss of consciousness or seizure": (
        r"\bunconscious\b",
        r"\bpassed out\b",
        r"\blost consciousness\b",
        r"\bblacked out\b",
        r"\bhaving a seizure\b",
        r"\bseizure right now\b",
        r"\bcurrently having a seizure\b",
        r"\bnot waking(?: up)?\b",
        r"\bunresponsive\b",
    ),
    "severe bleeding or injury": (
        r"\b(?:the )?bleeding (?:will not|won't|does not|doesn't) stop\b",
        r"\b(?:the )?bleeding is not stopping\b",
        r"\bbleeding that will not stop\b",
        r"\bwon't stop bleeding\b",
        r"\bwill not stop bleeding\b",
        r"\bsevere bleeding\b",
        r"\bheavy bleeding\b",
        r"\buncontrolled bleeding\b",
        r"\bmajor accident\b",
        r"\bsevere head injury\b",
        r"\bserious head injury\b",
    ),
    "possible severe allergic reaction": (
        r"\bthroat is closing\b",
        r"\bthroat closing\b",
        r"\btongue swelling\b",
        r"\btongue is swelling\b",
        r"\bswollen tongue\b",
        r"\banaphylaxis\b",
        r"\bsevere allergic reaction\b",
        r"\b(?:face|lips|tongue) swelling\b.*\bbreath(?:ing)?\b",
    ),
    "possible self-harm crisis": (
        r"\bgoing to kill myself\b",
        r"\bwant to kill myself\b",
        r"\babout to hurt myself\b",
        r"\bgoing to hurt myself\b",
        r"\bplan to hurt myself\b",
        r"\bsuicide attempt\b",
        r"\b(?:have )?overdosed\b",
        r"\btook an overdose\b",
    ),
}

# Split at sentence boundaries and contrast terms. Do NOT split at "and" or
# "or": a negation such as "no chest pain or breathing difficulty" applies
# to both coordinated symptoms.
CLAUSE_SPLITTER = re.compile(
    r"(?:[.!?;]+|\b(?:but|however|although|whereas)\b)",
    re.IGNORECASE,
)

NEGATION_BEFORE = re.compile(
    r"\b(?:no|not|never|deny|denies|denied|without|"
    r"don't|do not|doesn't|does not|"
    r"didn't|did not|"
    r"haven't|have not|hasn't|has not|"
    r"isn't|is not|aren't|are not|"
    r"wasn't|was not|weren't|were not)\b"
    r"(?:\s+\w+){0,8}\s*$",
    re.IGNORECASE,
)

NEGATION_AFTER = re.compile(
    r"^\s*(?:is|are|was|were|has been)?\s*"
    r"(?:not present|absent|denied|ruled out)\b",
    re.IGNORECASE,
)

HISTORICAL_MARKERS = re.compile(
    r"\b(?:yesterday|last night|last week|last month|previously|"
    r"earlier|in the past|history of|used to|had|experienced|suffered)\b",
    re.IGNORECASE,
)
CURRENT_MARKERS = re.compile(
    r"\b(?:now|currently|today|at present|anymore)\b",
    re.IGNORECASE,
)


class SafetyScreeningAgent:
    """
    Deterministic screening for configured emergency warning phrases.

    A negative result means only that no configured trigger was detected.
    It does not establish that the patient is safe.

    Safety screening uses the patient's raw message as its source of truth.
    The patient_intake argument is intentionally not treated as independent
    evidence because it is an LLM-generated extraction and may be inaccurate.
    """

    @staticmethod
    def _is_negated(clause: str, start: int, end: int) -> bool:
        preceding_text = clause[:start]
        following_text = clause[end:]
        return bool(
            NEGATION_BEFORE.search(preceding_text)
            or NEGATION_AFTER.search(following_text)
        )

    @staticmethod
    def _get_clauses(text: str) -> list[str]:
        return [
            clause.strip()
            for clause in CLAUSE_SPLITTER.split(text)
            if clause.strip()
        ]

    @staticmethod
    def _is_historical(clause: str) -> bool:
        return bool(HISTORICAL_MARKERS.search(clause))

    @staticmethod
    def _has_current_denial(
        clauses: list[str],
        category_patterns: tuple[str, ...],
        start_index: int,
    ) -> bool:
        for clause in clauses[start_index:]:
            if not CURRENT_MARKERS.search(clause):
                continue
            for pattern in category_patterns:
                for match in re.finditer(pattern, clause):
                    if SafetyScreeningAgent._is_negated(
                        clause, match.start(), match.end()
                    ):
                        return True
        return False

    def run(
        self,
        patient_message: str,
        patient_intake: dict | None = None,
    ) -> dict[str, Any]:
        text = re.sub(r"\s+", " ", (patient_message or "").lower()).strip()
        clauses = self._get_clauses(text)

        matches: list[str] = []
        historical_categories: list[str] = []

        for category, patterns in EMERGENCY_PATTERNS.items():
            detected = False

            for index, clause in enumerate(clauses):
                for pattern in patterns:
                    for match in re.finditer(pattern, clause):
                        if self._is_negated(clause, match.start(), match.end()):
                            continue

                        # A past symptom followed by an explicit current denial
                        # is recorded as historical, not as a current trigger.
                        if (
                            self._is_historical(clause)
                            and self._has_current_denial(
                                clauses, patterns, index + 1
                            )
                        ):
                            if category not in historical_categories:
                                historical_categories.append(category)
                            continue

                        detected = True
                        break
                    if detected:
                        break
                if detected:
                    break

            if detected:
                matches.append(category)

        limitations = [
            "Automated phrase screening is not clinically validated.",
            "This system cannot diagnose or rule out an emergency.",
            "A missed phrase does not mean the situation is safe.",
            "Structured AI-extracted intake is not used as independent emergency evidence.",
        ]

        if matches:
            return {
                "status": "emergency_trigger_detected",
                "emergency_detected": True,
                "requires_immediate_action": True,
                "matched_categories": matches,
                "historical_warning_categories": historical_categories,
                "requires_clinical_review": bool(historical_categories),
                "message": (
                    "Your message includes a possible emergency warning sign. "
                    "Please seek emergency medical help now. In India, call 112 "
                    "or go to the nearest emergency department. Do not wait "
                    "for CareAI to continue."
                ),
                "limitations": limitations,
            }

        return {
            "status": "no_trigger_detected",
            "emergency_detected": False,
            "requires_immediate_action": False,
            "matched_categories": [],
            "historical_warning_categories": historical_categories,
            "requires_clinical_review": bool(historical_categories),
            "message": "",
            "limitations": [
                "No configured emergency phrase was detected.",
                "This does not establish that the situation is safe.",
                "Seek urgent professional care if symptoms are severe, sudden, worsening, or concerning.",
                "Historical warning symptoms may still require professional review.",
            ],
        }
