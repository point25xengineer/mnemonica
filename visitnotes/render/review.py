"""U3/U4/U5 — the clinician's screen, as data.

D9 gives this screen sixty seconds, and that budget is what decides every
question here. Only blocking items demand attention. Everything that verified
collapses. The eye should land on the two things that need a decision, not
scan twenty things that don't.

Two rules that look like details and are not:

* **The discarded count is not optional.** D16 category 1 drops fabrications
  silently, which is right about the item and wrong about the number. On a
  page where everything verified is collapsed, a silently deleted medication
  looks exactly like one the model never found. The clinician never sees the
  fabricated text; they do see that something was thrown away.
* **Category 8 renders expanded.** A sig taken from a different turn than its
  drug is the one failure span verification structurally cannot catch — both
  quotes are genuine — so it does not get to hide among the things that
  actually verified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from visitnotes.contracts import Session
from visitnotes.render import actioncard
from visitnotes.render.audio import AudioCue, cue_for
from visitnotes.render.model import (
    Extraction,
    Flag,
    Item,
    Quote,
    Resolution,
    item_is_resolved,
)

__all__ = ["ReviewRow", "ReviewFlag", "Evidence", "build_review", "header_line"]


@dataclass
class Evidence:
    text: str
    turn_id: int
    turn_role: str
    audio_start: float
    min_word_probability: float
    cue: AudioCue | None
    verified: bool


@dataclass
class ReviewFlag:
    index: int
    d16_category: int | None
    blocking: bool
    reason: str
    render: str
    evidence: list[Evidence]
    options: list[str]
    chosen: str | None
    display: str | None
    heard_text: str | None
    near_matches: list[str]
    merge_target: str | None
    """An item this one is probably a duplicate of.

    The fixture's category-4 flag says `merge_into:med-lisinopril` — the
    patient's *"the other blood pressure pill"* is the lisinopril already on
    the list. Parsing that and never offering it is how a flag becomes
    decoration: the clinician reads the suggestion and still has to work out
    what to do with it.
    """


@dataclass
class ReviewRow:
    item: Item
    title: str
    kind: str
    expanded: bool
    blocking: bool
    resolved: bool
    dropped: bool
    sentences: list[actioncard.Sentence]
    needs_promotion: bool
    promoted: bool
    cue: AudioCue | None
    quote_text: str | None
    flags: list[ReviewFlag] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.item.id

    @property
    def category_labels(self) -> list[str]:
        return [f"D16.{c}" for c in self.item.d16_categories]


def _evidence(session: Session, quote: Quote, *, flagged: bool) -> Evidence:
    return Evidence(
        text=quote.text,
        turn_id=quote.turn_id,
        turn_role=quote.turn_role,
        audio_start=quote.audio_start,
        min_word_probability=quote.min_word_probability,
        cue=cue_for(session, quote, flagged=flagged),
        verified=quote.verify_against(session),
    )


def _sentences(
    item: Item, clinician_name: str, resolution: Resolution | None
) -> list[actioncard.Sentence]:
    promoted = bool(resolution and resolution.promoted)
    if item.kind == "medication":
        return actioncard.medication_sentences(
            item, clinician_name, promoted=promoted
        )
    if item.kind == "appointment":
        return [actioncard.appointment_sentence(item)]
    if item.kind == "red_flag":
        return [actioncard.red_flag_sentence(item)]
    quote = item.primary_quote
    if quote:
        return [actioncard.Sentence((actioncard.Fragment(quote.text),))]
    return []


def build_review(
    extraction: Extraction,
    session: Session,
    *,
    clinician_name: str,
    resolutions: dict[str, Resolution] | None = None,
) -> list[ReviewRow]:
    """Rows in the order the eye should travel: blocking, then expanded, then
    the collapsed remainder. `Extraction.items` already sorts that way."""
    resolutions = resolutions or {}
    rows: list[ReviewRow] = []

    for item in extraction.items:
        res = resolutions.get(item.id)
        quote = item.primary_quote
        flagged = bool(item.flags)
        sentences = _sentences(item, clinician_name, res)

        flags: list[ReviewFlag] = []
        for index, flag in enumerate(item.flags):
            flags.append(
                ReviewFlag(
                    index=index,
                    d16_category=flag.d16_category,
                    blocking=flag.blocking,
                    reason=flag.reason,
                    render=flag.render,
                    evidence=[
                        _evidence(session, q, flagged=True) for q in flag.evidence
                    ],
                    options=flag.options(),
                    chosen=res.settles(index) if res else None,
                    display=flag.display,
                    heard_text=flag.heard_text,
                    near_matches=list(flag.near_matches),
                    merge_target=(
                        flag.suggested_action.split(":", 1)[1]
                        if (flag.suggested_action or "").startswith("merge_into:")
                        else None
                    ),
                )
            )

        rows.append(
            ReviewRow(
                item=item,
                title=item.title,
                kind=item.kind,
                expanded=item.render_expanded,
                blocking=item.is_blocking,
                resolved=item_is_resolved(item, res),
                dropped=bool(res and res.dropped),
                sentences=sentences,
                needs_promotion=any(s.needs_promotion for s in sentences),
                promoted=bool(res and res.promoted),
                cue=cue_for(session, quote, flagged=flagged) if quote else None,
                quote_text=quote.text if quote else None,
                flags=flags,
            )
        )
    return rows


def header_line(extraction: Extraction) -> str:
    """*"3 confirmed · 1 needs your ear · 1 discarded"* — the honest count.

    Under-claiming is the product. The discarded number is in here because a
    number that only ever goes up is marketing, not a status line.
    """
    counts = extraction.header()
    parts = [f"{counts['confirmed']} confirmed"]
    if counts["blocking"]:
        parts.append(f"{counts['blocking']} needs your ear")
    if counts["needs_confirmation"]:
        parts.append(f"{counts['needs_confirmation']} to confirm")
    if counts["loose_threads"]:
        parts.append(f"{counts['loose_threads']} left open")
    parts.append(f"{counts['discarded']} discarded")
    return " · ".join(parts)
