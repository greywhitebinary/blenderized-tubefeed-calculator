"""
test_nutrients.py — tests for src/nutrients.py, the per-country nutrient
registry.

A quick pytest primer for a reader who knows nutrition, not testing
jargon: each `def test_...` function below is one independent check.
`assert` just means "this must be true or the test fails". A fixture
(the `@pytest.fixture`-decorated function) is a small reusable setup
step other tests can ask for by naming it as an argument.

Per the Week 3 test-writing brief: the tracked-nutrient set is DATA
(data/packs/canada/nutrients.csv), not something to freeze into an
assertion. These tests check the *mechanism* -- does load_registry()
parse the CSV correctly, do the tier/name lookups filter correctly, does
a missing pack fail loudly -- rather than asserting "Canada tracks
exactly these 19 nutrients", which would break the day an RD edits the
CSV to add or remove a row (as the CONTEXT.md §9 pinned-issues list says
they expect to, pending a survey of other practicing RDs).

The one place this file DOES pin a Canada-specific fact is called out
in a comment where it happens: sodium's numeric CNF code (307). It is
flagged as "worth testing" in the brief because it guards against a real
historical bug (the CNF "NA" string bug) rather than just restating
today's CSV contents.
"""

import pytest

from src.nutrients import (
    NutrientDef,
    VALID_TIERS,
    codes_for,
    defs_for_tier,
    load_registry,
    load_thinning_liquids,
    registry_by_name,
    thinning_csv_path,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def canada_registry() -> list[NutrientDef]:
    """The real Canada pack registry, loaded fresh for each test.

    load_registry() is cached internally (functools.lru_cache), so this
    is cheap to call repeatedly -- it's the small nutrients.csv, not the
    565k-row CNF table (that one is scripts/verify_backend.py's job, not
    ours).
    """
    return load_registry("canada")


# ---------------------------------------------------------------------------
# load_registry()
# ---------------------------------------------------------------------------


def test_load_registry_returns_nutrientdef_objects_with_expected_fields(canada_registry):
    """Every row of nutrients.csv should come back as a NutrientDef with
    all of its documented fields populated and correctly typed -- this is
    the basic "did the CSV parse" check, not a check on which nutrients
    exist.
    """
    assert len(canada_registry) > 0
    for d in canada_registry:
        assert isinstance(d, NutrientDef)
        # Identity fields: non-empty strings.
        assert isinstance(d.name, str) and d.name
        assert isinstance(d.label, str) and d.label
        assert isinstance(d.unit, str) and d.unit
        # code is the numeric CNF Nutrient_Code -- must parse as an int,
        # not a string like "307".
        assert isinstance(d.code, int)
        # tier must be one of the three documented values -- load_registry()
        # itself raises ValueError on anything else, so if we got this far
        # every row already passed that check, but we assert it again here
        # as a direct statement of the invariant.
        assert d.tier in VALID_TIERS
        # The three yes/no CSV columns must come back as real Python
        # bools, not the strings "yes"/"no" -- a downstream `if
        # d.on_label:` check would be silently truthy for the string "no"
        # otherwise.
        assert isinstance(d.on_label, bool)
        assert isinstance(d.show_in_report, bool)
        assert isinstance(d.offer_target, bool)
        assert isinstance(d.decimals, int)
        assert isinstance(d.notes, str)


def test_load_registry_names_are_unique(canada_registry):
    """The registry is keyed by `name` elsewhere (registry_by_name(),
    codes_for()) -- a duplicate name would silently shadow a row in
    those dicts, so this is worth guarding directly.
    """
    names = [d.name for d in canada_registry]
    assert len(names) == len(set(names))


def test_registry_carries_no_limit_or_target_type_column():
    """Neither the CNF nor a product label gives an upper or lower limit,
    and every target is the RD's own, so the registry records none. A
    target_type column (RDA/AI/UL) used to drive a "Below UL"/"Above UL"
    verdict for sodium; it was removed on 2026-09-28 and should not come
    back without a sourced limit behind it."""
    import csv
    from pathlib import Path

    csv_path = Path(__file__).resolve().parent.parent / "data/packs/canada/nutrients.csv"
    with csv_path.open(encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert "target_type" not in header
    assert not hasattr(NutrientDef, "target_type")


def test_load_registry_missing_pack_raises_filenotfounderror():
    """This is deliberate, documented behaviour (src/nutrients.py's module
    docstring, CONTEXT.md §11): there is NO hardcoded fallback registry.
    A country pack that forgot to ship nutrients.csv must fail loudly
    rather than silently render the Canadian table under a different
    pack's name. Do not "fix" this -- a passing test here means the
    safety rail is working, not that something is broken.
    """
    with pytest.raises(FileNotFoundError):
        load_registry("no_such_pack")


# ---------------------------------------------------------------------------
# codes_for() / defs_for_tier() -- tier filtering
# ---------------------------------------------------------------------------


def test_codes_for_no_tier_returns_every_nutrient_including_engine(canada_registry):
    """codes_for(tier=None) is documented to return ALL tiers -- including
    tier="engine" (water_g), which calculate_profile() needs internally
    even though water_g never gets its own report row. Checked against
    the registry itself, not a hardcoded count.
    """
    all_codes = codes_for(tier=None, pack="canada")
    assert set(all_codes) == {d.name for d in canada_registry}
    engine_names = {d.name for d in canada_registry if d.tier == "engine"}
    assert engine_names, "expected at least one engine-tier nutrient (water_g) to test against"
    assert engine_names.issubset(set(all_codes))


@pytest.mark.parametrize("tier", ["label", "clinical", "engine"])
def test_codes_for_filters_to_exactly_the_matching_tier(canada_registry, tier):
    """For each real tier, codes_for(tier=...) should return exactly the
    names whose registry row has that tier -- no more, no less. Compared
    against the registry itself so this doesn't freeze today's Canadian
    nutrient list.
    """
    expected = {d.name for d in canada_registry if d.tier == tier}
    result = codes_for(tier=tier, pack="canada")
    assert set(result) == expected
    # Every value should be the same numeric code the registry has on file.
    by_name = registry_by_name("canada")
    for name, code in result.items():
        assert code == by_name[name].code


def test_codes_for_unknown_tier_returns_empty_dict_not_an_error():
    """codes_for() filters with `d.tier == tier`; it does not validate
    that `tier` is one of the three known values. Feeding it a tier that
    doesn't exist in the data should just produce no matches -- an empty
    dict -- rather than raising. This test documents and locks in that
    actual behaviour (verified by reading src/nutrients.py before writing
    this test), rather than assuming a stricter contract the code doesn't
    actually implement.
    """
    assert codes_for(tier="not_a_real_tier", pack="canada") == {}


def test_defs_for_tier_returns_nutrientdefs_matching_the_tier(canada_registry):
    for tier in VALID_TIERS:
        expected_names = {d.name for d in canada_registry if d.tier == tier}
        result = defs_for_tier(tier, pack="canada")
        assert {d.name for d in result} == expected_names
        for d in result:
            assert d.tier == tier


def test_defs_for_tier_unknown_tier_returns_empty_list_not_an_error():
    """Same actual-behaviour-first reasoning as the codes_for() case above:
    defs_for_tier() has no tier-name validation of its own, so an unknown
    tier should just come back as an empty list.
    """
    assert defs_for_tier("not_a_real_tier", pack="canada") == []


# ---------------------------------------------------------------------------
# registry_by_name()
# ---------------------------------------------------------------------------


def test_registry_by_name_keys_match_each_defs_own_name(canada_registry):
    by_name = registry_by_name("canada")
    assert set(by_name) == {d.name for d in canada_registry}
    for name, d in by_name.items():
        assert d.name == name


# ---------------------------------------------------------------------------
# The CNF "NA" gotcha (CONTEXT.md §11): sodium survives the registry load
# ---------------------------------------------------------------------------


def test_sodium_survives_registry_load_and_keeps_its_numeric_cnf_code():
    """CNF's own Nutrient_Name.csv has the literal string "NA" in
    sodium's Tagname/Nutrient_Symbol columns, which pandas' default
    na_values handling would silently read as NaN -- any lookup that
    joined on Tagname/Symbol would lose sodium without erroring. The
    registry sidesteps this by keying on the NUMERIC Nutrient_Code (307)
    instead, and nutrients.csv is authored fresh (not derived from that
    Tagname/Symbol column), so this test is really checking that the
    workaround is still in place and sodium hasn't regressed back to a
    string-symbol lookup.

    NOTE: 307 is a real, frozen Canada-specific/CNF-specific fact (it's
    the Canadian Nutrient File's fixed numeric code for sodium, not an
    author's editorial choice like which nutrients to display) -- pinning
    it here is intentional per the test brief, not an accidental
    hardcode of the tracked-nutrient set.
    """
    by_name = registry_by_name("canada")
    assert "sodium_mg" in by_name
    sodium = by_name["sodium_mg"]
    assert sodium.code == 307
    assert sodium.name == "sodium_mg"  # not NaN, not the string "NA"


class TestThinningLiquids:
    """Moved out of app/streamlit_app.py 2026-08-17. The filter is the
    clinically load-bearing part: calculator.dilute() models only kcal,
    protein and water, so a nutritive thinner would show sodium DENSITY
    falling while real broth adds a sodium load. Anything with calories or
    protein must never reach the Dilution What-If's dropdown.
    """

    def test_the_shipped_pack_offers_water(self):
        liquids = load_thinning_liquids("canada")
        assert "Water" in liquids
        assert liquids["Water"]["water_g"] == 100.0

    def test_everything_offered_is_non_nutritive(self):
        for name, vals in load_thinning_liquids("canada").items():
            assert vals["kcal"] == 0.0, f"{name} carries calories"
            assert vals["protein_g"] == 0.0, f"{name} carries protein"

    def test_a_missing_pack_falls_back_to_water_rather_than_raising(self):
        """A pack with no thinning_liquids.csv still gets a usable
        dropdown instead of an empty one or an exception."""
        liquids = load_thinning_liquids("no-such-pack")
        assert liquids == {"Water": {"kcal": 0.0, "protein_g": 0.0, "water_g": 100.0}}

    def test_the_path_is_pack_aware(self):
        """Was the last loader reading from a hardcoded `canada` path
        (CONTEXT.md section 9); inert until a second pack exists, but it no
        longer serves Canadian reference data to a non-Canadian pack."""
        assert thinning_csv_path("canada").parent.name == "canada"
        assert thinning_csv_path("elsewhere").parent.name == "elsewhere"
