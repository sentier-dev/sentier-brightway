"""The environment check that runs before a Brightway project is opened.

bw2data 4.x opens a project through its automatic updates, one of which does
``import bw2io``; bw2io < 0.9 crashes at import against bw2data 4 (its
``remote.py`` compares the string ``__version__`` with a tuple). We catch that
mix and print the fix instead of letting bw2data raise a bare TypeError.
"""

from types import SimpleNamespace

import pytest

from sentier_brightway import preflight
from sentier_brightway.preflight import IncompatibleEnvironmentError, bw2io_conflict


@pytest.mark.parametrize(
    ("bw2data", "bw2io"),
    [
        ("4.7", "0.8.12"),
        ("4.0", "0.8.7"),
        ((4, 7), "0.8.12"),
        ("4.7.dev1", "0.8"),
    ],
)
def test_bw2data_4_with_old_bw2io_is_a_conflict(bw2data, bw2io):
    message = bw2io_conflict(bw2data, bw2io)
    assert message is not None
    assert "bw2io>=0.9" in message
    assert "0.8.12" in message or bw2io in message


@pytest.mark.parametrize(
    ("bw2data", "bw2io"),
    [
        ("4.7", "0.9.17"),
        ("4.7", "0.9.3"),
        ("4.7", None),  # bw2io not installed: bw2data skips the update with a warning
        ("3.6.6", "0.8.12"),  # legacy stack is consistent
        ((3, 6, 6), "0.8.12"),
        ("3.6.6", "0.9.17"),
    ],
)
def test_consistent_stacks_are_not_a_conflict(bw2data, bw2io):
    assert bw2io_conflict(bw2data, bw2io) is None


def test_check_environment_reads_bw2io_from_metadata_without_importing_it(monkeypatch):
    seen = []
    monkeypatch.setattr(
        preflight, "_installed_version", lambda name: seen.append(name) or "0.8.12"
    )
    bd = SimpleNamespace(__version__="4.7")
    with pytest.raises(IncompatibleEnvironmentError, match="bw2io 0.8.12"):
        preflight.check_environment(bd)
    assert seen == ["bw2io"]


def test_check_environment_passes_on_a_consistent_stack(monkeypatch):
    monkeypatch.setattr(preflight, "_installed_version", lambda name: "0.9.17")
    preflight.check_environment(SimpleNamespace(__version__="4.7"))


def test_check_environment_passes_when_bw2io_is_absent(monkeypatch):
    monkeypatch.setattr(preflight, "_installed_version", lambda name: None)
    preflight.check_environment(SimpleNamespace(__version__="4.7"))
