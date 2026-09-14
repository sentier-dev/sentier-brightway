"""Resolve where Sentier data is read from: a local checkout or a verified download cache."""

from __future__ import annotations

import hashlib
import os
import tomllib
import urllib.request
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Mapping

from platformdirs import user_cache_dir

ENV_VAR = "SENTIER_DATA_ROOT"
RAW = "https://raw.githubusercontent.com"


class IntegrityError(RuntimeError):
    """A downloaded file does not match the sha256 pinned in sources.toml."""


@dataclass(frozen=True)
class Source:
    name: str  # folder name under the data root, e.g. sentier-inventory
    repo: str  # GitHub owner/name
    ref: str  # commit sha
    files: Mapping[str, str]  # repo-relative path -> sha256

    def url(self, path: str) -> str:
        return f"{RAW}/{self.repo}/{self.ref}/{path}"


def parse_manifest(text: str) -> tuple[Source, ...]:
    data = tomllib.loads(text)
    return tuple(
        Source(name=s["name"], repo=s["repo"], ref=s["ref"], files=dict(s["files"]))
        for s in data["source"]
    )


def load_packaged_manifest() -> tuple[Source, ...]:
    text = resources.files("sentier_brightway").joinpath("sources.toml").read_text()
    return parse_manifest(text)


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 - fixed https host
        return resp.read()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def materialize(manifest: tuple[Source, ...], cache_dir: Path) -> Path:
    """Ensure every pinned file exists in ``cache_dir`` with the right hash; return the root."""
    for source in manifest:
        root = cache_dir / source.name
        for path, expected in source.files.items():
            target = root / path
            if target.is_file() and _sha256(target.read_bytes()) == expected:
                continue
            data = _download(source.url(path))
            actual = _sha256(data)
            if actual != expected:
                raise IntegrityError(
                    f"{source.url(path)}: expected sha256 {expected}, got {actual}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return cache_dir


def default_cache_dir() -> Path:
    return Path(user_cache_dir("sentier-brightway"))


def resolve_data_root(data_root: Path | str | None) -> Path:
    """Explicit argument, then ``$SENTIER_DATA_ROOT``, then the verified download cache."""
    if data_root is not None:
        return Path(data_root)
    if os.environ.get(ENV_VAR):
        return Path(os.environ[ENV_VAR])
    manifest = load_packaged_manifest()
    cache = default_cache_dir() / manifest[0].ref[:12]
    return materialize(manifest, cache_dir=cache)
