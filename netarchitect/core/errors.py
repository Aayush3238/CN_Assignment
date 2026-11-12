"""Typed failures used by the engines.

The CLI maps these to stable exit codes and the API returns a 400 with the
same message.  Boundary errors are deliberately explicit rather than silently
clamped, which is what the specification asks for.
"""

from __future__ import annotations


class NetArchitectError(Exception):
    """Base class for every expected, user-facing failure."""


class InvalidParameterError(NetArchitectError):
    """A scenario value is missing, the wrong type, or out of range."""


class PhysicalDistanceViolationError(NetArchitectError):
    """Copper was requested past its 100 m channel limit."""


class AddressSpaceExhaustedError(NetArchitectError):
    """A subnet request cannot fit inside the supplied root prefix."""


class OverlapError(NetArchitectError):
    """Two allocated blocks overlap.  This is a safety net, not a user error."""
