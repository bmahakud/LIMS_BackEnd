from decimal import Decimal
import re
from typing import Optional, Tuple
from .models import ComparisonQualifier


class CalculationRegistry:
    """
    Registry for verified refractory calculation formulas.
    Only enables formulas supported by verified ISO/ASTM laboratory specifications.
    Provides verified manual-entry fallbacks until automated formulas are certified.
    """

    @staticmethod
    def parse_qualified_input(raw_text: str) -> Tuple[Optional[Decimal], str]:
        """
        Parses text like '>1680', '<0.05', '>=85.0', or '2.89' into (numeric_value, qualifier).
        Never treats an observation such as '>1600' as an exact value of 1600.
        """
        raw = raw_text.strip()
        if not raw:
            return None, ComparisonQualifier.NONE

        if raw.startswith('>='):
            val_str = raw[2:].strip()
            qual = ComparisonQualifier.GREATER_THAN_OR_EQUAL
        elif raw.startswith('<='):
            val_str = raw[2:].strip()
            qual = ComparisonQualifier.LESS_THAN_OR_EQUAL
        elif raw.startswith('>'):
            val_str = raw[1:].strip()
            qual = ComparisonQualifier.GREATER_THAN
        elif raw.startswith('<'):
            val_str = raw[1:].strip()
            qual = ComparisonQualifier.LESS_THAN
        elif raw.startswith('~'):
            val_str = raw[1:].strip()
            qual = ComparisonQualifier.APPROX
        else:
            val_str = raw
            qual = ComparisonQualifier.NONE

        try:
            num = Decimal(val_str)
            return num, qual
        except Exception:
            return None, qual

    @classmethod
    def calculate_cold_crushing_strength(cls, peak_load_n: Decimal, area_mm2: Decimal) -> Decimal:
        """
        ISO 10059-1: CCS (MPa) = F_max (N) / A (mm²)
        1 N/mm² = 1 MPa.
        """
        if area_mm2 <= Decimal('0'):
            raise ValueError("Cross-sectional area must be positive.")
        return (peak_load_n / area_mm2).quantize(Decimal('0.1'))

    @classmethod
    def calculate_bulk_density(
        cls,
        dry_mass_g: Decimal,
        soaked_mass_g: Decimal,
        hydrostatic_mass_g: Decimal,
        water_density_g_cm3: Decimal = Decimal('1.000')
    ) -> Decimal:
        """
        ISO 5017: Bulk Density = [m1 / (m3 - m2)] * rho_liq
        m1 = dry mass, m2 = apparent mass in water, m3 = soaked mass in air.
        """
        denom = soaked_mass_g - hydrostatic_mass_g
        if denom <= Decimal('0'):
            raise ValueError("Bulk volume (soaked mass - hydrostatic mass) must be positive.")
        return ((dry_mass_g / denom) * water_density_g_cm3).quantize(Decimal('0.01'))

    @classmethod
    def calculate_apparent_porosity(
        cls,
        dry_mass_g: Decimal,
        soaked_mass_g: Decimal,
        hydrostatic_mass_g: Decimal
    ) -> Decimal:
        """
        ISO 5017: Apparent Porosity (%) = [(m3 - m1) / (m3 - m2)] * 100
        """
        denom = soaked_mass_g - hydrostatic_mass_g
        if denom <= Decimal('0'):
            raise ValueError("Bulk volume must be positive.")
        return (((soaked_mass_g - dry_mass_g) / denom) * Decimal('100.0')).quantize(Decimal('0.1'))
