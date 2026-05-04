/** Crawl-comparison passthrough route.
 *
 * Same pattern as the report passthrough — runs the fetch server-side so
 * the API token never ships to the browser, then returns the rendered
 * HTML with the upstream content-type.
 */

import { NextResponse } from "next/server";

import { api, ApiError } from "@/lib/api";

export const dynamic = "force-dynamic";

interface RouteParams {
  params: { id: string; crawlId: string; otherId: string };
}

export async function GET(_req: Request, { params }: RouteParams): Promise<Response> {
  const projectId = Number(params.id);
  const crawlId = Number(params.crawlId);
  const otherId = Number(params.otherId);
  if (![projectId, crawlId, otherId].every(Number.isFinite)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }

  try {
    const html = await api.getCrawlComparisonHtml(projectId, crawlId, otherId);
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
