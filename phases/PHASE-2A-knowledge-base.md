# Phase 2 · Track A — Knowledge base + deterministic tools

**Goal:** the three tools from D17, backed by RxNorm and openFDA.

**Blocked by:** nothing. **Start now** — RxNorm is already on disk, and this
track has **zero ML dependencies**, so a Phase 0 failure doesn't touch it.

Contracts: [../TOOLS.md](../TOOLS.md) §1–3.

---

## A1 — RXNCONSO → SQLite

Unzip; load `rrf/RXNCONSO.RRF`, filtered to `LAT='ENG'` and `SUPPRESS != 'Y'`.

**The gotcha that catches everyone once:** every RRF line ends with a trailing
`|`, so a naive `line.split('|')` produces a phantom empty final column and
misaligns every positional index past the last real field.

Only MySQL and Oracle load scripts ship. Write the SQLite loader.

**Done when:** ~246k rows queryable; TTY counts roughly match IN 5,844 /
BN 4,134 / SY 28,329 / TMSY 9,739 / PSN 21,305 / SCD 12,076 / SBD 8,079.

## A2 — RXNSAT `SPL_SET_ID` slice

Load only the `SPL_SET_ID` attribute rows from `rrf/RXNSAT.RRF` (283 MB file,
but you want a small slice: ~1.7M rows over 21,594 RxCUIs).

**Done when:** `rxcui → spl_set_id` is queryable.

## A3 — Normalization

One function, applied identically to index keys at build time and to queries
at lookup. **Any asymmetry produces misses you will never find.**

NFKD + strip diacritics → lowercase → strip leading articles (`the`, `your`)
→ drop punctuation except intra-word hyphens → collapse whitespace → strip
trailing dose fragments (numerals + `mg`/`milligram`/`mcg`/`ml`/`units`) →
strip trailing form words (`tablet`/`pill`/`capsule`).

Emit a **second, salt-stripped key**: remove `succinate`, `tartrate`,
`hydrochloride`/`hcl`, `sodium`, `maleate`, `besylate` — so a spoken
*"metoprolol succinate"* can also reach bare `metoprolol`.

Treat `ER`/`XR`/`SR`/`XL` the same: strip to base, keep the modifier.

> **The rationale here used to be backwards.** It claimed `IN` entries are
> often salt forms, so "metoprolol" would land `ambiguous` between two RXCUIs.
> Measured against this release: `metoprolol` **is** an `IN` (6918), and the
> salt forms are `PIN` — 221124 and 203191. So the salt-stripped key never
> fired and the ambiguity never appeared. A3.5 and A5.5 are the fix.

**Done when:** round-trip tests pass on a table of known variants.

## A3.5 — Fix the index composition · do this BEFORE A4

Counted off `RXNCONSO.RRF` (`LAT='ENG'`, `SUPPRESS != 'Y'`), matching
`\d+\s*(MG|ML|MCG|UNT|%|/)` case-insensitively:

| TTY | rows | dose-bearing | |
|---|---|---|---|
| `IN` | 5,844 | 42 | 0.7% |
| `BN` | 4,134 | 27 | 0.7% |
| `PIN` | 1,943 | 43 | 2.2% |
| **`SY`** | **28,329** | **25,427** | **89.8%** |
| **`TMSY`** | **9,739** | **6,468** | **66.4%** |
| **`PSN`** | **21,305** | **20,193** | **94.8%** |

Two things to change, and both are one predicate each:

**1. Filter `SY`/`TMSY` by that dose pattern.** A real `SY` row is
`metoprolol succinate 100 MG 24 HR Extended Release Oral Capsule` — an `SCD`
string wearing a different TTY. Unfiltered, they put 31,895 dose-bearing
strings into the index that exists specifically to keep dose *out* of name
matching. Since A6 rescores with Jaro-Winkler, which weights **prefix**
agreement, all of them score high against the bare ingredient and the margin
test returns `ambiguous` on drugs that should be trivial.

Apply the filter to `SY`/`TMSY` **only** — it would also drop 42 `IN`, 27 `BN`
and 43 `PIN` rows that are real names containing a numeral.

**2. Add `PIN`.** It was in neither index, and it is where salt forms live.
`PSN` goes to the *product* index despite its name — 94.8% of it carries a
dose.

Resulting spoken-name index: **18,094** strings.

    IN 5,844 + BN 4,134 + PIN 1,943 + SY 2,902 + TMSY 3,271

**Done when:** the built index has 18,094 rows and grepping it for
`\d+ *(MG|ML|MCG)` returns nothing.

## A4 — Indexes

Three, all precomputed at build time: exact hash, salt-stripped hash, and
**Double Metaphone**.

Double Metaphone, not Soundex — Soundex buckets are too lossy at 246k strings.

**Done when:** all three built and persisted over A3.5's 18,094 strings.

## A5 — Frequency prior

Count `SCD`/`SBD` products per ingredient. Widely prescribed drugs have many
marketed products, so product count is a serviceable prescribing-frequency
proxy — computable offline from data you already have.

**Do not skip this.** Without it, fuzzy matching ranks obscure entries above
obvious answers, and it reads as a broken matcher.

**Done when:** every ingredient has a score, and common drugs outrank obscure
ones on a spot check.

## A5.5 — The salt table

Precompute, offline, every `IN` concept having **two or more** distinct `PIN`
salt children. Measured against this release: **32 ingredients**, out of 5,844.
Metoprolol is one.

Why it matters, in one line: **succinate is extended-release once daily;
tartrate is immediate-release twice daily.** Same spoken word, different dosing
schedule. Without this table, *"metoprolol"* hits `IN` 6918 on A6's stage-1
exact lookup and returns `resolved` / `match_type="exact"` — a confident,
silent answer that buries the distinction.

