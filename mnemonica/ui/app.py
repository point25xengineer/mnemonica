"""U1 — the localhost app (D6).

Standard-library `http.server` plus Jinja2, and no web framework, for one
reason: D1 says nothing leaves the laptop, and 4b turns the Wi-Fi off. A
dependency we would have to `pip install` on venue Wi-Fi is a demo-day risk
taken for a router we do not need. One clinician, one visit, one machine.

Two audiences, one product. The screen is dense and keyboard-driven, built for
someone with fifteen minutes per visit. The paper (`/document`) is large-type
and high-contrast, built for a 78-year-old. Different design problems, one
render each.

Run it:

    python -m mnemonica.ui.app          # serves http://127.0.0.1:8765
    python -m mnemonica.ui.app --sweep  # U10, no server
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import urllib.parse
from datetime import date
from http import HTTPStatus
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from mnemonica.render import review as review_view
from mnemonica.render.document import render_patient_document
from mnemonica.ui import retention, state
from mnemonica.ui.state import (
    AppState,
    ConsentRequired,
    ReviewSession,
    SESSIONS_ROOT,
    StillBlocking,
)

RENDER_DIR = Path(__file__).resolve().parents[1] / "render"
STATIC_DIR = RENDER_DIR / "static"

_env = Environment(
    loader=FileSystemLoader(RENDER_DIR / "templates"),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

STATE = AppState()


class Handler(BaseHTTPRequestHandler):
    server_version = "Mnemonica/0.1"

    # -- plumbing ---------------------------------------------------------

    def log_message(self, fmt: str, *args) -> None:
        """Quiet, and deliberately so. The default handler logs the request
        line; a GET carrying an item id would put fragments of a clinical
        review into a terminal that outlives the session directory."""
        return

    def _send(self, body: bytes, status: int = 200, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, template: str, status: int = 200, **context) -> None:
        self._send(_env.get_template(template).render(**context).encode("utf-8"), status)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8")
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}

    # -- GET --------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path

        if path.startswith("/static/"):
            return self._static(path)
        if path == "/audio":
            return self._audio()
        if path == "/record":
            return self._record()
        if path == "/progress":
            return self._progress()
        if path == "/new":
            STATE.new_session()
            return self._redirect("/")
        if path in ("/", "/review"):
            return self._index()
        if path == "/document":
            return self._document()
        if path == "/approved":
            return self._approved()
        self._send(b"not found", HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8")

    def do_HEAD(self) -> None:  # noqa: N802
        """Media elements probe with HEAD before they stream. The default
        handler answers 501, which some players take as "no audio here"."""
        if urllib.parse.urlparse(self.path).path == "/audio":
            return self._audio(body=False)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def _record(self) -> None:
        """U2b — the live capture screen."""
        self._html("record.html", clinician_name=STATE.require().clinician_name)

    def _progress(self) -> None:
        body = json.dumps(STATE.require().progress.as_dict()).encode()
        self._send(body, HTTPStatus.OK, "application/json")

    def _static(self, path: str) -> None:
        name = Path(path).name
        target = STATIC_DIR / name
        if not target.exists() or target.parent != STATIC_DIR:
            return self._send(b"not found", HTTPStatus.NOT_FOUND, "text/plain")
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        self._send(target.read_bytes(), 200, ctype)

    def _audio(self, *, body: bool = True) -> None:
        """U4's source, with byte ranges — which is not a nicety.

        `BaseHTTPRequestHandler` answers every GET with the whole file and no
        `Accept-Ranges`, so the browser reports `seekable = [0, 0]` and
        silently ignores `currentTime = 64.35`. Clicking a line then plays the
        visit from the very beginning: no error, no console warning, just the
        wrong two seconds. Range support is what makes click-to-play land.

        Clinician-only by construction: the patient's copy is a printed page
        and has no way to ask for this route (D8).
        """
        current = STATE.current
        if current is None or current.session is None:
            return self._send(b"no session", HTTPStatus.NOT_FOUND, "text/plain")
        audio = current.session.audio_path
        if not audio.exists():
            return self._send(b"no audio yet", HTTPStatus.NOT_FOUND, "text/plain")

        # The recording is .m4a as often as .wav. Guessing beats hard-coding:
        # a wrong Content-Type makes the <audio> element refuse it silently,
        # which on stage looks exactly like a broken cue.
        ctype = mimetypes.guess_type(audio.name)[0] or "application/octet-stream"
        total = audio.stat().st_size
        start, end = self._range(total)

        if start is None:
            self.send_response(HTTPStatus.OK)
            length = total
        else:
            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
            length = end - start + 1

        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not body:
            return
        with audio.open("rb") as fh:
            if start is not None:
                fh.seek(start)
            self.wfile.write(fh.read(length))

    def _range(self, total: int) -> tuple[int | None, int | None]:
        """Parse one `bytes=` range. A multi-range request gets the whole
        file, which is a legal response and never what a media element asks
        for anyway."""
        header = self.headers.get("Range", "")
        if not header.startswith("bytes=") or "," in header:
            return None, None
        spec = header[len("bytes=") :].strip()
        try:
            first, _, last = spec.partition("-")
            if not first:  # suffix range: the final N bytes
                start = max(0, total - int(last))
                end = total - 1
            else:
                start = int(first)
                end = int(last) if last else total - 1
        except ValueError:
            return None, None
        if start >= total:
            return None, None
        return start, min(end, total - 1)

    def _index(self) -> None:
        current = STATE.require()
        if current.stage == "approved":
            return self._redirect("/approved")
        if current.stage == "consent":
            return self._html(
                "consent.html", clinician_name=current.clinician_name, error=None
            )
        if current.stage == "recording":
            # Mid-capture, or mid-pipeline. `/` is not the page they want.
            return self._redirect("/record")
        if current.session is None:
            current.load_fixture()
        show_details = (
            urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get(
                "checks", ["0"]
            )[0]
            == "1"
        )
        return self._render_review(current, show_details=show_details)

    def _render_review(
        self, current: ReviewSession, *, show_details: bool = False
    ) -> None:
        assert current.session and current.extraction
        rows = review_view.build_review(
            current.extraction,
            current.session,
            clinician_name=current.clinician_name,
            resolutions=current.resolutions,
        )
        self._html(
            "review.html",
            rows=rows,
            presentation=review_view.build_summary_review(
                current.extraction, current.session,
                unexpected_speaker=current.unexpected_speaker,
            ),
            header_line=review_view.header_line(current.extraction),
            discarded=current.extraction.discarded,
            unresolved=current.unresolved(),
            can_approve=current.can_approve,
            titles={r.id: r.title for r in rows},
            audio_available=current.session.audio_path.exists(),
            show_details=show_details,
        )

    def _document(self) -> None:
        """The print preview before approval, the signed artifact after.

        After approval it serves the stored bytes rather than re-rendering.
        D26's guarantee is one render; a preview route that re-renders post
        hoc is exactly the second code path that guarantee exists to forbid.
        """
        current = STATE.current
        if current is None or current.session is None or current.extraction is None:
            return self._send(b"no session", HTTPStatus.NOT_FOUND, "text/plain")
        if current.approved:
            return self._send(current.approved.document_html.encode("utf-8"))
        html = render_patient_document(
            current.extraction,
            current.session,
            clinician_name=current.clinician_name,
            resolutions=current.resolutions,
            approved_on=date.today(),
            unexpected_speaker=current.unexpected_speaker,
        )
        self._send(html.encode("utf-8"))

    def _approved(self) -> None:
        current = STATE.current
        if current is None or current.approved is None:
            return self._redirect("/")
        resource = json.loads(current.approved.fhir_path.read_text())
        self._html(
            "approved.html",
            clinician_name=current.clinician_name,
            fhir_path=current.approved.fhir_path,
            sha1=resource["content"][0]["attachment"]["hash"],
            shredded=current.approved.shredded,
        )

    # -- POST -------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        current = STATE.require()

        # Before `_form()`: an audio blob is binary, and reading it as UTF-8
        # form data raises on the first non-text byte.
        if path == "/upload":
            return self._upload(current)

        form = self._form()

        if path == "/consent":
            return self._consent(current, form)

        if current.stage == "consent":
            # D27, enforced on the server. A review action arriving before
            # consent means someone reached the screen another way.
            return self._send(b"consent required", HTTPStatus.CONFLICT, "text/plain")

        # A form that posts without the fields its handler needs used to
        # raise KeyError inside the request thread: a 500 with no body, an
        # unhandled traceback in the log, and a button that silently did
        # nothing. That is how /promote shipped broken — say what is missing.
        def need(*fields: str) -> str | None:
            missing = [f for f in fields if not form.get(f)]
            if missing:
                self._send(f"missing form field(s): {', '.join(missing)}".encode(),
                           HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8")
                return None
            return form["item_id"]

        if path == "/resolve":
            if (item_id := need("item_id", "flag_index", "option")) is None:
                return
            current.resolve(item_id, int(form["flag_index"]), form["option"])
            return self._redirect(f"/#row-{item_id}")
        if path == "/promote":
            if (item_id := need("item_id")) is None:
                return
            current.promote(item_id)
            return self._redirect(f"/#row-{item_id}")
        if path == "/drop":
            if (item_id := need("item_id")) is None:
                return
            current.drop(item_id)
            return self._redirect(f"/#row-{item_id}")
        if path == "/approve":
            try:
                current.approve()
            except StillBlocking as exc:
                return self._send(str(exc).encode(), HTTPStatus.CONFLICT, "text/plain")
            return self._redirect("/approved")

        self._send(b"not found", HTTPStatus.NOT_FOUND, "text/plain")

    def _upload(self, current: ReviewSession) -> None:
        """U2b — a take arrives from MediaRecorder.

        Two kinds. `enrollment` is the clinician alone and is only stored;
        `visit` is the consultation and starts the pipeline, on a worker
        thread so the POST can return and the page can poll `/progress`.

        The body is a raw blob rather than multipart: one file per request,
        and `Content-Length` is all the framing needed.
        """
        if current.stage not in ("recording", "consent"):
            return self._send(b"not recording", HTTPStatus.CONFLICT, "text/plain")

        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        kind = (query.get("kind") or ["visit"])[0]
        if kind not in ("enrollment", "visit"):
            return self._send(b"unknown kind", HTTPStatus.BAD_REQUEST, "text/plain")

        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return self._send(b"empty upload", HTTPStatus.BAD_REQUEST, "text/plain")

        current.session_dir.mkdir(parents=True, exist_ok=True)
        # The extension matters: ffmpeg sniffs content, but `load_audio` keys
        # its cache off the name, and a blob called .wav that is not one reads
        # as a decode failure rather than a naming mistake.
        target = current.session_dir / f"{kind}.webm"
        target.write_bytes(self.rfile.read(length))

        if kind == "enrollment":
            return self._send(b"ok", HTTPStatus.OK, "text/plain")

        enrollment = current.session_dir / "enrollment.webm"

        def work() -> None:
            try:
                current.ingest_recording(
                    target, enrollment if enrollment.exists() else None
                )
            except Exception:
                pass  # already on current.progress, which the page is polling

        current.progress.set("transcribing", "starting")
        threading.Thread(target=work, daemon=True).start()
        return self._send(b"started", HTTPStatus.ACCEPTED, "text/plain")

    def _consent(self, current: ReviewSession, form: dict[str, str]) -> None:
        current.clinician_name = form.get("clinician_name") or current.clinician_name
        if form.get("obtained") != "yes":
            return self._html(
                "consent.html",
                status=HTTPStatus.OK,
                clinician_name=current.clinician_name,
                error=(
                    "Recording cannot start without the patient's consent. "
                    "This is the one step with no override."
                ),
            )
        try:
            # The consent screen no longer asks how consent was given; verbal
            # is the case in an exam room, and it is what D27 prints in
            # the patient footer. A written-consent workflow would need
            # more than a radio button anyway.
            current.give_consent(method=form.get("method", "verbal"))
        except ConsentRequired as exc:
            return self._html(
                "consent.html", clinician_name=current.clinician_name, error=str(exc)
            )
        # A `--session` on the command line means the visit was recorded
        # earlier and the pipeline has already run: go straight to review.
        # With no session to load, the microphone is the input (U2b).
        if state.SESSION_OVERRIDE is not None:
            current.load_fixture()
            return self._redirect("/")
        current.start_recording()
        return self._redirect("/record")


def serve(port: int = 8765) -> None:
    swept = retention.sweep_expired(SESSIONS_ROOT)
    print(f"U10 sweep on startup: {swept.summary()}")
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Mnemonica review UI → http://127.0.0.1:{port}  (ctrl-c to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--audio",
        type=Path,
        help=(
            "attach a recording to the fixture session (the fixture's own "
            "audio_path is not committed). Without it, U4 shows each cue "
            "window instead of playing it."
        ),
    )
    parser.add_argument(
        "--session",
        type=Path,
        help=(
            "3a — a `Session` from the real pipeline "
            "(sessions/<name>/session.json) instead of 1c's fixture"
        ),
    )
    parser.add_argument(
        "--extraction",
        type=Path,
        help="the post-C5 envelope for --session (verify.run's -o output)",
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="run the U10 expiry sweep and exit (for cron, or before a demo)",
    )
    args = parser.parse_args()
    if args.sweep:
        print(retention.sweep_expired(SESSIONS_ROOT).summary())
        return
    if bool(args.session) != bool(args.extraction):
        parser.error("--session and --extraction go together: a Session with "
                     "the fixture's extraction would render quotes against "
                     "the wrong transcript")
    if args.session:
        state.SESSION_OVERRIDE = args.session.resolve()
        state.EXTRACTION_OVERRIDE = args.extraction.resolve()
    if args.audio:
        state.AUDIO_OVERRIDE = args.audio.resolve()
    serve(args.port)


if __name__ == "__main__":
    main()
