"""
report.py — Adequacy report: daily totals vs targets + formula comparison.

Phase 5 of the BTF Calculator; reworked in the round-2 clinical feedback
pass, then again per FEED_LOG_REWORK.md (the Intake Record rework).

generate_adequacy_report() and generate_clinical_screen() take a
daily_totals dict (nutrient_name -> amount, already "daily") rather than a
single NutrientProfile + daily_volume_mL — the Intake Record can span
several blends, commercial formulas, flushes, and oral foods in one day
(src.intake.aggregate_intake() is what produces that dict), so there is no
longer one profile these functions can compute daily totals from
internally. Per-blend functions (generate_density_summary(),
generate_comparator_table(), generate_formula_comparison()) still take a
NutrientProfile — densities are still a per-blend lens (design doc
section 3.5). generate_source_breakdown() is new: the Tube-Feed vs
Food-&-Drink vs Total subtotal table, built directly from an IntakeTotals'
per-source subtotals. generate_regimen_summary() (the old combined
BTF + commercial-formula summary) is REMOVED — a formula is now just
another Intake Record row, so aggregate_intake() already produces the
combined totals, and generate_source_breakdown() gives the "combined, but
still split" view the regimen summary existed for.

Adequacy logic (Appendix A6), for target_type in {RDA, AI, estimate}:
    pct_target = (daily_total / target) × 100

    status:
      < 90% of target  → "Below target"
      90%–110%         → "Meeting target"
      > 110% of target → "Above target"

For target_type == "UL" (a ceiling, not something to aim for — e.g.
sodium), the vocabulary is different: >100% of a UL is "Above UL", and
anything ≤100% is "Below UL". "Meeting target" would misleadingly imply
90-110% is the goal, when for a UL the goal is simply staying under it.
target_type now lives on the nutrient registry itself (NutrientDef.
target_type — see src/nutrients.py) rather than a separate targets.csv;
UL-ness is a property of the nutrient, not of a default value.

Two report tables, split by nutrient tier (src/nutrients.py):
  - generate_adequacy_report()  → tier="label" nutrients with
    show_in_report="yes" (this country's mandatory Nutrition Facts panel,
    filtered to the nutrients the author chose to display daily — sat
    fat/trans fat/cholesterol/sugars are still tracked and exported, just
    not shown here) + the derived Fluids provided / Free water rows. This
    is the MAIN table.
  - generate_clinical_screen()  → tier="clinical" nutrients (a one-time
    ASPEN-style "does this blend need a multivitamin?" screen — not a
    daily-tracked panel). A SEPARATE, collapsed table.
tier="engine" nutrients (water_g) never get a row in either table — they
exist only to feed internal calculations (free_water_fraction).

Both tables now hide any row whose per-recipe coverage is 0/N (no
ingredient supplied a value at all) — a confident-looking "0" for a
nutrient no ingredient could ever have supplied is worse than not
showing the row. The dropped nutrient names are returned alongside the
DataFrame so the caller can render a footnote ("not shown — no data from
any ingredient: X, Y").

The report is returned as a pandas DataFrame for easy display in the
Streamlit UI (st.dataframe, st.table) and export to Excel.
"""

import pandas as pd

try:
    from src.calculator import compare_with_formula, COMMERCIAL_FORMULAS
    from src.models import NutrientProfile
    from src.nutrients import NutrientDef, defs_for_tier, registry_by_name, DEFAULT_PACK
    from src.intake import (
        TUBE_FEED_LABEL as _TUBE_FEED_LABEL,
        FOOD_DRINK_LABEL as _FOOD_DRINK_LABEL,
        TOTAL_LABEL as _TOTAL_LABEL,
    )
except ImportError:
    from calculator import compare_with_formula, COMMERCIAL_FORMULAS
    from models import NutrientProfile
    from nutrients import NutrientDef, defs_for_tier, registry_by_name, DEFAULT_PACK
    from intake import (
        TUBE_FEED_LABEL as _TUBE_FEED_LABEL,
        FOOD_DRINK_LABEL as _FOOD_DRINK_LABEL,
        TOTAL_LABEL as _TOTAL_LABEL,
    )


# Adequacy status thresholds (Appendix A6)
BELOW_THRESHOLD = 0.90  # < 90% → Below
ABOVE_THRESHOLD = 1.10  # > 110% → Above

