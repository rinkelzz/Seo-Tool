# Deployment-Anleitung: SEO-Tool auf Portainer (Proxmox-LXC) via GHCR

Diese Anleitung deployt den Stack via Portainer-Stack-Repository, mit Images aus GitHub Container Registry. Bei jedem Push auf `main` baut GitHub Actions ein neues Image, Portainer pullt es beim nächsten Stack-Update automatisch.

## Voraussetzungen-Check

- LXC mit Docker und laufendem Portainer (hast du)
- LXC braucht Internet (für GHCR-Pull)
- Auf Proxmox: LXC sollte `nesting=1` und `keyctl=1` Features haben (Standard wenn Docker schon läuft)
- GitHub-Account (für Repo + GHCR)
- Lokal: `git` installiert

## Teil 1: GitHub-Repo einrichten

### 1.1 Neues Repo anlegen

Auf https://github.com/new ein neues Repo anlegen, z.B. `seo-tool`. **Privates Repo** ist okay — GHCR funktioniert auch privat (du brauchst dann nur einen Pull-Token im LXC).

### 1.2 Lokal Repo initialisieren und pushen

Im Projekt-Ordner (`C:\Users\tim\Documents\Claude\Projects\Seo`):

```powershell
cd C:\Users\tim\Documents\Claude\Projects\Seo
git init
git branch -m main
git add .
git commit -m "Phase 0: project skeleton"
git remote add origin https://github.com/DEIN-USER/seo-tool.git
git push -u origin main
```

Ersetze `DEIN-USER` durch deinen GitHub-Usernamen.

### 1.3 GitHub Actions baut das Image

Nach dem Push triggert `.github/workflows/build.yml` automatisch:
1. Tests laufen
2. Image wird gebaut und nach `ghcr.io/DEIN-USER/seo-tool:latest` gepusht

Im Repo unter "Actions" siehst du den Status. Beim ersten Lauf dauert der Build 5–10 Minuten.

### 1.4 GHCR-Image öffentlich/privat machen

Standardmäßig ist das GHCR-Package privat. Auf https://github.com/DEIN-USER?tab=packages findest du `seo-tool`. Klicke drauf → Package settings:

- **Privates Image** (empfohlen): du musst auf dem LXC einen Pull-Token einrichten (siehe 2.2)
- **Öffentliches Image**: Portainer kann ohne Auth pullen — einfacher, aber jeder im Internet könnte das Image runterladen (nicht den Code, der ist im Repo separat)

## Teil 2: LXC für GHCR-Pull vorbereiten

### 2.1 Falls Image öffentlich ist
Skip diesen Abschnitt.

### 2.2 Falls Image privat (empfohlen)

Auf dem LXC einmal `docker login` mit einem GitHub Personal Access Token:

```bash
# Auf https://github.com/settings/tokens/new einen "classic" PAT erstellen
# mit Scope: read:packages
# Token kopieren

# Auf dem LXC (SSH):
echo "DEIN-PAT" | docker login ghcr.io -u DEIN-GITHUB-USER --password-stdin
```

Damit liegt unter `~/.docker/config.json` die Auth-Info. Portainer-Stacks können Images pullen.

## Teil 3: Portainer-Stack einrichten

### 3.1 Im Portainer-UI: Neues Stack anlegen

1. Linkes Menü: **Stacks → + Add stack**
2. Name: `seo-tool`
3. Build method: **Repository**
4. Repository:
   - URL: `https://github.com/DEIN-USER/seo-tool`
   - Reference: `refs/heads/main`
   - Authentication: **on** (auch wenn das Repo privat ist; bei öffentlichem Repo kann es aus bleiben)
     - Username: dein GitHub-User
     - Personal Access Token: derselbe PAT von oben (oder ein separater mit `repo`-Scope)
5. Compose path: `infra/docker-compose.prod.yml`
6. **Automatic updates: on**, Mechanism **Polling**, Interval `5m`
   - Bei Push auf `main` baut GH Actions das neue Image, Portainer pullt es alle 5 Minuten und startet die Container neu

### 3.2 Environment variables eintragen

Im selben Formular gibts den Reiter **Environment variables**. Trag ein:

| Name | Beispielwert | Pflicht |
|---|---|---|
| `IMAGE_REPO` | `ghcr.io/DEIN-USER/seo-tool` | ja |
| `IMAGE_TAG` | `latest` | nein, default `latest` |
| `POSTGRES_PASSWORD` | (irgendein langes Passwort) | ja |
| `POSTGRES_USER` | `seo` | nein, default `seo` |
| `POSTGRES_DB` | `seo` | nein, default `seo` |
| `APP_API_TOKEN` | (langer Random-String, z.B. `openssl rand -hex 32`) | ja — der schützt deine API |
| `APP_LOG_LEVEL` | `INFO` | nein |
| `BACKEND_PORT` | `8000` | nein, default `8000` |
| `CRAWLER_USER_AGENT` | `SeoToolBot/0.1` | nein |
| `CRAWLER_MAX_CONCURRENCY` | `8` | nein |

