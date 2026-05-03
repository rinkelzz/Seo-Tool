"""Scoring: turn findings + page count into per-category 0–100 % scores.

Idea (close to Seobility's display): for each category compute
``score = max(0, 100 * (1 - issue_load / max_load))`` where
- ``issue_load`` = sum of (rule.weight × severity_multiplier) over all findings
- ``max_load``   = pages_evaluated × per_page_capacity

``per_page_capacity`` is calibrated so that a clean site scores 100 and a site
where every page violates roughly half of the registered rules lands near 50.
We pick a fixed reference (sum of weights of the registered rules) so adding a
new rule of weight 0 doesn't shift existing scores.
"""

from __future__ import annotations

from collections import Counter

from analyzers.base import Finding, FindingCategory, FindingSeverity, registry

SEVERITY_MULTIPLIER: dict[FindingSeverity, float] = {
    FindingSeverity.CRITICAL: 3.0,
    FindingSeverity.IMPORTANT: 1.5,
    FindingSeverity.TIP: 0.5,
}


def compute_scores(
    findings: list[Finding], *, pages_evaluated: int
) -> dict[FindingCategory, float]:
    """Return a 0–100 score per category.

    With ``pages_evaluated == 0`` we return ``None``-like behaviour by emitting
    ``100.0`` for every category — there's nothing to deduct from. The caller
    can decide whether to display that as "n/a".
    """
    out: dict[FindingCategory, float] = {}
    for cat in FindingCategory:
        out[cat] = _score_for(cat, findings, pages_evaluated)
    return out


def _score_for(cat: FindingCategory, findings: list[Finding], pages_evaluated: int) -> float:
    if pages_evaluated <= 0:
        return 100.0

    cat_findings = [f for f in findings if f.category == cat]
    cat_rules = registry.by_category(cat)
    if not cat_rules:
        return 100.0

    issue_load = 0.0
    rule_index = {r.rule_id: r for r in cat_rules}
    severity_counts: Counter[FindingSeverity] = Counter()
    for f in cat_findings:
        rule = rule_index.get(f.rule_id)
        if rule is None:
            continue
        issue_load += rule.weight * SEVERITY_MULTIPLIER[rule.severity]
        severity_counts[rule.severity] += 1

    # Reference: every page could in theory hit roughly half of the rule weights
    # at "important" severity. We use the sum of weights as the per-page capacity.
    per_page_capacity = (
        sum(r.weight for r in cat_rules) * SEVERITY_MULTIPLIER[FindingSeverity.IMPORTANT]
    )
    max_load = per_page_capacity * pages_evaluated
    if max_load <= 0:
        return 100.0

    score = 100.0 * (1.0 - issue_load / max_load)
    return max(0.0, min(100.0, round(score, 2)))


def overall_score(per_cat: dict[FindingCategory, float]) -> float:
    """Simple unweighted mean; rounded to 2 decimals."""
    if not per_cat:
        return 100.0
    return round(sum(per_cat.values()) / len(per_cat), 2)
