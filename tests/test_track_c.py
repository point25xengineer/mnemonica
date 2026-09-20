"""Track C — extraction, span verification, association, disposition.

The model is not loaded here. Everything downstream of C3 takes a
`VisitExtraction`, so the *inputs* to C4/C4.5/C5 are built from
`golden_extraction.json`'s own quotes — which are verbatim by construction (1c
located every one with `str.find` over the same transcript) — and the fixture's
dispositions are the target. That keeps the suite fast enough to run on every
edit and keeps a 6 GB model out of CI.

What a live run adds that this cannot is C3's verbatim fidelity: whether the
model quotes the transcript exactly. That is the gate, it needs the model, and
it is `mnemonica.extract.c3_gate`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mnemonica.contracts import Session
from mnemonica.extract.schema import (
    SummaryQuoteCall, TurnExtraction, VisitExtraction, merge_turns,
)
from mnemonica.tools.schemas import (
    AppointmentItem, LooseThreadItem, MedicationItem, ParseSigCall,
    RedFlagItem, ResolveDateCall, ResolveMedicationCall,
)
from mnemonica.verify.pipeline import verify
from mnemonica.verify.spans import SpanVerifier

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(scope="session")
def session() -> Session:
    return Session.model_validate_json((FIXTURES / "golden_visit.json").read_text())


@pytest.fixture(scope="session")
def golden() -> dict:
    return json.loads((FIXTURES / "golden_extraction.json").read_text())


@pytest.fixture(scope="session")
def kb():
    from mnemonica.tools.resolve_medication import MedicationKB

    try:
        return MedicationKB()
    except FileNotFoundError as e:  # pragma: no cover - env-dependent
        pytest.skip(str(e))


def model_output() -> VisitExtraction:
    """What the model would plausibly emit for this visit, per turn.

    Hand-built rather than generated, and deliberately *imperfect*: it takes
    the patient's "the 50 make me more tired" as a sig (a real model does this
    — it is a dose numeral in a sentence about the drug), it takes the
    companion's "two of the 25s", and it nests a sig from turn 20 under a
    mention from turn 12. Those three are D16 categories 2, 3 and 8, and a
    fixture that only contained clean input could not tell whether the checks
    fire at all."""
    metoprolol = MedicationItem(
        medication=ResolveMedicationCall(mention_quote="the metoprolol up to 50 milligrams"),
        sig=[
            ParseSigCall(sig_quote="25 milligrams"),
            ParseSigCall(sig_quote="up to 50 milligrams"),
            ParseSigCall(sig_quote="two of the 25s"),
            ParseSigCall(sig_quote="twice a day with food"),
            ParseSigCall(sig_quote="the metoprolol, 25, twice a day"),
            ParseSigCall(sig_quote="the 50 make me more tired"),
        ],
        change_kind="increased",
        change_evidence_quote="the metoprolol up to 50 milligrams",
    )
    lisinopril = MedicationItem(
        medication=ResolveMedicationCall(mention_quote="lisonopril"),
        sig=[ParseSigCall(sig_quote="Just take it the way you've been taking it")],
        change_kind="continued",
        change_evidence_quote="That one doesn't change",
    )
    unnamed = MedicationItem(
        medication=ResolveMedicationCall(mention_quote="the other blood pressure pill"),
        sig=[],
        change_kind="continued",
        change_evidence_quote="the other blood pressure pill",
    )
    fabricated = MedicationItem(
        medication=ResolveMedicationCall(
            mention_quote="amlodipine five milligrams at bedtime"),
        sig=[],
        change_kind="new",
        change_evidence_quote="amlodipine five milligrams at bedtime",
    )
    return merge_turns([
        TurnExtraction(medications=[metoprolol, lisinopril, unnamed, fabricated]),
        TurnExtraction(appointments=[AppointmentItem(
            when=ResolveDateCall(phrase_quote="about 10 days",
                                 event_kind="followup_visit"),
            purpose_quote="check the pressure again")]),
        TurnExtraction(red_flags=[
            RedFlagItem(instruction_quote="don't stop it on your own"),
            RedFlagItem(instruction_quote=(
                "If you feel dizzy when you stand up, or your heart feels "
                "like it's racing, call the office.")),
        ]),
        TurnExtraction(loose_threads=[LooseThreadItem(
            topic_quote="we may need to adjust the lysinopril as well")]),
        TurnExtraction(summary_quotes=[
            SummaryQuoteCall(heading="why_you_came_in",
                             quote="I've been checking the pressure at home"),
            SummaryQuoteCall(heading="what_the_doctor_found",
                             quote="that's higher than I want to see"),
            SummaryQuoteCall(heading="what_happens_next",
                             quote="bring the home monitor with you next time"),
        ]),
    ])


@pytest.fixture(scope="session")
def result(session, kb):
    return verify(session, model_output(), kb=kb)


# ------------------------------------------------------------------------ C1

def test_no_free_text_fields():
    """D12, structurally: every `str` is a quote or a closed enum.

    Walks the real JSON schema rather than the class bodies, so a `str` that
    arrives through a nested tool call is caught too."""
    schema = VisitExtraction.model_json_schema()
    offenders = []
    for name, spec in schema.get("$defs", {}).items():
        if name == "SummarySelection":
            # The exception, and it is not a loophole: these three fields hold
            # verbatim quotes and their *names* are the closed enum
            # (`SummaryHeading`). The model never writes a heading; it picks
            # one, which is what D7's extractive summary means.
            continue
        for field, prop in spec.get("properties", {}).items():
            flat = json.dumps(prop)
            is_enum = "enum" in prop or "const" in flat
            if '"type": "string"' in flat and not is_enum:
                if field != "quote" and not field.endswith("_quote"):
                    offenders.append(f"{name}.{field}")
    assert offenders == [], f"free-text fields in the schema: {offenders}"


def test_empty_extraction_is_expressible():
    """A no-content turn must be able to say so — otherwise a constrained
    decoder has to invent an item to satisfy the grammar."""
    assert TurnExtraction().model_dump() == {
        "medications": [], "appointments": [], "red_flags": [],
        "loose_threads": [], "summary_quotes": [],
    }


# ------------------------------------------------------------------------ C4

def test_fabricated_quote_is_dropped_and_counted(session):
    sv = SpanVerifier(session)
    assert sv.verify("amlodipine at bedtime", kind="medication") is None
    assert sv.drop_count == 1
    assert sv.dropped[0].d16_category == 1


def test_real_quote_resolves_to_real_offsets(session):
    sv = SpanVerifier(session)
    q = sv.verify("up to 50 milligrams")
    assert q is not None
    assert session.transcript_text[q.char_offset:q.char_end] == q.text
    assert sv.drop_count == 0


def test_offsets_match_the_golden_fixture(session, golden):
    """C4 computes what 1c located independently — same string, same answer."""
    sv = SpanVerifier(session)
    expected = golden["medications"][0]["mention_quote"]
    q = sv.verify(expected["text"])
    assert (q.char_offset, q.char_end) == (expected["char_offset"],
                                           expected["char_end"])
    assert q.turn_id == expected["turn_id"]
    assert q.turn_role == expected["turn_role"]


def test_multiple_matches_disambiguate_by_nearest_turn(session):
    """D14's third case. 'the' occurs everywhere; the turn decides which one."""
    sv = SpanVerifier(session)
    target = session.turns[20]
    q = sv.verify("the", near=target)
    assert target.char_start <= q.char_offset < target.char_end


