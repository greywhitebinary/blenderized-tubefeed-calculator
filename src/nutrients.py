"""
nutrients.py — Per-country nutrient registry.

Part of the nutrient-registry / data-pack refactor (see BUSINESS_CASE.md
Appendix C and CONTEXT.md §9/§10 for the design rationale).

The insight: a country's mandatory Nutrition Facts panel IS that
country's encoded public-health nutrient consensus (this is the
regulators' own stated reasoning — Health Canada removed vitamins A/C
in 2022 because "most Canadians get enough" and added potassium because
intakes are low; the FDA added vitamin D and potassium as "nutrients of
public health concern"). So "track what's on the label" and "use
public-health measures to choose nutrients" are the same rule — and
that rule is per-country by construction. A hardcoded nutrient list
cannot express that; this module reads it from data instead.

Each country ships a "pack" directory under data/packs/<pack>/ with a
nutrients.csv registry (this module), targets.csv (src/targets.py),
formulas.csv and thinning_liquids.csv (src/calculator.py and
app/streamlit_app.py). Adding a country is a data task — new CSVs under
data/packs/<pack>/ — not a code task. Canada is the only pack shipped
today; US/UK/AU are documented roadmap (see CONTEXT.md §9).

nutrients.csv columns:
    name       internal nutrient key, e.g. "energy_kcal"
    code       CNF Nutrient_Code (numeric — see the NA/NaN gotcha below)
    label      human-readable name, e.g. "Energy"
    unit       display unit, e.g. "kcal"
    tier       "label" | "clinical" | "engine" — WHY we track it (see below)
    on_label   "yes" | "no" — WHETHER a nutrition facts label can supply it
    decimals   how many decimal places to display this nutrient at
    notes      free-text provenance / rationale

`tier` and `on_label` are two independent axes — do not collapse them:
  - tier="label":    on this country's mandatory panel; the public-health
                      set. Rendered in the main adequacy table.
  - tier="clinical":  tracked for a BTF/clinical reason, not a public-health
                      one (e.g. the author's EN spreadsheet tracks it, or
                      it's part of the ASPEN-style one-time micro screen).
                      Rendered in a separate, collapsed screen — never the
                      main table.
  - tier="engine":    needed internally by the calculator (water_g only —
                      it feeds free_water_fraction) and NEVER gets its own
                      report row, in either table.
  - on_label:         can a custom food entered from a nutrition facts
                      label supply this nutrient? For the Canada pack,
                      every tier="label" row is on_label=yes and every
                      tier="clinical"/"engine" row is on_label=no — but a
                      future pack need not agree (e.g. a US pack would set
                      vitamin_d_ug to tier="label", on_label="yes", since
                      vitamin D is on the US label but not the Canadian
                      one — same nutrient, different truth, same code).
"""

import functools
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PACKS_DIR = Path(__file__).resolve().parent.parent / "data" / "packs"
DEFAULT_PACK = "canada"

VALID_TIERS = ("label", "clinical", "engine")


@dataclass(frozen=True)
class NutrientDef:
    """One row of a country's nutrient registry.

    Attributes:
        name:      Internal nutrient key, e.g. "energy_kcal" (matches
                   NutrientProfile.nutrient_totals keys).
        code:      CNF Nutrient_Code (numeric — see module docstring).
        label:     Human-readable display name, e.g. "Energy".
        unit:      Display unit, e.g. "kcal".
        tier:      "label" | "clinical" | "engine" — why we track it.
        on_label:  Whether a nutrition-facts label can supply this value.
        decimals:  Display precision for daily totals.
        notes:     Free-text provenance / clinical rationale.
    """

    name: str
    code: int
    label: str
    unit: str
    tier: str
    on_label: bool
    decimals: int
    notes: str


