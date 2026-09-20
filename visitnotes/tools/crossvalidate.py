"""A11 — cross-validation. **Not the model's job**, and that is the point.

Everything upstream of here checks that the model *pointed* at something real:
span verification proves a quote exists, turn attribution proves who said it.
None of it can tell you that 250 mg of a drug sold only in 5 mg and 10 mg
tablets is wrong, because the model quoted the clinician correctly and the
clinician said it.

This is the knowledge base catching an error nothing else in the pipeline can
see — the thesis demonstrating itself. It runs after `resolve_medication` and
`parse_sig` have both produced output for one item, in the pipeline, on
verified input.

Findings map to D16 dispositions. **Two sigs for one medication is category 7,
blocking** — both values shown with timestamps, the clinician picks. The rest
are prefilled and flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from visitnotes.tools.schemas import MedicationResolution, SigParse

__all__ = ["cross_validate", "Finding"]

Severity = Literal["blocking", "flag"]


@dataclass(frozen=True)
class Finding:
    kind: str
    severity: Severity
    message: str
    d16_category: int | None = None
    detail: dict = field(default_factory=dict)


_STRENGTH = re.compile(r"(\d+(?:\.\d+)?)\s*(MG|MCG|ML|G|UNT)\b", re.IGNORECASE)
_UNIT_ALIAS = {"MG": "mg", "MCG": "mcg", "ML": "mL", "G": "g", "UNT": "unit"}


def _strength_values(strings: list[str]) -> set[tuple[float, str]]:
    """`RXN_AVAILABLE_STRENGTH` is free text — `25 MG`, `10 MG/ML (expressed
    as metoprolol tartrate)`, `12.5 MG`. Pull the leading amount+unit and
    ignore the prose; a strength we cannot parse must not silently become a
    strength that does not exist."""
    out = set()
    for s in strings:
        m = _STRENGTH.search(s)
        if m:
            out.add((float(m.group(1)), _UNIT_ALIAS[m.group(2).upper()]))
    return out


def cross_validate(
    resolution: MedicationResolution,
    sigs: list[SigParse],
    *,
    drug_label: str = "this medication",
) -> list[Finding]:
    """Check one medication item's resolved drug against its parsed sig(s)."""
    findings: list[Finding] = []

    # --- D16 category 7: two instructions for one drug ---------------------
    # Checked first and independently of everything else: if the clinician
    # stated two different regimens, which one to validate against is exactly
    # the question, and answering it here would be the tool making a clinical
    # choice.
    real = [s for s in sigs if s.status in ("parsed", "partial")]
    distinct = {(s.dose_amount, s.dose_unit, s.frequency_per_day) for s in real}
    if len(real) > 1 and len(distinct) > 1:
        findings.append(Finding(
            kind="contradictory_sigs",
            severity="blocking",
            d16_category=7,
            message=(f"Two different instructions were given for "
                     f"{drug_label}. Both are shown; one must be chosen."),
            detail={"sigs": [s.normalized_sig for s in real]},
        ))
        return findings

    if not real:
        return findings
    sig = real[0]

    # --- dose vs available strengths --------------------------------------
    available = _strength_values(resolution.available_strengths)
    if (sig.dose_amount is not None and sig.dose_unit and available
            and resolution.status == "resolved"):
        units = {u for _, u in available}
        if sig.dose_unit in units:
            amounts = {a for a, u in available if u == sig.dose_unit}
            if sig.dose_amount not in amounts:
                # A dose can be two tablets of a marketed strength. Only flag
                # when it is not a whole-number multiple of anything sold —
                # "take two 25 mg tablets" is 50 mg and is not an error.
                multiple = any(
                    a and abs(sig.dose_amount / a - round(sig.dose_amount / a)) < 1e-9
                    and 1 <= round(sig.dose_amount / a) <= 4
                    for a in amounts)
                if not multiple:
                    findings.append(Finding(
                        kind="strength_not_marketed",
                        severity="flag",
                        message=(
                            f"{sig.dose_amount:g} {sig.dose_unit} of "
                            f"{resolution.canonical_name} is not a marketed "
                            f"strength."),
                        detail={"dose": f"{sig.dose_amount:g} {sig.dose_unit}",
                                "available": sorted(
                                    f"{a:g} {u}" for a, u in available)[:12]},
                    ))

    # --- form vs marketed dose forms --------------------------------------
    if sig.dose_form and resolution.dose_forms:
        forms = " ".join(resolution.dose_forms).lower()
        if sig.dose_form.lower() not in forms:
            findings.append(Finding(
                kind="dose_form_not_marketed",
                severity="flag",
                message=(f"{resolution.canonical_name} is not marketed as a "
                         f"{sig.dose_form}."),
                detail={"said": sig.dose_form,
                        "available": resolution.dose_forms[:8]},
            ))

    # --- internal consistency of the sig itself ---------------------------
    if (sig.max_daily_amount is not None and sig.dose_amount is not None
            and sig.frequency_per_day):
        scheduled = sig.dose_amount * sig.frequency_per_day
        if scheduled > sig.max_daily_amount + 1e-9:
            findings.append(Finding(
                kind="exceeds_stated_maximum",
                severity="blocking",
                d16_category=7,
                message=(f"The schedule comes to {scheduled:g} per day but "
                         f"the stated maximum is "
                         f"{sig.max_daily_amount:g}."),
                detail={"scheduled": scheduled,
                        "maximum": sig.max_daily_amount},
            ))

    # --- the salt question, restated where the dose lives ------------------
    if resolution.salt_unspecified:
        findings.append(Finding(
            kind="salt_unspecified",
            severity="flag",
            message=(f"{resolution.canonical_name}: which salt? "
                     + " or ".join(resolution.salt_candidates)
                     + " — they are not dosed the same."),
            detail={"candidates": resolution.salt_candidates},
        ))

    return findings