def test_drop_count_reaches_the_envelope(result):
    """Dropped silently, counted loudly — D16 category 1's whole compromise."""
    assert result.dropped == 1
    assert result["header"]["discarded"] == 1
    assert result["discarded"][0]["d16_category"] == 1
    assert "amlodipine" not in json.dumps(result.envelope)


# ---------------------------------------------------------------------- C4.5

def test_cross_turn_association_is_flagged(result):
    """The planted case: a sig from turn 20 under a mention from turn 12."""
    med = result["medications"][0]
    cat8 = [f for f in med["flags"] if f["d16_category"] == 8]
    assert cat8, "category 8 never fired — a check that never fires looks clean"
    assert all(f["render"] == "expanded" for f in cat8)
    assert all(len(f["evidence"]) == 2 for f in cat8)
    assert not any(f["blocking"] for f in cat8)


def test_same_turn_association_is_not_flagged(result):
    """The other half, and the one that decides whether the check is usable:
    the sig in the mention's own turn must not be flagged."""
    med = result["medications"][0]
    flagged = {f["evidence"][1]["text"] for f in med["flags"]
               if f["d16_category"] == 8}
    assert "up to 50 milligrams" not in flagged


# ------------------------------------------------------------------------ C5

def test_all_eight_d16_categories_fire(result):
    assert result.categories >= {1, 2, 3, 4, 5, 6, 7, 8}, (
        f"missing: {sorted({1,2,3,4,5,6,7,8} - result.categories)}")


