"""One read-only handle on the built knowledge base.

Opened once per process and shared. The tools are pure functions of
(arguments, knowledge base); nothing here writes, and nothing here caches
across a rebuild — `build.py` deletes and recreates the file, so a stale
handle fails loudly rather than answering from a deleted page.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "rxnorm.db"

_BUILD_HINT = (
    "knowledge base not built. Run:\n"
    "    /Users/evancanty/vn-shared/.venv/bin/python -m mnemonica.kb.build"
)


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or DB_PATH
    if not p.exists():
        raise FileNotFoundError(f"{p}: {_BUILD_HINT}")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def source_release(con: sqlite3.Connection) -> str:
    row = con.execute(
        "SELECT value FROM meta WHERE key='source_release'"
    ).fetchone()
    if row is None:
        raise RuntimeError("meta.source_release missing — rebuild the KB")
    return row["value"]
