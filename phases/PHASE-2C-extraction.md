# Phase 2 · Track C — Extraction + verification

**Goal:** turn a `Session` into verified, disposition-tagged fields — with
fabrication structurally impossible.

**Blocked by:** contract 1a and fixture 1c. **Not blocked by Track B.**

Contracts: [../TOOLS.md](../TOOLS.md) §4–5.

---

## C1 — Schemas

`VisitExtraction` and its nested tool calls, per TOOLS.md §4.

The rule that makes it work: **every field is either a verbatim quote, a
closed enum, or a nested tool call whose own fields are verbatim quotes.
There is no free-text field anywhere in the schema.** That is D12 expressed
structurally rather than asserted.

Note what the tool-call models deliberately *omit*:

- `parse_sig` takes no `drug_rxcui` — the model never saw `resolve_medication`'s
  output, because there is no feedback loop
- `parse_sig` takes no `speaker_role` — the runtime knows it from diarization;
  if the model supplied it, D19's dose rule would rest on the model's claim
  about who was talking
- `resolve_date` takes no anchor date — the runtime injects `visit_date`

The model can only pass arguments it can literally see in the transcript.

**Done when:** `VisitExtraction` validates, and a grep for `str` fields that
aren't quotes or enums returns nothing.

## C2 — xgrammar

`mlx-lm` has **no** built-in constrained decoding — verified by source
inspection. Its only JSON story is post-hoc parsing, with open correctness
bugs. xgrammar is what makes D13's first guarantee real.

```python
from xgrammar import GrammarCompiler, TokenizerInfo
from xgrammar.contrib.mlxlm import XGrammarLogitsProcessor

grammar = compiler.compile_json_schema(VisitExtraction, strict_mode=True)
out = mlx_lm.generate(model, tok, prompt,
                      logits_processors=[XGrammarLogitsProcessor(grammar)])
```

xgrammar ships a Metal bitmask kernel for MLX and an official mlx-lm contrib
integration. Do **not** route this through Ollama — on >32 GB machines it
defaults to its MLX engine, which has a documented history of *silently
ignoring* the `format` schema.

**Known unmeasured cost:** the processor round-trips the bitmask through
`numpy()` → `mx.array` each token, which is a CPU↔GPU hop per step. If decode
feels slow, that's the first place to look.

### GATE C2 — do this in your first hour

Compile the **real** schema before you write a prompt, load a model, or read
the fixture:

```python
compiler.compile_json_schema(VisitExtraction, strict_mode=True)
```

It needs nothing else, and it is the only assumption in the build that can kill
an entire track. `VisitExtraction` is nested Pydantic, so it emits `$defs` and
`$ref`; `strict_mode` is particular; the cp314 wheel is days old. Also check
that an **empty** result is reachable — a turn with nothing in it must be able
to produce empty lists, or constrained decoding will force the model to invent
something to satisfy the grammar.

**Pass:** it compiles, and a no-content turn yields all-empty lists.
**Fail:** post-hoc `json.loads` + one reparse retry. You lose D13's *first*
guarantee — well-formedness — and keep the second. Span verification is what
makes the output true; the grammar only makes it parseable. Degraded and
honest, exactly like gate 0g. Record the result in PLAN.md either way.

**Done when:** the real schema compiles (or the fallback is in place and
logged), and malformed JSON is impossible — try to provoke it and fail.

## C3 — Extraction prompt · GATE

Chunk **by speaker turn**, not by token window (D15). Less drift, attribution
free from the chunk's own label, and a failed extraction isolated to one turn
instead of poisoning a batch. It also makes transcript length irrelevant.

The prompt's whole job is the verbatim rule. From TOOLS.md §0:

> Pass text exactly as it appears in the transcript. Not corrected, not
> normalized, not expanded. If the transcript says `metropolol`, the argument
> is `metropolol`.

Reassure the model that this is safe — tell it the resolver matches
phonetically and reports its corrections, so it has no reason to "help".

**GATE:** develop on `mlx-community/Qwen3.5-9B-4bit` (5.98 GB) and measure
verbatim quote fidelity against the fixture. If quotes come back subtly
paraphrased, escalate:

1. 8-bit 9B (~10 GB) — **test this first.** Quantization noise degrades
   verbatim copying harder than it degrades reasoning, so 8-bit 9B may beat
   4-bit 27B for exact reproduction
