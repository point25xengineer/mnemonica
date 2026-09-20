"""U3/U4/U5 — the clinician's screen, as data.

D9 gives this screen sixty seconds, and that budget decides every question
here. Only blocking items demand attention. Everything that verified
collapses. The eye should land on the things that need a decision, not scan
twenty that don't.

**The screen asks questions; it does not report state.** The first build put
Track C's own vocabulary on the glass — `D16.7`, `turn 28 · clinician ·
140.8s`, `weakest word "metoprolol," p=0.85` — which is exactly the
information a doctor cannot act on and must read past. `QUESTIONS` below turns
each category into the one sentence the clinician answers. The provenance
still exists and is one keypress away (`show_details`), because it is what
makes an answer checkable; it is just not the default view.

Two rules that look like details and are not:

* **The discarded count is not optional.** D16 category 1 drops fabrications
  silently, which is right about the item and wrong about the number. On a
  page where everything verified is collapsed, a silently deleted medication
  looks exactly like one the model never found. The clinician never sees the
  fabricated text; they do see that something was thrown away.
* **Category 8 renders expanded.** A sig taken from a different turn than its
  drug is the one failure span verification structurally cannot catch — both
  quotes are genuine — so it does not get to hide among the things that
  actually verified.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from visitnotes.contracts import Session
from visitnotes.render import actioncard
from visitnotes.render.audio import AudioCue, cue_for
from visitnotes.render.model import (
    Extraction,
    Item,
    Quote,
    Resolution,
    item_is_resolved,
)

__all__ = [
    "ReviewRow",
    "ReviewFlag",
    "ReviewOption",
    "Evidence",
    "QUESTIONS",
    "build_review",
    "header_line",
]


QUESTIONS: dict[int, str] = {
    2: "A number was hard to hear.",
    3: "We couldn’t place the voice that said this.",
    4: "No match in the drug list.",
    5: "No dose was discussed.",
    6: "Raised, never settled.",
    7: "Two different doses were said. Which one?",
    8: "The instructions came from a different moment than the drug.",
}
"""One short sentence per D16 category, in the doctor's language.

