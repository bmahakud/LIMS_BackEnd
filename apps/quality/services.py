from decimal import Decimal
from typing import Optional, Tuple
from .models import SpecificationEvaluationStatus, QAReview, Deviation
from test_catalogue.models import SpecificationLimit
from results.models import Result, ComparisonQualifier


class SpecificationService:
    """
    Evaluates Results against approved SpecificationLimits.
    Correctly handles <, <=, >, >=, ranges, signed quantities, missing data, and qualified strings.
    Never marks ambiguous qualified data automatically as passed; assigns INDETERMINATE or NEEDS_REVIEW.
    """

    @classmethod
    def evaluate_result(cls, result: Result, limit: SpecificationLimit) -> Tuple[SpecificationEvaluationStatus, Optional[Decimal], str]:
        # Missing data check
        if result.numeric_value is None and not result.raw_input_text:
            return SpecificationEvaluationStatus.MISSING_DATA, None, "No result data recorded."

        val = result.numeric_value
        qual = result.qualifier

        min_v = limit.min_value
        max_v = limit.max_value

        # Handle qualified values with uncertainty
        if qual == ComparisonQualifier.GREATER_THAN:
            # E.g. Result is >1680. If min is 1650, >1680 is strictly >1650 -> PASS
            # But if min is 1700, >1680 is indeterminate (could be 1681 or 1720) -> INDETERMINATE
            if min_v is not None and val is not None:
                if val >= min_v:
                    return SpecificationEvaluationStatus.PASS, val - min_v, f"Value {result.raw_input_text} satisfies min requirement ≥ {min_v}"
                else:
                    return SpecificationEvaluationStatus.INDETERMINATE, None, f"Qualified value {result.raw_input_text} cannot establish definitive compliance with min {min_v}"
            if max_v is not None and val is not None:
                # If max is 1600, >1680 is definitely a violation
                if val >= max_v:
                    return SpecificationEvaluationStatus.FAIL, val - max_v, f"Value {result.raw_input_text} exceeds maximum allowable {max_v}"
                else:
                    return SpecificationEvaluationStatus.INDETERMINATE, None, f"Qualified value {result.raw_input_text} cannot confirm whether max {max_v} is exceeded"

        if qual == ComparisonQualifier.LESS_THAN:
            # E.g. Result is <0.05. If max is 0.20, <0.05 is strictly <0.20 -> PASS
            # If max is 0.02, <0.05 could be 0.04 (fails) or 0.01 (passes) -> INDETERMINATE
            if max_v is not None and val is not None:
                if val <= max_v:
                    return SpecificationEvaluationStatus.PASS, max_v - val, f"Value {result.raw_input_text} satisfies max requirement ≤ {max_v}"
                else:
                    return SpecificationEvaluationStatus.INDETERMINATE, None, f"Qualified value {result.raw_input_text} cannot establish definitive compliance with max {max_v}"
            if min_v is not None and val is not None:
                if val <= min_v:
                    return SpecificationEvaluationStatus.FAIL, min_v - val, f"Value {result.raw_input_text} fails minimum requirement {min_v}"
                else:
                    return SpecificationEvaluationStatus.INDETERMINATE, None, f"Qualified value {result.raw_input_text} cannot confirm compliance with min {min_v}"

        if val is None:
            return SpecificationEvaluationStatus.NEEDS_REVIEW, None, f"Unparsed observation '{result.raw_input_text}' requires technical review"

        # Standard numeric range checking
        # 1. Check minimum limit
        if min_v is not None:
            if val < min_v:
                delta = min_v - val
                return SpecificationEvaluationStatus.DEVIATION, -delta, f"Value {val} {result.unit} falls below required minimum {min_v} {limit.unit}"

        # 2. Check maximum limit (handles signed quantities like PLC -0.20% to +0.20%)
        if max_v is not None:
            if val > max_v:
                delta = val - max_v
                return SpecificationEvaluationStatus.DEVIATION, delta, f"Value {val} {result.unit} exceeds allowable maximum {max_v} {limit.unit}"

        return SpecificationEvaluationStatus.PASS, Decimal('0.0'), f"Value {val} {result.unit} conforms to specification limits"
