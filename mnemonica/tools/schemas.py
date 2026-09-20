"""The D17 tool contracts, as code — TOOLS.md §1–3.

Two kinds of model live here and the distinction is the whole safety argument:

- **`*Call`** — what the *model* supplies. Every field is a verbatim quote or
  a closed enum. There is no free-text field, no RxCUI, no computed date, no
  speaker role. A model can only point at the transcript.
- **`*Resolution` / `SigParse`** — what the *tools* return. The model never
  sees these (§0: single-shot, no feedback loop), so nothing here can be
  rationalized against.

Anything the runtime already knows is injected rather than asked for: the
visit date (D18), the speaker role of the source turn (D19), the transcript.
The model cannot hallucinate what it was never asked to supply.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "ResolveMedicationCall", "MedicationCandidate", "MedicationResolution",
    "ParseSigCall", "SigParse",
    "ResolveDateCall", "DateResolution",
    "MedicationItem", "AppointmentItem", "RedFlagItem", "LooseThreadItem",
]


# --------------------------------------------------------------- §1 medication

class ResolveMedicationCall(BaseModel):
    """Arguments. Nothing else — no RxCUI, no normalized name, no guessed
    spelling. Those are outputs, and asking the model for them invites
    invention."""

    mention_quote: str = Field(min_length=1)
    """The drug name verbatim from the transcript, misspellings included."""
    context_quote: str | None = None
    """The surrounding clause, verbatim, if it may disambiguate."""


class MedicationCandidate(BaseModel):
    rxcui: str
    name: str
    tty: str
    score: float
    edit_distance: int


class MedicationResolution(BaseModel):
    status: Literal["resolved", "ambiguous", "unresolved"]

    rxcui: str | None = None
    canonical_name: str | None = None
    tty: str | None = None
    ingredients: list[str] = Field(default_factory=list)
    brand_names: list[str] = Field(default_factory=list)
    is_brand: bool | None = None

    salt_unspecified: bool = False
    """A5.5 — an `IN` matched and that ingredient has 2+ marketed salt
    children. Succinate is once daily, tartrate twice daily; the same spoken
    word hides two schedules."""
    salt_candidates: list[str] = Field(default_factory=list)

    match_type: Literal["exact", "case_insensitive", "fuzzy", "none"] = "none"
    edit_distance: int | None = None
    match_confidence: float = 0.0

    candidates: list[MedicationCandidate] = Field(default_factory=list)

    spl_set_ids: list[str] = Field(default_factory=list)
    """For the openFDA join. Join on THIS, never on `openfda.rxcui` — only
    ~25% of label records carry one (A8)."""

    available_strengths: list[str] = Field(default_factory=list)
    dose_forms: list[str] = Field(default_factory=list)

    source: Literal["RxNorm Current Prescribable"] = "RxNorm Current Prescribable"
    source_release: str
    """Read from the release readme at build time, never hardcoded."""


# --------------------------------------------------------------------- §2 sig

class ParseSigCall(BaseModel):
    sig_quote: str = Field(min_length=1)
    """The dosing instruction verbatim. No `drug_rxcui` (the model never saw
    one) and no `speaker_role` (the runtime knows it from diarization — if the
    model supplied it, D19's dose-safety rule would rest on the model's claim
    about who was speaking)."""


class SigParse(BaseModel):
    status: Literal["parsed", "partial", "unparseable", "not_specified"]

    dose_amount: float | None = None
    dose_unit: str | None = None
    dose_form: str | None = None
    route: str | None = None

    frequency_per_day: float | None = None
    interval_hours: float | None = None
    timing: list[str] = Field(default_factory=list)
    days_of_week: list[str] | None = None

    prn: bool = False
    prn_condition: str | None = None

    duration_days: int | None = None
    total_quantity: float | None = None
    max_daily_amount: float | None = None

    unparsed_remainder: str | None = None
    normalized_sig: str | None = None
    parse_confidence: float = 0.0

    source: Literal["deterministic grammar"] = "deterministic grammar"
    grammar_version: str


# -------------------------------------------------------------------- §3 date

class ResolveDateCall(BaseModel):
    phrase_quote: str = Field(min_length=1)
    event_kind: Literal["followup_visit", "medication_start",
                        "medication_stop", "test_scheduled",
                        "test_results", "other"]
    """The one genuinely interpretive argument in any of the three tools — a
    classification, so it cannot be span-verified. Closed, with an `other`
    escape, so the failure mode is a miscategorized date and never an invented
    one. **No anchor date argument**: the runtime injects `visit_date` (D18)."""


class DateResolution(BaseModel):
    status: Literal["resolved", "resolved_range", "unanchored",
                    "unparseable", "not_a_date"]

    resolved_date: date | None = None
    range_start: date | None = None
    range_end: date | None = None

    precision: Literal["exact_day", "week_of", "month", "vague"] | None = None
    direction: Literal["future", "past"] | None = None

    anchor_date: date
    anchor_source: Literal["session_visit_date"] = "session_visit_date"

    original_phrase: str
    display_string: str | None = None
    """Both forms, per D18 — *"three weeks from today, which is Friday,
    October 9"*. A patient reading a bare date cannot catch an error in it;
    reading both lets them."""

    depends_on_event: str | None = None

    resolution_confidence: float = 0.0
    source: Literal["deterministic date resolver"] = "deterministic date resolver"


# --------------------------------------------------------- §4 composed schema

class MedicationItem(BaseModel):
    medication: ResolveMedicationCall
    sig: list[ParseSigCall] = Field(default_factory=list)
    start_or_stop: ResolveDateCall | None = None
    change_kind: Literal["new", "increased", "decreased",
                         "stopped", "continued", "unchanged"]
    change_evidence_quote: str
    change_kind_derived: bool = False


class AppointmentItem(BaseModel):
    when: ResolveDateCall
    purpose_quote: str


class RedFlagItem(BaseModel):
    instruction_quote: str


class LooseThreadItem(BaseModel):
    topic_quote: str
