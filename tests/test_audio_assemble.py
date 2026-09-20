"""B4's acceptance criteria, as tests that need no models.

Assembly is the step everything else rests on — it produces the string span
verification searches and the offsets every citation resolves through — and it
is also the only step in Track B that is pure arithmetic. So it gets tested
directly, with hand-built inputs, rather than only through a 3-minute pipeline
run that needs 3 GB of weights.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from visitnotes.audio.assemble import assemble  # noqa: E402
from visitnotes.audio.diarize import Diarization, Interval  # noqa: E402
from visitnotes.audio.transcribe import RawWord, Segment, Transcript  # noqa: E402

DR, PT = "SPEAKER_00", "SPEAKER_01"


def _segment(seg_id=0, *, compression_ratio=1.0, no_speech_prob=0.0):
    return Segment(
        id=seg_id,
        start=0.0,
        end=60.0,
        text="",
        avg_logprob=-0.2,
        compression_ratio=compression_ratio,
        no_speech_prob=no_speech_prob,
    )


def _words(*specs, segment_id=0):
    return [
        RawWord(text=t, start=s, end=e, probability=p, segment_id=segment_id)
        for t, s, e, p in specs
    ]


def _transcript(words, segments=None):
    return Transcript(
        words=words, segments=segments or [_segment()], language="en"
    )


def _diarization(*intervals):
    return Diarization(
        intervals=[Interval(*iv) for iv in intervals],
        labels=sorted({iv[2] for iv in intervals}),
    )


ROLES = {DR: "clinician", PT: "other"}


def test_offsets_index_into_transcript_text():
    """The assertion B4 exists to satisfy — and the one that, when wrong,
    breaks every citation without raising anything."""
    t = _transcript(
        _words(
            ("Right", 0.0, 0.4, 0.99),
            ("now", 0.4, 0.7, 0.98),
            ("you're", 0.7, 1.0, 0.97),
            ("taking", 1.0, 1.4, 0.99),
            ("metoprolol.", 1.4, 2.1, 0.88),
            ("The", 3.0, 3.2, 0.95),
            ("white", 3.2, 3.6, 0.93),
            ("one?", 3.6, 4.0, 0.91),
        )
    )
    a = assemble(t, _diarization((0.0, 2.5, DR), (2.8, 4.2, PT)), ROLES)

    assert a.transcript_text == "Right now you're taking metoprolol. The white one?"
    for turn in a.turns:
        assert a.transcript_text[turn.char_start : turn.char_end] == turn.text
        for w in turn.words:
            assert a.transcript_text[w.char_offset : w.char_end] == w.text


def test_word_outside_every_interval_is_dropped_not_snapped():
    """Whisper's silence inventions land exactly where pyannote found no
    speech. Snapping one to the nearest speaker turns a hallucination into an
    attributed, quotable span — strictly worse than deleting it."""
    t = _transcript(
        _words(
            ("Okay.", 0.0, 0.5, 0.99),
            ("Thanks", 30.0, 30.4, 0.41),  # over the silence
            ("for", 30.4, 30.6, 0.38),
            ("watching!", 30.6, 31.2, 0.35),
            ("Right.", 50.0, 50.5, 0.97),
        )
    )
    a = assemble(t, _diarization((0.0, 1.0, DR), (49.5, 51.0, PT)), ROLES)

    assert a.transcript_text == "Okay. Right."
    assert [d.text for d in a.dropped] == ["Thanks", "for", "watching!"]
    assert all("no diarization interval" in d.reason for d in a.dropped)
    # And it is gone from the search string, so no quote can ever cite it.
    assert "watching" not in a.transcript_text


def test_twenty_seconds_of_silence_produces_no_words():
    """B4's stated done-when, verbatim."""
    t = _transcript(
        _words(("Mm-hm.", 1.0, 1.4, 0.9))
        + _words(*[(f"w{i}", 5.0 + i, 5.4 + i, 0.3) for i in range(20)])
    )
    a = assemble(t, _diarization((0.5, 2.0, DR)), ROLES)

    assert a.transcript_text == "Mm-hm."
    assert len(a.dropped) == 20
    for turn in a.turns:
        for w in turn.words:
            assert not (5.0 <= w.start < 25.0)


