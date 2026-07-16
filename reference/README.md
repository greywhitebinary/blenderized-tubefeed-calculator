# reference/ — Bug-free reference solutions

> **Note:** The scaffold-and-fix learning workflow this folder supports is
> retired for the AI Masters Vibecoding Challenge (the project is now on the
> competition's 4-week plan — see `CONTEXT.md` §2 and §7). The folder is
> kept as-is in case the author returns to the learning project later; no
> new phases will be added to it for the competition build.

This folder contains **correct, working versions** of each module, organized
by phase. Use these to:

1. **Compare** against your own fixes after completing the scaffold-and-fix
   exercise for each phase.
2. **Unblock** yourself if you've been stuck for a long time and just want
   to see the answer (but try first!).
3. **Verify** that a phase works end-to-end before moving to the next.

## Structure

```
reference/
├── __init__.py
├── data_loader.py      ← Phase 2 reference (bug-free)
├── build_parquet.py    ← Phase 2 reference (bug-free)
└── ...                 ← future phases added here
```

## How to use

### Compare your fix to the reference

```bash
# After you've fixed src/data_loader.py, diff it against the reference:
diff src/data_loader.py reference/data_loader.py
```

### Run the reference directly

```bash
python reference/data_loader.py
```

### Build Parquet from the reference

```bash
python reference/build_parquet.py
```

## ⚠️ Important

The reference files use the same `CNF_DIR` path resolution as the `src/`
versions (`parent.parent`), since both `src/` and `reference/` are at the
project root level. You can safely copy reference code into `src/` without
adjusting paths.

## Phase inventory

| Phase | Module | Status |
|-------|--------|--------|
| 2 | `data_loader.py` | ✅ Available |
| 2 | `build_parquet.py` | ✅ Available |
| 3 | `models.py` + `calculator.py` | Pending |
| 4 | `measures.py` | Pending |
| 5 | `targets.py` + `report.py` | Pending |
| 6 | `streamlit_app.py` | Pending |
| 7 | Polish | Pending |