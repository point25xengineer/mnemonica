"""U9 step 2 — the local FHIR `DocumentReference` (D26).

The sentence to have memorised, because it is what resolves the apparent
conflict with D1:

    Nothing goes to a third party. The only destination is the provider's own
    record system, which already holds this patient's chart — and in our demo
    it is a local FHIR DocumentReference.

`content.attachment.data` is base64 of the bytes `render_patient_document`
produced, passed in by the caller. This module never re-renders, and it takes
the HTML as an argument specifically so it *cannot*: a second render is the
only way the chart copy and the paper could ever diverge.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

__all__ = ["build_document_reference", "write_document_reference"]

LOINC_CLINICAL_NOTE = "34133-9"
"""LOINC 34133-9 — *Summarization of episode note*. The closest standard code
for an after-visit summary."""


def build_document_reference(
    document_html: str,
    *,
    clinician_name: str,
    visit_date: date,
    authored_on: datetime | None = None,
    session_id: str,
) -> dict[str, Any]:
    """One resource, holding the exact bytes we printed.

    The SHA-1 in `content.attachment.hash` is FHIR's own field for this, and
    it is the cheap way to demonstrate on stage that the page in someone's
    hand and the record in the chart are the same render.
    """
    payload = document_html.encode("utf-8")
    authored_on = authored_on or datetime.now()

    return {
        "resourceType": "DocumentReference",
        "id": session_id,
        "status": "current",
        "docStatus": "final",
        "type": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": LOINC_CLINICAL_NOTE,
                    "display": "Summarization of episode note",
                }
            ],
            "text": "After-visit summary",
        },
        "subject": {"display": "Patient of record"},
        "date": authored_on.isoformat(timespec="seconds"),
        "author": [{"display": clinician_name}],
        "authenticator": {"display": clinician_name},
        "description": (
            "After-visit summary prepared from a recording of the visit with "
            "the patient's consent, reviewed and attested by the named "
            "clinician. Recording deleted at attestation."
        ),
        "content": [
            {
                "attachment": {
                    "contentType": "text/html; charset=utf-8",
                    "language": "en-US",
                    "data": base64.b64encode(payload).decode("ascii"),
                    "size": len(payload),
                    "hash": base64.b64encode(hashlib.sha1(payload).digest()).decode(
                        "ascii"
                    ),
                    "title": f"Visit summary, {visit_date.isoformat()}",
                    "creation": authored_on.isoformat(timespec="seconds"),
                }
            }
        ],
        "context": {"period": {"start": visit_date.isoformat()}},
    }


def write_document_reference(resource: dict[str, Any], path: Path) -> Path:
    """Written outside the session directory on purpose.

    U9 shreds `session_dir`. The chart copy is the one artifact that must
    survive it, so `ui.state` hands this an approved-records path and the
    shredder never sees it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(resource, indent=2))
    return path
