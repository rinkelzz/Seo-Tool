# SEO-Tool (Seobility-Klon)

Selbst-gehostetes Onpage-SEO-Analyse-Tool. Crawlt Domains, prüft Tech/Meta/Struktur/Content und erstellt Reports — Multi-Projekt-fähig, alle Daten bleiben lokal.

Siehe [PLAN.md](PLAN.md) für die Architektur und Phasenplan.

## Status

**Phase 1 (Crawler + Tech/Meta-Modul) — Teil A abgeschlossen.** Async-Crawler (`httpx` + `selectolax`) mit BFS, Concurrency-Limit, robots.txt-Respect, Sitemap- und Resource-Crawl noch nicht enthalten. Tech/Meta-Analyzer mit 22 Regeln (Title, Meta-Description, H1, Alt-Texte, Antwortzeit, Sprache, URL-Hygiene, HTTP-Fehler, noindex, HTML-Größe, Duplicate-Detection für Title/Description). Score-Berechnung pro Kategorie + Overall. Worker-Job persistiert Pages, Images, Links, Issues und Scores in einer Transaktion. **84 grüne Tests**, ruff + black sauber.

Noch offen in Phase 1 (Teil B): Sitemap-Discovery, Ressourcen-Crawl (CSS/JS), Web-UI für Issue-Drilldown.

Nächster Schritt: entweder Phase 1-B oder direkt **Phase 2 (Strukturmodul)** — Link-Graph, Klicktiefe, Linktext-Analyse, Redirect-Ketten.

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
- [x] Phase 1A — Crawler + Tech/Meta-Modul (Backend); 1B (Sitemap/Resources/UI) offen
- [ ] Phase 2 — Struktur-Modul
- [ ] Phase 3 — Content-Modul
- [ ] Phase 4 — Keyword-Tracking via Google Search Console
- [ ] Phase 5 — Backlink-Monitoring via GSC + Bing WMT
- [ ] Phase 6 — Reports + Multi-Projekt-Polish
