"""A6 — `resolve_medication`. TOOLS.md §1.

Staged: exact -> deterministic variants -> phonetic recall -> rescore ->
decide. The stage that matters is the last one, and the number that matters in
it is the **margin**, not the threshold.

A mumbled *"cele-"* scores high against both *Celexa* (citalopram, an
antidepressant) and *Celebrex* (celecoxib, an NSAID). Returning the winner
confidently is the dangerous behaviour — not because the score is wrong, but
because a score of 0.91 against 0.89 is a coin toss the patient cannot see.
So a close second place is `ambiguous`, both candidates are returned, and the
clinician picks with one click.

**Phonetic, not orthographic, scoring.** Whisper mishears; it does not typo.
`metropolol` is not a typing slip for *metoprolol*, it is what the acoustics
gave back, so similarity has to be judged by sound and by stem — which is why
the composite is Jaro-Winkler plus a Double Metaphone agreement term and not
plain Levenshtein.

**DEVIATION from TOOLS.md §1 stage 3, logged in PLAN.md.** The spec makes
Double Metaphone the *blocking* step — "retrieve everything sharing the
query's code". Measured, that fails A6's own acceptance case:
`doublemetaphone("metropolol")` is `MTRPLL` and `doublemetaphone("metoprolol")`
is `MTPRLL`. The codes differ because the error is a **metathesis**, two
sounds swapped, and a phonetic code is a positional encoding — it is robust to
substitution and brittle to transposition. Blocking on it drops the one
example the stage was introduced to recover, and drops it *silently*, as an
`unresolved` with an empty candidate list.

The fix is that the blocking step is not needed at all. A3.5 cut the name
index to **18,094 strings**, and a Jaro-Winkler pass over all of them takes
**14 ms** — under one frame, against 40–60 turns of extraction that each cost
a constrained generation. Blocking buys speed we do not need at the cost of
recall we cannot audit. So recall is exhaustive, and Double Metaphone keeps
the job it is actually good at: a term in the rescore, where agreement is
evidence rather than a gate.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

from jellyfish import jaro_winkler_similarity, levenshtein_distance
from metaphone import doublemetaphone

from visitnotes.kb.db import connect, source_release
from visitnotes.kb.normalize import names_a_dose_form, normalize
from visitnotes.tools.schemas import (
    MedicationCandidate, MedicationResolution, ResolveMedicationCall,
)

__all__ = ["resolve_medication", "MedicationKB",
           "SCORE_THRESHOLD", "AMBIGUITY_MARGIN"]


# ------------------------------------------------------------- 3c thresholds

SCORE_THRESHOLD = 0.72
"""Below this, nothing is a match and the status is `unresolved`.

**Set without labeled data, and biased deliberately.** There is no annotated
mistranscription corpus here, so this is not tuned, it is *chosen*: the
asymmetry is that over-flagging costs a click and under-flagging costs a wrong
dose. Phase 3c revisits it against real audio. Until then the honest answer to
"how did you validate this" is that we did not, so we biased toward asking the
doctor."""

RECALL_FLOOR = 0.80
"""Jaro-Winkler below which a string is not worth rescoring.

A *recall* floor, not a decision threshold: it only decides what gets looked
at, and the rescore decides what wins. Set well below `SCORE_THRESHOLD` on
purpose — a candidate the floor drops can never be flagged, never be offered
as an ambiguity, and never be seen again."""

AMBIGUITY_MARGIN = 0.06
"""How far clear of #2 the winner must be to be `resolved` rather than
`ambiguous`. The same asymmetry, applied to the more dangerous failure: a
confident single answer between *Celexa* and *Celebrex* is worse than a
two-item pick list."""

MAX_FUZZY_EDIT_DISTANCE = 3
"""Beyond this many edits, a high score is not evidence — it is prefix luck.

Measured: *Coumadin* is **not in the Current Prescribable release** (the brand
was discontinued), and a spoken "coumadin" scored 0.81 against *Comtan* —
above threshold, clear of #2, `resolved`. Jaro-Winkler weights the prefix, and
`co` is a prefix an awful lot of drugs share. Four edits between an eight-letter
name and its "match" means a different drug, whatever the composite says.

