"""
build_parquet.py — One-time script: convert CNF CSVs → Parquet for fast reload.

Phase 2 of the Blenderized Tube Feed Calculator — REFERENCE SOLUTION (bug-free).

Why Parquet?
  CSV is text; Parquet is columnar binary. Loading 565k rows of
  Nutrient_Amount from Parquet is ~20× faster than from CSV.

Usage:
  python src/build_parquet.py

Output:
  data/processed/*.parquet  (gitignored — regenerable from raw CSVs anytime)
"""

from pathlib import Path
import pandas as pd

# Resolve paths relative to this file
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CNF_DIR = PROJECT_ROOT / "cnf_fcen_all-files-data_2026"
PARQUET_DIR = PROJECT_ROOT / "data" / "processed"

# Map: parquet filename → CSV filename
TABLES = {
    "food_name.parquet": "Food_Name.csv",
    "nutrient_name.parquet": "Nutrient_Name.csv",
    "nutrient_amount.parquet": "Nutrient_Amount.csv",
    "measure_name.parquet": "Measure_Name.csv",
    "measure_type.parquet": "Measure_Type.csv",
    "measure_weight_conversion.parquet": "Measure_Weight_Conversion.csv",
    "food_group.parquet": "CNF_Food_Group.csv",
}


def build_parquet(cnf_dir: Path = CNF_DIR, out_dir: Path = PARQUET_DIR) -> None:
    """Read each CNF CSV and write a Parquet file to data/processed/.

    Uses index=False because the CSVs have no meaningful index column —
    writing the default RangeIndex would add a useless '__index_level_0__'
    column to the Parquet file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    for parquet_name, csv_name in TABLES.items():
        csv_path = cnf_dir / csv_name
        out_path = out_dir / parquet_name

        print(f"Reading {csv_name} ...")
        # All CNF CSVs use utf-8-sig to handle the BOM in some files
        df = pd.read_csv(csv_path, encoding="utf-8-sig")

        df.to_parquet(out_path, index=False)
        print(f"  → wrote {out_path} ({df.shape[0]} rows × {df.shape[1]} cols)")


def load_parquet(name: str, parquet_dir: Path = PARQUET_DIR) -> pd.DataFrame:
    """Load a single Parquet table by short name (e.g. 'food_name').

    Raises FileNotFoundError if the parquet file doesn't exist yet
    (run build_parquet() first).
    """
    path = parquet_dir / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run build_parquet() first to generate it."
        )
    return pd.read_parquet(path)


def load_all_parquet(parquet_dir: Path = PARQUET_DIR) -> dict[str, pd.DataFrame]:
    """Load all Parquet tables and return as a dict keyed by table name."""
    return {
        "food_name": load_parquet("food_name", parquet_dir),
        "nutrient_name": load_parquet("nutrient_name", parquet_dir),
        "nutrient_amount": load_parquet("nutrient_amount", parquet_dir),
        "measure_name": load_parquet("measure_name", parquet_dir),
        "measure_type": load_parquet("measure_type", parquet_dir),
        "measure_weight_conversion": load_parquet(
            "measure_weight_conversion", parquet_dir
        ),
        "food_group": load_parquet("food_group", parquet_dir),
    }


if __name__ == "__main__":
    build_parquet()
    print("\n✅ All Parquet files built. Verifying...")
    tables = load_all_parquet()
    for name, df in tables.items():
        print(f"  {name}: {df.shape[0]} rows × {df.shape[1]} cols")