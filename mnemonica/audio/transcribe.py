"""B1 — Whisper large-v3 → words with timestamps and confidence.

**large-v3, not turbo** (D21). Neither checkpoint ships ``alignment_heads``,
so mlx-whisper falls back to "the last half of the decoder layers" for the DTW
alignment that produces word timestamps. On large-v3 that is 16 layers; on
turbo it is 2, because turbo has only 4 decoder layers in total. The entire
provenance chain in this build is word offsets, so the 1.5 GB saving buys a
broken citation.

Segment-level fields are carried through, not discarded. Whisper large-v3
invents text over silence, and an exam room has plenty of it. Those inventions
land in ``transcript_text``, which makes them *verifiable spans* — ``str.find``
confirms them and span verification (D14) cannot help. ``no_speech_prob`` and
``compression_ratio`` are how D16 category 2 sees them; B4's drop rule catches
most of the rest.
"""

from __future__ import annotations

import env_guard  # noqa: F401  — must precede transformers/torch

from dataclasses import dataclass
from pathlib import Path

__all__ = ["RawWord", "Segment", "Transcript", "transcribe", "PRIMING_PROMPT"]

MODEL = "mlx-community/whisper-large-v3-mlx"
"""Pass this explicitly — mlx-whisper's in-code default is whisper-tiny, which
differs from its README, and a silent tiny run looks like a bad recording."""

#: Commonly prescribed generic names, used to bias spelling (see below).
#: Whisper's prompt context is ~224 tokens, so this is a targeted nudge, not a
#: vocabulary.
_COMMON_DRUGS = [
    "atorvastatin", "levothyroxine", "amlodipine", "omeprazole", "albuterol",
    "gabapentin", "losartan", "hydrochlorothiazide", "sertraline", "simvastatin",
    "montelukast", "escitalopram", "rosuvastatin", "bupropion", "furosemide",
    "pantoprazole", "trazodone", "fluoxetine", "tamsulosin", "duloxetine",
    "prednisone", "citalopram", "clopidogrel", "carvedilol", "meloxicam",
    "metformin", "glipizide", "allopurinol", "atenolol", "warfarin",
    "venlafaxine", "alprazolam", "clonazepam", "ibuprofen", "amoxicillin",
    "azithromycin", "cephalexin", "doxycycline", "ondansetron", "naproxen",
    "spironolactone", "diltiazem", "apixaban", "insulin glargine", "ezetimibe",
    "finasteride", "oxybutynin", "famotidine", "cetirizine", "propranolol",
]

#: Every drug spoken in the role-play script (1d). These are REMOVED from the
#: priming prompt, and the removal is the point.
#:
#: Priming on the demo's own drugs does two bad things, and the second is the
#: one that bites. It overfits the demo, so measured accuracy means nothing.
#: And it suppresses the `metropolol` -> *metoprolol* mistranscription that is
#: demo beat #2 — you would be priming away the exact error you are about to
#: show off catching.
_SCRIPT_DRUGS = frozenset({"metoprolol", "lisinopril"})

PRIMING_PROMPT = ", ".join(
    d for d in _COMMON_DRUGS if d.split()[0].lower() not in _SCRIPT_DRUGS
) + "."


@dataclass(frozen=True)
class Segment:
    """Whisper's own decode unit, kept for its quality signals.

    Not part of the `Session` contract — B4 attaches these to the words that
    came out of each one, and only the quality fields survive into D16.
    """

    id: int
    start: float
    end: float
    text: str
    avg_logprob: float
    compression_ratio: float
    no_speech_prob: float

    @property
    def is_suspect(self) -> bool:
        """The standard hallucination heuristic: repetitive text compresses
        well, and invented speech sits on top of `no_speech`."""
        return self.compression_ratio > 2.4 or self.no_speech_prob > 0.6


@dataclass(frozen=True)
class RawWord:
    """One `WordTiming` from mlx-whisper, before diarization places it.

    `text` is already stripped: mlx-whisper emits `" metoprolol"` with a
    leading space, and 1a's contract says `Word.text` carries no whitespace
    with `char_offset` pointing at the `m`. Strip once, here, so no downstream
    step has to remember to.
    """

    text: str
    start: float
    end: float
    probability: float
    segment_id: int


@dataclass(frozen=True)
class Transcript:
    words: list[RawWord]
    segments: list[Segment]
    language: str

    def segment(self, word: RawWord) -> Segment:
        return self.segments[word.segment_id]


def transcribe(
    path: Path | str,
    *,
    model: str = MODEL,
    prime_drug_names: bool = True,
) -> Transcript:
    """Run Whisper over `path` and return words with timings and confidence."""
    import mlx_whisper

    result = mlx_whisper.transcribe(
        str(path),
        path_or_hf_repo=model,
        word_timestamps=True,
        initial_prompt=PRIMING_PROMPT if prime_drug_names else None,
    )

    segments: list[Segment] = []
    words: list[RawWord] = []
    for i, seg in enumerate(result.get("segments", [])):
        segments.append(
            Segment(
                id=i,
                start=float(seg["start"]),
                end=float(seg["end"]),
                text=seg.get("text", ""),
                avg_logprob=float(seg.get("avg_logprob", 0.0)),
                compression_ratio=float(seg.get("compression_ratio", 0.0)),
                no_speech_prob=float(seg.get("no_speech_prob", 0.0)),
            )
        )
        for w in seg.get("words", []) or []:
            text = w["word"].strip()
            if not text:
                continue  # whitespace-only token: no span to cite
            words.append(
                RawWord(
                    text=text,
                    start=float(w["start"]),
                    end=float(w["end"]),
                    probability=float(w.get("probability", 1.0)),
                    segment_id=i,
                )
            )

    return Transcript(
        words=words, segments=segments, language=result.get("language", "en")
    )
