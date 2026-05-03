import { Card, CardContent } from "@/components/ui/Card";
import { cn } from "@/lib/cn";

function scoreColor(score: number | null): string {
  if (score === null) return "text-slate-400";
  if (score >= 80) return "text-green-600";
  if (score >= 60) return "text-orange-600";
  return "text-red-600";
}

interface ScoreCardProps {
  label: string;
  score: number | null;
}

export function ScoreCard({ label, score }: ScoreCardProps) {
  return (
    <Card>
      <CardContent>
        <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
        <p className={cn("mt-2 text-3xl font-semibold tabular-nums", scoreColor(score))}>
          {score === null ? "—" : `${score.toFixed(0)}%`}
        </p>
      </CardContent>
    </Card>
  );
}
