# Blenderized Tube Feed Calculator — Project Plan

> **Week 1 deliverable for the AI Masters Vibecoding Challenge.**
> Concept, market research, requirements, and methodology — in one document.

---

## 1. The concept

A transparent, open-source calculator that tells you exactly what your
blenderized tube-feed (BTF) recipe delivers nutritionally — per mL, per
day, and compared to commercial formula. No black boxes.

It's not groundbreaking. The math isn't new — RDs do it every day, by
hand or in spreadsheets. But there's no well-built, open-source,
Canadian tool that does it properly. So we're building one.

---

## 2. The problem

Registered Dietitians (RDs) who manage blenderized tube feeds are doing
the math by hand or in cobbled-together spreadsheets. They *can* do it
— they're trained, they're capable. But the process is:

- **Slow.** Building a nutrient profile for a single BTF recipe by hand
  takes 30–45 minutes. Adjusting one ingredient means recalculating
  everything.
- **Error-prone.** Every manual recalculation is a chance for a silent
  arithmetic error in a clinical context.
- **Unshareable.** Each RD's spreadsheet is their own. No standard, no
  validation, no audit trail. If an RD leaves a practice, their
  spreadsheet leaves with them.
- **Intimidating.** RDs who are *interested* in BTF but not confident in
  the math are deterred.

There are free tube-feed calculators online. Most are built for commercial
formula, not whole-food BTF. None show their work. None let you enter a
custom food from a nutrition facts label. None compare your BTF recipe
side-by-side with a commercial formula at the same volume. And many RDs
still prefer doing it by hand because they don't trust tools they can't
audit.

### The sweet spot — thin enough to flow, dense enough to nourish

Every BTF recipe lives in a tension between two physical realities:

1. **Thin enough to flow through the tube.** If the blend is too thick,
   it clogs. This is a physical property (viscosity) that no calculator
   can measure. The RD or caregiver uses a **drip test** — hold the
   syringe, watch how fast it drains, feel the resistance. Alberta Health
   Services' *Home Blended Food for Tube Feeding: Caregiver Handbook*
   (2021) describes it: *"If you can pull up the blended food in a 50 or
   60 mL syringe without resistance, then the consistency is likely
   good."* The ideal consistency *"may flow off the end of a spoon like
   liquid honey."* There is no sensor, no formula, no app that can
   replace this. It's tacit, embodied knowledge.

2. **Dense enough to nourish.** If the blend is too thin (too much
   water), the patient can't get enough calories/protein within the
   volume they tolerate. This *is* computable: kcal/mL × tolerated
   volume = daily kcal.

The **sweet spot** is where these two constraints overlap. The RD
iterates: tweak the recipe → check the numbers (tool) → drip test
(hands-on) → tweak again → until both sides work. BTF recipes should be
**at most as thick as Resource 2.0** (one of the thickest commercial
formulas) — thicker than that won't flow through a tube.

The tool handles the numbers side; the RD handles the flow side.

---

## 3. Why now

### Market growth

- The global tube feeding (enteral nutrition) market was valued at
  **$8.79 billion in 2025** and is expected to reach **$16.70 billion
  by 2033** (CAGR 8.36%) (Data Bridge Market Research).
- Growth drivers: aging populations, chronic disease prevalence (cancer,
  neurological disorders, GI conditions).
- BTF specifically: *"The growth in interest and demand for using
  blenderized tube feeds (BTFs) has outpaced the availability of robust
  evidence-based literature"* (State-of-the-art review).

### The evidence: support outpaces practice, and time is the top barrier

Dietitian surveys across three regions tell a consistent story:

- **Support outpaces practice.** Among US RDNs surveyed in 2025, 87%
  supported BTF and 76% used it in clinical practice — yet actual use
  *"continues to lag"* behind support, a gap attributed in part to the
  absence of facility-level BTF policies (Spurlock 2025).
- **Time is the #1 professional barrier.** In a 2025 Australia/New
  Zealand survey of dietitians, the most-cited barrier to supporting
  blended tube feeding was **health professional time commitment
  (63%)**, ahead of lack of practical guidelines (53%) and need for
  education/training (50%) (Reilly 2025). A calculator directly attacks
  the top-ranked barrier.
- **RDs are asking for transparent, reputable resources.** The 2024
  ASPEN member survey (Brown 2024) found *"desire for evidence-based
  guidelines and educational handouts from reputable sources, such as
  ASPEN, a need for education because of a lack of training."* ASPEN
  published its BTF Practice Recommendations the same year.

**Honest framing of the demand signal:** no survey has asked RDs "do
you want a BTF calculator?" The documented demand is for *time relief,
guidelines, and education*. This tool maps onto that demand in two
ways: the calculator addresses the time barrier directly, and the
transparent methodology (Appendix A) doubles as the kind of
show-your-work educational resource the surveys asked for. Both are
inferences from barrier data, not direct market research — which is
why hands-on pilot testing with practicing RDs is a stated success
metric (§10), not an afterthought.

### The adult gap

The most credible existing tool (the Nestlé/CHOP Compleat® recipe
builder) is **pediatric-only (ages 1–13)** and caregiver-facing. But
the adult evidence base is growing: BTF mitigated weight loss, GI
symptoms, and quality-of-life decline in head-and-neck cancer patients
on tube feeding (Spurlock 2022), and a pilot study found BTF safe and
effective for weight gain in adults on home enteral nutrition. The
adult BTF population — head-and-neck cancer, ALS, home enteral — is
the growing, underserved corner of this niche. This tool is
adult-focused by design (and deliberately ships **no** default targets
at all — see Appendix A6).

### Formula companies are investing

Nestlé built the Compleat® recipe builder. Abbott published BTF education
materials. The market is real enough that major companies are investing
in tools — but their tools are marketing instruments, not vendor-neutral
clinical instruments.

---

## 4. Value proposition

| Without this tool | With this tool |
|---|---|
| 30–45 min to build a BTF recipe profile | 2–3 minutes |
| Manual recalculation for every change | Live updates — change one ingredient, see everything update |
| Adequacy vs targets checked by eye | Automatic gap report with status indicators |
| No commercial-formula comparison | Side-by-side comparator |
| Mental math across feeds, batches, flushes, and oral intake | A day-level Intake Record that records and sums exactly what the client actually received |
| Errors are silent | Validated inputs, consistent math, every calculation visible |
| Hard to share or audit | Exportable recipe + methodology for chart documentation |
| Curated food list or no database | ~6,000 CNF foods + USDA supplement + custom foods from labels |

---

## 5. Design philosophy — "No black boxes"

