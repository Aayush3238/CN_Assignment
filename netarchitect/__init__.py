"""NetArchitect: explainable network planning and Cisco IOS generation.

The public API is deliberately small.  Everything funnels through
:func:`netarchitect.core.design.analyze`, which both the CLI and the web
dashboard call.  Neither interface recalculates masks or optical loss.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
