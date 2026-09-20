"""A1–A5.5, A7 — build the RxNorm knowledge base into one SQLite file.

    /Users/evancanty/vn-shared/.venv/bin/python -m visitnotes.kb.build

Everything here is **offline and deterministic**: same RRF in, same `.db` out.
No ML dependency, so a Phase 0 failure does not touch this track.

The gotcha that catches everyone once, stated up front: **every RRF line ends
with a trailing `|`**, so `line.split('|')` yields a phantom empty final column.
That is harmless for positional reads (the phantom is past the last real field)
but it makes the column count 19 rather than 18, so any `assert len(f) == 18`
fails and any "last field" read returns `''`. `_rows()` strips it once, here,
and nothing else in the codebase splits an RRF line.

Shape of the result — see `SCHEMA` below:

| table | what it answers | step |
|---|---|---|
| `name_index` | "someone said *X*; which concept is that?" — 18,094 rows | A3.5/A4 |
| `product` | "what is actually marketed for this concept?" | A1 |
| `spl` | `rxcui -> spl_set_id`, the **only** correct openFDA join | A2 |
| `strength` | `RXN_AVAILABLE_STRENGTH`, for A11 cross-validation | A2 |
| `ingredient_freq` | prescribing-frequency proxy, so fuzzy ranks sanely | A5 |
| `salt` | the 32 ingredients where one spoken word hides two schedules | A5.5 |
| `brand_ingredient` | brand -> ingredient, parsed out of `SBD` brackets | A7 |
| `meta` | `source_release`, read from the release, never hardcoded | — |
"""

from __future__ import annotations

import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from metaphone import doublemetaphone

from visitnotes.kb.normalize import has_dose, normalize

REPO = Path(__file__).resolve().parents[2]
RRF = REPO / "rrf"
DB_PATH = REPO / "data" / "rxnorm.db"

NAME_TTYS_UNFILTERED = ("IN", "BN", "PIN")
NAME_TTYS_DOSE_FILTERED = ("SY", "TMSY")
PRODUCT_TTYS = ("SCD", "SBD", "PSN")

EXPECTED_NAME_INDEX_ROWS = 18_094   # A3.5's acceptance number

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE concept (
    rxcui TEXT NOT NULL,
    tty   TEXT NOT NULL,
    str   TEXT NOT NULL
);
CREATE INDEX ix_concept_rxcui ON concept(rxcui);
CREATE INDEX ix_concept_tty   ON concept(tty);

CREATE TABLE name_index (
    rxcui    TEXT NOT NULL,
    tty      TEXT NOT NULL,
    str      TEXT NOT NULL,
    key      TEXT NOT NULL,
    salt_key TEXT NOT NULL,
    base_key TEXT NOT NULL,
    release_modifier TEXT,
    dmeta1   TEXT NOT NULL,
    dmeta2   TEXT NOT NULL
);
CREATE INDEX ix_name_key      ON name_index(key);
CREATE INDEX ix_name_salt_key ON name_index(salt_key);
CREATE INDEX ix_name_base_key ON name_index(base_key);
CREATE INDEX ix_name_dmeta1   ON name_index(dmeta1);
CREATE INDEX ix_name_dmeta2   ON name_index(dmeta2);
CREATE INDEX ix_name_rxcui    ON name_index(rxcui);

CREATE TABLE product (
    rxcui TEXT NOT NULL,
    tty   TEXT NOT NULL,
    str   TEXT NOT NULL,
    ingredient_key TEXT NOT NULL,
    ingredient_full_key TEXT NOT NULL,
    dose_form TEXT
);
CREATE INDEX ix_product_ing   ON product(ingredient_key);
CREATE INDEX ix_product_ingf  ON product(ingredient_full_key);
CREATE INDEX ix_product_rxcui ON product(rxcui);

CREATE TABLE spl (rxcui TEXT NOT NULL, spl_set_id TEXT NOT NULL);
CREATE INDEX ix_spl_rxcui ON spl(rxcui);
CREATE INDEX ix_spl_set   ON spl(spl_set_id);

CREATE TABLE strength (rxcui TEXT NOT NULL, strength TEXT NOT NULL);
CREATE INDEX ix_strength_rxcui ON strength(rxcui);

CREATE TABLE ingredient_freq (
    ingredient_key TEXT PRIMARY KEY,
    product_count  INTEGER NOT NULL
);

