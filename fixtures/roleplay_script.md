# Role-play script — 1d

**Do not record a real appointment.** No BAA exists anywhere in this stack.
Role-play means we never create PHI (PRESENTATION-NOTES item 3).

**Two speakers only** (D19, SPEC §6). v1 pins `num_speakers=2`; a third voice
is silently merged into an existing cluster, not detected.

| | |
|---|---|
| **Runtime** | ~3 min 32 s · 35 turns · 461 words |
| **Speakers** | `SPEAKER_00` Dr. Amara Osei (clinician) · `SPEAKER_01` Ray Delgado, 71 (patient) |
| **Visit date** | **Friday, 18 September 2026** — see *Dates* below |
| **Mirrors** | `fixtures/golden_visit.json` — generated from the same `TURNS` list |

---

## Drugs — verified against this RxNorm release

Checked before recording, not after. Nothing is more annoying than finding at
hour 20 that your hero drug is a suppressed entry.

| Spoken | RXCUI | TTY | Note |
|---|---|---|---|
| metoprolol | 6918 | `IN` | spoken **bare** throughout — no salt named |
| metoprolol succinate | 221124 | `PIN` | never spoken; this is the point |
| metoprolol tartrate | 203191 | `PIN` | never spoken; this is the point |
| lisinopril | 29046 | `IN` | |

All four are `SAB=RXNORM`, `SUPPRESS != 'O'`.

**Nobody says a salt, ever.** That is deliberate: `metoprolol` alone hits the
bare `IN` on exact lookup and returns `resolved` / `match_type="exact"` — a
confident answer that hides the difference between once-daily ER (succinate)
and twice-daily IR (tartrate). A5.5 is the flag that catches it, and this
script is what proves it fires.

## Dates — checked against a calendar

Any whole number of weeks from a Saturday is a Saturday, and the hackathon is
Sept 19–20, both weekend days. So the follow-up interval is **ten days**, not
"two weeks":

| Anchor | +10 days | |
|---|---|---|
| Fri 18 Sep 2026 (pinned `visit_date`) | **Mon 28 Sep 2026** | weekday |
| Sat 19 Sep 2026 (if a real mtime wins) | Tue 29 Sep 2026 | weekday |
| Sun 20 Sep 2026 (if recorded Sunday) | Wed 30 Sep 2026 | weekday |

Non-multiples of seven survive whichever anchor D18 actually reads. The script
also contains one **past** reference ("back in June") so `resolve_date`'s
backward direction is exercised, not assumed.

---

## What each turn is planting

Every D16 category, one script line, so the fixture doubles as the test plan.

| D16 | Turn | Plant |
|---|---|---|
| 1 fabrication | — | not plantable; C4 provokes it with a fake quote |
| 2 low confidence | **T9** | `162` spoken over a chair scrape → `probability` ≈ 0.4 |
| 3 ambiguous attribution | **T19** | crosstalk; patient says a dose, `role="unknown"` |
| 4 unresolved drug | **T11** | "the other blood pressure pill" |
| 5 not specified | **T16** | "just take it the way you've been taking it" |
| 6 loose thread | **T18** | "we may need to adjust the lisinopril too" — never revisited |
| 7 contradiction | **T12 / T28** | metoprolol **50 mg** at 1:11, **25 mg** at 2:58 |
| 8 cross-turn association | **T12 → T20** | "that one's twice a day" lands 8 turns after the metoprolol mention, with lisinopril the nearest drug named in between and **no drug named after it** |
| fuzzy match | **T28** | `metropolol` — expected mistranscription (see below) |
| salt unspecified | all | bare "metoprolol", no salt, ever |
| red flag | **T26 / T30** | "call the office" |
| appointment | **T22** | ten days, purpose stated |
| past date | **T5** | "back in June" |
| consent (D27) | **T0/T1** | captured on tape before anything else |

