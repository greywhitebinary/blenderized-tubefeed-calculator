# Phase 2 Spec — `data_loader.py` + `build_parquet.py`

> **Scaffold-and-fix exercise.** The code in `src/data_loader.py` and
> `src/build_parquet.py` has been scaffolded with **5 deliberate bugs**.
> Fix them one at a time, re-running the verification after each fix.
> When stuck >20 min, ask for a *hint* (not the answer).

---

## What these modules do

### `data_loader.py`
Loads each CNF CSV into a pandas DataFrame. Each function returns one table.
`load_all()` returns a dict of all 7 tables. This is the foundation — every
later module (`calculator.py`, `measures.py`, `report.py`) will call these
functions.

### `build_parquet.py`
One-time script that reads all CNF CSVs and writes them as Parquet files to
`data/processed/`. Also provides `load_parquet()` / `load_all_parquet()` for
fast reloading (~20× faster than CSV).

---

## Inputs & outputs

| Function | Input | Output |
|----------|-------|--------|
| `load_food_name()` | `Food_Name.csv` | DataFrame, `Food_Code` as a regular column |
| `load_nutrient_name()` | `Nutrient_Name.csv` | DataFrame, `Nutrient_Code` as a regular column |
| `load_nutrient_amount()` | `Nutrient_Amount.csv` | DataFrame, ~565k rows |
| `load_measure_name()` | `Measure_Name.csv` | DataFrame |
| `load_measure_type()` | `Measure_Type.csv` | DataFrame, 3 rows |
| `load_measure_weight_conversion()` | `Measure_Weight_Conversion.csv` | DataFrame, ~30k rows |
| `load_food_group()` | `CNF_Food_Group.csv` | DataFrame, 23 rows |
| `load_all()` | — | `dict[str, pd.DataFrame]` |
| `build_parquet()` | CNF CSVs | `data/processed/*.parquet` |
| `load_parquet(name)` | Parquet file | DataFrame |

---

## CNF columns to use (quick reference)

```
Food_Name:        Food_Code, Food_Description_EN, CNF_Food_Group_Code, ...
Nutrient_Name:    Nutrient_Code, Nutrient_Name_EN, Nutrient_Unit, Tagname
Nutrient_Amount:  Food_Code, Nutrient_Code, Nutrient_Amount
Measure_Name:     Measure_Code, Measure_Description_and_Unit_EN
Measure_Type:     Measure_Type_Code, Measure_Type_Description_EN
Measure_Weight:   Food_Code, Measure_Type_Code, Measure_Code, Measure_Weight_Conversion
CNF_Food_Group:   CNF_Food_Group_Code, CNF_Food_Group_Description_EN
```

---

## Edge cases to think about

1. **BOM (Byte Order Mark):** Several CNF CSVs start with a UTF-8 BOM
   (`\ufeff`). If you read with plain `encoding="utf-8"`, the first column
   name becomes `\ufeffNutrient_Code` instead of `Nutrient_Code` — and every
   later merge on `"Nutrient_Code"` will silently fail (no matching column).
   The fix is `encoding="utf-8-sig"` which strips the BOM.

2. **Index vs. column:** `pd.read_csv(..., index_col=0)` sets the first
   column as the DataFrame *index* (row labels), not a regular column. This
   is fine for lookups but means you can't `merge(on="Food_Code")` later
   unless you `.reset_index()` first. For this project, we want `Food_Code`
   as a regular column so merges work naturally.

3. **Separator:** CNF CSVs are comma-separated. Using the wrong `sep=`
   argument will produce a single giant column with everything jammed together.

4. **Filename typos:** Python won't catch a misspelled filename until runtime
   — `FileNotFoundError` is your clue.

5. **Parquet index:** `df.to_parquet(path, index=True)` writes the DataFrame's
   index as an extra column. If the index is just a default RangeIndex
   (0, 1, 2, ...), this adds a useless column that pollutes the data.

---

## Hint list — bug categories (no answers!)

There are **5 bugs** across the two files. Here are the categories:

