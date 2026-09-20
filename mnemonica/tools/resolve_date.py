"""A10 — `resolve_date`. TOOLS.md §3.

**The anchor is injected, never a model argument.** The model does not know
today's date and would invent one, and every date on the printed page would
then rest on a value nothing verified. `Session.visit_date` (D18) is read once
from the audio file's mtime at ingest, persisted, and passed in here.

**`display_string` carries both forms**, also per D18:

    "three weeks from today, which is Friday, October 9"

An elderly patient reading a bare date has no way to catch an error in it.
Reading both lets them — which only works if the day-of-week is right, so it is
computed, never written by hand. (TOOLS.md's own example got this wrong once:
it said *Friday, October 10*, and October 10, 2026 is a Saturday.)

**Past direction is not an edge case.** *"You started that three months ago"*
is a valid, resolvable, backward-looking date that appears in real histories,
and a resolver that assumes every relative phrase points forward will silently
schedule a follow-up for a thing that already happened.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from mnemonica.tools.schemas import DateResolution, ResolveDateCall

__all__ = ["resolve_date"]

_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "couple": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fourteen": 14, "fifteen": 15, "twenty": 20,
    "thirty": 30, "sixty": 60, "ninety": 90,
}
_NUM = r"(?:\d+|" + "|".join(_NUMBER_WORDS) + r")"

_UNIT_DAYS = {"day": 1, "week": 7, "fortnight": 14, "month": 30, "year": 365}

_PAST = re.compile(
    r"\bago\b"
    r"|\blast\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|week|month|year)\b"
    r"|\bback\s+in\s+(?:january|february|march|april|may|june|july|august"
    r"|september|october|november|december|\d{4})\b"
    r"|\bsince\b|\bpreviously\b|\bthe previous\b",
    re.IGNORECASE)
"""Past-direction cues, and every one of them is narrowed on purpose.

The first draft had a bare `\bback in\b`, which matches **"come back in three
weeks"** — the single most common follow-up phrasing there is, and TOOLS.md's
own worked example. It resolved to three weeks *before* the visit and printed
a confident August date for a September appointment. A bare `\blast\b` has the
same shape of bug against "the last time we talked".

