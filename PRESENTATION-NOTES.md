# Presentation must-says

Running list of things we have to state explicitly on stage.
Added as design decisions surface; check this before the pitch.

## 1. Scope of drug identification — REQUIRED (requested by team)

State plainly what our drug coverage is and is not:

- Drug names resolve against **RxNorm Current Prescribable Content**:
  246,241 English non-suppressed rows in the file, of which our spoken-name
  index is **18,094** — 5,844 ingredients, 4,134 brand names, 1,943 precise
  ingredients, plus filtered synonyms. Public domain, no UMLS account.
  Quote 18,094 if asked what we search; 246,241 is the corpus, not the index.
- This is the *prescribable* subset: suppressed, obsolete, veterinary-only
  and non-US drugs are deliberately excluded.
- Clinical label text is cited from **openFDA drug/label** (262,883 records, CC0).
  Coverage caveat: only ~64,660 (~25%) carry an `openfda.rxcui`;
  we join on `SPL_SET_ID` instead, which covers far more.
- **We do NOT do drug-drug interaction checking.** Say why, it is a
  credibility win: no free, comprehensive, redistributable DDI dataset
  exists. NLM retired the RxNav interaction API in Jan 2024 with no
  replacement, DrugBank academic downloads are paused, and DDInter is
  missing ATC classes C, G, J, M, N, S — i.e. statins, antihypertensives,
  antiarrhythmics, antibiotics, opioids, benzodiazepines, antidepressants
  and antipsychotics. For an elderly polypharmacy patient the free
  interaction data is missing nearly every drug they actually take.
  We chose not to ship a checker that fails silently on real input.
- Compounded preparations, investigational drugs and supplements will not
  resolve. Say so before a judge finds it.

## 2. openFDA disclaimer — know it before being asked

openFDA terms carry an explicit "not validated for clinical use" notice.
Consistent with our design (we cite label text, we do not assert claims),
but have the answer ready.

## 3. Compliance boundary

Fully local: no audio, transcript or note leaves the device. No BAA needed
because no third party is involved. Demo audio is teammate role-play, not
real patient data — we never created PHI.

**Consent (D27) — expect this question, it is the first one after privacy.**
The patient consents before recording; `Session.consent` is required and the
printed page states it. Massachusetts is an all-party-consent jurisdiction and
its wiretap statute is criminal rather than civil, which is worth knowing given
where we are standing. Our demo audio is teammate role-play, so the demo itself
was never in scope for it — but the *product* needs the step, and it has one.

**Retention covers derived artifacts, not just the `.wav`.** Logs, ffmpeg
scratch files and tracebacks carry transcript text. The sweep runs against a
session directory. *"Audio exists until the doctor signs, or 24 hours"* is a
claim that survives exactly one follow-up question about logs, so have the
answer.

## 4. Dependency network audit — we found and killed a leak

pyannote.audio 4.0.7 ships telemetry **ENABLED BY DEFAULT**
(`pyannote/audio/telemetry/config.yaml` → `metrics_enabled: true`).
It exports OpenTelemetry spans — including **audio duration and speaker
counts** — to `https://otel.pyannote.ai/v1/traces`.

For a product whose entire claim is "nothing leaves the device," a
dependency phoning home is a credibility kill shot if a judge finds it
before we mention it. We must:

    export PYANNOTE_METRICS_ENABLED=false

or call `set_telemetry_metrics(False, save_choice_as_default=True)`.

Say this on stage as a positive: we audited our dependency tree for
outbound network calls, found one, and disabled it. "Local-first" is a
property you have to verify, not a design intention. Consider running
the demo with Wi-Fi off entirely as proof.

## 5. Attribution obligations (license compliance)

- pyannote.audio library: **MIT** (© 2020 CNRS).
- `speaker-diarization-community-1` weights: **CC-BY-4.0** — commercial use
  allowed, attribution required. Credit pyannote + cite the two Interspeech
  papers.
- openFDA: CC0, attribution requested not required.
- MedlinePlus condition topics: "Courtesy of MedlinePlus from the National
  Library of Medicine."
- NOT used, deliberately: MedlinePlus drug pages (AHFS/ASHP copyrighted,
  and their terms forbid ingesting into a patient-facing health IT system).

## 6. Known limitation: two-speaker assumption (state it before asked)

v1 pins pyannote `num_speakers=2` — one clinician, one patient. Say this
plainly, because a judge who knows geriatrics will ask about the adult
child or home aide who is very often in the room.

Our answer:
- The dose-safety rule depends on knowing which turns are the clinician's,
  and clinician identity comes from *voice enrollment*, not from speaker
  count. So the rule is robust to who else is present in principle.
