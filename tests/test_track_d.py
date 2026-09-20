"""Track D's done-when list, as tests (U1-U10).

Each test names the step it defends. A UI is easy to eyeball into looking
right, and the failures that matter here are invisible ones: a collapsed
category-8 flag, a discarded count nobody prints, a shred that missed the log
sitting beside the audio. So they are asserted rather than demoed.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from mnemonica.contracts import Consent, Session
from mnemonica.render import actioncard, fhir
from mnemonica.render.audio import cue_for, words_in
from mnemonica.render.document import render_patient_document
from mnemonica.render.model import Extraction, Resolution, item_is_resolved
from mnemonica.render.review import ReviewFlag, build_review, header_line
from mnemonica.render.summary import HEADINGS, build_summary
from mnemonica.ui import retention, state

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"


@pytest.fixture(scope="module")
def session() -> Session:
    return Session.model_validate_json((FIXTURES / "golden_visit.json").read_text())


@pytest.fixture(scope="module")
def extraction() -> Extraction:
    return Extraction.load(FIXTURES / "golden_extraction.json")


@pytest.fixture
def rows(extraction, session):
    return build_review(extraction, session, clinician_name="Dr. Kovak")


# -- the fixture itself ---------------------------------------------------


def test_computed_header_matches_the_fixtures_own_counts(full_scope, extraction):
    """If these two ever disagree, the fixture's `header` block is wrong and
    the UI must not quietly print either number."""
    assert extraction.header() == extraction.recorded_header


def test_every_quote_still_lands_on_its_own_text(extraction, session):
    """D14, re-run at render time. Stale offsets are how a citation points at
    the wrong characters without anything raising."""
    for item in extraction.items:
        for quote in item.all_quotes():
            assert quote.verify_against(session), f"{item.id}: {quote.text!r}"
    for quotes in extraction.summary_quotes.values():
        for quote in quotes:
            assert quote.verify_against(session)


# -- U3: the review list --------------------------------------------------


def test_exactly_one_item_demands_attention(rows):
    blocking = [r for r in rows if r.blocking]
    assert [r.id for r in blocking] == ["med-metoprolol"]


def test_blocking_items_come_first(rows):
    assert rows[0].blocking


def test_verified_items_collapse(rows):
    """D9's whole budget. An item with no flags must not be open."""
    for row in rows:
        if not row.item.flags:
            assert not row.expanded, f"{row.id} has no flags but renders expanded"


def test_category_8_renders_expanded_even_though_it_is_not_blocking(extraction, rows):
    """The failure span verification structurally cannot catch does not get to
    hide inside the collapsed section."""
    item = extraction.item("med-metoprolol")
    cat8 = [f for f in item.flags if f.d16_category == 8]
    assert cat8, "the fixture's category-8 plant is gone"
    assert all(f.render == "expanded" for f in cat8)
    assert not cat8[0].blocking
    assert next(r for r in rows if r.id == item.id).expanded


def test_the_header_shows_the_discarded_count(full_scope, extraction):
    """D16 category 1 is silent about the item and loud about the number."""
    line = header_line(extraction)
    assert "1 discarded" in line
    assert "3 confirmed" in line
    assert "1 needs your ear" in line


def test_the_discarded_text_is_never_rendered(extraction):
    """It was fabricated. Showing it invites someone to rescue it."""
    for discarded in extraction.discarded:
        assert not hasattr(discarded, "text")
        assert set(vars(discarded)) == {
            "d16_category",
            "kind",
            "reason",
            "dropped_at",
        }


def test_category_5_is_not_an_error(extraction, rows):
    """*"as directed"* resolves to *not specified*. The item is flagged, not
    blocking, and the flag collapses — it is the most likely of the eight to
    regress into looking like a failure."""
    item = extraction.item("med-lisinopril")
    assert not item.is_blocking
    flag = next(f for f in item.flags if f.d16_category == 5)
    assert flag.render == "collapsed"
    assert flag.display == "not specified"
    row = next(r for r in rows if r.id == item.id)
    text = " ".join(s.plain() for s in row.sentences)
    assert "no change was discussed" in text


