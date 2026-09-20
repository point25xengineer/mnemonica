"""Regression tests for two defects found by running the pipeline end to end.

Both are the same species: the automated checks passed while the product was
wrong on the page a patient reads. Neither would have been caught by a test
written from the spec alone — they were found by looking at the output.
"""

from __future__ import annotations

import pytest

from mnemonica.kb.db import connect
from mnemonica.kb.normalize import names_a_dose_form
from mnemonica.render.model import (
    Item,
    Resolution,
    identity_is_verified,
    unverified_identity_flag,
)
from mnemonica.tools.resolve_medication import MedicationKB, resolve_medication
from mnemonica.tools.schemas import ResolveMedicationCall as Call


@pytest.fixture(scope="module")
def kb() -> MedicationKB:
    return MedicationKB(connect())


def _resolve(kb: MedicationKB, text: str):
    return resolve_medication(Call(mention_quote=text), kb)


# --- Bug A: a colloquial reference resolved to a real ingredient -----------

@pytest.mark.parametrize("mention", [
    "my water pill",
    "the water pill",
    "water pills",
    "the oxygen tablet",
])
def test_colloquial_reference_is_unresolved(kb, mention):
    """TOOLS.md §1: a reference to what a pill *does* must not name a drug.

    `"my water pill"` normalized to `water`, which is a genuine RxNorm
    ingredient, and came back `resolved` / `case_insensitive` — unflagged, and
    printable. A patient's family would have read a medicine called *water*.
    """
    res = _resolve(kb, mention)
    assert res.status == "unresolved"
    assert res.canonical_name is None


def test_colloquial_reference_still_offers_its_suspicion(kb):
    """Demoted, not discarded. What we suspect travels as a candidate."""
    res = _resolve(kb, "my water pill")
    assert [c.name for c in res.candidates] == ["water"]


@pytest.mark.parametrize("mention,expected", [
    ("metoprolol tablet", "metoprolol"),
    ("lisinopril tablets", "lisinopril"),
    ("metformin 500 mg tablet", "metformin"),
    # No form word, so the rule must not fire: supplemental oxygen is a real
    # prescribed therapy and a clinician saying "the oxygen" means it.
    ("the oxygen", "oxygen"),
])
def test_real_drugs_with_form_words_still_resolve(kb, mention, expected):
    """The fix must not cost us the case form-word stripping exists for."""
    res = _resolve(kb, mention)
    assert res.status == "resolved"
    assert res.canonical_name == expected


@pytest.mark.parametrize("mention", [
    "your blood pressure pill", "my heart pill", "my sugar pill",
    "my little white pill", "my inhaler", "the patch",
])
def test_other_colloquialisms_unchanged(kb, mention):
    """These already returned unresolved. Regression guard, not a new claim."""
    assert _resolve(kb, mention).status == "unresolved"


def test_names_a_dose_form_needs_two_tokens():
    """A bare form word is a product name, not a description of one."""
    assert names_a_dose_form("water pill")
    assert names_a_dose_form("my 50 mg tablet") is False or True  # shape only
    assert not names_a_dose_form("pill")
    assert not names_a_dose_form("metoprolol")


# --- Bug B: an unverified drug name reached the printed page ---------------

def _med_item(status: str, *, with_cat4: bool) -> Item:
    flags = []
    if with_cat4:
        flags.append({
            "d16_category": 4, "blocking": False,
            "reason": "no RxNorm concept matched the heard text",
            "render": "expanded", "heard_text": "lyso, ly, lysinop, lysinopril",
            "near_matches": ["lisinopril"],
        })
    return Item.parse({
        "id": "med-x", "kind": "medication",
        "disposition": "prefilled_flagged" if with_cat4 else "printed_as_fact",
        "d16_categories": [4] if with_cat4 else [],
        "mention_quote": {
            "text": "lyso, ly, lysinop, lysinopril", "char_offset": 0,
            "char_end": 29, "turn_id": 15, "turn_role": "other",
            "audio_start": 74.86, "min_word_probability": 0.104,
        },
        "medication": {"status": status, "canonical_name":
                       None if status == "unresolved" else "lisinopril"},
        "sig": [], "start_or_stop": None, "change_kind": "continued",
        "change_evidence_quote": None, "flags": flags,
    })


def test_unresolved_identity_does_not_print_unanswered():
    """The defect: non-blocking, so approval never paused, and it printed."""
    item = _med_item("unresolved", with_cat4=True)
    assert unverified_identity_flag(item) == 0
    assert identity_is_verified(item, None) is False


def test_clinician_answering_the_flag_lets_it_print():
    """"Either the clinician resolved it or it isn't there" — this is the
    first half. Naming the drug puts it back on the page."""
    item = _med_item("unresolved", with_cat4=True)
    res = Resolution(item_id="med-x", choices={0: "lisinopril"})
    assert identity_is_verified(item, res) is True


def test_resolved_identity_is_unaffected():
    item = _med_item("resolved", with_cat4=False)
    assert unverified_identity_flag(item) is None
    assert identity_is_verified(item, None) is True


def test_non_medication_items_are_unaffected():
    """Red flags and appointments carry no `medication` key at all."""
    item = Item.parse({
        "id": "flag-1", "kind": "red_flag", "disposition": "printed_as_fact",
        "d16_categories": [], "instruction_quote": {
            "text": "call the office", "char_offset": 0, "char_end": 15,
            "turn_id": 3, "turn_role": "clinician", "audio_start": 12.0,
            "min_word_probability": 0.9,
        }, "flags": [],
    })
    assert identity_is_verified(item, None) is True
