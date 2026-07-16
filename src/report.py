"""
report.py — Adequacy report: daily totals vs targets + formula comparison.

Phase 5 of the BTF Calculator.

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

Two report tables, split by nutrient tier (src/nutrients.py):
  - generate_adequacy_report()  → tier="label" nutrients (this country's
    mandatory Nutrition Facts panel) + the derived Free water row. This
    is the MAIN table.
  - generate_clinical_screen()  → tier="clinical" nutrients (a one-time
    ASPEN-style "does this blend need a multivitamin?" screen — not a
    daily-tracked panel). A SEPARATE, collapsed table.
tier="engine" nutrients (water_g) never get a row in either table — they
exist only to feed internal calculations (free_water_fraction).

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
    from src.targets import load_target_types
except ImportError:
    from calculator import (
        calculate_daily_totals,
        compare_with_formula,
        COMMERCIAL_FORMULAS,
    )
    from models import NutrientProfile
    from nutrients import NutrientDef, defs_for_tier, registry_by_name, DEFAULT_PACK
    from targets import load_target_types


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


def _tier_rows(
    defs: list[NutrientDef],
    daily_totals: dict[str, float],
    targets: dict[str, float],
    target_types: dict[str, str],
) -> list[dict]:
    """Build report rows for a list of NutrientDef (one tier's worth)."""
    rows = []
    for d in defs:
        daily_val = daily_totals.get(d.name, 0.0)
        target_val = targets.get(d.name, 0.0)
        ttype = target_types.get(d.name, "estimate")
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
            }
        )
    return rows


def generate_adequacy_report(
    profile: NutrientProfile,
    daily_volume_mL: float,
    targets: dict[str, float] | None = None,
    target_types: dict[str, str] | None = None,
    pack: str = DEFAULT_PACK,
) -> pd.DataFrame:
    """Generate the MAIN adequacy report as a DataFrame.

    Rows: every tier="label" nutrient (this country's mandatory Nutrition
    Facts panel — see data/packs/<pack>/nutrients.csv), plus the derived
    Free water row. tier="clinical" nutrients are NOT here — see
    generate_clinical_screen(). tier="engine" nutrients (water_g) never
    get a row anywhere.

    Columns: Nutrient, Daily Total, Unit, Target, % Target, Status, Source

    Args:
        profile:         The recipe's NutrientProfile.
        daily_volume_mL: Total daily delivery volume.
        targets:         nutrient_name → target_value. Defaults to {}
                          (renders "No target" for everything).
        target_types:    nutrient_name → "RDA"|"AI"|"UL"|"estimate", used
                          for UL-appropriate status language (sodium
                          reads "Above UL"/"Below UL", not "Above
                          target"). Defaults to the pack's targets.csv
                          (load_target_types()) — pass explicitly if the
                          RD's targets came from a different source.
        pack:             Which data pack's nutrient registry to report
                          against. Defaults to DEFAULT_PACK ("canada").
    """
    if targets is None:
        targets = {}
    if target_types is None:
        target_types = load_target_types(pack=pack)

    daily_totals = calculate_daily_totals(profile, daily_volume_mL)

    rows = _tier_rows(defs_for_tier("label", pack=pack), daily_totals, targets, target_types)

    # Free water (Appendix A6): free water is a first-class computed
    # output, not a CNF nutrient lookup — it's derived from
    # free_water_fraction (food moisture + added water) and compared
    # against the fluid_mL target separately. Labeled "Free water (mL)"
    # so it isn't confused with total daily delivery volume. Its Source
    # note explains the underlying limitation: no label carries moisture,
    # so recipes built partly from custom/label foods will UNDER-report
    # free water (see the caption in app/streamlit_app.py's custom-food form).
    water_def = registry_by_name(pack).get("water_g")
    water_decimals = water_def.decimals if water_def else 1
    free_water_mL = profile.free_water_fraction * daily_volume_mL
    fluid_target = targets.get("fluid_mL", 0.0)
    fluid_type = target_types.get("fluid_mL", "estimate")
    fluid_pct = (free_water_mL / fluid_target * 100) if fluid_target > 0 else 0.0
    rows.append(
        {
            "Nutrient": "Free water",
            "Daily Total": round(free_water_mL, water_decimals),
            "Unit": "mL",
            "Target": round(fluid_target, water_decimals) if fluid_target > 0 else "—",
            "% Target": round(fluid_pct, 0) if fluid_target > 0 else "—",
            "Status": _adequacy_status(free_water_mL, fluid_target, fluid_type),
            "Source": "Derived (food moisture + added water) — no label carries moisture",
        }
    )

    return pd.DataFrame(rows)


def generate_clinical_screen(
    profile: NutrientProfile,
    daily_volume_mL: float,
    targets: dict[str, float] | None = None,
    target_types: dict[str, str] | None = None,
    pack: str = DEFAULT_PACK,
) -> pd.DataFrame:
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
    Unit, Target, % Target, Status, Source. Magnesium and phosphorus
    intentionally have no target row in targets.csv (see src/targets.py
    docstring) and so render "No target" here — that's correct, not a bug.
    """
    if targets is None:
        targets = {}
    if target_types is None:
        target_types = load_target_types(pack=pack)

    daily_totals = calculate_daily_totals(profile, daily_volume_mL)
    rows = _tier_rows(defs_for_tier("clinical", pack=pack), daily_totals, targets, target_types)
    return pd.DataFrame(rows)


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