"""A8 — openFDA drug labels into SQLite FTS5. Blocked by 0d (the 14 zips).

    /Users/evancanty/vn-shared/.venv/bin/python -m mnemonica.kb.openfda

**Join on `SPL_SET_ID`, never on `openfda.rxcui`.** Only ~64,660 of 262,883
label records carry an rxcui — about a quarter. Joining on it drops three
quarters of the labels, and it drops them *invisibly*: the lookup returns
nothing and looks exactly like a drug the FDA has no label for. RxNorm's
`RXNSAT` gives `rxcui -> spl_set_id` for 21,594 concepts (A2), and every label
record carries its own `spl_set_id`, so that is the join that works.

`geriatric_use` is the field worth having. It is public-domain,
FDA-authoritative, quotable text about dosing in patients over 65 — which is
the population this whole project is for — and no model wrote it.

The label text is stored in a separate database from RxNorm. It is ~1.8 GB of
source JSON and rebuilding it should not mean rebuilding the drug index.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OPENFDA_DIR = REPO / "openfda"
LABEL_DB = REPO / "data" / "openfda_labels.db"

FIELDS = (
    "dosage_and_administration",
    "drug_interactions",
    "geriatric_use",
    "information_for_patients",
    "spl_medguide",
)
"""What we surface. Not the whole label: a full record is tens of kilobytes of
`clinical_pharmacology` that nobody reading a visit summary wants, and FTS5
over all of it makes every query match everything."""

SCHEMA = """
CREATE TABLE label (
    spl_set_id TEXT NOT NULL,
    brand_name TEXT,
    generic_name TEXT,
    effective_time TEXT
);
CREATE INDEX ix_label_set ON label(spl_set_id);

CREATE VIRTUAL TABLE label_text USING fts5(
    spl_set_id UNINDEXED,
    field UNINDEXED,
    body,
    tokenize = 'porter unicode61'
);
"""


# ------------------------------------------------------------------- lookup

class LabelKB:
    """Read side of A8 — what a resolved RxCUI's label actually says.

    Takes `spl_set_ids` straight off a `MedicationResolution`, which is where
    `resolve_medication` put them (RxNorm `RXNSAT`), so the join never touches
    `openfda.rxcui`.
    """

    def __init__(self, path: Path | None = None) -> None:
        p = path or LABEL_DB
        if not p.exists():
            raise FileNotFoundError(
                f"{p}: openFDA index not built. Run:\n"
                f"    /Users/evancanty/vn-shared/.venv/bin/python "
                f"-m mnemonica.kb.openfda")
        self.con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        self.con.row_factory = sqlite3.Row

    def sections(self, spl_set_ids: list[str], field: str | None = None,
                 limit: int = 5) -> list[sqlite3.Row]:
        if not spl_set_ids:
            return []
        marks = ",".join("?" * len(spl_set_ids))
        sql = (f"SELECT spl_set_id, field, body FROM label_text "
               f"WHERE spl_set_id IN ({marks})")
        args = list(spl_set_ids)
        if field:
            sql += " AND field = ?"
            args.append(field)
        sql += f" LIMIT {int(limit)}"
        return self.con.execute(sql, args).fetchall()

    def geriatric_use(self, spl_set_ids: list[str]) -> str | None:
        """The differentiator: FDA-authoritative, public-domain, quotable text
        on dosing over 65 — for the exact population this is built for."""
        rows = self.sections(spl_set_ids, "geriatric_use", limit=1)
        return rows[0]["body"] if rows else None

    def search(self, query: str, limit: int = 10) -> list[sqlite3.Row]:
        """Full-text search across the indexed sections."""
        return self.con.execute(
            "SELECT spl_set_id, field, snippet(label_text, 2, '[', ']', '…', 20) "
            "AS snip FROM label_text WHERE label_text MATCH ? LIMIT ?",
            (query, limit)).fetchall()


def _labels():
    for zpath in sorted(OPENFDA_DIR.glob("drug-label-*.json.zip")):
        with zipfile.ZipFile(zpath) as z:
            for name in z.namelist():
                with z.open(name) as fh:
                    payload = json.load(fh)
        yield zpath.name, payload.get("results", [])


def main() -> int:
    if not OPENFDA_DIR.exists():
        print(f"{OPENFDA_DIR} missing — A8 is blocked by 0d")
        return 1
    LABEL_DB.parent.mkdir(exist_ok=True)
    if LABEL_DB.exists():
        LABEL_DB.unlink()

    con = sqlite3.connect(LABEL_DB)
    con.executescript(SCHEMA)

    total = with_text = with_rxcui = 0
    for fname, results in _labels():
        meta_rows, text_rows = [], []
        for rec in results:
            total += 1
            ofda = rec.get("openfda") or {}
            set_ids = ofda.get("spl_set_id") or (
                [rec["set_id"]] if rec.get("set_id") else [])
            if not set_ids:
                continue
            set_id = set_ids[0]
            if ofda.get("rxcui"):
                with_rxcui += 1
            meta_rows.append((
                set_id,
                "; ".join(ofda.get("brand_name") or [])[:200] or None,
                "; ".join(ofda.get("generic_name") or [])[:200] or None,
                rec.get("effective_time"),
            ))
            had = False
            for field in FIELDS:
                value = rec.get(field)
                if not value:
                    continue
                body = " ".join(value) if isinstance(value, list) else str(value)
                text_rows.append((set_id, field, body))
                had = True
            with_text += had
        con.executemany("INSERT INTO label VALUES (?,?,?,?)", meta_rows)
        con.executemany("INSERT INTO label_text VALUES (?,?,?)", text_rows)
        con.commit()
        print(f"  {fname}  +{len(meta_rows):,} labels  +{len(text_rows):,} sections")

    con.execute("INSERT INTO label_text(label_text) VALUES ('optimize')")
    con.commit()
    con.close()
    pct = 100 * with_rxcui / max(1, total)
    print(f"  {total:,} records, {with_text:,} with indexed text")
    print(f"  {with_rxcui:,} carry an openfda.rxcui ({pct:.0f}%) — which is "
          f"why the join is on SPL_SET_ID")
    print(f"  {LABEL_DB.relative_to(REPO)}  "
          f"{LABEL_DB.stat().st_size / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
