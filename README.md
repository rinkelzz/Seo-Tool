# SEO-Tool (Seobility-Klon)

Selbst-gehostetes Onpage-SEO-Analyse-Tool. Crawlt Domains, prüft Tech/Meta/Struktur/Content und erstellt Reports — Multi-Projekt-fähig, alle Daten bleiben lokal.

Siehe [PLAN.md](PLAN.md) für die Architektur und Phasenplan.

## Status

**Phase 1B-1 (Sitemap-Discovery & -Diff) abgeschlossen.** Neuer `crawler/sitemap.py` liest `Sitemap:`-Direktiven aus `robots.txt` (Default `/sitemap.xml` als Fallback), folgt Sitemap-Index-Files rekursiv (depth-bounded auf 3, max 50 Sitemaps insgesamt), entgzippt `.xml.gz` transparent. Ergebnis wird als `Sitemap`-Rows pro Projekt persistiert (`urls` als JSONB-Liste, frische Crawls ersetzen ältere Snapshots). Strukturanalyzer um zwei neue Regeln erweitert: `structure.sitemap.in_sitemap_only` (URL deklariert aber nicht gecrawlt — important) und `structure.sitemap.in_crawl_only` (gecrawlt aber nicht im Sitemap — tip). **152 grüne Tests** (war 140).

Vorherige Phasen:
- Phase 4A: Content-Modul (Hauptinhalt via trafilatura, Page-Duplicates exakt + MinHash, Block-Boilerplate, Keyword-im-Body, Cannibalization).
- Phase 3: Next.js-14-Frontend + Backend-API für Crawl-Detail, Summary, Issues, Pages.
- Phase 2: Strukturanalyzer mit 13 Regeln + Externe-Link-Checker.
- Phase 1A: Async-Crawler + Tech/Meta-Analyzer mit 22 Regeln.

Noch offen: Phase 1B-2 (Resource-Crawl für CSS/JS), Phase 4B (Tippfehler via LanguageTool — separater PR wegen Java-Toolchain).

Nächster Schritt: **Phase 5 (Keyword-Tracking via Google Search Console)**, **Phase 7 (Reports + PDF-Export)** oder **Phase 1B-2**.

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
- [x] Phase 1A — Crawler + Tech/Meta-Modul (Backend); 1B-2 (Resource-Crawl CSS/JS) offen
- [x] Phase 1B-1 — Sitemap-Discovery + Sitemap-Diff
- [x] Phase 2 — Struktur-Modul (Backend)
- [x] Phase 3 — Web-UI (Next.js)
- [x] Phase 4A — Content-Modul (Hauptinhalt, Duplicates, Cannibalization); 4B (LanguageTool) offen
- [ ] Phase 4 — Keyword-Tracking via Google Search Console
- [ ] Phase 5 — Backlink-Monitoring via GSC + Bing WMT
- [ ] Phase 6 — Reports + Multi-Projekt-Polish
