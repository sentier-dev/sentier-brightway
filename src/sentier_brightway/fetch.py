"""Resolve where Sentier data is read from: a local checkout or a verified download cache."""

from __future__ import annotations

import hashlib
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Mapping

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from platformdirs import user_cache_dir

ENV_VAR = "SENTIER_DATA_ROOT"
RAW = "https://raw.githubusercontent.com"
_OFFLINE_HINT = (
    "offline or unreachable commit? set SENTIER_DATA_ROOT to a local checkout of the four "
    "Sentier data repos"
)


class FetchError(RuntimeError):
    """A pinned file could not be downloaded to, or written into, the local cache."""


class IntegrityError(FetchError):
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
    text = (
        resources.files("sentier_brightway").joinpath("sources.toml").read_text(encoding="utf-8")
    )
    return parse_manifest(text)


def manifest_key(manifest: tuple[Source, ...]) -> str:
    """Stable cache-directory name covering every source's name, repo, ref and file digests.

    Changing any single ref, or any single file's pinned sha256, changes this key, so a stale
    cache is never mistaken for a fresh one. Nothing prunes old key directories yet (each is
    roughly the size of the manifest's payload, ~36 MB for the current one)."""
    parts = []
    for source in manifest:
        files = ",".join(f"{path}={digest}" for path, digest in sorted(source.files.items()))
        parts.append(f"{source.name}|{source.repo}|{source.ref}|{files}")
    canonical = "\n".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 - fixed https host
        return resp.read()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(target: Path, data: bytes) -> None:
    tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)


def materialize(manifest: tuple[Source, ...], cache_dir: Path) -> Path:
    """Ensure every pinned file exists in ``cache_dir`` with the right hash; return the root."""
    for source in manifest:
        root = cache_dir / source.name
        for path, expected in source.files.items():
            target = root / path
            if target.is_file() and _sha256(target.read_bytes()) == expected:
                continue
            url = source.url(path)
            try:
                data = _download(url)
            except urllib.error.URLError as exc:
                raise FetchError(f"failed to download {url}: {exc}; {_OFFLINE_HINT}") from exc
            actual = _sha256(data)
            if actual != expected:
                raise IntegrityError(f"{url}: expected sha256 {expected}, got {actual}")
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(target, data)
            except OSError as exc:
                raise FetchError(f"failed to write {target}: {exc}; {_OFFLINE_HINT}") from exc
    return cache_dir


def default_cache_dir() -> Path:
    return Path(user_cache_dir("sentier-brightway"))


def resolve_data_root(data_root: Path | str | None) -> Path:
    """Explicit argument, then ``$SENTIER_DATA_ROOT``, then the verified download cache.

    The argument and the env var are both ``expanduser()``-ed and must already exist as a
    directory (a ``~/dds``-shaped local checkout); only the download-cache path is created on
    demand, since it is the one path this package is allowed to write to."""
    if data_root is not None:
        path = Path(data_root).expanduser()
        if not path.is_dir():
            raise FileNotFoundError(f"data_root argument does not exist: {path}")
        return path
    env_value = os.environ.get(ENV_VAR)
    if env_value:
        path = Path(env_value).expanduser()
        if not path.is_dir():
            raise FileNotFoundError(f"${ENV_VAR} does not exist: {path}")
        return path
    manifest = load_packaged_manifest()
    cache = default_cache_dir() / manifest_key(manifest)
    return materialize(manifest, cache_dir=cache)
