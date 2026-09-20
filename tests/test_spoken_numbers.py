"""Doses arrive as words, because they are spoken.

`"twenty-five mg"` parsed to **5.0** — not None, not flagged, just wrong and
printed as fact. The hyphen is a word boundary, so an alternation of single
number words matched `five mg` and dropped the `twenty`. A dose five times too
small is the exact outcome the product exists to prevent, and it was the
quietest possible version of it.
"""

from __future__ import annotations

import pytest

from mnemonica.tools.parse_sig import _number, parse_sig
from mnemonica.tools.schemas import ParseSigCall as Call


def dose(text: str):
    r = parse_sig(Call(sig_quote=text))
    return r.dose_amount, r.dose_unit


# --- the bug --------------------------------------------------------------

def test_hyphenated_compound_is_not_its_last_word():
    """The regression. 25, never 5."""
    assert dose("twenty-five mg at night") == (25.0, "mg")


@pytest.mark.parametrize("text,expected", [
    ("five hundred milligrams twice a day", 500.0),
    ("a thousand milligrams twice a day", 1000.0),
    ("two hundred and fifty mg", 250.0),
])
def test_scale_words_compose(text, expected):
    """`hundred` and `thousand` had no entry at all, so these parsed to None
    — safe, but it silently cost the dose on every spoken prescription."""
    assert dose(text)[0] == expected


@pytest.mark.parametrize("word,value", [
    ("thirteen", 13), ("fifteen", 15), ("sixteen", 16), ("seventeen", 17),
    ("eighteen", 18), ("nineteen", 19), ("forty", 40), ("fifty", 50),
    ("seventy", 70), ("eighty", 80),
])
def test_numbers_that_were_missing_from_the_table(word, value):
    """`fifteen` and `fifty` were both absent — the pair most easily confused
    by ear, and the one D16 category 2 exists to flag."""
    assert dose(f"{word} milligrams once a day")[0] == float(value)


def test_longest_match_wins():
    """`seventeen` must not be read as `seven`."""
    assert dose("seventeen mg daily")[0] == 17.0
    assert dose("seven mg daily")[0] == 7.0


# --- folding --------------------------------------------------------------

@pytest.mark.parametrize("phrase,value", [
    ("twenty-five", 25.0),
    ("five hundred", 500.0),
    ("a thousand", 1000.0),
    ("one thousand two hundred and fifty", 1250.0),
    ("7.5", 7.5),
    ("half", 0.5),
])
def test_number_phrases_fold(phrase, value):
    assert _number(phrase) == value


def test_a_non_number_is_an_error_not_a_zero():
    """Returning 0.0 for unparseable text would be a silent wrong dose again."""
    with pytest.raises(ValueError):
        _number("as directed")


# --- nothing that worked before may stop working --------------------------

@pytest.mark.parametrize("text,expected", [
    ("500 mg twice a day", (500.0, "mg")),
    ("25 mg at night", (25.0, "mg")),
    ("ten milligrams once a day", (10.0, "mg")),
    ("take two tablets daily", (2.0, "tablet")),
    ("one tablet twice daily with food", (1.0, "tablet")),
    ("half a tablet at night", (0.5, "tablet")),
])
def test_existing_forms_are_unchanged(text, expected):
    assert dose(text) == expected


def test_as_directed_still_reports_not_specified():
    """D16 category 5. A wider number grammar must not turn "no dose was
    stated" into a parse failure."""
    assert parse_sig(Call(sig_quote="take it as directed")).status == "not_specified"
