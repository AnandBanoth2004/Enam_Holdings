import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const variants = {
  neutral: "border-line bg-surface-muted text-ink-secondary",
  brand: "border-brand/15 bg-brand-tint text-brand",
  info: "border-info/15 bg-info-tint text-info",
  positive: "border-positive/15 bg-positive-tint text-positive",
  negative: "border-negative/15 bg-negative-tint text-negative",
  caution: "border-caution/15 bg-caution-tint text-caution",
} as const;

export function Badge({
  className,
  variant = "neutral",
  ...props
}: HTMLAttributes<HTMLSpanElement> & {
  variant?: keyof typeof variants;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold leading-4",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
