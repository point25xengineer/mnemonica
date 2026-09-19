"""Build the golden fixtures — 1c.

    python fixtures/build_golden.py

Writes `fixtures/golden_visit.json` (1c-i, a `Session`) and
`fixtures/golden_extraction.json` (1c-ii, dispositioned items as C5 emits
them). Both are committed; this script is how you regenerate them.

**The content is hand-written — the offsets are not.** The phase file says
write the fixture by hand, and the dialogue below is hand-authored, mirroring
`roleplay_script.md` turn for turn. But hand-typing `char_offset` for 400
words is how you get a fixture that is subtly wrong in a way nobody notices
until Track C's citations point at the wrong characters. So the turns are
authored and the offsets are computed, from the same string Track C will
search.

Every quote in `golden_extraction.json` is likewise located with `str.find`
over the transcript this script just built — exactly as C4 will (D14). The two
fixtures are consistent with each other by construction, not by inspection.

## The turn list is a prediction of pyannote's output, not a stage script

Consecutive same-speaker lines are merged, because
`exclusive_speaker_diarization` emits one turn per contiguous stretch of one
voice. A fixture with two adjacent clinician turns predicts something pyannote
would never produce, and B5's diff against it would be noise. Turns here
alternate strictly.

Word timings are interpolated across each turn proportional to word length.
They are plausible, not measured — nothing in the pipeline does arithmetic on
them except click-to-play (U4), which only needs monotonicity.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import date, datetime
from pathlib import Path

# Run as a script from anywhere: `python fixtures/build_golden.py`. There is
# no package install step in this project and adding one at hour 3 is not
# worth four people's setup time.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from visitnotes.contracts import Consent, Session, Turn, Word  # noqa: E402

HERE = Path(__file__).parent
VISIT_DATE = date(2026, 9, 18)  # Friday — see roleplay_script.md, "Dates"
SESSION_DIR = Path("fixtures/sessions/golden")
RXNORM_RELEASE = "09012026"

DR = "SPEAKER_00"  # Dr. Amara Osei — clinician
PT = "SPEAKER_01"  # Ray Delgado, 71 — patient

# ---------------------------------------------------------------------------
# The dialogue. `heard` differs from the script only where we PREDICT an ASR
# error; everything else is what was said. Turn ids match roleplay_script.md,
# and tests/test_script_matches_fixture.py fails if they drift apart.
# ---------------------------------------------------------------------------

#: (id, cluster, role, start, end, heard_text)
TURNS: list[tuple[int, str, str, float, float, str]] = [
    (0, DR, "clinician", 0.0, 8.2, "Morning, Ray. Before we get started, I'd like to record this visit so you go home with a written summary. Nothing leaves this laptop. Is that alright with you?"),
    (1, PT, "other", 8.4, 11.0, "Yeah, that's fine by me."),
    (2, DR, "clinician", 11.2, 14.1, "Thank you. Okay, recording now."),
    (3, PT, "other", 14.3, 17.2, "Do I need to, uh, do I need to sign something?"),
    (4, DR, "clinician", 17.4, 23.0, "No, saying yes is enough, I've got it noted. So how have things been?"),
    (5, PT, "other", 23.2, 33.1, "Not bad. The headaches I had back in June, those are, those are mostly gone now. And I've been checking the pressure at home, like you asked."),
    (6, DR, "clinician", 33.3, 37.0, "Good, that's what I like to hear. What kind of numbers are you getting?"),
    (7, PT, "other", 37.2, 44.0, "Um, mostly one fifty over ninety. Ninety-two, sometimes."),
    (8, DR, "clinician", 44.2, 46.1, "Mm-hm."),
    # D16 cat 2 — "sixty-two" is spoken over a chair scrape.
    (9, PT, "other", 46.3, 55.0, "One morning it was one sixty-two. That one scared me a little."),
    (10, DR, "clinician", 55.2, 64.0, "Okay. That's higher than I want to see. Right now you're taking the metoprolol, twenty-five milligrams, and the lisinopril at ten."),
    # D16 cat 4 — "the other blood pressure pill" resolves to nothing.
    (11, PT, "other", 64.2, 71.0, "The little white one, yeah. And the, the other blood pressure pill, I don't know what that one's called."),
    # The metoprolol mention. Its sig arrives 8 turns later, at turn 20.
    (12, DR, "clinician", 71.2, 79.3, "That's the lisinopril. So what I'd like to do is bring the metoprolol up to fifty milligrams."),
    (13, PT, "other", 79.5, 82.0, "Fifty. Okay."),
    (14, DR, "clinician", 82.2, 89.0, "Your heart rate's got room for it, and the headaches coming back would be the thing I'd worry about otherwise."),
    (15, PT, "other", 89.2, 93.0, "And the other one? The lisinopril?"),
    # D16 cat 5 — a complete, correct parse whose finding is that no dose exists.
    (16, DR, "clinician", 93.2, 98.1, "That one doesn't change, just take it the way you've been taking it."),
    (17, PT, "other", 98.3, 100.2, "Okay."),
    # D16 cat 6 — the loose thread. Never revisited, deliberately.
    (18, DR, "clinician", 100.4, 111.0, "Though, um, we may need to adjust the lisinopril as well, depending. Let me have a look at your kidney numbers. Now, the dosing."),
    # D16 cat 3 — the patient states a dose over the clinician; role is unknown.
    (19, PT, "unknown", 111.0, 114.2, "So that's two of the twenty-fives?"),
    # D16 cat 8 — "twice a day" lands here, with lisinopril the nearest named drug.
    (20, DR, "clinician", 114.4, 125.0, "Let's get you the fifties, it's one tablet instead of two. And that one's twice a day, with food."),
    (21, PT, "other", 125.2, 129.0, "Twice a day. Morning and night."),
    (22, DR, "clinician", 129.2, 139.0, "Right. And I want to see you back in about ten days so we can check the pressure again and make sure the higher dose isn't dropping it too far."),
    (23, PT, "other", 139.2, 154.0, "Ten days. I'll get that on the calendar. Will the fifty make me more tired? When I started the twenty-five I was, I was dragging for about a week."),
    (24, DR, "clinician", 154.2, 164.0, "It can, at first. Tiredness, cold hands, those are the common ones, and they usually settle after a week or two."),
    (25, PT, "other", 164.2, 167.0, "And if they don't?"),
    (26, DR, "clinician", 167.2, 175.0, "Then we look at it again. But don't stop it on your own, that's the one thing I'd ask you."),
    (27, PT, "other", 175.2, 178.0, "No, I won't."),
    # D16 cat 7 (contradicts turn 12) + the predicted fuzzy match, "metropolol".
    (28, DR, "clinician", 178.2, 187.0, "So, going back over it, the metropolol, twenty-five, twice a day, and the lisinopril stays where it is."),
    (29, PT, "other", 187.2, 189.0, "Got it."),
    (30, DR, "clinician", 189.2, 198.0, "One more thing. If you feel dizzy when you stand up, or your heart feels like it's racing, call the office. Don't wait for the ten days."),
    (31, PT, "other", 198.2, 201.0, "Dizzy or racing. Okay."),
    (32, DR, "clinician", 201.2, 206.0, "And bring the home monitor with you next time, I'd like to see it against ours."),
    (33, PT, "other", 206.2, 209.0, "Will do. Thanks, doc."),
    (34, DR, "clinician", 209.2, 212.0, "Take care, Ray."),
]

#: (turn id, token, probability) — the words we deliberately degrade.
#: A fixture where every word is 0.99 tests nothing D16 category 2 cares about.
LOW_CONFIDENCE: list[tuple[int, str, float]] = [
    (9, "sixty-two.", 0.41),   # the cat 2 plant: chair scrape over the number
    (9, "one", 0.62),          # its neighbour degrades too, as ASR does
    (19, "twenty-fives?", 0.58),  # spoken over the clinician
    (28, "metropolol,", 0.66),    # the mistranscription is not confident either
    (3, "uh,", 0.55),
    (18, "um,", 0.51),
]


def build_session() -> Session:
    """Author the turns, compute every offset from the transcript itself."""
    rng = random.Random(20260918)  # deterministic: the fixture is committed
    transcript_parts: list[str] = []
    cursor = 0
    turns: list[Turn] = []

    overrides = {(tid, tok): p for tid, tok, p in LOW_CONFIDENCE}

    for tid, cluster, role, start, end, text in TURNS:
        if transcript_parts:
            cursor += 1  # the single space joining this turn to the last
        char_start = cursor
        tokens = text.split()
        total = sum(len(t) for t in tokens)
        words: list[Word] = []
        elapsed = 0
        # Walk the turn text forward, so a repeated token ("the", "those")
        # gets its own offset instead of every copy pointing at the first.
        within = 0
        for token in tokens:
            i = text.index(token, within)
            within = i + len(token)
            frac_start = (elapsed) / total
            elapsed += len(token)
            frac_end = elapsed / total
            probability = overrides.get(
                (tid, token), round(rng.uniform(0.86, 0.995), 3)
            )
            words.append(
                Word(
                    text=token,
                    start=round(start + (end - start) * frac_start, 3),
                    end=round(start + (end - start) * frac_end, 3),
                    probability=probability,
                    speaker_cluster=cluster,
                    char_offset=char_start + i,
                )
            )
        cursor = char_start + len(text)
        transcript_parts.append(text)
        turns.append(
            Turn(
                id=tid,
                speaker_cluster=cluster,
                role=role,
                start=start,
                end=end,
                words=words,
                text=text,
                char_start=char_start,
                char_end=cursor,
            )
        )

    return Session(
        visit_date=VISIT_DATE,
        session_dir=SESSION_DIR,
        audio_path=SESSION_DIR / "visit.wav",
        transcript_text=" ".join(transcript_parts),
        turns=turns,
        consent=Consent(
            obtained=True,
            method="verbal",
            # D27: before recording. Turn 0 is t=0 of the audio; consent
            # precedes it.
            obtained_at=datetime(2026, 9, 18, 9, 12, 0),
        ),
    )


# ---------------------------------------------------------------------------
# 1c-ii — the extraction fixture. Dispositioned items, as C5 emits them.
#
# Track D is blocked without this file. A `Session` contains turns and words
# and NO extracted items, so a review list cannot be rendered from 1c-i alone.
#
# The disposition envelope below is not in TOOLS.md — §4 defines the model's
# output shape, and §5 defines the verification steps, but the post-C5 shape
# that Track D actually consumes was never written down. This file pins it.
# If C5 emits something different, change it HERE and tell Track D, because
# they will have built against it.
# ---------------------------------------------------------------------------

#: Real values, read from this RxNorm release (09012026) — not invented.
METOPROLOL_STRENGTHS = [
    "25 MG Oral Tablet",
    "50 MG Oral Tablet",
    "75 MG Oral Tablet",
    "100 MG Oral Tablet",
    "10 MG/ML Oral Solution",
]
LISINOPRIL_STRENGTHS = [
    "5 MG Oral Tablet",
    "10 MG Oral Tablet",
    "20 MG Oral Tablet",
    "30 MG Oral Tablet",
    "40 MG Oral Tablet",
]
METOPROLOL_SPL = ["00940cc5-d2eb-4841-9138-de97d7b1c674"]
LISINOPRIL_SPL = ["00b266d9-ac4a-e931-e063-6294a90a6a0b"]


class Locator:
    """Resolve a verbatim quote the way C4 will: `str.find`, then the turn.

    Refuses a quote that does not occur exactly once. D14 accepts an offset
    only on a single match; a fixture quote with two matches would encode a
    disambiguation that the real pipeline has to make and we are guessing at.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def __call__(self, quote: str) -> dict:
        text = self.session.transcript_text
        n = text.count(quote)
        if n != 1:
            raise ValueError(f"quote {quote!r} occurs {n} times; need exactly 1")
        offset = text.index(quote)
        turn = self.session.turn_at_offset(offset)
        assert turn is not None
        return {
            "text": quote,
            "char_offset": offset,
            "char_end": offset + len(quote),
            "turn_id": turn.id,
            "turn_role": turn.role,
            "audio_start": turn.words[0].start,
            "min_word_probability": round(
                min(
                    w.probability
                    for w in turn.words
                    if w.char_offset >= offset and w.char_end <= offset + len(quote)
                ),
                3,
            ),
        }