def test_category_4_offers_the_raw_text_and_near_matches(extraction, rows):
    item = extraction.item("med-unresolved-bp-pill")
    flag = next(f for f in item.flags if f.d16_category == 4)
    assert flag.heard_text == "the other blood pressure pill"
    assert flag.render == "expanded"
    row = next(r for r in rows if r.id == item.id)
    assert "the other blood pressure pill" in " ".join(
        s.plain() for s in row.sentences
    )


def test_contradiction_shows_both_values_with_timestamps(rows):
    """D16 category 7 — both, with times, and nothing pre-selected."""
    row = next(r for r in rows if r.id == "med-metoprolol")
    flag = next(f for f in row.flags if f.d16_category == 7)
    assert flag.blocking
    assert len(flag.evidence) == 2
    # Two distinct moments, each playable. The values themselves come from the
    # fixture, which is regenerated whenever the recording is.
    assert all(e.cue is not None for e in flag.evidence)
    assert len({e.cue.start for e in flag.evidence}) == 2
    assert len(flag.options) == 2
    assert flag.chosen is None
    assert all(o.cue is not None for o in flag.options), (
        "the doctor has to hear both doses before committing to one"
    )


def test_loose_thread_gets_its_own_row(full_scope, extraction, rows):
    """D16 category 6. Counted separately from the confirm queue so it does
    not inflate the number the clinician reads as work."""
    row = next(r for r in rows if r.kind == "loose_thread")
    assert row.expanded
    assert not row.blocking
    assert extraction.header()["loose_threads"] == 1
    assert extraction.header()["needs_confirmation"] == 2


def test_a_question_is_asked_in_the_doctors_language(rows):
    """Not Track C's. *"dose stated in a turn with no confident speaker role"*
    is correct and is not something to read with a patient in the chair."""
    from mnemonica.render.review import QUESTIONS

    asked = [f.question for row in rows for f in row.flags]
    assert asked
    for question in asked:
        assert len(question) < 80, question
    row = next(r for r in rows if r.id == "med-metoprolol")
    assert next(f for f in row.flags if f.d16_category == 7).question == QUESTIONS[7]


def test_category_8_is_recorded_but_stays_off_the_glass(rows):
    """It fired on every row of the demo, three times on one, and a warning
    that is always on is read as chrome. Held back from the screen by
    explicit instruction — the flag, its two quotes and their audio are
    still built, so the extraction and the FHIR copy are unchanged and
    putting it back is one predicate."""
    row = next(r for r in rows if r.id == "med-metoprolol")
    cat8 = next(f for f in row.flags if f.d16_category == 8)
    assert cat8.bookkeeping
    assert cat8 not in row.questions and cat8 not in row.notes
    assert len(cat8.evidence) == 2, "both quotes, side by side"
    assert all(e.cue for e in cat8.evidence)


def test_an_unparsed_dose_remainder_stays_off_the_glass(rows):
    """The span the grammar could not parse is already on the screen. The
    note only adds a more alarming way to read a line already shown."""
    flag = ReviewFlag(
        index=0, d16_category=None, blocking=False,
        question='a dose was spoken but not fully parsed: “25”',
        render="collapsed", evidence=[], options=[], chosen=None,
        merge_target=None,
    )
    assert flag.bookkeeping
    row = next(r for r in rows if r.id == "med-metoprolol")
    row.flags.append(flag)
    assert flag not in row.questions and flag not in row.notes
    assert flag in row.flags, "still recorded, only hidden"


def test_category_3_reads_correctly_for_a_patient_turn(rows):
    """It fires for two situations. "We couldn't place the voice" is wrong
    about a turn we placed confidently as the patient."""
    unresolved = next(r for r in rows if r.id == "med-unresolved-bp-pill")
    cat3 = next(f for f in unresolved.flags if f.d16_category == 3)
    assert cat3.question == "The patient said this, not the doctor."

    blocking = next(r for r in rows if r.blocking)
    unplaced = next(f for f in blocking.flags if f.d16_category == 3)
    assert "couldn\u2019t place" in unplaced.question


