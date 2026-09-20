# Phase 2 · Track D — Review UI + output

**Goal:** a clinician reviews and signs in under 60 seconds; the patient gets
paper they can actually read.

**Blocked by:** contract 1a and fixture **1c-ii** (`golden_extraction.json`).
**Not blocked by Track B or C.**

A `Session` has turns and words but no extracted items and no dispositions, so
`golden_visit.json` alone cannot render a review list. If 1c-ii does not exist,
say so in PLAN.md's Blockers table rather than waiting on Track C.

> **Steps here are U1–U10, not D1–D9.** `D1`–`D27` are architecture decisions
> in SPEC.md, and this file used to use both meanings at once — *"D8 — Approve:
> shred the audio (D2)"* pointed at two different documents in one sentence.
> Every `D`-number below refers to SPEC.md.

---

## U1 — App shell

localhost web app (D6). Two audiences, one product: the **clinician** operates
the screen, the **patient** receives the artifact it prints.

Those are different design problems. The screen is dense, keyboard-driven,
built for someone with fifteen minutes per visit. The paper is large-type,
high-contrast, built for a 78-year-old.

**Done when:** it serves, loads the fixture, and renders something.

## U2 — Consent capture · D27

Before recording starts, not after. `Session.consent` is a required field and a
session cannot reach review without it.

One screen, one control: *"Patient informed and consented to recording"*, plus
verbal/written and a timestamp. It persists into the `Session` and prints as a
line on the patient's copy (U8).

Roughly fifteen minutes of work, and it closes the largest gap in the spec —
nothing in the original pipeline turned on a microphone with the patient's
knowledge. Massachusetts is an all-party-consent jurisdiction and its wiretap
statute is criminal rather than civil, which is worth knowing given where the
demo is happening. Our own audio is teammate role-play so the demo was never in
scope for it; the product needs the step regardless.

**Done when:** recording cannot start without it, and the value reaches the
printed footer.

## U3 — Review list

D9's 60-second budget drives everything here. Real visits run 15–20 minutes;
a five-minute approval step means nobody ever uses this.

So: **only blocking items demand attention.** Verified content stays collapsed
unless asked for. The eye should land on the two things that need a decision,
not scan twenty things that don't.

Show the honest count up front — *"14 confirmed · 2 need your ear · 1
discarded"* — not just the confirmed number. Under-claiming is the product.

**The discarded count is not optional.** D16 category 1 drops fabrications
silently, which is right about the *item* and wrong about the *number*: a
silently deleted medication looks exactly like one the model never found, and
since everything verified stays collapsed, an omission is invisible on a page
that looks complete. The clinician never sees the fabricated text. They do see
that something was thrown away.

**D16 category 8 renders expanded.** Cross-turn association — a sig taken from
a different turn than its drug — is the one failure span verification cannot
catch, so it does not get to hide inside the collapsed section with everything
that actually verified. Both quotes, both timestamps, side by side.

**Done when:** the fixture renders with exactly its two blocking items
demanding attention, its category-8 item expanded, the discarded count in the
header, and the rest collapsed.

## U4 — Audio playback

Click any line, hear the doctor say it, cued to the word offset.

**This is clinician-only** (D8, Collision 1). The patient's copy carries no
audio affordance at all. Provenance is how the doctor verifies in seconds;
the paper then carries the doctor's authority, not the model's confidence.

Cue to `char_offset` → the word's `start` time. Auto-cue flagged items to the
uncertain word specifically, not the start of the turn.

**Done when:** clicking a line plays the right two seconds.

## U5 — Blocking-item resolution

Keyboard-only. The doctor supplies the value; they're the one who said it.

The two blocking cases:

- **ambiguous attribution on a dose** — who said this?
- **contradiction** — you said 20 mg at 3:10 and 10 mg at 11:45; which?

For contradictions, show both with both timestamps and let them pick. Don't
pre-select.

**Done when:** both blocking types are resolvable without touching the mouse,
and resolution unblocks the approve action.

## U6 — Action card template

**Templated**, not generated (D7, Q10c). Fixed sentence skeletons with
extracted values slotted in:

> Dr. —— increased your **metoprolol** from **25 mg** to **50 mg**.
> Take **one tablet twice daily**, with food.

Contents: medications and changes, appointments, tests ordered, red-flag
instructions. Nothing else.

Dates print **both** forms — *"three weeks from today, which is Friday,
October 9"* (D18). Check the day-of-week against a calendar; the spec's own
example had it wrong, and that is the error printing both forms exists to let a
patient catch.

**Two things this template cannot assume:**