def build_extraction(session: Session) -> dict:
    q = Locator(session)

    # --- the centrepiece ---------------------------------------------------
    # One drug, four dose statements, three of which need a human. This is
    # the item the demo lives or dies on.
    mention = q("the metoprolol up to fifty milligrams")
    prior_dose = q("twenty-five milligrams")          # turn 10, the baseline
    new_dose = q("up to fifty milligrams")            # turn 12, the change
    unknown_dose = q("two of the twenty-fives")       # turn 19, role=unknown
    later_sig = q("twice a day, with food")           # turn 20, cat 8
    contradiction = q("the metropolol, twenty-five, twice a day")  # turn 28

    metoprolol = {
        "id": "med-metoprolol",
        "kind": "medication",
        "disposition": "blocking",
        "d16_categories": [3, 7, 8],
        "mention_quote": mention,
        "medication": {
            "status": "resolved",
            "rxcui": "6918",
            "canonical_name": "metoprolol",
            "tty": "IN",
            "ingredients": ["metoprolol"],
            "brand_names": ["Lopressor", "Toprol-XL"],
            "is_brand": False,
            # A5.5: an IN matched and this ingredient has 2+ PIN salt children.
            # Never printed as fact unclicked — the salts differ in dosing
            # frequency, which is the entire clinical content of this card.
            "salt_unspecified": True,
            "salt_candidates": ["metoprolol succinate", "metoprolol tartrate"],
            "match_type": "exact",
            "edit_distance": 0,
            "match_confidence": 0.98,
            "candidates": [],
            "spl_set_ids": METOPROLOL_SPL,
            "available_strengths": METOPROLOL_STRENGTHS,
            "dose_forms": ["Oral Tablet", "Oral Solution"],
            "source": "RxNorm Current Prescribable",
            "source_release": RXNORM_RELEASE,
        },
        "sig": [
            {
                "quote": new_dose,
                "status": "parsed",
                "dose_amount": 50.0,
                "dose_unit": "mg",
                "dose_form": None,
                "route": "oral",
                "frequency_per_day": None,
                "interval_hours": None,
                "timing": [],
                "prn": False,
                "prn_condition": None,
                "unparsed_remainder": None,
                "normalized_sig": "50 mg",
                "parse_confidence": 0.94,
                "source": "deterministic grammar",
                "grammar_version": "0.1.0",
            },
            {
                # D16 cat 3. A dose, from a turn whose role is unknown.
                # D19: a dose may only be extracted from a clinician turn.
                "quote": unknown_dose,
                "status": "parsed",
                "dose_amount": 25.0,
                "dose_unit": "mg",
                "dose_form": "tablet",
                "route": "oral",
                "frequency_per_day": None,
                "interval_hours": None,
                "timing": [],
                "prn": False,
                "prn_condition": None,
                "unparsed_remainder": None,
                "normalized_sig": "2 x 25 mg",
                "parse_confidence": 0.71,
                "source": "deterministic grammar",
                "grammar_version": "0.1.0",
                "blocking_reason": "attribution_ambiguous",
            },
            {
                # D16 cat 8. Genuine quote, genuine sig, different turn from
                # the mention — and lisinopril is the nearest drug named
                # before it. Span verification passes and the card can still
                # be wrong.
                "quote": later_sig,
                "status": "partial",
                "dose_amount": None,
                "dose_unit": None,
                "dose_form": None,
                "route": "oral",
                "frequency_per_day": 2.0,
                "interval_hours": None,
                "timing": ["with food"],
                "prn": False,
                "prn_condition": None,
                "unparsed_remainder": None,
                "normalized_sig": "twice daily with food",
                "parse_confidence": 0.89,
                "source": "deterministic grammar",
                "grammar_version": "0.1.0",
            },
            {
                # D16 cat 7. 25 mg here against 50 mg at turn 12.
                "quote": contradiction,
                "status": "parsed",
                "dose_amount": 25.0,
                "dose_unit": "mg",
                "dose_form": None,
                "route": "oral",
                "frequency_per_day": 2.0,
                "interval_hours": None,
                "timing": [],
                "prn": False,
                "prn_condition": None,
                "unparsed_remainder": None,
                "normalized_sig": "25 mg twice daily",
                "parse_confidence": 0.92,
                "source": "deterministic grammar",
                "grammar_version": "0.1.0",
            },
        ],
        "start_or_stop": None,
        "change_kind": "increased",
        "change_evidence_quote": mention,
        # U6: printable as fact ONLY because two parsed doses made it
        # arithmetic. 25 -> 50. The model's opinion was not consulted.
        "change_kind_derived": True,
        "change_kind_derivation": {
            "from_dose": {"amount": 25.0, "unit": "mg", "quote": prior_dose},
            "to_dose": {"amount": 50.0, "unit": "mg", "quote": new_dose},
            "rule": "both doses parsed and resolved; 50 > 25",
        },
        "flags": [
            {
                "d16_category": 7,
                "blocking": True,
                "reason": "two different doses for one drug",
                "render": "expanded",
                "evidence": [new_dose, contradiction],
            },
            {
                "d16_category": 3,
                "blocking": True,
                "reason": "dose stated in a turn with no confident speaker role",
                "render": "expanded",
                "evidence": [unknown_dose],
            },
            {
                "d16_category": 8,
                "blocking": False,
                "reason": "sig came from a different turn than the drug mention",
                "render": "expanded",  # never collapsed, never fact unclicked
                "evidence": [mention, later_sig],
            },
            {
                "d16_category": None,
                "blocking": False,
                "reason": "salt unspecified: succinate (once daily) or tartrate (twice daily)?",
                "render": "expanded",
                "choices": ["metoprolol succinate", "metoprolol tartrate"],
            },
        ],
    }

    # --- the quiet one: correct, and still not printable as fact -----------
    lisinopril = {
        "id": "med-lisinopril",
        "kind": "medication",
        "disposition": "prefilled_flagged",
        "d16_categories": [5],
        "mention_quote": q("the lisinopril at ten"),
        "medication": {
            "status": "resolved",
            "rxcui": "29046",
            "canonical_name": "lisinopril",
            "tty": "IN",
            "ingredients": ["lisinopril"],
            "brand_names": ["Zestril", "Prinivil"],
            "is_brand": False,
            "salt_unspecified": False,
            "salt_candidates": [],
            "match_type": "exact",
            "edit_distance": 0,
            "match_confidence": 0.99,
            "candidates": [],
            "spl_set_ids": LISINOPRIL_SPL,
            "available_strengths": LISINOPRIL_STRENGTHS,
            "dose_forms": ["Oral Tablet", "Oral Solution"],
            "source": "RxNorm Current Prescribable",
            "source_release": RXNORM_RELEASE,
        },
        "sig": [
            {
                # D16 cat 5. A COMPLETE, SUCCESSFUL parse whose finding is
                # that no dose was stated. This is not an error and must not
                # look like one: "your doctor never said it" is a different
                # fact from "I could not hear it".
                "quote": q("just take it the way you've been taking it"),
                "status": "not_specified",
                "dose_amount": None,
                "dose_unit": None,
                "dose_form": None,
                "route": None,
                "frequency_per_day": None,
                "interval_hours": None,
                "timing": [],
                "prn": False,
                "prn_condition": None,
                "unparsed_remainder": None,
                "normalized_sig": None,
                "parse_confidence": 0.97,
                "source": "deterministic grammar",
                "grammar_version": "0.1.0",
            }
        ],
        "start_or_stop": None,
        "change_kind": "continued",
        "change_evidence_quote": q("That one doesn't change"),
        # No two doses to compare, so nothing was derived. U6: prefilled and
        # flagged, never printed as fact. The clinician's click promotes it.
        "change_kind_derived": False,
        "change_kind_derivation": None,
        "flags": [
            {
                "d16_category": 5,
                "blocking": False,
                "reason": "no dose spoken — not an error",
                "render": "collapsed",
                "display": "not specified",
            },
            {
                "d16_category": None,
                "blocking": False,
                "reason": "change_kind was not derived from two parsed doses",
                "render": "collapsed",
            },
        ],
    }

    # --- D16 cat 4 ---------------------------------------------------------
    unresolved = {
        "id": "med-unresolved-bp-pill",
        "kind": "medication",
        "disposition": "prefilled_flagged",
        "d16_categories": [4],
        "mention_quote": q("the other blood pressure pill"),
        "medication": {
            "status": "unresolved",
            "rxcui": None,
            "canonical_name": None,
            "tty": None,
            "ingredients": [],
            "brand_names": [],
            "is_brand": None,
            "salt_unspecified": False,
            "salt_candidates": [],
            "match_type": "none",
            "edit_distance": None,
            "match_confidence": 0.0,
            "candidates": [],
            "spl_set_ids": [],
            "available_strengths": [],
            "dose_forms": [],
            "source": "RxNorm Current Prescribable",
            "source_release": RXNORM_RELEASE,
        },
        "sig": [],
        "start_or_stop": None,
        "change_kind": "continued",
        "change_evidence_quote": q("the other blood pressure pill"),
        "change_kind_derived": False,
        "change_kind_derivation": None,
        "flags": [
            {
                "d16_category": 4,
                "blocking": False,
                "reason": "no RxNorm concept matched the heard text",
                "render": "expanded",
                "heard_text": "the other blood pressure pill",
                "near_matches": [],
                # The clinician answers this in one click: the next turn is
                # "That's the lisinopril." Track D should offer merging into
                # an existing item, not just free-text correction.
                "suggested_action": "merge_into:med-lisinopril",
            },
            {
                "d16_category": 3,
                "blocking": False,
                "reason": "spoken by the patient, not the clinician",
                "render": "expanded",
            },
        ],
    }

    appointment = {
        "id": "appt-followup",
        "kind": "appointment",
        "disposition": "printed_as_fact",
        "d16_categories": [],
        "when": {
            "quote": q("about ten days"),
            "status": "resolved",
            "resolved_date": "2026-09-28",
            "range_start": None,
            "range_end": None,
            "precision": "exact_day",
            "direction": "future",
            "anchor_date": VISIT_DATE.isoformat(),
            "anchor_source": "session_visit_date",
            "original_phrase": "about ten days",
            # D18: BOTH forms. A patient reading a bare date cannot catch an
            # error; reading both lets them. Ten days, not two weeks —
            # multiples of seven from this weekend print a weekend.
            "display_string": "about ten days from today, which is Monday, September 28",
            "depends_on_event": None,
            "resolution_confidence": 0.93,
            "source": "deterministic date resolver",
        },
        "purpose_quote": q("check the pressure again"),
        "flags": [],
    }

    red_flags = [
        {
            "id": "flag-dizzy",
            "kind": "red_flag",
            "disposition": "printed_as_fact",
            "d16_categories": [],
            "instruction_quote": q(
                "If you feel dizzy when you stand up, or your heart feels like "
                "it's racing, call the office."
            ),
            "flags": [],
        },
        {
            "id": "flag-dont-stop",
            "kind": "red_flag",
            "disposition": "printed_as_fact",
            "d16_categories": [],
            "instruction_quote": q("don't stop it on your own"),
            "flags": [],
        },
    ]

    loose_threads = [
        {
            "id": "thread-lisinopril-adjust",
            "kind": "loose_thread",
            "disposition": "surfaced",
            "d16_categories": [6],
            # Arguably the most valuable output in the product: "you told the
            # patient you'd adjust the dose and never specified it."
            "topic_quote": q("we may need to adjust the lisinopril as well"),
            "flags": [
                {
                    "d16_category": 6,
                    "blocking": False,
                    "reason": "raised and never resolved anywhere later in the visit",
                    "render": "expanded",
                }
            ],
        }
    ]

    return {
        "$fixture": "golden_extraction",
        "$mirrors": "golden_visit.json",
        "$note": (
            "Hand-authored post-C5 output. Every quote was located with "
            "str.find over golden_visit.json's transcript_text and occurs "
            "exactly once, so offsets here are real, not asserted."
        ),
        "visit_date": VISIT_DATE.isoformat(),
        "header": {
            # U3. The discarded count is what keeps an omission visible in a
            # 60-second review; collapsing it would let the clinician attest
            # to a page that looks complete and is not.
            "confirmed": 3,
            "blocking": 1,
            "needs_confirmation": 2,
            "discarded": 1,
            "loose_threads": 1,
        },
        "medications": [metoprolol, lisinopril, unresolved],
        "appointments": [appointment],
        "red_flags": red_flags,
        "loose_threads": loose_threads,
        "discarded": [
            {
                # D16 cat 1. Counted, never shown. The clinician sees "1
                # discarded" and nothing else: the fabricated text is the
                # part that must not reach a human. Deliberately no quote
                # field here — if you add one, you have broken the rule.
                "d16_category": 1,
                "kind": "medication",
                "reason": "span_verification_failed",
                "dropped_at": "C4",
            }
        ],
        # D7 — extractive summary. Verbatim quotes under fixed headings; no
        # generated prose anywhere. SummarySelection is referenced in TOOLS
        # §4 but never defined there; this is the shape Track D gets.
        "summary_quotes": {
            "why_you_came_in": [q("I've been checking the pressure at home")],
            "what_the_doctor_found": [
                q("That's higher than I want to see"),
                q("Your heart rate's got room for it"),
            ],
            "what_happens_next": [
                q("bring the home monitor with you next time"),
            ],
        },
    }