Inspired by the EN spreadsheet created by Hui Jun Chew, RD (North York
General Hospital, Toronto). That spreadsheet is a practical, well-built
tool that RDs trust because:

1. **Everything is visible.** Every formula is in the cell. An RD can
   point to any number and say "here's where this came from."
2. **Reference data is human-editable.** If a formulation changes, an RD
   updates it without touching code.
3. **Clinical judgment overrides everywhere.** The tool never says "this
   is the answer" — it says "here are the calculations, you decide."
4. **Multiple methods shown simultaneously.** The tool doesn't pick one
   equation; it shows all and lets the RD choose.

This BTF tool carries that philosophy forward: every nutrient calculation
is traceable, the methodology (Appendix A) documents every equation, and
the RD is always the final authority.

---

## 6. Target users

### Primary: Registered Dietitians (RDs)

- Working in home care, private practice, outpatient clinics, and
  community health settings where BTF is managed.
- Already know their patients' targets from prior assessment.
- Want a tool that *accelerates* their calculation, not one that
  *replaces* their judgment.

### Secondary: Patients and caregivers (via the RD)

- The RD uses the tool to **show** the patient/caregiver what their
  feeding schedule delivers.
- The flexible delivery input is a *communication* feature — it helps
  the RD translate between the patient's mental model ("300 mL, 4 times
  a day") and the nutritional reality.
- The AHS handbook confirms this audience: it's written for caregivers
  but repeatedly says "talk to your dietitian."
- The tool is designed to be usable by anyone on the care team, with
  the safety guardrail: **"for RD use, estimates only."**

---

## 7. Core features

1. **Recipe builder.** Search CNF 2026 (~5,993 foods) or USDA supplement
   (~7,000 whole foods) or add a custom food from a nutrition facts
   label. Enter grams (or mL, for a liquid custom food) per ingredient
   and measured final blend volume. There is no separate "added water"
   field — water is an ordinary ingredient like anything else (CNF
   carries it at ~99.9% moisture), entered and toggled "counts as
   fluid" the same as any other liquid. **Use what's in your kitchen,
   at the amounts you actually used.**

2. **Live density panel.** kcal/mL, protein/mL, free-water fraction —
   updated instantly as ingredients change. Per-mL density is the
   primary lens because the patient can only tolerate so many mL/day.
   The tool shows density live; the RD checks flow with a drip test.
   An optional patient weight adds a display-only per-kg row (kcal/kg,
   protein g/kg, fluid mL/kg) — no target or equation is derived from it.

3. **The day is a list of intake events — an Intake Record, not a
   schedule formula.** Real BTF days don't follow "one recipe × one
   schedule": families blend in the morning and again in the afternoon
   with different ingredients, keep a batch in the fridge and draw from
   it across the day, or the client eats and drinks by mouth alongside
   the tube feed (BTF isn't necessarily NPO-except-tube). So the design
   separates two things that are **not** the same: the volume a recipe
   *produces* (its batch) and the volume the client *received*. The app
   holds multiple named **blends** per day (each with its own
   ingredients and measured batch volume — a blend is a *formulation*,
   scale-free, not a batch), and one **Intake Record** — a single
   chronological list of rows, each with an optional time and a
   `source_type` of blend, commercial formula, water flush, or oral
   food/drink: `0800 · Morning blend · 300 mL`,
   `0830 · 1 small banana (oral)`, `1500 · Fridge batch · 350 mL`,
   `2000 · Peptamen 1.5 · 250 mL`, flushes interleaved. Displayed
   grouped under "Tube Feed" and "Food & Drink" headers for
   scannability, but it's one list and one aggregation — never two
   separately-maintained logs merged into a third view. Daily totals
   are the **direct sum over this record** — never an extrapolation,
   and there is deliberately **no over-draw flag**: a blend's density is
   scale-free (1.2 kcal/mL whether made once or three times today), so
   logging 600 mL against a "400 mL blend" just means it was made more
   than once — the ordinary case, not an anomaly. The only guard that
   remains is a real invalidity: a blend with ingredients but no
   measured volume can't produce a density and says so clearly. (Naive
   designs multiply one recipe's density by a prescribed daily volume,
   silently inventing batches that were never made — this design makes
   that failure impossible by construction.) An oral row is architecturally
   simpler than a blend row — a single food needs no batch/density
   concept, just the same grams × per-100g scaling a blend ingredient
   already uses — so oral entry reuses the exact same CNF search (with
   food-group filter and household-measure or grams entry) and
   custom-food-from-label form already built for blends, not a second
   food-search UI.

   The AHS handbook confirms syringe bolus is the primary method for
   BTF: *"Home blended food is mostly offered by syringe as the blend
   may be thicker than formula"* and *"Pumps are not routinely provided
   because their design does not work well with home blended food."*
   Pump delivery is accordingly not offered; the delivery route is
   recorded only as wording for the chart note.

4. **Adequacy report, in two tiers, a fluids ledger, and a per-source
   split.** At the day's logged intake (tube feed and oral together): a
   main table of nine displayed nutrients (energy, protein, fat,
   carbohydrate, fibre, sodium, potassium, calcium, iron — chosen by the
   author as "what's needed," not everything; saturated fat, trans fat,
   cholesterol, and sugars are still computed and exported, just not
   shown daily) plus two fluid rows: **Fluid provided** (full volume of
   every counts-as-fluid contribution — blend ingredients, formula and
   flush volumes, oral drinks — the I&O convention; this drives the
   fluid-adequacy status) and **Free water (estimated)** (CNF food
   moisture from blend and oral rows, blended with any commercial
   formula's declared free-water content; secondary/informational, no
   target of its own). A **per-source breakdown** table — Tube Feed vs.
   Food & Drink vs. Total, across the same nutrients — answers "I want
   the combined numbers, but I still want to see the split." Targets are
   always blank until the RD enters patient-specific numbers — there
   are no population defaults (protein practice runs 1.0-1.5 g/kg, not
   the 0.8 g/kg population RDA a default would imply). Status
   indicators: meeting / below / above target — except sodium (a
   Tolerable Upper Intake Level, not a target to aim for), which reads
   "Below UL" / "Above UL" instead. Any row with literally zero
   ingredient coverage is hidden with a footnote, rather than shown as
   a confident zero. A second, collapsed **"BTF micro screen"** shows
   magnesium, phosphorus, zinc, vitamin D, and vitamin B12 — nutrients
   not on a Canadian label but clinically relevant to BTF (the author's
   EN spreadsheet tracks magnesium/phosphorus; the rest are an
   ASPEN-style one-time supplementation check, not a daily-tracked
   panel). See Appendix C for why the split exists.

