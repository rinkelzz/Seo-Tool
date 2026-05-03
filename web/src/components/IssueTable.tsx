import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/Table";
import { categoryLabel, severityLabel } from "@/lib/format";
import type { Issue, IssueSeverity } from "@/lib/types";

function severityTone(s: IssueSeverity): "critical" | "important" | "tip" {
  return s;
}

interface IssueTableProps {
  issues: Issue[];
  projectId: number;
  crawlId: number;
}

export function IssueTable({ issues, projectId, crawlId }: IssueTableProps) {
  if (issues.length === 0) {
    return (
      <p className="px-5 py-8 text-center text-sm text-slate-500">
        Keine Findings für diese Filter.
      </p>
    );
  }

  return (
    <Table>
      <THead>
        <TR>
          <TH>Severity</TH>
          <TH>Kategorie</TH>
          <TH>Regel</TH>
          <TH>Seite</TH>
          <TH>Details</TH>
        </TR>
      </THead>
      <TBody>
        {issues.map((issue) => (
          <TR key={issue.id}>
            <TD>
              <Badge tone={severityTone(issue.severity)}>{severityLabel(issue.severity)}</Badge>
            </TD>
            <TD className="text-slate-600">{categoryLabel(issue.category)}</TD>
            <TD className="font-mono text-xs">{issue.rule_id}</TD>
            <TD>
              {issue.page_id ? (
                <Link
                  href={`/projects/${projectId}/crawls/${crawlId}/pages/${issue.page_id}`}
                  className="text-sm text-slate-900 hover:underline"
                >
                  Seite öffnen
                </Link>
              ) : (
                <span className="text-xs text-slate-400">projektweit</span>
              )}
            </TD>
            <TD className="max-w-md text-xs text-slate-500">
              {issue.payload && Object.keys(issue.payload).length > 0 ? (
                <code className="whitespace-pre-wrap break-words">
                  {JSON.stringify(issue.payload)}
                </code>
              ) : (
                "—"
              )}
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
