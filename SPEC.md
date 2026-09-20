# Mnemonica — Design Specification

**HackMIT 2026 · Healthcare track · Sept 19–20, 2026**

A local-first clinical documentation tool. It records a doctor–patient
consultation, extracts the medically actionable content, presents it to the
clinician for a sub-minute review, and on approval prints a plain-language
summary for the patient.

Every decision below was argued before it was made. Rejected alternatives are
recorded with the reason, so nobody re-opens a settled question without new
information.

---

## 1. Thesis

The model is not allowed to write anything.

It points at what the doctor said, and our code checks that they said it.

That sentence is literally true of this system, with no asterisk, and
everything in this spec exists to keep it true:

- The LLM emits **structured fields containing verbatim quotes**, never prose.
- A **grammar** makes malformed output mechanically impossible.
- **Our code**, not the model, verifies each quote occurs in the transcript.
- **Deterministic tools** — not the model — normalize drugs, parse dosages and
  resolve dates.
- A **licensed clinician** approves before any patient ever sees a word.

We are not trying to win an argument with AI skeptics. We are trying to build
something a skeptical clinician would actually use in an exam room. The
argument takes care of itself.

---

## 2. Pipeline

```
  microphone / audio file
            |
            v
  [1] mlx-whisper large-v3        -> transcript + per-word timestamps
            |                        + per-word probability
            v
  [2] pyannote community-1        -> exclusive speaker diarization
            |                        (2 clusters)
            v
  [3] voice enrollment match      -> which cluster is the clinician
            |
            v
  [4] turn-chunked extraction     -> xgrammar-constrained JSON
      (MLX LLM)                      { field, verbatim_quote }
            |
            v
  [5] verification layer          -> quote found in transcript? offsets by
            |                        search. not found -> DROP (fabrication)
            v
  [6] deterministic tools         -> RxNorm resolve / sig parse / date anchor
            |
            v
  [7] clinician review UI         -> <= 60s. blocking items resolved.
            |                        click any line to hear the audio
            v  (approve)
  [8] render + print              -> medicines table (templated) +
            |                        visit summary (extractive quotes)
            v
  [9] shred audio                 -> immediately on approval
```

Stages run **sequentially**, not concurrently. The pipeline is inherently
ordered and parallel execution only creates memory contention on the GPU.

---

## 3. Decisions

### 3.1 Privacy and deployment

**D1 — Fully local. No cloud transcription.** *(Q1b)*

Nothing leaves the device: no audio, no transcript, no note. We do not use
ElevenLabs, despite it being a HackMIT sponsor, and we accept the cost.

- *Rejected — cloud STT with an honest boundary:* the sensitive artifact is
  the raw audio, so shipping exactly that to a third party while calling the
  product private is the contradiction a skeptic would find first.
- *Rejected — hybrid toggle:* a consent screen is a good demo beat but it
  concedes the claim.
- **Cost incurred:** we lose ElevenLabs' diarization, medical-tuned ASR, and
  `keyterms` priming. D9 covers the replacement.
- **Note:** ElevenLabs has no prize track at HackMIT 2026, so this costs no
  points. Self-hosted ElevenLabs (VPC / on-prem) is enterprise + NDA gated and
  was never reachable. `scribe_v2_medical` is HIPAA-eligible only with an
  Enterprise BAA and Zero Retention Mode — unavailable to us, which means we
  could not lawfully have put real PHI through it anyway.

**D2 — Audio is deleted the instant the clinician approves.** *(Q19a)*

**D3 — Unapproved sessions expire after 24 hours**, audio and extracted data
both. *(Q23a)*

Together D2 and D3 make the retention policy statable in one sentence with no
exceptions: *audio exists until the doctor signs, or 24 hours, whichever comes
first. There is no third case.* An unreviewed visit note is clinically stale
within a day, so nothing of value is lost.

- *Rejected — 7 or 30 day windows:* holding medical audio on a laptop to serve
  a hypothetical future dispute is a liability we would have to defend, and
  retention windows are a hospital policy question, not ours to invent.
- Delete the structured extraction too, not just the recording. A list of
  someone's medications is PHI without the audio.
- **Every derived artifact is in scope, not just the two obvious ones.** D16
  category 1 logs each dropped quote, and that log line contains transcript
  text. So do ffmpeg scratch files, crash tracebacks carrying transcript
  context, and any `.jsonl` debug trace. The one-sentence claim survives
  exactly one question about logs. Write the sweep against a **session
  directory**, not against two file paths, so there is nothing to forget.

**D4 — Dependency telemetry is disabled.** Non-negotiable.

pyannote.audio 4.0.7 ships `metrics_enabled: true` and exports OpenTelemetry
spans — including audio duration and speaker counts — to
`https://otel.pyannote.ai/v1/traces`. For a product claiming nothing leaves
the device, this is a credibility kill shot.

    export PYANNOTE_METRICS_ENABLED=false

**Order matters.** pyannote reads this at import time. `os.environ[...]` set
*after* `import pyannote.audio` does nothing — which is the failure mode where
you believe telemetry is off and it is not. Put it in the shell profile, and in
code only at the very top of the entry point, above every pyannote import.

Run the demo with Wi-Fi off. It is the cheapest possible proof of the claim.

**D5 — Voice embeddings are biometric data. Both of them.** Stored locally,
never transmitted.

The clinician's enrolled embedding is the obvious one, and it belongs to the
clinician, not the patient. But `speaker_embeddings` carries a vector for
**every** cluster — B3 has to embed the patient's voice in order to compare
clusters against the enrollment at all, and B6's distance check reads the same
array. So the pipeline does compute a patient voiceprint, transiently.

