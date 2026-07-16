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

Persistence (CONTEXT.md §3): each loader below checks data/processed/ for a
pre-built Parquet file first (built by build_parquet.py — ~20x faster than
CSV for the big tables) and falls back to the raw CSV if the Parquet file
isn't there yet. The fast path only applies when reading from the default
CNF_DIR — a caller-supplied data_dir (e.g. tests pointing at a fixture
folder) always reads CSV, since a Parquet cache built from the real CNF
data wouldn't match it.
"""

from pathlib import Path
import pandas as pd

# Default location of raw CNF CSVs (relative to this file: ../../cnf_fcen_...)
CNF_DIR = Path(__file__).resolve().parent.parent / "cnf_fcen_all-files-data_2026"

# Default location of pre-built Parquet tables (see build_parquet.py).
# Gitignored/regenerable — run `python src/build_parquet.py` to (re)build.
PARQUET_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def _load_table(
    csv_name: str,
    parquet_name: str,
    data_dir: Path,
    encoding: str | None = "utf-8-sig",
) -> pd.DataFrame:
    """Load one table, preferring a pre-built Parquet file over the raw CSV.

    Only attempts the Parquet fast path when data_dir is the default
    CNF_DIR — a custom data_dir means the caller wants a specific CSV
    source, and the Parquet cache (built once, from CNF_DIR) wouldn't
    necessarily match it.
    """
    if data_dir == CNF_DIR:
        parquet_path = PARQUET_DIR / parquet_name
        if parquet_path.exists():
            return pd.read_parquet(parquet_path)

    read_kwargs = {} if encoding is None else {"encoding": encoding}
    return pd.read_csv(data_dir / csv_name, **read_kwargs)


def load_food_name(data_dir: Path = CNF_DIR) -> pd.DataFrame:
    """Load Food_Name.csv — the master list of ~5,993 foods.

    Columns: Food_Code (PK), Food_Description_EN, Food_Description_FR,
    Alternate_Description_EN, Alternate_Description_FR, Food_Source_Code,
    USDA_NDB_Code, CNF_Food_Group_Code, Comment_EN, Comment_FR,
    ScientificName, Food_Last_Updated_Date

    Note: Food_Name.csv does NOT have a BOM, so plain utf-8 is fine.
    Food_Code must be a regular column (not the index) so merges work later.
    """
    return _load_table("Food_Name.csv", "food_name.parquet", data_dir, encoding=None)


def load_nutrient_name(data_dir: Path = CNF_DIR) -> pd.DataFrame:
    """Load Nutrient_Name.csv — the ~173 nutrient definitions.

    Columns: Nutrient_Code (PK), Nutrient_Symbol, Nutrient_Unit,
    Nutrient_Name_EN, Nutrient_Name_FR, Tagname, Nutrient_Decimals

    Note: This file HAS a BOM — must use utf-8-sig to strip it, otherwise
    the first column becomes '\\ufeffNutrient_Code' and merges silently fail.
    """
    return _load_table("Nutrient_Name.csv", "nutrient_name.parquet", data_dir)


def load_nutrient_amount(data_dir: Path = CNF_DIR) -> pd.DataFrame:
    """Load Nutrient_Amount.csv — the big one: ~565k rows of nutrient values.

    Columns: Food_Code (FK), Nutrient_Code (FK), Nutrient_Amount,
    STD_Error, Observations, Nutrient_Source_Code, Nutrient_Last_Updated_Date

    Note: This file HAS a BOM — must use utf-8-sig.
    """
    return _load_table("Nutrient_Amount.csv", "nutrient_amount.parquet", data_dir)


def load_measure_name(data_dir: Path = CNF_DIR) -> pd.DataFrame:
    """Load Measure_Name.csv — household measure descriptions (~1,496 rows).

    Columns: Measure_Code (PK), Measure_Description_and_Unit_EN,
    Measure_Description_and_Unit_FR
    """
    return _load_table("Measure_Name.csv", "measure_name.parquet", data_dir)


def load_measure_type(data_dir: Path = CNF_DIR) -> pd.DataFrame:
    """Load Measure_Type.csv — 3 rows: Refuse, User-defined, Yield.

    Columns: Measure_Type_Code (PK), Measure_Type_Description_EN,
    Measure_Type_Description_FR
    """
    return _load_table("Measure_Type.csv", "measure_type.parquet", data_dir)


def load_measure_weight_conversion(data_dir: Path = CNF_DIR) -> pd.DataFrame:
    """Load Measure_Weight_Conversion.csv — food + measure → grams (~29,868 rows).

    Columns: Food_Code (FK), Measure_Type_Code, Measure_Code (FK),
    Measure_Weight_Conversion, Measure_Weight_Conversion_Last_Updated_Date

    Note: CNF CSVs are comma-separated (sep="," is the default).
    """
    return _load_table(
        "Measure_Weight_Conversion.csv",
        "measure_weight_conversion.parquet",
        data_dir,
    )


def load_food_group(data_dir: Path = CNF_DIR) -> pd.DataFrame:
    """Load CNF_Food_Group.csv — 23 food group descriptions.

    Columns: CNF_Food_Group_Code (PK), CNF_Food_Group_Description_EN,
    CNF_Food_Group_Description_FR
    """
    return _load_table("CNF_Food_Group.csv", "food_group.parquet", data_dir)


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