# Presentation must-says

Running list of things we have to state explicitly on stage.
Added as design decisions surface; check this before the pitch.

## 1. Scope of drug identification — REQUIRED (requested by team)

State plainly what our drug coverage is and is not:

- Drug names resolve against **RxNorm Current Prescribable Content**
  (~246,241 name strings / 5,844 ingredients / 4,134 brand names).
  Public domain, no UMLS account.
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

The clinician's enrolled voice embedding is a biometric identifier. It is
stored locally, never transmitted, and belongs to the clinician (not the
patient). Worth one sentence if privacy comes up — it shows we know the
difference between "local" and "harmless."

## 8. Deferred, on purpose (have these ready as "future work")

- Mobile app delivery of the patient copy (v1 prints locally to stay local).
- 3+ speaker consultations.
- Drug-drug interaction checking (see item 1 for why — this is a
  deliberate omission, not a gap).
- Real EHR integration; v1 writes a local FHIR DocumentReference.