def test_pipeline_bookkeeping_stays_off_the_glass(rows):
    """The screen already asks about an underived change_kind in its own
    words; repeating it in Track C's is noise."""
    row = next(r for r in rows if r.id == "med-lisinopril")
    assert any(f.bookkeeping for f in row.flags)
    assert not any(f.question.startswith("change_kind") for f in row.notes)


def test_a_note_is_not_dressed_up_as_a_question(rows):
    """Category 5 has nothing to answer. Giving it the same frame as a
    blocking contradiction is what makes the most-correct row in the table
    look like a failure."""
    row = next(r for r in rows if r.id == "med-lisinopril")
    quiet = [f for f in row.flags if f.quiet]
    assert quiet
    assert all(f.d16_category != 7 for f in quiet)
    assert row.notes and not any(f.blocking for f in row.notes)


def test_a_clean_row_carries_no_status_word(rows):
    """Nothing in the corner means nothing to do."""
    for row in rows:
        if not row.item.flags:
            assert row.status == ""


def test_a_blocking_row_says_so_in_a_word(rows):
    row = next(r for r in rows if r.blocking)
    assert row.status == "needs you"


# -- U4: audio ------------------------------------------------------------


def test_a_flagged_line_cues_to_the_uncertain_word(extraction, session):
    """Not to the start of the turn. If a dose numeral came back weak inside a
    confident sentence, that word is what the doctor needs to hear."""
    item = extraction.item("med-metoprolol")
    flag = next(f for f in item.flags if f.d16_category == 7)
    weak = flag.evidence[1]  # 'the metropolol, twenty-five, twice a day', p=0.66
    cue = cue_for(session, weak, flagged=True)
    assert cue is not None
    assert cue.focus_probability == min(
        w.probability for w in words_in(session, weak)
    )
    assert cue.start <= cue.focus < cue.end
    assert cue.duration < 4.0, "a cue longer than a few seconds is not a cue"


def test_a_verified_line_cues_to_its_whole_span(full_scope, extraction, session):
    quote = extraction.item("flag-dizzy").primary_quote
    cue = cue_for(session, quote, flagged=False)
    words = words_in(session, quote)
    assert cue.start == pytest.approx(min(w.start for w in words) - 0.35)
    assert cue.end == pytest.approx(max(w.end for w in words) + 0.25)


def test_every_row_can_be_played(rows):
    for row in rows:
        if row.quote_text:
            assert row.cue is not None, f"{row.id} has a quote but no cue"


# -- U5: resolution -------------------------------------------------------


def test_blocking_item_is_unresolved_until_every_blocking_flag_is_answered(
    extraction,
):
    item = extraction.item("med-metoprolol")
    blocking = [i for i, f in enumerate(item.flags) if f.blocking]
    assert len(blocking) == 2

    res = Resolution(item_id=item.id)
    assert not item_is_resolved(item, res)
    res.choices[blocking[0]] = item.flags[blocking[0]].options()[0]
    assert not item_is_resolved(item, res), "one of two answered is not resolved"
    res.choices[blocking[1]] = item.flags[blocking[1]].options()[0]
    assert item_is_resolved(item, res)


def test_dropping_an_item_counts_as_answering_it(extraction):
    item = extraction.item("med-metoprolol")
    assert item_is_resolved(item, Resolution(item_id=item.id, dropped=True))


def test_non_blocking_items_never_gate_approval(extraction):
    for item in extraction.items:
        if not item.is_blocking:
            assert item_is_resolved(item, None)


# -- U6: the action card --------------------------------------------------


def test_underived_change_kind_is_flagged_not_printed(extraction):
    """A closed enum guarantees well-formed, not correct — and this is the
    headline sentence."""
    item = extraction.item("med-lisinopril")
    assert item.raw["change_kind_derived"] is False
    sentences = actioncard.medication_sentences(item, "Dr. Kovak")
    assert not any(s.needs_promotion for s in sentences), (
        "'continued' is not a directional claim; only increased/decreased "
        "need promotion"
    )


