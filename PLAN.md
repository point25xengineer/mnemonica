# Build Hub

**This file is the single source of truth for build state.** Everyone syncs
here. If it isn't ticked here, it isn't done.

Architecture decisions live in [SPEC.md](SPEC.md) (**D1**–**D27**). Tool
contracts live in [TOOLS.md](TOOLS.md). Step-by-step detail lives in
[phases/](phases/). This file tracks *progress*, not design.

---

## Protocol — read this before editing

1. **Check your blockers before you start, and re-check before each step.**
   This file is the source of truth for *whether you can begin*, not just for
   recording that you did. Your phase file's header names what blocks you;
   confirm every one of those boxes is `[x]` and every gate you depend on
   reads `pass` or `fail` — not `—`. Starting behind an unanswered gate is how
   a track builds an afternoon of work on an assumption that was never true.
2. **Only edit your own track's section.** Four people editing one file
   conflicts constantly. Your section is yours; everything else is read-only
   to you.
3. **Tick the box the moment a step's acceptance criteria pass** — not when
   you think it'll pass, not at the end of a batch. Someone downstream is
   reading this to decide whether they can start.
4. **Append to the Log, never edit it.** Append-only merges cleanly; edits in
   place do not.
5. **Record gate results immediately.** Gate outcomes change *other people's*
   plans. A failed 0g rewrites Track B's whole approach.
6. **Pull before you read, not just before you push.** `git pull --rebase
   origin main` at the start of every step. Pulling only when you are ready to
   write means working an hour against stale state — including a gate that
   failed while you were building on it passing.
7. **If a gate you depend on comes back `fail`, stop and re-read your phase
   file.** Every gate has a documented degraded mode; it is the plan, not a
   surprise. Do not keep going on the assumption it will be fixed.
8. **If you are blocked, park properly.** Mark the step `[!]`, add a Blockers
   row saying what you need and who can clear it, and then do the next step in
   your track that is *not* blocked. Do not idle, and do not work around a
   blocker by guessing at what the upstream step will produce.
9. **If you deviate from SPEC.md, log it and say why.** Then update SPEC.md.
   Silent drift across eight files is how the architecture dies.

Status markers: `[ ]` not started · `[~]` in progress · `[x]` done ·
`[!]` blocked (add a line to Blockers)

---

## Status at a glance

| Track | Owner | Progress | State |
|---|---|---|---|
| Phase 0 — environment | | 0 / 8 | not started |
| Phase 1 — foundations | Evan + agent | 2 / 6 | in progress |
| Track A — knowledge base | | 0 / 13 | **can start now** |
| Track B — audio | | 0 / 6 | waits on 0g, 0h, 1e |
| Track C — extraction | | 0 / 6 | waits on 1a, 1c |
| Track D — interface | | 0 / 10 | waits on 1a, **1c-ii** |
| Phase 3 — integration | | 0 / 5 | waits on all tracks |
| Phase 4 — demo | | 0 / 4 | waits on Phase 3 |

## Gate results — record immediately, others depend on these

**`—` means not answered, and not answered means do not proceed.** If your
track waits on a gate, its row must say `pass` or `fail` before you start the
steps behind it. A blank is not "probably fine"; it is "nobody has checked."

| Gate | Question | Result | Decided by | Consequence |
|---|---|---|---|---|
| **0g** | pyannote imports + runs on Python 3.14? | — | | fail → Track B goes single-speaker, every dose blocking |
| **0h** | MPS turn boundaries match CPU? | — | | fail → CPU only, ~8 min per 15 min audio |
| **B5** | word offsets good enough for click-to-play? | — | | fail → check you're on large-v3, not turbo |
| **C2** | does `compile_json_schema(VisitExtraction)` compile at all? | — | | fail → post-hoc parse + retry; span verification still holds |
| **C3** | verbatim quote fidelity holding? | — | | fail → 8-bit 9B, then 35B MoE |
| **3c** | thresholds calibrated? | — | | no labeled data — bias toward flagging |

---

## Phase 0 — Environment · [phases/PHASE-0-environment.md](phases/PHASE-0-environment.md)

- [x] **0a** repo init, specs committed
- [ ] **0b** pip install the stack · CLOCK
- [ ] **0c** ffmpeg resolves
- [ ] **0d** openFDA downloaded, 14 parts / 1.77 GB · CLOCK
- [ ] **0e** `PYANNOTE_METRICS_ENABLED=false` in profile **and** in code *(set it above the pyannote import — it is read at import time)*, plus `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` once weights are cached
- [ ] **0f** diarization model loads (ungated mirror, no token)
- [ ] **0g** GATE — pyannote on Python 3.14
- [ ] **0h** GATE — MPS output matches CPU

