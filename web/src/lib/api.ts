/** Server-side API client for the FastAPI backend.
 *
 * This module is *server-only*. It reads ``API_URL`` and ``API_TOKEN`` from
 * env at request time and never ships either to the browser. Pages call it
 * inside React Server Components or server actions.
 */

import "server-only";

import { unstable_noStore as noStore } from "next/cache";

import type {
  Crawl,
  CrawlSummary,
  IssueCategory,
  IssueListResponse,
  IssueSeverity,
  PageDetail,
  PageListResponse,
  Project,
  ProjectCreate,
  SitemapRow,
} from "@/lib/types";

const DEFAULT_API_URL = "http://backend:8000";

function apiUrl(): string {
  return process.env.API_URL ?? DEFAULT_API_URL;
}

function apiToken(): string {
  const token = process.env.API_TOKEN;
  if (!token) {
    throw new Error(
      "API_TOKEN env var is not set — the frontend cannot authenticate against the backend.",
    );
  }
  return token;
}

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  query?: Record<string, string | number | boolean | undefined>,
): Promise<T> {
  // Mark the calling RSC as dynamic — must run BEFORE apiToken() can throw,
  // otherwise Next.js will static-render the page during `next build`, the
  // missing-token error gets caught by the page's try/catch, and the
  // resulting "Backend nicht erreichbar" HTML is baked into the bundle.
  // Runtime env vars then have no effect. ``cache: "no-store"`` on the
  // fetch below isn't sufficient on its own because the fetch never runs
  // when an earlier statement throws.
  noStore();

  const url = new URL(path, apiUrl());
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== "") {
        url.searchParams.set(k, String(v));
      }
    }
  }

  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${apiToken()}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(url, { ...init, headers, cache: "no-store" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, `${res.status} ${res.statusText}: ${text}`.trim());
  }
  // 204 has no body
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Fetch a non-JSON resource (HTML/PDF) and return the raw text body.
 *
 * Same auth + dynamic-rendering treatment as ``request<T>``. Used by the
 * report passthrough route — keeps the API token server-only.
 */
async function requestText(path: string, init: RequestInit = {}): Promise<string> {
  noStore();
  const url = new URL(path, apiUrl());
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${apiToken()}`);
  const res = await fetch(url, { ...init, headers, cache: "no-store" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, `${res.status} ${res.statusText}: ${text}`.trim());
  }
  return await res.text();
}

/** Fetch a binary resource (PDF) and return the raw bytes plus the
 * upstream Content-Type / Content-Disposition headers so the passthrough
 * route can forward them to the browser unchanged.
 */
async function requestBinary(
  path: string,
  init: RequestInit = {},
): Promise<{ body: ArrayBuffer; contentType: string; contentDisposition: string | null }> {
  noStore();
  const url = new URL(path, apiUrl());
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${apiToken()}`);
  const res = await fetch(url, { ...init, headers, cache: "no-store" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, `${res.status} ${res.statusText}: ${text}`.trim());
  }
  return {
    body: await res.arrayBuffer(),
    contentType: res.headers.get("content-type") ?? "application/octet-stream",
    contentDisposition: res.headers.get("content-disposition"),
  };
}

export const api = {
  // ---- projects ----
  listProjects: () => request<Project[]>("/api/projects"),
  getProject: (id: number) => request<Project>(`/api/projects/${id}`),
  createProject: (input: ProjectCreate) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(input) }),
  updateProject: (id: number, patch: Partial<ProjectCreate>) =>
    request<Project>(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  // ---- crawls ----
  listCrawls: (projectId: number) =>
    request<Crawl[]>(`/api/projects/${projectId}/crawls`),
  getCrawl: (projectId: number, crawlId: number) =>
    request<Crawl>(`/api/projects/${projectId}/crawls/${crawlId}`),
  triggerCrawl: (projectId: number) =>
    request<Crawl>(`/api/projects/${projectId}/crawls`, { method: "POST" }),
  getCrawlSummary: (projectId: number, crawlId: number) =>
    request<CrawlSummary>(`/api/projects/${projectId}/crawls/${crawlId}/summary`),

  // ---- issues ----
  listIssues: (
    projectId: number,
    crawlId: number,
    filters: {
      severity?: IssueSeverity;
      category?: IssueCategory;
      rule_id?: string;
      page_id?: number;
      limit?: number;
      offset?: number;
    } = {},
  ) =>
    request<IssueListResponse>(
      `/api/projects/${projectId}/crawls/${crawlId}/issues`,
      {},
      filters,
    ),

  // ---- pages ----
  listPages: (
    projectId: number,
    crawlId: number,
    filters: { has_issues?: boolean; status_code?: number; limit?: number; offset?: number } = {},
  ) =>
    request<PageListResponse>(
      `/api/projects/${projectId}/crawls/${crawlId}/pages`,
      {},
      filters,
    ),
  getPage: (projectId: number, crawlId: number, pageId: number) =>
    request<PageDetail>(
      `/api/projects/${projectId}/crawls/${crawlId}/pages/${pageId}`,
    ),

  // ---- sitemaps ----
  listSitemaps: (projectId: number) =>
    request<SitemapRow[]>(`/api/projects/${projectId}/sitemaps`),

  // ---- reports ----
  getCrawlReportHtml: (projectId: number, crawlId: number) =>
    requestText(`/api/projects/${projectId}/crawls/${crawlId}/report.html`),
  getCrawlReportPdf: (projectId: number, crawlId: number) =>
    requestBinary(`/api/projects/${projectId}/crawls/${crawlId}/report.pdf`),
  getCrawlComparisonHtml: (projectId: number, crawlId: number, otherId: number) =>
    requestText(
      `/api/projects/${projectId}/crawls/${crawlId}/compare/${otherId}.html`,
    ),
  getCrawlIssuesCsv: (projectId: number, crawlId: number) =>
    requestBinary(`/api/projects/${projectId}/crawls/${crawlId}/issues.csv`),
};

export { ApiError };
