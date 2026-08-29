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
    # ---- Ensure (Abbott) and Boost / MCT Oil (Nestle) oral nutritional
    # supplements added 2026-08-28. Transcribed from
    # data/packs/canada/formula_sources/2024_abbott-adult-product-guide.pdf
    # (Ensure line, pp. 7-15) and
    # data/packs/canada/formula_sources/2026_nestle-product-guide.pdf
    # (Boost line + MCT Oil, pp. 6-27). Both printed columns are
    # transcribed independently from the page, not derived from each
    # other, per the rule at the top of this file. Single-volume pages
    # (Boost CarbSmart, Boost High Protein, Boost Original, Boost
    # Protein+, Boost Soothe, MCT Oil) have only one column, so the
    # cross-column check is trivially satisfied for them; the entry is
    # still included for the audit trail.
    "Ensure Advance": {
        "volumes_mL": [100, 235],
        "nutrients": {
            "Energy_Cal": [149, 350],
            "Protein_g": [8.5, 20],
            "Fat_g": [4.7, 11],
            "Carbohydrate_g": [18.8, 44],
            "Fibre_g": [1.3, 3],
            "VitaminA_ug": [160, 375],
            "VitaminD_mcg": [0.64, 1.5],
            "VitaminE_mgTE": [1.19, 2.8],
            "VitaminC_mg": [6.4, 15],
            "Thiamine_mg": [0.14, 0.33],
            "Riboflavin_mg": [0.17, 0.41],
            "Niacin_mgNE": [4.3, 10],
            "VitaminB6_mg": [0.17, 0.41],
            "Folate_ugDFE": [43, 102],
            "VitaminB12_mcg": [0.12, 0.28],
            "PantothenicAcid_mg": [0.55, 1.3],
            "Biotin_mcg": [14.9, 35],
            "Choline_mg": [34.9, 82],
            "Sodium_mg": [110, 259],
            "Potassium_mg": [200, 470],
            "Chloride_mg": [66, 155],
            "Calcium_mg": [106, 249],
            "Phosphorus_mg": [107, 251],
            "Magnesium_mg": [28.1, 66],
            "Iron_mg": [1.11, 2.6],
            "Zinc_mg": [1.58, 3.7],
            "Iodine_mcg": [18, 42],
            "Copper_mg": [0.21, 0.5],
            "Manganese_mg": [0.47, 1.1],
            "Selenium_mcg": [5.1, 12],
            "Chromium_mcg": [4.7, 11],
            "Molybdenum_mcg": [11.1, 26],
        },
    },
    "Ensure Protein Max 30 g": {
        # Cholesterol_mg, VitaminA_ug and Folate_ugDFE are deliberately
        # OMITTED from this table, not merely close-but-passing: verified by
        # a 300dpi re-render of p.8, the guide itself prints
        # Cholesterol 6.1 mg (100 mL) / 25 mg (330 mL), Vitamin A 81.8 mcg RE
        # (100 mL) / 300 mcg RE (330 mL), and Folic Acid 18.2 mcg DFE
        # (100 mL) / 100 mcg DFE (330 mL) -- none of which scale consistently
        # (a factor of 3.3x would put the 330 mL column at ~20.1, ~270 and
        # ~60 respectively, not 25/300/100). This is the guide's own
        # printing, not a transcription slip, so it is left out of the
        # cross-column check rather than faked into agreement, and
        # formulas.csv leaves vitamin_a_rae_ug_per_mL, retinol_ug_per_mL and
        # folate_dfe_ug_per_mL blank for this feed for the same reason
        # (2026-08-28; cholesterol isn't a tracked CSV column either way).
        "volumes_mL": [100, 330],
        "nutrients": {
            "Energy_Cal": [45.5, 150],
            "Protein_g": [9.09, 30],
            "Fat_g": [0.45, 1.5],
            "Carbohydrate_g": [1.82, 6],
            "Fibre_g": [0.61, 2],
            "Sugars_g": [0.3, 1],
            "VitaminD_mcg": [4.24, 14.0],
            "VitaminE_mg": [1.7, 5.5],
            "VitaminK_mcg": [9.09, 30.0],
            "VitaminC_mg": [13.6, 45.0],
            "Thiamine_mg": [0.09, 0.3],
            "Riboflavin_mg": [0.098, 0.35],
            "Niacin_mg": [2.42, 8.0],
            "VitaminB6_mg": [0.13, 0.45],
            "VitaminB12_mcg": [0.179, 0.6],
            "PantothenicAcid_mg": [0.379, 1.3],
            "Biotin_mcg": [2.3, 7.5],
            "Choline_mg": [25.0, 80.0],
            "Sodium_mg": [42.4, 140],
            "Potassium_mg": [142, 450],
            "Chloride_mg": [68.5, 225],
            "Calcium_mg": [197, 600],
            "Phosphorus_mg": [152, 500],
            "Magnesium_mg": [31.8, 110],
            "Iron_mg": [1.36, 4.5],
            "Zinc_mg": [0.83, 2.5],
            "Iodine_mcg": [12.0, 40],
            "Copper_mg": [0.068, 0.22],
            "Manganese_mg": [0.176, 0.6],
            "Selenium_mcg": [4.18, 14.0],
            "Chromium_mcg": [2.65, 8.5],
            "Molybdenum_mcg": [3.42, 11.5],
        },
    },
    "Ensure Compact": {
        "volumes_mL": [100, 118],
        "nutrients": {
            "Energy_Cal": [185, 218],
            "Protein_g": [7.6, 9.0],
            "Fat_g": [5.1, 6.0],
            "Carbohydrate_g": [27, 32],
            "VitaminA_IU": [420, 497],
            "VitaminD_IU": [68, 80],
            "VitaminE_IU": [9.5, 11],
            "VitaminK_mg": [0.015, 0.018],
            "VitaminC_mg": [39, 46],
            "Thiamine_mg": [0.32, 0.38],
            "Riboflavin_mg": [0.4, 0.47],
            "Niacin_mg": [2.2, 2.6],
            "VitaminB6_mg": [0.46, 0.54],
            "FolicAcid_mg": [0.055, 0.065],
            "VitaminB12_mg": [0.0006, 0.00071],
            "PantothenicAcid_mg": [1.5, 1.8],
            "Biotin_mg": [0.01, 0.012],
            "Choline_mg": [101, 119],
            "Sodium_mg": [137, 162],
            "Potassium_mg": [279, 330],
            "Chloride_mg": [156, 185],
            "Calcium_mg": [276, 326],
            "Phosphorus_mg": [159, 188],
            "Magnesium_mg": [36, 43],
            "Iron_mg": [3.8, 4.5],
            "Zinc_mg": [2.2, 2.6],
            "Iodine_mg": [0.032, 0.038],
            "Copper_mg": [0.27, 0.32],
            "Manganese_mg": [0.64, 0.76],
            "Selenium_mg": [0.012, 0.014],
            "Chromium_mg": [0.009, 0.011],
            "Molybdenum_mg": [0.016, 0.019],
        },
    },
    "Ensure Regular": {
        "volumes_mL": [100, 235],
        "nutrients": {
            "Energy_Cal": [100, 240],
            "Protein_g": [3.79, 9],
            "Fat_g": [2.54, 6],
            "Carbohydrate_g": [15.32, 36],
            "Fibre_g": [0, 0],
            "Sugars_g": [7.6, 18],
            "VitaminA_ug": [95, 240],
            "VitaminD_mcg": [2.11, 5],
            "VitaminE_mg": [3.2, 7.5],
            "VitaminK_mcg": [10.1, 24],
            "VitaminC_mg": [19, 45],
            "Thiamine_mg": [0.13, 0.33],
            "Riboflavin_mg": [0.17, 0.43],
            "Niacin_mg": [2.36, 5.5],
            "VitaminB6_mg": [0.18, 0.43],
            "Folate_ugDFE": [42, 100],
            "VitaminB12_mcg": [0.25, 0.6],
            "PantothenicAcid_mg": [0.63, 1.5],
            "Biotin_mcg": [3.2, 7.5],
            "Choline_mg": [58, 140],
            "Sodium_mg": [89, 210],
            "Potassium_mg": [198, 450],
            "Chloride_mg": [97, 225],
            "Calcium_mg": [139, 350],
            "Phosphorus_mg": [106, 250],
            "Magnesium_mg": [35.5, 80],
            "Iron_mg": [1.9, 4.5],
            "Zinc_mg": [1.39, 3.5],
            "Iodine_mcg": [16.2, 40],
            "Copper_mg": [0.09, 0.21],
            "Manganese_mg": [0.24, 0.55],
            "Selenium_mcg": [5.8, 14],
            "Chromium_mcg": [3.7, 9.4],
            "Molybdenum_mcg": [6.6, 15.5],
        },
    },
    "Ensure High Protein 16 g": {
        "volumes_mL": [100, 235],
        "nutrients": {
            "Energy_Cal": [68, 160],
            "Protein_g": [6.75, 16],
            "Fat_g": [0.84, 2.0],
            "Carbohydrate_g": [8.02, 19],
            "Sugars_g": [3.38, 7.9],
            "Fibre_g": [0.38, 0.89],
            "Cholesterol_mg": [8, 19],
            "VitaminA_ug": [95, 223],
            "VitaminD_mcg": [0.42, 1.0],
            "VitaminE_mg": [0.95, 2.2],
            "VitaminC_mg": [5.7, 13],
            "Thiamine_mg": [0.15, 0.35],
            "Riboflavin_mg": [0.16, 0.38],
            "Niacin_mgNE": [2.36, 5.6],
            "VitaminB6_mg": [0.14, 0.33],
            "Folate_ugDFE": [30, 71],
            "VitaminB12_mcg": [0.14, 0.33],
            "Biotin_mcg": [11.5, 27],
            "PantothenicAcid_mg": [0.55, 1.3],
            "Choline_mg": [58.0, 136],
            "Sodium_mg": [87, 204],
            "Potassium_mg": [198, 465],
            "Chloride_mg": [88, 207],
            "Calcium_mg": [138, 324],
            "Phosphorus_mg": [79, 186],
            "Magnesium_mg": [17.7, 42],
            "Iron_mg": [0.76, 1.8],
            "Zinc_mg": [1.18, 2.8],
            "Copper_mg": [0.11, 0.26],
            "Manganese_mg": [0.39, 0.92],
            "Selenium_mcg": [2.3, 5.4],
            "Chromium_mcg": [3.0, 7.1],
            "Molybdenum_mcg": [4.8, 11],
            "Iodine_mcg": [15.8, 37],
        },
    },
    "Ensure High Protein 12 g": {
        "volumes_mL": [100, 235],
        "nutrients": {
            "Energy_Cal": [96, 225],
            "Protein_g": [5.02, 12],
            "Fat_g": [2.55, 6],
            "Carbohydrate_g": [13.2, 31],
            "VitaminA_ug": [149, 350],
            "VitaminD_mcg": [0.53, 1.3],
            "VitaminE_mg": [1.07, 2.5],
            "VitaminC_mg": [6.4, 15],
            "Thiamine_mg": [0.138, 0.32],
            "Riboflavin_mg": [0.184, 0.43],
            "Niacin_mgNE": [2.55, 6],
            "VitaminB6_mg": [0.2, 0.47],
            "Folate_ugDFE": [43, 101],
            "VitaminB12_mcg": [0.21, 0.49],
            "PantothenicAcid_mg": [0.74, 1.7],
            "Biotin_mcg": [14.9, 35],
            "Sodium_mg": [123, 289],
            "Potassium_mg": [182, 428],
            "Chloride_mg": [107, 251],
            "Calcium_mg": [117, 275],
            "Phosphorus_mg": [117, 275],
            "Magnesium_mg": [27.7, 65],
            "Iron_mg": [1.49, 3.5],
            "Zinc_mg": [1.7, 4],
            "Iodine_mcg": [17, 40],
            "Copper_mg": [0.21, 0.5],
            "Manganese_mg": [0.55, 1.3],
            "Selenium_mcg": [5.1, 12],
            "Chromium_mcg": [4.3, 10],
            "Molybdenum_mcg": [11.9, 28],
        },
    },
    "Ensure Plus Calories": {
        # VitaminA_ug is deliberately OMITTED: verified by a 300dpi re-render
        # of p.13, the guide itself prints Vitamin A 95 mcg (100 mL) / 200 mcg
        # (235 mL), a 2.35x scale-up would put the 235 mL column at ~223, not
        # 200 -- an 11% gap, the guide's own printing rather than a
        # transcription slip. formulas.csv leaves vitamin_a_rae_ug_per_mL and
        # retinol_ug_per_mL blank for this feed for the same reason
        # (2026-08-28).
        "volumes_mL": [100, 235],
        "nutrients": {
            "Energy_Cal": [148, 350],
            "Protein_g": [5.5, 13],
            "Fat_g": [4.64, 11],
            "Carbohydrate_g": [21.1, 50],
            "Fibre_g": [0, 0],
            "Sugars_g": [8.44, 20],
            "Cholesterol_mg": [4, 10],
            "VitaminD_mcg": [3.38, 8],
            "VitaminE_mg": [3.16, 7.5],
            "VitaminK_mcg": [10.1, 24],
            "VitaminC_mg": [19.0, 45],
            "Thiamine_mg": [0.13, 0.3],
            "Riboflavin_mg": [0.14, 0.35],
            "Niacin_mg": [2.9, 7.0],
            "VitaminB6_mg": [0.18, 0.45],
            "Folate_ugDFE": [42, 100],
            "VitaminB12_mcg": [0.25, 0.6],
            "PantothenicAcid_mg": [0.53, 1.2],
            "Biotin_mcg": [3.2, 7.5],
            "Choline_mg": [58.0, 140],
            "Sodium_mg": [89, 210],
            "Potassium_mg": [198, 450],
            "Chloride_mg": [97, 225],
            "Calcium_mg": [139, 350],
            "Phosphorus_mg": [79, 175],
            "Magnesium_mg": [35.4, 80],
            "Iron_mg": [1.9, 4.5],
            "Zinc_mg": [1.39, 3.5],
            "Iodine_mcg": [15.8, 35],
            "Copper_mg": [0.09, 0.23],
            "Manganese_mg": [0.24, 0.6],
            "Selenium_mcg": [5.8, 14],
            "Chromium_mcg": [3.7, 8.5],
            "Molybdenum_mcg": [4.8, 11],
        },
    },
    "Ensure Plus": {
        "volumes_mL": [100, 235],
        "nutrients": {
            "Energy_Cal": [151, 355],
            "Protein_g": [5.66, 13],
            "Fat_g": [4.04, 9.5],
            "Carbohydrate_g": [23, 54],
            "VitaminA_IU": [532, 1250],
            "VitaminD_IU": [26, 61],
            "VitaminE_IU": [1.7, 4.0],
            "VitaminC_mg": [6.4, 15.0],
            "Thiamine_mcg": [138, 324],
            "Riboflavin_mcg": [181, 425],
            "Niacin_mgNE": [2.56, 6.01],
            "VitaminB6_mg": [0.21, 0.49],
            "FolicAcid_mcg": [26, 61],
            "VitaminB12_mcg": [0.21, 0.49],
            "PantothenicAcid_mg": [0.74, 1.74],
            "Biotin_mg": [0.0149, 0.035],
            "Sodium_mg": [107, 251],
            "Potassium_mg": [196, 461],
            "Chloride_mg": [164, 385],
            "Calcium_mg": [128, 301],
            "Phosphorus_mg": [117, 275],
            "Magnesium_mg": [27.7, 65.1],
            "Iron_mg": [1.62, 3.81],
            "Zinc_mg": [1.7, 4.0],
            "Iodine_mcg": [17.1, 40.2],
            "Copper_mg": [0.213, 0.5],
            "Manganese_mg": [0.55, 1.3],
            "Selenium_mcg": [5.5, 13],
            "Chromium_mcg": [4.7, 11],
            "Molybdenum_mcg": [11.9, 28],
        },
    },
    "Ensure Clear": {
        # VitaminA_ug and Calcium_mg are deliberately OMITTED: verified by a
        # 300dpi re-render of p.15, the guide itself prints Vitamin A 95 mcg
        # (100 mL) / 250 mcg (237 mL) and Calcium 14.8 mg (100 mL) / 40 mg
        # (237 mL); a 2.37x scale-up would put the 237 mL column at ~225 and
        # ~35, not 250/40 -- the guide's own printing rather than a
        # transcription slip. formulas.csv leaves vitamin_a_rae_ug_per_mL,
        # retinol_ug_per_mL and calcium_per_mL blank for this feed for the
        # same reason (2026-08-28).
        "volumes_mL": [100, 237],
        "nutrients": {
            "Energy_Cal": [101, 240],
            "Protein_g": [3.38, 8],
            "Fat_g": [0, 0],
            "Carbohydrate_g": [21.94, 52],
            "Fibre_g": [0, 0],
            "Sugars_g": [12.66, 30],
            "Cholesterol_mg": [2, 5],
            "VitaminD_mcg": [1.69, 4],
            "VitaminE_mg": [0.9, 2.25],
            "VitaminK_mcg": [7.6, 18],
            "VitaminC_mg": [11.4, 27],
            "Thiamine_mg": [0.14, 0.35],
            "Riboflavin_mg": [0.18, 0.45],
            "Niacin_mg": [1.69, 4],
            "VitaminB6_mg": [0.18, 0.4],
            "Folate_ugDFE": [42, 100],
            "VitaminB12_mcg": [0.25, 0.6],
            "PantothenicAcid_mg": [0.32, 0.8],
            "Biotin_mcg": [1.9, 4.5],
            "Sodium_mg": [30, 70],
            "Potassium_mg": [12.7, 30],
            "Phosphorus_mg": [90, 225],
            "Iron_mg": [1.14, 2.5],
            "Magnesium_mg": [3.6, 8],
            "Zinc_mg": [1.39, 3.5],
            "Iodine_mcg": [19, 45],
            "Copper_mg": [0.06, 0.14],
            "Manganese_mg": [0.1, 0.225],
            "Selenium_mcg": [4, 10],
            "Chromium_mcg": [1.5, 3.5],
            "Molybdenum_mcg": [1.9, 4.5],
        },
    },
    "Boost CarbSmart": {
        "volumes_mL": [237],
        "nutrients": {
            "Energy_Cal": [190],
            "Protein_g": [16],
            "Fat_g": [7],
            "Carbohydrate_g": [17],
            "Fibre_g": [3],
            "Sugars_g": [0.5],
            "VitaminA_ug": [210],
            "VitaminD_mcg": [0.9],
            "VitaminE_mg": [2.1],
            "VitaminC_mg": [10.6],
            "Thiamine_mg": [0.3],
            "Riboflavin_mg": [0.38],
            "Niacin_mg": [6.3],
            "PantothenicAcid_mg": [1.3],
            "VitaminB6_mg": [0.38],
            "Biotin_mcg": [25.5],
            "Folate_ugDFE": [106],
            "VitaminB12_mcg": [0.21],
            "Sodium_mg": [125],
            "Potassium_mg": [350],
            "Chloride_mg": [115],
            "Calcium_mg": [280],
            "Phosphorus_mg": [260],
            "Magnesium_mg": [54],
            "Iron_mg": [2.5],
            "Zinc_mg": [3],
            "Manganese_mg": [0.95],
            "Copper_mg": [0.32],
            "Iodine_mcg": [50],
            "Selenium_mcg": [4],
            "Molybdenum_mcg": [8],
            "Chromium_mcg": [0.2],
        },
    },
    "Boost Fruit Flavoured": {
        "volumes_mL": [100, 237],
        "nutrients": {
            "Energy_Cal": [76, 180],
            "Protein_g": [3.8, 9],
            "Fat_g": [0.21, 0.5],
            "Carbohydrate_g": [15, 36],
            "Sugars_g": [15, 36],
            "VitaminA_IU": [191, 453],
            "VitaminD_IU": [21, 50],
            "VitaminE_IU": [2.4, 5.7],
            "VitaminK_mg": [0.0038, 0.009],
            "VitaminC_mg": [16, 37.5],
            "Thiamine_mg": [0.16, 0.38],
            "Riboflavin_mg": [0.18, 0.43],
            "Niacin_mg": [2.1, 5],
            "PantothenicAcid_mg": [0.53, 1.25],
            "VitaminB6_mg": [0.21, 0.5],
            "Biotin_mg": [0.016, 0.038],
            "FolicAcid_mg": [0.021, 0.05],
            "VitaminB12_mg": [0.00063, 0.0015],
            "Choline_mg": [55, 130],
            "Sodium_mg": [6.3, 15],
            "Potassium_mg": [15, 35],
            "Chloride_mg": [25, 60],
            "Calcium_mg": [33, 79],
            "Phosphorus_mg": [84, 200],
            "Magnesium_mg": [17, 40],
            "Iron_mg": [0.95, 2.25],
            "Zinc_mg": [1.6, 3.75],
            "Manganese_mg": [0.21, 0.5],
            "Copper_mg": [0.11, 0.25],
            "Iodine_mg": [0.0084, 0.02],
        },
    },
    "Boost High Protein": {
        "volumes_mL": [237],
        "nutrients": {
            "Energy_Cal": [240],
            "Protein_g": [15],
            "Fat_g": [5],
            "Carbohydrate_g": [34],
            "Sugars_g": [14],
            "Cholesterol_mg": [7],
            "Sodium_mg": [250],
            "Potassium_mg": [450],
            "Chloride_mg": [400],
            "Manganese_mg": [1.2],
            "Copper_mg": [0.6],
            "Selenium_mcg": [12],
            "Molybdenum_mcg": [25],
            "Chromium_mcg": [12],
            "Biotin_mcg": [40],
            "Choline_mg": [55],
            "Calcium_mg": [370],
            "Phosphorus_mg": [300],
            "Magnesium_mg": [90],
            "Iron_mg": [4.5],
            "Zinc_mg": [4],
            "Iodine_mcg": [40],
            "VitaminA_ug": [450],
            "VitaminD_mcg": [1.5],
            "VitaminE_mg": [2.5],
            "VitaminC_mg": [15],
            "Thiamine_mg": [0.38],
            "Riboflavin_mg": [0.5],
            "Niacin_mg": [8],
            "PantothenicAcid_mg": [1.4],
            "VitaminB6_mg": [0.413],
            "Folate_ugDFE": [133],
            "VitaminB12_mcg": [0.26],
        },
    },
    "Boost Original": {
        "volumes_mL": [237],
        "nutrients": {
            "Energy_Cal": [230],
            "Protein_g": [10],
            "Fat_g": [6],
            "Carbohydrate_g": [34],
            "Sugars_g": [14],
            "Cholesterol_mg": [6.8],
            "Sodium_mg": [265],
            "Potassium_mg": [410],
            "Chloride_mg": [320],
            "Manganese_mg": [1.1],
            "Copper_mg": [0.6],
            "Selenium_mcg": [11],
            "Molybdenum_mcg": [22],
            "Chromium_mcg": [11],
            "Biotin_mcg": [30],
            "Choline_mg": [55],
            "Calcium_mg": [308],
            "Phosphorus_mg": [265],
            "Magnesium_mg": [90],
            "Iron_mg": [3.5],
            "Zinc_mg": [4.06],
            "Iodine_mcg": [40],
            "VitaminA_ug": [301],
            "VitaminD_mcg": [1.5],
            "VitaminE_mg": [2.5],
            "VitaminC_mg": [15],
            "Thiamine_mg": [0.33],
            "Riboflavin_mg": [0.43],
            "Niacin_mg": [7],
            "PantothenicAcid_mg": [1.4],
            "VitaminB6_mg": [0.415],
            "Folate_ugDFE": [107],
            "VitaminB12_mcg": [0.26],
        },
    },
    "Boost Plus Calories": {
        "volumes_mL": [100, 237],
        "nutrients": {
            "Energy_Cal": [152, 360],
            "Protein_g": [5.9, 14],
            "Fat_g": [5.9, 14],
            "Carbohydrate_g": [19, 45],
            "Fibre_g": [1.3, 3],
            "Sugars_g": [9, 22],
            "Cholesterol_mg": [4.2, 10],
            "Retinol_IU": [211, 500],
            "BetaCarotene_IU": [211, 500],
            "VitaminD_IU": [34, 80],
            "VitaminE_IU": [13, 30],
            "VitaminK_mg": [0.014, 0.032],
            "VitaminC_mg": [25, 60],
            "Thiamine_mg": [0.16, 0.38],
            "Riboflavin_mg": [0.18, 0.43],
            "Niacin_mg": [2.1, 5],
            "PantothenicAcid_mg": [1.06, 2.5],
            "VitaminB6_mg": [0.3, 0.7],
            "Biotin_mg": [0.032, 0.075],
            "FolicAcid_mg": [0.051, 0.12],
            "VitaminB12_mg": [0.0009, 0.0021],
            "Choline_mg": [23, 55],
            "Sodium_mg": [84, 200],
            "Potassium_mg": [152, 360],
            "Chloride_mg": [115, 273],
            "Calcium_mg": [148, 350],
            "Phosphorus_mg": [127, 300],
            "Magnesium_mg": [42, 100],
            "Iron_mg": [1.9, 4.5],
            "Zinc_mg": [1.9, 4.5],
            "Manganese_mg": [0.3, 0.7],
            "Copper_mg": [0.21, 0.5],
            "Iodine_mg": [0.016, 0.038],
            "Selenium_mg": [0.0076, 0.018],
            "Molybdenum_mg": [0.008, 0.019],
            "Chromium_mg": [0.013, 0.03],
        },
    },
    "Boost Protein+": {
        "volumes_mL": [325],
        "nutrients": {
            "Energy_Cal": [270],
            "Protein_g": [27],
            "Fat_g": [8],
            "Carbohydrate_g": [22],
            "Fibre_g": [2],
            "Sugars_g": [13],
            "Cholesterol_mg": [15],
            "Sodium_mg": [265],
            "Potassium_mg": [700],
            "Chloride_mg": [250],
            "Manganese_mg": [1],
            "Copper_mg": [0.55],
            "Selenium_mcg": [15],
            "Molybdenum_mcg": [25],
            "Chromium_mcg": [12],
            "Biotin_mcg": [35],
            "Choline_mg": [150],
            "Calcium_mg": [450],
            "Phosphorus_mg": [400],
            "Magnesium_mg": [100],
            "Iron_mg": [3.3],
            "Zinc_mg": [4],
            "Iodine_mcg": [40],
            "VitaminA_ug": [350],
            "VitaminD_mcg": [1.25],
            "VitaminE_mg": [3.22],
            "VitaminC_mg": [20],
            "Thiamine_mg": [0.35],
            "Riboflavin_mg": [0.5],
            "Niacin_mg": [6.6],
            "PantothenicAcid_mg": [1.3],
            "VitaminB6_mg": [0.45],
            "Folate_ugDFE": [116.7],
            "VitaminB12_mcg": [0.3],
        },
    },
    "Boost Soothe": {
        "volumes_mL": [237],
        "nutrients": {
            "Energy_Cal": [300],
            "Protein_g": [10],
            "Fat_g": [0],
            "Carbohydrate_g": [65],
            "Sugars_g": [15],
            "Cholesterol_mg": [5],
            "Sodium_mg": [0],
        },
    },
    "Boost 1.5": {
        "volumes_mL": [100, 237],
        "nutrients": {
            "Energy_Cal": [152, 360],
            "Protein_g": [5.5, 13],
            "Fat_g": [4.6, 11],
            "Carbohydrate_g": [22, 52],
            "VitaminA_IU": [450, 1067],
            "VitaminD_IU": [42, 100],
            "VitaminE_IU": [3.2, 7.5],
            "VitaminK_mg": [0.0084, 0.02],
            "VitaminC_mg": [15, 36],
            "Thiamine_mg": [0.25, 0.6],
            "Riboflavin_mg": [0.29, 0.68],
            "Niacin_mg": [3.4, 8],
            "PantothenicAcid_mg": [1.1, 2.5],
            "VitaminB6_mg": [0.34, 0.8],
            "Biotin_mg": [0.032, 0.075],
            "FolicAcid_mg": [0.042, 0.1],
            "VitaminB12_mg": [0.001, 0.0024],
            "Choline_mg": [42, 100],
            "Sodium_mg": [131, 310],
            "Potassium_mg": [194, 460],
            "Chloride_mg": [143, 340],
            "Calcium_mg": [127, 300],
            "Phosphorus_mg": [105, 250],
            "Magnesium_mg": [42, 100],
            "Iron_mg": [1.9, 4.5],
            "Zinc_mg": [2.5, 6],
            "Manganese_mg": [0.21, 0.5],
            "Copper_mg": [0.21, 0.5],
            "Iodine_mg": [0.016, 0.038],
            "Selenium_mg": [0.0076, 0.018],
            "Molybdenum_mg": [0.008, 0.019],
            "Chromium_mg": [0.013, 0.03],
        },
    },
    "Boost 2.24": {
        "volumes_mL": [100, 237],
        "nutrients": {
            "Energy_Cal": [224, 530],
            "Protein_g": [9.3, 22],
            "Fat_g": [11, 26],
            "Carbohydrate_g": [22, 52],
            "Sugars_g": [5.5, 13],
            "VitaminA_IU": [730, 1730],
            "VitaminD_IU": [202, 480],
            "VitaminE_IU": [4.7, 11],
            "VitaminK_mg": [0.025, 0.06],
            "VitaminC_mg": [25, 60],
            "Thiamine_mg": [0.21, 0.5],
            "Riboflavin_mg": [0.25, 0.6],
            "Niacin_mg": [3.4, 8],
            "PantothenicAcid_mg": [1.05, 2.5],
            "VitaminB6_mg": [0.34, 0.8],
            "Biotin_mg": [0.006, 0.015],
            "FolicAcid_mg": [0.05, 0.12],
            "VitaminB12_mg": [0.0005, 0.0012],
            "Choline_mg": [46, 110],
            "Sodium_mg": [118, 280],
            "Potassium_mg": [177, 420],
            "Chloride_mg": [127, 300],
            "Calcium_mg": [105, 250],
            "Phosphorus_mg": [105, 250],
            "Magnesium_mg": [34, 80],
            "Iron_mg": [2.7, 6.3],
            "Zinc_mg": [2.3, 5.5],
            "Manganese_mg": [0.46, 1.1],
            "Copper_mg": [0.22, 0.53],
            "Iodine_mg": [0.025, 0.06],
            "Selenium_mg": [0.012, 0.028],
            "Molybdenum_mg": [0.01, 0.023],
            "Chromium_mg": [0.008, 0.018],
        },
    },
    # MCT Oil prints TWO energy figures that disagree by 4%: the Nutrition
    # Facts panel's 80 Cal per 10 mL (transcribed below) and the Features
    # at a Glance row's "Caloric density 7.7 Cal/ml". formulas.csv stores
    # 7.7, not 8.0. Canadian labelling rounds calories to the nearest 10
    # above 50, so on a 10 mL serving the panel figure carries barely one
    # significant figure, while 7.7 reconciles with the chemistry (MCT is
    # ~8.3 kcal/g at ~0.93 g/mL, giving 7.7 kcal/mL). Section 1's "take the
    # column with more significant figures" is the same preference applied
    # to a product whose only serving size is tiny.
    "MCT Oil": {
        "volumes_mL": [10],
        "nutrients": {
            "Energy_Cal": [80],
            "Fat_g": [9],
            "Carbohydrate_g": [0],
            "Protein_g": [0],
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
