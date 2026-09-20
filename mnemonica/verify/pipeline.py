"""C5 — verification order and D16 disposition. TOOLS.md §5, SPEC.md D16.

This is the whole of Track C downstream of generation: a `Session` plus what
the model emitted goes in, and the post-C5 envelope Track D renders comes out
(`render/model.py` is the one file that knows those key names, and
`fixtures/golden_extraction.json` is the pinned example).

The order is TOOLS §5's and it is not negotiable — nothing proceeds on
unverified input:

    1 span verification   2 offset assignment   3 turn attribution
    4 association check   5 tool execution      6 cross-validation
    7 disposition         8 render (Track D)

The rules worth stating in one place, because they are what the architecture
is *for*:

- **"I couldn't hear it" and "your doctor never said it" must never look the
  same.** Categories 2/3/4 are the machine failing; 5/6/7 are the visit being
  what it was. A system that collapses them blames itself for the doctor's
  omissions, or the doctor for its own.
- **Only two blocking cases**: ambiguous attribution on a dose (D19), and
  internal contradiction (category 7). Everything else is glance-and-accept,
  because over-flagging costs a click and under-flagging costs a wrong dose.
- **`change_kind` is derived wherever it can be.** Two parsed doses for one
  drug make `increased`/`decreased` arithmetic, not a judgement — derived, it
  prints as fact; otherwise it is prefilled and flagged, and the clinician's
  click is what promotes it. It is the verb of the headline sentence, and a
  closed enum guarantees well-formed, not correct.
- **Cross-turn mentions of one drug are merged on the RxCUI**, never on the
  string the model happened to quote. `merge_turns` deliberately leaves them
  separate because identity is not known until `resolve_medication` has run;
  this is where it becomes known, so this is where they merge.

Thresholds live in `thresholds.py` and are 3c's to move.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from mnemonica.contracts import Session
from mnemonica.extract.schema import VisitExtraction
from mnemonica.tools.crossvalidate import cross_validate
from mnemonica.tools.parse_sig import parse_sig
from mnemonica.tools.resolve_date import resolve_date
from mnemonica.tools.resolve_medication import MedicationKB, resolve_medication
from mnemonica.tools.schemas import (
    MedicationResolution, ParseSigCall, ResolveMedicationCall, SigParse,
)
from mnemonica.verify.associate import check_association
from mnemonica.verify.spans import Quote, SpanVerifier
from mnemonica.verify.thresholds import DOSE_WORD_PROBABILITY, LOW_WORD_PROBABILITY

__all__ = ["verify", "Verified"]

SUMMARY_QUOTES_PER_HEADING = 3
"""How many quotes one heading of the extractive summary shows."""

_DOSE_NUMERAL = re.compile(r"\b\d+(?:\.\d+)?")
"""A numeral that could be a dose. **No trailing `\\b`** — people say
"two of the 25s" and "let's get you the 50s", and a word boundary after
the digits does not match a following "s". Getting that wrong loses D19's
blocking case on the one line it exists for."""


def _flag(category, blocking, reason, render="expanded", **extra) -> dict:
    return {"d16_category": category, "blocking": blocking, "reason": reason,
            "render": render, **extra}


@dataclass
class Verified:
    """The envelope, plus the run's own accounting."""

    envelope: dict
    dropped: int = 0
    categories: set[int] = field(default_factory=set)

    def __getitem__(self, key):  # convenience in tests and at the REPL
        return self.envelope[key]


# ---------------------------------------------------------------- medications

@dataclass
class _Med:
    """One drug, accumulated across every turn that mentioned it."""

    id: str
    mention: Quote
    heard: str
    resolution: MedicationResolution
    sigs: list[tuple[Quote, SigParse]] = field(default_factory=list)
    date_quote: Quote | None = None
    date_resolution: object | None = None
    change_kind: str = "continued"
    change_quote: Quote | None = None
    change_from_model: bool = True


