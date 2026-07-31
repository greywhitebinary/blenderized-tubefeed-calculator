"""
label_extract.py — read a Nutrition Facts panel from a photo.

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
This is a **typing shortcut**. It photographs a Nutrition Facts table and
fills in the app's existing custom-food form so the RD doesn't have to
key thirteen numbers by hand.

It is not a data source. Nothing it returns reaches a blend, a total, or
a chart note without a human reading it first. The extracted values land
in the NFt-lookalike form as editable drafts, where the RD holds the real
label beside its digital twin and confirms — the form doubles as the
verification UI (BUSINESS_CASE.md §7, CONTEXT.md §11).

The reason is blunt: a misread sodium digit becomes a wrong number in a
patient's daily total, and nothing downstream would flag it. The model
reads a document; it never computes nutrition.

NEVER FABRICATE
---------------
A nutrient not printed on the label comes back as **absent**, never as
0. This is the same distinction the whole app is built on — a measured
zero and an unmeasured value are different clinical facts (see
`nutrient_coverage` in src/calculator.py, and CNF's own "assumed zero"
provenance code). A label with no potassium line must not produce
"potassium: 0 mg", because that would read as a measurement.

The schema therefore makes every nutrient nullable, the prompt says so
explicitly, and `ExtractedLabel.values` contains only what was actually
read. What was missing is listed separately so the UI can say so.

THE FIELDS ARE DATA, NOT CODE
-----------------------------
Both the JSON schema and the prompt are built from the nutrient registry
(`data/packs/<pack>/nutrients.csv`, the rows with `on_label=yes`). A
static model class would hardcode today's Canadian panel into Python and
silently go stale the moment a pack changes or Canada revises the
mandatory list. Same rule as everywhere else in this project: never
hardcode a nutrient list.

COST AND CAPS
-------------
Caps are enforced by the caller (the app owns session state), but the
policy numbers live here so there is one place to read them. The API key
belongs to the app's author and the app is public: every call any visitor
makes is billed to her personally. See CONTEXT.md §11 for the rule that
a paid feature ships its cap in the same commit.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from src.nutrients import DEFAULT_PACK, load_registry

_LOGGER = logging.getLogger(__name__)

#: Haiku by the author's choice: reading a printed table is the cheapest
#: thing a vision model does, and this runs on her card. Roughly a third
#: of a cent per photo.
#:
#: The DATED id, because the undated alias "claude-haiku-4-5" is NOT what
#: `client.models.list()` returns for this account -- that endpoint is
#: the authority on what a key can actually call, and it costs nothing
#: to ask. Assuming the alias resolves was the first of three bugs in
#: this file's first live call.
LABEL_MODEL = "claude-haiku-4-5-20251001"

#: The output is a small flat JSON object; it does not need room to ramble.
MAX_OUTPUT_TOKENS = 1024

#: Longest edge we send. Bigger photos are resized before the model sees
#: them anyway, so a 12-megapixel phone shot costs upload time and token
#: count without adding legible detail.
MAX_IMAGE_DIMENSION = 1568

SUPPORTED_MEDIA_TYPES = ("image/jpeg", "image/png", "image/webp")

#: Hard API limit on how many response-schema fields may be nullable or
#: union-typed. Exceeding it is a 400, not a warning:
#:   "Schemas contains too many parameters with union types (17 ...).
#:    This causes exponential compilation cost. Reduce the number of
#:    nullable or union-typed parameters (limit: 16 ...)"
#: The budget is spent entirely on nutrients, because "this nutrient is
#: not on the label" is the one distinction that must not be faked.
MAX_UNION_PARAMETERS = 16

# --- Spend policy ---------------------------------------------------------
# Enforced in app/streamlit_app.py; stated here so the numbers are in one
# place. NOTE: neither of these is the real protection. The spend limit
# set on the API key in the Anthropic console is, because it survives a
# bug in this file. These two reduce how often it gets tested.
MAX_EXTRACTIONS_PER_SESSION = 10
MAX_EXTRACTIONS_PER_DAY = 200
APPROX_COST_PER_EXTRACTION_USD = 0.004


class LabelExtractionError(RuntimeError):
    """Extraction failed in a way the RD needs to be told about.

    Always carries a message fit to show on screen. The fallback is never
    silent: if this raises, the form stays empty and the RD types the
    label by hand, exactly as before this feature existed.
    """


@dataclass
class ExtractedLabel:
    """What was read off a label photo, ready to draft into the form."""

    food_name: str = ""
    serving_amount: float | None = None
    serving_unit: str = "g"
    #: registry nutrient name -> value as printed, per serving. Contains
    #: ONLY nutrients actually found on the label.
    values: dict[str, float] = field(default_factory=dict)
    #: Registry nutrients with no line on this label. Left for the RD to
    #: fill or leave alone — never defaulted to 0.
    missing: list[str] = field(default_factory=list)
    #: Anything the model wants to flag (glare, a cropped line).
    notes: str = ""

    @property
    def found_count(self) -> int:
        return len(self.values)


def label_nutrients(pack: str = DEFAULT_PACK) -> list:
    """The registry rows a Nutrition Facts panel can actually supply."""
    return [d for d in load_registry(pack) if d.on_label]


def build_output_schema(pack: str = DEFAULT_PACK) -> dict[str, Any]:
    """JSON schema for the model's reply, built from the registry.

    Every nutrient is `["number", "null"]`. The null is the whole point:
    it gives the model a correct way to say "this label has no fibre
    line", so it never has to choose between inventing a number and
    breaking the schema.
    """
    # The nullable budget is spent entirely on nutrients -- see
    # MAX_UNION_PARAMETERS. These four are plain types, using a sentinel
    # the label cannot legitimately produce: an empty string, or a
    # serving size of 0. That is safe here for the same reason 0 is a
    # safe "no target" in the targets form -- a sentinel only works when
    # the sentinel value is impossible as a real answer. No label prints
    # a 0 mL serving.
    #
    # It would NOT be safe for a nutrient, where 0 is a perfectly real
    # printed value, which is why the nutrients keep the unions.
    properties: dict[str, Any] = {
        "food_name": {
            "type": "string",
            "description": "Product name as printed. Empty string if not visible.",
        },
        "serving_amount": {
            "type": "number",
            "description": (
                "Serving size number as printed (e.g. 250 for '250 mL'). "
                "Use 0 if no serving size is visible."
            ),
        },
        "serving_unit": {
            # Deliberately no "enum". Combining an enum with a nullable
            # type is rejected outright:
            #   400 invalid_request_error -- output_config.format.schema:
            #   Enum value 'g' does not match declared type
            #   '['string', 'null']'
            # The permitted values are stated in the description, and
            # anything unexpected is coerced to "g" in
            # parse_response_json() rather than trusted -- so the
            # constraint is enforced where it actually matters.
            "type": "string",
            "description": 'Unit of the serving size: exactly "g" or "mL".',
        },
        "notes": {
            "type": "string",
            "description": "Anything unreadable or uncertain. Empty if the label was clear.",
        },
    }

    nutrients = label_nutrients(pack)
    if len(nutrients) > MAX_UNION_PARAMETERS:
        # A clear failure at build time beats an opaque 400 at call time.
        raise LabelExtractionError(
            f"The '{pack}' pack has {len(nutrients)} label nutrients, but a "
            f"response schema may contain at most {MAX_UNION_PARAMETERS} "
            "nullable fields. Split the extraction into two calls rather than "
            "making any nutrient non-nullable — a nutrient that cannot be null "
            "is a nutrient the model has to invent."
        )
    for d in nutrients:
        properties[d.name] = {
            "type": ["number", "null"],
            "description": f"{d.label} in {d.unit} per serving as printed, or null if absent.",
        }

    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def build_prompt(pack: str = DEFAULT_PACK) -> str:
    """Instructions for reading the panel.

    The traps called out here are the ones that would produce a
    confident wrong number rather than an obvious failure.
    """
    lines = "\n".join(f"- {d.name}: {d.label}, in {d.unit}" for d in label_nutrients(pack))
    return f"""Read this Nutrition Facts panel and report exactly what is printed.

