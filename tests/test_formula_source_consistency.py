"""
test_formula_source_consistency.py — the check that would have caught the
2026-08 Abbott mix-up.

WHAT HAPPENED. Four Abbott feeds (Jevity 1.2 Cal, Jevity 1.5 Cal, Osmolite
1.2 Cal, TwoCal HN) were derived from the 2024 Abbott adult product guide,
whose nutrition table printed two columns for each of those four products:
a small carton and a ready-to-hang container. Those columns disagreed on
20-24 nutrients because they described two different SKUs, not one product
at two serving sizes -- and nothing in the data pipeline noticed. See
data/packs/canada/formula_sources/UNIT_CONVERSIONS.md section 1 for the
full story and its resolution.

THE RULE (UNIT_CONVERSIONS.md section 1): "divide each column by its own
volume. If the per-mL figures agree, it is one product and either column
will do. If they diverge for many nutrients at once, stop." That check was
never mechanised -- it lived only as something a person was supposed to do
by hand before typing a number into formulas.csv. This file mechanises it.

WHAT THIS FILE DOES NOT DO. It does not re-parse the PDFs (this repo
deliberately has no PDF table-scraper -- see formula_sources/README.md).
SOURCE_TABLES below is a hand-transcription of the "NUTRIENT VALUES" table
each Abbott Product Information Sheet prints (dated October 2025 for the
three Jevity/Osmolite sheets, September 2025 for TwoCal HN), one row per
disclosed nutrient, one entry per printed column. Adding a new multi-column
feed just means adding another entry to SOURCE_TABLES -- the comparison
logic is generic, not hardcoded to these four products.
"""

import csv
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FORMULAS_CSV = PROJECT_ROOT / "data" / "packs" / "canada" / "formulas.csv"

# Relative spread tolerance for figures rounded to 2-3 significant figures
# by the manufacturer at each of several volumes. The tightest legitimate
# rounding noise measured across every nutrient in every table below is
# 5.4% (Vitamin K, Jevity 1.2 Cal / Osmolite 1.2 Cal, driven by the 1500 mL
# column's "0.19 mg" carrying only 2 sig figs). 10% leaves that comfortable
# headroom while remaining far below the smallest real disagreement in the
# 2024 guide's two-SKU mix-up (roughly 30%, and up to ~19x for biotin).
TOLERANCE = 0.10

