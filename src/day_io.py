"""
day_io.py — save a whole working day to a spreadsheet, and read it back.

WHY THIS EXISTS
---------------
Close the browser tab and everything goes: the blends, the day's intake,
the targets. That is the single most likely first complaint from an RD
pilot, and it is the gap between "this works" and "I could use this on
Tuesday".

`recipe_io.py` already saves *recipes*. This saves the **day** — the
recipes plus what was actually given, the targets they were measured
against, and any custom foods those rows depend on.

WHY A FILE, NOT AN ACCOUNT
--------------------------
The deployed app runs on a shared public server with no per-user
storage, and holds no patient data by design (BUSINESS_CASE.md §8) —
which is exactly what makes public deployment simple and safe. Saving
server-side would throw that away. A file downloads to the RD's own
machine, where clinical records already live, and nothing
patient-identifying ever crosses the network.

That does mean the file contains whatever the RD typed in the day label.
If they typed a patient name, the file has a patient name in it. It is
their file on their machine, the same as any chart export — but the UI
says so rather than leaving them to work it out.

WHAT MUST BE IN THE FILE
------------------------
  Record        label, patient weight, format version
  Targets       one row per nutrient with a target set
  Blends        one row per blend: name, measured volume, flow test
  Ingredients   one row per ingredient, tagged with its blend
  Intake        one row per thing actually given, in time order
  Custom foods  per-100 g values for label-entered foods

**The Custom foods sheet is not optional.** A food entered from a
nutrition label lives only in session state under a negative food code.
An ingredient row or an oral intake row can reference that code, so a
file without those values reloads into a day with dangling references
and silently wrong totals. Saving the day means saving everything the
day's rows point at.

LOADING REPLACES, IT DOES NOT MERGE
-----------------------------------
Opening a saved day is "go back to that day", so it replaces what is on
screen. Recipes are the opposite — those load *alongside* what you have.
The difference is deliberate and the UI confirms before replacing,
because merging two days would produce an intake record that never
happened.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import time as dtime
from io import BytesIO
from typing import Any

import pandas as pd

# Excel cell reading is shared with recipe_io on purpose. Both files have
# already been bitten by the same two traps -- a blank cell arriving as
# the literal string "nan", and a blank date arriving as pandas NaT, which
# subclasses datetime and so passes a naive isinstance check. One
# implementation of those rules, not two.
from src.recipe_io import _coerce_bool, _coerce_date, _coerce_float, _coerce_str

# v1  inputs only (six sheets), with a separate "report" workbook alongside.
# v2  one file: the same input sheets, plus the computed report sheets, plus
#     a readable "Source" column on Intake and "Delivery method" on Day.
#     Two downloads became one because the failure was asymmetric -- an RD
#     who saved only the report could not reload it and lost the day's work,
#     while nobody is harmed by a file carrying extra sheets. v1 files still
#     load: the reader takes sheets and columns by name and ignores anything
#     it doesn't recognise.
DAY_FORMAT_VERSION = 3

RECORD_SHEET = "Record"
# What RECORD_SHEET was called before format version 3 (2026-08-16). Kept
# only to RECOGNISE such a file and say so plainly -- it is never read.
LEGACY_RECORD_SHEET = "Day"
TARGETS_SHEET = "Targets"
BLENDS_SHEET = "Blends"
INGREDIENTS_SHEET = "Ingredients"
INTAKE_SHEET = "Intake"
CUSTOM_FOODS_SHEET = "Custom foods"

_BLEND_ID_COLUMN = "Blend id"
_BLEND_NAME_COLUMN = "Blend name"

# The reloadable half. A report sheet may not overwrite one of these --
# that would make the file unopenable by the app it came from.
_INPUT_SHEETS = frozenset(
    {RECORD_SHEET, TARGETS_SHEET, BLENDS_SHEET, INGREDIENTS_SHEET, INTAKE_SHEET, CUSTOM_FOODS_SHEET}
)


class DayFileError(ValueError):
    """The uploaded file isn't a day file we can read.

    Structural problems only (missing sheet, missing column). Problems
    with individual rows are collected as warnings so one bad line never
    costs the RD the whole day.
    """


@dataclass
class ParsedDay:
    """A day file read off disk, ready to apply to session state."""

    label: str = ""
    patient_weight: float = 0.0
    weight_unit: str = "kg"
    format_version: int = DAY_FORMAT_VERSION
    targets: dict[str, float] = field(default_factory=dict)
    blends: dict[int, dict[str, Any]] = field(default_factory=dict)
    intake_log: list[dict[str, Any]] = field(default_factory=list)
    custom_foods: dict[int, dict[str, float]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """One line an RD can check before agreeing to replace their day."""
        blends = len(self.blends)
        rows = len(self.intake_log)
        bits = [
            f"{blends} blend{'s' if blends != 1 else ''}",
            f"{rows} intake row{'s' if rows != 1 else ''}",
        ]
        if self.targets:
            bits.append(f"{len(self.targets)} target{'s' if len(self.targets) != 1 else ''}")
        if self.custom_foods:
            # Was missing the plural every sibling count here has, so a
            # two-custom-food day read "2 custom food" in the sentence an
            # RD reads right before agreeing to replace their day
            # (2026-08-20 review).
            n = len(self.custom_foods)
            bits.append(f"{n} custom food{'s' if n != 1 else ''}")
        return ", ".join(bits)


def _time_to_text(value: Any) -> str:
    """Times are written HH:MM so the Intake sheet sorts and reads plainly."""
    if isinstance(value, dtime):
        return value.strftime("%H:%M")
    return ""


def _text_to_time(value: Any) -> dtime | None:
    """Read a time cell back.

    Excel may hand this back as a real time, as a datetime, or as text,
    depending on how the cell was formatted -- so all three are accepted
    rather than assuming the one we wrote.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, dtime):
        return value
    if isinstance(value, pd.Timestamp):
        return value.time()
    text = _coerce_str(value)
    if not text:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return pd.to_datetime(text, format=fmt).time()
        except ValueError, TypeError:
            continue
    return None


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def day_to_workbook_bytes(
    *,
    label: str,
    patient_weight: float,
    weight_unit: str,
    targets: dict[str, float],
    blends: dict[int, dict[str, Any]],
    intake_log: list[dict[str, Any]],
    custom_foods: dict[int, dict[str, float]],
    delivery_method: str = "",
    extra_sheets: dict[str, pd.DataFrame] | None = None,
) -> bytes:
    """Serialise a whole day to .xlsx bytes.

    Args:
        extra_sheets: computed report tables (adequacy, micro screen,
            per-source breakdown, water ledger, chart note) written after
            the reloadable sheets, so ONE file both reopens in the app and
            reads as a report. Sheet names must not collide with the six
            input sheets; the caller owns their content and column order.
            The reader ignores them entirely -- they are for humans.
        delivery_method: chart-note wording only, recorded so the report
            half of the file is self-describing.

    An intake row may carry a "_source_name" key (the readable blend or
    formula name). It is written to a "Source" column for people reading
    the file, and ignored on load, which reads "Source id".
    """
    day_df = pd.DataFrame(
        [
            {"Field": "Record label", "Value": label or ""},
            {"Field": "Patient weight", "Value": float(patient_weight or 0.0)},
            {"Field": "Weight unit", "Value": weight_unit or "kg"},
            {"Field": "Delivery method", "Value": delivery_method or ""},
            {"Field": "Format version", "Value": DAY_FORMAT_VERSION},
        ]
    )

    # Only targets that were actually set. 0 means "no target" in this app
    # (the number_input can't be blank), so writing zeros would turn "not
    # set" into a row that looks deliberate.
    targets_df = pd.DataFrame(
        [
            {"Nutrient": name, "Target per day": float(value)}
            for name, value in sorted(targets.items())
            if value
        ],
        columns=["Nutrient", "Target per day"],
    )

    blend_rows: list[dict[str, Any]] = []
    ingredient_rows: list[dict[str, Any]] = []
    for blend_id, blend in sorted(blends.items()):
        flow = blend.get("flow_test") or {}
        name = blend.get("name", "") or ""
        blend_rows.append(
            {
                _BLEND_ID_COLUMN: blend_id,
                _BLEND_NAME_COLUMN: name,
                "Measured final volume (mL)": float(blend.get("measured_volume_mL", 0.0) or 0.0),
                "Flow test date": flow.get("date") or "",
                "Flow test result": flow.get("result", "") or "",
                "Flow test notes": flow.get("notes", "") or "",
            }
        )
        for ing in blend.get("ingredients", []):
            ingredient_rows.append(
                {
                    _BLEND_ID_COLUMN: blend_id,
                    _BLEND_NAME_COLUMN: name,
                    "CNF food code": ing.get("food_code"),
                    "Food description": ing.get("food_description", "") or "",
                    "Amount": float(ing.get("grams", 0.0) or 0.0),
                    "Unit": ing.get("unit", "g") or "g",
                    "Counts as fluid": "Yes" if ing.get("counts_as_fluid") else "No",
                    # Blank rather than 0 when there's no household
                    # measure, so a plain gram-only row doesn't pick up a
                    # phantom "0 g per 1" in the sheet (Change 4,
                    # 2026-08-15). .get(), not ["measure_grams"] -- older
                    # in-memory ingredient dicts (before this change)
                    # won't have the key at all.
                    "Measure label": ing.get("measure_label") or "",
                    "Measure grams": (
                        float(ing["measure_grams"]) if ing.get("measure_grams") else ""
                    ),
                }
            )

    intake_rows = [
        {
            "Time": _time_to_text(row.get("time")),
            "Source type": row.get("source_type", ""),
            # Blend id, formula name, food code, or blank for a flush --
            # written as text so a formula name and a blend id can share
            # one column without Excel retyping it.
            "Source id": "" if row.get("source_id") is None else str(row.get("source_id")),
            # Readable name for whoever opens the file; the loader uses
            # "Source id" and ignores this.
            "Source": row.get("_source_name") or "",
            "Description": row.get("food_description") or "",
            "Amount": float(row.get("amount", 0.0) or 0.0),
            "Unit": row.get("unit", "mL") or "mL",
            "Counts as fluid": "Yes" if row.get("counts_as_fluid") else "No",
            # Same blank-not-zero rule as the Ingredients sheet above.
            "Measure label": row.get("measure_label") or "",
            "Measure grams": float(row["measure_grams"]) if row.get("measure_grams") else "",
        }
        for row in intake_log
    ]
    intake_df = pd.DataFrame(
        intake_rows,
        columns=[
            "Time",
            "Source type",
            "Source id",
            "Source",
            "Description",
            "Amount",
            "Unit",
            "Counts as fluid",
            "Measure label",
            "Measure grams",
        ],
    )

    # Long format (one row per nutrient) rather than a column per
    # nutrient: the tracked set is data and can change between packs, so a
    # wide sheet would bake today's nutrient list into every saved file.
    custom_rows = [
        {"Food code": code, "Nutrient": nutrient, "Per 100 g": float(value)}
        for code, values in sorted(custom_foods.items())
        for nutrient, value in sorted(values.items())
    ]
    custom_df = pd.DataFrame(custom_rows, columns=["Food code", "Nutrient", "Per 100 g"])

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        day_df.to_excel(writer, sheet_name=RECORD_SHEET, index=False)
        targets_df.to_excel(writer, sheet_name=TARGETS_SHEET, index=False)
        pd.DataFrame(
            blend_rows,
            columns=[
                _BLEND_ID_COLUMN,
                _BLEND_NAME_COLUMN,
                "Measured final volume (mL)",
                "Flow test date",
                "Flow test result",
                "Flow test notes",
            ],
        ).to_excel(writer, sheet_name=BLENDS_SHEET, index=False)
        pd.DataFrame(
            ingredient_rows,
            columns=[
                _BLEND_ID_COLUMN,
                _BLEND_NAME_COLUMN,
                "CNF food code",
                "Food description",
                "Amount",
                "Unit",
                "Counts as fluid",
                "Measure label",
                "Measure grams",
            ],
        ).to_excel(writer, sheet_name=INGREDIENTS_SHEET, index=False)
        intake_df.to_excel(writer, sheet_name=INTAKE_SHEET, index=False)
        custom_df.to_excel(writer, sheet_name=CUSTOM_FOODS_SHEET, index=False)

        # Report tables last, so the file reads inputs-then-results in tab
        # order. Excel caps a sheet title at 31 characters and rejects
        # : \ / ? * [ ] outright (openpyxl raises), so names are trimmed
        # and screened here rather than trusting the caller.
        for sheet_name, frame in (extra_sheets or {}).items():
            safe = re.sub(r"[:\\/?*\[\]]", "-", str(sheet_name))[:31]
            if not safe or safe in _INPUT_SHEETS:
                continue
            frame.to_excel(writer, sheet_name=safe, index=False)
    return buffer.getvalue()


