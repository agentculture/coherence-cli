"""coherence.quality.heuristics — offline, rule-based quality signal detection.

This module is deliberately *dumb* and honest: pure text heuristics over
``re`` + ``datetime``, no embeddings, no numpy/httpx, and no network. It never
performs I/O and — importantly for deterministic tests — never calls
``datetime.now()``: age is always computed against a ``reference_date`` the
caller passes in (the CLI boundary supplies today; tests supply a fixed date).

It scores three components of information quality, each in ``[0, 1]`` with an
explicit *confidence* and a set of machine-readable diagnostic *codes* that
name what a rule could NOT verify:

* **freshness** — does the text carry a dateable statement (an ISO date, a
  ``Month Year``, a version string, or a relative-time marker)? When a real
  calendar date is present *and* a ``reference_date`` is supplied, an age is
  derivable and freshness decays with that age (half-life
  :data:`_HALF_LIFE_DAYS`). When a marker is present but no age can be computed,
  freshness falls back to :data:`PRESENCE_BASELINE` at reduced confidence. When
  *no* dateable marker is found, freshness is ``0.0`` at low confidence with a
  ``no_dateable_statements`` diagnostic — never a fabricated positive score.
* **provenance** — is there source attribution (a URL, DOI, ``[n]`` citation,
  an "according to" phrase, a file path, or a commit reference)? A present
  marker raises the score but the rule cannot verify the source *resolves* or
  when it was actually published, so it emits ``source_liveness_unverified``
  and ``publication_date_unverified``.
* **fidelity** — quote-vs-paraphrase: does the text carry verbatim quotes,
  exact figures, or code spans, rather than reading as unattributed
  paraphrase? Present verbatim signal raises the score but the rule cannot
  verify the quote matches any real source (``quote_accuracy_unverified``).

Every rule is a documented, case-insensitive regex/substring scan. The scoring
is intentionally simple, bounded, and deterministic, so two runs over the same
text and ``reference_date`` always agree.
"""

from __future__ import annotations

import re
from datetime import date
from typing import NamedTuple

# --- confidence levels ----------------------------------------------------
#
# Confidence answers "how much can a rule vouch for this component's score?".
# It is reported alongside every component so an absent signal lowers
# confidence *visibly* rather than silently inflating the score.
CONFIDENCE_HIGH = 0.9  # a verifiable-by-rule measurement (e.g. a computed age)
CONFIDENCE_MODERATE = 0.5  # a marker is present but not fully groundable
CONFIDENCE_LOW = 0.2  # the signal is absent; the score reflects that absence

# Freshness half-life in days: at this age, a decayed date scores 0.5.
_HALF_LIFE_DAYS = 365.0

# Freshness fallback when a dateable marker exists but no age is derivable —
# strictly between "no evidence" (0.0) and "fully fresh" (1.0).
PRESENCE_BASELINE = 0.5

# Provenance/fidelity map a count of distinct signal categories to a score:
# base for the first category, plus a step per additional category, capped.
_MARKER_BASE = 0.4
_MARKER_STEP = 0.2


# --- diagnostic catalog ---------------------------------------------------
#
# One stable, machine-readable code per distinguishable "what a rule could not
# verify / what was absent" condition, each paired with a human-readable hint.
DIAGNOSTIC_MESSAGES: dict[str, str] = {
    "no_dateable_statements": (
        "No dateable statement found (no ISO date, 'Month Year', version, or "
        "relative-time marker) — freshness cannot be grounded, so its "
        "confidence is lowered rather than a freshness score fabricated."
    ),
    "age_not_derivable": (
        "A dateable marker is present but its age could not be computed (no "
        "parseable calendar date, or no reference date supplied) — freshness "
        "falls back to a presence baseline at reduced confidence."
    ),
    "publication_date_unverified": (
        "A date or source is present, but the heuristic cannot verify the "
        "actual publication date — it sees only the string, not the record."
    ),
    "source_liveness_unverified": (
        "A source marker (URL, citation, file, or commit) is present, but the "
        "heuristic cannot check that it resolves or that the source exists."
    ),
    "no_source_attribution": (
        "No source attribution found (no URL, DOI, citation, 'according to', "
        "file, or commit reference) — provenance confidence is lowered."
    ),
    "quote_accuracy_unverified": (
        "Verbatim quotes, exact figures, or code spans are present, but the "
        "heuristic cannot verify they match any real source."
    ),
    "no_verbatim_signal": (
        "No verbatim quote, exact figure, or code span found — the content "
        "reads as unattributed paraphrase, so fidelity confidence is lowered."
    ),
}


class ComponentScore(NamedTuple):
    """One component's ``(score, confidence, codes)`` triple.

    ``score`` and ``confidence`` are floats in ``[0, 1]``; ``codes`` is the
    ordered tuple of diagnostic codes this component raises (each a key of
    :data:`DIAGNOSTIC_MESSAGES`).
    """

    score: float
    confidence: float
    codes: tuple[str, ...]


