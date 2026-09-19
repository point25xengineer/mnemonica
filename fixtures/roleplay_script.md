# Role-play script — 1d

**Do not record a real appointment.** No BAA exists anywhere in this stack.
Role-play means we never create PHI (PRESENTATION-NOTES item 3).

**Two speakers only** (D19, SPEC §6). v1 pins `num_speakers=2`; a third voice
is silently merged into an existing cluster, not detected.

| | |
|---|---|
| **Runtime** | ~3 min 30 s (≈520 words) |
| **Speakers** | `SPEAKER_00` Dr. Amara Osei (clinician) · `SPEAKER_01` Ray Delgado, 71 (patient) |
| **Visit date** | **Friday, 18 September 2026** — see *Dates* below |
| **Mirrors** | `fixtures/golden_visit.json`, turn for turn |

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
| 3 ambiguous attribution | **T21** | crosstalk; patient says a dose, `role="unknown"` |
| 4 unresolved drug | **T11** | "the other blood pressure pill" |
| 5 not specified | **T17** | "just take it the way you've been taking it" |
| 6 loose thread | **T19** | "we may need to adjust the lisinopril too" — never revisited |
| 7 contradiction | **T13 / T32** | metoprolol **50 mg** at 1:13, **25 mg** at 2:58 |
| 8 cross-turn association | **T13 → T23** | "that one's twice a day" lands 10 turns after the metoprolol mention, with lisinopril named three times in between and **no drug named after it** |
| fuzzy match | **T32** | `metropolol` — expected mistranscription (see below) |
| salt unspecified | all | bare "metoprolol", no salt, ever |
| red flag | **T30 / T34** | "call the office" |
| appointment | **T25** | ten days, purpose stated |
| past date | **T5** | "back in June" |
| consent (D27) | **T0/T1** | captured on tape before anything else |

**T32 is the sharp one, and it is two plants at once.** The doctor, thinking
of the old regimen, says a dose that contradicts T13 — *and* it is the turn
where a mistranscription is most likely. `25` twice a day and `50` once a day
are clinically near-identical, which is exactly why a human skims past it. The
system must not.

**The fuzzy match is a prediction, not a line to perform.** Say *metoprolol*
correctly every time. `metropolol` is what we expect Whisper to emit at T32,
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

**T0** · 00:00 · **DR. OSEI:** Morning, Ray. Before we get started — I'd like
to record this visit so you go home with a written summary. Nothing leaves this
laptop. Is that alright with you?

**T1** · 00:08 · **RAY:** Yeah, that's fine by me.

**T2** · 00:11 · **DR. OSEI:** Thank you. Okay — recording now.

**T3** · 00:14 · **RAY:** Do I need to, uh — do I need to sign something?

**T4** · 00:17 · **DR. OSEI:** No, saying yes is enough, I've got it noted. So
— how have things been?

**T5** · 00:23 · **RAY:** Not bad. The headaches I had back in June, those are
— those are mostly gone now. And I've been checking the pressure at home, like
you asked.

**T6** · 00:33 · **DR. OSEI:** Good, that's what I like to hear. What kind of
numbers are you getting?

**T7** · 00:37 · **RAY:** Um, mostly one fifty over ninety. Ninety-two,
sometimes.

**T8** · 00:44 · **DR. OSEI:** Mm-hm.

**T9** · 00:46 · **RAY:** One morning it was — *(chair scrape over the number)*
one sixty-two. That one scared me a little.

> *Recording note: make noise across "sixty-two" — scrape the chair, or cough.
> This is the D16 category 2 plant and we need the per-word probability to
> actually drop. Do not enunciate it.*

**T10** · 00:55 · **DR. OSEI:** Okay. That's higher than I want to see. Right
now you're taking the metoprolol, twenty-five milligrams, and the lisinopril at
ten.

**T11** · 01:04 · **RAY:** The little white one, yeah. And the — the other
blood pressure pill, I don't know what that one's called.

**T12** · 01:11 · **DR. OSEI:** That's the lisinopril.

**T13** · 01:13 · **DR. OSEI:** So what I'd like to do is bring the metoprolol
up to fifty milligrams.