**T28 is the sharp one, and it is two plants at once.** The doctor, thinking
of the old regimen, says a dose that contradicts T12 — *and* it is the turn
where a mistranscription is most likely. `25` twice a day and `50` once a day
are clinically near-identical, which is exactly why a human skims past it. The
system must not.

**The fuzzy match is a prediction, not a line to perform.** Say *metoprolol*
correctly every time. `metropolol` is what we expect Whisper to emit at T28,
where it is said fast and mid-sentence, and the fixture plants it there as the
prediction. If the real transcript comes back clean, that is a pass for Track B
and the fuzzy path still has its unit test — do **not** re-record to force an
error in.

---

## Script

Stage directions are in *italics* and are not spoken. Say the disfluencies —
the "um"s, the restarts, the half-overlaps are written in on purpose. A clean
script makes accuracy look fake-good and then collapses on stage.

---

<!-- BEGIN GENERATED DIALOGUE -->

*Generated from `fixtures/build_golden.py`. Edit the `TURNS` list there and re-run `python fixtures/build_golden.py --script`; editing this block by hand is how the script and the fixture drift apart.*

**T0** · 00:00 · **DR. OSEI:** Morning, Ray. Before we get started, I'd like to record this visit so you go home with a written summary. Nothing leaves this laptop. Is that alright with you?

**T1** · 00:08 · **RAY:** Yeah, that's fine by me.

**T2** · 00:11 · **DR. OSEI:** Thank you. Okay, recording now.

**T3** · 00:14 · **RAY:** Do I need to, uh, do I need to sign something?

**T4** · 00:17 · **DR. OSEI:** No, saying yes is enough, I've got it noted. So how have things been?

**T5** · 00:23 · **RAY:** Not bad. The headaches I had back in June, those are, those are mostly gone now. And I've been checking the pressure at home, like you asked.

**T6** · 00:33 · **DR. OSEI:** Good, that's what I like to hear. What kind of numbers are you getting?

**T7** · 00:37 · **RAY:** Um, mostly one fifty over ninety. Ninety-two, sometimes.

**T8** · 00:44 · **DR. OSEI:** Mm-hm.

**T9** · 00:46 · **RAY:** One morning it was one sixty-two. That one scared me a little.

> *Recording note: Make noise across "sixty-two" — scrape the chair, or cough. This is the D16 category 2 plant and the per-word probability has to actually drop. Do not enunciate it.*

**T10** · 00:55 · **DR. OSEI:** Okay. That's higher than I want to see. Right now you're taking the metoprolol, twenty-five milligrams, and the lisinopril at ten.

**T11** · 01:04 · **RAY:** The little white one, yeah. And the, the other blood pressure pill, I don't know what that one's called.

**T12** · 01:11 · **DR. OSEI:** That's the lisinopril. So what I'd like to do is bring the metoprolol up to fifty milligrams.

**T13** · 01:19 · **RAY:** Fifty. Okay.

**T14** · 01:22 · **DR. OSEI:** Your heart rate's got room for it, and the headaches coming back would be the thing I'd worry about otherwise.

**T15** · 01:29 · **RAY:** And the other one? The lisinopril?

**T16** · 01:33 · **DR. OSEI:** That one doesn't change, just take it the way you've been taking it.

**T17** · 01:38 · **RAY:** Okay.

**T18** · 01:40 · **DR. OSEI:** Though, um, we may need to adjust the lisinopril as well, depending. Let me have a look at your kidney numbers. Now, the dosing.

> *Recording note: This is the loose thread, and it ends mid-turn on "Now, the dosing." Do NOT come back to the lisinopril. The temptation to resolve it on tape is strong; resisting it is the whole plant. Note also that this turn does not name metoprolol before the sig lands at turn 20 — a nearest-mention heuristic that guesses right by accident tests nothing.*

**T19** · 01:51 · **RAY:** So that's two of the twenty-fives?

> *Recording note: Start speaking before she finishes turn 18 — a real half-second overlap. The patient stating a dose over the clinician is the D16 category 3 plant, and exclusive diarization needs something to actually exclude.*

