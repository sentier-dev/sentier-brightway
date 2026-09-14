import hashlib

import pytest

from sentier_brightway import fetch


def _toml(sha: str) -> str:
    return f"""
[[source]]
name = "sentier-inventory"
repo = "sentier-dev/sentier-inventory"
ref = "0123456789abcdef0123456789abcdef01234567"
[source.files]
"data/02-electricity/processes.parquet" = "{sha}"
"""


def test_explicit_data_root_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIER_DATA_ROOT", str(tmp_path / "env"))
    assert fetch.resolve_data_root(tmp_path / "arg") == tmp_path / "arg"


def test_env_var_is_used_when_no_argument(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIER_DATA_ROOT", str(tmp_path / "env"))
    assert fetch.resolve_data_root(None) == tmp_path / "env"


def test_manifest_download_verifies_sha_and_caches(tmp_path, monkeypatch):
    payload = b"parquet-bytes"
    sha = hashlib.sha256(payload).hexdigest()
    calls = []

    def fake_download(url: str) -> bytes:
        calls.append(url)
        return payload

    monkeypatch.setattr(fetch, "_download", fake_download)
    manifest = fetch.parse_manifest(_toml(sha))
    root = fetch.materialize(manifest, cache_dir=tmp_path / "cache")
    target = root / "sentier-inventory" / "data/02-electricity/processes.parquet"
    assert target.read_bytes() == payload
    assert calls == [
        "https://raw.githubusercontent.com/sentier-dev/sentier-inventory/"
        "0123456789abcdef0123456789abcdef01234567/data/02-electricity/processes.parquet"
    ]
    fetch.materialize(manifest, cache_dir=tmp_path / "cache")
    assert len(calls) == 1  # second call served from cache


def test_sha_mismatch_is_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "_download", lambda url: b"tampered")
    manifest = fetch.parse_manifest(_toml("00" * 32))
    with pytest.raises(fetch.IntegrityError):
        fetch.materialize(manifest, cache_dir=tmp_path / "cache")


def test_packaged_manifest_parses():
    manifest = fetch.load_packaged_manifest()
    assert {s.name for s in manifest} >= {
        "sentier-inventory",
        "sentier-vocab",
        "sentier-methods",
        "sentier-mappings",
    }