A past cue flips the sign of every arithmetic branch below it, so a loose one
does not degrade the answer, it inverts it."""

_RELATIVE = re.compile(
    rf"\b(?:in|after|for)?\s*({_NUM})\s+(day|week|fortnight|month|year)s?\b",
    re.IGNORECASE)
_VAGUE_RELATIVE = re.compile(
    r"\b(?:in\s+)?a\s+(few|couple of|couple)\s+(day|week|month)s?\b",
    re.IGNORECASE)
_WEEKDAY = re.compile(
    r"\b(?:(next|this|last)\s+)?(monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday)\b", re.IGNORECASE)
_TOMORROW = re.compile(r"\btomorrow\b", re.IGNORECASE)
_YESTERDAY = re.compile(r"\byesterday\b", re.IGNORECASE)
_TODAY = re.compile(r"\btoday\b", re.IGNORECASE)
_MONTH_DAY = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|"
    r"november|december)\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.IGNORECASE)
_MONTH_ONLY = re.compile(
    r"\b(?:in\s+)?(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\b(?!\s+\d)", re.IGNORECASE)

_EVENT_ANCHOR = re.compile(
    r"\b(?:before|after|following|prior to)\s+(?:your|the|his|her)?\s*"
    r"(?P<event>[a-z][a-z\s-]{2,40}?)(?:[,.;]|$)", re.IGNORECASE)
"""*"the week before your procedure"* — anchored to an event the session does
not know the date of. The honest status is `unanchored`, and the clinician
supplies the reference date at review. Guessing the procedure date from the
visit date would be inventing a medical fact."""

_NOT_A_DATE = re.compile(
    r"^\s*(?:as needed|if needed|when needed|as directed|sometime|whenever)"
    r"\s*$", re.IGNORECASE)

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}


def _number(token: str) -> int:
    t = token.lower()
    return _NUMBER_WORDS.get(t, None) if t in _NUMBER_WORDS else int(t)


def _pretty(d: date) -> str:
    return f"{calendar.day_name[d.weekday()]}, {calendar.month_name[d.month]} {d.day}"


def _display(phrase: str, d: date) -> str:
    """Both forms, D18. Computed — the day-of-week is never written by hand.

    When the phrase already names the calendar date ("October 9"), repeating it
    reads as a stutter — *"October 9, which is Friday, October 9"*. The part the
    patient cannot verify unaided is the **day of week**, so that is what gets
    added."""
    said = phrase.strip().rstrip(".")
    if calendar.month_name[d.month].lower() in said.lower():
        return f"{said}, which is a {calendar.day_name[d.weekday()]}"
    return f"{said}, which is {_pretty(d)}"


def resolve_date(call: ResolveDateCall, visit_date: date) -> DateResolution:
    """Resolve a spoken time expression against the session's visit date.

    `visit_date` is a parameter of this function and **not** a field of
    `ResolveDateCall` — that separation is the whole point of D18.
    """
    phrase = call.phrase_quote
    low = phrase.lower()
    res = DateResolution(status="unparseable", anchor_date=visit_date,
                         original_phrase=phrase)

    if _NOT_A_DATE.match(low):
        res.status = "not_a_date"
        res.resolution_confidence = 0.9
        return res

    past = bool(_PAST.search(low))
    sign = -1 if past else 1

    # Event-anchored beats every calendar rule: "the week before your
    # procedure" contains "week", and reading it as seven days from today
    # would produce a confident, wrong, printable date.
    ev = _EVENT_ANCHOR.search(phrase)
    if ev and not _WEEKDAY.search(low) and not _MONTH_DAY.search(low):
        event = ev.group("event").strip()
        if event and not any(u in event for u in _UNIT_DAYS):
            res.status = "unanchored"
            res.depends_on_event = event
            res.direction = "past" if past else "future"
            res.resolution_confidence = 0.8
            res.display_string = phrase.strip()
            return res

    if _TOMORROW.search(low):
        return _exact(res, phrase, visit_date + timedelta(days=1), "future")
    if _YESTERDAY.search(low):
        return _exact(res, phrase, visit_date - timedelta(days=1), "past")
    if _TODAY.search(low):
        return _exact(res, phrase, visit_date, "future")

    m = _MONTH_DAY.search(phrase)
    if m:
        month, day = _MONTHS[m.group(1).lower()], int(m.group(2))
        year = visit_date.year
        try:
            d = date(year, month, day)
        except ValueError:
            res.status = "unparseable"
            return res
        # A month/day already past in this year means next year, unless the
        # phrase points backwards.
        if not past and d < visit_date:
            d = date(year + 1, month, day)
        elif past and d > visit_date:
            d = date(year - 1, month, day)
        return _exact(res, phrase, d, "past" if past else "future")

    m = _VAGUE_RELATIVE.search(phrase)
    if m:
        unit = _UNIT_DAYS[m.group(2).lower()]
        lo, hi = (2, 3) if m.group(1).lower().startswith("couple") else (2, 4)
        res.status = "resolved_range"
        res.range_start = visit_date + timedelta(days=sign * lo * unit)
        res.range_end = visit_date + timedelta(days=sign * hi * unit)
        if past:
            res.range_start, res.range_end = res.range_end, res.range_start
        res.precision = "vague"
        res.direction = "past" if past else "future"
        res.resolution_confidence = 0.6
        res.display_string = (
            f"{phrase.strip().rstrip('.')}, which is between "
            f"{_pretty(res.range_start)} and {_pretty(res.range_end)}")
        return res

    m = _RELATIVE.search(phrase)
    if m:
        n = _number(m.group(1))
        unit = m.group(2).lower()
        days = n * _UNIT_DAYS[unit]
        d = visit_date + timedelta(days=sign * days)
        precision = "exact_day" if unit in ("day", "week", "fortnight") else "month"
        return _exact(res, phrase, d, "past" if past else "future",
                      precision=precision,
                      confidence=0.9 if precision == "exact_day" else 0.7)

    m = _WEEKDAY.search(phrase)
    if m:
        qualifier = (m.group(1) or "").lower()
        target = [d.lower() for d in calendar.day_name].index(m.group(2).lower())
        backward = qualifier == "last" or past
        delta = (target - visit_date.weekday()) % 7
        if backward:
            delta = -((visit_date.weekday() - target) % 7 or 7)
        elif delta == 0 or qualifier == "next":
            delta = delta or 7
        return _exact(res, phrase, visit_date + timedelta(days=delta),
                      "past" if backward else "future", confidence=0.75)

    m = _MONTH_ONLY.search(phrase)
    if m:
        month = _MONTHS[m.group(1).lower()]
        year = visit_date.year + (1 if not past and month < visit_date.month else 0)
        if past and month > visit_date.month:
            year -= 1
        res.status = "resolved_range"
        res.range_start = date(year, month, 1)
        res.range_end = date(year, month,
                             calendar.monthrange(year, month)[1])
        res.precision = "month"
        res.direction = "past" if past else "future"
        res.resolution_confidence = 0.6
        res.display_string = (
            f"{phrase.strip().rstrip('.')}, which is sometime in "
            f"{calendar.month_name[month]} {year}")
        return res

    return res    # unparseable — prefilled and flagged, never guessed


def _exact(res: DateResolution, phrase: str, d: date,
           direction: str, precision: str = "exact_day",
           confidence: float = 0.95) -> DateResolution:
    res.status = "resolved"
    res.resolved_date = d
    res.precision = precision
    res.direction = direction
    res.resolution_confidence = confidence
    res.display_string = _display(phrase, d)
    return res