**Rule: non-clinician embeddings are never persisted, never logged, and never
leave the function that computes the distances.** `Session` has no field for
them. Say this precisely if privacy comes up — "the embedding belongs to the
clinician" is not quite true, and knowing the difference between *local* and
*harmless* is the point being made.

**D27 — The patient consents to the recording, and the artifact proves it.**

Numbered last because it was found last, in review. It belongs here.

Nothing in the pipeline turned on a microphone with the patient's knowledge.
That is a hole in a product whose entire claim is about handling someone's
most sensitive data carefully, and it is the first question a healthcare-track
judge asks after the privacy one.

- `Session.consent` is captured **at session start**, before recording, and is
  a required field — a session cannot reach review without it.
- The printed footer already names the attesting clinician (D10). It also
  states that the patient was informed: *"Recorded with your knowledge and
  consent."*
- **Massachusetts is an all-party-consent jurisdiction**, and its wiretap
  statute is criminal rather than civil. We are demoing in Cambridge. Our
  own audio is teammate role-play (§8) so the demo is clean, but the *product*
  was specified without a consent step and that is the thing being fixed.

- *Rejected — implicit consent from the visit itself:* consent to be treated
  is not consent to be recorded, and the distinction is exactly the one a
  patient would care about.
- *Rejected — a consent checkbox with no artifact:* if it does not appear on
  the patient's copy, it is a UI affordance rather than a record.

This is roughly fifteen minutes of work and it closes the largest gap in the
spec. Do not defer it.

### 3.2 Product shape

**D6 — The clinician is the user. The patient is the audience.** *(Q12c)*

The clinician records, reviews, approves, and prints. The patient receives
paper plus an identical digital copy. This is the strongest available trust
architecture and it is how human medical scribes have always worked: the tool
drafts, a licensed professional attests, the signature is the clinical act.

**D7 — Two output artifacts, both derived, neither LLM-authored.** *(Q3a+b, Q10a+c)*

| Artifact | Content | Rendering |
|---|---|---|
| **Action card** | medications, dosages, appointments, tests, red-flag instructions | **templated** — fixed skeletons with extracted values slotted in. Medications render as a **table** (medicine / what changed / how to take it); `medication_row` is a second reader over the same item as `medication_sentences`, so the two shapes cannot disagree about a dose |
| **Visit summary** | *Purpose of visit* (symptom, then finding) and *What your doctor advised* (medicines, warnings, next visit, leftover advice) | **extractive** — selected verbatim spans, joined into one short paragraph per part by template connectives only |

- *Rejected — abstractive summary:* the moment one section is model-authored,
  the thesis in §1 needs a footnote, and that section is what a skeptic will
  find. Verbatim quotes read slightly rough; the roughness is an asset,
  because it looks like evidence rather than content.

**D8 — Audio playback is a clinician review tool only.** *(Q16a, Collision 1)*

The patient's copy carries no audio affordance. Provenance is how the doctor
verifies in seconds; the paper then carries the doctor's authority, not the
model's confidence.

- *Rejected — QR codes per line on the handout:* a feature for judges, not for
  a 78-year-old.
- Consequence: D2's deletion is harmless. Provenance is needed at approval
  time and never again.

**D9 — Review must complete in under 60 seconds.** *(Q18)*

Real visits run 15–20 minutes. A five-minute approval step means nobody ever
uses this. This constrains the UI hard: only blocking items demand attention,
resolution is keyboard-only, verified content stays collapsed. State the
60-second target out loud — committing to a number signals we thought about
the exam room, not just the model.

**D10 — The printed page carries a one-line footer naming the clinician.** *(Q25b)*

> *Prepared from a recording of your visit and reviewed by Dr. ——, Sept 19, 2026.*

- *Rejected — prominent AI disclosure:* a loud "AI GENERATED" banner
  manufactures the exact distrust we are dissolving, and misrepresents the
  system, since a doctor has attested to every line by the time it prints.
- *Rejected — no disclosure:* faintly evasive, and invites the question anyway.
- Naming the responsible human is stronger than naming the model.

**D11 — Liability sits with the attesting clinician.** Have this memorized.

Not a novel arrangement: it is precisely how human scribes and dictation
services have worked for decades. The tool produces a draft, a licensed
professional reviews and signs. Because the model never speaks to the patient
unattended, there is no path by which its error reaches a patient without a
doctor having looked at it.

### 3.3 Anti-hallucination architecture

**D12 — Span-locked extraction plus template rendering.** *(Q5a+c)*

The LLM emits only structured fields, each carrying a verbatim transcript
quote. Patient-visible prose comes from templates (D7). The model extracted
and routed; it authored nothing.

**The honest asterisk, stated here rather than discovered by a judge.** Three
values in the schema are model-decided and *cannot* be span-verified, because
they are classifications rather than quotes:

| Value | Risk |
|---|---|
| `change_kind` | it is the **verb** of the headline sentence — *"Dr. — **increased** your metoprolol"* |
| `event_kind` | miscategorizes a date rather than inventing one; already a closed enum with an `other` escape |
| the **association itself** | which `sig` nests under which `medication` — see D16 category 8 |

`change_kind` is the sharp one. Mitigation, in order of preference:

1. **Derive it.** When two doses for one drug are parsed and both resolve,
   `increased`/`decreased` is arithmetic, not a judgement. Compute it.
2. When it cannot be derived, `change_kind` is **never printed as fact** — it
   is prefilled and flagged, and the clinician's click is what promotes it.

A closed enum keeps the thesis in §1 literally true — the model still authored
no prose — but "it only picked from a list" is not a safety argument when the
list is {increased, decreased}.

**D13 — Two independent guarantees, neither doing the other's job.**

| Layer | Guarantees | Mechanism |
|---|---|---|
| **xgrammar** | output is well-formed and schema-conformant | grammar-constrained decoding — mechanically impossible to violate |
| **our code** | the quote actually occurs in the transcript | string search over the real transcript |

