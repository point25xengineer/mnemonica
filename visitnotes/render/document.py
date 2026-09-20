"""U8/U9 — the patient's document. One render, two destinations.

D26's guarantee is not that the FHIR resource is byte-identical to a sheet of
paper — those are different encodings and the claim would be false. It is that
the bytes we render for print are the *same bytes* stored in
`content.attachment`. That only holds if there is exactly one function that
produces them, which is `render_patient_document` below. Do not add a second
path that "just tweaks it for the chart".

Items the clinician dropped do not appear. Items still blocking cannot get
here at all — `ui.state` refuses to approve — but the filter is written
defensively anyway, because the cost of being wrong is a patient reading a
dose nobody attested to.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from visitnotes.contracts import Session
from visitnotes.render import actioncard
from visitnotes.render.model import Extraction, Item, Resolution, item_is_resolved
from visitnotes.render.summary import build_summary

__all__ = ["render_patient_document", "long_date"]

TEMPLATES = Path(__file__).resolve().parent / "templates"

_env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def long_date(value: date | datetime) -> str:
    """`Friday, September 18, 2026` — weekday computed, never transcribed."""
    if isinstance(value, datetime):
        value = value.date()
    return f"{value.strftime('%A, %B')} {value.day}, {value.year}"


@dataclass(frozen=True)
class _RenderedMed:
    sentences: list[actioncard.Sentence]


def _printable(
    items: list[Item], resolutions: dict[str, Resolution]
) -> list[tuple[Item, Resolution | None]]:
    out = []
    for item in items:
        res = resolutions.get(item.id)
        if res and res.dropped:
            continue
        if not item_is_resolved(item, res):
            continue
        out.append((item, res))
    return out


def render_patient_document(
    extraction: Extraction,
    session: Session,
    *,
    clinician_name: str,
    resolutions: dict[str, Resolution] | None = None,
    approved_on: date | None = None,
    unexpected_speaker: bool = False,
) -> str:
    """The whole patient-facing artifact, as one self-contained HTML string."""
    resolutions = resolutions or {}
    approved_on = approved_on or date.today()

    medications = [
        _RenderedMed(
            actioncard.medication_sentences(
                item,
                clinician_name,
                promoted=bool(res and res.promoted),
                resolution=res,
            )
        )
        for item, res in _printable(extraction.medications, resolutions)
    ]

    appointments = [
        {"sentence": actioncard.appointment_sentence(item)}
        for item, _ in _printable(extraction.appointments, resolutions)
    ]

    red_flags = [
        {"text": item.primary_quote.text}
        for item, _ in _printable(extraction.red_flags, resolutions)
        if item.primary_quote and item.primary_quote.verify_against(session)
    ]

    consent = session.consent
    return _env.get_template("patient.html").render(
        visit_date_long=long_date(extraction.visit_date),
        clinician_name=clinician_name,
        medications=medications,
        appointments=appointments,
        red_flags=red_flags,
        summary=build_summary(
            extraction, session, unexpected_speaker=unexpected_speaker
        ),
        consent_method=consent.method,
        consent_date_long=long_date(consent.obtained_at),
        approved_date_long=long_date(approved_on),
    )