def main() -> None:
    session = build_session()
    (HERE / "golden_visit.json").write_text(
        session.model_dump_json(indent=2) + "\n"
    )
    extraction = build_extraction(session)
    (HERE / "golden_extraction.json").write_text(
        json.dumps(extraction, indent=2) + "\n"
    )
    print(
        f"golden_visit.json      {len(session.turns)} turns, "
        f"{sum(len(t.words) for t in session.turns)} words, "
        f"{len(session.transcript_text)} chars"
    )
    print(
        f"golden_extraction.json {len(extraction['medications'])} medications, "
        f"{len(extraction['appointments'])} appointments, "
        f"{len(extraction['red_flags'])} red flags, "
        f"{len(extraction['loose_threads'])} loose threads, "
        f"{len(extraction['discarded'])} discarded"
    )


def _cli() -> None:
    if "--script" in sys.argv:
        changed = write_script()
        print(
            f"roleplay_script.md {'rewritten' if changed else 'already in sync'}"
        )
        return
    main()


# ---------------------------------------------------------------------------
# Regenerating the script's dialogue from the same list that builds the
# fixture. The phase file's rule is that the two mirror each other turn for
# turn; making that mechanical beats making it a discipline note, because
# discipline is what fails at hour 19.
#
#     python fixtures/build_golden.py --script
# ---------------------------------------------------------------------------

