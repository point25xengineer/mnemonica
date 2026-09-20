"""A9 — `parse_sig`. TOOLS.md §2. A grammar over sig language, not an LLM.

**The distinction this whole file exists to protect:**

    not_specified  the clinician never said a dose
    unparseable    a dose was said and we failed to read it

"Take it as directed" is a *complete, correct, successful* parse whose finding
is that no dose exists. Reporting it as a failure blames the tool for the
clinician's omission, and — worse — makes it look identical to *"I could not
hear it"*. That is D16's central rule, and this is where it is made concrete.

Everything here is deterministic and inspectable: regexes over a verbatim
quote, no scoring, no model. If the grammar cannot account for a stretch of
text, it says so in `unparsed_remainder` rather than guessing, because a sig
the tool half-understood is the one place a confident blank is dangerous.

**`partial` has two causes, and only one of them leaves a remainder.** TOOLS.md
§2 defines it as "some components found, `unparsed_remainder` non-empty", which
covers *"take the 25 mg one, you know, the way we discussed"*. It does not
cover *"10 mg for ten days"* — every word accounted for, nothing left over, and
no frequency anywhere. Both are the same thing to the clinician (something is
missing, do not print this as fact) and both get `partial`. The remainder is
empty in the second case because there genuinely is no leftover text, and
inventing one to satisfy the field would be the tool lying about its own
coverage.
"""

from __future__ import annotations

import re

from mnemonica.tools.schemas import ParseSigCall, SigParse

__all__ = ["parse_sig", "GRAMMAR_VERSION"]

GRAMMAR_VERSION = "1.0"

_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
    "half": 0.5, "quarter": 0.25,
}
"""Doses are spoken, so they arrive as words at least as often as digits.

The gaps here were not cosmetic. `fifteen` and `fifty` were both missing — the
pair most often confused by ear, and the one D16 category 2 exists to flag —
and so were every ten from forty up.
"""

_MULTIPLIERS = {"hundred": 100, "thousand": 1000}
"""Scale words, which the old flat table had no way to express.

`"five hundred milligrams"` parsed to **None**, and `"twenty-five mg"` parsed
to **5** — the hyphen is a word boundary, so a single-token alternation
matched `five mg` and silently dropped the `twenty`. A wrong dose that prints
as fact is the one outcome this system is built to make impossible, so the
number grammar has to fold a phrase rather than match a token.
"""

_UNIT_CANON = {
    "mg": "mg", "milligram": "mg", "milligrams": "mg", "mgs": "mg",
    "mcg": "mcg", "microgram": "mcg", "micrograms": "mcg",
    "g": "g", "gram": "g", "grams": "g",
    "ml": "mL", "milliliter": "mL", "milliliters": "mL", "mls": "mL",
    "unit": "unit", "units": "unit", "iu": "unit",
    "tablet": "tablet", "tablets": "tablet", "tab": "tablet", "tabs": "tablet",
    "pill": "tablet", "pills": "tablet",
    "capsule": "capsule", "capsules": "capsule", "cap": "capsule",
    "puff": "puff", "puffs": "puff",
    "drop": "drop", "drops": "drop",
    "patch": "patch", "patches": "patch",
    "teaspoon": "teaspoon", "teaspoons": "teaspoon", "tsp": "teaspoon",
}

_FORM_WORDS = {"tablet", "capsule", "inhaler", "patch", "cream", "ointment",
               "solution", "suspension", "injection", "suppository"}

_ROUTES = {
    "oral": ("by mouth", "orally", "oral", "swallow", "po"),
    "topical": ("on the skin", "topically", "topical", "rub in", "apply to"),
    "inhaled": ("inhale", "inhaled", "puff", "nebuliz"),
    "injection": ("inject", "injection", "subcutaneous", "under the skin",
                  "shot", "intramuscular"),
    "sublingual": ("under your tongue", "under the tongue", "sublingual"),
    "rectal": ("rectally", "suppository"),
    "ophthalmic": ("in your eye", "in the eye", "each eye", "eye drops"),
    "otic": ("in your ear", "in the ear", "ear drops"),
}

_NOT_SPECIFIED = (
    "as directed", "as before", "same as before", "same as always",
    "keep taking it", "keep taking them", "as prescribed", "as you have been",
    "the usual", "usual dose", "per the label", "as needed",  # bare PRN
    "continue as", "stay on the same", "no change",
    # Found by C5 against the real recording: 1c-ii asserts `not_specified`
    # for turn 16's "Just take it the way you've been taking it", and A9's
    # list reached it with neither "as you have been" nor "keep taking it".
    # Without this, D16 category 5 never fires and "your doctor didn't say"
    # renders as "we couldn't parse it" — the one confusion D16 forbids.
    "the way you've been taking it", "the way you have been taking it",
    "been taking it",
)
"""Phrases that are a *complete* answer whose content is "no dose stated".

Deliberately conservative: a phrase here suppresses the `unparseable` status,
so a phrase that actually does carry a dose must never appear on this list.
`"as needed"` is here because a bare *as needed*, with no amount anywhere in
the quote, specifies frequency-of-occasion and nothing else."""