Truncating here converts that into `unresolved`, which prints as D16 category 4
— the raw heard text, flagged, with near-matches offered. The right answer for
a drug this database does not contain is *"we could not identify this"*, not a
neighbour."""

# Composite rescore weights. Jaro-Winkler dominates because drug names carry
# their identity in the stem; the priors only break ties.
W_JARO, W_PHONETIC, W_TOKEN, W_TTY, W_FREQ = 0.55, 0.15, 0.08, 0.12, 0.10

_TTY_PRIOR = {"IN": 1.0, "BN": 1.0, "PIN": 0.92, "TMSY": 0.70, "SY": 0.65}
_TTY_RANK = {"IN": 0, "PIN": 1, "BN": 2, "TMSY": 3, "SY": 4}
_CANONICAL_RANK = ("IN", "PIN", "BN", "PSN", "SCD", "SBD", "SY", "TMSY")

MAX_SPL_SET_IDS = 50
"""A widely marketed ingredient has thousands of SPL set ids. The openFDA join
(A8) needs a handful of labels, not every NDC ever filed, and an unbounded
list turns one resolution into a megabyte of provenance."""


_PHRASE_TAIL = {
    "up", "to", "at", "of", "from", "for", "in", "on", "by", "with", "about",
    "around", "and", "or", "back", "down", "over", "under", "per", "a", "an",
}
"""Where a spoken mention stops being a drug name.

*"metoprolol **up to** 50 milligrams"*, *"lisonopril **at** 10"* — the head is
everything before these, and the tail is dose and qualifier text that belongs
to `parse_sig`."""


def _self_correction_tail(raw: str) -> str | None:
    """The word a comma-separated stutter converged on, or `None`.

    *"the lyso, ly, lysinop, lysinopril"* is what a real patient sounds like
    reaching for a drug name, and Whisper transcribes the whole run-up. The
    normalized key of the whole run-up matches nothing — 3d's first real pass
    returned it `unresolved` with an **empty** near-match list, which is D16
    category 4 firing without the one thing that makes it useful.

    **This only ever supplies near-matches; it never resolves.** A stutter is
    evidence about what the speaker was reaching for, not evidence about what
    they said, and the difference between those two is the whole of D16.

    Read off the **raw** mention, because `normalize` drops the commas that
    are the only evidence a self-correction happened. Fragments must converge
    — every one sharing a two-character prefix with the last — so that
    *"metoprolol, lisinopril"* is two drugs and not a stutter, and a phrase
    with no comma at all (*"the other blood pressure pill"*, the fixture's
    category 4 plant) is never touched.
    """
    parts = [p.strip() for p in raw.split(",")]
    parts = [p for p in parts if p]
    if len(parts) < 3:
        return None
    tail = parts[-1].split()[-1].lower()
    if len(tail) < 4:
        return None
    for frag in parts[:-1]:
        word = frag.split()[-1].lower()
        if len(word) < 2 or not tail.startswith(word[:2]):
            return None
    return tail


COLLOQUIAL_DESCRIPTORS = frozenset({
    "water", "sugar", "fluid", "oxygen", "iron", "air", "salt", "starch",
    "blood", "heart", "nerve", "pain", "sleep", "stomach", "chest", "breathing",
})
"""Words that name what a pill *does*, and are also RxNorm ingredients.

A deliberately short list, and deliberately not dressed up as a principle. The
frequency prior was tried first and cannot do this job: `water` has 7
prescribable products and `oxygen` 12, against `lisinopril` 16 — but
`potassium` has 1 and `calcium` 0, so any threshold that rejects water also
rejects two real prescriptions.

So: an enumerated list, applied only to the `<descriptor> <form word>` shape.
`metoprolol` is not in it, so *"metoprolol tablet"* is untouched. Measured on
this release, *"my water pill"* and *"the oxygen pill"* were the only mentions
of that shape resolving wrongly; *"my heart pill"*, *"my sugar pill"* and
*"your blood pressure pill"* already came back `unresolved`, and stay that way.

