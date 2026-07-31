"""
test_label_extract.py — tests for reading a Nutrition Facts photo
(src/label_extract.py).

No network and no API key. A stub client returns whatever JSON a test
wants, which is the only way to check the cases that matter: what happens
when the model omits a nutrient, returns nonsense, or the service falls
over. Those are the paths a live photo would almost never exercise, and
they are exactly where a wrong number would come from.

THE RULE UNDER TEST, above all others: a nutrient with no line on the
label must never arrive as 0. A printed "0 g" is a measurement; a missing
line is not, and only the RD holding the label can tell the difference.
The app already draws that distinction everywhere else (nutrient
coverage, CNF's assumed-zero provenance) and an AI shortcut is not
allowed to quietly erase it.
"""

import json

import pytest

from src.label_extract import (
    MAX_IMAGE_DIMENSION,
    ExtractedLabel,
    LabelExtractionError,
    build_output_schema,
    build_prompt,
    extract_label,
    label_nutrients,
    parse_response_json,
    prepare_image,
)

# ---------------------------------------------------------------------------
# Stub client — stands in for anthropic.Anthropic
# ---------------------------------------------------------------------------


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Response:
    def __init__(self, text):
        self.content = [_Block(text)]


class StubClient:
    """Returns canned JSON and records what it was sent."""

    def __init__(self, payload=None, raise_with=None, text=None):
        self.payload = payload
        self.raise_with = raise_with
        self.text = text
        self.calls = []

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_with is not None:
            raise self.raise_with
        return _Response(self.text if self.text is not None else json.dumps(self.payload))


def _png_bytes(width=40, height=40):
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


FULL_LABEL = {
    "food_name": "Ensure Plus Vanilla",
    "serving_amount": 235,
    "serving_unit": "mL",
    "energy_kcal": 350,
    "fat_g": 11,
    "saturated_fat_g": 1.5,
    "trans_fat_g": 0,
    "carbohydrate_g": 50,
    "fibre_g": None,
    "sugars_g": 18,
    "protein_g": 13,
    "cholesterol_mg": None,
    "sodium_mg": 240,
    "potassium_mg": None,
    "calcium_mg": 330,
    "iron_mg": 4.2,
    "notes": "",
}


# ---------------------------------------------------------------------------
# The never-fabricate rule
# ---------------------------------------------------------------------------


class TestNeverFabricates:
    def test_a_missing_line_is_reported_missing_not_zero(self):
        """The most important test in this file.

        This label has no fibre, cholesterol or potassium line. If those
        arrived as 0, an RD would read "0 g fibre" as a measurement and a
        blend built from it would under-report fibre with no warning.
        """
        result = parse_response_json(FULL_LABEL)

        assert "fibre_g" not in result.values
        assert "cholesterol_mg" not in result.values
        assert "potassium_mg" not in result.values
        assert set(result.missing) == {"fibre_g", "cholesterol_mg", "potassium_mg"}

    def test_a_printed_zero_is_kept_as_a_real_value(self):
        """The other half of the same rule. Trans fat is printed 0 g on
        this label, and that IS a measurement -- it must survive."""
        result = parse_response_json(FULL_LABEL)
        assert result.values["trans_fat_g"] == 0.0
        assert "trans_fat_g" not in result.missing

    def test_every_label_nutrient_is_either_found_or_missing(self):
        """No nutrient may fall down the gap between the two lists."""
        result = parse_response_json(FULL_LABEL)
        expected = {d.name for d in label_nutrients()}
        assert set(result.values) | set(result.missing) == expected
        assert not set(result.values) & set(result.missing)

    def test_an_empty_reply_reports_everything_missing_and_nothing_zero(self):
        """A photo of a blank page must not produce a food made of zeros."""
        result = parse_response_json({})
        assert result.values == {}
        assert set(result.missing) == {d.name for d in label_nutrients()}

    def test_a_negative_value_is_clamped(self):
        """A misread minus sign is not a measurement of negative sodium."""
        result = parse_response_json({**FULL_LABEL, "sodium_mg": -240})
        assert result.values["sodium_mg"] == 0.0

    def test_non_numeric_values_are_treated_as_absent(self):
        result = parse_response_json({**FULL_LABEL, "sodium_mg": "about 240"})
        assert "sodium_mg" not in result.values
        assert "sodium_mg" in result.missing


# ---------------------------------------------------------------------------
# Schema and prompt are built from the registry, not hardcoded
# ---------------------------------------------------------------------------


class TestBuiltFromTheRegistry:
    def test_schema_covers_exactly_the_label_nutrients(self):
        schema = build_output_schema()
        for d in label_nutrients():
            assert d.name in schema["properties"], d.name
        assert schema["additionalProperties"] is False

    def test_every_nutrient_is_nullable(self):
        """The null is what lets the model say "not on this label"
        without either inventing a number or breaking the schema."""
        schema = build_output_schema()
        for d in label_nutrients():
            assert schema["properties"][d.name]["type"] == ["number", "null"], d.name

    def test_prompt_names_every_nutrient_with_its_unit(self):
        prompt = build_prompt()
        for d in label_nutrients():
            assert d.name in prompt, d.name
            assert d.unit in prompt

    def test_prompt_warns_off_the_percent_daily_value_column(self):
        """ "Sodium 300 mg 13 %" -- reading 13 would be a plausible,
        invisible, badly wrong answer."""
        prompt = build_prompt()
        assert "Daily Value" in prompt


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


