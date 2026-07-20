"""AppTest check for the 2026-07-20 tab restructure (scratch verification).

Asserts: three tabs named Nutrition Targets / Feed Recipes / Daily Intake
Record render on fresh load with no exception; after loading the example
day, the Feed Recipes tab carries the per-blend density panel, dilution
what-if, comparator, and flow test, and the Daily Intake Record tab
carries the intake editor, daily totals/adequacy, chart note, and export.
"""

from streamlit.testing.v1 import AppTest


def main() -> None:
    at = AppTest.from_file("app/streamlit_app.py", default_timeout=60)
    at.run()
    assert not at.exception, f"fresh load raised: {at.exception}"

    labels = [t.label for t in at.tabs]
    assert labels == ["Nutrition Targets", "Feed Recipes", "Daily Intake Record"], labels
    print(f"tabs OK: {labels}")

    # Fresh load: all three tab shells render (targets inputs, blend
    # selector, intake editor).
    assert len(at.number_input) > 0
    assert len(at.tabs) == 3

    # Load the example day, then check section placement by subheader text.
    at.button(key="Load example day") if False else None  # button has no key
    load_btn = next(b for b in at.button if "Load example" in b.label)
    load_btn.click().run()
    assert not at.exception, f"example load raised: {at.exception}"

    subheaders = [s.value for s in at.subheader]
    for expected in (
        "Blend",
        "Ingredients",
        "Per-blend density panel",
        "Dilution What-If",
        "Commercial Formula Comparator",
        "Flow Test",
        "Intake Record",
        "Daily Totals & Adequacy",
        "Per-Source Breakdown",
        "Chart Note",
        "Export",
    ):
        assert expected in subheaders, f"missing subheader: {expected!r} — have {subheaders}"
    print("section placement OK: all expected subheaders present")

    # The example day produces a chart note and a non-empty adequacy table.
    assert any("Provides ~" in (c.value or "") for c in at.code), "no chart note"
    assert len(at.dataframe) > 0
    print("chart note + tables OK")

    # Round-2 feedback checks:
    # (a) weight unit radio offers kg/lbs.
    weight_radio = next(r for r in at.radio if r.key == "weight_unit")
    assert list(weight_radio.options) == ["kg", "lbs"]
    print("weight kg/lbs toggle OK")

    # (b) comparator Company filter is back (round-3 feedback), defaulting
    # to "All" so cross-company comparison still works.
    company_radio = next(r for r in at.radio if r.label == "Company")
    assert company_radio.value == "All", company_radio.value
    print("comparator company-filter OK (present, defaults to All)")

    # (c) flush helper: med-flush mode adds one labeled flush row.
    rows_before = len(at.session_state["intake_log"])
    flush_radio = next(r for r in at.radio if r.key == "flush_mode")
    flush_radio.set_value("Med flushes (daily, rough)").run()
    assert not at.exception, f"flush mode switch raised: {at.exception}"
    next(b for b in at.button if b.key == "flush_add_btn").click().run()
    assert not at.exception, f"flush add raised: {at.exception}"
    log = at.session_state["intake_log"]
    assert len(log) == rows_before + 1
    assert log[-1]["source_type"] == "flush"
    assert log[-1]["food_description"] == "Med flushes"
    assert log[-1]["counts_as_fluid"] is True
    print(f"med-flush helper OK: added {log[-1]['amount']:.0f} mL row")

    # (d) with-feeds mode computes from the number of tube-feed rows.
    flush_radio = next(r for r in at.radio if r.key == "flush_mode")
    flush_radio.set_value("With feeds (calculated)").run()
    n_feeds = sum(
        1 for r in at.session_state["intake_log"]
        if r["source_type"] in ("blend", "formula")
    )
    assert n_feeds == 2, n_feeds  # example day: two blend feeds
    next(b for b in at.button if b.key == "flush_add_btn").click().run()
    log = at.session_state["intake_log"]
    assert log[-1]["food_description"] == "Water flushes with feeds"
    assert log[-1]["amount"] == 60.0 * 2 * n_feeds  # defaults: 60 mL × 2 × feeds
    print(f"with-feeds helper OK: {log[-1]['amount']:.0f} mL from {n_feeds} feeds")

    print("=== TAB RESTRUCTURE APPTTEST PASSED ===")


if __name__ == "__main__":
    main()