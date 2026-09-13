"""Insight Miner: a personal, rules-compliant Reddit harvester."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("insightminer")
except PackageNotFoundError:  # pragma: no cover - editable installs always resolve
    __version__ = "0.0.0"

__all__ = ["__version__"]
