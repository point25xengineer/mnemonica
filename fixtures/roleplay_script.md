# Role-play script — 1d

**Do not record a real appointment.** No BAA exists anywhere in this stack.
Role-play means we never create PHI (PRESENTATION-NOTES item 3).

**Two speakers only** (D19, SPEC §6). v1 pins `num_speakers=2`; a third voice
is silently merged into an existing cluster, not detected.

| | |
|---|---|
| **Runtime** | 2 min 48 s · 35 turns · 480 words · **recorded** |
| **Speakers** | `SPEAKER_00` Dr. Amara Osei (clinician) · `SPEAKER_01` Ray Delgado, 71 (patient) |
| **Visit date** | **Friday, 18 September 2026** — see *Dates* below |
| **Mirrors** | `fixtures/golden_visit.json` — both generated from `asr_words.json` |

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
| 2 low confidence | **T23** | `50` in "will the 50 make me more tired" → **p = 0.14** |
| 3 ambiguous attribution | **T19** | crosstalk; patient says a dose, `role="unknown"` |
| 4 unresolved drug | **T11** | "the other blood pressure pill" |
| 5 not specified | **T16** | "just take it the way you've been taking it" |
| 6 loose thread | **T18** | "we may need to adjust the lisinopril too" — never revisited |
| 7 contradiction | **T12 / T28** | metoprolol **50 mg** at 1:04, **25** at 2:22 |
| 8 cross-turn association | **T12 → T20** | "that one's twice a day" lands 8 turns after the metoprolol mention, with lisinopril the nearest drug named in between and **no drug named after it** |
| fuzzy match | **T10, T15, T18, T28** | **lisinopril**, wrong three ways — `lisonopril`, `lysinopril`, `lysinop` |
| salt unspecified | all | bare "metoprolol", no salt, ever |
| red flag | **T26 / T30** | "call the office" |
| appointment | **T22** | ten days, purpose stated |
| past date | **T5** | "back in June" |
| consent (D27) | **T0/T1** | captured on tape before anything else |

**T28 is the sharp one.** The doctor, reciting the old regimen from memory,
says a dose that contradicts T12. `25` twice a day and `50` once a day are
clinically near-identical, which is exactly why a human skims past it. The
system must not.

## What the recording actually did — two plants moved

The take is in, and reality reassigned two of the plants. Both moves are
improvements, and both are recorded here because the fixture now encodes them.

**The fuzzy match landed on lisinopril, not metoprolol.** Metoprolol came back
correct all three times it was said. Lisinopril did not, three separate ways:

| Heard | p | Edit distance |
|---|---|---|
| `lisonopril` (T10) | 0.90 | 1 |
| `lysinopril` (T15, T18) | **1.00** | 1 |
| `lysinopril` (T28) | 0.78 | 1 |
| `lyso,` `ly,` `lysinop,` (T15) | 0.10–0.77 | the actor's own restarts |

All inside `edit_distance <= 2`, so they hit TOOLS §1's *"likely
mistranscription, show both heard and resolved"* disposition. **Two of them
came back at p = 1.00.** No confidence signal flags them; `resolve_medication`
is the only thing between a confidently-wrong drug name and a printed page.
That is the demo, and we did not have to stage it.

**The category 2 plant moved from T9 to T23.** The scripted plant was noise
over a blood-pressure reading. It did not land — the actor read *"sixty-two"*
and Whisper heard `62.` correctly at p = 1.00, so there is no ASR error there
at all. Meanwhile T23's *"will the **50** make me more tired?"* came back at
**p = 0.14**, which is a better category 2 case than the scripted one: a dose
numeral rather than a vital, in a patient turn.

**One thing the transcript shows that no plant asked for:** Whisper writes
numerals as digits — `25 milligrams`, `150 over 90`, `the 50s`. Anything
matching quotes against a transcript must expect digits, not words.

---

## Script

Stage directions are in *italics* and are not spoken. Say the disfluencies —
the "um"s, the restarts, the half-overlaps are written in on purpose. A clean
script makes accuracy look fake-good and then collapses on stage.

---

<!-- BEGIN GENERATED DIALOGUE -->

*Generated from the committed ASR output by `fixtures/build_golden.py`. This is a transcript of the take that exists, not a script to perform from scratch — re-run `python fixtures/build_golden.py --script` after changing `TURN_BOUNDS`. Editing this block by hand makes the script and the fixture disagree.*

**T0** · 00:00 · **DR. OSEI:** Good morning, Ray. Before we get started, I'd like to record this visit so you go home with a written summary. Nothing leaves this laptop. Is that alright with you?

**T1** · 00:07 · **RAY:** Yeah, that's fine by me.

**T2** · 00:09 · **DR. OSEI:** Thank you. Okay, recording now.

**T3** · 00:11 · **RAY:** Do I need to, uh, do I need to sign something?