SPEAKER_LABEL = {DR: "DR. OSEI", PT: "RAY"}

#: Where the fixture PREDICTS an ASR error. The script says the left-hand
#: side; the transcript is expected to come back with the right-hand side.
#: Say the drug name correctly — do not perform the error.
MISTRANSCRIBED = {28: [("metropolol", "metoprolol")]}

#: Recording notes, printed under their turn. Not spoken.
NOTES: dict[int, str] = {
    9: "Make noise across \"sixty-two\" — scrape the chair, or cough. This is "
       "the D16 category 2 plant and the per-word probability has to actually "
       "drop. Do not enunciate it.",
    18: "This is the loose thread, and it ends mid-turn on \"Now, the "
        "dosing.\" Do NOT come back to the lisinopril. The temptation to "
        "resolve it on tape is strong; resisting it is the whole plant. Note "
        "also that this turn does not name metoprolol before the sig lands "
        "at turn 20 — a nearest-mention heuristic that guesses right by "
        "accident tests nothing.",
    19: "Start speaking before she finishes turn 18 — a real half-second "
        "overlap. The patient stating a dose over the clinician is the D16 "
        "category 3 plant, and exclusive diarization needs something to "
        "actually exclude.",
    20: "Do NOT name the drug in this turn. \"That one\" is the category 8 "
        "plant: the sig is eight turns downstream of the mention, and "
        "lisinopril is the nearest drug named in between. Span verification "
        "cannot see this failure — every quote in it is genuine.",
    28: "This contradicts turn 12 (fifty milligrams) and it should sound "
        "completely unremarkable — she is reciting the old regimen from "
        "memory, slightly too fast. That is the failure mode. Say "
        "\"metoprolol\" correctly; the fixture predicts Whisper hears "
        "\"metropolol\" here, and if the real transcript comes back clean "
        "that is a pass for Track B, not a reason to re-record.",
}

