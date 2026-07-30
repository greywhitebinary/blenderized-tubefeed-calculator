# USDA SR Legacy Candidates — Is There a Real Gap to Fill?

**Status: analysis only. No code was written for the app. This answers one
question: after fixing the measurement method that produced the earlier
"1,628 new foods" estimate in `USDA_SUPPLEMENT.md`, how many genuinely new,
genuinely useful whole foods does USDA SR Legacy actually add on top of CNF
2026, for a Canadian RD?**

**Short answer: about a dozen, not sixteen hundred.** Read on for the
method, its limits, and why the number collapsed this much.

---

## 0. What was wrong with the earlier estimate

`USDA_SUPPLEMENT.md`'s 1,628-row figure was built correctly in its own
terms — category filter, keyword filter, then a code-based join against
CNF's `USDA_NDB_Code` column — but two things inflated it:

1. **A join bug.** CNF's `USDA_NDB_Code` column is inconsistently
   zero-padded (`"02048"`, 5 digits, next to `"1002"`, 4 digits, for no
   documented reason). A plain string match between CNF's codes and SR
   Legacy's `NDB_number` column only catches codes that happen to be
   padded the same way on both sides. I hit this myself on the first pass:
   naive string matching found 3,333 linked foods; normalising both sides
   to integers before comparing found **4,448** — exactly the number
   `USDA_SUPPLEMENT.md` reports, confirming this was the intended figure
   and the bug was in how I first tried to reproduce it, not in the
   original number. This matters because it's the same *class* of error
   as the wild-rice problem below: a mechanical join that looks clean but
   silently drops real matches because of a formatting quirk neither side
   documents.
2. **No check for whether the "new" rows were actually new.** The
   1,628-row list was never screened for whether CNF already had the same
   food under different words. It hadn't been — that's the substance of
   this review.

## 1. Method

**Step 1 — the reliable backbone: match by numeric code, not name.**
CNF's `Food_Name.csv` carries a `USDA_NDB_Code` column for 4,798 of its
5,993 foods (80%) — Health Canada's own paper trail of which USDA food
each CNF entry was adapted from. Joining that (as integers, per the fix
above) against SR Legacy's own `NDB_number` column in
`sr_legacy_food.csv` links **4,448 of SR Legacy's 7,793 foods (57%)**
cleanly. These are definitively already in CNF — no fuzzy matching
involved, just two databases agreeing on an ID.

**Step 2 — for the 3,345 unlinked remainder, match on word tokens.** This
is where the "wild rice" lesson from the brief applies. I did not search
CNF for `"wild rice"` as a substring (zero hits) and conclude it's
missing — I split both the USDA name and the CNF name into individual
words, dropped CNF's leading taxonomy word (`"Grains,"` in `"Grains,
rice, wild, dry"`) and USDA's parenthetical qualifiers, and asked: do the
significant words in the USDA name all show up somewhere in some CNF
name? For `"wild rice"` against `"Grains, rice, wild, cooked"`, yes — a
perfect match once you strip the organisational prefix.

The tricky part is knowing *which* leading words are pure organisational
scaffolding (safe to drop: "Grains," "Game," "Snacks," "Fast," "Soup,"
"Fruit," …) versus which leading words are the food's actual identity
even though they also look like a category (`"Beef, ground, lean, raw"`
— "Beef" isn't filler here, it's the only species word in the name, so
stripping it would break the match). I checked this empirically against
the real distribution of leading words in CNF's 5,993 names rather than
guessing, and calibrated the list accordingly.

**Step 3 — restrict to whole/minimally-prepared foods.** Same 13
categories and processed-food keyword exclusions (`canned`, `cured`,
`smoked`, `breaded`, `fast food`, `luncheon`, `sausage`, …) as
`USDA_SUPPLEMENT.md` used, applied to the unlinked remainder. This
produced 1,654 rows — close to, not identical to, the earlier 4,180 minus
1,628 math; the small difference is a slightly different keyword list, not
a different method.

## 2. Validating the matcher before trusting it

Two checks, not one, because a matcher that only passes on easy cases
isn't validated:

**Check A — 33 short, known-in-CNF search terms**, including the exact
wild-rice example from the brief, several Indigenous foods (caribou,
seal, moose, walrus, beluga, narwhal, muktuk, arctic char, cloudberry),
and ordinary staples (banana, salmon, oats, quinoa). **33/33 (100%)**
found a CNF match at full token coverage. This confirms the method does
what the brief's worked example asked it to do.

**Check B — a harder, more honest test.** I took 25 real SR Legacy foods
already **confirmed identical to a CNF food via the NDB code join**
(ground truth — no guessing) and ran the token matcher on their full,
real, messy descriptions (not the clean short search terms from Check A)
to see if it *independently* rediscovers a good match using only the
text. **16 of 25 (64%)** matched well (coverage ≥ 0.7) on the first try.
I read all 9 misses by hand. Two concrete failure modes showed up:

- **No stemming.** USDA's `"Longans, raw"` (plural) vs. CNF's `"Longan,
  raw"` (singular) share zero tokens under exact string match — a
  one-letter difference erases the whole match. A real weakness, not a
  hypothetical one.