2. `mlx-community/Qwen3.6-35B-A3B-4bit` (20.43 GB, ~65–85 tok/s MoE)
3. `mlx-community/Qwen3.8-27B-4bit` (16.08 GB, ~25–35 tok/s dense) as a
   quality reference

The MoE is 2–3× faster than the dense model because only ~3B params are
active, which matters against D9's 60-second budget.

**Done when:** extraction on the fixture produces quotes that pass C4 at a
rate you're willing to state out loud.

## C4 — Span verification

**The model does not emit character offsets. Your code computes them** (D14).

Models can't see character positions; asking for offsets means asking for
arithmetic on boundaries absent from their representation, and correct
extractions then fail your own verifier.

```
str.find(session.transcript_text, quote)
  1 match   → offsets assigned, accepted
  0 matches → FABRICATION → dropped silently, logged
  2+ matches → disambiguate by nearest turn
```

The zero-match case is D16 category 1. It never surfaces to the clinician,
never gets a badge, never gets a queue entry. The correct response to detected
fabrication is deletion, not disclosure.

The drop is **counted**, and the count reaches the UI (U3). The clinician
never sees the fabricated text — that part of "deletion, not disclosure" still
holds — but a silently deleted medication is indistinguishable from one the
model never found, and D9 collapses everything non-blocking, so an omission
would otherwise be invisible on a page that looks complete.

**Done when:** a deliberately fabricated quote is dropped, the drop count
increments, and a real one resolves to correct offsets.

## C4.5 — Association check · new, and it is the one nothing else covers

For each `MedicationItem`, compare the turn its `mention_quote` resolved to
against the turns its `sig`, `start_or_stop` and `change_evidence_quote`
resolved to. **Different turns → D16 category 8.**

This is the failure span verification structurally cannot see. The model can
take a genuine *"twice daily"* from drug A's turn and nest it under drug B —
every quote passes C4, every offset is real, and the action card is wrong. No
tool downstream can detect it, because nothing downstream knows what the
association was *supposed* to be. It is caught here by comparing offsets, or it
is not caught.

Not blocking: the common case is a sig and a mention sharing a turn, and
blocking that would spend D9's whole budget on the safe path. It is
**prefilled, flagged, and rendered expanded** with both quotes and both
timestamps (U3), so the clinician's eye lands on it without a keystroke.

**Done when:** the fixture's planted cross-turn case is flagged category 8, and
a same-turn medication is not.

## C5 — Dispositions

Assign across all **eight** D16 categories. The full table is SPEC.md D16; the
rules that matter most:

- **Categories 2/3/4 and 5/6/7 must never look the same.** "I couldn't hear
  it" and "your doctor never said it" are different facts. Collapsing them
  builds a system that blames itself for the doctor's omissions
- Only **two** blocking cases: ambiguous attribution on a dose, and internal
  contradiction. Everything else is glance-and-accept
- Category 6 (loose threads) is arguably your most valuable output — *"you
  told the patient you'd adjust the dose and never specified it"*
- Category 7: surface both values with both timestamps. Silently choosing the
  later one is a defensible heuristic and an indefensible product decision
- Category 8 (cross-turn association) renders **expanded**, never collapsed
- Category 2 now reads **segment-level** `no_speech_prob` and
  `compression_ratio`, not just per-word `probability` — Whisper's silence
  hallucinations are verifiable spans, so C4 cannot catch them
- **`change_kind` is derived, not trusted, wherever it can be.** Two parsed
  doses for one drug → `increased`/`decreased` is arithmetic; set
  `change_kind_derived=True` and print as fact. Otherwise it is prefilled and
  flagged. It is the verb of the headline sentence on the action card, and a
  closed enum guarantees well-formed, not correct

Thresholds get tuned in 3c, not here. Wire them as constants you can move.

**Done when:** running the fixture produces exactly the seven planted cases,
each in its correct disposition.

---

## Track C is done when

- [ ] malformed JSON is structurally impossible
- [ ] fabricated quotes are dropped silently
- [ ] offsets are computed, never model-supplied
- [ ] all eight D16 categories fire correctly on the fixture
- [ ] cross-turn association is detected (C4.5) and same-turn is not flagged
- [ ] the discarded count is exposed to the UI
- [ ] the chosen model is recorded, with the fidelity number that chose it