**T14** · 01:19 · **RAY:** Fifty. Okay.

**T15** · 01:22 · **DR. OSEI:** Your heart rate's got room for it, and the
headaches coming back would be the thing I'd worry about otherwise.

**T16** · 01:29 · **RAY:** And the other one? The lisinopril?

**T17** · 01:33 · **DR. OSEI:** That one doesn't change — just take it the way
you've been taking it.

**T18** · 01:38 · **RAY:** Okay.

**T19** · 01:40 · **DR. OSEI:** Though, um — we may need to adjust the
lisinopril as well, depending. Let me have a look at your kidney numbers.

> *Recording note: this is the loose thread. Do NOT come back to it. The
> temptation to resolve it on tape is strong; resisting it is the whole plant.*

**T20** · 01:49 · **DR. OSEI:** Now, the dosing —

**T21** · 01:51 · **RAY:** *(over her)* — so that's two of the twenty-fives?

> *Recording note: start speaking before she finishes T20 — a real half-second
> overlap. The patient saying a dose over the clinician is the D16 category 3
> plant, and exclusive diarization has to be given something to actually
> exclude.*

**T22** · 01:54 · **DR. OSEI:** Let's get you the fifties, it's one tablet
instead of two.

**T23** · 01:59 · **DR. OSEI:** And that one's twice a day, with food.

> *Recording note: **do not** name the drug in this turn. "That one" is the
> category 8 plant — two drugs are in play and the sig is five turns downstream
> of the mention, with lisinopril the nearest named drug. Nothing re-anchors
> metoprolol in between — T20 deliberately says "the dosing", not the drug
> name, because a nearest-mention heuristic that guesses right by accident
> tests nothing. Span verification cannot see this failure; every quote in it
> is genuine. The fixture is the only place it gets tested.*

**T24** · 02:05 · **RAY:** Twice a day. Morning and night.

**T25** · 02:09 · **DR. OSEI:** Right. And I want to see you back in about ten
days so we can check the pressure again and — and make sure the higher dose
isn't dropping it too far.

**T26** · 02:19 · **RAY:** Ten days. I'll get that on the calendar.

**T27** · 02:24 · **RAY:** Will the fifty make me more tired? When I started
the twenty-five I was — I was dragging for about a week.

**T28** · 02:34 · **DR. OSEI:** It can, at first. Tiredness, cold hands — those
are the common ones, and they usually settle after a week or two.

**T29** · 02:44 · **RAY:** And if they don't?

**T30** · 02:47 · **DR. OSEI:** Then we look at it again. But don't stop it on
your own — that's the one thing I'd ask you.

**T31** · 02:55 · **RAY:** No, I won't.

**T32** · 02:58 · **DR. OSEI:** So, going back over it — the metoprolol,
twenty-five, twice a day, and the lisinopril stays where it is.

> *Recording note: this contradicts T13 (50 mg) and it should sound completely
> unremarkable — she is reciting from memory of the old regimen, slightly too
> fast. That is the failure mode. Say "metoprolol" correctly; if Whisper hears
> "metropolol" here, that is the fuzzy-match plant landing on its own.*

**T33** · 03:07 · **RAY:** Got it.

**T34** · 03:09 · **DR. OSEI:** One more thing. If you feel dizzy when you
stand up, or your heart feels like it's racing — call the office. Don't wait
for the ten days.

**T35** · 03:18 · **RAY:** Dizzy or racing. Okay.

**T36** · 03:21 · **DR. OSEI:** And bring the home monitor with you next time,
I'd like to see it against ours.

**T37** · 03:26 · **RAY:** Will do. Thanks, doc.

**T38** · 03:29 · **DR. OSEI:** Take care, Ray.

---

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

## Mirroring rule

The fixture mirrors this script **turn for turn**: same ids, same speakers,
same words. That is what makes Track B's correctness testable rather than a
matter of opinion — B5 diffs its real `Session` against `golden_visit.json`
and the delta is the accuracy report.

If a line changes during recording, change it **here first**, then in the
fixture. A script and a fixture that have quietly diverged turn Track B's gate
into a debugging session.
