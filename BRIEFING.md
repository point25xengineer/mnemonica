# Start here

You are working on **Visit Notes**, a local-first clinical documentation tool
for HackMIT 2026. It records a doctor–patient consultation, extracts only what
the clinician verifiably said, and prints a plain-language summary after the
clinician reviews and signs it.

The thesis, which every design decision protects:

> **The model is not allowed to write anything. It points at what the doctor
> said, and our code checks that they said it.**

You were told which track you own when you were started — **Phase 0**,
**Phase 1**, **Track A**, **Track B**, **Track C** or **Track D**. Find yours
in §4 below. If you weren't told, stop and ask before doing anything.

---

## 1. Read these first, in this order

| | File | Why |
|---|---|---|
| 1 | [PLAN.md](PLAN.md) | The build hub — current state, ownership, gate results, and the protocol for updating it |
| 2 | [phases/README.md](phases/README.md) | Index of phase plans |
| 3 | your own file in [phases/](phases/) | Your steps, acceptance criteria, failure modes, done-when checklist |
| 4 | [SPEC.md](SPEC.md) | The 27 architecture decisions (D1–D27) with reasoning and rejected alternatives. §1–3 fully; §4–7 as needed |
| 5 | [TOOLS.md](TOOLS.md) | Read fully if you touch extraction or the three deterministic tools |

## 2. Ground rules

**SPEC.md wins.** If your phase file contradicts it, SPEC.md is right. If you
need to deviate, log it in PLAN.md under *Deviations* with the reason, then
update SPEC.md. Do not let the architecture drift silently across eight files.

**Stay in your own directory.** Track A owns `kb/` and `tools/`. Track B owns
`audio/`. Track C owns `extract/` and `verify/`. Track D owns `render/` and
`ui/`. `contracts.py` is shared — changes to it need agreement first.

**Update PLAN.md as you go.** Tick your box the moment a step's acceptance
criteria pass, not at the end of a batch — someone downstream is reading it to
decide whether they can start. Only edit your own section. Append to the Log,
never edit it. Record gate results immediately; they change other people's
plans.

**Build against the fixtures**, not live audio, unless you are Track B. They
are the reason three tracks can run in parallel.

- `fixtures/golden_visit.json` — a `Session`: turns, words, offsets. Track C.
- `fixtures/golden_extraction.json` — dispositioned items, post-C5. **Track D.**
  A `Session` has no extracted items in it, so Track D cannot render a review
  list from `golden_visit.json` alone.

**`git pull --rebase origin main` before you push.**

## 3. Non-negotiables

These are the product, not preferences.

- The model emits **verbatim quotes only** — never prose, and never character
  offsets. Our code finds offsets with `str.find`. A quote that isn't in the
  transcript is fabrication: the item is **dropped, and the drop is counted**.
  The clinician never sees the fabricated text, but the header does show
  *"… · 1 discarded"* — because a silently deleted medication is
  indistinguishable from one we never found, and an omission is invisible in a
  60-second review.
- **A verified span is not a correct extraction.** `str.find` proves the doctor
  said the words; it does not prove they were attached to the right drug. The
  model can take a real *"twice daily"* from drug A's turn and nest it under
  drug B — every quote passes. That is D16 **category 8**, caught by comparing
  turn offsets (TOOLS §5 step 4), and it is the residual risk in the whole
  design. Do not describe span verification as proving correctness.
- **Never "helpfully" correct** a drug name, expand an abbreviation, or
  normalize a quote before passing it to a tool. Verbatim is the entire
  verification mechanism. If the transcript says `metropolol`, that is the
  argument — `resolve_medication` handles it and reports the correction.
- **"I couldn't hear it" and "your doctor never said it" must never look the
  same** in any output. They are different facts.
- **Nothing unverified reaches the printed page.** Either the clinician
  resolved it or it isn't there.
- **Nothing leaves the device.** No API calls, no telemetry, no analytics. If
  you add a dependency, check that it doesn't phone home — one already did.
- **Logs are PHI too.** A dropped-quote log line contains transcript text. The
  retention policy (D2/D3) covers logs, ffmpeg scratch files and tracebacks,
  not just the `.wav` — write against a session *directory*. `.gitignore`
  already excludes `logs/`, `*.log`, `*.jsonl`; keep it that way.
- **The patient consents before recording** (**D27**). `Session.consent` is
  required, and the printed page says so.

## 4. Your track

### Phase 0 — Environment
Gates **0g** and **0h** are the highest-risk unknowns in the project. Do them
before anything else and record the results in PLAN.md — Track B cannot start
until you do. Nobody has publicly reported pyannote 4.0.7 on Python 3.14, so
confirm it rather than assuming it.

### Phase 1 — Foundations
Step **1c**, the hand-written fixtures, is the highest-leverage task in the
build. Without them, three people wait on one person's environment. Plant one
case per D16 category — **eight now, not seven** — so they double as the test
plan.

