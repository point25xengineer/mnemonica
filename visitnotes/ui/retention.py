"""U9 + U10 — the retention policy, which is the whole privacy claim.

    Audio exists until the doctor signs, or 24 hours, whichever comes first.
    There is no third case.

A policy statable in one sentence with no exceptions is worth more than a
flexible one, so this module is written to keep that sentence true rather than
to be convenient.

Three things it gets right that the obvious implementation gets wrong:

1. **The unit of retention is the directory, not the `.wav`** (D2/D3). A
   dropped-quote log line contains transcript text; so do ffmpeg scratch files
   and tracebacks. `unlink(audio_path)` shreds the recording and leaves the
   PHI sitting next to it. `Session.session_dir` exists for exactly this.
2. **The sweep covers extracted data too** (D3, Q23a). A structured list of
   someone's medications is PHI without the recording. Deleting the audio and
   keeping the JSON is not a retention policy, it is a compression step.
3. **The pre-computed demo session is exempt** (4a). Phase 4 runs the long
   visit the night before and leaves an unapproved session on disk. Without
   `DEMO_MARKER` this sweep deletes the demo, on demo day, silently.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "EXPIRY_SECONDS",
    "DEMO_MARKER",
    "shred",
    "mark_demo_fixture",
    "is_demo_fixture",
    "sweep_expired",
    "SweepResult",
]

EXPIRY_SECONDS = 24 * 60 * 60
"""D3, Q23a. Twenty-four hours, not "about a day"."""

DEMO_MARKER = ".demo-fixture"
"""Touch this inside a session directory and the sweep leaves it alone."""

OVERWRITE_CHUNK = 1 << 20


def _overwrite(path: Path) -> None:
    """Best effort at making the bytes unrecoverable before unlinking.

    On an APFS copy-on-write volume this is theatre and we should not claim
    otherwise on stage: overwriting a file in place does not guarantee the old
    blocks are gone. Say "deleted", not "securely wiped". It costs nothing and
    it removes the easy case, which is a file still sitting in the directory.
    """
    try:
        size = path.stat().st_size
        with path.open("r+b", buffering=0) as fh:
            remaining = size
            while remaining > 0:
                chunk = min(OVERWRITE_CHUNK, remaining)
                fh.write(os.urandom(chunk))
                remaining -= chunk
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        # A symlink, a permissions problem, a file that vanished. The unlink
        # below is what actually matters; never let this stage abort a shred.
        pass


def shred(session_dir: Path, *, root: Path) -> list[str]:
    """Delete a session directory and everything in it. Returns what went.

    `root` is a containment guard, and it is not paranoia: this function is
    called with a path that came from a JSON fixture. `fixtures/sessions/golden`
    is a checked-in directory, and a shred that walks out of the sessions root
    is one typo away from deleting the repository's own test data.
    """
    session_dir = Path(session_dir)
    root = Path(root).resolve()
    resolved = session_dir.resolve()

    if not resolved.is_relative_to(root):
        raise ValueError(
            f"refusing to shred {resolved}: outside the sessions root {root}"
        )
    if resolved == root:
        raise ValueError("refusing to shred the sessions root itself")
    if not resolved.exists():
        return []

    removed: list[str] = []
    for path in sorted(resolved.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_file() and not path.is_symlink():
            _overwrite(path)
            removed.append(str(path.relative_to(resolved)))
    shutil.rmtree(resolved, ignore_errors=False)
    return removed


def mark_demo_fixture(session_dir: Path) -> Path:
    """Phase 4a calls this. Do it when you create the session, not later."""
    marker = Path(session_dir) / DEMO_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        "Pre-computed demo session (PHASE-4 4a). Exempt from the U10 expiry "
        "sweep. Contains role-play audio, not patient data.\n"
    )
    return marker


def is_demo_fixture(session_dir: Path) -> bool:
    return (Path(session_dir) / DEMO_MARKER).exists()


@dataclass
class SweepResult:
    swept: list[str]
    kept_demo: list[str]
    kept_fresh: list[str]

    def summary(self) -> str:
        return (
            f"swept {len(self.swept)}, kept {len(self.kept_fresh)} fresh, "
            f"kept {len(self.kept_demo)} demo"
        )


def sweep_expired(
    root: Path,
    *,
    now: float | None = None,
    max_age_seconds: int = EXPIRY_SECONDS,
) -> SweepResult:
    """Delete every unapproved session older than 24 hours.

    Age is the directory's own mtime. An approved session's directory is
    already gone — U9 shredded it at attestation — so anything still here is
    by definition unapproved, and that is the whole population this sweep
    cares about.
    """
    root = Path(root)
    now = time.time() if now is None else now
    result = SweepResult(swept=[], kept_demo=[], kept_fresh=[])
    if not root.exists():
        return result

    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if is_demo_fixture(child):
            result.kept_demo.append(child.name)
            continue
        if now - child.stat().st_mtime < max_age_seconds:
            result.kept_fresh.append(child.name)
            continue
        shred(child, root=root)
        result.swept.append(child.name)
    return result
