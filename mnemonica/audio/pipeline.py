"""B5 — audio in, `Session` out.

    python -m mnemonica.audio.pipeline visit.m4a --session-dir sessions/demo

Stages run **sequentially and are freed between** (SPEC §2). Whisper is
3.08 GB and the extraction MoE is 20.43 GB against a ~36 GB practical working
set, so the reference is dropped and the MLX cache cleared before the next
model loads, rather than trusting that to happen in time.

Two contract obligations live here and nowhere else:

**`visit_date` is the audio file's mtime, read once at ingest and persisted**
(D18). It is read from the *source* file, before the copy, because `cp`
without `-p` resets mtime and so does any re-encode. Nothing downstream may
call `stat()` again.

**Consent is required before any of this runs** (D27). It is a parameter, not
a field filled in later: a `Session` that reached review without consent is a
recording that should never have been made.
"""

from __future__ import annotations

import env_guard  # noqa: F401  — must precede pyannote/whisper

import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ..contracts import Consent, Session
from .assemble import Assembled, DroppedWord, assemble
from .audio_io import load_audio
from .diarize import (
    DEVICE,
    Diarization,
    diarize,
    interval_embeddings,
    load_pipeline,
)
from .enroll import Enrollment, RoleAssignment, assign_roles, embed_enrollment
from .transcribe import Transcript, transcribe

__all__ = ["IngestResult", "ingest"]


@dataclass
class IngestResult:
    """The `Session` plus everything the review UI needs that is not in it.

    `Session` is the contract Tracks C and D consume and it stays clean. The
    diagnostics — dropped words, B6 flags, per-cluster distances — are Track
    B's own output, carried alongside rather than bolted onto the contract.
    """

    session: Session
    roles: RoleAssignment
    dropped: list[DroppedWord] = field(default_factory=list)
    suspect_segments: list[int] = field(default_factory=list)
    diarization: Diarization | None = None

    @property
    def flags(self) -> list[str]:
        return self.roles.flags


def _free_mlx() -> None:
    """Drop whatever MLX is holding before the next model loads."""
    import gc

    gc.collect()
    try:
        import mlx.core as mx

        mx.clear_cache()
    except Exception:
        pass  # older mlx, or nothing cached — not worth failing ingest over


def ingest(
    audio_path: Path | str,
    *,
    session_dir: Path | str,
    consent: Consent,
    enrollment_path: Path | str | None = None,
    device: str = DEVICE,
    num_speakers: int = 2,
    prime_drug_names: bool = True,
) -> IngestResult:
    """Run B1-B4 over `audio_path` and return a validated `Session`."""
    source = Path(audio_path)
    session_dir = Path(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)

    # D18 — read the mtime of the file as recorded, before anything touches it.
    visit_date = date.fromtimestamp(source.stat().st_mtime)

    # Everything this session wrote lives in one directory, because U9 shreds
    # the directory, not the file: a converted WAV or a log left outside it is
    # PHI that survives approval (D2/D3).
    stored = session_dir / source.name
    if stored.resolve() != source.resolve():
        shutil.copy2(source, stored)  # -p: keeps the mtime honest on disk too

    audio = load_audio(stored, work_dir=session_dir)

    # --- B1 --------------------------------------------------------------
    transcript: Transcript = transcribe(
        audio.path, prime_drug_names=prime_drug_names
    )
    _free_mlx()

    # --- B2, B3 ----------------------------------------------------------
    # One pipeline object for both: a diarization centroid and an enrollment
    # vector are only comparable if the same embedding model produced them.
    pipeline = load_pipeline(device)
    diarization = diarize(audio, pipeline=pipeline, num_speakers=num_speakers)

    # B6 needs per-interval vectors, not just centroids — a cluster holding
    # two people has an unremarkable centroid and a telltale spread.
    diarization.interval_embeddings = interval_embeddings(
        audio, diarization, pipeline=pipeline
    )

    enrollment: Enrollment | None = None
    if enrollment_path is not None:
        enrollment_audio = load_audio(enrollment_path, work_dir=session_dir)
        enrollment = embed_enrollment(enrollment_audio, pipeline=pipeline)

    roles = assign_roles(diarization, enrollment)
    del pipeline
    _free_mlx()

    # --- B4 --------------------------------------------------------------
    assembled: Assembled = assemble(transcript, diarization, roles.roles)

    session = Session(
        visit_date=visit_date,
        session_dir=session_dir,
        audio_path=stored,
        transcript_text=assembled.transcript_text,
        turns=assembled.turns,
        consent=consent,
    )
    return IngestResult(
        session=session,
        roles=roles,
        dropped=assembled.dropped,
        suspect_segments=assembled.suspect_segments,
        diarization=diarization,
    )


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    from datetime import datetime

    p = argparse.ArgumentParser(description="B5 — audio in, Session out")
    p.add_argument("audio")
    p.add_argument("--session-dir", required=True)
    p.add_argument("--enrollment", default=None, help="10 s clinician sample (1e)")
    p.add_argument("--device", default=DEVICE)
    p.add_argument("--no-priming", action="store_true")
    p.add_argument("--out", default=None, help="write the Session JSON here")
    args = p.parse_args(argv)

    # The CLI stands in for U2, which captures consent in the UI before
    # recording starts. There is no --no-consent flag, and that is deliberate.
    consent = Consent(obtained=True, method="verbal", obtained_at=datetime.now())

    result = ingest(
        args.audio,
        session_dir=args.session_dir,
        consent=consent,
        enrollment_path=args.enrollment,
        device=args.device,
        prime_drug_names=not args.no_priming,
    )
    s = result.session
    print(
        f"{len(s.turns)} turns · {sum(len(t.words) for t in s.turns)} words · "
        f"{len(s.transcript_text)} chars · visit_date {s.visit_date}"
    )
    print(f"dropped {len(result.dropped)} words with no diarization interval")
    for cluster, role in result.roles.roles.items():
        d = result.roles.distances.get(cluster)
        print(f"  {cluster}: {role}" + (f"  (distance {d:.3f})" if d is not None else ""))
    for flag in result.flags:
        print(f"  FLAG: {flag}")

    out = Path(args.out) if args.out else Path(args.session_dir) / "session.json"
    out.write_text(s.model_dump_json(indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