def test_derived_change_kind_prints_both_doses(extraction):
    item = extraction.item("med-metoprolol")
    sentences = actioncard.medication_sentences(item, "Dr. Kovak")
    headline = sentences[0]
    assert not headline.needs_promotion
    assert headline.plain() == (
        "Dr. Kovak increased your metoprolol from 25 mg to 50 mg."
    )


def test_an_underived_direction_needs_the_clinicians_click(extraction):
    """The synthetic case the fixture does not carry: same item, derivation
    removed. Without promotion the sentence is held back."""
    item = extraction.item("med-metoprolol")
    raw = json.loads(json.dumps(item.raw))
    raw["change_kind_derived"] = False
    from mnemonica.render.model import Item

    underived = Item.parse(raw)
    held = actioncard.medication_sentences(underived, "Dr. Kovak")[0]
    assert held.needs_promotion
    promoted = actioncard.medication_sentences(
        underived, "Dr. Kovak", promoted=True
    )[0]
    assert not promoted.needs_promotion


def test_no_prior_dose_changes_the_sentence_shape(extraction):
    """Nothing here reads a chart, so *"from 25 mg"* exists only if it was
    said aloud. The variant must not leave a blank or invent a baseline."""
    item = extraction.item("med-metoprolol")
    raw = json.loads(json.dumps(item.raw))
    raw["change_kind_derivation"]["from_dose"] = None
    from mnemonica.render.model import Item

    no_baseline = Item.parse(raw)
    text = actioncard.medication_sentences(no_baseline, "Dr. Kovak")[0].plain()
    assert text == "Dr. Kovak changed your metoprolol to 50 mg."
    assert "from" not in text


def test_salt_ambiguity_reaches_the_patient(extraction):
    """A5.5's plant. Bare "metoprolol" resolves, but succinate and tartrate are
    different dosing schedules, so the label check prints."""
    item = extraction.item("med-metoprolol")
    text = " ".join(
        s.plain() for s in actioncard.medication_sentences(item, "Dr. Kovak")
    )
    assert "metoprolol succinate or metoprolol tartrate" in text


def test_dates_print_both_forms_with_a_recomputed_weekday(full_scope, extraction):
    """D18. Printing both forms exists so a patient can catch a mismatch; a UI
    that copies the resolver's precomputed string can only repeat its error."""
    item = extraction.item("appt-followup")
    text = actioncard.appointment_sentence(item).plain()
    resolved = date.fromisoformat(item.raw["when"]["resolved_date"])
    assert f'{item.raw["when"]["original_phrase"]} from today' in text
    assert resolved.strftime("%A") in text
    assert f"{resolved.strftime('%B')} {resolved.day}" in text


def test_sigs_are_never_merged_across_turns(extraction):
    """Combining a dose from turn 12 with a frequency from turn 20 is exactly
    the smear D16 category 8 exists to catch. A template must not do it
    silently."""
    item = extraction.item("med-metoprolol")
    sig = actioncard._select_sig(item)
    quote = sig["quote"]
    for field in ("dose_amount", "frequency_per_day"):
        if sig.get(field) is not None:
            assert sig["quote"]["turn_id"] == quote["turn_id"]


# -- U7: the summary ------------------------------------------------------


def test_summary_headings_are_fixed_and_every_line_is_a_quote(
    extraction, session
):
    sections = build_summary(extraction, session)
    assert [s.heading for s in sections] == list(HEADINGS.values())
    for section in sections:
        for line in section.lines:
            assert line.quote.text in session.transcript_text


def test_patient_attribution_is_hedged_when_b6_saw_a_third_voice(
    extraction, session
):
    """`role` is only clinician/other/unknown. With an adult child in the room,
    "Why you came in" can print their words as the patient's."""
    calm = build_summary(extraction, session, unexpected_speaker=False)[0]
    assert calm.lines[0].speaker_label == "You said"
    hedged = build_summary(extraction, session, unexpected_speaker=True)[0]
    assert hedged.lines[0].speaker_label == "Someone in the room said"