# One entry per Abbott Product Information Sheet (October/September 2025),
# transcribed from the "NUTRIENT VALUES" table on page 2 of each PDF in
# data/packs/canada/formula_sources/. Every disclosed nutrient is included,
# not just the ones formulas.csv tracks, so this check also guards
# nutrients the app doesn't store (e.g. biotin) against the same class of
# mistake.
SOURCE_TABLES = {
    "Jevity 1.2 Cal": {
        "volumes_mL": [100, 237, 1500],
        "nutrients": {
            "Energy_Cal": [120, 284, 1800],
            "Protein_g": [5.6, 13, 83],
            "Fat_g": [3.9, 9.3, 59],
            "Carbohydrate_g": [17, 40, 254],
            "Fibre_g": [1.7, 4, 26],
            "Water_g": [81, 192, 1211],
            "VitaminA_IU": [240, 569, 3600],
            "BetaCarotene_mg": [0.13, 0.31, 1.9],
            "VitaminD_IU": [64, 152, 960],
            "VitaminE_IU": [8.4, 20, 125],
            "VitaminK_mg": [0.012, 0.029, 0.19],
            "Thiamine_mg": [0.17, 0.4, 2.6],
            "Riboflavin_mg": [0.25, 0.59, 3.7],
            "VitaminB6_mg": [0.14, 0.33, 2.1],
            "VitaminB12_mg": [0.00096, 0.0023, 0.014],
            "Niacin_mg": [0.83, 2, 12],
            "FolicAcid_mg": [0.019, 0.046, 0.29],
            "PantothenicAcid_mg": [0.4, 0.95, 6],
            "Biotin_mg": [0.0024, 0.0057, 0.036],
            "VitaminC_mg": [25, 59, 375],
            "Sodium_mg": [107, 254, 1600],
            "Potassium_mg": [239, 566, 3585],
            "Calcium_mg": [120, 284, 1800],
            "Phosphorus_mg": [120, 284, 1800],
            "Magnesium_mg": [37, 88, 555],
            "Iron_mg": [1.4, 3.4, 22],
            "Zinc_mg": [1.1, 2.6, 16],
            "Manganese_mg": [0.34, 0.81, 5.1],
            "Copper_mg": [0.17, 0.4, 2.6],
            "Selenium_mg": [0.0058, 0.014, 0.087],
        },
    },
    "Jevity 1.5 Cal": {
        "volumes_mL": [100, 237, 1500],
        "nutrients": {
            "Energy_Cal": [150, 356, 2250],
            "Protein_g": [6.4, 15, 96],
            "Fat_g": [5, 12, 75],
            "Carbohydrate_g": [22, 51, 324],
            "Fibre_g": [2.1, 5, 32],
            "Water_g": [76, 180, 1140],
            "VitaminA_IU": [300, 711, 4500],
            "VitaminD_IU": [80, 190, 1200],
            "VitaminE_IU": [12, 29, 180],
            "VitaminK_mg": [0.017, 0.04, 0.26],
            "Thiamine_mg": [0.19, 0.45, 2.8],
            "Riboflavin_mg": [0.32, 0.76, 4.8],
            "VitaminB6_mg": [0.23, 0.55, 3.4],
            "VitaminB12_mg": [0.0012, 0.0028, 0.018],
            "Niacin_mg": [1, 2.4, 15],
            "FolicAcid_mg": [0.024, 0.057, 0.36],
            "PantothenicAcid_mg": [0.79, 1.9, 12],
            "Biotin_mg": [0.003, 0.0071, 0.045],
            "VitaminC_mg": [30, 71, 450],
            "Sodium_mg": [133, 315, 1995],
            "Potassium_mg": [218, 517, 3270],
            "Calcium_mg": [130, 308, 1950],
            "Phosphorus_mg": [125, 296, 1875],
            "Magnesium_mg": [42, 100, 630],
            "Iron_mg": [1.8, 4.3, 27],
            "Zinc_mg": [1.3, 3.1, 20],
            "Manganese_mg": [0.43, 1, 6.5],
            "Copper_mg": [0.22, 0.52, 3.3],
            "Selenium_mg": [0.0074, 0.018, 0.11],
        },
    },
    "Osmolite 1.2 Cal": {
        "volumes_mL": [100, 237, 1500],
        "nutrients": {
            "Energy_Cal": [120, 284, 1800],
            "Protein_g": [5.6, 13, 83],
            "Fat_g": [3.9, 9.3, 59],
            "Carbohydrate_g": [16, 37, 236],
            "Water_g": [82, 194, 1230],
            "VitaminA_IU": [240, 569, 3600],
            "BetaCarotene_mg": [0.13, 0.31, 1.9],
            "VitaminD_IU": [64, 152, 960],
            "VitaminE_IU": [8.9, 21, 134],
            "VitaminK_mg": [0.012, 0.029, 0.19],
            "VitaminC_mg": [25, 59, 375],
            "Thiamine_mg": [0.17, 0.4, 2.6],
            "Riboflavin_mg": [0.25, 0.59, 3.7],
            "Niacin_mg": [0.83, 2, 12],
            "VitaminB6_mg": [0.14, 0.33, 2.1],
            "FolicAcid_mg": [0.019, 0.046, 0.29],
            "VitaminB12_mg": [0.00096, 0.0023, 0.014],
            "PantothenicAcid_mg": [0.4, 0.95, 6],
            "Biotin_mg": [0.0024, 0.0057, 0.036],
            "Sodium_mg": [107, 254, 1600],
            "Potassium_mg": [227, 538, 3410],
            "Calcium_mg": [120, 284, 1800],
            "Phosphorus_mg": [120, 284, 1800],
            "Magnesium_mg": [37, 88, 555],
            "Iron_mg": [1.4, 3.4, 22],
            "Zinc_mg": [1.1, 2.6, 16],
            "Copper_mg": [0.17, 0.4, 2.6],
            "Manganese_mg": [0.34, 0.81, 5.1],
            "Selenium_mg": [0.0058, 0.014, 0.087],
        },
    },
    "TwoCal HN": {
        "volumes_mL": [100, 237, 1000],
        "nutrients": {
            "Energy_Cal": [200, 474, 2000],
            "Protein_g": [8.4, 20, 84],
            "Fat_g": [9.1, 21, 91],
            "Carbohydrate_g": [22, 52, 219],
            "Fibre_g": [0.5, 1.2, 5.0],
            "Water_g": [70, 166, 700],
            "VitaminA_IU": [527, 1249, 5273],
            "VitaminD_IU": [96, 228, 960],
            "VitaminE_IU": [7.5, 18, 75],
            "VitaminK_mg": [0.017, 0.04, 0.17],
            "VitaminC_mg": [32, 75, 316],
            "Thiamine_mg": [0.25, 0.59, 2.5],
            "Riboflavin_mg": [0.27, 0.64, 2.7],
            "Niacin_mg": [3.4, 8.1, 34],
            "VitaminB6_mg": [0.36, 0.85, 3.6],
            "FolicAcid_mg": [0.069, 0.16, 0.69],
            "VitaminB12_mg": [0.001, 0.0024, 0.01],
            "PantothenicAcid_mg": [1.7, 4, 17],
            "Biotin_mg": [0.0084, 0.02, 0.084],
            "Sodium_mg": [84, 200, 844],
            "Potassium_mg": [211, 500, 2110],
            "Calcium_mg": [137, 325, 1371],
            "Phosphorus_mg": [132, 313, 1321],
            "Magnesium_mg": [41, 98, 414],
            "Iron_mg": [2.5, 5.9, 25],
            "Zinc_mg": [2.4, 5.7, 24],
            "Manganese_mg": [0.55, 1.3, 5.5],
            "Copper_mg": [0.21, 0.5, 2.1],
            "Selenium_mg": [0.0076, 0.018, 0.076],
        },
    },
}