_TIMING = {
    "morning": ("in the morning", "morning", "am", "when you wake"),
    "noon": ("at noon", "midday", "lunchtime", "with lunch"),
    "evening": ("in the evening", "evening", "with dinner", "at dinner",
                "suppertime"),
    "night": ("at night", "bedtime", "at bed", "before bed", "nighttime"),
    "with food": ("with food", "with a meal", "with meals", "after eating",
                  "after a meal"),
    "empty stomach": ("empty stomach", "before eating", "before a meal"),
}

_DAYS = {"monday": "monday", "tuesday": "tuesday", "wednesday": "wednesday",
         "thursday": "thursday", "friday": "friday", "saturday": "saturday",
         "sunday": "sunday"}

# Longest-first so `seventeen` cannot be matched as `seven`, and a phrase of
# number words — `twenty-five`, `five hundred`, `one thousand two hundred` —
# rather than one token.
_NUM_WORD = "|".join(
    sorted([*_NUMBER_WORDS, *_MULTIPLIERS], key=len, reverse=True)
)
_NUM = (r"(?:\d+(?:\.\d+)?|"
        rf"(?:{_NUM_WORD})(?:[\s-]+(?:and[\s-]+)?(?:{_NUM_WORD}))*)")
_UNITS = "|".join(sorted(_UNIT_CANON, key=len, reverse=True))

_RE_DOSE = re.compile(rf"\b({_NUM})\s*({_UNITS})\b", re.IGNORECASE)
_RE_FRACTION = re.compile(
    rf"\b(half|quarter)\s+(?:of\s+)?an?\s+({_UNITS})\b", re.IGNORECASE)
"""*half a tablet* is a dose, and `_RE_DOSE` reads it as **one** tablet: `a`
is a number word, `half` is not adjacent to the unit, and the result is a
doubled dose reported as `partial` with `half` sitting in the remainder.
Fractions get their own pass, before the general one."""
_RE_FREQ_WORD: tuple[tuple[str, float], ...] = (
    # ORDER IS LOAD-BEARING, and it is worth saying why: the bare `\bdaily\b`
    # alternative matches inside "twice daily". A dict got tried in insertion
    # order, hit `daily` first, and read *twice daily* as **once daily** — a
    # silent halving of the dose frequency, from a regex that looked right.
    # Most-specific first; the bare adverbs come last, as fallbacks.
    (r"\bevery other day\b", 0.5),
    (r"\btwice a week\b|\btwice weekly\b", 2 / 7),
    (r"\bonce a week\b|\bonce weekly\b|\bweekly\b", 1 / 7),
    (r"\bonce a month\b|\bmonthly\b", 1 / 30),
    (r"\bfour times (?:a|per) day\b|\bqid\b", 4.0),
    (r"\bthree times (?:a|per) day\b|\bthree times daily\b|\bthrice daily\b|\btid\b", 3.0),
    (r"\btwice (?:a|per) day\b|\btwice daily\b|\btwo times (?:a|per) day\b|\bbid\b", 2.0),
    (r"\bonce (?:a|per) day\b|\bonce daily\b|\bone time (?:a|per) day\b|\bqd\b", 1.0),
    (r"\bevery day\b|\beach day\b|\bdaily\b", 1.0),
)
_RE_INTERVAL = re.compile(rf"\bevery\s+({_NUM})\s*(hours?|hrs?|h)\b", re.IGNORECASE)
_RE_DURATION = re.compile(
    rf"\bfor\s+(?:the\s+next\s+)?({_NUM})\s*(days?|weeks?|months?)\b", re.IGNORECASE)
_RE_MAX = re.compile(
    rf"\b(?:no more than|not more than|up to|maximum of|max of)\s+({_NUM})\s*"
    rf"(?:({_UNITS})\s*)?(?:in|per|a)\s+(?:a\s+)?(?:day|24 hours)\b",
    re.IGNORECASE)
_RE_TOTAL = re.compile(
    rf"\b(?:a total of|dispense|total of)\s+({_NUM})\s*({_UNITS})?\b", re.IGNORECASE)