def test_a_stale_quote_is_dropped_rather_than_printed(extraction, session):
    from mnemonica.render.model import Quote

    broken = Quote(
        text="a line nobody said",
        char_offset=0,
        char_end=18,
        turn_id=0,
        turn_role="clinician",
        audio_start=0.0,
        min_word_probability=0.9,
    )
    doctored = Extraction(
        visit_date=extraction.visit_date,
        medications=[],
        appointments=[],
        red_flags=[],
        loose_threads=[],
        discarded=[],
        summary_quotes={"what_happens_next": [broken]},
        recorded_header={},
    )
    sections = build_summary(doctored, session)
    assert all(not s.lines for s in sections)


# -- U8: the printed page -------------------------------------------------


@pytest.fixture
def document(extraction, session) -> str:
    return render_patient_document(
        extraction,
        session,
        clinician_name="Dr. Ellery Kovak",
        approved_on=date(2026, 9, 19),
    )


def test_the_footer_names_the_clinician_the_date_and_the_consent(document):
    document = " ".join(document.split())  # the template wraps; the page does not
    assert "reviewed by Dr. Ellery Kovak" in document
    assert "Saturday, September 19, 2026" in document
    assert "verbal consent" in document
    assert "Friday, September 18, 2026" in document  # the consent's own date


def test_no_heading_appears_twice(document):
    """Two identical <h2>s on a page read at arm's length is the small
    confusion this document exists to avoid."""
    import re

    headings = re.findall(r"<h2>(.*?)</h2>", document, re.S)
    assert len(headings) == len(set(headings)), headings


def test_no_ai_banner(document):
    """D10 — it manufactures the exact distrust the product dissolves, and by
    the time this prints a doctor has attested to every line."""
    lowered = document.lower()
    for phrase in ("ai generated", "ai-generated", "artificial intelligence",
                   "generated by", "language model"):
        assert phrase not in lowered


def test_the_patients_copy_carries_no_audio_affordance(document):
    """D8, Collision 1. Provenance is the doctor's review tool; the paper
    carries the doctor's authority, not the model's confidence."""
    for token in ("<audio", "playback", "listen", "/audio", "review.js"):
        assert token not in document.lower()


def test_body_type_is_at_least_18px(document):
    import re

    body = re.search(r"body\s*\{[^}]*\}", document, re.S).group(0)
    size = re.search(r"font:\s*(\d+)px", body)
    assert size and int(size.group(1)) >= 18


def test_nothing_on_the_page_was_written_by_the_model(full_scope, document, session):
    """Every sentence is either a template of ours or a verbatim span. The
    only model-authored artefacts in the pipeline are *selections*."""
    import re
    from html import unescape

    quotes = re.findall(r"&ldquo;(.*?)&rdquo;", document, re.S)
    assert quotes, "the page should carry verbatim spans"
    for quote in quotes:
        assert unescape(quote) in session.transcript_text


def test_a_dropped_item_does_not_print(extraction, session):
    dropped = {"flag-dizzy": Resolution(item_id="flag-dizzy", dropped=True)}
    html = render_patient_document(
        extraction, session, clinician_name="Dr. Kovak", resolutions=dropped
    )
    assert "If you feel dizzy when you stand up" not in html


def test_an_unresolved_blocking_item_cannot_reach_the_page(extraction, session):
    html = render_patient_document(
        extraction, session, clinician_name="Dr. Kovak", resolutions={}
    )
    assert "increased your" not in html, (
        "metoprolol is blocking and unresolved; it must not print"
    )


# -- U9: approve ----------------------------------------------------------


@pytest.fixture
def live_session(tmp_path, monkeypatch) -> state.ReviewSession:
    monkeypatch.setattr(state, "SESSIONS_ROOT", tmp_path / "sessions")
    monkeypatch.setattr(state, "RECORDS_ROOT", tmp_path / "records")
    current = state.ReviewSession(session_id="test0001")
    current.give_consent(method="verbal")
    current.load_fixture()
    return current


