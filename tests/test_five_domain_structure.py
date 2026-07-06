"""Fresh-checkout five-domain structure + offline-suite proof (plan task t18).

Deliverable 2 of the final verification task. Three things a clean checkout must
satisfy, all fully OFFLINE:

1. **A package home per domain.** ``coherence.quality`` / ``coherence.meaning``
   / ``coherence.signal`` / ``coherence.investiture`` / ``coherence.frames`` are
   importable domain packages, and ``coherence.assess`` / ``coherence.schema``
   are importable support modules.

2. **The new nouns are registered on the real CLI.** ``quality`` / ``signal`` /
   ``investiture`` / ``frames`` / ``assess`` each appear in the top-level help,
   respond to ``-h`` (exit 0), and resolve through ``coherence explain``.

3. **The whole new-noun surface runs with no live endpoint.** The default embed
   endpoint (``localhost:8002``) is never contacted: the full suite passes in
   this worktree with no embed server running, and — as a cheap sanity guard —
   a socket monitor trips if a fully-offline noun (``quality`` / ``signal`` /
   ``frames``) ever opens a connection to the embed port. It never does.
"""

from __future__ import annotations

import importlib
import json
import socket

import pytest

from coherence.cli import main
from coherence.explain import known_paths
from coherence.meaning.embed import DEFAULT_EMBED_URL

_DOMAIN_PACKAGES = [
    "coherence.quality",
    "coherence.meaning",
    "coherence.signal",
    "coherence.investiture",
    "coherence.frames",
]
_SUPPORT_MODULES = ["coherence.assess", "coherence.schema"]

# The nouns added by the restructure (meaning pre-existed) that must be wired.
_REGISTERED_NOUNS = ["quality", "signal", "investiture", "frames", "assess"]

# The host:port a live meaning/investiture/assess run would dial.
_EMBED_HOST_PORT = "localhost:8002"
_EMBED_PORT = 8002


# --- 1. a package/module home per domain ------------------------------------


@pytest.mark.parametrize("module_name", _DOMAIN_PACKAGES + _SUPPORT_MODULES)
def test_domain_home_is_importable(module_name: str) -> None:
    module = importlib.import_module(module_name)
    # A real on-disk module/package (packages resolve to their __init__.py),
    # never a bare namespace stand-in.
    assert getattr(module, "__file__", None) is not None


@pytest.mark.parametrize("package_name", _DOMAIN_PACKAGES)
def test_domain_home_is_a_package(package_name: str) -> None:
    package = importlib.import_module(package_name)
    # Domain homes are packages (they have submodules), not flat modules.
    assert hasattr(package, "__path__")


# --- 2. new nouns are registered CLI nouns ----------------------------------


def test_new_nouns_appear_in_top_level_help(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    for noun in _REGISTERED_NOUNS:
        assert noun in out, f"{noun} missing from top-level help"


@pytest.mark.parametrize("noun", _REGISTERED_NOUNS)
def test_noun_responds_to_help(noun: str, capsys: pytest.CaptureFixture[str]) -> None:
    # argparse's -h prints help and raises SystemExit(0); the noun's own name
    # appears in its usage/prog line.
    with pytest.raises(SystemExit) as exc:
        main([noun, "-h"])
    assert exc.value.code == 0
    assert noun in capsys.readouterr().out


@pytest.mark.parametrize("noun", _REGISTERED_NOUNS)
def test_explain_resolves_each_noun(noun: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert (noun,) in known_paths()
    rc = main(["explain", noun])
    assert rc == 0
    assert capsys.readouterr().out.strip()


# --- 3. the new-noun surface runs offline -----------------------------------


def test_default_embed_endpoint_is_the_guarded_target() -> None:
    # Documents exactly what the offline guard below is protecting against.
    assert _EMBED_HOST_PORT in DEFAULT_EMBED_URL


def test_offline_nouns_never_dial_the_embed_endpoint(
    tmp_path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Belt-and-suspenders on top of "the suite passes with no embed server":
    # install a socket guard that trips if any command opens a connection to the
    # embed port, then drive the three fully-offline nouns end-to-end. They must
    # all succeed (exit 0) without dialing the endpoint.
    original_connect = socket.socket.connect
    dialed: list = []

    def _guarded_connect(self, address, *args, **kwargs):  # type: ignore[no-untyped-def]
        port = address[1] if isinstance(address, tuple) and len(address) >= 2 else None
        if port == _EMBED_PORT:
            dialed.append(address)
            raise AssertionError(f"an offline noun dialed the embed endpoint: {address!r}")
        return original_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)

    # quality score — rule-based heuristic, no embedding dependency.
    artifact = tmp_path / "a.md"
    artifact.write_text(
        "As of 2026-01-01, per https://example.com, retries fell 42%.", encoding="utf-8"
    )
    assert main(["quality", "score", str(artifact), "--json"]) == 0
    capsys.readouterr()

    # signal trend — pure numeric series engine, no embedding dependency.
    series = tmp_path / "series.json"
    series.write_text(
        json.dumps(
            {
                "domain": "quality",
                "points": [
                    {"id": "p0", "index": 0, "values": {"x": 0.1}},
                    {"id": "p1", "index": 1, "values": {"x": 0.2}},
                    {"id": "p2", "index": 2, "values": {"x": 0.3}},
                ],
            }
        ),
        encoding="utf-8",
    )
    assert main(["signal", "trend", str(series), "--json"]) == 0
    capsys.readouterr()

    # frames inspect — pure dict inspection, no embedding dependency.
    measurement = tmp_path / "m.json"
    measurement.write_text(
        json.dumps({"meaning_score": 0.5, "subdimensions": {}, "diagnostics": []}),
        encoding="utf-8",
    )
    assert main(["frames", "inspect", str(measurement), "--json"]) == 0
    capsys.readouterr()

    assert dialed == []
