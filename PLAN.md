# Build Hub

**This file is the single source of truth for build state.** Everyone syncs
here. If it isn't ticked here, it isn't done.

Architecture decisions live in [SPEC.md](SPEC.md) (**D1**–**D26**). Tool
contracts live in [TOOLS.md](TOOLS.md). Step-by-step detail lives in
[phases/](phases/). This file tracks *progress*, not design.

---

## Protocol — read this before editing

1. **Only edit your own track's section.** Four people editing one file
   conflicts constantly. Your section is yours; everything else is read-only
   to you.
2. **Tick the box the moment a step's acceptance criteria pass** — not when
   you think it'll pass, not at the end of a batch. Someone downstream is
   reading this to decide whether they can start.
3. **Append to the Log, never edit it.** Append-only merges cleanly; edits in
   place do not.
4. **Record gate results immediately.** Gate outcomes change *other people's*
   plans. A failed 0g rewrites Track B's whole approach.
5. **Pull before you push:** `git pull --rebase origin main`.
6. **If you deviate from SPEC.md, log it and say why.** Then update SPEC.md.
   Silent drift across eight files is how the architecture dies.

Status markers: `[ ]` not started · `[~]` in progress · `[x]` done ·
`[!]` blocked (add a line to Blockers)

---

## Status at a glance

| Track | Owner | Progress | State |
|---|---|---|---|
| Phase 0 — environment | | 0 / 8 | not started |
| Phase 1 — foundations | | 0 / 5 | not started |
| Track A — knowledge base | | 0 / 11 | **can start now** |
| Track B — audio | | 0 / 6 | waits on 0g, 0h, 1e |
| Track C — extraction | | 0 / 5 | waits on 1a, 1c |
| Track D — interface | | 0 / 9 | waits on 1a, 1c |
| Phase 3 — integration | | 0 / 5 | waits on all tracks |
| Phase 4 — demo | | 0 / 4 | waits on Phase 3 |

## Gate results — record immediately, others depend on these

| Gate | Question | Result | Decided by | Consequence |
|---|---|---|---|---|
| **0g** | pyannote imports + runs on Python 3.14? | — | | fail → Track B goes single-speaker, every dose blocking |
| **0h** | MPS turn boundaries match CPU? | — | | fail → CPU only, ~8 min per 15 min audio |
| **B5** | word offsets good enough for click-to-play? | — | | fail → check you're on large-v3, not turbo |
| **C3** | verbatim quote fidelity holding? | — | | fail → 8-bit 9B, then 35B MoE |
| **3c** | thresholds calibrated? | — | | no labeled data — bias toward flagging |

---

## Phase 0 — Environment · [phases/PHASE-0-environment.md](phases/PHASE-0-environment.md)

- [x] **0a** repo init, specs committed
- [ ] **0b** pip install the stack · CLOCK
- [ ] **0c** ffmpeg resolves
- [ ] **0d** openFDA downloaded, 14 parts / 1.77 GB · CLOCK
- [ ] **0e** `PYANNOTE_METRICS_ENABLED=false` in profile **and** in code
- [ ] **0f** diarization model loads (ungated mirror, no token)
- [ ] **0g** GATE — pyannote on Python 3.14
- [ ] **0h** GATE — MPS output matches CPU

## Phase 1 — Foundations · [phases/PHASE-1-foundations.md](phases/PHASE-1-foundations.md)

- [ ] **1a** HUMAN — data contract agreed, `contracts.py` committed
- [ ] **1b** repo skeleton committed
- [ ] **1c** HUMAN — golden fixture, all 7 D16 cases planted
- [ ] **1d** HUMAN — role-play script, drugs verified, 2 speakers
- [ ] **1e** HUMAN — clip + long visit + 10 s enrollment recorded

---

## Track A — Knowledge base + tools · [phases/PHASE-2A-knowledge-base.md](phases/PHASE-2A-knowledge-base.md)

*Owner:* ____  ·  *No ML dependencies. Nothing blocks this.*

- [ ] **A1** RXNCONSO → SQLite (watch the trailing pipe)
- [ ] **A2** RXNSAT `SPL_SET_ID` slice
- [ ] **A3** normalization + salt-stripped key
- [ ] **A4** indexes: exact, salt-stripped, Double Metaphone
- [ ] **A5** frequency prior from product counts
- [ ] **A6** `resolve_medication` + margin test
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
- [ ] **C2** xgrammar compile + logits processor
- [ ] **C3** GATE — turn-chunked prompt, verbatim fidelity on 9B
- [ ] **C4** span verification, offsets by `str.find`
- [ ] **C5** all 7 D16 dispositions fire on the fixture

## Track D — Review UI + output · [phases/PHASE-2D-interface.md](phases/PHASE-2D-interface.md)

*Owner:* ____  ·  *Needs 1a, 1c. Builds on the fixture, not on Track B.*

- [ ] **D1** localhost app shell
- [ ] **D2** review list — only blocking items demand attention
- [ ] **D3** click-a-line → audio playback (clinician only)
- [ ] **D4** blocking-item resolution, keyboard-only
- [ ] **D5** action card templates
- [ ] **D6** extractive summary — no generated prose
- [ ] **D7** print stylesheet, 18px+, clinician footer
- [ ] **D8** approve → shred audio, write FHIR, print
- [ ] **D9** 24 h expiry sweep for unapproved sessions

---

## Phase 3 — Integration · [phases/PHASE-3-integration.md](phases/PHASE-3-integration.md)

- [ ] **3a** swap fixture for real Track B output
- [ ] **3b** first end-to-end run
- [ ] **3c** HUMAN GATE — tune thresholds
- [ ] **3d** D16 sweep, all 7 categories on real audio
- [ ] **3e** time the review against the 60 s target → ____ s

## Phase 4 — Demo · [phases/PHASE-4-demo.md](phases/PHASE-4-demo.md)

- [ ] **4a** pre-compute the long file
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

Never in scope: live recording, interaction checking, mobile delivery,
3+ speakers.
