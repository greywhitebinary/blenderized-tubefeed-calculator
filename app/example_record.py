"""Populate the existing example record on explicit request."""

from datetime import time as dtime
import streamlit as st
from src.measures import (
    get_measures_for_food,
)
from src.food_search import find_food
from src.targets import empty_targets
from app.ui_common import render_alert


from app.session_state import _new_blend


def load_example_record(fn, lookup):
    # Synthetic demonstration case: H&N RT week 5, syringe bolus day. Real CNF
    # foods only -- see the ingredient table in the task/CONTEXT.md S9
    # 2026-07-23 entry for the sourcing rationale behind each pick
    # (COOKED variants preferred where the case calls for them; "Carrot,
    # boiled, drained" and "...with salt" both match the search substring,
    # so this relies on find_food()'s first-match convention resolving to
    # the unsalted row -- verified against CNF, not assumed).
    milk = find_food(fn, "Milk, fluid, whole, pasteurized, homogenized, 3.25% M.F.")
    yogurt = find_food(fn, "Yogourt (yogurt), Greek style, 2% M.F., plain")
    oats = find_food(fn, "Cereal, hot, oats (oatmeal), large flakes, prepared, Rogers")
    chicken = find_food(fn, "Chicken, broiler, breast, skinless, boneless, meat, braised")
    banana = find_food(fn, "Banana, raw")
    avocado = find_food(fn, "Avocado, raw, all commercial varieties")
    carrot = find_food(fn, "Carrot, boiled, drained")
    oil = find_food(fn, "Vegetable oil, canola")
    water = find_food(fn, "Water, municipal")
    # A SECOND blend, vegan, so the example demonstrates what one blend
    # cannot (author, 2026-08-15): that a day can hold several recipes,
    # that they can be compared against each other and against a
    # commercial formula, that "Save all N recipes" has something to
    # save, and that the Intake Record draws on whichever blend was
    # actually fed -- here the first, leaving this one on the shelf.
    soy = find_food(fn, "Plant-based beverage, soy beverage, all flavours, low fat, fortified")
    tofu = find_food(fn, "Tofu, regular, firm or extra firm")
    lentils = find_food(fn, "Lentils, mature seeds, boiled")
    peanut = find_food(fn, "Peanut butter, natural")
    spinach = find_food(fn, "Spinach, boiled, drained")
    _example_foods = [milk, yogurt, oats, chicken, banana, avocado, carrot, oil, water]
    _vegan_foods = [soy, tofu, lentils, peanut, spinach]
    if all(f is not None for f in _example_foods):
        # Drop any pre-existing empty starter blend(s) so the example
        # doesn't leave clutter alongside "Whole-food blend".
        st.session_state.blends = {
            bid: b for bid, b in st.session_state.blends.items() if b["ingredients"]
        }
        example_id = _new_blend("Whole-food blend")
        st.session_state.next_ingr_id += 9
        _base_id = st.session_state.next_ingr_id - 8

        # Descriptions come from CNF itself, not hand-written friendly
        # names (author, 2026-08-15). The example is meant to look like a
        # blend the RD built by searching, and searching yields CNF's own
        # wording -- "Cereal, hot, oats (oatmeal), large flakes, prepared,
        # Rogers", not "Rolled oats, cooked". Hand-written short names made
        # the example look like it came from somewhere other than the
        # database the app actually uses, and hid how long real CNF
        # descriptions get.
        def _cnf_name(code: int, fallback: str) -> str:
            _row = fn[fn["Food_Code"] == code]
            return str(_row.iloc[0]["Food_Description_EN"]) if len(_row) else fallback

        # Each row names the CNF household measure the RD would have
        # picked when searching, and its grams are that measure's own
        # weight -- so the example is a blend somebody actually built,
        # not one typed in grams (author, 2026-08-15). Weights come from
        # the lookup at runtime rather than being hard-coded, so they
        # cannot drift from CNF.
        #
        # Chicken deliberately has NO measure: CNF offers it only as
        # "1 piece" (181 g) and "1 food guide serving = 75g", neither of
        # which is the 50 g this case wants, so grams is what an RD would
        # really type. The example is more honest for showing both kinds
        # of row.
        def _measure_grams(code: int, label: str, fallback: float) -> float:
            _m = get_measures_for_food(code, lookup)
            _hit = _m[_m["Measure_Description_and_Unit_EN"] == label]
            return float(_hit.iloc[0]["grams"]) if len(_hit) else fallback

        # (code, fallback name, measure label or None, fallback grams, counts_as_fluid)
        _example_spec = [
            (milk, "Whole milk 3.25% M.F.", "250 ml", 257.0, True),
            (yogurt, "Greek yogurt, plain, 2%", "100 ml", 100.0, False),
            (oats, "Rolled oats, cooked", "100 ml", 100.0, False),
            (chicken, "Chicken breast, cooked (skinless)", None, 50.0, False),
            (banana, "Banana, raw", "1 small (15cm to 17.5cm long)", 100.0, False),
            (avocado, "Avocado, raw", "100 ml slices", 50.0, False),
            (carrot, "Carrots, cooked (boiled, drained)", "125 ml slices", 75.0, False),
            (oil, "Canola oil", "15 ml", 14.0, False),
            (water, "Water, municipal", "250 ml", 250.0, True),
        ]
        _example_ingredients = []
        for _offset, (_code, _fallback, _label, _fallback_g, _fluid) in enumerate(_example_spec):
            _grams = _measure_grams(_code, _label, _fallback_g) if _label else _fallback_g
            _example_ingredients.append(
                {
                    "id": _base_id + _offset,
                    "food_code": _code,
                    "food_description": _cnf_name(_code, _fallback),
                    "grams": _grams,
                    "unit": "g",
                    "counts_as_fluid": _fluid,
                    "measure_label": _label,
                    "measure_grams": _grams if _label else None,
                }
            )
        st.session_state.blends[example_id]["ingredients"] = _example_ingredients
        st.session_state.blends[example_id]["measured_volume_mL"] = 1000.0

        # --- Second blend: vegan, built the same way ---------------------
        # Deliberately NOT fed in the Intake Record below. A day usually
        # holds more recipes than were used, and seeing one blend sitting
        # unfed is how that reads on screen.
        if all(f is not None for f in _vegan_foods):
            vegan_id = _new_blend("Vegan blend")
            _vegan_spec = [
                (soy, "Soy beverage, fortified", "250 ml", 257.0, True),
                (tofu, "Tofu, firm", "125 ml", 133.0, False),
                (lentils, "Lentils, boiled", "125 ml", 105.0, False),
                (peanut, "Peanut butter, natural", "30 ml", 31.5, False),
                (banana, "Banana, raw", "1 medium (18cm to 20cm long)", 118.0, False),
                (spinach, "Spinach, boiled, drained", "125 ml", 95.0, False),
                (oil, "Canola oil", "15 ml", 14.0, False),
                (water, "Water, municipal", "250 ml", 250.0, True),
            ]
            _vegan_ingredients = []
            for _code, _fallback, _label, _fallback_g, _fluid in _vegan_spec:
                st.session_state.next_ingr_id += 1
                _grams = _measure_grams(_code, _label, _fallback_g)
                _vegan_ingredients.append(
                    {
                        "id": st.session_state.next_ingr_id,
                        "food_code": _code,
                        "food_description": _cnf_name(_code, _fallback),
                        "grams": _grams,
                        "unit": "g",
                        "counts_as_fluid": _fluid,
                        "measure_label": _label,
                        "measure_grams": _grams,
                    }
                )
            st.session_state.blends[vegan_id]["ingredients"] = _vegan_ingredients
            st.session_state.blends[vegan_id]["measured_volume_mL"] = 1000.0

            # _new_blend() selects whatever it just made, which would open
            # the example on the vegan blend. Land on the one the day
            # actually fed instead -- the Intake Record below is all
            # "Whole-food blend", so opening anywhere else reads as though
            # the numbers on screen belong to the recipe in front of you
            # when they do not.
            st.session_state.selected_blend_id = example_id
            st.session_state.pop("blend_selector", None)

        # Example Intake Record -- a full bolus day (design doc section
        # 3.2): the WHOLE "Whole-food blend" batch across 4 bolus feeds
        # (4 x 250 mL = 1000 mL, the full measured_volume_mL -- no
        # over-draw/batch-mismatch bookkeeping, just what was actually
        # given), 3 cartons of Resource 2.0 (237 mL each), 11 water-flush
        # rows (before/after several feeds + free-water sips) summing to
        # exactly 1032 mL so fluid lands at 507 (blend fluid ingredients)
        # + 711 (formula, full-volume I&O) + 1032 (flush) = 2250 mL, and
        # one oral CNF food via the real household-measure entry ("1
        # small" banana) for QOL -- spans every source_type.
        banana_measures = get_measures_for_food(banana, lookup)
        small = banana_measures[
            banana_measures["Measure_Description_and_Unit_EN"].str.contains(
                "small", case=False, na=False
            )
        ]
        banana_grams = float(small.iloc[0]["grams"]) if len(small) > 0 else 100.0
        # The real measure_label/measure_grams now carry "1 small" instead
        # of it being hand-glued onto food_description below (Change 3,
        # 2026-08-15) -- that glue is what broke the Excel export's " — "
        # split on this very row (see _intake_source_name()'s docstring).
        banana_measure_label = (
            str(small.iloc[0]["Measure_Description_and_Unit_EN"]) if len(small) > 0 else None
        )
        banana_measure_grams = banana_grams if len(small) > 0 else None

        _rows = [
            # Tube feed -- blend (full batch across 4 bolus feeds)
            {
                "time": dtime(8, 0),
                "source_type": "blend",
                "source_id": example_id,
                "food_description": None,
                "amount": 250.0,
                "unit": "mL",
                "counts_as_fluid": False,
            },
            {
                "time": dtime(12, 0),
                "source_type": "blend",
                "source_id": example_id,
                "food_description": None,
                "amount": 250.0,
                "unit": "mL",
                "counts_as_fluid": False,
            },
            {
                "time": dtime(17, 0),
                "source_type": "blend",
                "source_id": example_id,
                "food_description": None,
                "amount": 250.0,
                "unit": "mL",
                "counts_as_fluid": False,
            },
            {
                "time": dtime(21, 0),
                "source_type": "blend",
                "source_id": example_id,
                "food_description": None,
                "amount": 250.0,
                "unit": "mL",
                "counts_as_fluid": False,
            },
            # Tube feed -- Resource 2.0, 3 cartons
            {
                "time": dtime(10, 0),
                "source_type": "formula",
                "source_id": "Resource 2.0",
                "food_description": None,
                "amount": 237.0,
                "unit": "mL",
                "counts_as_fluid": False,
            },
            {
                "time": dtime(14, 0),
                "source_type": "formula",
                "source_id": "Resource 2.0",
                "food_description": None,
                "amount": 237.0,
                "unit": "mL",
                "counts_as_fluid": False,
            },
            {
                "time": dtime(20, 0),
                "source_type": "formula",
                "source_id": "Resource 2.0",
                "food_description": None,
                "amount": 237.0,
                "unit": "mL",
                "counts_as_fluid": False,
            },
            # Tube feed -- water flushes: before/after several feeds + free-water sips
            {
                "time": dtime(7, 45),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(8, 15),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(9, 0),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 244.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(10, 15),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(12, 15),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(14, 15),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(15, 30),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 274.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(17, 15),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(19, 0),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 274.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(20, 15),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            {
                "time": dtime(21, 15),
                "source_type": "flush",
                "source_id": None,
                "food_description": None,
                "amount": 30.0,
                "unit": "mL",
                "counts_as_fluid": True,
            },
            # Food & drink -- oral, small banana for QOL
            {
                "time": dtime(8, 30),
                "source_type": "oral",
                "source_id": banana,
                "food_description": "Banana, raw",
                "amount": banana_grams,
                "unit": "g",
                "counts_as_fluid": False,
                "measure_label": banana_measure_label,
                "measure_grams": banana_measure_grams,
            },
        ]
        st.session_state.next_intake_id = len(_rows) + 1
        st.session_state.intake_log = [{"id": i + 1, **row} for i, row in enumerate(_rows)]

        # Fix (2026-08-20 review): this used to wipe every custom food
        # unconditionally and rewind next_custom_code to -1. But the blend
        # filter above (~line 783) only drops EMPTY blends -- a blend an RD
        # had already built from a label-entered food (a negative code in
        # custom_foods, see add_food.py) survives it, so wiping custom_foods
        # here blanked that surviving blend's nutrients. Worse, resetting
        # the counter to -1 handed that same now-vacant code straight back
        # out to the next label typed, so the surviving blend would go on
        # to silently pull a DIFFERENT food's numbers. Mirror the day-file
        # loader's rule instead (_apply_saved_day, ~line 628): keep only
        # the custom foods still referenced by what survives -- the kept
        # blends' ingredients, plus any surviving intake row that names a
        # custom food directly (the example's own rows never do; both are
        # covered so this holds if that ever changes) -- and set the
        # counter to one below the LOWEST surviving code, so a freshly
        # typed label can never be handed a code still in use.
        _referenced_custom_codes = {
            _ing["food_code"]
            for _b in st.session_state.blends.values()
            for _ing in _b["ingredients"]
            if _ing.get("food_code") in st.session_state.custom_foods
        } | {
            _row["source_id"]
            for _row in st.session_state.intake_log
            if _row.get("source_id") in st.session_state.custom_foods
        }
        st.session_state.custom_foods = {
            _code: _food
            for _code, _food in st.session_state.custom_foods.items()
            if _code in _referenced_custom_codes
        }
        st.session_state.next_custom_code = (
            min(st.session_state.custom_foods) - 1 if st.session_state.custom_foods else -1
        )
        st.session_state["load_example"] = True

        # Presets set here, BEFORE the widgets they belong to are
        # instantiated further down in this same script run (the §11
        # widget-state gotcha: this is the one and only window in which
        # `st.session_state[key] = ...` for an already-existing widget key
        # is legal).
        #
        # These figures are spoken in the demo video -- keep them in step
        # with it. Other targets are zeroed because "Load example record"
        # warns that it replaces the targets on screen.
        st.session_state["patient_weight_input"] = 165.0
        st.session_state["weight_unit"] = "lbs"
        for _tname in empty_targets():
            st.session_state[f"target_{_tname}"] = 0.0
        st.session_state["target_energy_kcal"] = 2250.0
        st.session_state["target_protein_g"] = 100.0
        st.session_state["target_fluid_mL"] = 2250.0

        st.session_state["recipe_name_input"] = "Example — Demo case (H&N RT week 5)"
        st.session_state["delivery_method_input"] = "BTF using 24Fr PEG tube via syringe bolus"
        st.rerun()
    else:
        render_alert("error", "Could not find example foods in CNF.")