A grammar cannot know whether a quote is real. That stays ours.

**D14 — The model does NOT emit character offsets. Our code computes them.**

Models cannot see character positions; asking for offsets is asking for
arithmetic on boundaries absent from their representation. They get it wrong
constantly, and correct extractions then fail our own verifier.

The model emits the quote string only. We search the transcript:

- **exactly one match** -> deterministic offsets, accepted
- **zero matches** -> fabrication, dropped silently (see D16 category 1)
- **multiple matches** -> disambiguate by nearest turn

This makes the guarantee *stronger*, not weaker: offsets are computed by
`str.find`, not asserted by a model.

**D15 — Extraction is chunked by speaker turn, not by token window.**

Diarization already gives natural boundaries. Per-turn extraction means less
drift on long input, attribution for free from the chunk's speaker label, and
a failed extraction isolated to one turn instead of poisoning a batch. It also
makes transcript length irrelevant — a 4-minute clip and a 20-minute visit
present the same size input to the model.

**D16 — Uncertainty disposition table.** *(Q11)*

Eight distinct failure modes. The critical rule: **"I could not hear it" and
"your doctor never said it" must never look the same.** Conflating them builds
a system that blames itself for the doctor's omissions, or the doctor for its
own.

| # | Failure mode | Disposition |
|---|---|---|
| 1 | **Span verification failed** — quote not in transcript | **Dropped**, logged, **and counted**. This is fabrication; the correct response is deletion. The *count* is shown (see below). |
| 2 | Low transcription confidence — per-word `probability`, **or** segment-level `no_speech_prob` / `compression_ratio` | Prefilled + flagged, audio auto-cued to that word |
| 3 | Attribution ambiguous | **Blocking** for dose/frequency; flagged otherwise |
| 4 | Drug unresolved against RxNorm | Prefilled with raw heard text + flagged, offering near-matches |
| 5 | No dose spoken ("take as directed") | Explicit "not specified" — **not an error** |
| 6 | Loose thread ("we'll adjust your dose", never revisited) | Surfaced as a distinct *"you left this open"* section |
| 7 | Internal contradiction (20mg at 3:10, 10mg at 11:45) | **Blocking**, both values shown with timestamps |
| 8 | **Cross-turn association** — a sig, date or `change_kind` drawn from a different turn than the drug mention | Prefilled + flagged, shown **expanded** with both quotes and both timestamps. Never collapsed, never printed as fact unclicked. |

Four dispositions exist: dropped, blocking queue item, prefilled and
flagged for one-click confirm, or printed as fact.

**Only two blocking cases.** Everything else is glance-and-accept, because in
a clinician workflow **over-flagging costs a click and under-flagging costs a
wrong dose**. Tune the confidence threshold aggressively toward flagging and
say so as a deliberate choice.

Notes:
- **Category 1 is dropped but counted, and this is a change from the original
  reasoning.** "Deletion, not disclosure" is right about the *item* and wrong
  about the *number*. A silently deleted medication is indistinguishable from
  one the model never found, and D9 collapses everything non-blocking — so an
  omission is invisible in a 60-second review, on a page that looks complete.
  The header reads *"14 confirmed · 2 need your ear · 1 discarded"*. The
  clinician never sees the fabricated text, which is the part that mattered.
- **Category 8 is the one the architecture cannot verify.** `str.find` proves
  a quote is real; it does not prove the quote was attached to the right drug.
  The model can pull a genuine *"twice daily"* from drug A's turn and nest it
  under drug B — every span verifies, the card is wrong. This is the residual
  risk in the whole design and it is why association is surfaced expanded
  rather than left to the clinician's assumed diligence. Not blocking:
  blocking it would cost D9's budget on the common case, where the sig and the
  mention share a turn and nothing needs a second look.
- Category 2 now reads **segment-level** signals, not just per-word ones.
  Whisper large-v3 invents text over silence, and an exam room has plenty of
  it. Those inventions land in `transcript_text`, which makes them *verifiable
  spans* — `str.find` will happily confirm them. Segment `no_speech_prob` and
  `compression_ratio` (> ~2.4) are the standard heuristics, and B4's rule that
  a word with no diarization interval is dropped removes most of them before
  D16 ever runs.
- Category 6 is arguably our most valuable output. *"You told the patient
  you'd adjust the dose and never specified it"* is a genuine catch.
- Category 7: surface both, let the doctor pick. Silently choosing the later
  value is a defensible heuristic and an indefensible product decision.
- **Nothing unverified reaches the printed page.** Either the clinician
  resolved it or it is not there. Uncertainty is resolved *before* printing,
  so the patient's copy contains no hedging language at all.
- We have no labeled data to tune the confidence threshold against. If asked
  how we validated it, the honest answer — "we didn't, so we biased it toward
  asking the doctor" — is stronger than a fabricated figure.

**D17 — Three deterministic tools. No interaction checker.** *(Q4)*

1. **Drug name resolver** — heard text -> canonical RxNorm concept. Doubles as
   a transcription-error catcher.
2. **Dosage and frequency parser** — a real grammar over sig language
   ("one tablet twice daily with food"), not a model guess.
3. **Relative date resolver** — "come back in three weeks" -> a calendar date,
   computed in code.

Each is deterministic, independently testable, and demonstrable in ten
seconds. Together they cover the highest-stakes content: wrong dose, wrong
drug, wrong day.

- *Rejected — drug-drug interaction checking.* This is a deliberate omission
  and a credibility win, not a gap. See §6.

**D18 — Relative dates anchor to the visit date, captured once at ingest.** *(Q24b)*

Read the audio file's mtime **once at ingest and persist it** as the session's
visit date. Never read mtime again.

