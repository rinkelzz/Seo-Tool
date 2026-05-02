"""FastAPI application entrypoint."""

from fastapi import FastAPI

from backend.app.api import crawls, projects
from backend.app.core.settings import get_settings

settings = get_settings()

app = FastAPI(
    title="SEO Tool",
    description="Self-hosted SEO analysis tool (Seobility-style)",
    version="0.1.0",
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "env": settings.app_env}


app.include_router(projects.router)
app.include_router(crawls.router)
