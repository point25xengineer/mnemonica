"""One appointment said three times is one appointment.

Found by running roleplay_script_2 — a script the system had never seen —
through the pipeline and reading the patient's page, which offered three
follow-up visits on the same day in broken English.
"""

from __future__ import annotations

import pytest

from mnemonica.render.actioncard import _fit_phrase, _fit_purpose
from mnemonica.verify.pipeline import _one_per_appointment


def _appt(phrase, *, date="2026-10-31", kind="followup_visit",
          role="clinician", purpose=None, offset=0):
    return {
        "id": f"appt-{offset}", "kind": "appointment",
        "when": {"quote": {"text": phrase, "char_offset": offset},
                 "event_kind": kind, "resolved_date": date,
                 "original_phrase": phrase},
        "purpose_quote": {"text": purpose} if purpose else None,
        "_turn_role": role, "flags": [],
    }


# --- deduplication --------------------------------------------------------

def test_same_day_same_kind_collapses():
    """The patient repeating the date back is not a second visit."""
    kept = _one_per_appointment([
        _appt("in six weeks", offset=10),
        _appt("Six weeks.", role="other", offset=90),
    ])
    assert len(kept) == 1
    assert kept[0]["when"]["original_phrase"] == "in six weeks"


def test_clinician_phrasing_wins():
    kept = _one_per_appointment([
        _appt("Six weeks.", role="other", offset=10),
        _appt("in six weeks", role="clinician", offset=90),
    ])
    assert kept[0]["when"]["original_phrase"] == "in six weeks"


def test_a_duplicate_donates_its_purpose():
    """Merge, don't discard — the reason may have been captured from the
    turn that lost."""
    kept = _one_per_appointment([
        _appt("in six weeks", offset=10),
        _appt("Six weeks.", role="other", offset=90,
              purpose="see where the sugars have landed"),
    ])
    assert len(kept) == 1
    assert kept[0]["purpose_quote"]["text"] == "see where the sugars have landed"


def test_different_kinds_on_one_day_both_survive():
    """A follow-up visit and a blood test can honestly fall on the same day.
    Merging those would lose an instruction, not a duplicate."""
    kept = _one_per_appointment([
        _appt("in six weeks", kind="followup_visit", offset=10),
        _appt("in six weeks", kind="test_scheduled", offset=90),
    ])
    assert len(kept) == 2


def test_unresolved_dates_are_never_merged():
    """Two things we could not place are not evidence of being the same."""
    kept = _one_per_appointment([
        _appt("before your procedure", date=None, offset=10),
        _appt("after the holidays", date=None, offset=90),
    ])
    assert len(kept) == 2


def test_kept_entries_stay_in_transcript_order():
    kept = _one_per_appointment([
        _appt("in six weeks", date="2026-10-31", offset=200),
        _appt("tomorrow", date="2026-09-20", kind="test_scheduled", offset=20),
    ])
    assert [k["when"]["quote"]["char_offset"] for k in kept] == [20, 200]


def test_internal_role_marker_does_not_leak():
    kept = _one_per_appointment([_appt("in six weeks")])
    assert "_turn_role" not in kept[0]


# --- fitting the phrase into "Come back ___" ------------------------------

@pytest.mark.parametrize("phrase,expected", [
    ("in six weeks", "in six weeks"),
    ("Six weeks.", "six weeks"),
    # The frame supplies the verb; the model correctly quoted the whole clause.
    ("Come back and see me in six weeks", "in six weeks"),
    ("come in three weeks", "in three weeks"),   # keeps the preposition
    ("come back in a month", "in a month"),
])
def test_phrase_fits_the_frame(phrase, expected):
    assert _fit_phrase(phrase) == expected


@pytest.mark.parametrize("phrase", ["Monday morning", "March 3rd", "Tuesday"])
def test_proper_nouns_keep_their_capital(phrase):
    """No test of the letters alone separates "Monday" from "Six"."""
    assert _fit_phrase(phrase) == phrase


# --- fitting the purpose into ", to ___" ----------------------------------

def test_purpose_loses_its_subject():
    """`", to " + "we'll see..."` read as "to we'll see"."""
    assert _fit_purpose("we'll see where the sugars have landed") == \
        "see where the sugars have landed"


def test_bare_infinitive_is_left_alone():
    assert _fit_purpose("check the pressure again") == "check the pressure again"


def test_a_purpose_that_cannot_fit_is_dropped():
    """Decoration on an appointment. A mangled one costs more than none."""
    assert _fit_purpose("it") is None
    assert _fit_purpose("") is None


# --- every POST form must carry what its handler requires -----------------

def test_every_post_form_supplies_its_handlers_fields():
    """/promote shipped without `item_id` and 500'd on click.

    The button looked identical to the working ones, the keyboard shortcut
    routed to the same button, and nothing in the suite touched the template's
    form fields — so it stayed broken from Track D until a real click found
    it. This reads both files and checks they agree.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    html = (root / "mnemonica/render/templates/review.html").read_text()
    app = (root / "mnemonica/ui/app.py").read_text()

    forms = {}
    for match in re.finditer(
        r'<form[^>]*action="(/[a-z]+)"[^>]*>(.*?)</form>', html, re.S
    ):
        action, body = match.group(1), match.group(2)
        names = set(re.findall(r'name="([a-z_]+)"', body))
        forms.setdefault(action, set()).update(names)

    required = {}
    for match in re.finditer(
        r'if path == "(/[a-z]+)":\n(.*?)(?=\n        if path|\n\n)', app, re.S
    ):
        required[match.group(1)] = set(re.findall(r'need\(([^)]*)\)', match.group(2)))

    for action, fields in required.items():
        wanted = {f.strip().strip('"') for part in fields for f in part.split(",")}
        wanted.discard("")
        if not wanted or action not in forms:
            continue
        missing = wanted - forms[action]
        assert not missing, (
            f'form action="{action}" posts {sorted(forms[action])} but the '
            f"handler needs {sorted(wanted)} — missing {sorted(missing)}"
        )
