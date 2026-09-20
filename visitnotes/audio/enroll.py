"""B3 — enrollment match → `role`. B6 — the unexpected-speaker check.

pyannote emits anonymous ``SPEAKER_00`` / ``SPEAKER_01`` and has **no** notion
of who anyone is; named-speaker voiceprinting is a paid cloud feature, and D1
rules the cloud out. But 4.x exposes ``out.speaker_embeddings``, one centroid
per cluster in ``speaker_diarization.labels()`` order. That is the hook: embed
the 10-second enrollment sample from 1e with the *same* embedding model, and
the nearest cluster is the clinician.

Two things make this more than a nearest-neighbour call.

**Confidence decides `unknown`, not distance alone.** 1a's `Role` has three
values and `unknown` exists for exactly this: a cluster enrollment could not
place. A dose from an `unknown` turn is a D16 category 3 blocking item, so
guessing costs a silent misattribution while abstaining costs one confirmation
click. Abstain.

**The manual override is not optional** (D20, Q15c). Embeddings fail on colds,
masks and speakerphone, and the clinician is standing right there.
"""

from __future__ import annotations

import env_guard  # noqa: F401  — must precede pyannote

from dataclasses import dataclass

import numpy as np

from .audio_io import Audio, resample
from .diarize import Diarization

__all__ = [
    "Enrollment",
    "cluster_dispersion",
    "RoleAssignment",
    "embed_enrollment",
    "assign_roles",
    "unexpected_speaker_check",
]

# --- thresholds ------------------------------------------------------------
# Cosine distance in pyannote's community-1 embedding space. These are
# literature-plausible starting points, NOT calibrated — there is no labelled
# data in this build. Gate 3c tunes them, and the bias there is toward
# flagging: an extra confirmation click is cheap, a silent misattribution is
# not.

MAX_CLINICIAN_DISTANCE = 0.65
"""Beyond this, the nearest cluster is not convincingly the enrolled voice."""

MIN_MARGIN = 0.10
"""The runner-up must be at least this much further away. Two clusters at the
same distance from the enrollment sample means the sample matched the room,
not a person."""

MIN_CLUSTER_SEPARATION = 0.45
"""B6: two centroids closer than this are probably one voice split in two."""

MAX_CLUSTER_DISPERSION = 0.45
"""B6, and the threshold that actually catches a third person.

`num_speakers=2` does not fail loudly on three voices — it folds the third
into an existing cluster, whose *centroid* then sits between two people
looking like a perfectly ordinary speaker. What gives it away is one segment
that disagrees with the rest.

So this is the distance from the **worst** interval to its own cluster's
centroid, not the mean. An intruder who speaks once is exactly one outlier,
and averaging it across ten of the real speaker's intervals is how you dilute
the only evidence you have. Measured on the 1e take against a spliced
three-speaker version of it, at `MIN_EMBED_DURATION`:

    two speakers    worst interval 0.20 and 0.32
    three speakers  worst interval 0.65 — the intruder, correctly localised

0.45 sits between them. One file of each is not a calibration; gate 3c is,
and its bias is toward flagging."""

MIN_EMBED_DURATION = 2.0
"""Seconds. Intervals shorter than this are not embedded for B6.

This is load-bearing, not a performance tweak. At 1.0 s the check does not
work at all: a one-second "Mm-hm" embeds to something 0.71 away from its own
speaker's centroid — *further* than the genuine intruder at 0.65 — so the
noise floor swallows the signal. At 2.0 s the real speakers' worst intervals
drop to 0.20/0.32 and the intruder stands alone."""


@dataclass(frozen=True)
class Enrollment:
    """The clinician's 10-second sample, in the diarizer's embedding space."""

    vector: np.ndarray
    metric: str = "cosine"


@dataclass(frozen=True)
class RoleAssignment:
    """Which cluster is the clinician, and how sure we are.

    `flags` are B6 output: session-level strings that Track D renders as D16
    blocking items. They are deliberately human sentences — nothing downstream
    parses them.
    """

    roles: dict[str, str]
    distances: dict[str, float]
    clinician_cluster: str | None
    margin: float
    flags: list[str]

    @property
    def confident(self) -> bool:
        return self.clinician_cluster is not None and not self.flags

    def override(self, cluster: str) -> RoleAssignment:
        """D20 — "that's me". The clinician's own correction wins outright.

        It also clears the B6 flags that were about identity: the human just
        answered the question they were raised to ask.
        """
        if cluster not in self.roles:
            raise ValueError(f"no such cluster: {cluster!r}; have {list(self.roles)}")
        roles = {c: ("clinician" if c == cluster else "other") for c in self.roles}
        kept = [f for f in self.flags if "unexpected speaker" not in f]
        return RoleAssignment(
            roles=roles,
            distances=self.distances,
            clinician_cluster=cluster,
            margin=self.margin,
            flags=kept,
        )


def _distance(a: np.ndarray, b: np.ndarray, metric: str) -> float:
    if metric == "cosine":
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0.0:
            return float("inf")
        return 1.0 - float(np.dot(a, b)) / denom
    return float(np.linalg.norm(a - b))


