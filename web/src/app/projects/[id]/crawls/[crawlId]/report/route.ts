/** Report passthrough route.
 *
 * The browser cannot directly hit ``/api/projects/.../report.html`` on the
 * backend because that requires a Bearer token. Instead the user clicks a
 * link to this route, which runs server-side (so it can use the API_TOKEN),
 * fetches the rendered HTML from FastAPI, and returns it as-is. The
 * resulting page is fully self-contained (embedded CSS, no JS) — perfect
 * for printing or saving as PDF from the browser until Phase 7-B adds
 * native PDF rendering.
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
    const html = await api.getCrawlReportHtml(projectId, crawlId);
    return new Response(html, {
      status: 200,
      headers: { "content-type": "text/html; charset=utf-8" },
    });
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