Generier dir den `APP_API_TOKEN` z.B. so: `openssl rand -hex 32` auf dem LXC.

### 3.3 Stack deployen

Knopf **Deploy the stack**. Portainer:
1. Klont das Repo
2. Liest `infra/docker-compose.prod.yml`
3. Pullt `ghcr.io/.../seo-tool:latest`
4. Startet `db`, `redis`, `backend` (führt automatisch `alembic upgrade head` aus), `worker`

Im Stack-Status siehst du nach 1–2 Minuten alle 4 Container als **running**.

## Teil 4: Smoke-Tests

### 4.1 Health-Check

Aus dem LXC oder von deinem Rechner (wenn der Port erreichbar ist):

```bash
curl http://LXC-IP:8000/health
```

Antwort: `{"status":"ok","env":"production"}`

### 4.2 Erstes Projekt anlegen

```bash
TOKEN="DEIN-APP-API-TOKEN"
curl -X POST http://LXC-IP:8000/api/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","domain":"example.com","base_url":"https://example.com/"}'
```

Antwort: `{"id":1,"name":"Test",...}`

### 4.3 Crawl triggern

```bash
curl -X POST http://LXC-IP:8000/api/projects/1/crawls \
  -H "Authorization: Bearer $TOKEN"
```

Im Worker-Log (Portainer → Stack → worker → Logs) solltest du `crawl_started` und `crawl_completed` sehen. (Phase 0 macht noch keinen echten Crawl, nur den Status-Update.)

### 4.4 OpenAPI-Doku

Im Browser: `http://LXC-IP:8000/docs` → vollständige Swagger-UI mit allen Endpoints.

## Teil 5: Updates ausrollen

Nach Code-Änderungen einfach pushen:

```bash
git add .
git commit -m "feature xy"
git push
```

GitHub Actions baut das neue Image. Portainer pollt alle 5 Minuten und macht automatisch:
1. `git pull` im Stack-Workdir
2. `docker compose pull` (zieht das neue `:latest`)
3. `docker compose up -d` (startet Container mit neuem Image)

Wenn dir 5 Minuten zu lange sind: in Portainer **Stack → Update the stack → Pull and redeploy** — manuell sofort.

## Teil 6: Backup

Die Daten leben in zwei Docker-Volumes: `seo-tool_db_data` und `seo-tool_redis_data`.

**Postgres-Backup** (aus dem LXC, z.B. als Cronjob):

```bash
docker exec seo-tool-db-1 pg_dump -U seo seo > /var/backups/seo-$(date +%F).sql
```

Redis kannst du ignorieren (nur Job-Queue, regeneriert sich).

## Troubleshooting

**Container starten nicht / "image not found":**
- Prüfen ob das GHCR-Image existiert (auf github.com/DEIN-USER?tab=packages)
- Bei privatem Image: `docker login` auf dem LXC korrekt? Test: `docker pull ghcr.io/DEIN-USER/seo-tool:latest`

**Backend startet, aber Endpoints werfen 500:**
- Logs im Portainer (`Stack → backend → Logs`)
- Häufigster Grund: `DATABASE_URL` falsch oder `db`-Container noch nicht ready

**Alembic-Fehler beim Start:**
- Backend führt `alembic upgrade head` automatisch aus. Bei Schema-Konflikt (z.B. nach Schema-Änderung): einmalig `docker exec seo-tool-backend-1 alembic upgrade head`

**Worker pickt keine Jobs:**
- Worker-Logs prüfen
- Redis-Connectivity: `docker exec seo-tool-worker-1 python -c "from redis import Redis; Redis.from_url('redis://redis:6379/0').ping()"`

**Auto-Update tut nichts:**
- In Portainer: Stack → Settings → "Automatic updates" muss **on** sein, "Re-pull image" auch
- Image-Tag muss `latest` sein (oder konkret das, was GH Actions pusht)

## Sicherheits-Notizen

- `APP_API_TOKEN` schützt die API. Niemals ins Repo committen — nur in Portainer-Env.
- Wenn du den Backend-Port nach außen öffnest: nutze einen Reverse-Proxy (Caddy, Traefik, nginx) mit TLS davor. Sonst läuft die API über HTTP unverschlüsselt.
- Postgres ist nur Container-intern erreichbar (kein Port-Mapping in `docker-compose.prod.yml`) — gut so.

---

**Stand:** 2026-05-01, Phase 0. Mit Phase 1+ ändert sich an dieser Anleitung nichts — nur das Image-Tag wandert weiter.