Report these fields:
{lines}

Rules:
1. Report the amount PER SERVING, exactly as printed. Do not convert to
   per-100 g, and do not convert between units.
2. Use the % Daily Value column for NOTHING. "Sodium 300 mg 13 %" means
   sodium is 300, not 13. Ignore every percentage on the panel.
3. If a nutrient has no line on this label, return null for it. Do not
   infer it, calculate it from other values, or assume it is zero. A
   missing line and a printed 0 are different facts and only the printed
   0 is a measurement.
4. A printed "0 g" or "0 mg" IS a real value — report 0, not null.
5. Canadian panels are often bilingual. "Valeur nutritive", "Lipides",
   "Glucides", "Fibres", "Sucres", "Protéines", "Sodium", "Potassium",
   "Calcium", "Fer" are the same rows as their English equivalents.
6. Serving size may be printed as "Per 250 mL", "Pour 250 mL", or
   "Serving size 3/4 cup (175 g)". Report the metric amount and its unit.
7. If glare, blur or cropping makes a value uncertain, return null for
   that value and say so in notes. A null the RD can fill in is safe; a
   guess is not.
"""


def prepare_image(data: bytes, media_type: str) -> tuple[str, str]:
    """Downscale if needed and return (base64 payload, media type).

    Raises LabelExtractionError for a file type the API won't take, so
    the RD gets "use a JPEG or PNG" rather than an API error code.
    """
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise LabelExtractionError(
            f"{media_type or 'That file'} isn't a supported image type. "
            "Please upload a JPEG, PNG or WebP photo."
        )

    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is a declared dependency
        return base64.standard_b64encode(data).decode("utf-8"), media_type

    try:
        image = Image.open(BytesIO(data))
        image.load()
    except Exception as exc:  # noqa: BLE001 - shown to the RD as a message
        raise LabelExtractionError(
            "That image couldn't be opened. Try taking the photo again, or " "save it as a JPEG."
        ) from exc

    if max(image.size) <= MAX_IMAGE_DIMENSION:
        return base64.standard_b64encode(data).decode("utf-8"), media_type

    scale = MAX_IMAGE_DIMENSION / max(image.size)
    resized = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.LANCZOS,
    )
    buffer = BytesIO()
    # JPEG regardless of the input format: a photo of a printed label has
    # no transparency to preserve, and PNG of a photograph is far larger
    # for no gain in legibility.
    resized.convert("RGB").save(buffer, format="JPEG", quality=90)
    return base64.standard_b64encode(buffer.getvalue()).decode("utf-8"), "image/jpeg"


def _coerce_reading(value: Any) -> float | None:
    """A value is a number or it is absent. Nothing in between."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def parse_response_json(payload: dict[str, Any], pack: str = DEFAULT_PACK) -> ExtractedLabel:
    """Turn the model's JSON into an ExtractedLabel.

    Split out from the API call so the mapping — including the
    null-is-not-zero rule — is testable without a network or a key.
    """
    result = ExtractedLabel()
    result.food_name = str(payload.get("food_name") or "").strip()
    result.notes = str(payload.get("notes") or "").strip()
    result.serving_amount = _coerce_reading(payload.get("serving_amount"))

    unit = str(payload.get("serving_unit") or "").strip()
    result.serving_unit = unit if unit in ("g", "mL") else "g"

    for d in label_nutrients(pack):
        reading = _coerce_reading(payload.get(d.name))
        if reading is None:
            result.missing.append(d.name)
        else:
            # A negative nutrient is a misread, not a measurement.
            result.values[d.name] = max(0.0, reading)

    return result


