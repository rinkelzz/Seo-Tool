# SEO-Tool (Seobility-Klon)

Selbst-gehostetes Onpage-SEO-Analyse-Tool. Crawlt Domains, prüft Tech/Meta/Struktur/Content und erstellt Reports — Multi-Projekt-fähig, alle Daten bleiben lokal.

Siehe [PLAN.md](PLAN.md) für die Architektur und Phasenplan.

## Status

**Phase 2 (Strukturmodul) abgeschlossen.** Aufbauend auf Phase 1A: neuer Strukturanalyzer mit 13 Regeln — Klicktiefe (Tip/Important nach Schwellwerten), Orphan-Detection (Pages ohne eingehende interne Links), Outlink-Auffälligkeiten (keine / sehr viele), generische und mehrdeutige Anchor-Texte, Canonical-Hygiene (Cross-Domain, Mismatch), Redirect-Ketten (>2 Hops) und Redirect-Schleifen sowie externe Link-Health (broken / unreachable). Externer Link-Status-Checker (`HEAD` mit `GET`-Fallback bei 405/501) läuft als zweiter Pass nach dem Hauptcrawl, deduplizierte Probes, Throttling über Semaphore. `Page.redirect_chain` persistiert via Alembic-Migration. **109 grüne Tests** (war 84), ruff + black sauber.

Phase 1A liefert: Async-Crawler (`httpx` + `selectolax`) mit BFS, Concurrency, robots.txt; Tech/Meta-Analyzer mit 22 Regeln; Score pro Kategorie + Overall.

Noch offen in Phase 1 (Teil B): Sitemap-Discovery, Ressourcen-Crawl (CSS/JS), Web-UI für Issue-Drilldown.

Nächster Schritt: **Phase 3 (Content-Modul)** — Hauptinhalt-Extraktion, Duplicate-Content-Detection (MinHash/SimHash), Boilerplate-Erkennung, Keyword-Cannibalization, Title/H1-Keyword-Vergleich, Tippfehler via LanguageTool.

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
- [x] Phase 2 — Struktur-Modul (Backend)
- [ ] Phase 3 — Content-Modul
- [ ] Phase 4 — Keyword-Tracking via Google Search Console
- [ ] Phase 5 — Backlink-Monitoring via GSC + Bing WMT
- [ ] Phase 6 — Reports + Multi-Projekt-Polish
