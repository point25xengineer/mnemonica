"""C4.5 — the association check. D16 category 8, TOOLS.md §5 step 4.

**This is the failure span verification structurally cannot see.** The model
takes a genuine *"twice daily"* from drug A's turn and nests it under drug B.
Every quote is real, every offset is right, `str.find` is delighted — and the
action card is wrong. Nothing downstream can catch it, because nothing
downstream knows what the association was supposed to be. It is caught here by
comparing the turn a `sig`, date or change-evidence quote landed in against the
turn the drug mention landed in, or it is not caught at all.

**Not blocking.** The common case is a sig and a mention sharing a turn, and
blocking the common case would spend D9's entire 60-second budget on the safe
path. Instead it is prefilled, flagged, and rendered **expanded** with both
quotes and both timestamps, so the clinician's eye lands on it without a
keystroke.

Two deliberate softenings, both because a strict turn-equality test would fire
on almost every real item and a check that always fires is a check nobody
reads:

- **Adjacent clinician turns don't count.** "Let's go up to 50" / "Take it
  twice a day with food" two turns later is one thought, and it is how people
  actually speak. The gap that matters is the one where *another drug was
  named in between* — which is exactly the fixture's planted case: the sig at
  turn 20 is eight turns from the mention at turn 12, with lisinopril named in
  between and nothing re-anchoring metoprolol after it.
- **A drug named again in the sig's own turn cancels the finding.** If the
  clinician said the drug's name in the same breath as the dose, the
  association is not the model's guess.
"""

from __future__ import annotations

from dataclasses import dataclass

from visitnotes.contracts import Session
from visitnotes.verify.spans import Quote

__all__ = ["AssociationFinding", "check_association", "ADJACENT_TURNS"]

ADJACENT_TURNS = 2
"""How far a sig may sit from its mention before the gap is worth showing."""


@dataclass(frozen=True)
class AssociationFinding:
    """One quote that came from somewhere other than the drug's own turn."""

    field: str
    mention: Quote
    other: Quote
    turn_gap: int
    intervening_drug: str | None
    """A drug named between the two turns — the thing that makes a gap
    dangerous rather than merely long."""

    @property
    def reason(self) -> str:
        where = f"{self.turn_gap} turns" if self.turn_gap > 1 else "a different turn"
        if self.intervening_drug:
            return (f"{self.field} came from {where} away, with "
                    f"“{self.intervening_drug}” named in between")
        return f"{self.field} came from {where} away than the drug mention"


def check_association(
    session: Session,
    mention: Quote,
    others: list[tuple[str, Quote]],
    *,
    drug_names: list[str],
    mention_text: str,
) -> list[AssociationFinding]:
    """Compare each dependent quote's turn against the mention's turn.

    `drug_names` is every drug name spoken anywhere in the visit — the model
    does not supply it and could not be trusted with it; the pipeline has it
    from every mention it already verified."""
    findings: list[AssociationFinding] = []
    for field, quote in others:
        if quote is None or quote.turn_id == mention.turn_id:
            continue
        gap = abs(quote.turn_id - mention.turn_id)
        if _names_the_drug(session, quote.turn_id, mention_text):
            continue
        intervening = _intervening_drug(
            session, mention.turn_id, quote.turn_id, drug_names, mention_text
        )
        if gap <= ADJACENT_TURNS and intervening is None:
            continue
        findings.append(AssociationFinding(field, mention, quote, gap, intervening))
    return findings


def _names_the_drug(session: Session, turn_id: int, mention_text: str) -> bool:
    turn = next((t for t in session.turns if t.id == turn_id), None)
    if turn is None:
        return False
    head = mention_text.strip().split()
    return bool(head) and head[-1].lower().strip(",.") in turn.text.lower()


def _intervening_drug(
    session: Session, a: int, b: int, drug_names: list[str], mention_text: str
) -> str | None:
    lo, hi = sorted((a, b))
    mine = mention_text.lower()
    for turn in session.turns:
        if not lo < turn.id < hi:
            continue
        for name in drug_names:
            if name.lower() in mine:
                continue
            if name.lower() in turn.text.lower():
                return name
    return None
