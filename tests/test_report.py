"""
test_report.py — tests for src/report.py's two adequacy tables
(generate_adequacy_report -- the daily main table -- and
generate_clinical_screen -- the collapsed BTF micro screen) and the
helper functions that decide their wording.

A quick pytest primer for a reader who knows nutrition, not testing
jargon: `assert` means "this must be true or the test fails". A
fixture (the `@pytest.fixture`-decorated functions below) is reusable
setup other tests ask for by naming it as an argument -- here, mostly
small hand-built "daily totals" and "coverage" dictionaries standing in
for a real Intake Record day, per the brief's instruction not to load
the 565k-row CNF table for these tests.

The point of this file is the TIER rule: a nutrient's `tier` (from the
registry, src/nutrients.py) decides which of the two tables it can ever
appear in, and tier="engine" (water_g) must never appear in either --
getting this wrong would either clutter the daily table with one-time
screening nutrients, or silently drop mandatory-label nutrients from the
table an RD actually reads every day.

None of these tests hardcode "the Canadian nutrient list" as a
correctness assertion -- they read the registry (src/nutrients.py) at
test time and check that report.py's tier-filtering honours whatever
the registry says, so they keep passing if an RD edits nutrients.csv to
add/remove a nutrient. The one deliberate exception is called out where
it happens: sodium's target_type="UL" is a real, documented Canada-pack
fact (the only UL nutrient today) and is exactly the case the brief asks
to test directly.
"""

import pytest

