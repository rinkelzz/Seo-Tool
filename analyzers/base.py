"""Shared analyzer building blocks.

Analyzers emit ``Finding`` records, *not* SQLAlchemy ``Issue`` rows directly —
the worker persists them. This keeps analyzers pure and trivially testable.

Each ``Rule`` is registered once at import time. The registry lets the score
calculator know the universe of rules and their default weights, so a project
that triggers zero issues against ``meta.title.missing`` still gets credit
for that check passing.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class FindingSeverity(str, enum.Enum):
    """Mirrors ``backend.app.models.issue.IssueSeverity`` (kept decoupled on purpose)."""

    CRITICAL = "critical"
    IMPORTANT = "important"
    TIP = "tip"


class FindingCategory(str, enum.Enum):
    TECH_META = "tech_meta"
    STRUCTURE = "structure"
    CONTENT = "content"


@dataclass(frozen=True)
class Rule:
    """Static metadata for a single check."""

    rule_id: str
    category: FindingCategory
    severity: FindingSeverity
    description: str
    weight: float = 1.0  # used by the score calculator


@dataclass
class Finding:
    """One concrete issue found on one page (or project-wide if ``page_url`` is None)."""

    rule_id: str
    category: FindingCategory
    severity: FindingSeverity
    page_url: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class RuleRegistry:
    """Module-level rule registry. Each analyzer registers its rules at import."""

    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    def register(self, rule: Rule) -> Rule:
        if rule.rule_id in self._rules:
            raise ValueError(f"Rule {rule.rule_id!r} already registered")
        self._rules[rule.rule_id] = rule
        return rule

    def get(self, rule_id: str) -> Rule:
        return self._rules[rule_id]

    def all(self) -> list[Rule]:
        return list(self._rules.values())

    def by_category(self, category: FindingCategory) -> list[Rule]:
        return [r for r in self._rules.values() if r.category == category]


registry = RuleRegistry()