class DateableSignals(NamedTuple):
    """What the dateable-statement detector found in a text."""

    any_marker: bool
    parsed_date: date | None
    kinds: frozenset[str]


class ProvenanceSignals(NamedTuple):
    """What the source-attribution detector found in a text."""

    present: bool
    categories: int
    kinds: frozenset[str]


class FidelitySignals(NamedTuple):
    """What the verbatim/quote detector found in a text."""

    present: bool
    categories: int
    kinds: frozenset[str]


# --- dateable detection ---------------------------------------------------

_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# A version string needs an explicit 'v' prefix or the word "version", so a
# bare decimal like "3.14" is never mistaken for a version.
_VERSION_RE = re.compile(r"\bv\d+\.\d+(?:\.\d+)?\b|\bversion\s+\d", re.IGNORECASE)
_MONTH_YEAR_RE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+(\d{4})\b",
    re.IGNORECASE,
)
_RELATIVE_SIGNALS: tuple[str, ...] = (
    "as of",
    "yesterday",
    "today",
    "last week",
    "last month",
    "last year",
    "this week",
    "recently",
    "updated",
    "last updated",
    "last modified",
    "published",
    "revised",
)
_MONTH_INDEX: dict[str, int] = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _parse_first_date(text: str) -> date | None:
    """Return the first parseable calendar date in ``text``, or ``None``.

    Tries an ISO ``YYYY-MM-DD`` first, then a ``Month YYYY`` (mapped to the
    first of that month). An impossible date (e.g. ``2026-13-40``) is skipped
    rather than raising.
    """
    iso = _ISO_DATE_RE.search(text)
    if iso is not None:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            pass  # not a real calendar date; fall through
    month_year = _MONTH_YEAR_RE.search(text)
    if month_year is not None:
        month = _MONTH_INDEX[month_year.group(1)[:3].lower()]
        return date(int(month_year.group(2)), month, 1)
    return None


def detect_dateable(text: str) -> DateableSignals:
    """Scan ``text`` for dateable statements (freshness signal presence).

    Reports which kinds matched (``iso_date``, ``month_year``, ``version``,
    ``relative``), whether *any* marker was found, and the first parseable
    calendar date if one exists (ISO or ``Month Year``; a version or a bare
    relative phrase is a marker but yields no parseable date).
    """
    lowered = text.lower()
    kinds: set[str] = set()
    if _ISO_DATE_RE.search(text):
        kinds.add("iso_date")
    if _MONTH_YEAR_RE.search(text):
        kinds.add("month_year")
    if _VERSION_RE.search(text):
        kinds.add("version")
    if any(signal in lowered for signal in _RELATIVE_SIGNALS):
        kinds.add("relative")
    return DateableSignals(
        any_marker=bool(kinds),
        parsed_date=_parse_first_date(text),
        kinds=frozenset(kinds),
    )


# --- provenance detection -------------------------------------------------

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_DOI_RE = re.compile(r"\b10\.\d{4,9}/\S+\b")
_CITATION_RE = re.compile(r"\[\d+\]|\[[A-Z][A-Za-z]+,?\s*\d{4}\]")
_FILE_RE = re.compile(r"\b[\w./-]+\.(?:py|md|txt|json|ya?ml|toml|js|ts|go|rs|c|cpp|h|sh)\b")
# A git SHA: 7–40 hex chars with at least one letter (so a plain "1234567"
# decimal is not read as a commit), or the literal word "commit".
_COMMIT_RE = re.compile(r"\bcommit\b|\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b", re.IGNORECASE)
_ATTRIBUTION_SIGNALS: tuple[str, ...] = (
    "according to",
    "as reported by",
    "cited",
    "citing",
    "source:",
    "reference:",
    "sourced from",
    "per the",
)


def detect_provenance(text: str) -> ProvenanceSignals:
    """Scan ``text`` for source attribution (provenance signal presence).

    Reports which categories matched (``url``, ``doi``, ``citation``,
    ``attribution``, ``file``, ``commit``) and how many distinct categories
    were found. Detection is presence-only: it cannot confirm a source resolves
    or is real — that limit is surfaced as diagnostics by :func:`score_provenance`.
    """
    lowered = text.lower()
    kinds: set[str] = set()
    if _URL_RE.search(text):
        kinds.add("url")
    if _DOI_RE.search(text):
        kinds.add("doi")
    if _CITATION_RE.search(text):
        kinds.add("citation")
    if _FILE_RE.search(text):
        kinds.add("file")
    if _COMMIT_RE.search(text):
        kinds.add("commit")
    if any(signal in lowered for signal in _ATTRIBUTION_SIGNALS):
        kinds.add("attribution")
    return ProvenanceSignals(present=bool(kinds), categories=len(kinds), kinds=frozenset(kinds))


# --- fidelity detection ---------------------------------------------------

