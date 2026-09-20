"""B3's role assignment and B6's unexpected-speaker check, on synthetic vectors.

The real evidence for both lives in a pipeline run (see PLAN.md's B3/B6 log
entries): a proxy enrollment picks the clinician at cosine distance 0.095
against 0.937, and a spliced three-speaker file raises the flag at the right
timestamp while the genuine take stays silent. What is tested here is the
*decision logic* around those numbers — the abstain rules and the override —
because that is where a wrong answer is silent rather than loud.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mnemonica.audio.diarize import Diarization, Interval  # noqa: E402
from mnemonica.audio.enroll import (  # noqa: E402
    MAX_CLUSTER_DISPERSION,
    Enrollment,
    assign_roles,
    unexpected_speaker_check,
)

DR, PT = "SPEAKER_00", "SPEAKER_01"


def _unit(*components) -> np.ndarray:
    v = np.array(components, dtype=np.float32)
    return v / np.linalg.norm(v)


#: Two voices that are nothing like each other — the easy, normal case.
DR_VEC = _unit(1.0, 0.0, 0.0)
PT_VEC = _unit(0.0, 1.0, 0.0)


def _diarization(embeddings, *, intervals=None, labels=(DR, PT), interval_embeddings=None):
    return Diarization(
        intervals=intervals or [Interval(0.0, 5.0, DR), Interval(5.0, 10.0, PT)],
        labels=list(labels),
        embeddings=np.stack(embeddings),
        metric="cosine",
        interval_embeddings=interval_embeddings or {},
    )


def test_nearest_cluster_becomes_the_clinician():
    d = _diarization([DR_VEC, PT_VEC])
    r = assign_roles(d, Enrollment(vector=_unit(0.99, 0.1, 0.0)))

    assert r.roles == {DR: "clinician", PT: "other"}
    assert r.clinician_cluster == DR
    assert r.confident


def test_no_enrollment_means_unknown_not_a_guess():
    """The documented degraded mode. Every dose then becomes a D16 category 3
    blocking item, which the review flow absorbs — an invented role does not."""
    r = assign_roles(_diarization([DR_VEC, PT_VEC]), None)

    assert set(r.roles.values()) == {"unknown"}
    assert r.clinician_cluster is None
    assert any("no enrollment" in f for f in r.flags)


def test_enrolled_voice_matching_nobody_abstains():
    """A clinician who is not in the room at all — wrong file, wrong session."""
    d = _diarization([DR_VEC, PT_VEC])
    r = assign_roles(d, Enrollment(vector=_unit(0.0, 0.0, 1.0)))

    assert set(r.roles.values()) == {"unknown"}
    assert any("does not match any speaker" in f for f in r.flags)


def test_two_clusters_equally_close_abstains():
    """The enrollment sample matched the room, not a person. Picking the
    marginally-nearer of two is a coin flip presented as an identification."""
    d = _diarization([DR_VEC, PT_VEC])
    r = assign_roles(d, Enrollment(vector=_unit(1.0, 1.0, 0.0)))

    assert set(r.roles.values()) == {"unknown"}
    assert any("equally close" in f for f in r.flags)


def test_manual_override_wins_and_clears_the_identity_flags():
    """D20, Q15c — embeddings fail on colds, masks and speakerphone, and the
    clinician is standing right there."""
    d = _diarization([DR_VEC, PT_VEC])
    r = assign_roles(d, Enrollment(vector=_unit(1.0, 1.0, 0.0)))
    assert not r.confident

    fixed = r.override(PT)
    assert fixed.roles == {DR: "other", PT: "clinician"}
    assert fixed.confident


def test_override_rejects_a_cluster_that_does_not_exist():
    r = assign_roles(_diarization([DR_VEC, PT_VEC]), Enrollment(vector=DR_VEC))
    try:
        r.override("SPEAKER_99")
    except ValueError as e:
        assert "SPEAKER_99" in str(e)
    else:
        raise AssertionError("override accepted a cluster that is not in the session")


def test_padded_zero_centroid_does_not_win_by_being_close_to_the_origin():
    """pyannote pads with zero embeddings when there are more diarization
    labels than centroids. Cosine distance to a zero vector is undefined, and
    the naive answer is 1.0 — which can look like a match."""
    d = _diarization([np.zeros(3, dtype=np.float32), PT_VEC])
    r = assign_roles(d, Enrollment(vector=PT_VEC))

    assert r.clinician_cluster == PT
    assert r.distances[DR] == float("inf")


def test_b6_flags_a_cluster_holding_two_people():
    """One interval that disagrees with its own cluster's centroid — which is
    what a merged third voice looks like from the inside."""
    intervals = [Interval(0.0, 5.0, DR), Interval(5.0, 10.0, DR), Interval(10.0, 21.0, DR)]
    intruder = _unit(0.4, 0.0, 1.0)
    assert 1 - float(np.dot(intruder, DR_VEC)) > MAX_CLUSTER_DISPERSION

    d = _diarization(
        [DR_VEC, PT_VEC],
        intervals=intervals,
        interval_embeddings={0: DR_VEC, 1: DR_VEC, 2: intruder},
    )
    flags = unexpected_speaker_check(d)

    assert any("unexpected speaker" in f for f in flags)
    assert any("0:10" in f for f in flags), "the flag must say where to listen"


def test_b6_stays_quiet_on_two_well_separated_voices():
    """The check has to be silent on the normal case, or it is just noise."""
    d = _diarization(
        [DR_VEC, PT_VEC],
        intervals=[Interval(0.0, 5.0, DR), Interval(5.0, 10.0, DR), Interval(10.0, 15.0, PT)],
        interval_embeddings={0: DR_VEC, 1: _unit(0.99, 0.12, 0.0), 2: PT_VEC},
    )
    assert unexpected_speaker_check(d) == []


def test_b6_flags_two_clusters_that_are_really_one_voice():
    near = _unit(1.0, 0.15, 0.0)
    d = _diarization([DR_VEC, near], labels=(DR, PT))
    assert any("acoustically close" in f for f in unexpected_speaker_check(d))


def test_b6_ignores_a_cluster_with_a_single_interval():
    """One interval cannot tell you anything about spread — it *is* the mean."""
    d = _diarization(
        [DR_VEC, PT_VEC],
        intervals=[Interval(0.0, 5.0, DR), Interval(5.0, 10.0, PT)],
        interval_embeddings={0: _unit(0.0, 0.0, 1.0), 1: PT_VEC},
    )
    assert not any("sounds unlike" in f for f in unexpected_speaker_check(d))