**T20** · 01:54 · **DR. OSEI:** Let's get you the fifties, it's one tablet instead of two. And that one's twice a day, with food.

> *Recording note: Do NOT name the drug in this turn. "That one" is the category 8 plant: the sig is eight turns downstream of the mention, and lisinopril is the nearest drug named in between. Span verification cannot see this failure — every quote in it is genuine.*

**T21** · 02:05 · **RAY:** Twice a day. Morning and night.

**T22** · 02:09 · **DR. OSEI:** Right. And I want to see you back in about ten days so we can check the pressure again and make sure the higher dose isn't dropping it too far.

**T23** · 02:19 · **RAY:** Ten days. I'll get that on the calendar. Will the fifty make me more tired? When I started the twenty-five I was, I was dragging for about a week.

**T24** · 02:34 · **DR. OSEI:** It can, at first. Tiredness, cold hands, those are the common ones, and they usually settle after a week or two.

**T25** · 02:44 · **RAY:** And if they don't?

**T26** · 02:47 · **DR. OSEI:** Then we look at it again. But don't stop it on your own, that's the one thing I'd ask you.

**T27** · 02:55 · **RAY:** No, I won't.

**T28** · 02:58 · **DR. OSEI:** So, going back over it, the metoprolol, twenty-five, twice a day, and the lisinopril stays where it is.

> *Recording note: This contradicts turn 12 (fifty milligrams) and it should sound completely unremarkable — she is reciting the old regimen from memory, slightly too fast. That is the failure mode. Say "metoprolol" correctly; the fixture predicts Whisper hears "metropolol" here, and if the real transcript comes back clean that is a pass for Track B, not a reason to re-record.*

**T29** · 03:07 · **RAY:** Got it.

**T30** · 03:09 · **DR. OSEI:** One more thing. If you feel dizzy when you stand up, or your heart feels like it's racing, call the office. Don't wait for the ten days.

**T31** · 03:18 · **RAY:** Dizzy or racing. Okay.

**T32** · 03:21 · **DR. OSEI:** And bring the home monitor with you next time, I'd like to see it against ours.

**T33** · 03:26 · **RAY:** Will do. Thanks, doc.

**T34** · 03:29 · **DR. OSEI:** Take care, Ray.

<!-- END GENERATED DIALOGUE -->

## Recording notes — 1e

Three files, and the third is the one that gets forgotten.

| | File | Notes |
|---|---|---|
| 1 | **short clip**, this script, ~3:30 | run live in the demo |
| 2 | **longer visit**, 12–15 min | pre-computed (4a); improvise around the same two drugs |
| 3 | **clinician enrollment**, ~10 s | D20 does not work without it |

- The enrollment sample is **`SPEAKER_00` alone**, clean, no second voice, no
  crosstalk. Ten seconds of ordinary speech — reading this paragraph is fine.
  If the patient is audible anywhere in it, the embedding is polluted and every
  role assignment in the session inherits the error.
- One room, one mic position, no phone speakerphone. D20's embeddings fail on
  colds, masks and speakerphone, and we do not want to debug that at hour 19.
- Audio is **gitignored**. Put the files in the session directory, not the repo
  tree — `Session.session_dir` is what U9 shreds.
- File 2 must be exempted from U10's 24-hour sweep (4a), or it deletes itself
  before the demo.

## Mirroring rule — enforced, not requested

The dialogue above is **generated** from the `TURNS` list in
`fixtures/build_golden.py`, which is the same list that builds
`golden_visit.json`. They cannot drift, because there is only one of them.

To change a line: edit `TURNS`, then run

```
python fixtures/build_golden.py --script   # rewrite the dialogue block
python fixtures/build_golden.py            # rebuild both fixtures
```

`tests/test_fixtures.py` fails if the block is out of sync, so a hand-edit
inside the generated markers is caught rather than discovered at hour 19.

This is what makes Track B's correctness testable rather than a matter of
opinion: B5 diffs its real `Session` against `golden_visit.json`, and the
delta is the accuracy report.
