import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatScore } from "@/lib/format";
import type { DashboardCrawl } from "@/lib/types";

/** Score colour matches the per-card colour scale used elsewhere. */
function scoreColor(score: number | null): string {
  if (score === null) return "text-slate-400";
  if (score >= 80) return "text-green-600";
  if (score >= 60) return "text-orange-600";
  return "text-red-600";
}

interface DeltaProps {
  latest: DashboardCrawl | null;
  previous: DashboardCrawl | null;
}

/** Renders the "↑ +5" / "↓ -3" / "±0" / "—" indicator. ``—`` shows up
 *  whenever we lack one of the two crawls or one of the two scores. */
function ScoreDelta({ latest, previous }: DeltaProps) {
  const a = previous?.score_overall ?? null;
  const b = latest?.score_overall ?? null;
  if (a === null || b === null) {
    return <span className="text-xs text-slate-400">—</span>;
  }
  const delta = Math.round((b - a) * 10) / 10;
  if (delta === 0) {
    return <span className="text-xs text-slate-400">±0</span>;
  }
  const up = delta > 0;
  return (
    <span className={cn("text-xs font-medium", up ? "text-green-600" : "text-red-600")}>
      {up ? "↑" : "↓"} {up ? "+" : ""}
      {delta}
    </span>
  );
}

export default async function ProjectsPage() {
  let entries;
  try {
    entries = await api.getProjectsDashboard();
  } catch (err) {
    return (
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">Projekte</h1>
        <Card>
          <CardContent>
            <p className="text-sm text-red-600">
              Backend nicht erreichbar:{" "}
              {err instanceof ApiError ? err.message : (err as Error).message}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Projekte</h1>
        <Link href="/projects/new">
          <Button>Neues Projekt</Button>
        </Link>
      </div>

      {entries.length === 0 ? (
        <Card>
          <CardContent className="text-center text-sm text-slate-500">
            Noch keine Projekte angelegt.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <Table>
            <THead>
              <TR>
                <TH>Name</TH>
                <TH>Domain</TH>
                <TH className="text-right">Gesamt</TH>
                <TH>Trend</TH>
                <TH className="text-right">Tech</TH>
                <TH className="text-right">Struktur</TH>
                <TH className="text-right">Inhalt</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {entries.map(({ project, latest_crawl, previous_crawl }) => (
                <TR key={project.id}>
                  <TD className="font-medium">{project.name}</TD>
                  <TD className="text-slate-600">{project.domain}</TD>
                  <TD className="text-right">
                    {latest_crawl ? (
                      <span
                        className={cn(
                          "font-semibold tabular-nums",
                          scoreColor(latest_crawl.score_overall),
                        )}
                      >
                        {formatScore(latest_crawl.score_overall)}
                      </span>
                    ) : (
                      <Badge tone="neutral">noch kein Crawl</Badge>
                    )}
                  </TD>
                  <TD>
                    {latest_crawl ? (
                      <ScoreDelta latest={latest_crawl} previous={previous_crawl} />
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </TD>
                  <TD className={cn("text-right text-sm tabular-nums", scoreColor(latest_crawl?.score_tech ?? null))}>
                    {latest_crawl ? formatScore(latest_crawl.score_tech) : "—"}
                  </TD>
                  <TD className={cn("text-right text-sm tabular-nums", scoreColor(latest_crawl?.score_struct ?? null))}>
                    {latest_crawl ? formatScore(latest_crawl.score_struct) : "—"}
                  </TD>
                  <TD className={cn("text-right text-sm tabular-nums", scoreColor(latest_crawl?.score_content ?? null))}>
                    {latest_crawl ? formatScore(latest_crawl.score_content) : "—"}
                  </TD>
                  <TD className="text-right">
                    <Link
                      href={`/projects/${project.id}`}
                      className="text-sm font-medium text-slate-900 hover:underline"
                    >
                      Öffnen →
                    </Link>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Card>
      )}
    </div>
  );
}
