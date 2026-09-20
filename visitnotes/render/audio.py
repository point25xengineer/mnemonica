"""U4 — turning a verified span into two seconds of audio.

Nothing here touches an audio file. A `Quote` already carries `char_offset`
into `Session.transcript_text`, and every `Word` carries the same offset plus
its `start`/`end` — so the window is a lookup, not an alignment.

The one decision with teeth: a flagged item cues to the **uncertain word**,
not to the start of the quote. If a dose numeral came back at p=0.66 inside a
confident sentence, the doctor needs to hear *that word*. Cueing to the
sentence start makes them listen to two seconds of context and guess which
part we doubted.
"""

from __future__ import annotations

from dataclasses import dataclass

from visitnotes.contracts import Session, Word
from visitnotes.render.model import Quote

__all__ = ["AudioCue", "words_in", "cue_for"]

LEAD_IN = 0.35
"""Seconds of run-up. Playback that starts exactly on the word clips its
onset, and a clipped 'fifty' sounds like 'ifty'."""

TAIL = 0.25


@dataclass(frozen=True)
class AudioCue:
    """A play window, in seconds from the start of the recording."""

    start: float
    end: float
    focus: float
    """Where the interesting word actually begins — what the UI highlights."""
    focus_word: str
    focus_probability: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    def media_fragment(self) -> str:
        """`#t=` per the W3C media-fragment syntax, which every browser's
        `<audio>` honours without a line of JavaScript."""
        return f"#t={self.start:.3f},{self.end:.3f}"


def words_in(session: Session, quote: Quote) -> list[Word]:
    """Every word whose characters fall inside the quote's span.

    Intersection, not containment: a quote may begin mid-word if C4 trimmed
    punctuation, and dropping that word would move the cue past the thing we
    are asking about.
    """
    return [
        w
        for turn in session.turns
        for w in turn.words
        if w.char_offset < quote.char_end and w.char_end > quote.char_offset
    ]


def cue_for(session: Session, quote: Quote, *, flagged: bool) -> AudioCue | None:
    """The window to play when this line is clicked.

    Verified lines cue to the whole span — the doctor is confirming a sentence.
    Flagged lines cue to the least-confident word inside it, because that is
    the thing in question. Returns `None` when the quote matches no words at
    all, which means the offsets are stale and the caller should not be
    offering playback in the first place.
    """
    words = words_in(session, quote)
    if not words:
        return None

    span_start = min(w.start for w in words)
    span_end = max(w.end for w in words)
    weakest = min(words, key=lambda w: w.probability)

    if flagged:
        focus = weakest.start
        start = max(0.0, focus - LEAD_IN)
        end = max(weakest.end + TAIL, min(span_end, focus + 2.5))
    else:
        focus = span_start
        start = max(0.0, span_start - LEAD_IN)
        end = span_end + TAIL

    return AudioCue(
        start=start,
        end=end,
        focus=focus,
        focus_word=weakest.text,
        focus_probability=weakest.probability,
    )
