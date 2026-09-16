"""Thread Digest: a personal, rules-compliant Reddit reader."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("threaddigest")
except PackageNotFoundError:  # pragma: no cover - editable installs always resolve
    __version__ = "0.0.0"

__all__ = ["__version__"]