## Phase 1 — Foundations · [phases/PHASE-1-foundations.md](phases/PHASE-1-foundations.md)

- [x] **1a** HUMAN — data contract agreed, `contracts.py` committed
- [x] **1b** repo skeleton committed
- [ ] **1c-i** HUMAN — `fixtures/golden_visit.json` (`Session`), all **8** D16 cases planted
- [ ] **1c-ii** HUMAN — `fixtures/golden_extraction.json` (dispositioned items) — **Track D is blocked without this**; a `Session` has no items to render
- [ ] **1d** HUMAN — role-play script, drugs verified, 2 speakers
- [ ] **1e** HUMAN — clip + long visit + 10 s enrollment recorded

---

## Track A — Knowledge base + tools · [phases/PHASE-2A-knowledge-base.md](phases/PHASE-2A-knowledge-base.md)

*Owner:* ____  ·  *No ML dependencies. Nothing blocks this.*

- [ ] **A1** RXNCONSO → SQLite (watch the trailing pipe)
- [ ] **A2** RXNSAT `SPL_SET_ID` slice
- [ ] **A3** normalization + salt-stripped key
- [ ] **A3.5** filter `SY`/`TMSY` by dose pattern, add `PIN` → **18,094-string** name index *(do this BEFORE A4 — see SPEC §7)*
- [ ] **A4** indexes: exact, salt-stripped, Double Metaphone
- [ ] **A5** frequency prior from product counts
- [ ] **A5.5** salt table — the **32** `IN` concepts with 2+ `PIN` children
- [ ] **A6** `resolve_medication` + margin test + `salt_unspecified`
- [ ] **A7** brand → ingredient via SBD brackets
- [ ] **A8** openFDA → SQLite FTS5 *(needs 0d)*
- [ ] **A9** `parse_sig` — `not_specified` ≠ `unparseable`
- [ ] **A10** `resolve_date` — anchor injected, past direction works
- [ ] **A11** cross-validation vs available strengths

## Track B — Audio · [phases/PHASE-2B-audio.md](phases/PHASE-2B-audio.md)

*Owner:* ____  ·  *Needs 0g, 0h, 1e.*

- [ ] **B1** Whisper large-v3-mlx → `Word[]` (**not turbo**)
- [ ] **B2** pyannote, `exclusive_speaker_diarization`
- [ ] **B3** enrollment match → `role`, manual override
- [ ] **B4** word → turn assignment, `char_offset` assertion passes
- [ ] **B5** GATE — emit `Session`, diff against fixture
- [ ] **B6** unexpected-speaker cluster-distance check

## Track C — Extraction + verification · [phases/PHASE-2C-extraction.md](phases/PHASE-2C-extraction.md)

*Owner:* ____  ·  *Needs 1a, 1c. Builds on the fixture, not on Track B.*

- [ ] **C1** schemas — no free-text field anywhere
- [ ] **C2** GATE — xgrammar compiles the real `VisitExtraction`, + logits processor
- [ ] **C3** GATE — turn-chunked prompt, verbatim fidelity on 9B
- [ ] **C4** span verification, offsets by `str.find`
- [ ] **C4.5** association check — mention turn vs sig/date turn (**D16 cat 8**)
- [ ] **C5** all **8** D16 dispositions fire on the fixture

## Track D — Review UI + output · [phases/PHASE-2D-interface.md](phases/PHASE-2D-interface.md)

*Owner:* ____  ·  *Needs 1a, 1c. Builds on the fixture, not on Track B.*

Steps are **U**1–U10. `D1`–`D27` are SPEC decision IDs; this track used to
number its steps D1–D9 too, which made *"D8 — approve: shred the audio (D2)"*
mean two different documents in one sentence.

- [ ] **U1** localhost app shell
- [ ] **U2** consent capture at session start (**D27**) — required before recording
- [ ] **U3** review list — only blocking items demand attention; header shows the **discarded count** (D16 cat 1)
- [ ] **U4** click-a-line → audio playback (clinician only)
- [ ] **U5** blocking-item resolution, keyboard-only
- [ ] **U6** action card templates — `change_kind` never printed as fact unless derived
- [ ] **U7** extractive summary — no generated prose
- [ ] **U8** print stylesheet, 18px+, clinician footer **+ consent line**
- [ ] **U9** approve → shred audio **and logs**, write FHIR, print
- [ ] **U10** 24 h expiry sweep — **exempt pre-computed demo sessions (4a)**

