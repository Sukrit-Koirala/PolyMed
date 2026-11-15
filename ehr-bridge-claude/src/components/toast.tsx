"use client";

import { create } from "zustand";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Info, AlertTriangle, XCircle } from "lucide-react";

type Tone = "success" | "info" | "warning" | "error";
interface Toast { id: number; title: string; description?: string; tone: Tone }
const useToasts = create<{ toasts: Toast[]; push: (t: Omit<Toast, "id">) => void; dismiss: (id: number) => void }>((set) => ({
  toasts: [],
  push: (t) => {
    const id = Date.now() + Math.random();
    set((s) => ({ toasts: [...s.toasts, { ...t, id }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })), 4500);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));

export const toast = (title: string, description?: string, tone: Tone = "success") => useToasts.getState().push({ title, description, tone });

export function Toaster() {
  const { toasts, dismiss } = useToasts();
  const icon = { success: <CheckCircle2 className="size-4 text-emerald-600" />, info: <Info className="size-4 text-blue-600" />, warning: <AlertTriangle className="size-4 text-amber-600" />, error: <XCircle className="size-4 text-rose-600" /> };
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[min(380px,calc(100%-32px))] flex-col gap-2">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div key={t.id} initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8 }} onClick={() => dismiss(t.id)}
            className="pointer-events-auto flex cursor-pointer gap-2.5 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-lg">
            <div className="mt-0.5">{icon[t.tone]}</div>
            <div>
              <p className="text-sm font-medium text-slate-900">{t.title}</p>
              {t.description && <p className="mt-0.5 text-xs text-slate-500">{t.description}</p>}
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
