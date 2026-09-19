"""The shared data contract — Phase 1 step 1a.

Every track imports from this file. Track B *produces* a `Session`; Tracks C
and D *consume* one. If two tracks disagree about what a transcript is, you
find out at hour 18. So it is written once, here, and nowhere else.

Three invariants are worth stating out loud, because the whole design rests on
them:

1. **`Session.transcript_text` is the search string.** It is the exact string
   `resolve_medication` receives quotes from and the exact string span
   verification runs `str.find` over (D14). Every `Word.char_offset` indexes
   into it. If Track B builds transcript_text one way and Track C searches a
   differently-joined string, every citation silently breaks and nothing
   raises.

2. **`visit_date` is persisted, not recomputed** (D18). The audio file's mtime
   is read once at ingest and stored. `cp` without `-p` resets it, and so does
   any re-encode or cloud sync. Never read mtime again.

3. **`consent` is required** (D27), today, even though nothing populates it
   yet. Adding a required field to `Session` at hour 14 means touching four
   people's call sites.

Changing this file needs agreement first (BRIEFING §2), and when it changes it
merges to `main` immediately — everyone else has to rebase before their next
commit.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

__all__ = ["Word", "Turn", "Consent", "Session", "Role", "SpeakerCluster"]


Role = Literal["clinician", "other", "unknown"]
"""Who is speaking.

`other` is the patient or a companion — deliberately not split, because we
cannot tell them apart and D19 pins `num_speakers=2` anyway. `unknown` is a
cluster that enrollment could not match with confidence (D20), and it is what
makes D16 category 3 fire: a dose from an `unknown` turn is blocking.
"""

SpeakerCluster = str
"""A pyannote label: `"SPEAKER_00"`, `"SPEAKER_01"`.