@functools.lru_cache(maxsize=None)
def _load_registry_cached(pack: str) -> tuple[NutrientDef, ...]:
    """Cached CSV read — see load_registry() for the public entry point.

    Returns an immutable tuple (not a list) so the lru_cache-held value
    can never be mutated by a caller; load_registry() copies it into a
    fresh list on every call.
    """
    csv_path = PACKS_DIR / pack / "nutrients.csv"

    # DELIBERATE: unlike _load_commercial_formulas() / _load_thinning_liquids()
    # in src/calculator.py and app/streamlit_app.py (which fall back to a
    # small hardcoded dict if their CSV is missing), this function RAISES
    # if nutrients.csv is missing. Those other CSVs are reference data —
    # nice-to-have, safely defaulted. This registry is STRUCTURAL: it
    # defines which nutrients the entire app tracks and how. A silent
    # fallback to a hardcoded Canadian list would defeat the whole
    # data-pack design — a US pack that forgot its nutrients.csv would
    # silently show the Canadian panel instead of failing loudly. Do NOT
    # "fix" this by adding a fallback; fail loudly instead.
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Nutrient registry not found: {csv_path}\n"
            f"Every data pack MUST ship its own nutrients.csv — it defines "
            f"which nutrients this pack tracks and why (tier/on_label). "
            f"There is deliberately no hardcoded fallback for this file "
            f"(see the comment above this check in src/nutrients.py)."
        )

    # utf-8 (not utf-8-sig): this file is authored fresh by this project,
    # not sourced from CNF's raw CSVs, so it carries no BOM. The µg unit
    # requires real UTF-8 decoding to read correctly.
    df = pd.read_csv(csv_path, encoding="utf-8")

    defs = []
    for _, row in df.iterrows():
        tier = str(row["tier"]).strip()
        if tier not in VALID_TIERS:
            raise ValueError(
                f"{csv_path}: nutrient '{row['name']}' has invalid tier "
                f"'{tier}' — must be one of {VALID_TIERS}"
            )
        defs.append(
            NutrientDef(
                name=str(row["name"]).strip(),
                code=int(row["code"]),
                label=str(row["label"]).strip(),
                unit=str(row["unit"]).strip(),
                tier=tier,
                on_label=str(row["on_label"]).strip().lower() == "yes",
                decimals=int(row["decimals"]),
                notes=str(row["notes"]).strip(),
            )
        )
    return tuple(defs)


def load_registry(pack: str = DEFAULT_PACK) -> list[NutrientDef]:
    """Load the nutrient registry for a country pack.

    Reads data/packs/<pack>/nutrients.csv. Cached (functools.lru_cache)
    since the Streamlit app calls this on every rerun. Raises
    FileNotFoundError if the CSV is missing — see the comment in
    _load_registry_cached() for why this is deliberate.

    Args:
        pack: Data pack name, e.g. "canada". Defaults to DEFAULT_PACK.

    Returns:
        List of NutrientDef, in CSV row order. A fresh list each call —
        safe to mutate without corrupting the cache.
    """
    return list(_load_registry_cached(pack))


def registry_by_name(pack: str = DEFAULT_PACK) -> dict[str, NutrientDef]:
    """Registry as a dict keyed by internal nutrient name."""
    return {d.name: d for d in load_registry(pack)}


def codes_for(tier: str | None = None, pack: str = DEFAULT_PACK) -> dict[str, int]:
    """Nutrient name -> CNF Nutrient_Code, optionally filtered to one tier.

    tier=None (default) returns ALL tiers, including "engine" — this
    matches the pre-registry NUTRIENT_CODES behaviour (calculate_profile
    needs water_g's code even though it's never its own report row).
    """
    return {
        d.name: d.code
        for d in load_registry(pack)
        if tier is None or d.tier == tier
    }


def defs_for_tier(tier: str, pack: str = DEFAULT_PACK) -> list[NutrientDef]:
    """NutrientDef rows for one tier, in registry (CSV) order."""
    return [d for d in load_registry(pack) if d.tier == tier]


# ---------------------------------------------------------------------------
# Back-compat module-level values — built FROM the registry so existing
# `from src.calculator import NUTRIENT_CODES` style imports keep working
# without re-deriving anything.
# ---------------------------------------------------------------------------

# All tiers, including "engine" (water_g) — matches the original
# calculator.py NUTRIENT_CODES, which needed water_g's code internally.
NUTRIENT_CODES: dict[str, int] = codes_for(tier=None, pack=DEFAULT_PACK)

# Format: "Energy (kcal)" — matches the original calculator.py
# NUTRIENT_LABELS format that report.py used to string-parse. report.py
# has been updated to read `.unit`/`.label` directly off NutrientDef
# instead (see src/report.py), but this is kept for any other caller.
NUTRIENT_LABELS: dict[str, str] = {
    d.name: f"{d.label} ({d.unit})" for d in load_registry(DEFAULT_PACK)
}


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("Loading Canada nutrient registry...")
    registry = load_registry()
    print(f"  {len(registry)} nutrients loaded\n")

    for tier in VALID_TIERS:
        rows = [d for d in registry if d.tier == tier]
        print(f"{tier} ({len(rows)}):")
        for d in rows:
            print(f"  {d.name:<20} code={d.code:<4} on_label={d.on_label!s:<5} {d.label} ({d.unit})")
        print()

    print("✅ Nutrients registry smoke test passed.")
