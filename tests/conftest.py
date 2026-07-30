"""
conftest.py — shared pytest fixtures for the BTF Calculator test suite.

Read this file's docstrings even if you've never used pytest before: a
"fixture" is just a function pytest hands to any test that asks for it
by name (as a parameter). You don't call these functions yourself --
write a test with a parameter named e.g. `nutrient_amount_df` and pytest
finds this file and supplies it.

IMPORTANT — why these fixtures are hand-built instead of real CNF data:
the real Nutrient_Amount.csv is ~565,000 rows (see src/data_loader.py's
docstring) and is already covered by the integration check
`scripts/verify_backend.py`. Loading it in a unit test would make every
test slow AND would make it impossible to verify a number "by hand" --
you'd be trusting whatever CNF happens to say about chicken breast
rather than checking the arithmetic. So every "food" below is a made-up
row with clinically-plausible values, small enough to multiply out on a
calculator.

The nutrient CODES themselves are NOT made up, though. src/calculator.py
loads its tracked-nutrient set from data/packs/canada/nutrients.csv (via
src/nutrients.py) at import time and only keeps Nutrient_Amount rows
whose Nutrient_Code is in that registry -- so a fixture row using a code
the registry doesn't track would just silently vanish in the merge. The
codes used here (208 energy, 203 protein, 255 water/moisture, 307
sodium, 204 fat, 291 fibre, 205 carbohydrate, 306 potassium, 301
calcium, 303 iron) are copied from that CSV.
"""

import sys
from pathlib import Path

# Make "from src...." imports work no matter where pytest is invoked from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import pytest

from src.models import Ingredient, Recipe


# ---------------------------------------------------------------------------
# Food codes used across both test files. Real CNF Food_Codes are 5-digit
# numbers from the real ~5,993-row Food_Name.csv; these small numbers are
# obviously fixture-only and can never collide with a real Food_Code.
# ---------------------------------------------------------------------------

FOOD_CHICKEN = 1001   # Chicken breast, cooked -- a lean protein ingredient
FOOD_RICE = 1002      # Rice, white, cooked -- a carbohydrate ingredient
FOOD_OIL = 1003       # Canola oil -- a pure-fat, zero-water ingredient
FOOD_BANANA = 1004    # Banana, raw -- used as an oral/Food & Drink item
FOOD_WATER = 1005     # Plain water -- 100 g water per 100 g, 0 kcal
FOOD_ABSENT = 9999    # Deliberately has NO rows in nutrient_amount_df --
                      # simulates a CNF food_code with no nutrient data,
                      # e.g. a food whose CNF record is incomplete.

CUSTOM_PROTEIN_SHAKE = -1  # A custom food entered from a nutrition-facts
                           # label (negative food_code, per Appendix A9 --
                           # never collides with a real CNF Food_Code).


@pytest.fixture
def nutrient_amount_df() -> pd.DataFrame:
    """A small stand-in for the CNF Nutrient_Amount table.

    Shape matches the real table exactly (Food_Code, Nutrient_Code,
    Nutrient_Amount, one row per food-nutrient pair, values are per 100 g
    of the food) -- see src/data_loader.py::load_nutrient_amount()'s
    docstring. FOOD_ABSENT (9999) intentionally has no rows at all, to
    exercise "this ingredient's CNF data is missing" without needing the
    real 565k-row table.
    """
    rows = [
        # Chicken breast, cooked -- per 100 g
        (FOOD_CHICKEN, 208, 165.0),  # energy_kcal
        (FOOD_CHICKEN, 203, 31.0),   # protein_g
        (FOOD_CHICKEN, 255, 65.0),   # water_g (moisture)
        (FOOD_CHICKEN, 307, 74.0),   # sodium_mg
        (FOOD_CHICKEN, 204, 3.6),    # fat_g
        (FOOD_CHICKEN, 291, 0.0),    # fibre_g
        (FOOD_CHICKEN, 205, 0.0),    # carbohydrate_g
        # Rice, white, cooked -- per 100 g
        (FOOD_RICE, 208, 130.0),
        (FOOD_RICE, 203, 2.7),
        (FOOD_RICE, 255, 68.0),
        (FOOD_RICE, 307, 1.0),
        (FOOD_RICE, 204, 0.3),
        (FOOD_RICE, 291, 0.4),
        (FOOD_RICE, 205, 28.0),
        # Canola oil -- per 100 g (pure fat: no water, no protein)
        (FOOD_OIL, 208, 884.0),
        (FOOD_OIL, 203, 0.0),
        (FOOD_OIL, 255, 0.0),
        (FOOD_OIL, 307, 0.0),
        (FOOD_OIL, 204, 100.0),
        (FOOD_OIL, 291, 0.0),
        (FOOD_OIL, 205, 0.0),
        # Banana, raw -- per 100 g (the oral/Food & Drink test food)
        (FOOD_BANANA, 208, 89.0),
        (FOOD_BANANA, 203, 1.1),
        (FOOD_BANANA, 255, 75.0),
        (FOOD_BANANA, 307, 1.0),
        (FOOD_BANANA, 204, 0.3),
        (FOOD_BANANA, 291, 2.6),
        (FOOD_BANANA, 205, 23.0),
        (FOOD_BANANA, 306, 358.0),  # potassium_mg
        (FOOD_BANANA, 301, 5.0),    # calcium_mg
        (FOOD_BANANA, 303, 0.26),   # iron_mg
        # Plain water -- per 100 g is 100 g water, nothing else
        (FOOD_WATER, 208, 0.0),
        (FOOD_WATER, 203, 0.0),
        (FOOD_WATER, 255, 100.0),
        (FOOD_WATER, 307, 0.0),
        # FOOD_ABSENT (9999) has NO rows -- simulates a food missing from CNF.
    ]
    return pd.DataFrame(rows, columns=["Food_Code", "Nutrient_Code", "Nutrient_Amount"])


