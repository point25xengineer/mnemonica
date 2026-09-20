"""Build the golden fixtures — 1c.

    python fixtures/build_golden.py

Writes `fixtures/golden_visit.json` (1c-i, a `Session`) and
`fixtures/golden_extraction.json` (1c-ii, dispositioned items as C5 emits
them). Both are committed; this script is how you regenerate them.

**This is now ground truth, not a prediction.** The first draft of this file
hand-authored the dialogue and interpolated the timings, because no audio
existed. The role-play take now exists, so the turns carry the REAL
mlx-whisper output — real word boundaries, real per-word probabilities, real
mistranscriptions — read from `asr_words.json`, which is committed so this
rebuilds without the audio (gitignored, and role-play besides).

What is still hand-authored is the part diarization would produce: which words
belong to which turn, and which speaker is which. Those boundaries are
independent of Track B, which is the point — B5 diffs its real `Session`
against this one, and a fixture built from pyannote's own output could not
test pyannote.

Offsets are computed, never typed. Every quote in `golden_extraction.json` is
located with `str.find` over the transcript this script builds, exactly as C4
will (D14), and asserted to occur exactly once.

Word timings come from mlx-whisper's DTW alignment on large-v3 (D21 — not
turbo, whose 4 decoder layers wreck exactly this).
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

#: Turn boundaries over `asr_words.json`, as (id, cluster, role, first word
#: index, last word index, inclusive). This is the hand-authored part — it is
#: what diarization has to reproduce, so it must not come FROM diarization.
#:
#: Turn 19 is the D16 category 3 plant: the patient states a dose over the
#: clinician, and its role is `unknown` rather than `other`, because that is
#: what an enrollment match that fails on overlapped speech produces (D20).
TURN_BOUNDS: list[tuple[int, str, str, int, int]] = [
    (0,  DR, "clinician",   0,  29),
    (1,  PT, "other",      30,  34),
    (2,  DR, "clinician",  35,  39),
    (3,  PT, "other",      40,  50),
    (4,  DR, "clinician",  51,  64),
    (5,  PT, "other",      65,  92),
    (6,  DR, "clinician",  93, 106),
    (7,  PT, "other",     107, 113),
    (8,  DR, "clinician", 114, 115),
    (9,  PT, "other",     116, 128),
    (10, DR, "clinician", 129, 149),
    (11, PT, "other",     150, 169),   # cat 4 — "the other blood pressure pill"
    (12, DR, "clinician", 170, 186),   # the metoprolol mention
    (13, PT, "other",     187, 188),
    (14, DR, "clinician", 189, 208),
    (15, PT, "other",     209, 217),
    (16, DR, "clinician", 218, 230),   # cat 5 — no dose stated
    (17, PT, "other",     231, 232),
    (18, DR, "clinician", 233, 256),   # cat 6 — the loose thread
    (19, PT, "unknown",   257, 262),   # cat 3 — a dose, no confident role
    (20, DR, "clinician", 263, 281),   # cat 8 — the sig, 8 turns downstream
    (21, PT, "other",     282, 288),
    (22, DR, "clinician", 289, 318),   # the appointment
    (23, PT, "other",     319, 349),   # cat 2 — "the 50" at p=0.14
    (24, DR, "clinician", 350, 370),
    (25, PT, "other",     371, 374),
    (26, DR, "clinician", 375, 395),   # red flag — "don't stop it on your own"
    (27, PT, "other",     396, 400),
    (28, DR, "clinician", 401, 418),   # cat 7 — 25 against turn 12's 50
    (29, PT, "other",     419, 422),
    (30, DR, "clinician", 423, 449),   # red flag — "call the office"
    (31, PT, "other",     450, 456),
    (32, DR, "clinician", 457, 472),
    (33, PT, "other",     473, 476),
    (34, DR, "clinician", 477, 479),
]


def load_asr_words() -> list[dict]:
    """The committed mlx-whisper output. Leading spaces intact, as emitted."""
    return json.loads((HERE / "asr_words.json").read_text())["words"]


def build_session() -> Session:
    """Assemble the Session from real ASR words and authored turn boundaries."""
    asr = load_asr_words()
    transcript_parts: list[str] = []
    cursor = 0
    turns: list[Turn] = []

    for tid, cluster, role, first, last in TURN_BOUNDS:
        raw = asr[first : last + 1]
        # mlx-whisper emits " metoprolol" with a leading space. 1a's contract
        # says Word.text carries none and char_offset points at the first real
        # character; this strip-and-shift IS the B4 assertion, and Phase 0
        # confirmed the leading space empirically before we got here.
        tokens = [w["word"].strip() for w in raw]
        text = " ".join(tokens)
        if transcript_parts:
            cursor += 1  # the space joining this turn to the previous one
        char_start = cursor

        words: list[Word] = []
        within = 0
        for token, w in zip(tokens, raw):
            i = text.index(token, within)
            within = i + len(token)
            words.append(
                Word(
                    text=token,
                    start=w["start"],
                    end=w["end"],
                    probability=w["probability"],
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
                start=raw[0]["start"],
                end=raw[-1]["end"],
                words=words,
                text=text,
                char_start=char_start,
                char_end=cursor,
            )
        )

    return Session(
        visit_date=VISIT_DATE,
        session_dir=SESSION_DIR,
        audio_path=SESSION_DIR / "visit.m4a",
        transcript_text=" ".join(transcript_parts),
        turns=turns,
        consent=Consent(
            obtained=True,
            method="verbal",
            # D27 — before recording. Turn 0 is t=0 of the audio.
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
    mention = q("the metoprolol up to 50 milligrams")
    prior_dose = q("25 milligrams")                   # turn 10, the baseline
    new_dose = q("up to 50 milligrams")               # turn 12, the change
    unknown_dose = q("two of the 25s")                # turn 19, role=unknown
    later_sig = q("twice a day with food")            # turn 20, cat 8
    contradiction = q("the metoprolol, 25, twice a day")  # turn 28
    # The ASR heard the drug correctly here; it is LISINOPRIL that came back
    # mistranscribed, three separate ways. See the lisinopril item below.
    low_confidence_dose = q("the 50 make me more tired")  # turn 23, p=0.14

    metoprolol = {
        "id": "med-metoprolol",
        "kind": "medication",
        "disposition": "blocking",
        "d16_categories": [2, 3, 7, 8],
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
                # D16 cat 2. The one the script planted at the BP reading did
                # not land — the actor read "sixty-two" and Whisper heard it
                # correctly. This one landed for free, and it is the better
                # case: a DOSE numeral at p=0.14, in a patient turn.
                "d16_category": 2,
                "blocking": False,
                "reason": "dose numeral transcribed with low confidence",
                "render": "expanded",
                "min_word_probability": 0.14,
                "evidence": [low_confidence_dose],
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
        # The doctor said "lisinopril"; Whisper wrote "lisonopril". Every
        # confidence signal is high — only the knowledge base catches this.
        "mention_quote": q("the lisonopril at 10"),
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
            "match_type": "fuzzy",
            "edit_distance": 1,
            "match_confidence": 0.91,
            "heard_text": "lisonopril",
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
                "quote": q("Just take it the way you've been taking it"),
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
                # TOOLS §1: resolved + fuzzy + edit_distance <= 2 -> prefilled
                # and flagged, showing BOTH heard and resolved. "You said
                # lisonopril, we matched lisinopril" is the knowledge base
                # catching an ASR error that every confidence signal missed —
                # two of the three mistranscriptions came back at p=1.00.
                "d16_category": None,
                "blocking": False,
                "reason": "likely mistranscription — heard 'lisonopril', matched 'lisinopril'",
                "render": "expanded",
                "heard_text": "lisonopril",
                "resolved_name": "lisinopril",
                "edit_distance": 1,
                "other_spellings_in_visit": ["lysinopril", "lysinop,", "lyso,"],
            },
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
            "quote": q("about 10 days"),
            "status": "resolved",
            "resolved_date": "2026-09-28",
            "range_start": None,
            "range_end": None,
            "precision": "exact_day",
            "direction": "future",
            "anchor_date": VISIT_DATE.isoformat(),
            "anchor_source": "session_visit_date",
            "original_phrase": "about 10 days",
            # D18: BOTH forms. A patient reading a bare date cannot catch an
            # error; reading both lets them. Ten days, not two weeks —
            # multiples of seven from this weekend print a weekend.
            "display_string": "about 10 days from today, which is Monday, September 28",
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
            "topic_quote": q("we may need to adjust the lysinopril as well"),
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
                q("that's higher than I want to see"),
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

#: Where the ASR got it wrong. The transcript (left) is what Whisper wrote;
#: the script (right) is what was actually said. Applied in reverse when
#: rendering the script, so the script stays a record of the SPEECH.
#:
#: Every one of these is lisinopril. Metoprolol came back correct all three
#: times. Two of these were emitted at p=1.00 — confidence gave no warning at
#: all, which is exactly why resolve_medication exists.
MISTRANSCRIBED = {
    10: [("lisonopril", "lisinopril")],
    15: [("lyso, ly, lysinop, lysinopril", "liso, li, lisinop, lisinopril")],
    18: [("lysinopril", "lisinopril")],
    28: [("lysinopril", "lisinopril")],
}

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


def render_script_block(session: Session | None = None) -> str:
    session = session or build_session()
    lines = [
        BEGIN,
        "",
        "*Generated from the committed ASR output by "
        "`fixtures/build_golden.py`. This is a transcript of the take that "
        "exists, not a script to perform from scratch — re-run "
        "`python fixtures/build_golden.py --script` after changing "
        "`TURN_BOUNDS`. Editing this block by hand makes the script and the "
        "fixture disagree.*",
        "",
    ]
    for turn in session.turns:
        mm, ss = divmod(int(turn.start), 60)
        lines.append(
            f"**T{turn.id}** · {mm:02d}:{ss:02d} · "
            f"**{SPEAKER_LABEL[turn.speaker_cluster]}:** "
            f"{spoken_text(turn.id, turn.text)}"
        )
        tid = turn.id
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
