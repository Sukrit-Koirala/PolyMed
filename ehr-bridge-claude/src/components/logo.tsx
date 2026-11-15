import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-8", className)} aria-hidden>
      <rect width="32" height="32" rx="8" fill="#17223a" />
      <path d="M7 20c3-6 6-9 9-9s6 3 9 9" fill="none" stroke="#7fb3ff" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M9 22.5h14" stroke="#ffffff" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M16 8v4M14 10h4" stroke="#5ee0a8" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function Wordmark({ className, light }: { className?: string; light?: boolean }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <Logo className="size-8" />
      <div className="leading-tight">
        <div className={cn("text-[15px] font-semibold tracking-tight", light ? "text-white" : "text-navy-900")}>EHR Bridge</div>
        <div className={cn("text-[10px]", light ? "text-navy-200" : "text-slate-500")}>Your EHR holds the data.</div>
      </div>
    </div>
  );
}