def _verify_medications(session, extraction, sv, kb) -> list[_Med]:
    """Steps 1–3 and 5 for every medication the model emitted, merged on RxCUI.

    A mention whose quote is not in the transcript takes the whole item with it
    — there is no drug to attach anything to — and that is D16 category 1."""
    by_key: dict[str, _Med] = {}
    order: list[str] = []

    for item in extraction.medications:
        near = session.turn_at_offset(0)
        mention = sv.verify(item.medication.mention_quote, kind="medication")
        if mention is None:
            continue
        near = session.turn_at_offset(mention.char_offset)
        resolution = resolve_medication(
            ResolveMedicationCall(
                mention_quote=item.medication.mention_quote,
                context_quote=item.medication.context_quote,
            ),
            kb,
        )
        key = (resolution.rxcui
               or f"unresolved:{item.medication.mention_quote.strip().lower()}")
        med = by_key.get(key)
        if med is None:
            slug = (resolution.canonical_name
                    or item.medication.mention_quote).strip().lower()
            slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-") or "medication"
            med = _Med(id=f"med-{slug}", mention=mention, heard=mention.text,
                       resolution=resolution)
            by_key[key] = med
            order.append(key)

        for call in item.sig:
            quote = sv.verify(call.sig_quote, kind="sig", near=near)
            if quote is None:
                continue
            med.sigs.append((quote, parse_sig(ParseSigCall(sig_quote=quote.text))))

        if item.start_or_stop is not None and med.date_quote is None:
            quote = sv.verify(item.start_or_stop.phrase_quote, kind="date", near=near)
            if quote is not None:
                med.date_quote = quote
                med.date_resolution = resolve_date(
                    item.start_or_stop, session.visit_date)

        change = sv.verify(item.change_evidence_quote, kind="change_evidence",
                           near=near)
        if change is not None and (med.change_quote is None
                                   or item.change_kind != "continued"):
            med.change_quote = change
            med.change_kind = item.change_kind
            med.change_from_model = True

    return [by_key[k] for k in order]


def _derive_change_kind(med: _Med) -> dict | None:
    """Two parsed doses, one drug → arithmetic, not a judgement (D12).

    Only doses the **clinician** stated count. Deriving `increased` from a
    patient's *"should I take four?"* would launder a D19 violation into a
    printed fact, which is precisely the failure D19 exists to prevent."""
    doses = [
        (q, s) for q, s in med.sigs
        if s.dose_amount is not None and s.dose_unit and q.turn_role == "clinician"
    ]
    if len(doses) < 2:
        return None
    unit = doses[0][1].dose_unit
    if any(s.dose_unit != unit for _, s in doses):
        return None
    doses.sort(key=lambda pair: pair[0].char_offset)
    first, last = doses[0], doses[-1]
    if first[1].dose_amount == last[1].dose_amount:
        return None
    kind = "increased" if last[1].dose_amount > first[1].dose_amount else "decreased"
    return {
        "change_kind": kind,
        "from_dose": {"amount": first[1].dose_amount, "unit": first[1].dose_unit,
                      "quote": first[0].as_dict()},
        "to_dose": {"amount": last[1].dose_amount, "unit": last[1].dose_unit,
                    "quote": last[0].as_dict()},
        "rule": (f"both doses parsed and resolved; "
                 f"{last[1].dose_amount:g} "
                 f"{'>' if kind == 'increased' else '<'} "
                 f"{first[1].dose_amount:g}"),
    }