CREATE TABLE salt (
    in_rxcui TEXT NOT NULL,
    in_name  TEXT NOT NULL,
    in_key   TEXT NOT NULL,
    pin_rxcui TEXT NOT NULL,
    pin_name  TEXT NOT NULL
);
CREATE INDEX ix_salt_in_key ON salt(in_key);
CREATE INDEX ix_salt_in_rxcui ON salt(in_rxcui);

CREATE TABLE brand_ingredient (
    brand_key      TEXT NOT NULL,
    brand_name     TEXT NOT NULL,
    ingredient_key TEXT NOT NULL,
    ingredient_name TEXT NOT NULL,
    n              INTEGER NOT NULL
);
CREATE INDEX ix_brand_key ON brand_ingredient(brand_key);
"""


def _rows(path: Path):
    """Yield RRF fields with the trailing-pipe phantom column removed."""
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            f = line.rstrip("\n").split("|")
            if f and f[-1] == "":
                f.pop()
            yield f


# ---------------------------------------------------------------- A1 / A3.5

_DOSE_HEAD = re.compile(r"\s\d")
_BRACKETED = re.compile(r"\[([^\]]+)\]\s*$")
_RATE_PREFIX = re.compile(
    r"^[\d.]+\s*(?:HR|ML|ACTUAT|DAY|MG)\s+", re.IGNORECASE
)
"""RxNorm puts the release rate FIRST: `24 HR metoprolol succinate 25 MG
Extended Release Oral Tablet`. Without stripping it, the ingredient head of
every extended-release product is `24 hr metoprolol succinate` — which is not
a key anything looks up, so the frequency prior undercounts exactly the drugs
most likely to be discussed and A5.5 silently loses metoprolol, the hero
drug of the demo. 4,900 product strings start this way."""


def _ingredient_head(s: str) -> str:
    """Leading text of a product string, before the first dose numeral.

    `metoprolol succinate 25 MG Extended Release Oral Tablet [Toprol-XL]`
    -> `metoprolol succinate`. Crude, and deliberately so: A7 documents that
    bracket/leading-text parsing is the v1 stand-in for `RXNREL.RRF`.
    """
    s = _BRACKETED.sub("", s).strip()
    s = _RATE_PREFIX.sub("", s).strip()
    m = _DOSE_HEAD.search(s)
    return (s[: m.start()] if m else s).strip()


def load_conso(con: sqlite3.Connection, dose_forms: set[str]) -> None:
    name_rows, product_rows, concept_rows = [], [], []
    kept = defaultdict(int)

    for f in _rows(RRF / "RXNCONSO.RRF"):
        if len(f) < 17 or f[1] != "ENG" or f[16] == "Y":
            continue
        rxcui, tty, string = f[0], f[12], f[14]
        concept_rows.append((rxcui, tty, string))

        if tty in NAME_TTYS_UNFILTERED or (
            tty in NAME_TTYS_DOSE_FILTERED and not has_dose(string)
        ):
            n = normalize(string)
            if not n.key:
                continue
            d1, d2 = doublemetaphone(n.key.replace("-", " "))
            name_rows.append(
                (rxcui, tty, string, n.key, n.salt_key, n.base_key,
                 n.release_modifier, d1, d2 or d1)
            )
            kept[tty] += 1

        if tty in PRODUCT_TTYS:
            head = _ingredient_head(string)
            n = normalize(head) if head else None
            # Two ingredient keys, and the second one is not redundant:
            # `ingredient_key` is salt-stripped, so every metoprolol product
            # counts toward one frequency prior (A5); `ingredient_full_key`
            # keeps the salt, which is how A5.5 asks "is this salt actually
            # marketed?" A salt nobody sells cannot be what the clinician
            # meant, so it should not raise a dosing ambiguity.
            ing_key = n.salt_key if n else ""
            ing_full = n.key if n else ""
            low = string.lower()
            form = next(
                (df for df in dose_forms if low.endswith(" " + df)), None
            )
            product_rows.append((rxcui, tty, string, ing_key, ing_full, form))

    con.executemany("INSERT INTO concept VALUES (?,?,?)", concept_rows)
    con.executemany(
        "INSERT INTO name_index VALUES (?,?,?,?,?,?,?,?,?)", name_rows
    )
    con.executemany("INSERT INTO product VALUES (?,?,?,?,?,?)", product_rows)
    print(f"  name_index  {len(name_rows):>7,}  " +
          "  ".join(f"{t} {kept[t]:,}" for t in
                    NAME_TTYS_UNFILTERED + NAME_TTYS_DOSE_FILTERED))
    print(f"  product     {len(product_rows):>7,}")
    print(f"  concept     {len(concept_rows):>7,}  (A1: every ENG, "
          f"non-suppressed row)")


def collect_dose_forms() -> set[str]:
    """The `DF` concepts (120 of them), lowercased, longest first.

    Used as suffix tests against product strings, so a product's dose form is
    read off RxNorm's own vocabulary rather than a hand-written list that
    silently misses `Extended Release Oral Capsule`.
    """
    forms = {
        f[14].lower()
        for f in _rows(RRF / "RXNCONSO.RRF")
        if len(f) >= 17 and f[1] == "ENG" and f[16] != "Y" and f[12] == "DF"
    }
    return set(sorted(forms, key=len, reverse=True))


# ---------------------------------------------------------------------- A2

def load_sat(con: sqlite3.Connection) -> None:
    spl, strengths = [], []
    for f in _rows(RRF / "RXNSAT.RRF"):
        if len(f) < 11:
            continue
        atn, atv = f[8], f[10]
        if not atv:
            continue
        if atn == "SPL_SET_ID":
            spl.append((f[0], atv))
        elif atn == "RXN_AVAILABLE_STRENGTH":
            strengths.append((f[0], atv))
    con.executemany("INSERT INTO spl VALUES (?,?)", spl)
    con.executemany("INSERT INTO strength VALUES (?,?)", strengths)
    print(f"  spl         {len(spl):>7,}  over "
          f"{len({r for r, _ in spl}):,} rxcuis")
    print(f"  strength    {len(strengths):>7,}")


# ---------------------------------------------------------------------- A5

def build_frequency(con: sqlite3.Connection) -> None:
    """Product count per ingredient — the prescribing-frequency proxy.

    Counts `SCD`/`SBD` only, not `PSN`: `PSN` is a second *name* for a product
    that is already counted, so including it double-counts exactly the drugs
    with the most marketed products and inflates the prior it is meant to
    measure.
    """
    con.execute(
        "INSERT INTO ingredient_freq "
        "SELECT ingredient_key, COUNT(*) FROM product "
        "WHERE tty IN ('SCD','SBD') AND ingredient_key != '' "
        "GROUP BY ingredient_key"
    )
    n = con.execute("SELECT COUNT(*) FROM ingredient_freq").fetchone()[0]
    print(f"  ingredient_freq {n:>4,}")


# -------------------------------------------------------------------- A5.5

def build_salt_table(con: sqlite3.Connection) -> None:
    """The `IN` concepts with two or more distinct, **marketed** `PIN` salts.

    `RXNREL.RRF` holds the authoritative parent/child graph and v1 does not
    load it (A7), so the linkage is made through A3's salt key instead: `PIN`
    *metoprolol succinate* salt-strips to `metoprolol`, which is `IN` 6918's
    primary key. A string join standing in for a graph edge.

    Two filters on top of "2+ children", and each one earns its place:

    1. **The suffix must be a counter-ion** (`SALT_WORDS`). Without it the join
       returns 151 ingredients, most of them hydration states
       (*X monohydrate* vs *X anhydrous*) and formulations (*amphotericin B
       liposomal*). Those are not two dosing schedules wearing one name.
    2. **Both salts must actually be marketed** — each must head at least one
       `SCD`/`SBD` product. A salt with nothing on the market cannot be what
       the clinician meant, and flagging it would spend the patient's
       attention on a choice that does not exist.

    The flag is only worth anything if it is rare. A5.5's argument is that 32
    of 5,844 fires seldom enough to mean something; what actually falls out of
    this release under those two filters is recorded by the caller, and the
    number is an acceptance criterion precisely so that a drift in the join
    shows up as a number rather than as a silent miss.
    """
    con.execute(
        "INSERT INTO salt (in_rxcui, in_name, in_key, pin_rxcui, pin_name) "
        "SELECT i.rxcui, i.str, i.key, p.rxcui, p.str "
        "  FROM name_index i "
        "  JOIN name_index p ON p.salt_key = i.key AND p.key != i.key "
        " WHERE i.tty = 'IN' AND p.tty = 'PIN' "
        "   AND EXISTS (SELECT 1 FROM product m "
        "                WHERE m.ingredient_full_key = p.key "
        "                  AND m.tty IN ('SCD','SBD')) "
        " GROUP BY i.rxcui, p.rxcui"
    )
    # Drop ingredients left with a single marketed salt — the join above
    # filters children, so the "2+" test has to be re-applied after it.
    con.execute(
        "DELETE FROM salt WHERE in_rxcui IN ("
        "  SELECT in_rxcui FROM salt GROUP BY in_rxcui "
        "  HAVING COUNT(DISTINCT pin_rxcui) < 2)"
    )
    n = con.execute("SELECT COUNT(DISTINCT in_rxcui) FROM salt").fetchone()[0]
    print(f"  salt        {n:>7,} ingredients with 2+ marketed PIN salts")


# ---------------------------------------------------------------------- A7

def build_brand_ingredient(con: sqlite3.Connection) -> None:
    pairs: dict[tuple[str, str], list] = {}
    for tty, string in con.execute(
        "SELECT tty, str FROM product WHERE tty='SBD'"
    ):
        m = _BRACKETED.search(string)
        if not m:
            continue
        brand = m.group(1).strip()
        ing = _ingredient_head(string)
        if not ing:
            continue
        bk = normalize(brand).key
        ik = normalize(ing).salt_key
        if not bk or not ik:
            continue
        row = pairs.setdefault((bk, ik), [brand, ing, 0])
        row[2] += 1
    con.executemany(
        "INSERT INTO brand_ingredient VALUES (?,?,?,?,?)",
        [(bk, v[0], ik, v[1], v[2]) for (bk, ik), v in pairs.items()],
    )
    print(f"  brand_ingredient {len(pairs):>4,} brand->ingredient pairs")


# --------------------------------------------------------------------------

def read_release() -> str:
    """`source_release`, read off the release readme — never hardcoded.

    TOOLS.md calls this archive "09012026"; that is the **file mtime** inside
    the zip. The release itself is 09/08/2026, which is what the readme says
    and what a provenance line has to carry. Logged as a deviation in PLAN.md.
    """
    for d in (REPO / "rrf", REPO / "rrf" / "..", Path.home() / "vn-shared" /
              "rxnorm_release"):
        for readme in sorted(Path(d).glob("Readme_Full_Prescribe_*.txt")):
            m = re.search(r"(\d{8})", readme.name)
            if m:
                return m.group(1)
    raise FileNotFoundError(
        "no Readme_Full_Prescribe_*.txt found; source_release must come from "
        "the release, so refusing to guess"
    )


def main() -> int:
    DB_PATH.parent.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    release = read_release()
    print(f"building {DB_PATH.relative_to(REPO)} from RxNorm {release}")

    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    con.execute("INSERT INTO meta VALUES ('source_release', ?)", (release,))
    con.execute("INSERT INTO meta VALUES ('source', 'RxNorm Current Prescribable')")

    forms = collect_dose_forms()
    print(f"  dose forms  {len(forms):>7,}")
    load_conso(con, forms)
    load_sat(con)
    build_frequency(con)
    build_salt_table(con)
    build_brand_ingredient(con)
    con.commit()

    n = con.execute("SELECT COUNT(*) FROM name_index").fetchone()[0]
    dosey = con.execute(
        "SELECT COUNT(*) FROM name_index WHERE str REGEXP_DOSE"
    ).fetchone()[0] if False else sum(
        1 for (s,) in con.execute("SELECT str FROM name_index") if has_dose(s)
    )
    con.close()

    ok = True
    if n != EXPECTED_NAME_INDEX_ROWS:
        print(f"  WARN name_index is {n:,}, A3.5 expects "
              f"{EXPECTED_NAME_INDEX_ROWS:,}")
        ok = False
    # A3.5's acceptance: grepping the index for a dose pattern returns nothing.
    # IN/BN/PIN keep their 112 legitimate numeral-bearing names, so the check
    # is on SY/TMSY, which is where the filter runs.
    if dosey:
        by_tty = defaultdict(int)
        con = sqlite3.connect(DB_PATH)
        for tty, s in con.execute("SELECT tty, str FROM name_index"):
            if has_dose(s):
                by_tty[tty] += 1
        con.close()
        leaked = {t: c for t, c in by_tty.items() if t in NAME_TTYS_DOSE_FILTERED}
        print(f"  dose-bearing in index: {dict(by_tty)}"
              + ("  (all IN/BN/PIN — real names with numerals)" if not leaked else ""))
        if leaked:
            print(f"  FAIL SY/TMSY dose filter leaked: {leaked}")
            ok = False
    print("  OK" if ok else "  NOT OK")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
