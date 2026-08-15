"""
recipe_io.py — save a blend recipe to a spreadsheet, and read one back.

WHY THIS EXISTS
---------------
The calculator computes; this module *remembers*. An RD who works out a
blend that actually flows through the tube currently loses that knowledge
the moment the browser tab closes. A recipe file turns "this blend, at
this measured volume, passed the drip test" into something you can keep,
re-open in three weeks, and email to a colleague.

THE FILE
--------
One .xlsx workbook, two sheets — chosen so a single file serves both
readers without a conversion step:

  Sheet "Recipe"       one row PER BLEND: recipe id, name, measured
                       volume, flow-test date/result/notes, format
                       version.
  Sheet "Ingredients"  one row per ingredient, each tagged with the
                       recipe id and name it belongs to, then food code,
                       description, amount, unit, counts-as-fluid, and the
                       household measure it was entered/edited in (blank
                       when there isn't one).

A recipe is not a flat table — it has one set of facts about the batch
and a repeating list of ingredients — so two sheets is simply how a
person would lay it out anyway.

WHY EVERY INGREDIENT ROW REPEATS THE RECIPE NAME
------------------------------------------------
The app holds several blends at once, so a file has to be able to as
well (author, 2026-07-30: "if there is an option to add multiple BTFs...
the output should be able to provide all of these recipes"). The moment
a file holds more than one recipe, a flat ingredient list is ambiguous —
twenty rows and no way to tell which blend each belongs to.

The fix is the ordinary one for header/detail data: every ingredient row
names its parent. That makes the link explicit for the reader here, and
lets an RD sort or filter the Ingredients sheet by recipe in Excel
without needing anything from us.

Rows are matched on the numeric "Recipe id", not the name, because blend
names are free text and two blends can share one. If a multi-recipe file
somehow arrives with no usable link column at all, this module REFUSES
to load it rather than pooling the rows — silently merging two patients'
recipes into one blend is precisely the class of error this project
treats as unacceptable (FEED_LOG_REWORK.md §6.2).

FORMAT VERSIONS
---------------
v1 files (single recipe, no id columns) still load: a v1 file has one
recipe row and unlabelled ingredients, which is unambiguous, so every
ingredient is assigned to that one recipe. Nothing an RD has already
saved is orphaned by the v2 layout.

Every ingredient row carries BOTH the CNF food code and the description.
The code is what lets a file the app wrote reload with identical numbers.
The description is what makes the file readable by a human, and typeable
from scratch: leave the code blank and `resolve_ingredients()` will match
on the description instead, reporting what it found so the RD can confirm
before anything commits.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
It never silently guesses. A description that matches several CNF foods
comes back as AMBIGUOUS with the candidates attached, and one that
matches nothing comes back as UNMATCHED — both for a human to resolve.
Guessing would be the dangerous failure here: nothing errors, an RD just
gets a plausible wrong number in a clinical table. Same reasoning as the
label-photo rule in CONTEXT.md §11.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from typing import Any

import pandas as pd

# Bumped only on a breaking change to the sheet layout. Written into every
# file so a future reader can tell what it's looking at.
#   v1  single recipe per file; no id columns.
#   v2  many recipes per file; "Recipe id"/"Recipe name" link the sheets.
RECIPE_FORMAT_VERSION = 2

RECIPE_SHEET = "Recipe"
INGREDIENTS_SHEET = "Ingredients"

# The columns that tie an ingredient row to its recipe. Named here rather
# than inline because the reader has to test for their presence to tell a
# v2 file from a v1 one.
RECIPE_ID_COLUMN = "Recipe id"
RECIPE_NAME_COLUMN = "Recipe name"

# Column headers. Human-facing (they're what an RD sees in Excel), so they
# read as words rather than field names.
_RECIPE_COLUMNS = [
    RECIPE_ID_COLUMN,
    RECIPE_NAME_COLUMN,
    "Measured final volume (mL)",
    "Flow test date",
    "Flow test result",
    "Flow test notes",
    "Format version",
]
_INGREDIENT_COLUMNS = [
    # The link columns lead, so the grouping is the first thing an RD sees
    # when the sheet opens.
    RECIPE_ID_COLUMN,
    RECIPE_NAME_COLUMN,
    "CNF food code",
    "Food description",
    "Amount",
    "Unit",
    "Counts as fluid",
    # The CNF household measure this amount was entered/edited in, e.g.
    # "1 cup" and the grams in one of it -- carried through so a printed
    # recipe reads in the kitchen unit, not just grams (Change 4,
    # 2026-08-15). Blank for rows with no measure, same as every other
    # optional column here.
    "Measure label",
    "Measure grams",
]

# Per-ingredient outcomes from resolve_ingredients().
MATCH_BY_CODE = "matched_by_code"
MATCH_BY_DESCRIPTION = "matched_by_description"
AMBIGUOUS = "ambiguous"
UNMATCHED = "unmatched"


class RecipeFileError(ValueError):
    """The uploaded file isn't a recipe file we can read.

    Raised only for structural problems (missing sheet, missing column) —
    i.e. "this isn't the right kind of file at all". Problems with the
    *contents* of individual rows are reported per-row instead, so one bad
    line never costs the RD the whole upload.
    """


@dataclass
class ResolvedIngredient:
    """One ingredient row after we've tried to tie it to a CNF food.

    Attributes:
        status:           One of MATCH_BY_CODE / MATCH_BY_DESCRIPTION /
                          AMBIGUOUS / UNMATCHED.
        food_code:        The resolved CNF code, or None if unresolved.
        food_description: Description to display (from CNF where resolved,
                          else the text the RD typed).
        grams:            Amount used.
        unit:             "g" or "mL", as entered.
        counts_as_fluid:  Whether this ingredient counts toward fluid.
        measure_label:    CNF household-measure description ("1 cup"), or
                          None if this row has no measure (Change 5,
                          2026-08-15).
        measure_grams:    Grams in ONE of measure_label, or None.
        candidates:       For AMBIGUOUS rows, the (code, description)
                          options for a human to choose between.
        source_text:      What was actually in the file, kept for display
                          so the RD can see what they typed.
    """

    status: str
    food_code: int | None
    food_description: str
    grams: float
    unit: str = "g"
    counts_as_fluid: bool = False
    measure_label: str | None = None
    measure_grams: float | None = None
    candidates: list[tuple[int, str]] = field(default_factory=list)
    source_text: str = ""

    @property
    def needs_confirmation(self) -> bool:
        """True when a human must look at this row before it can be used."""
        return self.status in (AMBIGUOUS, UNMATCHED, MATCH_BY_DESCRIPTION)


@dataclass
class ParsedRecipe:
    """A recipe file read off disk, before CNF resolution.

    `row_warnings` collects per-row problems (a blank amount, an
    unreadable number) as plain sentences fit to show an RD — the row is
    skipped, the rest of the file still loads.
    """

    name: str = ""
    measured_volume_mL: float = 0.0
    flow_test_date: date | None = None
    flow_test_result: str = ""
    flow_test_notes: str = ""
    format_version: int = RECIPE_FORMAT_VERSION
    ingredients: list[dict[str, Any]] = field(default_factory=list)
    row_warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def recipes_to_workbook_bytes(
    entries: list[tuple[dict[str, Any], dict[str, Any] | None]],
) -> bytes:
    """Serialise any number of blends (each with its flow test) to .xlsx.

    Args:
        entries: (blend, flow_test) pairs. A blend is a session-state dict
            — {"name", "ingredients", "measured_volume_mL"} — where each
            ingredient is {"food_code", "food_description", "grams",
            "unit", "counts_as_fluid"}. flow_test is optional
            {"date", "result", "notes"}.

    Returns:
        Raw .xlsx bytes, ready to hand to st.download_button.

    Recipe ids are assigned here, 1..n by position, and are only
    meaningful within this one file. They are deliberately NOT the app's
    session blend ids: those restart at 1 every session, so writing them
    would produce files whose ids look authoritative and collide across
    downloads.
    """
    recipe_rows: list[dict[str, Any]] = []
    ingredient_rows: list[dict[str, Any]] = []

    for recipe_id, (blend, flow_test) in enumerate(entries, start=1):
        ft = flow_test or {}
        name = blend.get("name", "") or ""
        recipe_rows.append(
            {
                RECIPE_ID_COLUMN: recipe_id,
                RECIPE_NAME_COLUMN: name,
                "Measured final volume (mL)": float(blend.get("measured_volume_mL", 0.0) or 0.0),
                "Flow test date": ft.get("date") or "",
                "Flow test result": ft.get("result", "") or "",
                "Flow test notes": ft.get("notes", "") or "",
                "Format version": RECIPE_FORMAT_VERSION,
            }
        )
        for ing in blend.get("ingredients", []):
            ingredient_rows.append(
                {
                    # Repeated on every row so the sheet stands alone: an
                    # RD can sort or filter by recipe in Excel without
                    # cross-referencing the other sheet.
                    RECIPE_ID_COLUMN: recipe_id,
                    RECIPE_NAME_COLUMN: name,
                    "CNF food code": ing.get("food_code"),
                    "Food description": ing.get("food_description", "") or "",
                    "Amount": float(ing.get("grams", 0.0) or 0.0),
                    "Unit": ing.get("unit", "g") or "g",
                    # Written as Yes/No rather than TRUE/FALSE: this file is
                    # meant to be read and edited by a person in Excel.
                    "Counts as fluid": "Yes" if ing.get("counts_as_fluid") else "No",
                    # Blank rather than 0 with no measure -- same reasoning
                    # as day_io.py's Ingredients sheet.
                    "Measure label": ing.get("measure_label") or "",
                    "Measure grams": (
                        float(ing["measure_grams"]) if ing.get("measure_grams") else ""
                    ),
                }
            )

    recipe_df = pd.DataFrame(recipe_rows, columns=_RECIPE_COLUMNS)
    ingredients_df = pd.DataFrame(ingredient_rows, columns=_INGREDIENT_COLUMNS)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        recipe_df.to_excel(writer, sheet_name=RECIPE_SHEET, index=False)
        ingredients_df.to_excel(writer, sheet_name=INGREDIENTS_SHEET, index=False)
    return buffer.getvalue()


def recipe_to_workbook_bytes(
    blend: dict[str, Any],
    flow_test: dict[str, Any] | None = None,
) -> bytes:
    """Serialise a single blend. Thin wrapper over recipes_to_workbook_bytes().

    Kept because saving one blend is still the common case and reads
    better at the call site than wrapping it in a list.
    """
    return recipes_to_workbook_bytes([(blend, flow_test)])


def suggested_filename(blend_name: str, count: int = 1) -> str:
    """A safe, readable download filename for a saved recipe file.

    Mirrors the sanitising the Excel export already does — an RD's blend
    name can contain anything, and it has to survive being a filename on
    Windows and macOS alike.

    `count` only changes the "recipe"/"recipes" stem, so a file holding
    several blends is recognisable as such in a downloads folder without
    opening it.
    """
    cleaned = "".join(
        ch if (ch.isalnum() or ch in " -_") else "-" for ch in (blend_name or "")
    ).strip()
    cleaned = "-".join(cleaned.split()) or "recipe"
    stem = "btf-recipe" if count == 1 else "btf-recipes"
    return f"{stem}_{cleaned}.xlsx"


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _coerce_float(value: Any) -> float | None:
    """Best-effort number read. Returns None when the cell isn't a number.

    Excel hands back strings, floats, ints and NaN depending on how a cell
    was typed, so nothing here assumes a type.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(str(value).strip())
    except TypeError, ValueError:
        return None


