"""U7 — the extractive summary (D7, Q10a).

Selected verbatim quotes under three fixed headings. The model chose which
spans go where; it wrote none of the words. The quotes read slightly rough and
that roughness is the point — it looks like evidence rather than content, so
do not smooth it.

The attribution problem this module guards: *"Why you came in"* is filled from
non-clinician turns, and `Role` is only `clinician` / `other` / `unknown`. With
an adult child in the room, `other` is two people, and that heading can print a
daughter's words as her father's. D19's dose rule does not help — it guards
doses, not quotes. So when Track B's B6 raised its unexpected-speaker check,
patient-attributed quotes are flagged rather than printed under a heading that
claims to be the patient speaking.
"""

from __future__ import annotations

from dataclasses import dataclass

from visitnotes.contracts import Session
from visitnotes.render.model import Extraction, Quote

__all__ = ["HEADINGS", "SummaryLine", "SummarySection", "build_summary"]

HEADINGS: dict[str, str] = {
    "why_you_came_in": "Why you came in",
    "what_the_doctor_found": "What the doctor found",
    "what_happens_next": "What happens next",
}
"""Fixed. A model-chosen heading would be model-authored prose at the top of
every section."""

PATIENT_ATTRIBUTED = {"why_you_came_in"}


@dataclass(frozen=True)
class SummaryLine:
    quote: Quote
    attribution_uncertain: bool = False
    """B6 saw a third voice and this line claims to be the patient's."""

    @property
    def speaker_label(self) -> str:
        if self.quote.turn_role == "clinician":
            return "Your doctor said"
        if self.attribution_uncertain:
            return "Someone in the room said"
        return "You said"


@dataclass(frozen=True)
class SummarySection:
    key: str
    heading: str
    lines: tuple[SummaryLine, ...]


def build_summary(
    extraction: Extraction,
    session: Session,
    *,
    unexpected_speaker: bool = False,
) -> list[SummarySection]:
    """Every line traceable to a transcript span — and re-checked here.

    A quote whose offsets no longer land on its own text is dropped rather
    than printed. That is D16 category 1's rule applied one stage later: if we
    cannot prove it was said, it does not reach the patient.
    """
    sections: list[SummarySection] = []
    for key, heading in HEADINGS.items():
        lines: list[SummaryLine] = []
        for quote in extraction.summary_quotes.get(key, []):
            if not quote.verify_against(session):
                continue
            uncertain = (
                unexpected_speaker
                and key in PATIENT_ATTRIBUTED
                and quote.turn_role != "clinician"
            )
            lines.append(SummaryLine(quote=quote, attribution_uncertain=uncertain))
        sections.append(SummarySection(key=key, heading=heading, lines=tuple(lines)))
    return sections
