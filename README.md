# SEO-Tool (Seobility-Klon)

Selbst-gehostetes Onpage-SEO-Analyse-Tool. Crawlt Domains, prüft Tech/Meta/Struktur/Content und erstellt Reports — Multi-Projekt-fähig, alle Daten bleiben lokal.

Siehe [PLAN.md](PLAN.md) für die Architektur und Phasenplan.

## Status

**Phase 3 (Web-UI) abgeschlossen.** Next.js 14 (App Router, Server Components) + Tailwind 3 + selbstgebaute shadcn-Primitive im neuen `web/`-Verzeichnis. Server-seitiger API-Client liest `APP_API_TOKEN` aus env und proxiert FastAPI-Calls — der Browser sieht den Token nie. Pages: Projekt-Liste + Anlegen, Projekt-Übersicht mit Crawl-Historie und „Crawl starten"-Button, Crawl-Detail mit Score-Karten + Severity/Kategorie-gefilterter Issue-Tabelle, Page-Detail mit allen Meta-Daten, Bildern, Links und Findings. Backend um `GET /crawls/{id}`, `/summary`, `/issues` (paginiert + filterbar), `/pages`, `/pages/{id}` erweitert. **121 grüne Backend-Tests**, Next.js typecheck + production build sauber.

Vorherige Phasen:
- Phase 1A: Async-Crawler (`httpx` + `selectolax`) mit BFS, Concurrency, robots.txt; Tech/Meta-Analyzer mit 22 Regeln.
- Phase 2: Strukturanalyzer mit 13 Regeln (Klicktiefe, Orphan-Detection, Outlink-Auffälligkeiten, Anchor-Hygiene, Canonical, Redirect-Ketten/Loops, externe Link-Health) + asynchroner Externe-Link-Checker.

Noch offen in Phase 1 (Teil B): Sitemap-Discovery, Ressourcen-Crawl (CSS/JS).

Nächster Schritt: **Phase 4 (Content-Modul)** — Hauptinhalt-Extraktion, Duplicate-Content-Detection (MinHash/SimHash), Boilerplate-Erkennung, Keyword-Cannibalization, Tippfehler via LanguageTool.

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

# 5. Frontend
# http://localhost:3000
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
web/            Next.js-Frontend (Server Components, Tailwind)
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

### Frontend lokal

```bash
cd web
npm install
npm run dev   # http://localhost:3000

# Vor dem Push:
npm run typecheck
npm run build
```

Das Frontend braucht `API_URL` (Default `http://backend:8000` für docker-compose, lokal `http://localhost:8000`) und `API_TOKEN` (= `APP_API_TOKEN` aus der `.env`). Beide werden ausschliesslich serverseitig gelesen — der Token landet nie im Browser.

## Phasen (Kurzfassung aus PLAN.md)

- [x] Phase 0 — Grundgerüst
- [x] Phase 1A — Crawler + Tech/Meta-Modul (Backend); 1B (Sitemap/Resources) offen
- [x] Phase 2 — Struktur-Modul (Backend)
- [x] Phase 3 — Web-UI (Next.js)
- [ ] Phase 4 — Content-Modul
- [ ] Phase 4 — Keyword-Tracking via Google Search Console
- [ ] Phase 5 — Backlink-Monitoring via GSC + Bing WMT
- [ ] Phase 6 — Reports + Multi-Projekt-Polish
