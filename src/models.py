"""
models.py — Data structures for the Blenderized Tube Feed Calculator.

Phase 3 of the BTF Calculator.

These @dataclass types are the domain objects that flow through the
calculator, report, and UI layers. They carry no logic beyond simple
derived properties (densities, daily-volume calculation).

Key design decisions (from CONTEXT.md §1):
  - Recipe carries ingredients + added water + MEASURED final volume.
    Volume is measured, not computed — blending/air/rinse water make
    it incalculable from ingredient weights alone.
  - NutrientProfile stores per-recipe totals and computes densities
    using measured volume as the denominator.
  - Delivery encodes the three real-world delivery methods (syringe
    bolus, pump, direct) and computes daily volume from them.
"""

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Recipe-building blocks
# ---------------------------------------------------------------------------


@dataclass
class Ingredient:
    """A single food in a BTF recipe, with the grams actually used.

    Attributes:
        food_code:        CNF Food_Code (links to Nutrient_Amount table).
        food_description: Human-readable name (from Food_Name.csv).
        grams:            Grams of this food in the recipe (actual amount used).
    """

    food_code: int
    food_description: str
    grams: float


@dataclass
class Recipe:
    """A complete BTF recipe — what went into the blender + measured output.

    The recipe already works (someone is living on it). The tool
    characterizes it, doesn't design it.

    Attributes:
        name:                    Recipe label (e.g. "Chicken-veg blend").
        ingredients:             List of Ingredient objects with grams.
        added_water_mL:          Water added during blending (not from food).
        measured_final_volume_mL: Volume the user measured after blending
                                 (poured into a container and read the mark).
                                 This is the denominator for all densities.
    """

    name: str = ""
    ingredients: list[Ingredient] = field(default_factory=list)
    added_water_mL: float = 0.0
    measured_final_volume_mL: float = 0.0


# ---------------------------------------------------------------------------
# Calculated output
# ---------------------------------------------------------------------------


@dataclass
class NutrientProfile:
    """Nutrient totals for a recipe + derived densities.

    Built by calculator.calculate_profile(). The totals dict is keyed by
    internal nutrient names (see calculator.NUTRIENT_CODES), e.g.
    "energy_kcal", "protein_g", "water_g".

    Densities use measured_final_volume_mL as the denominator — this is
    the core design commitment: per-mL is the primary lens.

    Attributes:
        nutrient_totals:          Dict of nutrient_name → total amount in recipe.
        measured_final_volume_mL: The measured blend volume (denominator).
        added_water_mL:           Water added during blending (for free-water calc).
    """

    nutrient_totals: dict[str, float] = field(default_factory=dict)
    measured_final_volume_mL: float = 0.0
    added_water_mL: float = 0.0

    # -- Density properties (the primary outputs) ---------------------------

    @property
    def kcal_per_mL(self) -> float:
        """Energy density: kcal per mL of blend."""
        if self.measured_final_volume_mL <= 0:
            return 0.0
        return self.nutrient_totals.get("energy_kcal", 0.0) / self.measured_final_volume_mL

    @property
    def protein_per_mL(self) -> float:
        """Protein density: grams of protein per mL of blend."""
        if self.measured_final_volume_mL <= 0:
            return 0.0
        return self.nutrient_totals.get("protein_g", 0.0) / self.measured_final_volume_mL

    @property
    def free_water_fraction(self) -> float:
        """Free-water fraction: (food water + added water) / blend volume.

        Water from food ingredients comes from CNF moisture values (Nutrient_Code 255).
        Added water is the user's added_water_mL. Together they give the
        total free water in the blend, expressed as a fraction of volume.

        Uses the clinical approximation 1 g water ≈ 1 mL.
        """
        if self.measured_final_volume_mL <= 0:
            return 0.0
        food_water = self.nutrient_totals.get("water_g", 0.0)
        total_water = food_water + self.added_water_mL
        return total_water / self.measured_final_volume_mL

    @property
    def total_kcal(self) -> float:
        """Total kcal in the entire recipe."""
        return self.nutrient_totals.get("energy_kcal", 0.0)

    @property
    def total_protein_g(self) -> float:
        """Total protein (g) in the entire recipe."""
        return self.nutrient_totals.get("protein_g", 0.0)

    @property
    def total_water_g(self) -> float:
        """Total water (g) from food ingredients only (not added water)."""
        return self.nutrient_totals.get("water_g", 0.0)


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


class DeliveryMethod(Enum):
    """How the feed is administered to the patient.

    SYRINGE_BOLUS: The primary method for BTF (AHS handbook: "Home blended
        food is mostly offered by syringe as the blend may be thicker
        than formula"). User enters mL per bolus × times per day.
    PUMP: Continuous drip via enteral pump. Less common for BTF (AHS:
        "Pumps are not routinely provided because their design does not
        work well with home blended food"). User enters mL/hr × hours/day.
    DIRECT: User already knows the total daily volume and enters it directly.
    """

    SYRINGE_BOLUS = "syringe_bolus"
    PUMP = "pump"
    DIRECT = "direct"


@dataclass
class Delivery:
    """Delivery parameters — how the feed gets to the patient.

    Only the fields relevant to the chosen method need to be set;
    the rest default to 0.

    Attributes:
        method:         One of SYRINGE_BOLUS, PUMP, DIRECT.
        bolus_volume_mL:  mL per bolus (syringe method).
        times_per_day:    Number of boluses per day (syringe method).
        rate_mL_per_hr:   Pump rate in mL/hour (pump method).
        hours_per_day:    Hours the pump runs per day (pump method).
        daily_volume_mL:  Direct entry of total daily volume (direct method).
    """

    method: DeliveryMethod = DeliveryMethod.DIRECT
    bolus_volume_mL: float = 0.0
    times_per_day: float = 0.0
    rate_mL_per_hr: float = 0.0
    hours_per_day: float = 0.0
    daily_volume_mL: float = 0.0

    @property
    def calculated_daily_volume_mL(self) -> float:
        """Compute total daily volume (mL) from the delivery parameters.

        Syringe bolus:  bolus_volume_mL × times_per_day
        Pump:           rate_mL_per_hr × hours_per_day
        Direct:         daily_volume_mL (user-entered)
        """
        if self.method == DeliveryMethod.SYRINGE_BOLUS:
            return self.bolus_volume_mL * self.times_per_day
        elif self.method == DeliveryMethod.PUMP:
            return self.rate_mL_per_hr * self.hours_per_day
        else:
            return self.daily_volume_mL