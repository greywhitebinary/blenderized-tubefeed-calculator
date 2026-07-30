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

  Sheet "Recipe"       one row: recipe name, measured volume, flow-test
                       date/result/notes, plus a format version.
  Sheet "Ingredients"  one row per ingredient: food code, description,
                       amount, unit, counts-as-fluid.

A recipe is not a flat table — it has one set of facts about the batch
and a repeating list of ingredients — so two sheets is simply how a
person would lay it out anyway.

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
RECIPE_FORMAT_VERSION = 1

RECIPE_SHEET = "Recipe"
INGREDIENTS_SHEET = "Ingredients"

# Column headers. Human-facing (they're what an RD sees in Excel), so they
# read as words rather than field names.
_RECIPE_COLUMNS = [
    "Recipe name",
    "Measured final volume (mL)",
    "Flow test date",
    "Flow test result",
    "Flow test notes",
    "Format version",
]
_INGREDIENT_COLUMNS = [
    "CNF food code",
    "Food description",
    "Amount",
    "Unit",
    "Counts as fluid",
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


def recipe_to_workbook_bytes(
    blend: dict[str, Any],
    flow_test: dict[str, Any] | None = None,
) -> bytes:
    """Serialise one blend (plus its flow test) to .xlsx bytes.

    Args:
        blend: A session-state blend dict — {"name", "ingredients",
            "measured_volume_mL"}, where each ingredient is
            {"food_code", "food_description", "grams", "unit",
            "counts_as_fluid"}.
        flow_test: Optional {"date", "result", "notes"}.

    Returns:
        Raw .xlsx bytes, ready to hand to st.download_button.
    """
    ft = flow_test or {}

    recipe_df = pd.DataFrame(
        [
            {
                "Recipe name": blend.get("name", "") or "",
                "Measured final volume (mL)": float(blend.get("measured_volume_mL", 0.0) or 0.0),
                "Flow test date": ft.get("date") or "",
                "Flow test result": ft.get("result", "") or "",
                "Flow test notes": ft.get("notes", "") or "",
                "Format version": RECIPE_FORMAT_VERSION,
            }
        ],
        columns=_RECIPE_COLUMNS,
    )

    ingredient_rows = [
        {
            "CNF food code": ing.get("food_code"),
            "Food description": ing.get("food_description", "") or "",
            "Amount": float(ing.get("grams", 0.0) or 0.0),
            "Unit": ing.get("unit", "g") or "g",
            # Written as Yes/No rather than TRUE/FALSE: this file is meant
            # to be read and edited by a person in Excel.
            "Counts as fluid": "Yes" if ing.get("counts_as_fluid") else "No",
        }
        for ing in blend.get("ingredients", [])
    ]
    ingredients_df = pd.DataFrame(ingredient_rows, columns=_INGREDIENT_COLUMNS)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        recipe_df.to_excel(writer, sheet_name=RECIPE_SHEET, index=False)
        ingredients_df.to_excel(writer, sheet_name=INGREDIENTS_SHEET, index=False)
    return buffer.getvalue()


def suggested_filename(blend_name: str) -> str:
    """A safe, readable download filename for a blend.

    Mirrors the sanitising the Excel export already does — an RD's blend
    name can contain anything, and it has to survive being a filename on
    Windows and macOS alike.
    """
    cleaned = "".join(
        ch if (ch.isalnum() or ch in " -_") else "-" for ch in (blend_name or "")
    ).strip()
    cleaned = "-".join(cleaned.split()) or "recipe"
    return f"btf-recipe_{cleaned}.xlsx"


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


def workbook_bytes_to_recipe(data: bytes | BytesIO) -> ParsedRecipe:
    """Read a recipe workbook back into a ParsedRecipe.

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

    parsed = ParsedRecipe()

    # --- Recipe sheet (optional: a hand-built file may only have ingredients)
    recipe_df = sheets.get(RECIPE_SHEET)
    if recipe_df is not None and not recipe_df.empty:
        row = recipe_df.iloc[0]
        parsed.name = _coerce_str(row.get("Recipe name"))
        volume = _coerce_float(row.get("Measured final volume (mL)"))
        if volume is None:
            parsed.row_warnings.append(
                "No measured final volume found — you'll need to enter it "
                "before the densities can be calculated."
            )
        else:
            parsed.measured_volume_mL = volume
        raw_date = row.get("Flow test date")
        if isinstance(raw_date, pd.Timestamp):
            parsed.flow_test_date = raw_date.date()
        elif isinstance(raw_date, date):
            parsed.flow_test_date = raw_date
        parsed.flow_test_result = _coerce_str(row.get("Flow test result"))
        parsed.flow_test_notes = _coerce_str(row.get("Flow test notes"))
        version = _coerce_float(row.get("Format version"))
        if version is not None:
            parsed.format_version = int(version)

    # --- Ingredients sheet
    ingredients_df = sheets[INGREDIENTS_SHEET]
    for column in ("Food description", "Amount"):
        if column not in ingredients_df.columns:
            raise RecipeFileError(
                f"The '{INGREDIENTS_SHEET}' sheet has no '{column}' column. "
                f"It needs at least '{_INGREDIENT_COLUMNS[1]}' and "
                f"'{_INGREDIENT_COLUMNS[2]}'."
            )

    for position, row in ingredients_df.iterrows():
        description = _coerce_str(row.get("Food description"))
        code = _coerce_float(row.get("CNF food code"))
        amount = _coerce_float(row.get("Amount"))
        line_number = int(position) + 2  # +1 for the header, +1 for 1-based

        if not description and code is None:
            continue  # a genuinely blank row — silently skipped

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

        parsed.ingredients.append(
            {
                "food_code": int(code) if code is not None else None,
                "food_description": description,
                "grams": amount,
                "unit": unit,
                "counts_as_fluid": _coerce_bool(row.get("Counts as fluid")),
            }
        )

    return parsed


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
