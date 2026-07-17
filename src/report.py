"""
report.py — Adequacy report: daily totals vs targets + formula comparison.

Phase 5 of the BTF Calculator; reworked in the round-2 clinical feedback
pass (see .claude/plans/btf-clinical-feedback-round1.md Part 2.2-2.3).

This module takes a NutrientProfile, a daily volume, and optional targets,
and produces a structured adequacy report. It also generates the
commercial formula comparison.

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
    not shown here) + the derived Fluid provided / Free water rows. This
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
    from src.calculator import (
        calculate_daily_totals,
        compare_with_formula,
        COMMERCIAL_FORMULAS,
    )
    from src.models import NutrientProfile
    from src.nutrients import NutrientDef, defs_for_tier, registry_by_name, DEFAULT_PACK
except ImportError:
    from calculator import (
        calculate_daily_totals,
        compare_with_formula,
        COMMERCIAL_FORMULAS,
    )
    from models import NutrientProfile
    from nutrients import NutrientDef, defs_for_tier, registry_by_name, DEFAULT_PACK


# Adequacy status thresholds (Appendix A6)
BELOW_THRESHOLD = 0.90   # < 90% → Below
ABOVE_THRESHOLD = 1.10   # > 110% → Above

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
        return f"{n_supplying}/{n_total} ingredients"
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


def _tier_rows(
    defs: list[NutrientDef],
    daily_totals: dict[str, float],
    targets: dict[str, float],
    coverage: dict[str, tuple[int, int]],
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

        rows.append(
            {
                "Nutrient": d.label,
                "Daily Total": round(daily_val, d.decimals),
                "Unit": d.unit,
                "Target": round(target_val, d.decimals) if target_val > 0 else "—",
                "% Target": round(pct, 0) if target_val > 0 else "—",
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
    profile: NutrientProfile,
    daily_volume_mL: float,
    targets: dict[str, float] | None = None,
    pack: str = DEFAULT_PACK,
    fluid_provided_mL: float | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Generate the MAIN adequacy report as a DataFrame.

    Rows: every tier="label" nutrient with show_in_report="yes" (the nine
    nutrients the author chose to display daily — see
    data/packs/<pack>/nutrients.csv; sat fat/trans fat/cholesterol/sugars
    are tier="label" too but show_in_report="no", so they're computed and
    exported but not shown here), plus two derived fluid rows:
    "Fluid provided" (primary — see fluid_provided_mL below) and "Free
    water (CNF-estimated)" (secondary, informational only — no target
    comparison). tier="clinical" nutrients are NOT here — see
    generate_clinical_screen(). tier="engine" nutrients (water_g) never
    get a row anywhere. Rows with zero per-recipe coverage (no ingredient
    supplied a value) are dropped — see the second return value.

    Columns: Nutrient, Daily Total, Unit, Target, % Target, Status, Source,
    Coverage

    Args:
        profile:           The recipe's NutrientProfile.
        daily_volume_mL:   Total daily delivery volume.
        targets:           nutrient_name → target_value. Defaults to {}
                            (renders "No target" for everything). target_type
                            (RDA/AI/UL/estimate) is read straight off the
                            registry now (NutrientDef.target_type) — no
                            separate targets.csv exists (Part 0 #2 of the
                            round-2 clinical feedback plan: there are no
                            default targets anywhere in this app).
        pack:               Which data pack's nutrient registry to report
                            against. Defaults to DEFAULT_PACK ("canada").
        fluid_provided_mL: The fluids-ledger "Fluid provided" figure (full
                            volume of counts-as-fluid ingredients, scaled
                            to daily intake, plus flushes) — an app-level
                            computation (session-state ingredient toggles
                            + delivery/flush schedule), passed in here
                            because report.py has no access to per-
                            ingredient fluid flags. Defaults to None, in
                            which case the row falls back to the CNF free-
                            water figure (keeps this function usable
                            standalone, e.g. from verify_backend.py,
                            without requiring the app's fluids ledger).

    Returns:
        (DataFrame of visible rows, list of nutrient names hidden for
        zero coverage — e.g. a custom-food-only recipe missing sat-fat
        data). Empty list when nothing was hidden.
    """
    if targets is None:
        targets = {}

    daily_totals = calculate_daily_totals(profile, daily_volume_mL)
    coverage = profile.nutrient_coverage

    label_defs = [d for d in defs_for_tier("label", pack=pack) if d.show_in_report]
    rows = _tier_rows(label_defs, daily_totals, targets, coverage)

    # Free water (Appendix A6): a first-class computed output, not a CNF
    # nutrient lookup — derived from free_water_fraction (food moisture +
    # added water). Demoted to secondary/informational per the round-2
    # fluids-ledger rework (Part 0 #8, Part 2.4): it is NOT compared
    # against the fluid target (that's "Fluid provided"'s job below) — it
    # carries its own completeness/coverage flag and no Target/% Target/
    # Status of its own, so it never renders a misleading adequacy verdict
    # for a number that structurally under-counts custom/label foods (no
    # label carries moisture).
    water_def = registry_by_name(pack).get("water_g")
    water_decimals = water_def.decimals if water_def else 1
    free_water_mL = profile.free_water_fraction * daily_volume_mL
    rows.append(
        {
            "Nutrient": "Free water (CNF-estimated)",
            "Daily Total": round(free_water_mL, water_decimals),
            "Unit": "mL",
            "Target": "—",
            "% Target": "—",
            "Status": "Informational — see Fluid provided",
            "Source": "Derived (food moisture) — no label carries moisture; secondary to Fluid provided",
            "Coverage": _coverage_text("water_g", coverage),
            "_zero_coverage": _zero_coverage("water_g", coverage),
        }
    )

    # Fluid provided (Part 2.4): the PRIMARY fluid-adequacy row. Full
    # volume of counts-as-fluid ingredients (I&O convention) scaled to
    # daily intake, plus water flushes — computed at the app level (it
    # needs per-ingredient counts_as_fluid toggles this module has no
    # access to) and passed in. Falls back to the free-water figure when
    # not supplied, so this function stays usable without the app's
    # fluids ledger (e.g. scripts/verify_backend.py).
    fluid_val = fluid_provided_mL if fluid_provided_mL is not None else free_water_mL
    fluid_target = targets.get("fluid_mL", 0.0)
    fluid_pct = (fluid_val / fluid_target * 100) if fluid_target > 0 else 0.0
    rows.append(
        {
            "Nutrient": "Fluid provided",
            "Daily Total": round(fluid_val, 0),
            "Unit": "mL",
            "Target": round(fluid_target, 0) if fluid_target > 0 else "—",
            "% Target": round(fluid_pct, 0) if fluid_target > 0 else "—",
            "Status": _adequacy_status(fluid_val, fluid_target, "estimate"),
            "Source": "Full volume of counts-as-fluid ingredients (I&O convention) + flushes",
            "Coverage": "—",
            "_zero_coverage": False,
        }
    )

    return _finalize(rows)


