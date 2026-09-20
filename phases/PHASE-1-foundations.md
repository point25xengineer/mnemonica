# Phase 1 — Foundations

**Goal:** the agreements and artifacts that let four people work at once
without colliding.

**Blocked by:** nothing (1a, 1b, 1c). **Blocks:** every track.

---

## 1a — Agree the data contract · HUMAN · ~15 min

The highest-value fifteen minutes of the build. If Track B and Track C are
written against different ideas of what a transcript *is*, you lose the
evening at hour 18.

Write it once, in `mnemonica/contracts.py`, and import it everywhere:

```python
class Word(BaseModel):
    text: str
    start: float              # seconds
    end: float
    probability: float        # mlx-whisper WordTiming.probability
    speaker_cluster: str      # "SPEAKER_00"
    char_offset: int          # index into Session.transcript_text

class Turn(BaseModel):
    id: int
    speaker_cluster: str
    role: Literal["clinician", "other", "unknown"]
    start: float
    end: float
    words: list[Word]
    text: str

class Consent(BaseModel):
    """D27 — required. A session cannot reach review without it."""
    obtained: bool
    method: Literal["verbal", "written"]
    obtained_at: datetime

class Session(BaseModel):
    visit_date: date          # D18 — mtime read ONCE at ingest, then persisted
    audio_path: Path
    transcript_text: str      # what span verification searches (D14)
    turns: list[Turn]
    consent: Consent          # D27 — required, captured BEFORE recording
```

Two things worth saying out loud when you agree it:

- `char_offset` is the bridge to D14. Offsets index into
  `Session.transcript_text`, which is the exact string
  `resolve_medication` and span verification search.
- `visit_date` is persisted, not recomputed. `cp` without `-p` resets mtime,
  and so does any re-encode — read it once at ingest and never again.
- `consent` is **required now, even though nothing populates it today**.
  Adding a required field to `Session` at hour 14 means touching four people's
  call sites, which is the hour-18 failure this meeting exists to prevent.

**Done when:** `contracts.py` exists, is committed, and all four owners have
read it.

## 1b — Repo skeleton · ~20 min

```
mnemonica/
  contracts.py      # 1a
  schemas.py        # C1
  audio/            # Track B
  tools/            # Track A
  kb/               # Track A
  extract/          # Track C
  verify/           # Track C
  render/           # Track D
  ui/               # Track D
fixtures/
  golden_visit.json # 1c
tests/
```

Directory boundaries are ownership boundaries. Four people, four top-level
areas, minimal merge conflicts.

**Done when:** the tree exists with `__init__.py` files and is committed.

## 1c — Author the golden fixtures · HUMAN · ~60 min

**The unlock.** Hand-written JSON means Tracks C and D build and test against
realistic input before any audio exists — so a Phase 0 failure idles one person
instead of three.

**Two files, and the second one is not optional.**

| File | Shape | Unblocks |
|---|---|---|
| **1c-i** `fixtures/golden_visit.json` | `Session` — turns, words, offsets | Track C |
| **1c-ii** `fixtures/golden_extraction.json` | dispositioned items, as C5 would emit them | **Track D** |

A `Session` contains turns and words. It contains no extracted items and no
dispositions — so Track D, whose first real screen is a *review list*, cannot
render anything from 1c-i alone and ends up blocked on Track C. That is the
exact dependency this step exists to break, just moved one person over. Write
both.

Write it by hand: real turns, plausible timestamps, per-word probabilities
that vary. Mirror the 1d script exactly, so the fixture doubles as a
prediction of what the real pipeline should produce — that makes Track B's
correctness testable rather than a matter of opinion.

Plant one case per D16 category so the fixture is also the test plan:

| D16 | Plant |
|---|---|
| 1 fabrication | (not plantable in the fixture — C4 provokes it with a fake quote) |
| 2 low confidence | `probability` ≈ 0.4 on a dose numeral |
| 3 ambiguous attribution | a turn with `role="unknown"` containing a dose |
| 4 unresolved drug | "your blood pressure pill" |
| 5 not specified | "just take it as directed" |
| 6 loose thread | "we'll adjust your dose" — never revisited |
| 7 contradiction | two different doses for one drug, different timestamps |
| **8 cross-turn association** | **a drug named in one turn, its sig stated several turns later with another drug mentioned in between** |
| fuzzy match | `metropolol` — a plausible mistranscription |
| **salt unspecified** | **bare "metoprolol", no salt named — A5.5's flag** |

Category 8 is the one to plant carefully: two drugs in play, and a `"twice
daily"` that *could* plausibly attach to either. That is the failure span
verification cannot see, so the fixture is the only place it gets tested.

**Done when:** `golden_visit.json` validates against `Session`,
`golden_extraction.json` carries a dispositioned item for every row above, and
every row is present and findable.

## 1d — Write the role-play script · HUMAN · ~45 min

3–4 minutes of dialogue. **Two speakers only** (D19, and SPEC §6 — v1 pins
`num_speakers=2` and a third voice would be silently merged).

Before recording, check every drug name resolves against `RXNCONSO`. Nothing
is more annoying than finding at hour 20 that your hero drug is a suppressed
entry.

Write real disfluency in — overlaps, restarts, "um". A clean script makes
accuracy look fake-good and then collapses on stage.

**Check your follow-up dates against a calendar before recording.** Sept 19–20,
2026 are Saturday and Sunday, and *any* whole number of weeks from a Saturday
is a Saturday — so "come back in two weeks" and "in three weeks" both print a
weekend appointment on a medical document. Either pin the session's
`visit_date` to a weekday or write a non-multiple-of-seven interval into the
script.

**Done when:** the script is committed, every drug is verified, and it matches
the fixture turn for turn.

## 1e — Record · HUMAN · ~30 min

Three recordings:

1. the **short clip** (3–4 min) — run live in the demo
2. a **longer visit** — pre-computed, shown as evidence of scale
3. the **10-second clinician enrollment sample** — easy to forget, and D20
   does not work without it

Do **not** record a real appointment. No BAA exists anywhere in this stack;
role-play means you never create PHI, which is item 3 of PRESENTATION-NOTES.

**Done when:** three audio files exist, gitignored, and the enrollment sample
is clean single-speaker audio.

---

## Phase 1 is done when

- [ ] `contracts.py` committed and read by all four owners
- [ ] skeleton committed
- [ ] `golden_visit.json` validates and contains all eight D16 cases
- [ ] `golden_extraction.json` exists — **Track D is blocked without it**
- [ ] script committed, drugs verified, mirrors the fixture
- [ ] three recordings exist, including the enrollment sample
