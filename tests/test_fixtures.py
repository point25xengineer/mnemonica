"""1c's acceptance criteria, as tests.

The phase file's done-when for 1c is: `golden_visit.json` validates against
`Session`, `golden_extraction.json` carries a dispositioned item for every
D16 row, and every row is present and findable. "Findable" is the word that
matters — a fixture nobody can assert against is a document, not a test plan.

These tests are also the first real exercise of D14: every quote in the
extraction fixture is re-located here by `str.find` over the transcript, the
same way C4 will do it, and the recorded offsets must agree.
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from visitnotes.contracts import Session

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"


@pytest.fixture(scope="module")
def session() -> Session:
    """1c-i — and loading it at all is B4's offset assertion running."""
    return Session.model_validate_json((FIXTURES / "golden_visit.json").read_text())


@pytest.fixture(scope="module")
def extraction() -> dict:
    return json.loads((FIXTURES / "golden_extraction.json").read_text())


@pytest.fixture(scope="module")
def items(extraction) -> list[dict]:
    return [
        *extraction["medications"],
        *extraction["appointments"],
        *extraction["red_flags"],
        *extraction["loose_threads"],
    ]


# --- 1c-i ------------------------------------------------------------------


def test_golden_visit_validates_as_a_session(session):
    assert len(session.turns) == 35
    assert session.visit_date == date(2026, 9, 18)


def test_visit_date_is_a_weekday(session):
    """D18's demo trap. A weekend visit date prints weekend follow-ups."""
    assert session.visit_date.weekday() < 5, session.visit_date.strftime("%A")


def test_turns_alternate_speakers(session):
    """What exclusive_speaker_diarization actually emits.

    Two adjacent turns from one voice is something pyannote would merge, so a
    fixture containing them predicts output the real pipeline cannot produce
    and makes B5's diff noisy.
    """
    clusters = [t.speaker_cluster for t in session.turns]
    assert all(a != b for a, b in zip(clusters, clusters[1:]))


def test_turns_do_not_overlap_in_time(session):
    """Ditto: exclusive diarization strips overlapping speech."""
    for a, b in zip(session.turns, session.turns[1:]):
        assert a.end <= b.start, f"turn {a.id} overlaps turn {b.id}"


def test_word_probabilities_actually_vary(session):
    """A fixture where every word is 0.99 tests nothing D16 category 2 wants."""
    probs = [w.probability for t in session.turns for w in t.words]
    assert min(probs) < 0.5 < max(probs)


def test_a_dose_numeral_carries_low_confidence(session):
    """D16 category 2, planted at turn 9."""
    turn = next(t for t in session.turns if t.id == 9)
    word = next(w for w in turn.words if "sixty-two" in w.text)
    assert word.probability < 0.5


def test_one_turn_has_an_unknown_role(session):
    """D16 category 3 needs a turn whose speaker role is not established."""
    unknown = [t for t in session.turns if t.role == "unknown"]
    assert len(unknown) == 1
    assert "twenty-fives" in unknown[0].text  # and it contains a dose


# --- 1c-ii -----------------------------------------------------------------


def test_track_d_can_render_without_track_c(extraction):
    """The whole point of 1c-ii: a Session has no items to put on a screen."""
    assert extraction["medications"], "Track D is blocked without this"
    assert extraction["header"]["discarded"] >= 1


ALL_D16 = {1, 2, 3, 4, 5, 6, 7, 8}


def test_every_d16_category_is_present(extraction, items, session):
    """Eight now, not seven."""
    found = {c for item in items for c in item["d16_categories"]}
    found |= {d["d16_category"] for d in extraction["discarded"]}
    # Category 2 lives in the transcript's probabilities, not in a disposition.
    found |= {2} if any(
        w.probability < 0.5 for t in session.turns for w in t.words
    ) else set()
    assert found >= ALL_D16, f"missing {sorted(ALL_D16 - found)}"


def _quotes(node):
    """Every located quote anywhere in the tree."""
    if isinstance(node, dict):
        if "char_offset" in node and "text" in node:
            yield node
        for value in node.values():
            yield from _quotes(value)
    elif isinstance(node, list):
        for value in node:
            yield from _quotes(value)


def test_every_quote_verifies_against_the_transcript(extraction, session):
    """D14, run for real: our code finds the offsets, nothing asserts them."""
    text = session.transcript_text
    located = list(_quotes(extraction))
    assert len(located) > 15
    for q in located:
        assert text.count(q["text"]) == 1, f"{q['text']!r} is not unique"
        assert text.index(q["text"]) == q["char_offset"], q["text"]
        assert text[q["char_offset"] : q["char_end"]] == q["text"]


def test_every_quote_knows_its_turn(extraction, session):
    """Step 3 of the verification order — and what category 8 compares."""
    for q in _quotes(extraction):
        turn = session.turn_at_offset(q["char_offset"])
        assert turn is not None and turn.id == q["turn_id"]
        assert turn.role == q["turn_role"]


def test_category_8_evidence_spans_two_different_turns(extraction):
    """The failure span verification structurally cannot see.

    Both quotes are genuine and both pass D14. The only way to catch it is to
    compare which turn each one came from.
    """
    med = next(m for m in extraction["medications"] if 8 in m["d16_categories"])
    flag = next(f for f in med["flags"] if f["d16_category"] == 8)
    turns = {q["turn_id"] for q in flag["evidence"]}
    assert len(turns) == 2, "category 8 with one turn is not category 8"
    assert flag["render"] == "expanded", "category 8 is never collapsed"


