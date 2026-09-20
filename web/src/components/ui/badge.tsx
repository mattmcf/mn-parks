import { cn } from "@/lib/utils"

export function Badge({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-[hsl(var(--border))] bg-[hsl(var(--secondary))] px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-[hsl(var(--secondary-foreground))]",
        className,
      )}
      {...props}
    />
  )
}