- *Why not processing-time clock:* the pre-computed demo file would resolve
  every date against whenever we happened to run it, and in production any
  visit processed next morning silently shifts every follow-up by a day.
- *Why persist:* `cp` without `-p`, any re-encode, and any cloud sync resets
  mtime. Persisting at ingest keeps D18 correct under all of them.
- Print **both** the resolved date and the original phrasing — *"three weeks
  from today, which is Friday, October 9"* (from a visit on Friday,
  September 18, 2026) — because a patient reading a bare date has no way to
  catch an error, and reading both lets them.
- **Demo trap, and the reason that example changed.** Any whole number of
  weeks from a Saturday is a Saturday. The hackathon is Sept 19–20, 2026,
  both weekend days, so a recording made during the event plus *"in two
  weeks"* or *"in three weeks"* resolves to a Saturday follow-up on the
  printed page. Either pin the demo session's `visit_date` to a weekday, or
  write a non-multiple-of-seven interval into the script (1d). Check it
  against a calendar before recording, not after.

### 3.4 Speech processing

**D19 — pyannote.audio for diarization, `num_speakers=2`.** *(Q9b, Q22c)*

Attribution is a **correctness** requirement, not a display nicety. Without
it:

> **Companion:** "So should I take four of them?"
> **Doctor:** "No — two, and only at night."

...a system with no speaker separation can extract "four."

**Hard rule: a dose or frequency may only be extracted from a clinician-
labelled turn.** Ambiguous attribution is blocking (D16 category 3).

Use `output.exclusive_speaker_diarization` — new in 4.0, purpose-built for
downstream transcription. It strips overlapping speech so assigning each
Whisper word to a speaker is an unambiguous interval lookup.

**Accepted limitation:** pinning 2 speakers means a third voice is merged into
an existing cluster rather than detected. Mitigation: after enrollment
matching, check each cluster's distance from its assigned identity and flag
the session *"unexpected speaker — review manually"* when implausible. This
converts a silent misattribution into a D16 blocking item. See §6.

**D20 — Clinician identity by voice enrollment, with manual override.** *(Q15a+c)*

pyannote emits anonymous `SPEAKER_00` / `SPEAKER_01` with **no role
identification**; named-speaker voiceprinting is a paid cloud feature. But
4.x exposes `output.speaker_embeddings` aligned to the diarization labels —
the intended hook. The clinician records ~10 seconds once at setup; we match
clusters against that embedding.

Manual "that's me" override stays, because embeddings fail on colds, masks and
speakerphone.

- *Rejected — talk-time heuristic:* doctors dominate visit speech, so it is
  usually right. A rule about dosages must not rest on "usually."

**D21 — `mlx-community/whisper-large-v3-mlx` (3.08 GB). NOT turbo.**

Neither model ships `alignment_heads` in its config, so mlx-whisper falls back
to "use the last half of decoder layers" for the DTW alignment that produces
word timestamps. On large-v3 that is 16 layers. **On turbo it is 2**, because
turbo has only 4 decoder layers total — and it is not OpenAI's curated head
subset either. Expect measurably worse word-boundary precision.

Our entire provenance chain is word offsets. The 1.5 GB saving is not worth it.

Returns everything D16 needs: `WordTiming(word, tokens, start, end,
probability)` per word, plus `avg_logprob`, `compression_ratio` and
`no_speech_prob` per segment.

Pass the model ID explicitly — the in-code default differs from the README.

### 3.5 Model and runtime

**D22 — Python 3.14, plain pyannote, MLX. No WhisperX.** *(Q20a)*

WhisperX is hard-blocked on 3.14 (metadata caps at `<3.14`, and it pins
`torch~=2.8.0`, which has no cp314 macOS arm64 wheel). Adding a second Python
install to save ~40 lines of interval join would cost us MLX Whisper, our
single biggest speed advantage on this hardware.

Nobody has publicly reported pyannote 4.0.7 on 3.14. Wheels and metadata say
it works. **Verify it imports and diarizes a 30-second clip before building on
top of it.**

**D23 — xgrammar for schema enforcement.**

`mlx-lm` 0.31.3 has **no** constrained decoding — verified by source
inspection. Its only JSON story is post-hoc parsing, with open correctness
bugs. xgrammar 0.2.7 ships a Metal bitmask kernel for MLX, an official mlx-lm
contrib integration, and cp314 arm64 wheels published 2026-09-15.

    from xgrammar import GrammarCompiler
    grammar = compiler.compile_json_schema(MySchema, strict_mode=True)
    mlx_lm.generate(..., logits_processors=[XGrammarLogitsProcessor(grammar)])

- *Rejected — outlines:* hard-blocked on 3.14; the `<3.14` cap is still in
  `main`, not just the release.
- *Rejected — lm-format-enforcer:* installs on 3.14 but has no MLX
  integration at all.
- *Rejected — llama-cpp-python GBNF:* no cp314 Metal wheels; source build
  only, and we would give up MLX speed.
- **Rejected — Ollama, emphatically.** On >32 GB machines it defaults to its
  MLX engine, which has a documented history of **silently ignoring** the
  `format` schema — returning unconstrained prose with no error — plus an open
  bug (filed 2026-09-14) emitting a stray `"."` before the JSON. Silent schema
  drops are the precise failure mode this architecture exists to prevent.
  Ollama uses xgrammar internally anyway; calling it directly removes the
  layer that breaks.

**If xgrammar cannot compile our schema, we are not dead.** This is the only
unverified assumption in the build with no documented fallback, and Track C
dies without one. `VisitExtraction` is a nested Pydantic model, so it emits
`$defs`/`$ref`; `strict_mode=True` is particular; and the cp314 wheel is days
old. **Smoke-test `compile_json_schema` against the real schema in hour one**
(§9), not at hour ten.

