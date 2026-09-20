"""C3 — run the constrained extraction over a `Session`, one turn at a time.

The model is loaded once and every turn is a fresh generation with a fresh
`GrammarMatcher`. D24's model choice is a runtime argument, not a constant:
the 9B is what we develop on, and the MoE is what the demo runs, and C3's
fidelity number is what decides.

Nothing in here interprets output. A turn's JSON is parsed into a
`TurnExtraction` and handed on; whether the quotes are *real* is C4's question
and is not asked here. Keeping those separate is what lets the fallback in D23
be honest — without the grammar we lose well-formedness, and span verification
still runs unchanged.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from mnemonica.contracts import Session, Turn
from mnemonica.extract.grammar import GrammarCache
from mnemonica.extract.prompt import SYSTEM, build_prompt
from mnemonica.extract.schema import TurnExtraction, VisitExtraction, merge_turns

__all__ = ["Extractor", "TurnResult", "ExtractionRun", "DEV_MODEL", "DEMO_MODEL"]

DEV_MODEL = "mlx-community/Qwen3.5-9B-4bit"
"""D24 — develop here. 5.98 GB, cached at 0i."""
DEMO_MODEL = "mlx-community/Qwen3.6-35B-A3B-4bit"
"""D24 — 20.43 GB MoE, measured at 41 tok/s here (0i), not the 65–85 the spec
estimated. Time the real prompt before choosing on speed."""

MAX_TOKENS = 1024
"""One turn's JSON. A turn that wants more than this is a turn whose quotes
have smeared, which is a C4.5 finding rather than a budget problem."""


@dataclass
class TurnResult:
    turn_id: int
    extraction: TurnExtraction
    seconds: float
    tokens: int
    raw: str
    malformed: bool = False
    """True only on the D23 fallback path. Under the grammar it cannot happen,
    and a test tries to provoke it."""


@dataclass
class ExtractionRun:
    """Everything one pass over a session produced, plus what it cost.

    The timing is not decoration: 3b has to stopwatch the machine's time
    against a demo slot, and per-turn numbers are the only ones that let you
    say which turns are expensive."""

    visit: VisitExtraction
    turns: list[TurnResult] = field(default_factory=list)
    model: str = DEV_MODEL
    grammar: bool = True

    @property
    def seconds(self) -> float:
        return sum(t.seconds for t in self.turns)

    @property
    def tokens_per_second(self) -> float:
        total = sum(t.tokens for t in self.turns)
        return total / self.seconds if self.seconds else 0.0


class Extractor:
    """Loads a model once; extracts per turn.

    Constructing this loads several gigabytes, so tests that do not need a
    model must not construct one — everything downstream of C3 takes a
    `VisitExtraction`, not an `Extractor`."""

    def __init__(self, model_id: str = DEV_MODEL, *, use_grammar: bool = True):
        from mlx_lm import load

        self.model_id = model_id
        self.model, self.tokenizer = load(model_id)
        self.use_grammar = use_grammar
        self.cache = GrammarCache(self.tokenizer) if use_grammar else None

    # -- one turn ---------------------------------------------------------

    def _chat(self, user: str) -> str:
        return self.tokenizer.apply_chat_template(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            add_generation_prompt=True,
            tokenize=False,
            enable_thinking=False,  # see prompt.py — this is about quote
                                    # boundaries, not about JSON validity
        )

    def extract_turn(self, session: Session, turn: Turn) -> TurnResult:
        from mlx_lm import generate

        prompt = self._chat(build_prompt(session, turn))
        processors = None
        if self.cache is not None:
            processors = [self.cache.processor(TurnExtraction)]

        t0 = time.perf_counter()
        text = generate(
            self.model, self.tokenizer, prompt,
            max_tokens=MAX_TOKENS, logits_processors=processors, verbose=False,
        )
        elapsed = time.perf_counter() - t0

        extraction, malformed = self._parse(text)
        return TurnResult(
            turn_id=turn.id, extraction=extraction, seconds=elapsed,
            tokens=len(self.tokenizer.encode(text)), raw=text,
            malformed=malformed,
        )

    def _parse(self, text: str) -> tuple[TurnExtraction, bool]:
        """D23's fallback lives here and nowhere else.

        Under the grammar the first `json.loads` cannot fail. Without it, one
        reparse retry — strip anything before the first brace, which is the
        documented Ollama-class failure and also what a chatty model does —
        and then an empty extraction. An empty extraction is a *safe* failure:
        it loses a turn's content and invents nothing."""
        try:
            return TurnExtraction.model_validate_json(text), False
        except Exception:  # noqa: BLE001
            pass
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return (TurnExtraction.model_validate(
                    json.loads(text[start:end + 1])), True)
            except Exception:  # noqa: BLE001
                pass
        return TurnExtraction(), True

    # -- whole session ----------------------------------------------------

    def extract(self, session: Session, *, progress=None) -> ExtractionRun:
        results: list[TurnResult] = []
        for turn in session.turns:
            result = self.extract_turn(session, turn)
            results.append(result)
            if progress:
                progress(result, len(results), len(session.turns))
        return ExtractionRun(
            visit=merge_turns([r.extraction for r in results]),
            turns=results, model=self.model_id, grammar=self.use_grammar,
        )
