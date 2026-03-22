from __future__ import annotations

import statistics
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from domain.models.billing import CostAnomaly, ResourceType

DEFAULT_PRICING: dict[ResourceType, Decimal] = {
    ResourceType.CPU: Decimal("0.02"),  # per hour
    ResourceType.MEMORY: Decimal("0.005"),  # per GB-hour
    ResourceType.STORAGE: Decimal("0.01"),  # per GB-day
    ResourceType.NETWORK: Decimal("0.001"),  # per GB
    ResourceType.API_CALLS: Decimal("0.0001"),  # per call
}


class CostCalculator:
    def calculate_cost(
        self,
        resource_type: ResourceType,
        quantity: Decimal,
        custom_pricing: dict[ResourceType, Decimal] | None = None,
    ) -> Decimal:
        pricing = custom_pricing if custom_pricing is not None else DEFAULT_PRICING
        unit_price = pricing.get(resource_type, Decimal("0"))
        return (quantity * unit_price).quantize(Decimal("0.000001"))

    def detect_anomaly(
        self,
        current_value: float,
        historical_values: list[float],
        threshold: float = 2.5,
    ) -> CostAnomaly | None:
        if len(historical_values) < 2:
            return None

        mean = statistics.mean(historical_values)
        stdev = statistics.stdev(historical_values)

        if stdev == 0:
            if current_value == mean:
                return None
            deviation_factor = float("inf")
        else:
            deviation_factor = abs(current_value - mean) / stdev

        if deviation_factor >= threshold:
            return CostAnomaly(
                id=uuid4(),
                expected_value=Decimal(str(round(mean, 6))),
                actual_value=Decimal(str(round(current_value, 6))),
                deviation_factor=Decimal(str(round(deviation_factor, 6))),
                detected_at=datetime.now(UTC),
                acknowledged=False,
            )

        return None
