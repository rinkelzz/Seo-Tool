import Link from "next/link";
import { notFound } from "next/navigation";

import { triggerCrawlAction } from "@/app/actions";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { api, ApiError } from "@/lib/api";
import { formatDate, formatScore, statusLabel } from "@/lib/format";
import type { CrawlStatus } from "@/lib/types";

function statusTone(status: CrawlStatus): "neutral" | "success" | "critical" | "important" {
  switch (status) {
    case "completed":
      return "success";
    case "failed":
    case "cancelled":
      return "critical";
    case "running":
      return "important";
    default:
      return "neutral";
  }
}

interface PageProps {
  params: { id: string };
}

export default async function ProjectDetailPage({ params }: PageProps) {
  const projectId = Number(params.id);
  if (!Number.isFinite(projectId)) notFound();

  let project;
  let crawls;
  try {
    [project, crawls] = await Promise.all([
      api.getProject(projectId),
      api.listCrawls(projectId),
    ]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{project.name}</h1>
          <p className="text-sm text-slate-500">
            {project.domain} —{" "}
            <a href={project.base_url} className="hover:underline" target="_blank" rel="noreferrer">
              {project.base_url}
            </a>
          </p>
        </div>
        <form action={triggerCrawlAction}>
          <input type="hidden" name="project_id" value={projectId} />
          <Button type="submit">Neuen Crawl starten</Button>
        </form>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Crawl-Historie</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {crawls.length === 0 ? (
            <p className="px-5 py-6 text-center text-sm text-slate-500">
              Noch keine Crawls. Starte den ersten oben rechts.
            </p>
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>#</TH>
                  <TH>Status</TH>
                  <TH>Seiten</TH>
                  <TH>Score</TH>
                  <TH>Tech</TH>
                  <TH>Struktur</TH>
                  <TH>Inhalt</TH>
                  <TH>Gestartet</TH>
                  <TH />
                </TR>
              </THead>
              <TBody>
                {crawls.map((c) => (
                  <TR key={c.id}>
                    <TD className="font-mono text-xs text-slate-500">#{c.id}</TD>
                    <TD>
                      <Badge tone={statusTone(c.status)}>{statusLabel(c.status)}</Badge>
                    </TD>
                    <TD>{c.pages_crawled}</TD>
                    <TD className="font-medium">{formatScore(c.score_overall)}</TD>
                    <TD className="text-slate-600">{formatScore(c.score_tech)}</TD>
                    <TD className="text-slate-600">{formatScore(c.score_struct)}</TD>
                    <TD className="text-slate-600">{formatScore(c.score_content)}</TD>
                    <TD className="text-slate-500">{formatDate(c.started_at)}</TD>
                    <TD className="text-right">
                      {c.status === "completed" ? (
                        <Link
                          href={`/projects/${projectId}/crawls/${c.id}`}
                          className="text-sm font-medium text-slate-900 hover:underline"
                        >
                          Details →
                        </Link>
                      ) : c.error_message ? (
                        <span className="text-xs text-red-600">{c.error_message}</span>
                      ) : null}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
