"""The installed distribution version, with a fallback for an uninstalled source tree."""

from __future__ import annotations

import importlib.metadata

FALLBACK_VERSION = "0.1.0"


def _version() -> str:
    try:
        return importlib.metadata.version("sentier-brightway")
    except importlib.metadata.PackageNotFoundError:
        return FALLBACK_VERSION


__version__ = _version()
