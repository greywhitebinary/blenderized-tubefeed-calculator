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
the growing, underserved corner of this niche. This tool ships with
adult DRI defaults.

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
| Mental math for delivery schedules | Flexible delivery input (syringe/pump/direct) |
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
   label. Enter grams per ingredient, added water, and measured final
   blend volume. **Use what's in your kitchen, at the amounts you
   actually used.**

2. **Live density panel.** kcal/mL, protein/mL, free-water fraction —
   updated instantly as ingredients change. Per-mL density is the
   primary lens because the patient can only tolerate so many mL/day.
   The tool shows density live; the RD checks flow with a drip test.

3. **Flexible delivery input.**
   - Syringe bolus: ___ mL × ___ times/day
   - Pump: ___ mL/hr × ___ hours/day
   - Direct: ___ mL/day

   The AHS handbook confirms syringe bolus is the primary method for
   BTF: *"Home blended food is mostly offered by syringe as the blend
   may be thicker than formula"* and *"Pumps are not routinely provided
   because their design does not work well with home blended food."*

4. **Adequacy report, in two tiers.** At the entered daily volume: a main
   table of every nutrient on this country's mandatory Nutrition Facts
   panel (13 for Canada — energy, protein, fat, saturated fat, trans
   fat, cholesterol, carbohydrate, fibre, sugars, sodium, potassium,
   calcium, iron) plus free water, vs. optional target inputs. Status
   indicators: meeting / below / above target — except sodium (a
   Tolerable Upper Intake Level, not a target to aim for), which reads
   "Below UL" / "Above UL" instead. A second, collapsed **"BTF micro
   screen"** shows magnesium, phosphorus, zinc, vitamin D, and vitamin
   B12 — nutrients not on a Canadian label but clinically relevant to
   BTF (the author's EN spreadsheet tracks magnesium/phosphorus; the
   rest are an ASPEN-style one-time supplementation check, not a
   daily-tracked panel). See Appendix C for why the split exists.

5. **Commercial formula comparator.** Side-by-side: "Your BTF at 1,200
   mL/day = 1,560 kcal, 78 g protein. Peptamen 1.5 at 1,200 mL/day =
   1,800 kcal, 81.6 g protein."

6. **Live recipe adjustment.** There is no separate "what-if mode" — the
   recipe builder IS the what-if. Every edit updates everything
   instantly. The RD iterates: tweak → check numbers → drip test →
   tweak again.

   **Thinning liquids aren't just water.** Water (pure dilution), apple
   juice (adds calories), broth (adds sodium + protein), milk (adds
   calories + protein + calcium), oil (adds fat). The AHS handbook
   confirms: *"If your child needs more calories add: milk, juice, oil,
   formula"* vs. *"If your child does not need more calories add:
   cooking liquid, water."* The tool shows the impact of each choice.

7. **Export.** Save recipe as JSON. Export results for chart
   documentation.

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
both ship with the repo. No API keys needed.

---

## 12. The 4-week build plan

| Week | Deliverable | What gets built |
|---|---|---|
| **1 — Plan It** | This document posted publicly | Concept, market, requirements, methodology |
| **2 — Core Feature** | Working Streamlit app: recipe builder → density panel → delivery input → adequacy report → commercial comparator | Fix data loader; build calculator, measures, targets/report, Streamlit UI |
| **3 — Build to Last** | Tests, CI, deploy, custom food entry, USDA supplement | pytest suite, GitHub Actions, Streamlit Cloud deploy, label-entry, USDA data load |
| **4 — Ship + Pitch** | Live app + 2–3 min demo | Polish, export, demo video |

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
kcal_per_mL       = recipe_total_kcal / measured_final_volume_mL
protein_per_mL    = recipe_total_protein_g / measured_final_volume_mL
free_water_frac   = (recipe_total_water_g + added_water_mL) / measured_final_volume_mL
```

Final blend volume is a **measured input** (user poured it into a
container), not computed. Ingredients give nutrient totals; measured
volume gives the denominator.

### A4. Delivery

```
Syringe bolus:  daily_volume_mL = bolus_volume_mL × times_per_day
Pump:           daily_volume_mL = rate_mL_per_hr × hours_per_day
Direct:         daily_volume_mL = user-entered value
```

### A5. Daily totals

```
daily_kcal       = kcal_per_mL × daily_volume_mL
daily_protein_g  = protein_per_mL × daily_volume_mL
daily_[nutrient] = (recipe_[nutrient] / measured_volume_mL) × daily_volume_mL
```

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
estimate) in `data/packs/canada/targets.csv`. Sodium is a UL, so it
uses the second vocabulary — "Meeting target" would misleadingly imply
90-110% of the UL is the goal, when the actual goal is simply staying
under it.

**Two report tables, split by nutrient tier** (see Appendix C for the
full rationale — which nutrients are worth showing is itself a
national public-health judgment, encoded per-country in
`data/packs/<pack>/nutrients.csv`):

- **Main adequacy table** (`tier=label`) — every nutrient on the
  Canadian Nutrition Facts panel: Energy, Protein, Fat, Saturated Fat,
  Trans Fat, Cholesterol, Carbohydrate, Fibre, Sugars, Sodium,
  Potassium, Calcium, Iron — plus the derived Free water row (compared
  against the Fluid target).
- **BTF micro screen** (`tier=clinical`) — Magnesium, Phosphorus, Zinc,
  Vitamin D, Vitamin B12: tracked for BTF-clinical reasons, not because
  they're on a Canadian label. A one-time ASPEN-style supplementation
  screen, not a daily-tracked panel. Magnesium and phosphorus
  deliberately have no default target (refeeding-risk monitoring
  happens in hospital on known formulas, not via a BTF default) and so
  render "No target" — that's intentional, not a gap.

Both tables also carry a **Source** column (can a nutrition-facts label
ever supply this nutrient — "Label + CNF" vs. "CNF only") and a
**Coverage** column (how many of *this recipe's* ingredients actually
had CNF data for this nutrient, e.g. "3/5 ingredients" — flagged only
when incomplete, since a missing CNF row and a true zero otherwise both
silently read as 0).

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

Formula profiles (from EN spreadsheet):

| Formula | kcal/mL | Protein g/mL |
|---|---|---|
| Isosource Fibre 1.5 | 1.5 | 0.068 |
| Isosource Fibre 1.2 | 1.2 | 0.054 |
| Isosource Fibre 1.0 HP | 1.0 | 0.062 |
| Nepro | 1.8 | 0.081 |
| Peptamen AF 1.2 | 1.2 | 0.076 |
| Peptamen Intense High Protein | 1.0 | 0.092 |
| Resource 2.0 | 2.01 | 0.08 |
| Peptamen 1.5 | 1.5 | 0.068 |

### A8. Live recipe adjustment (thinning with different liquids)

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
per_100g_value = label_value × (100 / serving_size_g)
```

