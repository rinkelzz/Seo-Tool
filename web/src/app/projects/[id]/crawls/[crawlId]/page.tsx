import Link from "next/link";
import { notFound } from "next/navigation";

import { AutoRefresh } from "@/components/AutoRefresh";
import { CompareSelect } from "@/components/CompareSelect";
import { IssueTable } from "@/components/IssueTable";
import { ScoreCard } from "@/components/ScoreCard";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { api, ApiError } from "@/lib/api";
import { categoryLabel, formatDate, severityLabel, statusLabel } from "@/lib/format";
import type { IssueCategory, IssueSeverity } from "@/lib/types";

const SEVERITIES: IssueSeverity[] = ["critical", "important", "tip"];
const CATEGORIES: IssueCategory[] = ["tech_meta", "structure", "content"];
const PAGE_SIZE = 50;

interface PageProps {
  params: { id: string; crawlId: string };
  searchParams: {
    severity?: string;
    category?: string;
    q?: string;
    offset?: string;
  };
}

function parseFilter<T extends string>(value: string | undefined, allowed: readonly T[]): T | undefined {
  if (!value) return undefined;
  return (allowed as readonly string[]).includes(value) ? (value as T) : undefined;
}

function parseOffset(value: string | undefined): number {
  const n = Number(value ?? "0");
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 0;
}

