"use client";

import { useEffect } from "react";
import { useApp } from "@/lib/store";
import { useHydrated } from "@/lib/hooks";
import { Toaster } from "./toast";
import { Logo } from "./logo";

/**
 * Keeps state in sync across browser tabs (e.g. doctor in one tab, patient in
 * another) and avoids SSR/localStorage hydration mismatches by rendering the
 * client app only after hydration.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const hydrated = useHydrated();
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === "ehr-bridge-state-v1") useApp.persist.rehydrate();
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  if (!hydrated)
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex animate-pulse items-center gap-2 text-slate-400">
          <Logo className="size-7" />
          <span className="text-sm">Loading EHR Bridge…</span>
        </div>
      </div>
    );
  return (
    <>
      {children}
      <Toaster />
    </>
  );
}
