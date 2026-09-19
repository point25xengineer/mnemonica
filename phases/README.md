# Phase plans

One file per phase. Phase 2 splits by track, because the four tracks run
concurrently and should have separate owners and separate files.

| File | Owner | Blocked by |
|---|---|---|
| [PHASE-0-environment.md](PHASE-0-environment.md) | | nothing |
| [PHASE-1-foundations.md](PHASE-1-foundations.md) | | nothing (1a, 1b, 1c); 1e needs 1d |
| [PHASE-2A-knowledge-base.md](PHASE-2A-knowledge-base.md) | | **nothing — start now** |
| [PHASE-2B-audio.md](PHASE-2B-audio.md) | | gates 0g, 0h + recording 1e |
| [PHASE-2C-extraction.md](PHASE-2C-extraction.md) | | contract 1a + fixture 1c |
| [PHASE-2D-interface.md](PHASE-2D-interface.md) | | contract 1a + fixture 1c |
| [PHASE-3-integration.md](PHASE-3-integration.md) | | all four tracks |
| [PHASE-4-demo.md](PHASE-4-demo.md) | | Phase 3 |

Put your name in the Owner column when you pick one up.

Decisions are **D1**–**D26** in [../SPEC.md](../SPEC.md) §3. Tool contracts are
in [../TOOLS.md](../TOOLS.md). The dependency graph is [../PLAN.md](../PLAN.md).

**Rule for all phases:** if a step contradicts SPEC.md, SPEC.md wins — or the
decision gets changed there first, with its reasoning. Don't let the
architecture drift silently across eight files.
