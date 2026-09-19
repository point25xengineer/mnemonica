# Phase 1 — Foundations

**Goal:** the agreements and artifacts that let four people work at once
without colliding.

**Blocked by:** nothing (1a, 1b, 1c). **Blocks:** every track.

---

## 1a — Agree the data contract · HUMAN · ~15 min

The highest-value fifteen minutes of the build. If Track B and Track C are
written against different ideas of what a transcript *is*, you lose the
evening at hour 18.

Write it once, in `visitnotes/contracts.py`, and import it everywhere:

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

class Session(BaseModel):
    visit_date: date          # D18 — mtime read ONCE at ingest, then persisted
    audio_path: Path
    transcript_text: str      # what span verification searches (D14)
    turns: list[Turn]
```

Two things worth saying out loud when you agree it:

- `char_offset` is the bridge to D14. Offsets index into
  `Session.transcript_text`, which is the exact string
  `resolve_medication` and span verification search.
- `visit_date` is persisted, not recomputed. `cp` without `-p` resets mtime,
  and so does any re-encode — read it once at ingest and never again.

**Done when:** `contracts.py` exists, is committed, and all four owners have
read it.

## 1b — Repo skeleton · ~20 min

```
visitnotes/
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

## 1c — Author the golden fixture · HUMAN · ~45 min

**The unlock.** A hand-written `Session` JSON means Tracks C and D build and
test against realistic input before any audio exists — so a Phase 0 failure
idles one person instead of three.

Write it by hand: real turns, plausible timestamps, per-word probabilities
that vary. Mirror the 1d script exactly, so the fixture doubles as a
prediction of what the real pipeline should produce — that makes Track B's
correctness testable rather than a matter of opinion.

Plant one case per D16 category so the fixture is also the test plan:

| D16 | Plant |
|---|---|
| 2 low confidence | `probability` ≈ 0.4 on a dose numeral |
| 3 ambiguous attribution | a turn with `role="unknown"` containing a dose |
| 4 unresolved drug | "your blood pressure pill" |
| 5 not specified | "just take it as directed" |
| 6 loose thread | "we'll adjust your dose" — never revisited |
| 7 contradiction | two different doses for one drug, different timestamps |
| fuzzy match | `metropolol` — a plausible mistranscription |

**Done when:** `fixtures/golden_visit.json` validates against `Session`, and
every row above is present and findable.

## 1d — Write the role-play script · HUMAN · ~45 min

3–4 minutes of dialogue. **Two speakers only** (D19, and SPEC §6 — v1 pins
`num_speakers=2` and a third voice would be silently merged).

Before recording, check every drug name resolves against `RXNCONSO`. Nothing
is more annoying than finding at hour 20 that your hero drug is a suppressed
entry.

Write real disfluency in — overlaps, restarts, "um". A clean script makes
accuracy look fake-good and then collapses on stage.

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
- [ ] fixture validates and contains all seven D16 cases
- [ ] script committed, drugs verified, mirrors the fixture
- [ ] three recordings exist, including the enrollment sample