def _coerce_str(value: Any) -> str:
    """Read a text cell, treating an empty cell as an empty string.

    Not just str(value): pandas reads a blank Excel cell as NaN, and
    str(NaN) is the literal text "nan" — which would sail straight into a
    recipe as a flow-test result reading "nan". Exactly the same shape of
    trap as CNF's sodium row (§11), where a missing-looking value silently
    becomes real text. Anything falsy or NaN collapses to "".
    """
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _coerce_bool(value: Any) -> bool:
    """Read a human-typed yes/no cell. Anything unrecognised is False."""
    if isinstance(value, bool):
        return value
    return _coerce_str(value).lower() in {"yes", "y", "true", "1"}


def _coerce_date(value: Any) -> date | None:
    """Read a flow-test date cell, treating an empty cell as None.

    The NaT guard is load-bearing and only started mattering with
    multi-recipe files. When one recipe in a file has a flow-test date
    and another doesn't, pandas types the whole column as datetime and
    fills the blank with `pd.NaT`. NaT subclasses `datetime`, so a plain
    `isinstance(value, date)` test accepts it and a "no flow test"
    recipe comes back carrying a date-shaped object that isn't a date.

    Same shape of trap as blank cells reading back as the literal string
    "nan" (see _coerce_str) and as CNF's sodium row in §11: a missing
    value that arrives disguised as a real one.
    """
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _recipe_key(row: Any, use_id: bool) -> str:
    """The value tying a row to its recipe, as a comparable string."""
    if use_id:
        value = _coerce_float(row.get(RECIPE_ID_COLUMN))
        return "" if value is None else str(int(value))
    return _coerce_str(row.get(RECIPE_NAME_COLUMN))


