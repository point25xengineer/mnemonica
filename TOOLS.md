# Tool Contracts

Companion to [SPEC.md](SPEC.md). Defines the three deterministic tools from
**D17**, the exact arguments the model must supply, and what each returns.

---

## 0. Calling model

**Single-shot, no feedback loop.** The model emits tool invocations as part of
one xgrammar-constrained extraction (D23). It does **not** receive results and
cannot issue follow-up calls.

Why this matters:

- A model that reads a tool result can rationalize against it, retry until
  something passes, or narrate around a failure. Single-shot removes all three.
- **The model may only pass arguments it can see in the transcript.** It cannot
  pass an RxCUI to `parse_sig`, because no tool result ever reached it.
- Cross-tool linkage is **structural** — calls nest in the same extracted
  object — not model-decided.
- Values the runtime knows are **injected, never asked for**: the visit date
  (D18), the speaker role of the source turn (D19), the transcript itself.
  The model cannot hallucinate what it was never asked to supply.

```
         model                  pipeline                 tools
           |                        |                      |
   one constrained call             |                      |
   -> MedicationExtraction  ------> |                      |
      { mention_quote,              |-- resolve_medication -> RxNorm
        sig_quote,                  |-- parse_sig ---------> grammar
        followup_quote }            |-- resolve_date ------> anchor
           |                        |                      |
           |                 cross-validate <--------------+
           |                 map to D16 disposition
           |                        |
           X  (never returns)       v
                             template render
```

### The one rule that governs every argument

**Pass text exactly as it appears in the transcript.**

Not corrected. Not normalized. Not expanded. Not translated from brand to
generic. If the transcript says `metropolol`, the argument is `metropolol`.

This is not pedantry — it is the entire verification mechanism. D14 verifies
each argument by searching for it in the transcript. A model that "helpfully"
fixes a spelling produces a string that is not there, which is indistinguishable
from fabrication and is correctly dropped. Fixing mistranscriptions is
`resolve_medication`'s job, and it is good at it. The model's job is to point.

---

## 1. `resolve_medication`

### Description shown to the model

