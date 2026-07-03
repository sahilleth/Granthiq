import type { ConfidenceMetadata } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { AlertTriangle, CheckCircle2, HelpCircle, ShieldAlert } from "lucide-react";

const LEVEL_STYLES: Record<
  ConfidenceMetadata["level"],
  { className: string; icon: typeof CheckCircle2 }
> = {
  high: {
    className: "bg-primary/15 text-primary border-primary/35",
    icon: CheckCircle2,
  },
  medium: {
    className: "bg-primary/10 text-synapse-400 border-primary/25",
    icon: ShieldAlert,
  },
  low: {
    className: "bg-primary/8 text-synapse-300 border-primary/20",
    icon: AlertTriangle,
  },
  very_low: {
    className: "bg-muted text-muted-foreground border-border",
    icon: AlertTriangle,
  },
  none: {
    className: "bg-muted text-muted-foreground border-border",
    icon: HelpCircle,
  },
};

interface ConfidenceBadgeProps {
  confidence: ConfidenceMetadata;
  className?: string;
}

export function ConfidenceBadge({ confidence, className }: ConfidenceBadgeProps) {
  const style = LEVEL_STYLES[confidence.level] ?? LEVEL_STYLES.none;
  const Icon = style.icon;

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border",
        style.className,
        className
      )}
      title={`Max score: ${(confidence.max_score * 100).toFixed(0)}% · Avg: ${(confidence.avg_score * 100).toFixed(0)}% · ${confidence.source_count} sources`}
    >
      <Icon className="w-3.5 h-3.5 shrink-0" />
      <span>{confidence.label}</span>
      {confidence.source_count > 0 && (
        <span className="opacity-70">· {confidence.source_count} sources</span>
      )}
    </div>
  );
}