def test_recording_cannot_start_without_consent():
    fresh = state.ReviewSession(session_id="nope")
    with pytest.raises(state.ConsentRequired):
        fresh.start_recording()
    with pytest.raises(state.ConsentRequired):
        fresh.give_consent(method="verbal", obtained=False)


def test_consent_reaches_the_review_stage(live_session):
    assert live_session.stage == "review"
    assert live_session.consent.obtained is True


def test_approve_is_refused_while_anything_blocks(live_session):
    assert live_session.unresolved() == ["med-metoprolol"]
    assert not live_session.can_approve
    with pytest.raises(state.StillBlocking):
        live_session.approve()


def _settle(current: state.ReviewSession) -> None:
    item = current.extraction.item("med-metoprolol")
    for index, flag in enumerate(item.flags):
        if flag.blocking:
            current.resolve(item.id, index, flag.options()[0])


def test_approve_shreds_the_audio_and_the_logs(live_session):
    """D2/D3 — the unit of retention is the directory. A dropped-quote log
    line carries transcript text, so `unlink(audio_path)` shreds the recording
    and leaves the PHI sitting beside it."""
    (live_session.session_dir / "visit.wav").write_bytes(b"RIFF" + b"\0" * 2048)
    (live_session.session_dir / "scratch.txt").write_text("ffmpeg leftovers")
    _settle(live_session)

    result = live_session.approve()

    assert not live_session.session_dir.exists()
    assert {"visit.wav", "review.log", "scratch.txt"} <= set(result.shredded)
    assert result.document_path.exists()


def test_the_chart_copy_holds_the_exact_bytes_we_printed(live_session):
    """D26. Not "byte-identical to a sheet of paper" — one render, two
    destinations, no second code path to drift."""
    import base64

    _settle(live_session)
    result = live_session.approve()

    resource = json.loads(result.fhir_path.read_text())
    attachment = resource["content"][0]["attachment"]
    stored = base64.b64decode(attachment["data"]).decode("utf-8")
    assert stored == result.document_html
    assert stored == result.document_path.read_text()
    assert attachment["size"] == len(result.document_html.encode("utf-8"))


def test_the_chart_copy_survives_the_shred(live_session):
    _settle(live_session)
    result = live_session.approve()
    assert result.fhir_path.exists()
    assert not result.fhir_path.is_relative_to(live_session.session_dir)


def test_a_resolved_contradiction_prints_the_doctors_choice(live_session):
    _settle(live_session)
    result = live_session.approve()
    assert "metoprolol" in result.document_html


def test_the_fixture_directory_is_never_shreddable(tmp_path):
    with pytest.raises(ValueError):
        retention.shred(FIXTURES / "sessions" / "golden", root=tmp_path)


def test_the_sessions_root_itself_is_never_shreddable(tmp_path):
    with pytest.raises(ValueError):
        retention.shred(tmp_path, root=tmp_path)


# -- U10: expiry ----------------------------------------------------------


def _session_dir(root: Path, name: str, *, age_hours: float) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "visit.wav").write_bytes(b"\0" * 512)
    (directory / "extraction.json").write_text('{"medications": []}')
    old = (datetime.now() - timedelta(hours=age_hours)).timestamp()
    import os

    os.utime(directory, (old, old))
    return directory


def test_an_unapproved_session_expires_after_24_hours(tmp_path):
    stale = _session_dir(tmp_path, "stale", age_hours=25)
    fresh = _session_dir(tmp_path, "fresh", age_hours=2)

    result = retention.sweep_expired(tmp_path)

    assert result.swept == ["stale"]
    assert not stale.exists()
    assert fresh.exists()


def test_the_sweep_takes_the_extracted_data_too(tmp_path):
    """A structured list of someone's medications is PHI without the
    recording. Deleting the audio and keeping the JSON is a compression step,
    not a retention policy."""
    stale = _session_dir(tmp_path, "stale", age_hours=48)
    retention.sweep_expired(tmp_path)
    assert not (stale / "extraction.json").exists()
    assert not stale.exists()


