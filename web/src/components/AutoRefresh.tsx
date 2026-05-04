"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

interface AutoRefreshProps {
  /** When false the component is a no-op — useful for conditional polling. */
  enabled: boolean;
  /** Polling interval in milliseconds. */
  intervalMs?: number;
}

/** Periodically calls ``router.refresh()`` while ``enabled`` is true.
 *
 * Used on the project detail and crawl detail pages so an in-progress
 * crawl's status updates automatically — no manual reload. The page
 * decides when to enable the polling (typically: any crawl in
 * ``queued`` or ``running`` state).
 */
export function AutoRefresh({ enabled, intervalMs = 5000 }: AutoRefreshProps) {
  const router = useRouter();
  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(() => {
      router.refresh();
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [enabled, intervalMs, router]);
  return null;
}
