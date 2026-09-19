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

**Done when:** malformed JSON is impossible — try to provoke it and fail.

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

**Done when:** a deliberately fabricated quote is dropped, and a real one
resolves to correct offsets.

## C5 — Dispositions

Assign across all seven D16 categories. The full table is SPEC.md D16; the
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

Thresholds get tuned in 3c, not here. Wire them as constants you can move.

**Done when:** running the fixture produces exactly the seven planted cases,
each in its correct disposition.

---

## Track C is done when

- [ ] malformed JSON is structurally impossible
- [ ] fabricated quotes are dropped silently
- [ ] offsets are computed, never model-supplied
- [ ] all seven D16 categories fire correctly on the fixture
- [ ] the chosen model is recorded, with the fidelity number that chose it