def test_only_two_blocking_cases(result):
    """D16: ambiguous attribution on a dose, and internal contradiction.
    Everything else is glance-and-accept, or D9's budget is gone."""
    blocking = [f for item in result["medications"] for f in item["flags"]
                if f["blocking"]]
    assert {f["d16_category"] for f in blocking} == {3, 7}


def test_category_5_is_a_finding_not_an_error(result):
    """"take as directed" is a complete, correct parse whose finding is that
    no dose exists. It must not look like category 2 or 4."""
    lisinopril = next(m for m in result["medications"]
                      if m["medication"]["canonical_name"] == "lisinopril")
    cat5 = next(f for f in lisinopril["flags"] if f["d16_category"] == 5)
    assert cat5["blocking"] is False
    assert cat5["render"] == "collapsed"
    assert cat5["display"] == "not specified"
    assert lisinopril["disposition"] != "blocking"


def test_unresolved_drug_keeps_the_raw_text(result):
    """Category 4 — prefilled with what was heard, never with a guess."""
    item = next(m for m in result["medications"]
                if m["medication"]["status"] == "unresolved")
    cat4 = next(f for f in item["flags"] if f["d16_category"] == 4)
    assert cat4["heard_text"] == "the other blood pressure pill"
    assert item["medication"]["rxcui"] is None


def test_salt_unspecified_offers_both(result):
    """A5.5 — bare "metoprolol" resolves, and says which question it left open.
    Succinate is once daily; tartrate is twice. Same spoken word."""
    med = result["medications"][0]
    assert med["medication"]["salt_unspecified"] is True
    salt = next(f for f in med["flags"] if f.get("choices")
                and "succinate" in " ".join(f["choices"]))
    assert salt["choices"] == ["metoprolol succinate", "metoprolol tartrate"]


def test_fuzzy_match_shows_heard_and_resolved(result):
    """The resolver catching an ASR error is worth showing, not hiding."""
    lis = next(m for m in result["medications"]
               if m["medication"]["canonical_name"] == "lisinopril")
    assert lis["medication"]["match_type"] == "fuzzy"
    flag = next(f for f in lis["flags"] if f.get("heard_text") == "lisonopril")
    assert flag["resolved_name"] == "lisinopril"


def test_change_kind_is_derived_not_trusted(result):
    """Two parsed clinician doses → arithmetic. Derived prints as fact."""
    med = result["medications"][0]
    assert med["change_kind_derived"] is True
    assert med["change_kind"] == "increased"
    d = med["change_kind_derivation"]
    assert d["from_dose"]["amount"] < d["to_dose"]["amount"]


def test_underived_change_kind_is_flagged(result):
    """And when it cannot be derived, it is never printed as fact."""
    lis = next(m for m in result["medications"]
               if m["medication"]["canonical_name"] == "lisinopril")
    assert lis["change_kind_derived"] is False
    assert any("not derived" in f["reason"] for f in lis["flags"])


def test_loose_thread_is_surfaced(result):
    thread = result["loose_threads"][0]
    assert thread["disposition"] == "surfaced"
    assert thread["d16_categories"] == [6]
    assert "adjust the lysinopril" in thread["topic_quote"]["text"]


def test_appointment_prints_both_forms(result):
    """D18 — a patient reading a bare date cannot catch an error in it."""
    appt = result["appointments"][0]
    assert appt["when"]["resolved_date"] == "2026-09-28"
    assert "Monday, September 28" in appt["when"]["display_string"]
    assert appt["disposition"] == "printed_as_fact"


def test_header_matches_the_items(result):
    """U3 prints this. A header that drifts from its own list is a confident
    lie — and Track D recounts it, so a mismatch surfaces there too."""
    from mnemonica.render.model import Extraction

    parsed = Extraction.parse(result.envelope)
    assert parsed.header() == result["header"]


def test_every_quote_in_the_envelope_verifies(session, result):
    """D14 once more, over the finished envelope: nothing reaches Track D
    whose offsets do not still point at its own text."""
    from mnemonica.render.model import Extraction

    parsed = Extraction.parse(result.envelope)
    for item in parsed.items:
        for quote in item.all_quotes():
            assert quote.verify_against(session), f"{item.id}: {quote.text!r}"
