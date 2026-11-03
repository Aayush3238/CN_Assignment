"""NetArchitect: explainable network architecture recommendation engine.

The package is deliberately split into a headless ``core`` layer (pure rule
engine + data models) and a thin ``cli`` adapter. Keeping the engine free of
terminal/UI concerns makes it easy to test and, if needed later, wrap in an API.
"""

__version__ = "0.1.0"

from netarchitect.core.engine import run_scenario

__all__ = ["__version__", "run_scenario"]
