"""Domain-specific exceptions.

Using dedicated exception types lets the CLI map failures to meaningful exit
codes (validation vs. address-space exhaustion) instead of printing tracebacks.
"""


class NetArchitectError(Exception):
    """Base class for all expected engine errors."""


class PhysicalDistanceViolationError(NetArchitectError):
    """Raised when a requested cable type cannot cover the requested distance."""


class OpticalBudgetViolationError(PhysicalDistanceViolationError):
    """Raised when the link distance exceeds the transceiver's optical budget."""


class AddressSpaceExhaustedError(NetArchitectError):
    """Raised when the requested subnets do not fit inside the root prefix."""


class OverlapError(NetArchitectError):
    """Raised if the allocator ever produces overlapping subnets (safety net)."""
