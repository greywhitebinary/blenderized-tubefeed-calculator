"""Build chart-note text from the same source groups as the intake totals."""

from src.intake import (
    IntakeTotals,
    sorted_intake_log,
    intake_row_family,
    TUBE_FEED_LABEL,
    FOOD_DRINK_LABEL,
    WATER_FLUSH_LABEL,
)


def build_chart_note(
    intake_log: list[dict], intake_totals: IntakeTotals, delivery_method: str
) -> str:
    """Format a valid day's totals without modifying the order or its inputs."""
    _ordered_note_rows = sorted_intake_log(intake_log)
    _tube_note_rows = [r for r in _ordered_note_rows if intake_row_family(r) == TUBE_FEED_LABEL]
    _oral_note_rows = [r for r in _ordered_note_rows if intake_row_family(r) == FOOD_DRINK_LABEL]

    # --- The three summary lines, in the author's charting format
    # (2026-08-09): feed regimen, oral intake, total -- each one
    # Energy/Protein/CHO/Fat/Fluids in that order, and the feed line
    # showing its fluid split.
    #
    # "Fluids" is counted per line the way the clinic counts it, not
    # by one rule: feed = free water + flushes (so the bracket adds
    # up), oral = only rows ticked "counts as fluid", because nobody
    # charts the water in a banana. Total is the two added.
    _tube_sub = intake_totals.subtotals.get(TUBE_FEED_LABEL, {}).get("nutrient_totals", {})
    _oral_family = intake_totals.subtotals.get(FOOD_DRINK_LABEL, {})
    _oral_sub = _oral_family.get("nutrient_totals", {})
    _flush_mL = intake_totals.water_sources.get(WATER_FLUSH_LABEL, 0.0)

    def _macro_bits(totals: dict, fluid_mL: float) -> str:
        return (
            f"Energy {totals.get('energy_kcal', 0.0):.0f}kcal, "
            f"Protein {totals.get('protein_g', 0.0):.0f}g, "
            f"CHO {totals.get('carbohydrate_g', 0.0):.0f}g, "
            f"Fat {totals.get('fat_g', 0.0):.0f}g, "
            f"Fluids {fluid_mL:.0f}ml"
        )

    _tube_free_water = _tube_sub.get("water_g", 0.0)
    _tube_fluid = _tube_free_water + _flush_mL
    _oral_fluid = _oral_family.get("fluid_provided_mL", 0.0)

    # The delivery-method field is the opening line verbatim, so a
    # blank one drops the line rather than emitting a bare full stop.
    _water_split = (
        f" ({_tube_free_water:.0f}ml from free water " f"+ {_flush_mL:.0f}ml from water flushes)"
    )
    _total_line = "Total daily intake: " + _macro_bits(
        intake_totals.nutrient_totals, _tube_fluid + _oral_fluid
    )

    _summary_lines = []
    if delivery_method.strip():
        _summary_lines.append(delivery_method.strip().rstrip(".") + ".")
    if _tube_note_rows and _oral_note_rows:
        _summary_lines.append(
            "Feed regimen: " + _macro_bits(_tube_sub, _tube_fluid) + _water_split + "."
        )
        _summary_lines.append("Oral intake: " + _macro_bits(_oral_sub, _oral_fluid) + ".")
        _summary_lines.append(_total_line + ".")
    else:
        # One category only, so the category line and the total would
        # be the same numbers twice. Keep the total: every note then
        # ends on the same label whatever the day held, which is what
        # someone scanning back through a series of them looks for.
        # The water split rides along when there is tube feed to split.
        _summary_lines.append(_total_line + (_water_split if _tube_note_rows else "") + ".")

    # The flow-test line was dropped here too (author, 2026-08-10) --
    # it is still shown in the Feed Recipes tab and saved to the
    # workbook, it just isn't part of the pasted note.
    _note_text = "\n".join(_summary_lines)
    return _note_text