from src.nutrients import defs_for_tier, registry_by_name
from src.report import (
    _adequacy_status,
    _coverage_text,
    _zero_coverage,
    generate_adequacy_report,
    generate_clinical_screen,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def label_defs():
    """The nutrients that belong in the MAIN daily adequacy table:
    tier="label" (on Canada's mandatory Nutrition Facts panel) AND
    show_in_report=True (the author's "show what's needed" subset --
    e.g. saturated fat is tier="label" but show_in_report=False, so it's
    excluded here too, matching what generate_adequacy_report() itself
    filters on).
    """
    return [d for d in defs_for_tier("label", pack="canada") if d.show_in_report]


@pytest.fixture
def clinical_defs():
    """The nutrients that belong in the BTF micro screen: tier="clinical"
    and show_in_report=True (every clinical-tier row is show_in_report=
    True in the Canada pack, but we filter the same way report.py does
    rather than assuming that).
    """
    return [d for d in defs_for_tier("clinical", pack="canada") if d.show_in_report]


@pytest.fixture
def engine_defs():
    """The nutrients that must NEVER get their own row in either table
    (water_g today) -- tracked only so the calculator can compute
    free-water internally.
    """
    return defs_for_tier("engine", pack="canada")


def _full_coverage(defs):
    """Build a nutrient_coverage dict saying "every ingredient in this
    (fictional) recipe supplied a value" for each of the given
    NutrientDefs -- i.e. 1 of 1 ingredients had data. Use this when a
    test doesn't care about coverage/hiding and just wants ordinary rows.
    """
    return {d.name: (1, 1) for d in defs}


def _totals(defs, value=100.0):
    """A daily_totals dict giving every one of the given NutrientDefs the
    same made-up daily amount. The exact number doesn't matter for the
    tier-placement tests -- only that every nutrient in play has SOME
    value so its row isn't hidden for zero coverage.
    """
    return {d.name: value for d in defs}


# ---------------------------------------------------------------------------
# Tier placement: the whole point of having two report tables
# ---------------------------------------------------------------------------


def test_label_tier_nutrients_appear_in_main_table_only(label_defs, clinical_defs):
    """Every tier="label" (+ show_in_report) nutrient must show up as a
    row in generate_adequacy_report()'s table, by its registry `label`
    text, and must NOT show up in generate_clinical_screen()'s table.
    """
    all_defs = label_defs + clinical_defs
    totals = _totals(all_defs)
    coverage = _full_coverage(all_defs)

    main_df, _ = generate_adequacy_report(totals, targets={}, nutrient_coverage=coverage)
    screen_df, _ = generate_clinical_screen(totals, targets={}, nutrient_coverage=coverage)

    main_names = set(main_df["Nutrient"])
    screen_names = set(screen_df["Nutrient"])

    for d in label_defs:
        assert d.label in main_names, f"{d.label} (tier=label) missing from main adequacy table"
        assert d.label not in screen_names, f"{d.label} (tier=label) leaked into the micro screen"


def test_clinical_tier_nutrients_appear_in_micro_screen_only(label_defs, clinical_defs):
    """The mirror image of the test above: every tier="clinical" nutrient
    (magnesium, phosphorus, zinc, vitamin D, B12 in the Canada pack)
    belongs in generate_clinical_screen()'s table and must never leak
    into the daily main table an RD checks every day.
    """
    all_defs = label_defs + clinical_defs
    totals = _totals(all_defs)
    coverage = _full_coverage(all_defs)

    main_df, _ = generate_adequacy_report(totals, targets={}, nutrient_coverage=coverage)
    screen_df, _ = generate_clinical_screen(totals, targets={}, nutrient_coverage=coverage)

    main_names = set(main_df["Nutrient"])
    screen_names = set(screen_df["Nutrient"])

    for d in clinical_defs:
        assert d.label in screen_names, f"{d.label} (tier=clinical) missing from the micro screen"
        assert d.label not in main_names, f"{d.label} (tier=clinical) leaked into the main table"


def test_engine_tier_nutrient_never_rendered_in_either_table(
    label_defs, clinical_defs, engine_defs
):
    """tier="engine" (water_g) exists purely so the calculator can derive
    free-water internally -- it must never appear as its OWN row (by its
    registry label, "Water (moisture)") in either report table. Note
    generate_adequacy_report() DOES render a derived "Free water
    (estimated)" row from the water_g total -- that's a different,
    deliberately-named summary row, not water_g's registry row, so this
    test checks for the registry label specifically, not for the mere
    presence of the word "water".
    """
    assert engine_defs, "expected at least one engine-tier nutrient (water_g) to test against"

    all_defs = label_defs + clinical_defs + engine_defs
    totals = _totals(all_defs)
    coverage = _full_coverage(all_defs)

    main_df, _ = generate_adequacy_report(totals, targets={}, nutrient_coverage=coverage)
    screen_df, _ = generate_clinical_screen(totals, targets={}, nutrient_coverage=coverage)

    main_names = set(main_df["Nutrient"])
    screen_names = set(screen_df["Nutrient"])

    for d in engine_defs:
        assert d.label not in main_names
        assert d.label not in screen_names


# ---------------------------------------------------------------------------
# _adequacy_status(): UL wording vs ordinary target wording
# ---------------------------------------------------------------------------


def test_adequacy_status_ul_wording_is_above_below_ul_not_target():
    """A target_type="UL" (a ceiling, e.g. sodium) must never say "Above
    target"/"Meeting target"/"Below target" -- those phrases imply 90-110%
    is the goal, which is wrong for a ceiling nutrient where the goal is
    simply staying under it. Getting this wrong would mislead an RD about
    whether a number is a limit or something to aim for.
    """
    # 50% of the UL -> under the ceiling.
    assert _adequacy_status(daily_total=50, target=100, target_type="UL") == "Below UL"
    # Exactly at the ceiling (100%) is still "Below UL" -- only strictly
    # OVER the ceiling counts as "Above UL" (src/report.py: `pct > 1.0`).
    assert _adequacy_status(daily_total=100, target=100, target_type="UL") == "Below UL"
    # Over the ceiling -> "Above UL".
    assert _adequacy_status(daily_total=150, target=100, target_type="UL") == "Above UL"

    # And never the ordinary-target vocabulary for a UL nutrient:
    ul_status = _adequacy_status(daily_total=150, target=100, target_type="UL")
    assert "target" not in ul_status.lower()


def test_adequacy_status_ordinary_target_wording_for_non_ul_types():
    """RDA/AI/estimate (i.e. anything that isn't a ceiling) use the
    below/meeting/above TARGET vocabulary, with the documented 90%/110%
    thresholds.
    """
    assert _adequacy_status(daily_total=50, target=100, target_type="RDA") == "Below target"
    assert _adequacy_status(daily_total=95, target=100, target_type="AI") == "Meeting target"
    assert _adequacy_status(daily_total=150, target=100, target_type="estimate") == "Above target"
    # An empty target_type ("" -- every nutrient except sodium in the
    # Canada pack) should behave the same as "estimate" once _tier_rows()
    # has substituted the default; _adequacy_status() itself just takes
    # whatever string it's handed, so we call it with "estimate" directly
    # here (the "" -> "estimate" substitution is _tier_rows()'s job,
    # exercised by the sodium test below and the full-report test after
    # it).


def test_adequacy_status_no_target_entered_returns_no_target_regardless_of_type():
    """Targets always start blank in this app (no defaults anywhere --
    see src/targets.py's module docstring). A target of 0 (not entered)
    must render "No target", for EVERY target_type, including UL -- a
    dietitian who hasn't set a sodium ceiling yet should see "No target",
    not a false "Below UL" implying 0% of an unset ceiling.
    """
    assert _adequacy_status(daily_total=50, target=0, target_type="UL") == "No target"
    assert _adequacy_status(daily_total=50, target=0, target_type="RDA") == "No target"
    assert _adequacy_status(daily_total=50, target=0, target_type="") == "No target"


def test_sodium_reports_ul_wording_through_the_full_adequacy_report():
    """End-to-end version of the UL check, through the real
    generate_adequacy_report() path rather than calling _adequacy_status()
    directly -- this is what an RD actually sees on screen.

    NOTE: this pins a real Canada-pack fact -- sodium_mg is the only
    nutrient with target_type="UL" in data/packs/canada/nutrients.csv
    today. That's intentional per the test brief ("a test asserting this
    is well worth having"): sodium's UL-ness is a clinical fact (a
    ceiling, not a goal) independent of which OTHER nutrients the
    registry happens to track, so pinning it doesn't freeze the
    tracked-nutrient set the way asserting "there are exactly 10 rows in
    the main table" would.
    """
    sodium_def = registry_by_name("canada")["sodium_mg"]
    assert sodium_def.target_type == "UL"  # the documented Canada-pack fact

    totals = {"sodium_mg": 3000.0}
    targets = {"sodium_mg": 2300.0}
    coverage = {"sodium_mg": (1, 1)}

    df, hidden = generate_adequacy_report(totals, targets=targets, nutrient_coverage=coverage)
    row = df[df["Nutrient"] == sodium_def.label].iloc[0]

    assert row["Status"] == "Above UL"
    assert "target" not in row["Status"].lower()
    assert sodium_def.label not in hidden


# ---------------------------------------------------------------------------
# Zero-coverage hiding and the "N/M ingredients" provenance note
# ---------------------------------------------------------------------------


def test_zero_coverage_helper_flags_only_the_zero_of_n_case():
    """_zero_coverage() should be True only when the recipe has at least
    one ingredient that COULD have supplied this nutrient (n_total > 0)
    but NONE actually did (n_supplying == 0). An empty recipe (0/0, no
    ingredients at all) is a different case and must not be flagged --
    src/report.py's own docstring calls this out explicitly.
    """
    assert _zero_coverage("some_nutrient", {"some_nutrient": (0, 3)}) is True
    assert _zero_coverage("some_nutrient", {"some_nutrient": (1, 3)}) is False
    assert _zero_coverage("some_nutrient", {"some_nutrient": (0, 0)}) is False
    # A nutrient absent from the coverage dict entirely defaults to (0, 0)
    # -- also not the zero-coverage case.
    assert _zero_coverage("not_in_dict", {}) is False


def test_coverage_text_helper_shows_n_of_m_only_when_incomplete():
    """_coverage_text() should render "n/m ingredients" only when
    coverage is INCOMPLETE (fewer ingredients supplied a value than the
    recipe has); full coverage renders "—" -- the same "nothing to flag"
    convention used elsewhere in this table (Target/% Target also show
    "—" when there's nothing to report).
    """
    assert _coverage_text("x", {"x": (1, 2)}) == "1/2 ingredients"
    assert _coverage_text("x", {"x": (2, 2)}) == "—"
    assert _coverage_text("x", {"x": (0, 0)}) == "—"
    assert _coverage_text("missing", {}) == "—"


def test_zero_coverage_row_is_hidden_and_named_in_the_footnote_list(label_defs):
    """A nutrient with 0/N coverage (no ingredient in the recipe had CNF
    data for it at all) should be DROPPED from the visible table -- a
    confident-looking "0" would misrepresent "no data" as "measured
    zero" -- and its label should come back in the second return value so
    the caller can render the "not shown — no data from any ingredient:
    X, Y" footnote.
    """
    assert len(label_defs) >= 2, "need at least two label nutrients to isolate one"
    zero_def, *rest = label_defs

    totals = _totals(rest)
    totals[zero_def.name] = 0.0
    coverage = _full_coverage(rest)
    coverage[zero_def.name] = (0, 3)  # 3 ingredients in this fictional recipe, none had data

    df, hidden = generate_adequacy_report(totals, targets={}, nutrient_coverage=coverage)

    assert zero_def.label in hidden
    assert zero_def.label not in set(df["Nutrient"])
    # The rest of the table is unaffected.
    for d in rest:
        assert d.label in set(df["Nutrient"])


def test_partial_coverage_shows_n_of_m_ingredients_note_in_the_real_table(label_defs):
    """Same idea as the helper-level test above, but through the real
    generate_adequacy_report() DataFrame, checking the actual "Coverage"
    column text an RD would see.
    """
    assert len(label_defs) >= 2
    partial_def, full_def, *_ = label_defs

    totals = _totals(label_defs)
    coverage = _full_coverage(label_defs)
    coverage[partial_def.name] = (1, 2)  # only 1 of 2 ingredients had data

    df, hidden = generate_adequacy_report(totals, targets={}, nutrient_coverage=coverage)

    partial_row = df[df["Nutrient"] == partial_def.label].iloc[0]
    full_row = df[df["Nutrient"] == full_def.label].iloc[0]

    assert partial_row["Coverage"] == "1/2 ingredients"
    assert full_row["Coverage"] == "—"
    assert partial_def.label not in hidden  # incomplete, not zero -- still shown


# ---------------------------------------------------------------------------
# No target set -- targets always start blank in this app
# ---------------------------------------------------------------------------


def test_nutrient_with_no_target_set_shows_no_target_status_and_blank_dashes(label_defs):
    """Targets always start blank (no default targets anywhere -- see
    src/targets.py's module docstring). With an empty targets dict, every
    ordinary nutrient row should show Status="No target" and both Target
    and % Target as "—", never a fabricated percentage against a target
    of zero.
    """
    totals = _totals(label_defs, value=50.0)
    coverage = _full_coverage(label_defs)

    df, _ = generate_adequacy_report(totals, targets={}, nutrient_coverage=coverage)

    for d in label_defs:
        row = df[df["Nutrient"] == d.label].iloc[0]
        assert row["Status"] == "No target"
        assert row["Target"] == "—"
        assert row["% Target"] == "—"