Track C's `reason` strings are written for the people debugging the pipeline
(*"dose stated in a turn with no confident speaker role"*). They are correct
and they are not what someone with a patient in the chair should have to
parse. Anything not in this map falls back to the recorded reason, so a new
category degrades to verbose rather than to blank.
"""


@dataclass
class Evidence:
    """A quote, and the provenance behind it.

    `detail` is assembled here but only rendered when the clinician asks for
    it. Building it always costs nothing and means the toggle is a CSS-level
    decision rather than a second pass over the data.
    """

    text: str
    role: str
    cue: AudioCue | None
    detail: str
    verified: bool


@dataclass
class ReviewOption:
    """One answer, with the audio that justifies it.

    The option and its evidence are the same thing on this screen: *"which
    dose did you mean"* is answered by hearing both. Keeping them apart made
    the doctor match a button to a quote three lines above it.
    """

    label: str
    value: str
    cue: AudioCue | None
    chosen: bool


@dataclass
class ReviewFlag:
    index: int
    d16_category: int | None
    blocking: bool
    question: str
    render: str
    evidence: list[Evidence]
    options: list[ReviewOption]
    chosen: str | None
    merge_target: str | None
    """An item this one is probably a duplicate of.

    The fixture's category-4 flag says `merge_into:med-lisinopril` — the
    patient's *"the other blood pressure pill"* is the lisinopril already on
    the list. Parsing that and never offering it is how a flag becomes
    decoration.
    """

    @property
    def quiet(self) -> bool:
        """Nothing to do here — a note, not a question.

        These collapse into a single muted line. Category 5 is the canonical
        case: *"as directed"* is an answer, and dressing it up as a finding is
        what makes the most-correct behaviour in the table look like a
        failure.

        `render == "expanded"` overrides it. Category 8 is non-blocking and
        has no options, so a rule based on those alone demotes it to a
        footnote — which is precisely the hiding U3 forbids, since it is the
        one failure span verification structurally cannot catch.
        """
        if self.render == "expanded":
            return False
        return not self.blocking and not self.options and not self.merge_target

    @property
    def bookkeeping(self) -> bool:
        """A note about the pipeline's own state rather than about the visit.

        `change_kind was not derived from two parsed doses` is true, and the
        screen already answers it: an underived direction gets its own
        *"Is that the right word?"* question, and a non-directional verb needs
        no answer at all. Saying it twice, once in Track C's vocabulary, is
        noise. String-matched on purpose — if Track C rewords it we show a
        slightly verbose note, which degrades the right way.
        """
        return self.quiet and self.question.startswith("change_kind")


@dataclass
class ReviewRow:
    item: Item
    title: str
    kind: str
    expanded: bool
    blocking: bool
    resolved: bool
    dropped: bool
    sentences: list[actioncard.Sentence]
    needs_promotion: bool
    promoted: bool
    cue: AudioCue | None
    quote_text: str | None
    flags: list[ReviewFlag] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.item.id

    @property
    def category_labels(self) -> list[str]:
        return [f"D16.{c}" for c in self.item.d16_categories]

    @property
    def questions(self) -> list[ReviewFlag]:
        return [f for f in self.flags if not f.quiet]

    @property
    def notes(self) -> list[ReviewFlag]:
        return [f for f in self.flags if f.quiet and not f.bookkeeping]

    @property
    def status(self) -> str:
        """The one word in the corner of a collapsed row."""
        if self.dropped:
            return "dropped"
        if self.blocking and self.resolved:
            return "settled"
        if self.blocking:
            return "needs you"
        if self.needs_promotion:
            return "check wording"
        if self.questions:
            return "check"
        return ""


def _question(
    flag_category: int | None,
    reason: str,
    evidence: list[Evidence],
    default_role: str | None = None,
) -> str:
    """The one sentence the clinician answers.

    Category 3 fires for two different situations and needs two different
    sentences: a turn enrollment could not place at all, and a turn that is
    confidently the patient rather than the doctor. *"We couldn\u2019t place the
    voice"* is wrong for the second and *"the patient said this"* is a claim
    we cannot make about the first.
    """
    if flag_category == 3:
        # A flag need not carry evidence — the fixture's patient-attribution
        # flag does not, because the item's own mention quote IS the evidence.
        roles = {e.role for e in evidence} or {default_role}
        if roles == {"other"}:
            return "The patient said this, not the doctor."
    if flag_category in QUESTIONS:
        return QUESTIONS[flag_category]
    return reason


def _detail(quote: Quote, cue: AudioCue | None) -> str:
    who = {"clinician": "doctor", "other": "patient", "unknown": "unplaced voice"}
    parts = [
        who.get(quote.turn_role, quote.turn_role),
        f"{quote.audio_start:.0f}s",
        f"turn {quote.turn_id}",
    ]
    if cue:
        parts.append(f"weakest “{cue.focus_word}” p={cue.focus_probability:.2f}")
    return " · ".join(parts)


def _evidence(session: Session, quote: Quote, *, flagged: bool) -> Evidence:
    cue = cue_for(session, quote, flagged=flagged)
    return Evidence(
        text=quote.text,
        role=quote.turn_role,
        cue=cue,
        detail=_detail(quote, cue),
        verified=quote.verify_against(session),
    )


def _sentences(
    item: Item, clinician_name: str, resolution: Resolution | None
) -> list[actioncard.Sentence]:
    promoted = bool(resolution and resolution.promoted)
    if item.kind == "medication":
        return actioncard.medication_sentences(
            item, clinician_name, promoted=promoted
        )
    if item.kind == "appointment":
        return [actioncard.appointment_sentence(item)]
    if item.kind == "red_flag":
        return [actioncard.red_flag_sentence(item)]
    quote = item.primary_quote
    if quote:
        return [actioncard.Sentence((actioncard.Fragment(quote.text),))]
    return []


def build_review(
    extraction: Extraction,
    session: Session,
    *,
    clinician_name: str,
    resolutions: dict[str, Resolution] | None = None,
) -> list[ReviewRow]:
    """Rows in the order the eye should travel: blocking, then expanded, then
    the collapsed remainder. `Extraction.items` already sorts that way."""
    resolutions = resolutions or {}
    rows: list[ReviewRow] = []

    for item in extraction.items:
        res = resolutions.get(item.id)
        quote = item.primary_quote
        flagged = bool(item.flags)
        sentences = _sentences(item, clinician_name, res)

        flags: list[ReviewFlag] = []
        for index, flag in enumerate(item.flags):
            evidence = [_evidence(session, q, flagged=True) for q in flag.evidence]
            chosen = res.settles(index) if res else None
            labels = flag.options()

            # An option that came from a piece of evidence carries that
            # evidence's audio, so the button itself is the thing you play.
            options = [
                ReviewOption(
                    label=label,
                    value=label,
                    cue=(
                        evidence[position].cue
                        if not flag.choices and position < len(evidence)
                        else None
                    ),
                    chosen=chosen == label,
                )
                for position, label in enumerate(labels)
            ]

            flags.append(
                ReviewFlag(
                    index=index,
                    d16_category=flag.d16_category,
                    blocking=flag.blocking,
                    question=_question(
                        flag.d16_category,
                        flag.reason,
                        evidence,
                        default_role=quote.turn_role if quote else None,
                    ),
                    render=flag.render,
                    evidence=evidence,
                    options=options,
                    chosen=chosen,
                    merge_target=(
                        flag.suggested_action.split(":", 1)[1]
                        if (flag.suggested_action or "").startswith("merge_into:")
                        else None
                    ),
                )
            )

        rows.append(
            ReviewRow(
                item=item,
                title=item.title,
                kind=item.kind,
                expanded=item.render_expanded,
                blocking=item.is_blocking,
                resolved=item_is_resolved(item, res),
                dropped=bool(res and res.dropped),
                sentences=sentences,
                needs_promotion=any(s.needs_promotion for s in sentences),
                promoted=bool(res and res.promoted),
                cue=cue_for(session, quote, flagged=flagged) if quote else None,
                quote_text=quote.text if quote else None,
                flags=flags,
            )
        )
    return rows


def header_line(extraction: Extraction) -> str:
    """*"3 confirmed · 1 needs your ear · 1 discarded"* — the honest count.

    Under-claiming is the product. The discarded number is in here because a
    number that only ever goes up is marketing, not a status line.
    """
    counts = extraction.header()
    parts = [f"{counts['confirmed']} confirmed"]
    if counts["blocking"]:
        parts.append(f"{counts['blocking']} needs your ear")
    if counts["needs_confirmation"]:
        parts.append(f"{counts['needs_confirmation']} to confirm")
    if counts["loose_threads"]:
        parts.append(f"{counts['loose_threads']} left open")
    parts.append(f"{counts['discarded']} discarded")
    return " · ".join(parts)
