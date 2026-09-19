# Phase 3 — Integration

**Goal:** real audio through the whole chain, thresholds calibrated, all eight
D16 categories verified end to end.

**Blocked by:** all four tracks.

---

## 3a — Swap the fixture for real output

If contract 1a held, this is a one-line change: Tracks C and D stop reading
`fixtures/golden_visit.json` and start reading Track B's `Session`.

**That one line is the entire return on the fixture decision.** If it turns
into an afternoon, 1a wasn't specific enough — fix `contracts.py`, not the
call sites.

**Done when:** C and D run on real audio with no other edits.

## 3b — First end-to-end run

Short clip → transcript → turns → extraction → verification → tools → review
→ approve → print.

Expect the first run to fail somewhere unglamorous: a path, an encoding, an
off-by-one in `char_offset`. Budget for it.

**Stopwatch the whole pipeline while you are here.** D9's 60 seconds is the
*clinician's* time; nothing has ever budgeted the machine's. The live run is
model loads + Whisper + diarization + **one constrained generation per turn**
across 40–60 turns — plausibly four to six minutes, against a demo slot that is
usually three to five. You need the real number now, not at 4b.

If it does not fit: start the run under the intro slide. That is honest, and it
is not the same as pre-computing.

**Done when:** one complete run produces a printable page, and the end-to-end
wall clock is written into PLAN.md.

## 3c — Tune thresholds · HUMAN · GATE

Two numbers need setting, and **you have no labeled data to tune them
against.** Don't pretend otherwise.

- **transcription confidence** — below what per-word `probability` does a dose
  numeral get flagged? Also set the segment-level cut: `compression_ratio`
  above ~2.4 is the standard Whisper hallucination heuristic
- **resolution margin** — how close can `resolve_medication`'s #2 candidate
  be before the result is `ambiguous` rather than `resolved`?

Sanity-check the margin against A3.5: if it fires constantly, confirm the
dose-bearing `SY`/`TMSY` rows were actually filtered out of the index. A
flooded index looks exactly like a badly tuned threshold.

The asymmetry decides it: **over-flagging costs a click, under-flagging costs
a wrong dose.** Bias hard toward flagging, and say so as a deliberate choice.

If a judge asks how you validated them, *"we didn't, so we biased toward
asking the doctor"* is a much stronger answer than a fabricated figure.

**Done when:** both constants are set, committed, and someone can explain the
reasoning in one sentence.

## 3d — D16 sweep

Walk all eight categories using the planted fixture cases, now through the
real pipeline:

| # | Expect |
|---|---|
| 1 | fabricated quote dropped silently, logged |
| 2 | low-confidence dose prefilled + flagged, audio auto-cued |
| 3 | ambiguous attribution on a dose → **blocking** |
| 4 | unresolved drug prefilled with raw text + near-matches |
| 5 | "as directed" → *not specified*, **not** an error |
| 6 | loose thread in its own section |
| 7 | contradiction → **blocking**, both values with timestamps |
| 8 | cross-turn association flagged and rendered **expanded** |

Also verify, though they are not D16 rows:

| | Expect |
|---|---|
| salt | bare "metoprolol" → `resolved` + `salt_unspecified`, both salts offered |
| silence | a stretch of silence produces no words, no quotable spans |
| consent | recording cannot start without it; it prints on the page |

Category 5 is the one most likely to regress into looking like a failure.
Check it specifically. Category 8 is the one most likely to be *absent* rather
than wrong — confirm it actually fires, since a check that never fires looks
identical to a clean run.

**Done when:** all eight behave as specified on real audio.

## 3e — Time the review

Stopwatch the flow against D9's 60-second target. Have someone who didn't
build the UI do it.

If it's over: the fix is almost always that too much non-blocking content is
demanding attention. Collapse more.

**Done when:** a first-time user signs a correct note in under 60 seconds, and
you know the actual number to quote.

---

## Phase 3 is done when

- [ ] real audio runs end to end
- [ ] end-to-end wall clock measured and recorded
- [ ] thresholds set and defensible
- [ ] all eight D16 categories verified on real audio
- [ ] review timed, number recorded
- [ ] the printed page is something you'd hand to a relative