def generate_clinical_screen(
    profile: NutrientProfile,
    daily_volume_mL: float,
    targets: dict[str, float] | None = None,
    pack: str = DEFAULT_PACK,
) -> tuple[pd.DataFrame, list[str]]:
    """Generate the BTF micro screen — tier="clinical" nutrients only.

    This is a ONE-TIME ASPEN-style supplementation screen ("does this
    blend need a multivitamin?"), not a daily-tracked panel like the
    main adequacy report. These nutrients (magnesium, phosphorus, zinc,
    vitamin D, vitamin B12 for the Canada pack) are tracked for clinical
    reasons — the author's EN spreadsheet, or ASPEN BTF guidance — not
    because they're on a Canadian Nutrition Facts panel. A custom food
    entered from a label can NEVER supply these (see the Source column
    and each NutrientDef.on_label); a "Below target" here may partly
    reflect that structural gap rather than the recipe itself, and CNF
    coverage for some of these is well under 100% (vitamin D ~88%, so a
    low number may reflect missing CNF data, not missing nutrition — see
    scripts/trace_calculation.py's missing-data audit).

    Same columns as generate_adequacy_report(): Nutrient, Daily Total,
    Unit, Target, % Target, Status, Source, Coverage. None of these
    nutrients is offer_target="yes" (see src/nutrients.py — magnesium and
    phosphorus deliberately so; see src/targets.py's module docstring)
    so they always render "No target" here — that's correct, not a bug.
    Rows with zero per-recipe coverage are dropped — see the second
    return value.
    """
    if targets is None:
        targets = {}

    daily_totals = calculate_daily_totals(profile, daily_volume_mL)
    coverage = profile.nutrient_coverage
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
                "BTF": round(profile.kcal_per_mL, 3),
                "Formula": COMMERCIAL_FORMULAS[formula_name]["kcal_per_mL"],
                "Difference": round(
                    profile.kcal_per_mL
                    - COMMERCIAL_FORMULAS[formula_name]["kcal_per_mL"],
                    3,
                ),
            },
            {
                "Metric": "protein g/mL",
                "BTF": round(profile.protein_per_mL, 3),
                "Formula": COMMERCIAL_FORMULAS[formula_name]["protein_per_mL"],
                "Difference": round(
                    profile.protein_per_mL
                    - COMMERCIAL_FORMULAS[formula_name]["protein_per_mL"],
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
                "Value": f"{profile.kcal_per_mL:.3f} kcal/mL",
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