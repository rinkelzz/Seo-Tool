"use client";

import { useState, useTransition } from "react";

import { updateProjectScheduleAction } from "@/app/actions";
import { formatDate } from "@/lib/format";

interface ScheduleEditorProps {
  projectId: number;
  currentInterval: number | null;
  nextScheduledAt: string | null;
}

interface Option {
  value: string; // form-friendly: "" for null, otherwise minutes as string
  label: string;
}

const OPTIONS: Option[] = [
  { value: "", label: "Nur manuell" },
  { value: "60", label: "Stündlich" },
  { value: "360", label: "Alle 6 Stunden" },
  { value: "720", label: "Alle 12 Stunden" },
  { value: "1440", label: "Täglich" },
  { value: "10080", label: "Wöchentlich" },
];

/** Inline schedule picker on the project detail page. Selecting a new value
 * fires the server action and the page revalidates — no save button, no
 * confirmation step. The status messages live next to the dropdown. */
export function ScheduleEditor({
  projectId,
  currentInterval,
  nextScheduledAt,
}: ScheduleEditorProps) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  // Find the closest standard option; custom intervals (set via raw PATCH)
  // are still selectable through the option below.
  const knownValues = new Set(OPTIONS.map((o) => o.value));
  const currentValue = currentInterval === null ? "" : String(currentInterval);
  const isCustom = currentInterval !== null && !knownValues.has(currentValue);
  const customLabel = isCustom ? `Eigenes Intervall (${currentInterval} min)` : null;

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const next = e.target.value === "" ? null : Number(e.target.value);
    setError(null);
    startTransition(async () => {
      const result = await updateProjectScheduleAction(projectId, next);
      if (result?.error) {
        setError(result.error);
      } else {
        setSavedAt(Date.now());
      }
    });
  }

  return (
    <div className="inline-flex items-center gap-2">
      <select
        value={currentValue}
        onChange={handleChange}
        disabled={pending}
        className="h-8 rounded-md border border-slate-300 bg-white px-2 text-sm disabled:opacity-50"
      >
        {OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
        {isCustom && customLabel ? (
          <option value={currentValue}>{customLabel}</option>
        ) : null}
      </select>
      {currentInterval !== null && nextScheduledAt && !error ? (
        <span className="text-xs text-slate-500">
          nächster: {formatDate(nextScheduledAt)}
        </span>
      ) : null}
      {pending ? (
        <span className="text-xs text-slate-400">speichern…</span>
      ) : savedAt ? (
        <span className="text-xs text-green-600">gespeichert</span>
      ) : null}
      {error ? <span className="text-xs text-red-600">{error}</span> : null}
    </div>
  );
}
