"""Track A's knowledge-base acceptance criteria, as tests.

The numbers here are not decoration. A3.5's whole argument is that an index
of 18,094 strings behaves differently from an index of 48,046, and the
difference is invisible from the outside: a flooded index looks exactly like a
badly tuned margin threshold (Phase 3c warns about precisely this confusion).
So the shape of the index is asserted, not eyeballed.

These skip rather than fail when `data/rxnorm.db` is absent — the database is
built from 500 MB of RRF that is gitignored, so a fresh clone cannot have one
until `python -m visitnotes.kb.build` has run.
"""

import re

import pytest

from visitnotes.kb import db
from visitnotes.kb.normalize import has_dose, normalize

pytestmark = pytest.mark.skipif(
    not db.DB_PATH.exists(),
    reason="knowledge base not built — run python -m visitnotes.kb.build",
)


@pytest.fixture(scope="module")
def con():
    c = db.connect()
    yield c
    c.close()


# ------------------------------------------------------------------- A1 / A2

def test_a1_row_count(con):
    """~246k ENG, non-suppressed concepts."""
    n = con.execute("SELECT COUNT(*) FROM concept").fetchone()[0]
    assert 240_000 < n < 255_000, n


@pytest.mark.parametrize("tty,expected", [
    ("IN", 5844), ("BN", 4134), ("PIN", 1943), ("SY", 28329),
    ("TMSY", 9739), ("PSN", 21305), ("SCD", 12076), ("SBD", 8079),
])
def test_a1_tty_counts(con, tty, expected):
    n = con.execute("SELECT COUNT(*) FROM concept WHERE tty=?", (tty,)).fetchone()[0]
    assert n == expected


def test_a2_spl_slice(con):
    rxcuis = con.execute("SELECT COUNT(DISTINCT rxcui) FROM spl").fetchone()[0]
    assert rxcuis == 21_594


def test_source_release_is_read_not_hardcoded(con):
    """Provenance comes off the release readme.

    TOOLS.md calls this archive "09012026" — that is the mtime of the files
    inside the zip. The release is 09/08/2026, which is what the readme says
    and what belongs on a citation.
    """
    assert db.source_release(con) == "09082026"


# ------------------------------------------------------------------- A3 / A4

@pytest.mark.parametrize("raw,key", [
    ("Metoprolol Succinate", "metoprolol succinate"),
    ("METOPROLOL", "metoprolol"),
    ("the metoprolol 50 mg tablet", "metoprolol"),
    ("your lisinopril", "lisinopril"),
    ("Toprol-XL", "toprol-xl"),
    ("  spaced   out  ", "spaced out"),
])
def test_a3_normalization(raw, key):
    assert normalize(raw).key == key


def test_a3_intra_word_hyphen_survives():
    """`Toprol-XL` must not fuse to `toprolxl` nor split into two tokens."""
    n = normalize("Toprol-XL")
    assert n.key == "toprol-xl"
    assert n.base_key == "toprol" and n.release_modifier == "xl"


def test_a3_salt_key_never_empty():
    """Stripping every token of `sodium chloride` would leave nothing; the
    salt key falls back rather than emitting a key that matches everything."""
    assert normalize("sodium chloride").salt_key == "sodium chloride"


def test_a3_form_strip_does_not_eat_brand_names():
    """`Ery-Tab` normalized to `ery-` until the form pattern required a token
    boundary — a real drug indexed under a dangling hyphen."""
    assert normalize("Ery-Tab").key == "ery-tab"


def test_a3_is_symmetric_build_and_query(con):
    """The invariant the whole resolver rests on: re-normalizing a stored key
    is a no-op. An asymmetry here produces misses nobody can find."""
    rows = con.execute(
        "SELECT str, key FROM name_index ORDER BY rowid LIMIT 3000").fetchall()
    bad = [(r["str"], r["key"]) for r in rows
           if normalize(r["key"]).key != r["key"]]
    assert not bad, bad[:5]


