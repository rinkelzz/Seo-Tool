"""Score-calculation tests."""

from __future__ import annotations

from analyzers.base import Finding, FindingCategory, FindingSeverity
from analyzers.scoring import compute_scores, overall_score
from analyzers.tech_meta import (
    RULE_H1_MISSING,
    RULE_LANG_MISSING,
    RULE_TITLE_MISSING,
)


def test_zero_pages_returns_full_score() -> None:
    scores = compute_scores([], pages_evaluated=0)
    assert all(v == 100.0 for v in scores.values())


def test_no_findings_full_score() -> None:
    scores = compute_scores([], pages_evaluated=10)
    assert scores[FindingCategory.TECH_META] == 100.0


def test_critical_finding_lowers_score() -> None:
    f = Finding(
        rule_id=RULE_TITLE_MISSING.rule_id,
        category=FindingCategory.TECH_META,
        severity=FindingSeverity.CRITICAL,
        page_url="https://example.com/",
    )
    scores = compute_scores([f], pages_evaluated=10)
    assert scores[FindingCategory.TECH_META] < 100.0


def test_more_findings_lower_score() -> None:
    base = compute_scores([], pages_evaluated=10)[FindingCategory.TECH_META]
    one = compute_scores(
        [
            Finding(
                rule_id=RULE_TITLE_MISSING.rule_id,
                category=FindingCategory.TECH_META,
                severity=FindingSeverity.CRITICAL,
                page_url="https://example.com/a",
            )
        ],
        pages_evaluated=10,
    )[FindingCategory.TECH_META]
    many = compute_scores(
        [
            Finding(
                rule_id=RULE_TITLE_MISSING.rule_id,
                category=FindingCategory.TECH_META,
                severity=FindingSeverity.CRITICAL,
                page_url=f"https://example.com/{i}",
            )
            for i in range(5)
        ],
        pages_evaluated=10,
    )[FindingCategory.TECH_META]
    assert base > one > many


def test_critical_lowers_more_than_tip() -> None:
    crit = compute_scores(
        [
            Finding(
                rule_id=RULE_TITLE_MISSING.rule_id,
                category=FindingCategory.TECH_META,
                severity=FindingSeverity.CRITICAL,
                page_url="https://example.com/",
            )
        ],
        pages_evaluated=10,
    )[FindingCategory.TECH_META]
    tip = compute_scores(
        [
            Finding(
                rule_id=RULE_LANG_MISSING.rule_id,
                category=FindingCategory.TECH_META,
                severity=FindingSeverity.TIP,
                page_url="https://example.com/",
            )
        ],
        pages_evaluated=10,
    )[FindingCategory.TECH_META]
    assert crit < tip


def test_score_clamped_to_zero() -> None:
    # Pile a critical finding on every rule for every page — score should clamp at 0.
    findings = [
        Finding(
            rule_id=RULE_TITLE_MISSING.rule_id,
            category=FindingCategory.TECH_META,
            severity=FindingSeverity.CRITICAL,
            page_url=f"https://example.com/{i}",
        )
        for i in range(10000)
    ]
    score = compute_scores(findings, pages_evaluated=1)[FindingCategory.TECH_META]
    assert score == 0.0


def test_other_categories_unaffected_by_tech_findings() -> None:
    f = Finding(
        rule_id=RULE_H1_MISSING.rule_id,
        category=FindingCategory.TECH_META,
        severity=FindingSeverity.CRITICAL,
        page_url="https://example.com/",
    )
    scores = compute_scores([f], pages_evaluated=10)
    assert scores[FindingCategory.STRUCTURE] == 100.0
    assert scores[FindingCategory.CONTENT] == 100.0


def test_overall_score_is_mean() -> None:
    scores = {
        FindingCategory.TECH_META: 80.0,
        FindingCategory.STRUCTURE: 90.0,
        FindingCategory.CONTENT: 70.0,
    }
    assert overall_score(scores) == 80.0