_RE_PRN = re.compile(
    r"\b(?:as needed|if needed|when needed|only if|prn)\b", re.IGNORECASE)
_RE_PRN_COND = re.compile(
    r"\b(?:as needed|if needed|when needed|only if)\s+(?P<cond>for\s+[^,.;]+|[^,.;]+)",
    re.IGNORECASE)


def _number(token: str) -> float:
    """Fold a number phrase to a value: `"twenty-five"` -> 25.0.

    Standard English composition — units and tens accumulate, `hundred`
    scales what is pending, `thousand` banks it. `"one thousand two hundred
    and fifty"` is 1250.0.
    """
    t = token.lower().strip()
    try:
        return float(t)
    except ValueError:
        pass

    total = current = 0.0
    seen = False
    for word in re.split(r"[\s-]+", t):
        if word in ("and", ""):
            continue
        if word in _MULTIPLIERS:
            scale = _MULTIPLIERS[word]
            if scale == 100:
                current = (current or 1) * 100
            else:
                total += (current or 1) * scale
                current = 0.0
            seen = True
        elif word in _NUMBER_WORDS:
            current += _NUMBER_WORDS[word]
            seen = True
        else:
            raise ValueError(f"not a number phrase: {token!r}")
    if not seen:
        raise ValueError(f"not a number phrase: {token!r}")
    return total + current


def _consume(spans: list[tuple[int, int]], m: re.Match) -> None:
    spans.append((m.start(), m.end()))


def _remainder(text: str, spans: list[tuple[int, int]]) -> str | None:
    """What the grammar could not account for.

    Rendered as the leftover words, not as a character diff: a diff of a
    verbatim quote is unreadable in a review UI, and this string is shown to a
    clinician who has sixty seconds.
    """
    keep = [True] * len(text)
    for a, b in spans:
        for i in range(a, min(b, len(text))):
            keep[i] = False
    left = "".join(c if keep[i] else " " for i, c in enumerate(text))
    words = [w for w in re.split(r"[^\w%/-]+", left) if w]
    filler = {
        "take", "takes", "taking", "one", "a", "an", "the", "of", "and", "to",
        "your", "you", "it", "them", "that", "this", "is", "be", "with",
        "i", "want", "we", "ll", "d", "like", "should", "just", "keep", "on",
        "let", "s", "go", "up", "down", "so", "now", "then", "please", "ok",
        "okay", "for", "in", "at", "from", "each", "every", "per", "start",
        "starting", "continue", "sure", "make", "dose", "doses", "pills",
        "pill", "tablet", "tablets", "medication", "medicine", "same", "as",
        "well", "right", "well", "think", "if", "when", "do", "does", "not",
    }
    leftover = [w for w in words if w.lower() not in filler]
    return " ".join(leftover) if leftover else None


