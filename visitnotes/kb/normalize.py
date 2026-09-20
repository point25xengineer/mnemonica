"""A3 — normalization. One function, applied identically at build and at query.

**The invariant that makes the whole resolver work:** index keys and query
strings pass through the *same* code path. Any asymmetry — a build-time step
the query skips, or vice versa — produces misses that are almost impossible to
find later, because the index looks correct when you inspect it and the query
looks correct when you print it.

So there is exactly one public entry point, `normalize`, and `build.py` and
`resolve_medication.py` both call it. Nothing else normalizes anything.

Three keys come out of one input (`NormalizedName`):

- `key` — the primary spoken-name key
- `salt_key` — `key` with salt words removed, so spoken *"metoprolol
  succinate"* can also reach bare *metoprolol*
- `base_key` — `key` with a release modifier (ER/XR/SR/XL) removed, the
  modifier retained separately in `release_modifier`

The salt key is a *secondary* lookup (A6 stage 2), never the primary one. Per
A5.5 the interesting direction is the reverse: a bare `IN` hit whose ingredient
has two salt children is `resolved` + `salt_unspecified`, not `ambiguous`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

__all__ = ["normalize", "NormalizedName", "SALT_WORDS", "RELEASE_MODIFIERS",
           "DOSE_PATTERN", "has_dose"]


SALT_WORDS = (
    # A3 names these six explicitly.
    "succinate", "tartrate", "hydrochloride", "hcl", "sodium", "maleate",
    "besylate",
    # DEVIATION from A3, logged in PLAN.md. A3's six-word list is a subset of
    # the counter-ions RxNorm actually uses, and the gap is not cosmetic: with
    # six words the A5.5 salt join found **2** ingredients, not ~32, because
    # `paroxetine mesylate`, `hydroxyzine pamoate` and `diclofenac potassium`
    # never salt-stripped to their `IN`. The list below is the counter-ion
    # vocabulary measured off this release's `PIN` suffixes.
    #
    # Deliberately EXCLUDED, though they appear as PIN suffixes: hydration
    # states (`anhydrous`, `monohydrate`), formulation words (`liposomal`,
    # `lipid complex`) and source qualifiers (`human`, `equine`). None of
    # those is a salt, and treating them as one would flag `amphotericin b
    # liposomal` as a dosing ambiguity it is not.
    "dihydrochloride", "hydrobromide", "disodium", "potassium", "calcium",
    "magnesium", "sulfate", "bisulfate", "phosphate", "acetate", "mesylate",
    "bitartrate", "citrate", "fumarate", "chloride", "bromide", "nitrate",
    "tosylate", "pamoate", "lactate", "gluconate", "salicylate", "stearate",
    "valerate", "decanoate", "propionate", "carbonate", "oxalate", "malate",
    "aspartate", "saccharate", "benzoate", "napsylate", "edisylate",
    "xinafoate", "olamine", "strontium", "zinc", "tromethamine",
)
"""The counter-ions that turn an ingredient into a precise ingredient.

Only ever a *fallback* lookup (A6 stage 2), never the primary key — which is
what makes an over-broad entry survivable. `sodium chloride` is a drug, not a
salt form of one; stripping every token here would empty its key, and
`normalize` falls back to the primary key rather than emitting nothing.
"""

RELEASE_MODIFIERS = ("er", "xr", "sr", "xl", "cr", "la")

DOSE_PATTERN = re.compile(r"\d+\s*(?:MG|ML|MCG|UNT|%|/)", re.IGNORECASE)
"""A3.5's filter. A string matching this is a *product* string — it carries a
dose — and belongs in the product index, whatever TTY it claims to be."""

_LEADING_ARTICLES = ("the", "your", "my", "a", "an", "some")

_TRAILING_DOSE = re.compile(
    r"\s*\d+(?:\.\d+)?\s*(?:mg|milligrams?|mcg|micrograms?|ml|milliliters?|"
    r"g|grams?|units?|iu|mEq)\b\s*$",
    re.IGNORECASE,
)

_TRAILING_FORM = re.compile(
    r"(?:^|\s)(?:tablets?|pills?|capsules?|caps?|tabs?)\s*$", re.IGNORECASE
)
"""The leading `(?:^|\s)` is load-bearing. Without it the pattern matched the
`Tab` inside the brand name **Ery-Tab** and normalized it to `ery-` — a key
that indexes a real drug under a dangling hyphen and can never be looked up
again. A form word is a separate token, not a suffix."""


def has_dose(s: str) -> bool:
    """A3.5's predicate — does this string carry a dose? (`SY`/`TMSY` filter)"""
    return DOSE_PATTERN.search(s) is not None


@dataclass(frozen=True)
class NormalizedName:
    key: str
    salt_key: str
    base_key: str
    release_modifier: str | None

    def __bool__(self) -> bool:
        return bool(self.key)


def _strip_diacritics(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


def _drop_punctuation(s: str) -> str:
    """Punctuation goes, except a hyphen with a word character on both sides.

    `Toprol-XL` must survive as `toprol-xl`; `metoprolol,` must not keep its
    comma. A blanket `[^\\w\\s]` removal would fuse `Toprol-XL` into `toprolxl`
    and a blanket hyphen-to-space would split a real brand name in two.
    """
    s = re.sub(r"(?<=\w)-(?=\w)", "\x00", s)     # protect intra-word hyphens
    s = re.sub(r"[^\w\s\x00]", " ", s)
    return s.replace("\x00", "-")


def normalize(raw: str) -> NormalizedName:
    """The one normalizer. Build time and query time both call this."""
    s = _strip_diacritics(raw).lower()
    s = _drop_punctuation(s)
    s = re.sub(r"\s+", " ", s).strip()

    tokens = s.split()
    while tokens and tokens[0] in _LEADING_ARTICLES:
        tokens.pop(0)
    s = " ".join(tokens)

    # Trailing dose then trailing form, and repeat: "50 mg tablet" needs the
    # form stripped before the dose is at the end.
    for _ in range(3):
        before = s
        s = _TRAILING_FORM.sub("", s)
        s = _TRAILING_DOSE.sub("", s)
        s = s.strip()
        if not s:
            # Stripping must never consume the whole name: `Tabs` is a real
            # product name, and an empty key matches nothing forever.
            s = before
            break
        if s == before:
            break

    key = re.sub(r"\s+", " ", s).strip()

    tokens = key.split()
    salt_tokens = [t for t in tokens if t not in SALT_WORDS]
    # Never let salt-stripping empty the name: "sodium chloride" minus sodium
    # is still a drug, but bare "hcl" alone is not a mention worth a key.
    salt_key = " ".join(salt_tokens) if salt_tokens else key

    modifier = None
    base_tokens = list(tokens)
    if len(base_tokens) > 1 and base_tokens[-1] in RELEASE_MODIFIERS:
        modifier = base_tokens.pop()
    elif len(base_tokens) >= 1 and "-" in base_tokens[-1]:
        head, _, tail = base_tokens[-1].rpartition("-")
        if tail in RELEASE_MODIFIERS and head:
            modifier = tail
            base_tokens[-1] = head
    base_key = " ".join(base_tokens)

    return NormalizedName(
        key=key, salt_key=salt_key, base_key=base_key, release_modifier=modifier
    )
