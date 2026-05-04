"use client";

import { useRouter } from "next/navigation";

import { formatDate } from "@/lib/format";
import type { Crawl } from "@/lib/types";

interface CompareSelectProps {
  projectId: number;
  crawlId: number;
  candidates: Crawl[];
}

/** Dropdown for picking another crawl to compare against — when the user
 * selects an option we navigate to the comparison passthrough route. */
export function CompareSelect({ projectId, crawlId, candidates }: CompareSelectProps) {
  const router = useRouter();

  return (
    <div className="inline-flex items-center gap-1">
      <label className="sr-only" htmlFor="compare-select">
        Vergleichen mit
      </label>
      <select
        id="compare-select"
        className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
        defaultValue=""
        onChange={(e) => {
          const v = e.currentTarget.value;
          if (v) {
            router.push(`/projects/${projectId}/crawls/${crawlId}/compare/${v}`);
          }
        }}
      >
        <option value="" disabled>
          Vergleichen mit…
        </option>
        {candidates.map((c) => (
          <option key={c.id} value={c.id}>
            Crawl #{c.id}
            {c.started_at ? ` · ${formatDate(c.started_at)}` : ""}
          </option>
        ))}
      </select>
    </div>
  );
}
