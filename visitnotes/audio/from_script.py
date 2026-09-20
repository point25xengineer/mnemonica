"""Build a `Session` from a role-play script, with no audio and no models.

A development shortcut, not a pipeline stage. Recording two people every time
you want to check whether a template renders or a disposition fires is a slow
loop, and most of what Tracks C and D do has nothing to do with audio.

    python -m visitnotes.audio.from_script fixtures/roleplay_script_2.md \\
        --session-dir sessions/script2 --out sessions/script2/session.json

What this **is**: the same `Session` contract Track B emits, built from text.
Everything downstream — extraction, span verification, the tools, the review
screen — cannot tell the difference, which is the point.

What this is **not**: a substitute for running real audio. It fabricates the
three things only a microphone can produce, and every one of them is load
bearing somewhere:

* **Timings** are synthesised at a fixed speaking rate. Playback will be
  wrong, so gate B5's listening check cannot be done against a script.
* **Word probabilities** are all 1.0. D16 category 2 — low-confidence
  transcription — can therefore never fire here. A script cannot mumble.
* **Roles** come from the speaker labels in the markdown, not from voice
  enrollment. D20's matching and B6's unexpected-speaker check are both
  bypassed, so a role error in the real pipeline will not show up here.

The offsets are real, though: `char_offset` is computed against the same
`transcript_text` span verification searches, and the `Session` validator
enforces it on construction exactly as it does for the golden fixture.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from visitnotes.contracts import Consent, Session, Turn, Word  # noqa: E402

__all__ = ["parse_script", "session_from_script"]

WORDS_PER_SECOND = 2.6
"""Conversational speech, near enough. Only the ordering matters downstream —
nothing reads these numbers except the playback this file cannot support."""

GAP_SECONDS = 0.35
"""Between turns. Non-zero so turn boundaries are distinguishable."""

_SPEAKER = re.compile(r"^\*\*([A-Z][A-Z .'-]*?):?\*\*\s*(.*)$")
_STAGE = re.compile(r"\*\([^)]*\)\*")
"""`*(overlapping)*` and friends: a direction to the reader, never spoken."""

_CLINICIAN_HINTS = ("DR", "DOC", "CLINICIAN", "PHYSICIAN", "NURSE")


def _is_clinician(label: str) -> bool:
    head = label.replace(".", " ").split()[0].upper() if label.split() else ""
    return any(head.startswith(h) for h in _CLINICIAN_HINTS)


def _clean(text: str) -> str:
    """Strip stage directions and normalise the typography a markdown file
    carries but a transcript does not."""
    text = _STAGE.sub("", text)
    for fancy, plain in (("—", "-"), ("–", "-"), ("’", "'"),
                         ("‘", "'"), ("“", '"'), ("”", '"'),
                         ("…", "..."), (" ", " ")):
        text = text.replace(fancy, plain)
    text = text.replace("*", "").replace("&mdash;", "-")
    return re.sub(r"\s+", " ", text).strip()


def parse_script(markdown: str) -> list[tuple[str, str]]:
    """`[(speaker_label, spoken_text)]`, in order.

    Reads only the `## Script` section when one is present, so the expectations
    table and the casting notes in `roleplay_script_2.md` do not become turns.
    """
    lines = markdown.splitlines()
    start, end = 0, len(lines)
    for i, line in enumerate(lines):
        if re.match(r"^##\s+Script\b", line, re.I):
            start = i + 1
            for j in range(start, len(lines)):
                if re.match(r"^##\s+", lines[j]):
                    end = j
                    break
            break

    turns: list[tuple[str, str]] = []
    label: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if label and buffer:
            text = _clean(" ".join(buffer))
            if text:
                turns.append((label, text))

    for raw in lines[start:end]:
        line = raw.rstrip()
        if not line.strip() or line.startswith(("---", "#", ">", "|")):
            flush()
            label, buffer = None, []
            continue
        match = _SPEAKER.match(line.strip())
        if match:
            flush()
            label, buffer = match.group(1).strip(), [match.group(2)]
        elif label:
            buffer.append(line.strip())
    flush()
    return turns


def session_from_script(
    markdown: str,
    *,
    session_dir: Path,
    visit_date: date | None = None,
    consent: Consent | None = None,
) -> Session:
    """Assemble the `Session`. Offsets are computed, never assumed."""
    spoken = parse_script(markdown)
    if not spoken:
        raise ValueError(
            "no dialogue found — expected lines like `**DR:** ...` under a "
            "`## Script` heading"
        )

    transcript_parts: list[str] = []
    turns: list[Turn] = []
    cursor = 0
    clock = 0.0

    for index, (label, text) in enumerate(spoken):
        clinician = _is_clinician(label)
        cluster = "SPEAKER_00" if clinician else "SPEAKER_01"
        char_start = cursor
        words: list[Word] = []
        offset = cursor

        for token in text.split(" "):
            if not token:
                continue
            duration = max(len(token) / (WORDS_PER_SECOND * 5), 0.12)
            words.append(Word(
                text=token,
                start=round(clock, 3),
                end=round(clock + duration, 3),
                probability=1.0,   # a script cannot mumble — see the docstring
                speaker_cluster=cluster,
                char_offset=offset,
                char_end=offset + len(token),
            ))
            clock += duration
            offset += len(token) + 1

        transcript_parts.append(text)
        cursor = char_start + len(text)
        turns.append(Turn(
            id=index,
            speaker_cluster=cluster,
            role="clinician" if clinician else "other",
            start=round(words[0].start, 3),
            end=round(words[-1].end, 3),
            words=words,
            text=text,
            char_start=char_start,
            char_end=cursor,
        ))
        cursor += 1          # the separator joined below
        clock += GAP_SECONDS

    session_dir = Path(session_dir)
    return Session(
        visit_date=visit_date or date.today(),
        session_dir=session_dir,
        # Named but never written: there is no audio. The review screen
        # already handles a missing file ("No audio attached"), and D8 says
        # playback is the clinician's tool, not the patient's.
        audio_path=session_dir / "script-only.wav",
        transcript_text=" ".join(transcript_parts),
        turns=turns,
        consent=consent or Consent(
            obtained=True, method="verbal", obtained_at=datetime.now()
        ),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("script", type=Path, help="a role-play script markdown file")
    ap.add_argument("--session-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, help="where to write the Session JSON")
    ap.add_argument("--visit-date", type=date.fromisoformat, default=None,
                    help="anchor for relative dates (D18); default today")
    args = ap.parse_args(argv)

    session = session_from_script(
        args.script.read_text(),
        session_dir=args.session_dir,
        visit_date=args.visit_date,
    )

    clinician = sum(1 for t in session.turns if t.role == "clinician")
    print(f"{args.script} -> {len(session.turns)} turns "
          f"({clinician} clinician, {len(session.turns) - clinician} other) · "
          f"{len(session.transcript_text)} chars · visit {session.visit_date}")
    print("  timings synthesised, probabilities all 1.0 — D16 category 2 "
          "cannot fire from a script")

    out = args.out or (args.session_dir / "session.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(session.model_dump_json(indent=1))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
