import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-[var(--brand-ink)] !text-white hover:bg-black hover:!text-white visited:!text-white",
        outline: "border border-[var(--line)] bg-white !text-[var(--text)] hover:bg-[var(--surface)] hover:!text-[var(--text)] visited:!text-[var(--text)]",
        ghost: "!text-[var(--text)] hover:bg-[var(--surface)] hover:!text-[var(--text)] visited:!text-[var(--text)]",
        secondary: "bg-[var(--surface)] !text-[var(--text)] hover:bg-[#f2f2f0] hover:!text-[var(--text)] visited:!text-[var(--text)]",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3",
        lg: "h-10 rounded-md px-6",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

function Button({
  className,
  variant,
  size,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants>) {
  return <button className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}

export { Button, buttonVariants };
