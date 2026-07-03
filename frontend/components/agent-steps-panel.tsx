import type { AgentStep } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { CheckCircle2, Loader2, Search, Sparkles, ListTree } from "lucide-react";

const ACTION_ICONS = {
  plan: ListTree,
  search: Search,
  synthesize: Sparkles,
} as const;

interface AgentStepsPanelProps {
  steps: AgentStep[];
  className?: string;
}

export function AgentStepsPanel({ steps, className }: AgentStepsPanelProps) {
  if (steps.length === 0) return null;

  return (
    <div
      className={cn(
        "rounded-xl border border-primary/20 bg-primary/5 p-3 space-y-2",
        className
      )}
    >
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary">
        <Sparkles className="w-3.5 h-3.5" />
        Research Agent
      </div>
      <ol className="space-y-2">
        {steps.map((step) => {
          const Icon = ACTION_ICONS[step.action] ?? Sparkles;
          const isRunning = step.status === "running";

          return (
            <li
              key={`${step.id}-${step.action}-${step.status}`}
              className="flex items-start gap-2.5 text-sm"
            >
              <div
                className={cn(
                  "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full",
                  isRunning ? "bg-primary/20 text-primary" : "bg-primary/15 text-primary"
                )}
              >
                {isRunning ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <CheckCircle2 className="w-3 h-3" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 font-medium capitalize text-foreground/90">
                  <Icon className="w-3.5 h-3.5 text-muted-foreground" />
                  {step.action}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                  {step.detail}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
