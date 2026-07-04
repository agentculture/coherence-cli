"""Tests for coherence.meaning.diagnostics — offline rule-based diagnostics.

These tests are fully offline: the module under test is pure text heuristics
(no numpy, no httpx, no network). The acceptance criteria (plan task t4):

* Three rules — ``missing_consequence``, ``missing_owner``,
  ``missing_next_action`` — each returns ``True`` when the property is ABSENT
  (i.e. the diagnostic FIRES because the property is missing).
* ``diagnostics(text)`` returns a JSON-serializable list of
  ``{"code", "message"}`` dicts, one entry per fired rule, in stable order
  (consequence, owner, next_action), and ``[]`` for a healthy artifact.
"""

from __future__ import annotations

import json

from coherence.meaning import diagnostics as diag_mod
from coherence.meaning.diagnostics import (
    diagnostics,
    missing_consequence,
    missing_next_action,
    missing_owner,
)

# A rich, healthy artifact: it states a consequence, names an owner, and gives
# concrete next actions, so no diagnostic should fire.
HEALTHY = """\
Migration plan: the legacy sessions table must be dropped so that stale rows
stop double-counting in the weekly reports (otherwise dashboards break). Owned
by @alice, who is on-call this week.
- [ ] Run the archival job before dropping the table.
Next: verify the row counts, then drop.
"""


def _codes(text: str) -> list[str]:
    return [entry["code"] for entry in diagnostics(text)]


# --- missing_consequence: positive (fires) + negative (absent) ------------


def test_missing_consequence_fires_when_no_outcome_stated() -> None:
    # Describes an activity but states no outcome/impact/risk.
    text = "Refactor the parser module into three separate files."
    assert missing_consequence(text) is True
    assert "missing_consequence" in _codes(text)


def test_missing_consequence_absent_when_risk_stated() -> None:
    # "breaks" is a consequence signal, so the rule must not fire.
    text = "If we skip this migration the deploy breaks in production."
    assert missing_consequence(text) is False
    assert "missing_consequence" not in _codes(text)


# --- missing_owner: positive (fires) + negative (absent) ------------------


def test_missing_owner_fires_when_no_party_named() -> None:
    text = "The cache layer needs a rewrite before the next release."
    assert missing_owner(text) is True
    assert "missing_owner" in _codes(text)


def test_missing_owner_absent_when_party_named() -> None:
    # Both "assigned to", "@bob" and "responsible" name a party.
    text = "This is assigned to @bob, who is responsible for the rollout."
    assert missing_owner(text) is False
    assert "missing_owner" not in _codes(text)


# --- missing_next_action: positive (fires) + negative (absent) ------------


def test_missing_next_action_fires_when_no_step_given() -> None:
    text = "The system has been feeling sluggish for a while now."
    assert missing_next_action(text) is True
    assert "missing_next_action" in _codes(text)


def test_missing_next_action_absent_when_step_given() -> None:
    # "TODO", "run " and "add " are all actionable-step signals.
    text = "TODO: run the backfill script and add a covering index."
    assert missing_next_action(text) is False
    assert "missing_next_action" not in _codes(text)


# --- diagnostics(): shape, ordering, serializability ----------------------


def test_healthy_artifact_yields_no_diagnostics() -> None:
    assert diagnostics(HEALTHY) == []


def test_bare_artifact_fires_all_three_in_stable_order() -> None:
    codes = _codes("Something happened yesterday.")
    assert codes == ["missing_consequence", "missing_owner", "missing_next_action"]


def test_each_entry_has_code_and_message_only() -> None:
    for entry in diagnostics(""):
        assert set(entry.keys()) == {"code", "message"}
        assert isinstance(entry["code"], str)
        assert isinstance(entry["message"], str)
        assert entry["message"]  # human hint is non-empty


def test_diagnostics_is_json_serializable_round_trip() -> None:
    text = "The build has been red since Tuesday."
    result = diagnostics(text)
    dumped = json.dumps(result)
    assert json.loads(dumped) == result


def test_rule_functions_return_plain_bools() -> None:
    for text in ("", HEALTHY):
        assert isinstance(missing_consequence(text), bool)
        assert isinstance(missing_owner(text), bool)
        assert isinstance(missing_next_action(text), bool)


def test_case_insensitive_signals() -> None:
    # Uppercased signals must still be recognised (rule must NOT fire).
    assert missing_consequence("THIS BREAKS EVERYTHING.") is False
    assert missing_owner("OWNED BY @CAROL.") is False
    assert missing_next_action("TODO: FIX THE LEAK.") is False


def test_module_exports_public_api() -> None:
    for name in (
        "diagnostics",
        "missing_consequence",
        "missing_owner",
        "missing_next_action",
    ):
        assert name in diag_mod.__all__
