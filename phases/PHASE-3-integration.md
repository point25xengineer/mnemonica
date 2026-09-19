# Phase 3 — Integration

**Goal:** real audio through the whole chain, thresholds calibrated, all seven
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

**Done when:** one complete run produces a printable page.

## 3c — Tune thresholds · HUMAN · GATE

Two numbers need setting, and **you have no labeled data to tune them
against.** Don't pretend otherwise.

- **transcription confidence** — below what per-word `probability` does a dose
  numeral get flagged?
- **resolution margin** — how close can `resolve_medication`'s #2 candidate
  be before the result is `ambiguous` rather than `resolved`?

The asymmetry decides it: **over-flagging costs a click, under-flagging costs
a wrong dose.** Bias hard toward flagging, and say so as a deliberate choice.

If a judge asks how you validated them, *"we didn't, so we biased toward
asking the doctor"* is a much stronger answer than a fabricated figure.

**Done when:** both constants are set, committed, and someone can explain the
reasoning in one sentence.

## 3d — D16 sweep

Walk all seven categories using the planted fixture cases, now through the
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

Category 5 is the one most likely to regress into looking like a failure.
Check it specifically.

**Done when:** all seven behave as specified on real audio.

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
- [ ] thresholds set and defensible
- [ ] all seven D16 categories verified on real audio
- [ ] review timed, number recorded
- [ ] the printed page is something you'd hand to a relative
