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

**Done when:** the long result loads instantly from disk.

## 4b — Wi-Fi off, full run

Turn Wi-Fi off and run the short clip end to end.

This is the cheapest and most visceral proof of D1 you have. It also verifies
that D4's telemetry kill actually worked — if pyannote still tries to reach
`otel.pyannote.ai`, you'll find out here rather than from a judge.

Do this **before** the demo, not during, so a surprise is yours and not the
audience's.

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

**Done when:** someone outside the team can ask all five and get a confident
answer.

## 4d — Final drug check

Re-verify every drug in the script resolves. Do this **after** any RxNorm
reload or index rebuild — a rebuild that silently drops a TTY is the kind of
thing that only shows up on stage.

**Done when:** every script drug resolves, checked against the final build.

---

## The demo itself

1. **Short clip, live, Wi-Fi off.** The credibility moment.
2. The fuzzy-match beat — *"you said metropolol, we matched metoprolol"*. Your
   knowledge base catching an error the model couldn't.
3. A blocking item resolved by the clinician in a few seconds.
4. Approve → the audio is destroyed → paper comes out.
5. The long pre-computed file as evidence of scale.

What makes it land is that nothing is staged as a test. The product just
quietly does the right thing in situations that happen in every clinic —
which is the argument you chose in Q2, and it's stronger than a side-by-side
against ChatGPT would have been.

## Phase 4 is done when

- [ ] long file pre-computed
- [ ] Wi-Fi-off run clean, no outbound attempts
- [ ] all five judge questions answerable cold
- [ ] every script drug verified against the final build
