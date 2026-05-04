# SEO-Tool (Seobility-Klon)

Selbst-gehostetes Onpage-SEO-Analyse-Tool. Crawlt Domains, prüft Tech/Meta/Struktur/Content und erstellt Reports — Multi-Projekt-fähig, alle Daten bleiben lokal.

Siehe [PLAN.md](PLAN.md) für die Architektur und Phasenplan.

## Status

**Phase 1B-2 (Resource-Crawl) abgeschlossen.** Damit ist Phase 1B komplett. Extractor sammelt zusätzlich `<link rel="stylesheet">`, `<script src>` (deduplikatfrei pro Page) — Bilder bleiben wie zuvor. Neuer `crawler/resources.py` probt nach dem Hauptcrawl jede distinct Resource-URL einmal (HEAD mit GET-Fallback bei 405/501, deduplikatfrei, throttled über Semaphore). Persistierung in neuer `Resource`-Tabelle (`url`, `resource_type` enum, `is_internal`, `is_mixed_content`, `status_code`). Tech-Meta-Analyzer um drei neue Regeln erweitert: `tech.resource.broken` (4xx/5xx), `tech.resource.unreachable` (DNS/Timeout) und `tech.resource.mixed_content` (HTTPS-Page → HTTP-Resource — der Browser blockt das). Mixed-Content ist ein reiner URL-Scheme-Check und feuert auch ohne Probe. **167 grüne Tests** (war 152).

Vorherige Phasen:
- Phase 1B-1: Sitemap-Discovery + Sitemap-Diff.
- Phase 4A: Content-Modul (Hauptinhalt via trafilatura, Page-Duplicates exakt + MinHash, Block-Boilerplate, Keyword-im-Body, Cannibalization).
- Phase 3: Next.js-14-Frontend + Backend-API für Crawl-Detail, Summary, Issues, Pages.
- Phase 2: Strukturanalyzer mit 13 Regeln + Externe-Link-Checker.
- Phase 1A: Async-Crawler + Tech/Meta-Analyzer mit 22 Regeln.

Noch offen: Phase 4B (Tippfehler via LanguageTool — separater PR wegen Java-Toolchain).

Nächster Schritt: **Phase 5 (Keyword-Tracking via Google Search Console)**, **Phase 7 (Reports + PDF-Export)** oder UI-Polish (Resource-/Sitemap-Drilldown im Frontend).

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
- [ ] Phase 4 — Keyword-Tracking via Google Search Console
- [ ] Phase 5 — Backlink-Monitoring via GSC + Bing WMT
- [ ] Phase 6 — Reports + Multi-Projekt-Polish