---

## Phase 3 — Integration · [phases/PHASE-3-integration.md](phases/PHASE-3-integration.md)

- [ ] **3a** swap fixture for real Track B output
- [ ] **3b** first end-to-end run — **stopwatch the whole pipeline**, not just the review → ____ s
- [ ] **3c** HUMAN GATE — tune thresholds
- [ ] **3d** D16 sweep, all **8** categories on real audio
- [ ] **3e** time the review against the 60 s target → ____ s

## Phase 4 — Demo · [phases/PHASE-4-demo.md](phases/PHASE-4-demo.md)

- [ ] **4a** pre-compute the long file — **and exempt it from U10's sweep**, or it deletes itself before the demo
- [ ] **4b** Wi-Fi off, full run, no outbound attempts
- [ ] **4c** HUMAN — rehearse the five judge questions
- [ ] **4d** re-verify every script drug against the final build

---

## Blockers — live

*Anything marked `[!]` goes here with what you need to get unstuck. Delete the
line when it clears.*

| Step | Blocked on | Who can clear it | Raised |
|---|---|---|---|
| — | — | — | — |

## Deviations from SPEC.md

*Log any departure from a D-number decision, with the reason. Then update
SPEC.md — this table is the record, not the decision.*

| Decision | What we did instead | Why | Who |
|---|---|---|---|
| — | — | — | — |

---

## Log — append only, newest at the bottom

Format: `HH:MM · <step> · <what happened>`

```
21:55 · 0a · repo pushed to github.com/point25xengineer/visit-notes (private)
18:25 · spec · review pass landed. SPEC/TOOLS/phases corrected against the
        actual RxNorm release. Headlines: name index was 67% dose-bearing
        product strings (A3.5); PIN was unindexed so metoprolol succinate vs
        tartrate resolved silently to the bare ingredient (A5.5); D16 gained
        category 8 (cross-turn association); D27 added (patient consent);
        Track D steps renamed U1-U10. Nothing was deleted — see git diff.
18:55 · 1b · skeleton committed: visitnotes/{audio,tools,kb,extract,verify,
        render,ui}, fixtures/, tests/, all with __init__.py.
18:55 · 1a · contracts.py committed and merged to main — rebase before your
        next commit. Three additions beyond the PHASE-1 sketch, all agreed:
        (1) Turn.char_start/char_end + Session.turn_at_offset(), so C4.5 can
        ask "which turn did this quote come from" without scanning words —
        D16 cat 8 is the residual risk and should not rest on a hand-rolled
        loop. (2) Word.text excludes whitespace and the offset contract is
        exact: transcript_text[off:off+len(text)] == text, validated for
        every word on construction. mlx-whisper emits " metoprolol" with a
        leading space; unspecified, B strips it and C does not and every
        citation is off by one silently. This validator IS B4's assertion,
        and it runs when golden_visit.json loads. (3) Consent rejects
        obtained=False (D27).
18:55 · 1a · Session gained session_dir, and audio_path is validated to live
        inside it. D2/D3 retention covers logs, ffmpeg scratch and tracebacks
        — all PHI. audio_path alone invites unlink(audio_path) at U9, which
        shreds the .wav and leaves the log beside it. U9's owner: shred the
        directory. 13 tests in tests/test_contracts.py cover all of it.
```

---

## Cut list — agreed in advance, cut from the bottom

| | |
|---|---|
| 1 | Clip → transcript → `parse_sig` → action card with click-to-play |
| 2 | `resolve_medication` fuzzy match |
| 3 | D16 disposition table |
| 4 | `resolve_date` |
| 5 | Diarization + enrollment |
| 6 | Extractive summary (keep the card) |
| 7 | openFDA grounding + `geriatric_use` |
| 8 | Cross-validation vs available strengths |
| 9 | FHIR `DocumentReference` |
| 10 | Pre-computed long file |

**Cutting 5 removes a safety property, not a feature.** Without diarization
there is no clinician attribution, so D19's rule — a dose may only be extracted
from a clinician turn — has nothing to stand on, and the companion's *"should I
take four?"* can print as fact. If you cut it, adopt gate 0g's degraded mode in
the same breath: **every dose becomes a D16 category 3 blocking item**, and say
so on stage.

Never in scope: live recording, interaction checking, mobile delivery,
3+ speakers.
