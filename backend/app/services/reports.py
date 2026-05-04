"""Report data assembly + Jinja2 rendering.

Pulls everything needed to render a per-crawl SEO report into a single
``ReportContext``, then renders it through ``backend/app/templates/``. The
endpoint layer just hands back the rendered string.

Kept separate from the API so:
- ``report_html()`` can be reused by the upcoming PDF endpoint (Phase 7-B)
- the Jinja env is configured once at module level
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analyzers.base import registry
from backend.app.models.crawl import Crawl
from backend.app.models.issue import Issue, IssueCategory, IssueSeverity
from backend.app.models.page import Page
from backend.app.models.project import Project

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


# ---- per-rule grouping ----------------------------------------------------


@dataclass
class RuleSummary:
    """One rule and its findings within this crawl."""

    rule_id: str
    description: str
    severity: IssueSeverity
    category: IssueCategory
    count: int
    examples: list[Issue]  # up to 5 representative findings


@dataclass
class CategorySummary:
    """All rules belonging to one category, with hit/passed counts."""

    category: IssueCategory
    label: str
    score: float | None
    rules_with_findings: list[RuleSummary]
    rules_passing: list[str]  # rule_ids that didn't produce any finding

    @property
    def total_findings(self) -> int:
        return sum(r.count for r in self.rules_with_findings)


@dataclass
class ReportContext:
    """Everything the template needs."""

    project: Project
    crawl: Crawl
    pages_count: int
    by_severity: dict[IssueSeverity, int]
    categories: list[CategorySummary]


CATEGORY_LABELS: dict[IssueCategory, str] = {
    IssueCategory.TECH_META: "Technik & Meta",
    IssueCategory.STRUCTURE: "Struktur",
    IssueCategory.CONTENT: "Inhalt",
}

SEVERITY_LABELS: dict[IssueSeverity, str] = {
    IssueSeverity.CRITICAL: "Sehr wichtig",
    IssueSeverity.IMPORTANT: "Wichtig",
    IssueSeverity.TIP: "Tipp",
}

SEVERITY_ORDER: list[IssueSeverity] = [
    IssueSeverity.CRITICAL,
    IssueSeverity.IMPORTANT,
    IssueSeverity.TIP,
]

CATEGORY_ORDER: list[IssueCategory] = [
    IssueCategory.TECH_META,
    IssueCategory.STRUCTURE,
    IssueCategory.CONTENT,
]


def build_context(
    db: Session, project: Project, crawl: Crawl, *, examples_per_rule: int = 5
) -> ReportContext:
    """Assemble everything the report template renders."""
    pages_count = (
        db.scalar(select(func.count()).select_from(Page).where(Page.crawl_id == crawl.id)) or 0
    )

    issues = list(
        db.scalars(
            select(Issue)
            .where(Issue.crawl_id == crawl.id)
            .order_by(Issue.severity.desc(), Issue.id.asc())
        ).all()
    )

    by_severity: dict[IssueSeverity, int] = defaultdict(int)
    by_rule: dict[str, list[Issue]] = defaultdict(list)
    for issue in issues:
        by_severity[issue.severity] += 1
        by_rule[issue.rule_id].append(issue)

    score_by_category = {
        IssueCategory.TECH_META: _maybe_float(crawl.score_tech),
        IssueCategory.STRUCTURE: _maybe_float(crawl.score_struct),
        IssueCategory.CONTENT: _maybe_float(crawl.score_content),
    }

    categories: list[CategorySummary] = []
    for cat in CATEGORY_ORDER:
        cat_rules = registry.by_category(_to_finding_category(cat))
        rules_with_findings: list[RuleSummary] = []
        rules_passing: list[str] = []
        for rule in cat_rules:
            hits = by_rule.get(rule.rule_id, [])
            if hits:
                rules_with_findings.append(
                    RuleSummary(
                        rule_id=rule.rule_id,
                        description=rule.description,
                        severity=_to_issue_severity(rule.severity),
                        category=cat,
                        count=len(hits),
                        examples=hits[:examples_per_rule],
                    )
                )
            else:
                rules_passing.append(rule.rule_id)
        # Order: critical → important → tip; within each severity by count desc
        rules_with_findings.sort(key=lambda r: (SEVERITY_ORDER.index(r.severity), -r.count))
        categories.append(
            CategorySummary(
                category=cat,
                label=CATEGORY_LABELS[cat],
                score=score_by_category[cat],
                rules_with_findings=rules_with_findings,
                rules_passing=sorted(rules_passing),
            )
        )

    return ReportContext(
        project=project,
        crawl=crawl,
        pages_count=pages_count,
        by_severity={s: by_severity.get(s, 0) for s in SEVERITY_ORDER},
        categories=categories,
    )


def render_html(ctx: ReportContext) -> str:
    """Render ``crawl_report.html`` with the assembled context."""
    template = _env.get_template("reports/crawl_report.html")
    return template.render(
        ctx=ctx,
        severity_label=SEVERITY_LABELS,
        severity_order=SEVERITY_ORDER,
        page_url_for=_page_url_for,
        format_score=_format_score,
        format_datetime=_format_datetime,
        score_class=_score_class,
    )


def report_html(db: Session, project: Project, crawl: Crawl) -> str:
    """One-shot helper used by the API endpoint."""
    return render_html(build_context(db, project, crawl))


def render_pdf(html: str) -> bytes:
    """Render an HTML string to PDF bytes via WeasyPrint.

    Importing WeasyPrint pulls in Pango/Cairo at import time, which fails
    on dev machines that don't have the system libs. We import lazily so
    that ``backend.app.services.reports`` stays importable everywhere — the
    PDF-only endpoint is the only place that actually triggers the load.
    """
    from weasyprint import HTML  # noqa: PLC0415 — intentional lazy import

    return HTML(string=html).write_pdf()


def report_pdf(db: Session, project: Project, crawl: Crawl) -> bytes:
    """One-shot helper used by the PDF endpoint. Reuses the HTML template
    rendered by :func:`report_html` and runs it through WeasyPrint."""
    return render_pdf(report_html(db, project, crawl))


def render_comparison_html(ctx) -> str:  # type: ignore[no-untyped-def]
    """Render the crawl-vs-crawl comparison template.

    ``ctx`` is a ``backend.app.services.comparison.ComparisonContext`` —
    typed via duck typing here to avoid an import cycle (comparison.py
    already imports the labels/orders from this module).
    """
    template = _env.get_template("reports/crawl_comparison.html")
    return template.render(
        ctx=ctx,
        severity_label=SEVERITY_LABELS,
        severity_order=SEVERITY_ORDER,
        format_score=_format_score,
        format_datetime=_format_datetime,
        format_delta=_format_delta,
        score_class=_score_class,
        delta_class=_delta_class,
    )


# ---- helpers --------------------------------------------------------------


def _to_finding_category(cat: IssueCategory):  # type: ignore[no-untyped-def]
    """Translate ORM enum → analyzer enum (they're separate types on purpose)."""
    from analyzers.base import FindingCategory

    return FindingCategory(cat.value)


def _to_issue_severity(sev) -> IssueSeverity:  # type: ignore[no-untyped-def]
    return IssueSeverity(sev.value)


def _page_url_for(issues: Iterable[Issue]) -> list[str | None]:
    return [getattr(i.page, "url", None) for i in issues]


def _maybe_float(v) -> float | None:  # type: ignore[no-untyped-def]
    return float(v) if v is not None else None


def _format_score(v: float | None) -> str:
    return "—" if v is None else f"{v:.0f}%"


def _format_datetime(v) -> str:  # type: ignore[no-untyped-def]
    if v is None:
        return "—"
    return v.strftime("%d.%m.%Y %H:%M")


def _score_class(score: float | None) -> str:
    """CSS class for the score colour pill."""
    if score is None:
        return "score-na"
    if score >= 80:
        return "score-good"
    if score >= 60:
        return "score-mid"
    return "score-bad"


def _format_delta(delta: float | None) -> str:
    """Human-readable score delta (``+5``, ``-3``, ``±0``, ``—``)."""
    if delta is None:
        return "—"
    if delta == 0:
        return "±0"
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.0f}"


def _delta_class(delta: float | None) -> str:
    """CSS class for the delta arrow — green up, red down, neutral zero."""
    if delta is None or delta == 0:
        return "delta-zero"
    return "delta-up" if delta > 0 else "delta-down"
