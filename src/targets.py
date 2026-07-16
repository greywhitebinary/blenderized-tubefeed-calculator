"""
targets.py — Load DRI / tube-feed target tables for adequacy reporting.

Phase 5 of the BTF Calculator.

The RD brings their own targets (from prior assessment — the tool does
NOT do assessment equations, per CONTEXT.md §1). This module loads
default DRI targets from CSV files in data/targets/, and also allows
the RD to enter custom targets at runtime.

Targets are stored as a simple dict: nutrient_name → target_value.
The report module compares daily totals against these targets.
"""

from pathlib import Path
import pandas as pd

# Default location of target CSVs
TARGETS_DIR = Path(__file__).resolve().parent.parent / "data" / "targets"


def load_targets(csv_path: Path | str | None = None) -> dict[str, float]:
    """Load nutrient targets from a CSV file.

    Expected CSV format:
        nutrient,target,unit,source
        energy_kcal,2000,kcal,DRI general adult
        protein_g,75,g,DRI 1.0 g/kg reference
        ...

    Args:
        csv_path: Path to the targets CSV. Defaults to the adult DRI file.

    Returns:
        Dict mapping nutrient_name → target_value (float).
    """
    if csv_path is None:
        csv_path = TARGETS_DIR / "dri_adult_default.csv"

    df = pd.read_csv(csv_path)
    return dict(zip(df["nutrient"], df["target"].astype(float)))


def default_targets() -> dict[str, float]:
    """Return the default adult DRI targets.

    These are general-reference values. The RD should override with
    patient-specific targets from their assessment.
    """
    return load_targets()


def empty_targets() -> dict[str, float]:
    """Return a targets dict with all nutrients set to 0 (no targets).

    Used when the RD chooses not to enter targets — the report will
    show daily totals without adequacy status.
    """
    return {
        "energy_kcal": 0.0,
        "protein_g": 0.0,
        "fibre_g": 0.0,
        "sodium_mg": 0.0,
        "potassium_mg": 0.0,
        "calcium_mg": 0.0,
        "iron_mg": 0.0,
        "zinc_mg": 0.0,
        "vitamin_d_ug": 0.0,
        "vitamin_b12_ug": 0.0,
        "fluid_mL": 0.0,
    }


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("Loading default targets...")
    targets = default_targets()
    print(f"  {len(targets)} targets loaded\n")

    print(f"{'Nutrient':<25} {'Target':>10}")
    print("-" * 37)
    for name, val in targets.items():
        print(f"  {name:<23} {val:>10.1f}")

    print("\n✅ Targets smoke test passed.")