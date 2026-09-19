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
| 4 | [SPEC.md](SPEC.md) | The 26 architecture decisions (D1–D26) with reasoning and rejected alternatives. §1–3 fully; §4–7 as needed |
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

**Build against `fixtures/golden_visit.json`**, not live audio, unless you are
Track B. That fixture is the reason three tracks can run in parallel.

**`git pull --rebase origin main` before you push.**

## 3. Non-negotiables

These are the product, not preferences.

- The model emits **verbatim quotes only** — never prose, and never character
  offsets. Our code finds offsets with `str.find`. A quote that isn't in the
  transcript is fabrication and gets dropped silently.
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

## 4. Your track

### Phase 0 — Environment
Gates **0g** and **0h** are the highest-risk unknowns in the project. Do them
before anything else and record the results in PLAN.md — Track B cannot start
until you do. Nobody has publicly reported pyannote 4.0.7 on Python 3.14, so
confirm it rather than assuming it.

### Phase 1 — Foundations
Step **1c**, the hand-written fixture, is the highest-leverage task in the
build. Without it, three people wait on one person's environment. Plant one
case per D16 category so it doubles as the test plan.

### Track A — Knowledge base + tools
Nothing blocks you — RxNorm is already unzipped on disk and you have no ML
dependencies. Start immediately. Do **not** skip the frequency prior (**A5**)
or the margin test (**A6**); both are the difference between a matcher that
looks fine and one that is dangerous. Watch the trailing-pipe gotcha in
**A1** — every RRF line ends with `|`.

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

### Track D — Review UI + output
The **60-second review budget** drives every layout decision. Only blocking
items should demand attention; everything verified stays collapsed. Two
audiences, one product: the clinician operates the screen, the patient
receives the paper — dense and keyboard-driven versus 18px and high-contrast.

---

## 5. First action

Read the five files in §1, then **state your plan for your first three steps
before writing any code.** Put your name in the Owner column of PLAN.md so
nobody duplicates your work.

When you finish a step, tick it in PLAN.md and add one Log line. When you are
blocked, mark the step `[!]` and add a row to the Blockers table saying what
you need and who can clear it.
