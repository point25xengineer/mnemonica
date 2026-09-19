"""The contract's invariants, as tests — 1a.

These are not ceremony. Each one is a failure that is silent in production:
an off-by-one offset breaks every citation without raising, an audio file
outside the session directory survives U9's shred, and a session without
consent reaches review in violation of D27.
"""

from datetime import date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from visitnotes.contracts import Consent, Session, Turn, Word

TRANSCRIPT = "Let's increase the metoprolol. Okay, fifty milligrams?"
CLINICIAN_TEXT = "Let's increase the metoprolol."
PATIENT_TEXT = "Okay, fifty milligrams?"


def _words(text: str, cluster: str) -> list[Word]:
    """Word objects whose offsets genuinely index into TRANSCRIPT."""
    words, cursor = [], TRANSCRIPT.index(text)
    for token in text.split():
        offset = TRANSCRIPT.index(token, cursor)
        cursor = offset + len(token)
        words.append(
            Word(
                text=token,
                start=0.0,
                end=0.5,
                probability=0.95,
                speaker_cluster=cluster,
                char_offset=offset,
            )
        )
    return words


def _turn(id: int, text: str, cluster: str, role: str) -> Turn:
    start = TRANSCRIPT.index(text)
    return Turn(
        id=id,
        speaker_cluster=cluster,
        role=role,
        start=float(id),
        end=float(id) + 1.0,
        words=_words(text, cluster),
        text=text,
        char_start=start,
        char_end=start + len(text),
    )


def _consent() -> Consent:
    return Consent(
        obtained=True, method="verbal", obtained_at=datetime(2026, 9, 18, 9, 0)
    )


def _session(**overrides) -> Session:
    kwargs = dict(
        visit_date=date(2026, 9, 18),
        session_dir=Path("fixtures/sessions/golden"),
        audio_path=Path("fixtures/sessions/golden/visit.wav"),
        transcript_text=TRANSCRIPT,
        turns=[
            _turn(0, CLINICIAN_TEXT, "SPEAKER_00", "clinician"),
            _turn(1, PATIENT_TEXT, "SPEAKER_01", "other"),
        ],
        consent=_consent(),
    )
    return Session(**(kwargs | overrides))


def test_a_valid_session_constructs():
    assert len(_session().turns) == 2


def test_word_offsets_must_index_into_transcript_text():
    """B4's assertion. A wrong offset raises at construction, not at citation."""
    turn = _turn(0, CLINICIAN_TEXT, "SPEAKER_00", "clinician")
    broken = turn.words[0].model_copy(update={"char_offset": turn.words[0].char_offset + 1})
    with pytest.raises(ValidationError, match="claims offset"):
        _session(turns=[turn.model_copy(update={"words": [broken, *turn.words[1:]]})])


def test_turn_text_must_match_its_char_span():
    turn = _turn(0, CLINICIAN_TEXT, "SPEAKER_00", "clinician")
    with pytest.raises(ValidationError):
        _session(turns=[turn.model_copy(update={"char_start": turn.char_start + 1})])


def test_a_word_may_not_escape_its_turn():
    clinician = _turn(0, CLINICIAN_TEXT, "SPEAKER_00", "clinician")
    stray = _words(PATIENT_TEXT, "SPEAKER_00")[0]  # a word from turn 1's span
    with pytest.raises(ValidationError, match="outside the turn"):
        Turn(
            **clinician.model_dump()
            | {"words": [w.model_dump() for w in (*clinician.words, stray)]}
        )


def test_turn_at_offset_finds_the_source_turn():
    """C4.5: a quote's offset answers which turn it came from (D16 cat 8)."""
    session = _session()
    assert session.turn_at_offset(TRANSCRIPT.index("metoprolol")).id == 0
    assert session.turn_at_offset(TRANSCRIPT.index("fifty")).id == 1
    assert session.turn_at_offset(len(TRANSCRIPT) + 10) is None


def test_clinician_turns_excludes_the_patient():
    """D19: a dose may only be extracted from a clinician turn."""
    assert [t.id for t in _session().clinician_turns()] == [0]


def test_consent_cannot_be_unobtained():
    """D27."""
    with pytest.raises(ValidationError, match="D27"):
        Consent(obtained=False, method="verbal", obtained_at=datetime(2026, 9, 18, 9, 0))


def test_session_requires_consent():
    with pytest.raises(ValidationError):
        Session(
            visit_date=date(2026, 9, 18),
            session_dir=Path("s"),
            audio_path=Path("s/visit.wav"),
            transcript_text=TRANSCRIPT,
            turns=[_turn(0, CLINICIAN_TEXT, "SPEAKER_00", "clinician")],
        )


@pytest.mark.parametrize(
    "session_dir,audio_path,why",
    [
        ("sessions/a", "sessions/b/visit.wav", "audio outside the session dir"),
        ("/tmp/s", "visit.wav", "one absolute, one relative"),
        ("sessions/a", "sessions/a/../b/visit.wav", "'..' escapes containment"),
    ],
)
def test_audio_must_live_inside_the_session_dir(session_dir, audio_path, why):
    """U9 shreds the directory; audio stored elsewhere survives approval."""
    with pytest.raises(ValidationError):
        _session(session_dir=Path(session_dir), audio_path=Path(audio_path))


def test_turn_ids_are_unique_and_ascending():
    turns = _session().turns
    with pytest.raises(ValidationError, match="ascending"):
        _session(turns=[turns[1].model_copy(update={"id": 1}), turns[0].model_copy(update={"id": 0})])


def test_round_trips_through_json():
    """The fixture loads as a Session — 1c's acceptance criterion."""
    session = _session()
    assert Session.model_validate_json(session.model_dump_json()) == session
