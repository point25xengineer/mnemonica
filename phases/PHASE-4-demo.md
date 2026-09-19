# Phase 4 — Demo

**Goal:** a demo that survives contact with a skeptical judge.

**Blocked by:** Phase 3.

---

## 4a — Pre-compute the long file

Run the longer visit recording through the full pipeline and save the result.

Shown as evidence of scale, and **labelled honestly as pre-computed.** At
~0.55× real-time on CPU, a 15-minute file takes about 8 minutes of
diarization — you cannot stand on stage and wait, and pretending it's live is
the kind of thing that unravels under one question.

**Flag it as exempt from U10's expiry sweep.** This is an unapproved session
sitting on disk, which is exactly what the 24-hour sweep deletes. Pre-compute
it the night before, demo the next afternoon, and without the flag it deletes
itself somewhere around lunch.

**Done when:** the long result loads instantly from disk, and survives a sweep
run.

## 4b — Wi-Fi off, full run

Turn Wi-Fi off and run the short clip end to end.

This is the cheapest and most visceral proof of D1 you have. It also verifies
that D4's telemetry kill actually worked — if pyannote still tries to reach
`otel.pyannote.ai`, you'll find out here rather than from a judge.

Do this **before** the demo, not during, so a surprise is yours and not the
audience's.

Have `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` set (0e) and every weight
pre-cached. A lazy metadata fetch on a cached model is the classic way a
"fully local" run dies with Wi-Fi off, and it fails as a hang rather than a
clean error.

Confirm the telemetry kill is actually in effect and not just in the profile —
the env var must be set **above** the pyannote import to do anything.

**Done when:** the full pipeline completes with no network, and nothing in the
logs attempted an outbound connection.

## 4c — Rehearse · HUMAN

Whoever presents has to defend these cold, without notes:

**Drug scope** (PRESENTATION-NOTES item 1) — what resolves, what doesn't, and
why *Prescribable* RxNorm specifically. Compounded preparations,
investigational drugs and supplements will not resolve. Say it before anyone
asks.

**No interaction checking** (item 1) — this is a credibility win, not a gap.
NLM retired the RxNav interaction API in January 2024 with no replacement,
DrugBank's academic downloads are paused, and DDInter is missing ATC classes
C, G, J, M, N and S — statins, antihypertensives, antiarrhythmics,
antibiotics, opioids, benzodiazepines, antidepressants, antipsychotics. For an
elderly polypharmacy patient the free interaction data is missing nearly every
drug they actually take. *We chose not to ship a checker that fails silently
on real input.*

**Two-speaker limitation** (item 6) — a geriatrics-literate judge will ask
about the adult child in the room. Do not claim you handle multi-party
consultations. Claim you detect when you might not be able to.

**Liability** (D11) — it sits with the attesting clinician, exactly as with a
human scribe. The tool drafts, a licensed professional signs, and no model
output reaches a patient unattended.

**openFDA disclaimer** (item 2) — their terms say "not validated for clinical
use". Consistent with your design, since you cite label text rather than
asserting claims. Have it ready.

**Consent** (item 3, D27) — the patient consents before recording,
`Session.consent` is required, and the printed page says so. Expect this
immediately after the privacy question, and know that Massachusetts is an
all-party-consent state with a criminal wiretap statute. Our audio is teammate
role-play, so the demo never created PHI and was never in scope for it — but
the product has the step either way.

**What span verification does not prove** — if a judge is sharp, they will ask
whether checking the quote exists proves the output is right. It does not, and
saying so first is the strong move: the model can attach a real quote to the
wrong drug. That is why cross-turn association is detected by comparing offsets
and rendered expanded rather than collapsed. *"We know exactly which part of
this we cannot verify, and it is the part we put in front of the doctor."*

**Done when:** someone outside the team can ask all seven and get a confident
answer.

## 4d — Final drug check

Re-verify every drug in the script resolves. Do this **after** any RxNorm
reload or index rebuild — a rebuild that silently drops a TTY is the kind of
thing that only shows up on stage.

Check the **salt table** survived the rebuild too (A5.5) — bare "metoprolol"
should come back `salt_unspecified` with both candidates. A rebuild that
silently drops a TTY is the thing that only shows up on stage, and `PIN` is the
newest entry in the index.

**Done when:** every script drug resolves, checked against the final build, and
the salt flag still fires.

---

## The demo itself

1. **Short clip, live, Wi-Fi off.** The credibility moment.
2. The fuzzy-match beat — *"you said metropolol, we matched metoprolol"*. Your
   knowledge base catching an error the model couldn't.
2b. The salt beat, if you want a second one — *"the doctor said metoprolol.
   There are two, succinate is once daily and tartrate is twice daily, and he
   didn't say which."* Not an error and not a failure: a finding. It is the
   same shape as "take as directed", and it is the knowledge base knowing
   something the transcript alone cannot tell you.
3. A blocking item resolved by the clinician in a few seconds.
4. Approve → the audio is destroyed → paper comes out.
5. The long pre-computed file as evidence of scale.

What makes it land is that nothing is staged as a test. The product just
quietly does the right thing in situations that happen in every clinic —
which is the argument you chose in Q2, and it's stronger than a side-by-side
against ChatGPT would have been.

## Phase 4 is done when

- [ ] long file pre-computed **and exempt from the sweep**
- [ ] Wi-Fi-off run clean, no outbound attempts, offline env vars set
- [ ] all seven judge questions answerable cold
- [ ] every script drug verified against the final build