Fallback: post-hoc `json.loads` with one reparse retry. We lose D13's *first*
guarantee — well-formedness — and keep the second, which is the one that
matters. Span verification is what makes the output true; the grammar only
makes it parseable. Degraded and honest, like gate 0g.

**D24 — Extraction model: build on 9B, demo on the MoE.**

With xgrammar handling structure, the model's job shrinks sharply. It is not
producing valid JSON — that is guaranteed — it is only choosing spans. That is
mechanical, so a smaller model goes further than expected. Our thesis arriving
as an implementation detail.

| Repo ID | On disk | Speed (M5 Pro) | Role |
|---|---|---|---|
| `mlx-community/Qwen3.5-9B-4bit` | 5.98 GB | fast | **develop on this** |
| `mlx-community/Qwen3.6-35B-A3B-4bit` | 20.43 GB | ~65–85 tok/s (MoE) | demo candidate |
| `mlx-community/Qwen3.8-27B-4bit` | 16.08 GB | ~25–35 tok/s (dense) | quality reference |

The MoE is 2–3x faster than the dense 27B because only ~3B params are active.
Given D9's 60-second budget and D15's per-turn chunking — many short
generations rather than one long one — throughput matters more than headroom.

**Hypothesis worth ten minutes:** 9B at 8-bit may beat 27B at 4-bit for exact
quote reproduction. Quantization noise degrades verbatim copying harder than
it degrades reasoning, and 8-bit 9B is ~10 GB where 8-bit 27B at 29.5 GB is
tight against the ~36 GB practical GPU working set (macOS wires ~75% of
unified memory by default).

No credible published benchmark ranks these models on structured extraction.
Benchmark on our own schema; anyone claiming otherwise is guessing.

Most current flagships are natively multimodal and their cards advertise
`mlx-vlm`. They remain mlx-lm loadable, but **verify a load before building on
one.**

### 3.6 Output and integration

**D29 — Only medications reach a human.**

Extraction still produces appointments, red flags and loose threads; they are
still verified and still in `extraction.json`. They are not shown. The review
screen is one box per medication, and the patient's page carries the medicines
table and nothing else.

Every kind is a surface that can be wrong in its own way, and the non-drug
ones are the ungrounded ones: appointments needed deduplication, red flags
needed deduplication and a containment threshold, and nothing checks either
beyond quoting them. Medications are what the tool layer actually grounds —
RxNorm resolves the name, the sig grammar parses the dose, cross-validation
checks it against available strengths, and D16 category 7 catches a
contradiction. A narrower product that is right beats a broad one that is
nearly right.

Gated by `render/model.py::SCOPE`, not by the prompt, so the data survives and
the decision is one line to reverse. The tests for the hidden kinds widen
`SCOPE` through a fixture rather than being deleted — they are capability
tests, and reversing this should not require rewriting a suite to prove
something that never stopped working.

**A mention with no drug name in it is dropped before it becomes a box.**
Per-turn extraction nominates from a single turn, so a clinician's correction
— *"Five hundred. With food."* — arrives as a medication containing no drug,
and so does *"Still on it"*. On the test script two of the four boxes were
fragments like these. Under D29 they were half of everything the clinician had
to confirm. The test is narrow: a phrase is dropped only when every token is a
number word, a unit or a function word. *"my blood pressure pill"* and
*"water pill"* survive — they name a drug by what it does, which is a real
mention D16 category 4 exists to flag.

- *Rejected — fixing it in the prompt.* The model is not wrong to nominate
  these; they are what the turn said. The judgement that a phrase names no
  drug is deterministic and belongs where it can be audited.

**D28 — Live capture in the browser.** *(supersedes the original scope cut)*

Numbered last because it was reversed last. Live recording was cut early — a
pre-recorded file is the same demo from the audience's seat, minus a class of
microphone failure — but the consent screen grew a button saying **Start
recording** that did not record. A control promising something the system
cannot do is worse than the missing feature: a judge clicks it and concludes
the demo is canned.

`MediaRecorder` in the page, two takes (the clinician's voice for D20's
enrollment, then the visit), posted as raw blobs to `/upload`. The visit
upload runs `audio.pipeline` then `verify` on a worker thread while the page
polls `/progress` and follows the real per-turn extraction count. About 96 s
end to end on a four-minute visit.

Vanilla JS and stdlib `http.server` — no new dependency, because D1 says
nothing leaves the laptop and a CDN script is a thing that leaves.

`--session`/`--extraction` still skip capture and go straight to review, so the
pre-computed path is intact and remains the demo fallback.

- *Rejected — the Web Speech API.* Chrome's built-in recogniser would have
  given live transcription in an afternoon, and it ships audio to Google's
  servers. It would work immediately and silently destroy D1.

**D25 — Print locally. Mobile deferred.** *(Collision 2)*

Printing keeps the artifact inside the practice. Mobile delivery of the patient
copy is explicit future work, not a gap.

- **Say "inside the practice", not "on-device".** A network printer is a hop,
  and it spools. It is the provider's own equipment, which is the same
  argument D26 makes about the chart — but the precise phrasing is what keeps
  the claim true, and this document is otherwise careful about exactly that.
  Demo over USB or AirPrint to a local printer if one is in the room.

**D26 — Digital chart copy is a local FHIR `DocumentReference` whose embedded
content is byte-for-byte the document we printed.** *(Q17a, Collision 3)*

(Phrased carefully: a FHIR resource and a sheet of paper are different
encodings, so "byte-identical to the printed copy" cannot be literally true.
What *is* true, and is the actual guarantee, is that the bytes rendered for
print are the exact bytes stored in `content.attachment` — one render, two
destinations, no second code path to drift.)

Rehearse this sentence, because it resolves the apparent conflict with D1:

