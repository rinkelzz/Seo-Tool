/** PDF report passthrough.
 *
 * Browser cannot directly authenticate against the FastAPI ``report.pdf``
 * endpoint, so we run the fetch server-side, propagate ``content-type``
 * and ``content-disposition`` from the upstream response, and serve the
 * raw bytes back to the browser.
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
    const pdf = await api.getCrawlReportPdf(projectId, crawlId);
    const headers: Record<string, string> = { "content-type": pdf.contentType };
    if (pdf.contentDisposition) {
      headers["content-disposition"] = pdf.contentDisposition;
    }
    return new Response(pdf.body, { status: 200, headers });
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
