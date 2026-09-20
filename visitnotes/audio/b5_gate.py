"""B5's gate evidence — diff a real `Session` against golden fixture 1c.

    python -m visitnotes.audio.b5_gate sessions/b5/session.json

The fixture's *words* come from the same mlx-whisper run this pipeline
reproduces, but its **turn segmentation and speaker roles are hand-authored**
— deliberately, because a fixture built from pyannote's own output cannot test
pyannote. So this is not an equality check. Word-level agreement should be
near-total; turn boundaries are where diarization is actually on trial, and a
disagreement there is a finding, not a failure.

What this cannot tell you is whether the word *offsets* are accurate enough
for click-to-play (U4). That is B5's judgment call and it needs ears: play
five random citations and listen. If they are sloppy, check you are on
`large-v3-mlx` and not turbo.
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from visitnotes.contracts import Session  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "golden_visit.json"


def compare(real: Session, golden: Session) -> int:
    print(f"{'':22} {'real':>12} {'fixture':>12}")
    rows = [
        ("turns", len(real.turns), len(golden.turns)),
        ("words", sum(len(t.words) for t in real.turns), sum(len(t.words) for t in golden.turns)),
        ("transcript chars", len(real.transcript_text), len(golden.transcript_text)),
        ("clinician turns", len(real.clinician_turns()), len(golden.clinician_turns())),
    ]
    for label, a, b in rows:
        mark = " " if a == b else "*"
        print(f"{mark} {label:20} {a:>12} {b:>12}")
    print(f"  visit_date           {str(real.visit_date):>12} {str(golden.visit_date):>12}")

    print("\n--- transcript_text ---")
    r, g = real.transcript_text, golden.transcript_text
    if r == g:
        print("identical — every fixture quote resolves against the real transcript")
    else:
        sm = difflib.SequenceMatcher(None, g, r, autojunk=False)
        print(f"similarity {sm.ratio():.4f}")
        shown = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal" or shown >= 20:
                continue
            print(f"  {tag:7} fixture {g[i1:i2]!r:40} real {r[j1:j2]!r}")
            shown += 1

    print("\n--- turn boundaries (this is what diarization is on trial for) ---")
    real_bounds = [(t.speaker_cluster, t.text) for t in real.turns]
    gold_bounds = [(t.speaker_cluster, t.text) for t in golden.turns]
    mismatches = 0
    for i, (a, b) in enumerate(zip(real_bounds, gold_bounds)):
        if a[1] != b[1]:
            mismatches += 1
            if mismatches <= 8:
                print(f"  turn {i}:")
                print(f"    fixture [{b[0]}] {b[1][:90]}")
                print(f"    real    [{a[0]}] {a[1][:90]}")
    if not mismatches:
        print("every turn's text matches the fixture, turn for turn")
    else:
        print(f"{mismatches}/{min(len(real_bounds), len(gold_bounds))} turns differ")

    print("\n--- every fixture quote, re-located in the real transcript (D14) ---")
    extraction = json.loads((FIXTURE.parent / "golden_extraction.json").read_text())
    quotes = _quotes(extraction)
    bad = 0
    for q in quotes:
        text, off = q["text"], q.get("char_offset")
        # `str.find` is literally what span verification does (C4). If a
        # fixture quote cannot be found in the transcript Track B just built,
        # the two strings have drifted and every citation is wrong.
        if r.find(text) < 0:
            print(f"  NOT FOUND {text!r}")
            bad += 1
            continue
        # Stronger: the fixture's own offset must still land on it. This is
        # the check that would catch a one-character join difference, which
        # `find` alone would survive.
        if off is not None and r[off : off + len(text)] != text:
            print(f"  OFFSET DRIFT {text!r} @ {off} -> {r[off:off + len(text)]!r}")
            bad += 1
            continue
        turn = real.turn_at_offset(off) if off is not None else None
        if turn is not None and q.get("turn_id") is not None and turn.id != q["turn_id"]:
            # C4.5 answers "which turn did this come from" through exactly this
            # lookup, and D16 category 8 is decided by the answer.
            print(f"  TURN DRIFT {text!r}: fixture turn {q['turn_id']}, real turn {turn.id}")
            bad += 1
    print(f"{len(quotes) - bad}/{len(quotes)} quotes resolve at the fixture's own offset")

    return bad + mismatches


def _quotes(node) -> list[dict]:
    """Every quote object under the extraction fixture, at any depth.

    A quote is any dict carrying both `text` and `char_offset` — the shape
    `golden_extraction.json` uses for `mention_quote`, `sig[].quote` and the
    rest. Matching on shape rather than on key names means a new quote field
    in C5's output is checked automatically instead of silently skipped.
    """
    out: list[dict] = []
    if isinstance(node, dict):
        if isinstance(node.get("text"), str) and "char_offset" in node:
            out.append(node)
        else:
            for v in node.values():
                out += _quotes(v)
    elif isinstance(node, list):
        for v in node:
            out += _quotes(v)
    return out


def main(argv: list[str]) -> int:
    real = Session.model_validate_json(Path(argv[1]).read_text())
    golden = Session.model_validate_json(FIXTURE.read_text())
    return 0 if compare(real, golden) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
