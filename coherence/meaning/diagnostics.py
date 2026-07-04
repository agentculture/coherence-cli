"""coherence.meaning.diagnostics — offline, rule-based artifact diagnostics.

This module is deliberately *dumb*: pure text heuristics, no embeddings and no
network. It never imports numpy or httpx and never performs any I/O — it only
scans an artifact's text for lexical signals. That makes it a fast, always-
available complement to the embedding-based Meaning Gradient (see the sibling
``axis`` / ``embed`` modules): even with no embedding endpoint reachable, an
agent can still get a cheap, deterministic read on whether an artifact is
missing the ingredients that make a claim actionable.

Three rules, each answering "is this property ABSENT?" — ``True`` means the
diagnostic FIRES because the property is missing:

* :func:`missing_consequence` — the text states no outcome, impact, or risk.
* :func:`missing_owner` — no responsible party is named.
* :func:`missing_next_action` — there is no actionable next step.

Every rule is a case-insensitive substring / small-regex scan over a documented
signal list. The heuristics are intentionally simple and permissive: a single
matching signal is enough to consider the property PRESENT (so the rule does
not fire). They favour false negatives (staying quiet) over false positives
(nagging), which keeps them safe to run everywhere.

:func:`diagnostics` composes the three rules into a JSON-serializable list of
``{"code", "message"}`` entries — one per fired rule, in the stable order
consequence -> owner -> next_action, and ``[]`` for a healthy artifact.
"""

from __future__ import annotations

import re
from typing import Callable

# --- consequence ----------------------------------------------------------
#
# A claim earns its keep by saying what happens as a result: an outcome, an
# impact, or a risk. These substrings are the lexical fingerprints of that
# "and therefore..." move. Matched case-insensitively as plain substrings.
_CONSEQUENCE_SIGNALS: tuple[str, ...] = (
    "so that",
    "otherwise",
    "result",
    "impact",
    "leads to",
    "causes",
    "risk",
    "breaks",
    "fails",
    "consequence",
)

# --- owner -----------------------------------------------------------------
#
# Someone accountable should be named. These substrings cover the common ways
# a party is called out; ``@name`` mentions are handled separately by regex
# below because they are a pattern, not a fixed string.
_OWNER_SIGNALS: tuple[str, ...] = (
    "owner",
    "owned by",
    "assigned to",
    "responsible",
    "on-call",
    "will handle",
)

# An "@handle" mention (e.g. ``@alice``) names a party. One or more word
# characters after the ``@`` — deliberately loose; this is a heuristic.
_MENTION_RE = re.compile(r"@\w+")

# --- next action -----------------------------------------------------------
#
# A healthy artifact points at a concrete next step. These substrings flag the
# usual actionable markers: task keywords, section labels, modal obligations,
# and imperative verbs (kept with a trailing space so "run "/"add "/"fix "
# match the verb rather than words like "brand" or "prefix"). The Markdown
# checkbox "- [ ]" is included verbatim as a to-do marker.
_NEXT_ACTION_SIGNALS: tuple[str, ...] = (
    "todo",
    "next:",
    "action:",
    "must",
    "should",
    "run ",
    "add ",
    "fix ",
    "- [ ]",
)


def _contains_any(haystack: str, signals: tuple[str, ...]) -> bool:
    """Return ``True`` if any signal appears in ``haystack`` (already lowered)."""
    return any(signal in haystack for signal in signals)


def missing_consequence(text: str) -> bool:
    """Return ``True`` when ``text`` states no outcome, impact, or risk.

    Fires (returns ``True``) when none of the consequence signals
    (:data:`_CONSEQUENCE_SIGNALS`, e.g. ``"so that"``, ``"otherwise"``,
    ``"result"``, ``"impact"``, ``"leads to"``, ``"causes"``, ``"risk"``,
    ``"breaks"``, ``"fails"``, ``"consequence"``) is present. Case-insensitive.
    """
    return not _contains_any(text.lower(), _CONSEQUENCE_SIGNALS)


def missing_owner(text: str) -> bool:
    """Return ``True`` when ``text`` names no responsible party.

    Fires (returns ``True``) when neither an ``@handle`` mention nor any owner
    signal (:data:`_OWNER_SIGNALS`, e.g. ``"owner"``, ``"owned by"``,
    ``"assigned to"``, ``"responsible"``, ``"on-call"``, ``"will handle"``) is
    present. Case-insensitive.
    """
    lowered = text.lower()
    if _MENTION_RE.search(text):
        return False
    return not _contains_any(lowered, _OWNER_SIGNALS)


def missing_next_action(text: str) -> bool:
    """Return ``True`` when ``text`` gives no actionable next step.

    Fires (returns ``True``) when none of the next-action signals
    (:data:`_NEXT_ACTION_SIGNALS`, e.g. a ``TODO``, ``"next:"``, ``"action:"``,
    a modal ``"must"``/``"should"``, an imperative ``"run "``/``"add "``/
    ``"fix "``, or a ``- [ ]`` checkbox) is present. Case-insensitive.
    """
    return not _contains_any(text.lower(), _NEXT_ACTION_SIGNALS)


# Rule registry, in the stable emission order (consequence -> owner ->
# next_action). Each tuple is (code, predicate, human hint).
_RULES: tuple[tuple[str, Callable[[str], bool], str], ...] = (
    (
        "missing_consequence",
        missing_consequence,
        "No stated outcome, impact, or risk — say what happens (or what breaks) as a result.",
    ),
    (
        "missing_owner",
        missing_owner,
        "No responsible party named — name an owner (e.g. @name, 'owned by', 'assigned to').",
    ),
    (
        "missing_next_action",
        missing_next_action,
        "No actionable next step — add a concrete action (a TODO, 'next:', a "
        "'- [ ]' checkbox, or an imperative like 'run ...').",
    ),
)


def diagnostics(text: str) -> list[dict]:
    """Run every rule over ``text`` and return the fired diagnostics.

    Returns a JSON-serializable list of ``{"code", "message"}`` dicts — one
    entry for each rule that FIRES (i.e. whose property is missing), in the
    stable order consequence -> owner -> next_action. A healthy artifact that
    satisfies all three properties yields an empty list.
    """
    return [
        {"code": code, "message": message} for code, predicate, message in _RULES if predicate(text)
    ]


__all__ = [
    "diagnostics",
    "missing_consequence",
    "missing_owner",
    "missing_next_action",
]
