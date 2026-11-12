"""Allow ``python -m netarchitect`` to behave exactly like the console script."""

from __future__ import annotations

from netarchitect.cli import app

if __name__ == "__main__":  # pragma: no cover - exercised by the console script
    app()