def per_mL_by_column(raw_values, volumes_mL):
    """Divide each printed column's value by its own volume."""
    return [v / vol for v, vol in zip(raw_values, volumes_mL)]


def relative_spread(per_mL_values):
    """(max - min) / mean of a set of per-mL figures that should all be
    the same number modulo rounding. Zero means perfect agreement; large
    means the columns describe different things."""
    mean = sum(per_mL_values) / len(per_mL_values)
    if mean == 0:
        return 0.0
    return (max(per_mL_values) - min(per_mL_values)) / mean


@pytest.fixture(scope="module")
def formulas_by_name():
    with open(FORMULAS_CSV, encoding="utf-8-sig", newline="") as f:
        return {row["name"]: row for row in csv.DictReader(f)}


def find_disagreements(volumes_mL, nutrients, tolerance=TOLERANCE):
    """Return a list of (nutrient, per_mL_values, spread) for every
    nutrient whose columns disagree by more than `tolerance`. An empty
    list means every column of this table describes the same product."""
    disagreements = []
    for nutrient, raw_values in nutrients.items():
        assert len(raw_values) == len(volumes_mL), (
            f"{nutrient} has {len(raw_values)} values for "
            f"{len(volumes_mL)} declared volumes -- a transcription error, "
            f"fix it before trusting this check"
        )
        per_mL = per_mL_by_column(raw_values, volumes_mL)
        spread = relative_spread(per_mL)
        if spread > tolerance:
            disagreements.append((nutrient, per_mL, spread))
    return disagreements


class TestMultiColumnSourcesAgreeWithThemselves:
    """The mechanised version of UNIT_CONVERSIONS.md section 1's manual
    rule. For every feed whose source PDF prints more than one volume
    column, every nutrient's per-mL figure must agree across columns --
    disagreement means the columns describe two different products (as
    happened with the 2024 Abbott guide's can vs. ready-to-hang SKUs),
    not one product at two serving sizes."""

    @pytest.mark.parametrize("feed_name", sorted(SOURCE_TABLES))
    def test_columns_agree(self, feed_name):
        table = SOURCE_TABLES[feed_name]
        disagreements = find_disagreements(table["volumes_mL"], table["nutrients"])
        if disagreements:
            lines = [
                f"  {nutrient}: per-mL {['%.6g' % v for v in per_mL]} "
                f"from columns {table['volumes_mL']} mL -- spread {spread:.1%}"
                for nutrient, per_mL, spread in disagreements
            ]
            pytest.fail(
                f"{feed_name}: {len(disagreements)} nutrient(s) disagree by more "
                f"than {TOLERANCE:.0%} across the source PDF's own columns -- this "
                f"is the exact failure mode that put wrong vitamin/mineral values "
                f"into formulas.csv in 2026-08 (see UNIT_CONVERSIONS.md section 1). "
                f"Do not average or pick a column: STOP and re-check the PDF, or "
                f"confirm with the manufacturer which figure is right.\n" + "\n".join(lines)
            )


