"""GATE C2 — does xgrammar compile the real schema, and is EMPTY reachable?

    /Users/evancanty/vn-shared/.venv/bin/python -m visitnotes.extract.c2_gate
    ... --live          also generate against a no-content turn (loads 6 GB)

Two questions, and the second is the one that is easy to forget.

1. **Does `compile_json_schema(VisitExtraction, strict_mode=True)` compile?**
   It is the only assumption in the build that can kill an entire track, it
   needs nothing else to answer, and `VisitExtraction` is nested Pydantic so it
   emits `$defs`/`$ref` — the case `strict_mode` is particular about.

2. **Can a no-content turn produce all-empty lists?** A grammar that cannot
   express "nothing here" forces a constrained decoder to invent an item to
   satisfy it — the grammar would then be *causing* fabrication, which is an
   exquisite way to lose. Most turns in a real visit contain nothing.

Question 2 is answered twice: by walking the empty JSON document through a
`GrammarMatcher` token by token (no model, always run), and, with `--live`, by
actually generating on a turn that contains nothing.

Fail → post-hoc `json.loads` + one reparse retry (`Extractor(use_grammar=
False)`). We lose D13's first guarantee, well-formedness, and keep the second.
Span verification is what makes the output true; the grammar only makes it
parseable. Record the result in PLAN.md either way.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import env_guard  # noqa: F401,E402  — before transformers

from visitnotes.contracts import Session  # noqa: E402
from visitnotes.extract.grammar import GrammarCache  # noqa: E402
from visitnotes.extract.runner import DEV_MODEL  # noqa: E402
from visitnotes.extract.schema import TurnExtraction, VisitExtraction  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "golden_visit.json"

EMPTY = json.dumps({
    "medications": [], "appointments": [], "red_flags": [],
    "loose_threads": [], "summary_quotes": [],
})


def main(argv: list[str]) -> int:
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(DEV_MODEL)
    cache = GrammarCache(tok)
    ok = True

    for schema in (VisitExtraction, TurnExtraction):
        try:
            cache.compile(schema)
            print(f"  ok    compile_json_schema({schema.__name__}, strict_mode=True)")
        except Exception as e:  # noqa: BLE001 — the failure IS the gate result
            ok = False
            print(f"  FAIL  compile {schema.__name__} — {e}")

    if not ok:
        print("\nGATE C2: FAIL — fall back to Extractor(use_grammar=False)")
        return 1

    # -- is an empty extraction reachable? --------------------------------
    import xgrammar as xgr

    matcher = xgr.GrammarMatcher(cache.compile(TurnExtraction))
    for tid in tok.encode(EMPTY, add_special_tokens=False):
        if not matcher.accept_token(int(tid)):
            ok = False
            print(f"  FAIL  grammar rejects the empty extraction at token {tid!r}")
            break
    else:
        print(f"  ok    empty extraction accepted token by token — {EMPTY}")

    if "--live" in argv:
        ok = _live(cache) and ok

    print(f"\nGATE C2: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def _live(cache) -> bool:
    """Generate on a turn that genuinely contains nothing extractable."""
    from visitnotes.extract.runner import Extractor

    session = Session.model_validate_json(FIXTURE.read_text())
    ex = Extractor(DEV_MODEL)
    # The shortest, emptiest turn in the fixture — greetings, not medicine.
    turn = min(session.turns, key=lambda t: len(t.text))
    result = ex.extract_turn(session, turn)
    empty = result.extraction == TurnExtraction()
    print(f"  {'ok   ' if empty else 'FAIL '} live no-content turn {turn.id} "
          f"({turn.text!r}) -> {result.raw.strip()[:120]} "
          f"[{result.seconds:.1f}s]")
    return empty


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
