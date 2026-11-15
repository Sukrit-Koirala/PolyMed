"use client";

import Link from "next/link";
import { ShieldX } from "lucide-react";
import { useAuth } from "@/lib/store";
import type { Role } from "@/lib/types";
import { buttonVariants } from "./ui";

export function RoleGuard({ role, children }: { role: Role; children: React.ReactNode }) {
  const user = useAuth((s) => s.user);
  if (!user || user.role !== role) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-card">
          <ShieldX className="mx-auto size-10 text-rose-500" />
          <h1 className="mt-3 text-lg font-semibold text-slate-900">Not authorized</h1>
          <p className="mt-1 text-sm text-slate-500">
            {user ? `You're signed in as ${user.name} (${user.role}). This area is only available to ${role} accounts.` : "Please sign in with a demo account to continue."}
          </p>
          <p className="mt-2 text-xs text-slate-400">Demo security simulation — route checks run in the browser.</p>
          <Link href="/" className={buttonVariants({ className: "mt-5" })}>Go to sign-in</Link>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
