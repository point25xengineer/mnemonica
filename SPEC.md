# Visit Notes — Design Specification

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
  [8] render + print              -> action card (templated) +
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

**D4 — Dependency telemetry is disabled.** Non-negotiable.

pyannote.audio 4.0.7 ships `metrics_enabled: true` and exports OpenTelemetry
spans — including audio duration and speaker counts — to
`https://otel.pyannote.ai/v1/traces`. For a product claiming nothing leaves
the device, this is a credibility kill shot.

    export PYANNOTE_METRICS_ENABLED=false

Run the demo with Wi-Fi off. It is the cheapest possible proof of the claim.

**D5 — The clinician's enrolled voice embedding is biometric data.** Stored
locally, never transmitted. It belongs to the clinician, not the patient.

### 3.2 Product shape

**D6 — The clinician is the user. The patient is the audience.** *(Q12c)*

The clinician records, reviews, approves, and prints. The patient receives
paper plus an identical digital copy. This is the strongest available trust
architecture and it is how human medical scribes have always worked: the tool
drafts, a licensed professional attests, the signature is the clinical act.

**D7 — Two output artifacts, both derived, neither LLM-authored.** *(Q3a+b, Q10a+c)*

| Artifact | Content | Rendering |
|---|---|---|
| **Action card** | medications, dosages, appointments, tests, red-flag instructions | **templated** — fixed sentence skeletons with extracted values slotted in |
| **Visit summary** | why you came in / what the doctor found / what happens next | **extractive** — selected verbatim quotes, grouped under fixed headings |

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

Seven distinct failure modes. The critical rule: **"I could not hear it" and
"your doctor never said it" must never look the same.** Conflating them builds
a system that blames itself for the doctor's omissions, or the doctor for its
own.

| # | Failure mode | Disposition |
|---|---|---|
| 1 | **Span verification failed** — quote not in transcript | **Dropped silently**, logged. This is fabrication; the correct response is deletion, not disclosure. |
| 2 | Low transcription confidence (per-word probability) | Prefilled + flagged, audio auto-cued to that word |
| 3 | Attribution ambiguous | **Blocking** for dose/frequency; flagged otherwise |
| 4 | Drug unresolved against RxNorm | Prefilled with raw heard text + flagged, offering near-matches |
| 5 | No dose spoken ("take as directed") | Explicit "not specified" — **not an error** |
| 6 | Loose thread ("we'll adjust your dose", never revisited) | Surfaced as a distinct *"you left this open"* section |
| 7 | Internal contradiction (20mg at 3:10, 10mg at 11:45) | **Blocking**, both values shown with timestamps |

Four dispositions exist: dropped silently, blocking queue item, prefilled and
flagged for one-click confirm, or printed as fact.

**Only two blocking cases.** Everything else is glance-and-accept, because in
a clinician workflow **over-flagging costs a click and under-flagging costs a
wrong dose**. Tune the confidence threshold aggressively toward flagging and
say so as a deliberate choice.

Notes:
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
  from today, which is Friday, October 10"* — because a patient reading a bare
  date has no way to catch an error, and reading both lets them.

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

**D25 — Print locally. Mobile deferred.** *(Collision 2)*

Printing keeps the artifact on-device. Mobile delivery of the patient copy is
explicit future work, not a gap.

**D26 — Digital chart copy is a local FHIR `DocumentReference`, and is
byte-identical to the printed copy.** *(Q17a, Collision 3)*

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
  -> fuzzy match against RXNCONSO names (~246,241 strings, all TTYs)
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

## 5. Verified dependency stack

All confirmed to have cp314 macOS arm64 wheels.

```
Python 3.14.7                 (standard build, not 3.14t)
mlx            0.32.2         cp314 + macosx_26_0_arm64 — OS natively targeted
mlx-lm         0.31.3
xgrammar       0.2.7          cp314 arm64, published 2026-09-15
mlx-whisper    0.4.3
pyannote.audio 4.0.7
torch          2.14.0
ffmpeg                        HARD dependency for both Whisper and pyannote
```

Hardware: MacBook Pro, Apple M5 Pro, 18 cores, 48 GB unified memory.
Practical GPU working set ~36 GB.

Licenses: pyannote.audio MIT (© 2020 CNRS); `speaker-diarization-community-1`
weights CC-BY-4.0 (commercial use permitted, attribution required — credit
pyannote and cite the two Interspeech papers).

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

**Repo hygiene**
- `.gitignore` the data before `git init`: `*.zip`, `rrf/`, the openFDA
  directory. 1.85 GB of reference data does not belong in git history.

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

**Start these downloads now.** They are the only things in this project that
cleverness cannot speed up later: PyTorch (1–2 GB) and openFDA (1.77 GB).

---

## 9. Open verification tasks

Do these before building on top of the assumption.

- [ ] pyannote 4.0.7 imports and diarizes a 30-second clip on Python 3.14
      (nobody has publicly reported this combination)
- [ ] MPS diarization output matches CPU on the same file
- [ ] Chosen MLX model loads via `mlx-lm` despite advertising `mlx-vlm`
- [ ] Whisper word offsets are accurate enough for click-to-play
- [ ] xgrammar per-token bitmask round-trip overhead is acceptable
      (unmeasured; involves a CPU<->GPU hop each step)
- [ ] 8-bit 9B vs 4-bit 27B on verbatim quote fidelity (D24 hypothesis)
- [ ] Demo script drugs all resolve against RXNCONSO

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

See also [PRESENTATION-NOTES.md](PRESENTATION-NOTES.md) for what must be said
on stage.