- **The verb is model-chosen unless derived.** `increased`/`decreased` comes
  from a closed enum the model picked. Print it as fact only when
  `change_kind_derived` is true (the pipeline computed it from two parsed
  doses); otherwise it is prefilled and flagged, and the clinician's click
  promotes it. A closed enum guarantees well-formed, not correct, and this is
  the headline sentence.
- **There may be no prior dose.** Nothing in this system reads a chart, so
  *"from 25 mg"* exists only if the clinician said it aloud. Needs a variant —
  *"Dr. —— changed your metoprolol to 50 mg"* — rather than a blank or an
  invented baseline.

**Done when:** the fixture's verified items render, no LLM-authored string
appears anywhere in the output, and an underived `change_kind` is flagged
rather than printed.

## U7 — Extractive summary

**Selected verbatim quotes**, grouped under fixed headings (D7, Q10a):
"Why you came in" / "What the doctor found" / "What happens next".

The model chose which spans go where; it wrote none of the words.

Verbatim quotes read slightly rough. **That roughness is an asset** — it looks
like evidence, not content. Do not smooth it.

**Watch the attribution with three people in the room.** "Why you came in" is
filled from non-clinician turns, and `role` is only `clinician`/`other`/
`unknown` — with an adult child present, that heading can print their words as
the patient's. The dose-safety rule (D19) only guards doses. Flag or restrict
quotes attributed to the patient when B6 raised its unexpected-speaker check.

**Done when:** every line in the summary is traceable to a transcript span.

## U8 — Print stylesheet

Accessibility floor, non-negotiable:

- 18px minimum body text
- real contrast, no information carried by color alone
- tap/read targets sized for a shaky hand
- short sentences, generous leading

Footer names the responsible human (D10, Q25b):

> *Prepared from a recording of your visit, made with your consent, and
> reviewed by Dr. ——, Sept 19, 2026.*

The consent clause is D27 and comes from `Session.consent` (U2) — if it is not
on the page it is a UI affordance rather than a record.

No "AI GENERATED" banner. It manufactures the exact distrust the product
dissolves, and misrepresents the system — by the time it prints, a doctor has
attested to every line.

**Done when:** a print preview is legible at arm's length and the footer
carries a real name, a date, and the consent clause.

## U9 — Approve

Three things happen, atomically:

1. **shred the audio** (D2, Q19a) — the recording's only job was enabling
   review; the doctor signed, so it's gone. **Shred the session's logs and
   scratch files with it**: a dropped-quote log line carries transcript text,
   so "audio exists until the doctor signs" is only true if the sweep runs
   against the session *directory*, not two file paths
2. write the local FHIR `DocumentReference` (D26) whose
   `content.attachment` holds **the exact bytes we rendered for print** — one
   render, two destinations, so the patient's copy and the record cannot
   diverge. (Not "byte-identical to the printed copy": a FHIR resource and a
   sheet of paper are different encodings. The guarantee is the single render.)
3. print

Rehearse the sentence that resolves the apparent conflict with D1:
*"nothing goes to a third party — the only destination is the provider's own
record system, which already holds this patient's chart."*

**Done when:** approving deletes the audio file **and the session's logs**,
writes the FHIR resource, and the two outputs come from one render.

## U10 — Expiry sweep

Unapproved sessions expire after **24 hours** (D3, Q23a) — audio *and*
extracted data. A structured list of someone's medications is PHI without the
recording.

This closes the hole in delete-on-approval: without it, a session nobody signs
is retained forever, which is the opposite of the policy.

The claim you get to make: *"audio exists until the doctor signs, or 24 hours,
whichever comes first. There is no third case."* A policy statable in one
sentence with no exceptions is worth more than a flexible one.

**Exempt the pre-computed demo session.** Phase 4a runs the long visit through
the pipeline and saves the result — an unapproved session, sitting on disk. If
you build it the night before and demo the next afternoon, this sweep deletes
your demo. Flag it, or do not run the sweep on demo day.

**Done when:** a backdated unapproved session is swept — audio, data and logs —
and a session flagged as a demo fixture survives.

---

## Track D is done when

- [x] consent is captured before recording and prints on the page (U2, D27)
- [x] only blocking items demand attention; the rest collapse
- [x] the discarded count is in the header
- [x] category-8 items render expanded, not collapsed
- [x] click-to-play lands correctly
- [x] both blocking types resolve keyboard-only
- [x] no LLM-authored prose reaches the page; underived `change_kind` is flagged
- [x] print is legible at 18px+ with the clinician footer
- [x] approve shreds audio **and logs**, writes FHIR, and prints
- [x] expiry sweep works, and skips flagged demo sessions
