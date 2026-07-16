"""
data_loader.py — Load Canadian Nutrient File (CNF) 2026 CSVs into pandas.

Phase 2 of the Blenderized Tube Feed Calculator.

Each function reads one CNF CSV and returns a cleaned DataFrame.
load_all() returns a dict of all tables for convenience.

CNF schema quick reference (all nutrient amounts are per 100 g edible food):
  Food_Name.csv                 ~5,993 rows   Food_Code (PK)
  Nutrient_Name.csv              ~173 rows   Nutrient_Code (PK)
  Nutrient_Amount.csv          ~565,409 rows  Food_Code + Nutrient_Code → amount
  Measure_Name.csv              ~1,496 rows   Measure_Code (PK)
  Measure_Type.csv                   3 rows   Measure_Type_Code (PK)
  Measure_Weight_Conversion.csv ~29,868 rows  Food_Code + Measure_Code → grams
  CNF_Food_Group.csv                23 rows   CNF_Food_Group_Code (PK)
"""

from pathlib import Path
import pandas as pd

# Default location of raw CNF CSVs (relative to this file: ../../cnf_fcen_...)
CNF_DIR = Path(__file__).resolve().parent.parent / "cnf_fcen_all-files-data_2026"


def load_food_name(data_dir: Path = CNF_DIR) -> pd.DataFrame:
    """Load Food_Name.csv — the master list of ~5,993 foods.

    Columns: Food_Code (PK), Food_Description_EN, Food_Description_FR,
    Alternate_Description_EN, Alternate_Description_FR, Food_Source_Code,
    USDA_NDB_Code, CNF_Food_Group_Code, Comment_EN, Comment_FR,
    ScientificName, Food_Last_Updated_Date

    Note: Food_Name.csv does NOT have a BOM, so plain utf-8 is fine.
    Food_Code must be a regular column (not the index) so merges work later.
    """
    df = pd.read_csv(data_dir / "Food_Name.csv")
    return df


def load_nutrient_name(data_dir: Path = CNF_DIR) -> pd.DataFrame:
    """Load Nutrient_Name.csv — the ~173 nutrient definitions.

    Columns: Nutrient_Code (PK), Nutrient_Symbol, Nutrient_Unit,
    Nutrient_Name_EN, Nutrient_Name_FR, Tagname, Nutrient_Decimals

    Note: This file HAS a BOM — must use utf-8-sig to strip it, otherwise
    the first column becomes '\\ufeffNutrient_Code' and merges silently fail.
    """
    df = pd.read_csv(data_dir / "Nutrient_Name.csv", encoding="utf-8-sig")
    return df


def load_nutrient_amount(data_dir: Path = CNF_DIR) -> pd.DataFrame:
    """Load Nutrient_Amount.csv — the big one: ~565k rows of nutrient values.

    Columns: Food_Code (FK), Nutrient_Code (FK), Nutrient_Amount,
    STD_Error, Observations, Nutrient_Source_Code, Nutrient_Last_Updated_Date

    Note: This file HAS a BOM — must use utf-8-sig.
    """
    df = pd.read_csv(data_dir / "Nutrient_Amount.csv", encoding="utf-8-sig")
    return df


def load_measure_name(data_dir: Path = CNF_DIR) -> pd.DataFrame:
    """Load Measure_Name.csv — household measure descriptions (~1,496 rows).

    Columns: Measure_Code (PK), Measure_Description_and_Unit_EN,
    Measure_Description_and_Unit_FR
    """
    df = pd.read_csv(data_dir / "Measure_Name.csv", encoding="utf-8-sig")
    return df


def load_measure_type(data_dir: Path = CNF_DIR) -> pd.DataFrame:
    """Load Measure_Type.csv — 3 rows: Refuse, User-defined, Yield.

    Columns: Measure_Type_Code (PK), Measure_Type_Description_EN,
    Measure_Type_Description_FR
    """
    df = pd.read_csv(data_dir / "Measure_Type.csv", encoding="utf-8-sig")
    return df


def load_measure_weight_conversion(data_dir: Path = CNF_DIR) -> pd.DataFrame:
    """Load Measure_Weight_Conversion.csv — food + measure → grams (~29,868 rows).

    Columns: Food_Code (FK), Measure_Type_Code, Measure_Code (FK),
    Measure_Weight_Conversion, Measure_Weight_Conversion_Last_Updated_Date

    Note: CNF CSVs are comma-separated (sep="," is the default).
    """
    df = pd.read_csv(
        data_dir / "Measure_Weight_Conversion.csv",
        encoding="utf-8-sig",
    )
    return df


def load_food_group(data_dir: Path = CNF_DIR) -> pd.DataFrame:
    """Load CNF_Food_Group.csv — 23 food group descriptions.

    Columns: CNF_Food_Group_Code (PK), CNF_Food_Group_Description_EN,
    CNF_Food_Group_Description_FR
    """
    df = pd.read_csv(data_dir / "CNF_Food_Group.csv", encoding="utf-8-sig")
    return df


def load_all(data_dir: Path = CNF_DIR) -> dict[str, pd.DataFrame]:
    """Load all CNF tables and return as a dict keyed by table name."""
    return {
        "food_name": load_food_name(data_dir),
        "nutrient_name": load_nutrient_name(data_dir),
        "nutrient_amount": load_nutrient_amount(data_dir),
        "measure_name": load_measure_name(data_dir),
        "measure_type": load_measure_type(data_dir),
        "measure_weight_conversion": load_measure_weight_conversion(data_dir),
        "food_group": load_food_group(data_dir),
    }


if __name__ == "__main__":
    # Quick smoke test when run directly
    tables = load_all()
    for name, df in tables.items():
        print(f"{name}: {df.shape[0]} rows × {df.shape[1]} cols")
        print(f"  columns: {list(df.columns)}")
        print()