**Write both files.** `golden_visit.json` (a `Session`) unblocks Track C;
`golden_extraction.json` (dispositioned items) unblocks Track D. Shipping only
the first leaves Track D blocked on Track C, which is the exact problem 1c
exists to solve.

For **1d**, check your follow-up dates against a calendar: every whole number
of weeks from the hackathon's Saturday lands on a weekend, and *"come back in
three weeks"* printing a Saturday appointment is a bad look on a medical
document. Pin `visit_date` to a weekday or pick a non-multiple-of-seven
interval.

### Track A — Knowledge base + tools
Nothing blocks you — RxNorm is already unzipped on disk and you have no ML
dependencies. Start immediately. Do **not** skip the frequency prior (**A5**)
or the margin test (**A6**); both are the difference between a matcher that
looks fine and one that is dangerous. Watch the trailing-pipe gotcha in
**A1** — every RRF line ends with `|`.

**Build the index right the first time — A3.5 before A4.** These numbers were
measured off this exact RxNorm release, not assumed (SPEC §7, TOOLS §1):

- `SY` is **89.8%** dose-bearing product strings and `TMSY` is **66.4%**. A
  real `SY` row is `metoprolol succinate 100 MG 24 HR Extended Release Oral
  Capsule`. Indexing them unfiltered puts 31,895 dose-bearing strings into the
  index whose purpose is keeping dose *out* of name matching — and
  Jaro-Winkler weights prefix agreement, so they all score high and flood the
  margin test. Filter `SY`/`TMSY` only; `IN`/`BN`/`PIN` go in whole.
- **`PIN` was missing from both indexes, and it is where salt forms live.**
  `metoprolol` is `IN` 6918; `metoprolol succinate` is `PIN` 221124 and
  `metoprolol tartrate` is `PIN` 203191. Without `PIN`, *"metoprolol"* hit the
  bare `IN` on the exact lookup and returned `resolved` / `match_type="exact"`
  — a confident, silent answer that hides the difference between once-daily ER
  and twice-daily IR. **A5.5** precomputes the 32 ingredients where this
  matters.

Net: the name index is **18,094** strings, not 48,046 and not 246,241.

### Track B — Audio
**Do not use Whisper turbo.** Its 4 decoder layers wreck word-boundary
precision, and the entire product rests on word offsets — use
`whisper-large-v3-mlx`. If gate **0g** failed, read the single-speaker
fallback at the bottom of your phase file; that is the plan, not a surprise.
Assert that `char_offset` indexes into the same string span verification
searches, or every citation silently breaks.

### Track C — Extraction + verification
`mlx-lm` has **no** built-in constrained decoding — xgrammar is what makes the
schema guarantee real. Do **not** route this through Ollama; its MLX engine
has a documented history of silently ignoring schema constraints, which is
exactly the failure this architecture exists to prevent.

**Do C2 in your first hour.** `compile_json_schema(VisitExtraction,
strict_mode=True)` on the real nested schema, before the prompt, the fixture or
the model. It is the only assumption in the build that can kill a whole track,
it needs nothing else to test, and the cp314 wheel is days old. If it fails:
post-hoc `json.loads` + one retry. You lose well-formedness, not truth — span
verification is what makes the output true (SPEC D23).

**C4.5 is yours and it is new.** Compare the turn each `*_quote` resolved to.
When a `sig` or date came from a different turn than its drug mention, that is
**D16 category 8** — the failure span verification structurally cannot see,
because every quote in it is genuine.

### Track D — Review UI + output
The **60-second review budget** drives every layout decision. Only blocking
items should demand attention; everything verified stays collapsed. Two
audiences, one product: the clinician operates the screen, the patient
receives the paper — dense and keyboard-driven versus 18px and high-contrast.

Your steps are **U1–U10**, not D1–D9 — `D` numbers are SPEC decisions, and the
old numbering made *"D8 — approve: shred the audio (D2)"* mean two documents at
once.

Four things the 60-second budget must **not** collapse away:

- **U2 — consent before recording** (D27), and a line about it on the printed
  page. Fifteen minutes, and it closes the largest gap in the spec.
- **U3 — the discarded count in the header.** *"14 confirmed · 2 need your
  ear · 1 discarded."* Collapsing everything means the clinician attests to
  content they did not read; the count is what keeps an omission visible.
- **D16 category 8 renders expanded**, with both quotes and both timestamps.
  Everything else verified may collapse; this may not.
- **U6 — `change_kind` is never printed as fact unless the pipeline derived
  it** from two parsed doses. It is the verb of the headline sentence
  (*"**increased** your metoprolol"*) and otherwise the model picked it.

---

## 5. First action

Read the five files in §1, then **state your plan for your first three steps
before writing any code.** Put your name in the Owner column of PLAN.md so
nobody duplicates your work.

When you finish a step, tick it in PLAN.md and add one Log line. When you are
blocked, mark the step `[!]` and add a row to the Blockers table saying what
you need and who can clear it.
