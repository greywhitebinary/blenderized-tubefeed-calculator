"""AppTest checks for source classification and saved chart-note wording."""

import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest
from src.day_io import day_to_workbook_bytes, workbook_bytes_to_day


def example():
    app = AppTest.from_file(str(ROOT / "app/streamlit_app.py"), default_timeout=60).run()
    next(button for button in app.button if "example" in button.label.lower()).click().run()
    assert not app.exception
    return app


def test_oral_modular_uses_same_note_group_as_intake_table():
    app = example()
    formula = next(
        row.copy() for row in app.session_state["intake_log"] if row["source_type"] == "formula"
    )
    app.session_state["intake_log"] = [
        {**formula, "id": 1},
        {
            "id": 2,
            "time": None,
            "source_type": "modular",
            "source_id": "Boost Pudding",
            "amount": 100.0,
            "unit": "g",
            "counts_as_fluid": False,
            "route": "oral",
        },
    ]
    app.run()
    assert not app.exception
    note = app.session_state["_chart_note_generated_record"]
    assert "Feed regimen: " in note, note
    assert "Oral intake: Energy 162kcal" in note, note
    assert "Total daily intake: " in note


def test_delivery_method_is_restored_and_blank_clears_previous_wording():
    app = example()
    for method in ["Pump via gastrostomy — saved wording", ""]:
        payload = day_to_workbook_bytes(
            label="Saved test record",
            patient_weight=60,
            weight_unit="kg",
            targets={},
            blends=app.session_state["blends"],
            intake_log=app.session_state["intake_log"],
            custom_foods=app.session_state["custom_foods"],
            delivery_method=method,
        )
        parsed = workbook_bytes_to_day(payload)
        assert parsed.delivery_method == method
        app.text_input(key="delivery_method_input").set_value("Different current wording").run()
        app.session_state["_apply_day"] = parsed
        app.run()
        assert not app.exception
        assert app.text_input(key="delivery_method_input").value == method
        note = app.session_state["_chart_note_generated_record"]
        assert "Different current wording" not in note
        if method:
            assert note.startswith(method + "."), note


def test_delete_blend_and_intake_preserve_unrelated_records():
    app = example()
    selected = app.session_state["selected_blend_id"]
    blends = deepcopy(app.session_state["blends"])
    expected_rows = [
        deepcopy(row)
        for row in app.session_state["intake_log"]
        if not (row["source_type"] == "blend" and row["source_id"] == selected)
    ]
    next(button for button in app.button if button.label == "🗑️ Delete blend").click().run()
    assert not app.exception
    del blends[selected]
    assert app.session_state["blends"] == blends
    assert app.session_state["intake_log"] == expected_rows
    assert app.session_state["selected_blend_id"] in blends
    previous_id = app.session_state["next_intake_id"]
    app.number_input(key="tf_amount_input").set_value(100).run()
    app.button(key="tf_add_btn").click().run()
    assert not app.exception
    rows = app.session_state["intake_log"]
    assert rows[:-1] == expected_rows
    assert rows[-1]["amount"] == 100
    assert rows[-1]["id"] > previous_id
    assert len({row["id"] for row in rows}) == len(rows)
    app.button(key=f"del_intake_{rows[-1]['id']}").click().run()
    assert not app.exception
    assert app.session_state["intake_log"] == expected_rows


def test_thinning_creates_independent_copy_and_keeps_intake():
    app = example()
    selected = app.session_state["selected_blend_id"]
    blends = deepcopy(app.session_state["blends"])
    rows = deepcopy(app.session_state["intake_log"])
    next(slider for slider in app.slider if slider.label == "Add liquid (mL)").set_value(150).run()
    app.button(key=f"dilute_commit_{selected}").click().run()
    assert not app.exception
    new_id = app.session_state["selected_blend_id"]
    assert new_id not in blends
    for blend_id, original in blends.items():
        assert app.session_state["blends"][blend_id] == original
    copied = app.session_state["blends"][new_id]
    original = blends[selected]
    assert copied["measured_volume_mL"] == original["measured_volume_mL"] + 150
    assert len(copied["ingredients"]) == len(original["ingredients"]) + 1
    for before, after in zip(original["ingredients"], copied["ingredients"]):
        assert {k: v for k, v in before.items() if k != "id"} == {
            k: v for k, v in after.items() if k != "id"
        }
    assert copied["ingredients"][-1]["grams"] == 150
    ids = [
        ing["id"] for blend in app.session_state["blends"].values() for ing in blend["ingredients"]
    ]
    assert len(ids) == len(set(ids))
    assert app.session_state["intake_log"] == rows


if __name__ == "__main__":
    test_oral_modular_uses_same_note_group_as_intake_table()
    test_delivery_method_is_restored_and_blank_clears_previous_wording()
    test_delete_blend_and_intake_preserve_unrelated_records()
    test_thinning_creates_independent_copy_and_keeps_intake()
    print("WORKFLOW CONNECTIONS PASSED")