# Source column text (P1-4 / P1-6): tells the RD whether a custom food
# entered from a nutrition facts label could ever supply this nutrient.
_SOURCE_ON_LABEL = "Label + CNF"
_SOURCE_CNF_ONLY = "CNF only — labels don't carry this"


def _adequacy_status(daily_total: float, target: float, target_type: str = "estimate") -> str:
    """Determine adequacy status for a nutrient.

    For target_type == "UL" (a ceiling — e.g. sodium):
      ≤ 100% of target → "Below UL"
      > 100% of target  → "Above UL"

    For every other target_type (RDA / AI / estimate):
      < 90% of target  → "Below target"
      90%–110%         → "Meeting target"
      > 110% of target → "Above target"

    If target is 0 (not entered), returns "No target" regardless of type.
    """
    if target <= 0:
        return "No target"
    pct = daily_total / target
    if target_type == "UL":
        return "Above UL" if pct > 1.0 else "Below UL"
    if pct < BELOW_THRESHOLD:
        return "Below target"
    elif pct > ABOVE_THRESHOLD:
        return "Above target"
    else:
        return "Meeting target"


def _fmt(value: float, decimals: int) -> str:
    """A number rendered at ITS OWN precision, as text.

    A pandas numeric column formats to a single width, so one nutrient
    with a decimal drags every other value in the column along with it:
    Energy (0 dp in the registry) rendered as "2204.0" purely because
    Protein (1 dp) shared the column (author, 2026-08-10). Nobody quotes
    a day as 2204.0 kcal. Returning text is what lets each row keep the
    decimals the registry actually gives it.

    The report frames are display/export artefacts -- one row per
    nutrient, never summed or sorted downstream -- so text costs nothing
    here. The reloadable Intake sheet stays numeric.
    """
    return f"{value:.{max(decimals, 0)}f}"


def _source_text(nutrient_def: NutrientDef) -> str:
    """'Can a custom food entered from a label supply this nutrient?'"""
    return _SOURCE_ON_LABEL if nutrient_def.on_label else _SOURCE_CNF_ONLY


def _coverage_text(name: str, coverage: dict[str, tuple[int, int]]) -> str:
    """'How many of THIS recipe's ingredients actually had data for this
    nutrient?' (P2 — per-recipe coverage provenance, on top of the
    registry's static on_label flag from P1).

    Only flags incomplete coverage (n_supplying < n_total) — full
    coverage is the expected case and renders "—", same convention as
    the Target/% Target columns for "nothing to flag here".
    """
    n_supplying, n_total = coverage.get(name, (0, 0))
    if n_total > 0 and n_supplying < n_total:
        # "sources", not "ingredients" (author's ruling 2026-07-30). On a
        # whole day this counts three different kinds of thing, and only
        # one of them is an ingredient: a blend contributes one per
        # ingredient PER FEED, a commercial formula contributes exactly
        # one (it is a finished product, not an ingredient list), and an
        # oral food contributes one. The real example day reads 36/40 --
        # 4 blend feeds x 9 ingredients, + 3 formula feeds, + 1 banana --
        # for a day involving only 11 distinct foods.
        #
        # The NUMBER is deliberately left as-is: counting a blend once
        # per feed weights the note by how much each thing actually
        # contributed to the day, which is the question an RD is asking.
        # Only the noun was wrong.
        return f"{n_supplying}/{n_total} sources"
    return "—"


def _zero_coverage(name: str, coverage: dict[str, tuple[int, int]]) -> bool:
    """True when NO ingredient in this recipe supplied a value for this
    nutrient (0/N, N>0) — the row would render a confident-looking "0"
    that isn't a measured zero, just an absence of data. Rows like this
    are dropped from display (see _hide_zero_coverage below); N==0 (an
    empty recipe) is not this case and is left alone.
    """
    n_supplying, n_total = coverage.get(name, (0, 0))
    return n_total > 0 and n_supplying == 0


# Per-kg is shown ONLY for these, not every nutrient (author, 2026-08-01).
# kcal/kg, protein g/kg and fluid mL/kg are what adult practice actually
# quotes; sodium mg/kg and potassium mg/kg are paediatric figures, and a
# column that fills them in everywhere implies all the rows are equally
# comparable when they are not. Everything else renders "—", the same
# "nothing to say here" convention the Target/% Target columns already use.
# Value maps to how many decimals that figure is normally quoted at.
PER_KG_DECIMALS: dict[str, int] = {
    "energy_kcal": 1,
    "protein_g": 2,
}
PER_KG_FLUID_DECIMALS = 1


