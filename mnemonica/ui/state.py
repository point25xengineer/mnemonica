"""The review session and its state machine — U2, U5, U9.

One visit moves through four stages and cannot skip one:

    consent  ->  recording  ->  review  ->  approved

`consent -> recording` is D27, and it is enforced here rather than in the
template, because a gate that lives in a UI is an affordance, not a rule. A
`Session` cannot even be constructed without a `Consent` (contract 1a), so the
only way to reach review without one is to never record — which is the point.

`review -> approved` is gated on every blocking item being settled. That gate
is the product: the doctor's signature is the clinical act (D6, D11), so the
system must not let them sign something it knows it could not verify.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from mnemonica.contracts import Consent, Session
from mnemonica.render import fhir
from mnemonica.render.document import render_patient_document
from mnemonica.render.model import Extraction, Resolution, item_is_resolved
from mnemonica.ui import retention

__all__ = ["ReviewSession", "AppState", "Stage", "ApprovalResult"]

Stage = Literal["consent", "recording", "review", "approved"]

REPO_ROOT = Path(__file__).resolve().parents[2]
SESSIONS_ROOT = REPO_ROOT / "data" / "sessions"
RECORDS_ROOT = REPO_ROOT / "data" / "records"
FIXTURES = REPO_ROOT / "fixtures"

SESSION_OVERRIDE: Path | None = None
EXTRACTION_OVERRIDE: Path | None = None
"""3a — the real pipeline's output in place of 1c's fixtures.

Set by ``app.py --session/--extraction``. They are module-level rather than
parameters because the two `load_fixture()` call sites in `app.py` are HTTP
handlers with no argument to thread through, and because 3a's whole claim is
that swapping the fixture for Track B's output is a *path*, not a code change.
`Session` is the same contract either way, so nothing below this line knows
which one it got."""

AUDIO_OVERRIDE: Path | None = None
"""A recording to attach to the fixture session (``app.py --audio``).

