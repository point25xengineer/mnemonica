"""C3 — the per-turn extraction prompt. TOOLS.md §0, D15.

The prompt has one job, and it is the verbatim rule:

> Pass text exactly as it appears in the transcript. Not corrected, not
> normalized, not expanded. If the transcript says `metropolol`, the argument
> is `metropolol`.

A model that "helpfully" fixes a spelling produces a string that is not in the
transcript, which is indistinguishable from fabrication and is correctly
dropped by C4. So the prompt does not merely forbid correcting — it explains
*why the model does not need to*: the resolver matches phonetically, recovers
the intended drug, and reports that it corrected something. Helping is the
failure mode; the model's job is to point.

**Chunked by speaker turn, not by token window** (D15). Three things fall out
of that: attribution comes from the chunk's own label rather than from the
model, a bad extraction is isolated to one turn instead of poisoning a batch,
and transcript length stops mattering — a 3-minute clip and a 20-minute visit
present the same size input.

The turn is shown with a little context around it, because a sig often lands a
turn or two from the drug it belongs to (that gap is D16 category 8, and C4.5
is what catches it). Context is **labelled as context** and the model is told
to quote only from the current turn: quotes taken from a neighbour would pass
span verification and silently move the attribution the whole design rests on.

`enable_thinking=False`, and the reason is not what 0i first assumed. Thinking
tokens do not break the grammar — the mask hides them and the JSON stays valid
either way. What drifts is quote *selection*: thinking-on returned a
`sig_quote` that swallowed the entire dose sentence where thinking-off returned
the tight clause. A sig quote that smears across a sentence boundary is exactly
the association error C4.5 hunts.
"""

from __future__ import annotations

from mnemonica.contracts import Session, Turn

__all__ = ["SYSTEM", "build_prompt", "CONTEXT_TURNS"]

CONTEXT_TURNS = 2
"""How many neighbouring turns to show, each side. Two is enough to carry a
pronoun's referent ("take it twice a day") without inviting a quote from
outside the current turn."""


SYSTEM = """\
You extract structured facts from one turn of a recorded medical visit.

THE ONE RULE: every string you emit must appear in the CURRENT TURN exactly \
as written there, character for character. Copy it; do not correct spelling, \
do not expand abbreviations, do not convert words to numerals or numerals to \
words, do not tidy punctuation, do not join text that is not adjacent.

If the transcript says "metropolol", you write "metropolol". You do not need \
to fix misheard drug names: a drug database matches them phonetically, \
recovers the intended drug far more reliably than a guess would, and reports \
that it made a correction — which a silent fix cannot. Correcting a name \
produces text that is not in the transcript, and text that is not in the \
transcript is discarded.

Quote ONLY from the CURRENT TURN. Earlier and later turns are shown for \
context so you can tell what a pronoun refers to. They are not yours to quote.

Most turns contain nothing worth extracting. Empty lists are the correct, \
expected answer — never invent an item to fill one.

What each field wants:
- medications.medication.mention_quote: the drug name alone, as spoken. Not \
the dose, not the frequency.
- medications.sig[].sig_quote: a dosing instruction, as spoken. If the \
clinician gave none ("take it as directed", "same as before"), quote that \
phrase anyway — "no dose was specified" is a real finding. If two different \
instructions were given, emit two entries; do not choose between them.
- medications.change_evidence_quote: the words that show what changed.
- medications.change_kind: one of new, increased, decreased, stopped, \
continued, unchanged.
- appointments.when.phrase_quote: a time expression, as spoken. Keep enough \
of it to carry direction: "come back in three weeks", not "three weeks". Do \
not compute a date; you do not know today's date and must not guess it.
- red_flags.instruction_quote: what to watch for and when to call.
- loose_threads.topic_quote: something the clinician said they might do or \
would decide later and then never settled — "we may need to adjust the other \
one as well", with no dose and no date anywhere. Not a plan that was carried \
out in the same breath.
- summary_quotes: at most ONE quote from this turn, and only if the turn \
directly answers one heading. Most turns answer none. Pleasantries, \
acknowledgements and "okay, I'll call" answer nothing. The three headings are \
narrow and do not overlap:
  * why_you_came_in - a SYMPTOM or problem the patient reports. What they \
feel, where, for how long. Usually spoken by the patient. Not what the doctor \
decides to do about it. A symptom usually arrives wrapped in a polite answer \
- "oh, not too bad, but my feet have been bothering me" - and patients often \
play it down. Quote the symptom clause, not the pleasantry around it, and do \
not skip a symptom because the patient called it nothing.
  * what_the_doctor_found - a FINDING, test result or diagnosis the clinician \
states. A number, a reading, a name for the problem. "Your A1C came back at \
seven point four" is a finding. "I'm sending you for bloods" is not - that is \
a plan.
  * what_happens_next - a recommendation that is NOT already captured \
elsewhere. Medications, appointments and call-the-office warnings each have \
their own field and must NOT be repeated here. This heading is for the \
leftovers: lifestyle advice, a referral, something to watch for.

Answer with JSON only."""


def _render(turn: Turn, *, current: bool) -> str:
    who = {"clinician": "DOCTOR", "other": "PATIENT/COMPANION",
           "unknown": "UNIDENTIFIED SPEAKER"}[turn.role]
    tag = "CURRENT TURN" if current else "context"
    return f"[{tag} · turn {turn.id} · {who}]\n{turn.text}"


def build_prompt(session: Session, turn: Turn) -> str:
    """The user message for one turn, with `CONTEXT_TURNS` either side."""
    i = session.turns.index(turn)
    lo = max(0, i - CONTEXT_TURNS)
    hi = min(len(session.turns), i + CONTEXT_TURNS + 1)
    blocks = [
        _render(t, current=(t.id == turn.id)) for t in session.turns[lo:hi]
    ]
    return (
        "\n\n".join(blocks)
        + f"\n\nExtract from turn {turn.id} only. Quote it exactly."
    )
