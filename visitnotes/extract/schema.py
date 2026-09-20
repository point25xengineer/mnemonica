"""C1 — the extraction schema. TOOLS.md §4.

**Every field is a verbatim quote, a closed enum, or a nested tool call whose
own fields are verbatim quotes. There is no free-text field anywhere.** That is
D12 expressed structurally rather than asserted, and it is the reason a
grammar-constrained model cannot author prose even if it wants to: there is
nowhere to put it.

The convention that makes the rule checkable by a test rather than by reading:
**every `str` field is named `quote` or ends in `_quote`.**
`tests/test_track_c.py::test_no_free_text_fields` walks the schema and fails on
anything else, so a future field called `note` or `rationale` cannot be added
quietly.

Two shapes, not one:

- `TurnExtraction` is what the model emits, **once per speaker turn** (D15).
  Chunking by turn is what makes attribution free and keeps a bad extraction
  from poisoning a batch.
- `VisitExtraction` is the merged whole-visit object of TOOLS §4, assembled by
  our code from the per-turn results. The gate in C2 compiles both, because
  TOOLS §4 names `VisitExtraction` and the runtime actually generates against
  `TurnExtraction`.

`summary_quotes` differs between them for a reason. A per-turn call cannot make
a whole-visit selection, so the model tags individual quotes with a heading and
the merge groups them into `SummarySelection` (D7's three fixed headings).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from visitnotes.tools.schemas import (
    AppointmentItem, LooseThreadItem, MedicationItem, RedFlagItem,
)

__all__ = [
    "SummaryHeading", "SummaryQuoteCall", "SummarySelection",
    "TurnExtraction", "VisitExtraction", "merge_turns",
]


SummaryHeading = Literal[
    "why_you_came_in", "what_the_doctor_found", "what_happens_next"
]
"""D7's three fixed headings. The summary is extractive: quotes are *selected*
and grouped under a heading, never written. A closed enum is what keeps the
grouping from becoming a place to put a sentence."""


class SummaryQuoteCall(BaseModel):
    """One quote the model nominates for the visit summary, with its heading.

    Per-turn, because that is how generation is chunked. The whole-visit
    `SummarySelection` is assembled from these by `merge_turns`."""

    heading: SummaryHeading
    quote: str = Field(min_length=1)


class SummarySelection(BaseModel):
    """D7's extractive summary — verbatim quotes under fixed headings.

    Referenced by TOOLS §4 and never defined there; `golden_extraction.json`
    pinned this shape (1c-ii) and this is it as code."""

    why_you_came_in: list[str] = Field(default_factory=list)
    what_the_doctor_found: list[str] = Field(default_factory=list)
    what_happens_next: list[str] = Field(default_factory=list)


class TurnExtraction(BaseModel):
    """What the model emits for ONE turn (D15).

    Every list defaults empty and **must be able to stay empty** — most turns
    in a real visit contain no medication, no appointment and no red flag. A
    schema that cannot express "nothing here" forces a constrained decoder to
    invent something to satisfy the grammar, which is the C2 gate's second
    half."""

    medications: list[MedicationItem] = Field(default_factory=list)
    appointments: list[AppointmentItem] = Field(default_factory=list)
    red_flags: list[RedFlagItem] = Field(default_factory=list)
    loose_threads: list[LooseThreadItem] = Field(default_factory=list)
    summary_quotes: list[SummaryQuoteCall] = Field(default_factory=list)


class VisitExtraction(BaseModel):
    """TOOLS §4's whole-visit object — the merge of every `TurnExtraction`.

    Our code builds it; the model never emits one. It is still compiled at the
    C2 gate because TOOLS §4 names it and because a schema that cannot compile
    is a schema we would rather find out about now."""

    medications: list[MedicationItem] = Field(default_factory=list)
    appointments: list[AppointmentItem] = Field(default_factory=list)
    red_flags: list[RedFlagItem] = Field(default_factory=list)
    loose_threads: list[LooseThreadItem] = Field(default_factory=list)
    summary_quotes: SummarySelection = Field(default_factory=SummarySelection)


def merge_turns(per_turn: list[TurnExtraction]) -> VisitExtraction:
    """Concatenate per-turn results into the whole-visit object.

    Deliberately dumb: no dedup, no cross-turn merging of one drug's mentions.
    Both of those are decisions about *identity*, and identity is not known
    until `resolve_medication` has run — so they happen in the verification
    pipeline, after the tools, where a merge can be justified by an RxCUI
    rather than by string equality on what the model happened to quote."""
    visit = VisitExtraction()
    summary = SummarySelection()
    for turn in per_turn:
        visit.medications.extend(turn.medications)
        visit.appointments.extend(turn.appointments)
        visit.red_flags.extend(turn.red_flags)
        visit.loose_threads.extend(turn.loose_threads)
        for sq in turn.summary_quotes:
            getattr(summary, sq.heading).append(sq.quote)
    visit.summary_quotes = summary
    return visit
