"""Catch a Brightway environment that bw2data itself will crash in, before we open a project.

bw2data 4.x applies automatic updates when a project is opened, and one of them
(``fix_migrations_filename``) does ``import bw2io``. bw2io < 0.9 was written for
legacy bw2data, whose ``__version__`` was a tuple; against bw2data 4 it dies at
import time with ``TypeError: '<' not supported between instances of 'str' and
'tuple'``. The mix shows up in Activity Browser environments where bw2data was
upgraded on its own. We read the installed bw2io version from package metadata
(never by importing it) and name the fix.
"""

from __future__ import annotations

import re
from importlib import metadata

MIN_BW2IO_FOR_BW2DATA_4 = (0, 9)
BW2IO_FIX = 'pip install -U "bw2io>=0.9.3"'


class IncompatibleEnvironmentError(RuntimeError):
    """The installed Brightway packages cannot work together; the message names the fix."""


def _parse(version: object) -> tuple[int, ...]:
    """Leading integer components of a version given as ``"4.7"``, ``"0.9.17"`` or ``(4, 7)``."""
    if isinstance(version, tuple):
        parts = []
        for part in version:
            if not isinstance(part, int):
                break
            parts.append(part)
        return tuple(parts)
    parts = []
    for piece in str(version).split("."):
        match = re.match(r"\d+", piece)
        if match is None:
            break
        parts.append(int(match.group()))
    return tuple(parts)


def _installed_version(name: str) -> str | None:
    """Version of an installed distribution without importing it; None if absent."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def bw2io_conflict(bw2data_version: object, bw2io_version: str | None) -> str | None:
    """The message to show when bw2data >= 4 sits next to bw2io < 0.9, else None."""
    if bw2io_version is None:
        return None
    if _parse(bw2data_version)[:1] < (4,):
        return None
    if _parse(bw2io_version) >= MIN_BW2IO_FOR_BW2DATA_4:
        return None
    bd = (
        bw2data_version
        if isinstance(bw2data_version, str)
        else ".".join(map(str, bw2data_version))
    )
    return (
        f"bw2io {bw2io_version} cannot run next to bw2data {bd}: bw2data 4 imports bw2io "
        f"while opening a project, and bw2io < 0.9 fails at import against bw2data 4 "
        f"(TypeError: '<' not supported between instances of 'str' and 'tuple'). "
        f"Upgrade it in this Python environment first: {BW2IO_FIX}"
    )


def check_environment(bd) -> None:
    """Raise IncompatibleEnvironmentError before ``bd.projects.set_current`` can crash."""
    message = bw2io_conflict(getattr(bd, "__version__", "0"), _installed_version("bw2io"))
    if message is not None:
        raise IncompatibleEnvironmentError(message)
