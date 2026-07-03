import { cn } from "@/lib/utils"
import { BRAND } from "@/lib/brand"

interface LogoProps {
  className?: string
  showWordmark?: boolean
  wordmarkClassName?: string
}

export function Logo({ className, showWordmark, wordmarkClassName }: LogoProps) {
  return (
    <div className="relative inline-flex items-center gap-2">
      {/* Size className applies to the icon box only, so the wordmark flows
          beside it instead of overflowing a width-constrained wrapper. */}
      <span className={cn("relative block shrink-0", className)}>
        <img
          src="/logo.svg"
          alt={`${BRAND.name} logo`}
          className="h-full w-full object-contain dark:hidden"
        />
        <img
          src="/white-logo.svg"
          alt={`${BRAND.name} logo`}
          className="h-full w-full object-contain hidden dark:block"
        />
      </span>
      {showWordmark && (
        <span
          className={cn(
            "font-semibold tracking-tight text-foreground text-lg",
            wordmarkClassName
          )}
        >
          {BRAND.name}
        </span>
      )}
    </div>
  )
}
