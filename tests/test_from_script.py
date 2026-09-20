"""The script-to-Session shortcut (dev loop, not a pipeline stage)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from mnemonica.audio.from_script import parse_script, session_from_script

SCRIPT = Path(__file__).resolve().parents[1] / "fixtures" / "roleplay_script_2.md"


def test_parses_only_the_script_section():
    """The expectations table and casting notes must not become turns."""
    turns = parse_script(SCRIPT.read_text())
    assert len(turns) > 20
    spoken = " ".join(t for _, t in turns)
    assert "Known bugs" not in spoken
    assert "expectations" not in spoken.lower()


def test_roles_come_from_the_speaker_labels():
    turns = parse_script(SCRIPT.read_text())
    labels = {label for label, _ in turns}
    assert labels == {"DR", "PT"}


def test_stage_directions_are_not_spoken():
    """`*(overlapping)*` is a note to the reader."""
    spoken = " ".join(t for _, t in parse_script(SCRIPT.read_text()))
    assert "overlapping" not in spoken


def test_offsets_index_into_the_transcript():
    """The D14 bridge. `Session`'s validator enforces it, so construction
    succeeding is the assertion — but check it explicitly too, because this
    is the one that silently breaks everything downstream."""
    s = session_from_script(SCRIPT.read_text(), session_dir=Path("sessions/x"))
    for turn in s.turns:
        assert s.transcript_text[turn.char_start:turn.char_end] == turn.text
        for w in turn.words:
            assert s.transcript_text[w.char_offset:w.char_end] == w.text


def test_visit_date_anchors_relative_dates():
    s = session_from_script(SCRIPT.read_text(), session_dir=Path("sessions/x"),
                            visit_date=date(2026, 9, 19))
    assert s.visit_date == date(2026, 9, 19)


def test_probabilities_are_all_certain():
    """Documented limitation: a script cannot mumble, so D16 category 2
    (low-confidence transcription) can never fire from one. Asserted so the
    limitation stays visible rather than becoming a surprise."""
    s = session_from_script(SCRIPT.read_text(), session_dir=Path("sessions/x"))
    assert all(w.probability == 1.0 for t in s.turns for w in t.words)


def test_empty_script_is_an_error_not_an_empty_session():
    with pytest.raises(ValueError, match="no dialogue"):
        session_from_script("# Notes\n\nNothing spoken here.",
                            session_dir=Path("sessions/x"))