def _medication_flags(session, med, drug_names) -> list[dict]:
    """The D16 table, applied to one drug. Order is review order."""
    flags: list[dict] = []
    res = med.resolution

    # -- category 7: two different instructions (blocking) + strength checks
    for finding in cross_validate(
        res, [s for _, s in med.sigs],
        drug_label=res.canonical_name or med.heard,
    ):
        evidence = []
        if finding.d16_category == 7:
            evidence = [q.as_dict() for q, s in med.sigs
                        if s.dose_amount is not None or s.frequency_per_day]
        flags.append(_flag(finding.d16_category, finding.severity == "blocking",
                           finding.message, "expanded", evidence=evidence))

    # -- category 3: D19 — a dose from a turn with no confident clinician role
    #
    # The trigger is a dose **numeral in the quote**, not a successfully parsed
    # dose. "So that's two of the 25s?" does not parse, and it is exactly the
    # companion's question D19 exists for: a grammar failure must not be what
    # lets an unattributed dose through.
    for quote, sig in med.sigs:
        if (sig.dose_amount is None and sig.frequency_per_day is None
                and not _DOSE_NUMERAL.search(quote.text)):
            continue
        if quote.turn_role == "clinician":
            continue
        blocking = quote.turn_role == "unknown"
        flags.append(_flag(
            3, blocking,
            "dose stated in a turn with no confident speaker role" if blocking
            else "dose stated by the patient, not the clinician",
            "expanded", evidence=[quote.as_dict()]))

    if res.status != "unresolved" and med.mention.turn_role != "clinician":
        flags.append(_flag(3, False, "spoken by the patient, not the clinician"))

    # -- category 4: no RxNorm concept matched
    if res.status == "unresolved":
        flags.append(_flag(4, False, "no RxNorm concept matched the heard text",
                           heard_text=med.heard,
                           near_matches=[c.name for c in res.candidates[:3]]))
    elif res.status == "ambiguous":
        flags.append(_flag(None, False,
                           "two drugs match what was heard about equally well",
                           heard_text=med.heard,
                           choices=[c.name for c in res.candidates[:4]]))

    # -- the resolver's own findings: salt, and a corrected mishearing
    if res.salt_unspecified:
        flags.append(_flag(
            None, False,
            f"salt unspecified: {' or '.join(res.salt_candidates)} — these do "
            f"not share a dosing schedule",
            choices=list(res.salt_candidates)))
    if res.match_type == "fuzzy" and res.canonical_name:
        flags.append(_flag(
            None, False,
            f"likely mistranscription — heard '{med.heard}', matched "
            f"'{res.canonical_name}'",
            heard_text=med.heard, resolved_name=res.canonical_name,
            edit_distance=res.edit_distance))

    # -- category 5: no dose spoken. A finding, NOT an error.
    if any(s.status == "not_specified" for _, s in med.sigs):
        flags.append(_flag(5, False, "no dose spoken — not an error",
                           "collapsed", display="not specified"))
    for quote, sig in med.sigs:
        if sig.status in ("unparseable", "partial") and sig.unparsed_remainder:
            flags.append(_flag(
                None, False,
                f"a dose was spoken but not fully parsed: "
                f"“{sig.unparsed_remainder}”",
                evidence=[quote.as_dict()]))

    # -- category 2: a dose numeral we could not hear confidently
    for quote, _ in med.sigs:
        threshold = (DOSE_WORD_PROBABILITY if _DOSE_NUMERAL.search(quote.text)
                     else LOW_WORD_PROBABILITY)
        if quote.min_word_probability < threshold:
            flags.append(_flag(
                2, False, "dose numeral transcribed with low confidence",
                "expanded", min_word_probability=quote.min_word_probability,
                evidence=[quote.as_dict()]))
    if med.mention.min_word_probability < LOW_WORD_PROBABILITY:
        flags.append(_flag(2, False, "drug name transcribed with low confidence",
                           "expanded", evidence=[med.mention.as_dict()]))

    # -- category 8: association drawn from another turn (C4.5)
    others: list[tuple[str, Quote]] = [("the dose instruction", q)
                                       for q, _ in med.sigs]
    if med.date_quote:
        others.append(("the date", med.date_quote))
    if med.change_quote:
        others.append(("what changed", med.change_quote))
    for finding in check_association(
        session, med.mention, others, drug_names=drug_names,
        # The drug's *name*, not the mention phrase: "the metoprolol up to 50
        # milligrams" ends in "milligrams", and asking whether a turn names
        # "milligrams" answers a different question than the one C4.5 asks.
        mention_text=res.canonical_name or med.heard,
    ):
        flags.append(_flag(8, False, finding.reason, "expanded",
                           evidence=[finding.mention.as_dict(),
                                     finding.other.as_dict()]))
    return flags


def _medication_dict(session, med, drug_names) -> dict:
    flags = _medication_flags(session, med, drug_names)
    derived = _derive_change_kind(med)
    if derived:
        change_kind, derivation, is_derived = (
            derived["change_kind"], derived, True)
    else:
        change_kind, derivation, is_derived = med.change_kind, None, False
        flags.append(_flag(
            None, False,
            "change_kind was not derived from two parsed doses — the model "
            "chose it, so it is not printed as fact",
            "collapsed"))

    blocking = any(f["blocking"] for f in flags)
    disposition = ("blocking" if blocking
                   else "prefilled_flagged" if flags else "printed_as_fact")
    sigs = []
    for quote, sig in med.sigs:
        entry = {"quote": quote.as_dict(), **sig.model_dump(mode="json")}
        if quote.turn_role != "clinician" and (
            sig.dose_amount is not None or sig.frequency_per_day
            or _DOSE_NUMERAL.search(quote.text)
        ):
            entry["blocking_reason"] = "attribution_ambiguous"
        sigs.append(entry)

    resolution = med.resolution.model_dump(mode="json")
    if med.resolution.match_type == "fuzzy":
        resolution["heard_text"] = med.heard

    return {
        "id": med.id,
        "kind": "medication",
        "disposition": disposition,
        "d16_categories": sorted({f["d16_category"] for f in flags
                                  if f["d16_category"]}),
        "mention_quote": med.mention.as_dict(),
        "medication": resolution,
        "sig": sigs,
        "start_or_stop": (
            {"quote": med.date_quote.as_dict(),
             **med.date_resolution.model_dump(mode="json")}
            if med.date_quote and med.date_resolution else None),
        "change_kind": change_kind,
        "change_evidence_quote": (med.change_quote.as_dict()
                                  if med.change_quote else None),
        "change_kind_derived": is_derived,
        "change_kind_derivation": derivation,
        "flags": flags,
    }