def _per_kg_cell(name: str, daily_val: float, patient_weight_kg: float | None):
    """The Per kg cell for one row, or "—" when it isn't a per-kg figure."""
    if not patient_weight_kg or patient_weight_kg <= 0 or name not in PER_KG_DECIMALS:
        return "—"
    return round(daily_val / patient_weight_kg, PER_KG_DECIMALS[name])


# Clinical reading order for the report tables (author, 2026-08-08),
# matching the Nutrition Targets form. The registry is ordered like a
# Nutrition Facts TABLE, which is how a label is laid out; a dietitian
# reads energy and protein first and works down. Anything not named here
# keeps its registry order underneath, so adding a nutrient to
# nutrients.csv still lands somewhere sensible without touching this.
REPORT_LEAD_ORDER = ("energy_kcal", "protein_g", "carbohydrate_g", "fat_g")


def _ordered_label_defs(pack: str) -> list[NutrientDef]:
    """tier="label" rows that get displayed, in clinical reading order."""
    defs = [d for d in defs_for_tier("label", pack=pack) if d.show_in_report]
    by_name = {d.name: d for d in defs}
    lead = [by_name[n] for n in REPORT_LEAD_ORDER if n in by_name]
    return lead + [d for d in defs if d.name not in REPORT_LEAD_ORDER]


def _tier_rows(
    defs: list[NutrientDef],
    daily_totals: dict[str, float],
    targets: dict[str, float],
    coverage: dict[str, tuple[int, int]],
    patient_weight_kg: float | None = None,
) -> list[dict]:
    """Build report rows for a list of NutrientDef (one tier's worth).

    target_type now comes straight off each NutrientDef (registry-owned —
    see src/nutrients.py) instead of a separate targets.csv-derived dict;
    an empty target_type ("" — every nutrient except sodium today)
    behaves as "estimate" (the default, non-UL vocabulary).
    """
    rows = []
    for d in defs:
        daily_val = daily_totals.get(d.name, 0.0)
        target_val = targets.get(d.name, 0.0)
        ttype = d.target_type or "estimate"
        pct = (daily_val / target_val * 100) if target_val > 0 else 0.0
        status = _adequacy_status(daily_val, target_val, ttype)

        row: dict = {
            "Nutrient": d.label,
            "Daily Total": _fmt(daily_val, d.decimals),
            "Unit": d.unit,
        }
        # Column only exists when a weight was entered -- an all-"—"
        # column would be noise for the many days with no weight.
        if patient_weight_kg:
            row["Per kg"] = _per_kg_cell(d.name, daily_val, patient_weight_kg)
        rows.append(
            {
                **row,
                "Target": _fmt(target_val, d.decimals) if target_val > 0 else "—",
                "% Target": _fmt(pct, 0) if target_val > 0 else "—",
                "Status": status,
                "Source": _source_text(d),
                "Coverage": _coverage_text(d.name, coverage),
                "_zero_coverage": _zero_coverage(d.name, coverage),
            }
        )
    return rows


def _finalize(rows: list[dict]) -> tuple[pd.DataFrame, list[str]]:
    """Split rows into (visible DataFrame, hidden nutrient names).

    Drops any row flagged `_zero_coverage` before returning — see
    _zero_coverage() above — and strips the internal flag column either
    way so callers never see it.
    """
    hidden = [r["Nutrient"] for r in rows if r.get("_zero_coverage")]
    visible = [
        {k: v for k, v in r.items() if k != "_zero_coverage"}
        for r in rows
        if not r.get("_zero_coverage")
    ]
    return pd.DataFrame(visible), hidden


