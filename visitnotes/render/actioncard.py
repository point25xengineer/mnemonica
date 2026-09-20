"""U6 — the action card. Templated, never generated (D7, Q10c).

Every sentence on the patient's page comes from a skeleton in this file with
extracted values slotted into it. No string here was written by a model, and
`tests/test_track_d.py` asserts that the rendered page contains no span the
model authored.

Two things the template is not allowed to assume, both of which produce a
confidently wrong headline sentence if you let them slide:

* **The verb.** `increased` / `decreased` came from a closed enum the model
  picked, and a closed enum guarantees well-formed, not correct. It prints as
  fact only when `change_kind_derived` is true — the pipeline computed it from
  two parsed doses — or when the clinician has promoted it with a click.
* **The prior dose.** Nothing in this system reads a chart, so *"from 25 mg"*
  exists only if the clinician said it out loud. When there is no baseline the
  sentence changes shape rather than leaving a blank or inventing one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Literal

from visitnotes.render.model import Item, Resolution

__all__ = ["Fragment", "Sentence", "MedicationRow", "medication_sentences",
           "medication_row", "appointment_sentence", "red_flag_sentence",
           "format_dose", "format_frequency"]


@dataclass(frozen=True)
class Fragment:
    """A run of text. `strong` is the large-type emphasis on the values a
    patient will look for — the drug, the dose, the date."""

    text: str
    strong: bool = False


@dataclass(frozen=True)
class Sentence:
    """One templated line, plus whether it may be stated as fact yet.

    `needs_promotion` is U6's flag: the sentence is prefilled and shown to the
    clinician, but it does not print until they say the verb is right.
    """

    fragments: tuple[Fragment, ...]
    needs_promotion: bool = False
    promotion_reason: str | None = None

    def plain(self) -> str:
        return "".join(f.text for f in self.fragments)


# -- value formatting ----------------------------------------------------
# Deliberately boring. Every one of these takes a parsed number and returns
# the words a patient reads; none of them takes free text.


def format_dose(amount: float | None, unit: str | None) -> str | None:
    if amount is None or unit is None:
        return None
    whole = int(amount)
    number = str(whole) if amount == whole else f"{amount:g}"
    return f"{number} {unit}"


def format_frequency(per_day: float | None) -> str | None:
    if per_day is None:
        return None
    words = {1: "once a day", 2: "twice a day", 3: "three times a day",
             4: "four times a day"}
    whole = int(per_day)
    if per_day == whole and whole in words:
        return words[whole]
    return f"{per_day:g} times a day"


def format_timing(timing: Iterable[str]) -> str:
    """The parser emits a closed vocabulary here (`with food`, `in the
    morning`), so it is safe to append verbatim."""
    parts = [t for t in timing if t]
    return ", " + " and ".join(parts) if parts else ""


def format_date_both_ways(resolved: date, original_phrase: str) -> str:
    """D18 — print the relative phrase *and* the calendar date.

    The weekday is recomputed from the date here rather than taken from the
    resolver's `display_string`. Printing both forms exists so a patient can
    catch a mismatch; a UI that copies a precomputed sentence containing the
    weekday can only reproduce the resolver's mistake.
    """
    return (
        f"{original_phrase} from today, which is "
        f"{resolved.strftime('%A, %B')} {resolved.day}"
    )


# -- medication ----------------------------------------------------------


def _clinician(clinician_name: str) -> str:
    return clinician_name.strip() or "Your doctor"


def _settled_quotes(item: Item, resolution: Resolution | None) -> set[str]:
    """The sig quotes the clinician picked when settling a category 7 flag.

    Category 7's options *are* the competing sig quotes (`Flag.options`), so a
    settled contradiction is the clinician naming which instruction is the
    real one. Nothing downstream may then print a different dose — which is
    what 3b's first real run did.
    """
    if resolution is None:
        return set()
    return {
        choice
        for i, flag in enumerate(item.flags)
        if flag.blocking and flag.d16_category == 7
        for choice in (resolution.settles(i),)
        if choice
    }


def _select_sig(
    item: Item, settled: set[str] | None = None
) -> dict[str, Any] | None:
    """Which of an item's sigs is the one the patient is told to follow.

    **The clinician's answer wins outright.** If they settled a category 7
    contradiction, `settled` holds the quote they chose and that sig is the
    instruction; the others were the losing side of a question they have
    already answered. Falling back to parse confidence there printed *"from
    25 mg to 50 mg"* above *"The dose is 25 mg"* on the same card — the first
    end-to-end run's worst finding, and invisible on the fixture because the
    fixture was never carried through an approval.

    Otherwise: highest parse confidence among the sigs that are not themselves
    the reason the item is blocking. Sigs are never merged across turns:
    combining a dose from turn 12 with a frequency from turn 20 is exactly the
    cross-turn smear D16 category 8 exists to catch, and doing it silently in
    a template would launder the very thing the flag is warning about.
    """
    sigs = [s for s in (item.raw.get("sig") or []) if not s.get("blocking_reason")]
    if settled:
        chosen = [s for s in sigs if (s.get("quote") or {}).get("text") in settled]
        if chosen:
            return max(chosen, key=lambda s: s.get("parse_confidence") or 0.0)
    usable = [s for s in sigs if s.get("status") in ("parsed", "partial")]
    if not usable:
        return sigs[0] if sigs else None
    return max(usable, key=lambda s: s.get("parse_confidence") or 0.0)


def _sig_is_not_specified(item: Item) -> bool:
    """D16 category 5 — *"as directed"* is an answer, not a failure."""
    return any(
        s.get("status") == "not_specified" for s in (item.raw.get("sig") or [])
    )


def medication_sentences(
    item: Item,
    clinician_name: str,
    *,
    promoted: bool = False,
    resolution: Resolution | None = None,
) -> list[Sentence]:
    """The headline change, then how to take it.

    `promoted` is the clinician's click on an underived `change_kind`.
    `resolution` is the rest of their answer — which sig a settled category 7
    contradiction landed on. It is optional so that the review screen, which
    renders before anything is settled, can keep calling this unchanged.
    """
    med = item.raw.get("medication") or {}
    name = med.get("canonical_name")
    # "your" reads correctly in front of a drug name and wrongly in front of
    # the words a patient used for one — "your the other blood pressure pill".
    # The heard text carries its own determiner, so the possessive drops.
    possessive = "your "
    if not name:
        # D16 category 4 — unresolved. The patient's page prints what was
        # actually said rather than a drug we could not name. It is NOT
        # quoted: quotation marks on this page mean a verified verbatim span
        # the doctor said (the red flags, the summary), and a drug reference
        # dropped into a sentence we wrote is not one of those.
        heard = item.primary_quote
        name = heard.text if heard else "a medication"
        possessive = ""

    doctor = _clinician(clinician_name)
    change = item.raw.get("change_kind")
    derived = bool(item.raw.get("change_kind_derived"))
    derivation = item.raw.get("change_kind_derivation") or {}
    to_dose = format_dose(
        (derivation.get("to_dose") or {}).get("amount"),
        (derivation.get("to_dose") or {}).get("unit"),
    )
    from_dose = format_dose(
        (derivation.get("from_dose") or {}).get("amount"),
        (derivation.get("from_dose") or {}).get("unit"),
    )

    settled = _settled_quotes(item, resolution)
    sig = _select_sig(item, settled) or {}
    if settled:
        # The derivation was computed from the whole sig list, including the
        # doses the clinician has just told us were not the instruction. Once
        # they have chosen, the chosen sig is the only dose that may head the
        # card.
        chosen_dose = format_dose(sig.get("dose_amount"), sig.get("dose_unit"))
        if chosen_dose:
            to_dose = chosen_dose
        # "increased from 25 mg to 25 mg" is not a sentence anyone should
        # read. With no distinct baseline left, say what it is now and claim
        # no direction.
        if from_dose == to_dose:
            from_dose = None
    if to_dose is None:
        to_dose = format_dose(sig.get("dose_amount"), sig.get("dose_unit"))

    sentences: list[Sentence] = []
    needs = change in ("increased", "decreased") and not derived and not promoted
    reason = (
        "the word “%s” was chosen by the model, not computed from two "
        "doses — confirm it before this prints" % change
        if needs
        else None
    )

    if change in ("increased", "decreased"):
        verb = change
        if from_dose and to_dose:
            frags = (
                Fragment(f"{doctor} {verb} {possessive}"),
                Fragment(name, strong=True),
                Fragment(" from "),
                Fragment(from_dose, strong=True),
                Fragment(" to "),
                Fragment(to_dose, strong=True),
                Fragment("."),
            )
        elif to_dose:
            # No baseline was spoken. Say what changed, not what it changed
            # from — the chart is not ours to read.
            frags = (
                Fragment(f"{doctor} changed {possessive}"),
                Fragment(name, strong=True),
                Fragment(" to "),
                Fragment(to_dose, strong=True),
                Fragment("."),
            )
            needs = False if derived else needs
        else:
            frags = (
                Fragment(f"{doctor} {verb} {possessive}"),
                Fragment(name, strong=True),
                Fragment("."),
            )
        sentences.append(Sentence(frags, needs_promotion=needs, promotion_reason=reason))
    elif change in ("continued", "unchanged"):
        sentences.append(
            Sentence(
                (
                    Fragment(f"Keep taking {possessive}"),
                    Fragment(name, strong=True),
                    Fragment(" the same way you have been."),
                )
            )
        )
    elif change in ("started", "new"):
        frags = [Fragment(f"{doctor} started you on "), Fragment(name, strong=True)]
        if to_dose:
            frags += [Fragment(", "), Fragment(to_dose, strong=True)]
        frags.append(Fragment("."))
        sentences.append(Sentence(tuple(frags)))
    elif change == "stopped":
        sentences.append(
            Sentence(
                (
                    Fragment(f"{doctor} stopped {possessive}"),
                    Fragment(name, strong=True),
                    Fragment("."),
                )
            )
        )

    if not sentences:
        # No branch matched — an unrecognised `change_kind`, or none at all.
        # The card must still name its medicine: "How to take it: no change
        # was discussed" with no drug attached is what the real run printed
        # for `unchanged`, and it is unusable on paper. A drug the patient
        # cannot identify is worse than a verb we decline to assert, so this
        # says the one thing we are certain of and claims no change.
        sentences.append(
            Sentence(
                (
                    Fragment(f"About {possessive}"),
                    Fragment(name, strong=True),
                    Fragment(":"),
                )
            )
        )

    # How to take it.
    if _sig_is_not_specified(item):
        sentences.append(
            Sentence(
                (
                    Fragment("How to take it: "),
                    Fragment("no change was discussed", strong=True),
                    Fragment(" — keep taking it the way you have been."),
                )
            )
        )
    else:
        dose = format_dose(sig.get("dose_amount"), sig.get("dose_unit"))
        freq = format_frequency(sig.get("frequency_per_day"))
        timing = format_timing(sig.get("timing") or [])
        if dose and freq:
            sentences.append(
                Sentence(
                    (
                        Fragment("Take "),
                        Fragment(dose, strong=True),
                        Fragment(" "),
                        Fragment(freq + timing, strong=True),
                        Fragment("."),
                    )
                )
            )
        elif freq:
            sentences.append(
                Sentence(
                    (
                        Fragment("Take it "),
                        Fragment(freq + timing, strong=True),
                        Fragment("."),
                    )
                )
            )
        elif dose and dose != to_dose:
            # Only when it adds something. The headline already said "to
            # 50 mg"; repeating it as "The dose is 50 mg" reads as a second,
            # separate instruction to someone scanning the page.
            sentences.append(
                Sentence((Fragment("The dose is "), Fragment(dose, strong=True),
                          Fragment(".")))
            )

    salt = med.get("salt_candidates") or []
    if med.get("salt_unspecified") and salt:
        sentences.append(
            Sentence(
                (
                    Fragment("Check the label: your "),
                    Fragment(name, strong=True),
                    Fragment(" may be " + " or ".join(salt) + "."),
                )
            )
        )
    return sentences


@dataclass(frozen=True)
class MedicationRow:
    """One medication as table cells rather than prose (U8b).

    Same slotted values as `medication_sentences`, same templates, same
    verbatim rule — only the shape changes. A row is easier to scan than a
    paragraph when what the reader wants is *which of my pills changed*, and
    scanning is what a patient does with this page at the pharmacy counter.

    Cells are `Sentence`s, not strings, so the large-type emphasis on doses
    survives into the table exactly as it does in the prose version.
    """

    name: str
    change: Sentence | None
    how: Sentence | None
    notes: tuple[Sentence, ...] = ()


_CHANGE_VERB = {
    "increased": "Dose increased",
    "decreased": "Dose decreased",
    "stopped": "Stop taking this",
    "new": "New medicine",
    "continued": "No change",
    "unchanged": "No change",
}


def medication_row(
    item: Item,
    clinician_name: str,
    *,
    promoted: bool = False,
    resolution: Resolution | None = None,
) -> MedicationRow:
    """The table form of `medication_sentences`.

    Deliberately a second reader over the same data rather than a
    reimplementation: every value below comes from the same helpers the prose
    version uses, so the two cannot drift into disagreeing about a dose.
    """
    med = item.raw.get("medication") or {}
    name = med.get("canonical_name")
    if not name:
        heard = item.primary_quote
        name = heard.text if heard else "a medication"

    derivation = item.raw.get("change_kind_derivation") or {}
    from_dose = format_dose(
        (derivation.get("from_dose") or {}).get("amount"),
        (derivation.get("from_dose") or {}).get("unit"),
    )
    to_dose = format_dose(
        (derivation.get("to_dose") or {}).get("amount"),
        (derivation.get("to_dose") or {}).get("unit"),
    )
    change_kind = item.raw.get("change_kind")
    verb = _CHANGE_VERB.get(change_kind or "", "Changed")

    if change_kind in ("stopped", "new", "continued", "unchanged"):
        change = Sentence((Fragment(verb),))
    elif from_dose and to_dose:
        change = Sentence((
            Fragment(verb + " from "), Fragment(from_dose, strong=True),
            Fragment(" to "), Fragment(to_dose, strong=True),
        ))
    elif to_dose:
        change = Sentence((
            Fragment(verb + " to "), Fragment(to_dose, strong=True),
        ))
    else:
        change = Sentence((Fragment(verb),))

    if _sig_is_not_specified(item):
        how = Sentence((Fragment("Keep taking it the way you have been"),))
    else:
        settled = _settled_quotes(item, resolution)
        sig = _select_sig(item, settled) or {}
        dose = format_dose(sig.get("dose_amount"), sig.get("dose_unit"))
        freq = format_frequency(sig.get("frequency_per_day"))
        timing = format_timing(sig.get("timing") or [])
        parts: list[Fragment] = []
        if dose:
            parts.append(Fragment(dose, strong=True))
        if freq:
            if parts:
                parts.append(Fragment(", "))
            parts.append(Fragment(freq + timing, strong=True))
        elif timing and parts:
            parts.append(Fragment(timing))
        how = Sentence(tuple(parts)) if parts else None

    notes: list[Sentence] = []
    salt = med.get("salt_candidates") or []
    if med.get("salt_unspecified") and salt:
        notes.append(Sentence((
            Fragment("Check the label — this may be "),
            Fragment(" or ".join(salt) + "."),
        )))

    return MedicationRow(name=name, change=change, how=how, notes=tuple(notes))


# -- appointment ---------------------------------------------------------


def appointment_sentence(item: Item) -> Sentence:
    when = item.raw.get("when") or {}
    resolved = when.get("resolved_date")
    phrase = when.get("original_phrase") or "soon"
    purpose = item.raw.get("purpose_quote") or {}

    if resolved:
        when_text = format_date_both_ways(date.fromisoformat(resolved), phrase)
    else:
        when_text = phrase

    frags = [Fragment("Come back "), Fragment(when_text, strong=True)]
    if purpose.get("text"):
        # The purpose is a verbatim span, quoted so it reads as the doctor's
        # words rather than ours.
        frags += [Fragment(", to "), Fragment(purpose["text"])]
    frags.append(Fragment("."))
    return Sentence(tuple(frags))


# -- red flag ------------------------------------------------------------


def red_flag_sentence(item: Item) -> Sentence:
    """Verbatim. A red-flag instruction is the one place where paraphrase is
    least defensible, so the template contributes nothing but the quotation
    marks."""
    quote = item.primary_quote
    text = quote.text if quote else ""
    return Sentence((Fragment(text, strong=True),))
