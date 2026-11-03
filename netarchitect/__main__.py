"""Allow ``python -m netarchitect`` to behave like the installed console script."""

from netarchitect.cli import app

if __name__ == "__main__":
    app()