Anonymous and role-free by construction — pyannote does not know who anyone
is. Mapping a cluster to a `Role` is D20's enrollment match, and it happens
once per session, not per turn.
"""


class Word(BaseModel):
    """One word from mlx-whisper, placed in the transcript and in a cluster.

    `text` carries no leading or trailing whitespace: mlx-whisper's
    `WordTiming.word` usually arrives as `" metoprolol"`, and the leading space
    must be stripped at ingest with `char_offset` pointing at the `m`. The
    contract is exact:

        session.transcript_text[w.char_offset : w.char_offset + len(w.text)] == w.text

    `Session` validates this for every word, so a fixture or a Track B run that
    gets it wrong fails loudly at construction rather than quietly at citation
    time.
    """

    text: str = Field(min_length=1)
    start: float = Field(ge=0.0)
    """Seconds from the start of the audio."""
    end: float = Field(ge=0.0)
    probability: float = Field(ge=0.0, le=1.0)
    """mlx-whisper `WordTiming.probability`. D16 category 2 reads this."""
    speaker_cluster: SpeakerCluster
    char_offset: int = Field(ge=0)
    """Index into `Session.transcript_text` — the string span verification
    searches (D14). Not an index into `Turn.text`."""

    @property
    def char_end(self) -> int:
        return self.char_offset + len(self.text)

    @model_validator(mode="after")
    def _times_ordered(self) -> Word:
        if self.end < self.start:
            raise ValueError(f"word {self.text!r}: end {self.end} < start {self.start}")
        return self


class Turn(BaseModel):
    """One speaker's contiguous stretch of speech — D15's extraction unit.

    Extraction is chunked by turn, so attribution comes free from the chunk's
    speaker label, and a failed extraction is isolated to one turn.

    `char_start` / `char_end` bound this turn inside `transcript_text`. They
    are what C4.5 needs: given a verified quote's offset, which turn did it
    come from? A `sig` whose quote lands in a different turn than its drug
    mention is D16 category 8 — the failure span verification structurally
    cannot see, because both quotes are genuine.
    """

    id: int = Field(ge=0)
    speaker_cluster: SpeakerCluster
    role: Role
    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    words: list[Word] = Field(min_length=1)
    text: str = Field(min_length=1)
    """Exactly `transcript_text[char_start:char_end]`. Validated."""
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)

    @model_validator(mode="after")
    def _internally_consistent(self) -> Turn:
        if self.end < self.start:
            raise ValueError(f"turn {self.id}: end {self.end} < start {self.start}")
        if self.char_end < self.char_start:
            raise ValueError(f"turn {self.id}: char_end < char_start")
        if len(self.text) != self.char_end - self.char_start:
            raise ValueError(
                f"turn {self.id}: text is {len(self.text)} chars but "
                f"char span is {self.char_end - self.char_start}"
            )
        for w in self.words:
            if w.speaker_cluster != self.speaker_cluster:
                raise ValueError(
                    f"turn {self.id} is {self.speaker_cluster} but word "
                    f"{w.text!r} is {w.speaker_cluster}"
                )
            if w.char_offset < self.char_start or w.char_end > self.char_end:
                raise ValueError(
                    f"turn {self.id}: word {w.text!r} at {w.char_offset} "
                    f"falls outside the turn's span "
                    f"[{self.char_start}, {self.char_end})"
                )
        return self

    def contains_offset(self, offset: int) -> bool:
        """Did a verified quote at `offset` come from this turn? (C4.5)"""
        return self.char_start <= offset < self.char_end


class Consent(BaseModel):
    """D27 — the patient consents before recording starts.

    Required. A session cannot reach review without it, and the printed page
    carries a line saying it was obtained (U8).
    """

    obtained: bool
    method: Literal["verbal", "written"]
    obtained_at: datetime

    @model_validator(mode="after")
    def _must_be_obtained(self) -> Consent:
        if not self.obtained:
            raise ValueError(
                "D27: recording requires obtained consent; a Session cannot "
                "carry consent.obtained=False"
            )
        return self


class Session(BaseModel):
    """One visit: the audio, the transcript, and what was said in it.

    This is Track B's output and Tracks C and D's input. The fixtures in
    `fixtures/golden_visit.json` are a hand-written instance of it (1c-i), and
    they are what lets C and D build before any audio exists.
    """

    visit_date: date
    """D18 — the audio file's mtime, read ONCE at ingest and persisted here.
    Every relative date ("come back in three weeks") anchors to this."""
    session_dir: Path
    """Everything this session wrote, in one directory — D2/D3's unit of
    retention.

    The retention policy covers **logs too**: a dropped-quote log line
    contains transcript text, and so do ffmpeg scratch files and tracebacks.
    `audio_path` alone invites `unlink(audio_path)` at U9, which shreds the
    `.wav` and leaves the PHI beside it. Shred this directory, not the file.

    `audio_path` must live inside it — validated."""
    audio_path: Path
    transcript_text: str
    """The single search string. `str.find` over this is span verification."""
    turns: list[Turn]
    consent: Consent

    @model_validator(mode="after")
    def _audio_lives_in_session_dir(self) -> Session:
        """U9 shreds `session_dir`. An `audio_path` outside it survives.

        Compared as written — no `resolve()`, because fixture paths point at
        files that do not exist. Both paths must therefore be absolute, or
        both relative to the same root.
        """
        if self.audio_path.is_absolute() != self.session_dir.is_absolute():
            raise ValueError(
                f"audio_path ({self.audio_path}) and session_dir "
                f"({self.session_dir}) must both be absolute or both relative"
            )
        if ".." in self.audio_path.parts or ".." in self.session_dir.parts:
            raise ValueError("'..' in a session path defeats the containment check")
        if not self.audio_path.is_relative_to(self.session_dir):
            raise ValueError(
                f"audio_path {self.audio_path} is outside session_dir "
                f"{self.session_dir} — U9 shreds the directory, so audio "
                f"stored elsewhere would survive approval"
            )
        return self

    @model_validator(mode="after")
    def _offsets_index_into_transcript(self) -> Session:
        """The assertion B4 must pass and 1c must satisfy.

        This is the one that silently breaks everything if it is wrong, so it
        runs on every construction — including `Session.model_validate_json`
        of the golden fixture.
        """
        text = self.transcript_text
        for turn in self.turns:
            if text[turn.char_start : turn.char_end] != turn.text:
                raise ValueError(
                    f"turn {turn.id}: transcript_text"
                    f"[{turn.char_start}:{turn.char_end}] is "
                    f"{text[turn.char_start : turn.char_end]!r}, not {turn.text!r}"
                )
            for w in turn.words:
                found = text[w.char_offset : w.char_end]
                if found != w.text:
                    raise ValueError(
                        f"turn {turn.id}: word {w.text!r} claims offset "
                        f"{w.char_offset}, where transcript_text has {found!r}"
                    )
        ids = [t.id for t in self.turns]
        if ids != sorted(ids) or len(set(ids)) != len(ids):
            raise ValueError("turn ids must be unique and ascending")
        return self

    def turn_at_offset(self, offset: int) -> Turn | None:
        """Which turn does a verified quote belong to? (C4.5, D16 category 8)"""
        for turn in self.turns:
            if turn.contains_offset(offset):
                return turn
        return None

    def clinician_turns(self) -> list[Turn]:
        """D19's hard rule: a dose or frequency may only be extracted from a
        clinician-labelled turn."""
        return [t for t in self.turns if t.role == "clinician"]