def test_the_precomputed_demo_session_survives(tmp_path):
    """4a builds the long file the night before. Without this exemption the
    sweep deletes the demo, on demo day, silently."""
    demo = _session_dir(tmp_path, "demo-long-visit", age_hours=30)
    retention.mark_demo_fixture(demo)

    result = retention.sweep_expired(tmp_path)

    assert result.kept_demo == ["demo-long-visit"]
    assert demo.exists()
    assert (demo / "visit.wav").exists()


def test_the_policy_has_no_third_case(tmp_path):
    """*"Audio exists until the doctor signs, or 24 hours, whichever comes
    first."* Anything still on disk after a sweep is under 24h or flagged."""
    _session_dir(tmp_path, "stale", age_hours=25)
    _session_dir(tmp_path, "fresh", age_hours=1)
    retention.mark_demo_fixture(_session_dir(tmp_path, "demo", age_hours=99))

    retention.sweep_expired(tmp_path)

    survivors = {p.name for p in tmp_path.iterdir() if p.is_dir()}
    assert survivors == {"fresh", "demo"}


# -- Phase 3: what the fixture could not show ----------------------------
#
# Every case below was found by 3b's first end-to-end run on real audio and
# was invisible on the fixture — not because the fixture is wrong, but because
# it only ever carried `continued` and `increased`, and was never carried
# through an approval with a settled contradiction.


def test_a_settled_contradiction_decides_the_printed_dose(extraction):
    """The real run printed *"from 25 mg to 50 mg"* and *"The dose is 25 mg"*
    on one card, because sig selection never saw the clinician's answer.

    Category 7's options *are* the competing sig quotes, so settling it is the
    clinician naming the instruction. Nothing may then print a different one.
    """
    item = extraction.item("med-metoprolol")
    cat7 = next(i for i, f in enumerate(item.flags)
                if f.blocking and f.d16_category == 7)
    chosen = item.flags[cat7].options()[1]

    res = Resolution(item_id=item.id, choices={cat7: chosen})
    text = " ".join(
        s.plain()
        for s in actioncard.medication_sentences(
            item, "Dr. Kovak", resolution=res
        )
    )
    sig = next(s for s in item.raw["sig"]
               if s["quote"]["text"] == chosen)
    losing = [s for s in item.raw["sig"] if s["quote"]["text"] != chosen
              and s.get("dose_amount")]
    for other in losing:
        assert f"The dose is {other['dose_amount']:g} mg" not in text, (
            "a dose the clinician did not choose reached the patient's page"
        )
    if sig.get("frequency_per_day"):
        assert "twice a day" in text


def test_no_headline_ever_leaves_the_drug_unnamed(extraction):
    """`change_kind` is a six-value enum; the card handled four of them.

    `unchanged` and `new` fell through to no headline at all, and the real run
    printed *"How to take it: no change was discussed"* with no drug attached.
    A patient cannot act on an instruction about an unnamed medicine, so every
    value of the enum — and anything outside it — must name the drug.
    """
    from mnemonica.render.model import Item

    # lisinopril, not metoprolol: metoprolol carries a salt flag, and that
    # sentence names the drug by coincidence, so the fixture's headline drug
    # passes this test even with the headline missing entirely. The item that
    # exposed the bug on real audio is the one with nothing else to fall back
    # on.
    item = extraction.item("med-lisinopril")
    kinds = ["new", "increased", "decreased", "stopped", "continued",
             "unchanged", "something-the-model-invented", None]
    for kind in kinds:
        raw = json.loads(json.dumps(item.raw))
        raw["change_kind"] = kind
        sentences = actioncard.medication_sentences(Item.parse(raw), "Dr. Kovak")
        assert sentences, f"{kind!r} produced no sentences at all"
        assert "lisinopril" in sentences[0].plain(), (
            f"{kind!r} left the drug unnamed"
        )