def generate_adequacy_report(
    daily_totals: dict[str, float],
    targets: dict[str, float] | None = None,
    pack: str = DEFAULT_PACK,
    fluid_provided_mL: float | None = None,
    nutrient_coverage: dict[str, tuple[int, int]] | None = None,
    patient_weight_kg: float | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Generate the MAIN adequacy report as a DataFrame.

    Rows: every tier="label" nutrient with show_in_report="yes" (the nine
    nutrients the author chose to display daily — see
    data/packs/<pack>/nutrients.csv; sat fat/trans fat/cholesterol/sugars
    are tier="label" too but show_in_report="no", so they're computed and
    exported but not shown here), plus two derived fluid rows:
    "Fluids provided" (primary — see fluid_provided_mL below) and "Free
    water (estimated)" (secondary, informational only — no target
    comparison). tier="clinical" nutrients are NOT here — see
    generate_clinical_screen(). tier="engine" nutrients (water_g) never
    get a row anywhere. Rows with zero coverage (no ingredient supplied a
    value) are dropped — see the second return value.

    Columns: Nutrient, Daily Total, Unit, Target, % Target, Status, Source,
    Coverage

    Args:
        daily_totals:      nutrient_name -> daily total amount (already
                            "daily" -- this is the Intake Record
                            aggregation's output, src.intake.aggregate_
                            intake().nutrient_totals, not a per-recipe
                            total needing further scaling). "water_g" here
                            is the estimated free-water total -- CNF food
                            moisture blended with any formula-declared
                            free_water_per_mL (see src/intake.py's module
                            docstring for why that blending is deliberate).
        targets:           nutrient_name → target_value. Defaults to {}
                            (renders "No target" for everything). target_type
                            (RDA/AI/UL/estimate) is read straight off the
                            registry now (NutrientDef.target_type) — no
                            separate targets.csv exists (there are no
                            default targets anywhere in this app).
        pack:               Which data pack's nutrient registry to report
                            against. Defaults to DEFAULT_PACK ("canada").
        fluid_provided_mL: The Intake Record's full-volume I&O-convention
                            fluid total (src.intake.aggregate_intake()
                            .fluid_provided_mL). Defaults to None, in
                            which case the row falls back to daily_totals'
                            water_g figure (keeps this function usable
                            standalone, e.g. from verify_backend.py).
        nutrient_coverage: nutrient_name -> (n_supplying, n_total), from
                            the same aggregation. Defaults to {} (nothing
                            hidden).

    Returns:
        (DataFrame of visible rows, list of nutrient names hidden for
        zero coverage — e.g. a custom-food-only day missing sat-fat
        data). Empty list when nothing was hidden.
    """
    if targets is None:
        targets = {}
    coverage = nutrient_coverage or {}

    label_defs = _ordered_label_defs(pack)
    rows = _tier_rows(label_defs, daily_totals, targets, coverage, patient_weight_kg)

    # Free water: a first-class computed output, not a single CNF nutrient
    # lookup -- see daily_totals' docstring note above for what it blends.
    # Demoted to secondary/informational (not compared against the fluid
    # target -- that's "Fluids provided"'s job below): it carries its own
    # completeness/coverage flag and no Target/% Target/Status of its own,
    # so it never renders a misleading adequacy verdict for a number that
    # structurally under-counts custom/label foods (no label carries
    # moisture) and formula rows without a free_water_per_mL value.
    # 0 dp, NOT water_g's registry decimals (1). The registry describes it
    # as a nutrient in grams, where 1 dp is right; this row displays it as
    # mL, and it was the only millilitre figure in the app carrying a
    # decimal (author, 2026-08-10). Nobody quotes free water as 1340.4 mL.
    free_water_mL = daily_totals.get("water_g", 0.0)
    _free_water_row: dict = {
        "Nutrient": "Free water from foods and feeds",
        "Daily Total": _fmt(free_water_mL, 0),
        "Unit": "mL",
    }
    if patient_weight_kg:
        # Deliberately "—": the per-kg fluid figure an RD quotes is the
        # I&O "Fluids provided" total below, not this estimate, which
        # structurally under-counts label-entered foods.
        _free_water_row["Per kg"] = "—"
    _water_rows = []
    _water_rows.append(
        {
            **_free_water_row,
            "Target": "—",
            "% Target": "—",
            "Status": "Informational — see Fluids provided",
            # Short enough to READ in the cell. This used to carry all three
            # sentences of the explanation, which no column width can fit --
            # a grid cell cannot wrap, so it truncated at ~40 characters and
            # the provenance was invisible precisely where it mattered. The
            # full wording now sits in a caption under the table, where prose
            # wraps (author, 2026-08-14). Nothing was dropped, only moved.
            "Source": "CNF food moisture + formula free water",
            "Coverage": _coverage_text("water_g", coverage),
            "_zero_coverage": _zero_coverage("water_g", coverage),
        }
    )

    # Fluids provided: the PRIMARY fluid-adequacy row -- the Intake
    # Record's full-volume I&O-convention total across every row (blend
    # rows via their own fluid fraction, formula/flush rows at full
    # volume, oral rows via their own counts_as_fluid toggle -- see
    # src.intake.aggregate_intake()). Falls back to the free-water figure
    # when not supplied, so this function stays usable without a full
    # Intake Record (e.g. scripts/verify_backend.py).
    fluid_val = fluid_provided_mL if fluid_provided_mL is not None else free_water_mL
    fluid_target = targets.get("fluid_mL", 0.0)
    fluid_pct = (fluid_val / fluid_target * 100) if fluid_target > 0 else 0.0
    _fluid_row: dict = {
        "Nutrient": "Fluids provided",
        "Daily Total": _fmt(fluid_val, 0),
        "Unit": "mL",
    }
    if patient_weight_kg:
        _fluid_row["Per kg"] = round(fluid_val / patient_weight_kg, PER_KG_FLUID_DECIMALS)
    _water_rows.append(
        {
            **_fluid_row,
            "Target": _fmt(fluid_target, 0) if fluid_target > 0 else "—",
            "% Target": _fmt(fluid_pct, 0) if fluid_target > 0 else "—",
            "Status": _adequacy_status(fluid_val, fluid_target, "estimate"),
            "Source": "Full volume of counts-as-fluid ingredients (I&O convention) + flushes",
            "Coverage": "—",
            "_zero_coverage": False,
        }
    )

    # The two water rows sit with the macros, straight after Fat, so every
    # table in the app reads energy / protein / carbohydrate / fat / water
    # (author, 2026-08-08). They used to be appended at the end because
    # they are derived rather than registry nutrients, which is an
    # implementation fact the reader should not have to know. If Fat is
    # ever hidden, they fall to the bottom rather than guessing a slot.
    _fat_def = registry_by_name(pack).get("fat_g")
    _fat_label = _fat_def.label if _fat_def else None
    _after_fat = next((i + 1 for i, r in enumerate(rows) if r["Nutrient"] == _fat_label), len(rows))
    rows[_after_fat:_after_fat] = _water_rows

    return _finalize(rows)


def format_ingredient_breakdown(
    breakdown_df: pd.DataFrame,
    pack: str = DEFAULT_PACK,
    units_by_food_code: dict[int, str] | None = None,
) -> pd.DataFrame:
    """Format src.calculator.compute_ingredient_breakdown()'s per-
    ingredient DataFrame for display — the Nutrition view's table
    (Change 1.4, plan you-know-the-line-vectorized-milner.md).

    Same "registry owns the label and decimals" idiom as
    generate_adequacy_report(): each nutrient column keeps ITS OWN
    display precision (via _fmt(), as text) rather than one width for
    the whole numeric column, so Energy's 0 dp is never dragged to
    "2204.0" by Protein's 1 dp sharing a column.

    Columns: Ingredient, Amount, then one column per tier="label"
    nutrient with show_in_report="yes" — the SAME nine nutrients and
    reading order the Adequacy table leads with (_ordered_label_defs()),
    so a nutrient's figure here and its figure there are never at two
    different precisions or in two different orders. tier="clinical"/
    "engine" nutrients are not columns here, same scope as the Adequacy
    table's main columns.

    A "Total" row is appended, column-summed from the UNFORMATTED
    breakdown_df (not by re-parsing the formatted text) — this is the
    row that should equal calculate_profile()'s / compute_nutrient_
    totals()'s whole-blend numbers; see
    tests/test_calculator.py::TestComputeIngredientBreakdown for the
    reconciliation this depends on holding upstream.

    Args:
        breakdown_df:       compute_ingredient_breakdown()'s return value
                             (food_code, food_description, grams, plus one
                             column per tracked nutrient).
        pack:                Which data pack's nutrient registry to
                             format against.
        units_by_food_code: food_code -> "g"/"mL", for the Amount column.
                             compute_ingredient_breakdown() works in grams
                             only (src/models.py's Ingredient carries no
                             unit) — the app's session-state ingredient
                             dicts are what know a row was entered in mL,
                             so the caller passes that mapping in rather
                             than this module reaching into app state.
                             A food_code missing from this dict (or no
                             dict at all) defaults to "g", matching how
                             an ingredient with no recorded unit is
                             treated everywhere else in the app.

    Returns:
        DataFrame, one row per ingredient in breakdown_df's order, plus a
        trailing Total row. Empty DataFrame (no rows) for an empty
        breakdown_df.
    """
    units_by_food_code = units_by_food_code or {}
    defs = _ordered_label_defs(pack)
    nutrient_cols = [f"{d.label} ({d.unit})" for d in defs]

    if len(breakdown_df) == 0:
        return pd.DataFrame(columns=["Ingredient", "Amount", *nutrient_cols])

    rows = []
    for _, r in breakdown_df.iterrows():
        unit = units_by_food_code.get(int(r["food_code"]), "g")
        row: dict = {
            "Ingredient": r["food_description"],
            "Amount": f"{r['grams']:.0f} {unit}",
        }
        for d in defs:
            row[f"{d.label} ({d.unit})"] = _fmt(float(r.get(d.name, 0.0)), d.decimals)
        rows.append(row)

    # Total row's Amount: grams and mL summed separately, never added
    # together as one number -- a gram and a millilitre are not the same
    # quantity for a blend carrying oil and solids.
    #
    # This total stays even though the Ingredients section's standalone
    # "Total ingredient weight" caption was removed (author, 2026-08-15).
    # Different thing: here it is one column sum in a table where every
    # other column is also a sum, so it reads as arithmetic rather than as
    # an unexplained figure sitting next to the measured volume.
    _total_g = sum(
        r["grams"]
        for _, r in breakdown_df.iterrows()
        if units_by_food_code.get(int(r["food_code"]), "g") == "g"
    )
    _total_mL = sum(
        r["grams"]
        for _, r in breakdown_df.iterrows()
        if units_by_food_code.get(int(r["food_code"]), "g") == "mL"
    )
    amount_total = f"{_total_g:.0f} g" + (f" + {_total_mL:.0f} mL" if _total_mL > 0 else "")

    total_row: dict = {"Ingredient": "Total", "Amount": amount_total}
    for d in defs:
        total_row[f"{d.label} ({d.unit})"] = _fmt(float(breakdown_df[d.name].sum()), d.decimals)
    rows.append(total_row)

    return pd.DataFrame(rows)


def generate_clinical_screen(
    daily_totals: dict[str, float],
    targets: dict[str, float] | None = None,
    pack: str = DEFAULT_PACK,
    nutrient_coverage: dict[str, tuple[int, int]] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Generate the BTF micro screen — tier="clinical" nutrients only.

    This is a ONE-TIME ASPEN-style supplementation screen ("does this
    blend need a multivitamin?"), not a daily-tracked panel like the
    main adequacy report. These nutrients (magnesium, phosphorus, zinc,
    vitamin D, vitamin B12 for the Canada pack) are tracked for clinical
    reasons — the author's EN spreadsheet, or ASPEN BTF guidance — not
    because they're on a Canadian Nutrition Facts table. A custom food
    entered from a label can NEVER supply these (see the Source column
    and each NutrientDef.on_label); a "Below target" here may partly
    reflect that structural gap rather than the recipe itself, and CNF
    coverage for some of these is well under 100% (vitamin D ~88%, so a
    low number may reflect missing CNF data, not missing nutrition — see
    scripts/trace_calculation.py's missing-data audit).

    Args:
        daily_totals:      nutrient_name -> daily total (see
                            generate_adequacy_report()'s docstring — same
                            Intake Record aggregation output).
        targets:            nutrient_name -> target_value.
        pack:               Data pack to report against.
        nutrient_coverage: nutrient_name -> (n_supplying, n_total), from
                            the same aggregation.

    Same columns as generate_adequacy_report(): Nutrient, Daily Total,
    Unit, Target, % Target, Status, Source, Coverage. None of these
    nutrients is offer_target="yes" (see src/nutrients.py — magnesium and
    phosphorus deliberately so; see src/targets.py's module docstring)
    so they always render "No target" here — that's correct, not a bug.
    Rows with zero coverage are dropped — see the second return value.
    """
    if targets is None:
        targets = {}
    coverage = nutrient_coverage or {}

    clinical_defs = [d for d in defs_for_tier("clinical", pack=pack) if d.show_in_report]
    rows = _tier_rows(clinical_defs, daily_totals, targets, coverage)
    return _finalize(rows)