**T4** · 00:13 · **DR. OSEI:** No, saying yes is enough. I've got it noted. So how have things been?

**T5** · 00:17 · **RAY:** Not bad. Uh, the headaches I had back in June, those are, those are mostly gone now. And I've been checking the pressure at home, like you asked.

**T6** · 00:25 · **DR. OSEI:** Good. That's what I like to hear. What kind of numbers are you getting?

**T7** · 00:30 · **RAY:** Um, mostly 150 over 90. 92 sometimes.

**T8** · 00:35 · **DR. OSEI:** Mm -hmm.

**T9** · 00:37 · **RAY:** Um, one, one morning it was 62. That one scared me a little.

> *Recording note: Make noise across "sixty-two" — scrape the chair, or cough. This is the D16 category 2 plant and the per-word probability has to actually drop. Do not enunciate it.*

**T10** · 00:43 · **DR. OSEI:** Okay, that's higher than I want to see. Right now you're taking the metoprolol, 25 milligrams, and the lisinopril at 10?

**T11** · 00:52 · **RAY:** Uh, yeah, the little white one, yeah. And the other blood pressure pill, I don't know what that one's called.

**T12** · 00:58 · **DR. OSEI:** That's the lisinopril. So what I'd like to do is bring the metoprolol up to 50 milligrams.

**T13** · 01:05 · **RAY:** 50, okay.

**T14** · 01:06 · **DR. OSEI:** Your heart rate's got room for it, and the headaches coming back would be the thing I'd worry about otherwise.

**T15** · 01:13 · **RAY:** And the other one, the liso, li, lisinop, lisinopril?

**T16** · 01:18 · **DR. OSEI:** That one doesn't change. Just take it the way you've been taking it.

**T17** · 01:22 · **RAY:** Oh, okay.

**T18** · 01:23 · **DR. OSEI:** Though, um, we may need to adjust the lisinopril as well, depending. Let me have a look at your kidney numbers. Now the dosing.

> *Recording note: This is the loose thread, and it ends mid-turn on "Now, the dosing." Do NOT come back to the lisinopril. The temptation to resolve it on tape is strong; resisting it is the whole plant. Note also that this turn does not name metoprolol before the sig lands at turn 20 — a nearest-mention heuristic that guesses right by accident tests nothing.*

**T19** · 01:36 · **RAY:** So that's two of the 25s?

> *Recording note: Start speaking before she finishes turn 18 — a real half-second overlap. The patient stating a dose over the clinician is the D16 category 3 plant, and exclusive diarization needs something to actually exclude.*

**T20** · 01:39 · **DR. OSEI:** Let's get you the 50s. It's one tablet instead of two, and that's once twice a day with food.

> *Recording note: Do NOT name the drug in this turn. "That one" is the category 8 plant: the sig is eight turns downstream of the mention, and lisinopril is the nearest drug named in between. Span verification cannot see this failure — every quote in it is genuine.*

**T21** · 01:46 · **RAY:** Uh, twice a day, morning and night?

**T22** · 01:49 · **DR. OSEI:** Right. And I want to see you back in about 10 days so we can check the pressure again and make sure the higher dose isn't doping it too far.

**T23** · 01:56 · **RAY:** Uh, 10 days. Okay, I'll get that on my calendar. Will the 50 make me more tired? When I started the 20, uh, 25, I was dragging for about a week.

**T24** · 02:06 · **DR. OSEI:** It can at first. Tiredness, cold hands, those are the common ones, and they usually settle after a week or two.

**T25** · 02:12 · **RAY:** And if they don't?

**T26** · 02:14 · **DR. OSEI:** Uh, then we look at it again. But don't stop it on your own. That's the one thing I'd ask you.

**T27** · 02:19 · **RAY:** No, no, okay, I won't.

**T28** · 02:20 · **DR. OSEI:** So going back over it, the metoprolol, 25, twice a day, and the lisinopril stays where it is.

> *Recording note: This contradicts turn 12 (fifty milligrams) and it should sound completely unremarkable — she is reciting the old regimen from memory, slightly too fast. That is the failure mode. Say "metoprolol" correctly; the fixture predicts Whisper hears "metropolol" here, and if the real transcript comes back clean that is a pass for Track B, not a reason to re-record.*

**T29** · 02:28 · **RAY:** Got it, got it.

**T30** · 02:30 · **DR. OSEI:** One more thing. If you feel dizzy when you stand up, or your heart feels like it's racing, call the office. Don't wait for the 10 days.

**T31** · 02:37 · **RAY:** Dizzy or racing, okay, okay, I'll call.

**T32** · 02:39 · **DR. OSEI:** And bring the home monitor with you next time. I'd like to see it against ours.

**T33** · 02:43 · **RAY:** Will do. Thanks, doc.

**T34** · 02:44 · **DR. OSEI:** Take care, Ray.

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
