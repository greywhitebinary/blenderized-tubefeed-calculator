"""
report.py — Adequacy report: daily totals vs targets + formula comparison.

Phase 5 of the BTF Calculator.

This module takes a NutrientProfile, a daily volume, and optional targets,
and produces a structured adequacy report. It also generates the
commercial formula comparison.

Adequacy logic (Appendix A6):
    pct_target = (daily_total / target) × 100

    status:
      < 90% of target  → "Below target"
      90%–110%         → "Meeting target"
      > 110% of target → "Above target"

The report is returned as a pandas DataFrame for easy display in the
Streamlit UI (st.dataframe, st.table) and export to Excel.
"""

import pandas as pd

try:
    from src.calculator import (
        NUTRIENT_CODES,
        NUTRIENT_LABELS,
        calculate_daily_totals,
        compare_with_formula,
        COMMERCIAL_FORMULAS,
    )
    from src.models import NutrientProfile
except ImportError:
    from calculator import (
        NUTRIENT_CODES,
        NUTRIENT_LABELS,
        calculate_daily_totals,
        compare_with_formula,
        COMMERCIAL_FORMULAS,
    )
    from models import NutrientProfile


# Adequacy status thresholds (Appendix A6)
BELOW_THRESHOLD = 0.90   # < 90% → Below
ABOVE_THRESHOLD = 1.10   # > 110% → Above


def _adequacy_status(daily_total: float, target: float) -> str:
    """Determine adequacy status for a nutrient.

    < 90% of target  → "Below target"
    90%–110%         → "Meeting target"
    > 110% of target → "Above target"

    If target is 0 (not entered), returns "No target".
    """
    if target <= 0:
        return "No target"
    pct = daily_total / target
    if pct < BELOW_THRESHOLD:
        return "Below target"
    elif pct > ABOVE_THRESHOLD:
        return "Above target"
    else:
        return "Meeting target"


def generate_adequacy_report(
    profile: NutrientProfile,
    daily_volume_mL: float,
    targets: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Generate the adequacy report as a DataFrame.

    Columns: Nutrient, Daily Total, Unit, Target, % Target, Status
    """
    if targets is None:
        targets = {}

    daily_totals = calculate_daily_totals(profile, daily_volume_mL)

    rows = []
    for name in NUTRIENT_CODES:
        daily_val = daily_totals.get(name, 0.0)
        target_val = targets.get(name, 0.0)
        pct = (daily_val / target_val * 100) if target_val > 0 else 0.0
        status = _adequacy_status(daily_val, target_val)

        label = NUTRIENT_LABELS[name]
        if "(" in label and ")" in label:
            unit = label[label.index("(") + 1 : label.index(")")]
        else:
            unit = ""
        display_name = label.split("(")[0].strip()

        rows.append(
            {
                "Nutrient": display_name,
                "Daily Total": round(daily_val, 1),
                "Unit": unit,
                "Target": round(target_val, 1) if target_val > 0 else "—",
                "% Target": round(pct, 0) if target_val > 0 else "—",
                "Status": status,
            }
        )

    # Free water (Appendix A6): free water is "first-class computed output",
    # not part of NUTRIENT_CODES (it's derived from free_water_fraction, not
    # a CNF nutrient lookup) — compared against the fluid target separately.
    # Labeled "Free water (mL)" so it isn't confused with total daily volume.
    free_water_mL = profile.free_water_fraction * daily_volume_mL
    fluid_target = targets.get("fluid_mL", 0.0)
    fluid_pct = (free_water_mL / fluid_target * 100) if fluid_target > 0 else 0.0
    rows.append(
        {
            "Nutrient": "Free water",
            "Daily Total": round(free_water_mL, 1),
            "Unit": "mL",
            "Target": round(fluid_target, 1) if fluid_target > 0 else "—",
            "% Target": round(fluid_pct, 0) if fluid_target > 0 else "—",
            "Status": _adequacy_status(free_water_mL, fluid_target),
        }
    )

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