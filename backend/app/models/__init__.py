"""SQLAlchemy-Models. Importiert hier, damit Alembic alle Tabellen findet."""

from backend.app.models.backlink import Backlink
from backend.app.models.content_block import ContentBlock
from backend.app.models.crawl import Crawl, CrawlStatus
from backend.app.models.image import Image
from backend.app.models.issue import Issue, IssueSeverity
from backend.app.models.keyword import Keyword, KeywordRanking
from backend.app.models.link import Link
from backend.app.models.page import Page
from backend.app.models.project import Project
from backend.app.models.resource import Resource, ResourceType
from backend.app.models.sitemap import Sitemap

__all__ = [
    "Backlink",
    "ContentBlock",
    "Crawl",
    "CrawlStatus",
    "Image",
    "Issue",
    "IssueSeverity",
    "Keyword",
    "KeywordRanking",
    "Link",
    "Page",
    "Project",
    "Resource",
    "ResourceType",
    "Sitemap",
]
