"""
test_targets.py — tests for src/targets.py.

A quick pytest primer for a reader who knows nutrition, not testing
jargon: `assert` means "this must be true or the test fails".

This module is small on purpose: since the round-2 clinical feedback
pass, targets.py has exactly one function, empty_targets(), and no
default/DRI values live anywhere in this app (see targets.py's module
docstring -- "2000 kcal / 75 g protein" isn't defensible for tube-fed
patients, so the RD always starts blank and types in patient-specific
numbers from their own assessment). These tests check that
empty_targets():
  1. hands back a target KEY for every nutrient the registry marks
     offer_target=yes (plus the special fluid_mL key), read from the
     registry rather than hardcoded, so this doesn't freeze today's
     Canadian nutrient list; and
  2. never invents a target key for magnesium or phosphorus, which the
     registry deliberately marks offer_target=no.
"""

import pytest

from src.nutrients import load_registry
from src.targets import empty_targets

# ---------------------------------------------------------------------------
# empty_targets() shape: keys come from the registry's offer_target column
# ---------------------------------------------------------------------------


def test_empty_targets_keys_match_registry_offer_target_flags():
    """empty_targets() should offer exactly one key per registry row with
    offer_target=yes, plus "fluid_mL" (the fluids-ledger target, which
    isn't a CNF nutrient at all, so it can't come from the registry).
    Checked against the registry itself rather than a hardcoded list of
    nutrient names, so this keeps passing if an RD edits nutrients.csv.
    """
    registry = load_registry("canada")
    expected_nutrient_keys = {d.name for d in registry if d.offer_target}

    targets = empty_targets("canada")

    assert "fluid_mL" in targets
    assert set(targets) - {"fluid_mL"} == expected_nutrient_keys


def test_empty_targets_all_values_are_zero():
    """ "Empty" means every value starts at 0.0 (blank) -- this is the
    ONLY way targets are seeded in this app; there is no DRI/default
    variant to fall back to. A nonzero value here would mean a default
    crept back in.
    """
    targets = empty_targets("canada")
    assert len(targets) > 0
    assert all(v == 0.0 for v in targets.values())
    assert all(isinstance(v, float) for v in targets.values())


def test_empty_targets_missing_pack_raises_filenotfounderror():
    """empty_targets() gets its keys from load_registry(), which raises
    FileNotFoundError for a pack with no nutrients.csv (deliberate, no
    fallback -- see src/nutrients.py). empty_targets() doesn't catch or
    mask that, so the same loud failure should surface here.
    """
    with pytest.raises(FileNotFoundError):
        empty_targets("no_such_pack")


# ---------------------------------------------------------------------------
# Magnesium and phosphorus are deliberately target-less
# ---------------------------------------------------------------------------


def test_magnesium_and_phosphorus_get_no_target_key():
    """Magnesium and phosphorus are tracked (tier="clinical", for the
    author's EN-spreadsheet / BTF-micro-screen reasons) but the registry
    deliberately sets offer_target=no for both -- refeeding-risk
    monitoring happens in hospital on known formulas, not via a BTF
    default target (src/targets.py's module docstring, CONTEXT.md §9's
    pinned-issues list). This must not silently regress: do not invent a
    target field for either nutrient without the author's explicit
    sign-off, which is exactly what this test guards against.
    """
    registry = load_registry("canada")
    by_name = {d.name: d for d in registry}

    # Confirm the registry still encodes this as the reason -- if either
    # nutrient flips to offer_target=yes, that's an intentional registry
    # edit (not a bug), and this test should be revisited alongside it.
    assert by_name["magnesium_mg"].offer_target is False
    assert by_name["phosphorus_mg"].offer_target is False

    targets = empty_targets("canada")
    assert "magnesium_mg" not in targets
    assert "phosphorus_mg" not in targets


def test_no_clinical_tier_nutrient_gets_a_target_key():
    """More generally: NO tier="clinical" nutrient should ever produce a
    target key (the BTF micro screen is a one-time screen, not something
    an RD sets a daily numeric goal against) -- checked against the
    registry's clinical-tier rows as a group, not just the two named in
    the brief, so a future clinical-tier addition (e.g. a hypothetical
    zinc target) would also be caught here if it slipped through without
    an offer_target=no.
    """
    registry = load_registry("canada")
    clinical_names = {d.name for d in registry if d.tier == "clinical"}
    assert clinical_names, "expected at least one clinical-tier nutrient to test against"

    targets = empty_targets("canada")
    assert clinical_names.isdisjoint(set(targets))
