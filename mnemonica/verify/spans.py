"""C4 — span verification. D14, TOOLS.md §5 steps 1–3.

**The model does not emit character offsets. This code computes them.** Models
cannot see character positions; asking for offsets is asking for arithmetic on
boundaries absent from their representation, and correct extractions then fail
our own verifier. So the model emits a string and we search for it:

    one match    -> offsets assigned, accepted
    zero matches -> FABRICATION -> dropped silently, logged, counted
    2+ matches   -> disambiguate by nearest turn

That makes the guarantee stronger, not weaker: offsets come from `str.find`,
not from a claim.

The zero-match case is D16 category 1. The item never surfaces to the
clinician, never gets a badge, never gets a queue entry — the correct response
to detected fabrication is deletion, not disclosure. But the **count** reaches
the UI, because a silently deleted medication is indistinguishable from one the
model never found, and D9 collapses everything non-blocking: on a page that
looks complete, an omission is otherwise invisible.

Verification is deliberately **exact**, not fuzzy. A near-match is a model that
edited the transcript, and the whole verbatim rule exists to make that
detectable. Whitespace is the one concession — a quote spanning a turn boundary
picks up the join — and even that only collapses runs of whitespace, never
changes a character.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mnemonica.contracts import Role, Session, Turn

__all__ = ["Quote", "SpanVerifier", "Dropped"]

_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class Quote:
    """A verified span. Mirrors `render.model.Quote` — the shape Track D reads.

    `min_word_probability` is carried here because D16 category 2 needs it and
    this is the only place that knows which words a span covers. Recomputing it
    downstream would mean re-walking the word list from an offset, which is the
    kind of duplicated arithmetic that drifts."""

    text: str
    char_offset: int
    char_end: int
    turn_id: int
    turn_role: Role
    audio_start: float
    min_word_probability: float

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "char_offset": self.char_offset,
            "char_end": self.char_end,
            "turn_id": self.turn_id,
            "turn_role": self.turn_role,
            "audio_start": round(self.audio_start, 2),
            "min_word_probability": round(self.min_word_probability, 3),
        }


@dataclass(frozen=True)
class Dropped:
    """D16 category 1 — one fabrication, recorded without its text.

    The fabricated string is **not** stored. It is written to the log (which
    D2/D3 shred with the session) and counted here; putting it in the envelope
    would walk it back into the UI through a side door."""

    d16_category: int
    kind: str
    reason: str
    dropped_at: str

    def as_dict(self) -> dict:
        return {
            "d16_category": self.d16_category, "kind": self.kind,
            "reason": self.reason, "dropped_at": self.dropped_at,
        }


class SpanVerifier:
    """Verifies quotes against one session's `transcript_text`.

    Stateful on purpose: it accumulates the drop count, which is the number
    U3's header prints."""

    def __init__(self, session: Session, *, logger=None):
        self.session = session
        self.text = session.transcript_text
        self.dropped: list[Dropped] = []
        self.empty = 0
        """Fields the model left blank. Not fabrications, not counted as
        discarded — see `verify`."""
        self._log = logger

    # -- the search -------------------------------------------------------

    def _occurrences(self, needle: str) -> list[int]:
        out, i = [], self.text.find(needle)
        while i != -1:
            out.append(i)
            i = self.text.find(needle, i + 1)
        return out

    def _relaxed(self, needle: str) -> list[int]:
        """Whitespace-insensitive retry.

        A quote that spans a turn boundary picks up whatever joined the turns,
        and a model that renders that join as a single space has not edited
        anything meaningful. Character content still has to match exactly."""
        pattern = r"\s+".join(re.escape(p) for p in _WS.split(needle.strip()) if p)
        if not pattern:
            return []
        return [m.start() for m in re.finditer(pattern, self.text)]

    def verify(
        self, quote: str, *, kind: str = "quote", near: Turn | None = None,
        stage: str = "C4",
    ) -> Quote | None:
        """One quote → a `Quote` with real offsets, or `None` (dropped).

        `near` is the turn the model was looking at when it produced this. It
        only decides between **several genuine occurrences**; it can never
        rescue a quote that is not in the transcript."""
        if not quote or not quote.strip():
            # An empty string is an **absence, not a fabrication**, and the
            # difference reaches the clinician: category 1's count is the
            # promise that something was thrown away. A model that emits
            # `change_evidence_quote: ""` is declining to support a field the
            # schema makes required — measured at 2 of 38 quotes on the 9B —
            # and counting that as a discarded item would make the header
            # claim a deletion that never happened.
            self.empty += 1
            return None

        hits = self._occurrences(quote)
        matched = quote
        if not hits:
            hits = self._relaxed(quote)
            if hits:
                # Re-read the real text at the match so the stored span is the
                # transcript's characters, never the model's rendering of them.
                pattern = r"\s+".join(
                    re.escape(p) for p in _WS.split(quote.strip()) if p)
                m = re.compile(pattern).match(self.text, hits[0])
                matched = m.group(0) if m else quote
        if not hits:
            return self._drop(kind, "span_verification_failed", stage)

        offset = hits[0] if len(hits) == 1 else self._nearest(hits, near)
        if len(hits) > 1 and matched != quote:
            m = re.compile(
                r"\s+".join(re.escape(p) for p in _WS.split(quote.strip()) if p)
            ).match(self.text, offset)
            matched = m.group(0) if m else matched
        return self._build(matched, offset)

    def _nearest(self, hits: list[int], near: Turn | None) -> int:
        """D14's multiple-match rule: disambiguate by nearest turn.

        With no turn to aim at, take the first occurrence — earliest is at
        least deterministic, and any preference we invented here would be a
        guess dressed as a rule."""
        if near is None:
            return hits[0]
        inside = [h for h in hits if near.char_start <= h < near.char_end]
        if inside:
            return inside[0]
        mid = (near.char_start + near.char_end) // 2
        return min(hits, key=lambda h: abs(h - mid))

    # -- assembling the verified span -------------------------------------

    def _build(self, text: str, offset: int) -> Quote:
        end = offset + len(text)
        turn = self.session.turn_at_offset(offset)
        if turn is None:  # a span landing in a turn join — take the next turn
            turn = min(
                (t for t in self.session.turns if t.char_start >= offset),
                key=lambda t: t.char_start,
                default=self.session.turns[-1],
            )
        words = [w for w in turn.words if w.char_offset < end and w.char_end > offset]
        return Quote(
            text=text, char_offset=offset, char_end=end,
            turn_id=turn.id, turn_role=turn.role,
            audio_start=words[0].start if words else turn.start,
            min_word_probability=min((w.probability for w in words), default=1.0),
        )

    def _drop(self, kind: str, reason: str, stage: str) -> None:
        """Deletion, not disclosure — and a count."""
        self.dropped.append(Dropped(1, kind, reason, stage))
        if self._log:
            self._log(kind, reason, stage)
        return None

    @property
    def drop_count(self) -> int:
        return len(self.dropped)
