"""Tests for coherence.quality.heuristics — offline, rule-based quality signals.

Every test here is fully OFFLINE and deterministic: the module under test is
pure text heuristics (``re`` + ``datetime`` only, no numpy, no httpx, no
network, and — crucially — no ``datetime.now()`` in any path a test asserts on;
a ``reference_date`` is always passed explicitly). The acceptance criteria
under test (plan task t11):

* Three component detectors — dateable (freshness), provenance, fidelity —
  each reporting *presence* and *kinds* of signal it found, deterministically.
* Three component scorers — ``score_freshness``/``score_provenance``/
  ``score_fidelity`` — each returning a ``(score, confidence, codes)`` triple
  in ``[0, 1]`` whose diagnostic ``codes`` name what the rule could NOT verify
  and lower confidence honestly when a signal is absent (never fabricated).
"""

from __future__ import annotations

from datetime import date

from coherence.quality import heuristics as heur
from coherence.quality.heuristics import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MODERATE,
    detect_dateable,
    detect_fidelity,
    detect_provenance,
    score_fidelity,
    score_freshness,
    score_provenance,
)

_REF = date(2026, 7, 7)


# --- dateable detection ---------------------------------------------------


def test_detect_iso_date_is_parseable() -> None:
    signals = detect_dateable("Report generated 2026-01-15 for the quarter.")
    assert signals.any_marker is True
    assert "iso_date" in signals.kinds
    assert signals.parsed_date == date(2026, 1, 15)


def test_detect_month_year_is_parseable_to_first_of_month() -> None:
    signals = detect_dateable("Published January 2026 in the internal wiki.")
    assert signals.any_marker is True
    assert "month_year" in signals.kinds
    assert signals.parsed_date == date(2026, 1, 1)


def test_detect_version_marker_has_no_parseable_date() -> None:
    signals = detect_dateable("Running v1.2.3 in production since the migration.")
    assert signals.any_marker is True
    assert "version" in signals.kinds
    assert signals.parsed_date is None


def test_detect_relative_marker_has_no_parseable_date() -> None:
    signals = detect_dateable("This was last updated as of the recent rollout.")
    assert signals.any_marker is True
    assert "relative" in signals.kinds
    assert signals.parsed_date is None


def test_detect_no_dateable_marker() -> None:
    signals = detect_dateable("The parser module should be split into smaller pieces.")
    assert signals.any_marker is False
    assert signals.parsed_date is None
    assert signals.kinds == frozenset()


def test_detect_dateable_ignores_bare_decimal_as_version() -> None:
    # A plain decimal like pi must NOT be read as a version string.
    signals = detect_dateable("The ratio settled around 3.14 after tuning.")
    assert "version" not in signals.kinds


def test_detect_dateable_rejects_impossible_iso_date() -> None:
    # 2026-13-40 is not a real calendar date; it must not parse.
    signals = detect_dateable("Filed under 2026-13-40 by mistake.")
    assert signals.parsed_date is None


# --- provenance detection -------------------------------------------------


def test_detect_url_is_provenance() -> None:
    signals = detect_provenance("See https://example.com/study for the numbers.")
    assert signals.present is True
    assert "url" in signals.kinds
    assert signals.categories >= 1


def test_detect_attribution_phrase_is_provenance() -> None:
    signals = detect_provenance("According to the vendor, throughput doubled.")
    assert signals.present is True
    assert "attribution" in signals.kinds


def test_detect_file_and_commit_references_are_provenance() -> None:
    signals = detect_provenance("Fixed in coherence/quality/score.py at commit a1b2c3d.")
    assert signals.present is True
    assert "file" in signals.kinds
    assert "commit" in signals.kinds
    assert signals.categories >= 2


def test_detect_citation_bracket_is_provenance() -> None:
    signals = detect_provenance("The effect is well established [12].")
    assert signals.present is True
    assert "citation" in signals.kinds


def test_detect_no_provenance() -> None:
    signals = detect_provenance("We should probably rewrite the cache layer.")
    assert signals.present is False
    assert signals.categories == 0
    assert signals.kinds == frozenset()


# --- fidelity detection ---------------------------------------------------


def test_detect_verbatim_quote_is_fidelity() -> None:
    signals = detect_fidelity('The RFC states "connections MUST be closed on error".')
    assert signals.present is True
    assert "quote" in signals.kinds


def test_detect_exact_figures_are_fidelity() -> None:
    signals = detect_fidelity("Latency fell by 42% to 118ms at peak load.")
    assert signals.present is True
    assert "figure" in signals.kinds


def test_detect_code_span_is_fidelity() -> None:
    signals = detect_fidelity("Call `make rollback` to revert the change.")
    assert signals.present is True
    assert "code" in signals.kinds


