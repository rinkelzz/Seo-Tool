import Link from "next/link";
import { notFound } from "next/navigation";

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

interface PageProps {
  params: { id: string; crawlId: string };
  searchParams: { severity?: string; category?: string };
}

function parseFilter<T extends string>(value: string | undefined, allowed: readonly T[]): T | undefined {
  if (!value) return undefined;
  return (allowed as readonly string[]).includes(value) ? (value as T) : undefined;
}

export default async function CrawlDetailPage({ params, searchParams }: PageProps) {
  const projectId = Number(params.id);
  const crawlId = Number(params.crawlId);
  if (!Number.isFinite(projectId) || !Number.isFinite(crawlId)) notFound();

  const severity = parseFilter(searchParams.severity, SEVERITIES);
  const category = parseFilter(searchParams.category, CATEGORIES);

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
      api.listIssues(projectId, crawlId, { severity, category, limit: 200 }),
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

  const filterHref = (overrides: { severity?: string; category?: string }): string => {
    const next = { severity, category, ...overrides };
    const sp = new URLSearchParams();
    if (next.severity) sp.set("severity", next.severity);
    if (next.category) sp.set("category", next.category);
    return sp.toString() ? `?${sp.toString()}` : "";
  };

  return (
    <div className="space-y-6">
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
                !severity && !category ? "border-slate-900 text-slate-900" : "border-slate-200 text-slate-500"
              }`}
            >
              alle
            </Link>
            {SEVERITIES.map((s) => (
              <Link
                key={s}
                href={`/projects/${projectId}/crawls/${crawlId}${filterHref({ severity: severity === s ? undefined : s })}`}
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
                href={`/projects/${projectId}/crawls/${crawlId}${filterHref({ category: category === c ? undefined : c })}`}
                className={`rounded-full border px-2 py-0.5 text-xs ${
                  category === c ? "border-slate-900 text-slate-900" : "border-slate-200 text-slate-500"
                }`}
              >
                {categoryLabel(c)}
              </Link>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            Findings ({issues.total}
            {issues.total > issues.items.length ? ` — zeige ${issues.items.length}` : ""})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <IssueTable issues={issues.items} projectId={projectId} crawlId={crawlId} />
        </CardContent>
      </Card>
    </div>
  );
}
