"""
targets.py — Target-key scaffolding for adequacy reporting.

Round-2 clinical feedback (see the handoff plan under
.claude/plans/btf-clinical-feedback-round1.md, Part 0 #2 and Part 2.3):
**there are no default targets anywhere in this app.** "2000 kcal / 75 g
protein" as a population default is not defensible for tube-fed patients
(e.g. protein practice is 1.0-1.5 g/kg, not the 0.8 g/kg population RDA),
and a guideline fluid default has the same problem. `data/packs/canada/
targets.csv` has been DELETED — the author's words: "we'll recreate it if
necessary." Targets always start blank; the RD enters patient-specific
values from their own assessment, or leaves them blank (blank = no
adequacy %, daily totals still shown).

What used to live here (load_targets(), default_targets(),
load_target_types()) is gone along with targets.csv. The one thing that
survives is empty_targets() — it still hands the app a dict of
zero-valued target keys to build the custom-targets form from, but its
keys now come from the nutrient registry's `offer_target` column
(data/packs/<pack>/nutrients.csv — see src/nutrients.py) instead of a
targets.csv row list. `target_type` (RDA/AI/UL/estimate — the UL-ness
that drives sodium's "Above UL" wording) also moved into the registry
as of this round, since it's a property of the nutrient, not of a
default value; src/report.py reads it off NutrientDef directly now.

Deliberately NOT offered as a target field: magnesium and phosphorus
(the author's clinical reasoning stands from the prior round: refeeding-
risk monitoring happens in hospital on known formulas, not via a BTF
default target) — nor any other tier="clinical" nutrient. Only the nine
core tier="label" nutrients (registry `offer_target=yes`) get a target
field, plus the special `fluid_mL` key (not a CNF nutrient — the target
for the fluids-ledger adequacy row, see src/report.py).
"""

try:
    from src.nutrients import load_registry, DEFAULT_PACK
except ImportError:
    from nutrients import load_registry, DEFAULT_PACK


def empty_targets(pack: str = DEFAULT_PACK) -> dict[str, float]:
    """Return a targets dict with all offerable nutrients set to 0 (no targets).

    This is the ONLY way targets are ever seeded in this app — there is no
    default/DRI variant anymore. The RD always starts blank and types in
    whatever patient-specific values they already have from assessment.

    Keys are derived from the nutrient registry (every `offer_target=yes`
    row — the nine core label-tier nutrients energy/protein/fat/carb/
    fibre/sodium/potassium/calcium/iron), plus "fluid_mL", which isn't a
    CNF nutrient — it's the target for the derived fluid-adequacy row
    (src/report.py). tier="clinical" nutrients (magnesium, phosphorus,
    zinc, vitamin D, B12) are NOT offer_target and so have no key here —
    the BTF micro screen always renders "No target" for them, correctly.
    """
    targets = {d.name: 0.0 for d in load_registry(pack) if d.offer_target}
    targets["fluid_mL"] = 0.0
    return targets


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    print("Loading empty (blank) targets scaffold...")
    targets = empty_targets()
    print(f"  {len(targets)} target keys available for entry\n")

    print(f"{'Nutrient':<25} {'Target':>10}")
    print("-" * 37)
    for name, val in targets.items():
        print(f"  {name:<23} {val:>10.1f}")

    print("\n✅ Targets smoke test passed (no defaults — blank scaffold only).")