`golden_visit.json` names `fixtures/sessions/golden/visit.m4a`, which is not
in the repository — it is a recording of two people, and 1e keeps it out of
git. Pointing at a local copy is how U4 gets audible on this machine without
the fixture lying about where the file lives.
"""


@dataclass
class Progress:
    """What the recording screen shows while the pipeline runs (U2b).

    The chain takes ~90 s on an M5 Pro and the clinician is watching it. A
    spinner with no stages reads as a hang; naming the stage reads as work.
    Coarse on purpose — these are the four things a person can picture, not
    the eleven the code actually does.
    """

    stage: str = "idle"
    detail: str = ""
    done: int = 0
    total: int = 0
    error: str | None = None
    finished: bool = False

    def set(self, stage: str, detail: str = "", *, done: int = 0,
            total: int = 0) -> None:
        self.stage, self.detail, self.done, self.total = stage, detail, done, total

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage, "detail": self.detail, "done": self.done,
            "total": self.total, "error": self.error, "finished": self.finished,
        }


class ConsentRequired(RuntimeError):
    """D27. Raised rather than returned, because every caller that could
    swallow a `False` here is a caller that turns on a microphone."""


class StillBlocking(RuntimeError):
    """U5/U9 — something unresolved reached approve."""


@dataclass
class ApprovalResult:
    document_html: str
    document_path: Path
    fhir_path: Path
    shredded: list[str]
    approved_at: datetime


@dataclass
class ReviewSession:
    """One visit, in one directory, at one stage."""

    session_id: str
    stage: Stage = "consent"
    consent: Consent | None = None
    session: Session | None = None
    extraction: Extraction | None = None
    clinician_name: str = "Dr. Ellery Kovak"
    unexpected_speaker: bool = False
    resolutions: dict[str, Resolution] = field(default_factory=dict)
    approved: ApprovalResult | None = None
    progress: Progress = field(default_factory=lambda: Progress())

    @property
    def session_dir(self) -> Path:
        return SESSIONS_ROOT / self.session_id

    @property
    def records_dir(self) -> Path:
        return RECORDS_ROOT / self.session_id

    # -- U2 ---------------------------------------------------------------

    def give_consent(self, *, method: str, obtained: bool = True) -> Consent:
        """The one control on the consent screen.

        `Consent` rejects `obtained=False` at construction, so a refusal never
        becomes a half-populated session sitting in memory waiting to be
        recorded into.
        """
        if not obtained:
            raise ConsentRequired(
                "the patient did not consent — recording cannot start (D27)"
            )
        self.consent = Consent(
            obtained=True,
            method=method,  # type: ignore[arg-type]
            obtained_at=datetime.now().replace(microsecond=0),
        )
        self.stage = "recording"
        return self.consent

    def start_recording(self) -> None:
        if self.consent is None:
            raise ConsentRequired(
                "recording requires the patient's consent first (D27)"
            )
        self.stage = "recording"

    # -- ingest -----------------------------------------------------------

    def load_fixture(
        self,
        visit_path: Path | None = None,
        extraction_path: Path | None = None,
    ) -> None:
        """3a's seam. Today it reads 1c's fixtures; when Track B lands, this
        method takes a `Session` from the pipeline and nothing else changes.

        The fixture's own `session_dir` points inside `fixtures/`, which is
        checked-in test data that U9 must never shred. So the session is
        re-homed into a working directory under `data/sessions/` and the
        contract's containment validator re-runs on the rewritten paths.
        """
        visit_path = (visit_path or SESSION_OVERRIDE
                      or FIXTURES / "golden_visit.json")
        extraction_path = (extraction_path or EXTRACTION_OVERRIDE
                           or FIXTURES / "golden_extraction.json")

        raw = json.loads(Path(visit_path).read_text())
        original_audio = Path(raw["audio_path"])
        source_audio = AUDIO_OVERRIDE or (REPO_ROOT / original_audio)

        # The copy keeps the source's extension, not the fixture's. Naming a
        # .wav `visit.m4a` makes the browser refuse to decode it, which looks
        # identical to a cue pointing at the wrong second.
        self.session_dir.mkdir(parents=True, exist_ok=True)
        raw["session_dir"] = str(self.session_dir)
        raw["audio_path"] = str(
            self.session_dir / f"visit{source_audio.suffix or original_audio.suffix}"
        )
        self.session = Session.model_validate(raw)

        if source_audio.exists():
            shutil.copy2(source_audio, self.session.audio_path)

        self.extraction = Extraction.load(extraction_path)
        if self.consent is None:
            # The fixture carries its own consent (1c-i), and it is a real
            # record of a real role-play. Adopt it rather than re-asking.
            self.consent = self.session.consent
        (self.session_dir / "review.log").write_text(
            f"{datetime.now().isoformat(timespec='seconds')} session opened\n"
        )
        self.stage = "review"

    def ingest_recording(
        self,
        audio_path: Path,
        enrollment_path: Path | None = None,
        *,
        model_id: str | None = None,
    ) -> None:
        """A recording made moments ago, all the way to a review screen.

        The same two stages the CLI runs (`audio.pipeline` then `verify.run`),
        called in-process so the clinician never leaves the page. `load_fixture`
        remains the path for a pre-computed session — the demo fallback, and
        what the tests use — and neither knows about the other.

        Imports are local because they pull in MLX, Whisper and pyannote: at
        module scope they would cost ~10 s on every `ui.app` start, including
        the runs that never record anything.
        """
        from mnemonica.audio.pipeline import ingest
        from mnemonica.extract.runner import DEV_MODEL, Extractor
        from mnemonica.verify.pipeline import verify
        from mnemonica.verify.run import _log

        if self.consent is None:
            raise ConsentRequired("recording requires consent first (D27)")

        p = self.progress
        try:
            p.set("transcribing", "Whisper large-v3 — words and timings")
            result = ingest(
                audio_path,
                session_dir=self.session_dir,
                consent=self.consent,
                enrollment_path=enrollment_path,
            )
            self.session = result.session
            self.unexpected_speaker = bool(result.flags)
            (self.session_dir / "session.json").write_text(
                self.session.model_dump_json(indent=1)
            )

            p.set("extracting", "quoting what the clinician said",
                  total=len(self.session.turns))
            extractor = Extractor(model_id or DEV_MODEL)

            def tick(_result, done: int, total: int) -> None:
                p.set("extracting", "quoting what the clinician said",
                      done=done, total=total)

            run = extractor.extract(self.session, progress=tick)

            p.set("verifying", "checking every quote against the transcript")
            verified = verify(self.session, run.visit, logger=_log(self.session))
            (self.session_dir / "extraction.json").write_text(
                json.dumps(verified.envelope, indent=1)
            )
            self.extraction = Extraction.parse(verified.envelope)

            self._log("session opened from a live recording")
            self.stage = "review"
            p.set("done")
        except Exception as exc:  # surfaced on the page, not just in a log
            p.error = f"{type(exc).__name__}: {exc}"
            p.set("failed", p.error)
            raise
        finally:
            p.finished = True

    # -- U5 ---------------------------------------------------------------

    def _resolution(self, item_id: str) -> Resolution:
        return self.resolutions.setdefault(item_id, Resolution(item_id=item_id))

    def resolve(self, item_id: str, flag_index: int, option: str) -> Resolution:
        res = self._resolution(item_id)
        res.choices[flag_index] = option
        res.resolved_at = datetime.now().isoformat(timespec="seconds")
        self._log(f"resolved {item_id} flag {flag_index} -> {option!r}")
        return res

    def promote(self, item_id: str) -> Resolution:
        """U6 — the clinician confirms a `change_kind` the pipeline could not
        derive. Only after this does the verb print as fact."""
        res = self._resolution(item_id)
        res.promoted = True
        res.resolved_at = datetime.now().isoformat(timespec="seconds")
        self._log(f"promoted change_kind on {item_id}")
        return res

    def drop(self, item_id: str) -> Resolution:
        res = self._resolution(item_id)
        res.dropped = True
        res.resolved_at = datetime.now().isoformat(timespec="seconds")
        self._log(f"dropped {item_id}")
        return res

    def unresolved(self) -> list[str]:
        if self.extraction is None:
            return []
        return [
            item.id
            for item in self.extraction.items
            if not item_is_resolved(item, self.resolutions.get(item.id))
        ]

    @property
    def can_approve(self) -> bool:
        return self.stage == "review" and not self.unresolved()

    def _log(self, line: str) -> None:
        """Written into the session directory, which is shredded at approval.

        A review log records which item the doctor was looking at and what
        they chose, so it carries transcript-adjacent PHI. That is precisely
        why D2/D3 make the *directory* the unit of retention.
        """
        if self.stage == "approved":
            return
        path = self.session_dir / "review.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")

    # -- U9 ---------------------------------------------------------------

    def approve(self, *, approved_at: datetime | None = None) -> ApprovalResult:
        """Render once, write twice, then shred. In that order.

        The order is the guarantee. Rendering after the shred is impossible
        (the audio is gone, but so is the log the render would have been
        checked against); shredding before the write risks losing the only
        copy if the write fails. Render, persist both destinations from the
        same string, then delete.
        """
        if self.session is None or self.extraction is None:
            raise StillBlocking("nothing loaded to approve")
        outstanding = self.unresolved()
        if outstanding:
            raise StillBlocking(
                "these items still need a decision: " + ", ".join(outstanding)
            )

        approved_at = approved_at or datetime.now().replace(microsecond=0)
        html = render_patient_document(
            self.extraction,
            self.session,
            clinician_name=self.clinician_name,
            resolutions=self.resolutions,
            approved_on=approved_at.date(),
            unexpected_speaker=self.unexpected_speaker,
        )

        self.records_dir.mkdir(parents=True, exist_ok=True)
        document_path = self.records_dir / "visit-summary.html"
        document_path.write_text(html)

        resource = fhir.build_document_reference(
            html,
            clinician_name=self.clinician_name,
            visit_date=self.extraction.visit_date,
            authored_on=approved_at,
            session_id=self.session_id,
        )
        fhir_path = fhir.write_document_reference(
            resource, self.records_dir / "DocumentReference.json"
        )

        shredded = retention.shred(self.session_dir, root=SESSIONS_ROOT)

        self.stage = "approved"
        self.approved = ApprovalResult(
            document_html=html,
            document_path=document_path,
            fhir_path=fhir_path,
            shredded=shredded,
            approved_at=approved_at,
        )
        return self.approved


@dataclass
class AppState:
    """What the HTTP layer holds. One visit at a time — D6's clinician is one
    person with one patient in the room."""

    current: ReviewSession | None = None

    def new_session(self) -> ReviewSession:
        self.current = ReviewSession(session_id=uuid.uuid4().hex[:12])
        return self.current

    def require(self) -> ReviewSession:
        if self.current is None:
            return self.new_session()
        return self.current