def embed_enrollment(audio: Audio, *, pipeline) -> Enrollment:
    """Embed the 10-second enrollment clip with the diarizer's own model.

    Reuses `pipeline._embedding` on purpose. A centroid from the diarization
    run and a vector from a separately-instantiated model are numbers in two
    different spaces, and comparing them produces a confident wrong answer.
    """
    import torch

    embedder = getattr(pipeline, "_embedding", None)
    if embedder is None:
        raise RuntimeError(
            "this pipeline exposes no embedding model (OracleClustering?); "
            "enrollment cannot run — fall back to the manual override"
        )

    samples = resample(audio.mono(), audio.sample_rate, embedder.sample_rate)
    min_samples = getattr(embedder, "min_num_samples", 0) or 0
    if len(samples) < min_samples:
        raise ValueError(
            f"enrollment clip is {len(samples) / embedder.sample_rate:.1f}s; the "
            f"embedding model needs {min_samples / embedder.sample_rate:.1f}s"
        )

    batch = torch.from_numpy(samples).reshape(1, 1, -1)  # (batch, channel, time)
    vector = np.asarray(embedder(batch)).reshape(-1)
    return Enrollment(vector=vector, metric=getattr(embedder, "metric", "cosine"))


def assign_roles(
    diarization: Diarization, enrollment: Enrollment | None
) -> RoleAssignment:
    """B3 + B6 — map clusters to roles, and flag when we should not be trusted.

    With no enrollment (1e's sample missing, or the embedder unavailable) every
    cluster is `unknown`. That is the documented degraded mode, not a failure:
    the review flow absorbs it by making every dose blocking.
    """
    labels = list(diarization.labels)
    flags = unexpected_speaker_check(diarization)

    if enrollment is None or diarization.embeddings is None:
        return RoleAssignment(
            roles={c: "unknown" for c in labels},
            distances={},
            clinician_cluster=None,
            margin=0.0,
            flags=flags + ["no enrollment sample — every speaker is unidentified"],
        )

    distances = {}
    for cluster in labels:
        centroid = diarization.embedding_of(cluster)
        if centroid is None or not np.any(centroid):
            # Padded zero embedding: more diarization labels than centroids.
            distances[cluster] = float("inf")
            continue
        distances[cluster] = _distance(enrollment.vector, centroid, enrollment.metric)

    ordered = sorted(distances.items(), key=lambda kv: kv[1])
    best, best_d = ordered[0]
    runner_up_d = ordered[1][1] if len(ordered) > 1 else float("inf")
    margin = runner_up_d - best_d

    if best_d > MAX_CLINICIAN_DISTANCE:
        flags.append(
            f"unexpected speaker — the enrolled voice does not match any "
            f"speaker in this recording (nearest {best_d:.2f})"
        )
        clinician = None
    elif margin < MIN_MARGIN:
        flags.append(
            f"unexpected speaker — two speakers are equally close to the "
            f"enrolled voice (margin {margin:.2f}); review manually"
        )
        clinician = None
    else:
        clinician = best

    roles = {
        c: ("clinician" if c == clinician else "other" if clinician else "unknown")
        for c in labels
    }
    return RoleAssignment(
        roles=roles,
        distances=distances,
        clinician_cluster=clinician,
        margin=margin,
        flags=flags,
    )


def cluster_dispersion(diarization: Diarization) -> dict[str, tuple[float, float]]:
    """Per cluster: `(worst distance to its own centroid, when it happened)`.

    The timestamp is not decoration. "SPEAKER_01 has high variance" is not
    something a clinician can act on; "listen at 1:29" is.
    """
    if not diarization.interval_embeddings or diarization.embeddings is None:
        return {}

    spreads: dict[str, list[tuple[float, float]]] = {c: [] for c in diarization.labels}
    for idx, vector in diarization.interval_embeddings.items():
        interval = diarization.intervals[idx]
        centroid = diarization.embedding_of(interval.cluster)
        if centroid is None or not np.any(centroid) or interval.cluster not in spreads:
            continue
        d = _distance(vector, centroid, diarization.metric)
        spreads[interval.cluster].append((d, interval.start))

    # One interval tells you nothing about spread; two is the minimum that can.
    return {c: max(v) for c, v in spreads.items() if len(v) >= 2}


def unexpected_speaker_check(diarization: Diarization) -> list[str]:
    """B6 — did `num_speakers=2` hide someone?

    D19 pins two speakers, so a third voice is merged into an existing cluster
    rather than detected. This cannot recover the third person. It converts the
    silent misattribution into a visible D16 blocking item, which is the
    difference between "we don't handle three speakers" and "we detect when we
    might not be able to" — the claim PRESENTATION-NOTES item 6 commits to.
    """
    flags: list[str] = []
    embeddings = diarization.embeddings
    if embeddings is None or len(diarization.labels) < 2:
        return flags

    for cluster, (spread, at) in cluster_dispersion(diarization).items():
        if spread > MAX_CLUSTER_DISPERSION:
            flags.append(
                f"unexpected speaker — a segment at {int(at) // 60}:"
                f"{int(at) % 60:02d} sounds unlike the rest of {cluster} "
                f"(distance {spread:.2f}); a third person may have been merged "
                f"into it. Listen and review manually."
            )

    labels = diarization.labels
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a, b = embeddings[i], embeddings[j]
            if not np.any(a) or not np.any(b):
                continue
            d = _distance(a, b, diarization.metric)
            if d < MIN_CLUSTER_SEPARATION:
                flags.append(
                    f"unexpected speaker — {labels[i]} and {labels[j]} are "
                    f"acoustically close (distance {d:.2f}); a third voice may "
                    f"have been merged into one of them. Review manually."
                )
    return flags
