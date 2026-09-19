# Phase 2 · Track D — Review UI + output

**Goal:** a clinician reviews and signs in under 60 seconds; the patient gets
paper they can actually read.

**Blocked by:** contract 1a and fixture 1c. **Not blocked by Track B or C.**

---

## D1 — App shell

localhost web app (D6). Two audiences, one product: the **clinician** operates
the screen, the **patient** receives the artifact it prints.

Those are different design problems. The screen is dense, keyboard-driven,
built for someone with fifteen minutes per visit. The paper is large-type,
high-contrast, built for a 78-year-old.

**Done when:** it serves, loads the fixture, and renders something.

## D2 — Review list

D9's 60-second budget drives everything here. Real visits run 15–20 minutes;
a five-minute approval step means nobody ever uses this.

So: **only blocking items demand attention.** Verified content stays collapsed
unless asked for. The eye should land on the two things that need a decision,
not scan twenty things that don't.

Show the honest count up front — *"14 items confirmed, 2 need your ear"* — not
just the confirmed number. Under-claiming is the product.

**Done when:** the fixture renders with exactly its two blocking items
demanding attention and the rest collapsed.

## D3 — Audio playback

Click any line, hear the doctor say it, cued to the word offset.

**This is clinician-only** (D8, Collision 1). The patient's copy carries no
audio affordance at all. Provenance is how the doctor verifies in seconds;
the paper then carries the doctor's authority, not the model's confidence.

Cue to `char_offset` → the word's `start` time. Auto-cue flagged items to the
uncertain word specifically, not the start of the turn.

**Done when:** clicking a line plays the right two seconds.

## D4 — Blocking-item resolution

Keyboard-only. The doctor supplies the value; they're the one who said it.

The two blocking cases:

- **ambiguous attribution on a dose** — who said this?
- **contradiction** — you said 20 mg at 3:10 and 10 mg at 11:45; which?

For contradictions, show both with both timestamps and let them pick. Don't
pre-select.

**Done when:** both blocking types are resolvable without touching the mouse,
and resolution unblocks the approve action.

## D5 — Action card template

**Templated**, not generated (D7, Q10c). Fixed sentence skeletons with
extracted values slotted in:

> Dr. —— increased your **metoprolol** from **25 mg** to **50 mg**.
> Take **one tablet twice daily**, with food.

Contents: medications and changes, appointments, tests ordered, red-flag
instructions. Nothing else.

Dates print **both** forms — *"three weeks from today, which is Friday,
October 10"* (D18).

**Done when:** the fixture's verified items render, and no LLM-authored string
appears anywhere in the output.

## D6 — Extractive summary

**Selected verbatim quotes**, grouped under fixed headings (D7, Q10a):
"Why you came in" / "What the doctor found" / "What happens next".

The model chose which spans go where; it wrote none of the words.

Verbatim quotes read slightly rough. **That roughness is an asset** — it looks
like evidence, not content. Do not smooth it.

**Done when:** every line in the summary is traceable to a transcript span.

## D7 — Print stylesheet

Accessibility floor, non-negotiable:

- 18px minimum body text
- real contrast, no information carried by color alone
- tap/read targets sized for a shaky hand
- short sentences, generous leading

Footer names the responsible human (D10, Q25b):

> *Prepared from a recording of your visit and reviewed by Dr. ——,
> Sept 19, 2026.*

No "AI GENERATED" banner. It manufactures the exact distrust the product
dissolves, and misrepresents the system — by the time it prints, a doctor has
attested to every line.

**Done when:** a print preview is legible at arm's length and the footer
carries a real name and date.

## D8 — Approve

Three things happen, atomically:

1. **shred the audio** (D2, Q19a) — the recording's only job was enabling
   review; the doctor signed, so it's gone
2. write the local FHIR `DocumentReference` (D26), **byte-identical to the
   printed copy** so the patient and the record never diverge
3. print

Rehearse the sentence that resolves the apparent conflict with D1:
*"nothing goes to a third party — the only destination is the provider's own
record system, which already holds this patient's chart."*

**Done when:** approving deletes the audio file, writes the FHIR resource, and
the two outputs match.

## D9 — Expiry sweep

Unapproved sessions expire after **24 hours** (D3, Q23a) — audio *and*
extracted data. A structured list of someone's medications is PHI without the
recording.

This closes the hole in delete-on-approval: without it, a session nobody signs
is retained forever, which is the opposite of the policy.

The claim you get to make: *"audio exists until the doctor signs, or 24 hours,
whichever comes first. There is no third case."* A policy statable in one
sentence with no exceptions is worth more than a flexible one.

**Done when:** a backdated unapproved session is swept, audio and data both.

---

## Track D is done when

- [ ] only blocking items demand attention; the rest collapse
- [ ] click-to-play lands correctly
- [ ] both blocking types resolve keyboard-only
- [ ] no LLM-authored prose reaches the page
- [ ] print is legible at 18px+ with the clinician footer
- [ ] approve shreds, writes FHIR, and prints
- [ ] expiry sweep works
