"""Tests for src/domain/services/cost_calculator.py"""

from decimal import Decimal

import pytest

from domain.models.billing import CostAnomaly, ResourceType
from domain.services.cost_calculator import CostCalculator


@pytest.fixture
def calculator():
    return CostCalculator()


class TestCalculateCost:
    @pytest.mark.parametrize(
        "resource_type, expected_price",
        [
            (ResourceType.CPU, Decimal("0.02")),
            (ResourceType.MEMORY, Decimal("0.005")),
            (ResourceType.STORAGE, Decimal("0.01")),
            (ResourceType.NETWORK, Decimal("0.001")),
            (ResourceType.API_CALLS, Decimal("0.0001")),
        ],
    )
    def test_default_pricing(self, calculator, resource_type, expected_price):
        quantity = Decimal("100")
        result = calculator.calculate_cost(resource_type, quantity)
        expected = (quantity * expected_price).quantize(Decimal("0.000001"))
        assert result == expected

    def test_custom_pricing(self, calculator):
        custom = {ResourceType.CPU: Decimal("0.10")}
        result = calculator.calculate_cost(ResourceType.CPU, Decimal("100"), custom_pricing=custom)
        assert result == Decimal("10.000000")

    def test_custom_pricing_missing_type_returns_zero(self, calculator):
        custom = {ResourceType.CPU: Decimal("0.10")}
        result = calculator.calculate_cost(
            ResourceType.STORAGE, Decimal("100"), custom_pricing=custom
        )
        assert result == Decimal("0.000000")

    def test_zero_quantity(self, calculator):
        result = calculator.calculate_cost(ResourceType.CPU, Decimal("0"))
        assert result == Decimal("0.000000")


class TestDetectAnomaly:
    def test_returns_none_with_empty_history(self, calculator):
        assert calculator.detect_anomaly(10.0, []) is None

    def test_returns_none_with_single_value(self, calculator):
        assert calculator.detect_anomaly(10.0, [5.0]) is None

    def test_returns_anomaly_when_exceeds_threshold(self, calculator):
        historical = [10.0, 12.0, 11.0, 10.5, 11.5]
        result = calculator.detect_anomaly(30.0, historical)
        assert isinstance(result, CostAnomaly)

    def test_anomaly_fields(self, calculator):
        historical = [10.0, 12.0, 11.0, 10.5, 11.5]
        result = calculator.detect_anomaly(30.0, historical)
        assert result.actual_value == Decimal(str(round(30.0, 6)))
        assert result.acknowledged is False

    def test_returns_none_when_within_range(self, calculator):
        historical = [10.0, 12.0, 11.0, 10.5, 11.5]
        result = calculator.detect_anomaly(11.0, historical)
        assert result is None

    def test_flat_historical_same_value_returns_none(self, calculator):
        historical = [5.0, 5.0, 5.0, 5.0]
        result = calculator.detect_anomaly(5.0, historical)
        assert result is None

    def test_flat_historical_different_value_returns_anomaly(self, calculator):
        historical = [5.0, 5.0, 5.0, 5.0]
        result = calculator.detect_anomaly(6.0, historical)
        assert isinstance(result, CostAnomaly)
        assert result.deviation_factor == Decimal("Infinity")
