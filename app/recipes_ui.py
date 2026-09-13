"""Coordinate recipe panels in their established screen order."""

from app.recipe_editor import render_recipe_editor
from app.recipe_analysis import render_density, render_dilution, render_comparator
from app.recipe_io_ui import render_recipe_record


def render_recipes(fn, na, lookup, fg, targets):
    selected_id, blend, flow_test = render_recipe_editor(fn, na, lookup, fg)
    profile, fluid_fraction = render_density(blend, na)
    render_dilution(selected_id, blend, profile, fluid_fraction, fn, targets)
    render_recipe_record(selected_id, blend, flow_test, fn)
    render_comparator(selected_id, blend, profile, na)
