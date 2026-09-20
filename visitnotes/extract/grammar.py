"""C2 — xgrammar constrained decoding on MLX. D23, TOOLS.md §4.

`mlx-lm` 0.31.3 has no constrained decoding of its own; its only JSON story is
post-hoc parsing. xgrammar is what makes D13's *first* guarantee real — output
that is schema-conformant by construction rather than by inspection.

**`xgrammar.contrib.mlxlm` does not import on this build.** It reaches for
`xgrammar.kernels.apply_token_bitmask_inplace_kernels`, which 0.2.7 does not
export, so the "official mlx-lm integration" the spec counted on is a dead
path here. `xgr.apply_token_bitmask_inplace` itself is no help either: it reads
`logits.device` and dies with `AttributeError` on an mlx array, because it is
torch-only.

So the mask is applied by hand, and the three traps found at 0i are all in
these twenty lines:

1. The bitmask is packed int32. Unpack it with
   `np.unpackbits(..., bitorder="little")`, not by bit-twiddling in mlx.
2. It unpacks to the **tokenizer's** vocabulary (248,096 here) while mlx logits
   are padded wider (248,320). Pad the mask with zeros, or every generation
   dies on a broadcast error.
3. `GrammarMatcher` **raises** once it has accepted the stop token and you ask
   it to fill another mask. Guard with `is_terminated()` — without it,
   generation blows up immediately after the JSON closes, which looks like a
   grammar failure and is not.

Fallback, per D23: if a schema will not compile, post-hoc `json.loads` plus one
reparse retry. We lose well-formedness and keep span verification, which is the
guarantee that makes the output *true* rather than merely parseable.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "GrammarCache", "MLXGrammarProcessor", "compile_schema",
    "grammar_available",
]


def grammar_available() -> bool:
    """Is constrained decoding usable at all? D23's fallback hinges on this."""
    try:
        import xgrammar  # noqa: F401
    except Exception:  # noqa: BLE001 — absence is the answer, not a crash
        return False
    return True


def _huggingface_tokenizer(tokenizer):
    """`TokenizerInfo.from_huggingface` type-checks, and the check is strict.

    It rejects mlx-lm's `TokenizerWrapper` — it wants the transformers
    tokenizer inside — and it also rejects the raw `tokenizers.Tokenizer` one
    layer further in, which is what transformers 5's backend holds. So walk
    the `_tokenizer` chain and take the first layer xgrammar will accept,
    rather than hardcoding a depth that changes with a dependency bump.
    """
    import xgrammar as xgr

    seen, node = [], tokenizer
    while node is not None:
        seen.append(type(node).__name__)
        try:
            xgr.TokenizerInfo.from_huggingface(node)
            return node
        except ValueError:
            node = getattr(node, "_tokenizer", None)
    raise TypeError(
        "no layer of this tokenizer is one xgrammar accepts: "
        + " -> ".join(seen)
    )


class GrammarCache:
    """Compiles once per (tokenizer, schema) and hands out fresh matchers.

    Compilation is the expensive half and it is identical for every turn;
    matchers are cheap and must be per-generation, because a matcher carries
    the state of one JSON document."""

    def __init__(self, tokenizer, vocab_size: int | None = None):
        import xgrammar as xgr

        self._xgr = xgr
        self.tokenizer_info = xgr.TokenizerInfo.from_huggingface(
            _huggingface_tokenizer(tokenizer), vocab_size=vocab_size
        )
        self.compiler = xgr.GrammarCompiler(self.tokenizer_info)
        self._compiled: dict[str, object] = {}

    def compile(self, schema: type) -> object:
        key = schema.__name__
        if key not in self._compiled:
            self._compiled[key] = self.compiler.compile_json_schema(
                schema, strict_mode=True
            )
        return self._compiled[key]

    def processor(self, schema: type) -> MLXGrammarProcessor:
        return MLXGrammarProcessor(
            self._xgr, self.compile(schema), self.tokenizer_info.vocab_size
        )


class MLXGrammarProcessor:
    """An `mlx_lm` logits processor: `(tokens, logits) -> logits`.

    One instance per generation. `tokens` arrives as the running history —
    growing by one per step and starting with the final prompt token — so the
    first call has nothing to accept and every later call accepts exactly the
    tokens that appeared since it last ran.
    """

    def __init__(self, xgr, compiled, vocab_size: int):
        self._xgr = xgr
        self.matcher = xgr.GrammarMatcher(compiled)
        self.vocab_size = vocab_size
        self.bitmask = xgr.allocate_token_bitmask(1, vocab_size)
        self._seen: int | None = None
        self.rejected = 0
        """How many times the grammar had to veto the model's first choice —
        kept as a cheap sanity signal, not a metric anyone tunes."""

    def __call__(self, tokens, logits):
        import mlx.core as mx

        if self._seen is None:
            # First call: `tokens` is the tail of the prompt, not output.
            self._seen = int(tokens.size)
        else:
            for tok in np.asarray(tokens[self._seen:]).reshape(-1).tolist():
                if self.matcher.is_terminated():
                    break
                if not self.matcher.accept_token(int(tok)):
                    self.rejected += 1
            self._seen = int(tokens.size)

        if self.matcher.is_terminated():
            # Trap 3: filling a mask after the stop token raises.
            return logits

        self.matcher.fill_next_token_bitmask(self.bitmask)
        bits = np.unpackbits(
            np.asarray(self.bitmask).view(np.uint8), bitorder="little"
        )[: self.vocab_size]
        width = logits.shape[-1]
        if bits.size < width:
            # Trap 2: the tokenizer vocab (248,096) is narrower than mlx's
            # padded logits (248,320). Read the width off the logits rather
            # than off the model config, which does not carry it.
            bits = np.pad(bits, (0, width - bits.size))
        allowed = mx.array(bits.astype(np.bool_)).reshape(logits.shape)
        return mx.where(allowed, logits, -float("inf"))

    @property
    def terminated(self) -> bool:
        return self.matcher.is_terminated()


def compile_schema(tokenizer, schema: type, vocab_size: int | None = None):
    """One-shot compile — the C2 gate's whole question, callable on its own."""
    return GrammarCache(tokenizer, vocab_size).compile(schema)
