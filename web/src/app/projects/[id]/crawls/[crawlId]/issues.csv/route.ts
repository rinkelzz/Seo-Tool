/** CSV passthrough route — propagates upstream content-type and
 * content-disposition so the browser triggers a file download.
 */

import { NextResponse } from "next/server";

import { api, ApiError } from "@/lib/api";

export const dynamic = "force-dynamic";

interface RouteParams {
  params: { id: string; crawlId: string };
}

export async function GET(_req: Request, { params }: RouteParams): Promise<Response> {
  const projectId = Number(params.id);
  const crawlId = Number(params.crawlId);
  if (!Number.isFinite(projectId) || !Number.isFinite(crawlId)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }

  try {
    const csv = await api.getCrawlIssuesCsv(projectId, crawlId);
    const headers: Record<string, string> = { "content-type": csv.contentType };
    if (csv.contentDisposition) {
      headers["content-disposition"] = csv.contentDisposition;
    }
    return new Response(csv.body, { status: 200, headers });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    return NextResponse.json(
      { error: (err as Error).message ?? "unknown error" },
      { status: 500 },
    );
  }
}