@pytest.fixture
def custom_foods() -> dict[int, dict[str, float]]:
    """A custom food entered from a nutrition-facts label (Appendix A9) --
    e.g. an RD adding a commercial protein shake that isn't in CNF.
    Values are already per-100 g (as label_to_per_100g() would produce),
    keyed by the same negative food_code convention calculate_profile()
    and compute_nutrient_totals() expect.
    """
    return {
        CUSTOM_PROTEIN_SHAKE: {
            "energy_kcal": 250.0,
            "protein_g": 10.0,
            "sodium_mg": 120.0,
        }
    }


@pytest.fixture
def morning_blend_ingredients() -> list[dict]:
    """Raw session-state ingredient dicts (the shape app/streamlit_app.py
    stores, not Ingredient dataclass instances) for one blend: chicken +
    rice + added water. The water ingredient is flagged
    counts_as_fluid=True (it "counts as fluid" toward the daily fluid
    ledger); chicken and rice are not (food, not drink) -- mirrors the
    per-ingredient toggle described in FEED_LOG_REWORK.md / CONTEXT.md
    section 9's "fluids-ledger convention" note.
    """
    return [
        {
            "id": 1,
            "food_code": FOOD_CHICKEN,
            "food_description": "Chicken breast, cooked",
            "grams": 200.0,
            "unit": "g",
            "counts_as_fluid": False,
        },
        {
            "id": 2,
            "food_code": FOOD_RICE,
            "food_description": "Rice, white, cooked",
            "grams": 150.0,
            "unit": "g",
            "counts_as_fluid": False,
        },
        {
            "id": 3,
            "food_code": FOOD_WATER,
            "food_description": "Water",
            "grams": 150.0,
            "unit": "g",
            "counts_as_fluid": True,
        },
    ]


@pytest.fixture
def blends(morning_blend_ingredients) -> dict[int, dict]:
    """One blend ("Morning blend"): chicken + rice + water, measured to
    500 mL after blending. This is the blend used to pin the "logged mL
    is never scaled up to the batch" behavior in test_intake.py -- see
    FEED_LOG_REWORK.md section 1 (the bug) and section 6.2 (the fix).

    Hand-check (per 100 g, x grams/100, summed):
      energy_kcal = 165*2 + 130*1.5 + 0*1.5   = 525.0
      protein_g   = 31*2  + 2.7*1.5 + 0       = 66.05
      water_g     = 65*2  + 68*1.5  + 100*1.5 = 382.0
    -> kcal/mL = 525/500 = 1.05, protein/mL = 66.05/500 = 0.1321,
       free_water_fraction = 382/500 = 0.764 (no added_water_mL set).
    Fluid fraction (only the water ingredient counts): 150/500 = 0.3.
    """
    return {
        1: {
            "name": "Morning blend",
            "ingredients": morning_blend_ingredients,
            "measured_volume_mL": 500.0,
        }
    }


@pytest.fixture
def formulas() -> dict[str, dict]:
    """A small hand-written stand-in for data/packs/canada/formulas.csv's
    loaded shape (src/calculator.py::_load_commercial_formulas()'s return
    value) -- a made-up 1.2 kcal/mL commercial formula, deliberately
    NOT the real catalog, so this test doesn't break if an RD edits the
    real CSV. Optional columns this fixture omits (e.g. fibre_per_mL)
    are simply absent, matching the real loader's "missing column ->
    None, never a fabricated 0" contract.
    """
    return {
        "Test Formula 1.2": {
            "kcal_per_mL": 1.2,
            "protein_per_mL": 0.05,
            "free_water_per_mL": 0.85,
            "sodium_per_mL": 0.9,
        }
    }


@pytest.fixture
def sample_recipe() -> Recipe:
    """A minimal two-ingredient recipe with a measured volume, for
    calculator tests that don't need the full three-ingredient blend.
    """
    return Recipe(
        name="Two-ingredient test recipe",
        ingredients=[
            Ingredient(FOOD_CHICKEN, "Chicken breast, cooked", 200.0),
            Ingredient(FOOD_RICE, "Rice, white, cooked", 150.0),
        ],
        measured_final_volume_mL=400.0,
    )