def generate_formula_comparison(
    profile: NutrientProfile,
    formula_name: str,
    daily_volume_mL: float,
) -> pd.DataFrame:
    """Generate the BTF vs commercial formula comparison as a DataFrame."""
    comparison = compare_with_formula(profile, formula_name, daily_volume_mL)

    btf_kcal = comparison["btf"]["kcal"]
    formula_kcal = comparison["formula"]["kcal"]
    btf_protein = comparison["btf"]["protein_g"]
    formula_protein = comparison["formula"]["protein_g"]

    return pd.DataFrame(
        [
            {
                "Metric": "Energy (kcal)",
                "BTF": round(btf_kcal, 0),
                "Formula": round(formula_kcal, 0),
                "Difference": round(btf_kcal - formula_kcal, 0),
            },
            {
                "Metric": "Protein (g)",
                "BTF": round(btf_protein, 1),
                "Formula": round(formula_protein, 1),
                "Difference": round(btf_protein - formula_protein, 1),
            },
            {
                "Metric": "kcal/mL",
                "BTF": round(profile.kcal_per_mL, 2),
                "Formula": COMMERCIAL_FORMULAS[formula_name]["kcal_per_mL"],
                "Difference": round(
                    profile.kcal_per_mL - COMMERCIAL_FORMULAS[formula_name]["kcal_per_mL"],
                    3,
                ),
            },
            {
                "Metric": "protein g/mL",
                "BTF": round(profile.protein_per_mL, 3),
                "Formula": COMMERCIAL_FORMULAS[formula_name]["protein_per_mL"],
                "Difference": round(
                    profile.protein_per_mL - COMMERCIAL_FORMULAS[formula_name]["protein_per_mL"],
                    3,
                ),
            },
        ]
    )