- With `num_speakers=2` pinned, a third voice would be merged into an
  existing cluster rather than detected. We mitigate by checking each
  cluster's distance from its assigned identity and flagging the session
  for manual review when it looks implausible — a silent misattribution
  becomes a blocking review item.
- Supporting 3+ speakers is auto-detection plus one extra role category,
  not an architectural change. Deliberately out of scope for v1.

Do NOT claim we handle multi-party consultations. Claim we detect when
we might not be able to.

## 7. Biometric data note

Voice embeddings are biometric identifiers — **both of them**, which is the
precise version of this answer.

The clinician's enrolled embedding is the obvious one and belongs to the
clinician, not the patient. But `speaker_embeddings` carries a vector per
cluster: we have to embed the patient's voice to compare clusters against the
enrollment at all. So the pipeline does compute a patient voiceprint,
transiently. **It is never persisted, never logged, and `Session` has no field
for it.**

Say it that way. "The embedding belongs to the clinician" is not quite true,
and the point being made is that we know the difference between *local* and
*harmless*.

## 8. Deferred, on purpose (have these ready as "future work")

- Mobile app delivery of the patient copy (v1 prints locally to stay local).
- 3+ speaker consultations.
- Drug-drug interaction checking (see item 1 for why — this is a
  deliberate omission, not a gap).
- Real EHR integration; v1 writes a local FHIR DocumentReference.
- Live transcription *during* recording. Possible locally with a small
  Whisper, deliberately not built via the browser's speech API — see item 10.

Note: live *recording* was on this list and is now built (D28). If anyone
asks why it moved, the answer is that the consent screen shipped a button
saying "Start recording" that did not record, and a control promising
something the system cannot do is worse than the missing feature.

## 9. We audited our own knowledge base, not just our dependencies

Item 4 is a dependency audit. This is the data audit, and it is the better
story because it caught a clinical error rather than a privacy one.

We counted what is actually in RxNorm instead of trusting the TTY names:

- **`SY` is 89.8% dose-bearing product strings**, `TMSY` 66.4%, `PSN` 94.8%.
  A "synonym" row is `metoprolol succinate 100 MG 24 HR Extended Release Oral
  Capsule`. Indexing those as spoken names would have flooded our fuzzy matcher
  with 31,895 strings that carry a dose — in the index built to keep dose out.
- **`PIN` is where salt forms live, and we had not indexed it.** `metoprolol`
  is `IN` 6918; `metoprolol succinate` is `PIN` 221124, `metoprolol tartrate`
  is `PIN` 203191. So *"metoprolol"* matched the bare ingredient exactly and
  returned a confident answer — hiding that **succinate is extended-release
  once daily and tartrate is immediate-release twice daily.** Same spoken word,
  different dosing schedule.
- We precomputed the **32 ingredients** (of 5,844) where a bare name has two or
  more salt forms. Say *"metoprolol"* and we resolve the ingredient and flag
  that the salt was not specified — not an error, a finding, exactly like
  "take as directed."

The line: *we found this by counting our own data, which is the only way to
find it. A matcher that looks fine on a demo is the thing we were most afraid
of shipping.*

## 10. Live capture, and the shortcut we did not take

The app records the visit in the browser (D28). Two takes: a few seconds of
the clinician's voice, because pyannote returns anonymous clusters and D20
matches them against an enrolled voiceprint — without it there is no way to
know which speaker is the doctor, and D19's rule that a dose may only come
from a clinician turn has nothing to stand on.

**Worth saying out loud, because it is the strongest privacy point we have:**
Chrome ships a speech recogniser, `webkitSpeechRecognition`. It would have
given us live transcription in an afternoon, for free, and it sends the audio
to Google's servers. We did not use it. Everything — transcription,
diarisation, extraction — runs on this laptop, which is why 4b can turn the
Wi-Fi off and have the demo still work.

## 11. Defects we found by using it, not by testing it

Have one of these ready. They are the best evidence that the verification
layer is real rather than decorative, and every one was green in the suite.

- A patient's stumble over a drug name printed as a **third medicine** on the
  handout, duplicating one already listed correctly. Unresolved items now
  never reach the page.
- `"my water pill"` resolved to the ingredient **water** — a real RxNorm
  entry — and printed as a medicine.
- The same follow-up appointment printed **three times** in broken English,
  because dedup only caught identical spans and not overlapping ones.
- `"twenty-five mg"` parsed to **5.0**. Not null, not flagged — a dose five
  times too small, printed as fact. It also silently disabled the metformin
  contradiction, since D16 category 7 needs two *parsed* doses to see a
  conflict.

The honest framing: a test suite cannot see a page. Every one of these was
found by reading the output.