With it:

- spoken *"metoprolol succinate"* → exact `PIN` hit. Specified. No flag.
- spoken *"metoprolol"* → exact `IN` hit, ingredient is on the table →
  `resolved`, `salt_unspecified=True`, both salts in `salt_candidates`.

Deliberately **not** `ambiguous`. The resolution succeeded — the ingredient
really is metoprolol and the clinician really did not say which salt. That is
A9's *"not specified is a finding, not a failure"* applied to a different
field.

32 of 5,844 means this fires rarely enough to mean something. It is one
`GROUP BY` at ingest.

**Done when:** the table has ~32 rows, bare `metoprolol` sets
`salt_unspecified`, and `metoprolol succinate` does not.

## A6 — `resolve_medication`

Staged, per TOOLS.md §1:

1. exact hash lookup → `match_type="exact"`, then **check A5.5's salt table
   and set `salt_unspecified`**
2. deterministic variants (salt-stripped, release-modifier-stripped)
3. **Double Metaphone candidate generation** — Whisper's errors are acoustic,
   not orthographic, so recall must be phonetic. This recovers
   `metropolol` → *metoprolol*
4. rescore: **Jaro-Winkler** (weights prefix agreement; drug names carry
   identity in the stem) + phonetic distance + token overlap + TTY prior +
   frequency prior
5. decide — **and test the margin, not just the threshold**

A mumbled "cele-" scores high against both *Celexa* (citalopram) and
*Celebrex* (celecoxib). Returning the winner confidently is the dangerous
behavior:

| Condition | Status |
|---|---|
| above threshold, clear margin over #2 | `resolved` |
| above threshold, #2 within margin | `ambiguous` — return both |
| nothing above threshold | `unresolved` |

**Done when:** the fixture's `metropolol` resolves with `match_type="fuzzy"`,
a deliberately ambiguous input returns two candidates rather than one, and bare
`metoprolol` comes back `resolved` **with `salt_unspecified=True`** rather than
a confident bare-ingredient answer.

## A7 — Brand → ingredient

`RXNREL` (198 MB) holds the authoritative `has_ingredient` / `tradename_of`
graph and v1 does not load it. Workaround: parse the bracketed brand out of
`SBD` strings — `metoprolol succinate 25 MG Extended Release Oral Tablet
[Toprol-XL]` — taking the leading text as the ingredient. ~8k rows.

Adequate for v1, fragile against format variation. Load `RXNREL` if brand
handling matters more than ingest time.

**Done when:** a brand name resolves to its ingredient on a spot check.

## A8 — openFDA → SQLite FTS5

**Blocked by 0d.** Stream the 14 zips, index the label text.

**Join on `SPL_SET_ID`, never on `openfda.rxcui`** — only ~64,660 of 262,883
records (~25%) carry an rxcui. Getting this wrong looks like a broken drug
lookup when it is a broken join.

Fields worth surfacing: `dosage_and_administration`, `drug_interactions`,
**`geriatric_use`**, `information_for_patients`, `spl_medguide`.

`geriatric_use` is the differentiator — public-domain, FDA-authoritative,
quotable text about dosing in patients over 65.

**Done when:** a resolved RxCUI returns its label text.

## A9 — `parse_sig` · no dependencies, start any time

A real grammar over sig language, per TOOLS.md §2.

**The distinction that matters most:** `not_specified` vs `unparseable`.
"Take as directed" is a complete, correct, *successful* parse whose finding is
that no dose exists. Reporting it as failure blames your tool for the
clinician's omission. This is D16's rule — "I couldn't hear it" and "your
doctor never said it" must never look the same — made concrete.

**Done when:** all four statuses are reachable, and `unparsed_remainder` is
populated on partials.

## A10 — `resolve_date` · no dependencies, start any time

Per TOOLS.md §3. The anchor is injected from `Session.visit_date` — **never a
model argument**, because the model doesn't know the date and would invent it.

Handle **past** direction: "you started that three months ago" is valid and
appears in real histories.

`display_string` carries **both** forms — *"three weeks from today, which is
Friday, October 9"* (from a visit on Friday, September 18, 2026) — because a
patient reading a bare date can't catch an error, and reading both lets them.

The old example read *Friday, October 10*; October 10, 2026 is a **Saturday**.
A wrong day-of-week is exactly what printing both forms is meant to let a
patient catch, so get your own examples right. Unit-test day-of-week, not just
the date.

**Done when:** all five statuses reachable, including `unanchored` for
"the week before your procedure".

## A11 — Cross-validation

Not the model's job — pipeline work, after A6 and A9 both run on one item:

- `dose_amount` + `dose_unit` vs `available_strengths` (a 250 mg dose of a
  drug sold only in 5 mg and 10 mg tablets is flagged)
- `dose_form` vs `dose_forms`
- `max_daily_amount` vs `frequency_per_day × dose_amount`
- two `parse_sig` results for one medication → **D16 category 7, blocking**

This is your knowledge base catching an error the model couldn't — the thesis
demonstrating itself. It is also the most likely thing to get cut for time.

**Done when:** a deliberately wrong strength in the fixture gets flagged.

---

## Track A is done when

- [ ] the spoken-name index is 18,094 rows with no dose-bearing strings (A3.5)
- [ ] `resolve_medication` handles exact, fuzzy and ambiguous correctly
- [ ] bare `metoprolol` returns `salt_unspecified=True` with both salts (A5.5)
- [ ] `parse_sig` distinguishes `not_specified` from `unparseable`
- [ ] `resolve_date` anchors to `visit_date` and handles past direction
- [ ] cross-validation flags the planted bad strength
- [ ] every tool returns its documented schema with provenance fields set
