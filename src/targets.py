"""
targets.py — Load DRI / tube-feed target tables for adequacy reporting.

Phase 5 of the BTF Calculator.

The RD brings their own targets (from prior assessment — the tool does
NOT do assessment equations, per CONTEXT.md §1). This module loads
default DRI targets from CSV files in data/packs/<pack>/, and also
allows the RD to enter custom targets at runtime.

Targets are stored as a simple dict: nutrient_name → target_value.
The report module compares daily totals against these targets, along
with each target's `target_type` (RDA | AI | UL | estimate) — see
load_target_types() and BUSINESS_CASE.md Appendix C.

Deliberately NOT invented: Magnesium and phosphorus have no target rows
here (the author's clinical reasoning: refeeding-risk monitoring happens
in hospital on known formulas, not via a BTF default target — see
CONTEXT.md §9). Nutrients with no meaningful daily target (fat, sat fat,
trans, cholesterol, carbohydrate, sugars) also have no rows. Do not add
targets for these — the report renders "No target" for them, correctly.
"""

from pathlib import Path
import pandas as pd

try:
    from src.nutrients import load_registry
except ImportError:
    from nutrients import load_registry

# Default location of pack CSVs (targets.csv lives alongside nutrients.csv,
# formulas.csv, thinning_liquids.csv — one directory per country pack).
PACKS_DIR = Path(__file__).resolve().parent.parent / "data" / "packs"
DEFAULT_PACK = "canada"


def _targets_csv(pack: str = DEFAULT_PACK) -> Path:
    return PACKS_DIR / pack / "targets.csv"


def load_targets(
    csv_path: Path | str | None = None, pack: str = DEFAULT_PACK
) -> dict[str, float]:
    """Load nutrient targets from a CSV file.

    Expected CSV format:
        nutrient,target,unit,target_type,source
        energy_kcal,2000,kcal,estimate,DRI general adult
        protein_g,75,g,estimate,DRI 1.0 g/kg reference
        ...

    Args:
        csv_path: Explicit path to a targets CSV, overriding `pack`.
        pack:     Which data pack's targets.csv to load. Ignored if
                  csv_path is given. Defaults to DEFAULT_PACK ("canada").

    Returns:
        Dict mapping nutrient_name → target_value (float).
    """
    if csv_path is None:
        csv_path = _targets_csv(pack)

    df = pd.read_csv(csv_path)
    return dict(zip(df["nutrient"], df["target"].astype(float)))


def load_target_types(
    csv_path: Path | str | None = None, pack: str = DEFAULT_PACK
) -> dict[str, str]:
    """Load each target's type (RDA | AI | UL | estimate) from the same CSV.

    report.py needs this to render UL-appropriate adequacy language
    ("Above UL" / "Below UL" instead of "Above target" / "Meeting
    target") — a UL is a ceiling, not something to aim for, so the
    normal 90-110% "meeting target" language is misleading for it.

    Args:
        csv_path: Explicit path to a targets CSV, overriding `pack`.
        pack:     Which data pack's targets.csv to load. Ignored if
                  csv_path is given. Defaults to DEFAULT_PACK ("canada").

    Returns:
        Dict mapping nutrient_name → target_type string.
    """
    if csv_path is None:
        csv_path = _targets_csv(pack)

    df = pd.read_csv(csv_path)
    return dict(zip(df["nutrient"], df["target_type"].astype(str)))


def default_targets() -> dict[str, float]:
    """Return the default adult DRI targets.

    These are general-reference values. The RD should override with
    patient-specific targets from their assessment.
    """
    return load_targets()


def empty_targets(pack: str = DEFAULT_PACK) -> dict[str, float]:
    """Return a targets dict with all nutrients set to 0 (no targets).

    Used when the RD chooses not to enter targets — the report will
    show daily totals without adequacy status.

    Keys are derived from the nutrient registry (every tier except
    "engine" — water_g is never targeted, it only feeds the free-water
    calculation), plus "fluid_mL", which isn't a CNF nutrient — it's the
    target for the derived Free water row. Not every key here has a row
    in targets.csv (e.g. magnesium_mg deliberately doesn't — see this
    module's docstring); those simply stay at 0.0 ("No target") unless
    the RD enters a value.
    """
    targets = {d.name: 0.0 for d in load_registry(pack) if d.tier != "engine"}
    targets["fluid_mL"] = 0.0
    return targets


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