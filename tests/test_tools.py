"""Track A's three tools, tested against their done-when criteria.

The A6 tests are about **status**, not about which string won. A resolver that
returns the right drug and the wrong status is the dangerous one: `resolved`
on a coin toss between *Celexa* and *Celebrex* prints as fact, and nobody
downstream can tell it was a guess.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from mnemonica.kb import db
from mnemonica.tools.crossvalidate import cross_validate
from mnemonica.tools.parse_sig import parse_sig
from mnemonica.tools.resolve_date import resolve_date
from mnemonica.tools.schemas import (
    ParseSigCall, ResolveDateCall, ResolveMedicationCall,
)

REPO = Path(__file__).resolve().parents[1]
VISIT = date(2026, 9, 18)   # a Friday — golden_visit.json's visit_date

needs_kb = pytest.mark.skipif(
    not db.DB_PATH.exists(),
    reason="knowledge base not built — run python -m mnemonica.kb.build",
)


@pytest.fixture(scope="module")
def kb():
    from mnemonica.tools.resolve_medication import MedicationKB
    return MedicationKB()


def _resolve(kb, text):
    from mnemonica.tools.resolve_medication import resolve_medication
    return resolve_medication(ResolveMedicationCall(mention_quote=text), kb)


# ========================================================== A6 resolve_medication

@needs_kb
def test_a6_exact_match(kb):
    r = _resolve(kb, "lisinopril")
    assert (r.status, r.match_type, r.rxcui) == ("resolved", "exact", "29046")
    assert r.match_confidence == 1.0


@needs_kb
def test_a6_case_insensitive_is_labelled_as_such(kb):
    r = _resolve(kb, "LISINOPRIL")
    assert r.status == "resolved" and r.match_type == "case_insensitive"


@needs_kb
def test_a6_recovers_whisper_mistranscription(kb):
    """A6's headline acceptance case. `metropolol` is a **metathesis** — two
    sounds swapped — which is why a Double Metaphone *bucket* cannot find it
    (`MTRPLL` vs `MTPRLL`) and why recall is exhaustive instead."""
    r = _resolve(kb, "metropolol")
    assert r.status == "resolved"
    assert r.match_type == "fuzzy"
    assert r.canonical_name == "metoprolol"
    assert 0 < r.edit_distance <= 2


@needs_kb
@pytest.mark.parametrize("heard,expected", [
    ("lisinipril", "lisinopril"),
    ("gabapenten", "gabapentin"),
    ("amlodapine", "amlodipine"),
    ("vancomicin", "vancomycin"),
])
def test_a6_fuzzy_recovery(kb, heard, expected):
    r = _resolve(kb, heard)
    assert r.status == "resolved" and r.canonical_name.lower() == expected


@needs_kb
def test_a6_close_second_place_is_ambiguous_not_a_winner(kb):
    """The margin test, on a pair that actually matters: prednisone and
    prednisoLONE are different drugs at different potencies."""
    r = _resolve(kb, "predisone")
    assert r.status == "ambiguous"
    assert len(r.candidates) >= 2
    names = {c.name.lower() for c in r.candidates}
    assert "prednisone" in names and "prednisolone" in names


@needs_kb
def test_a6_unknown_drug_is_unresolved_with_near_matches(kb):
    """*Coumadin* is not in the Current Prescribable release, and it scored
    0.81 against *Comtan* — above threshold, clear of #2. Four edits between
    an eight-letter name and its "match" is a different drug."""
    r = _resolve(kb, "coumadin")
    assert r.status == "unresolved"
    assert r.rxcui is None
    assert r.candidates, "D16 category 4 shows near-matches, not a blank"


@needs_kb
def test_a6_unnamed_drug_is_unresolved(kb):
    """*"your blood pressure pill"* — the resolver reporting that it cannot
    identify this is the correct outcome, not a failure."""
    assert _resolve(kb, "your blood pressure pill").status == "unresolved"


@needs_kb
def test_a6_bare_metoprolol_is_resolved_and_salt_unspecified(kb):
    """A5.5's whole point. Deliberately NOT `ambiguous`: the resolution
    succeeded — the ingredient really is metoprolol and the clinician really
    did not say which salt."""
    r = _resolve(kb, "metoprolol")
    assert r.status == "resolved"
    assert r.rxcui == "6918" and r.tty == "IN"
    assert r.salt_unspecified is True
    assert set(r.salt_candidates) == {"metoprolol succinate",
                                      "metoprolol tartrate"}


@needs_kb
def test_a6_named_salt_sets_no_flag(kb):
    r = _resolve(kb, "metoprolol succinate")
    assert r.status == "resolved" and r.tty == "PIN"
    assert r.salt_unspecified is False


@needs_kb
def test_a6_strengths_are_scoped_to_the_named_salt(kb):
    """Asking for *metoprolol*'s strengths returns both salts' products, so a
    12.5 mg tartrate strength would silently validate a 12.5 mg succinate dose
    that is not marketed."""
    succ = _resolve(kb, "metoprolol succinate").available_strengths
    assert succ and all("tartrate" not in s for s in succ)


@needs_kb
def test_a6_brand_resolves_and_is_flagged_as_one(kb):
    r = _resolve(kb, "Toprol")
    assert r.status == "resolved" and r.is_brand is True
    assert any("metoprolol" in i.lower() for i in r.ingredients)


@needs_kb
def test_a6_provenance_is_always_set(kb):
    r = _resolve(kb, "lisinopril")
    assert r.source == "RxNorm Current Prescribable"
    assert r.source_release == "09082026"


@needs_kb
def test_a6_head_of_phrase_backoff(kb):
    """`golden_extraction.json`'s mention quotes carry trailing dose text,
    though TOOLS.md tells the model to pass the name alone."""
    assert _resolve(kb, "the metoprolol up to 50 milligrams").rxcui == "6918"
    assert _resolve(kb, "the lisonopril at 10").rxcui == "29046"
    # ...and the backoff must not rescue a phrase that names no drug.
    assert _resolve(kb, "the other blood pressure pill").status == "unresolved"


@needs_kb
def test_a6_matches_the_golden_fixture(kb):
    """Every medication in 1c-ii resolves to the status and RxCUI the
    hand-authored fixture recorded."""
    fixture = json.loads(
        (REPO / "fixtures" / "golden_extraction.json").read_text())
    for item in fixture["medications"]:
        expected = item["medication"]
        got = _resolve(kb, item["mention_quote"]["text"])
        assert got.status == expected["status"], item["id"]
        assert got.rxcui == expected.get("rxcui"), item["id"]
        assert got.salt_unspecified == expected.get("salt_unspecified", False)


# ================================================================ A9 parse_sig

def _sig(text):
    return parse_sig(ParseSigCall(sig_quote=text))


def test_a9_parsed():
    p = _sig("Take one 50 mg tablet once daily in the morning")
    assert p.status == "parsed"
    assert (p.dose_amount, p.dose_unit, p.frequency_per_day) == (50.0, "mg", 1.0)
    assert p.timing == ["morning"]


@pytest.mark.parametrize("text", [
    "take it as directed", "same as before", "just keep taking it",
])
def test_a9_not_specified_is_not_an_error(text):
    """D16 category 5, and the single most important distinction in this tool.
    "Take as directed" is a complete, correct, successful parse whose finding
    is that no dose exists."""
    p = _sig(text)
    assert p.status == "not_specified"
    assert p.parse_confidence == 1.0
    assert p.unparsed_remainder is None


def test_a9_unparseable_is_distinct_from_not_specified():
    p = _sig("take the blue one when your ankles look puffy")
    assert p.status == "unparseable"
    assert p.dose_amount is None


def test_a9_partial_populates_the_remainder():
    p = _sig("take the 25 mg one, the way we discussed at the hospital")
    assert p.status == "partial"
    assert p.unparsed_remainder


def test_a9_all_four_statuses_are_reachable():
    got = {_sig(t).status for t in (
        "50 mg twice a day",
        "take the 25 mg one, the way we discussed at the hospital",
        "ask the pharmacist",
        "take it as directed",
    )}
    assert got == {"parsed", "partial", "unparseable", "not_specified"}


def test_a9_twice_daily_is_not_once_daily():
    """The bare `daily` alternative matched inside "twice daily" and halved
    the frequency — a silent, plausible, wrong answer."""
    assert _sig("two puffs twice daily").frequency_per_day == 2.0
    assert _sig("three times a day").frequency_per_day == 3.0


def test_a9_half_a_tablet_is_half():
    p = _sig("half a tablet once daily")
    assert p.dose_amount == 0.5 and p.dose_unit == "tablet"


def test_a9_interval_becomes_a_frequency():
    p = _sig("one tablet every eight hours as needed for pain")
    assert p.interval_hours == 8.0 and p.frequency_per_day == 3.0
    assert p.prn is True and "pain" in p.prn_condition


def test_a9_normalized_sig_is_built_from_fields_only():
    """Nothing unparsed may leak into a string that reads as understood."""
    p = _sig("50 milligrams twice a day with food")
    assert p.normalized_sig == "50 mg twice daily with food"


# ============================================================== A10 resolve_date

def _date(phrase, kind="followup_visit", visit=VISIT):
    return resolve_date(
        ResolveDateCall(phrase_quote=phrase, event_kind=kind), visit)


def test_a10_relative_future():
    r = _date("come back in three weeks")
    assert r.status == "resolved"
    assert r.resolved_date == date(2026, 10, 9)
    assert r.direction == "future"


def test_a10_come_back_in_is_not_a_past_cue():
    """A bare `\\bback in\\b` past-cue matched **"come back in three weeks"**
    and resolved it three weeks *before* the visit. A past cue inverts the
    arithmetic; it does not merely degrade it."""
    assert _date("come back in three weeks").direction == "future"
    assert _date("come back in ten days").resolved_date == date(2026, 9, 28)


def test_a10_past_direction_works():
    r = _date("you started that three months ago", kind="medication_start")
    assert r.status == "resolved" and r.direction == "past"
    assert r.resolved_date < VISIT


def test_a10_display_carries_both_forms_with_the_right_weekday():
    """D18. TOOLS.md's own example said *Friday, October 10*; October 10, 2026
    is a Saturday. A wrong day-of-week is exactly what printing both forms is
    meant to let a patient catch."""
    r = _date("come back in three weeks")
    assert r.display_string == (
        "come back in three weeks, which is Friday, October 9")
    assert r.resolved_date.strftime("%A") == "Friday"


def test_a10_anchor_is_echoed_and_never_a_model_argument():
    r = _date("in ten days")
    assert r.anchor_date == VISIT
    assert r.anchor_source == "session_visit_date"
    assert "anchor" not in ResolveDateCall.model_fields


def test_a10_unanchored():
    r = _date("the week before your procedure", kind="test_scheduled")
    assert r.status == "unanchored"
    assert "procedure" in r.depends_on_event


def test_a10_range():
    r = _date("in a few weeks")
    assert r.status == "resolved_range"
    assert r.range_start < r.range_end
    assert r.precision == "vague"


def test_a10_not_a_date_and_unparseable_are_different():
    assert _date("as needed", kind="other").status == "not_a_date"
    assert _date("when the stars align").status == "unparseable"


def test_a10_all_five_statuses_are_reachable():
    got = {_date(p, kind="other").status for p in (
        "in ten days", "in a few weeks", "the week before your procedure",
        "when the stars align", "as needed")}
    assert got == {"resolved", "resolved_range", "unanchored",
                   "unparseable", "not_a_date"}


@pytest.mark.parametrize("phrase,expected", [
    ("next Tuesday", date(2026, 9, 22)),
    ("tomorrow", date(2026, 9, 19)),
    ("yesterday", date(2026, 9, 17)),
    ("October 9", date(2026, 10, 9)),
    ("last Monday", date(2026, 9, 14)),
])
def test_a10_weekday_and_calendar_forms(phrase, expected):
    assert _date(phrase).resolved_date == expected


# ============================================================ A11 cross-validate

@needs_kb
def test_a11_flags_an_unmarketed_strength(kb):
    """The planted bad strength. This is the knowledge base catching an error
    the model structurally cannot — every quote was real."""
    r = _resolve(kb, "metoprolol succinate")
    findings = cross_validate(r, [_sig("250 mg once daily")])
    kinds = {f.kind for f in findings}
    assert "strength_not_marketed" in kinds


@needs_kb
def test_a11_accepts_a_marketed_strength(kb):
    r = _resolve(kb, "metoprolol succinate")
    findings = cross_validate(r, [_sig("50 mg once daily")])
    assert not [f for f in findings if f.kind == "strength_not_marketed"]


@needs_kb
def test_a11_two_sigs_for_one_drug_is_blocking(kb):
    """D16 category 7. Both values are shown; the tool does not choose."""
    r = _resolve(kb, "lisinopril")
    findings = cross_validate(
        r, [_sig("10 mg twice daily"), _sig("20 mg once daily")])
    assert [f for f in findings
            if f.kind == "contradictory_sigs"
            and f.severity == "blocking" and f.d16_category == 7]


@needs_kb
def test_a11_schedule_over_stated_maximum_is_blocking(kb):
    r = _resolve(kb, "lisinopril")
    findings = cross_validate(
        r, [_sig("10 mg twice a day, no more than 15 mg in a day")])
    assert [f for f in findings if f.kind == "exceeds_stated_maximum"
            and f.severity == "blocking"]


@needs_kb
def test_a11_multiples_of_a_marketed_strength_are_not_flagged(kb):
    """*"two 25 mg tablets"* is 50 mg and is not an error."""
    r = _resolve(kb, "metoprolol succinate")
    sig = _sig("50 mg once daily")
    assert not [f for f in cross_validate(r, [sig])
                if f.kind == "strength_not_marketed"]


# ================================================================ A8 openFDA

@pytest.mark.skipif(
    not (REPO / "data" / "openfda_labels.db").exists(),
    reason="openFDA index not built — run python -m mnemonica.kb.openfda",
)
@needs_kb
def test_a8_resolved_rxcui_returns_label_text(kb):
    """The full chain: spoken name -> RxNorm -> SPL_SET_ID -> FDA label.

    Joined on `SPL_SET_ID`, never on `openfda.rxcui` — only 64,660 of 262,883
    label records carry one, and the missing 75% look exactly like a drug with
    no label rather than like a broken join.
    """
    from mnemonica.kb.openfda import LabelKB
    labels = LabelKB()
    r = _resolve(kb, "metoprolol succinate")
    assert r.spl_set_ids
    text = labels.geriatric_use(r.spl_set_ids)
    assert text and "geriatric" in text.lower()


# -- Phase 3: found by 3b's first run on real audio -----------------------


@needs_kb
def test_a6_stutter_is_unresolved_but_offers_the_word_it_converged_on(kb):
    """*"the lyso, ly, lysinop, lysinopril"* is what a patient reaching for a
    drug name sounds like, and Whisper transcribes the whole run-up.

    The real run returned it `unresolved` with an **empty** near-match list —
    D16 category 4 firing without the one thing that makes it actionable. It
    must stay `unresolved`, because a stutter is evidence about what the
    speaker was reaching for and not about what they said; but the clinician
    is owed the guess.
    """
    r = _resolve(kb, "lyso, ly, lysinop, lysinopril")
    assert r.status == "unresolved"
    assert r.rxcui is None
    assert [c.name for c in r.candidates] == ["lisinopril"]


@needs_kb
def test_a6_the_category_4_plant_is_still_unresolved_with_no_guess(kb):
    """The guard on the line above. *"the other blood pressure pill"* has no
    comma, so the self-correction backoff must never see it — a general
    prefix sweep is what "resolved" this once before (see Deviations)."""
    r = _resolve(kb, "the other blood pressure pill")
    assert r.status == "unresolved"
    assert not r.candidates


@needs_kb
def test_a6_two_drugs_in_one_breath_are_not_read_as_a_stutter(kb):
    """Commas alone are not evidence of self-correction. The fragments have
    to converge, or *"metoprolol, lisinopril"* becomes a guess at one drug."""
    r = _resolve(kb, "aspirin, metformin, lisinopril")
    assert r.status == "unresolved"
    assert "lisinopril" not in [c.name for c in r.candidates]
