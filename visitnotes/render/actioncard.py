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

from visitnotes.render.model import Item

__all__ = ["Fragment", "Sentence", "medication_sentences", "appointment_sentence",
           "red_flag_sentence", "format_dose", "format_frequency"]


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


def _select_sig(item: Item) -> dict[str, Any] | None:
    """Which of an item's sigs is the one the patient is told to follow.

    Highest parse confidence among the sigs that are not themselves the reason
    the item is blocking. Sigs are never merged across turns: combining a dose
    from turn 12 with a frequency from turn 20 is exactly the cross-turn smear
    D16 category 8 exists to catch, and doing it silently in a template would
    launder the very thing the flag is warning about.
    """
    sigs = [s for s in (item.raw.get("sig") or []) if not s.get("blocking_reason")]
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
) -> list[Sentence]:
    """The headline change, then how to take it.

    `promoted` is the clinician's click on an underived `change_kind`.
    """
    med = item.raw.get("medication") or {}
    name = med.get("canonical_name")
    if not name:
        # D16 category 4 — unresolved. The patient's page prints what was
        # actually said, in quotes, rather than a drug we could not name.
        heard = item.primary_quote
        name = f"“{heard.text}”" if heard else "a medication"

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

    sig = _select_sig(item) or {}
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
                Fragment(f"{doctor} {verb} your "),
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
                Fragment(f"{doctor} changed your "),
                Fragment(name, strong=True),
                Fragment(" to "),
                Fragment(to_dose, strong=True),
                Fragment("."),
            )
            needs = False if derived else needs
        else:
            frags = (
                Fragment(f"{doctor} {verb} your "),
                Fragment(name, strong=True),
                Fragment("."),
            )
        sentences.append(Sentence(frags, needs_promotion=needs, promotion_reason=reason))
    elif change == "continued":
        sentences.append(
            Sentence(
                (
                    Fragment("Keep taking your "),
                    Fragment(name, strong=True),
                    Fragment(" the same way you have been."),
                )
            )
        )
    elif change == "started":
        frags = [Fragment(f"{doctor} started you on "), Fragment(name, strong=True)]
        if to_dose:
            frags += [Fragment(", "), Fragment(to_dose, strong=True)]
        frags.append(Fragment("."))
        sentences.append(Sentence(tuple(frags)))
    elif change == "stopped":
        sentences.append(
            Sentence(
                (
                    Fragment(f"{doctor} stopped your "),
                    Fragment(name, strong=True),
                    Fragment("."),
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
