"""RQ queue helpers — used by the API to enqueue jobs for the worker."""

from functools import lru_cache

from redis import Redis
from rq import Queue

from backend.app.core.settings import get_settings


@lru_cache
def get_redis() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url)


@lru_cache
def get_crawl_queue() -> Queue:
    return Queue("crawl", connection=get_redis())