# ------------------------------------------- appointments, flags, threads

def _appointments(session, extraction, sv, visit_date: date) -> list[dict]:
    """One entry per distinct span.

    Per-turn extraction sees each turn with its neighbours for context (D15),
    so the same follow-up gets nominated two or three times from either side of
    it. Deduplicating on the **verified offsets** is safe in a way that
    deduplicating on the model's strings would not be: identical offsets are
    the same words in the same place, not two things that happen to read alike.
    """
    out, spans = [], []
    for i, item in enumerate(extraction.appointments):
        when = sv.verify(item.when.phrase_quote, kind="appointment")
        if when is None:
            continue
        # Identical offsets were already deduplicated here; overlapping ones
        # were not, and that is the common case. `"in six weeks"` sits inside
        # `"Come back and see me in six weeks"`, so the same follow-up
        # nominated from either side of the turn produced two entries and
        # printed twice. Overlapping offsets are the same words in the same
        # place, which is the same argument identical offsets rest on.
        if any(when.char_offset < end and start < when.char_end
               for start, end in spans):
            continue
        spans.append((when.char_offset, when.char_end))
        purpose = sv.verify(item.purpose_quote, kind="appointment_purpose",
                            near=session.turn_at_offset(when.char_offset))
        resolution = resolve_date(item.when, visit_date)
        flags: list[dict] = []
        if resolution.status == "unanchored":
            flags.append(_flag(
                None, False,
                f"the date hangs off “{resolution.depends_on_event}”, not off "
                f"the visit — it needs that event's date"))
        elif resolution.status in ("unparseable", "not_a_date"):
            flags.append(_flag(None, False,
                               "the time expression could not be resolved"))
        if when.min_word_probability < LOW_WORD_PROBABILITY:
            flags.append(_flag(2, False,
                               "the date was transcribed with low confidence",
                               "expanded", evidence=[when.as_dict()]))
        out.append({
            "id": f"appt-{i + 1}" if i else "appt-followup",
            "kind": "appointment",
            "disposition": "prefilled_flagged" if flags else "printed_as_fact",
            "d16_categories": sorted({f["d16_category"] for f in flags
                                      if f["d16_category"]}),
            # `event_kind` is the model's classification, not the resolver's
            # output, so it is not in the resolution dump — but it is what
            # keeps a follow-up visit and a blood test on the same day from
            # being merged as duplicates.
            "when": {"quote": when.as_dict(), "event_kind": item.when.event_kind,
                     **resolution.model_dump(mode="json")},
            "purpose_quote": purpose.as_dict() if purpose else None,
            "flags": flags,
            "_turn_role": when.turn_role,
        })
    return _one_per_appointment(out)