def suggested_day_filename(label: str) -> str:
    """A safe, readable download filename for a saved day.

    Runs of dashes collapse to one: a realistic label like
    "James W, H&N RT wk 5" replaces both the comma and the ampersand,
    which would otherwise leave "James-W--H-N". Cosmetic, but this is the
    filename an RD sees in their downloads folder.
    """
    cleaned = "".join(ch if (ch.isalnum() or ch in " -_") else "-" for ch in (label or "")).strip()
    cleaned = "-".join(cleaned.split())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-") or "record"
    return f"btf-record_{cleaned}.xlsx"


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def workbook_bytes_to_day(data: bytes | BytesIO) -> ParsedDay:
    """Read a day workbook back into a ParsedDay."""
    buffer = BytesIO(data) if isinstance(data, bytes) else data
    try:
        sheets = pd.read_excel(buffer, sheet_name=None, engine="openpyxl")
    except Exception as exc:  # noqa: BLE001 - surfaced to the RD as a message
        raise DayFileError(
            "That file couldn't be opened as a spreadsheet. Please upload an "
            ".xlsx record saved from this app."
        ) from exc

    # The Intake sheet is what makes this a day rather than a recipe file.
    # Checking for it by name gives the RD a useful message when they
    # upload a recipe here by mistake, which is an easy thing to do.
    if INTAKE_SHEET not in sheets:
        raise DayFileError(
            f"This spreadsheet has no '{INTAKE_SHEET}' sheet, so it isn't a saved record. "
            "If it's a saved recipe, load it from the Feed Recipes tab instead."
        )

    parsed = ParsedDay()

    # --- Record sheet
    #
    # Format version 3 renamed this sheet from "Day" (2026-08-16), and the
    # reader deliberately does NOT accept the old name (author's call: the
    # app is new enough that few such files exist). Refusing LOUDLY is the
    # part that matters. The read below tolerates a missing sheet, so an
    # older file would otherwise open looking fine while its label, weight
    # and unit came back blank -- a silent wrong answer, which is worse
    # than a file that plainly will not open.
    if RECORD_SHEET not in sheets and LEGACY_RECORD_SHEET in sheets:
        raise DayFileError(
            f"This file was saved before the '{LEGACY_RECORD_SHEET}' sheet was renamed "
            f"to '{RECORD_SHEET}', so it can't be opened here."
        )

    day_df = sheets.get(RECORD_SHEET)
    if day_df is not None and {"Field", "Value"}.issubset(day_df.columns):
        values = {_coerce_str(r.get("Field")): r.get("Value") for _, r in day_df.iterrows()}
        parsed.label = _coerce_str(values.get("Record label"))
        parsed.patient_weight = _coerce_float(values.get("Patient weight")) or 0.0
        parsed.weight_unit = _coerce_str(values.get("Weight unit")) or "kg"
        version = _coerce_float(values.get("Format version"))
        if version is not None:
            parsed.format_version = int(version)

    # --- Targets
    targets_df = sheets.get(TARGETS_SHEET)
    if targets_df is not None and "Nutrient" in targets_df.columns:
        for _, row in targets_df.iterrows():
            name = _coerce_str(row.get("Nutrient"))
            value = _coerce_float(row.get("Target per day"))
            if name and value is not None:
                parsed.targets[name] = value

    # --- Blends
    blends_df = sheets.get(BLENDS_SHEET)
    if blends_df is not None and _BLEND_ID_COLUMN in blends_df.columns:
        for _, row in blends_df.iterrows():
            blend_id = _coerce_float(row.get(_BLEND_ID_COLUMN))
            if blend_id is None:
                continue
            parsed.blends[int(blend_id)] = {
                "name": _coerce_str(row.get(_BLEND_NAME_COLUMN)),
                "ingredients": [],
                "measured_volume_mL": _coerce_float(row.get("Measured final volume (mL)")) or 0.0,
                "flow_test": {
                    "date": _coerce_date(row.get("Flow test date")),
                    "result": _coerce_str(row.get("Flow test result")) or "Not done",
                    "notes": _coerce_str(row.get("Flow test notes")),
                },
            }

    # --- Ingredients
    ingredients_df = sheets.get(INGREDIENTS_SHEET)
    next_ingredient_id = 0
    if ingredients_df is not None and _BLEND_ID_COLUMN in ingredients_df.columns:
        for position, row in ingredients_df.iterrows():
            blend_id = _coerce_float(row.get(_BLEND_ID_COLUMN))
            code = _coerce_float(row.get("CNF food code"))
            amount = _coerce_float(row.get("Amount"))
            line = int(position) + 2
            if blend_id is None or code is None:
                continue
            if int(blend_id) not in parsed.blends:
                parsed.warnings.append(
                    f"Ingredients row {line} belongs to blend {int(blend_id)}, "
                    "which isn't in this file — skipped."
                )
                continue
            if amount is None or amount <= 0:
                parsed.warnings.append(f"Ingredients row {line} has no usable amount — skipped.")
                continue
            next_ingredient_id += 1
            parsed.blends[int(blend_id)]["ingredients"].append(
                {
                    "id": next_ingredient_id,
                    "food_code": int(code),
                    "food_description": _coerce_str(row.get("Food description")),
                    "grams": amount,
                    "unit": _coerce_str(row.get("Unit")) or "g",
                    "counts_as_fluid": _coerce_bool(row.get("Counts as fluid")),
                    # .get() on an absent column returns None -- a v1/v2
                    # file saved before this change simply has no
                    # household measure, exactly like a CNF food with none
                    # (Change 4, 2026-08-15). No format-version branch.
                    "measure_label": _coerce_str(row.get("Measure label")) or None,
                    "measure_grams": _coerce_float(row.get("Measure grams")),
                }
            )

    # --- Custom foods (read BEFORE validating intake, since intake rows
    # may reference these codes)
    custom_df = sheets.get(CUSTOM_FOODS_SHEET)
    if custom_df is not None and "Food code" in custom_df.columns:
        for _, row in custom_df.iterrows():
            code = _coerce_float(row.get("Food code"))
            nutrient = _coerce_str(row.get("Nutrient"))
            value = _coerce_float(row.get("Per 100 g"))
            if code is None or not nutrient or value is None:
                continue
            parsed.custom_foods.setdefault(int(code), {})[nutrient] = value

    # --- Intake
    intake_df = sheets[INTAKE_SHEET]
    for column in ("Source type", "Amount"):
        if column not in intake_df.columns:
            raise DayFileError(
                f"The '{INTAKE_SHEET}' sheet has no '{column}' column, so the record "
                "can't be read."
            )

    next_intake_id = 0
    for position, row in intake_df.iterrows():
        source_type = _coerce_str(row.get("Source type")).lower()
        amount = _coerce_float(row.get("Amount"))
        line = int(position) + 2

        if not source_type:
            continue
        if source_type not in ("blend", "formula", "flush", "oral"):
            parsed.warnings.append(
                f"Intake row {line} has source type '{source_type}', which isn't "
                "one of blend/formula/flush/oral — skipped."
            )
            continue
        if amount is None or amount <= 0:
            parsed.warnings.append(f"Intake row {line} has no usable amount — skipped.")
            continue

        raw_source = _coerce_str(row.get("Source id"))
        source_id: int | str | None
        if source_type == "flush":
            source_id = None
        elif source_type == "formula":
            source_id = raw_source
        else:
            # blend id or CNF/custom food code -- both integers.
            numeric = _coerce_float(raw_source)
            if numeric is None:
                parsed.warnings.append(
                    f"Intake row {line} ({source_type}) has no usable source id — skipped."
                )
                continue
            source_id = int(numeric)

        # A blend row pointing at a blend this file doesn't contain would
        # silently contribute nothing to the day's totals. Say so.
        if source_type == "blend" and source_id not in parsed.blends:
            parsed.warnings.append(
                f"Intake row {line} refers to blend {source_id}, which isn't in "
                "this file — skipped."
            )
            continue

        next_intake_id += 1
        parsed.intake_log.append(
            {
                "id": next_intake_id,
                "time": _text_to_time(row.get("Time")),
                "source_type": source_type,
                "source_id": source_id,
                "food_description": _coerce_str(row.get("Description")) or None,
                "amount": amount,
                "unit": _coerce_str(row.get("Unit")) or "mL",
                "counts_as_fluid": _coerce_bool(row.get("Counts as fluid")),
                "measure_label": _coerce_str(row.get("Measure label")) or None,
                "measure_grams": _coerce_float(row.get("Measure grams")),
            }
        )

    return parsed