def test_a4_indexes_are_populated(con):
    row = con.execute(
        "SELECT COUNT(*) n, COUNT(DISTINCT key) k, COUNT(DISTINCT dmeta1) d "
        "FROM name_index").fetchone()
    assert row["n"] == 18_094
    assert row["k"] > 10_000 and row["d"] > 5_000


# ----------------------------------------------------------------------- A3.5

def test_a35_index_size(con):
    assert con.execute("SELECT COUNT(*) FROM name_index").fetchone()[0] == 18_094


def test_a35_no_dose_bearing_sy_or_tmsy(con):
    """The filter's acceptance criterion. Applied to `SY`/`TMSY` only — it
    would also drop 42 `IN`, 27 `BN` and 43 `PIN` rows that are real names
    containing a numeral."""
    leaked = [r["str"] for r in con.execute(
        "SELECT str FROM name_index WHERE tty IN ('SY','TMSY')")
        if has_dose(r["str"])]
    assert not leaked, leaked[:5]


def test_a35_legitimate_numeral_names_are_kept(con):
    counts = {tty: sum(1 for r in con.execute(
        "SELECT str FROM name_index WHERE tty=?", (tty,)) if has_dose(r["str"]))
        for tty in ("IN", "BN", "PIN")}
    assert counts == {"IN": 42, "BN": 27, "PIN": 43}


def test_a35_pin_is_present(con):
    """`PIN` was in neither index in the original design, and it is where salt
    forms live — which is how the demo's hero drug returned a confident bare
    ingredient with both salts unreachable."""
    rows = {r["rxcui"] for r in con.execute(
        "SELECT rxcui FROM name_index WHERE key LIKE 'metoprolol %'")}
    assert {"221124", "203191"} <= rows


# ------------------------------------------------------------------------- A5

def test_a5_frequency_prior_ranks_common_over_obscure(con):
    def count(key):
        row = con.execute(
            "SELECT product_count FROM ingredient_freq WHERE ingredient_key=?",
            (key,)).fetchone()
        return row["product_count"] if row else 0

    assert count("metoprolol") > count("pitavastatin")
    assert count("lisinopril") > count("levamisole")
    assert count("aspirin") > 20


# ----------------------------------------------------------------------- A5.5

def test_a55_salt_table_is_small_and_specific(con):
    """Rare enough to mean something. A5.5 estimated ~32 of 5,844; the
    marketed-salt filter lands at 20. Either way the point is the order of
    magnitude — a table of hundreds would be noise, not a finding."""
    n = con.execute("SELECT COUNT(DISTINCT in_rxcui) FROM salt").fetchone()[0]
    assert 10 <= n <= 60, n


def test_a55_metoprolol_is_on_the_table(con):
    salts = {r["pin_name"] for r in con.execute(
        "SELECT pin_name FROM salt WHERE in_rxcui='6918'")}
    assert salts == {"metoprolol succinate", "metoprolol tartrate"}


def test_a55_excludes_hydration_states(con):
    """*X anhydrous* vs *X monohydrate* is not two dosing schedules."""
    names = " ".join(r["pin_name"] for r in con.execute(
        "SELECT pin_name FROM salt")).lower()
    assert "anhydrous" not in names and "monohydrate" not in names


# ------------------------------------------------------------------------- A7

def test_a7_brand_resolves_to_ingredient(con):
    """The bracket in this release reads `[Toprol]`, not `[Toprol-XL]` — worth
    pinning, because A7 is a string parse over a format that varies and the
    spec's own example uses the other spelling."""
    row = con.execute(
        "SELECT ingredient_name FROM brand_ingredient WHERE brand_key='toprol'"
    ).fetchone()
    assert row and "metoprolol" in row["ingredient_name"].lower()


def test_a7_release_rate_prefix_is_stripped(con):
    """RxNorm writes `24 HR metoprolol succinate 25 MG ...`. Left in, the
    ingredient head of every extended-release product is `24 hr <drug>` —
    a key nothing looks up."""
    bad = con.execute(
        "SELECT COUNT(*) FROM product WHERE ingredient_key LIKE '%hr %' "
        "AND ingredient_key GLOB '[0-9]*'").fetchone()[0]
    assert bad == 0
