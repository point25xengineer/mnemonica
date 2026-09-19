# Agent kickoff brief

Copy the block below, replace `<<TRACK>>` with one of **Phase 0**, **Phase 1**,
**Track A**, **Track B**, **Track C**, **Track D**, and paste it as the agent's
first message.

---

```
You are working on Visit Notes, a local-first clinical documentation tool
for HackMIT 2026. It records a doctor–patient consultation, extracts only
what the clinician verifiably said, and prints a plain-language summary
after the clinician reviews and signs it.

The thesis, which every design decision protects:
  The model is not allowed to write anything. It points at what the doctor
  said, and our code checks that they said it.

YOUR ASSIGNMENT: <<TRACK>>

READ THESE FIRST, IN THIS ORDER:
  1. PLAN.md                 - the build hub. Current state, who owns what,
                               gate results, and the protocol for updating it.
  2. phases/README.md        - index of phase plans.
  3. Your own phase file in phases/ - your steps, acceptance criteria,
                               failure modes, and done-when checklist.
  4. SPEC.md                 - the 26 architecture decisions (D1-D26) with
                               reasoning and rejected alternatives. Read §1-3
                               fully; §4-7 as needed.
  5. TOOLS.md                - if you touch extraction or the three
                               deterministic tools, read this fully.

GROUND RULES:

- SPEC.md wins. If your phase file contradicts it, SPEC.md is right. If you
  need to deviate, log it in PLAN.md under "Deviations" with the reason, then
  update SPEC.md. Do not let the architecture drift silently.

- Stay in your own directory. Track A owns kb/ and tools/, Track B owns
  audio/, Track C owns extract/ and verify/, Track D owns render/ and ui/.
  contracts.py is shared and changes to it need agreement first.

- Update PLAN.md as you go. Tick your box the moment a step's acceptance
  criteria pass, not at the end of a batch - someone downstream is reading it
  to decide whether they can start. Only edit your own section. Append to the
  Log, never edit it. Record gate results immediately; they change other
  people's plans.

- Build against fixtures/golden_visit.json, not against live audio, unless
  you are Track B. That fixture is why three tracks can run in parallel.

- git pull --rebase origin main before you push.

NON-NEGOTIABLES - these are the product, not preferences:

- The model emits verbatim quotes only, never prose, and never character
  offsets. Our code finds offsets with str.find. A quote that isn't in the
  transcript is fabrication and gets dropped silently.

- Never "helpfully" correct a drug name, expand an abbreviation, or normalize
  a quote before passing it to a tool. Verbatim is the entire verification
  mechanism.

- "I couldn't hear it" and "your doctor never said it" must never look the
  same in any output. They are different facts.

- Nothing unverified ever reaches the printed page.

- Nothing leaves the device. No API calls, no telemetry, no analytics. If you
  add a dependency, check it doesn't phone home.

When you finish a step, tick it in PLAN.md and add one Log line. When you are
blocked, mark the step [!] and add a row to the Blockers table saying what you
need and who can clear it.

Start by reading the five files above, then tell me your plan for your first
three steps before writing code.
```

---

## Per-track one-liners

If you want to add a line of specific context, use these:

| Track | Add |
|---|---|
| **Phase 0** | "Gates 0g and 0h are the highest-risk unknowns in the project. Do them before anything else and record the results — Track B cannot start until you do." |
| **Phase 1** | "Step 1c, the hand-written fixture, is the highest-leverage task in the build. Without it three people wait on one person's environment." |
| **Track A** | "Nothing blocks you — RxNorm is already unzipped on disk and you have no ML dependencies. Do not skip the frequency prior (A5) or the margin test (A6); both are the difference between a matcher that looks fine and one that's dangerous." |
| **Track B** | "Do not use Whisper turbo. Its 4 decoder layers wreck word-boundary precision and the whole product rests on word offsets. If gate 0g failed, read the single-speaker fallback section at the bottom of your phase file — that's the plan, not a surprise." |
| **Track C** | "mlx-lm has no built-in constrained decoding; xgrammar is what makes the schema guarantee real. Do not route this through Ollama — its MLX engine has silently ignored schema constraints." |
| **Track D** | "The 60-second review budget drives every layout decision. Only blocking items should demand attention; everything verified stays collapsed. Two audiences: the clinician operates the screen, the patient receives the paper." |