Note what this does **not** cover: *"the oxygen"*, with no form word, still
resolves — supplemental oxygen is a real prescribed therapy and a clinician
saying it means it.
"""


def _is_colloquial_reference(raw: str, key: str) -> bool:
    """*"my water pill"* names an effect, not an ingredient.

    Fires only when both halves of the shape are present: the mention ended in
    a dose form, and what remained is a single descriptor word. TOOLS.md §1
    requires a reference like this to report `unresolved` — the resolver may
    offer what it suspects, but never as a result.
    """
    return " " not in key and key in COLLOQUIAL_DESCRIPTORS \
        and names_a_dose_form(raw)


def _head_of_phrase(key: str) -> str:
    """The leading tokens of a normalized key, cut at the first function word
    or numeral. Returns the key unchanged when there is nothing to cut."""
    out: list[str] = []
    for tok in key.split():
        if tok in _PHRASE_TAIL or tok[0].isdigit():
            break
        out.append(tok)
    return " ".join(out)


@dataclass(frozen=True)
class _Row:
    rxcui: str
    tty: str
    str_: str
    key: str
    salt_key: str
    base_key: str
    dmeta1: str
    dmeta2: str


class MedicationKB:
    """The built knowledge base, opened once and queried per mention."""

    def __init__(self, con: sqlite3.Connection | None = None) -> None:
        self.con = con or connect()
        self.release = source_release(self.con)
        self._rows: list[_Row] | None = None
        self._freq_max = math.log1p(
            self.con.execute(
                "SELECT COALESCE(MAX(product_count), 1) FROM ingredient_freq"
            ).fetchone()[0]
        )

    # -- lookups -----------------------------------------------------------

    @property
    def rows(self) -> list[_Row]:
        """Every name-index row, in memory. 18,094 of them, read once.

        Loaded lazily so importing the module costs nothing, and cached so a
        60-turn extraction pays for it once rather than sixty times.
        """
        if self._rows is None:
            self._rows = [
                _Row(r["rxcui"], r["tty"], r["str"], r["key"], r["salt_key"],
                     r["base_key"], r["dmeta1"], r["dmeta2"])
                for r in self.con.execute(
                    "SELECT rxcui, tty, str, key, salt_key, base_key, "
                    "dmeta1, dmeta2 FROM name_index")
            ]
        return self._rows

    def by_column(self, column: str, value: str) -> list[_Row]:
        if column not in ("key", "salt_key", "base_key", "dmeta1", "dmeta2"):
            raise ValueError(f"not an indexed column: {column}")
        rows = self.con.execute(
            f"SELECT rxcui, tty, str, key, salt_key, base_key, dmeta1, dmeta2 "
            f"FROM name_index WHERE {column} = ?",
            (value,),
        ).fetchall()
        return [_Row(r["rxcui"], r["tty"], r["str"], r["key"], r["salt_key"],
                     r["base_key"], r["dmeta1"], r["dmeta2"]) for r in rows]

    def frequency(self, key: str) -> float:
        row = self.con.execute(
            "SELECT product_count FROM ingredient_freq WHERE ingredient_key=?",
            (key,),
        ).fetchone()
        if not row or not self._freq_max:
            return 0.0
        return min(1.0, math.log1p(row["product_count"]) / self._freq_max)

    def canonical_name(self, rxcui: str) -> str | None:
        rows = self.con.execute(
            "SELECT tty, str FROM concept WHERE rxcui=?", (rxcui,)
        ).fetchall()
        if not rows:
            return None
        rows.sort(key=lambda r: (_CANONICAL_RANK.index(r["tty"])
                                 if r["tty"] in _CANONICAL_RANK else 99,
                                 len(r["str"])))
        return rows[0]["str"]

    def salts(self, rxcui: str) -> list[str]:
        return [r["pin_name"] for r in self.con.execute(
            "SELECT DISTINCT pin_name FROM salt WHERE in_rxcui=? "
            "ORDER BY pin_name", (rxcui,))]

    def brands_for(self, ingredient_key: str) -> list[str]:
        return [r["brand_name"] for r in self.con.execute(
            "SELECT brand_name FROM brand_ingredient WHERE ingredient_key=? "
            "ORDER BY n DESC LIMIT 12", (ingredient_key,))]

    def ingredients_for_brand(self, brand_key: str) -> list[str]:
        return [r["ingredient_name"] for r in self.con.execute(
            "SELECT DISTINCT ingredient_name FROM brand_ingredient "
            "WHERE brand_key=? ORDER BY n DESC LIMIT 6", (brand_key,))]

    def products(self, ingredient_key: str, *, exact: bool = False
                 ) -> list[sqlite3.Row]:
        """Marketed products for an ingredient.

        `exact=True` keys on the salt-bearing name rather than the
        salt-stripped one, and the difference is A11's whole point: asking for
        *metoprolol*'s strengths returns both salts' products, so a 12.5 mg
        **tartrate** strength would silently validate a 12.5 mg **succinate**
        dose that is not marketed. When the resolution named a salt, the
        cross-validation has to be against that salt.
        """
        column = "ingredient_full_key" if exact else "ingredient_key"
        return self.con.execute(
            f"SELECT rxcui, dose_form FROM product WHERE {column}=? "
            f"AND tty IN ('SCD','SBD')", (ingredient_key,)).fetchall()


# ------------------------------------------------------------------ scoring

def _token_overlap(a: str, b: str, jaro: float) -> float:
    """Jaccard over tokens — but only where multi-word names make it mean
    something.

    For two single-token names it degenerates to an exact-match indicator,
    which is not a *similarity* at all: `metropolol` vs `metoprolol` scores a
    flat 0, and that 0 is what pushed the resolver's own acceptance case
    (A6: recover `metropolol`) 0.005 under the threshold — a near-miss
    reported as `unresolved` with the right answer sitting at the top of a
    candidate list nobody was going to look at. Where the term cannot
    discriminate, fall back to the measure that can."""
    ta, tb = set(a.split()), set(b.split())
    if len(ta) == 1 and len(tb) == 1:
        return jaro
    return len(ta & tb) / max(1, len(ta | tb))


def _score(kb: MedicationKB, q_key: str, q_d1: str, q_d2: str, row: _Row) -> float:
    jaro = jaro_winkler_similarity(q_key, row.key)
    phonetic = 1.0 if {q_d1, q_d2} & {row.dmeta1, row.dmeta2} - {""} else 0.0
    token = _token_overlap(q_key, row.key, jaro)
    tty = _TTY_PRIOR.get(row.tty, 0.5)
    freq = kb.frequency(row.salt_key)
    return (W_JARO * jaro + W_PHONETIC * phonetic + W_TOKEN * token
            + W_TTY * tty + W_FREQ * freq)


def _best_by_tty(rows: list[_Row]) -> list[_Row]:
    """Collapse an exact-key hit set to the preferred TTY.

    One normalized key can land on several rows — `metoprolol` is `IN` 6918
    and also a `SY` of something. That is not ambiguity, it is the same
    concept seen through different vocabularies, so prefer the better TTY and
    only call it ambiguous when two *different* concepts tie at that rank.
    """
    if not rows:
        return []
    best = min(_TTY_RANK.get(r.tty, 9) for r in rows)
    return [r for r in rows if _TTY_RANK.get(r.tty, 9) == best]


# ---------------------------------------------------------------- enrichment

def _enrich(kb: MedicationKB, row: _Row, res: MedicationResolution) -> None:
    res.rxcui = row.rxcui
    res.tty = row.tty
    res.canonical_name = kb.canonical_name(row.rxcui) or row.str_
    res.is_brand = row.tty == "BN"

    if row.tty == "BN":
        res.ingredients = kb.ingredients_for_brand(row.key)
        res.brand_names = [row.str_]
        ing_key = normalize(res.ingredients[0]).salt_key if res.ingredients else row.key
    else:
        res.ingredients = [row.str_]
        ing_key = row.salt_key
        res.brand_names = kb.brands_for(ing_key)

    # A5.5 — one hash lookup, and the whole point of the table.
    if row.tty == "IN":
        salts = kb.salts(row.rxcui)
        if salts:
            res.salt_unspecified = True
            res.salt_candidates = salts

    # A PIN names a specific salt, so validate against that salt's products.
    # An IN does not, so the union across salts is the honest answer.
    products = (kb.products(row.key, exact=True) if row.tty == "PIN"
                else kb.products(ing_key))
    if not products:
        products = kb.products(ing_key)
    rxcuis = [p["rxcui"] for p in products]
    res.dose_forms = sorted({p["dose_form"] for p in products if p["dose_form"]})

    if rxcuis:
        marks = ",".join("?" * len(rxcuis))
        res.available_strengths = sorted({
            r["strength"] for r in kb.con.execute(
                f"SELECT DISTINCT strength FROM strength WHERE rxcui IN ({marks})",
                rxcuis)})
        res.spl_set_ids = [r["spl_set_id"] for r in kb.con.execute(
            f"SELECT DISTINCT spl_set_id FROM spl WHERE rxcui IN ({marks}) "
            f"LIMIT {MAX_SPL_SET_IDS}", rxcuis)]
    # The concept's own SPL ids, if it has any, come first.
    own = [r["spl_set_id"] for r in kb.con.execute(
        "SELECT DISTINCT spl_set_id FROM spl WHERE rxcui=?", (row.rxcui,))]
    if own:
        res.spl_set_ids = list(dict.fromkeys(own + res.spl_set_ids))[:MAX_SPL_SET_IDS]


# ------------------------------------------------------------------- the tool

def resolve_medication(
    call: ResolveMedicationCall, kb: MedicationKB
) -> MedicationResolution:
    """Resolve a spoken drug mention against RxNorm.

    `call.mention_quote` arrives **verbatim**, misspellings included — that is
    the contract (TOOLS.md §0) and it is what makes span verification possible.
    Correcting it is this function's job, not the model's.

    **Head-of-phrase backoff.** TOOLS.md §1 tells the model to pass the drug
    name alone, without dose or context. `fixtures/golden_extraction.json`
    does not: its mention quotes are `"the metoprolol up to 50 milligrams"`
    and `"the lisonopril at 10"`, and it expects both `resolved`. Both are
    right in their own terms — the instruction is what the model is *asked*
    for, the fixture is what a real extraction *does*, and a resolver that
    only handles the well-behaved case fails on the fixture Tracks C and D are
    already building against.

    So a phrase that does not resolve whole is retried on its **head**: the
    tokens before the first preposition or numeral. English puts the head of
    a noun phrase early, and the tail after *up to* / *at* / *of* is where the
    dose and the qualifiers live.

    Deliberately NOT a general "try every prefix" backoff. That version was
    written first and it resolved *"the other blood pressure pill"* — the
    fixture's D16 category 4 plant, which must come back `unresolved` — by
    scoring the prefix `other blood` against the index until something stuck.
    Chopping at a closed list of function words cannot do that: a phrase with
    no preposition and no numeral is not retried at all, and the retry runs
    the same stages at the same thresholds as the first attempt.
    """
    n = normalize(call.mention_quote)
    if not n.key:
        return MedicationResolution(status="unresolved",
                                    source_release=kb.release)

    res = _resolve_normalized(n, call.mention_quote, kb)

    # *"my water pill"* — a description of an effect, whose residue after the
    # form word is stripped happens to be a real RxNorm ingredient. Demote it
    # before anything downstream can treat it as an identified drug; what we
    # suspect travels as a candidate, which is where a suspicion belongs.
    if res.status == "resolved" and _is_colloquial_reference(
        call.mention_quote, n.key
    ):
        return MedicationResolution(
            status="unresolved",
            match_type="none",
            match_confidence=0.0,
            candidates=[MedicationCandidate(
                rxcui=res.rxcui, name=res.canonical_name or n.key,
                tty=res.tty or "IN",
                score=round(res.match_confidence or 0.0, 4),
                edit_distance=res.edit_distance or 0,
            )] if res.rxcui else [],
            source_release=kb.release,
        )

    if res.status != "unresolved":
        return res

    head = _head_of_phrase(n.key)
    if head and head != n.key:
        attempt = _resolve_normalized(normalize(head), head, kb)
        if attempt.status != "unresolved":
            return attempt

    # Still unresolved. If the mention was a self-correction, say what it was
    # converging on — as a suggestion the clinician confirms, never as a
    # result. `res.status` is deliberately untouched.
    if not res.candidates:
        tail = _self_correction_tail(call.mention_quote)
        if tail:
            guess = _resolve_normalized(normalize(tail), tail, kb)
            if guess.status == "resolved" and guess.rxcui:
                res.candidates = [MedicationCandidate(
                    rxcui=guess.rxcui, name=guess.canonical_name or tail,
                    tty=guess.tty or "IN",
                    score=round(guess.match_confidence or 0.0, 4),
                    edit_distance=guess.edit_distance or 0)]
            elif guess.candidates:
                res.candidates = list(guess.candidates[:3])
    return res


def _resolve_normalized(
    n, raw: str, kb: MedicationKB
) -> MedicationResolution:
    res = MedicationResolution(status="unresolved", source_release=kb.release)
    if not n.key:
        return res

    d1, d2 = doublemetaphone(n.key.replace("-", " "))

    # 1 — exact hash on the normalized key.
    hits = _best_by_tty(kb.by_column("key", n.key))
    if hits:
        distinct = {r.rxcui for r in hits}
        if len(distinct) == 1:
            row = hits[0]
            res.status = "resolved"
            res.match_type = (
                "exact" if raw.strip() == row.str_ else "case_insensitive"
            )
            res.edit_distance = 0
            res.match_confidence = 1.0
            _enrich(kb, row, res)
            return res
        # Two different concepts share one spoken key. That is real ambiguity,
        # not a vocabulary artefact, and it is exactly what must not be
        # silently collapsed to a winner.
        res.status = "ambiguous"
        res.match_type = "exact"
        res.edit_distance = 0
        res.match_confidence = 1.0
        res.candidates = [
            MedicationCandidate(rxcui=r.rxcui, name=r.str_, tty=r.tty,
                                score=1.0, edit_distance=0)
            for r in sorted(hits, key=lambda r: r.str_)
        ]
        return res

    # 2 — deterministic variants. No scoring yet.
    for column, value in (("salt_key", n.key), ("key", n.salt_key),
                          ("key", n.base_key), ("base_key", n.base_key)):
        if not value:
            continue
        variant = _best_by_tty(kb.by_column(column, value))
        if variant and len({r.rxcui for r in variant}) == 1:
            row = variant[0]
            res.status = "resolved"
            res.match_type = "fuzzy"
            res.edit_distance = levenshtein_distance(n.key, row.key)
            res.match_confidence = 0.9
            _enrich(kb, row, res)
            return res

    # 3 — candidate generation: exhaustive, not blocked. See the module
    # docstring for why the spec's Double Metaphone bucket is not a gate here.
    pool: dict[tuple[str, str], _Row] = {}
    for r in kb.rows:
        if jaro_winkler_similarity(n.key, r.key) >= RECALL_FLOOR:
            pool[(r.rxcui, r.key)] = r
        elif {d1, d2} & {r.dmeta1, r.dmeta2} - {""}:
            # A phonetic twin whose spelling diverged far enough to fall under
            # the floor is exactly the case the code was added for; keep it.
            pool[(r.rxcui, r.key)] = r

    if not pool:
        return res

    # 4 — rescore.
    scored = sorted(
        ((_score(kb, n.key, d1, d2, r), r) for r in pool.values()),
        key=lambda sr: (-sr[0], _TTY_RANK.get(sr[1].tty, 9), sr[1].str_),
    )

    # Collapse before comparing #1 with #2, on the normalized KEY rather than
    # on the RxCUI. Two rows for one RxCUI are obviously not two candidates —
    # but neither are `hydrOXYzine` (5553) and `hydrOXYzine Pill` (1164647),
    # which are two RxCUIs spelling one spoken name. Keying on RxCUI alone let
    # that pair fill both places and reported a clean match as `ambiguous`,
    # asking the clinician to choose between a drug and itself. Ambiguity has
    # to mean two different *answers*.
    by_key: dict[str, tuple[float, _Row]] = {}
    for score, r in scored:
        prev = by_key.get(r.key)
        if prev is None or _TTY_RANK.get(r.tty, 9) < _TTY_RANK.get(prev[1].tty, 9):
            by_key[r.key] = (prev[0] if prev else score, r)
    ranked = sorted(by_key.values(), key=lambda sr: -sr[0])

    top_score, top = ranked[0]
    top_edit = levenshtein_distance(n.key, top.key)
    if top_score < SCORE_THRESHOLD or top_edit > MAX_FUZZY_EDIT_DISTANCE:
        res.candidates = [
            MedicationCandidate(rxcui=r.rxcui, name=r.str_, tty=r.tty,
                                score=round(s, 4),
                                edit_distance=levenshtein_distance(n.key, r.key))
            for s, r in ranked[:5]
        ]
        return res    # unresolved — D16 category 4

    # 5 — decide on the MARGIN, not the threshold.
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    if top_score - runner_up < AMBIGUITY_MARGIN:
        res.status = "ambiguous"
        res.match_type = "fuzzy"
        res.match_confidence = round(top_score, 4)
        res.edit_distance = top_edit
        res.candidates = [
            MedicationCandidate(rxcui=r.rxcui, name=r.str_, tty=r.tty,
                                score=round(s, 4),
                                edit_distance=levenshtein_distance(n.key, r.key))
            for s, r in ranked[:5]
            if top_score - s < AMBIGUITY_MARGIN * 2
        ]
        return res

    res.status = "resolved"
    res.match_type = "fuzzy"
    res.match_confidence = round(top_score, 4)
    res.edit_distance = top_edit
    _enrich(kb, top, res)
    res.candidates = [
        MedicationCandidate(rxcui=r.rxcui, name=r.str_, tty=r.tty,
                            score=round(s, 4),
                            edit_distance=levenshtein_distance(n.key, r.key))
        for s, r in ranked[1:4]
    ]
    return res
