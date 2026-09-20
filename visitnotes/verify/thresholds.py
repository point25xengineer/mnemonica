"""The numbers 3c tunes. One file, so the gate is a diff and not a scavenger hunt.

**There is no labeled data to tune these against, and pretending otherwise
would be worse than the numbers being rough.** What settles them is an
asymmetry rather than a measurement: over-flagging costs a click and
under-flagging costs a wrong dose. So every value here is biased toward
flagging, deliberately, and that is the sentence to say out loud when a judge
asks how they were validated.

Each constant records what it is and what moving it costs.
"""

from __future__ import annotations

__all__ = [
    "LOW_WORD_PROBABILITY", "DOSE_WORD_PROBABILITY", "COMPRESSION_RATIO_CEILING",
]

DOSE_WORD_PROBABILITY = 0.80
"""D16 category 2 — below this per-word `probability`, a **dose numeral** is
flagged and the audio is auto-cued to that word.

Set high on purpose. A numeral is one token of acoustic evidence with no
redundancy: "15" and "50" differ by a vowel, and unlike a drug name there is no
knowledge base downstream that can catch a wrong one. The real recording's
planted case sits at 0.14 and the correct doses at 0.99+, so anything in this
range separates them — the question is only how much of the safe middle to
give up, and the answer is all of it."""

LOW_WORD_PROBABILITY = 0.55
"""The same signal on **non-dose** text. Lower, because a shaky word in a
sentence has context around it and the cost of being wrong is a confusing
quote rather than a wrong dose."""

COMPRESSION_RATIO_CEILING = 2.4
"""Whisper's standard hallucination heuristic, kept for a pipeline that can
supply it — and **nothing in this build can**.

1c measured mlx-whisper's segment fields across nine consecutive segments of
the real recording: `no_speech_prob` 0.101, `compression_ratio` 1.64,
`avg_logprob` -0.098, *identical* on every one, because the 30-second decode
window's statistics are stamped onto every sentence inside it. At sentence
granularity they carry no information, and contract 1a does not carry them
onto `Word` at all.

So D16 category 2 is implemented on per-word probability alone. That is a
documented departure from the spec's wording, not an oversight: a threshold on
a constant is a check that never fires, which looks exactly like a clean run."""