def generate_density_summary(profile: NutrientProfile) -> pd.DataFrame:
    """Generate the density panel as a DataFrame."""
    return pd.DataFrame(
        [
            {
                "Metric": "Energy density",
                "Value": f"{profile.kcal_per_mL:.2f} kcal/mL",
                "Note": "Primary lens — patient tolerates limited mL/day",
            },
            {
                "Metric": "Protein density",
                "Value": f"{profile.protein_per_mL:.3f} g/mL",
                "Note": "Protein per mL of blend",
            },
            {
                "Metric": "Free-water fraction",
                "Value": f"{profile.free_water_fraction:.3f}",
                "Note": "(food water + added water) / volume",
            },
            {
                "Metric": "Total energy (per recipe)",
                "Value": f"{profile.total_kcal:.0f} kcal",
                "Note": "In the full batch",
            },
            {
                "Metric": "Total protein (per recipe)",
                "Value": f"{profile.total_protein_g:.1f} g",
                "Note": "In the full batch",
            },
            {
                "Metric": "Measured volume",
                "Value": f"{profile.measured_final_volume_mL:.0f} mL",
                "Note": "User-measured, not computed",
            },
        ]
    )


def generate_comparator_table(
    profile: NutrientProfile,
    daily_volume_mL: float,
    formula_names: list[str],
) -> pd.DataFrame:
    """Generate the multi-formula comparator table (round-2 clinical
    feedback, Part 0 #11): TRANSPOSED from the old generate_formula_
    comparison() shape — metrics as COLUMNS, one row per recipe/formula,
    BTF always first. Supports comparing against up to several formulas
    at once (the app enforces "up to 4" via st.multiselect's
    max_selections; this function itself doesn't cap the list).

    Columns: Name, Energy (kcal), Protein (g), Free water (mL), kcal/mL,
    Protein g/mL. Free water uses each formula's free_water_per_mL
    (data/packs/canada/formulas.csv, Part 2.6) — "—" when a formula's
    CSV row omits it (never a fabricated 0).

    Args:
        profile:         The BTF recipe's NutrientProfile.
        daily_volume_mL: Daily volume to compare all rows at (the BTF and
                          every formula are shown at the SAME volume, so
                          the comparison isolates density, not dose).
        formula_names:   Which COMMERCIAL_FORMULAS keys to include as
                          additional rows, in the order given.
    """
    rows = [
        {
            "Name": "BTF (this recipe)",
            "Energy (kcal)": round(profile.kcal_per_mL * daily_volume_mL, 0),
            "Protein (g)": round(profile.protein_per_mL * daily_volume_mL, 1),
            "Free water (mL)": round(profile.free_water_fraction * daily_volume_mL, 0),
            "kcal/mL": round(profile.kcal_per_mL, 2),
            "Protein g/mL": round(profile.protein_per_mL, 3),
        }
    ]
    for name in formula_names:
        formula = COMMERCIAL_FORMULAS[name]
        fw_per_mL = formula.get("free_water_per_mL")
        rows.append(
            {
                "Name": name,
                "Energy (kcal)": round(formula["kcal_per_mL"] * daily_volume_mL, 0),
                "Protein (g)": round(formula["protein_per_mL"] * daily_volume_mL, 1),
                "Free water (mL)": (
                    round(fw_per_mL * daily_volume_mL, 0) if fw_per_mL is not None else "—"
                ),
                "kcal/mL": formula["kcal_per_mL"],
                "Protein g/mL": formula["protein_per_mL"],
            }
        )
    return pd.DataFrame(rows)


