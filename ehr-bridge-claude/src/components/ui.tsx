"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cva, type VariantProps } from "class-variance-authority";
import { X, Inbox } from "lucide-react";
import { cn, initials } from "@/lib/utils";

/* ---------------- Button ---------------- */
export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-navy-400 focus-visible:ring-offset-1 disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-navy-800 text-white hover:bg-navy-900 shadow-sm",
        primary: "bg-[#2a5bd7] text-white hover:bg-[#2149b3] shadow-sm",
        outline: "border border-slate-200 bg-white text-slate-800 hover:bg-slate-50",
        ghost: "text-slate-700 hover:bg-slate-100",
        success: "bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm",
        danger: "bg-rose-600 text-white hover:bg-rose-700 shadow-sm",
        "danger-outline": "border border-rose-200 bg-white text-rose-700 hover:bg-rose-50",
        amber: "border border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100",
        link: "text-[#2a5bd7] underline-offset-4 hover:underline px-0",
      },
      size: { sm: "h-8 px-3 text-xs", md: "h-9 px-4", lg: "h-11 px-5 text-[15px]", icon: "h-9 w-9" },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, type = "button", ...props }, ref) => (
  <button ref={ref} type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />
));
Button.displayName = "Button";

/* ---------------- Card ---------------- */
export function Card({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-slate-200/80 bg-white shadow-card", className)} {...p} />;
}
export function CardHeader({ className, title, description, action, icon }: { className?: string; title: React.ReactNode; description?: React.ReactNode; action?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className={cn("flex items-start justify-between gap-3 px-5 pt-4 pb-3", className)}>
      <div className="flex items-start gap-2.5 min-w-0">
        {icon && <div className="mt-0.5 text-slate-500 [&_svg]:size-4">{icon}</div>}
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold text-slate-900 leading-tight">{title}</h3>
          {description && <p className="mt-0.5 text-xs text-slate-500">{description}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}
export function CardBody({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-5 pb-5", className)} {...p} />;
}

/* ---------------- Badge ---------------- */
const badgeVariants = cva("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4 whitespace-nowrap [&_svg]:size-3", {
  variants: {
    tone: {
      slate: "border-slate-200 bg-slate-50 text-slate-700",
      navy: "border-navy-200 bg-navy-50 text-navy-700",
      blue: "border-blue-200 bg-blue-50 text-blue-700",
      green: "border-emerald-200 bg-emerald-50 text-emerald-700",
      amber: "border-amber-200 bg-amber-50 text-amber-800",
      red: "border-rose-200 bg-rose-50 text-rose-700",
      violet: "border-violet-200 bg-violet-50 text-violet-700",
      teal: "border-teal-200 bg-teal-50 text-teal-700",
      outline: "border-dashed border-slate-300 bg-white text-slate-600",
    },
  },
  defaultVariants: { tone: "slate" },
});
export function Badge({ className, tone, ...p }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...p} />;
}

/* ---------------- Inputs ---------------- */
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input ref={ref} className={cn("h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-navy-300 focus:border-navy-300 disabled:bg-slate-50", className)} {...p} />
));
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...p }, ref) => (
  <textarea ref={ref} className={cn("w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-navy-300", className)} {...p} />
));
Textarea.displayName = "Textarea";

export function Select({ className, children, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn("h-9 w-full rounded-lg border border-slate-200 bg-white px-2.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-navy-300", className)} {...p}>
      {children}
    </select>
  );
}

export function Label({ className, children, hint, ...p }: React.LabelHTMLAttributes<HTMLLabelElement> & { hint?: string }) {
  return (
    <label className={cn("mb-1 block text-xs font-medium text-slate-600", className)} {...p}>
      {children}
      {hint && <span className="ml-1 font-normal text-slate-400">{hint}</span>}
    </label>
  );
}

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <Label hint={hint}>{label}</Label>
      {children}
    </div>
  );
}

export function Checkbox({ checked, onChange, label, description, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: React.ReactNode; description?: React.ReactNode; disabled?: boolean }) {
  return (
    <label className={cn("flex cursor-pointer items-start gap-2.5 rounded-lg border p-2.5 transition-colors", checked ? "border-navy-300 bg-navy-50/60" : "border-slate-200 hover:bg-slate-50", disabled && "cursor-not-allowed opacity-60")}>
      <input type="checkbox" className="mt-0.5 size-4 accent-navy-700" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span>
        <span className="block text-sm font-medium text-slate-800">{label}</span>
        {description && <span className="block text-xs text-slate-500">{description}</span>}
      </span>
    </label>
  );
}

