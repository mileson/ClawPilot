import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        default: "border-transparent bg-[var(--text)] text-white",
        active: "border-emerald-300 bg-emerald-50 text-emerald-700",
        probation: "border-amber-300 bg-amber-50 text-amber-700",
        suspended: "border-rose-300 bg-rose-50 text-rose-700",
        neutral: "border-[var(--line)] bg-[var(--surface)] text-[var(--muted)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