export default async function CrawlDetailPage({ params, searchParams }: PageProps) {
  const projectId = Number(params.id);
  const crawlId = Number(params.crawlId);
  if (!Number.isFinite(projectId) || !Number.isFinite(crawlId)) notFound();

  const severity = parseFilter(searchParams.severity, SEVERITIES);
  const category = parseFilter(searchParams.category, CATEGORIES);
  const q = (searchParams.q ?? "").trim() || undefined;
  const offset = parseOffset(searchParams.offset);

  let project;
  let crawl;
  let summary;
  let issues;
  let allCrawls;
  try {
    [project, crawl, summary, issues, allCrawls] = await Promise.all([
      api.getProject(projectId),
      api.getCrawl(projectId, crawlId),
      api.getCrawlSummary(projectId, crawlId),
      api.listIssues(projectId, crawlId, {
        severity,
        category,
        q,
        limit: PAGE_SIZE,
        offset,
      }),
      api.listCrawls(projectId),
    ]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  // Comparison candidates: every other completed crawl of this project,
  // most recent first.
  const compareCandidates = allCrawls.filter(
    (c) => c.id !== crawlId && c.status === "completed",
  );

  // Build a URL relative to the current page. ``offset`` resets on every
  // filter/search change so the user doesn't end up "past the end" of a
  // narrower result set.
  const buildHref = (overrides: {
    severity?: string;
    category?: string;
    q?: string;
    offset?: number;
    /** Set true to keep current offset; otherwise it resets to 0. */
    keepOffset?: boolean;
  }): string => {
    const next = {
      severity: "severity" in overrides ? overrides.severity : severity,
      category: "category" in overrides ? overrides.category : category,
      q: "q" in overrides ? overrides.q : q,
      offset: overrides.offset ?? (overrides.keepOffset ? offset : 0),
    };
    const sp = new URLSearchParams();
    if (next.severity) sp.set("severity", next.severity);
    if (next.category) sp.set("category", next.category);
    if (next.q) sp.set("q", next.q);
    if (next.offset && next.offset > 0) sp.set("offset", String(next.offset));
    return sp.toString() ? `?${sp.toString()}` : "";
  };

  const totalPages = Math.max(1, Math.ceil(issues.total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const prevHref =
    offset > 0
      ? `/projects/${projectId}/crawls/${crawlId}${buildHref({
          offset: Math.max(0, offset - PAGE_SIZE),
        })}`
      : null;
  const nextHref =
    offset + PAGE_SIZE < issues.total
      ? `/projects/${projectId}/crawls/${crawlId}${buildHref({
          offset: offset + PAGE_SIZE,
        })}`
      : null;

  const crawlInProgress = crawl.status === "queued" || crawl.status === "running";

  return (
    <div className="space-y-6">
      <AutoRefresh enabled={crawlInProgress} intervalMs={5000} />
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">
            <Link href={`/projects/${projectId}`} className="hover:underline">
              {project.name}
            </Link>
            {" / Crawl #"}
            {crawl.id}
          </p>
          <h1 className="text-2xl font-semibold">Crawl-Auswertung</h1>
          <p className="mt-1 text-sm text-slate-500">
            <Badge tone={crawl.status === "completed" ? "success" : "neutral"}>
              {statusLabel(crawl.status)}
            </Badge>{" "}
            · {crawl.pages_crawled} Seiten · gestartet {formatDate(crawl.started_at)}
            {crawl.finished_at ? ` · fertig ${formatDate(crawl.finished_at)}` : ""}
          </p>
        </div>
        {crawl.status === "completed" && (
          <div className="flex flex-wrap items-center gap-2">
            <a
              href={`/projects/${projectId}/crawls/${crawlId}/report`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-900 hover:bg-slate-100"
            >
              Report ansehen ↗
            </a>
            <a
              href={`/projects/${projectId}/crawls/${crawlId}/report.pdf`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
            >
              PDF ↓
            </a>
            <a
              href={`/projects/${projectId}/crawls/${crawlId}/issues.csv`}
              className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-900 hover:bg-slate-100"
            >
              CSV ↓
            </a>
            {compareCandidates.length > 0 && (
              <CompareSelect
                projectId={projectId}
                crawlId={crawlId}
                candidates={compareCandidates}
              />
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <ScoreCard label="Gesamt" score={crawl.score_overall} />
        <ScoreCard label="Technik & Meta" score={crawl.score_tech} />
        <ScoreCard label="Struktur" score={crawl.score_struct} />
        <ScoreCard label="Inhalt" score={crawl.score_content} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Übersicht</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-slate-500">Insgesamt:</span>
            <Badge tone="neutral">{summary.total} Findings</Badge>
            {SEVERITIES.map((s) =>
              summary.by_severity[s] ? (
                <Badge key={s} tone={s}>
                  {summary.by_severity[s]} {severityLabel(s)}
                </Badge>
              ) : null,
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-slate-500">Filter:</span>
            <Link
              href={`/projects/${projectId}/crawls/${crawlId}`}
              className={`rounded-full border px-2 py-0.5 text-xs ${
                !severity && !category && !q
                  ? "border-slate-900 text-slate-900"
                  : "border-slate-200 text-slate-500"
              }`}
            >
              alle
            </Link>
            {SEVERITIES.map((s) => (
              <Link
                key={s}
                href={`/projects/${projectId}/crawls/${crawlId}${buildHref({ severity: severity === s ? undefined : s })}`}
                className={`rounded-full border px-2 py-0.5 text-xs ${
                  severity === s ? "border-slate-900 text-slate-900" : "border-slate-200 text-slate-500"
                }`}
              >
                {severityLabel(s)}
              </Link>
            ))}
            {CATEGORIES.map((c) => (
              <Link
                key={c}
                href={`/projects/${projectId}/crawls/${crawlId}${buildHref({ category: category === c ? undefined : c })}`}
                className={`rounded-full border px-2 py-0.5 text-xs ${
                  category === c ? "border-slate-900 text-slate-900" : "border-slate-200 text-slate-500"
                }`}
              >
                {categoryLabel(c)}
              </Link>
            ))}
          </div>
          {/* Search form — submits via plain GET so we don't need a client
              component or server action. Hidden inputs preserve severity +
              category filters across submits; offset resets to 0 on every
              new query (default <input> with no value submits empty). */}
          <form
            method="get"
            action={`/projects/${projectId}/crawls/${crawlId}`}
            className="flex flex-wrap items-center gap-2 text-sm"
          >
            {severity && <input type="hidden" name="severity" value={severity} />}
            {category && <input type="hidden" name="category" value={category} />}
            <label className="text-slate-500" htmlFor="issue-search">
              Suche:
            </label>
            <input
              id="issue-search"
              type="search"
              name="q"
              defaultValue={q ?? ""}
              placeholder="Regel-ID enthält … (z.B. duplicate)"
              className="h-9 w-72 rounded-md border border-slate-300 bg-white px-3 text-sm"
            />
            <button
              type="submit"
              className="inline-flex h-9 items-center justify-center rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-900 hover:bg-slate-100"
            >
              Filtern
            </button>
            {q && (
              <Link
                href={`/projects/${projectId}/crawls/${crawlId}${buildHref({ q: undefined })}`}
                className="text-xs text-slate-500 underline"
              >
                Suche zurücksetzen
              </Link>
            )}
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            Findings ({issues.total})
            {issues.total > 0 && (
              <span className="ml-2 text-xs font-normal text-slate-500">
                {offset + 1}–{Math.min(offset + issues.items.length, issues.total)}{" "}
                · Seite {currentPage} von {totalPages}
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <IssueTable issues={issues.items} projectId={projectId} crawlId={crawlId} />
        </CardContent>
        {(prevHref || nextHref) && (
          <div className="flex items-center justify-between gap-2 border-t border-slate-200 px-5 py-3 text-sm">
            {prevHref ? (
              <Link
                href={prevHref}
                className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-3 py-1.5 font-medium text-slate-900 hover:bg-slate-100"
              >
                ← Vorherige
              </Link>
            ) : (
              <span className="text-xs text-slate-400">← Vorherige</span>
            )}
            <span className="text-xs text-slate-500">
              Seite {currentPage} von {totalPages}
            </span>
            {nextHref ? (
              <Link
                href={nextHref}
                className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-3 py-1.5 font-medium text-slate-900 hover:bg-slate-100"
              >
                Nächste →
              </Link>
            ) : (
              <span className="text-xs text-slate-400">Nächste →</span>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
