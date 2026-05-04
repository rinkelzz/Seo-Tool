"""Crawl-vs-crawl comparison.

Builds a structured diff between two crawls of the same project. Used by
the comparison HTML report; downstream the data shape is stable enough
that PDF or JSON variants can hang off it without changing the analyzer.

A finding (=Issue row) is identified by ``(rule_id, page_url)`` — the
same rule firing twice on the same page is one finding, while the same
rule on different pages counts separately.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analyzers.base import registry
from backend.app.models.crawl import Crawl
from backend.app.models.issue import Issue, IssueCategory, IssueSeverity
from backend.app.models.page import Page
from backend.app.models.project import Project
from backend.app.services.reports import (
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    SEVERITY_LABELS,
    SEVERITY_ORDER,
)


@dataclass(frozen=True)
class FindingKey:
    """How we identify a finding for diffing — (rule_id, page_url)."""

    rule_id: str
    page_url: str | None  # ``None`` for project-wide findings


@dataclass
class FindingSnapshot:
    """The bits of an Issue we need for the comparison view."""

    rule_id: str
    page_url: str | None
    category: IssueCategory
    severity: IssueSeverity
    description: str  # from rule registry, not the model
    payload: dict | None


@dataclass
class CategoryDelta:
    category: IssueCategory
    label: str
    score_a: float | None
    score_b: float | None
    new: list[FindingSnapshot] = field(default_factory=list)
    resolved: list[FindingSnapshot] = field(default_factory=list)
    persistent: list[FindingSnapshot] = field(default_factory=list)

    @property
    def score_delta(self) -> float | None:
        if self.score_a is None or self.score_b is None:
            return None
        return round(self.score_b - self.score_a, 2)


@dataclass
class ComparisonContext:
    project: Project
    crawl_a: Crawl
    crawl_b: Crawl
    pages_a: int
    pages_b: int
    overall_a: float | None
    overall_b: float | None
    categories: list[CategoryDelta]

    @property
    def overall_delta(self) -> float | None:
        if self.overall_a is None or self.overall_b is None:
            return None
        return round(self.overall_b - self.overall_a, 2)


def build_comparison(
    db: Session,
    project: Project,
    crawl_a: Crawl,
    crawl_b: Crawl,
) -> ComparisonContext:
    """Compute the full diff between ``crawl_a`` (older) and ``crawl_b`` (newer).

    The two crawls must belong to the same project. The caller is expected
    to have already verified that — this helper does not re-check.
    """
    rule_descriptions = {r.rule_id: r.description for r in registry.all()}

    snap_a = _snapshot_for_crawl(db, crawl_a.id, rule_descriptions)
    snap_b = _snapshot_for_crawl(db, crawl_b.id, rule_descriptions)
    pages_a = (
        db.scalar(select(func.count()).select_from(Page).where(Page.crawl_id == crawl_a.id)) or 0
    )
    pages_b = (
        db.scalar(select(func.count()).select_from(Page).where(Page.crawl_id == crawl_b.id)) or 0
    )

    keys_a = set(snap_a.keys())
    keys_b = set(snap_b.keys())

    new_keys = keys_b - keys_a
    resolved_keys = keys_a - keys_b
    persistent_keys = keys_a & keys_b

    categories: list[CategoryDelta] = []
    for cat in CATEGORY_ORDER:
        score_a = _maybe_float(_score_for_category(crawl_a, cat))
        score_b = _maybe_float(_score_for_category(crawl_b, cat))
        delta = CategoryDelta(
            category=cat,
            label=CATEGORY_LABELS[cat],
            score_a=score_a,
            score_b=score_b,
        )
        delta.new = _bucket_for_category(snap_b, new_keys, cat)
        delta.resolved = _bucket_for_category(snap_a, resolved_keys, cat)
        delta.persistent = _bucket_for_category(snap_b, persistent_keys, cat)
        categories.append(delta)

    return ComparisonContext(
        project=project,
        crawl_a=crawl_a,
        crawl_b=crawl_b,
        pages_a=pages_a,
        pages_b=pages_b,
        overall_a=_maybe_float(crawl_a.score_overall),
        overall_b=_maybe_float(crawl_b.score_overall),
        categories=categories,
    )


# ---- helpers --------------------------------------------------------------


def _snapshot_for_crawl(
    db: Session, crawl_id: int, rule_descriptions: dict[str, str]
) -> dict[FindingKey, FindingSnapshot]:
    """Load all issues for one crawl into a (rule_id, page_url) → snapshot map.

    We load Issue + Page in a single join so the per-issue page URL is
    available without lazy-loading per row.
    """
    stmt = (
        select(Issue, Page.url)
        .outerjoin(Page, Issue.page_id == Page.id)
        .where(Issue.crawl_id == crawl_id)
    )
    out: dict[FindingKey, FindingSnapshot] = {}
    for issue, page_url in db.execute(stmt).all():
        key = FindingKey(rule_id=issue.rule_id, page_url=page_url)
        if key in out:
            continue  # duplicate (rule_id, page_url) — keep first; DB shouldn't allow but be safe
        out[key] = FindingSnapshot(
            rule_id=issue.rule_id,
            page_url=page_url,
            category=issue.category,
            severity=issue.severity,
            description=rule_descriptions.get(issue.rule_id, issue.rule_id),
            payload=issue.payload,
        )
    return out


def _bucket_for_category(
    snapshots: dict[FindingKey, FindingSnapshot],
    keys: Iterable[FindingKey],
    category: IssueCategory,
) -> list[FindingSnapshot]:
    """Return the snapshots in ``keys`` whose category matches ``category``,
    sorted by severity descending then by rule_id."""
    items = [snapshots[k] for k in keys if k in snapshots and snapshots[k].category == category]
    items.sort(key=lambda s: (SEVERITY_ORDER.index(s.severity), s.rule_id, s.page_url or ""))
    return items


def _score_for_category(crawl: Crawl, cat: IssueCategory):  # type: ignore[no-untyped-def]
    return {
        IssueCategory.TECH_META: crawl.score_tech,
        IssueCategory.STRUCTURE: crawl.score_struct,
        IssueCategory.CONTENT: crawl.score_content,
    }[cat]


def _maybe_float(v) -> float | None:  # type: ignore[no-untyped-def]
    return float(v) if v is not None else None


# Re-export labels for the template — saves the renderer importing from
# both modules.
__all__ = [
    "CATEGORY_LABELS",
    "CategoryDelta",
    "ComparisonContext",
    "FindingKey",
    "FindingSnapshot",
    "SEVERITY_LABELS",
    "SEVERITY_ORDER",
    "build_comparison",
]
