/** Small formatting helpers used in multiple page components. */

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "—";
  return `${score.toFixed(0)}%`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("de-DE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatMs(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `${n} ms`;
}

export function severityLabel(s: string): string {
  switch (s) {
    case "critical":
      return "Sehr wichtig";
    case "important":
      return "Wichtig";
    case "tip":
      return "Tipp";
    default:
      return s;
  }
}

export function categoryLabel(c: string): string {
  switch (c) {
    case "tech_meta":
      return "Technik & Meta";
    case "structure":
      return "Struktur";
    case "content":
      return "Inhalt";
    default:
      return c;
  }
}

export function statusLabel(s: string): string {
  switch (s) {
    case "queued":
      return "Eingereiht";
    case "running":
      return "Läuft";
    case "completed":
      return "Fertig";
    case "failed":
      return "Fehler";
    case "cancelled":
      return "Abgebrochen";
    default:
      return s;
  }
}