class TestCheckerHasTeeth:
    """Proves find_disagreements() actually rejects inconsistent data,
    rather than being a check that can never fail. Uses a synthetic
    two-SKU-style mix-up: one nutrient reported consistently, and one
    reported from two different products (a >2x per-mL disagreement --
    smaller than several of the real 2024 Abbott gaps, e.g. biotin's
    ~19x, but far above the 10% rounding-noise ceiling)."""

    def test_detects_a_synthetic_two_sku_mismatch(self):
        volumes_mL = [100, 1000]
        nutrients = {
            "Energy_Cal": [120, 1200],  # consistent: 1.2 kcal/mL either way
            "Zinc_mg": [1.1, 23.0],  # inconsistent: 0.011 vs 0.023 mg/mL
        }
        disagreements = find_disagreements(volumes_mL, nutrients)
        flagged = {d[0] for d in disagreements}
        assert flagged == {"Zinc_mg"}, (
            "the checker must flag the inconsistent nutrient and only that one -- " f"got {flagged}"
        )
        _, per_mL, spread = next(d for d in disagreements if d[0] == "Zinc_mg")
        assert spread > 0.5  # a ~71% spread, nothing close to rounding noise

    def test_passes_clean_data(self):
        """The inverse: a table where every column genuinely agrees must
        produce zero disagreements, or every real feed above would be a
        false positive."""
        volumes_mL = [100, 1000]
        nutrients = {"Sodium_mg": [107, 1070], "Potassium_mg": [239, 2390]}
        assert find_disagreements(volumes_mL, nutrients) == []


class TestFourAbbottFeedsMatchTheirNewSheets:
    """Regression test tying formulas.csv back to the October/September
    2025 Product Information Sheets that replaced the 2024 guide's
    ambiguous small-volume column for these four rows (UNIT_CONVERSIONS.md
    section 1). Recomputes each stored value from the sheet's own "per 100
    mL" column plus the documented conversion rules, and fails if
    formulas.csv drifts from its cited source -- whether from a future
    hand-edit or from reverting to the old guide's numbers."""

    FEED_ROWS = {
        # name -> (formulas.csv column, expected value, tolerance)
        "Jevity 1.2 Cal": {
            "kcal_per_mL": 1.2,
            "protein_per_mL": 0.056,
            "fat_per_mL": 0.039,
            "carbohydrate_per_mL": 0.17,
            "fibre_per_mL": 0.017,
            "sodium_per_mL": 1.07,
            "potassium_per_mL": 2.39,
            "zinc_mg_per_mL": 0.011,
            "manganese_mg_per_mL": 0.0034,
            "vitamin_a_rae_ug_per_mL": 0.72,  # 2.4 IU/mL x 0.3
            "vitamin_d_ug_per_mL": 0.016,  # 0.64 IU/mL / 40
            "vitamin_e_mg_per_mL": 0.0378,  # 0.084 IU/mL x 0.45 (DL-alpha, synthetic)
            "folate_dfe_ug_per_mL": 0.323,  # 0.19 ug/mL x 1.7
        },
        "Jevity 1.5 Cal": {
            "sodium_per_mL": 1.33,
            "potassium_per_mL": 2.18,
            "vitamin_a_rae_ug_per_mL": 0.9,
            "vitamin_e_mg_per_mL": 0.054,
        },
        "Osmolite 1.2 Cal": {
            "sodium_per_mL": 1.07,
            "potassium_per_mL": 2.27,
            "vitamin_e_mg_per_mL": 0.04005,
        },
        "TwoCal HN": {
            "sodium_per_mL": 0.84,
            "potassium_per_mL": 2.11,
            "vitamin_a_rae_ug_per_mL": 1.581,
            "folate_dfe_ug_per_mL": 1.173,
        },
    }

    @pytest.mark.parametrize("feed_name", sorted(FEED_ROWS))
    def test_stored_values_match_the_new_sheet(self, feed_name, formulas_by_name):
        row = formulas_by_name[feed_name]
        for column, expected in self.FEED_ROWS[feed_name].items():
            actual = row[column]
            assert actual != "", f"{feed_name}.{column} is blank, expected {expected}"
            assert float(actual) == pytest.approx(expected, rel=1e-6), (
                f"{feed_name}.{column} = {actual}, expected {expected} from the "
                f"October/September 2025 Product Information Sheet"
            )

    @pytest.mark.parametrize("feed_name", sorted(FEED_ROWS))
    def test_source_column_cites_the_new_sheet_not_the_2024_guide(
        self, feed_name, formulas_by_name
    ):
        source = formulas_by_name[feed_name]["source"]
        assert (
            "2024_abbott-adult-product-guide.pdf" not in source
        ), f"{feed_name}'s source still cites the superseded 2024 guide: {source!r}"
        assert "Product Information Sheet" in source or "Product_Information_Sheet" in source
