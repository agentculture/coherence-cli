"""Banned-terms language guard for coherence-cli's shipped documentation.

Per the five-domain restructure's non-goals
(``docs/specs/2026-07-06-coherence-cli-ships-as-a-five-domain-coherence-eng.md``):
scores are described as model-relative, anchor-defined semantic measurements —
never as literal physics, souls, universal meaning, or any other mystical
framing. This module is a small, grep-able guard that keeps the *shipped*
docs honest about that: README.md and the domain/envelope/series reference
docs must never contain the banned vocabulary itself, even in passing.

Deliberately checked: README.md, docs/domains.md, docs/envelope.md,
docs/signal-series.md — the docs a human or agent actually reads to
understand what coherence-cli measures.

Deliberately EXCLUDED: docs/specs/**, docs/plans/**, .devague/** — these are
devague-generated planning artifacts that quote the non-goals *verbatim*
(e.g. "no literal physics, no literal souls, no universal-meaning claims") as
part of stating what NOT to build. Grepping those would always fail, for the
wrong reason: the spec is naming forbidden language, not using it. The
shipped docs checked here must instead describe the same constraint without
reaching for the banned words at all (see README.md's "Language and
falsifiability" section for how that rewrite reads).

Matching is case-insensitive and word-boundary sensitive (``\\bsoul\\b``, not a
bare substring scan) so an unrelated word that happens to contain the banned
text as a fragment is never a false positive.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

# The docs a human/agent actually reads for coherence-cli's product surface.
# NOT a glob: docs/specs/**, docs/plans/**, and .devague/** are intentionally
# excluded (see module docstring) because they quote the non-goals verbatim.
CHECKED_DOCS: tuple[str, ...] = (
    "README.md",
    "docs/domains.md",
    "docs/envelope.md",
    "docs/signal-series.md",
)

# One compiled, word-boundary-sensitive, case-insensitive pattern per banned
# term. Each catches the singular/plural or hyphen/space variant that would
# plausibly appear in prose, without over-matching an unrelated word that
# merely contains the same letters as a fragment (e.g. "console", "consult",
# "physical", "consensual" must never trip these).
_BANNED_TERMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("soul", re.compile(r"\bsouls?\b", re.IGNORECASE)),
    ("mystical", re.compile(r"\bmystical\b", re.IGNORECASE)),
    ("literal physics", re.compile(r"\bliteral[-\s]+physics\b", re.IGNORECASE)),
    ("universal meaning", re.compile(r"\buniversal[-\s]+meaning\b", re.IGNORECASE)),
)


def _read(relative_path: str) -> str:
    path = _REPO_ROOT / relative_path
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("relative_path", CHECKED_DOCS)
def test_checked_doc_exists(relative_path: str) -> None:
    assert (_REPO_ROOT / relative_path).is_file(), (
        f"{relative_path} is expected to exist and be checked for banned "
        "mystical/universal-meaning/literal-physics language"
    )


@pytest.mark.parametrize("relative_path", CHECKED_DOCS)
@pytest.mark.parametrize("term_label, pattern", _BANNED_TERMS)
def test_doc_contains_no_banned_term(
    relative_path: str, term_label: str, pattern: re.Pattern[str]
) -> None:
    text = _read(relative_path)
    matches = pattern.findall(text)
    assert not matches, (
        f"{relative_path} contains banned term {term_label!r} ({matches!r}). "
        "coherence-cli describes scores as model-relative, anchor-defined "
        "semantic measurements -- rephrase without reaching for mystical, "
        "universal-meaning, soul, or literal-physics language (see this "
        "module's docstring for why docs/specs and docs/plans are excluded "
        "from this check)."
    )


def test_readme_names_all_five_coherence_domains() -> None:
    text = _read("README.md").lower()
    domains = ("quality", "meaning", "signal", "investiture", "frames")
    missing = [domain for domain in domains if domain not in text]
    assert not missing, f"README.md is missing coherence domain name(s): {missing}"


def test_readme_declares_scores_model_relative() -> None:
    text = _read("README.md").lower()
    assert "model-relative" in text, (
        "README.md should declare coherence-cli's scores as model-relative "
        "(see docs/envelope.md and the spec's non-goals)"
    )
