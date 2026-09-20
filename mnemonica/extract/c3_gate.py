"""GATE C3 — verbatim quote fidelity, measured on the real transcript.

    /Users/evancanty/vn-shared/.venv/bin/python -m mnemonica.extract.c3_gate
    ... --model mlx-community/Qwen3.6-35B-A3B-4bit
    ... --turns 8          a quick pass while iterating on the prompt

Extraction runs turn by turn over `golden_visit.json` and every string the
model emits is looked up in the transcript exactly as C4 will look it up. The
number that matters is the share that is found. A quote the model paraphrased
is not a near miss — it is indistinguishable from fabrication and C4 drops it,
so fidelity here *is* the recall of the whole system.

D24's escalation ladder, if 4-bit 9B will not hold the line:

1. **8-bit 9B first.** Quantization noise degrades verbatim copying harder
   than it degrades reasoning, so 8-bit 9B may beat 4-bit 27B at exact
   reproduction. Not cached — pull it the moment this gate asks for it.
2. `Qwen3.6-35B-A3B-4bit`, the MoE. Cached. Measured at 41 tok/s here, not
   the 65–85 D24 estimated, so time it rather than assuming it.
3. `Qwen3.8-27B-4bit` as a quality reference.

The wall clock this prints is also 3b's number, minus audio: model load plus
one constrained generation per turn is the machine's half of D9's budget, and
nothing else in the plan measures it.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import env_guard  # noqa: F401,E402

from mnemonica.contracts import Session  # noqa: E402
from mnemonica.extract.runner import DEV_MODEL, Extractor  # noqa: E402
from mnemonica.verify.spans import SpanVerifier  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "golden_visit.json"


def quotes_of(extraction) -> list[tuple[str, str]]:
    """Every string the model emitted, with the field it came from."""
    out: list[tuple[str, str]] = []
    for med in extraction.medications:
        out.append(("mention_quote", med.medication.mention_quote))
        if med.medication.context_quote:
            out.append(("context_quote", med.medication.context_quote))
        out += [("sig_quote", s.sig_quote) for s in med.sig]
        out.append(("change_evidence_quote", med.change_evidence_quote))
        if med.start_or_stop:
            out.append(("phrase_quote", med.start_or_stop.phrase_quote))
    for appt in extraction.appointments:
        out.append(("phrase_quote", appt.when.phrase_quote))
        out.append(("purpose_quote", appt.purpose_quote))
    out += [("instruction_quote", f.instruction_quote) for f in extraction.red_flags]
    out += [("topic_quote", t.topic_quote) for t in extraction.loose_threads]
    out += [("summary", s.quote) for s in extraction.summary_quotes]
    return out


def main(argv: list[str]) -> int:
    model = DEV_MODEL
    if "--model" in argv:
        model = argv[argv.index("--model") + 1]
    limit = int(argv[argv.index("--turns") + 1]) if "--turns" in argv else None

    session = Session.model_validate_json(FIXTURE.read_text())
    turns = session.turns[:limit] if limit else session.turns
    print(f"model {model} · {len(turns)} turns")

    ex = Extractor(model)
    verifier = SpanVerifier(session)
    found = missed = blank = 0
    by_field: Counter[str] = Counter()
    misses: list[tuple[int, str, str]] = []
    seconds = 0.0

    for turn in turns:
        result = ex.extract_turn(session, turn)
        seconds += result.seconds
        for field, quote in quotes_of(result.extraction):
            if not quote.strip():
                # An empty required field is the model declining to answer,
                # not inventing one. Counting it as a fidelity miss would
                # understate exact copying and overstate fabrication — two
                # different problems with two different fixes.
                blank += 1
                continue
            if verifier.verify(quote, kind=field, near=turn) is None:
                missed += 1
                by_field[field] += 1
                misses.append((turn.id, field, quote))
            else:
                found += 1
        print(f"  turn {turn.id:>3} {result.seconds:5.1f}s  "
              f"{'MALFORMED ' if result.malformed else ''}"
              f"{len(quotes_of(result.extraction)):>2} quotes")

    total = found + missed
    fidelity = found / total if total else 1.0
    print(f"\nverbatim fidelity  {fidelity:6.1%}   ({found}/{total} quotes found)")
    print(f"left blank         {blank:6}    required fields the model declined "
          f"to fill")
    print(f"wall clock         {seconds:6.1f}s   "
          f"({seconds / len(turns):.1f}s per turn, {ex.model_id})")
    if misses:
        print("\nquotes that are not in the transcript (C4 drops these):")
        for turn_id, field, quote in misses[:12]:
            print(f"  turn {turn_id:>3} {field:>22}  {quote!r}")
        print(f"  by field: {dict(by_field)}")

    Path("sessions").mkdir(exist_ok=True)
    Path("sessions/c3_gate.json").write_text(json.dumps({
        "model": ex.model_id, "turns": len(turns), "found": found,
        "missed": missed, "blank": blank, "fidelity": fidelity,
        "seconds": seconds,
        "misses": [{"turn": t, "field": f, "quote": q} for t, f, q in misses],
    }, indent=1))
    print("\nwritten: sessions/c3_gate.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
