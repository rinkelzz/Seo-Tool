# SEO-Tool (Seobility-Klon)

Selbst-gehostetes Onpage-SEO-Analyse-Tool. Crawlt Domains, prüft Tech/Meta/Struktur/Content und erstellt Reports — Multi-Projekt-fähig, alle Daten bleiben lokal.

Siehe [PLAN.md](PLAN.md) für die Architektur und Phasenplan.

## Status

**Phase 7-B (PDF-Export via WeasyPrint) abgeschlossen.** Reports gibt's jetzt als HTML *und* PDF — gleiche Datenpipeline, gleiches Template. Neuer Endpoint `GET /api/projects/{pid}/crawls/{cid}/report.pdf` rendert via WeasyPrint server-seitig und liefert `application/pdf`-Bytes mit `Content-Disposition: inline; filename="seo-report-<domain>-crawl-<id>.pdf"`. WeasyPrint wird **lazy importiert**, sodass der Rest des Codes auf Maschinen ohne GTK-Stack importierbar bleibt (z.B. Windows-Dev-Env oder CI ohne Pango/Cairo). Backend-Dockerfile um GTK-System-Pakete erweitert (Pango/Cairo/HarfBuzz/Cairo/GdkPixbuf + DejaVu-Fonts). Frontend-Passthrough-Route `/report.pdf` reicht Content-Type und Content-Disposition durch; „PDF herunterladen"-Button neben „Report ansehen". **181 grüne Tests** (war 177).

Phase 7-C (Crawl-A-vs-B-Vergleich, CSV-Export) folgt separat.

Phase 7-A: HTML-Report-Service ([backend/app/services/reports.py](backend/app/services/reports.py)) + Jinja2-Template ([backend/app/templates/reports/crawl_report.html](backend/app/templates/reports/crawl_report.html)).

Vorherige Phasen:
- Phase 1B-2: Resource-Crawl (CSS/JS/Image-Status, Mixed-Content).
- Phase 1B-1: Sitemap-Discovery + Sitemap-Diff.
- Phase 4A: Content-Modul (Hauptinhalt via trafilatura, Page-Duplicates exakt + MinHash, Block-Boilerplate, Keyword-im-Body, Cannibalization).
- Phase 3: Next.js-14-Frontend + Backend-API für Crawl-Detail, Summary, Issues, Pages.
- Phase 2: Strukturanalyzer mit 13 Regeln + Externe-Link-Checker.
- Phase 1A: Async-Crawler + Tech/Meta-Analyzer mit 22 Regeln.

Noch offen: Phase 4B (Tippfehler via LanguageTool — separater PR wegen Java-Toolchain), Phase 7-C (Crawl-Vergleich, CSV-Export).

Nächster Schritt: **Phase 7-C (Crawl-Vergleich + CSV-Export)**, **Phase 5 (Keyword-Tracking via GSC)** oder UI-Polish (Live-Polling, Resource-/Sitemap-Drilldown).

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
- [x] Phase 4A — Content-Modul (Hauptinhalt, Duplicates, Cannibalization); 4B (LanguageTool) offen
- [x] Phase 7-A — HTML-Report pro Crawl
- [x] Phase 7-B — PDF-Export (WeasyPrint)
- [ ] Phase 7-C — Crawl-A-vs-B-Vergleich, CSV-Export
- [ ] Phase 5 — Keyword-Tracking via Google Search Console
- [ ] Phase 6 — Backlink-Monitoring via GSC + Bing WMT