def parse_sig(call: ParseSigCall) -> SigParse:
    """Parse a verbatim dosing instruction.

    No `drug_rxcui` and no `speaker_role` arrive here, by design (§2): the
    model never saw a tool result, and the runtime — not the model — knows who
    was speaking. Strength cross-validation is A11's job, in the pipeline.
    """
    text = call.sig_quote
    low = text.lower()
    spans: list[tuple[int, int]] = []

    out = SigParse(status="unparseable", grammar_version=GRAMMAR_VERSION)

    # --- dose -------------------------------------------------------------
    frac = _RE_FRACTION.search(text)
    if frac:
        out.dose_amount = 0.5 if frac.group(1).lower() == "half" else 0.25
        unit = _UNIT_CANON[frac.group(2).lower()]
        out.dose_unit = unit
        if unit in ("tablet", "capsule", "patch"):
            out.dose_form = unit
        _consume(spans, frac)

    doses = [] if frac else list(_RE_DOSE.finditer(text))
    for m in doses:
        _consume(spans, m)
    if doses and out.dose_amount is None:
        first = doses[0]
        out.dose_amount = _number(first.group(1))
        unit = _UNIT_CANON[first.group(2).lower()]
        out.dose_unit = unit
        if unit in ("tablet", "capsule", "patch"):
            out.dose_form = unit

    # --- form (stated separately from the dose unit) ----------------------
    if out.dose_form is None:
        for form in _FORM_WORDS:
            m = re.search(rf"\b{form}s?\b", low)
            if m:
                out.dose_form = form
                _consume(spans, m)
                break

    # --- route ------------------------------------------------------------
    # Word boundaries, not substring containment: `"puff" in "puffy"` is True,
    # so *"when your ankles look puffy"* was classified route=inhaled and the
    # remainder came back as the word `y`.
    for route, cues in _ROUTES.items():
        m = next((mm for c in cues
                  if (mm := re.search(rf"\b{re.escape(c)}\b", low))), None)
        if m:
            out.route = route
            _consume(spans, m)
            break

    # --- frequency --------------------------------------------------------
    for pattern, per_day in _RE_FREQ_WORD:
        m = re.search(pattern, low)
        if m:
            out.frequency_per_day = per_day
            _consume(spans, m)
            break
    m = _RE_INTERVAL.search(text)
    if m:
        out.interval_hours = _number(m.group(1))
        if out.frequency_per_day is None and out.interval_hours:
            out.frequency_per_day = round(24 / out.interval_hours, 4)
        _consume(spans, m)

    # --- timing / days ----------------------------------------------------
    for label, cues in _TIMING.items():
        for c in cues:
            m = re.search(rf"\b{re.escape(c)}\b", low)
            if m:
                out.timing.append(label)
                _consume(spans, m)
                break
    days = [canon for word, canon in _DAYS.items()
            if re.search(rf"\b{word}s?\b", low)]
    if days:
        out.days_of_week = days
        for word in _DAYS:
            for m in re.finditer(rf"\b{word}s?\b", low):
                _consume(spans, m)

    # --- prn --------------------------------------------------------------
    m = _RE_PRN.search(text)
    if m:
        out.prn = True
        _consume(spans, m)
        cond = _RE_PRN_COND.search(text)
        if cond and cond.group("cond").strip():
            out.prn_condition = cond.group("cond").strip()
            _consume(spans, cond)

    # --- duration / totals / max -----------------------------------------
    m = _RE_DURATION.search(text)
    if m:
        n, unit = _number(m.group(1)), m.group(2).lower()
        mult = 7 if unit.startswith("week") else 30 if unit.startswith("month") else 1
        out.duration_days = int(n * mult)
        _consume(spans, m)
    m = _RE_MAX.search(text)
    if m:
        out.max_daily_amount = _number(m.group(1))
        _consume(spans, m)
    m = _RE_TOTAL.search(text)
    if m:
        out.total_quantity = _number(m.group(1))
        _consume(spans, m)

    # --- status -----------------------------------------------------------
    found_any = any((out.dose_amount is not None, out.frequency_per_day,
                     out.interval_hours, out.duration_days,
                     out.max_daily_amount, out.timing, out.days_of_week))
    explicit_none = any(p in low for p in _NOT_SPECIFIED)
    out.unparsed_remainder = _remainder(text, spans)

    if out.dose_amount is None and explicit_none and not found_any:
        # "Take it as directed" — a complete parse whose finding is that no
        # dose exists. NOT an error: D16 category 5.
        out.status = "not_specified"
        out.parse_confidence = 1.0
        out.unparsed_remainder = None
        out.normalized_sig = "not specified"
        return out

    if not found_any:
        out.status = "unparseable"
        out.parse_confidence = 0.0
        out.normalized_sig = None
        return out

    complete = out.dose_amount is not None and (
        out.frequency_per_day is not None or out.interval_hours is not None
        or out.prn)
    if complete and not out.unparsed_remainder:
        out.status = "parsed"
        out.parse_confidence = 0.95
    else:
        out.status = "partial"
        out.parse_confidence = 0.6 if complete else 0.4
    out.normalized_sig = _normalize_sig(out)
    return out


_FREQ_TEXT = {1.0: "once daily", 2.0: "twice daily", 3.0: "three times daily",
              4.0: "four times daily", 0.5: "every other day"}


def _normalize_sig(p: SigParse) -> str:
    """The canonical string U6's template prints. Built from parsed fields
    only — never from the input text, so nothing unparsed can leak through
    into something that reads as understood."""
    bits: list[str] = []
    if p.dose_amount is not None:
        amount = (f"{p.dose_amount:g}")
        bits.append(f"{amount} {p.dose_unit}" if p.dose_unit else amount)
    if p.frequency_per_day in _FREQ_TEXT:
        bits.append(_FREQ_TEXT[p.frequency_per_day])
    elif p.interval_hours:
        bits.append(f"every {p.interval_hours:g} hours")
    elif p.frequency_per_day:
        bits.append(f"{p.frequency_per_day:g} times per day")
    if p.timing:
        bits.append(", ".join(p.timing))
    if p.days_of_week:
        bits.append("on " + ", ".join(p.days_of_week))
    if p.prn:
        bits.append("as needed" + (f" {p.prn_condition}" if p.prn_condition else ""))
    if p.duration_days:
        bits.append(f"for {p.duration_days} days")
    if p.max_daily_amount:
        bits.append(f"no more than {p.max_daily_amount:g} per day")
    return " ".join(bits) if bits else "not specified"