class TestImageHandling:
    def test_a_small_image_is_passed_through_untouched(self):
        payload, media_type = prepare_image(_png_bytes(40, 40), "image/png")
        assert media_type == "image/png"
        assert payload

    def test_a_large_photo_is_downscaled(self):
        """A 12-megapixel phone shot is resized before it is sent anyway,
        so uploading it whole costs time and tokens for no more detail.

        Checks the decoded PIXEL dimensions, not the byte count: base64
        inflates by a third, and a synthetic flat-colour PNG compresses
        far better than any JPEG of it, so comparing sizes would fail on
        a correct implementation.
        """
        import base64
        from io import BytesIO

        from PIL import Image

        big = _png_bytes(MAX_IMAGE_DIMENSION * 2, MAX_IMAGE_DIMENSION * 2)
        payload, media_type = prepare_image(big, "image/png")

        assert media_type == "image/jpeg"
        sent = Image.open(BytesIO(base64.standard_b64decode(payload)))
        assert max(sent.size) == MAX_IMAGE_DIMENSION, sent.size
        assert sent.width == sent.height, "aspect ratio must be preserved"

    def test_downscaling_preserves_a_non_square_aspect_ratio(self):
        import base64
        from io import BytesIO

        from PIL import Image

        payload, _ = prepare_image(
            _png_bytes(MAX_IMAGE_DIMENSION * 2, MAX_IMAGE_DIMENSION), "image/png"
        )
        sent = Image.open(BytesIO(base64.standard_b64decode(payload)))
        assert max(sent.size) == MAX_IMAGE_DIMENSION
        assert sent.width == 2 * sent.height

    def test_an_unsupported_file_type_is_refused_readably(self):
        with pytest.raises(LabelExtractionError) as excinfo:
            prepare_image(b"%PDF-1.4", "application/pdf")
        assert "JPEG" in str(excinfo.value)

    def test_a_corrupt_image_is_refused_readably(self):
        with pytest.raises(LabelExtractionError) as excinfo:
            prepare_image(b"not an image at all", "image/png")
        assert "couldn't be opened" in str(excinfo.value).lower()


# ---------------------------------------------------------------------------
# The call itself
# ---------------------------------------------------------------------------


class TestExtractLabel:
    def test_a_good_photo_produces_drafts(self):
        client = StubClient(payload=FULL_LABEL)
        result = extract_label(_png_bytes(), "image/png", client=client)

        assert isinstance(result, ExtractedLabel)
        assert result.food_name == "Ensure Plus Vanilla"
        assert result.serving_amount == 235.0
        assert result.serving_unit == "mL"
        assert result.values["sodium_mg"] == 240.0

    def test_the_request_carries_the_image_and_the_schema(self):
        client = StubClient(payload=FULL_LABEL)
        extract_label(_png_bytes(), "image/png", client=client)

        sent = client.calls[0]
        assert sent["model"].startswith("claude-haiku")
        blocks = sent["messages"][0]["content"]
        assert blocks[0]["type"] == "image"
        assert blocks[0]["source"]["type"] == "base64"
        assert sent["output_config"]["format"]["type"] == "json_schema"

    def test_an_api_failure_becomes_a_readable_message(self):
        """And the message must point at the fallback: type it by hand.
        A failed shortcut is an inconvenience, not a dead end."""
        client = StubClient(raise_with=RuntimeError("connection reset"))
        with pytest.raises(LabelExtractionError) as excinfo:
            extract_label(_png_bytes(), "image/png", client=client)
        assert "by hand" in str(excinfo.value)

    def test_the_api_error_text_is_not_leaked_to_the_rd(self):
        """Exception text from an API client can carry request details."""
        client = StubClient(raise_with=RuntimeError("x-api-key sk-ant-secret"))
        with pytest.raises(LabelExtractionError) as excinfo:
            extract_label(_png_bytes(), "image/png", client=client)
        assert "sk-ant" not in str(excinfo.value)

    def test_an_unparseable_reply_becomes_a_readable_message(self):
        client = StubClient(text="I'm afraid I can't read that label.")
        with pytest.raises(LabelExtractionError) as excinfo:
            extract_label(_png_bytes(), "image/png", client=client)
        assert "by hand" in str(excinfo.value)

    def test_a_serving_unit_we_dont_use_falls_back_to_grams(self):
        client = StubClient(payload={**FULL_LABEL, "serving_unit": "oz"})
        result = extract_label(_png_bytes(), "image/png", client=client)
        assert result.serving_unit == "g"