> Nothing goes to a third party. The only destination is the provider's own
> record system, which already holds this patient's chart — and in our demo it
> is a local FHIR DocumentReference.

The chart copy matching the printed copy exactly means the patient and the
record never diverge. The chart integration is optional scope.

- *Rejected — real EHR sandbox (SMART on FHIR / Epic):* OAuth against a
  sandbox is a classic hour-20 disaster, and it would send data off-device,
  converting our strongest claim into an asterisk.

---

## 4. Data sources

All public domain or CC0. **No UMLS account** — NLM approval takes five
business days, so RxNorm full, SNOMED CT, UMLS and RxNav-in-a-Box were never
reachable inside 24 hours.

| Source | Size | License | Purpose |
|---|---|---|---|
| **RxNorm Current Prescribable** | 74.75 MB (512 MB unpacked) | Public domain, **no account** | drug name resolution (D17 tool 1) |
| **openFDA `drug/label`** | 1,774 MB / 14 parts | CC0 | citable clinical label text |
| CHV lay-term map | 3.3 MB / 158k rows | no stated license | professional -> lay term |
| UMich Plain Language Dictionary | 408 KB / 1,962 terms | no LICENSE file | jargon glossary |
| ICD-10-CM descriptions | 2.2 MB | Public domain | diagnosis grounding |
| MedlinePlus health topics | 4.77 MB / 1,017 EN | Public domain | *condition* plain language |

### The join

```
transcript drug mention
  -> fuzzy match against the SPOKEN-NAME index (18,094 strings — NOT all
     246,241; see TOOLS.md §1 and the landmine in §7)
  -> RxCUI
  -> RXNSAT.SPL_SET_ID          <-- 1.7M rows over 21,594 RxCUIs
  -> openFDA label set_id
  -> cite exact label text
```

**Join on `SPL_SET_ID`, never on `openfda.rxcui`.** Only ~64,660 of 262,883
label records (~25%) carry an rxcui. Getting this wrong looks like a broken
drug lookup when it is a broken join.

Useful openFDA fields: `dosage_and_administration`, `drug_interactions`,
**`geriatric_use`**, `information_for_patients`, `spl_medguide`,
`boxed_warning`, `contraindications`.

`geriatric_use` is a differentiator worth building on: public-domain,
FDA-authoritative, quotable text specifically about dosing in patients over
65 — *"here is what this drug's own label says about people your age, in the
label's exact words."* On thesis, zero generation.

### Do not use MedlinePlus for drug information

MedlinePlus **drug** pages are AHFS/ASHP copyrighted, and their terms
specifically forbid ingesting that content into "an EHR, patient portal, or
other health IT system" — exactly what we are building. Use openFDA
`spl_medguide` and `information_for_patients` instead; both public domain.
MedlinePlus *condition* topics are fine.

---

## 5. Stack, as installed

Versions read off the running environment, not planned. All have cp314 macOS
arm64 wheels.

| | Version | Role |
|---|---|---|
| Python | 3.14.7 | standard build, not 3.14t |
| `mlx` | 0.32.2 | cp314 + `macosx_26_0_arm64` — this OS is natively targeted |
| `mlx-lm` | 0.31.3 | runs the extraction model |
| `xgrammar` | 0.2.7 | grammar-constrained decoding (D23); mlx-lm has none of its own |
| `mlx-whisper` | 0.4.3 | B1 — word timestamps and per-word probability |
| `pyannote.audio` | 4.0.7 | B2 — diarization and speaker embeddings |
| `torch` | 2.14.0 | pyannote's backend |
| `transformers` | 5.17.0 | tokenizer for the grammar compiler |
| `jinja2` | 3.1.6 | the two page templates |
| `pydantic` | 2.13.5 | `contracts.py`, and the extraction schema xgrammar compiles |
| `jellyfish` | 1.2.1 | Jaro-Winkler for A6's rescore |
| `metaphone` | 0.6 | Double Metaphone for A6's phonetic recall |
| `numpy` | 2.5.3 | — |
| **ffmpeg** | — | **hard dependency** for both Whisper and pyannote 4.x (torchcodec is ffmpeg-only) |

No web framework: the UI is stdlib `http.server` plus Jinja2, and the
recording page is vanilla JS. D1 says nothing leaves the laptop, and 4b turns
the Wi-Fi off — a dependency we would have to install on venue Wi-Fi is a
demo-day risk taken for a router we do not need.

**Models cached locally** (`~/.cache/huggingface`):

| Model | Size | Used by |
|---|---|---|
| `mlx-community/whisper-large-v3-mlx` | 3.08 GB | B1. **Not turbo** — see D21 |
| `pyannote-community/speaker-diarization-community-1` | ~33 MB | B2. Ungated mirror, no token |
| `mlx-community/Qwen3.5-9B-4bit` | 5.98 GB | C3, the working model |
| `mlx-community/Qwen3.6-35B-A3B-4bit` | 20.43 GB | C3 escalation if fidelity drops |

**Databases built locally** (`data/`, gitignored):

| File | Size | From |
|---|---|---|
| `rxnorm.db` | 245 MB | RxNorm Current Prescribable (A1–A7) |
| `openfda_labels.db` | 1.82 GB | openFDA drug labels (A8) |

Hardware: MacBook Pro, Apple M5 Pro, 18 cores, 48 GB unified memory.
Practical GPU working set ~36 GB.

Licenses: `pyannote.audio` MIT (© 2020 CNRS); `speaker-diarization-community-1`
weights CC-BY-4.0 (commercial use permitted, attribution required — credit
pyannote and cite the two Interspeech papers). RxNorm and openFDA are public
domain / CC0.

---

## 6. Known limitations — state these before a judge finds them

**No drug-drug interaction checking. Deliberate.**