def generate_source_breakdown(
    intake_totals,
    pack: str = DEFAULT_PACK,
) -> pd.DataFrame:
    """Per-source subtotal breakdown (FEED_LOG_REWORK.md section 3.5):
    rows = {Tube Feed, Food & Drink, Total}, columns = the displayed
    macro/fluid nutrients. Directly answers the author's "I want combined
    numbers, but I still want to see the split" request.

    Supersedes the old combined BTF + commercial-formula "regimen
    summary" (generate_regimen_summary, removed by this rework) — a
    formula is now just an Intake Record row like any other, so there is
    nothing left to separately "combine"; the Intake Record aggregation
    (src.intake.aggregate_intake()) already produces exactly this
    Tube-Feed/Food-&-Drink/Total split as a byproduct of one pass over
    the rows (FEED_LOG_REWORK.md section 2: "What this dissolves").

    Args:
        intake_totals: an src.intake.IntakeTotals (or any object exposing
                        the same `.subtotals` dict shape — duck-typed here
                        to avoid a hard import-cycle dependency on
                        src/intake.py, matching this module's existing
                        style of taking plain dicts/DataFrames).
        pack:           Which data pack's nutrient registry to report
                        against (for column labels/decimals/order).
    """
    label_defs = _ordered_label_defs(pack)
    rows = []
    for source_label in (_TUBE_FEED_LABEL, _FOOD_DRINK_LABEL, _TOTAL_LABEL):
        sub = intake_totals.subtotals.get(
            source_label, {"nutrient_totals": {}, "fluid_provided_mL": 0.0}
        )
        row: dict = {"Source": source_label}
        for d in label_defs:
            row[f"{d.label} ({d.unit})"] = _fmt(sub["nutrient_totals"].get(d.name, 0.0), d.decimals)
            # Fluids sits straight after Fat, same as the adequacy table
            # and the targets form, so the reading order is the same
            # wherever you look.
            if d.name == "fat_g":
                row["Fluids provided (mL)"] = _fmt(sub["fluid_provided_mL"], 0)
        if "Fluids provided (mL)" not in row:
            row["Fluids provided (mL)"] = _fmt(sub["fluid_provided_mL"], 0)
        rows.append(row)
    return pd.DataFrame(rows)


def generate_water_ledger(water_sources: dict[str, float]) -> pd.DataFrame:
    """Every water source the day drew on, one row each, plus a total.

    The clinical distinction this preserves (author, 2026-07-30): water
    that arrived as PART OF SOMETHING FED is free water -- tap water
    stirred into a blend included, because in the recipe it IS the
    recipe, exactly like the moisture in a banana. Only a flush is water
    given as water, so it gets its own line and is added on top.

    Deliberately NO intermediate "free water subtotal" row: the author
    wants the sources themselves visible, then the total. Nothing here is
    recomputed -- these are aggregate_intake()'s own per-source numbers.

    Returns an empty DataFrame when the day has no water at all, so the
    caller can show nothing rather than a table of zeroes.
    """
    if not water_sources:
        return pd.DataFrame(columns=["Water source", "mL/day"])

    rows = [
        {"Water source": label, "mL/day": round(value, 0)}
        for label, value in sorted(water_sources.items())
    ]
    rows.append({"Water source": "Total water", "mL/day": round(sum(water_sources.values()), 0)})
    return pd.DataFrame(rows)