| # | File               | Category                  | Difficulty |
|---|--------------------|---------------------------|------------|
| 1 | `data_loader.py`   | Encoding / BOM            | Easy       |
| 2 | `data_loader.py`   | Encoding / BOM            | Easy       |
| 3 | `data_loader.py`   | Filename typo             | Easy       |
| 4 | `data_loader.py`   | Wrong parameter value     | Medium     |
| 5 | `data_loader.py`   | Index vs. column (pandas) | Medium     |
| 6 | `build_parquet.py` | Unwanted index in output  | Subtle     |

> Wait — that's 6 rows but only 5 bugs. One of those categories is a
> *red herring* (already correct). You'll have to figure out which.

---

## Verification step

After fixing all bugs, run this command from the project root:

```bash
python src/data_loader.py
```

**Expected output** (row counts may vary slightly from the CNF docs):

```
food_name: 5993 rows × 11 cols
  columns: ['Food_Description_EN', 'Food_Description_FR', 'Alternate_Description_EN', 'Alternate_Description_FR', 'Food_Source_Code', 'USDA_NDB_Code', 'CNF_Food_Group_Code', 'Comment_EN', 'Comment_FR', 'ScientificName', 'Food_Last_Updated_Date']

nutrient_name: 173 rows × 6 cols
  columns: ['Nutrient_Symbol', 'Nutrient_Unit', 'Nutrient_Name_EN', 'Nutrient_Name_FR', 'Tagname', 'Nutrient_Decimals']

nutrient_amount: 565409 rows × 6 cols
  columns: ['Food_Code', 'Nutrient_Code', 'Nutrient_Amount', 'STD_Error', 'Observations', 'Nutrient_Source_Code', 'Nutrient_Last_Updated_Date']

measure_name: 1496 rows × 2 cols
  columns: ['Measure_Description_and_Unit_EN', 'Measure_Description_and_Unit_FR']

measure_type: 3 rows × 2 cols
  columns: ['Measure_Type_Description_EN', 'Measure_Type_Description_FR']

measure_weight_conversion: 29868 rows × 4 cols
  columns: ['Food_Code', 'Measure_Type_Code', 'Measure_Code', 'Measure_Weight_Conversion', 'Measure_Weight_Conversion_Last_Updated_Date']

food_group: 23 rows × 2 cols
  columns: ['CNF_Food_Group_Description_EN', 'CNF_Food_Group_Description_FR']
```

### Key checks to look for:

1. **No `\ufeff` in any column name** — if you see `\ufeffNutrient_Code`,
   you have a BOM bug.
2. **`Food_Code` is a column, not the index** — `food_name.columns` should
   include `Food_Description_EN` etc. but NOT `Food_Code` as the index.
   Wait — actually `Food_Code` should appear as a regular column. If
   `df.index.name == "Food_Code"`, that's the index bug.
3. **`measure_type` loads successfully** — if you get `FileNotFoundError`,
   check the filename spelling.
4. **`measure_weight_conversion` has 5 columns** — if it has 1 column with
   everything jammed together, check the separator.
5. **Row counts match** the CNF docs (~5,993 / ~173 / ~565,409 / etc.)

### Then test the Parquet build:

```bash
python src/build_parquet.py
```

This should create `data/processed/*.parquet` files and print verification
output with the same row counts.

### Then test the notebook:

```bash
jupyter notebook notebooks/00_explore_cnf.ipynb
```

Run all cells. The spot-check (Section 3) should show chicken foods and
their nutrient values without errors.

---

## How to approach the fixes

1. Run `python src/data_loader.py` — note which errors appear.
2. Fix **one bug at a time**, re-run after each.
3. Read the error messages carefully — `FileNotFoundError`, `KeyError`,
   `UnicodeDecodeError` are all clues.
4. Some bugs are **silent** (no error, just wrong data) — check column names
   and row counts against the expected output above.
5. When all 7 tables load with correct shapes and clean column names,
   move on to `build_parquet.py`.
6. After Parquet builds, try `load_all_parquet()` and compare row counts
   to `load_all()` — they should match.

Good luck! 🍀