def extract_label(
    image_bytes: bytes,
    media_type: str,
    *,
    client: Any,
    pack: str = DEFAULT_PACK,
) -> ExtractedLabel:
    """Read a Nutrition Facts photo into draft values for the form.

    Args:
        image_bytes: The uploaded photo.
        media_type:  Its MIME type, e.g. "image/jpeg".
        client:      An `anthropic.Anthropic` instance. Injected rather
                     than constructed here so tests can pass a stub and
                     so the key is read in exactly one place, in the app.
        pack:        Data pack whose label nutrients to read.

    Raises:
        LabelExtractionError: with a message fit to show the RD.
    """
    payload_b64, payload_media_type = prepare_image(image_bytes, media_type)

    try:
        response = client.messages.create(
            model=LABEL_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": payload_media_type,
                                "data": payload_b64,
                            },
                        },
                        {"type": "text", "text": build_prompt(pack)},
                    ],
                }
            ],
            output_config={"format": {"type": "json_schema", "schema": build_output_schema(pack)}},
        )
    except Exception as exc:  # noqa: BLE001 - any API failure is one message
        # Logged for whoever maintains this, shown to nobody. The first
        # real failure of this feature was a 400 caused by a bug in the
        # schema above, and the on-screen message said "the service
        # didn't respond" -- which sent the author looking at her API key
        # and her network instead of at my code. The RD still gets one
        # calm sentence; the actual reason now reaches the app logs.
        #
        # The API key is never part of an exception message, and is not
        # logged here. Only the error the service returned.
        _LOGGER.warning("Label extraction failed: %s: %s", type(exc).__name__, exc)
        raise LabelExtractionError(
            "Couldn't read the label just now. You can still type the values " "in by hand below."
        ) from exc

    try:
        text = next(block.text for block in response.content if block.type == "text")
        payload = json.loads(text)
    except (StopIteration, AttributeError, ValueError, TypeError) as exc:
        raise LabelExtractionError(
            "Couldn't make sense of the label in that photo. Try a straighter, "
            "closer shot — or type the values in by hand below."
        ) from exc

    return parse_response_json(payload, pack)