_QUOTE_RE = re.compile(r"\"[^\"]{3,}\"|“[^”]{3,}”")
_CODE_RE = re.compile(r"`[^`]+`")
_FIGURE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s?%"  # percentages
    r"|\$\s?\d"  # currency
    r"|\b\d[\d,]*\.\d+\b"  # decimals / money
    r"|\b\d+\s?(?:ms|kb|mb|gb|tb|px|km|kg|s)\b",  # measurements
    re.IGNORECASE,
)


def detect_fidelity(text: str) -> FidelitySignals:
    """Scan ``text`` for verbatim signal (quote-vs-paraphrase fidelity).

    Reports which categories matched (``quote``, ``figure``, ``code``) and how
    many distinct categories were found. Presence of verbatim signal cannot be
    checked for *accuracy* against a real source — that limit is surfaced as a
    diagnostic by :func:`score_fidelity`.
    """
    kinds: set[str] = set()
    if _QUOTE_RE.search(text):
        kinds.add("quote")
    if _FIGURE_RE.search(text):
        kinds.add("figure")
    if _CODE_RE.search(text):
        kinds.add("code")
    return FidelitySignals(present=bool(kinds), categories=len(kinds), kinds=frozenset(kinds))


# --- component scorers ----------------------------------------------------


def _decay(age_days: int) -> float:
    """Map an age in days to a freshness score in ``(0, 1]`` (1.0 for age <= 0)."""
    if age_days <= 0:
        return 1.0
    return 0.5 ** (age_days / _HALF_LIFE_DAYS)


def _marker_score(categories: int) -> float:
    """Map a count of distinct signal categories to a bounded score in ``[0, 1]``."""
    return min(1.0, _MARKER_BASE + _MARKER_STEP * (categories - 1))


def score_freshness(text: str, reference_date: date | None) -> ComponentScore:
    """Score the freshness of ``text`` against ``reference_date``.

    * No dateable marker → ``0.0`` at :data:`CONFIDENCE_LOW` with
      ``no_dateable_statements`` (absence of evidence, never a fabricated score).
    * A parseable date *and* a ``reference_date`` → age-decayed score at
      :data:`CONFIDENCE_HIGH` with ``publication_date_unverified`` (the date is
      real to the parser, but its truth as a publication date is unverifiable).
    * A marker present but no derivable age (a version/relative phrase, or a
      date with ``reference_date is None``) → :data:`PRESENCE_BASELINE` at
      :data:`CONFIDENCE_MODERATE` with ``age_not_derivable`` (plus
      ``publication_date_unverified`` when a date string was seen).
    """
    signals = detect_dateable(text)
    if not signals.any_marker:
        return ComponentScore(0.0, CONFIDENCE_LOW, ("no_dateable_statements",))

    codes: list[str] = []
    if signals.parsed_date is not None:
        codes.append("publication_date_unverified")
        if reference_date is not None:
            age_days = (reference_date - signals.parsed_date).days
            return ComponentScore(_decay(age_days), CONFIDENCE_HIGH, tuple(codes))

    codes.append("age_not_derivable")
    return ComponentScore(PRESENCE_BASELINE, CONFIDENCE_MODERATE, tuple(codes))


def score_provenance(text: str) -> ComponentScore:
    """Score the source attribution of ``text``.

    Absent → ``0.0`` at :data:`CONFIDENCE_LOW` with ``no_source_attribution``.
    Present → a bounded score at :data:`CONFIDENCE_MODERATE`, naming both
    limits a rule cannot cross: ``source_liveness_unverified`` (it cannot check
    the source resolves) and ``publication_date_unverified`` (it cannot confirm
    when the source was actually published).
    """
    signals = detect_provenance(text)
    if not signals.present:
        return ComponentScore(0.0, CONFIDENCE_LOW, ("no_source_attribution",))
    return ComponentScore(
        _marker_score(signals.categories),
        CONFIDENCE_MODERATE,
        ("source_liveness_unverified", "publication_date_unverified"),
    )


def score_fidelity(text: str) -> ComponentScore:
    """Score the quote-vs-paraphrase fidelity of ``text``.

    Absent → ``0.0`` at :data:`CONFIDENCE_LOW` with ``no_verbatim_signal``.
    Present → a bounded score at :data:`CONFIDENCE_MODERATE` with
    ``quote_accuracy_unverified`` (a rule can see a quote/figure but cannot
    verify it matches any real source).
    """
    signals = detect_fidelity(text)
    if not signals.present:
        return ComponentScore(0.0, CONFIDENCE_LOW, ("no_verbatim_signal",))
    return ComponentScore(
        _marker_score(signals.categories),
        CONFIDENCE_MODERATE,
        ("quote_accuracy_unverified",),
    )


__all__ = [
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MODERATE",
    "CONFIDENCE_LOW",
    "PRESENCE_BASELINE",
    "DIAGNOSTIC_MESSAGES",
    "ComponentScore",
    "DateableSignals",
    "ProvenanceSignals",
    "FidelitySignals",
    "detect_dateable",
    "detect_provenance",
    "detect_fidelity",
    "score_freshness",
    "score_provenance",
    "score_fidelity",
]
