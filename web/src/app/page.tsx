import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";

export default async function ProjectsPage() {
  let projects;
  try {
    projects = await api.listProjects();
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

      {projects.length === 0 ? (
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
                <TH>Robots</TH>
                <TH>Angelegt</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {projects.map((p) => (
                <TR key={p.id}>
                  <TD className="font-medium">{p.name}</TD>
                  <TD className="text-slate-600">{p.domain}</TD>
                  <TD>
                    <Badge tone={p.robots_respect ? "success" : "neutral"}>
                      {p.robots_respect ? "respektiert" : "ignoriert"}
                    </Badge>
                  </TD>
                  <TD className="text-slate-500">{formatDate(p.created_at)}</TD>
                  <TD className="text-right">
                    <Link
                      href={`/projects/${p.id}`}
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
