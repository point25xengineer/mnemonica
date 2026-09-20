"""B4 — place every word in a speaker's turn, and build the search string.

This is the bridge to D14. `Session.transcript_text` is the exact string span
verification runs `str.find` over, and every `Word.char_offset` indexes into
it. If Track B joins the transcript one way and Track C searches a
differently-joined string, every citation silently points at the wrong
characters and nothing raises. So the offsets are *computed here from the
string that is actually emitted*, never carried over from somewhere else.

**A word with no overlapping diarization interval is DROPPED, not snapped to
the nearest speaker.** It never enters `transcript_text` and never gets an
offset. Three lines, and the cheapest anti-hallucination measure in the build:
Whisper large-v3 invents text over silence, and silence is exactly where
pyannote finds no speech — so exclusive diarization deletes most inventions
before they can become quotable spans. A snapped word, by contrast, is an
invention with a speaker attached, which is worse than no word at all.

`char_offset` is computed *after* dropping, for the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..contracts import Role, Turn, Word
from .diarize import Diarization
from .transcribe import RawWord, Transcript

__all__ = ["Assembled", "DroppedWord", "assemble"]


@dataclass(frozen=True)
class DroppedWord:
    """A word that did not survive to the transcript, and why.

    Kept for the review header's count and for the demo's "here is what we
    threw away" beat. It is PHI — it lives in `session_dir` with everything
    else (D2/D3) and dies with it at U9.
    """

    text: str
    start: float
    end: float
    probability: float
    reason: str


@dataclass
class Assembled:
    transcript_text: str
    turns: list[Turn]
    dropped: list[DroppedWord] = field(default_factory=list)
    suspect_segments: list[int] = field(default_factory=list)
    """Whisper segment ids that tripped the compression-ratio /
    no_speech_prob heuristic. Words from these survive if diarization backs
    them — D16 category 2 reads the flag, it does not delete the text."""

    def assert_offsets(self) -> None:
        """The B4 acceptance criterion, stated as code.

        `Session` validates this too, on construction. It is asserted here as
        well so a failure names B4 rather than surfacing as a pydantic error
        three frames away from the bug.
        """
        for turn in self.turns:
            span = self.transcript_text[turn.char_start : turn.char_end]
            assert span == turn.text, f"turn {turn.id}: {span!r} != {turn.text!r}"
            for w in turn.words:
                found = self.transcript_text[w.char_offset : w.char_end]
                assert found == w.text, (
                    f"word {w.text!r} claims offset {w.char_offset}, "
                    f"where transcript_text has {found!r}"
                )


def assemble(
    transcript: Transcript,
    diarization: Diarization,
    roles: dict[str, Role],
) -> Assembled:
    """Words + intervals + roles → turns, transcript text and offsets."""
    suspect = {s.id for s in transcript.segments if s.is_suspect}

    kept: list[tuple[RawWord, str]] = []
    dropped: list[DroppedWord] = []
    for w in transcript.words:
        cluster = diarization.cluster_at(w.start, w.end)
        if cluster is None:
            dropped.append(
                DroppedWord(
                    text=w.text,
                    start=w.start,
                    end=w.end,
                    probability=w.probability,
                    reason=(
                        "hallucinated over silence — no diarization interval"
                        if w.segment_id in suspect
                        else "no diarization interval"
                    ),
                )
            )
            continue
        kept.append((w, cluster))

    # One turn per contiguous stretch of one voice. exclusive_speaker_
    # diarization can emit several adjacent intervals for the same speaker;
    # merging them here is what makes the output comparable to fixture 1c,
    # whose consecutive same-speaker lines are merged for this exact reason.
    groups: list[tuple[str, list[RawWord]]] = []
    for word, cluster in kept:
        if groups and groups[-1][0] == cluster:
            groups[-1][1].append(word)
        else:
            groups.append((cluster, [word]))

    turns: list[Turn] = []
    parts: list[str] = []
    cursor = 0
    for turn_id, (cluster, raw_words) in enumerate(groups):
        tokens = [w.text for w in raw_words]
        text = " ".join(tokens)
        if parts:
            cursor += 1  # the single space joining this turn to the previous
        char_start = cursor

        words: list[Word] = []
        within = 0
        for token, raw in zip(tokens, raw_words):
            # index(), not find(): a token that is not there is a bug in the
            # join above, and it should raise here rather than silently
            # produce offset -1.
            i = text.index(token, within)
            within = i + len(token)
            words.append(
                Word(
                    text=token,
                    start=raw.start,
                    end=raw.end,
                    probability=raw.probability,
                    speaker_cluster=cluster,
                    char_offset=char_start + i,
                )
            )

        cursor = char_start + len(text)
        parts.append(text)
        turns.append(
            Turn(
                id=turn_id,
                speaker_cluster=cluster,
                role=roles.get(cluster, "unknown"),
                start=raw_words[0].start,
                end=raw_words[-1].end,
                words=words,
                text=text,
                char_start=char_start,
                char_end=cursor,
            )
        )

    assembled = Assembled(
        transcript_text=" ".join(parts),
        turns=turns,
        dropped=dropped,
        suspect_segments=sorted(suspect),
    )
    assembled.assert_offsets()
    return assembled