def workbook_bytes_to_recipes(data: bytes | BytesIO) -> list[ParsedRecipe]:
    """Read a recipe workbook back into one ParsedRecipe per recipe.

    Handles both format versions:
      v2  many recipes, ingredients tagged with "Recipe id"/"Recipe name".
      v1  one recipe, untagged ingredients — unambiguous, so they all
          belong to it.

    Structural problems raise RecipeFileError (wrong kind of file). Bad
    individual rows are skipped with a warning, so one mistyped line
    doesn't cost the whole upload.
    """
    buffer = BytesIO(data) if isinstance(data, bytes) else data
    try:
        sheets = pd.read_excel(buffer, sheet_name=None, engine="openpyxl")
    except Exception as exc:  # noqa: BLE001 - surfaced to the RD as a message
        raise RecipeFileError(
            "That file couldn't be opened as a spreadsheet. Please upload an "
            ".xlsx recipe file saved from this app, or one built from it."
        ) from exc

    if INGREDIENTS_SHEET not in sheets:
        raise RecipeFileError(
            f"This spreadsheet has no '{INGREDIENTS_SHEET}' sheet, so there's "
            "nothing to load. A recipe file needs a 'Recipe' sheet and an "
            "'Ingredients' sheet."
        )

    ingredients_df = sheets[INGREDIENTS_SHEET]
    for column in ("Food description", "Amount"):
        if column not in ingredients_df.columns:
            raise RecipeFileError(
                f"The '{INGREDIENTS_SHEET}' sheet has no '{column}' column. "
                "It needs at least 'Food description' and 'Amount'."
            )

    # --- Recipe sheet (optional: a hand-built file may only have ingredients)
    recipe_df = sheets.get(RECIPE_SHEET)
    recipe_rows = (
        [row for _, row in recipe_df.iterrows()]
        if recipe_df is not None and not recipe_df.empty
        else []
    )

    # Which column links the two sheets? Prefer the id -- blend names are
    # free text and two blends can legitimately share one.
    link_by_id = RECIPE_ID_COLUMN in ingredients_df.columns and any(
        RECIPE_ID_COLUMN in r.index for r in recipe_rows
    )
    link_by_name = RECIPE_NAME_COLUMN in ingredients_df.columns
    has_link = link_by_id or link_by_name

    # A file holding several recipes with no way to tell the ingredients
    # apart is NOT loaded as one merged blend. Pooling two recipes would
    # silently invent a feed nobody wrote, with plausible-looking numbers
    # -- the same failure mode as the batch-extrapolation bug in
    # FEED_LOG_REWORK.md 6.2. Refuse, and say what's missing.
    if len(recipe_rows) > 1 and not has_link:
        raise RecipeFileError(
            f"This file lists {len(recipe_rows)} recipes, but the "
            f"'{INGREDIENTS_SHEET}' sheet has no '{RECIPE_NAME_COLUMN}' column "
            "saying which recipe each ingredient belongs to. Add that column "
            "(one recipe name per ingredient row) and upload it again — "
            "guessing would risk mixing two recipes together."
        )

    parsed_by_key: dict[str, ParsedRecipe] = {}
    order: list[str] = []

    def _slot(key: str) -> ParsedRecipe:
        if key not in parsed_by_key:
            parsed_by_key[key] = ParsedRecipe()
            order.append(key)
        return parsed_by_key[key]

    # --- Header rows
    for position, row in enumerate(recipe_rows, start=1):
        key = _recipe_key(row, link_by_id) if has_link else ""
        if not key:
            key = str(position)
        parsed = _slot(key)
        parsed.name = _coerce_str(row.get(RECIPE_NAME_COLUMN))
        volume = _coerce_float(row.get("Measured final volume (mL)"))
        if volume is None:
            parsed.row_warnings.append(
                "No measured final volume found — you'll need to enter it "
                "before the densities can be calculated."
            )
        else:
            parsed.measured_volume_mL = volume
        parsed.flow_test_date = _coerce_date(row.get("Flow test date"))
        parsed.flow_test_result = _coerce_str(row.get("Flow test result"))
        parsed.flow_test_notes = _coerce_str(row.get("Flow test notes"))
        version = _coerce_float(row.get("Format version"))
        if version is not None:
            parsed.format_version = int(version)

    single_key = order[0] if len(order) == 1 else None

    # --- Ingredient rows
    for position, row in ingredients_df.iterrows():
        description = _coerce_str(row.get("Food description"))
        code = _coerce_float(row.get("CNF food code"))
        amount = _coerce_float(row.get("Amount"))
        line_number = int(position) + 2  # +1 for the header, +1 for 1-based

        if not description and code is None:
            continue  # a genuinely blank row — silently skipped

        # With exactly one recipe in the file there is nothing to be
        # ambiguous about, so untagged rows (every v1 file) belong to it.
        key = _recipe_key(row, link_by_id) if has_link else ""
        if not key:
            key = single_key if single_key is not None else "1"

        parsed = _slot(key)

        if amount is None or amount <= 0:
            parsed.row_warnings.append(
                f"Row {line_number} ({description or 'no description'}) has no "
                "usable amount, so it was skipped."
            )
            continue

        unit = _coerce_str(row.get("Unit")) or "g"
        if unit not in ("g", "mL"):
            parsed.row_warnings.append(
                f"Row {line_number} ({description}) had unit '{unit}', which "
                "isn't 'g' or 'mL' — treated as grams."
            )
            unit = "g"

        if not parsed.name:
            parsed.name = _coerce_str(row.get(RECIPE_NAME_COLUMN))

        parsed.ingredients.append(
            {
                "food_code": int(code) if code is not None else None,
                "food_description": description,
                "grams": amount,
                "unit": unit,
                "counts_as_fluid": _coerce_bool(row.get("Counts as fluid")),
                # .get() on an absent column returns None -- an older
                # recipe file (or a v1 file, which never had this column
                # at all) simply has no household measure. No
                # format-version branch (Change 4, 2026-08-15).
                "measure_label": _coerce_str(row.get("Measure label")) or None,
                "measure_grams": _coerce_float(row.get("Measure grams")),
            }
        )

    return [parsed_by_key[key] for key in order] or [ParsedRecipe()]


