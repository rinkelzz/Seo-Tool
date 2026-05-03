"""SEO analyzer modules.

Each analyzer takes a ``CrawlResult`` (the raw output of ``crawler.run_crawl``)
and produces a list of ``Finding`` records, which the worker then persists as
``Issue`` rows.
"""

from analyzers.base import Finding, FindingSeverity, Rule
from analyzers.scoring import compute_scores
from analyzers.tech_meta import TECH_META_RULES, analyze_tech_meta

__all__ = [
    "TECH_META_RULES",
    "Finding",
    "FindingSeverity",
    "Rule",
    "analyze_tech_meta",
    "compute_scores",
]
