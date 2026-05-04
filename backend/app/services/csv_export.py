"""CSV exporters.

Streams CSV directly out — no in-memory accumulation — so a project with
hundreds of thousands of issues exports without blowing the worker.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.issue import Issue
from backend.app.models.page import Page

_ISSUE_HEADER = [
    "issue_id",
    "rule_id",
    "category",
    "severity",
    "page_url",
    "page_id",
    "payload",
    "created_at",
]


def stream_issues_csv(db: Session, crawl_id: int) -> Iterator[bytes]:
    """Yield CSV rows for every issue in ``crawl_id`` as UTF-8 bytes.

    First yield is the header row; each subsequent yield is one finding.
    Rows are emitted as bytes (with a UTF-8 BOM up front so Excel opens
    German umlauts correctly without prompting for an encoding).
    """
    yield "﻿".encode()  # BOM for Excel UTF-8 detection
    yield _csv_row(_ISSUE_HEADER)

    stmt = (
        select(Issue, Page.url)
        .outerjoin(Page, Issue.page_id == Page.id)
        .where(Issue.crawl_id == crawl_id)
        .order_by(Issue.severity.desc(), Issue.id.asc())
    )

    for issue, page_url in db.execute(stmt).yield_per(500):
        yield _csv_row(
            [
                issue.id,
                issue.rule_id,
                issue.category.value,
                issue.severity.value,
                page_url or "",
                issue.page_id if issue.page_id is not None else "",
                json.dumps(issue.payload, ensure_ascii=False) if issue.payload else "",
                issue.created_at.isoformat() if issue.created_at else "",
            ]
        )


def _csv_row(values: Iterable[object]) -> bytes:
    """Render one CSV row to UTF-8 bytes via ``csv.writer``.

    Going through ``csv.writer`` (rather than f-string concatenation)
    handles quoting/escaping of cells containing commas, quotes, and
    newlines correctly.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["" if v is None else str(v) for v in values])
    return buffer.getvalue().encode("utf-8")
