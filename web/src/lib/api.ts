/** Server-side API client for the FastAPI backend.
 *
 * This module is *server-only*. It reads ``API_URL`` and ``API_TOKEN`` from
 * env at request time and never ships either to the browser. Pages call it
 * inside React Server Components or server actions.
 */

import "server-only";

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

export const api = {
  // ---- projects ----
  listProjects: () => request<Project[]>("/api/projects"),
  getProject: (id: number) => request<Project>(`/api/projects/${id}`),
  createProject: (input: ProjectCreate) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(input) }),

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
};

export { ApiError };