5. **Commercial formula comparator — and mixed regimens for free.**
   Pick up to four benchmark formulas; a transposed table (metrics as
   columns, the BTF as the first row) shows each at an independent
   "compare at this volume" what-if — a density comparison, deliberately
   separate from the day's actual logged intake. Combined BTF + formula
   regimens need no separate feature at all: a formula is simply another
   Intake Record row (#3), so the day's totals naturally sum blend +
   formula + flushes + oral — the author's own EN spreadsheet's "Totals
   from EN + BP + Propofol" concept, generalized and now reported with
   the per-source breakdown from #4.

6. **Live recipe adjustment is the core interaction — not a mode, the
   editor itself.** There is no separate "what-if" screen for the
   central use case. The recipe builder IS the what-if: add/remove/swap
   an ingredient, change an amount, swap water for juice or broth — and
   every number (densities, daily totals, adequacy, comparator) updates
   instantly on the same screen the RD is already editing. The RD
   iterates: tweak → check numbers → drip test → tweak again. Live
   recipe adjustment is the core interaction, full stop.

   **Dilution What-If is a separate, secondary aid — not the core
   feature.** A small calculator, one level down from the main flow,
   that answers one narrow question before the RD commits to an actual
   ingredient edit: "if we must thin this recipe, what does it cost in
   density?" It previews a hypothetical addition (Appendix A8) without
   touching the real recipe. **Thinning liquids aren't just water.**
   Water (pure dilution), apple juice (adds calories), broth (adds
   sodium + protein), milk (adds calories + protein + calcium), oil
   (adds fat). The AHS handbook confirms: *"If your child needs more
   calories add: milk, juice, oil, formula"* vs. *"If your child does
   not need more calories add: cooking liquid, water."* Once the RD has
   an answer they like, they still make the change through the actual
   recipe builder above (#1) — that's what makes it "live."

7. **Flow-test documentation and a copy-pasteable chart note.** A simple
   date/result/notes record of the RD's own drip test (the tool cannot
   measure flow — this is documentation, not computation) and a
   generated chart-note paragraph — essentially the Intake Record read
   aloud, tube feed and oral interleaved by time, plus totals:
   times/sources/volumes (same-source tube-feed rows grouped, e.g.
   "0800 300 mL + 1200 100 mL Morning blend"), macros, the fluid math,
   and the flow-test result when recorded — in a code block with a
   built-in copy button. No patient-identifying fields.

8. **Export.** Excel export covering each blend and its ingredients
   (with the fluids-ledger unit/counts-as-fluid columns) on its own
   sheet, the full Intake Record (chronological), density panel,
   adequacy and micro-screen tables, the per-source breakdown, formula
   comparator, flow test, and the chart note text.

### Where AI belongs in a clinical calculator (roadmap)

The core of this tool is deliberately deterministic — every number
traceable, no model in the arithmetic. That is the thesis, not a
limitation. AI belongs **at the edges**, where the work is tedious and
verification by the RD is cheap:

> **The parts that must be trusted are transparent; the parts that are
> tedious are AI-assisted; the RD verifies everything at the boundary.
> The agent is in the workflow, not in the math.**

Planned, in priority order (sequenced after the core build, Week 3+):

1. **Label photo → custom food (flagship).** Photograph a Nutrition
   Facts panel; a vision model extracts the values and fills the app's
   Nutrition-Facts-lookalike entry form — which doubles as the
   *verification UI*: the RD holds the real label beside its digital twin
   and confirms before anything is saved. The model reads a document; it
   never computes nutrition. (Deploying this publicly for RD pilot
   testing is part of the same milestone — Streamlit Community Cloud,
   with the API key in app secrets. Feasible precisely because the app
   holds no patient data.)
2. **Manufacturer PDF → formulas.csv, in-app.** The formula table's
   audit trail (each manufacturer's healthcare-professional PDF stored
   beside the CSV as provenance) promoted to a feature: upload the HCP
   product PDF, the agent extracts kcal/mL, protein/mL, free water; the
   RD approves the diff before it lands.
3. **Plain-words recipe matching.** "A scoop of oats, half a banana,
   splash of 2% milk" → proposed CNF matches + household measures for the
   RD to confirm. **Clinical design constraint (author's ruling): default
   to COOKED preparations** — blended feeds go directly into the stomach,
   so "oats" means cooked oats and "chicken" means cooked chicken. The
   matcher must never silently select raw meat/egg entries; raw variants
   (e.g., sushi-grade fish) are surfaced only as an explicit, flagged
   choice. Search assist only — never calculation.
4. **USDA SR Legacy supplement** — the multi-source data story,
   specified in §8 and Appendix C.

**Explicitly rejected — AI-written chart notes (ADIME).** An LLM cannot
write an assessment note without the patient's medical picture, which
this tool deliberately never holds (no PHI, by design — also what makes
public deployment simple). The deterministic chart-note paragraph
(macros + fluid in charting-friendly sentences, generated from the
actual intake) is the right scope; the RD writes the rest of the note
where the patient context lives.

### Out of scope

- **Assessment page** (energy equations, IBW, etc.). The RD brings their
  own targets. Reference equations documented in Appendix B.
- **Osmolality, viscosity, food safety.** Not computable from nutrient
  data. The tool acknowledges the thickness ceiling (at most like
  Resource 2.0) but cannot measure it — the drip test is the RD's domain.
- **EMR integration.** Future.

---

## 8. Data — CNF + USDA supplement

### The problem with CNF alone

CNF 2026 has ~5,993 foods. That's good for Canadian packaged foods and
common whole foods, but it's limited. If someone searches for plantain,
cassava flour, or specific ethnic foods, CNF may not have them.

### The solution: dual database

**Whole foods are whole foods.** A raw plantain from CNF and a raw
plantain from USDA have essentially the same nutrient profile. Cooked
lentils are cooked lentils. The biology doesn't change at the border.

**Packaged foods are different.** Canadian yogurt has different
fortification than US yogurt. Canadian bread has different folic acid
levels. Canadian milk has different vitamin D fortification. For
packaged foods, using the wrong country's database gives wrong numbers.

| Data source | Used for | Why |
|---|---|---|
| **CNF 2026** (primary) | Canadian packaged foods, common foods | Right fortification, Canadian-specific |
| **USDA SR Legacy** (supplement) | Whole foods CNF doesn't have | Whole foods are interchangeable across countries |
| **Custom label entry** | Specific branded products | Always the most accurate for packaged foods |

The search function checks CNF first, then USDA for foods not found. The
user sees one unified search — they don't need to know which database it
came from.

### Cultural foods

This isn't a separate feature — it's a natural consequence of having a
large database + custom entry. But it matters. Most BTF tools have a
curated food list (Compleat has ~40 foods). If your family eats dal,
roti, and okra — or jollof rice, plantains, and egusi — or congee, pork
floss, and bok choy — those foods aren't on a 40-food list. BTF is about
real food, family food. If the tool can't handle your family's food,
it's not really "real food."

With CNF + USDA supplement + custom entry, you can use **your** kitchen,
**your** food, **your** culture. That's a real benefit, not a
breakthrough — just a consequence of not restricting people to a
curated list.

---

## 9. Competitive landscape

### BTF-specific tools

| Competitor | What it is | Audience | What it does | What it doesn't do |
|---|---|---|---|---|
| **Compleat® (Nestlé/CHOP)** | Food-guide recipe builder | Patients/caregivers | Category-based selection, calorie-targeted, blended volume per ingredient, volume limit + variance, PDF export, supplementation flags | **Pediatric-only (ages 1–13)**, curated ~40 foods, fixed portions (can't enter grams), US-focused, no density lens, no thinning-liquid comparison, no commercial comparator, black box math, vendor-locked |
| **Blended Recipe Builder** | Nutrition app | Patients/caregivers | Macros + micros, blend book, recipes, videos, education | Unclear database size, no density lens, no commercial comparator, no transparent math |
| **BlendWise Nutrition** | Full service + grocery delivery | Patients/caregivers | RD guidance, automated meal planning, grocery delivery | Not a self-serve tool, not open-source, service model |
| **TubieTable** | Recipe generator | Patients/caregivers | Tube type filtering, recipe generation | Not a calculator, no density lens, no adequacy report |
| **The Blend** | Recipe community | Patients/caregivers | Recipe sharing | Not a calculator, no nutrient analysis |
| **Hilarie Geurink RD** | Consulting service | Patients/caregivers | Personal RD consulting, community | Not a tool, service model |

### Other competitors

| Competitor | What it does | What it doesn't do |
|---|---|
| **Hand-built Excel spreadsheets** | The real competitor. Every RD has their own. | Not validated, not shareable, not maintainable, no BTF-specific features |
| **Professional nutrient-analysis software** (ESHA Food Processor, Nutritionist Pro) | The *other* real competitor: validated recipe analysis RDs already use and trust | Paid licenses, US-data-centric, and no BTF machinery: no per-mL density lens, no measured-volume denominator, no free-water fraction, no formula comparator, no dilution what-if |
| **Commercial formula calculators** (Nestlé, Abbott) | Calculate EN for their own products | Built to sell formula, not analyze BTF |
| **Generic nutrition apps** (MyFitnessPal, Cronometer) | Track oral intake | Not built for tube feeding, no density/mL |

### Where we fit

Every competitor is either (a) patient/caregiver-facing, (b) a formula
company marketing tool, or (c) general-purpose paid analysis software
with none of the BTF-specific machinery. None are open-source,
transparent calculators with a large food database and Canadian data.

Our differentiators, honestly stated:
- **Adult-focused** — the credible incumbents are pediatric; the
  growing adult BTF population (head/neck cancer, ALS, home enteral)
  has no dedicated tool
- **Transparent math** — every calculation visible and documented
- **Calculator not food guide** — enter what's in your blender, not pick
  from a curated list
- **Actual grams, not fixed servings** — enter what you really used
- **Large database + custom entry** — CNF + USDA + labels = use what's
  in your kitchen
- **Per-mL density lens** — kcal/mL as primary metric
- **Sweet spot awareness** — shows density while RD checks flow
- **Thinning-liquid comparison** — water vs juice vs broth vs milk
- **Commercial formula comparator** — side-by-side
- **Canadian** — CNF data, Canadian fortification, Canadian formulas
- **Open-source** — MIT licensed, vendor-neutral

These are practical differences, not breakthroughs. But they're real,
and none of the existing tools offer all of them.

---

## 10. Business model, risks, and success metrics

### Market sizing (honest)

This is a narrow professional niche, sized in the hundreds, not
thousands. There is no reliable national count of home enteral patients
in Canada; the closest proxy is a 2017 survey in which 240 Canadian RDs
recalled ~5,600 EN patients across acute, long-term, and home care
settings (Hopkins 2017). BTF is a fraction of that caseload, managed by
a smaller subset of RDs. Realistic serviceable market: **hundreds of
regular users.** The value proposition is depth, not reach — each use
informs a clinical decision for a patient who lives on the recipe.

### Business model: impact-driven open source

There are no institutional budgets for BTF calculators, and
willingness-to-pay for allied-health tooling is structurally low —
RD-facing software budgets are a fraction of physician-facing ones.
This is not a SaaS opportunity, and pretending otherwise would distort
the design. **This is an open-source public-health tool that should
exist because the alternative is every RD reinventing their own
unvalidated spreadsheet.**

- **License:** MIT or CC BY-NC-SA.
- **Sustainability model:** open-source, community-maintained;
  reference data (formulas, targets, thinning liquids) lives in
  human-editable CSVs so clinical upkeep requires no code. Future:
  grant funding from nutrition associations (Dietitians of Canada,
  ASPEN, BDA).
- **Distribution (go-to-market):** professional word of mouth —
  colleague pilots first, then Dietitians of Canada networks, the Oley
  Foundation, and ASPEN BTF interest groups. Niche clinical tools live
  or die on trust networks, not marketing.
- **The success currency is adoption and impact, not revenue.**

### Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| **Trust/validation** — RDs won't chart numbers from an unvalidated tool | Adoption-killing | Validation appendix: worked examples cross-checked against hand calculation and established software; every equation already documented (Appendix A) |
| **Author–domain distance** — the author is an RD, but not a BTF specialist | Clinical blind spots | Pilot testing with practicing BTF RDs before any promotion; their feedback is the product roadmap |
| **Policy vacuum** — facilities lack BTF policies, so institutional use lags regardless of tool quality (Spurlock 2025) | Caps adoption ceiling | Accept it; target individual RDs in home/community practice where policy friction is lowest |
| **Discoverability** — niche clinical tools die in obscurity | No users | Trust-network distribution (see go-to-market); the transparent methodology doc is itself shareable education content |
| **Maintenance / bus factor** — CNF editions, formula reformulations, single maintainer | Slow decay | Editable-CSV reference data; documented CNF upgrade path; open-source license so others can fork |

### Success metrics (KPIs)

1. **Efficiency:** time from ingredients-in-hand to full nutrient
   profile under 5 minutes (baseline: 30–45 by hand).
2. **Accuracy:** validation appendix published — worked examples
   matching hand calculation to rounding error.
3. **Adoption:** 3–5 practicing RD colleagues complete a pilot on a
   real recipe and report back.
4. **Education:** methodology (Appendix A) readable standalone by an
   RD with no Python knowledge — the "show your work" resource the
   ASPEN survey asked for.
5. **Maintainability:** a formula or target update requires editing
   one CSV row, zero code.

---

## 11. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12+ | Author's focus; fastest path to shipping |
| Data | pandas | Standard for tabular data; handles 565k-row CSV |
| UI | Streamlit | Fastest path from Python to live web app; free cloud deployment. Chosen for competition speed, not just legacy. Graduation path: FastAPI + React. |
| Persistence | Parquet (pyarrow) | Binary, fast load |
| Tests | pytest | Standard, simple |
| Deployment | Streamlit Community Cloud | Free, public URL, auto-deploys from GitHub |

**Data:** CNF 2026 (primary) + USDA SR Legacy (supplement). Both public,
both ship with the repo. No API keys needed for the core — the
deterministic calculator runs entirely on local data. The AI-assist
edges (§7 roadmap: label photo, PDF extraction) use a vision-model API
key held in deployment secrets, never in the repo.

---

## 12. The 4-week build plan

| Week | Deliverable | What gets built |
|---|---|---|
| **1 — Plan It** | This document posted publicly | Concept, market, requirements, methodology — including the Intake Record model (§7.3), the per-country nutrient registry (Appendix C), and the AI roadmap (§7) |
| **2 — Core Feature** | Working Streamlit app | Data layer (CNF load, registry); calculator (blends → densities); Intake Record → daily totals; two-tier adequacy + fluids ledger; comparator; NFt-lookalike custom-food entry; chart note; export |
| **3 — Build to Last** | Tests, CI, public deploy, AI-assist edges | pytest suite, GitHub Actions, Streamlit Cloud deploy for RD pilot testing, label-photo extraction (flagship), PDF → formulas extraction, USDA supplement |
| **4 — Ship + Pitch** | Live app + 2–3 min demo | Polish from pilot feedback, validation appendix, demo video |

---

## 13. The story (for the Week 1 post)

> I'm a nutrition subject-matter expert. I've watched colleagues struggle
> with spreadsheets to calculate blenderized tube-feed recipes. The math
> isn't new — RDs do it every day. But they do it by hand or in
> spreadsheets that don't survive when they change jobs.
>
> Nestlé built the Compleat® recipe builder — but it's a marketing tool
> with a curated list of 40 foods in fixed servings. RDs don't need a
> food guide. They need a calculator: "tell me what's in my blender, and
> I'll tell you what it delivers — per mL, per day, and compared to
> commercial formula."
>
> So I'm building it. Open-source. Free. Every calculation visible, every
> assumption documented. No black boxes.
>
> It uses Canadian data (CNF 2026) with USDA as a supplement for foods
> CNF doesn't have — because whole foods are whole foods, but packaged
> foods differ across borders. You can also enter custom foods from
> nutrition facts labels. The result: you use what's in your kitchen, at
> the amounts you actually used.
>
> The core insight is the **sweet spot**: every BTF recipe must be thin
> enough to flow through the tube (the RD checks this with a drip test —
> no app can measure thickness) AND dense enough to nourish (the tool
> calculates kcal/mL and shows whether the patient can meet targets
> within their volume tolerance). The tool handles the numbers side; the
> RD handles the physical side.
>
> This isn't a startup. It's a tool that should exist and doesn't.

---

## Appendix A: Methodology — every equation, no black boxes

### A1. Data source

CNF 2026: ~5,993 foods × ~173 nutrients, all per 100 g of edible food.
USDA SR Legacy: ~7,000 whole foods as supplement.
Custom foods: entered from nutrition facts labels, converted to per-100 g.

### A2. Core calculation

```
nutrient_from_ingredient = grams × (Nutrient_Amount / 100)
recipe_total[nutrient] = Σ ( ingredient_grams × (Nutrient_Amount / 100) )
```

Example: 200 g chicken breast at 110 kcal/100 g → 200 × (110/100) = 220 kcal

### A3. Densities

```
kcal_per_mL       = blend_total_kcal / measured_final_volume_mL
protein_per_mL    = blend_total_protein_g / measured_final_volume_mL
free_water_frac   = blend_total_water_g / measured_final_volume_mL
```

Computed **per blend**. Final blend volume is a **measured input** (user
reads it off the blender jug or a measuring cup), not computed.
Ingredients give nutrient totals; measured volume gives the denominator.
There is no separate "added water" term — water is an ordinary
ingredient (CNF moisture ≈ 100%), so it flows into `blend_total_water_g`
like everything else. 1 g water ≈ 1 mL (standard clinical
approximation).

### A4. The Intake Record

The day's intake is one chronological list of rows — *time (optional) ·
source_type · source · amount* — where `source_type` is `blend`,
`formula`, `flush`, or `oral`. Amounts are **recorded, never inferred**:

```
fluid_provided_mL = Σ over rows: each row's own fluid contribution
  blend row    → blend_fluid_fraction × amount   (its counts-as-fluid ingredients)
  formula row  → amount                          (I&O convention: entirely fluid)
  flush row    → amount                          (100% fluid, no nutrients)
  oral row     → amount if counts_as_fluid else 0
```

There is deliberately **no over-draw bookkeeping and no over-draw flag**
— not "warn instead of block," removed as a concept. A blend's
composition is scale-free: 1.2 kcal/mL is 1.2 kcal/mL whether the blend
was made once today or three times. Logging 600 mL against a "400 mL
blend" just means it was made more than once — the ordinary case a
flag would otherwise fire hardest on. The one guard that survives is a
real invalidity, not a judgment call: a blend with ingredients but no
measured volume can't produce a density (division by zero) and must
say so clearly.

### A5. Daily totals

```
daily_[nutrient] = Σ over Intake Record rows:
  blend row    → blend_density_[nutrient] × amount   (calculate_daily_totals)
  formula row  → formula_per_mL_[nutrient] × amount  (energy, protein only;
                   free water via formula_free_water_per_mL × amount, folded
                   into the "water_g" total alongside CNF food moisture)
  flush row    → fluid only (no nutrient contribution)
  oral row     → compute_nutrient_totals([food], amount)  (no volume/density
                   concept — a single food scales the same way a blend
                   ingredient does)
```

One definition of "what the client received," used everywhere:
adequacy, the Tube-Feed/Food-&-Drink/Total breakdown, per-kg display,
the fluid ledger, and the chart note all read from this same sum. A
design that instead multiplies one blend's density by a prescribed
daily volume silently invents batches that were never made; this model
makes that error impossible by construction.

### A6. Adequacy

```
pct_target = (daily_total / target) × 100

status (target_type = RDA | AI | estimate):
  < 90% of target  → "Below target"
  90%–110%         → "Meeting target"
  > 110% of target → "Above target"

status (target_type = UL — a ceiling, not a target to aim for):
  ≤ 100% of target → "Below UL"
  > 100% of target  → "Above UL"
```

Every tracked nutrient carries a `target_type` (RDA / AI / UL /
estimate, empty defaults to "estimate") in the nutrient registry itself
— `data/packs/canada/nutrients.csv`'s `target_type` column, not a
separate targets file. Sodium is the only Canada-pack nutrient marked
`UL`, so it alone uses the second vocabulary — "Meeting target" would
misleadingly imply 90-110% of the UL is the goal, when the actual goal
is simply staying under it.

**There are no default targets anywhere in this design.** Targets
always start blank; the RD enters patient-specific numbers from their
own assessment, or leaves them blank (blank = no adequacy %, daily
totals still shown). The design deliberately carries no targets file at
all — a population default like "2000 kcal / 75 g protein" is not
defensible for tube-fed patients (protein practice runs 1.0-1.5 g/kg,
not the 0.8 g/kg population RDA a default would imply).

**Two report tables, split by nutrient tier** (see Appendix C for the
full rationale — which nutrients are worth showing is itself a
national public-health judgment, encoded per-country in
`data/packs/<pack>/nutrients.csv`):

- **Main adequacy table** (`tier=label` AND `show_in_report=yes`) —
  nine nutrients the author chose to display daily: Energy, Protein,
  Fat, Carbohydrate, Fibre, Sodium, Potassium, Calcium, Iron. Saturated
  Fat, Trans Fat, Cholesterol, and Sugars are `tier=label` too (they're
  on the Canadian panel, so a custom-food label form still asks for
  them, and they're computed and exported) but `show_in_report=no` —
  "show what's needed," not everything (future practice-area additions
  go through this registry column, not a code change). The table also
  carries two fluid rows: **Fluid provided** (full volume of every
  counts-as-fluid contribution across the Intake Record — blend
  ingredients, formula and flush volumes, oral drinks — the I&O
  convention, compared against the Fluid target) and **Free water
  (estimated)** (CNF food moisture from blend/oral rows blended with
  any formula's declared free-water content, secondary/informational,
  no target of its own).
- **BTF micro screen** (`tier=clinical`) — Magnesium, Phosphorus, Zinc,
  Vitamin D, Vitamin B12: tracked for BTF-clinical reasons, not because
  they're on a Canadian label. A one-time ASPEN-style supplementation
  screen, not a daily-tracked panel. None of these nutrients offers a
  target field at all (`offer_target=no` — magnesium and phosphorus
  deliberately so: refeeding-risk monitoring happens in hospital on
  known formulas, not via a BTF default) and so always render "No
  target" — that's intentional, not a gap.

Both tables also carry a **Source** column (can a nutrition-facts label
ever supply this nutrient — "Label + CNF" vs. "CNF only") and a
**Coverage** column (how many of *this recipe's* ingredients actually
had data for this nutrient, e.g. "3/5 ingredients" — flagged only when
incomplete, since a missing CNF row and a true zero otherwise both
silently read as 0). A nutrient with **zero** ingredients supplying a
value is hidden from its table entirely, with a footnote listing what
was hidden — never shown as a confident zero.

### A7. Commercial formula comparator

At same daily volume:
```
BTF daily kcal     = kcal_per_mL × daily_volume_mL
formula daily kcal = formula_kcal_per_mL × daily_volume_mL
```

At same target kcal:
```
BTF volume needed     = target_kcal / kcal_per_mL
formula volume needed = target_kcal / formula_kcal_per_mL
```

The comparator picks up to four formulas via multiselect and shows
them TRANSPOSED — metrics as columns, the BTF as the first row, each
selected formula as a row below, all at the day's volume.

Formula profiles (from EN spreadsheet — `free_water_per_mL` is the same
sheet's W column):

| Formula | kcal/mL | Protein g/mL | Free water/mL |
|---|---|---|---|
| Isosource Fibre 1.5 | 1.5 | 0.068 | 0.765 |
| Isosource Fibre 1.2 | 1.2 | 0.054 | 0.804 |
| Isosource Fibre 1.0 HP | 1.0 | 0.062 | 0.839 |
| Nepro | 1.8 | 0.081 | 0.727 |
| Peptamen AF 1.2 | 1.2 | 0.076 | 0.810 |
| Peptamen Intense High Protein | 1.0 | 0.092 | 0.840 |
| Resource 2.0 | 2.01 | 0.08 | 0.684 |
| Peptamen 1.5 | 1.5 | 0.068 | 0.770 |

### A8. Dilution What-If (recipe-development aid, not the core feature)

The math below backs a *secondary* aid — a one-off "what does thinning
cost?" preview, separate from the actual recipe (see §7 item 6). The
app's real live-recipe-adjustment mechanism needs no special math beyond
A2-A5: every ingredient edit just re-runs `calculate_profile()`. This
section documents `dilute()`, the function behind the preview slider.

General case — adding any liquid:
```
new_volume_mL       = measured_final_volume_mL + added_liquid_mL
new_kcal_per_mL     = (recipe_total_kcal + liquid_kcal) / new_volume_mL
new_protein_per_mL  = (recipe_total_protein_g + liquid_protein_g) / new_volume_mL
new_water_frac      = (recipe_total_water_g + liquid_water_g) / new_volume_mL
```

For pure water: liquid_kcal = 0, liquid_protein_g = 0.
For juice/broth/milk/oil: both numerator and denominator change.

Required daily volume to meet targets:
```
volume_to_meet_kcal    = target_kcal / new_kcal_per_mL
volume_to_meet_protein = target_protein_g / new_protein_per_mL
required_daily_volume  = max(volume_to_meet_kcal, volume_to_meet_protein)
```

### A9. Custom foods from labels

```
per_100_[basis]_value = label_value × (100 / serving_size_[basis])
```

Example: 175 g serving has 130 kcal → per 100 g = 130 × (100/175) = 74.3 kcal

The label form offers a basis unit — "per ___ g" or "per ___ mL" —
matching how a real Nutrition Facts panel is printed. Whichever basis the RD picks flows through, unchanged, to the
separate "Amount used in recipe" field: an mL-basis food's usage can
only be entered in mL, by construction, since converting between them
would require guessing a density the app doesn't have. The math above
is the same either way — it doesn't care whether "100" means grams or
mL, only that the label side and the recipe-usage side agree.

### A10. Limitations

The tool does NOT calculate:
- **Osmolality** — not computable from CNF data
- **Viscosity/tube-flow** — requires physical measurement (drip test);
  thickness ceiling is at most like Resource 2.0
- **Nutrient losses from blending/holding** — real but not quantifiable
- **Food safety** — outside scope
- **Assessment equations** — RD brings their own targets (see Appendix B)

### A11. Key assumptions

1. CNF/USDA values are accurate for the foods used (custom entry covers
   specific products)
2. Measured final volume is accurate (user reads it from a container)
3. 1 g water ≈ 1 mL (standard clinical approximation)
4. No nutrient loss from blending (known limitation)
5. The recipe already works — the tool characterizes, doesn't design

---

## Appendix B: Reference equations (not in the app)

### Energy — predictive equations

**Harris-Benedict:**
- Males: REE = 66.47 + (13.75 × wt) + (5.00 × ht) - (6.75 × age)
- Females: REE = 655.10 + (9.56 × wt) + (1.85 × ht) - (4.68 × age)

**Mifflin-St Jeor:**
- Males: REE = (10 × wt) + (6.25 × ht) - (5 × age) + 5
- Females: REE = (10 × wt) + (6.25 × ht) - (5 × age) - 161

**Penn State** (critically ill, <60 yrs):
- RMR = (0.96 × REE_HB) + (167 × temp°C) + (31 × Ve) - 6212

**Weight-based:** Energy = wt_kg × 20–35 kcal/kg

### Weight considerations

- IBW: Males 48 kg/152 cm + 1.1 kg/cm; Females 45.5 kg/152 cm + 0.9 kg/cm
- AdjBW (CBW > 120% IBW): (CBW - IBW) × 0.25 + IBW
- Amputation adjustments: Hand 0.7%, Foot 1.5%, Lower arm 2.3%, Lower
  leg 5.9%, Entire arm 5%, Entire leg 16%

### Protein

Protein = wt_kg × 0.8–2.0 g/kg (factors: stress, wounds, renal, hepatic)

### Fluid

- Weight-based: wt_kg × 25–35 mL/kg
- Deficit: ((140 - Na) × wt × 0.6) / Na

---

## Appendix C: Internationalization — data pack specification

### The insight this section is built on

Early drafts of this appendix framed internationalization as "swap the
database" — a data task, mechanically true but analytically thin. The
real finding, reached while designing the nutrient tracking layer, is
sharper: **which nutrients are worth showing is itself a national
public-health judgment, not an engineering choice.**

A country's mandatory Nutrition Facts panel is not an arbitrary list —
it is that country's regulator publicly stating which nutrients matter
enough to legislate. That is not an inference from this project; it is
the regulators' own stated reasoning:

- **Health Canada**, in its 2022 nutrition labelling regulations,
  **removed vitamins A and C** from the mandatory panel because *"most
  Canadians get enough of these nutrients"*, and **added potassium**
  because Canadian intakes are low.
- The **FDA**, in its 2016 label overhaul, **added vitamin D and
  potassium** explicitly as *"nutrients of public health concern"* —
  nutrients Americans are commonly short on.

So "track what's on the label" and "use public-health measures to
choose which nutrients to track" turn out to be **the same rule**, and
that rule is per-country by construction — because the underlying
public-health judgment is per-country. A single hardcoded nutrient list
cannot express this; a per-country nutrient *registry* can, and that's
what this project ships.

### Verified mandatory nutrition panels, four countries

| | Canada (13) | US (15) | EU/UK (7) | Australia/NZ (7) |
|---|---|---|---|---|
| Macros | energy, fat, sat, trans, cholesterol, carb, fibre, sugars, protein | same + **added sugars** | energy, fat, saturates, carb, sugars, protein | energy (**kJ**), protein, fat, sat, carb, sugars |
| Sodium | sodium | sodium | **salt** (Na × 2.5) | sodium |
| **Micros** | **potassium, calcium, iron** | **vitamin D, calcium, iron, potassium** | **none** | **none** |
| Fibre | mandatory | mandatory | voluntary | only if a claim is made |

Two consequences fall directly out of this table, and both are things a
hardcoded nutrient list gets structurally wrong:

1. **EU/UK and Australia/NZ mandate zero micronutrients.** A calculator
   built around "the 11 nutrients that matter" has silently baked in a
   Canadian/US assumption that doesn't hold elsewhere.
2. **Vitamin D flips provenance across the Canada/US border** — on the
   US label, absent from the Canadian one. Same nutrient, same CNF/USDA
   lookup code, different truth about whether a consumer-facing label
   can ever supply it. That's a data fact, not a code fact, and the
   registry design (below) is built specifically so it stays that way.

### The pack directory

Each country ships as a **data pack** — a folder of plain CSVs, no code:

```
data/packs/
  canada/
    nutrients.csv          # the registry: what to track, why, and target_type
    formulas.csv            # commercial formula profiles (kcal/mL, protein/mL, free water/mL)
    formula_sources/        # manufacturer HCP PDFs — the audit trail behind formulas.csv
    thinning_liquids.csv    # thinning liquid presets (kcal, protein, water per 100 mL)
  us/                       # FUTURE — same files, US data
    nutrients.csv           #   e.g. vitamin_d_ug moves to tier=label, on_label=yes
    formulas.csv
    thinning_liquids.csv
```

(No `targets.csv` anywhere — there are deliberately no default targets;
see A6. `target_type` lives on the nutrient registry itself.)

Canada is the launch pack. The **acceptance criterion this design is
held to**: adding a country is **writing new CSVs under
`data/packs/<country>/`, with zero Python changes.** The build will be
tested against exactly that — a throwaway US pack promoting
`vitamin_d_ug` to `tier=label, on_label=yes` must move vitamin D into
the main adequacy table and out of the micro screen with no code
change, and every loader (registry, formulas, thinning liquids) must
take the pack as a parameter rather than assuming Canada. One
documented deferral: kJ vs kcal, and the EU's "salt" vs sodium
convention, need a per-pack units-conversion layer (`config.yaml`)
planned beyond the 4-week window.

### `nutrients.csv` — the registry schema

```csv
name,code,label,unit,tier,on_label,show_in_report,offer_target,target_type,decimals,notes
energy_kcal,208,Energy,kcal,label,yes,yes,yes,,0,Canadian NFt core
sodium_mg,307,Sodium,mg,label,yes,yes,yes,UL,0,Canadian NFt core; UL not RDA
potassium_mg,306,Potassium,mg,label,yes,yes,yes,AI,0,Canadian NFt core; added by the 2022 regs — intakes are low
sugars_g,269,Sugars,g,label,yes,no,no,,1,Canadian NFt core; computed and exported, not shown daily
water_g,255,Water (moisture),g,engine,no,no,no,,1,Free-water denominator; no label carries moisture
magnesium_mg,304,Magnesium,mg,clinical,no,yes,no,,1,Author's EN spreadsheet tracks Mg; not on any NFt
vitamin_d_ug,328,Vitamin D,µg,clinical,no,yes,no,,1,ASPEN BTF supplementation screen; on US labels but not Canadian
```

Every nutrient the tool tracks carries **four independent axes** — the
design does not collapse them into one:

- **`tier` — why we track it.**
  - `label`: on this country's mandatory panel — the public-health set,
    eligible for the main adequacy table (subject to `show_in_report`,
    below).
  - `clinical`: tracked for a BTF/clinical reason (the author's EN
    spreadsheet, or ASPEN BTF guidance), not a public-health one —
    shown in a separate, collapsed "BTF micro screen": a **one-time**
    "does this blend need a multivitamin?" check, not a daily-tracked
    panel. Deliberately not hospital-style daily micro tracking — see
    §1's clinical reasoning for why (commercial formula EN doesn't need
    it; refeeding-risk patients are monitored in hospital on known
    formulas; BTF at home is a community/public-health setting).
  - `engine`: needed internally by the calculator (`water_g` only, to
    compute `free_water_fraction`) — never its own report row, in
    either table.
- **`on_label` — can a nutrition-facts label supply it?** Drives the
  custom-food-entry form: a food entered from a label can only ever
  populate the fields that are actually printed on that country's
  label. For the Canada pack, every `label`-tier row is `on_label=yes`
  and every `clinical`/`engine` row is `on_label=no` — but that
  agreement is a fact about *this* pack, not a rule the code enforces.
  A future US pack would set `vitamin_d_ug` to `tier=label,
  on_label=yes`: same CNF/USDA code, different country, different
  truth — pure data, zero code change.
- **`show_in_report` — is it displayed daily, or just tracked?** A
  `tier=label` nutrient can still be hidden from the main adequacy
  table (`show_in_report=no`) while remaining computed and exported —
  this is how "show what's needed, not everything" (Saturated Fat,
  Trans Fat, Cholesterol, Sugars) is expressed: real Canadian label
  fields, still on the custom-food form, just not cluttering the daily
  table. Every `tier=clinical` row is `show_in_report=yes` in the
  Canada pack (the
  micro screen shows all five); `tier=engine` is always `no`.
- **`offer_target` — does the custom-targets form offer a field for
  it?** Only the nine `show_in_report=yes` label-tier nutrients are
  `offer_target=yes`. No `tier=clinical` nutrient offers a target field
  at all — magnesium and phosphorus deliberately so (see A6);
  zinc/vitamin D/B12 likewise, since the micro screen is a one-time
  screen, not something the RD sets a daily number against.

`target_type` (RDA/AI/UL/estimate, empty defaults to "estimate") lives
on this registry rather than a separate targets file — see A6; there
are no default targets anywhere in the design.

The calculator engine reads all four columns off the registry at
runtime; it is to have no Canada-specific branch anywhere. Build Canada
first, architect for swappability — and hold the build to it: the
verification suite will assert that loading a nonexistent pack fails
loudly (`FileNotFoundError`, no silent fallback to a hardcoded Canadian
list), proving the registry is genuinely data-driven rather than a
Canadian default with a data-shaped facade.

---

## References

1. Canadian Nutrient File (CNF) 2026. Health Canada.
2. USDA FoodData Central, SR Legacy subset. US Department of Agriculture.
3. Alberta Health Services. *Home Blended Food for Tube Feeding: Caregiver
   Handbook.* April 2021.
4. Brown T, et al. "Knowledge and clinical practice of ASPEN registered
   dietitian nutritionist members regarding blenderized tube feedings."
   *Nutr Clin Pract.* 2024;39(3):651-664.
5. ASPEN. *Blenderized Tube Feedings: ASPEN Practice Recommendations,
   Sections 1–4.* 2024. nutritioncare.org
6. Compleat® Blend from Scratch recipe builder. compleat.com/blend-from-
   scratch. Powered by Blenderized Diet Recipe Calculator by Robin Cook,
   M.S., R.D., L.D.N. (CHOP).
7. Data Bridge Market Research. *Tube Feeding Nutrition Market.* 2025.
8. Chew HJ, RD. EN spreadsheet. North York General Hospital, Toronto.
9. Reilly C, et al. "A study of professional practices, attitudes and
   barriers to blended tube feeding in Australia and New Zealand."
   *Nutr Diet.* 2025;82(2). doi:10.1111/1747-0080.12909
10. Spurlock AY, et al. "Exploring healthcare facilities' blenderized
    tube feeding policy trends: A survey of registered dietitian
    nutritionists." *Nutr Clin Pract.* 2025. doi:10.1002/ncp.11267
11. Spurlock AY, et al. "Blenderized food tube feeding in patients with
    head and neck cancer." *Nutr Clin Pract.* 2022;37(3):615-624.
    doi:10.1002/ncp.10760
12. Hopkins B, et al. *Prevalence and Management of Enteral Nutrition
    Intolerance in the Non-ICU Setting in Canada.* 2017. (240 RDs,
    ~5,600 EN patients across acute, LTC, and home care.)
13. Health Canada. *Nutrition Facts Table: Regulatory changes* (Food
    Labelling Changes, 2022 coming-into-force). Removed mandatory
    vitamin A and C declarations ("most Canadians get enough of these
    nutrients"); added mandatory potassium. canada.ca/en/health-canada.
14. US Food and Drug Administration. *Changes to the Nutrition Facts
    Label*, 21 CFR 101.9 (2016 final rule). Added vitamin D and
    potassium as mandatory "nutrients of public health concern";
    removed vitamins A and C as mandatory. fda.gov.
15. European Parliament and Council. *Regulation (EU) No 1169/2011 on
    the provision of food information to consumers*, Article 30
    (mandatory nutrition declaration: energy, fat, saturates,
    carbohydrate, sugars, protein, salt). eur-lex.europa.eu.
16. Food Standards Australia New Zealand. *Australia New Zealand Food
    Standards Code — Standard 1.2.8, Nutrition information
    requirements.* foodstandards.gov.au.