def test_detect_no_fidelity_pure_paraphrase() -> None:
    signals = detect_fidelity("The team feels the approach is broadly reasonable.")
    assert signals.present is False
    assert signals.categories == 0
    assert signals.kinds == frozenset()


# --- freshness scorer -----------------------------------------------------


def test_score_freshness_recent_iso_date_is_fresh_and_high_confidence() -> None:
    result = score_freshness("As of 2026-07-01 the index is rebuilt.", _REF)
    assert result.score > 0.9
    assert abs(result.confidence - CONFIDENCE_HIGH) <= 1e-9
    assert "publication_date_unverified" in result.codes


def test_score_freshness_old_date_less_fresh_than_recent() -> None:
    old = score_freshness("Written 2020-01-01, long ago.", _REF)
    recent = score_freshness("Written 2026-07-01, just now.", _REF)
    assert old.score < recent.score


def test_score_freshness_future_date_clamps_to_fully_fresh() -> None:
    result = score_freshness("Effective 2027-01-01 going forward.", _REF)
    assert abs(result.score - 1.0) <= 1e-9


def test_score_freshness_no_dateable_lowers_confidence_never_fabricates() -> None:
    result = score_freshness("Refactor the parser into three files.", _REF)
    assert abs(result.score) <= 1e-9  # 0.0, not an invented positive score
    assert abs(result.confidence - CONFIDENCE_LOW) <= 1e-9
    assert result.codes == ("no_dateable_statements",)


def test_score_freshness_marker_without_parseable_date_is_age_not_derivable() -> None:
    result = score_freshness("Running v1.2.3 in production.", _REF)
    assert "age_not_derivable" in result.codes
    assert abs(result.confidence - CONFIDENCE_MODERATE) <= 1e-9
    # A presence baseline, strictly between "no evidence" and "fully fresh".
    assert 0.0 < result.score < 1.0


def test_score_freshness_parseable_date_but_no_reference_is_age_not_derivable() -> None:
    # reference_date=None means age cannot be computed even though a date exists;
    # library code must NOT silently substitute datetime.now().
    result = score_freshness("Dated 2026-01-15 in the header.", None)
    assert "age_not_derivable" in result.codes
    assert "publication_date_unverified" in result.codes


# --- provenance scorer ----------------------------------------------------


def test_score_provenance_present_names_unverifiable_liveness_and_date() -> None:
    result = score_provenance("According to https://example.com/report latency fell.")
    assert result.score > 0.0
    assert "source_liveness_unverified" in result.codes
    assert "publication_date_unverified" in result.codes


def test_score_provenance_absent_lowers_confidence_with_diagnostic() -> None:
    result = score_provenance("We should rewrite the cache layer soon.")
    assert abs(result.score) <= 1e-9
    assert abs(result.confidence - CONFIDENCE_LOW) <= 1e-9
    assert result.codes == ("no_source_attribution",)


def test_score_provenance_more_categories_scores_higher() -> None:
    one = score_provenance("See https://example.com/x.")
    two = score_provenance("According to https://example.com/x in report.py.")
    assert two.score > one.score


# --- fidelity scorer ------------------------------------------------------


def test_score_fidelity_present_names_quote_accuracy_unverified() -> None:
    result = score_fidelity('The spec says "retries MUST back off" at 200ms.')
    assert result.score > 0.0
    assert "quote_accuracy_unverified" in result.codes


def test_score_fidelity_absent_lowers_confidence_with_diagnostic() -> None:
    result = score_fidelity("The team broadly agrees the approach is fine.")
    assert abs(result.score) <= 1e-9
    assert abs(result.confidence - CONFIDENCE_LOW) <= 1e-9
    assert result.codes == ("no_verbatim_signal",)


# --- catalog / exports ----------------------------------------------------


def test_every_emitted_code_has_a_diagnostic_message() -> None:
    emitted = set()
    for result in (
        score_freshness("Refactor the parser.", _REF),
        score_freshness("As of 2026-07-01 rebuilt.", _REF),
        score_freshness("Running v1.2.3.", _REF),
        score_provenance("See https://example.com/x."),
        score_provenance("Rewrite the cache."),
        score_fidelity('Says "hi" at 5%.'),
        score_fidelity("Broadly fine."),
    ):
        emitted.update(result.codes)
    for code in emitted:
        assert code in heur.DIAGNOSTIC_MESSAGES
        assert heur.DIAGNOSTIC_MESSAGES[code]  # non-empty message


def test_confidence_constants_are_ordered_floats_in_unit_range() -> None:
    assert 0.0 <= CONFIDENCE_LOW < CONFIDENCE_MODERATE < CONFIDENCE_HIGH <= 1.0
    for value in (CONFIDENCE_LOW, CONFIDENCE_MODERATE, CONFIDENCE_HIGH):
        assert isinstance(value, float)
