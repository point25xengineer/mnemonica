# Implementation Plan

Ordering and parallelism only. Rationale lives in [SPEC.md](SPEC.md) (**D1**–**D26**)
and [TOOLS.md](TOOLS.md). **HUMAN** = needs a person. **GATE** = stop and verify.
**CLOCK** = start it and walk away.

---

## The one structural idea

**Author a golden fixture by hand (1c), first.**

A hand-written `Session` JSON decouples everything downstream of diarization
from the ML pipeline. Tracks C and D build against it and never wait on Track B.
Without it, three people wait on one person's environment.

Track A needs nothing from anyone and can start now.

---

## Phase 0 — Unblock

0a–0e run simultaneously.

| # | Step | |
|---|---|---|
| 0a | `git init`, commit specs | before openFDA lands |
| 0b | `pip install` the stack | **CLOCK** |
| 0c | ffmpeg (`imageio-ffmpeg`) | hard dep for Whisper + pyannote |
| 0d | openFDA, 14 parts / 1.77 GB | **CLOCK** — only A8 needs it |
| 0e | `PYANNOTE_METRICS_ENABLED=false` | D4 |
| 0f | Diarization model access | **HUMAN**, or skip it — use the ungated mirror |
| **0g** | **pyannote imports + runs on Python 3.14** | **GATE** |
| **0h** | **MPS output matches CPU** | **GATE** |

---

## Phase 1 — Foundations

| # | Step | |
|---|---|---|
| 1a | Agree `Word` / `Turn` / `Session` contract | **HUMAN** ~15 min |
| 1b | Repo skeleton | ~20 min |
| 1c | Author golden fixture | **HUMAN** ~45 min |
| 1d | Write role-play script — 3–4 min, **two speakers** | **HUMAN** |
| 1e | Record clip, long visit, + 10s voice enrollment | **HUMAN** |

**1a contract** — everything downstream consumes `list[Turn]`:

```python
Word:    text, start, end, probability, speaker_cluster, char_offset
Turn:    id, speaker_cluster, role, start, end, words, text
Session: visit_date, audio_path, transcript_text, turns
```

**1c** must plant one case per D16 category — it doubles as the test plan.
**1d** must mirror 1c, so Track B's correctness is testable rather than debatable.

---

## Phase 2 — Four parallel tracks

No cross-track dependencies until Phase 3.

### Track A — KB + tools · zero ML deps, start immediately

| # | Step | Deps |
|---|---|---|
| A1 | `RXNCONSO` -> SQLite (trailing-pipe gotcha) | — |
| A2 | `RXNSAT` `SPL_SET_ID` slice | A1 |
| A3 | Normalization + salt-stripped key | A1 |
| A4 | Indexes: exact, salt-stripped, Double Metaphone | A3 |
| A5 | Frequency prior (product counts) | A1 |
| A6 | `resolve_medication` + margin test | A4, A5 |
| A7 | Brand -> ingredient via `SBD` brackets | A1 |
| A8 | openFDA -> SQLite FTS5 | 0d, A2 |
| A9 | `parse_sig` grammar | — |
| A10 | `resolve_date` | — |
| A11 | Cross-validation | A6, A9 |

A9 and A10 are pure functions — a third person owns them from minute one.

### Track B — Audio · after GATE 0g

| # | Step | Deps |
|---|---|---|
| B1 | Whisper -> `Word` records (`large-v3-mlx`, **not turbo**) | 0b, 0c |
| B2 | pyannote diarize, `exclusive_speaker_diarization` | 0g |
| B3 | Enrollment match -> `role` | B2, 1e |
| B4 | Word -> turn assignment, `char_offset` | B1, B2 |
| B5 | Emit `Session`, persist `visit_date` | B4 |
| B6 | Cluster-distance sanity check | B3 |

**GATE B5:** diff against fixture 1c; word offsets usable for click-to-play.

### Track C — Extraction + verification · against fixture

| # | Step | Deps |
|---|---|---|
| C1 | Pydantic schemas (TOOLS.md §4) | 1a |
| C2 | xgrammar compile + logits processor | C1, 0b |
| C3 | Turn-chunked extraction prompt | C2 |
| C4 | Span verification + offsets by `str.find` | C1, 1c |
| C5 | D16 disposition assignment | C4, A6, A9, A10 |

**GATE C3:** develop on `Qwen3.5-9B-4bit`; if quotes come back paraphrased,
escalate to 8-bit 9B, then the 35B MoE.

### Track D — UI + output · against fixture

| # | Step | Deps |
|---|---|---|
| D1 | localhost app shell | 1a |
| D2 | Review list — only blocking items demand attention | D1, 1c |
| D3 | Click-a-line -> audio playback | D2 |
| D4 | Blocking-item resolution, keyboard-only | D2 |
| D5 | Action card templates | 1c |
| D6 | Extractive summary | 1c |
| D7 | Print stylesheet + clinician footer | D5, D6 |
| D8 | Approve -> shred audio, write FHIR | D4, D7 |
| D9 | 24h expiry sweep | D8 |

---

## Phase 3 — Integration

| # | Step |
|---|---|
| 3a | Swap fixture for real Track B output (one line, if 1a held) |
| 3b | First end-to-end run |
| 3c | Tune confidence + margin thresholds — **HUMAN GATE**, bias toward flagging |
| 3d | Verify all seven D16 categories via the planted cases |
| 3e | Time the review against the 60-second target |

## Phase 4 — Demo

| # | Step |
|---|---|
| 4a | Pre-compute the long file |
| 4b | **Wi-Fi off, full run** |
| 4c | Rehearse — **HUMAN** |
| 4d | Re-confirm every script drug resolves |

---

## Human-input index

| Step | What |
|---|---|
| 0f | Model access — avoidable via the ungated mirror |
| 1a | Agree the data contract |
| 1c | Author the fixture |
| 1d | Write the script |
| 1e | Cast, record, enroll |
| 3c | Tune thresholds |
| 4c | Rehearse |

## Gate index

| Gate | If it fails |
|---|---|
| 0g | Single-speaker mode, all doses blocking. Do **not** install Python 3.13 |
| 0h | CPU diarization — budget ~8 min per 15 min audio |
| B5 | Confirm you are not on Whisper turbo |
| C3 | 8-bit 9B, then the 35B MoE |
| 3c | Bias toward flagging |

## Cut list

Agree now, cut from the bottom.

| | |
|---|---|
| 1 | Clip -> transcript -> `parse_sig` -> action card with click-to-play |
| 2 | `resolve_medication` fuzzy match |
| 3 | D16 disposition table |
| 4 | `resolve_date` |
| 5 | Diarization + enrollment |
| 6 | Extractive summary (keep the action card) |
| 7 | openFDA grounding + `geriatric_use` |
| 8 | Cross-validation vs available strengths |
| 9 | FHIR `DocumentReference` |
| 10 | Pre-computed long file |

Never in scope: live recording, interaction checking, mobile, 3+ speakers.