- **Tie-breaking picks the wrong species when a generic word inflates
  both candidates equally.** USDA's `"Chicken, heart, all classes,
  raw"` tied exactly with both CNF's correct `"Chicken, broiler, heart,
  raw"` and the wrong `"Turkey, all classes, heart, raw"` — the shared
  phrase `"all classes"` counts the same either way, and my code broke
  the tie by whichever the internal index happened to find first.

**What this means for the headline number:** both failure modes make the
matcher **less** likely to recognise a true duplicate, which pushes
"genuinely new" numbers **up**, not down. So the method's known bias is
toward *overestimating* novelty — the safer direction for a review whose
whole point is not to overclaim. Any residual error in the final
shortlist below is more likely a false "new" than a hidden real gap.

## 3. The real number, and how it compares to 1,628

| Stage | Rows |
|---|---|
| SR Legacy total | 7,793 |
| Linked to CNF via corrected NDB-code join | 4,448 (57%) |
| Unlinked | 3,345 |
| ...restricted to whole/minimally-prepared categories | 1,654 |
| ...minus token-matched CNF duplicates the code join missed | **1,568** |

1,568 is already a big drop from "1,628 skip the token-matching step
entirely" — but it is **still not the real number**, and I don't think
it's honest to present it as one. I hand-reviewed every row in the
smaller categories (Vegetables, Fruits, Finfish/Shellfish, Nuts/Seeds,
Spices — 48 rows total) and sampled the larger ones (Dairy, Fats and
Oils, Legumes, Cereal Grains, Poultry — 377 rows), and the 1,568 is
dominated by exactly the kind of content Appendix C already rules out or
this tool has no use for:

- **1,143 rows (73%) are Beef, Pork, or Lamb/Veal/Game** — fine-grained
  butchery cuts (a dozen near-identical "top round" vs. "bottom round"
  distinctions). Excluded categorically, per the task brief, regardless
  of CNF status.
- **A large share of Dairy (107) and Legumes (55) is branded product
  names** — CHOBANI, DANNON OIKOS, KRAFT, SILK, Vitasoy, HOUSE FOODS,
  UNCLE BEN'S, Bolthouse Farms, Odwalla, Naked Juice. Appendix C's own
  rule (whole foods cross borders, packaged foods don't) excludes these
  by definition, and the same CHOBANI leak `USDA_SUPPLEMENT.md` already
  flagged is still here, plus many more branded rows alongside it.
- **Most of Fats and Oils (98)** is food-service/industrial formulation
  (`"Oil, industrial, soy (partially hydrogenated), principal uses
  candy coatings"`) — not something a home blender kitchen has.
- **Most of Poultry (75)** is brine-injected retail poultry (`"with added
  solution"`) — a processed product, not a whole food.
- **A meaningful slice of what's left is already in CNF under different
  wording** — I hand-confirmed this for semolina, sorghum flour, several
  tofu-coagulant variants, mixed nuts, sunflower seeds, and goat meat/milk/
  cheese, all of which the token matcher's coverage threshold (0.8) was
  too strict to catch automatically, but a direct lookup shows CNF already
  has them, in some cases (goat) with *more* variety than USDA.

**After that pass, the count of foods that are (a) genuinely absent from
CNF and (b) something a Canadian RD would plausibly reach for is
approximately 12** — see the shortlist below. That is roughly **2 orders
of magnitude smaller** than the original 1,628 estimate, and about 8%
of even the improved 1,568 mechanical figure. If the earlier number was
pitched publicly as "1,628 new foods," that framing does not survive
contact with what's actually in those rows.

`data/usda_candidates.csv` contains these 12 rows — one row per
genuinely-new, genuinely-relevant candidate, with its FDC ID, NDB
number, category, a short reason, a confidence rating, and (where one
exists) the nearest CNF food it is not the same as.

## 4. The curated shortlist, grouped by why it matters

### Latin American cheeses (the strongest finding)
CNF names exactly three Mexican cheeses — anejo, asadero, chihuahua.
USDA SR Legacy has four more, and they are not variants of the ones CNF
already has — they're different cheeses (different moisture, different
use):

- **Queso fresco** — fresh, mild, crumbly; used in tacos, salads, as a
  topping.
- **Queso blanco** — fresh white cheese, similar family, distinct
  product.
- **Queso seco** — aged, firm, drier.
- **Queso cotija** — aged, salty, crumbly ("Mexican parmesan").

This is the one place the review found a real, clean, "a Canadian RD
serving a Latin American family would actually go looking for this and
not find it in CNF" gap.

### Pacific/Filipino ingredients
- **Mountain yam (Hawaii)**, raw and two cooked/salted forms — a
  distinct yam species/variety from CNF's generic `"Yam, raw"`, used in
  Hawaiian and Filipino cooking.
- **Tree fern, cooked** (with and without salt) — a fiddlehead-like
  vegetable (pako/paco) used in Filipino cooking. Genuinely absent from
  CNF (zero shared tokens, not a formatting mismatch).

### Niche Latin American / Caribbean fruit
- **Naranjilla (lulo)** — South/Central American fruit used as juice or
  puree.