def _one_per_appointment(entries: list[dict]) -> list[dict]:
    """Collapse entries that are the same appointment said twice.

    Overlap catches a follow-up nominated from either side of one turn. It
    does not catch the patient repeating the date back — `"Six weeks."` is a
    different span in a different turn, and it printed as a third visit.

    Two entries are the same appointment when they resolve to the same day
    **and** are the same kind of event. The kind matters: a follow-up visit
    and a blood test can honestly fall on one day, and merging those would
    lose a real instruction rather than a duplicate.

    Which survives: the clinician's, then the one carrying a purpose, then the
    earliest. The doctor sets the appointment; the patient echoes it, and the
    echo is the one with no reason attached.
    """
    def rank(entry: dict) -> tuple[int, int, int]:
        return (
            0 if entry.get("_turn_role") == "clinician" else 1,
            0 if (entry.get("purpose_quote") or {}).get("text") else 1,
            (entry["when"].get("quote") or {}).get("char_offset", 0),
        )

    best: dict[tuple, dict] = {}
    for entry in entries:
        when = entry["when"]
        key = (when.get("resolved_date"), when.get("event_kind"))
        if key[0] is None:          # unresolved dates are never merged
            best[("unresolved", id(entry))] = entry
            continue
        current = best.get(key)
        if current is None:
            best[key] = entry
            continue
        winner, loser = ((entry, current) if rank(entry) < rank(current)
                         else (current, entry))
        # Merge rather than discard. The clinician's phrasing is the one to
        # print, but the reason may have been captured from the turn where the
        # patient repeated the date back — dropping the whole losing entry
        # loses a real instruction along with the duplicate.
        if not (winner.get("purpose_quote") or {}).get("text"):
            purpose = (loser.get("purpose_quote") or {}).get("text")
            if purpose:
                winner["purpose_quote"] = loser["purpose_quote"]
        best[key] = winner

    kept = sorted(best.values(),
                  key=lambda e: (e["when"].get("quote") or {}).get("char_offset", 0))
    for entry in kept:
        entry.pop("_turn_role", None)
    return kept


def _simple_items(extraction, sv, *, attr, kind, quote_field, id_prefix,
                  disposition, flag) -> list[dict]:
    """Red flags and loose threads: one verbatim quote each, nothing to resolve."""
    out, spans = [], []
    for i, item in enumerate(getattr(extraction, attr), start=1):
        quote = sv.verify(getattr(item, quote_field), kind=kind)
        if quote is None:
            continue
        # Overlapping offsets are the same words in the same place — the same
        # argument identical offsets rest on, and the case that actually
        # happens when a turn is nominated from either side.
        if any(quote.char_offset < end and start < quote.char_end
               for start, end in spans):
            continue
        spans.append((quote.char_offset, quote.char_end))
        flags = [flag] if flag else []
        out.append({
            "id": f"{id_prefix}-{i}",
            "kind": kind,
            "disposition": disposition,
            "d16_categories": sorted({f["d16_category"] for f in flags
                                      if f["d16_category"]}),
            quote_field: quote.as_dict(),
            "flags": flags,
        })
    return _drop_restatements(out, quote_field)


_STOPWORDS = frozenset("""
a an and or if the this that these those to of in on at for with your you
my me we us i it its is are was were be been being do does did don don't
not no so then than there here when what which who whom how any some
call calls called get gets got go goes going come comes start starts
isn don doesn didn won aren wasn weren hasn haven wouldn couldn shouldn
""".split())
"""Function words, plus the verbs every warning shares.

`call`, `get` and `go` are in here because every red flag contains them —
"call the office", "if you get a sore", "if it goes numb". Leaving them in
makes two unrelated warnings look similar, which is the direction that loses
an instruction.
"""


def _content(text: str) -> set[str]:
    """Content words, lightly stemmed so `numbness` meets `numb`."""
    import re as _re
    words = _re.findall(r"[a-z]+", text.lower())
    out = set()
    for w in words:
        if w in _STOPWORDS or len(w) < 3:
            continue
        for suffix in ("ness", "ing", "ed", "es", "s"):
            if w.endswith(suffix) and len(w) - len(suffix) >= 3:
                w = w[: -len(suffix)]
                break
        out.add(w)
    return out


CONTAINMENT = 0.7
MIN_SHARED = 3
"""Both must hold before two warnings are treated as one.

The asymmetry drives this: printing a warning twice is mildly confusing,
dropping a distinct one is dangerous, so the test is tuned to under-merge.

Measured on the pair this was built for — "if your feet start going numb, or
you get any sore on your foot that isn't healing up, you call the office"
against "if there's a sore, or numbness, you call" — containment is 0.75 on
three shared words. Unrelated warnings in the same script score **0.00**, so
the gap either side of the threshold is wide.

`MIN_SHARED` exists because containment is jumpy on short quotes: with four
content words each one is worth 0.25, and a two-word instruction could clear
any ratio on a single coincidence. Three shared content words is a real
overlap, not an accident of length.
"""