No free, comprehensive, redistributable DDI dataset exists. NLM retired the
RxNav interaction API in January 2024 with no replacement. DrugBank's academic
downloads are paused and its license excludes clinical use. DDInter is
CC BY-NC-SA and ships only 8 ATC classes, **missing C, G, J, M, N and S** —
that is statins, antihypertensives, antiarrhythmics, antibiotics, opioids,
benzodiazepines, antidepressants and antipsychotics. For an elderly
polypharmacy patient the free interaction data is missing nearly every drug
they actually take.

We chose not to ship a checker that fails silently on real input and looks
fine on a curated demo. If interaction *grounding* is ever wanted, the honest
version is citing openFDA `drug_interactions` label text — quote the label,
never assert a verdict.

**Two-speaker assumption.** D19. A geriatrics-literate judge will ask about the
adult child or home aide who is very often in the room. Our answer: clinician
identity comes from voice enrollment, not speaker count, so the dose-safety
rule is robust in principle; with `num_speakers=2` pinned we mitigate by
flagging implausible cluster distances for manual review. Supporting 3+
speakers is auto-detection plus one role category — not an architectural
change.

**Do not claim we handle multi-party consultations. Claim we detect when we
might not be able to.**

**Drug coverage.** RxNorm *Prescribable* deliberately excludes suppressed,
obsolete, veterinary-only and non-US drugs. Compounded preparations,
investigational drugs and supplements will not resolve.

**openFDA carries a "not validated for clinical use" disclaimer.** Consistent
with our design — we cite label text, we do not assert claims — but have the
answer ready.

**Deferred on purpose:** mobile delivery, 3+ speakers, interaction checking,
real EHR integration.

---

## 7. Implementation landmines

Each of these has already cost someone time. None should cost it twice.

**Environment**
- `ffmpeg` is a hard dependency. pyannote 4.x dropped sox and soundfile for
  torchcodec, which is ffmpeg-only. Whisper needs it too. **Install first.**
- No Homebrew, no cmake, no `timeout` (it is not on macOS). Use static ffmpeg
  builds from evermeet.cx, or `pip install imageio-ffmpeg`.

**pyannote 4.x — 3.x tutorials are wrong**
- Model ID is `pyannote/speaker-diarization-community-1`, not
  `speaker-diarization-3.1`. Gate is **auto-approval, instant**.
- Kwarg is `token=`. `use_auth_token=` was removed in 4.0 and raises
  `TypeError`.
- `pipeline(...)` returns a **`DiarizeOutput` dataclass**, not an `Annotation`.
  Every 3.x example calling `.itertracks(yield_label=True)` on the return value
  breaks. `legacy=True` restores the old shape.
- Ungated mirror if the gate form is a nuisance:
  `pyannote-community/speaker-diarization-community-1`.
- Model download is only ~33 MB. **PyTorch is the 1–2 GB download.**
- `export PYANNOTE_METRICS_ENABLED=false` (D4).

**MPS**
- MPS works in 4.0.7; the old `aten::_fft_r2c` crash is already patched
  internally, so `PYTORCH_ENABLE_MPS_FALLBACK` is unnecessary.
- **But diff one run against CPU on the same file before trusting it.**
  pyannote's MPS issues are closed *wontfix*, including one titled "wrong
  timestamps when using MPS on a Mac M1." Wrong timestamps would silently
  corrupt the entire provenance chain.
- CPU-only diarization runs ~0.55x real-time on M5 Pro: 15 min audio ≈ 8 min.
  Whisper is not the bottleneck; pyannote is. D19's safety rule makes
  diarization blocking, so the wait cannot hide behind a streaming transcript.

**RxNorm RRF**
- **Every line ends with a trailing `|`**, producing a phantom empty final
  column. A naive `line.split('|')` misaligns every positional index past the
  last real field. This catches everyone exactly once.
- Only MySQL and Oracle load scripts ship. Write the SQLite loader.
- **`RXNREL.RRF` (198 MB) is optional, with a caveat.** Load RXNCONSO
  (30.6 MB) and the `SPL_SET_ID` slice of RXNSAT (283 MB) first — those are
  required. RXNREL holds the `has_ingredient` / `tradename_of` graph, which is
  the authoritative way to link a brand name's RXCUI to its ingredient
  concept. Without it, brand -> generic mapping is derived by parsing the
  bracketed brand out of SBD strings (`... Oral Tablet [Toprol-XL]`, ~8k rows).
  That workaround is adequate for v1 but fragile against format variation.
  See TOOLS.md §1 "Resolution algorithm", step 6.

**RxNorm TTYs are not what their names suggest — measured, not assumed**

Counted directly off `RXNCONSO.RRF` (`LAT='ENG'`, `SUPPRESS != 'Y'`):

Matching `\d+\s*(MG|ML|MCG|UNT|%|/)`, case-insensitive:

| TTY | rows | dose-bearing | |
|---|---|---|---|
| `IN` | 5,844 | 42 | 0.7% |
| `BN` | 4,134 | 27 | 0.7% |
| `PIN` | 1,943 | 43 | 2.2% |
| **`SY`** | **28,329** | **25,427** | **89.8%** |
| **`TMSY`** | **9,739** | **6,468** | **66.4%** |
| **`PSN`** | **21,305** | **20,193** | **94.8%** |

- **`SY` and `TMSY` are overwhelmingly product strings**, not synonyms a
  clinician would say — `metoprolol succinate 100 MG 24 HR Extended Release
  Oral Capsule` is an `SY`. Putting them in a "what clinicians say" index
  defeats the reason `SCD`/`SBD` were excluded from it. **Filter them by dose
  pattern at build time.**
- **`PSN` is 94.3% dose-bearing** and belongs in the product index, not the
  name index.