/* ---------------- Dialog & Sheet ---------------- */
export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({ className, children, title, description, size = "md", hideClose }: { className?: string; children: React.ReactNode; title: React.ReactNode; description?: React.ReactNode; size?: "sm" | "md" | "lg" | "xl" | "full"; hideClose?: boolean }) {
  const w = { sm: "max-w-md", md: "max-w-xl", lg: "max-w-3xl", xl: "max-w-5xl", full: "max-w-[1200px]" }[size];
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-[2px] data-[state=open]:animate-in" />
      <DialogPrimitive.Content
        className={cn("fixed left-1/2 top-1/2 z-50 flex max-h-[92vh] w-[calc(100%-24px)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl focus:outline-none", w, className)}
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-4">
          <div>
            <DialogPrimitive.Title className="text-base font-semibold text-slate-900">{title}</DialogPrimitive.Title>
            {description ? <DialogPrimitive.Description className="mt-0.5 text-sm text-slate-500">{description}</DialogPrimitive.Description> : <DialogPrimitive.Description className="sr-only">Dialog</DialogPrimitive.Description>}
          </div>
          {!hideClose && (
            <DialogPrimitive.Close className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Close">
              <X className="size-5" />
            </DialogPrimitive.Close>
          )}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function Sheet({ open, onOpenChange, title, description, children, width = "max-w-3xl", headerExtra }: { open: boolean; onOpenChange: (o: boolean) => void; title: React.ReactNode; description?: React.ReactNode; children: React.ReactNode; width?: string; headerExtra?: React.ReactNode }) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-slate-900/30" />
        <DialogPrimitive.Content className={cn("fixed inset-y-0 right-0 z-40 flex w-full flex-col bg-slate-50 shadow-2xl focus:outline-none animate-slide-in", width)} onOpenAutoFocus={(e) => e.preventDefault()}>
          <div className="flex items-start justify-between gap-4 border-b border-slate-200 bg-white px-6 py-4">
            <div className="min-w-0 flex-1">
              <DialogPrimitive.Title className="text-base font-semibold text-slate-900">{title}</DialogPrimitive.Title>
              {description ? <DialogPrimitive.Description className="mt-0.5 text-sm text-slate-500">{description}</DialogPrimitive.Description> : <DialogPrimitive.Description className="sr-only">Panel</DialogPrimitive.Description>}
              {headerExtra}
            </div>
            <DialogPrimitive.Close className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Close">
              <X className="size-5" />
            </DialogPrimitive.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

/* ---------------- Tabs ---------------- */
export const Tabs = TabsPrimitive.Root;
export function TabsList({ className, ...p }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn("flex gap-1 overflow-x-auto border-b border-slate-200", className)} {...p} />;
}
export function TabsTrigger({ className, ...p }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn("-mb-px flex shrink-0 items-center gap-1.5 border-b-2 border-transparent px-3 py-2 text-sm font-medium text-slate-500 hover:text-slate-800 data-[state=active]:border-navy-700 data-[state=active]:text-navy-900 [&_svg]:size-3.5", className)}
      {...p}
    />
  );
}
export function TabsContent({ className, ...p }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content className={cn("focus:outline-none", className)} {...p} />;
}

/* ---------------- Segmented control ---------------- */
export function Segmented<T extends string>({ value, onChange, options, className }: { value: T; onChange: (v: T) => void; options: { value: T; label: React.ReactNode; count?: number }[]; className?: string }) {
  return (
    <div className={cn("inline-flex flex-wrap rounded-lg bg-slate-100 p-0.5", className)}>
      {options.map((o) => (
        <button key={o.value} type="button" onClick={() => onChange(o.value)} className={cn("flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors", value === o.value ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800")}>
          {o.label}
          {o.count !== undefined && <span className={cn("rounded-full px-1.5 text-[10px]", value === o.value ? "bg-navy-100 text-navy-800" : "bg-slate-200 text-slate-600")}>{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

/* ---------------- Misc ---------------- */
export function Progress({ value, className, tone = "navy" }: { value: number; className?: string; tone?: "navy" | "green" | "amber" }) {
  const c = { navy: "bg-navy-600", green: "bg-emerald-500", amber: "bg-amber-500" }[tone];
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-slate-100", className)}>
      <div className={cn("h-full rounded-full transition-all", c)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export function Avatar({ name, className, tone = "navy" }: { name: string; className?: string; tone?: "navy" | "teal" | "violet" | "amber" }) {
  const c = { navy: "bg-navy-100 text-navy-800", teal: "bg-teal-100 text-teal-800", violet: "bg-violet-100 text-violet-800", amber: "bg-amber-100 text-amber-800" }[tone];
  return <div className={cn("flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold", c, className)}>{initials(name)}</div>;
}

export function EmptyState({ icon, title, description, action, className }: { icon?: React.ReactNode; title: string; description?: string; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 px-6 py-10 text-center", className)}>
      <div className="mb-2 text-slate-300 [&_svg]:size-8">{icon ?? <Inbox />}</div>
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {description && <p className="mt-1 max-w-sm text-xs text-slate-500">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <span className={cn("inline-block size-4 animate-spin rounded-full border-2 border-current border-r-transparent", className)} />;
}

export function KV({ k, v, className }: { k: React.ReactNode; v: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-baseline justify-between gap-3 py-1.5 text-sm", className)}>
      <span className="text-slate-500">{k}</span>
      <span className="text-right font-medium text-slate-800">{v}</span>
    </div>
  );
}

export function Callout({ tone = "blue", icon, title, children, className }: { tone?: "blue" | "amber" | "green" | "red" | "slate"; icon?: React.ReactNode; title?: React.ReactNode; children?: React.ReactNode; className?: string }) {
  const c = {
    blue: "border-blue-200 bg-blue-50/70 text-blue-900",
    amber: "border-amber-200 bg-amber-50/80 text-amber-900",
    green: "border-emerald-200 bg-emerald-50/80 text-emerald-900",
    red: "border-rose-200 bg-rose-50/80 text-rose-900",
    slate: "border-slate-200 bg-slate-50 text-slate-700",
  }[tone];
  return (
    <div className={cn("flex gap-2.5 rounded-lg border px-3.5 py-2.5 text-sm", c, className)}>
      {icon && <div className="mt-0.5 shrink-0 [&_svg]:size-4">{icon}</div>}
      <div className="min-w-0">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={cn("text-[13px] opacity-90", title && "mt-0.5")}>{children}</div>}
      </div>
    </div>
  );
}

export function Table({ className, ...p }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn("w-full text-sm", className)} {...p} />
    </div>
  );
}
export function Th({ className, ...p }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return <th className={cn("whitespace-nowrap border-b border-slate-100 px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500", className)} {...p} />;
}
export function Td({ className, ...p }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("border-b border-slate-100 px-4 py-3 align-middle text-slate-700", className)} {...p} />;
}
