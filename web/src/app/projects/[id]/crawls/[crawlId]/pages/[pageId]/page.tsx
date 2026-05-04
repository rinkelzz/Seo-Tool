import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { IssueTable } from "@/components/IssueTable";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { api, ApiError } from "@/lib/api";
import { formatBytes, formatMs } from "@/lib/format";

interface PageProps {
  params: { id: string; crawlId: string; pageId: string };
}

function metaRow(label: string, value: ReactNode) {
  return (
    <div className="grid grid-cols-3 gap-2 border-b border-slate-100 py-2 text-sm last:border-b-0">
      <dt className="text-slate-500">{label}</dt>
      <dd className="col-span-2 break-words text-slate-900">{value ?? "—"}</dd>
    </div>
  );
}

export default async function PageDetailPage({ params }: PageProps) {
  const projectId = Number(params.id);
  const crawlId = Number(params.crawlId);
  const pageId = Number(params.pageId);
  if (!Number.isFinite(projectId) || !Number.isFinite(crawlId) || !Number.isFinite(pageId)) {
    notFound();
  }

  let page;
  try {
    page = await api.getPage(projectId, crawlId, pageId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">
          <Link
            href={`/projects/${projectId}/crawls/${crawlId}`}
            className="hover:underline"
          >
            ← zurück zur Crawl-Übersicht
          </Link>
        </p>
        <h1 className="mt-1 break-all text-2xl font-semibold">{page.url}</h1>
        <p className="mt-1 text-sm text-slate-500">
          {page.status_code !== null && (
            <Badge tone={page.status_code >= 400 ? "critical" : "success"}>
              HTTP {page.status_code}
            </Badge>
          )}
          {" · "}Tiefe {page.depth ?? "—"} · {formatMs(page.response_time_ms)} ·{" "}
          {formatBytes(page.html_size)}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Meta-Daten</CardTitle>
        </CardHeader>
        <CardContent>
          <dl>
            {metaRow("Title", page.title)}
            {metaRow("Meta-Description", page.meta_description)}
            {metaRow("H1", page.h1)}
            {metaRow("Sprache", page.language)}
            {metaRow("Wortzahl", page.word_count?.toString() ?? "—")}
            {metaRow("Canonical", page.canonical_url)}
            {metaRow("Meta-Robots", page.meta_robots)}
            {metaRow(
              "Indexierbar",
              page.is_indexable === null ? "—" : page.is_indexable ? "ja" : "nein",
            )}
            {page.redirect_chain && page.redirect_chain.length > 0
              ? metaRow(
                  "Redirect-Kette",
                  <ol className="list-decimal pl-5 text-xs">
                    {page.redirect_chain.map((hop, i) => (
                      <li key={i} className="break-all">
                        {hop}
                      </li>
                    ))}
                  </ol>,
                )
              : null}
            {page.fetch_error
              ? metaRow(
                  "Fetch-Fehler",
                  <span className="text-red-600">{page.fetch_error}</span>,
                )
              : null}
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Findings ({page.issues.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <IssueTable issues={page.issues} projectId={projectId} crawlId={crawlId} />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Bilder ({page.images.length})</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {page.images.length === 0 ? (
              <p className="px-5 py-6 text-center text-sm text-slate-500">Keine Bilder.</p>
            ) : (
              <Table>
                <THead>
                  <TR>
                    <TH>src</TH>
                    <TH>alt</TH>
                  </TR>
                </THead>
                <TBody>
                  {page.images.map((img) => (
                    <TR key={img.id}>
                      <TD className="break-all text-xs">{img.src}</TD>
                      <TD>
                        {img.has_alt ? (
                          <span className="text-xs">{img.alt}</span>
                        ) : (
                          <Badge tone="critical">fehlt</Badge>
                        )}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Ausgehende Links ({page.links.length})</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {page.links.length === 0 ? (
              <p className="px-5 py-6 text-center text-sm text-slate-500">Keine Links.</p>
            ) : (
              <Table>
                <THead>
                  <TR>
                    <TH>Ziel</TH>
                    <TH>Anker</TH>
                    <TH>Status</TH>
                  </TR>
                </THead>
                <TBody>
                  {page.links.map((link) => (
                    <TR key={link.id}>
                      <TD className="max-w-xs truncate text-xs">{link.target_url}</TD>
                      <TD className="text-xs">{link.anchor_text || "—"}</TD>
                      <TD>
                        {link.target_status_code === null ? (
                          <Badge tone={link.is_internal ? "success" : "neutral"}>
                            {link.is_internal ? "intern" : "extern"}
                          </Badge>
                        ) : link.target_status_code >= 400 ? (
                          <Badge tone="critical">HTTP {link.target_status_code}</Badge>
                        ) : (
                          <Badge tone="success">HTTP {link.target_status_code}</Badge>
                        )}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Eingebundene Ressourcen ({page.resources.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {page.resources.length === 0 ? (
            <p className="px-5 py-6 text-center text-sm text-slate-500">
              Keine CSS/JS/Bild-Ressourcen entdeckt.
            </p>
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Typ</TH>
                  <TH>URL</TH>
                  <TH>Status</TH>
                  <TH>Hinweis</TH>
                </TR>
              </THead>
              <TBody>
                {page.resources.map((res) => (
                  <TR key={res.id}>
                    <TD>
                      <Badge tone="neutral">{res.resource_type}</Badge>
                    </TD>
                    <TD className="break-all text-xs">{res.url}</TD>
                    <TD>
                      {res.status_code === null ? (
                        res.probe_error ? (
                          <Badge tone="critical">unreachable</Badge>
                        ) : (
                          <Badge tone="neutral">—</Badge>
                        )
                      ) : res.status_code >= 400 ? (
                        <Badge tone="critical">HTTP {res.status_code}</Badge>
                      ) : (
                        <Badge tone="success">HTTP {res.status_code}</Badge>
                      )}
                    </TD>
                    <TD>
                      {res.is_mixed_content ? (
                        <Badge tone="critical">mixed-content</Badge>
                      ) : res.is_internal ? (
                        <span className="text-xs text-slate-500">intern</span>
                      ) : (
                        <span className="text-xs text-slate-500">extern</span>
                      )}
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