def workbook_bytes_to_recipe(data: bytes | BytesIO) -> ParsedRecipe:
    """Read a workbook expected to hold exactly one recipe.

    Kept for callers that genuinely want one. Raises RecipeFileError on a
    multi-recipe file rather than quietly returning the first, so nobody
    loses recipes to a convenience default.
    """
    recipes = workbook_bytes_to_recipes(data)
    if len(recipes) > 1:
        raise RecipeFileError(
            f"This file holds {len(recipes)} recipes; use "
            "workbook_bytes_to_recipes() to read them all."
        )
    return recipes[0]


# ---------------------------------------------------------------------------
# Resolving typed descriptions against CNF
# ---------------------------------------------------------------------------


def resolve_ingredients(
    parsed: ParsedRecipe,
    food_name_df: pd.DataFrame,
    description_column: str = "Food_Description_EN",
    code_column: str = "Food_Code",
) -> list[ResolvedIngredient]:
    """Tie each parsed ingredient to a CNF food, without ever guessing.

    A row carrying a food code is taken at its word (that's a file this
    app wrote, or someone who looked the code up). A row with only a
    description is matched case-insensitively:

      * exactly one match  -> MATCH_BY_DESCRIPTION, still flagged for
                              confirmation, because "one match" is not the
                              same as "the right match";
      * several matches    -> AMBIGUOUS, with candidates attached;
      * no match           -> UNMATCHED.

    Nothing here mutates the recipe. The caller shows the result and lets
    the RD confirm — see CONTEXT.md §11 on why an uploaded recipe lands as
    a draft rather than committing itself.
    """
    resolved: list[ResolvedIngredient] = []
    descriptions = food_name_df[description_column].astype(str)

    for ing in parsed.ingredients:
        common = {
            "grams": ing["grams"],
            "unit": ing.get("unit", "g"),
            "counts_as_fluid": ing.get("counts_as_fluid", False),
            "source_text": ing.get("food_description", ""),
            # .get(), unlike the bracket access on "grams" above: existing
            # parsed-recipe dicts predate this change and have no such
            # keys at all (Change 5, 2026-08-15).
            "measure_label": ing.get("measure_label"),
            "measure_grams": ing.get("measure_grams"),
        }
        code = ing.get("food_code")

        if code is not None:
            known = food_name_df[food_name_df[code_column] == code]
            if not known.empty:
                resolved.append(
                    ResolvedIngredient(
                        status=MATCH_BY_CODE,
                        food_code=int(code),
                        food_description=str(known.iloc[0][description_column]),
                        **common,
                    )
                )
                continue
            # A code that isn't in CNF: fall through to description matching
            # rather than trusting a number that resolves to nothing.

        text = (ing.get("food_description") or "").strip()
        if not text:
            resolved.append(
                ResolvedIngredient(status=UNMATCHED, food_code=None, food_description="", **common)
            )
            continue

        hits = food_name_df[descriptions.str.contains(text, case=False, na=False, regex=False)]
        if len(hits) == 1:
            resolved.append(
                ResolvedIngredient(
                    status=MATCH_BY_DESCRIPTION,
                    food_code=int(hits.iloc[0][code_column]),
                    food_description=str(hits.iloc[0][description_column]),
                    **common,
                )
            )
        elif len(hits) > 1:
            resolved.append(
                ResolvedIngredient(
                    status=AMBIGUOUS,
                    food_code=None,
                    food_description=text,
                    candidates=[
                        (int(r[code_column]), str(r[description_column]))
                        for _, r in hits.head(25).iterrows()
                    ],
                    **common,
                )
            )
        else:
            resolved.append(
                ResolvedIngredient(
                    status=UNMATCHED, food_code=None, food_description=text, **common
                )
            )

    return resolved