SCRIPT_PATH = HERE / "roleplay_script.md"
BEGIN = "<!-- BEGIN GENERATED DIALOGUE -->"
END = "<!-- END GENERATED DIALOGUE -->"


def spoken_text(turn_id: int, heard: str) -> str:
    """What the actor says, as opposed to what we predict Whisper hears."""
    text = heard
    for wrong, right in MISTRANSCRIBED.get(turn_id, []):
        text = text.replace(wrong, right)
    return text


def render_script_block() -> str:
    lines = [
        BEGIN,
        "",
        "*Generated from `fixtures/build_golden.py`. Edit the `TURNS` list "
        "there and re-run `python fixtures/build_golden.py --script`; editing "
        "this block by hand is how the script and the fixture drift apart.*",
        "",
    ]
    for tid, cluster, _role, start, _end, heard in TURNS:
        mm, ss = divmod(int(start), 60)
        lines.append(
            f"**T{tid}** · {mm:02d}:{ss:02d} · **{SPEAKER_LABEL[cluster]}:** "
            f"{spoken_text(tid, heard)}"
        )
        lines.append("")
        if tid in NOTES:
            lines.append(f"> *Recording note: {NOTES[tid]}*")
            lines.append("")
    lines.append(END)
    return "\n".join(lines)


def write_script() -> bool:
    """Rewrite the generated block in place. True if the file changed."""
    original = SCRIPT_PATH.read_text()
    start = original.index(BEGIN)
    end = original.index(END) + len(END)
    updated = original[:start] + render_script_block() + original[end:]
    if updated != original:
        SCRIPT_PATH.write_text(updated)
    return updated != original


if __name__ == "__main__":
    _cli()
