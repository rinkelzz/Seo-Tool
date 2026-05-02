# Seobility-Klon: Bauplan

**Projekt:** Eigener SEO-Analyse-Stack (Self-hosted, Multi-Projekt)
**Vorbild:** Seobility-Export `2026-04-29_venture-full-export.pdf` (220 Seiten gecrawlt, Onpage-Bereich „Gesamtexport")
**Stand:** 2026-04-30
**Ziel-Architektur:** Lokale Web-App, lauffähig per `docker compose up`, alle Daten bleiben bei dir.

---

## 1. Was Seobility laut deinem Export tatsächlich liefert

Aus dem PDF lassen sich exakt diese Analysemodule rekonstruieren — das ist die Funktionsliste, die wir nachbauen müssen:

**Technik & Meta**

- Charset, Sprachangabe, Komprimierung, Software-Version
- Redirect für `www.` und `https://`
- Durchschnittliche Antwortzeit (Buckets: schnell / mittel / lang)
- Problematische / doppelte Seitentitel, Meta-Descriptions
- Probleme mit H1, Heading-Struktur, Strong/Bold-Tags
- Fehlende Alt-Attribute, sehr große HTML-Seiten
- URL-Probleme: dynamische Parameter, Session-IDs, zu lange URLs, zu viele Unterverzeichnisse
- Eingebundene Dateien (Bilder, JS, CSS) — abrufbar, blockiert, unsicher unter https
- Robots.txt-Status, nicht analysierbare Datentypen, technische Probleme

**Struktur**

- Linktext-Analyse (identische Linktexte für unterschiedliche Seiten)
- Interne Verlinkung (Seiten mit zu vielen / zu wenigen)
- Weiterleitungen, fehlerhafte Weiterleitungen, Redirect-Schleifen
- Probleme mit externen Links (Status-Codes)
- Klicktiefe von der Startseite (≥3 Klicks ist Tipp)
- Canonical / Alternate Link Fehler
- Sitemap-Analyse: gefundene Sitemaps, URLs in Sitemaps, nur in Sitemaps gefundene URLs

**Inhalt**

- Duplicate Content (ganze Seiten)
- Doppelte Textblöcke / Boilerplate-Erkennung (im Export: „545 Inhalte/Textblöcke ... auf mehr als einer Seite")
- Keyword-Konkurrenz (Cannibalization)
- Keywords aus Title / H1 nicht im Text wiederverwendet
- Tippfehler-Erkennung

**Außerhalb des Exports, aber in Seobility enthalten** (von dir gewünscht):

- Keyword-Ranking-Tracking (Google SERP)
- Backlink-Monitoring

**Reporting**

- Optimierungs-Score pro Bereich (im PDF: 78 % / 84 % / 64 %)
- Priorisierte To-do-Liste mit „Sehr wichtig / Wichtig / Tipp"
- Historische Entwicklung („ab Crawling 2 verfügbar")
- Vollständiger PDF-Export

---

## 2. Tech-Stack-Entscheidung

| Schicht | Wahl | Begründung |
|---|---|---|
| **Crawler-Engine** | Python + `httpx` async + `selectolax` (HTML-Parser) | Schneller als BeautifulSoup, gutes Async-Verhalten, kein Browser-Overhead. `Scrapy` wäre Alternative, aber für unsere kontrollierten Crawls ist Eigenbau leichter zu integrieren. |
| **Headless-Browser (optional)** | Playwright (nur für JS-gerenderte Seiten) | Wird pro Projekt umschaltbar — die meisten Seiten brauchen ihn nicht. |
| **Backend / API** | FastAPI (Python) | Gleiche Sprache wie Crawler, gute async-Integration, automatische OpenAPI-Doku. |
| **Datenbank** | PostgreSQL 16 | Volltextsuche (Duplicate Content), JSONB für flexible Issue-Payloads, gute Aggregation. |
| **Job-Queue** | RQ (Redis Queue) | Einfacher als Celery, reicht für 1 Person + Cron-Scans. |
| **Frontend** | Next.js (React) + Tailwind + shadcn/ui | Dashboard, Drilldowns, Tabellen mit Filter — dafür ist Next.js angemessen. |
| **PDF-Reports** | WeasyPrint (HTML→PDF) | Reports werden als HTML-Templates gebaut und 1:1 zu PDF gerendert — gleiche Quelle für Web-Ansicht und Export. |
| **Tippfehler** | `language-tool-python` (LanguageTool, lokal) | Open-Source, läuft lokal, deutsch + englisch. |
| **SERP-Daten** | **Google Search Console API (kostenlos)** | Liefert Rankings, Impressionen, Klicks, CTR für eigene Domains. Einschränkung: keine Konkurrenz-Rankings, nur Durchschnittspositionen. Reicht für persönlichen Gebrauch. |
| **Backlink-Daten** | **Google Search Console + Bing Webmaster Tools (beide kostenlos)** | Beide haben Backlink-Reports. Zusammen ca. 60–70 % Coverage gegenüber Ahrefs. Kein eigener Backlink-Crawl. |
| **Deployment** | `docker compose` (Postgres + Redis + API + Worker + Web) | Ein Befehl zum Starten, alles isoliert, leicht backup-bar. |

---

## 3. Architektur-Übersicht

```
┌─────────────────────────────────────────────────────────────┐
│  Next.js Web-UI                                             │
│  - Projekt-Dashboard, Crawl-Historie, Issue-Drilldown       │
│  - Keyword-Rankings, Backlink-Monitor                       │
│  - PDF-Export-Trigger                                        │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST / OpenAPI
┌──────────────────────────▼──────────────────────────────────┐
│  FastAPI                                                    │
│  - Projekt-CRUD, Crawl-Trigger, Issue-Queries               │
│  - Auth (Single-User-Token zunächst)                        │
└──────┬───────────────────┬─────────────────────┬────────────┘
       │                   │                     │
┌──────▼──────┐   ┌────────▼────────┐   ┌────────▼─────────┐
│  PostgreSQL │   │  Redis (RQ)     │   │  Worker(s)       │
│  - Projekte │   │  - Crawl-Jobs   │   │  - Crawler       │
│  - Crawls   │   │  - Scheduler    │   │  - Analyzer      │
│  - Issues   │   │                 │   │  - SERP-Fetcher  │
│  - Pages    │   │                 │   │  - Backlink-Sync │
└─────────────┘   └─────────────────┘   └────────┬─────────┘
                                                 │
                            ┌────────────────────┼─────────────┐
                            │                    │             │
                      ┌─────▼──────┐    ┌────────▼──────┐  ┌───▼────────┐
                      │ Ziel-Site  │    │ DataForSEO    │  │ Ahrefs API │
                      │ (Crawling) │    │ (SERP)        │  │ (Backlinks)│
                      └────────────┘    └───────────────┘  └────────────┘
```

---

## 4. Datenmodell (Kern-Tabellen)

```
projects(id, name, domain, base_url, robots_respect, js_render, created_at)
crawls(id, project_id, started_at, finished_at, status, pages_crawled, score_tech, score_struct, score_content)
pages(id, crawl_id, url, status_code, response_time_ms, content_hash, title, meta_desc, h1, word_count, depth, html_size, ...)
links(id, crawl_id, source_page_id, target_url, anchor_text, rel, is_internal, is_followed)
images(id, page_id, src, alt, has_alt)
issues(id, crawl_id, page_id, rule_id, severity, payload_json)
content_blocks(id, page_id, block_hash, text_excerpt)  -- für Boilerplate / Duplicate-Block-Erkennung
keywords(id, project_id, keyword, location, device, language)
keyword_rankings(id, keyword_id, checked_at, position, url, serp_features_json)
backlinks(id, project_id, source_url, target_url, anchor, dr, first_seen_at, last_seen_at, status)
sitemaps(id, project_id, url, last_fetched_at, urls_count)
```

Issues werden **regel-basiert** geschrieben (`rule_id` z.B. `meta.title.duplicate`, `tech.response_time.medium`). Severity-Mapping spiegelt Seobility: `critical` / `important` / `tip`. Damit lassen sich Reports und To-do-Listen exakt rekonstruieren.

---

## 5. Phasenplan

Die Reihenfolge ist so gewählt, dass nach Phase 1 schon ein nutzbares Tool steht und jede weitere Phase additiv ist.

### Phase 0 — Grundgerüst *(ca. 1–2 Tage)*

- Repo-Struktur (`backend/`, `worker/`, `web/`, `infra/`)
- `docker-compose.yml` mit Postgres + Redis + Backend-Stub + Worker-Stub
- Alembic-Migrations, Basis-Schema, Test-Setup (pytest + httpx)
- CI: GitHub Actions oder lokal (Pre-commit, Ruff, Black, Mypy)

### Phase 1 — Crawler + Tech/Meta-Modul *(MVP, ca. 1 Woche)*

- HTTP-Crawler mit Concurrency-Limit, robots.txt-Respect, User-Agent-Rotation
- Sitemap-Discovery (`/sitemap.xml`, `/robots.txt` → Sitemap-Index)
- Ressourcen-Crawl (Bilder, CSS, JS) für „eingebundene Dateien"-Checks
- Analyzer-Module für alle Punkte aus §1 / Technik & Meta:
  - Title / Meta-Desc / H1 / Headings / Strong-Bold / Alt
  - URL-Heuristiken
  - Antwortzeit-Bucketing
  - Charset / Komprimierung / Sprache
- Score-Berechnung (gewichtete Issue-Counts → Prozent)
- Einfache Web-UI: Projekt anlegen, Crawl starten, Issue-Tabelle
- **Akzeptanz:** Eigene Domain crawlen, Score und To-do-Liste erscheint und matcht Seobility ±5 Punkte

### Phase 2 — Strukturmodul *(ca. 4–5 Tage)*

- Link-Graph-Aufbau während des Crawls
- Klicktiefe (BFS von Startseite)
- Linktext-Analyse (gleiche Anchors → unterschiedliche Targets)
- Externe-Link-Status-Checks (parallel, mit Throttling)
- Canonical / Alternate Validierung
- Redirect-Ketten und -Schleifen
- Sitemap-Diff (im Sitemap aber nicht gecrawlt / umgekehrt)

### Phase 3 — Content-Modul *(ca. 1 Woche)*

- Text-Extraktion (Hauptinhalt erkennen, Boilerplate trennen — `trafilatura` ist ein heißer Kandidat)
- Content-Hash + n-Gramm-Shingling für Duplicate-Detection (MinHash/SimHash)
- Block-Level-Duplicate (Header/Footer-Wiederholungen)
- Keyword-Extraktion (TF-IDF projektweit), Cannibalization-Erkennung
- Title/H1-Keywords ↔ Body-Vergleich
- LanguageTool-Integration für Tippfehler

### Phase 4 — Keyword-Tracking via Google Search Console *(ca. 3 Tage, 0 €)*

- OAuth-Anbindung an Google Search Console pro Projekt
- Täglicher Sync der GSC Search-Analytics-Daten (Queries, Pages, Impressions, Klicks, Position, CTR)
- Eigene Keyword-Liste pro Projekt (Filter über GSC-Daten)
- Verlaufs-Charts im Frontend (Position, CTR, Impressions über Zeit)
- *Einschränkung:* keine Konkurrenz-Rankings, nur eigene Domain. Falls später gewünscht, lässt sich DataForSEO als optionales Premium-Modul nachrüsten.

### Phase 5 — Backlink-Monitoring via GSC + Bing WMT *(ca. 3 Tage, 0 €)*

- OAuth-Anbindung an Google Search Console *Links*-Report
- API-Anbindung an Bing Webmaster Tools (kostenlose API, ergänzt GSC gut)
- Backlinks aus beiden Quellen mergen, deduplizieren
- Diff: neue / verlorene Backlinks zwischen Syncs
- Alerts auf Verluste / neue Top-Domains
- *Einschränkung:* keine DR/Spam-Scores wie bei Ahrefs. Falls später relevant, lässt sich Majestic Lite (~50 €/Mon) ergänzen.

### Phase 6 — Reports + Multi-Projekt-Polish *(ca. 1 Woche)*

- HTML→PDF-Report wie das Seobility-Beispiel (gleiche Struktur, eigenes Branding)
- Vergleich „Crawl 1 vs Crawl 2" (genau das +/- im PDF)
- Projekt-Übersicht / Cross-Projekt-Dashboard
- Geplante Crawls per Cron
- Daten-Export (CSV/JSON pro Issue-Typ)

**Gesamtzeit grob:** 5–7 Wochen Vollzeit, oder als Nebenprojekt 3–4 Monate. Phase 1 alleine ist nach ~1 Woche schon nutzbar.

---

## 6. Kostenübersicht (0 €-Strategie)

| Modul | Datenquelle | Kosten |
|---|---|---|
| Crawler / Tech-Meta / Struktur / Content | Eigener Crawler | **0 €** |
| Tippfehler | LanguageTool (lokal) | **0 €** |
| Keyword-Tracking (Phase 4) | Google Search Console API | **0 €** |
| Backlinks (Phase 5) | GSC + Bing Webmaster Tools | **0 €** |
| Hosting | Lokal auf deinem Rechner | **0 €** |
| **Laufende Kosten gesamt** | | **0 €/Monat** |

**Optionale Upgrades später** (nur falls echter Bedarf):
- DataForSEO für Konkurrenz-Rankings: ab ~5 €/Monat
- Majestic Lite für besseren Backlink-Index: ab ~50 €/Monat
- Hetzner VPS für nächtliche Crawls großer Sites: ~5 €/Monat

Wir bauen die Architektur so, dass diese später als Plugins anschließbar sind — keine Festlegung jetzt.

## 7. Offene Punkte (nicht-finanziell)

1. **Authentifizierung** — Single-User-Token reicht erstmal? Oder gleich richtige Auth (für später, falls du das jemand zeigen willst)?
2. **Hosting** — Auf deinem Rechner ist gratis, aber Crawls großer Sites blockieren deine Bandbreite. Für jetzt: lokal starten, später bei Bedarf auf NAS/VPS verschieben.
3. **Google Search Console Setup** — du brauchst pro Projekt verifizierten GSC-Zugriff. Hast du den für deine Domains schon? Falls nicht, das ist der erste Schritt vor Phase 4.

---

## 8. Sofort-nächster-Schritt-Vorschlag

Wenn du den Plan in Grundzügen ok findest, würde ich konkret als nächstes:

1. Repo-Skeleton anlegen (`docker-compose.yml`, FastAPI-Stub, leere Worker, Postgres-Migration mit Kern-Tabellen)
2. Crawler als isoliertes Python-Modul bauen, mit Tests gegen `httpbin` und 2–3 echte Test-URLs
3. Erstes Tech/Meta-Analyzer-Set (Title, Meta-Desc, H1) damit die Pipeline durchläuft
4. Minimal-UI: Projekt anlegen + Crawl starten + Issue-Liste

Damit hast du nach ~3 Tagen das Skelett laufen und kannst Module nachziehen.

---

## Anhang: Relevante Open-Source-Bausteine

- **Crawler:** `httpx`, `selectolax`, `urllib.robotparser`, `protego` (besseres robots.txt), `playwright` (optional)
- **Content:** `trafilatura` (Hauptinhalt-Extraktion), `datasketch` (MinHash für Duplicate)
- **Tippfehler:** `language-tool-python`
- **SEO-spezifisch:** `advertools` (sitemap parsing, robots, log analysis)
- **PDF:** `weasyprint`
- **Vergleichbare OSS-Projekte zur Inspiration:** Screaming Frog (kommerziell, nicht OSS), `siteliner.com` (closed), aber als Referenz für Algorithmen — `yacy`, `nutch`, einzelne SEO-Audit-Skripte auf GitHub.
