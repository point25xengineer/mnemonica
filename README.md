# Visit Notes

A local-first clinical documentation tool. It records a doctor–patient
consultation, extracts only what the clinician verifiably said, and prints a
plain-language summary after the clinician reviews and signs it.

> **The model is not allowed to write anything. It points at what the doctor
> said, and our code checks that they said it.**

Nothing leaves the device. No API calls, no telemetry.

---

## Running it

Everything uses the shared venv. Set this once per shell:

```bash
cd "/Users/evancanty/HackMIT 26 Project"
VP=/Users/evancanty/vn-shared/.venv/bin/python
```

### Record a real visit (live capture)

```bash
$VP -m visitnotes.ui.app
```

Open **http://127.0.0.1:8765** in a browser that can reach your microphone —
Chrome or Safari, not an embedded pane — and allow mic access when asked.

Consent, then two takes: a few seconds of the clinician's voice alone, then
the consultation. Stop, and the pipeline runs on this machine with a live
progress bar (~90 s for a four-minute visit). It lands on the review screen.

The voice sample is not a formality. pyannote returns anonymous clusters, and
matching them against an enrolled voiceprint is the only thing that tells the
system which speaker is the doctor — which is what D19's rule, that a dose may
only come from a clinician turn, stands on.

### See it working (fastest — no pipeline run, ~5 seconds)

```bash
$VP -m visitnotes.ui.app --session sessions/phase3/session.json --extraction sessions/phase3/extraction.json --audio "sessions/phase3/MedScribe test 1.m4a"
```

Then open **http://127.0.0.1:8765**. Passing `--session` skips capture and
goes straight to review — the demo fallback, and what to use if a microphone
is unavailable. Settle the blocking item, approve, and the patient's page
renders.

### Full run, from audio (~90 seconds)

Three stages. Each writes a file the next one reads — there is no single
orchestrator, on purpose: each stage is separately inspectable.

```bash
$VP -m visitnotes.audio.pipeline path/to/visit.m4a --session-dir sessions/mine --enrollment path/to/clinician.wav --out sessions/mine/session.json
```

```bash
$VP -m visitnotes.verify.run sessions/mine/session.json -o sessions/mine/extraction.json
```

```bash
$VP -m visitnotes.ui.app --session sessions/mine/session.json --extraction sessions/mine/extraction.json --audio path/to/visit.m4a
```

Roughly 22 s for stage 1, 69 s for stage 2 on an M5 Pro. Stage 2 is the LLM.

The `--enrollment` file is a 10-second sample of the clinician's voice. It is
how the system knows which speaker is the doctor, so **it must be the same
person who reads the doctor's lines** — a mismatched sample produces confident
wrong role assignment, which looks like a diarization bug and is not one.

### Tests

```bash
$VP -m pytest -q
```

241 tests, about two seconds. They cover logic only — no model inference — so
a green suite does **not** mean the pipeline works. Run the full chain above
for that.

### Other entry points

```bash
$VP -m visitnotes.ui.app --sweep          # delete unapproved sessions >24h old
$VP -m visitnotes.kb.build                # rebuild rxnorm.db from rrf/
$VP -m visitnotes.kb.openfda              # rebuild openfda_labels.db
$VP -m phase0.gate_0g_0h                  # re-run the pyannote / MPS gates
$VP -m phase0.offline_proof               # prove nothing reaches the network
```

---

## What to check by hand

A green suite and a rendered page are not the same thing. These have no
automated equivalent:

- **Listen to five citations.** Click lines in the review screen and confirm
  playback lands on the right words. Gate B5 is a structural pass only —
  nobody has done the listening half.
- **Read the printed page as a patient would.** Print it. Arm's length.
- **Time the review.** Target is 60 seconds, measured by someone who did not
  build the UI. Still unrecorded (3e).

Two defects were found this way, both with the suite green. See `fdf9269`.

---

## Documents

| File | What it is |
|---|---|
| [SPEC.md](SPEC.md) | The 27 architecture decisions (D1–D27), each with its reasoning and the alternatives rejected |
| [TOOLS.md](TOOLS.md) | Contracts for the three deterministic tools, and the drug resolution algorithm |
| [PLAN.md](PLAN.md) | The build hub — live status, gate results, blockers, log |
| [BRIEFING.md](BRIEFING.md) | Kickoff brief for anyone (or any agent) joining |
| [phases/](phases/) | Per-phase execution plans |
| [PRESENTATION-NOTES.md](PRESENTATION-NOTES.md) | What must be said on stage, and the five questions judges will ask |
| [fixtures/roleplay_script.md](fixtures/roleplay_script.md) | Script 1 — cardiac. The demo take; the fixture encodes it |
| [fixtures/roleplay_script_2.md](fixtures/roleplay_script_2.md) | Script 2 — endocrine. A fresh test case with an expectations table |

**If code and SPEC.md disagree, SPEC.md is right** — or the decision gets
changed there first, with its reasoning.

---

## Layout

```
visitnotes/
  contracts.py   Word / Turn / Session — the shared data contract
  audio/         Whisper + pyannote -> Session
  extract/       xgrammar-constrained extraction
  verify/        span verification, D16 dispositions
  kb/            RxNorm + openFDA
  tools/         resolve_medication, parse_sig, resolve_date
  render/        action card, summary, FHIR
  ui/            review screen, retention
```

## Requirements

Apple Silicon, macOS. Models and databases are cached locally and are not in
git: `data/rxnorm.db` (244 MB), `data/openfda_labels.db` (1.8 GB), plus
Whisper, pyannote and Qwen weights in `~/.cache/huggingface`. Rebuild the
databases with the commands above; the weights download on first use.