def _drop_restatements(entries: list[dict], quote_field: str) -> list[dict]:
    """Collapse one instruction said twice in different words.

    Overlap catches a span nominated twice. It does not catch the clinician
    restating the warning later in the visit — "if your feet start going numb,
    or you get any sore that isn't healing up, you call the office" and "if
    there's a sore, or numbness, you call" are one instruction and printed as
    two bordered boxes of equal weight, leaving the patient to work out
    whether they differ.

    No model here: this layer is deterministic by design, and a semantic
    judgement about which safety instructions are "the same" is exactly the
    kind of call that should not be made by something that cannot be audited.
    Content-word containment is crude, explainable, and tuned to under-merge.
    """
    kept: list[dict] = []
    for entry in entries:
        words = _content((entry.get(quote_field) or {}).get("text", ""))
        if not words:
            kept.append(entry)
            continue
        replaced = False
        for index, existing in enumerate(kept):
            other = _content((existing.get(quote_field) or {}).get("text", ""))
            if not other:
                continue
            shared = words & other
            overlap = len(shared) / min(len(words), len(other))
            if len(shared) < MIN_SHARED or overlap < CONTAINMENT:
                continue
            # Same instruction. Keep the fuller statement of it — the longer
            # one carries the detail the restatement dropped.
            if len(words) > len(other):
                kept[index] = entry
            replaced = True
            break
        if not replaced:
            kept.append(entry)
    return kept


# ------------------------------------------------------------------ the whole

def verify(
    session: Session, extraction: VisitExtraction, *,
    kb: MedicationKB | None = None, logger=None,
) -> Verified:
    """Run TOOLS §5 end to end. This is C4 + C4.5 + C5."""
    kb = kb or MedicationKB()
    sv = SpanVerifier(session, logger=logger)

    meds = _verify_medications(session, extraction, sv, kb)
    drug_names = [m.resolution.canonical_name or m.heard for m in meds]
    medications = [_medication_dict(session, m, drug_names) for m in meds]

    appointments = _appointments(session, extraction, sv, session.visit_date)
    red_flags = _simple_items(
        extraction, sv, attr="red_flags", kind="red_flag",
        quote_field="instruction_quote", id_prefix="flag",
        disposition="printed_as_fact", flag=None)
    loose_threads = _simple_items(
        extraction, sv, attr="loose_threads", kind="loose_thread",
        quote_field="topic_quote", id_prefix="thread",
        disposition="surfaced",
        flag=_flag(6, False,
                   "raised and never resolved anywhere later in the visit"))

    summary: dict[str, list[dict]] = {}
    seen_spans: set[tuple[int, int]] = set()
    for heading in ("why_you_came_in", "what_the_doctor_found",
                    "what_happens_next"):
        chosen = []
        for raw in getattr(extraction.summary_quotes, heading):
            quote = sv.verify(raw, kind="summary")
            if quote is None or (quote.char_offset, quote.char_end) in seen_spans:
                continue
            seen_spans.add((quote.char_offset, quote.char_end))
            chosen.append(quote)
        # In transcript order, and capped: D7's summary is three short groups
        # of quotes a patient will actually read, not every line the model
        # thought was nice. The cap is a *display* decision made here rather
        # than a limit imposed on the model, which would have it choosing
        # which truth to withhold.
        chosen.sort(key=lambda q: q.char_offset)
        summary[heading] = [q.as_dict() for q in chosen[:SUMMARY_QUOTES_PER_HEADING]]

    envelope = {
        "visit_date": session.visit_date.isoformat(),
        "medications": medications,
        "appointments": appointments,
        "red_flags": red_flags,
        "loose_threads": loose_threads,
        "discarded": [d.as_dict() for d in sv.dropped],
        "summary_quotes": summary,
    }
    envelope["header"] = _header(envelope)
    categories = {c for group in ("medications", "appointments", "red_flags",
                                  "loose_threads")
                  for item in envelope[group] for c in item["d16_categories"]}
    if sv.dropped:
        categories.add(1)
    return Verified(envelope, dropped=sv.drop_count, categories=categories)


def _header(envelope: dict) -> dict:
    """*"14 confirmed · 2 need your ear · 1 discarded"* (U3).

    Counted the same way `render.model.Extraction.header()` counts, because a
    header that disagrees with its own item list is a lie told confidently."""
    items = (envelope["medications"] + envelope["appointments"]
             + envelope["red_flags"] + envelope["loose_threads"])
    return {
        "confirmed": sum(1 for i in items if not i["flags"]),
        "blocking": sum(1 for i in items if i["disposition"] == "blocking"),
        "needs_confirmation": sum(
            1 for i in items
            if i["flags"] and i["disposition"] != "blocking"
            and i["kind"] != "loose_thread"),
        "discarded": len(envelope["discarded"]),
        "loose_threads": len(envelope["loose_threads"]),
    }