> Identify a medication the clinician mentioned and resolve it against the
> RxNorm drug database.
>
> Pass the drug name **exactly as it appears in the transcript**, including any
> apparent misspelling, mistranscription, or partial word. Do not correct it.
> Do not expand abbreviations. Do not substitute a generic name for a brand
> name or vice versa. Do not include the dose, form, or frequency — those
> belong to `parse_sig`.
>
> If the clinician refers to a drug without naming it ("your blood pressure
> pill"), pass that phrase verbatim; the resolver will report that it could not
> be identified, which is the correct outcome.
>
> You do not need to correct misheard drug names. The resolver matches
> phonetically and will recover the intended drug from a mistranscription far
> more reliably than a guess would — and it reports *that* it corrected
> something, which a silent guess cannot.

### Arguments

| Field | Type | Required | Description |
|---|---|---|---|
| `mention_quote` | `str` | yes | The drug name verbatim from the transcript. Must occur in the transcript exactly. |
| `context_quote` | `str` | no | The surrounding clause, verbatim, if it may disambiguate (e.g. distinguishing a drug from a condition of the same name). Must also occur verbatim. |

```python
class ResolveMedicationCall(BaseModel):
    mention_quote: str
    context_quote: str | None = None
```

Nothing else. No RxCUI, no normalized name, no guessed spelling — those are
outputs, and asking the model for them invites invention.

### Returns

```python
class MedicationResolution(BaseModel):
    status: Literal["resolved", "ambiguous", "unresolved"]

    # populated when status == "resolved"
    rxcui: str | None
    canonical_name: str | None        # RxNorm preferred name
    tty: str | None                   # IN | BN | PSN | SCD | SBD | SY | TMSY
    ingredients: list[str]            # normalized ingredient names
    brand_names: list[str]            # known brands for this ingredient
    is_brand: bool | None

    # how we got there — drives D16 disposition
    match_type: Literal["exact", "case_insensitive", "fuzzy", "none"]
    edit_distance: int | None         # > 0 implies possible mistranscription
    match_confidence: float           # 0.0 - 1.0

    # populated when status == "ambiguous"
    candidates: list[MedicationCandidate]   # ranked, each with rxcui + score

    # for the openFDA join (SPEC.md §4) — join on THIS, never on openfda.rxcui
    spl_set_ids: list[str]

    # for cross-validation against parse_sig
    available_strengths: list[str]    # RXN_AVAILABLE_STRENGTH
    dose_forms: list[str]

    # provenance for the citation chain
    source: Literal["RxNorm Current Prescribable"]
    source_release: str               # e.g. "09082026"
```

### Resolution algorithm

Two indexes, built once offline from `RXNCONSO.RRF` filtered to `LAT='ENG'` and
`SUPPRESS != 'Y'`.

**Spoken-name index** — what clinicians actually say, and the only index
searched for a name:

| TTY | Rows | Content |
|---|---|---|
| `IN` | 5,844 | ingredients — *metoprolol succinate* |
| `BN` | 4,134 | brand names — *Toprol-XL* |
| `SY` | 28,329 | synonyms |
| `TMSY` | 9,739 | tall-man synonyms |

**Product index** — `SCD` (12,076) + `SBD` (8,079), full strings like
*metoprolol succinate 25 MG Extended Release Oral Tablet*. Never searched for a
name; clinicians do not speak this way, which is precisely why dose lives in
`parse_sig`. Used for enrichment and cross-validation after a concept is known.

**Normalization** — one function, applied identically to index keys at build
time and to the query at lookup. Any asymmetry produces misses that are almost
impossible to find later.

    NFKD + strip diacritics -> lowercase -> strip leading articles ("the",
    "your") -> drop punctuation except intra-word hyphens -> collapse
    whitespace -> strip trailing dose fragments (numerals + mg/milligram/
    mcg/ml/units) -> strip trailing form words (tablet/pill/capsule)

Then emit a **second, salt-stripped key** with `succinate`, `tartrate`,
`hydrochloride`/`hcl`, `sodium`, `maleate`, `besylate` removed. RxNorm `IN`
entries are frequently salt forms, so "metoprolol" must be able to reach both
*metoprolol succinate* and *metoprolol tartrate* — which are different RXCUIs,
making this a genuine `ambiguous` result rather than something to resolve
silently. Treat `ER`/`XR`/`SR`/`XL` the same way: strip to base, retain the
modifier as a separate attribute.

**Staged match:**

1. **Exact hash lookup** on the normalized key. Most mentions land here.
   -> `match_type="exact"`.
2. **Deterministic variants** — retry with the salt-stripped and
   release-modifier-stripped keys. Still no scoring.
3. **Phonetic candidate generation.** The critical stage, and the reason it is
   phonetic: **Whisper's errors are acoustic, not orthographic — it mishears,
   it does not typo.** Precompute a **Double Metaphone** code for every index
   key at build time; at query time retrieve everything sharing the query's
   code. This is what recovers `metropolol` -> *metoprolol* and
   `hydroxyzine` <-> *hydralazine*. Use Double Metaphone, not Soundex — Soundex
   buckets are too lossy to be useful at 246k strings.
4. **Rescore** the few dozen candidates from steps 2–3 on a composite:
   - **Jaro-Winkler**, not plain Levenshtein — it weights prefix agreement, and
     drug names carry their identity in the stem
   - phonetic distance
   - token overlap for multi-word names
   - **TTY prior** — prefer `IN`/`BN` over `SY`/`TMSY`
   - **frequency prior** — count `SCD`/`SBD` products per ingredient. Widely
     prescribed drugs have many marketed products, so product count is a
     serviceable prescribing-frequency proxy, computable offline from data we
     already have. Without this prior, fuzzy matching over 246k strings will
     rank obscure entries above the obvious answer.
5. **Decide status — and test the margin, not just the threshold.** A mumbled
   "cele-" scores high against both *Celexa* (citalopram, antidepressant) and
   *Celebrex* (celecoxib, NSAID). Confidently returning the winner is exactly
   the dangerous behavior:

   | Condition | Status |
   |---|---|
   | above threshold, **clear margin** over #2 | `resolved` |
   | above threshold, #2 **within margin** | `ambiguous` — return both |
   | nothing above threshold | `unresolved` |

   Two thresholds. The margin one is the one that prevents harm.
6. **Enrich** from the RXCUI: `SPL_SET_ID` from `RXNSAT` for the openFDA join,
   plus `RXN_AVAILABLE_STRENGTH` and dose forms for §3 cross-validation.

   **Brand -> ingredient linkage caveat:** the authoritative
   `has_ingredient` / `tradename_of` graph lives in `RXNREL.RRF` (198 MB),
   which v1 does not load. Workaround: parse the bracketed brand out of `SBD`
   strings — `metoprolol succinate 25 MG Extended Release Oral Tablet
   [Toprol-XL]` — taking the leading text as the ingredient. ~8k rows, fast,
   adequate for v1, and fragile against format variation. Load `RXNREL` if
   brand handling matters more than ingest time.

### Upstream: bias Whisper with the drug list

Going local (D1) cost us ElevenLabs' `keyterms` priming, but Whisper's
`initial_prompt` is the analogue: seed it with the drugs most likely to appear
— the ~50 most commonly prescribed, or the ones in the demo script — and
Whisper produces correct spellings more often, so step 3 fires less often.

Prompt context is limited (~224 tokens), so this is a targeted bias, not the
whole vocabulary. It closes the same loop the sponsor API would have:
**the knowledge base does not just verify the transcript, it improves it.**

### Disposition mapping (D16)

| Result | Disposition |
|---|---|
| `resolved`, `match_type="exact"` | printed as fact |
| `resolved`, `match_type="fuzzy"`, `edit_distance <= 2` | prefilled + flagged — **likely mistranscription, show both heard and resolved** |
| `resolved`, `match_type="fuzzy"`, `edit_distance > 2` | prefilled + flagged, low confidence |
| `ambiguous` | prefilled + flagged, candidates offered for one-click pick |
| `unresolved` | **category 4** — prefilled with raw heard text + flagged |

The fuzzy-match case is worth surfacing prominently in the UI. "You said
*metropolol*, we matched *metoprolol*" is the resolver catching an ASR error,
which is a genuinely useful thing for a clinician to see and a good
demonstration that the knowledge base is doing work the model is not.

---

## 2. `parse_sig`

### Description shown to the model

> Capture a dosing instruction — how much of a medication to take, how often,
> and under what conditions.
>
> Pass the instruction **exactly as spoken**, verbatim from the transcript. Do
> not normalize it, do not convert words to numerals, do not infer a frequency
> that was not stated, and do not merge instructions said at different points
> in the conversation into one quote.
>
> If the clinician gave no specific instruction ("take it as directed", "same
> as before"), pass that phrase verbatim anyway. The parser will report that no
> dose was specified, which is a real finding and not an error.
>
> If the clinician stated **two different** instructions for the same drug,
> emit **two separate calls** with their respective quotes. Do not choose
> between them.

### Arguments

| Field | Type | Required | Description |
|---|---|---|---|
| `sig_quote` | `str` | yes | The dosing instruction verbatim. Must occur in the transcript exactly. |

```python
class ParseSigCall(BaseModel):
    sig_quote: str
```

Deliberately minimal. Note what is **absent** and why:

- **No `drug_rxcui`** — the model never saw `resolve_medication`'s output.
  Strength cross-validation happens in the pipeline.
- **No `speaker_role`** — the runtime knows which turn this came from via
  diarization. If the model supplied it, D19's dose-safety rule would depend on
  the model's claim about who was speaking, which defeats the point.

### Returns

```python
class SigParse(BaseModel):
    status: Literal["parsed", "partial", "unparseable", "not_specified"]

    dose_amount: float | None
    dose_unit: str | None             # mg | mL | tablet | puff | unit
    dose_form: str | None             # tablet | capsule | inhaler | patch
    route: str | None                 # oral | topical | inhaled | injection

    frequency_per_day: float | None   # 2.0 for "twice daily"
    interval_hours: float | None      # 8.0 for "every 8 hours"
    timing: list[str]                 # ["morning"] | ["night", "with food"]
    days_of_week: list[str] | None    # for weekly regimens

    prn: bool                         # as-needed
    prn_condition: str | None         # verbatim: "if the pain comes back"

    duration_days: int | None         # "for ten days"
    total_quantity: float | None
    max_daily_amount: float | None    # "no more than 4 in a day"

    # honesty fields
    unparsed_remainder: str | None    # text we could not account for
    normalized_sig: str | None        # canonical string for the template
    parse_confidence: float

    source: Literal["deterministic grammar"]
    grammar_version: str
```

### The status distinction that matters most

| Status | Means | Disposition |
|---|---|---|
| `parsed` | every component extracted | printed as fact |
| `partial` | some components found, `unparsed_remainder` non-empty | prefilled + flagged |
| **`not_specified`** | **no dose was stated in the audio** | **category 5 — "not specified", NOT an error** |
| `unparseable` | a dose appears to be present but the grammar failed | prefilled + flagged |

`not_specified` versus `unparseable` is the single most important distinction in
this tool, and it is the concrete instance of D16's rule that *"I could not
hear it"* and *"your doctor never said it"* must never look the same. "Take as
directed" is a complete, correct, successful parse whose finding is that no dose
exists. Reporting it as a failure would blame the tool for the clinician's
omission.

### Pipeline cross-validation (not the model's job)

After both tools run on the same extracted object:

- `dose_amount` + `dose_unit` checked against `available_strengths` from
  `resolve_medication`. A 250 mg dose of a drug available only in 5 mg and
  10 mg tablets is flagged.
- `dose_form` checked against `dose_forms`.
- `max_daily_amount` checked against `frequency_per_day * dose_amount` for
  internal consistency.
- Two `parse_sig` results for one medication -> **D16 category 7, blocking**,
  both shown with timestamps.

---

## 3. `resolve_date`

### Description shown to the model

> Capture a point in time the clinician referred to — a follow-up appointment,
> when to start or stop a medication, when a test is scheduled.
>
> Pass the time expression **exactly as spoken**, verbatim. Do not compute a
> date. Do not resolve "three weeks" into a calendar date. You do not know
> today's date and must not guess it — the resolver is given the visit date and
> will do the arithmetic.
>
> Include enough of the phrase to capture direction and reference point: prefer
> `"come back in three weeks"` over `"three weeks"`.
>
> If the expression depends on an event rather than the visit ("the week before
> your procedure"), pass it verbatim anyway. The resolver will report that it
> has no anchor, which is the correct outcome.

### Arguments

| Field | Type | Required | Description |
|---|---|---|---|
| `phrase_quote` | `str` | yes | The time expression verbatim. Must occur in the transcript exactly. |
| `event_kind` | `enum` | yes | What the date is *for*: `followup_visit`, `medication_start`, `medication_stop`, `test_scheduled`, `test_results`, `other`. |

```python
class ResolveDateCall(BaseModel):
    phrase_quote: str
    event_kind: Literal["followup_visit", "medication_start",
                        "medication_stop", "test_scheduled",
                        "test_results", "other"]
```

**No anchor date argument.** The runtime injects the session's visit date per
D18. This is the whole reason D18 exists as a persisted session field: if the
model supplied the anchor, every date would rest on a value it invented.

`event_kind` is the one genuinely interpretive argument in any of the three
tools — it is a classification, not a quote, so it cannot be span-verified. It
is deliberately a closed enum with an `other` escape so the failure mode is a
miscategorized date rather than an invented one.

### Returns

```python
class DateResolution(BaseModel):
    status: Literal["resolved", "resolved_range", "unanchored",
                    "unparseable", "not_a_date"]

    resolved_date: date | None
    range_start: date | None          # for "in a few weeks"
    range_end: date | None

    precision: Literal["exact_day", "week_of", "month", "vague"] | None
    direction: Literal["future", "past"] | None

    anchor_date: date                 # always echoed — the visit date (D18)
    anchor_source: Literal["session_visit_date"]

    original_phrase: str              # echoed verbatim
    display_string: str | None        # BOTH forms, per D18

    # for status == "unanchored"
    depends_on_event: str | None      # verbatim: "your procedure"

    resolution_confidence: float
    source: Literal["deterministic date resolver"]
```

`display_string` must carry **both** the resolved date and the original
phrasing, per D18:

> `"three weeks from today, which is Friday, October 10"`

An elderly patient reading a bare date has no way to catch an error. Reading
both lets them.

### Disposition mapping

| Result | Disposition |
|---|---|
| `resolved`, `precision="exact_day"` | printed as fact |
| `resolved_range` / `precision="vague"` | printed with the range stated honestly ("in the next few weeks") |
| `unanchored` | prefilled + flagged — clinician supplies the reference event date |
| `unparseable` | prefilled + flagged |
| `not_a_date` | dropped — the model misidentified a phrase |

Handle **past** direction correctly. "You started that three months ago" is a
valid, resolvable, backward-looking date and appears in real visit histories.

---

## 4. Composed extraction schema

The three tools do not appear as independent top-level calls. They nest inside
extraction objects, which is what makes the linkage structural rather than
model-decided (§0).

```python
class MedicationItem(BaseModel):
    """One medication discussed in the visit."""
    medication: ResolveMedicationCall
    sig: list[ParseSigCall]              # 0, 1, or 2+ (2+ -> D16 cat 7)
    start_or_stop: ResolveDateCall | None
    change_kind: Literal["new", "increased", "decreased",
                         "stopped", "continued", "unchanged"]
    change_evidence_quote: str            # verbatim support for change_kind

class AppointmentItem(BaseModel):
    when: ResolveDateCall
    purpose_quote: str                    # verbatim

class RedFlagItem(BaseModel):
    instruction_quote: str                # verbatim: "call us if the swelling spreads"

class LooseThreadItem(BaseModel):
    """D16 category 6 — raised and never resolved."""
    topic_quote: str                      # verbatim

class VisitExtraction(BaseModel):
    medications: list[MedicationItem]
    appointments: list[AppointmentItem]
    red_flags: list[RedFlagItem]
    loose_threads: list[LooseThreadItem]
    summary_quotes: SummarySelection       # D7 extractive summary
```

Compile with `compile_json_schema(VisitExtraction, strict_mode=True)` per D23.

Note that **every** field is either a verbatim quote (span-verifiable), a
closed enum, or a nested tool call whose own fields are verbatim quotes. There
is no free-text field anywhere in the schema. That is the structural expression
of the thesis in SPEC.md §1.

---

## 5. Verification order

For every extracted object, in this order. Any step failing sends the item to
its D16 disposition; nothing proceeds on unverified input.

1. **Span verification** — every `*_quote` field found in the transcript by
   search (D14). Zero matches -> dropped silently as fabrication.
2. **Offset assignment** — computed from the search result, never from the
   model.
3. **Turn attribution** — map offsets to the diarized turn; look up speaker
   role from the enrollment match (D20). A dose from a non-clinician turn ->
   D16 category 3, blocking (D19).
4. **Tool execution** — `resolve_medication`, `parse_sig`, `resolve_date` run
   on their verified arguments.
5. **Cross-validation** — strength/form consistency, duplicate sig detection.
6. **Disposition** — assign from the D16 table.
7. **Render** — templated action card, extractive summary (D7). Only items
   printed as fact or clinician-resolved reach the page.

---

## 6. What none of these tools do

- **No drug-drug interaction checking.** Deliberate; see SPEC.md §6 for why the
  free data makes it irresponsible.
- **No clinical judgment.** No tool decides whether a dose is appropriate, only
  whether it is internally consistent and consistent with available strengths.
- **No inference across turns.** A tool sees one verbatim quote. Connecting a
  drug named at 2:10 to a dose stated at 9:40 is the model's structural job via
  `MedicationItem`, and the clinician confirms it.
- **No writing.** No tool returns patient-facing prose. Templates do that (D7).