def test_category_3_dose_came_from_a_non_clinician_turn(extraction):
    """D19: a dose may only be extracted from a clinician turn."""
    med = next(m for m in extraction["medications"] if 3 in m["d16_categories"])
    sig = next(s for s in med["sig"] if s.get("blocking_reason") == "attribution_ambiguous")
    assert sig["quote"]["turn_role"] != "clinician"
    assert sig["dose_amount"] is not None


def test_category_7_shows_two_different_doses_with_timestamps(extraction):
    med = next(m for m in extraction["medications"] if 7 in m["d16_categories"])
    flag = next(f for f in med["flags"] if f["d16_category"] == 7)
    doses = {q["turn_id"] for q in flag["evidence"]}
    assert len(doses) == 2
    assert all("audio_start" in q for q in flag["evidence"]), "D16 cat 7 shows timestamps"
    assert med["disposition"] == "blocking"


def test_category_5_is_not_an_error(extraction):
    """"Your doctor never said it" must not look like "I could not hear it"."""
    med = next(m for m in extraction["medications"] if 5 in m["d16_categories"])
    sig = med["sig"][0]
    assert sig["status"] == "not_specified"
    assert sig["status"] != "unparseable"
    assert sig["parse_confidence"] > 0.9, "a successful parse, not a failed one"


def test_the_unresolved_drug_keeps_its_heard_text(extraction):
    """D16 category 4 — prefilled with what was heard, never blanked."""
    med = next(m for m in extraction["medications"] if 4 in m["d16_categories"])
    assert med["medication"]["status"] == "unresolved"
    flag = next(f for f in med["flags"] if f["d16_category"] == 4)
    assert flag["heard_text"] == "the other blood pressure pill"


def test_the_loose_thread_is_never_resolved_later(extraction, session):
    """Category 6 is only category 6 if nobody comes back to it."""
    thread = extraction["loose_threads"][0]
    after = [t for t in session.turns if t.id > thread["topic_quote"]["turn_id"]]
    assert not any("adjust" in t.text and "lisinopril" in t.text for t in after)


def test_salt_is_never_specified_anywhere_in_the_visit(session, extraction):
    """A5.5 — the flag only fires because nobody says a salt."""
    assert "succinate" not in session.transcript_text
    assert "tartrate" not in session.transcript_text
    med = next(m for m in extraction["medications"] if m["id"] == "med-metoprolol")
    assert med["medication"]["salt_unspecified"] is True
    assert len(med["medication"]["salt_candidates"]) == 2


def test_change_kind_is_only_fact_when_derived(extraction):
    """U6 — the verb of the headline sentence.

    "Dr. Osei increased your metoprolol" is printable because two parsed doses
    made it arithmetic. Everywhere else it is prefilled and flagged.
    """
    for med in extraction["medications"]:
        if med["change_kind_derived"]:
            d = med["change_kind_derivation"]
            assert d["from_dose"]["amount"] != d["to_dose"]["amount"]
            assert (med["change_kind"] == "increased") == (
                d["to_dose"]["amount"] > d["from_dose"]["amount"]
            )
        else:
            assert med["change_kind_derivation"] is None
            assert med["disposition"] != "printed_as_fact"


def test_discarded_items_carry_no_text(extraction):
    """D16 category 1: counted, never shown.

    The clinician sees the number and not the fabrication. If a quote field
    ever appears here, the rule has been broken.
    """
    for d in extraction["discarded"]:
        assert d["d16_category"] == 1
        assert not any(k in d for k in ("quote", "text", "mention_quote"))
    assert extraction["header"]["discarded"] == len(extraction["discarded"])


def test_the_followup_date_is_a_weekday(extraction):
    """The trap D18 calls out by name: no weekend appointment on a medical
    document. Ten days, not two weeks."""
    when = extraction["appointments"][0]["when"]
    resolved = date.fromisoformat(when["resolved_date"])
    assert resolved.weekday() < 5, resolved.strftime("%A")
    assert (resolved - date.fromisoformat(when["anchor_date"])).days % 7 != 0


def test_the_followup_prints_both_forms(extraction):
    """D18 — a patient reading a bare date cannot catch an error."""
    when = extraction["appointments"][0]["when"]
    assert when["original_phrase"] in when["display_string"]
    assert "Monday, September 28" in when["display_string"]


def test_the_summary_is_extractive_only(extraction, session):
    """D7 — selected verbatim quotes under fixed headings, no generated prose."""
    summary = extraction["summary_quotes"]
    assert set(summary) == {
        "why_you_came_in",
        "what_the_doctor_found",
        "what_happens_next",
    }
    for quotes in summary.values():
        assert quotes
        for q in quotes:
            assert q["text"] in session.transcript_text


# --- the two fixtures and the script cannot drift --------------------------


def test_regenerating_changes_nothing():
    """Committed fixtures match what the builder produces, and the script's
    generated block matches the TURNS that built them."""
    before = {
        p.name: p.read_text()
        for p in (
            FIXTURES / "golden_visit.json",
            FIXTURES / "golden_extraction.json",
            FIXTURES / "roleplay_script.md",
        )
    }
    subprocess.run(
        [sys.executable, str(FIXTURES / "build_golden.py")], check=True, cwd=ROOT
    )
    subprocess.run(
        [sys.executable, str(FIXTURES / "build_golden.py"), "--script"],
        check=True,
        cwd=ROOT,
    )
    for name, text in before.items():
        assert (FIXTURES / name).read_text() == text, f"{name} is out of sync"
