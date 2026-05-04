# SEO-Tool (Seobility-Klon)

Selbst-gehostetes Onpage-SEO-Analyse-Tool. Crawlt Domains, prüft Tech/Meta/Struktur/Content und erstellt Reports — Multi-Projekt-fähig, alle Daten bleiben lokal.

Siehe [PLAN.md](PLAN.md) für die Architektur und Phasenplan.

## Status

**Phase 4B (Tippfehler-Check via LanguageTool) abgeschlossen.** Optionaler 5. Crawl-Pass — pro HTML-Seite POST an die LanguageTool-API, zurück kommen Spelling/Grammatik-Matches. Als `content.spelling.errors`-Finding (TIP) auf Seiten mit ≥ N Auffälligkeiten (Default-Schwelle 5, konfigurierbar). Default **opt-in via `CRAWLER_SPELLCHECK_ENABLED=true`** — der LT-Container kommt mit ~2 GB Image und ~600 MB RAM, deshalb hinter einem Flag versteckt. Läuft im selben asyncio-Loop wie die anderen Probes, Failure ist best-effort. **208 grüne Tests** (war 199).

**Phase 8-A (UI-Polish) abgeschlossen.** Drei Quality-of-Life-Verbesserungen für die Web-UI:

- **Live-Polling**: AutoRefresh-Component aktualisiert Projekt- und Crawl-Detail-Page alle 5 s automatisch, solange ein Crawl im `queued`- oder `running`-Status ist. Kein manuelles Reloaden mehr.
- **Resources-Drilldown** auf der Page-Detail-Page: zeigt die gefundenen CSS/JS/Image-Ressourcen samt Status-Code und Mixed-Content-Flag (Daten waren in DB, wurden aber nirgends angezeigt). Page-Detail-API liefert jetzt `resources: ResourceRead[]` mit.
- **Sitemap-Übersicht** auf der Projekt-Detail-Page: neuer Endpoint `GET /api/projects/{id}/sitemaps` listet alle gefundenen Sitemaps mit URL-Count, Last-Fetched-At und Fetch-Error-Status.

**199 grüne Tests** (war 195).

Phase 7-C (Crawl-Vergleich + CSV-Export): siehe vorherige Releases.

- **Crawl-vs-Crawl-Vergleich**: neuer Endpoint `GET /api/projects/{pid}/crawls/{cid}/compare/{other_id}.html`. Diff über `(rule_id, page_url)` mit drei Buckets pro Kategorie — neue Findings (in B nicht in A), behobene (in A nicht in B), persistente. Score-Deltas pro Kategorie + Overall, Reihenfolge wird automatisch chronologisch normalisiert (kleinere Crawl-ID = "vorher"). Eigenes Jinja2-Template ([crawl_comparison.html](backend/app/templates/reports/crawl_comparison.html)) mit Score-Karten, Delta-Pfeilen und farbcodierten Badges. Frontend: „Vergleichen mit…"-Dropdown auf der Crawl-Detail-Page (zeigt alle anderen completed Crawls).
- **CSV-Export**: `GET /api/projects/{pid}/crawls/{cid}/issues.csv` streamt Findings als UTF-8-CSV mit BOM (Excel-kompatibel für Umlaute), JSON-serialisierte Payload-Spalte. Frontend: „CSV ↓"-Button. Streaming via `yield_per(500)` damit Crawls mit hunderttausenden Findings nicht den Worker sprengen.

**195 grüne Tests** (war 181).

Phase 7-B: PDF via WeasyPrint (Lazy-Import + GTK-System-Deps in Backend-Dockerfile).
Phase 7-A: HTML-Report-Service ([backend/app/services/reports.py](backend/app/services/reports.py)) + Jinja2-Template.

Phase 7-A: HTML-Report-Service ([backend/app/services/reports.py](backend/app/services/reports.py)) + Jinja2-Template ([backend/app/templates/reports/crawl_report.html](backend/app/templates/reports/crawl_report.html)).

Vorherige Phasen:
- Phase 1B-2: Resource-Crawl (CSS/JS/Image-Status, Mixed-Content).
- Phase 1B-1: Sitemap-Discovery + Sitemap-Diff.
- Phase 4A: Content-Modul (Hauptinhalt via trafilatura, Page-Duplicates exakt + MinHash, Block-Boilerplate, Keyword-im-Body, Cannibalization).
- Phase 3: Next.js-14-Frontend + Backend-API für Crawl-Detail, Summary, Issues, Pages.
- Phase 2: Strukturanalyzer mit 13 Regeln + Externe-Link-Checker.
- Phase 1A: Async-Crawler + Tech/Meta-Analyzer mit 22 Regeln.

Noch offen: Phase 5 (Keyword-Tracking via GSC), Phase 6 (Backlink-Monitoring), Pagination/Such-Filter im Frontend.

Nächster Schritt: **Phase 5 (Keyword-Tracking via GSC)** — braucht User-seitige Google-Cloud-OAuth-Setup.

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
- [x] Phase 1A — Crawler + Tech/Meta-Modul (Backend)
- [x] Phase 1B-1 — Sitemap-Discovery + Sitemap-Diff
- [x] Phase 1B-2 — Resource-Crawl (CSS/JS/Image-Status, Mixed-Content)
- [x] Phase 2 — Struktur-Modul (Backend)
- [x] Phase 3 — Web-UI (Next.js)
- [x] Phase 4A — Content-Modul (Hauptinhalt, Duplicates, Cannibalization)
- [x] Phase 4B — Tippfehler-Check via LanguageTool (opt-in)
- [x] Phase 7-A — HTML-Report pro Crawl
- [x] Phase 7-B — PDF-Export (WeasyPrint)
- [x] Phase 7-C — Crawl-A-vs-B-Vergleich + CSV-Export
- [x] Phase 8-A — UI-Polish (Live-Polling, Resources/Sitemap-Drilldown)
- [ ] Phase 5 — Keyword-Tracking via Google Search Console
- [ ] Phase 6 — Backlink-Monitoring via GSC + Bing WMT
