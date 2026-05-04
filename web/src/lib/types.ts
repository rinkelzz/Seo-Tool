/** API types — kept hand-written to match the Pydantic schemas in backend/app/schemas. */

export type IssueCategory = "tech_meta" | "structure" | "content";
export type IssueSeverity = "critical" | "important" | "tip";
export type CrawlStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface Project {
  id: number;
  name: string;
  domain: string;
  base_url: string;
  robots_respect: boolean;
  js_render: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  domain: string;
  base_url: string;
  robots_respect?: boolean;
  js_render?: boolean;
}

export interface Crawl {
  id: number;
  project_id: number;
  status: CrawlStatus;
  started_at: string | null;
  finished_at: string | null;
  pages_crawled: number;
  error_message: string | null;
  score_tech: number | null;
  score_struct: number | null;
  score_content: number | null;
  score_overall: number | null;
  created_at: string;
}

export interface IssueCount {
  rule_id: string;
  category: IssueCategory;
  severity: IssueSeverity;
  count: number;
}

export interface CrawlSummary {
  by_category: Partial<Record<IssueCategory, number>>;
  by_severity: Partial<Record<IssueSeverity, number>>;
  by_rule: IssueCount[];
  total: number;
}

export interface Issue {
  id: number;
  crawl_id: number;
  page_id: number | null;
  rule_id: string;
  category: IssueCategory;
  severity: IssueSeverity;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface IssueListResponse {
  items: Issue[];
  total: number;
  limit: number;
  offset: number;
}

export interface PageRow {
  id: number;
  crawl_id: number;
  url: string;
  status_code: number | null;
  response_time_ms: number | null;
  content_type: string | null;
  html_size: number | null;
  title: string | null;
  meta_description: string | null;
  h1: string | null;
  language: string | null;
  word_count: number | null;
  depth: number | null;
  is_indexable: boolean | null;
  fetch_error: string | null;
  created_at: string;
}

export interface ImageRow {
  id: number;
  src: string;
  alt: string | null;
  has_alt: boolean;
}

export interface LinkRow {
  id: number;
  target_url: string;
  anchor_text: string | null;
  rel: string | null;
  is_internal: boolean;
  is_followed: boolean;
  target_status_code: number | null;
}

export type ResourceType = "stylesheet" | "script" | "image";

export interface ResourceRow {
  id: number;
  url: string;
  resource_type: ResourceType;
  is_internal: boolean;
  is_mixed_content: boolean;
  status_code: number | null;
  probe_error: string | null;
}

export interface PageDetail extends PageRow {
  canonical_url: string | null;
  meta_robots: string | null;
  redirect_chain: string[] | null;
  images: ImageRow[];
  links: LinkRow[];
  resources: ResourceRow[];
  issues: Issue[];
}

export interface SitemapRow {
  id: number;
  project_id: number;
  url: string;
  last_fetched_at: string | null;
  urls_count: number;
  fetch_error: string | null;
}

export interface PageListResponse {
  items: PageRow[];
  total: number;
  limit: number;
  offset: number;
}
