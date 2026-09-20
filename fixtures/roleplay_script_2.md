# Role-play script 2 — "Mrs. Okonjo, diabetes and thyroid review"

A second test case, deliberately **not** the script the fixture was built from.
Script 1 is cardiac (metoprolol, lisinopril); this one is endocrine, so the
drugs, the phrasing and the failure modes are all new. If the system only
works on script 1, it was tuned rather than built, and this is how you find
out.

**Two speakers only** (D19 — v1 pins `num_speakers=2`).
**Runtime:** ~4 minutes at a natural pace. Don't rush the disfluency.

All drug names below were checked against the built `rxnorm.db` before this
was written (1d). Do not substitute a drug without re-checking it.

---

## Casting and delivery

**DR. HALVORSEN** — clinician. Warm, slightly rushed. Talks over the patient
once, on purpose (marked). Corrects their own dose mid-sentence.

**MRS. OKONJO** — patient, 74. Mishears numbers, stumbles on the long drug
name, refers to one medicine only by what it does.

Record in one take. Leave the stumbles in — a clean read makes accuracy look
better than it is and then collapses on stage.

---

## Script

**DR:** Morning, Mrs. Okonjo. Come in, sit down. How've you been since March?

**PT:** Oh, not too bad. The — my feet have been bothering me a bit, but
that's, you know, that's nothing new.

**DR:** Mm. We'll come back to the feet. Let me look at your sugars first.
So your A1C came back at seven point four, which is — that's down from
eight point one, so whatever you're doing, keep doing it.

**PT:** Really? That's better?

**DR:** That's better. That's a good bit better. Okay. So — I want to bring
your metformin up. Let's go to a thousand milligrams twice a day.

**PT:** A thousand, twice —

**DR:** Sorry — no. Let me — five hundred twice a day. Five hundred. I was
looking at the wrong line. Five hundred milligrams, twice a day, with food.
Always with food, or it'll upset your stomach.

**PT:** Five hundred. With food.

**DR:** With food. Now your thyroid. You're on the levothyroxine — just keep
taking that as directed, same as before, nothing changes there.

**PT:** That's the Synthroid?

**DR:** Same thing, yes. Synthroid's the brand name for it. Same medicine.

**PT:** Okay. And what about — I take a, um, the water pill. The one for the
swelling.

**DR:** Right, the water pill, we're leaving that alone for now.

**PT:** And the other one, the — atorva— ator— the cholesterol one.

**DR:** Atorvastatin.

**PT:** That one. Am I still on that?

**DR:** Still on it, same dose, don't change anything. You started that back
in March and it's working fine.

**PT:** March. Alright.

**DR:** Now — I'm going to send you for bloods before your next visit. Come
back and see me in six weeks and we'll see where the sugars have landed.

**PT:** Six weeks.

**DR:** Six weeks. And listen — this is important. If your feet start going
numb, or you get any sore on your foot that isn't healing up, you call the
office. Don't wait for the six weeks. Call us.

**PT:** If there's a sore.

**DR:** If there's a sore, or numbness, you call. That's not a wait-and-see.

**PT:** Alright.

**DR:** We should also talk about getting your eyes looked at, it's been a
while —

**PT:** *(overlapping)* — my daughter keeps saying the same thing.

**DR:** Right. Okay. Any questions for me?

**PT:** No, I don't think so. Five hundred, with food.

**DR:** Five hundred, with food. Six weeks. Take care, Mrs. Okonjo.

---

## What this should produce

Hard requirements are deterministic — they come from code, not the model.
Observations depend on extraction and may vary between runs.

| # | Planted | Expect | Kind |
|---|---|---|---|
| 1 | metformin stated twice — 1000 mg, then corrected to 500 mg | **D16 cat 7, blocking.** Both doses shown with timestamps, clinician picks | hard |
| 2 | "keep taking that as directed, same as before" | **D16 cat 5** — `not_specified`, presented as a finding, **not** an error | hard |
| 3 | levothyroxine **and** Synthroid, same drug | Brand resolves via A7 to the same ingredient. **Should not print as two medicines** | hard |
| 4 | "the water pill" | Should be **unresolved** — see Known bug A below | hard |
| 5 | "atorva— ator—" stumble, then doctor says the name | Resolves to atorvastatin. The stumble should **not** become a third medicine — see Known bug B | hard |
| 6 | "come back and see me in six weeks" | `resolve_date` → a real date, printed **both ways** | hard |
| 7 | "you started that back in March" | Past direction, resolves **backwards**, not forward | hard |
| 8 | "if your feet start going numb… you call the office" | Red flag, verbatim on the patient page | hard |
| 9 | Eye appointment raised, never settled | **D16 cat 6** — loose thread | observation |
| 10 | "seven point four", "eight point one" | Should **not** be read as doses | observation |
| 11 | Doctor talks over the patient once | Overlap — `exclusive_speaker_diarization` should not mis-attribute | hard |
| 12 | Every dose is spoken by the clinician | No dose may come from a patient turn (D19) | hard |

### Known bugs this script is built to catch

**A — "my water pill" resolves to the ingredient *water*.**
Normalization strips the article and the trailing form word, leaving `water`,
which is a genuine RxNorm ingredient — so it comes back `resolved`,
`case_insensitive`, unflagged. TOOLS.md §1 says a colloquial reference must
report `unresolved`. Measured: `the oxygen` fails the same way; `my heart
pill`, `my sugar pill`, `your blood pressure pill` all correctly return
unresolved. Narrow, but "water pill" is the single most common way an elderly
patient names a diuretic.

**B — an unresolved mention prints on the patient's page.**
On script 1, a patient's stumble (`"lyso, ly, lysinop, lysinopril"`) rendered
as a third medicine, duplicating lisinopril, on the printed handout. The
extraction was honest — `unresolved`, cats `[2, 4]`, near-match at 0.889 — but
the disposition was `prefilled_flagged`, which is not blocking, so approving
without touching it sent it to paper. Line 5 above re-creates the conditions.

### How to run it

```bash
VP=/Users/evancanty/vn-shared/.venv/bin/python
$VP -m mnemonica.audio.pipeline sessions/script2/visit.m4a \
    --session-dir sessions/script2 \
    --enrollment sessions/script2/clinician.wav \
    --out sessions/script2/session.json
$VP -m mnemonica.verify.run sessions/script2/session.json \
    -o sessions/script2/extraction.json
$VP -m mnemonica.ui.app --session sessions/script2/session.json \
    --extraction sessions/script2/extraction.json \
    --audio sessions/script2/visit.m4a
```

Record a fresh 10-second enrollment sample from whoever reads DR. HALVORSEN —
the existing one is a different voice and B3 will assign the wrong role.

### While you're in the UI — the manual checks

These are the ones no test covers:

- **Listen to five citations.** Gate B5 is still a structural pass only; nobody
  has confirmed playback lands on the right words. Check the corrected
  metformin dose specifically — being two seconds off there is the worst case.
- **Read the printed page as a patient.** Three medicines or four? Does the
  water pill appear as a medicine called *water*?
- **Time the review** (3e is still blank). Hand it to someone who didn't build
  the UI and start a stopwatch.