def test_adjacent_intervals_of_one_voice_become_one_turn():
    """exclusive_speaker_diarization emits one interval per contiguous stretch
    and can emit several in a row for the same speaker. Fixture 1c merges
    consecutive same-speaker lines for exactly this reason, so B5's diff would
    be noise if assembly did not."""
    t = _transcript(
        _words(
            ("No,", 0.0, 0.3, 0.99),
            ("saying", 0.5, 0.9, 0.98),
            ("yes", 1.2, 1.5, 0.97),
            ("is", 2.6, 2.8, 0.96),
            ("enough.", 2.9, 3.4, 0.95),
        )
    )
    a = assemble(t, _diarization((0.0, 2.0, DR), (2.5, 3.6, DR)), ROLES)

    assert len(a.turns) == 1
    assert a.turns[0].text == "No, saying yes is enough."
    assert a.turns[0].role == "clinician"


def test_word_straddling_a_boundary_goes_to_whoever_said_most_of_it():
    t = _transcript(_words(("overlap", 1.8, 2.6, 0.8)))
    a = assemble(t, _diarization((0.0, 2.0, DR), (2.0, 4.0, PT)), ROLES)
    assert a.turns[0].speaker_cluster == PT  # 0.6 s of it vs 0.2 s


def test_unmapped_cluster_becomes_unknown_not_a_guess():
    """A cluster enrollment could not place is `unknown`, which makes every
    dose from it a D16 category 3 blocking item (D20)."""
    t = _transcript(_words(("Fifty", 0.0, 0.5, 0.9), ("milligrams.", 0.5, 1.2, 0.9)))
    a = assemble(t, _diarization((0.0, 1.5, "SPEAKER_07")), roles={})
    assert a.turns[0].role == "unknown"


def test_suspect_segments_are_flagged_not_deleted():
    """D16 category 2 reads the flag. Deleting text Whisper was merely unsure
    about would remove it from the transcript the clinician reviews."""
    words = _words(("Subscribe", 0.0, 0.6, 0.55), ("now.", 0.6, 1.0, 0.5))
    t = _transcript(words, segments=[_segment(0, compression_ratio=3.1)])
    a = assemble(t, _diarization((0.0, 1.2, DR)), ROLES)

    assert a.suspect_segments == [0]
    assert a.transcript_text == "Subscribe now."


def test_assembled_session_round_trips_through_the_contract():
    """Assembly's output has to survive `Session`'s validators, which run the
    same offset check independently."""
    from datetime import date, datetime

    from visitnotes.contracts import Consent, Session

    t = _transcript(
        _words(
            ("Bring", 0.0, 0.4, 0.99),
            ("it", 0.4, 0.6, 0.98),
            ("to", 0.6, 0.8, 0.97),
            ("50.", 0.8, 1.3, 0.92),
            ("Alright.", 2.0, 2.6, 0.95),
        )
    )
    a = assemble(t, _diarization((0.0, 1.5, DR), (1.9, 2.8, PT)), ROLES)

    session = Session(
        visit_date=date(2026, 9, 19),
        session_dir=Path("sessions/x"),
        audio_path=Path("sessions/x/visit.m4a"),
        transcript_text=a.transcript_text,
        turns=a.turns,
        consent=Consent(
            obtained=True, method="verbal", obtained_at=datetime(2026, 9, 19, 9, 0)
        ),
    )
    assert session.turn_at_offset(session.transcript_text.index("50.")).role == "clinician"
    assert [t.role for t in session.clinician_turns()] == ["clinician"]


def test_offsets_survive_repeated_words():
    """`str.index` from a moving cursor, not from 0 — a turn that says the same
    word twice must not give both occurrences the first one's offset."""
    t = _transcript(
        _words(
            ("Ninety", 0.0, 0.4, 0.9),
            ("over", 0.4, 0.6, 0.9),
            ("ninety.", 0.6, 1.1, 0.9),
            ("Ninety", 1.2, 1.6, 0.9),
        )
    )
    a = assemble(t, _diarization((0.0, 2.0, DR)), ROLES)
    offsets = [w.char_offset for w in a.turns[0].words]
    assert len(set(offsets)) == len(offsets)
    for w in a.turns[0].words:
        assert a.transcript_text[w.char_offset : w.char_end] == w.text


def test_empty_after_dropping_produces_no_turns():
    """A recording that is all silence is an empty transcript, not a crash."""
    t = _transcript(_words(("Thank", 10.0, 10.4, 0.3), ("you.", 10.4, 10.8, 0.3)))
    a = assemble(t, _diarization((0.0, 1.0, DR)), ROLES)
    assert a.turns == []
    assert a.transcript_text == ""
    assert len(a.dropped) == 2