- **Nance** — a small Central American/Caribbean fruit.
- **Muscadine grapes** — a real US-native grape variety absent from CNF,
  though it's a crop that doesn't grow in or get commonly imported to
  Canada, so its practical value here is the lowest of the twelve.

### What I looked at and didn't include
Turtle (green, raw) and a specific date variety (deglet noor, as
distinct from CNF's existing "Date, domestic" and "Date, medjool") are
genuinely absent from CNF by the same method, but I left them off the
shortlist — turtle isn't something a BTF recipe would use, and deglet
noor is a variety-level distinction under a fruit CNF already has two
entries for. Included in the interest of completeness, not because they
clear the "an RD would reach for this" bar.

## 5. Indigenous foods — checked directly, not excluded by default

This is the piece the task asked to be examined rather than waved away,
so here's what I actually found.

SR Legacy's `"American Indian/Alaska Native Foods"` category has 165
rows; 71 of them already link to CNF via the NDB code join, leaving 94
unlinked. I ran the token matcher and hand-reviewed all 94. Two clear
patterns:

1. **Where USDA and CNF cover the same species (caribou, seal, moose,
   walrus, beluga, narwhal, muktuk, bear, bison, elk), CNF's own
   "Game meat, Indigenous" series is already the richer source** —
   verified directly: CNF has 20 caribou entries, 24 seal, 15 moose, 12
   walrus, 9 beluga, 8 narwhal, 8 muktuk, 7 bear, 13 bison, 9 elk, plus a
   chokecherry and 3 lambsquarters entries some of the "new" USDA rows
   turned out to duplicate. The 94 "unlinked" rows for these species are
   mostly a different cut or prep of an animal CNF already has extensive
   coverage of (e.g., USDA's "Caribou, hind quarter meat, raw" against
   CNF's already-present "Game meat, Indigenous, caribou (reindeer),
   meat, raw") — not a new food, a finer cut of an existing one.
2. **The rows that are genuinely novel are specific tribal dishes from
   US Southwest, Plains, and Pacific Northwest nations** — Navajo (kneel-
   down bread, blue-corn piki bread, mutton-and-corn stew, tortillas),
   Hopi (piki bread, tamales, pinto bean and hominy stew), Apache (tennis
   bread, acorn stew), Klamath (wocas — pond-lily seeds). These are real
   gaps in the sense that neither database has them — but they document
   US tribal culinary traditions with no equivalent in the Canadian
   First Nations, Inuit, or Métis foods CNF's own series already covers.
   They are also finished dishes (stews, breads), not raw ingredients a
   Canadian RD would blend from scratch.

**Verdict on Indigenous foods specifically: USDA adds close to nothing
usable for a Canadian RD here.** The overlap that exists is already
better served by CNF's own series; the genuine additions are
US-tribe-specific and don't serve the population a Canadian tool is
built for. None of the 94 made the shortlist above.

## 6. Verdict: is this worth 3–5 days of build?

**No, not as originally scoped — and the honest number is exactly why.**

`USDA_SUPPLEMENT.md`'s 3–5 day estimate covers real, necessary
engineering if you're integrating a second database: the
`Ingredient.source` field, the two-lookup-table branch in
`_scale_ingredients()`, `nutrient_map.csv` plus its `verify_backend.py`
assertion, provenance surfacing across five UI touchpoints, and the
CNF-first/USDA-fallback search trigger. That is legitimate,
well-scoped work *if the payoff is 1,628 new foods*. It is not
proportionate work for **12 rows**, four of which are variants of a
single cheese category.

The 12 real foods this review found are better captured a different
way entirely: **type them in by hand through the app's existing custom-
food-entry form**, the same path already built for any food neither
database has (dal, egusi, and now queso fresco/cotija/blanco/seco,
naranjilla, nance, muscadine, mountain yam, tree fern). That's roughly
an hour of data entry against public nutrient references, not a
multi-day two-database integration — and it captures 100% of the real
value this review found, with none of the added maintenance surface
(a second lookup table, a nutrient-code mapping to keep in sync, a
2018-vintage data-freshness risk the original proposal itself flagged
for exactly this kind of residual packaged-adjacent row, five UI
surfaces to build and test).

If the author's goal was specifically "fix the ethnic/cultural-food
gap" — the motivating framing in `BUSINESS_CASE.md` §8 — this review
confirms `USDA_SUPPLEMENT.md`'s own finding and sharpens it: most of the
named motivating examples (plantain, cassava, okra, yam, taro,
breadfruit, tamarind, jackfruit) are already in CNF, and the dal/egusi
gap USDA doesn't fix either. What USDA *does* add, once honestly
filtered, is a short, specific list — four Mexican cheeses foremost —
worth having, not worth building a second database architecture for.

**Recommendation: skip the SR Legacy integration. Hand-enter the 12
rows in `data/usda_candidates.csv` as custom foods if/when a pilot RD
asks for them.** Revisit a real USDA integration only if a future US
version of this tool needs it for its own reasons (per the author's own
conclusion that a US version is a separate product, not an upgrade) —
not to serve the Canadian tool this review was asked about.