Example: 175 g serving has 130 kcal → per 100 g = 130 × (100/175) = 74.3 kcal

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
real finding, reached while building the nutrient tracking layer, is
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
    nutrients.csv          # the registry: what to track, and why
    targets.csv             # DRI / tube-feed targets, with target_type
    formulas.csv             # commercial formula profiles (kcal/mL, protein/mL)
    thinning_liquids.csv     # thinning liquid presets (kcal, protein, water per 100 mL)
  us/                       # NOT YET BUILT — same four files, US data
    nutrients.csv            #   e.g. vitamin_d_ug moves to tier=label, on_label=yes
    targets.csv
    formulas.csv
    thinning_liquids.csv
```

Canada is the only pack implemented today. The goal — and the acceptance
criterion this design is held to — is that adding a country is **writing
new CSVs under `data/packs/<country>/`, with zero Python changes.**

Status against that criterion, stated honestly:

- **Met** for `nutrients.csv` and `targets.csv`. The registry, the
  targets loader, and both report functions all take a `pack` argument.
  Verified: a US pack promoting `vitamin_d_ug` to `tier=label,
  on_label=yes` moves vitamin D into the main adequacy table and out of
  the micro screen with no code change.
- **Not yet met** for `formulas.csv` and `thinning_liquids.csv`. These
  still load once from a hardcoded `canada` path
  (`_load_commercial_formulas()` in `src/calculator.py`,
  `_load_thinning_liquids()` in `app/streamlit_app.py`). A US pack would
  currently get US nutrients and US targets but **Canadian formulas** —
  which matters, since commercial formulary is among the most
  country-specific data in the tool. Parameterizing these two loaders by
  `pack` is the outstanding work to fully meet the criterion.
- **Deferred by design** to a future `config.yaml` per pack: kJ vs kcal,
  and the EU's "salt" vs sodium convention, which need a units-conversion
  layer this project hasn't built yet.

### `nutrients.csv` — the registry schema

```csv
name,code,label,unit,tier,on_label,decimals,notes
energy_kcal,208,Energy,kcal,label,yes,0,Canadian NFt core
sodium_mg,307,Sodium,mg,label,yes,0,Canadian NFt core; added 2022 regs
water_g,255,Water (moisture),g,engine,no,1,Free-water denominator; no label carries moisture
magnesium_mg,304,Magnesium,mg,clinical,no,1,Author's EN spreadsheet tracks Mg; not on any NFt
vitamin_d_ug,328,Vitamin D,µg,clinical,no,1,ASPEN BTF supplementation screen; on US labels but not Canadian
```

Every nutrient the tool tracks carries **two independent axes** — the
design does not collapse them into one:

- **`tier` — why we track it.**
  - `label`: on this country's mandatory panel — the public-health set,
    shown in the main adequacy table.
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

The calculator engine (`src/calculator.py`, `src/report.py`) reads
`tier` and `on_label` off the registry at runtime; it has no
Canada-specific branch anywhere. Build Canada first, architect for
swappability — and the swap is real: it was exercised in this
project's own verification suite (`load_registry("no_such_pack")` must
raise `FileNotFoundError`, proving the registry is genuinely
data-driven rather than a Canadian default with a data-shaped facade).

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