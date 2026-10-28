"""Module for testing calling functions in the pattern section."""

from pathlib import Path


def callfunc1(path: Path, env: dict, a=None) -> dict:
    """Call function."""
    return {"a": a}
