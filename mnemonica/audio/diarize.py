"""B2 — pyannote speaker diarization.

Uses ``exclusive_speaker_diarization``, new in pyannote 4.0 and built for
downstream transcription: it strips overlapping speech, so assigning a word to
a speaker is an unambiguous interval lookup rather than a tie-break. That is
also what makes B4's drop rule cheap — a word with no interval under it is a
word nobody was speaking.

``num_speakers=2`` per D19/Q22c. Accepted limitation: a third voice is merged
into an existing cluster rather than detected. B6 is the mitigation.

The 4.x API breaks, all confirmed by gate 0g: the result is a ``DiarizeOutput``
not an ``Annotation`` (reach through ``.speaker_diarization`` or pass
``legacy=True``), and the kwarg is ``token=``, not ``use_auth_token=``.
"""

from __future__ import annotations

import env_guard  # noqa: F401  — must precede pyannote; telemetry is read at import time

from dataclasses import dataclass, field

import numpy as np

from .audio_io import Audio

__all__ = [
    "Interval",
    "Diarization",
    "diarize",
    "load_pipeline",
    "interval_embeddings",
    "MODEL",
]

MODEL = "pyannote-community/speaker-diarization-community-1"
"""The ungated community mirror — no HF token, no gate form (0f)."""

DEVICE = "mps"
"""Gate 0h: worst boundary delta between CPU and MPS was 0.0 ms with identical
labels, at 4.9x real-time against 3.5x. CPU remains a working fallback."""


@dataclass(frozen=True)
class Interval:
    start: float
    end: float
    cluster: str

    def contains(self, t: float) -> bool:
        return self.start <= t < self.end

    def overlap(self, start: float, end: float) -> float:
        return max(0.0, min(self.end, end) - max(self.start, start))


@dataclass
class Diarization:
    """Exclusive turns plus the per-cluster embeddings B3 and B6 read."""

    intervals: list[Interval]
    labels: list[str]
    embeddings: np.ndarray | None = None
    """``(num_clusters, dim)`` centroids, in `labels` order. `None` only under
    OracleClustering, which this build never uses."""
    metric: str = "cosine"
    """The distance the embedding model was trained under — B3 must compare in
    the same one."""
    interval_embeddings: dict[int, np.ndarray] = field(default_factory=dict)
    """One embedding per interval, keyed by index into `intervals`.

    The centroids above cannot answer B6's question. A cluster holding two
    people has a centroid sitting between them, which looks like a perfectly
    ordinary speaker. What gives it away is *spread* — the segments inside it
    disagree with each other. That needs per-interval vectors, so B6 computes
    them (see `interval_embeddings`)."""
    _raw: object = field(default=None, repr=False)

    def cluster_at(self, start: float, end: float) -> str | None:
        """Which cluster owns the span `[start, end)`?

        Picks the interval with the largest overlap rather than the one under
        the midpoint: a word straddling a turn boundary should go to whoever
        said most of it. Returns None when nothing overlaps at all — B4 drops
        that word.
        """
        best, best_overlap = None, 0.0
        for iv in self.intervals:
            o = iv.overlap(start, end)
            if o > best_overlap:
                best, best_overlap = iv.cluster, o
        return best

    def embedding_of(self, cluster: str) -> np.ndarray | None:
        if self.embeddings is None or cluster not in self.labels:
            return None
        return self.embeddings[self.labels.index(cluster)]

    @property
    def speech_duration(self) -> float:
        return sum(iv.end - iv.start for iv in self.intervals)


def load_pipeline(device: str = DEVICE):
    """Load the diarization pipeline onto `device`.

    Kept separate from `diarize` so B3's enrollment embedding can reuse the
    *same* pipeline object: a centroid and an enrollment vector are only
    comparable if they came out of the same embedding model.
    """
    import torch
    from pyannote.audio import Pipeline

    pipeline = Pipeline.from_pretrained(MODEL)
    return pipeline.to(torch.device(device))


def diarize(audio: Audio, *, pipeline=None, num_speakers: int = 2) -> Diarization:
    """Split `audio` into exclusive single-speaker intervals."""
    pipeline = pipeline if pipeline is not None else load_pipeline()

    # Never `pipeline(path)` — torchcodec cannot decode here. See Deviations.
    out = pipeline(audio.as_pyannote_input(), num_speakers=num_speakers)

    exclusive = getattr(out, "exclusive_speaker_diarization", None)
    if exclusive is None:  # legacy=True, or a pipeline that predates 4.0
        exclusive = out
    labels = list(getattr(out, "speaker_diarization", exclusive).labels())

    intervals = [
        Interval(start=float(seg.start), end=float(seg.end), cluster=label)
        for seg, _, label in exclusive.itertracks(yield_label=True)
    ]
    intervals.sort(key=lambda iv: iv.start)

    embeddings = getattr(out, "speaker_embeddings", None)
    metric = getattr(getattr(pipeline, "_embedding", None), "metric", "cosine")

    return Diarization(
        intervals=intervals,
        labels=labels,
        embeddings=embeddings,
        metric=metric,
        _raw=out,
    )


def interval_embeddings(
    audio: Audio,
    diarization: Diarization,
    *,
    pipeline,
    min_duration: float | None = None,
) -> dict[int, np.ndarray]:
    """Embed each diarization interval separately — B6's raw material.

    Intervals shorter than `min_duration` are skipped, and that cut-off is
    what makes the check work at all — a one-second "Mm-hm" embeds further
    from its own speaker than a genuine intruder does. See
    `enroll.MIN_EMBED_DURATION`.

    This is a second pass over the audio with the embedding model only, not the
    full pipeline, so it costs a fraction of diarization itself.
    """
    import torch

    from .audio_io import resample

    if min_duration is None:
        from .enroll import MIN_EMBED_DURATION

        min_duration = MIN_EMBED_DURATION

    embedder = getattr(pipeline, "_embedding", None)
    if embedder is None:
        return {}

    samples = resample(audio.mono(), audio.sample_rate, embedder.sample_rate)
    rate = embedder.sample_rate
    min_samples = getattr(embedder, "min_num_samples", 0) or 0

    out: dict[int, np.ndarray] = {}
    for i, iv in enumerate(diarization.intervals):
        if iv.end - iv.start < min_duration:
            continue
        chunk = samples[int(iv.start * rate) : int(iv.end * rate)]
        if len(chunk) < max(min_samples, 1):
            continue
        batch = torch.from_numpy(chunk).reshape(1, 1, -1)
        vector = np.asarray(embedder(batch)).reshape(-1)
        if np.any(np.isnan(vector)) or not np.any(vector):
            continue
        out[i] = vector
    return out