- **`PIN` (precise ingredient) is the TTY the design was missing.** Salt forms
  live there — `metoprolol succinate` is `PIN` 221124, `metoprolol tartrate` is
  `PIN` 203191 — and `PIN` was in neither index. See TOOLS.md §1.
- **Apply the dose filter to `SY`/`TMSY` only.** It would also drop 42 `IN`,
  27 `BN` and 43 `PIN` rows, which are real ingredient names that happen to
  carry a numeral. Those three TTYs go in whole.

Net: the spoken-name index is **18,094** strings — IN 5,844 + BN 4,134 +
PIN 1,943 + SY 2,902 + TMSY 3,271 — not the 48,046 the unfiltered TTY list
implies, and certainly not 246,241.

**Repo hygiene**
- `.gitignore` the data before `git init`: `*.zip`, `rrf/`, the openFDA
  directory, **and `logs/` / `*.log` / `*.jsonl`** — D2's retention claim
  covers logs, and so must the ignore file. 1.85 GB of reference data does not
  belong in git history, and neither does a transcript fragment.

---

## 8. Demo plan

**Two files.** *(Q21d)*

1. **Short clip, run live, Wi-Fi off.** A 3–4 minute segment — the
   medication-and-follow-up portion of a visit, which is genuinely short in
   reality. ~2 min CPU, well under a minute on MPS. Wi-Fi off is the cheapest,
   most visceral proof of D1 available.
2. **Longer visit, pre-computed**, shown as evidence of scale and **labelled
   honestly as pre-computed.**

A tight 4-minute script with real disfluency demonstrates the mechanism better
than 15 rambling minutes.

**Audio is teammate role-play.** *(Q6a)* Real recordings of a real relative's
appointment would create PHI with no plan for it — and with no BAA anywhere in
this stack, synthetic or consented role-play is the only defensible source. We
never created PHI.

**Script constraint:** use drugs verified to resolve against RxNorm, and — per
D19 and §6 — **two speakers only.**

**Budget the wall clock, not just the review.** D9's 60 seconds is the
*clinician's* time. Nothing in this spec budgets the pipeline's. The live run
is model loads (several GB of weights) + Whisper + diarization + **one
constrained generation per turn** across 40–60 turns — plausibly four to six
minutes, against a demo slot that is usually three to five. Measure it
end to end at 3b, not at 4b. If it does not fit, start the run under the
intro slide; that is honest and it is not the same as pre-computing.

Related: Whisper (3.08 GB) and a 20.43 GB MoE against a ~36 GB working set do
not coexist. Stages run sequentially (§2) — so free each model before loading
the next, explicitly. MLX will not do it for you in time.

**Start these downloads now.** They are the only things in this project that
cleverness cannot speed up later: PyTorch (1–2 GB) and openFDA (1.77 GB).

---

## 9. Open verification tasks

Do these before building on top of the assumption.

- [ ] **`compile_json_schema(VisitExtraction, strict_mode=True)` actually
      compiles** — hour one, needs no audio, no fixture, no model. The only
      track-killing assumption in the build (D23)
- [ ] pyannote 4.0.7 imports and diarizes a 30-second clip on Python 3.14
      (nobody has publicly reported this combination)
- [ ] MPS diarization output matches CPU on the same file
- [ ] Chosen MLX model loads via `mlx-lm` despite advertising `mlx-vlm`
- [ ] Whisper word offsets are accurate enough for click-to-play
- [ ] xgrammar per-token bitmask round-trip overhead is acceptable
      (unmeasured; involves a CPU<->GPU hop each step)
- [ ] 8-bit 9B vs 4-bit 27B on verbatim quote fidelity (D24 hypothesis)
- [ ] Demo script drugs all resolve against RXNCONSO
- [ ] The spoken-name index contains no dose-bearing strings after filtering
      (§7) — grep the built index for `\d+ *(MG|ML|MCG)` and expect zero
- [ ] Every follow-up date in the script lands on a **weekday** (D18)

---

## 10. Decision index

| | Decision | From |
|---|---|---|
| D1 | Fully local, no cloud STT | Q1b |
| D2 | Delete audio on approval | Q19a |
| D3 | 24h expiry for unapproved sessions | Q23a |
| D4 | Telemetry disabled | — |
| D5 | Voice embedding is biometric data | — |
| D6 | Clinician is user, patient is audience | Q12c |
| D7 | Action card + extractive visit summary | Q3a+b, Q10a+c |
| D8 | Audio playback is clinician-only | Q16a |
| D9 | 60-second review budget | Q18 |
| D10 | Footer names the clinician | Q25b |
| D11 | Liability rests with the attesting clinician | — |
| D12 | Span-locked extraction + templates | Q5a+c |
| D13 | Grammar for structure, code for truth | — |
| D14 | Code computes offsets, not the model | — |
| D15 | Chunk by speaker turn | — |
| D16 | Seven-mode disposition table | Q11 |
| D17 | Three deterministic tools, no DDI checker | Q4 |
| D18 | Visit date from mtime, persisted at ingest | Q24b |
| D19 | pyannote, `num_speakers=2` | Q9b, Q22c |
| D20 | Voice enrollment + manual override | Q15a+c |
| D21 | whisper-large-v3-mlx, not turbo | — |
| D22 | Python 3.14, MLX, no WhisperX | Q20a |
| D23 | xgrammar, not Ollama/outlines | — |
| D24 | 9B to build, MoE to demo | — |
| D25 | Print locally, mobile deferred | — |
| D26 | Local FHIR DocumentReference, identical to print | Q17a |
| D27 | Patient consents to the recording; the artifact proves it | — |
| D28 | Live capture in the browser (reverses the original scope cut) | — |
| D29 | Only medications reach a human; drug-less mentions dropped | — |

See also [PRESENTATION-NOTES.md](PRESENTATION-NOTES.md) for what must be said
on stage.
