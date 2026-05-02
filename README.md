# SEO-Tool (Seobility-Klon)

Selbst-gehostetes Onpage-SEO-Analyse-Tool. Crawlt Domains, prüft Tech/Meta/Struktur/Content und erstellt Reports — Multi-Projekt-fähig, alle Daten bleiben lokal.

Siehe [PLAN.md](PLAN.md) für die Architektur und Phasenplan.

## Status

**Phase 0 (Grundgerüst) abgeschlossen** — Repo-Struktur, Docker-Setup, Datenbank-Schema (11 Tabellen + Alembic), FastAPI mit Project-CRUD und Crawl-Trigger, RQ-Worker mit Crawl-Job-Stub, 10 grüne Tests, ruff + black sauber.

Nächster Schritt: **Phase 1 (Crawler + Tech/Meta-Modul)**.

## Schnellstart

```bash
# 1. .env anlegen
cp .env.example .env

# 2. Stack starten
docker compose -f infra/docker-compose.yml up -d --build

# 3. Migrations laufen lassen
docker compose -f infra/docker-compose.yml exec backend alembic upgrade head

# 4. Health-Check
curl http://localhost:8000/health
```

## Verzeichnisstruktur

```
backend/        FastAPI-App (Web-API)
worker/         RQ-Worker (Crawl-Jobs)
crawler/        HTTP-Crawler-Engine (geteilt von Backend + Worker)
analyzers/      Analyzer-Module (Tech/Meta, Struktur, Content)
migrations/     Alembic-Migrations
tests/          pytest-Tests
infra/          docker-compose.yml, Dockerfiles
web/            Frontend (kommt später, Phase 1+)
```

## Entwicklung

```bash
# Lokale Python-Umgebung (außerhalb von Docker)
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

# Tests
pytest

# Linting
ruff check .
black .
mypy backend worker crawler analyzers
```

## Phasen (Kurzfassung aus PLAN.md)

- [x] Phase 0 — Grundgerüst
- [ ] Phase 1 — Crawler + Tech/Meta-Modul (MVP)
- [ ] Phase 2 — Struktur-Modul
- [ ] Phase 3 — Content-Modul
- [ ] Phase 4 — Keyword-Tracking via Google Search Console
- [ ] Phase 5 — Backlink-Monitoring via GSC + Bing WMT
- [ ] Phase 6 — Reports + Multi-Projekt-Polish
