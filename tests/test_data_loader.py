"""
test_data_loader.py — tests for src/data_loader.py's Parquet-cache fast
path, specifically the fallback to CSV when that cache is unusable.

This file does not exercise the real CNF loaders end to end (those are
covered by the integration check scripts/verify_backend.py, per
conftest.py's own reasoning) -- it pins one narrow behaviour: the Parquet
cache is a speed optimisation, never a source of truth, and a bad cache
file must never be allowed to take the app down.
"""

from src import data_loader


def test_a_corrupt_parquet_cache_falls_through_to_csv(tmp_path, monkeypatch):
    """build_parquet.py writes the cache non-atomically, so a build killed
    partway through (a deploy interrupted, a full disk) can leave a
    truncated or corrupt .parquet file sitting where a good one is
    expected. Before this fix, only ImportError was caught around
    pd.read_parquet() -- a corrupt file raised pyarrow's ArrowInvalid
    (a ValueError) straight out of _load_table() and killed app startup,
    even though the docstring already promised the cache would "fall
    through to CSV" on any read problem (2026-08-20 review).
    """
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    parquet_dir = tmp_path / "parquet"
    parquet_dir.mkdir()

    (csv_dir / "Food_Name.csv").write_text("Food_Code,Food_Description_EN\n1,Test food from CSV\n")
    # A truncated/garbage file, standing in for a cache build that never
    # finished -- real Parquet files open with a magic-bytes footer this
    # does not have.
    (parquet_dir / "food_name.parquet").write_bytes(b"not a real parquet file")

    # _load_table() only tries the fast path when data_dir IS the module's
    # CNF_DIR (a caller-supplied dir means "read this CSV, not the shared
    # cache") -- so both globals have to move together for the test to
    # exercise that branch at all.
    monkeypatch.setattr(data_loader, "CNF_DIR", csv_dir)
    monkeypatch.setattr(data_loader, "PARQUET_DIR", parquet_dir)

    df = data_loader.load_food_name(csv_dir)

    assert list(df["Food_Description_EN"]) == ["Test food from CSV"]


def test_a_missing_parquet_cache_reads_csv_as_before(tmp_path, monkeypatch):
    """Sanity check alongside the corrupt-cache test above: no cache file
    at all (the ordinary case before build_parquet.py has ever run) must
    keep reading the CSV exactly as it always has.
    """
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    parquet_dir = tmp_path / "parquet"  # deliberately never created

    (csv_dir / "Food_Name.csv").write_text("Food_Code,Food_Description_EN\n1,Test food from CSV\n")

    monkeypatch.setattr(data_loader, "CNF_DIR", csv_dir)
    monkeypatch.setattr(data_loader, "PARQUET_DIR", parquet_dir)

    df = data_loader.load_food_name(csv_dir)

    assert list(df["Food_Description_EN"]) == ["Test food from CSV"]
