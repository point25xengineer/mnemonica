"""The shape Track D consumes — `golden_extraction.json`, parsed.

1c-ii pinned a post-C5 disposition envelope that TOOLS §4 never defined (see
PLAN.md → Deviations). This module is the one place that knows that JSON's
key names. Everything downstream — the review screen, the action cards, the
printed page — reads these dataclasses, so when C5 lands and the envelope
shifts, one file changes.

Nothing here interprets. `Item.is_blocking` reads the recorded disposition; it
does not re-derive it from flags. Track C decides dispositions; Track D
renders them. If those two ever disagree the fixture is wrong, and
`tests/test_track_d.py` says so rather than letting the UI paper over it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

from mnemonica.contracts import Role, Session, Turn

__all__ = [
    "Quote",
    "Flag",
    "Item",
    "Discarded",
    "Extraction",
    "Disposition",
]

Disposition = Literal[
    "printed_as_fact",
    "prefilled_flagged",
    "blocking",
    "surfaced",
]
"""Where an item sits in the D16 table, as Track C dispositioned it."""


@dataclass(frozen=True)
class Quote:
    """A verified span — text plus where it lives in the transcript and audio.

    `char_offset` indexes `Session.transcript_text` (contract 1a), which is
    what makes U4's click-to-play possible without a second alignment pass:
    the words are already keyed to the same string.
    """

    text: str
    char_offset: int
    char_end: int
    turn_id: int
    turn_role: Role
    audio_start: float
    min_word_probability: float

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Quote:
        return cls(
            text=raw["text"],
            char_offset=raw["char_offset"],
            char_end=raw["char_end"],
            turn_id=raw["turn_id"],
            turn_role=raw["turn_role"],
            audio_start=raw["audio_start"],
            min_word_probability=raw["min_word_probability"],
        )

    def verify_against(self, session: Session) -> bool:
        """D14, run again at render time.

        C4 already did this. Doing it once more before anything prints costs
        microseconds and closes the case where an item survives extraction and
        then gets rendered from a stale offset.
        """
        return (
            session.transcript_text[self.char_offset : self.char_end] == self.text
        )


@dataclass(frozen=True)
class Flag:
    """One reason an item is not simply true.

    `render` is the fixture's own instruction — `"expanded"` or `"collapsed"`.
    U3 obeys it rather than inferring from `blocking`, because D16 category 8
    is non-blocking and must still be expanded: span verification structurally
    cannot catch a cross-turn association, so it does not get to hide.
    """

    d16_category: int | None
    blocking: bool
    reason: str
    render: Literal["expanded", "collapsed"]
    evidence: tuple[Quote, ...] = ()
    choices: tuple[str, ...] = ()
    display: str | None = None
    heard_text: str | None = None
    near_matches: tuple[str, ...] = ()
    suggested_action: str | None = None

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Flag:
        return cls(
            d16_category=raw.get("d16_category"),
            blocking=bool(raw.get("blocking", False)),
            reason=raw["reason"],
            render=raw.get("render", "collapsed"),
            evidence=tuple(Quote.parse(q) for q in raw.get("evidence", [])),
            choices=tuple(raw.get("choices", [])),
            display=raw.get("display"),
            heard_text=raw.get("heard_text"),
            near_matches=tuple(raw.get("near_matches", [])),
            suggested_action=raw.get("suggested_action"),
        )

    @property
    def needs_a_choice(self) -> bool:
        """Can the clinician settle this with one keystroke? (U5)

        Two shapes qualify: an explicit `choices` list (salt selection), and a
        blocking flag carrying two pieces of evidence (a contradiction — pick
        the one you meant). Attribution ambiguity has one piece of evidence and
        is settled by confirming or dropping it.
        """
        return bool(self.choices) or (self.blocking and len(self.evidence) >= 2)

    def options(self) -> list[str]:
        if self.choices:
            return list(self.choices)
        if self.blocking and len(self.evidence) >= 2:
            return [q.text for q in self.evidence]
        if self.blocking:
            return ["Confirm as spoken", "Remove this"]
        return []


@dataclass
class Item:
    """One extracted thing — a medication, an appointment, a red flag, a
    thread — with everything needed to render and to resolve it."""

    id: str
    kind: str
    disposition: Disposition
    d16_categories: tuple[int, ...]
    flags: tuple[Flag, ...]
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Item:
        return cls(
            id=raw["id"],
            kind=raw["kind"],
            disposition=raw["disposition"],
            d16_categories=tuple(raw.get("d16_categories", [])),
            flags=tuple(Flag.parse(f) for f in raw.get("flags", [])),
            raw=raw,
        )

    # -- disposition ------------------------------------------------------

    @property
    def is_blocking(self) -> bool:
        return self.disposition == "blocking"

    @property
    def blocking_flags(self) -> list[Flag]:
        return [f for f in self.flags if f.blocking]

    @property
    def render_expanded(self) -> bool:
        """U3's collapse rule.

        Blocking always. Otherwise: expanded iff some flag says so. A fully
        verified item has no flags and collapses — which is the entire point
        of the 60-second budget.
        """
        return self.is_blocking or any(f.render == "expanded" for f in self.flags)

    @property
    def is_verified(self) -> bool:
        return not self.flags and self.disposition == "printed_as_fact"

    # -- quotes -----------------------------------------------------------

    @property
    def primary_quote(self) -> Quote | None:
        """The span U4 cues to when the line is clicked."""
        for key in (
            "mention_quote",
            "instruction_quote",
            "topic_quote",
            "purpose_quote",
        ):
            if self.raw.get(key):
                return Quote.parse(self.raw[key])
        when = self.raw.get("when")
        if isinstance(when, dict) and when.get("quote"):
            return Quote.parse(when["quote"])
        return None

    def all_quotes(self) -> list[Quote]:
        """Every span this item rests on — what D14 is re-checked against."""
        found: list[Quote] = []
        q = self.primary_quote
        if q:
            found.append(q)
        for key in ("change_evidence_quote", "purpose_quote"):
            if self.raw.get(key):
                found.append(Quote.parse(self.raw[key]))
        for sig in self.raw.get("sig", []) or []:
            if sig.get("quote"):
                found.append(Quote.parse(sig["quote"]))
        deriv = self.raw.get("change_kind_derivation")
        if deriv:
            for side in ("from_dose", "to_dose"):
                if deriv.get(side, {}).get("quote"):
                    found.append(Quote.parse(deriv[side]["quote"]))
        for f in self.flags:
            found.extend(f.evidence)
        seen: set[tuple[int, int]] = set()
        unique: list[Quote] = []
        for quote in found:
            key = (quote.char_offset, quote.char_end)
            if key not in seen:
                seen.add(key)
                unique.append(quote)
        return unique

    @property
    def title(self) -> str:
        if self.kind == "medication":
            med = self.raw.get("medication", {})
            name = med.get("canonical_name")
            if name:
                return name
            heard = self.primary_quote
            return f"“{heard.text}”" if heard else "unidentified medication"
        if self.kind == "appointment":
            return "Follow-up appointment"
        if self.kind == "red_flag":
            # Two red flags both titled "When to call" are indistinguishable
            # while collapsed, which is the state they are normally in.
            quote = self.primary_quote
            if quote:
                words = quote.text.split()
                short = " ".join(words[:8])
                return short + ("\u2026" if len(words) > 8 else "")
            return "When to call"
        if self.kind == "loose_thread":
            return "Raised but not settled"
        return self.kind.replace("_", " ")


@dataclass(frozen=True)
class Discarded:
    """D16 category 1 — dropped silently, counted loudly.

    The clinician never sees the fabricated text. They do see that something
    was thrown away, because on a page where everything verified is collapsed,
    a silent deletion is indistinguishable from a clean run.
    """

    d16_category: int
    kind: str
    reason: str
    dropped_at: str

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Discarded:
        return cls(
            d16_category=raw["d16_category"],
            kind=raw["kind"],
            reason=raw["reason"],
            dropped_at=raw["dropped_at"],
        )


@dataclass
class Extraction:
    """The whole post-C5 payload for one visit."""

    visit_date: date
    medications: list[Item]
    appointments: list[Item]
    red_flags: list[Item]
    loose_threads: list[Item]
    discarded: list[Discarded]
    summary_quotes: dict[str, list[Quote]]
    recorded_header: dict[str, int]

    @classmethod
    def load(cls, path: Path | str) -> Extraction:
        return cls.parse(json.loads(Path(path).read_text()))

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Extraction:
        def items(key: str) -> list[Item]:
            return [Item.parse(i) for i in raw.get(key, [])]

        return cls(
            visit_date=date.fromisoformat(raw["visit_date"]),
            medications=items("medications"),
            appointments=items("appointments"),
            red_flags=items("red_flags"),
            loose_threads=items("loose_threads"),
            discarded=[Discarded.parse(d) for d in raw.get("discarded", [])],
            summary_quotes={
                heading: [Quote.parse(q) for q in quotes]
                for heading, quotes in raw.get("summary_quotes", {}).items()
            },
            recorded_header=dict(raw.get("header", {})),
        )

    @property
    def items(self) -> list[Item]:
        """Review order: blocking first, then anything expanded, then the
        collapsed remainder — D9's eye-path, not the JSON's key order."""
        # `summary` is a scope entry but not an item list — it is quotes,
        # with nothing to settle — so it is filtered out here and consulted
        # directly by the two renderers.
        everything = [
            item
            for kind in SCOPE
            if kind in ITEM_KINDS
            for item in getattr(self, kind)
        ]
        return sorted(
            everything,
            key=lambda i: (0 if i.is_blocking else 1 if i.render_expanded else 2),
        )

    def item(self, item_id: str) -> Item | None:
        for i in self.items:
            if i.id == item_id:
                return i
        return None

    def header(self) -> dict[str, int]:
        """Counted from the items, not copied from the fixture's `header`.

        U3 prints this, and a header block that drifts from its own item list
        is a lie told confidently. `tests/test_track_d.py` asserts the two
        agree; when they don't, the fixture is what's wrong.
        """
        every = self.items
        return {
            "confirmed": sum(1 for i in every if not i.flags),
            "blocking": sum(1 for i in every if i.is_blocking),
            "needs_confirmation": sum(
                1
                for i in every
                if i.flags and not i.is_blocking and i.kind != "loose_thread"
            ),
            "discarded": len(self.discarded),
            "loose_threads": len(self.loose_threads),
        }


@dataclass
class Resolution:
    """What the clinician decided about one item (U5).

    Kept out of `Item` on purpose. `Item` is Track C's output and is read-only
    to Track D; this is the doctor's half of the record, and at approval time
    the two are rendered together. Keeping them separate is what lets U9 say
    honestly which values came from the model and which from the human.
    """

    item_id: str
    choices: dict[int, str] = field(default_factory=dict)
    """Flag index → the option the clinician picked."""
    promoted: bool = False
    """They confirmed an underived `change_kind` (U6)."""
    dropped: bool = False
    """They threw the item out. It does not print."""
    resolved_at: str | None = None

    def settles(self, flag_index: int) -> str | None:
        return self.choices.get(flag_index)


ITEM_KINDS: frozenset[str] = frozenset(
    {"medications", "appointments", "red_flags", "loose_threads"}
)
"""Scope entries that are lists of `Item`. `summary` is not one."""

SCOPE: tuple[str, ...] = ("medications",)
"""Which extracted kinds reach a human — D29.

