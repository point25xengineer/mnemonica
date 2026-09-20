"""Track C end to end: a `Session` in, the post-C5 envelope out.

    python -m visitnotes.verify.run fixtures/golden_visit.json \
        -o sessions/demo/extraction.json

This is the seam 3a swaps: today it reads a `Session` from a file, and Track
B's output *is* a `Session`, so integration is a different path argument and
not a code change. If 3a turns into an afternoon, the contract was not specific
enough and `contracts.py` is what should change — not this call site.

`--no-grammar` runs D23's fallback deliberately, which is worth doing once
before you need it: the number to compare is fidelity, and it should barely
move. The grammar makes output parseable; span verification is what makes it
true.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import env_guard  # noqa: F401,E402

from visitnotes.contracts import Session  # noqa: E402
from visitnotes.extract.runner import DEV_MODEL, Extractor  # noqa: E402
from visitnotes.verify.pipeline import verify  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("session", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("extraction.json"))
    ap.add_argument("--model", default=DEV_MODEL)
    ap.add_argument("--no-grammar", action="store_true",
                    help="D23's post-hoc fallback, on purpose")
    args = ap.parse_args(argv)

    session = Session.model_validate_json(args.session.read_text())
    print(f"{args.session} · {len(session.turns)} turns · "
          f"visit {session.visit_date}")

    started = time.perf_counter()
    extractor = Extractor(args.model, use_grammar=not args.no_grammar)
    loaded = time.perf_counter()

    def tick(result, done, total):
        print(f"  {done:>3}/{total}  turn {result.turn_id:>3}  "
              f"{result.seconds:5.1f}s", end="\r", flush=True)

    run = extractor.extract(session, progress=tick)
    generated = time.perf_counter()

    result = verify(session, run.visit, logger=_log(session))
    done = time.perf_counter()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result.envelope, indent=1))

    header = result["header"]
    print(f"\n  model load     {loaded - started:6.1f}s")
    print(f"  extraction     {generated - loaded:6.1f}s  "
          f"({run.tokens_per_second:.0f} tok/s)")
    print(f"  verification   {done - generated:6.1f}s")
    print(f"  TOTAL          {done - started:6.1f}s   <- 3b's number")
    print(f"\n  {header['confirmed']} confirmed · {header['blocking']} blocking "
          f"· {header['needs_confirmation']} need confirmation · "
          f"{header['discarded']} discarded")
    print(f"  D16 categories fired: {sorted(result.categories)}")
    print(f"\nwritten: {args.out}")
    return 0


def _log(session: Session):
    """D16 category 1's log — and D2/D3's reason for `session_dir`.

    A dropped-quote line is transcript-adjacent PHI, so it goes inside the
    session directory that U9 shreds, never to stdout and never to a global
    log file."""
    path = session.session_dir / "dropped.log"

    def write(kind: str, reason: str, stage: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as fh:
                fh.write(f"{stage}\t{kind}\t{reason}\n")
        except OSError:
            pass  # a fixture's session_dir does not exist; the count still holds

    return write


if __name__ == "__main__":
    raise SystemExit(main())