Extraction still produces appointments, red flags and loose threads, they are
still verified, and they are still in `extraction.json`. They are simply not
shown. Narrowing here rather than in the prompt keeps the data, keeps the
tests, and makes the decision one line to reverse:

    SCOPE = ("medications", "appointments", "red_flags", "loose_threads")

Why medications. Every kind is a surface that can be wrong in its own way —
appointments needed deduplication, red flags needed deduplication, and each
carried its own rendering quirks. Medications are the highest-stakes output
and the one the tool layer actually grounds: RxNorm resolves the name, the sig
grammar parses the dose, and D16 category 7 catches a contradiction. Nothing
grounds a red flag beyond quoting it.

A narrower product that is right beats a broad one that is nearly right,
particularly when the broad parts are the ungrounded ones.
"""


def unverified_identity_flag(item: Item) -> int | None:
    """Index of this item's D16 category 4 flag — no RxNorm concept matched.

    Deliberately separate from `is_blocking`. Category 4 is *not* blocking:
    D16 says an unresolved drug name is prefilled and flagged, and a clinician
    may sign without touching it. But SPEC D16 also says nothing unverified
    reaches the printed page, and both hold at once only if an unresolved name
    is allowed to sit unanswered in review **and** is kept off the handout.

    The failure this closes: a patient's own stumble over a drug name
    (`"lyso, ly, lysinop, lysinopril"`) printed as a third medicine on the
    page their family reads, duplicating one already listed correctly above
    it. Nothing was blocking, so approval never paused.
    """
    med = item.raw.get("medication")
    if not isinstance(med, dict) or med.get("status") != "unresolved":
        return None
    for i, flag in enumerate(item.flags):
        if flag.d16_category == 4:
            return i
    return None


def identity_is_verified(item: Item, resolution: Resolution | None) -> bool:
    """May this item's drug name be printed as a medicine the patient takes?

    True when the resolver named the drug, or when the clinician answered the
    flag saying it could not. An unanswered category 4 is neither.
    """
    index = unverified_identity_flag(item)
    if index is None:
        return True
    if resolution is None:
        return False
    return resolution.settles(index) is not None


def item_is_resolved(item: Item, resolution: Resolution | None) -> bool:
    """Has every blocking flag on this item been answered?

    Approval is gated on this for every item, so it is deliberately strict: an
    item with no resolution and a blocking flag is not resolved, and dropping
    the item counts as answering it.
    """
    if not item.is_blocking:
        return True
    if resolution is None:
        return False
    if resolution.dropped:
        return True
    return all(
        resolution.settles(i) is not None
        for i, f in enumerate(item.flags)
        if f.blocking
    )
